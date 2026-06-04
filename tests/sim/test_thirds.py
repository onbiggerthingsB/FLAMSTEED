import json, numpy as np, pytest
from wcmodel.sim.thirds import rank_thirds, assign_thirds_to_slots, load_assignment_table

def test_rank_thirds_takes_best_8_of_12():
    thirds = {g: {"points": p, "gd": 0, "gf": 0}
              for g, p in zip("ABCDEFGHIJKL", [9,8,7,6,5,4,3,2,1,0,0,0])}
    best8 = rank_thirds(thirds, rng=np.random.default_rng(0))
    assert len(best8) == 8 and set(best8) == set("ABCDEFGH")   # top 8 by points

def test_rank_thirds_tiebreak_gd_gf_then_seeded():
    # ties at the 8/9 boundary resolved by GD -> GF -> seeded random
    thirds = {g: {"points": 5, "gd": d, "gf": 0} for g, d in
              zip("ABCDEFGHIJKL", [8,7,6,5,4,3,2,1,1,1,1,1])}  # H,I,J,K,L tie on (5,1,0)
    o1 = rank_thirds(thirds, rng=np.random.default_rng(3))
    o2 = rank_thirds(thirds, rng=np.random.default_rng(3))
    assert set(o1) == set(o2)                                  # seeded deterministic
    assert set("ABCDEFG") <= set(o1)                           # the clear top-7 always qualify

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
