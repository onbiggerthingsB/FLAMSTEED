"""Per-fixture edge overlay: re-keys the scanner's ranked opportunities by event so the
schedule/match-detail can attach the model-vs-line edge. Matches the real
``wcmodel.live.scan`` opportunity shape, but emits ONLY the as-of-cutoff, decision-time
fields. The synthetic taint is propagated onto every edge node — if EITHER the scan or the
opportunity is synthetic, the node is tainted (a NON-REAL edge can never read as real).

WHAT THE DASHBOARD EDGE NODE DELIBERATELY OMITS (C5 FOCAL Codex):

  * ``close_odds`` (HIGH-4). The close is the latest line <= kickoff, i.e. FUTURE information
    at a pre-kickoff cutoff. Publishing it in the AS-OF-CUTOFF snapshot would LEAK a
    post-cutoff price. Realized CLV (entry vs close) is the LIVE paper tracker's job (Phase 5),
    computed POST-match — NOT the as-of-cutoff dashboard. The edge itself (model_fair vs the
    de-vigged ENTRY) uses the decision-time ENTRY (<= cutoff) and stays. (The aggregate
    historical CLV in ``track.json`` is fine — that is backtest, where closes are known.)
  * ``model`` (MED-5). A bare 1X2 probability triple escapes every gate (a naked-probability
    surface). The gated model 1X2 lives in the per-fixture forecast's ``one_x_two`` (checked
    by ``gate_fixture_forecast``, all three outcomes) — the edge node must not duplicate an
    ungated copy.
  * ``liquidity``. The edge x liquidity ranking is the SCANNER's concern (``rank_key`` on the
    scan opportunity); the dashboard node carries only the decision-time fields the spec
    enumerates.

So the dashboard edge node = exactly ``{staked, edge, stake_signal, entry_odds, is_synthetic}``."""
from __future__ import annotations


def edges_by_event(ranked) -> dict:
    """Map ``(home, away, commence_date) -> edge node`` from a ``Ranked`` scan. A fixture
    absent from ``opportunities`` simply has no entry (the caller renders a coverage gap);
    nothing is fabricated.

    The decision-time fields are read STRICTLY (``opp[...]``): a missing one is a contract
    break and fails loud (``KeyError``) rather than silently degrading. ``close_odds`` and
    ``model`` are deliberately NOT read (see module docstring), so an opportunity lacking them
    still produces a valid node. The synthetic taint fails SAFE: a missing/changed
    ``is_synthetic`` defaults to ``True`` (NON-REAL), so a node can never silently read as
    real."""
    out: dict = {}
    ranked_synth = bool(getattr(ranked, "is_synthetic", False))
    for opp in getattr(ranked, "opportunities", []):
        key = tuple(opp["event_key"])
        out[key] = {
            "staked": opp["staked"],
            "edge": float(opp["edge"]),
            "stake_signal": float(opp["stake_signal"]),   # a SIGNAL, not a placed stake
            "entry_odds": float(opp["entry_odds"]),       # decision-time ENTRY (<= cutoff), staked-side scalar
            # taint if EITHER the scan or this opportunity is synthetic; the taint FAILS SAFE
            # to NON-REAL — a missing/changed opp taint defaults True, never silently real.
            "is_synthetic": ranked_synth or bool(opp.get("is_synthetic", True)),
        }
    return out
