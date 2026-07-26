"""AFC-2027 tiebreak registry: order dispatch + final-matchday penalties criterion.

Contract (plan Task 2, regs extract config/afc2027_rules_extract.md):
two-team dead tie (after all-group GD/GF) + drawn h2h + pairing in
``final_pairings`` => the afc_2027 path consumes exactly one ``permutation(2)``
per such tie (regs Art. 7.3.2.7, modeled as a seeded coin flip)."""
import pytest

from wcmodel.sim.groups import rank_group


class _NoRNG:
    def permutation(self, n):
        raise AssertionError("RNG must not be consulted")


class _SeqRNG:
    """Deterministic: permutation(n) returns identity; records calls."""
    def __init__(self):
        self.calls = []
    def permutation(self, n):
        self.calls.append(n)
        import numpy as np
        return np.arange(n)


def test_default_order_unchanged_and_no_pairings_needed():
    res = {("X", "Y"): (1, 0), ("X", "Z"): (1, 0), ("Y", "Z"): (1, 0)}
    assert rank_group(["X", "Y", "Z"], res, rng=_NoRNG()) == ["X", "Y", "Z"]


def test_unknown_order_raises():
    with pytest.raises(ValueError, match="unknown tiebreak order"):
        rank_group(["X", "Y"], {("X", "Y"): (1, 0)}, rng=_NoRNG(), order="uefa")


def _two_way_dead_tie():
    """P and Q: identical points/GD/GF overall AND h2h drawn; R, S detached.
    P-Q was the final-matchday game."""
    return ["P", "Q", "R", "S"], {
        ("P", "Q"): (1, 1), ("R", "S"): (0, 0),
        ("P", "R"): (2, 0), ("Q", "S"): (2, 0),
        ("P", "S"): (3, 1), ("Q", "R"): (3, 1),
    }


def test_afc_penalties_criterion_fires_on_final_md_draw():
    teams, res = _two_way_dead_tie()
    rng = _SeqRNG()
    out = rank_group(teams, res, rng=rng, order="afc_2027",
                     final_pairings={frozenset(("P", "Q")), frozenset(("R", "S"))})
    assert rng.calls == [2, 2]        # penalties coin-flips for P/Q AND R/S ties
    assert set(out[:2]) == {"P", "Q"}


def test_fifa_order_uses_random_tail_not_penalties():
    """Same inputs under fifa_2026: identical ranking route but the tie is
    broken by the generic seeded tail — final_pairings must be irrelevant."""
    teams, res = _two_way_dead_tie()
    rng = _SeqRNG()
    out = rank_group(teams, res, rng=rng, order="fifa_2026",
                     final_pairings={frozenset(("P", "Q"))})
    assert set(out[:2]) == {"P", "Q"}


def test_afc_without_pairings_falls_back_to_tail():
    teams, res = _two_way_dead_tie()
    rng = _SeqRNG()
    out = rank_group(teams, res, rng=rng, order="afc_2027", final_pairings=None)
    assert set(out[:2]) == {"P", "Q"}
