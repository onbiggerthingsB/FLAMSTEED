import numpy as np
from wcmodel.sim.groups import group_table, rank_group


def _results(scores):  # 4 teams A,B,C,D; the 6 round-robin fixtures in this order
    fx = [("A", "B"), ("C", "D"), ("A", "C"), ("B", "D"), ("A", "D"), ("B", "C")]
    return {f: s for f, s in zip(fx, scores)}


def test_points_goal_diff_goals_ordering():
    r = _results([(2, 0), (1, 0), (2, 0), (1, 0), (2, 0), (1, 0)])
    table = group_table(["A", "B", "C", "D"], r)
    order = rank_group(["A", "B", "C", "D"], r, rng=np.random.default_rng(0))
    assert order[0] == "A"
    assert table["A"]["points"] == 9 and table["D"]["points"] == 0


def test_head_to_head_breaks_equal_points_and_gd():
    # A,B level on points/GD/GF (both 6/+1/2) with A having beaten B head-to-head
    # (A vs B = 1-0). C (4 pts) and D (1 pt) sit strictly below, so the tied cluster
    # is exactly {A, B} and ONLY the head-to-head mini-table can separate them. The
    # h2h table (A 3 pts vs B 0) resolves strictly -> A above B, RNG never invoked.
    r = _results([(1, 0), (0, 0), (0, 1), (1, 0), (1, 0), (1, 0)])
    order, random_used = rank_group(
        ["A", "B", "C", "D"], r, rng=np.random.default_rng(0), _return_random_used=True
    )
    assert order.index("A") < order.index("B")
    assert random_used is False  # head-to-head broke the tie; no random draw needed


def test_head_to_head_beats_all_group_goal_difference():
    # THE key precedence regression. FIFA 2026 applies head-to-head (a-c) BEFORE
    # all-group GD/GF (d-e). Construct A,B LEVEL on POINTS where A has the BETTER
    # all-group GD but B BEAT A head-to-head -> B must rank ABOVE A.
    #
    # Fixtures: A-B, C-D, A-C, B-D, A-D, B-C
    #   A-B = 1-2  (B beats A head-to-head)
    #   C-D = 0-0
    #   A-C = 5-0  (A big win)
    #   B-D = 1-0  (B win)
    #   A-D = 3-0  (A big win)
    #   B-C = 0-1  (B loses to C)
    # Resulting standings (overall):
    #   A: 6 pts, GF 9, GA 2, GD +7   <- BETTER all-group GD
    #   B: 6 pts, GF 3, GA 2, GD +1   <- WORSE all-group GD, but BEAT A head-to-head
    #   C: 4 pts                       (strictly below -> cluster is exactly {A,B})
    #   D: 1 pt                        (strictly below)
    # all-group GD says A>B (+7 vs +1); head-to-head says B>A (B won 2-1). They
    # DISAGREE -> this pins the precedence. OLD code (all-group GD first) ranked A
    # above B (RED). FIFA-correct code (h2h first) ranks B above A (GREEN).
    r = _results([(1, 2), (0, 0), (5, 0), (1, 0), (3, 0), (0, 1)])
    table = group_table(["A", "B", "C", "D"], r)
    assert table["A"]["points"] == table["B"]["points"] == 6
    assert table["A"]["gd"] > table["B"]["gd"]  # A has the better all-group GD
    order, random_used = rank_group(
        ["A", "B", "C", "D"], r, rng=np.random.default_rng(0), _return_random_used=True
    )
    assert order.index("B") < order.index("A")  # head-to-head (a-c) beats all-group GD (d)
    assert random_used is False  # head-to-head resolved it strictly; no random draw


def test_recursive_head_to_head_three_way_tie():
    # 3-way POINTS tie {A,B,C}; D last. The 3-way head-to-head mini-table separates
    # C (worst h2h GD) to the bottom of the cluster but leaves A and B STILL level
    # on (a-c). REAPPLYING a-c to just {A,B}'s mutual match (A beat B 2-0) separates
    # them -> final order A, B, C. A and B are IDENTICAL on all-group GD/GF, so ONLY
    # the recursive h2h reapply can separate them (proves the recursion is load-bearing).
    #
    # Fixtures: A-B, C-D, A-C, B-D, A-D, B-C
    #   A-B = 2-0, A-C = 1-2, B-C = 3-0  (the three mutual matches)
    #   A-D = 1-0, B-D = 1-0, C-D = 1-0  (each beats D -> equal points, D last)
    # Overall: A,B,C all 6 pts (A,B GD +2 GF 4 identical; C GD -1); D 0 pts.
    # 3-way h2h mini-table:  A (3 pts, GD +1, GF 3), B (3 pts, GD +1, GF 3),
    #                        C (3 pts, GD -2, GF 2)  -> C separates to bottom.
    # Reapply a-c to {A,B} (single match A-B = 2-0): A 3 h2h pts vs B 0 -> A above B.
    r = _results([(2, 0), (1, 0), (1, 2), (1, 0), (1, 0), (3, 0)])
    table = group_table(["A", "B", "C", "D"], r)
    assert table["A"]["points"] == table["B"]["points"] == table["C"]["points"] == 6
    assert table["A"]["gd"] == table["B"]["gd"] and table["A"]["gf"] == table["B"]["gf"]
    order, random_used = rank_group(
        ["A", "B", "C", "D"], r, rng=np.random.default_rng(0), _return_random_used=True
    )
    assert order == ["A", "B", "C", "D"]
    assert random_used is False  # fully resolved by recursive head-to-head; no random draw


def test_all_group_gd_breaks_tie_when_head_to_head_level():
    # A,B level on POINTS; their head-to-head is a DRAW (A-B = 1-1 -> identical on
    # a-c: 1 h2h pt, GD 0, GF 1 each). With head-to-head exhausted, all-group GD (d)
    # decides -> A (GD +3) ranks above B (GD +1). Proves d-e apply ONLY after h2h.
    #
    # Fixtures: A-B, C-D, A-C, B-D, A-D, B-C
    #   A-B = 1-1 (draw -> h2h level), A-C = 3-0 (A bigger win), B-D = 1-0 (B win),
    #   C-D = 0-0, A-D = 0-0, B-C = 0-0
    # Overall: A 5 pts GD +3, B 5 pts GD +1, C 2 pts, D 2 pts (both below cluster).
    r = _results([(1, 1), (0, 0), (3, 0), (1, 0), (0, 0), (0, 0)])
    table = group_table(["A", "B", "C", "D"], r)
    assert table["A"]["points"] == table["B"]["points"] == 5
    assert table["A"]["gd"] > table["B"]["gd"]
    order, random_used = rank_group(
        ["A", "B", "C", "D"], r, rng=np.random.default_rng(0), _return_random_used=True
    )
    assert order.index("A") < order.index("B")  # all-group GD breaks it once h2h is level
    assert random_used is False  # all-group GD resolved it; random tail not reached


def test_random_tail_is_seeded_and_can_reorder_total_ties():
    # Two teams identical on EVERY criterion incl. head-to-head -> only the random tail separates them.
    r = _results([(1, 1), (2, 0), (1, 0), (1, 0), (2, 2), (2, 2)])
    o1 = rank_group(["A", "B", "C", "D"], r, rng=np.random.default_rng(7))
    o2 = rank_group(["A", "B", "C", "D"], r, rng=np.random.default_rng(7))
    assert o1 == o2                              # same seed -> deterministic
    seen = {tuple(rank_group(["A", "B", "C", "D"], r, rng=np.random.default_rng(s))) for s in range(20)}
    assert len(seen) > 1                         # different seeds CAN reorder the total tie
