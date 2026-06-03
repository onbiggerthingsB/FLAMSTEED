"""De-vig functions: bookmaker odds -> implied probabilities (overround removed).

Three methods, all pure math (no store/network):

- `multiplicative`: closed-form normalisation of inverse odds. The naive baseline;
  spreads the overround proportionally and so inherits the book's favourite-longshot
  bias.
- `power`: raises inverse odds to a single exponent k chosen so they sum to 1.
- `shin`: Shin (1992). Models a proportion z of inside (informed) money and solves
  for it; the primary method because it counteracts favourite-longshot bias —
  longshots get shrunk relative to `multiplicative`.

Shin is the method we trust by default; `multiplicative` and `power` are kept as
sensitivity checks. Deciding empirically which de-vig is best calibrated is Phase 4
work — here we only ship the functions.

Each function takes decimal odds and returns probabilities that sum to 1.0.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq


def multiplicative(odds: list[float]) -> list[float]:
    inv = np.array([1.0 / o for o in odds])
    return list(inv / inv.sum())


def power(odds: list[float]) -> list[float]:
    inv = np.array([1.0 / o for o in odds])
    f = lambda k: (inv ** k).sum() - 1.0
    k = brentq(f, 1e-6, 100.0)
    p = inv ** k
    return list(p / p.sum())


def shin(odds: list[float]) -> list[float]:
    """Shin (1992) de-vig: solve for insider proportion z s.t. probs sum to 1.

    With no overround (sum of inverse odds <= 1, e.g. a fair book) the insider
    proportion z is 0 and there is no interior root in the bracket. We detect the
    absent sign change and pin z at the lower bound, where probs reduce to the
    multiplicative result -- the correct zero-vig Shin limit.
    """
    lo, hi = 1e-9, 0.4
    pi = np.array([1.0 / o for o in odds]); s = pi.sum()
    def probs(z):
        return (np.sqrt(z**2 + 4*(1 - z)*pi**2 / s) - z) / (2*(1 - z))
    f = lambda z: probs(z).sum() - 1.0
    z = brentq(f, lo, hi) if f(lo) * f(hi) < 0 else lo
    p = probs(z)
    return list(p / p.sum())
