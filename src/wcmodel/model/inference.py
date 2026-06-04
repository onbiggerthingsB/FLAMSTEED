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
"""
from __future__ import annotations

import arviz as az
import pymc as pm


def sample(
    model: pm.Model,
    *,
    backend: str,
    draws: int,
    seed: int,
    tune: int = 1000,
    advi_iters: int = 30000,
) -> az.InferenceData:
    """Sample ``model`` with the requested backend (seeded).

    backend:
      * ``"nuts"``        -- exact reference sampler (2 chains, 1 core).
      * ``"advi"``        -- fast mean-field VI for walk-forward refits. Seed is
                             threaded into BOTH fit and draw for reproducibility.
      * ``"pathfinder"``  -- NOT available in this stack -> NotImplementedError.

    Returns an arviz idata-like object (a DataTree in arviz 1.1.0) with a
    ``.posterior`` group carrying the model's parameters.
    """
    with model:
        if backend == "nuts":
            return pm.sample(
                draws,
                tune=tune,
                chains=2,
                cores=1,
                random_seed=seed,
                progressbar=False,
            )
        if backend == "advi":
            # Seed the fit AND the draw: both are required for bit-identical
            # reproducibility (mean-field draws are themselves stochastic).
            approx = pm.fit(
                n=advi_iters, method="advi", random_seed=seed, progressbar=False
            )
            return approx.sample(draws, random_seed=seed)
        if backend == "pathfinder":
            raise NotImplementedError(
                "pathfinder backend is not available in pymc 6.0.1 "
                "(requires pymc_experimental.fit_pathfinder or nutpie, neither "
                "installed); use advi or nuts"
            )
        raise ValueError(f"unknown backend {backend!r}")


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
