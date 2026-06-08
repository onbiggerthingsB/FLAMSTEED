"""Pure: read derived-market probabilities off a normalized scoreline grid.

The grid ``g[h, a] = P(home goals = h, away goals = a)`` is the (already sum-1) output of
``posterior.predict_scoreline``. These functions take ONLY the grid — no model, no odds — so the
edge they price comes purely from the model's goal distribution (market-prior-free), and they are
trivially testable against hand-computed grids.
"""
from __future__ import annotations

import numpy as np

DEFAULT_LINES = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)


def totals_probs(grid, lines=DEFAULT_LINES) -> dict[float, dict[str, float]]:
    """Over/Under-total-goals probabilities for each line L: ``{L: {"over", "under"}}``.

    ``P(over L) = Σ g[h, a]`` over cells with ``h + a > L``; under is the complement. Because the
    grid is a normalized pmf, ``over + under == 1`` exactly. A non-finite or non-positive-sum grid
    is a broken predictive -> raise (never fabricate a price), mirroring predict_scoreline's guard.
    """
    g = np.asarray(grid, dtype=float)
    if g.ndim != 2 or g.shape[0] != g.shape[1]:
        raise ValueError(f"totals_probs: grid must be a square 2D pmf, got shape {g.shape}")
    s = g.sum()
    if not np.isfinite(s) or s <= 0.0:
        raise ValueError("totals_probs: non-finite or empty scoreline grid")
    n = g.shape[0]
    tot = np.arange(n)[:, None] + np.arange(n)[None, :]   # total goals per cell
    out: dict[float, dict[str, float]] = {}
    for L in lines:
        p_over = float(g[tot > L].sum())
        p_over = min(max(p_over, 0.0), 1.0)               # clamp FP drift into [0,1]
        out[float(L)] = {"over": p_over, "under": 1.0 - p_over}
    return out
