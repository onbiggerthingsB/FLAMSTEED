"""Favorite-band reliability diagnostic (Phase 1) — pure-function unit tests.

Covers the grid->1X2 / margin-tail helpers, the bucketed reliability aggregation,
and the leakage-guarded `score_fixtures` (with a fake posterior, no ADVI fit).
"""
import numpy as np
import pandas as pd
import pytest

from wcmodel.model.calibration import (
    FAVORITE_BANDS,
    favorite_band_reliability,
    grid_margin_stats,
    grid_to_1x2,
    score_fixtures,
)


# --- Task 1: grid_to_1x2 + grid_margin_stats --------------------------------

def _grid_from_pairs(pairs):
    """Build a (max+1)x(max+1) scoreline grid from {(h,a): prob} (auto-normalized)."""
    n = 1 + max(max(h, a) for (h, a) in pairs)
    g = np.zeros((n, n), dtype=float)
    for (h, a), p in pairs.items():
        g[h, a] = p
    return g / g.sum()


def test_grid_to_1x2_splits_home_draw_away():
    # 1-0 (home), 0-0 (draw), 0-1 (away) each 1/3.
    g = _grid_from_pairs({(1, 0): 1.0, (0, 0): 1.0, (0, 1): 1.0})
    p = grid_to_1x2(g)
    assert set(p) == {"home", "draw", "away"}
    assert pytest.approx(p["home"], abs=1e-9) == 1 / 3
    assert pytest.approx(p["draw"], abs=1e-9) == 1 / 3
    assert pytest.approx(p["away"], abs=1e-9) == 1 / 3
    assert pytest.approx(sum(p.values()), abs=1e-9) == 1.0


def test_grid_margin_stats_e_margin_and_tail():
    # 0-0 (margin0), 2-0 (margin2), 4-0 (margin4) each 1/3.
    g = _grid_from_pairs({(0, 0): 1.0, (2, 0): 1.0, (4, 0): 1.0})
    m = grid_margin_stats(g)
    assert pytest.approx(m["e_margin"], abs=1e-9) == (0 + 2 + 4) / 3
    assert pytest.approx(m["p_marg_ge2"], abs=1e-9) == 2 / 3   # margins 2 and 4
    assert pytest.approx(m["p_marg_ge3"], abs=1e-9) == 1 / 3   # only margin 4
    assert pytest.approx(m["p_marg_ge4"], abs=1e-9) == 1 / 3   # only margin 4


# --- Task 2: favorite_band_reliability --------------------------------------

def _row(p_home, p_draw, p_away, realized_outcome, realized_margin,
         e_margin=1.0, p2=0.3, p3=0.1, p4=0.03):
    return {
        "probs": {"home": p_home, "draw": p_draw, "away": p_away},
        "outcome": realized_outcome, "realized_margin": realized_margin,
        "e_margin": e_margin, "p_marg_ge2": p2, "p_marg_ge3": p3, "p_marg_ge4": p4,
    }


def test_bands_constant_covers_055_to_1():
    lows = [lo for (lo, hi, _label) in FAVORITE_BANDS]
    assert lows[0] == 0.55
    assert FAVORITE_BANDS[-1][1] >= 1.0


def test_favorite_band_reliability_buckets_and_rates():
    # Two fixtures in the 0.65-0.75 band: one home favorite that WON, one home
    # favorite that DREW. predicted fav-win = 0.70 (mean), realized = 0.5.
    rows = [
        _row(0.70, 0.20, 0.10, "home", 2),   # home favorite, won
        _row(0.70, 0.20, 0.10, "draw", 0),   # home favorite, drew
    ]
    out = favorite_band_reliability(rows)
    b = out["0.65-0.75"]
    assert b["n"] == 2
    assert b["pred_fav_win"] == pytest.approx(0.70, abs=1e-9)
    assert b["real_fav_win"] == pytest.approx(0.5, abs=1e-9)
    assert b["pred_draw"] == pytest.approx(0.20, abs=1e-9)
    assert b["real_draw"] == pytest.approx(0.5, abs=1e-9)
    assert np.isfinite(b["mean_rps"])
    assert out["all"]["n"] == 2


def test_favorite_band_reliability_away_favorite_counts_correctly():
    # Away favorite (p_away highest) that won -> real_fav_win should be 1.0.
    rows = [_row(0.10, 0.20, 0.70, "away", 1)]
    out = favorite_band_reliability(rows)
    assert out["0.65-0.75"]["real_fav_win"] == pytest.approx(1.0, abs=1e-9)


def test_favorite_band_reliability_empty_bucket_is_null_safe():
    out = favorite_band_reliability([])
    assert out["all"]["n"] == 0
    assert out["0.55-0.65"]["n"] == 0
    assert out["0.55-0.65"]["mean_rps"] is None


def test_favorite_band_reliability_ignores_non_favorites():
    # p_fav = 0.45 < 0.55 -> not a favorite fixture, dropped from every bucket.
    out = favorite_band_reliability([_row(0.45, 0.30, 0.25, "home", 1)])
    assert out["all"]["n"] == 0


# --- Task 3: score_fixtures (fake posterior, no ADVI) -----------------------

class _FakePosterior:
    """Minimal posterior: knows teams {A,B,C}; predict_scoreline returns a fixed
    home-tilted 3x3 grid (home favorite) regardless of inputs."""
    teams = ["A", "B", "C"]

    def predict_scoreline(self, home, away, neutral=False, max_goals=10,
                          covariates=None, host_factor=None):
        g = np.array([[0.10, 0.05, 0.02],
                      [0.30, 0.10, 0.03],
                      [0.20, 0.08, 0.12]], dtype=float)
        return g / g.sum()


def test_score_fixtures_builds_rows_and_skips_unknown_team():
    heldout = pd.DataFrame([
        {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 0,
         "neutral": False, "date": pd.Timestamp("2025-07-01")},
        {"home_team": "A", "away_team": "Z", "home_score": 1, "away_score": 1,
         "neutral": True, "date": pd.Timestamp("2025-07-02")},
    ])
    rows = score_fixtures(_FakePosterior(), heldout, cutoff="2025-06-01")
    assert len(rows) == 1                      # the Z fixture was skipped
    r = rows[0]
    assert set(r["probs"]) == {"home", "draw", "away"}
    assert r["outcome"] == "home"              # 2-0 -> home win
    assert r["realized_margin"] == 2
    assert 0.0 <= r["p_marg_ge2"] <= 1.0
    assert pytest.approx(sum(r["probs"].values()), abs=1e-9) == 1.0


def test_score_fixtures_rejects_heldout_before_cutoff():
    heldout = pd.DataFrame([
        {"home_team": "A", "away_team": "B", "home_score": 1, "away_score": 0,
         "neutral": False, "date": pd.Timestamp("2025-05-01")},
    ])
    with pytest.raises(AssertionError, match="LEAKAGE"):
        score_fixtures(_FakePosterior(), heldout, cutoff="2025-06-01")
