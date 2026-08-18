"""The accumulator and the Premier League ranker (plan v2 T3, decisions D7-D10).

Every ranker test here is a HAND-BUILT ORACLE: the season is constructed from an
all-0-0 double round-robin plus a handful of named overrides and a points-
adjustment vector, and the test asserts the intermediate table (points, goal
difference, goals for) BEFORE it asserts the ladder. That assertion is the
positive control — if a construction slips, the test says the table is not what
the author claimed rather than silently ranking something else.

The clauses under test (Premier League Handbook, as adjudicated in plan v2 D7/D8):

    C.4  points
    C.5  goal difference
    C.6  goals scored
    C.7  clubs still level share the position ... UNLESS the tie is *material*
    C.17 material tie: .1 head-to-head points among the block
                       .2 goals scored as the visiting club in the ORIGINAL
                          block's head-to-head matches (literal reading)
                       .3 two clubs still level -> play-off (no model here)
                       3+ clubs still level    -> no textual rule at all

Unresolved ties are allocated fractionally (D8), which is the Rao-Blackwellised
form of a coin flip: same expectation, zero added variance, and — asserted
below — no RNG in the ranker at all.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_table.py -q
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from epl import paths, season as season_mod, table as table_mod
from wcmodel.sim.groups import group_table

C = 20

#: The 2026/27 ladder, straight out of the manifest (plan v2 D7).
BOUNDARIES = ((1, 2), (4, 5), (5, 6), (6, 7), (7, 8), (17, 18))
RULE_ID = (
    "PL-2026-27:C4-C7+C17;material={1|2,4|5,5|6,6|7,7|8,17|18};"
    "h2h_away=original_set;unresolved=fractional;v1"
)


# ---------------------------------------------------------------------------
# season construction helpers
# ---------------------------------------------------------------------------

def _round_robin(n_clubs: int = C):
    """Every ordered pair (home, away), the 380-fixture double round-robin."""
    pairs = [(i, j) for i in range(n_clubs) for j in range(n_clubs) if i != j]
    return (np.array([p[0] for p in pairs], np.int16),
            np.array([p[1] for p in pairs], np.int16))


def _season(overrides: dict, adjustments, n_clubs: int = C):
    """One simulated season: 0-0 everywhere, then `overrides`, then adjustments.

    Returns (totals, scorelines, home_idx, away_idx). The 0-0 base leaves every
    club on 38 draws / 38 points / GF 0 / GA 0, so an override moves exactly the
    clubs it names and the arithmetic stays checkable by hand.
    """
    home, away = _round_robin(n_clubs)
    sl = np.zeros((1, home.size, 2), np.int8)
    for (h, a), (hg, ag) in overrides.items():
        f = int(np.flatnonzero((home == h) & (away == a))[0])
        sl[0, f, 0] = hg
        sl[0, f, 1] = ag
    adj = np.asarray(adjustments, np.int16)
    totals = table_mod.accumulate(sl, home, away, n_clubs=n_clubs, adjustments=adj)
    return totals, sl, home, away


def _rank(overrides, adjustments, n_clubs: int = C):
    totals, sl, home, away = _season(overrides, adjustments, n_clubs)
    ranking = table_mod.rank(totals, sl, home, away, BOUNDARIES, RULE_ID)
    return totals, ranking


def _row(arr):
    return arr[0].tolist()


def _random_season(rng, n_sims=1, n_clubs=C, mean=1.15):
    """Random low-scoring seasons — low means produce (pts, GD, GF) ties often
    enough for the shared/unresolved paths to be exercised."""
    home, away = _round_robin(n_clubs)
    sl = rng.poisson(mean, size=(n_sims, home.size, 2)).astype(np.int8)
    return sl, home, away


# ---------------------------------------------------------------------------
# the accumulator
# ---------------------------------------------------------------------------

def test_accumulate_matches_group_table_oracle():
    """200 random seasons against `wcmodel.sim.groups.group_table` (oracle only —
    the accumulator is vectorised and the oracle is a scalar dict walk)."""
    home, away = _round_robin()
    checked = 0
    for seed in range(200):
        rng = np.random.default_rng(seed)
        sl = rng.poisson(1.35, size=(1, home.size, 2)).astype(np.int8)
        totals = table_mod.accumulate(sl, home, away, n_clubs=C)

        results = {(int(h), int(a)): (int(sl[0, f, 0]), int(sl[0, f, 1]))
                   for f, (h, a) in enumerate(zip(home, away))}
        oracle = group_table(list(range(C)), results)
        for club in range(C):
            assert int(totals.pts[0, club]) == oracle[club]["points"], (seed, club)
            assert int(totals.gf[0, club]) == oracle[club]["gf"], (seed, club)
            assert int(totals.ga[0, club]) == oracle[club]["ga"], (seed, club)
            assert int(totals.gd[0, club]) == oracle[club]["gd"], (seed, club)
        checked += 1
    assert checked == 200


def test_accumulate_applies_adjustments_to_points_only():
    """A deduction moves points and nothing else (D16)."""
    adj = np.zeros(C, np.int16)
    adj[8] = -8
    adj[15] = -4
    sl, home, away = _random_season(np.random.default_rng(7))
    plain = table_mod.accumulate(sl, home, away, n_clubs=C)
    docked = table_mod.accumulate(sl, home, away, n_clubs=C, adjustments=adj)

    assert int(docked.pts[0, 8]) == int(plain.pts[0, 8]) - 8
    assert int(docked.pts[0, 15]) == int(plain.pts[0, 15]) - 4
    assert np.array_equal(docked.gd, plain.gd)
    assert np.array_equal(docked.gf, plain.gf)
    assert np.array_equal(docked.w, plain.w)


def test_identities_p_w_d_l_gd_sum_zero():
    """Every coherence identity of D10 that lives at table level, plus the
    positive control that the checker actually rejects a broken table."""
    sl, home, away = _random_season(np.random.default_rng(11), n_sims=50)
    adj = np.zeros(C, np.int16)
    adj[3] = -6
    totals = table_mod.accumulate(sl, home, away, n_clubs=C, adjustments=adj)

    assert np.all(totals.w + totals.d + totals.l == totals.fixtures_per_club)
    assert np.all(totals.fixtures_per_club == 2 * (C - 1))
    assert np.array_equal(totals.gd, totals.gf - totals.ga)
    assert np.all(totals.gd.sum(axis=1) == 0)
    assert np.array_equal(totals.gf.sum(axis=1), totals.ga.sum(axis=1))
    assert np.array_equal(totals.w.sum(axis=1), totals.l.sum(axis=1))
    assert np.array_equal(totals.pts, 3 * totals.w + totals.d + adj[None, :])

    table_mod.check_identities(totals)                    # green on the real thing

    broken = table_mod.Totals(                            # positive control
        pts=totals.pts.copy(), gd=totals.gd.copy(), gf=totals.gf.copy(),
        ga=totals.ga.copy(), w=totals.w.copy(), d=totals.d.copy(),
        l=totals.l.copy(), adjustments=totals.adjustments.copy(),
        fixtures_per_club=totals.fixtures_per_club.copy(),
    )
    broken.gf[0, 0] += 1                                  # one phantom goal
    with pytest.raises(table_mod.IdentityViolation):
        table_mod.check_identities(broken)


# ---------------------------------------------------------------------------
# C.4 -> C.5 -> C.6
# ---------------------------------------------------------------------------

#: Points/GD/GF separation, hand-built, with FOUR level pairs: two that check
#: the ladder is STABLE and two that DISCRIMINATE.
#:
#: `np.lexsort` is stable, so a pair whose winner already sits at the LOWER club
#: index proves nothing about the key that is supposed to separate them — delete
#: the key and the permutation comes out identical, and so does every block and
#: resolution code derived from it. Each stability pair below is therefore
#: matched by a pair whose winner sits at the HIGHER club index, which is the
#: only arrangement a dropped or reordered key can be caught by:
#:
#:    40 pts  club 0  (GD +2) over club 1 (GD  0)   C.5, stable   (0 <  1)
#:    34 pts  club 9  (GD +2) over club 2 (GD +1)   C.5, DISCRIMINATING (9 > 2)
#:            — and club 2 has the better GF (4 v 2), so this pair also flips if
#:              C.6 is ever ranked ahead of C.5
#:    33 pts  club 10 (GF  3) over club 5 (GF  2)   C.6, DISCRIMINATING (10 > 5)
#:    30 pts  club 3  (GF  1) over club 4 (GF  0)   C.6, stable   (3 <  4)
#:
#: Clubs 6-8 and 11-19 are separated on points alone and fill positions 1-12.
ORDER_OVERRIDES = {
    (0, 11): (2, 0),      # club 0:  W, GD +2, GF 2   (club 11: GD -2)
    (2, 12): (4, 3),      # club 2:  W, GD +1, GF 4   (club 12: GD -1)
    (3, 13): (1, 1),      # club 3:  D, GD  0, GF 1
    (5, 14): (2, 2),      # club 5:  D, GD  0, GF 2
    (9, 15): (2, 0),      # club 9:  W, GD +2, GF 2   (club 15: GD -2)
    (10, 16): (3, 3),     # club 10: D, GD  0, GF 3
}
#: The all-0-0 base leaves every club on 38 points; an override that is a win
#: adds 2 more, so each adjustment below is chosen against the POST-override
#: total to land the four level pairs at 40 / 34 / 33 / 30.
ORDER_ADJ = np.zeros(C, np.int16)
for _club, _adj in {
    0: 0, 1: 2,                            # 40, 40  — split by GD
    9: -6, 2: -6,                          # 34, 34  — split by GD
    10: -5, 5: -5,                         # 33, 33  — split by GF
    3: -8, 4: -8,                          # 30, 30  — split by GF
    6: 22, 7: 21, 8: 20, 11: 20, 12: 19,   # 60, 59, 58, 57, 56
    13: 17, 14: 16, 15: 16, 16: 14,        # 55, 54, 53, 52
    17: 13, 18: 12, 19: 11,                # 51, 50, 49
}.items():
    ORDER_ADJ[_club] = _adj

#: The whole ladder this fixture must produce: club index at each position.
ORDER_EXPECTED = [6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 0, 1, 9, 2, 10, 5, 3, 4]


def test_points_gd_gf_order():
    totals, ranking = _rank(ORDER_OVERRIDES, ORDER_ADJ)

    # the table the ladder is asked to rank (asserted, not assumed)
    def table_row(club):
        return (int(totals.pts[0, club]), int(totals.gd[0, club]),
                int(totals.gf[0, club]))

    assert table_row(0) == (40, 2, 2) and table_row(1) == (40, 0, 0)
    assert table_row(9) == (34, 2, 2) and table_row(2) == (34, 1, 4)
    assert table_row(10) == (33, 0, 3) and table_row(5) == (33, 0, 2)
    assert table_row(3) == (30, 0, 1) and table_row(4) == (30, 0, 0)

    start = _row(ranking.block_start)
    span = _row(ranking.block_span)
    code = _row(ranking.resolution_code)

    assert span == [1] * C, "no shared block should survive points/GD/GF here"

    # C.5 — goal difference
    assert start[0] == 13 and start[1] == 14          # stable pair, 0 beats 1
    assert code[0] == table_mod.GD and code[1] == table_mod.GD
    assert start[9] == 15 and start[2] == 16, (
        "club 9 wins on GD from the HIGHER club index: this is the pair that "
        "dies if -gd leaves the sort, or if -gf is ranked ahead of it")
    assert code[9] == table_mod.GD and code[2] == table_mod.GD

    # C.6 — goals scored
    assert start[10] == 17 and start[5] == 18, (
        "club 10 wins on GF from the HIGHER club index: this is the pair that "
        "dies if -gf leaves the sort")
    assert code[10] == table_mod.GF and code[5] == table_mod.GF
    assert start[3] == 19 and start[4] == 20          # stable pair, 3 beats 4
    assert code[3] == table_mod.GF and code[4] == table_mod.GF

    # C.4 alone
    assert start[6] == 1 and code[6] == table_mod.UNIQUE
    assert start[19] == 12 and code[19] == table_mod.UNIQUE

    # `order` is the ladder sequence: club index at each position
    assert _row(ranking.order) == ORDER_EXPECTED


# ---------------------------------------------------------------------------
# C.7 — the non-material shared block
# ---------------------------------------------------------------------------

SHARED_ADJ = np.zeros(C, np.int16)
for _i in range(10):
    SHARED_ADJ[_i] = 30 - _i         # 68 .. 59  -> positions 1..10
for _i in range(12, C):
    SHARED_ADJ[_i] = -(_i - 11)      # 37 .. 30  -> positions 13..20
# clubs 10 and 11 keep 38 -> level, positions 11-12


def test_nonmaterial_tie_is_shared_fractional():
    totals, ranking = _rank({}, SHARED_ADJ)

    assert int(totals.pts[0, 10]) == 38 and int(totals.pts[0, 11]) == 38
    assert int(totals.gd[0, 10]) == int(totals.gd[0, 11]) == 0

    start, span = _row(ranking.block_start), _row(ranking.block_span)
    code = _row(ranking.resolution_code)
    assert start[10] == start[11] == 11
    assert span[10] == span[11] == 2
    assert code[10] == code[11] == table_mod.SHARED_NONMATERIAL
    assert not table_mod.is_material(11, 2, BOUNDARIES)

    mass = table_mod.position_mass(ranking)
    assert mass[0, 10, 10] == pytest.approx(0.5)     # position 11, zero-based
    assert mass[0, 10, 11] == pytest.approx(0.5)
    assert mass[0, 11, 10] == pytest.approx(0.5)
    assert mass[0, 11, 11] == pytest.approx(0.5)
    assert mass[0].sum(axis=1) == pytest.approx(np.ones(C), abs=1e-8)
    assert mass[0].sum(axis=0) == pytest.approx(np.ones(C), abs=1e-8)

    sums = table_mod.position_mass_sums(ranking)
    assert sums.shared[10, 10] == pytest.approx(0.5)
    assert sums.unresolved_playoff.sum() == 0.0
    assert sums.unresolved_multiway.sum() == 0.0
    table_mod.check_doubly_stochastic(sums.matrix_prob)


# ---------------------------------------------------------------------------
# C.17.1 head-to-head points, then C.17.2 away goals
# ---------------------------------------------------------------------------

#: 17th/18th resolved by head-to-head POINTS. Club 16 beats club 17 at home and
#: draws away; club 18 is the compensator that levels the pair on GF and GD and
#: is pushed clear of them by one point.
H2H_PTS_OVERRIDES = {(16, 17): (2, 0), (17, 16): (0, 0),
                     (17, 18): (2, 0), (18, 16): (2, 0)}
H2H_PTS_ADJ = np.zeros(C, np.int16)
for _i in range(16):
    H2H_PTS_ADJ[_i] = 20 - _i        # 58 .. 43
H2H_PTS_ADJ[18] = -1                 # 39 - 1 = 38
H2H_PTS_ADJ[19] = -2                 # 38 - 2 = 36

#: 17th/18th level on head-to-head points (two draws) and separated only by
#: goals scored as the visiting club: 2 for club 16, 1 for club 17.
H2H_AWAY_OVERRIDES = {(16, 17): (1, 1), (17, 16): (2, 2)}
H2H_AWAY_ADJ = np.zeros(C, np.int16)
for _i in range(16):
    H2H_AWAY_ADJ[_i] = 20 - _i
H2H_AWAY_ADJ[18] = -1
H2H_AWAY_ADJ[19] = -2


def test_material_tie_uses_h2h_points_then_away_goals():
    totals, ranking = _rank(H2H_PTS_OVERRIDES, H2H_PTS_ADJ)

    assert int(totals.pts[0, 16]) == int(totals.pts[0, 17]) == 39
    assert int(totals.gd[0, 16]) == int(totals.gd[0, 17]) == 0
    assert int(totals.gf[0, 16]) == int(totals.gf[0, 17]) == 2
    assert table_mod.is_material(17, 2, BOUNDARIES)

    start, span = _row(ranking.block_start), _row(ranking.block_span)
    code = _row(ranking.resolution_code)
    assert (start[16], span[16]) == (17, 1)
    assert (start[17], span[17]) == (18, 1)
    assert code[16] == code[17] == table_mod.H2H_PTS

    totals2, ranking2 = _rank(H2H_AWAY_OVERRIDES, H2H_AWAY_ADJ)

    assert int(totals2.pts[0, 16]) == int(totals2.pts[0, 17]) == 38
    assert int(totals2.gd[0, 16]) == int(totals2.gd[0, 17]) == 0
    assert int(totals2.gf[0, 16]) == int(totals2.gf[0, 17]) == 3

    start2, span2 = _row(ranking2.block_start), _row(ranking2.block_span)
    code2 = _row(ranking2.resolution_code)
    assert (start2[16], span2[16]) == (17, 1)
    assert (start2[17], span2[17]) == (18, 1)
    assert code2[16] == code2[17] == table_mod.H2H_AWAY, (
        "head-to-head points are level here, so C.17.2 must be what separates them")


#: A three-way material block at 16-18 where C.17.1 leaves clubs 15 and 16
#: level, and the two readings of C.17.2 disagree:
#:   original-set (implemented) : club 16 has 3 away goals, club 15 has 2
#:   still-tied-subset (UEFA)   : club 15 has 2, club 16 has 1
ORIGINAL_SET_OVERRIDES = {
    (15, 16): (1, 1), (16, 15): (2, 2),
    (15, 17): (1, 0), (17, 15): (0, 0),
    (16, 17): (1, 0), (17, 16): (2, 2),
    (15, 18): (2, 2),                     # levels club 15's GF/GA with club 16
    (17, 18): (2, 0), (17, 19): (2, 1),   # levels club 17's points/GF/GA too
}
ORIGINAL_SET_ADJ = np.zeros(C, np.int16)
for _i in range(15):
    ORIGINAL_SET_ADJ[_i] = 20 - _i        # 58 .. 44, all clear of the block


def test_h2h_away_goals_use_original_block_matches():
    totals, ranking = _rank(ORIGINAL_SET_OVERRIDES, ORIGINAL_SET_ADJ)

    for club in (15, 16, 17):
        assert int(totals.pts[0, club]) == 40, club
        assert int(totals.gd[0, club]) == 1, club
        assert int(totals.gf[0, club]) == 6, club
    assert table_mod.is_material(16, 3, BOUNDARIES)

    among = {(h, a): (hg, ag) for (h, a), (hg, ag) in ORIGINAL_SET_OVERRIDES.items()
             if h in (15, 16, 17) and a in (15, 16, 17)}

    # the two readings really do disagree — otherwise this test proves nothing
    original_away = {15: 2, 16: 3, 17: 0}
    subset_away = {15: 2, 16: 1}
    assert sum(ag for (h, a), (hg, ag) in among.items() if a == 16) == original_away[16]
    assert sum(ag for (h, a), (hg, ag) in among.items() if a == 15) == original_away[15]
    assert among[(15, 16)][1] == subset_away[16]
    assert among[(16, 15)][1] == subset_away[15]
    assert (original_away[16] > original_away[15]) != (subset_away[16] > subset_away[15])

    ladder = table_mod.h2h_ladder([15, 16, 17], among)
    assert ladder == [((16,), table_mod.H2H_AWAY),
                      ((15,), table_mod.H2H_AWAY),
                      ((17,), table_mod.H2H_PTS)]

    start = _row(ranking.block_start)
    code = _row(ranking.resolution_code)
    assert start[16] == 16, "the original-set reading puts club 16 above club 15"
    assert start[15] == 17
    assert start[17] == 18
    assert code[16] == code[15] == table_mod.H2H_AWAY
    assert code[17] == table_mod.H2H_PTS
    assert _row(ranking.order)[15:18] == [16, 15, 17]


# ---------------------------------------------------------------------------
# C.17.3 and the case the Handbook does not cover
# ---------------------------------------------------------------------------

PLAYOFF_OVERRIDES = {(16, 17): (1, 1), (17, 16): (1, 1)}
PLAYOFF_ADJ = np.zeros(C, np.int16)
for _i in range(16):
    PLAYOFF_ADJ[_i] = 20 - _i
PLAYOFF_ADJ[18] = -1
PLAYOFF_ADJ[19] = -2

MULTIWAY_ADJ = np.zeros(C, np.int16)
for _i in range(15):
    MULTIWAY_ADJ[_i] = 20 - _i       # 58 .. 44
MULTIWAY_ADJ[18] = -1
MULTIWAY_ADJ[19] = -2                # clubs 15, 16, 17 keep 38 -> positions 16-18


def test_two_way_unresolved_is_playoff_half_half_and_flagged():
    totals, ranking = _rank(PLAYOFF_OVERRIDES, PLAYOFF_ADJ)

    assert int(totals.pts[0, 16]) == int(totals.pts[0, 17]) == 38
    assert int(totals.gf[0, 16]) == int(totals.gf[0, 17]) == 2

    start, span = _row(ranking.block_start), _row(ranking.block_span)
    code = _row(ranking.resolution_code)
    assert start[16] == start[17] == 17
    assert span[16] == span[17] == 2
    assert code[16] == code[17] == table_mod.UNRESOLVED_PLAYOFF

    sums = table_mod.position_mass_sums(ranking)
    assert sums.unresolved_playoff[16, 16] == pytest.approx(0.5)
    assert sums.unresolved_playoff[16, 17] == pytest.approx(0.5)
    assert sums.unresolved_playoff[17, 16] == pytest.approx(0.5)
    assert sums.unresolved_playoff[17, 17] == pytest.approx(0.5)
    assert sums.unresolved_playoff.sum() == pytest.approx(2.0)
    assert sums.unresolved_multiway.sum() == 0.0
    assert sums.shared.sum() == 0.0
    table_mod.check_doubly_stochastic(sums.matrix_prob)


def test_three_way_unresolved_is_multiway_third_each_and_flagged():
    totals, ranking = _rank({}, MULTIWAY_ADJ)

    for club in (15, 16, 17):
        assert int(totals.pts[0, club]) == 38, club

    start, span = _row(ranking.block_start), _row(ranking.block_span)
    code = _row(ranking.resolution_code)
    for club in (15, 16, 17):
        assert start[club] == 16 and span[club] == 3, club
        assert code[club] == table_mod.UNRESOLVED_MULTIWAY, club

    mass = table_mod.position_mass(ranking)
    for club in (15, 16, 17):
        for pos in (15, 16, 17):
            assert mass[0, club, pos] == pytest.approx(1.0 / 3.0)

    sums = table_mod.position_mass_sums(ranking)
    assert sums.unresolved_multiway.sum() == pytest.approx(3.0)
    assert sums.unresolved_playoff.sum() == 0.0
    table_mod.check_doubly_stochastic(sums.matrix_prob)


# ---------------------------------------------------------------------------
# the materiality gate itself
# ---------------------------------------------------------------------------

def test_material_predicate_exact_at_each_boundary():
    """Exact, not approximate: every two-club block in the table is classified."""
    assert not table_mod.is_material(3, 2, BOUNDARIES)     # {3,4}
    assert table_mod.is_material(4, 2, BOUNDARIES)         # {4,5}
    assert table_mod.is_material(17, 2, BOUNDARIES)        # {17,18}
    assert not table_mod.is_material(18, 2, BOUNDARIES)    # {18,19}

    material_starts = {s for s in range(1, C) if table_mod.is_material(s, 2, BOUNDARIES)}
    assert material_starts == {1, 4, 5, 6, 7, 17}

    # a block only has to CONTAIN both sides of a boundary
    assert table_mod.is_material(2, 4, BOUNDARIES)          # {2,3,4,5} spans 4|5
    assert not table_mod.is_material(8, 9, BOUNDARIES)      # {8..16} spans nothing
    assert not table_mod.is_material(5, 1, BOUNDARIES)      # a singleton is never a tie
    assert table_mod.is_material(16, 3, BOUNDARIES)         # {16,17,18} spans 17|18


def test_boundary_set_versioned_in_rule_id():
    manifest = season_mod.load_manifest("2026/27")
    assert manifest.tiebreak_rule_id == RULE_ID
    assert table_mod.parse_material_boundaries(RULE_ID) == tuple(
        tuple(b) for b in manifest.material_boundaries)

    totals, sl, home, away = _season({}, SHARED_ADJ)

    # positive control: the rule id is load-bearing, not decoration
    with pytest.raises(table_mod.RuleIdMismatch):
        table_mod.rank(totals, sl, home, away, ((1, 2), (17, 18)), RULE_ID)

    other = RULE_ID.replace("h2h_away=original_set", "h2h_away=tied_subset")
    with pytest.raises(table_mod.RuleIdMismatch):
        table_mod.rank(totals, sl, home, away, BOUNDARIES, other)

    with pytest.raises(table_mod.RuleIdMismatch):
        table_mod.rank(totals, sl, home, away, BOUNDARIES, "PL-2026-27:no-material-clause")


# ---------------------------------------------------------------------------
# D10 — the display matrix is doubly stochastic
# ---------------------------------------------------------------------------

def test_matrix_doubly_stochastic_on_random_seasons_1e_8():
    sl, home, away = _random_season(np.random.default_rng(2027), n_sims=400)
    totals = table_mod.accumulate(sl, home, away, n_clubs=C)
    ranking = table_mod.rank(totals, sl, home, away, BOUNDARIES, RULE_ID)

    mass = table_mod.position_mass(ranking)
    assert np.allclose(mass.sum(axis=2), 1.0, atol=1e-8)     # every club, one season
    assert np.allclose(mass.sum(axis=1), 1.0, atol=1e-8)     # every position, one season

    sums = table_mod.position_mass_sums(ranking)
    assert np.allclose(sums.matrix, mass.sum(axis=0), atol=1e-10)
    table_mod.check_doubly_stochastic(sums.matrix_prob, tol=1e-8)

    # positive control: the fractional path must actually have fired, or this
    # test only proves that a permutation matrix sums to one
    shared_or_unresolved = ranking.block_span > 1
    assert shared_or_unresolved.any(), "no tie block in 400 seasons — sample too small"

    # and the checker must reject a matrix that is not doubly stochastic
    bad = sums.matrix_prob.copy()
    bad[0, 0] += 1e-3
    with pytest.raises(table_mod.CoherenceViolation):
        table_mod.check_doubly_stochastic(bad, tol=1e-8)


def test_shared_and_unresolved_masses_are_a_subset_of_the_matrix():
    sl, home, away = _random_season(np.random.default_rng(99), n_sims=200)
    totals = table_mod.accumulate(sl, home, away, n_clubs=C)
    ranking = table_mod.rank(totals, sl, home, away, BOUNDARIES, RULE_ID)
    sums = table_mod.position_mass_sums(ranking)

    parts = sums.shared + sums.unresolved_playoff + sums.unresolved_multiway
    assert np.all(parts <= sums.matrix + 1e-9)
    assert sums.n_sims == 200
    assert np.allclose(sums.unresolved, sums.unresolved_playoff + sums.unresolved_multiway)


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------

ALL_CASES = (
    ("order", ORDER_OVERRIDES, ORDER_ADJ),
    ("shared", {}, SHARED_ADJ),
    ("h2h_pts", H2H_PTS_OVERRIDES, H2H_PTS_ADJ),
    ("h2h_away", H2H_AWAY_OVERRIDES, H2H_AWAY_ADJ),
    ("original_set", ORIGINAL_SET_OVERRIDES, ORIGINAL_SET_ADJ),
    ("playoff", PLAYOFF_OVERRIDES, PLAYOFF_ADJ),
    ("multiway", {}, MULTIWAY_ADJ),
)


def test_ranker_is_deterministic_and_consumes_no_rng(monkeypatch):
    seen = set()

    def _legacy_state():
        st = np.random.get_state()
        return st[0], st[1].tobytes(), st[2], st[3], st[4]

    def _forbidden(*a, **k):                       # any modern Generator use
        raise AssertionError("the ranker must not construct an RNG")

    monkeypatch.setattr(np.random, "default_rng", _forbidden)
    np.random.seed(20260611)
    before = _legacy_state()

    for name, overrides, adj in ALL_CASES:
        totals, sl, home, away = _season(overrides, adj)
        first = table_mod.rank(totals, sl, home, away, BOUNDARIES, RULE_ID)
        second = table_mod.rank(totals, sl, home, away, BOUNDARIES, RULE_ID)
        for field in ("block_start", "block_span", "resolution_code", "order"):
            assert np.array_equal(getattr(first, field), getattr(second, field)), (name, field)
        assert np.array_equal(table_mod.position_mass(first),
                              table_mod.position_mass(second)), name
        seen.update(int(c) for c in first.resolution_code[0])

    assert _legacy_state() == before, "the ranker touched the legacy RNG stream"
    assert seen == set(range(len(table_mod.RESOLUTION_NAMES))), (
        f"cases did not exercise every resolution code: saw {sorted(seen)}")

    # positive control 1: the legacy-state guard can detect consumption
    np.random.random()
    assert _legacy_state() != before

    # positive control 2: the default_rng guard is armed
    with pytest.raises(AssertionError):
        np.random.default_rng(0)


def test_rank_20000_seasons_under_two_seconds():
    """Plan v2 T3 acceptance: 20,000 seasons ranked in under 2 s, excluding the
    rare head-to-head path (random seasons essentially never hit it)."""
    sl, home, away = _random_season(np.random.default_rng(5), n_sims=20_000, mean=1.35)
    totals = table_mod.accumulate(sl, home, away, n_clubs=C)
    start = time.perf_counter()
    ranking = table_mod.rank(totals, sl, home, away, BOUNDARIES, RULE_ID)
    elapsed = time.perf_counter() - start
    assert ranking.block_start.shape == (20_000, C)
    assert elapsed < 2.0, f"rank took {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# the realised table (D16 + the T1 hand-off)
# ---------------------------------------------------------------------------

def _archive_2023_24():
    if not paths.MATCHES_PARQUET.exists():
        pytest.skip(f"archive parquet absent ({paths.MATCHES_PARQUET}) — gitignored input")
    import pandas as pd
    frame = pd.read_parquet(paths.MATCHES_PARQUET)
    frame = frame[frame["season"] == "2023/24"]
    if len(frame) != 380:
        pytest.skip("archive does not hold a complete 2023/24")
    return {(r.home_key, r.away_key): (int(r.fthg), int(r.ftag))
            for r in frame.itertuples()}


def test_realised_2023_24_positions():
    results = _archive_2023_24()
    rows = season_mod.load_adjustments()
    adjustments = season_mod.adjustments_at(rows, "2023/24", "2024-06-30")
    assert adjustments == {"everton": -8, "nottm_forest": -4}

    placed = table_mod.official_positions_for_realised(
        results, adjustments, boundaries=BOUNDARIES, rule_id=RULE_ID)

    assert [club for club, _, _ in placed] == [
        "man_city", "arsenal", "liverpool", "aston_villa", "tottenham", "chelsea",
        "newcastle", "man_united", "west_ham", "crystal_palace", "brighton",
        "bournemouth", "fulham", "wolves", "everton", "brentford", "nottm_forest",
        "luton", "burnley", "sheffield_united",
    ]
    assert [pos for _, pos, _ in placed] == list(range(1, 21))
    assert all(span == 1 for _, _, span in placed), "2023/24 held no shared position"


def test_2023_24_final_table_everton_15th_forest_17th_with_ledger_everton_higher_without():
    """The T1 hand-off (plan v2 D16): the deduction ledger is what makes the
    realised table official. Everton finish 15th and Forest 17th with it; drop
    it and Everton finish strictly higher while Forest stay 17th."""
    results = _archive_2023_24()
    rows = season_mod.load_adjustments()
    adjustments = season_mod.adjustments_at(rows, "2023/24", "2024-06-30")

    with_ledger = dict(
        (club, pos) for club, pos, _ in table_mod.official_positions_for_realised(
            results, adjustments, boundaries=BOUNDARIES, rule_id=RULE_ID))
    without = dict(
        (club, pos) for club, pos, _ in table_mod.official_positions_for_realised(
            results, {}, boundaries=BOUNDARIES, rule_id=RULE_ID))

    assert with_ledger["everton"] == 15
    assert with_ledger["nottm_forest"] == 17
    assert without["everton"] < with_ledger["everton"]
    assert without["nottm_forest"] == 17


def test_official_positions_reports_a_shared_block():
    """A synthetic dead heat: two clubs level on points, GD and GF at 11th/12th
    share the position, and the span says so."""
    clubs = [f"c{i:02d}" for i in range(C)]
    results = {(clubs[i], clubs[j]): (0, 0)
               for i in range(C) for j in range(C) if i != j}
    adjustments = {clubs[i]: int(SHARED_ADJ[i]) for i in range(C)}

    placed = table_mod.official_positions_for_realised(
        results, adjustments, boundaries=BOUNDARIES, rule_id=RULE_ID)
    by_club = {club: (pos, span) for club, pos, span in placed}
    assert by_club[clubs[10]] == (11, 2)
    assert by_club[clubs[11]] == (11, 2)


# ---------------------------------------------------------------------------
# the pure head-to-head ladder
# ---------------------------------------------------------------------------

def test_h2h_ladder_is_pure_and_orders_by_points_then_away_goals():
    among = {("a", "b"): (2, 0), ("b", "a"): (0, 0),
             ("a", "c"): (1, 1), ("c", "a"): (1, 1),
             ("b", "c"): (0, 0), ("c", "b"): (0, 0)}
    frozen = {k: v for k, v in among.items()}
    ladder = table_mod.h2h_ladder(["a", "b", "c"], among)
    assert among == frozen, "h2h_ladder must not mutate its input"

    # a: 3 + 1 + 1 + 1 = 6 ; b: 0 + 1 + 1 + 1 = 3 ; c: 1 + 1 + 1 + 1 = 4
    assert [members for members, _ in ladder] == [("a",), ("c",), ("b",)]
    assert all(code == table_mod.H2H_PTS for _, code in ladder)


def test_h2h_ladder_flags_playoff_and_multiway_by_size():
    two = {("a", "b"): (1, 1), ("b", "a"): (1, 1)}
    assert table_mod.h2h_ladder(["a", "b"], two) == [
        (("a", "b"), table_mod.UNRESOLVED_PLAYOFF)]

    three = {(x, y): (0, 0) for x in "abc" for y in "abc" if x != y}
    assert table_mod.h2h_ladder(["a", "b", "c"], three) == [
        (("a", "b", "c"), table_mod.UNRESOLVED_MULTIWAY)]

    # a 3-way block that splits into a resolved club and a two-club play-off
    mixed = {("a", "b"): (3, 0), ("b", "a"): (0, 0),
             ("a", "c"): (3, 0), ("c", "a"): (0, 0),
             ("b", "c"): (1, 1), ("c", "b"): (1, 1)}
    assert table_mod.h2h_ladder(["a", "b", "c"], mixed) == [
        (("a",), table_mod.H2H_PTS), (("b", "c"), table_mod.UNRESOLVED_PLAYOFF)]
