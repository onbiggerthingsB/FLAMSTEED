"""Phase-2b host-effect estimator — pure (value-in / value-out).

Estimates ``k_elo`` — the host advantage as a multiple of the standard Elo home
advantage — from finals-tier host games given as
``{rating_home, rating_away, outcome}`` rows. ``k_elo = 1.0`` ≡ "hosts behave
like an ordinary home team"; ``k_elo = 0.0`` ≡ neutral. The host overperformance
is ``k_elo − 1.0`` in standard-home-advantage units (spec §1, pitfall 1).

This module does NO I/O, NO fit, NO network — it is unit-testable on synthetic
host games (see the mandatory recovery test). The win-expectancy mapping
``elo_host_probs`` re-derives the exact ``data.elo.elo_1x2_baseline`` formula but
with a VARIABLE home-advantage magnitude (so the estimator can sweep it); the
equivalence at aligned magnitudes is locked by a test.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize_scalar

# Outcome -> index into (pH, pD, pA), so neg_loglik picks the realised mass.
_OUTCOME_IDX = {"H": 0, "D": 1, "A": 2}


def elo_host_probs(
    rating_home: float,
    rating_away: float,
    k_elo: float,
    *,
    draw_base: float,
    home_advantage: float = 100.0,
) -> tuple[float, float, float]:
    """Elo win-expectancy -> (pH, pD, pA) with home advantage ``k_elo*home_advantage``.

    The SAME 3-line mapping as ``data.elo.elo_1x2_baseline`` (E sets the H/A
    split; draw mass ``p_draw = draw_base*(1-|2E-1|)`` peaks at ``draw_base`` for
    an even match), but with a VARIABLE home-advantage magnitude — ``k_elo``
    carries the multiplier, ``home_advantage`` (default 100) is the Elo unit.
    Clipped to >= 0 and renormalised to sum to 1.
    """
    dr = rating_home - rating_away + k_elo * home_advantage
    e = 1.0 / (1.0 + 10.0 ** (-dr / 400.0))

    p_draw = draw_base * (1.0 - abs(2.0 * e - 1.0))
    p_home = e - p_draw / 2.0
    p_away = (1.0 - e) - p_draw / 2.0

    p_home, p_draw, p_away = (max(p, 0.0) for p in (p_home, p_draw, p_away))
    total = p_home + p_draw + p_away
    return (p_home / total, p_draw / total, p_away / total)


def neg_loglik(
    k_elo: float,
    rows: list[dict],
    *,
    draw_base: float,
    home_advantage: float = 100.0,
) -> float:
    """Multinomial NLL of the realised H/D/A outcomes under ``elo_host_probs``.

    ``rows = [{"rating_home", "rating_away", "outcome": "H"|"D"|"A"}, ...]``;
    returns ``-sum log p(observed)``.
    """
    nll = 0.0
    for row in rows:
        probs = elo_host_probs(
            row["rating_home"], row["rating_away"], k_elo,
            draw_base=draw_base, home_advantage=home_advantage,
        )
        p = probs[_OUTCOME_IDX[row["outcome"]]]
        nll -= math.log(max(p, 1e-300))
    return nll


def estimate_k_elo(
    rows: list[dict],
    *,
    draw_base: float,
    home_advantage: float = 100.0,
) -> float:
    """MLE ``k_elo``: minimise ``neg_loglik`` on the bounded interval [-2, 8].

    Returns ``nan`` for empty rows.
    """
    if not rows:
        return float("nan")
    res = minimize_scalar(
        lambda k: neg_loglik(
            k, rows, draw_base=draw_base, home_advantage=home_advantage,
        ),
        bounds=(-2.0, 8.0),
        method="bounded",
        options={"xatol": 1e-6},
    )
    return float(res.x)


def bootstrap_k_ci(
    rows: list[dict],
    *,
    n_boot: int = 2000,
    seed: int = 0,
    draw_base: float,
    home_advantage: float = 100.0,
) -> dict:
    """Seeded MATCH-resample paired bootstrap CI for ``k_elo``.

    Resamples whole host-game rows with replacement (``np.random.default_rng(seed)``),
    re-estimates ``k_elo`` per resample, and returns the point estimate plus the
    2.5/97.5 percentile bounds: ``{"k", "lo95", "hi95"}``. Deterministic for a
    fixed seed. All-nan for empty rows.
    """
    if not rows:
        return {"k": float("nan"), "lo95": float("nan"), "hi95": float("nan")}

    k_point = estimate_k_elo(rows, draw_base=draw_base, home_advantage=home_advantage)

    rng = np.random.default_rng(seed)
    n = len(rows)
    boots = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        resample = [rows[i] for i in idx]
        boots[b] = estimate_k_elo(
            resample, draw_base=draw_base, home_advantage=home_advantage,
        )
    lo95, hi95 = np.percentile(boots, [2.5, 97.5])
    return {"k": float(k_point), "lo95": float(lo95), "hi95": float(hi95)}
