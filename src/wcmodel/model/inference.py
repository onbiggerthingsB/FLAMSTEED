"""Backend dispatch (seeded) + the ADVI-falsely-tight calibration check.

ADVI mean-field underestimates posterior variance, and downstream we depend on
posterior WIDTH (provisional-widening + Phase-4 stake sizing). The periodic NUTS
fit is the reference: ``advi_variance_check`` flags any parameter whose ADVI 94%
HDI width is materially below NUTS (a calibration issue, surfaced -- never
silent).

API provenance (verified against the INSTALLED pymc 6.0.1 / arviz 1.1.0; these
deviate from the older-arviz idioms in the task spec):

* ADVI seeding -- ``pm.fit(method="advi", random_seed=seed)`` returns a
  ``MeanField`` approximation; ``approx.sample(draws, random_seed=seed)`` then
  draws from it. Passing ``random_seed`` to BOTH the fit and the sample makes two
  full runs bit-identical (verified: delta 0.0 at atol 1e-6). Reproducibility is
  a hard project invariant, so both seeds are threaded.

* ``az.hdi`` -- arviz 1.1.0 migrated InferenceData to xarray's DataTree. ``az.hdi``
  takes ``prob=`` (not ``hdi_prob=``) and returns a DataTree whose bound
  coordinate is ``ci_bound`` with values ``"lower"`` / ``"upper"`` (NOT a ``hdi``
  dim with ``"lower"`` / ``"higher"`` as in older arviz). ``_hdi_width`` reads
  those coords accordingly.

* ``pathfinder`` -- ``pm.fit`` in pymc 6.0.1 only supports
  ``{advi, fullrank_advi, svgd, asvgd}``; there is no ``method="pathfinder"`` and
  neither ``pymc_experimental`` nor ``nutpie`` is installed. The branch therefore
  raises a clear, actionable ``NotImplementedError`` rather than crashing with a
  cryptic ``KeyError`` from ``pm.fit``.

P5 inference-upgrade additions (this file is the SINGLE backend-dispatch seam):

* ``fullrank_advi`` -- PyMC's FULL-RANK ADVI (``pm.fit(method="fullrank_advi")``).
  No new dependency (it is a stock ``pm.fit`` method, verified present in the
  installed pymc 6.0.1). It models a full posterior covariance, so it does NOT
  share mean-field's variance-underestimation failure mode -- the motivation for
  offering it as a cheap middle rung between ``advi`` and ``nuts``. Seeded in BOTH
  fit and draw exactly like ``advi``.

* ``nuts`` -- now accepts ``chains`` / ``target_accept`` (and the existing
  ``tune``) so the comparison harness can drive production-fidelity NUTS. The
  SAMPLER ENGINE is selected by ``_resolve_nuts_sampler``: prefer ``nutpie`` if
  importable, else ``numpyro``, else PyMC's native pure-Python NUTS. nutpie /
  numpyro are NOT installed in this venv (probed: both ``ImportError``), so the
  default resolution lands on the native sampler -- which requires NO new
  dependency and is what the pre-P5 ``backend="nuts"`` path already used. The
  optional accelerated engines are gated behind LAZY imports (only attempted when
  ``nuts_sampler`` explicitly requests one), and a missing requested engine fails
  LOUD with the exact ``pip install`` command -- never a cryptic deep crash and
  never a silent fall-through to a slower sampler the caller did not ask for.

* ``nuts_diagnostics`` -- extracts (divergences, min bulk-ESS, max R-hat) from a
  fitted NUTS idata's ``sample_stats`` / posterior, for the provenance/meta
  capture the adoption gate reads. Returns ``None``-valued fields gracefully when
  a group is absent (e.g. a cache-reloaded posterior-only idata) rather than
  raising -- the caller decides whether absent diagnostics are acceptable.
"""
from __future__ import annotations

import arviz as az
import pymc as pm

#: pip install hints surfaced in the fail-loud ImportError for an absent
#: accelerated NUTS engine. Kept here so the message names the exact package.
_NUTS_INSTALL_HINT = {
    "nutpie": "pip install nutpie",
    "numpyro": "pip install numpyro",
}


def _resolve_nuts_sampler(nuts_sampler: str | None) -> str:
    """Resolve the NUTS engine name for ``pm.sample(nuts_sampler=...)``.

    Selection (LAZY imports — nothing is imported unless it is a candidate):

    * ``nuts_sampler is None`` (the harness default) -> AUTO: prefer ``"nutpie"``
      if importable, else ``"numpyro"`` if importable, else PyMC's native
      ``"pymc"`` sampler (always available, no extra dependency). The accelerated
      engines are simply faster; the native one is the correct, dependency-free
      fallback the pre-P5 code already used.
    * an EXPLICIT ``"nutpie"`` / ``"numpyro"`` -> import-probe it; if missing,
      raise a LOUD ``ImportError`` naming the package and its ``pip install``
      command (NEVER silently downgrade to a different engine — the caller asked
      for this one on purpose).
    * an explicit ``"pymc"`` -> the native sampler, returned as-is.

    Returns the resolved engine string to hand to ``pm.sample``.
    """
    if nuts_sampler in ("nutpie", "numpyro"):
        try:
            __import__(nuts_sampler)
        except ImportError as exc:  # fail LOUD, name the package + install cmd
            raise ImportError(
                f"nuts backend requested nuts_sampler={nuts_sampler!r} but "
                f"{nuts_sampler!r} is not importable in this environment; "
                f"install it ({_NUTS_INSTALL_HINT[nuts_sampler]}) or use "
                "nuts_sampler='pymc' (native, no extra dependency)."
            ) from exc
        return nuts_sampler
    if nuts_sampler == "pymc":
        return "pymc"
    if nuts_sampler is not None:
        raise ValueError(
            f"unknown nuts_sampler {nuts_sampler!r}; choose from "
            "{'nutpie', 'numpyro', 'pymc'} (or None for auto)"
        )
    # AUTO resolution: prefer the accelerated engines if present, else native.
    for cand in ("nutpie", "numpyro"):
        try:
            __import__(cand)
            return cand
        except ImportError:
            continue
    return "pymc"


def sample(
    model: pm.Model,
    *,
    backend: str,
    draws: int,
    seed: int,
    tune: int = 1000,
    advi_iters: int = 30000,
    chains: int = 2,
    target_accept: float = 0.9,
    nuts_sampler: str | None = None,
) -> az.InferenceData:
    """Sample ``model`` with the requested backend (seeded).

    backend:
      * ``"advi"``          -- fast mean-field VI for walk-forward refits. Seed is
                               threaded into BOTH fit and draw for reproducibility.
                               BYTE-IDENTICAL to the pre-P5 path (the new
                               ``chains``/``target_accept``/``nuts_sampler`` knobs
                               are NUTS-only and never touch this branch).
      * ``"fullrank_advi"`` -- PyMC full-rank ADVI (full posterior covariance);
                               no new dependency. Seeded fit + draw like advi.
      * ``"nuts"``          -- reference HMC/NUTS sampler. ``chains`` /
                               ``target_accept`` / ``tune`` are honoured; the
                               engine is ``_resolve_nuts_sampler(nuts_sampler)``
                               (auto: nutpie>numpyro>native). ``sample_stats``
                               (divergences etc.) are returned for diagnostics.
      * ``"pathfinder"``    -- NOT available in this stack -> NotImplementedError.

    Returns an arviz idata-like object (a DataTree in arviz 1.1.0) with a
    ``.posterior`` group carrying the model's parameters.
    """
    with model:
        if backend == "nuts":
            engine = _resolve_nuts_sampler(nuts_sampler)
            # cores=1 keeps the seeded run reproducible/serial (the project
            # invariant); the native 'pymc' engine takes no nuts_sampler kwarg
            # other than the name, so pass it uniformly.
            return pm.sample(
                draws,
                tune=tune,
                chains=chains,
                cores=1,
                target_accept=target_accept,
                nuts_sampler=engine,
                random_seed=seed,
                progressbar=False,
            )
        if backend == "advi":
            # Seed the fit AND the draw: both are required for bit-identical
            # reproducibility (mean-field draws are themselves stochastic).
            # BYTE-IDENTICAL-OFF: this branch is unchanged from the pre-P5 code.
            approx = pm.fit(
                n=advi_iters, method="advi", random_seed=seed, progressbar=False
            )
            return approx.sample(draws, random_seed=seed)
        if backend == "fullrank_advi":
            # PyMC full-rank ADVI: a full posterior covariance (no mean-field
            # variance underestimation). Stock pm.fit method -> NO new dep. Seeded
            # in fit + draw exactly like the advi branch.
            approx = pm.fit(
                n=advi_iters, method="fullrank_advi", random_seed=seed,
                progressbar=False,
            )
            return approx.sample(draws, random_seed=seed)
        if backend == "pathfinder":
            raise NotImplementedError(
                "pathfinder backend is not available in pymc 6.0.1 "
                "(requires pymc_experimental.fit_pathfinder or nutpie, neither "
                "installed); use advi, fullrank_advi or nuts"
            )
        raise ValueError(f"unknown backend {backend!r}")


def nuts_diagnostics(idata) -> dict:
    """NUTS convergence diagnostics from a fitted idata -> provenance dict.

    Returns ``{"divergences": int|None, "min_ess_bulk": float|None,
    "max_rhat": float|None, "n_chains": int|None, "n_draws": int|None}``:

    * ``divergences`` -- total post-warmup divergent transitions
      (``sample_stats["diverging"].sum()``). A high count means the sampler hit
      pathological geometry and the posterior is untrustworthy.
    * ``min_ess_bulk`` / ``max_rhat`` -- the WORST per-parameter bulk-ESS (lowest)
      and R-hat (highest) across the model parameters (``az.ess`` / ``az.rhat``).
      min-ESS << draws or max-R-hat >> 1.01 flags non-convergence.

    Robust to a posterior-ONLY idata (e.g. a cache-reloaded fit that dropped
    ``sample_stats`` — see model/cache.py): a missing group yields ``None`` for the
    affected field instead of raising, so a caller can record "diagnostics
    unavailable (cached fit)" rather than crash. ESS/R-hat with a single draw-chain
    are degenerate; guarded to ``None``.
    """
    out: dict = {
        "divergences": None,
        "min_ess_bulk": None,
        "max_rhat": None,
        "n_chains": None,
        "n_draws": None,
    }
    post = getattr(idata, "posterior", None)
    if post is not None:
        dims = getattr(post, "dims", {})
        out["n_chains"] = int(dims["chain"]) if "chain" in dims else None
        out["n_draws"] = int(dims["draw"]) if "draw" in dims else None

    ss = getattr(idata, "sample_stats", None)
    if ss is not None and "diverging" in ss:
        out["divergences"] = int(ss["diverging"].sum())

    # ESS / R-hat need >=2 chains (R-hat) and a non-degenerate sample to be
    # meaningful; az.ess/az.rhat raise or return NaN on a single chain. Guard.
    if post is not None and out.get("n_chains") and out["n_chains"] >= 2:
        try:
            ess = az.ess(idata)
            rhat = az.rhat(idata)
            out["min_ess_bulk"] = float(
                min(float(ess[v].min()) for v in ess.data_vars)
            )
            out["max_rhat"] = float(
                max(float(rhat[v].max()) for v in rhat.data_vars)
            )
        except (KeyError, ValueError, TypeError):
            pass
    return out


def _hdi_width(idata, param: str) -> float:
    """Mean width of the 94% HDI for ``param``.

    arviz 1.1.0: ``az.hdi`` returns a DataTree with a ``ci_bound`` coordinate
    (values ``"lower"`` / ``"upper"``); the width is upper - lower, averaged over
    any remaining (e.g. per-team) dims so scalar and vector params both reduce to
    a single float.
    """
    h = az.hdi(idata, var_names=[param], prob=0.94)[param]
    return float((h.sel(ci_bound="upper") - h.sel(ci_bound="lower")).mean())


def advi_variance_check(
    advi_idata, nuts_idata, params, rel_tol: float = 0.5
) -> dict:
    """Flag params where ADVI width < (1 - rel_tol) * NUTS width.

    Returns ``{param: {advi_width, nuts_width, ratio, flagged}}``. A param is
    flagged when its ADVI 94% HDI is materially tighter than the NUTS reference
    (ratio below ``1 - rel_tol``) -- i.e. ADVI is falsely confident and any
    downstream width-dependent logic would under-hedge. ``flagged`` is False when
    the NUTS reference width is non-positive (degenerate, nothing to compare).
    """
    out = {}
    for p in params:
        wa = _hdi_width(advi_idata, p)
        wn = _hdi_width(nuts_idata, p)
        out[p] = {
            "advi_width": wa,
            "nuts_width": wn,
            "ratio": (wa / wn if wn else float("nan")),
            "flagged": bool(wn > 0 and wa < (1 - rel_tol) * wn),
        }
    return out
