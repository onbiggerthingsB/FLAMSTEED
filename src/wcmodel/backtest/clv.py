"""Closing-Line Value — the PRIMARY number (north-star §0: CLV is the leading
indicator).

Two measures (north-star §5.3), both on the bet's PRICE (decimal odds):
  * ``clv_pct``  — ``entry_odds / close_odds - 1``. Positive iff you got a better
    (higher) decimal price than the close — i.e. you beat the sharp closing line.
  * ``beat_close`` — strictly positive CLV (equal-to-close is NOT a beat).

Entry = the price available at the decision time ``T_bet``; close = the Pinnacle
closing snapshot (kickoff−1 min). ``clv_summary`` aggregates a list of bets into
the beat-close rate + the average CLV% — reported FIRST in the backtest report.

CLV is measured on the BET (the side actually staked) at the de-vigged-selection
stage's chosen price; ``entry_odds``/``close_odds`` here are the raw decimal odds
for the staked outcome (de-vig affects the EDGE, not the price you transact at —
CLV compares transacted prices).
"""
from __future__ import annotations

import numpy as np


def clv_pct(*, entry_odds: float, close_odds: float) -> float:
    """``entry_odds / close_odds - 1`` — positive iff the entry price beats the close."""
    return entry_odds / close_odds - 1.0


def beat_close(*, entry_odds: float, close_odds: float) -> bool:
    """True iff the entry price STRICTLY beats the close (equal is not a beat)."""
    return entry_odds > close_odds


def clv_summary(bets: list[dict]) -> dict:
    """Aggregate ``[{entry_odds, close_odds}, ...]`` -> beat-close rate + avg CLV%.

    Returns ``{n_bets, beat_close_rate, avg_clv}``. An empty list yields
    ``n_bets=0`` with NaN metrics (no bets to summarise — never a divide-by-zero).
    """
    n = len(bets)
    if n == 0:
        return {"n_bets": 0, "beat_close_rate": float("nan"), "avg_clv": float("nan")}
    beats = sum(1 for b in bets if beat_close(entry_odds=b["entry_odds"],
                                              close_odds=b["close_odds"]))
    clvs = [clv_pct(entry_odds=b["entry_odds"], close_odds=b["close_odds"]) for b in bets]
    return {
        "n_bets": n,
        "beat_close_rate": beats / n,
        "avg_clv": float(np.mean(clvs)),
    }
