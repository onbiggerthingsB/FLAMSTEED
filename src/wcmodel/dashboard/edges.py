"""Per-fixture edge overlay: re-keys the scanner's ranked opportunities by event so the
schedule/match-detail can attach the model-vs-line edge. Matches the real
``wcmodel.live.scan`` opportunity shape (stake_signal + scalar staked-side odds + the
model 1X2). The synthetic taint is propagated onto every edge node — if EITHER the scan
or the opportunity is synthetic, the node is tainted (a NON-REAL edge can never read as
real)."""
from __future__ import annotations


def edges_by_event(ranked) -> dict:
    """Map ``(home, away, commence_date) -> edge node`` from a ``Ranked`` scan. A fixture
    absent from ``opportunities`` simply has no entry (the caller renders a coverage gap);
    nothing is fabricated.

    Required opportunity fields are read STRICTLY (``opp[...]``): a missing one is a
    contract break and fails loud (``KeyError``) rather than silently degrading. The one
    exception is the synthetic taint, which fails SAFE: a missing/changed ``is_synthetic``
    defaults to ``True`` (NON-REAL), so a node can never silently read as real."""
    out: dict = {}
    ranked_synth = bool(getattr(ranked, "is_synthetic", False))
    for opp in getattr(ranked, "opportunities", []):
        key = tuple(opp["event_key"])
        out[key] = {
            "staked": opp["staked"],
            "edge": float(opp["edge"]),
            "liquidity": float(opp["liquidity"]),
            "stake_signal": float(opp["stake_signal"]),   # a SIGNAL, not a placed stake
            "entry_odds": float(opp["entry_odds"]),       # staked-side decimal odds (scalar)
            "close_odds": float(opp["close_odds"]),       # staked-side close (CLV only)
            "model": opp["model"],                         # STRICT: a missing model is a contract break -> fail loud
            # taint if EITHER the scan or this opportunity is synthetic; the taint FAILS SAFE
            # to NON-REAL — a missing/changed opp taint defaults True, never silently real.
            "is_synthetic": ranked_synth or bool(opp.get("is_synthetic", True)),
        }
    return out
