"""Pure scoreline-tail-mass + Wilson-CI helpers for the Phase-4a tail diagnostic.

Frame-in / value-out: NO I/O, NO network, NO fit, NO posterior. Every function
takes a normalized scoreline grid (or plain scalars) and returns a float / tuple,
so they unit-test against hand-computed values and compose into
``scripts/diagnose_tails.py`` without dragging the heavy model into a test.

The grid convention is the project's predict-time grid: ``grid[h, a] = P(home
goals = h, away goals = a)`` (the exact array ``Posterior.predict_scoreline``
returns; rows = home goals, columns = away goals). Tail-mass helpers are SUMS
over the cells satisfying an event; the favorite-oriented helpers take a
``fav_is_home`` flag so a match where the stronger team is AWAY sums the mirrored
region — that orientation is locked by a transpose-mirror test, so predicted and
realized are always scored on the SAME favorite side.

The four tail markets tested in Phase 4a (the spec thresholds):
  * P(favorite scores >= 4)        — :func:`fav_score_ge`   (k=4)
  * P(|goal difference| >= 3)      — :func:`abs_gd_ge`      (k=3)
  * P(total goals >= 5)            — :func:`total_ge`       (k=5)
  * P(favorite wins by >= 2)       — :func:`fav_margin_ge`  (k=2)
:func:`tail_masses` returns all four at the fixed thresholds in one call (the
PREDICTED side), and :func:`realized_tail_events` returns the matching 0/1
indicators from a realized score (the REALIZED side) with the SAME orientation
and thresholds, so they are apples-to-apples.
"""
from __future__ import annotations

import math

import numpy as np

# The four Phase-4a tail markets, keyed by their fixed thresholds (favorite goals
# >= 4, |GD| >= 3, total >= 5, favorite margin >= 2). Used by both the predicted
# (:func:`tail_masses`) and realized (:func:`realized_tail_events`) sides so the
# two are scored on the identical event set.
TAIL_THRESHOLDS = {
    "fav_score_ge4": 4,
    "abs_gd_ge3": 3,
    "total_ge5": 5,
    "fav_margin_ge2": 2,
}


def _hh_aa(grid: np.ndarray):
    """Return FULL-shape ``(H, A)`` integer index grids for ``grid[h, a]``.

    Both are broadcast to ``grid.shape`` so any elementwise comparison (e.g.
    ``H >= k``) yields a full 2-D boolean mask that indexes the grid directly —
    a half-broadcast ``(n_home, 1)`` mask would raise on a non-square grid."""
    n_home, n_away = grid.shape
    h, a = np.meshgrid(np.arange(n_home), np.arange(n_away), indexing="ij")
    return h, a


def fav_score_ge(grid: np.ndarray, *, fav_is_home: bool, k: int) -> float:
    """Grid mass with the FAVORITE's own goal count ``>= k``.

    ``fav_is_home`` selects which axis is the favorite: home goals (the row index)
    when True, away goals (the column index) when False. Orientation-aware:
    ``fav_score_ge(grid.T, fav_is_home=True, k) == fav_score_ge(grid,
    fav_is_home=False, k)`` (transpose swaps the home/away axes).
    """
    g = np.asarray(grid, dtype=float)
    h, a = _hh_aa(g)
    fav_goals = h if fav_is_home else a
    return float(g[fav_goals >= k].sum())


def abs_gd_ge(grid: np.ndarray, *, k: int) -> float:
    """Grid mass with the absolute goal difference ``|home - away| >= k``.

    Orientation-invariant (``|h - a| == |a - h|``)."""
    g = np.asarray(grid, dtype=float)
    h, a = _hh_aa(g)
    return float(g[np.abs(h - a) >= k].sum())


def total_ge(grid: np.ndarray, *, k: int) -> float:
    """Grid mass with the total goals ``home + away >= k``. Orientation-invariant."""
    g = np.asarray(grid, dtype=float)
    h, a = _hh_aa(g)
    return float(g[(h + a) >= k].sum())


def fav_margin_ge(grid: np.ndarray, *, fav_is_home: bool, k: int) -> float:
    """Grid mass with the SIGNED favorite margin ``(favorite - underdog goals) >= k``.

    A win for the underdog is a NEGATIVE favorite margin, so it never counts toward
    a positive ``k`` — "favorite wins by >= k" excludes upsets. Orientation-aware
    (mirrors under transpose, like :func:`fav_score_ge`)."""
    g = np.asarray(grid, dtype=float)
    h, a = _hh_aa(g)
    margin = (h - a) if fav_is_home else (a - h)
    return float(g[margin >= k].sum())


def tail_masses(grid: np.ndarray, *, fav_is_home: bool) -> dict:
    """The four Phase-4a PREDICTED tail masses at the fixed thresholds.

    Keys = :data:`TAIL_THRESHOLDS`: ``fav_score_ge4``, ``abs_gd_ge3``,
    ``total_ge5``, ``fav_margin_ge2``. ``fav_is_home`` orients the two
    favorite-specific markets."""
    return {
        "fav_score_ge4": fav_score_ge(grid, fav_is_home=fav_is_home, k=4),
        "abs_gd_ge3": abs_gd_ge(grid, k=3),
        "total_ge5": total_ge(grid, k=5),
        "fav_margin_ge2": fav_margin_ge(grid, fav_is_home=fav_is_home, k=2),
    }


def realized_tail_events(home_score: int, away_score: int, *, fav_is_home: bool) -> dict:
    """The four Phase-4a REALIZED 0/1 indicators from a realized score.

    Same keys / thresholds / orientation as :func:`tail_masses`, so the predicted
    grid mass and the realized indicator are apples-to-apples. ``fav_is_home``
    orients the favorite-specific markets (an upset is a negative favorite margin
    and a favorite goal count on the losing side, exactly as in the grid helpers)."""
    h, a = int(home_score), int(away_score)
    fav = h if fav_is_home else a
    und = a if fav_is_home else h
    return {
        "fav_score_ge4": int(fav >= 4),
        "abs_gd_ge3": int(abs(h - a) >= 3),
        "total_ge5": int(h + a >= 5),
        "fav_margin_ge2": int(fav - und >= 2),
    }


def wilson_ci(k: int, n: int, *, z: float = 1.96) -> tuple:
    """Closed-form Wilson score 95%-by-default binomial CI for ``k`` of ``n``.

    The Wilson interval is well-behaved at extreme proportions (0 or 1) and small
    ``n``, unlike the normal-approximation interval — appropriate for the rare
    tail events here. ``n == 0`` returns ``(nan, nan)`` (undefined, no division by
    zero). Returns ``(lo, hi)`` clipped to [0, 1] by construction of the formula."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1.0 - p) / n + z2 / (4 * n * n))) / denom
    # Clip to [0, 1] — the Wilson formula is bounded analytically, but floating-
    # point can produce a ~-1e-17 lower edge at k=0 (or ~1+1e-17 at k=n); a
    # probability interval must never report a negative/>1 bound.
    lo = min(max(centre - half, 0.0), 1.0)
    hi = min(max(centre + half, 0.0), 1.0)
    return (lo, hi)
