"""Leakage-safe totals backtest: model grid vs historical soft-book totals odds -> ROI + CLV.

Per row: the model fit is as-of the row's cutoff (trained on < cutoff); the edge/side/stake come from
the model grid vs the RAW ENTRY soft-book odds; the realized total settles the bet; CLV uses entry vs
close on the bet line. The model NEVER sees the odds. ``score_totals_row`` is pure given a posterior
(stub-testable).
"""
from __future__ import annotations

import numpy as np

from wcmodel.backtest.clv import clv_pct
from wcmodel.markets.derived import totals_probs
from wcmodel.markets.totals_edge import totals_edges


def _settle_total(line: float, side: str, *, home_goals: int, away_goals: int) -> bool:
    total = int(home_goals) + int(away_goals)
    return (total > line) if side == "over" else (total < line)


def score_totals_row(posterior, row: dict, *, lines, edge_threshold: float, se: float = 0.0) -> dict:
    """Score one fixture: derive totals probs from the model grid, place +EV picks vs ENTRY odds,
    settle vs the realized total, compute pnl (unit stake fraction) + CLV. Returns ``{"bets": [...]}``.
    A pick with no matching close line gets ``clv=None`` (recorded, not crashed)."""
    grid = posterior.predict_scoreline(row["home"], row["away"], neutral=row.get("neutral", True))
    mp = totals_probs(grid, lines=lines)
    picks = totals_edges(mp, row["entry"], edge_threshold=edge_threshold, se=se)
    hg, ag = row["home_goals"], row["away_goals"]
    bets = []
    for p in picks:
        won = _settle_total(p["line"], p["side"], home_goals=hg, away_goals=ag)
        # unit-stake pnl at the staked fraction: win -> stake*(odds-1); lose -> -stake
        pnl = p["stake"] * (p["odds"] - 1.0) if won else -p["stake"]
        close_line = row.get("close", {}).get(p["line"])
        close_odds = close_line.get(f"{p['side']}_odds") if close_line else None
        clv = clv_pct(entry_odds=p["odds"], close_odds=close_odds) if close_odds else None
        bets.append({**p, "won": won, "pnl": float(pnl), "clv": clv})
    return {"home": row["home"], "away": row["away"], "bets": bets}


def aggregate_totals(scored: list[dict]) -> dict:
    """Aggregate scored rows -> per-line + overall {n_bets, roi, beat_close_rate, avg_clv}.
    ROI = total pnl / total staked; beat_close_rate / avg_clv over bets with a non-None clv."""
    bets = [b for r in scored for b in r["bets"]]

    def _agg(bs: list[dict]) -> dict:
        if not bs:
            return {"n_bets": 0, "roi": float("nan"), "beat_close_rate": float("nan"),
                    "avg_clv": float("nan")}
        staked = sum(b["stake"] for b in bs)
        pnl = sum(b["pnl"] for b in bs)
        clvs = [b["clv"] for b in bs if b["clv"] is not None]
        return {"n_bets": len(bs),
                "roi": float(pnl / staked) if staked > 0 else float("nan"),
                "beat_close_rate": float(np.mean([c > 0 for c in clvs])) if clvs else float("nan"),
                "avg_clv": float(np.mean(clvs)) if clvs else float("nan")}

    by_line = {}
    for L in sorted({b["line"] for b in bets}):
        by_line[L] = _agg([b for b in bets if b["line"] == L])
    return {"overall": _agg(bets), "by_line": by_line}


def calibration_table(rows: list[dict], bins=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)) -> dict:
    """Reliability table for the model's P(over) vs realized over-rate, per predicted-prob bin.

    ``rows``: ``[{"line","p_over","over_hit"}]`` (one per scorable fixture/line — NOT only bet ones,
    so the diagnostic is unbiased by the bet filter). Returns ``{(lo, hi): {n, predicted, observed}}``
    where predicted = mean model P(over) in the bin, observed = realized over-rate. Under-confidence
    shows as predicted pulled toward 0.5 vs a more extreme observed.
    """
    edges = list(bins)
    out: dict[tuple, dict] = {}
    for lo, hi in zip(edges[:-1], edges[1:]):
        b = [r for r in rows if (lo <= r["p_over"] < hi) or (hi == edges[-1] and r["p_over"] == hi)]
        if not b:
            continue
        out[(lo, hi)] = {"n": len(b),
                         "predicted": float(np.mean([r["p_over"] for r in b])),
                         "observed": float(np.mean([1.0 if r["over_hit"] else 0.0 for r in b]))}
    return out
