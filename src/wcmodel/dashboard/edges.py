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

WHAT THE EDGE NODE DOES CARRY (the GHOST LINE — spec §4 "ghost the sharp line into the
win-bar"). When the scan opportunity carries a VALID ``market_1x2`` — the de-vigged ENTRY
market 1X2 that the ``LiveDecision`` already computed via ``market_fair_1x2(ENTRY odds)`` —
the node emits it as ``market_1x2 = {home, draw, away}``. This is the SAME de-vigged ENTRY
distribution that DROVE the edge (``edge = model_fair - market_entry``), so it is:

  * LEAKAGE-SAFE — it is the de-vig of the DECISION-TIME ENTRY (<= cutoff), NEVER the close
    (which is post-cutoff and deliberately omitted above). The edge already trusts it.
  * a DERIVED COMPARISON, NOT a forecast estimate (like the edge itself) — so it carries NO
    uncertainty companion BY DESIGN; the frontend ghosts it into the win-bar inside a
    data-derived/distribution region (the no-naked-number guard exempts it consciously).

It is emitted ONLY where a VALID line exists — finite, all-three, each in [0, 1], summing to
~1 (the de-vig is a distribution). A missing or degenerate market 1X2 (a coverage-gap edge,
or an unsafe number) emits NO market line — never a fabricated/unsafe one.

So the dashboard edge node = the decision-time fields ``{staked, edge, stake_signal,
entry_odds, is_synthetic}`` PLUS the derived ``market_1x2`` WHEN a valid de-vigged ENTRY line
exists (else omitted)."""
from __future__ import annotations

import math

_OUTCOMES = ("home", "draw", "away")


def _safe_market_1x2(m) -> dict | None:
    """Return a fresh ``{home, draw, away}`` of floats IFF ``m`` is a valid de-vigged ENTRY
    1X2 distribution — finite, all three outcomes, each in [0, 1], summing to ~1 — else
    ``None`` (omit the line). A DERIVED comparison gated like the edge: finiteness + [0,1] +
    sum~1, NO uncertainty companion (by design). Coerces the source so a mutated source never
    mutates the bundle; never fabricates a number."""
    if not isinstance(m, dict) or not all(o in m for o in _OUTCOMES):
        return None
    try:
        vals = {o: float(m[o]) for o in _OUTCOMES}
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and 0.0 <= v <= 1.0 for v in vals.values()):
        return None
    if abs(sum(vals.values()) - 1.0) > 1e-6:
        return None
    return vals


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
        node = {
            "staked": opp["staked"],
            "edge": float(opp["edge"]),
            "stake_signal": float(opp["stake_signal"]),   # a SIGNAL, not a placed stake
            "entry_odds": float(opp["entry_odds"]),       # decision-time ENTRY (<= cutoff), staked-side scalar
            # taint if EITHER the scan or this opportunity is synthetic; the taint FAILS SAFE
            # to NON-REAL — a missing/changed opp taint defaults True, never silently real.
            "is_synthetic": ranked_synth or bool(opp.get("is_synthetic", True)),
        }
        # GHOST LINE: the de-vigged ENTRY market 1X2 (DERIVED comparison, leakage-safe — the
        # de-vig of the decision-time ENTRY odds <= cutoff that DROVE the edge, NEVER the
        # close). Emitted ONLY when valid (finite/[0,1]/sum~1); a missing/degenerate line is
        # OMITTED (no market line), never fabricated. NO uncertainty companion (derived).
        market_1x2 = _safe_market_1x2(opp.get("market_1x2"))
        if market_1x2 is not None:
            node["market_1x2"] = market_1x2
        out[key] = node
    return out
