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


def test_random_tail_is_seeded_and_can_reorder_total_ties():
    # Two teams identical on EVERY criterion incl. head-to-head -> only the random tail separates them.
    r = _results([(1, 1), (2, 0), (1, 0), (1, 0), (2, 2), (2, 2)])
    o1 = rank_group(["A", "B", "C", "D"], r, rng=np.random.default_rng(7))
    o2 = rank_group(["A", "B", "C", "D"], r, rng=np.random.default_rng(7))
    assert o1 == o2                              # same seed -> deterministic
    seen = {tuple(rank_group(["A", "B", "C", "D"], r, rng=np.random.default_rng(s))) for s in range(20)}
    assert len(seen) > 1                         # different seeds CAN reorder the total tie
