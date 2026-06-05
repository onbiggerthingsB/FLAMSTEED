"""Staking + simulated ROI: ¼-Kelly × posterior-uncertainty shrink, commission,
bankroll path, bootstrap CIs (north-star §5.7).

Stake sizing has three gates:
  1. EDGE TRIGGER — only bet when ``edge > edge_threshold`` (D5: 2pp; the trigger,
     NOT a lockbox DOF).
  2. ¼-KELLY — ``kelly_fraction`` (lockbox DOF #9, default 0.25) × the full-Kelly
     fraction ``f* = (b·p − q)/b`` (``b = decimal_odds − 1``), clamped at 0 (a
     non-positive Kelly = no edge = no bet).
  3. UNCERTAINTY SHRINK — scale the stake DOWN by the model's own posterior / MC
     standard error on that price: ``shrink = 1/(1 + k·SE)`` ∈ (0, 1]. A confident
     price (SE≈0) is unshrunk; a noisy price is shrunk toward zero. Uncertainty
     thus reduces exposure, never inflates it.

COMMISSION (D5). Pinnacle close = margin already in the line -> NO separate
commission. Betfair (if/when used) = 2% on NET winnings (losses are unaffected).

Outputs: the realised P&L per bet feeds ``bankroll_path`` + ``roi_metrics`` (ROI,
hit-rate, turnover, max drawdown both absolute + fractional) and seeded
``bootstrap_ci`` on any scalar metric.
"""
from __future__ import annotations

import numpy as np

#: Shrink sensitivity: stake multiplier = 1/(1 + _SHRINK_K * SE). Chosen so an SE
#: of ~0.1 (a very noisy progression price) roughly halves the stake.
_SHRINK_K = 10.0


def kelly_fraction_bet(*, prob: float, decimal_odds: float) -> float:
    """Full-Kelly stake fraction for a back bet, clamped at 0.

    ``f* = (b·p − q)/b`` with ``b = decimal_odds − 1``, ``q = 1 − p``. A
    non-positive result (no positive expectation) clamps to 0 (no bet).
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    f = (b * prob - (1.0 - prob)) / b
    return max(f, 0.0)


def uncertainty_shrink(*, se: float) -> float:
    """Posterior/MC-uncertainty stake multiplier in (0, 1]: ``1/(1 + k·SE)``.

    SE = 0 -> 1.0 (no shrink); larger SE -> smaller multiplier (more shrink). The
    shrink only ever SCALES DOWN exposure.
    """
    return 1.0 / (1.0 + _SHRINK_K * max(se, 0.0))


def stake_fraction(*, prob: float, decimal_odds: float, edge: float, se: float,
                   kelly_fraction: float, edge_threshold: float) -> float:
    """Bankroll fraction to stake: ¼-Kelly × uncertainty shrink, gated by the edge.

    Returns 0.0 unless ``edge > edge_threshold``; otherwise
    ``kelly_fraction × full_Kelly(prob, odds) × uncertainty_shrink(se)``.
    """
    if edge <= edge_threshold:
        return 0.0
    full = kelly_fraction_bet(prob=prob, decimal_odds=decimal_odds)
    return kelly_fraction * full * uncertainty_shrink(se=se)


def settle_bet(*, stake: float, decimal_odds: float, won: bool, venue: str,
               commission: dict) -> float:
    """Realised P&L of one settled back bet (commission per ``venue``).

    Win: gross profit = ``stake·(decimal_odds − 1)``; the venue's commission is
    taken on NET winnings (Pinnacle 0, Betfair 0.02). Loss: ``−stake`` (commission
    never applies to a loss).
    """
    if not won:
        return -stake
    gross = stake * (decimal_odds - 1.0)
    comm = commission.get(venue, 0.0)
    return gross * (1.0 - comm)


def bankroll_path(pnls: list[float], *, start: float) -> list[float]:
    """Cumulative bankroll after each bet, prefixed with the starting bankroll.

    ``len == len(pnls) + 1`` (index 0 is ``start``).
    """
    path = [start]
    for p in pnls:
        path.append(path[-1] + p)
    return path


def roi_metrics(*, pnls: list[float], stakes: list[float], start: float) -> dict:
    """ROI / hit-rate / turnover / max drawdown over a settled bet sequence.

    ROI = net P&L / turnover (sum of stakes); hit-rate = fraction of profitable
    bets; max drawdown = largest peak-to-trough drop of the bankroll path (both
    absolute and as a fraction of the running peak). Empty input -> zeros / NaN.
    """
    n = len(pnls)
    if n == 0:
        return {"roi": float("nan"), "hit_rate": float("nan"), "turnover": 0.0,
                "net": 0.0, "max_drawdown": 0.0, "max_drawdown_frac": 0.0}
    net = float(np.sum(pnls))
    turnover = float(np.sum(stakes))
    hit_rate = float(np.mean([p > 0 for p in pnls]))
    path = bankroll_path(pnls, start=start)
    peak = path[0]
    max_dd = 0.0
    max_dd_frac = 0.0
    for v in path:
        peak = max(peak, v)
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
        if peak > 0 and (dd / peak) > max_dd_frac:
            max_dd_frac = dd / peak
    return {
        "roi": net / turnover if turnover > 0 else float("nan"),
        "hit_rate": hit_rate,
        "turnover": turnover,
        "net": net,
        "max_drawdown": max_dd,
        "max_drawdown_frac": max_dd_frac,
    }


def bootstrap_ci(*, pnls: list[float], stakes: list[float], start: float,
                 metric: str, resamples: int, seed: int,
                 alpha: float = 0.05) -> tuple[float, float]:
    """Seeded bootstrap CI for a scalar ``roi_metrics`` field over the bet sequence.

    Resamples (bet, stake) pairs WITH replacement ``resamples`` times, recomputes
    ``metric``, and returns the ``[alpha/2, 1−alpha/2]`` percentile interval.
    Seeded (``np.random.default_rng(seed)``) so the CI is bit-reproducible.
    """
    rng = np.random.default_rng(seed)
    n = len(pnls)
    if n == 0:
        return (float("nan"), float("nan"))
    pnls_a = np.asarray(pnls, dtype=float)
    stakes_a = np.asarray(stakes, dtype=float)
    vals = np.empty(resamples)
    for i in range(resamples):
        idx = rng.integers(0, n, size=n)
        vals[i] = roi_metrics(pnls=list(pnls_a[idx]), stakes=list(stakes_a[idx]),
                              start=start)[metric]
    lo = float(np.nanpercentile(vals, 100 * alpha / 2))
    hi = float(np.nanpercentile(vals, 100 * (1 - alpha / 2)))
    return (lo, hi)
