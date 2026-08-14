"""Closing prices -> a probability forecast. BENCHMARK ONLY.

These functions exist to answer one question — "did the model beat the market?"
— and for no other purpose. Nothing here is displayed publicly and nothing here
is turned into a betting signal. That rule is absolute; see
:data:`epl.schema.ODDS_COLUMNS`.

Two methods, both closed-form-ish and both pure:

``proportional``
    Normalise the inverse prices. The naive baseline: it spreads the overround
    evenly across outcomes in proportion to price, so it inherits the book's
    favourite-longshot bias whole. This is the headline de-vig, because it is
    the one the published EPL bar (~0.196 RPS) is quoted on and the one with no
    free choices in it.
``shin``
    Shin (1992). Models a proportion ``z`` of informed money and solves for it,
    which shrinks longshots relative to ``proportional``. Reported alongside,
    never instead: preferring whichever de-vig scores better would be choosing
    the benchmark to suit the answer.

Both are re-implementations rather than imports of ``wcmodel.data.devig``, and
the package's tests assert they agree with it to 1e-12 on the real prices. The
duplication is the point: this probe must be able to state its market bar
without a dependency on a preregistration-locked module, and an independent
implementation that agrees is evidence, where an import would only be a
re-export.
"""

from __future__ import annotations

import numpy as np

__all__ = ["proportional", "shin", "overround", "MIN_OVERROUND"]

#: A real 1X2 book's inverse-price sum is its overround and is >= 1 by
#: construction. A row below this is not a tight book, it is a corrupt row.
MIN_OVERROUND = 1.0


def _inverse(odds: np.ndarray) -> np.ndarray:
    prices = np.asarray(odds, dtype=float)
    if prices.ndim != 2 or prices.shape[1] != 3:
        raise ValueError(f"expected an (n, 3) array of decimal odds in "
                         f"(home, draw, away) order; got {prices.shape}")
    if not np.isfinite(prices).all():
        raise ValueError("non-finite decimal odds — filter to complete rows "
                         "before de-vigging, do not impute a price")
    if (prices <= 1.0).any():
        bad = prices[(prices <= 1.0).any(axis=1)][:3]
        raise ValueError(f"decimal odds must exceed 1.0; got rows like {bad}")
    return 1.0 / prices


def overround(odds: np.ndarray) -> np.ndarray:
    """Per-row sum of inverse prices — the book's margin plus one."""
    return _inverse(odds).sum(axis=1)


def proportional(odds: np.ndarray) -> np.ndarray:
    """Inverse prices normalised to sum to 1. Shape ``(n, 3)``."""
    inv = _inverse(odds)
    total = inv.sum(axis=1, keepdims=True)
    if (total < MIN_OVERROUND - 1e-9).any():
        raise ValueError(
            f"{int((total < MIN_OVERROUND - 1e-9).sum())} row(s) have an "
            "inverse-price sum below 1, which no real book has; these are "
            "corrupt or mis-aligned price columns, not tight markets")
    return inv / total


def shin(odds: np.ndarray, tol: float = 1e-12, max_iter: int = 200,
         ) -> np.ndarray:
    """Shin (1992) de-vig, vectorised over rows. Shape ``(n, 3)``.

    Solves per row for the insider proportion ``z`` in ``[0, 0.4]`` such that

        p_i(z) = (sqrt(z^2 + 4 (1 - z) pi_i^2 / S) - z) / (2 (1 - z))

    sums to 1, where ``pi`` are the inverse prices and ``S`` their sum. The sum
    is monotone decreasing in ``z``, so a plain bisection is both sufficient and
    exactly reproducible — no optimizer state, no per-row branch on convergence
    flags. A book with no overround (``S = 1``) has ``z = 0``, where the formula
    reduces to :func:`proportional`; that is the correct zero-vig limit, and it
    is what the lower bracket returns.
    """
    inv = _inverse(odds)
    total = inv.sum(axis=1, keepdims=True)
    if (total < MIN_OVERROUND - 1e-9).any():
        raise ValueError("inverse-price sum below 1 — see `proportional`")

    def probs(z: np.ndarray) -> np.ndarray:
        z = z.reshape(-1, 1)
        return (np.sqrt(z ** 2 + 4.0 * (1.0 - z) * inv ** 2 / total) - z) / (
            2.0 * (1.0 - z))

    lo = np.zeros(inv.shape[0])
    hi = np.full(inv.shape[0], 0.4)
    # f(0) = S - 1 >= 0 and f is decreasing; if even z = 0.4 leaves the sum
    # above 1 the book is wider than Shin's window, which no Pinnacle 1X2
    # market is, so refuse rather than silently returning a hi-bound answer.
    if (probs(hi).sum(axis=1) > 1.0 + 1e-9).any():
        raise ValueError("Shin's insider proportion exceeds 0.4 on some row — "
                         "an overround far wider than any 1X2 book here")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f = probs(mid).sum(axis=1) - 1.0
        lo = np.where(f > 0.0, mid, lo)
        hi = np.where(f > 0.0, hi, mid)
        if np.max(hi - lo) < tol:
            break
    p = probs(0.5 * (lo + hi))
    return p / p.sum(axis=1, keepdims=True)
