import json, numpy as np, pytest
from wcmodel.sim.thirds import rank_thirds, assign_thirds_to_slots, load_assignment_table


class _NoRNG:
    """A sentinel rng whose .permutation must never be called. If rank_thirds touches
    it, the tie did NOT straddle the 8/9 qualification boundary and consuming RNG would
    spuriously perturb the shared per-sim stream -> hard failure."""
    def permutation(self, *a, **k):  # pragma: no cover - asserted not-called
        raise AssertionError(
            "rank_thirds consumed RNG without a genuine 8/9-boundary straddle"
        )


def test_rank_thirds_takes_best_8_of_12():
    thirds = {g: {"points": p, "gd": 0, "gf": 0}
              for g, p in zip("ABCDEFGHIJKL", [9,8,7,6,5,4,3,2,1,0,0,0])}
    best8 = rank_thirds(thirds, rng=np.random.default_rng(0))
    assert len(best8) == 8 and set(best8) == set("ABCDEFGH")   # top 8 by points


def test_rank_thirds_no_rng_for_tie_inside_top8():
    # A,B,C,D all tie on (9,0,0) -- but the tie is WHOLLY inside the top 8: all four
    # qualify regardless of internal order, and the 8/9 boundary (8th=2 pts, 9th=1 pt)
    # is a distinct key. No straddle -> rank_thirds must NOT consume RNG.
    thirds = {g: {"points": p, "gd": 0, "gf": 0}
              for g, p in zip("ABCDEFGHIJKL", [9,9,9,9,5,4,3,2,1,0,0,0])}
    best8 = rank_thirds(thirds, rng=_NoRNG())                  # sentinel: must not be called
    assert len(best8) == 8 and set(best8) == set("ABCDEFGH")
    # Seed-independent: the (non-)draw cannot depend on the stream.
    assert set(rank_thirds(thirds, rng=np.random.default_rng(7))) == set("ABCDEFGH")


def test_rank_thirds_no_rng_when_boundary_exact():
    # The boundary-key cluster fills EXACTLY to 8: G,H tie on (3,0,0) and together they
    # are precisely the 7th+8th slots (6 strictly-better A-F, 2 boundary-tied, 2 slots
    # left). No straddle -> all boundary-tied teams qualify deterministically, no RNG.
    thirds = {g: {"points": p, "gd": 0, "gf": 0}
              for g, p in zip("ABCDEFGHIJKL", [9,8,7,6,5,4,3,3,1,0,0,0])}
    best8 = rank_thirds(thirds, rng=_NoRNG())                  # sentinel: must not be called
    assert len(best8) == 8 and set(best8) == set("ABCDEFGH")


def test_rank_thirds_rng_only_on_boundary_straddle():
    # Genuine straddle: A-G strictly better (7 teams), then H,I,J tie on (2,1,0) for the
    # SINGLE remaining slot (3 boundary-tied teams > 1 slot). RNG decides which of the
    # three qualifies -- mirroring FIFA's drawing-of-lots, only when it decides
    # qualification. The qualifying SET therefore varies with the seed.
    thirds = {g: {"points": p, "gd": d, "gf": f} for g, (p, d, f) in zip(
        "ABCDEFGHIJKL",
        [(9,0,0),(8,0,0),(7,0,0),(6,0,0),(5,0,0),(4,0,0),(3,0,0),  # A-G clear top 7
         (2,1,0),(2,1,0),(2,1,0),                                  # H,I,J tie on (2,1,0)
         (1,0,0),(0,0,0)])}                                        # K,L eliminated
    base = set("ABCDEFG")                                         # always qualify

    s0 = set(rank_thirds(thirds, rng=np.random.default_rng(0)))   # -> J takes the slot
    s1 = set(rank_thirds(thirds, rng=np.random.default_rng(1)))   # -> H takes the slot
    s5 = set(rank_thirds(thirds, rng=np.random.default_rng(5)))   # -> I takes the slot

    for s in (s0, s1, s5):
        assert len(s) == 8 and base <= s                          # 7 clear + 1 of H/I/J
        assert len(s - base) == 1 and (s - base) <= set("HIJ")
    # The boundary draw genuinely changes WHICH team qualifies across seeds.
    assert s0 == {*base, "J"} and s1 == {*base, "H"} and s5 == {*base, "I"}
    assert len({frozenset(s0), frozenset(s1), frozenset(s5)}) == 3 # all distinct sets
    # Seed-deterministic: same seed -> same set.
    assert s0 == set(rank_thirds(thirds, rng=np.random.default_rng(0)))


def test_assignment_is_annexc_lookup_exact():
    # The oracle IS the sourced Annex C table. assign must reproduce it verbatim.
    tbl = load_assignment_table()
    for key in ["ABCDEFGH", "EFGHIJKL", "ACDEGIKL"]:           # spot combinations
        expected = {int(m): g for m, g in tbl["table"][key].items()}
        got = assign_thirds_to_slots(set(key))                 # {match_no: group}
        assert got == expected


def test_assignment_respects_eligibility_and_bijection():
    elig = {79:set("CEFHI"),85:set("EFGIJ"),81:set("BEFIJ"),74:set("ABCDF"),
            82:set("AEHIJ"),77:set("CDFGH"),87:set("DEIJL"),80:set("EHIJK")}
    a = assign_thirds_to_slots(set("ABCDEFGH"))
    assert sorted(a.values()) == sorted("ABCDEFGH")            # bijection onto the 8
    for m, g in a.items():
        assert g in elig[m]                                    # eligibility


def test_invalid_combination_raises():
    with pytest.raises((KeyError, ValueError)):
        assign_thirds_to_slots(set("ABCDEFG"))                 # only 7 -> not a valid combo
