"""Pure: the ±1.5 goal-line cover probabilities, read off a normalized scoreline grid.

The grid ``g[h, a] = P(home goals = h, away goals = a)`` is the (already sum-1) output of
``posterior.predict_scoreline`` (rows = HOME, cols = AWAY — the orientation
``predict_1x2`` uses: home win = lower triangle ``np.tril(g, -1)``, h > a). This module takes
ONLY the grid — no model, no odds — so the line it prices comes purely from the model's goal
distribution (market-prior-free), exactly like ``markets/derived.py``'s ``totals_probs``, and
is trivially testable against hand-computed grids.

Half-goal line (no push):
  * P(home covers −1.5) = Σ g[h, a] over cells with ``h − a >= 2`` (home wins by >=2).
  * P(away covers +1.5) = 1 − P(home covers −1.5) (the complement; a ±1.5 line can never push).
The pair sums to exactly 1.0 by construction.
"""
from __future__ import annotations

import numpy as np


def cover_line(grid) -> dict[str, float]:
    """The ±1.5 goal-line cover pair ``{"home", "away"}`` from the scoreline grid.

    ``home`` = P(home covers −1.5) = Σ over cells with ``h − a >= 2``. ``away`` = P(away
    covers +1.5) = its complement (a half-goal line has no push, so the two outcomes partition
    the probability space and sum to 1 EXACTLY).

    A non-finite, non-positive-sum, or negative-mass grid is a broken predictive → raise
    (never fabricate a price), mirroring ``predict_scoreline`` / ``totals_probs``' guards.
    """
    g = np.asarray(grid, dtype=float)
    if g.ndim != 2 or g.shape[0] != g.shape[1]:
        raise ValueError(f"cover_line: grid must be a square 2D pmf, got shape {g.shape}")
    s = g.sum()
    if not np.isfinite(s) or s <= 0.0:
        raise ValueError("cover_line: non-finite or empty scoreline grid")
    if (g < 0).any():
        raise ValueError("cover_line: scoreline grid has negative mass (not a valid pmf)")
    n = g.shape[0]
    margin = np.arange(n)[:, None] - np.arange(n)[None, :]   # h − a per cell
    p_home = float(g[margin >= 2].sum())
    p_home = min(max(p_home, 0.0), 1.0)                      # clamp FP drift into [0, 1]
    return {"home": p_home, "away": 1.0 - p_home}
