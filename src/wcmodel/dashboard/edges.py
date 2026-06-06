"""Per-fixture edge overlay: re-keys the scanner's ranked opportunities by event so the
schedule/match-detail can attach the model-vs-line edge. The scan's synthetic taint is
propagated onto every edge node (a synthetic edge can never read as real)."""
from __future__ import annotations


def edges_by_event(ranked) -> dict:
    """Map ``(home, away, commence_date) -> edge node`` from a ``Ranked`` scan. A fixture
    absent from ``opportunities`` simply has no entry (the caller renders a coverage gap);
    nothing is fabricated."""
    out: dict = {}
    synth = bool(getattr(ranked, "is_synthetic", False))
    for opp in getattr(ranked, "opportunities", []):
        key = tuple(opp["event_key"])
        out[key] = {
            "staked": opp["staked"],
            "edge": float(opp["edge"]),
            "liquidity": float(opp["liquidity"]),
            "stake": float(opp["stake"]),
            "entry_odds": opp["entry_odds"],
            "close_odds": opp["close_odds"],
            "is_synthetic": synth,        # taint rides the edge into the artifact
        }
    return out
