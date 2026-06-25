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

    # Score-validity hygiene + played filter via the SHARED `valid_played_results`
    # helper (the single definition, identical to features.build and
    # count_volatility_arm): a non-numeric/inf/negative/non-integral score -> NaN
    # -> dropped, so only finite, non-negative, whole-number scores (incl. a 0-0)
    # reach Elo — guaranteeing the baseline scores the model on the SAME row set
    # the fit and the provisional set consume.
    results = features.valid_played_results(results)

    results["match_type"] = results["tournament"].map(tiers.match_type)
    if results.empty:
        return {}

    # Thread the resolved `cfg` so the leakage-safe baseline Elo uses the PASSED
    # config's K/T params (not global disk) — keeps the lockbox's Elo-baseline
    # comparison config-consistent with the model fit. Only the K/T params move;
    # the `< cutoff` slice above (the leakage-safe window) is untouched, so the
    # baseline still never peeks past the cutoff.
    elo = compute_elo_history(
        results[["match_id", "date", "home_team", "away_team",
                 "home_score", "away_score", "neutral", "match_type"]],
        config=cfg,
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
        # Thread `cfg` so the baseline's home_advantage / draw_base come from the
        # PASSED config (not global disk), config-consistent with the threaded
        # ratings above and the model fit.
        elo_scores.append(
            rps(elo_1x2_baseline(r_home, r_away, neutral, config=cfg), outcome))

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


# ---------------------------------------------------------------------------
# Favorite-band reliability diagnostic (J/G/K Phase 1, READ-ONLY).
# Pure helpers + aggregation: no fit, no I/O. The walk-forward harness that fits
# the production model per cutoff lives in scripts/diagnose_favorite_band.py.
# ---------------------------------------------------------------------------

def grid_to_1x2(grid: np.ndarray) -> dict:
    """Collapse a (home,away) scoreline grid into the 1X2 distribution.

    ``grid[i, j] = P(home scores i, away scores j)``. Home win = lower triangle
    (i > j), draw = diagonal (i == j), away win = upper triangle (i < j). Mirrors
    ``posterior.predict_1x2`` exactly so the diagnostic 1X2 equals what the model
    ships. The grid is assumed already normalized (predict_scoreline output)."""
    g = np.asarray(grid, dtype=float)
    return {
        "home": float(np.tril(g, -1).sum()),
        "draw": float(np.trace(g)),
        "away": float(np.triu(g, 1).sum()),
    }


def grid_margin_stats(grid: np.ndarray) -> dict:
    """Expected goal margin and margin-tail probabilities from a scoreline grid.

    margin = |home - away|. Returns ``e_margin`` (sum |i-j| * p[i,j]) and
    ``p_marg_ge2`` / ``p_marg_ge3`` / ``p_marg_ge4`` (sum of p over cells with
    |i-j| >= k). The blowout-tail check for favorite-band calibration."""
    g = np.asarray(grid, dtype=float)
    n = g.shape[0]
    idx = np.arange(n)
    margin = np.abs(idx[:, None] - idx[None, :])
    return {
        "e_margin": float((margin * g).sum()),
        "p_marg_ge2": float(g[margin >= 2].sum()),
        "p_marg_ge3": float(g[margin >= 3].sum()),
        "p_marg_ge4": float(g[margin >= 4].sum()),
    }


# Favorite-probability buckets for the reliability diagnostic. Half-open
# [lo, hi); the top band's hi is 1.0+eps so a 1.0 favorite lands in it.
FAVORITE_BANDS = [
    (0.55, 0.65, "0.55-0.65"),
    (0.65, 0.75, "0.65-0.75"),
    (0.75, 0.85, "0.75-0.85"),
    (0.85, 1.0 + 1e-9, "0.85+"),
]


def _band_label(p_fav: float):
    """The band a favorite probability falls in, or None if p_fav < 0.55."""
    for lo, hi, label in FAVORITE_BANDS:
        if lo <= p_fav < hi:
            return label
    return None


def _aggregate_band(rows: list) -> dict:
    """Per-bucket reliability metrics for a list of favorite-fixture rows.

    Each row: {"probs": {home,draw,away}, "outcome": label,
    "realized_margin": int, "e_margin","p_marg_ge2/3/4": float}. The favorite
    side is derived per row (home if p_home >= p_away else away). Predicted rates
    are model means; realized rates are empirical frequencies; the favorite-win
    reliability SE is binomial sqrt(p(1-p)/n), used to flag miscalibration."""
    n = len(rows)
    if n == 0:
        return {
            "n": 0, "pred_fav_win": None, "real_fav_win": None,
            "pred_draw": None, "real_draw": None, "pred_dog_win": None,
            "real_dog_win": None, "mean_rps": None, "mean_logloss": None,
            "e_margin_pred": None, "e_margin_real": None,
            "pred_marg_ge2": None, "real_marg_ge2": None,
            "pred_marg_ge3": None, "real_marg_ge3": None,
            "pred_marg_ge4": None, "real_marg_ge4": None,
            "real_fav_win_se": None, "miscalibrated": None,
        }
    pred_fav, pred_draw, pred_dog = [], [], []
    real_fav, real_draw, real_dog = [], [], []
    rps_vals, ll_vals = [], []
    e_margin_pred, real_margin = [], []
    pred2, pred3, pred4 = [], [], []
    real2, real3, real4 = [], [], []
    for r in rows:
        p = r["probs"]
        fav_side = "home" if p["home"] >= p["away"] else "away"
        dog_side = "away" if fav_side == "home" else "home"
        pred_fav.append(p[fav_side]); pred_draw.append(p["draw"]); pred_dog.append(p[dog_side])
        real_fav.append(1.0 if r["outcome"] == fav_side else 0.0)
        real_draw.append(1.0 if r["outcome"] == "draw" else 0.0)
        real_dog.append(1.0 if r["outcome"] == dog_side else 0.0)
        rps_vals.append(rps(p, r["outcome"]))
        ll_vals.append(log_loss(p, r["outcome"]))
        e_margin_pred.append(float(r["e_margin"])); real_margin.append(float(r["realized_margin"]))
        pred2.append(float(r["p_marg_ge2"])); pred3.append(float(r["p_marg_ge3"])); pred4.append(float(r["p_marg_ge4"]))
        m = int(r["realized_margin"])
        real2.append(1.0 if m >= 2 else 0.0); real3.append(1.0 if m >= 3 else 0.0); real4.append(1.0 if m >= 4 else 0.0)
    rfw = float(np.mean(real_fav))
    se = float(np.sqrt(max(rfw * (1.0 - rfw), 0.0) / n))
    pfw = float(np.mean(pred_fav))
    # Miscalibrated iff the predicted favorite-win rate is outside the realized
    # +/-1.96*SE band (binomial). n==0 returned above.
    miscalibrated = bool(abs(pfw - rfw) > 1.96 * se) if se > 0 else bool(pfw != rfw)
    return {
        "n": n,
        "pred_fav_win": pfw, "real_fav_win": rfw,
        "pred_draw": float(np.mean(pred_draw)), "real_draw": float(np.mean(real_draw)),
        "pred_dog_win": float(np.mean(pred_dog)), "real_dog_win": float(np.mean(real_dog)),
        "mean_rps": float(np.mean(rps_vals)), "mean_logloss": float(np.mean(ll_vals)),
        "e_margin_pred": float(np.mean(e_margin_pred)), "e_margin_real": float(np.mean(real_margin)),
        "pred_marg_ge2": float(np.mean(pred2)), "real_marg_ge2": float(np.mean(real2)),
        "pred_marg_ge3": float(np.mean(pred3)), "real_marg_ge3": float(np.mean(real3)),
        "pred_marg_ge4": float(np.mean(pred4)), "real_marg_ge4": float(np.mean(real4)),
        "real_fav_win_se": se, "miscalibrated": miscalibrated,
    }


def favorite_band_reliability(rows: list, bands=FAVORITE_BANDS) -> dict:
    """Bucket favorite fixtures by model favorite probability and report
    predicted-vs-realized reliability per band, plus an ``all`` aggregate.

    A "favorite fixture" has p_fav = max(p_home, p_away) >= 0.55 (the lowest band
    floor); rows below that are ignored (not favorites). Returns
    {band_label: metrics, ..., "all": metrics}. Pure: no fit, no I/O."""
    by_band: dict = {label: [] for (_lo, _hi, label) in bands}
    favorites: list = []
    for r in rows:
        p = r["probs"]
        p_fav = max(float(p["home"]), float(p["away"]))
        label = _band_label(p_fav)
        if label is None:
            continue
        by_band[label].append(r)
        favorites.append(r)
    out = {label: _aggregate_band(by_band[label]) for (_lo, _hi, label) in bands}
    out["all"] = _aggregate_band(favorites)
    return out


def score_fixtures(posterior, heldout: pd.DataFrame, *, cutoff,
                   max_goals: int = _MAX_GOALS) -> list:
    """Score each held-out fixture with an already-fit ``posterior`` into a
    favorite-band row. Leakage guard: every held-out match must be dated on/after
    the cutoff DAY (the training window is strictly ``< cutoff``); a held-out row
    before the cutoff would mean fit-and-eval overlap and raises. Fixtures with a
    team the posterior never trained on are skipped (cannot be priced)."""
    cutoff_day = pd.Timestamp(cutoff)
    if cutoff_day.tz is not None:
        cutoff_day = cutoff_day.tz_convert("UTC").tz_localize(None)
    cutoff_day = cutoff_day.normalize()
    known = set(posterior.teams)
    rows: list = []
    for _, row in heldout.iterrows():
        d = pd.Timestamp(row["date"])
        if d.tz is not None:
            d = d.tz_convert("UTC").tz_localize(None)
        assert d.normalize() >= cutoff_day, (
            f"LEAKAGE: held-out match {row['home_team']} v {row['away_team']} "
            f"dated {d.date()} is before cutoff {cutoff_day.date()}")
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in known or away not in known:
            continue
        neutral = bool(row["neutral"])
        try:
            grid = posterior.predict_scoreline(home, away, neutral=neutral,
                                               max_goals=max_goals)
        except KeyError:
            continue
        probs = grid_to_1x2(grid)
        margin = grid_margin_stats(grid)
        hs, as_ = int(row["home_score"]), int(row["away_score"])
        rows.append({
            "home": home, "away": away,
            "probs": probs,
            "outcome": _outcome(hs, as_),
            "realized_margin": abs(hs - as_),
            "e_margin": margin["e_margin"],
            "p_marg_ge2": margin["p_marg_ge2"],
            "p_marg_ge3": margin["p_marg_ge3"],
            "p_marg_ge4": margin["p_marg_ge4"],
        })
    return rows
