import numpy as np
import pandas as pd

from wcmodel.backtest.walkforward import (
    EloMemo, build_cutoff_grid, walkforward, Metrics,
)
from wcmodel.backtest.odds_ingest import synthetic_odds_sample


def test_elo_memo_matches_features_build_elo(small_store, cfg):
    """The memoised per-cutoff Elo must equal a from-scratch compute_elo_history on
    the SAME leakage-safe < cutoff slice (correctness preserved while skipping the
    O(N) recompute when the < cutoff result set is unchanged)."""
    from wcmodel.data.features import valid_played_results
    from wcmodel.data import tiers
    from wcmodel.data.elo import compute_elo_history

    cutoff = pd.Timestamp("2024-06-01")
    memo = EloMemo(small_store, config=cfg)
    got = memo.elo_as_of(cutoff)

    # Reference: replicate features.build's < cutoff_day, valid-played, K-wired input.
    res = small_store.read("results", cutoff=cutoff)
    res["date"] = pd.to_datetime(res["date"])
    res = res.loc[res["date"] < cutoff.normalize()].copy()
    res = valid_played_results(res)
    res["match_type"] = res["tournament"].map(tiers.match_type)
    ref = compute_elo_history(res[["match_id", "date", "home_team", "away_team",
                                   "home_score", "away_score", "neutral", "match_type"]],
                              config=cfg)
    # Latest rating_pre per team must match between memo and reference.
    g = got.sort_values("date").groupby("team")["rating_pre"].last()
    r = ref.sort_values("date").groupby("team")["rating_pre"].last()
    assert np.allclose(g.reindex(r.index).to_numpy(), r.to_numpy())


def test_elo_memo_is_cached_across_repeat_cutoffs(small_store, cfg):
    memo = EloMemo(small_store, config=cfg)
    a = memo.elo_as_of(pd.Timestamp("2024-06-01"))
    hits_before = memo.hits
    b = memo.elo_as_of(pd.Timestamp("2024-06-01"))     # identical < cutoff set -> cache hit
    assert memo.hits == hits_before + 1
    assert a.equals(b)


def _synthetic_run_inputs(small_store):
    """Build a one-event synthetic odds sample + the realised result that settles it,
    using teams + a date that exist in small_store (so the as-of-cutoff fit resolves).
    The settle result is a Brazil home win, and a model that likes Brazil at a juicy
    entry price gives a positive-edge bet. CLEARLY NON-REAL (synthetic harness)."""
    s = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2024-06-30T19:00:00Z",
        entry=(2.50, 3.40, 3.00),      # generous entry on Brazil
        close=(2.10, 3.50, 3.40),      # close drifts shorter on Brazil -> +CLV
        bookmaker="pinnacle", seed=0,
    )
    results_for_settle = pd.DataFrame([{
        "home_team": "Brazil", "away_team": "Croatia",
        "date": pd.Timestamp("2024-06-30"), "home_score": 2, "away_score": 0,
        "tournament": "FIFA World Cup",
    }])
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-30"])})
    return [s], results_for_settle, matches


def test_walkforward_runs_and_taints_synthetic(small_store):
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    m = walkforward(small_store, samples, results_for_settle=rfs, matches=matches,
                    fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    # The whole Metrics is tainted non-real (D1): no number here is ever an edge claim.
    assert m.is_synthetic is True and m.summary["is_synthetic"] is True
    # CLV + ROI summaries exist and the bet (if placed) recorded its tier + baselines.
    assert "clv_beat_close_rate" in m.summary and "roi_roi" in m.summary
    for b in m.bets:
        assert set(b["model"]) == {"home", "draw", "away"}
        assert "rps_market" in b and "rps_elo" in b
        # D1 rider: EVERY emitted per-bet record carries the SYNTHETIC marker.
        assert b["synthetic"] is True


def test_walkforward_cache_round_trips(tmp_path, small_store):
    samples, rfs, matches = _synthetic_run_inputs(small_store)
    kw = dict(results_for_settle=rfs, matches=matches,
              fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0},
              cache_dir=str(tmp_path))
    a = walkforward(small_store, samples, **kw)
    b = walkforward(small_store, samples, **kw)     # second call hits the content cache
    assert a.summary == b.summary
    assert (tmp_path).glob("walkforward-*.json")    # a cache artifact was written
