"""Realized-CLV PAPER tracker (Phase-5 §2.5) — the AUTHORITATIVE forward number.

An APPEND-ONLY paper bet-log: per signal we record the entry price (at decision
time), the eventual close, realized CLV (``entry/close - 1``, beat-close), and the
settled PAPER P&L. CLV-first reporting, stratified by tier. The whole thing is a
PAPER ledger (L2: no real bet is ever placed; project ROI stays simulated/paper).

REUSES Phase-4: ``clv_pct``/``beat_close``/``clv_summary`` (the CLV math),
``settle_bet`` (the venue-commission P&L — Pinnacle margin-in-line, Betfair 2% on net
winnings), ``roi_metrics`` (ROI/hit/turnover/drawdown), ``check_foresight_red`` (the
"too-good = bug" STOP). The ledger is the Phase-5 ``AppendOnlyLedger`` (immutable: a
re-logged signal raises ``ImmutableLogError``).

FORESIGHT-RED (L5). ``clv_report(..., check_red=True)`` runs ``check_foresight_red``
on the summary; a suspiciously-good live CLV/ROI => SUSPECTED feed/logging bug =>
raise (STOP, do not celebrate).
"""
from __future__ import annotations

import numpy as np

from wcmodel.config import load_config
from wcmodel.backtest.clv import beat_close, clv_pct, clv_summary
from wcmodel.backtest.report import MIN_STRATUM_N, render_stratum
from wcmodel.backtest.staking import roi_metrics, settle_bet
from wcmodel.backtest.validation import check_foresight_red
from wcmodel.live.validation import AppendOnlyLedger

#: The unmistakable NOT-REAL banner stamped on a synthetic/dry-run realized-CLV
#: report (mirrors the scanner's ``scan._DRY_RUN_BANNER``): a paper realized-CLV
#: report off the dry-run harness can never be mistaken for a funded forward number.
DRY_RUN_BANNER = (
    "DRY-RUN — NOT REAL / NOT A FORWARD EDGE CLAIM (Phase-5 synthetic/fixture "
    "harness; realized CLV is PAPER and non-real until the feed is funded + flipped on)"
)


def paper_pnl(*, stake: float, decimal_odds: float, won: bool, venue: str,
              commission: dict) -> float:
    """PAPER P&L of one settled signal — delegates to the Phase-4 ``settle_bet``
    (Pinnacle margin-in-line => no commission; Betfair => 2% on NET winnings; a loss
    is ``-stake``). PAPER only: no real bet was placed."""
    return settle_bet(stake=stake, decimal_odds=decimal_odds, won=won, venue=venue,
                      commission=commission)


class PaperClvTracker:
    """The append-only realized-CLV PAPER ledger (one JSONL record per settled signal)."""

    def __init__(self, path):
        self._ledger = AppendOnlyLedger(path)

    def log_signal(self, *, event_key: list, staked: str, entry_odds: float,
                   close_odds: float, stake: float, won: bool, match_type: str,
                   confederation: str, venue: str, commission: dict,
                   is_synthetic: bool) -> None:
        """Append one settled paper signal: entry/close/CLV/beat-close + paper P&L +
        tier tags. REFUSES a re-log of the same (event_key, staked) signal (the ledger
        is append-only / immutable — a logged entry can never be silently re-priced)."""
        rec = {
            "event_key": list(event_key), "staked": staked,
            "entry_odds": entry_odds, "close_odds": close_odds,
            "clv_pct": clv_pct(entry_odds=entry_odds, close_odds=close_odds),
            "beat_close": beat_close(entry_odds=entry_odds, close_odds=close_odds),
            "stake": stake, "won": bool(won),
            "paper_pnl": paper_pnl(stake=stake, decimal_odds=entry_odds, won=won,
                                   venue=venue, commission=commission),
            "match_type": match_type, "confederation": confederation,
            "paper": True,                     # L2: never a real bet
            "is_synthetic": bool(is_synthetic),  # L1: non-real until the feed is funded
        }
        self._ledger.append(rec)               # immutable: a re-log raises ImmutableLogError

    def records(self) -> list[dict]:
        return self._ledger.records()


def _stratify(records: list[dict], *, by: str) -> dict:
    """Group settled signals by a tier key and fold CLV + ROI per stratum, COVERAGE-
    GAPPING a thin tier per spec §1.2 ("a thin stratum is a coverage gap, never
    silently averaged").

    REUSES the project's thin-stratum chokepoint (``report.render_stratum`` /
    ``MIN_STRATUM_N`` = 30): each stratum is folded into ``{n_bets, clv_*, roi_*}`` and
    routed THROUGH ``render_stratum``, so a tier with ``< MIN_STRATUM_N`` settled
    signals renders as ``{"coverage_gap": True, "n_bets": k, "render":
    "insufficient coverage (n=k)"}`` with NO CLV/ROI number, and a healthy tier renders
    its metrics with ``coverage_gap=False``. A realized CLV on n=1 is meaningless +
    misleading — exactly what §1.2 forbids — so the number is WITHHELD for thin tiers
    via the SAME single ``< 30`` rule the backtest report enforces (one chokepoint,
    never re-implemented, never bypassed)."""
    groups: dict[str, list] = {}
    for r in records:
        groups.setdefault(r.get(by, ""), []).append(r)
    out: dict[str, dict] = {}
    for k, recs in groups.items():
        clv = clv_summary([{"entry_odds": r["entry_odds"], "close_odds": r["close_odds"]}
                           for r in recs])
        roi = roi_metrics(pnls=[r["paper_pnl"] for r in recs],
                          stakes=[r["stake"] for r in recs], start=1.0)
        # `render_stratum`/`stratum_is_coverage_gap` key on `n_bets` (the shared coverage
        # denominator), so fold the count under `n_bets` and let the chokepoint decide:
        # a thin tier yields the coverage-gap render (NO number); a healthy one its metrics.
        stratum = {"n_bets": len(recs),
                   **{f"clv_{kk}": vv for kk, vv in clv.items() if kk != "n_bets"},
                   **{f"roi_{kk}": vv for kk, vv in roi.items()}}
        out[k] = render_stratum(stratum)
    return out


def clv_report(records: list[dict], *, config: dict | None = None,
               check_red: bool = False) -> dict:
    """CLV-FIRST realized-CLV report over the paper ledger (the authoritative forward
    number). Leads with the beat-close rate + avg CLV (north-star §0), folds paper
    ROI, stratifies by match_type + confederation, and labels the whole thing non-real
    if any record is synthetic. With ``check_red=True`` runs the foresight-RED STOP on
    the summary (a too-good number => raise, not celebrate)."""
    clv = clv_summary([{"entry_odds": r["entry_odds"], "close_odds": r["close_odds"]}
                       for r in records])
    roi = roi_metrics(pnls=[r["paper_pnl"] for r in records],
                      stakes=[r["stake"] for r in records], start=1.0)
    summary = {**{f"clv_{k}": v for k, v in clv.items()},
               **{f"roi_{k}": v for k, v in roi.items()}}
    if check_red:
        # REUSED Phase-4 gate: a suspiciously-good live CLV/ROI => SUSPECTED bug => STOP.
        check_foresight_red(summary, config=config or load_config())
    is_synthetic = any(r.get("is_synthetic") for r in records)
    return {
        "summary": summary,                    # CLV-first
        "by_match_type": _stratify(records, by="match_type"),
        "by_confederation": _stratify(records, by="confederation"),
        "n_signals": len(records),
        "paper": True,                          # L2: simulated/paper, never real
        "is_synthetic": is_synthetic,
        # NOT-REAL BANNER (betting-safety): when ANY settled signal is synthetic/dry-run
        # the whole report carries an unmistakable banner (mirrors the scanner's report),
        # so a PAPER realized-CLV number off the dry-run harness can never be mistaken
        # for a funded forward edge. `None` on a (hypothetical) all-real ledger.
        "banner": DRY_RUN_BANNER if is_synthetic else None,
    }
