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
    assert node["entry_odds"] == 2.5 and node["close_odds"] == 2.1   # scalars (staked side)
    assert node["model"] == {"home": 0.62, "draw": 0.24, "away": 0.14}
    assert node["is_synthetic"] is True              # taint rode in
    assert "stake" not in node                       # the wrong plan key is gone


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
