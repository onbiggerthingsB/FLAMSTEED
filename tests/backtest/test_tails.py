"""Unit tests for the pure scoreline-tail-mass helpers (Phase 4a §2.4).

PURE helpers only — synthetic hand-checkable grids, NO fits, NO posterior, NO
network. ``grid[h, a] = P(home goals = h, away goals = a)``. Each test pins one
helper against a BY-HAND sum so the tail-mass arithmetic is non-vacuous:

  * ``fav_score_ge``   — favorite's own goal count >= k (orientation-aware).
  * ``abs_gd_ge``      — |home - away| >= k (orientation-invariant).
  * ``total_ge``       — home + away >= k (orientation-invariant).
  * ``fav_margin_ge``  — signed (favorite - underdog goals) >= k (orientation-aware).
  * ``tail_masses``    — the four at the spec thresholds (4, 3, 5, 2).
  * ``realized_tail_events`` — the four 0/1 realized indicators, SAME orientation.
  * ``wilson_ci``      — closed-form binomial CI (hand value + edge cases).

The orientation contract is locked by a MIRROR test: transposing the grid swaps
the home/away axes, so a favorite-home query on ``grid.T`` must equal a
favorite-away query on ``grid`` (and the symmetric markets are transpose-invariant).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from wcmodel.backtest import tails


# --------------------------------------------------------------------------- #
# Hand-checkable fixtures.
# --------------------------------------------------------------------------- #
def _grid_3x3():
    """A normalized 3x3 grid (home goals 0..2, away goals 0..2) with named masses.

    Layout grid[h, a]:
        a=0    a=1    a=2
    h=0 0.10   0.05   0.05
    h=1 0.15   0.10   0.05
    h=2 0.20   0.15   0.15
    Sums to 1.00.
    """
    g = np.array(
        [
            [0.10, 0.05, 0.05],
            [0.15, 0.10, 0.05],
            [0.20, 0.15, 0.15],
        ]
    )
    assert g.sum() == pytest.approx(1.0)
    return g


# --------------------------------------------------------------------------- #
# fav_score_ge
# --------------------------------------------------------------------------- #
def test_fav_score_ge_home_favorite_handcomputed():
    g = _grid_3x3()
    # favorite = home; P(home goals >= 2) = sum of row h=2 = 0.20+0.15+0.15 = 0.50.
    assert tails.fav_score_ge(g, fav_is_home=True, k=2) == pytest.approx(0.50)
    # P(home goals >= 1) = rows h=1,2 = (0.15+0.10+0.05)+(0.50) = 0.30+0.50 = 0.80.
    assert tails.fav_score_ge(g, fav_is_home=True, k=1) == pytest.approx(0.80)
    # k=0 -> whole grid.
    assert tails.fav_score_ge(g, fav_is_home=True, k=0) == pytest.approx(1.0)


def test_fav_score_ge_away_favorite_handcomputed():
    g = _grid_3x3()
    # favorite = away; P(away goals >= 2) = column a=2 = 0.05+0.05+0.15 = 0.25.
    assert tails.fav_score_ge(g, fav_is_home=False, k=2) == pytest.approx(0.25)


def test_fav_score_ge_orientation_mirror():
    """Transposing swaps home<->away: fav-home on grid.T == fav-away on grid."""
    g = _grid_3x3()
    for k in (1, 2):
        assert tails.fav_score_ge(g.T, fav_is_home=True, k=k) == pytest.approx(
            tails.fav_score_ge(g, fav_is_home=False, k=k)
        )


# --------------------------------------------------------------------------- #
# abs_gd_ge / total_ge  (orientation-invariant)
# --------------------------------------------------------------------------- #
def test_abs_gd_ge_handcomputed():
    g = _grid_3x3()
    # |h-a| >= 2: cells (h=2,a=0)=0.20 and (h=0,a=2)=0.05 -> 0.25.
    assert tails.abs_gd_ge(g, k=2) == pytest.approx(0.25)
    # |h-a| >= 1: everything off the diagonal. diagonal = 0.10+0.10+0.15 = 0.35.
    assert tails.abs_gd_ge(g, k=1) == pytest.approx(1.0 - 0.35)


def test_total_ge_handcomputed():
    g = _grid_3x3()
    # h+a >= 4: cells with h+a in {4}: (2,2)=0.15 -> 0.15.
    assert tails.total_ge(g, k=4) == pytest.approx(0.15)
    # h+a >= 3: (1,2)=0.05,(2,1)=0.15,(2,2)=0.15 -> 0.35.
    assert tails.total_ge(g, k=3) == pytest.approx(0.35)


def test_symmetric_markets_transpose_invariant():
    g = _grid_3x3()
    for k in (1, 2, 3, 4):
        assert tails.abs_gd_ge(g.T, k=k) == pytest.approx(tails.abs_gd_ge(g, k=k))
        assert tails.total_ge(g.T, k=k) == pytest.approx(tails.total_ge(g, k=k))


# --------------------------------------------------------------------------- #
# fav_margin_ge  (signed favorite margin)
# --------------------------------------------------------------------------- #
def test_fav_margin_ge_home_favorite_handcomputed():
    g = _grid_3x3()
    # favorite = home; (h - a) >= 2: cell (2,0)=0.20 only -> 0.20.
    assert tails.fav_margin_ge(g, fav_is_home=True, k=2) == pytest.approx(0.20)
    # (h - a) >= 1: (1,0)=0.15,(2,0)=0.20,(2,1)=0.15 -> 0.50.
    assert tails.fav_margin_ge(g, fav_is_home=True, k=1) == pytest.approx(0.50)


def test_fav_margin_ge_away_favorite_is_underdog_loss():
    g = _grid_3x3()
    # favorite = away; (a - h) >= 2: cell (h=0,a=2)=0.05 only -> 0.05.
    assert tails.fav_margin_ge(g, fav_is_home=False, k=2) == pytest.approx(0.05)


def test_fav_margin_ge_orientation_mirror():
    g = _grid_3x3()
    for k in (1, 2):
        assert tails.fav_margin_ge(g.T, fav_is_home=True, k=k) == pytest.approx(
            tails.fav_margin_ge(g, fav_is_home=False, k=k)
        )


# --------------------------------------------------------------------------- #
# tail_masses
# --------------------------------------------------------------------------- #
def test_tail_masses_keys_and_thresholds():
    g = _grid_3x3()
    out = tails.tail_masses(g, fav_is_home=True)
    assert set(out) == {"fav_score_ge4", "abs_gd_ge3", "total_ge5", "fav_margin_ge2"}
    # Each equals the individual helper at the fixed spec threshold.
    assert out["fav_score_ge4"] == pytest.approx(tails.fav_score_ge(g, fav_is_home=True, k=4))
    assert out["abs_gd_ge3"] == pytest.approx(tails.abs_gd_ge(g, k=3))
    assert out["total_ge5"] == pytest.approx(tails.total_ge(g, k=5))
    assert out["fav_margin_ge2"] == pytest.approx(tails.fav_margin_ge(g, fav_is_home=True, k=2))
    # On the tiny 3x3 grid the >=4 / >=5 events are impossible (max goals 2 each).
    assert out["fav_score_ge4"] == pytest.approx(0.0)
    assert out["total_ge5"] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# realized_tail_events
# --------------------------------------------------------------------------- #
def test_realized_tail_events_fav_home_blowout():
    # 5-0, favorite=home: fav scores 5 (>=4 yes), |GD|=5 (>=3 yes), total 5 (>=5 yes),
    # fav margin +5 (>=2 yes) -> all four 1.
    out = tails.realized_tail_events(5, 0, fav_is_home=True)
    assert out == {"fav_score_ge4": 1, "abs_gd_ge3": 1, "total_ge5": 1, "fav_margin_ge2": 1}


def test_realized_tail_events_goalless_draw():
    out = tails.realized_tail_events(0, 0, fav_is_home=True)
    assert out == {"fav_score_ge4": 0, "abs_gd_ge3": 0, "total_ge5": 0, "fav_margin_ge2": 0}


def test_realized_tail_events_underdog_win_does_not_count_fav_margin():
    # favorite=home, underdog (away) wins 0-3: fav scored 0 (<4), |GD|=3 (>=3 yes),
    # total 3 (<5), fav margin = 0-3 = -3 (<2 -> no). The upset is NOT a fav-by-2.
    out = tails.realized_tail_events(0, 3, fav_is_home=True)
    assert out == {"fav_score_ge4": 0, "abs_gd_ge3": 1, "total_ge5": 0, "fav_margin_ge2": 0}


def test_realized_tail_events_orientation_away_favorite():
    # away team is the favorite and wins 1-4: fav (away) scored 4 (>=4 yes),
    # |GD|=3 (>=3 yes), total 5 (>=5 yes), fav margin = 4-1 = 3 (>=2 yes) -> all four.
    out = tails.realized_tail_events(1, 4, fav_is_home=False)
    assert out == {"fav_score_ge4": 1, "abs_gd_ge3": 1, "total_ge5": 1, "fav_margin_ge2": 1}


# --------------------------------------------------------------------------- #
# wilson_ci
# --------------------------------------------------------------------------- #
def test_wilson_ci_symmetric_midpoint():
    lo, hi = tails.wilson_ci(5, 10)
    # 5/10 -> centred at 0.5, symmetric interval.
    assert lo < 0.5 < hi
    assert (0.5 - lo) == pytest.approx(hi - 0.5, abs=1e-12)
    # Hand value for z=1.96, p=0.5, n=10: centre = (0.5 + z^2/2n)/(1+z^2/n).
    z = 1.96
    denom = 1.0 + z * z / 10
    centre = (0.5 + z * z / 20) / denom
    half = (z * math.sqrt(0.25 / 10 + z * z / (4 * 100))) / denom
    assert lo == pytest.approx(centre - half, abs=1e-12)
    assert hi == pytest.approx(centre + half, abs=1e-12)


def test_wilson_ci_bounds_and_empty():
    lo, hi = tails.wilson_ci(0, 20)
    assert lo == pytest.approx(0.0, abs=1e-12) or lo >= 0.0
    assert 0.0 <= lo <= hi <= 1.0
    lo, hi = tails.wilson_ci(20, 20)
    assert 0.0 <= lo <= hi <= 1.0
    # n == 0 -> undefined interval (nan, nan), no division by zero.
    lo, hi = tails.wilson_ci(0, 0)
    assert math.isnan(lo) and math.isnan(hi)
