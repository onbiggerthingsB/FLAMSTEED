import pytest

from wcmodel.dashboard.edges import edges_by_event


class _FakeRanked:
    is_synthetic = True
    opportunities = [{
        "event_key": ["Spain", "Morocco", "2026-06-11"], "staked": "home",
        "edge": 0.04, "liquidity": 50.0, "stake_signal": 1.1,
        "entry_odds": 2.5, "close_odds": 2.1,
        "model": {"home": 0.62, "draw": 0.24, "away": 0.14},
        "is_synthetic": True,
    }]
    non_bets = {"no_odds": 1}


def test_edges_carry_real_scan_fields_and_synthetic_taint():
    out = edges_by_event(_FakeRanked())
    key = ("Spain", "Morocco", "2026-06-11")
    node = out[key]
    assert node["staked"] == "home"
    assert node["edge"] == 0.04                       # scalar
    assert node["stake_signal"] == 1.1               # SIGNAL, not "stake"
    assert node["entry_odds"] == 2.5                  # scalar (staked side, decision-time ENTRY <= cutoff)
    assert node["is_synthetic"] is True              # taint rode in
    assert "stake" not in node                       # the wrong plan key is gone


def test_edge_node_omits_post_cutoff_close_and_bare_model(
):
    """HIGH-4 / MED-5 (C5 FOCAL Codex): the as-of-cutoff dashboard edge node must NOT carry

      * ``close_odds`` (HIGH-4) — the close is the latest <= kickoff line, i.e. FUTURE info at
        a pre-kickoff cutoff; publishing it in the as-of-cutoff snapshot LEAKS a post-cutoff
        price. Realized CLV (entry vs close) is the LIVE paper tracker's job (Phase 5), computed
        POST-match, not the as-of-cutoff dashboard.
      * ``model`` (MED-5) — a bare 1X2 probability triple escapes any gate (a naked-probability
        surface). The gated 1X2 lives in the fixture forecast's ``one_x_two`` (gate_fixture_
        forecast, all three outcomes), so the edge node must not duplicate an ungated copy.

    The dashboard edge node = exactly ``{staked, edge, stake_signal, entry_odds, is_synthetic}``.
    RED before the fix (the node carried close_odds + model); GREEN after."""
    out = edges_by_event(_FakeRanked())
    node = out[("Spain", "Morocco", "2026-06-11")]
    assert "close_odds" not in node, (
        "post-cutoff close_odds leaked into the as-of-cutoff dashboard edge node (HIGH-4)")
    assert "model" not in node, (
        "a bare, ungated 1X2 model triple escaped into the edge node (MED-5)")
    # The node carries EXACTLY the decision-time fields (no realized-CLV, no naked model).
    assert set(node) == {"staked", "edge", "stake_signal", "entry_odds", "is_synthetic"}


def test_missing_edge_is_a_coverage_gap_not_a_number():
    out = edges_by_event(_FakeRanked())
    assert ("Germany", "Japan", "2026-06-12") not in out   # no fabricated edge


def test_taint_propagates_if_either_ranked_or_opp_is_synthetic():
    class _Mixed:
        is_synthetic = False
        opportunities = [{
            "event_key": ["A", "B", "2026-06-11"], "staked": "home", "edge": 0.02,
            "liquidity": 10.0, "stake_signal": 0.5, "entry_odds": 2.0, "close_odds": 1.9,
            "model": {"home": 0.5, "draw": 0.3, "away": 0.2}, "is_synthetic": True,
        }]
        non_bets = {}
    out = edges_by_event(_Mixed())
    assert out[("A", "B", "2026-06-11")]["is_synthetic"] is True   # opp-level taint wins


def test_edge_node_does_not_read_model_or_close_so_their_absence_is_harmless():
    """MED-5 / HIGH-4 corollary: since the edge node no longer carries ``model`` or
    ``close_odds``, an opportunity LACKING them must NOT raise — the node is built purely from
    the decision-time fields. (Pre-fix, a missing ``model`` was a strict-read KeyError; that
    strict read is gone now that the bare model is dropped.)"""
    class _NoModelNoClose:
        is_synthetic = True
        opportunities = [{
            "event_key": ["A", "B", "2026-06-11"], "staked": "home", "edge": 0.02,
            "stake_signal": 0.5, "entry_odds": 2.0,
            "is_synthetic": True,   # NO "model", NO "close_odds" -> still builds the node
        }]
        non_bets = {}
    out = edges_by_event(_NoModelNoClose())          # must NOT raise
    assert set(out[("A", "B", "2026-06-11")]) == {
        "staked", "edge", "stake_signal", "entry_odds", "is_synthetic"}


def test_missing_opp_taint_defaults_NON_REAL_never_silently_real():
    class _NoTaint:
        is_synthetic = False        # ranked-level says real...
        opportunities = [{
            "event_key": ["A", "B", "2026-06-11"], "staked": "home", "edge": 0.02,
            "liquidity": 10.0, "stake_signal": 0.5, "entry_odds": 2.0, "close_odds": 1.9,
            "model": {"home": 0.5, "draw": 0.3, "away": 0.2},
            # NOTE: no "is_synthetic" on the opp -> must FAIL SAFE to True, not silently real
        }]
        non_bets = {}
    out = edges_by_event(_NoTaint())
    assert out[("A", "B", "2026-06-11")]["is_synthetic"] is True   # fail-safe NON-REAL
