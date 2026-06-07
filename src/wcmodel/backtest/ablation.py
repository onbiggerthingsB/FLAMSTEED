"""T7 — the ablation + accept/reject backtest gate (the disciplined covariate gate).

A covariate ships ONLY if it earns it. ``run_ablation`` is the validation harness
that decides, per candidate covariate, whether enabling it actually improves the
out-of-sample forecast — measured by a PAIRED ranked-probability-score (RPS) test
over a COMMON fixture set.

THE PAIRED RPS EVAL (FIX 1/2/3b — the core of the gate)
-------------------------------------------------------
For each walk-forward ``cutoff`` (the provided ``cutoffs`` drive the loop — FIX 5):

  1. Fit the BASELINE (``covariates.enabled = []``) and the CANDIDATE
     (``enabled = [candidate]``) on the ``< cutoff`` data via ``cached_fit`` — same
     seed, same windows, same store; the persisted ``CovariateTransform`` is
     restored on a cache hit (FIX 3a), so the cached candidate predicts WITH the
     covariate (not a zero offset).
  2. Determine the COMMON evaluation set = the real matches PLAYED in the next
     window ``[cutoff, next_cutoff)`` with known outcomes, read leakage-safely from
     the store. This is the SAME set of fixtures + outcomes for BOTH arms.
  3. For EACH eval fixture, compute its covariate values LEAKAGE-SAFELY from
     ``features.build(cutoff)`` (the ``< cutoff`` panel only) + the host_factor, then
     score ``rps`` for the CANDIDATE's ``predict_1x2`` WITH those covariates and for
     the BASELINE's ``predict_1x2`` WITHOUT — over the IDENTICAL fixture/outcome.

The delta is therefore PAIRED by construction: same fixtures, same outcomes, only
the model differs. ``d_i = rps_baseline_i − rps_candidate_i`` (positive = candidate
better); ``mean_d = mean(d_i)``.

THE PAIRED SIGNIFICANCE TEST (FIX 1/2)
--------------------------------------
A one-sided SIGN-FLIP permutation null on the paired differences: for
``B = backtest.permutation_shuffles`` iterations, flip the sign of each ``d_i``
independently with prob 0.5 and record the permuted mean; the p-value is
``p = (1 + count(perm_mean >= mean_d)) / (B + 1)``. Seeded -> reproducible. This is
the uplift gate — NOT the old candidate-vs-chance ``null_p`` (kept only as a sanity
field). If MORE THAN ONE candidate is tested, a Bonferroni multiplicity correction
is applied (``p_adj = min(1, p * n_candidates)``; recorded in ``_meta``).

THE VERDICT
-----------
``verdict = "accept"`` iff ``mean_d > 0`` AND ``p_adj < 0.05`` AND
``candidate_clv >= baseline_clv − tol``. A NaN/None in ANY input fails the
comparison and yields ``"reject"`` (fail-safe — an unmeasurable arm is never
accepted, never a crash — FIX 4).

CLV CAVEAT (documented)
-----------------------
CLV is a SECONDARY guard computed on the existing covariate-free betting path
(``walkforward`` does not thread fixture covariates into its ``model_fair_1x2`` /
stake / CLV path). The PRIMARY metric — RPS — IS covariate-aware via the paired
forecast eval above. So the gate's uplift evidence sees the covariate; CLV only
guards that enabling it does not degrade the close-line edge on the baseline path.

``use_lockbox=True`` runs the final ACCEPTED set ONCE against the held-out
single-use lockbox (``LockboxRegistry``, read AT MOST ONCE, enforced on disk).

NO bet, NO spend — signal-only / paper. Synthetic odds taint the whole report
NON-REAL (``is_synthetic`` propagates), so no number off this harness is ever a
real edge claim. Leakage is impossible by construction: every covariate flows
through the SAME leakage-safe ``features.build`` / ``CovariateTransform`` proven by
the T6 covariate leakage canary, and the eval set is read strictly from played,
known-outcome matches in the forward window.
"""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd

import wcmodel.model.cache as _model_cache
from wcmodel.backtest.baselines import model_fair_1x2, rps
from wcmodel.backtest.lockbox import LockboxRegistry
from wcmodel.backtest.report import permutation_null
from wcmodel.backtest.walkforward import walkforward
from wcmodel.config import load_config
from wcmodel.data import features
from wcmodel.data.features import valid_played_results

#: Default CLV tolerance: a candidate may be at most this much WORSE on average CLV
#: than the baseline and still accept (CLV is noisy; a hair of slack avoids
#: rejecting a real RPS win on CLV measurement noise). Overridable via
#: ``config["backtest"]["ablation_clv_tol"]``.
_DEFAULT_CLV_TOL = 1e-3

#: Accept bar on the PAIRED permutation p-value (the uplift gate).
_PAIRED_P_ACCEPT = 0.05


def _is_bad(x) -> bool:
    """True iff ``x`` is None or NaN — the fail-safe sentinel for an unmeasurable
    arm. ``float(None)`` would CRASH and ``nan`` comparisons silently go False, so
    we test explicitly and route to ``"reject"`` (FIX 4)."""
    if x is None:
        return True
    try:
        return bool(math.isnan(float(x)))
    except (TypeError, ValueError):
        return True


def _verdict(*, mean_d, p_value, baseline_clv, candidate_clv, tol: float) -> str:
    """The accept/reject gate as a PURE function (no fit, no I/O).

    Accept iff ALL three hold:
      1. ``mean_d > 0``                          — candidate's paired OOS RPS is
         better (positive = lower candidate RPS over the common fixture set);
      2. ``p_value < _PAIRED_P_ACCEPT`` (0.05)   — the paired sign-flip permutation
         p clears the bar (a noise-level delta is REJECTED);
      3. ``candidate_clv >= baseline_clv − tol`` — CLV is not (meaningfully) worse.

    NaN/None in ANY input (an empty/unmeasurable arm produced no RPS/CLV/p) ->
    ``"reject"`` (FIX 4: fail-safe — never a crash, never a spurious accept).
    """
    if any(_is_bad(v) for v in (mean_d, p_value, baseline_clv, candidate_clv)):
        return "reject"
    rps_better = float(mean_d) > 0.0
    p_ok = float(p_value) < _PAIRED_P_ACCEPT
    clv_ok = float(candidate_clv) >= float(baseline_clv) - tol
    return "accept" if (rps_better and p_ok and clv_ok) else "reject"


def _arm_config(base_config: dict, enabled: list[str]) -> dict:
    """A DEEP COPY of ``base_config`` with ``model.covariates.enabled`` set to
    ``enabled`` and NOTHING else changed — the SINGLE point of difference between
    the two paired arms."""
    cfg = copy.deepcopy(base_config)
    cfg["model"]["covariates"]["enabled"] = list(enabled)
    return cfg


def _avg_clv(metrics) -> float:
    """The arm's average CLV% (``summary["clv_avg_clv"]``) -> float, NaN-safe.

    FIX 4: an EMPTY-bets arm canonicalises its CLV/RPS aggregates to ``None`` (the
    walkforward JSON round-trip folds NaN -> None), and a bare ``float(None)`` would
    CRASH the whole ablation. Map None/missing -> NaN so the verdict's NaN-safe gate
    routes to ``"reject"`` (fail-safe) rather than aborting the run."""
    v = metrics.summary.get("clv_avg_clv")
    return float("nan") if v is None else float(v)


def _candidate_null_p(per_fixture_probs, outcomes, *, shuffles, seed) -> float:
    """The OLD candidate-vs-chance label-permutation p (sanity field only, NOT the
    gate). ``percentile`` is the fraction of shuffles the candidate BEATS; the
    p-value is ``1 − percentile``. Empty -> 1.0 (no signal)."""
    if not per_fixture_probs:
        return 1.0
    res = permutation_null(per_fixture_probs, outcomes, shuffles=shuffles, seed=seed)
    return float(1.0 - res["percentile"])


# --------------------------------------------------------------------------- #
# The COMMON OOS eval set + leakage-safe per-fixture covariates.               #
# --------------------------------------------------------------------------- #

def _settle_outcome(home_score, away_score) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _played_in_window(store, *, lo, hi):
    """The real matches PLAYED in ``[lo, hi)`` with KNOWN outcomes — the OOS eval
    set, read leakage-safely from the store.

    Reads ``results`` as-of ``hi`` (so every row in the window is observable),
    keeps only VALID PLAYED matches (``valid_played_results`` — finite, integral,
    non-negative scores), and filters to ``lo <= date < hi``. Returns a frame with
    ``home_team, away_team, date, home_score, away_score`` (one row per fixture).
    The window is half-open at the top so a fixture exactly on ``next_cutoff`` lands
    in the NEXT window, never double-counted.
    """
    lo = pd.Timestamp(lo).normalize()
    hi = pd.Timestamp(hi).normalize()
    res = store.read("results", cutoff=hi)
    res = res.copy()
    res["date"] = pd.to_datetime(res["date"])
    if getattr(res["date"].dt, "tz", None) is not None:
        res["date"] = res["date"].dt.tz_convert("UTC").dt.tz_localize(None)
    res = valid_played_results(res)
    res = res.loc[(res["date"] >= lo) & (res["date"] < hi)].copy()
    return res[["home_team", "away_team", "date",
                "home_score", "away_score"]].reset_index(drop=True)


def _last_match_date_before(panel: pd.DataFrame, team: str):
    """The team's latest played date in the ``< cutoff`` panel, or None.

    ``panel`` is the leakage-safe ``features.build(cutoff)`` frame (two rows per
    match, one per team). Used to derive ``rest_days`` for a FUTURE fixture exactly
    as ``derived.rest_days`` does (gap to the team's previous fixture) — no future
    leakage because the panel is strictly ``< cutoff``."""
    if panel is None or panel.empty or "team" not in panel.columns:
        return None
    rows = panel.loc[panel["team"] == team]
    if rows.empty:
        return None
    return pd.to_datetime(rows["date"]).max()


def _fixture_covariates(*, enabled, panel, home, away, fixture_date):
    """Leakage-safe covariate dict for ONE eval fixture, in the ``predict_1x2``
    contract (``{name, name__away}`` for a per-team covariate, ``{name}`` for a
    per-match covariate). EVERY value is derived ONLY from the ``< cutoff`` panel /
    the venue table — NEVER from the fixture's own (future) outcome.

    * ``rest_days`` (per-team): ``(fixture_date − team's last < cutoff match).days``
      for each side; NaN (no prior match) -> masked to a zero contribution by the
      CovariateTransform (never imputed). This mirrors ``derived.rest_days``.
    * ``travel_km`` (per-team): NaN here — the eval fixtures carry no venue/itinerary,
      so travel gaps to NaN (masked). Documented coverage gap, not imputation.
    * ``altitude_m`` (per-match): the fixture venue's altitude if a venue is known,
      else NaN (masked).

    An enabled covariate the candidate did not actually fit (absent from the train
    panel) simply contributes nothing at predict — the transform map gates it.
    """
    cov: dict = {}
    fd = pd.Timestamp(fixture_date).normalize()
    for name in enabled:
        if name == "rest_days":
            for side, team in (("", home), ("__away", away)):
                last = _last_match_date_before(panel, team)
                v = float("nan") if last is None else float((fd - last).days)
                cov[f"{name}{side}"] = v
        elif name == "travel_km":
            # No itinerary for a prospective eval fixture -> NaN both sides (masked).
            cov[name] = float("nan")
            cov[f"{name}__away"] = float("nan")
        elif name == "altitude_m":
            cov[name] = float("nan")  # eval fixtures carry no venue -> masked gap
        # An unclassified covariate is rejected at fit by scoreline._covariate_betas;
        # here it simply produces no key and predict treats it as baseline.
    return cov


def _paired_rps_over_window(*, store, base_post, cand_post, enabled, cfg,
                            lo, hi):
    """Score the BASELINE and CANDIDATE over the SAME OOS fixtures in ``[lo, hi)``.

    Returns ``(d_list, base_rps_list, cand_rps_list, cand_probs, outcomes)`` —
    ``d_i = rps_baseline_i − rps_candidate_i`` per eval fixture, plus the per-arm
    RPS lists, the candidate's per-fixture prob dicts and the realised outcomes
    (for the sanity null). The candidate's ``predict_1x2`` is called WITH the
    leakage-safe per-fixture covariates; the baseline WITHOUT — over the IDENTICAL
    fixture and outcome, so the delta is paired."""
    eval_set = _played_in_window(store, lo=lo, hi=hi)
    if eval_set.empty:
        return [], [], [], [], []

    # The leakage-safe < cutoff panel (rest_days history), built ONCE per cutoff
    # for the per-fixture covariate derivation.
    try:
        panel = features.build(lo, store, cfg)
    except Exception:
        panel = None

    d_list, base_rps_list, cand_rps_list, cand_probs, outcomes = [], [], [], [], []
    for r in eval_set.itertuples(index=False):
        home, away = r.home_team, r.away_team
        try:
            base_p = model_fair_1x2(base_post, home=home, away=away, neutral=True)
        except KeyError:
            continue  # a team absent from the as-of-cutoff fit -> no model price
        cov = _fixture_covariates(enabled=enabled, panel=panel,
                                  home=home, away=away, fixture_date=r.date)
        try:
            cand_p = cand_post.predict_1x2(home, away, neutral=True, covariates=cov)
        except KeyError:
            continue
        outcome = _settle_outcome(int(r.home_score), int(r.away_score))
        r_base = rps(base_p, outcome)
        r_cand = rps(cand_p, outcome)
        base_rps_list.append(r_base)
        cand_rps_list.append(r_cand)
        d_list.append(r_base - r_cand)
        cand_probs.append(cand_p)
        outcomes.append(outcome)
    return d_list, base_rps_list, cand_rps_list, cand_probs, outcomes


def _sign_flip_p(d_list, *, shuffles, seed) -> tuple[float, float]:
    """One-sided sign-flip permutation p-value on paired differences ``d_list``.

    For ``B = shuffles`` iterations flip the sign of each ``d_i`` independently with
    prob 0.5 and record the permuted mean; ``p = (1 + count(perm_mean >= mean_d)) /
    (B + 1)``. Returns ``(mean_d, p)``. Empty/degenerate -> ``(nan, nan)`` so the
    verdict fail-safe REJECTS (FIX 4)."""
    d = np.asarray(d_list, dtype=float)
    if d.size == 0 or not np.all(np.isfinite(d)):
        return float("nan"), float("nan")
    mean_d = float(d.mean())
    rng = np.random.default_rng(seed)
    # Each iteration draws an independent ±1 sign vector and recomputes the mean.
    signs = rng.choice((-1.0, 1.0), size=(shuffles, d.size))
    perm_means = (signs * d).mean(axis=1)
    p = float((1 + int(np.count_nonzero(perm_means >= mean_d))) / (shuffles + 1))
    return mean_d, p


def _eval_window_bounds(cutoffs, matches):
    """The ordered ``(lo, hi)`` OOS windows the paired eval iterates (FIX 5).

    The provided ``cutoffs`` DRIVE the loop: each consecutive pair ``(c_k, c_{k+1})``
    is a half-open window ``[c_k, c_{k+1})``; the LAST window runs to the max match
    date + 1 day (inclusive of the final played fixtures) so a real fixture on or
    after the last cutoff is still evaluated. ``matches`` provides that upper bound.
    """
    cs = sorted(pd.Timestamp(c).normalize() for c in cutoffs)
    if not cs:
        return []
    if matches is not None and len(matches) and "date" in matches.columns:
        last = pd.to_datetime(matches["date"]).max().normalize() + pd.Timedelta(days=1)
    else:
        last = cs[-1] + pd.Timedelta(days=1)
    bounds = []
    for i, lo in enumerate(cs):
        hi = cs[i + 1] if i + 1 < len(cs) else max(last, lo + pd.Timedelta(days=1))
        bounds.append((lo, hi))
    return bounds


# --------------------------------------------------------------------------- #
# Arm runners.                                                                 #
# --------------------------------------------------------------------------- #

def _walkforward_arm(store, odds_samples, *, enabled, base_config, seed,
                     results_for_settle, matches, fit_kwargs, cache_dir):
    """Run ONE walk-forward arm (covariate-free betting path) for the CLV guard.

    The seed is bound into ``fit_kwargs`` so BOTH arms share the sampler seed. CLV
    is computed on this path (which does NOT thread fixture covariates — documented
    secondary guard); the covariate effect itself is measured by the paired RPS eval.
    """
    cfg = _arm_config(base_config, enabled)
    fk = {**(fit_kwargs or {}), "seed": seed}
    return walkforward(
        store, odds_samples,
        results_for_settle=results_for_settle, matches=matches,
        config=cfg, fit_kwargs=fk, cache_dir=cache_dir,
    )


def _fit_arm(store, *, enabled, base_config, seed, fit_kwargs, cache_dir, cutoff):
    """Fit ONE arm's posterior as-of ``cutoff`` via ``cached_fit`` (transforms
    restored on a hit — FIX 3a). Returns the ``Posterior`` (or None if the as-of
    panel could not be fit, e.g. no ``< cutoff`` history)."""
    cfg = _arm_config(base_config, enabled)
    fk = fit_kwargs or {}
    try:
        post, _meta = _model_cache.cached_fit(
            cutoff=cutoff, store=store,
            backend=fk.get("backend", "advi"),
            draws=fk.get("draws", 200),
            seed=seed,
            advi_iters=fk.get("advi_iters", 2000),
            cache_dir=fk.get("cache_dir", cache_dir or "data/cache"),
            config=cfg,
        )
        return post
    except (KeyError, ValueError):
        return None


def run_ablation(store, odds_samples: list[dict], *, candidates: list[str],
                 cutoffs: list[str], config: dict | None = None, seed: int = 0,
                 results_for_settle: pd.DataFrame, matches: pd.DataFrame,
                 fit_kwargs: dict | None = None, cache_dir=None,
                 use_lockbox: bool = False, lockbox_path=None) -> dict:
    """Paired baseline-vs-candidate ablation -> a per-candidate verdict report.

    Per candidate the report carries: ``mean_d`` (paired mean RPS improvement;
    positive = candidate better), ``paired_p`` (the sign-flip permutation p),
    ``paired_p_adj`` (Bonferroni-corrected across candidates), ``baseline_rps`` /
    ``candidate_rps`` (mean RPS over the common eval set), ``n_eval`` (common
    fixture count), ``baseline_clv`` / ``candidate_clv``, ``null_p`` (the OLD
    candidate-vs-chance sanity field — NOT the gate), and ``verdict``.

    The RPS eval is PAIRED over a COMMON fixture set WITH the covariate in the
    candidate's predict (FIX 1/2/3b); the eval iterates the provided ``cutoffs``
    (FIX 5); CLV is a secondary guard on the covariate-free betting path.

    Returns ``{<candidate>: {...}, "_meta": {cutoffs, seed, is_synthetic, clv_tol,
    n_eval_total, permutation_shuffles, multiplicity, accepted, [lockbox]}}``. NO
    bet, NO spend — signal-only / paper.
    """
    cfg = config or load_config()
    bt = cfg["backtest"]
    shuffles = int(bt.get("permutation_shuffles", 200))
    tol = float(bt.get("ablation_clv_tol", _DEFAULT_CLV_TOL))
    n_candidates = len(candidates)

    report: dict = {}
    accepted: list[str] = []
    any_synthetic = False

    # The OOS windows the paired eval iterates (the provided cutoffs DRIVE it).
    windows = _eval_window_bounds(cutoffs, matches)

    # The baseline CLV arm (covariate-free betting path) is the SAME for every
    # candidate; run it ONCE so each candidate is compared to the IDENTICAL baseline.
    baseline_wf = _walkforward_arm(
        store, odds_samples, enabled=[], base_config=cfg, seed=seed,
        results_for_settle=results_for_settle, matches=matches,
        fit_kwargs=fit_kwargs, cache_dir=cache_dir,
    )
    any_synthetic = any_synthetic or bool(baseline_wf.is_synthetic)
    baseline_clv = _avg_clv(baseline_wf)

    # The baseline posteriors as-of each cutoff (reused across candidates — the
    # baseline fit does not depend on which candidate is being tested).
    baseline_posts = {
        lo: _fit_arm(store, enabled=[], base_config=cfg, seed=seed,
                     fit_kwargs=fit_kwargs, cache_dir=cache_dir, cutoff=lo)
        for (lo, _hi) in windows
    }

    n_eval_total = 0
    for candidate in candidates:
        # CLV arm for this candidate (secondary guard, covariate-free betting path).
        cand_wf = _walkforward_arm(
            store, odds_samples, enabled=[candidate], base_config=cfg, seed=seed,
            results_for_settle=results_for_settle, matches=matches,
            fit_kwargs=fit_kwargs, cache_dir=cache_dir,
        )
        any_synthetic = any_synthetic or bool(cand_wf.is_synthetic)
        candidate_clv = _avg_clv(cand_wf)

        # PAIRED RPS eval over the common OOS fixture set per cutoff window.
        d_all, base_rps_all, cand_rps_all, cand_probs_all, outcomes_all = [], [], [], [], []
        for (lo, hi) in windows:
            base_post = baseline_posts.get(lo)
            cand_post = _fit_arm(store, enabled=[candidate], base_config=cfg,
                                 seed=seed, fit_kwargs=fit_kwargs,
                                 cache_dir=cache_dir, cutoff=lo)
            if base_post is None or cand_post is None:
                continue
            d, br, cr, cp, oc = _paired_rps_over_window(
                store=store, base_post=base_post, cand_post=cand_post,
                enabled=[candidate], cfg=cfg, lo=lo, hi=hi,
            )
            d_all.extend(d); base_rps_all.extend(br); cand_rps_all.extend(cr)
            cand_probs_all.extend(cp); outcomes_all.extend(oc)

        n_eval = len(d_all)
        n_eval_total += n_eval
        mean_d, paired_p = _sign_flip_p(d_all, shuffles=shuffles, seed=seed)
        # Bonferroni multiplicity correction across the tested candidates.
        paired_p_adj = (float("nan") if _is_bad(paired_p)
                        else min(1.0, float(paired_p) * max(n_candidates, 1)))
        baseline_rps = float(np.mean(base_rps_all)) if base_rps_all else float("nan")
        candidate_rps = float(np.mean(cand_rps_all)) if cand_rps_all else float("nan")
        # The OLD candidate-vs-chance sanity field (permutation_null refuses < the
        # pre-registered shuffles; on a tiny eval set it can raise -> record nan).
        try:
            null_p = _candidate_null_p(cand_probs_all, outcomes_all,
                                       shuffles=shuffles, seed=seed)
        except ValueError:
            null_p = float("nan")

        verdict = _verdict(mean_d=mean_d, p_value=paired_p_adj,
                           baseline_clv=baseline_clv, candidate_clv=candidate_clv,
                           tol=tol)
        if verdict == "accept":
            accepted.append(candidate)

        report[candidate] = {
            "mean_d": mean_d,
            "paired_p": paired_p,
            "paired_p_adj": paired_p_adj,
            "baseline_rps": baseline_rps,
            "candidate_rps": candidate_rps,
            "delta_rps": mean_d,                 # alias: paired mean RPS improvement
            "n_eval": n_eval,
            "null_p": null_p,                    # sanity field only (NOT the gate)
            "baseline_clv": baseline_clv,
            "candidate_clv": candidate_clv,
            "verdict": verdict,
        }

    report["_meta"] = {
        "cutoffs": list(cutoffs),
        "seed": seed,
        "is_synthetic": bool(any_synthetic),
        "clv_tol": tol,
        "permutation_shuffles": shuffles,
        "n_eval_total": n_eval_total,
        "multiplicity": ("bonferroni" if n_candidates > 1 else "none"),
        "n_candidates": n_candidates,
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
    spent on a defined model rather than left dangling."""
    reg = (LockboxRegistry.load(path=lockbox_path)
           if lockbox_path is not None else LockboxRegistry.load())

    def _eval() -> dict:
        metrics = _walkforward_arm(
            store, odds_samples, enabled=accepted, base_config=base_config,
            seed=seed, results_for_settle=results_for_settle, matches=matches,
            fit_kwargs=fit_kwargs, cache_dir=cache_dir,
        )
        _mrps = metrics.summary.get("mean_rps_model")
        return {
            "enabled": list(accepted),
            "mean_rps_model": float("nan") if _mrps is None else float(_mrps),
            "avg_clv": _avg_clv(metrics),
            "n_bets": len(metrics.bets),
            "is_synthetic": bool(metrics.is_synthetic),
        }

    return reg.evaluate_on_lockbox(_eval)
