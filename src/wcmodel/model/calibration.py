"""Phase-2 calibration harness — IN-SAMPLE RPS vs the Elo baseline + PPC.

What this is (and is NOT)
-------------------------
This reports whether the Bayesian scoreline model has signal against the naive
Phase-1 Elo baseline, plus posterior-predictive sanity (does the model reproduce
the observed draw-rate / home-win-rate / mean total goals on the fixtures it was
fit on). It is a Phase-2 INTERNAL DIAGNOSTIC — there is NO betting here (that is
Phase 4).

**The same-cutoff RPS is IN-SAMPLE.** ``features.build(cutoff)`` returns exactly
the matches strictly before ``cutoff`` — i.e. the matches the model was FIT on —
so scoring those same matches is an in-sample fit check, NOT the betting bar.
``vs_elo_baseline`` therefore stamps ``in_sample=True``. Per the project rule, a
TOO-GOOD in-sample result (model RPS << Elo RPS) must be treated as a SUSPECTED
OVERFIT / leakage bug and SURFACED, never celebrated; the only honest verdict of
edge is the Phase-4 walk-forward, out-of-sample RPS/CLV.

Leakage-safe Elo baseline
-------------------------
The Elo baseline ratings come from the SAME ``< cutoff`` leakage-safe slice that
``features.build`` consumes — ``_leakage_safe_elo`` mirrors that slice EXACTLY
(tz-aware cutoff coerced to naive UTC; ``date < cutoff.normalize()``; the score-
validity + played filter; ``match_type`` via the tier taxonomy) and then runs the
single source-of-truth ``compute_elo_history``. We take each team's LATEST
``rating_post`` in that history (the as-of-cutoff rating, ordered by a stable
mergesort to match ``features._strength_bands``). No post-cutoff match ever
enters, so the baseline can never peek past the cutoff — the same discipline the
model fit obeys, so model and baseline are scored on identical information.

RPS literal
-----------
``rps`` is the standard 3-outcome ranked probability score over the ORDERED
outcomes ``("home","draw","away")``:

    RPS = (1/(r-1)) * sum_{i=1..r-1} (CP_i - CO_i)^2

where CP_i / CO_i are the cumulative predicted / observed probabilities and
``r = 3``. (The r-th cumulative is identically 1 for both, contributing 0, so the
sum stops at ``r-1``.) The task draft asserted ``rps({.5,.3,.2}, "away") ==
0.2725``; the standard formula gives **0.445**, so the test literal is corrected:
    observed=away -> cumulative observed [0,0,1]; cumulative predicted [.5,.8,1];
    RPS = (1/2)*[(.5-0)^2 + (.8-0)^2] = (1/2)*(0.25+0.64) = (1/2)*0.89 = 0.445.
No standard RPS variant (with/without the 1/(r-1) factor, either cumulation
direction) reproduces 0.2725, so 0.445 is the verified value.

Phase-4 extension (noted, NOT built here)
-----------------------------------------
A Phase-4 calibration harness must additionally let the lockbox compare the
pre-registered degrees of freedom on OUT-OF-SAMPLE data: the widening mechanism
((a) likelihood down-weight vs (c) predictive-variance inflation) and the
likelihood (Dixon-Coles vs bivariate-Poisson). Here we only score the CONFIGURED
model on its own fitted fixtures (in-sample); the DOF sweep + true walk-forward
RPS/CLV belong to Phase 4.

Reproducible & NULL-safe: ``vs_elo_baseline`` is a deterministic reduction over a
fitted ``Posterior`` (the seeded fit is the caller's); the played filter
guarantees integer goals so ``_outcome`` never sees a NaN score.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from wcmodel.config import load_config
from wcmodel.data import features, tiers
from wcmodel.data.elo import compute_elo_history, elo_1x2_baseline
from wcmodel.model.panel import to_match_panel

_OUTCOMES = ("home", "draw", "away")
_MAX_GOALS = 8  # 1X2 truncation depth for predict_1x2 (international goal rates)


def rps(probs: dict, outcome: str) -> float:
    """Standard 3-outcome ranked probability score (lower is better, in [0,1]).

    ``probs`` maps each of ``("home","draw","away")`` to a probability;
    ``outcome`` is the realised label. RPS = (1/(r-1)) * sum_{i=1..r-1}
    (CP_i - CO_i)^2 over the cumulative predicted (CP) / observed (CO)
    distributions in that fixed outcome order (r = 3). See module docstring for
    the corrected ``0.445`` worked example.
    """
    if outcome not in _OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; choose from {_OUTCOMES}")
    cp = 0.0
    co = 0.0
    s = 0.0
    for k in _OUTCOMES[:-1]:           # first r-1 cumulatives (r-th is 1 for both)
        cp += float(probs[k])
        co += 1.0 if k == outcome else 0.0
        s += (cp - co) ** 2
    return s / (len(_OUTCOMES) - 1)


def log_loss(probs: dict, outcome: str) -> float:
    """Negative log-likelihood of the realised ``outcome`` (prob clipped >=1e-15)."""
    if outcome not in _OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; choose from {_OUTCOMES}")
    return -math.log(max(float(probs[outcome]), 1e-15))


def _outcome(home_goals, away_goals) -> str:
    """Map a (home, away) goal pair to its 1X2 label."""
    h, a = int(home_goals), int(away_goals)
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def _leakage_safe_elo(store, cutoff, config=None) -> dict[str, float]:
    """Latest as-of-cutoff Elo ``rating_post`` per team, leakage-safe.

    Mirrors EXACTLY the ``< cutoff`` slice ``features.build`` feeds to
    ``compute_elo_history`` (do NOT recompute over a different/contaminated
    slice): tz-aware cutoff -> naive UTC; ``date < cutoff.normalize()``; the same
    score-validity hygiene + played filter; ``match_type`` via the tier taxonomy.
    Returns ``{team: latest rating_post}`` — each team's most-recent post-update
    rating in that history (ordered by a stable mergesort, matching
    ``features._strength_bands``), i.e. the best as-of-cutoff strength estimate
    that never peeks past the cutoff.
    """
    cfg = config or load_config()
    cutoff = pd.Timestamp(cutoff)
    # tz-aware cutoff -> naive UTC (mirror features.build day-floor semantics).
    if cutoff.tz is not None:
        cutoff = cutoff.tz_convert("UTC").tz_localize(None)
    cutoff_day = cutoff.normalize()

    results = store.read("results", cutoff=cutoff)
    results["date"] = pd.to_datetime(results["date"])
    if getattr(results["date"].dt, "tz", None) is not None:
        results["date"] = results["date"].dt.tz_convert("UTC").dt.tz_localize(None)
    results = results.loc[results["date"] < cutoff_day].copy()

    # Score-validity hygiene + played filter (identical to features.build): a
    # non-numeric/inf/negative/non-integral score -> NaN -> dropped, so only
    # finite, non-negative, whole-number scores (incl. a 0-0) reach Elo.
    for _c in ("home_score", "away_score"):
        s = pd.to_numeric(results[_c], errors="coerce")
        s = s.where(np.isfinite(s) & (s >= 0) & (s == s.round()))
        results[_c] = s
    results = results.loc[
        results["home_score"].notna() & results["away_score"].notna()].copy()

    results["match_type"] = results["tournament"].map(tiers.match_type)
    if results.empty:
        return {}

    elo = compute_elo_history(
        results[["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "neutral", "match_type"]]
    )
    last = (elo.sort_values("date", kind="mergesort")
               .groupby("team", sort=False)["rating_post"].last())
    return last.to_dict()


def vs_elo_baseline(posterior, store, cutoff, config=None) -> dict:
    """IN-SAMPLE model RPS vs the naive-Elo baseline over the fitted fixtures.

    Builds the cutoff match panel (the matches the model was fit on), recomputes
    the leakage-safe ``< cutoff`` Elo ratings (see ``_leakage_safe_elo``), then
    for EVERY match scores the model 1X2 (``posterior.predict_1x2``) and the Elo
    1X2 (``elo_1x2_baseline``) against the actual outcome. Returns the mean RPS of
    each, the match count, and ``in_sample=True``.

    ``in_sample=True`` is load-bearing: these are the FITTED matches, so a model
    RPS far below the Elo RPS is a SUSPECTED OVERFIT/leakage signal to surface —
    the honest edge verdict is the Phase-4 out-of-sample walk-forward.
    """
    cfg = config or load_config()
    mp = to_match_panel(features.build(cutoff, store, cfg))
    ratings = _leakage_safe_elo(store, cutoff, cfg)
    initial = cfg["elo"]["initial_rating"]

    model_scores: list[float] = []
    elo_scores: list[float] = []
    for row in mp.itertuples(index=False):
        outcome = _outcome(row.home_goals, row.away_goals)
        neutral = bool(row.neutral)

        model_p = posterior.predict_1x2(
            row.home_team, row.away_team, neutral=neutral, max_goals=_MAX_GOALS
        )
        model_scores.append(rps(model_p, outcome))

        # A team unseen in the < cutoff Elo history (e.g. a debutant whose only
        # appearances are at/after the cutoff) falls back to the shared initial
        # rating — the SAME no-faked-low-rating convention as compute_elo_history.
        r_home = ratings.get(row.home_team, initial)
        r_away = ratings.get(row.away_team, initial)
        elo_scores.append(rps(elo_1x2_baseline(r_home, r_away, neutral), outcome))

    n = len(model_scores)
    return {
        "model_rps": float(np.mean(model_scores)) if n else float("nan"),
        "elo_rps": float(np.mean(elo_scores)) if n else float("nan"),
        "n_matches": n,
        "in_sample": True,
    }


def posterior_predictive_checks(posterior, match_panel) -> dict:
    """Observed vs model-predicted aggregate rates over the fitted fixtures.

    Compares the OBSERVED draw-rate / home-win-rate / mean total goals on the
    panel the model was fit on against the model's PREDICTED expectations
    (``posterior.predict_scoreline`` -> 1X2 probs for the rates; the grid's
    expected total goals for the mean-total). A model that fits well should
    roughly reproduce these in-sample aggregates; a large gap is a
    misspecification signal. Returns ``{metric: {"obs": .., "pred": ..}}`` plus
    ``n_matches``.
    """
    n = len(match_panel)
    if n == 0:
        return {"draw_rate": {"obs": float("nan"), "pred": float("nan")},
                "home_win_rate": {"obs": float("nan"), "pred": float("nan")},
                "mean_total_goals": {"obs": float("nan"), "pred": float("nan")},
                "n_matches": 0}

    obs_draw = float((match_panel["home_goals"] == match_panel["away_goals"]).mean())
    obs_home = float((match_panel["home_goals"] > match_panel["away_goals"]).mean())
    obs_total = float((match_panel["home_goals"] + match_panel["away_goals"]).mean())

    pred_draw = []
    pred_home = []
    pred_total = []
    n_grid = _MAX_GOALS + 1
    idx = np.arange(n_grid)
    for row in match_panel.itertuples(index=False):
        neutral = bool(row.neutral)
        grid = posterior.predict_scoreline(
            row.home_team, row.away_team, neutral=neutral, max_goals=_MAX_GOALS
        )
        pred_home.append(float(np.tril(grid, -1).sum()))
        pred_draw.append(float(np.trace(grid)))
        # E[home goals] + E[away goals] from the (max_goals+1)^2 predictive grid.
        pred_total.append(
            float((grid.sum(axis=1) * idx).sum() + (grid.sum(axis=0) * idx).sum())
        )

    return {
        "draw_rate": {"obs": obs_draw, "pred": float(np.mean(pred_draw))},
        "home_win_rate": {"obs": obs_home, "pred": float(np.mean(pred_home))},
        "mean_total_goals": {"obs": obs_total, "pred": float(np.mean(pred_total))},
        "n_matches": n,
    }
