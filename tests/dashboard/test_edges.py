from wcmodel.dashboard.edges import edges_by_event


class _FakeRanked:
    is_synthetic = True
    opportunities = [{
        "event_key": ["Spain", "Morocco", "2026-06-11"], "staked": "home",
        "edge": 0.04, "liquidity": 50.0, "stake": 1.1,
        "entry_odds": {"home": 2.5, "draw": 3.4, "away": 3.0},
        "close_odds": {"home": 2.1, "draw": 3.5, "away": 3.4},
    }]
    non_bets = {"no_odds": 1}


def test_edges_are_keyed_by_event_and_carry_synthetic_taint():
    out = edges_by_event(_FakeRanked())
    key = ("Spain", "Morocco", "2026-06-11")
    assert out[key]["edge"] == 0.04
    assert out[key]["staked"] == "home"
    assert out[key]["is_synthetic"] is True


def test_missing_edge_is_a_coverage_gap_not_a_number():
    out = edges_by_event(_FakeRanked())
    assert ("Germany", "Japan", "2026-06-12") not in out
