"""T7 — the ablation + accept/reject backtest runner (the disciplined covariate gate).

A covariate ships ONLY if it earns it. ``run_ablation`` is the validation harness
that decides: for each candidate covariate it runs the Phase-4 ``walkforward``
TWICE over the SAME cutoffs / seed / windows / odds / de-vig — once with
``model.covariates.enabled = [candidate]`` (the candidate arm), once with
``enabled = []`` (the baseline arm). The ONLY difference between the two arms is the
covariate; everything else is byte-identical (PAIRED, so the baseline is never
advantaged or run differently). The pairing is what makes the RPS delta an unbiased
estimate of the covariate's effect.

For each candidate it reports:
  * ``delta_rps``      = ``baseline_mean_rps − candidate_mean_rps`` (positive =
    candidate better — lower out-of-sample RPS is better);
  * ``null_p``         = the label-permutation-null p-value on the CANDIDATE's own
    per-bet probs/outcomes (reuse ``report.permutation_null``); ``null_p`` is the
    fraction of shuffles whose RPS is at-least-as-good as the candidate's real RPS,
    i.e. ``1 − percentile``. A genuinely-informative candidate clears ``< 0.05``.
    This is the OVERFIT guard: a too-good RPS that the null also reproduces under
    label-shuffling does NOT clear the bar (the delta is a flag, not an auto-accept);
  * ``baseline_clv`` / ``candidate_clv`` = the average CLV% of each arm
    (``clv_summary`` — CLV is the north-star leading indicator).

``verdict = "accept"`` iff ``delta_rps > 0`` AND ``null_p < 0.05`` AND
``candidate_clv >= baseline_clv − tol`` (the covariate must not DEGRADE CLV).
Otherwise ``"reject"``.

``use_lockbox=True`` runs the final ACCEPTED set ONCE against the held-out
single-use lockbox (the P4-T7 ``LockboxRegistry`` mechanism — read AT MOST ONCE,
enforced on disk) and records the result under ``_meta["lockbox"]``.

NO bet, NO spend — signal-only / paper. Synthetic odds taint the whole report
NON-REAL (``walkforward``'s ``is_synthetic`` propagates), so no number off this
harness is ever a real edge claim. Leakage is impossible by construction: the
candidate's covariate flows through the SAME leakage-safe ``features.build`` /
``CovariateTransform`` proven by the T6 covariate leakage canary.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from wcmodel.backtest.lockbox import LockboxRegistry
from wcmodel.backtest.report import permutation_null
from wcmodel.backtest.walkforward import walkforward
from wcmodel.config import load_config

#: Default CLV tolerance: a candidate may be at most this much WORSE on average CLV
#: than the baseline and still accept (CLV is noisy; a hair of slack avoids
#: rejecting a real RPS win on CLV measurement noise). Documented small constant;
#: overridable via ``config["backtest"]["ablation_clv_tol"]``.
_DEFAULT_CLV_TOL = 1e-3

#: Accept bar on the permutation-null p-value (mirrors the D4 ~99th-percentile
#: discipline: real RPS must sit in the best ~1% of the null).
_NULL_P_ACCEPT = 0.05


def _verdict(*, delta_rps: float, null_p: float, baseline_clv: float,
             candidate_clv: float, tol: float) -> str:
    """The accept/reject gate as a PURE function (no fit, no I/O).

    Accept iff ALL three hold:
      1. ``delta_rps > 0``                       — candidate's OOS RPS is better;
      2. ``null_p < _NULL_P_ACCEPT`` (0.05)      — the improvement clears the
         permutation null (a too-good-but-chance delta is REJECTED, not accepted);
      3. ``candidate_clv >= baseline_clv − tol`` — CLV is not (meaningfully) worse.

    A NaN in any input (e.g. an empty-bets arm produced no RPS/CLV) fails the
    comparison and yields ``"reject"`` — fail-safe: an unmeasurable candidate is
    never accepted.
    """
    rps_better = delta_rps > 0
    null_ok = null_p < _NULL_P_ACCEPT
    clv_ok = candidate_clv >= baseline_clv - tol
    # NaN-safe: any NaN makes the corresponding comparison False -> reject.
    if rps_better and null_ok and clv_ok:
        return "accept"
    return "reject"


def _arm_config(base_config: dict, enabled: list[str]) -> dict:
    """A DEEP COPY of ``base_config`` with ``model.covariates.enabled`` set to
    ``enabled`` and NOTHING else changed.

    Deep-copied so mutating the candidate arm's ``enabled`` can never bleed into the
    baseline arm (or the caller's config). This is the SINGLE point of difference
    between the two paired arms — every other DOF (elo, windows, prior, widening,
    backtest thresholds, de-vig, seed) is carried over untouched.
    """
    cfg = copy.deepcopy(base_config)
    cfg["model"]["covariates"]["enabled"] = list(enabled)
    return cfg


def _mean_rps(metrics) -> float:
    """The arm's out-of-sample mean model RPS (``summary["mean_rps_model"]`` —
    NaN on an empty-bets arm)."""
    return float(metrics.summary.get("mean_rps_model", float("nan")))


def _avg_clv(metrics) -> float:
    """The arm's average CLV% (``summary["clv_avg_clv"]`` — NaN on empty bets)."""
    return float(metrics.summary.get("clv_avg_clv", float("nan")))


def _null_p_value(metrics, *, shuffles: int, seed: int) -> float:
    """The label-permutation-null p-value on the arm's per-bet probs/outcomes.

    Reuses the project's ``permutation_null`` (the same machinery as the P4-T7
    report). It returns ``percentile`` = the fraction of shuffles the model BEATS
    (real RPS < shuffled RPS); the p-value is ``1 − percentile`` = the fraction of
    shuffles that do at-least-as-well as the real model. A genuinely-informative
    candidate sits at ~the 99th percentile, i.e. ``null_p ≈ 0.01``.

    With NO bets there is nothing to permute -> ``null_p = 1.0`` (the candidate
    cannot clear the bar; an unmeasurable signal is treated as no signal).
    """
    probs = [b["model"] for b in metrics.bets]
    outcomes = [b["outcome"] for b in metrics.bets]
    if not probs:
        return 1.0
    res = permutation_null(probs, outcomes, shuffles=shuffles, seed=seed)
    return float(1.0 - res["percentile"])


def _run_arm(store, odds_samples, *, enabled, base_config, seed, results_for_settle,
             matches, fit_kwargs, cache_dir):
    """Run ONE walk-forward arm with ``covariates.enabled = enabled``.

    The seed is bound into ``fit_kwargs`` so BOTH arms share the identical sampler
    seed (the pairing guarantee at the fit level too, not just the config level).
    Returns the ``Metrics``.
    """
    cfg = _arm_config(base_config, enabled)
    fk = {**(fit_kwargs or {}), "seed": seed}
    return walkforward(
        store, odds_samples,
        results_for_settle=results_for_settle, matches=matches,
        config=cfg, fit_kwargs=fk, cache_dir=cache_dir,
    )


def run_ablation(store, odds_samples: list[dict], *, candidates: list[str],
                 cutoffs: list[str], config: dict | None = None, seed: int = 0,
                 results_for_settle: pd.DataFrame, matches: pd.DataFrame,
                 fit_kwargs: dict | None = None, cache_dir=None,
                 use_lockbox: bool = False, lockbox_path=None) -> dict:
    """Paired baseline-vs-candidate ablation over identical cutoffs -> a verdict report.

    Parameters
    ----------
    store
        Bitemporal store (leakage-safe per-cutoff reads; the SAME object feeds both
        arms — pairing at the data level).
    odds_samples
        The de-vigged market snapshots (the SAME list feeds both arms). Synthetic
        samples taint the whole report NON-REAL.
    candidates
        The covariate names to ablate (e.g. ``["rest_days"]``). Each is run as its
        own paired baseline-vs-candidate pair.
    cutoffs
        The walk-forward cutoff window, recorded in ``_meta["cutoffs"]`` as the
        paired identity (BOTH arms sweep the SAME grid; the grid itself is driven by
        ``config.backtest.odds_start`` / ``matches`` inside ``walkforward``).
    config
        Pre-loaded config (defaults to ``load_config``). DEEP-COPIED per arm so the
        only per-arm difference is ``model.covariates.enabled``.
    seed
        The global ablation seed; bound into BOTH arms' ``fit_kwargs`` and used for
        the permutation null (paired, reproducible).
    results_for_settle, matches
        Threaded straight through to ``walkforward`` (settle frame + window panel) —
        the SAME objects for both arms.
    fit_kwargs
        Sampler knobs (draws/advi_iters/backend). ``seed`` is overridden with the
        ablation ``seed`` so the two arms cannot diverge on the sampler seed.
    use_lockbox, lockbox_path
        If ``use_lockbox`` is True, run the ACCEPTED candidate set ONCE against the
        single-use lockbox (``LockboxRegistry``, read AT MOST ONCE, enforced on
        disk) and record it under ``_meta["lockbox"]``. ``lockbox_path`` overrides
        the committed registry (used by tests with an isolated temp registry so the
        real single shot is never burned).

    Returns
    -------
    dict
        ``{<candidate>: {baseline_rps, candidate_rps, delta_rps, null_p,
        baseline_clv, candidate_clv, verdict}, ..., "_meta": {cutoffs, seed,
        is_synthetic, clv_tol, [accepted], [lockbox]}}``.

        NO bet, NO spend — signal-only / paper.
    """
    cfg = config or load_config()
    bt = cfg["backtest"]
    shuffles = int(bt.get("permutation_shuffles", 200))
    tol = float(bt.get("ablation_clv_tol", _DEFAULT_CLV_TOL))

    report: dict = {}
    accepted: list[str] = []
    any_synthetic = False

    # The baseline arm is the SAME for every candidate (enabled=[]); run it ONCE and
    # reuse it across candidates so each candidate is compared against the IDENTICAL
    # baseline (no per-candidate baseline drift — paired against one fixed reference).
    baseline = _run_arm(
        store, odds_samples, enabled=[], base_config=cfg, seed=seed,
        results_for_settle=results_for_settle, matches=matches,
        fit_kwargs=fit_kwargs, cache_dir=cache_dir,
    )
    any_synthetic = any_synthetic or bool(baseline.is_synthetic)
    baseline_rps = _mean_rps(baseline)
    baseline_clv = _avg_clv(baseline)

    for candidate in candidates:
        cand = _run_arm(
            store, odds_samples, enabled=[candidate], base_config=cfg, seed=seed,
            results_for_settle=results_for_settle, matches=matches,
            fit_kwargs=fit_kwargs, cache_dir=cache_dir,
        )
        any_synthetic = any_synthetic or bool(cand.is_synthetic)

        candidate_rps = _mean_rps(cand)
        candidate_clv = _avg_clv(cand)
        delta_rps = baseline_rps - candidate_rps        # positive = candidate better
        null_p = _null_p_value(cand, shuffles=shuffles, seed=seed)

        verdict = _verdict(delta_rps=delta_rps, null_p=null_p,
                           baseline_clv=baseline_clv, candidate_clv=candidate_clv,
                           tol=tol)
        if verdict == "accept":
            accepted.append(candidate)

        report[candidate] = {
            "baseline_rps": baseline_rps,
            "candidate_rps": candidate_rps,
            "delta_rps": delta_rps,
            "null_p": null_p,
            "baseline_clv": baseline_clv,
            "candidate_clv": candidate_clv,
            "verdict": verdict,
        }

    report["_meta"] = {
        "cutoffs": list(cutoffs),
        "seed": seed,
        "is_synthetic": bool(any_synthetic),
        "clv_tol": tol,
        "accepted": list(accepted),
    }

    if use_lockbox:
        report["_meta"]["lockbox"] = _evaluate_lockbox(
            store, odds_samples, accepted=accepted, base_config=cfg, seed=seed,
            results_for_settle=results_for_settle, matches=matches,
            fit_kwargs=fit_kwargs, cache_dir=cache_dir, lockbox_path=lockbox_path,
        )

    return report


def _evaluate_lockbox(store, odds_samples, *, accepted, base_config, seed,
                      results_for_settle, matches, fit_kwargs, cache_dir,
                      lockbox_path) -> dict:
    """Run the ACCEPTED set ONCE against the single-use lockbox; record the result.

    The eval is wrapped in ``LockboxRegistry.evaluate_on_lockbox`` — single-use is
    ENFORCED ON DISK (the ``used`` flag is burned BEFORE the eval runs; a second
    call raises ``LockboxUsedError`` even from a fresh process). The lockbox arm is
    the accepted covariate set as ONE model (``enabled = accepted``); on an empty
    accepted set it is the baseline (``enabled = []``), so the lockbox is still
    spent on a defined model rather than left dangling.
    """
    reg = (LockboxRegistry.load(path=lockbox_path)
           if lockbox_path is not None else LockboxRegistry.load())

    def _eval() -> dict:
        metrics = _run_arm(
            store, odds_samples, enabled=accepted, base_config=base_config,
            seed=seed, results_for_settle=results_for_settle, matches=matches,
            fit_kwargs=fit_kwargs, cache_dir=cache_dir,
        )
        return {
            "enabled": list(accepted),
            "mean_rps_model": _mean_rps(metrics),
            "avg_clv": _avg_clv(metrics),
            "n_bets": len(metrics.bets),
            "is_synthetic": bool(metrics.is_synthetic),
        }

    return reg.evaluate_on_lockbox(_eval)
