from wcmodel.sim.bracket import build_bracket


def test_bracket_parses_groups_and_knockout_graph(wc2026):
    b = build_bracket(wc2026)
    assert len(b.groups) == 12 and all(len(t) == 4 for t in b.groups.values())
    assert sum(len(f) for f in b.group_fixtures.values()) == 72       # 6 per group
    assert len(b.third_place_slots) == 8
    assert b.third_place_slots[74] == frozenset("ABCDF")
    assert b.third_place_slots[87] == frozenset("DEIJL")
    assert set(b.knockout_feeders) == set(range(73, 105))
    assert b.knockout_feeders[73] == ("2A", "2B")
    assert b.knockout_feeders[74] == ("1E", "3rd-ABCDF")
    assert b.knockout_feeders[89] == ("W74", "W77")
    assert b.match_round[73] == "R32" and b.match_round[104] == "Final"
