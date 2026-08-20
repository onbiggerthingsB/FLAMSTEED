"""The metrics and the retrospective harness (plan v2 T8).

What these tests are actually for
---------------------------------
T8 exists so that the numbers the retrospective will eventually report are
DEFINED BEFORE ANY OF THEM EXISTS. Plan v2 §5 is a preregistration: the metric
set, the cutoff schedule and the comparison structure are fixed there, and the
job of this file is to make each of them checkable against something outside
this repository rather than against my own restatement of it.

1. **TRPS is the published score, not a look-alike.** The primary metric is
   Ekstrøm, Van Eetvelde, Ley & Brefeld's tournament rank probability score
   (arXiv:1912.07364, eq. 2). The test reproduces the paper's own Examples 1
   and 2 — matrices and answers both taken from the paper — including its
   headline claim that a confident-and-wrong prediction scores WORSE than
   random guessing. If our normalisation, orientation or cumulation were off,
   at least one of those five published numbers would move.
2. **The flat null is analytic, so it cannot be quietly wrong.** For a full
   ranking of T teams the flat matrix scores exactly (T+1)/(6T) whatever the
   realised order is. 20 clubs -> 0.175, and the paper's 4-team case -> 0.2083,
   which is the value it prints for its own flat matrix X^4. The implementation
   is checked against the closed form and the closed form against the paper.
3. **The cutoff schedule is a rule, not a list of dates.** §5 defines MW0 as
   the season's first weekly walk-forward cutoff and MWk as the earliest weekly
   cutoff with >= 10k of the season's fixtures behind it. The test asserts the
   rule at the boundary — the chosen cutoff clears the bar and the weekly
   cutoff before it does not — so a schedule that happened to produce familiar
   dates for the wrong reason still fails.
4. **The ledger is resumable and keyed by what produced it.** A retrospective
   that silently re-ran, or that appended a second row for the same forecast,
   would corrupt the paired comparison. The test counts runner invocations
   across two calls, and its positive control changes the seed to prove the key
   is load-bearing rather than a constant.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_simretro.py -q
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import baseline, bridge as bridge_mod, leaguesim, particles, paths
from epl import season as season_mod, simmetrics, simretro, table as table_mod

SEED = 20260611
BOUNDARIES = leaguesim.DEFAULT_BOUNDARIES
RULE_ID = leaguesim.DEFAULT_RULE_ID

needs_archive = pytest.mark.skipif(
    not paths.MATCHES_PARQUET.exists(),
    reason="archive parquet absent (data/epl is gitignored)")


# ==========================================================================
# the paper's own examples (arXiv:1912.07364, Section 2, Examples 1 and 2)
# ==========================================================================
#
# The paper writes a prediction as ranks x teams; `simmetrics.trps` takes the
# product's orientation (clubs x positions), so every matrix below is
# transposed at the call. Both matrices and both answers are the paper's.

PAPER_X1 = np.array([[1.0, 0.0, 0.0, 0.0],
                     [0.0, 1.0, 0.0, 0.0],
                     [0.0, 0.0, 1.0, 1.0]])

PAPER_X2 = np.array([[0.7, 0.1, 0.1, 0.1],
                     [0.1, 0.5, 0.2, 0.2],
                     [0.2, 0.4, 0.7, 0.7]])

#: the paper's "completely flat prediction" for Example 1's rank sizes 1, 1, 2
PAPER_FLAT_1 = np.array([[0.25, 0.25, 0.25, 0.25],
                         [0.25, 0.25, 0.25, 0.25],
                         [0.50, 0.50, 0.50, 0.50]])

PAPER_X3 = np.array([[0.75, 0.25, 0.00, 0.00],
                     [0.25, 0.75, 0.00, 0.00],
                     [0.00, 0.00, 0.75, 0.25],
                     [0.00, 0.00, 0.25, 0.75]])

PAPER_X4 = np.full((4, 4), 0.25)


def _published(got: float, printed: float, exact: float) -> None:
    """Two checks, not one.

    `printed` is the value the paper prints, to the digits it prints — matched
    to within one rounding step, which is all a rounded figure can license.
    `exact` is the value worked through by hand from eq. 2 for the same
    matrices. Either alone could be satisfied by a subtly wrong implementation;
    together they pin the normalisation, the orientation and the cumulation.
    """
    assert got == pytest.approx(printed, abs=1e-3), f"paper prints {printed}"
    assert got == pytest.approx(exact, rel=1e-12), "hand computation from eq. 2"


def test_trps_matches_paper_example_1():
    """Five published numbers, including "confident and wrong is worse than flat"."""
    # Outcome A: team 1 first, team 2 second, teams 3 and 4 in the last rank.
    a = [1, 2, 3, 3]
    assert simmetrics.trps(PAPER_X1.T, a) == pytest.approx(0.0, abs=1e-12)
    _published(simmetrics.trps(PAPER_X2.T, a), 0.063, 1 / 16)       # 0.0625
    _published(simmetrics.trps(PAPER_FLAT_1.T, a), 0.219, 7 / 32)   # 0.21875

    # Outcome B: the two leaders swapped.
    b = [2, 1, 3, 3]
    confident_and_wrong = simmetrics.trps(PAPER_X1.T, b)
    hedged = simmetrics.trps(PAPER_X2.T, b)
    flat = simmetrics.trps(PAPER_FLAT_1.T, b)
    _published(confident_and_wrong, 0.25, 1 / 4)
    _published(hedged, 0.213, 17 / 80)                              # 0.2125

    # The paper's point, asserted rather than assumed: X2 beats X1, and X1 is
    # so confidently wrong that it is beaten by random guessing.
    assert hedged < confident_and_wrong
    assert flat < confident_and_wrong

    # Example 2 — a second, independent set of published values, and the case
    # the paper uses to show TRPS is non-local where log loss is not.
    _published(simmetrics.trps(PAPER_X3.T, [1, 2, 3, 4]), 0.0208, 1 / 48)
    _published(simmetrics.trps(PAPER_X4.T, [1, 2, 3, 4]), 0.2083, 5 / 24)
    _published(simmetrics.trps(PAPER_X3.T, [2, 1, 4, 3]), 0.188, 3 / 16)
    _published(simmetrics.trps(PAPER_X4.T, [2, 1, 4, 3]), 0.2083, 5 / 24)


def test_trps_zero_for_perfect_and_flat_analytic_for_20_teams():
    """Perfect scores 0; flat scores the closed form; a wrong-but-sharp one is worse."""
    positions = list(range(1, 21))
    perfect = np.eye(20)
    assert simmetrics.trps(perfect, positions) == pytest.approx(0.0, abs=1e-12)

    flat = bridge_mod.flat_matrix(20)
    closed_form = 21.0 / 120.0                       # (T + 1) / (6T) at T = 20
    assert simmetrics.trps(flat, positions) == pytest.approx(closed_form, abs=1e-12)
    assert simmetrics.flat_trps(positions) == pytest.approx(closed_form, abs=1e-12)

    # the same closed form reproduces the paper's flat 4-team value
    assert simmetrics.flat_trps([1, 2, 3, 4]) == pytest.approx(0.2083, abs=5e-4)

    # order-invariance of the flat null: it cannot prefer one realised table
    rng = np.random.default_rng(0)
    shuffled = list(rng.permutation(np.arange(1, 21)))
    assert simmetrics.flat_trps(shuffled) == pytest.approx(closed_form, abs=1e-12)

    # POSITIVE CONTROL: a perfect matrix scored against the reversed table is
    # the worst score this metric can produce on 20 clubs — sum_t |2t - 21| =
    # 200 mismatched boundaries out of 380 — and must be far worse than flat,
    # or "0 for perfect" is measuring nothing.
    reversed_positions = list(range(20, 0, -1))
    worst = simmetrics.trps(perfect, reversed_positions)
    assert worst == pytest.approx(200.0 / 380.0, rel=1e-12)
    assert worst > 2 * closed_form


def test_wtrps_weights_sum_to_19_and_reduce_to_trps_when_uniform():
    """The weighted form is the paper's, and its consequence weights are ours."""
    positions = [3, 1, 2] + list(range(4, 21))
    rng = np.random.default_rng(11)
    matrix = rng.random((20, 20)) + 0.05
    matrix = _doubly_stochastic(matrix)

    uniform = np.ones(19)
    assert simmetrics.wtrps(matrix, positions, uniform) == pytest.approx(
        simmetrics.trps(matrix, positions), abs=1e-12)

    weights = simmetrics.consequence_weights()
    assert weights.shape == (19,)
    assert weights.sum() == pytest.approx(19.0, abs=1e-12)
    assert np.count_nonzero(weights) == 5
    for rank in simmetrics.CONSEQUENCE_RANKS:
        assert weights[rank - 1] == pytest.approx(19.0 / 5.0, abs=1e-12)

    # POSITIVE CONTROL: concentrating the weight must actually change the score
    assert simmetrics.wtrps(matrix, positions, weights) != pytest.approx(
        simmetrics.trps(matrix, positions), abs=1e-6)

    # the paper's scale condition is enforced, not assumed
    with pytest.raises(simmetrics.MetricError):
        simmetrics.wtrps(matrix, positions, np.ones(19) * 2.0)
    with pytest.raises(simmetrics.MetricError):
        simmetrics.wtrps(matrix, positions, np.ones(18))


def test_consequence_briers_zero_for_perfect_and_flag_the_markets():
    positions = list(range(1, 21))
    perfect = np.eye(20)
    got = simmetrics.consequence_briers(perfect, positions)
    assert set(got) == set(leaguesim.MARKETS)
    assert all(v == pytest.approx(0.0, abs=1e-12) for v in got.values())

    flat = bridge_mod.flat_matrix(20)
    flat_scores = simmetrics.consequence_briers(flat, positions)
    # champion is the 20-way multi-category Brier: sum_c (p_c - o_c)^2
    assert flat_scores["champion"] == pytest.approx(
        (1 - 0.05) ** 2 + 19 * 0.05 ** 2, abs=1e-12)
    # relegation is a per-club binary Brier averaged over the 20 clubs; the flat
    # matrix gives every club 3/20 and three of them relegate
    p = 3.0 / 20.0
    assert flat_scores["relegated"] == pytest.approx(
        (3 * (1 - p) ** 2 + 17 * p ** 2) / 20.0, abs=1e-12)

    # POSITIVE CONTROL: every market must be strictly worse under flat
    assert all(flat_scores[m] > got[m] for m in leaguesim.MARKETS)


def test_logloss_floor_and_zero_hit_count():
    n_sims = 20_000
    floor = 0.5 / n_sims

    got = simmetrics.champion_logloss_floored([0.25, 0.0, floor / 2, 1.0], n_sims)
    assert got["floor"] == pytest.approx(floor)
    assert got["n"] == 4
    assert got["zero_hits"] == 1, "only the literal 0.0 is a zero hit"
    assert got["n_floored"] == 2, "the zero and the sub-floor value both floor"

    expected = np.mean([-math.log(0.25), -math.log(floor), -math.log(floor),
                        -math.log(1.0)])
    assert got["value"] == pytest.approx(expected, rel=1e-12)
    assert got["per_entry"][3] == pytest.approx(0.0, abs=1e-12)

    # POSITIVE CONTROL: without the floor the zero hit is infinite, so the floor
    # is doing work rather than decorating a finite number.
    assert math.isfinite(got["value"])
    assert got["value"] > -math.log(0.25)

    # a scalar is accepted and reported the same way
    single = simmetrics.champion_logloss_floored(0.0, n_sims)
    assert single["zero_hits"] == 1 and single["n"] == 1
    assert single["value"] == pytest.approx(-math.log(floor))


def test_crps_and_coverage_on_synthetic_rows():
    n_sims, n_clubs = 4_000, 3
    rng = np.random.default_rng(5)
    # club 0: a point mass exactly on the truth; club 1: centred and wide;
    # club 2: badly located.
    rows = np.stack([
        np.full(n_sims, 50),
        rng.integers(30, 71, n_sims),
        rng.integers(0, 11, n_sims),
    ], axis=1).astype(np.int16)
    actual = np.array([50, 50, 50])

    crps = simmetrics.points_crps(rows, actual)
    assert crps.shape == (n_clubs,)
    assert crps[0] == pytest.approx(0.0, abs=1e-12), "a point mass on truth is free"
    assert 0 < crps[1] < crps[2], "the badly located club must score worst"

    # closed form on a hand sample: CRPS = mean|x - y| - (1/2) mean|x - x'|
    small = np.array([[1], [2], [4], [8]], dtype=np.int16)
    y = np.array([3])
    pairs = np.abs(small[:, 0][:, None] - small[:, 0][None, :])
    want = np.abs(small[:, 0] - 3).mean() - 0.5 * pairs.mean()
    assert simmetrics.points_crps(small, y)[0] == pytest.approx(want, rel=1e-12)

    assert simmetrics.points_mae(rows, actual) == pytest.approx(
        float(np.abs(rows.mean(axis=0) - actual).mean()), rel=1e-12)

    coverage = simmetrics.interval_coverage(rows, actual)
    assert set(coverage) == {"coverage50", "coverage90"}
    assert coverage["coverage50"] == pytest.approx(2.0 / 3.0, abs=1e-9)
    assert coverage["coverage90"] == pytest.approx(2.0 / 3.0, abs=1e-9)

    # POSITIVE CONTROL: move every club's truth outside its own support and the
    # coverage must collapse, or the interval test is not testing an interval.
    away = simmetrics.interval_coverage(rows, np.array([-5, -5, -5]))
    assert away["coverage50"] == 0.0 and away["coverage90"] == 0.0

    # the histogram round-trip the ledger relies on is exact
    hist = simmetrics.points_histogram(rows)
    back = simmetrics.points_from_histogram(hist)
    np.testing.assert_array_equal(np.sort(back, axis=0), np.sort(rows, axis=0))
    np.testing.assert_allclose(simmetrics.points_crps(back, actual), crps, atol=1e-12)


def test_boundary_decider_rates_on_a_hand_built_season():
    """Two seasons built so each boundary is settled by a named rung."""
    clubs = 20
    # season 0: everyone separated on points. season 1: 17th and 18th level on
    # points and separated by goal difference.
    pts = np.tile(np.arange(clubs, 0, -1, dtype=np.int16) * 3, (2, 1))
    pts[1, 17] = pts[1, 16]
    gd = np.tile(np.arange(clubs, 0, -1, dtype=np.int16), (2, 1))
    gf = gd.copy()
    totals = table_mod.Totals(
        pts=pts, gd=gd, gf=gf, ga=np.zeros_like(gf),
        w=np.zeros_like(gf), d=np.zeros_like(gf), l=np.zeros_like(gf),
        adjustments=np.zeros(clubs, np.int16),
        fixtures_per_club=np.zeros(clubs, np.int16))
    scorelines = np.zeros((2, 0, 2), np.int8)
    empty = np.zeros(0, np.int64)
    ranking = table_mod.rank(totals, scorelines, empty, empty, BOUNDARIES, RULE_ID)

    rates = simmetrics.boundary_decider_rates(ranking, pts, gd, gf)
    assert "17|18" in rates and "1|2" in rates
    assert rates["1|2"]["UNIQUE"] == pytest.approx(1.0)
    assert rates["17|18"]["UNIQUE"] == pytest.approx(0.5)
    assert rates["17|18"]["GD"] == pytest.approx(0.5)
    for boundary, shares in rates.items():
        assert sum(shares.values()) == pytest.approx(1.0), boundary


@needs_archive
def test_boundary_decider_rates_agree_with_the_engine(smoke_runs):
    """The metric layer's rates are the engine's, computed from the rows."""
    run = smoke_runs["dc_native"]
    rows = run.retained_rows
    ranking = table_mod.Ranking(
        block_start=rows.block_start, block_span=rows.block_span,
        resolution_code=rows.resolution_code, order=rows.order,
        boundaries=run.plan.boundaries, rule_id=run.plan.rule_id)
    mine = simmetrics.boundary_decider_rates(ranking, rows.points, rows.gd, rows.gf)
    theirs = run.tie_diagnostics["boundary_deciders"]
    assert set(mine) == set(theirs)
    for boundary in mine:
        for rung, share in mine[boundary].items():
            assert share == pytest.approx(theirs[boundary][rung], abs=1e-12)


# ==========================================================================
# the schedule and the realised table
# ==========================================================================

@needs_archive
def test_cutoff_schedule_rule_mw0_is_opener_mwk_first_cutoff_with_10k_played():
    matches = baseline.load_matches()
    for season in ("2024/25", "2025/26"):
        schedule = simretro.cutoff_schedule(matches, season)
        assert list(schedule) == list(simretro.CUTOFF_LABELS)

        weekly = simretro.weekly_cutoffs(matches, season)
        dates = pd.to_datetime(
            matches.loc[(matches["season"] == season) & matches["played"], "date"]
        ).dt.normalize()

        assert schedule["MW0"] == weekly[0], "MW0 is the season's first cutoff"
        assert int((dates < schedule["MW0"]).sum()) == 0, "the opener sees nothing"

        for label in ("MW3", "MW6", "MW10", "MW19", "MW28"):
            k = int(label[2:])
            chosen = schedule[label]
            assert int((dates < chosen).sum()) >= 10 * k
            earlier = [c for c in weekly if c < chosen]
            assert earlier, f"{label} cannot be the first cutoff"
            # THE RULE, at its boundary: the cutoff before the chosen one must
            # NOT clear the bar, or "earliest" is unverified.
            assert int((dates < earlier[-1]).sum()) < 10 * k

    # the schedule this repo already hard-codes elsewhere, re-derived
    assert str(simretro.cutoff_schedule(matches, "2024/25")["MW0"].date()) == "2024-08-16"
    assert str(simretro.cutoff_schedule(matches, "2024/25")["MW10"].date()) == "2024-11-23"
    assert str(simretro.cutoff_schedule(matches, "2025/26")["MW0"].date()) == "2025-08-15"


@needs_archive
def test_realised_positions_use_final_adjustments():
    matches = baseline.load_matches()
    # The verified gate is ON (the default): the four 2023/24 rows carry their
    # attestation as of 2026-08-20, so this no longer opts out of D16.
    realised = simretro.realised_positions(matches, "2023/24")

    assert realised.adjustments == {"everton": -8, "nottm_forest": -4}, (
        "the FINAL state of the ledger, not a point-in-time snapshot")
    assert realised.position["everton"] == 15
    assert realised.position["nottm_forest"] == 17
    assert sorted(realised.position.values()) == list(range(1, 21))
    assert realised.n_shared == 0

    # POSITIVE CONTROL 1: the point-in-time state mid-season is a different
    # number, so "final" is a choice this function makes and not a tautology.
    rows = season_mod.load_adjustments()
    mid = season_mod.adjustments_at(rows, "2023/24", "2023-12-01")
    assert mid == {"everton": -10}
    assert mid != realised.adjustments

    # POSITIVE CONTROL 2: drop the ledger and Everton finish strictly higher.
    without = simretro.realised_positions(matches, "2023/24", adjustments={})
    assert without.position["everton"] < realised.position["everton"]

    # a season with no adjustment rows scores under the gate without complaint
    clean = simretro.realised_positions(matches, "2024/25")
    assert clean.adjustments == {}
    assert sorted(clean.position.values()) == list(range(1, 21))


@needs_archive
def test_2023_24_scores_under_the_verified_gate_after_the_attestation(monkeypatch):
    """R1's hole 1, closed — and the guard that made it a hole still bites.

    R1 refused all six cutoffs of 2023/24 with `UnverifiedAdjustment` because
    the four points-adjustment rows were seeded `verified: false`. They were
    checked against premierleague.com and the flip was authorised on
    2026-08-20, so the season scores under the DEFAULT gate. The refusal path
    is driven below on a synthetic unverified row, because pointing it at the
    real rows now would be a canary that cannot fail.
    """
    matches = baseline.load_matches()
    realised = simretro.realised_positions(matches, "2023/24")

    assert realised.adjustments == {"everton": -8, "nottm_forest": -4}
    assert realised.position["everton"] == 15
    assert realised.position["nottm_forest"] == 17
    assert sorted(realised.position.values()) == list(range(1, 21))
    assert realised.n_shared == 0

    # POSITIVE CONTROL: the gate is live. A synthetic unverified row in the
    # ledger refuses the same call, on the same season, with nothing else
    # changed — so what scored above is the attestation and not a dead guard.
    synthetic = [{"id": "adj-2324-synthetic-01", "season": "2023/24",
                  "club_key": "everton", "delta": -10, "known_at": "2023-11-17",
                  "source": "test", "supersedes": None, "verified": False,
                  "note": "synthetic: checked against nothing"}]
    monkeypatch.setattr(season_mod, "load_adjustments", lambda *a, **k: synthetic)
    with pytest.raises(season_mod.UnverifiedAdjustment) as caught:
        simretro.realised_positions(matches, "2023/24")
    assert "adj-2324-synthetic-01" in str(caught.value)

    # and the same synthetic row, verified, scores — Everton one place lower
    # than the real -8 leaves them, because -10 is a bigger deduction.
    synthetic[0]["verified"] = True
    worse = simretro.realised_positions(matches, "2023/24")
    assert worse.adjustments == {"everton": -10}
    assert worse.position["everton"] > realised.position["everton"]


# ==========================================================================
# the harness
# ==========================================================================

def _doubly_stochastic(matrix, iterations: int = 200) -> np.ndarray:
    """Sinkhorn, so a random matrix becomes an admissible forecast."""
    out = np.asarray(matrix, float).copy()
    for _ in range(iterations):
        out /= out.sum(axis=1, keepdims=True)
        out /= out.sum(axis=0, keepdims=True)
    return out / out.sum(axis=1, keepdims=True)


def _fake_arm(rng, n_clubs=20, n_sims=64, sharp=1.0):
    """An `ArmResult` with an admissible matrix and plausible points rows."""
    matrix = _doubly_stochastic(rng.random((n_clubs, n_clubs)) ** sharp + 1e-3)
    points = rng.integers(20, 95, (n_sims, n_clubs)).astype(np.int16)
    return simretro.ArmResult(
        matrix=matrix, matrix_se=np.full_like(matrix, 1e-3),
        consequences=None, points=points, tie_diagnostics={}, mc={"cluster": 1e-3},
        n_sims=n_sims, n_particles=8, digest=None, envelope={"seed": SEED},
        is_null=False)


class _CountingRunner:
    """A runner that records every (season, cutoff, seed) it was asked for.

    `undefined_at` names a (null, cutoff) the runner declines to produce, the
    way `ppg_pointmass` is undefined at the opener. Resuming must not pay for a
    fit again just to rediscover that.

    Under harness v3 the runner SAYS SO, in a typed field (A4 (i)): a refusal
    is a fact the runner knows and the scorer does not, and the caller no
    longer manufactures a reason on its behalf.
    """

    def __init__(self, clubs, undefined_at: tuple = ()):
        self.clubs = tuple(clubs)
        self.calls: list[tuple] = []
        self.undefined_at = set(undefined_at)

    def __call__(self, *, season, cutoff_label, cutoff, arms, nulls, n_sims, seed):
        self.calls.append((season, cutoff_label, seed))
        rng = np.random.default_rng(abs(hash((season, cutoff_label, seed))) % 2**32)
        out = {arm: _fake_arm(rng, len(self.clubs), n_sims) for arm in arms}
        refusals = {}
        for null in nulls:
            if (null, cutoff_label) in self.undefined_at:
                refusals[null] = ("arm_not_defined",
                                  f"{null} is not defined at {cutoff_label}")
                continue
            out[null] = simretro.ArmResult.from_null(
                bridge_mod.flat_matrix(len(self.clubs)), n_sims=n_sims)
        return simretro.CutoffResult(clubs=self.clubs, arms=out,
                                     provenance={"synthetic": True,
                                                 "wall_seconds": rng.random()},
                                     refusals=refusals)


def test_retro_ledger_resumable_and_keyed_by_envelope_hash(tmp_path):
    clubs = [f"club_{i:02d}" for i in range(20)]
    realised = simretro.Realised(
        season="2099/00",
        position={c: i + 1 for i, c in enumerate(clubs)},
        span={c: 1 for c in clubs},
        points={c: 80 - 3 * i for i, c in enumerate(clubs)},
        adjustments={}, n_shared=0)

    # `ppg` stands in for the real ppg_pointmass: undefined at the opener.
    runner = _CountingRunner(clubs, undefined_at=(("ppg", "MW0"),))
    ledger = tmp_path / "retro.jsonl"
    schedule = {"MW0": pd.Timestamp("2099-08-10"), "MW10": pd.Timestamp("2099-11-20")}
    kwargs = dict(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                  arms=("dc_native", "dc_wdl_bridge"), nulls=("flat", "ppg"),
                  n_sims=64, seed=SEED, ledger_path=ledger, runner=runner,
                  schedules={"2099/00": schedule},
                  realised={"2099/00": realised}, verbose=False,
                  allow_unrecorded_harness=True)

    first = simretro.run_retro(**kwargs)
    assert len(runner.calls) == 2, "one runner call per (season, cutoff)"
    assert len(first) == 8, "2 arms + 2 nulls at both cutoffs, ppg@MW0 refused"
    forecasts = [r for r in first if not r.get("not_applicable")]
    assert len(forecasts) == 7, "2 arms + flat at both cutoffs, ppg only at MW10"
    assert not any(r["arm"] == "ppg" and r["cutoff_label"] == "MW0"
                   for r in forecasts), "ppg is undefined at the opener"
    refused = [r for r in first if r.get("refusal_kind")]
    assert all(r["refusal_kind"] == "arm_not_defined" for r in refused)
    assert [(r["arm"], r["cutoff_label"]) for r in refused] == [("ppg", "MW0")], (
        "and the refusal comes BACK, documented: it is the only evidence the "
        "completeness accounting has that the cell is missing on purpose")
    keys = [row["run_key"] for row in first]
    assert len(set(keys)) == len(keys), "keys must identify a row uniquely"
    assert all(row["envelope_hash"] for row in first)
    assert len({row["envelope_hash"] for row in first}) == len(keys), (
        "the provenance hash must distinguish the rows it stands for")
    assert all(row["cutoff_label"] in ("MW0", "MW10") for row in first)

    # resume: nothing new is computed and nothing new is written — INCLUDING
    # the cutoff where a null was undefined, which must not cost a second fit.
    before = ledger.read_text()
    second = simretro.run_retro(**kwargs)
    assert len(runner.calls) == 2, "a resumed run must not refit anything"
    assert ledger.read_text() == before, "the ledger is append-only and complete"
    assert [r["run_key"] for r in second] == keys

    # the hash is over content, not over the clock: the synthetic runner puts a
    # different `wall_seconds` in its provenance every call, and re-running the
    # same request under a fresh ledger must still produce the same hashes.
    fresh = simretro.run_retro(**{**kwargs, "ledger_path": tmp_path / "again.jsonl"})
    assert len(runner.calls) == 4
    assert [r["envelope_hash"] for r in fresh] == [r["envelope_hash"] for r in first]

    # POSITIVE CONTROL: the key is load-bearing — change the seed and the same
    # (season, cutoff) is computed again and appended rather than skipped.
    simretro.run_retro(**{**kwargs, "seed": SEED + 1})
    assert len(runner.calls) == 6
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert len({r["run_key"] for r in rows}) == len(rows)
    scoreable = [r for r in rows if not r.get("refusal_kind")]
    assert len(scoreable) == 14, "seven rows per seed"
    assert len(rows) - len(scoreable) == 2, "one typed refusal marker per seed"

    scores = simretro.score_retro(rows, n_boot=200)
    assert {r["arm"] for r in scores["rows"]} == {"dc_native", "dc_wdl_bridge",
                                                  "flat", "ppg"}
    for row in scores["rows"]:
        assert 0.0 <= row["trps"] <= 1.0
        assert row["flat_trps"] == pytest.approx(21.0 / 120.0, abs=1e-12)
    assert set(scores["by_cutoff"]) == {"MW0", "MW10"}
    assert "dc_native-dc_wdl_bridge" in scores["comparisons"]["MW0"]

    markdown = simretro.report(scores)
    assert "TRPS" in markdown and "MW0" in markdown and "MW10" in markdown
    assert "wTRPS" in markdown


def test_report_never_averages_trps_across_cutoffs(tmp_path):
    """§5's rule, enforced where it is easy to break: the report and the scores."""
    clubs = [f"club_{i:02d}" for i in range(20)]
    realised = simretro.Realised(
        season="2099/00", position={c: i + 1 for i, c in enumerate(clubs)},
        span={c: 1 for c in clubs}, points={c: 80 - 3 * i for i, c in enumerate(clubs)},
        adjustments={}, n_shared=0)
    runner = _CountingRunner(clubs)
    rows = simretro.run_retro(
        seasons=("2099/00",), cutoffs=("MW0", "MW10"), arms=("dc_native",),
        nulls=(), n_sims=64, seed=SEED, ledger_path=tmp_path / "r.jsonl",
        runner=runner, schedules={"2099/00": {"MW0": pd.Timestamp("2099-08-10"),
                                              "MW10": pd.Timestamp("2099-11-20")}},
        realised={"2099/00": realised}, verbose=False,
        allow_unrecorded_harness=True)
    scores = simretro.score_retro(rows, n_boot=100)

    # every aggregate is inside one cutoff label
    for label, per_arm in scores["by_cutoff"].items():
        for arm, cell in per_arm.items():
            assert cell["cutoff_label"] == label
    assert "trps" not in scores, "no cross-cutoff headline may exist"
    assert scores["never_averaged_across_cutoffs"] is True

    markdown = simretro.report(scores)
    for label in ("MW0", "MW10"):
        assert markdown.count(f"| {label} ") >= 1


# ==========================================================================
# the smoke run — the real archive, real fits, real arms
# ==========================================================================

@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    if not paths.MATCHES_PARQUET.exists():
        pytest.skip("archive parquet absent")
    directory = tmp_path_factory.mktemp("smoke_retro")
    return simretro.run_retro(
        seasons=simretro.SMOKE_SEASONS, cutoffs=simretro.SMOKE_CUTOFFS,
        n_sims=2_000, seed=SEED, ledger_path=directory / "smoke.jsonl",
        smoke=True, verbose=False, allow_unrecorded_harness=True)


@pytest.fixture(scope="module")
def smoke_runs(tmp_path_factory):
    """One real dc_native run, kept so the engine cross-check is not a second fit."""
    if not paths.MATCHES_PARQUET.exists():
        pytest.skip("archive parquet absent")
    runner = simretro.ArchiveRunner(verbose=False)
    matches = baseline.load_matches()
    cutoff = simretro.cutoff_schedule(matches, "2025/26")["MW10"]
    # 2,000 over the retrospective's 1,000 particles: two sims per particle.
    # 500 was inadmissible — fewer sims than draws, so half the book was never
    # used and every "cluster" held one observation — and `SimPlan.from_state`
    # now refuses it (D15 is written for equal clusters).
    result = runner(season="2025/26", cutoff_label="MW10", cutoff=cutoff,
                    arms=("dc_native",), nulls=(), n_sims=2_000, seed=SEED)
    return {"dc_native": result.arms["dc_native"].run}


@pytest.mark.slow
@needs_archive
def test_smoke_retro_runs_one_season_two_cutoffs_three_arms(smoke, tmp_path):
    seen = {(row["season"], row["cutoff_label"], row["arm"])
            for row in smoke if not row.get("refusal_kind")}
    refused = {(row["season"], row["cutoff_label"], row["arm"])
               for row in smoke if row.get("refusal_kind") == "arm_not_defined"}
    assert {s for s, _, _ in seen} == {"2025/26"}
    assert {c for _, c, _ in seen} == {"MW0", "MW10"}
    for arm in simretro.ARMS:
        assert ("2025/26", "MW0", arm) in seen
        assert ("2025/26", "MW10", arm) in seen
    assert ("2025/26", "MW0", "flat") in seen
    assert ("2025/26", "MW10", "ppg_pointmass") in seen, "PPG is defined by MW10"
    assert ("2025/26", "MW0", "ppg_pointmass") not in seen, "PPG is NA at the opener"
    assert refused == {("2025/26", "MW0", "ppg_pointmass")}, (
        "and the refusal is RETURNED, documented, not filtered out of the run")

    # the grid is stated, from the same normalisation the run used — which is
    # what `_cli` now does and what makes the accounting below mean anything
    scores = simretro.score_retro(
        smoke, n_boot=1_000,
        expected_triples=simretro.requested_cells(smoke=True))
    by = {(r["season"], r["cutoff_label"], r["arm"]): r for r in scores["rows"]}
    for label in ("MW0", "MW10"):
        native = by[("2025/26", label, "dc_native")]
        flat = by[("2025/26", label, "flat")]
        assert native["trps"] < flat["trps"], (
            f"dc_native must beat the flat null at {label} (plan v2 §5 STOP)")
        assert native["wtrps"] > 0 and native["mc"]["cluster"] > 0
        assert native["points"]["crps"] > 0
        assert set(native["briers"]) == set(leaguesim.MARKETS)
    assert scores["sanity"]["n_expected"] == 10, "two cutoffs x five arms"
    assert scores["sanity"]["n_scored"] == 9
    assert scores["sanity"]["n_typed_refusals"] == 1, "ppg_pointmass at MW0"
    assert scores["sanity"]["n_cells_compared"] == 2
    assert scores["sanity"]["complete"] is True, "9 scored + 1 refused == 10"
    assert scores["sanity"]["dc_native_beats_flat_everywhere"] is True
    assert scores["sanity"]["STOP_AND_INSPECT"] is False

    # the SAME rows, scored the way the harness used to be called, certify
    # nothing at all — the smoke grid is two cutoffs of the preregistered 42
    blind = simretro.score_retro(smoke, n_boot=200)
    assert blind["sanity"]["n_expected"] == 210
    assert blind["sanity"]["complete"] is False
    assert blind["sanity"]["dc_native_beats_flat_everywhere"] is False
    assert blind["sanity"]["STOP_AND_INSPECT"] is True

    markdown = simretro.report(scores)
    out = tmp_path / "smoke.md"
    out.write_text(markdown)
    assert "TRPS" in markdown and "wTRPS" in markdown and "MC" in markdown
    assert "dc_native" in markdown and "flat" in markdown
    assert out.stat().st_size > 200


# ==========================================================================
# harness v2 — amendment A2, recorded before this code existed
# ==========================================================================

def _v2_kwargs(tmp_path, clubs, realised, runner, ledger=None):
    return dict(
        seasons=("2099/00",), cutoffs=("MW0", "MW10"),
        arms=("dc_native",), nulls=("flat",), n_sims=64, seed=SEED,
        ledger_path=ledger or (tmp_path / "retro.jsonl"), runner=runner,
        schedules={"2099/00": {"MW0": pd.Timestamp("2099-08-10"),
                               "MW10": pd.Timestamp("2099-11-20")}},
        realised={"2099/00": realised}, verbose=False)


def _clubs_and_realised():
    clubs = [f"club_{i:02d}" for i in range(20)]
    return clubs, simretro.Realised(
        season="2099/00", position={c: i + 1 for i, c in enumerate(clubs)},
        span={c: 1 for c in clubs},
        points={c: 80 - 3 * i for i, c in enumerate(clubs)},
        adjustments={}, n_shared=0)


def test_resume_key_carries_producer_identity_and_a_foreign_ledger_refuses(
        tmp_path, monkeypatch):
    """A2 (a): a ledger written by one producer cannot be resumed by another.

    The v1 key was the question and nothing else — season, cutoff, arm, N,
    seed — so a resume kept another producer's rows, appended its own, marked
    neither, and reported nothing. The `envelope_hash` that would have caught it
    is on every row and was never consulted at resume time.
    """
    clubs, realised = _clubs_and_realised()
    ledger = tmp_path / "retro.jsonl"
    runner = _CountingRunner(clubs)
    first = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner,
                                            ledger))
    me = simretro.producer_identity()
    assert all(row["producer"] == me for row in first)
    assert all(row["run_key"].endswith(f"|p{me[:12]}") for row in first)

    # resuming with the SAME producer is free: no runner call at all
    calls = len(runner.calls)
    again = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner,
                                            ledger))
    assert len(runner.calls) == calls, "the same producer resumes for nothing"
    assert [r["run_key"] for r in again] == [r["run_key"] for r in first]

    # a DIFFERENT producer refuses the ledger outright, before any fit
    monkeypatch.setattr(simretro.producer_identity, "__wrapped__", None,
                        raising=False)
    other = _CountingRunner(clubs)
    with monkeypatch.context() as patch:
        patch.setattr(simretro, "producer_identity", lambda *a, **k: "f" * 64)
        with pytest.raises(simretro.RetroError, match="different producer"):
            simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, other,
                                            ledger))
        assert other.calls == [], "it refused BEFORE paying for a fit"

        # ... and the override is explicit, and marks every row it writes
        mixed = simretro.run_retro(
            **_v3_kwargs(tmp_path, clubs, realised, other, ledger),
            allow_foreign_producer=True)
        assert other.calls, "the override really did run"
        assert all(r["producer"] == "f" * 64 for r in mixed)
        assert all(r.get("allow_foreign_producer") for r in mixed)

    # POSITIVE CONTROL: the producer identity moves when the harness moves.
    with monkeypatch.context() as patch:
        patch.setattr(simretro, "SCHEMA_VERSION", "epl-simretro-99")
        simretro.producer_identity.cache_clear()
        assert simretro.producer_identity() != me
    simretro.producer_identity.cache_clear()
    assert simretro.producer_identity() == me


def test_beats_flat_everywhere_needs_every_expected_cell(tmp_path):
    """A2 (b): completeness, not just non-emptiness.

    `bool(checked and not violations)` was True on ANY non-empty subset,
    because a missing cell is not a violation — it is simply not counted. One
    surviving cell of a preregistered twenty-eight reported True.
    """
    clubs, realised = _clubs_and_realised()
    runner = _CountingRunner(clubs)
    rows = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner))
    # The fake runner's matrices are random and lose to the flat null, which
    # would make the flag False for the wrong reason and leave this test unable
    # to see the completeness identity at all. dc_native's matrix is replaced
    # with a doubly stochastic one concentrated on the realised order, so the
    # ONLY thing that can move the flag below is the accounting.
    sharp = 0.6 * np.eye(len(clubs)) + 0.4 / len(clubs)
    rows = [dict(r, matrix=sharp.tolist()) if r["arm"] == "dc_native" else r
            for r in rows]

    whole_grid = simretro.requested_cells(seasons=("2099/00",),
                                          cutoffs=("MW0", "MW10"),
                                          arms=("dc_native",), nulls=("flat",))
    full = simretro.score_retro(rows, n_boot=50, expected_triples=whole_grid)
    sanity = full["sanity"]
    assert sanity["violations"] == [], "the fixture must beat the flat null"
    assert sanity["n_expected"] == 4 and sanity["n_scored"] == 4
    assert sanity["n_cells_compared"] == 2
    assert sanity["complete"] is True
    assert sanity["dc_native_beats_flat_everywhere"] is True

    # drop one cutoff's flat row: one cell survives, and the flag must not
    thin = [r for r in rows
            if not (r["arm"] == "flat" and r["cutoff_label"] == "MW10")]
    partial = simretro.score_retro(thin, n_boot=50, expected_triples=whole_grid)
    assert partial["sanity"]["n_scored"] == 3
    assert partial["sanity"]["n_cells_compared"] == 1
    assert partial["sanity"]["n_expected"] == 4
    assert partial["sanity"]["complete"] is False
    assert partial["sanity"]["dc_native_beats_flat_everywhere"] is False
    assert partial["sanity"]["STOP_AND_INSPECT"] is True
    assert partial["sanity"]["missing"][0]["documented"] is False

    # a TYPED refusal is different from a hole: it closes the accounting
    documented = {"season": "2099/00", "cutoff_label": "MW10", "arm": "flat",
                  "refusal_kind": "arm_not_defined",
                  "reason": "flat is undefined here",
                  "not_applicable": "flat is undefined here"}
    with_reason = simretro.score_retro(thin + [documented], n_boot=50,
                                       expected_triples=whole_grid)
    assert with_reason["sanity"]["n_typed_refusals"] == 1
    assert with_reason["sanity"]["complete"] is True
    assert with_reason["sanity"]["missing"][0]["reason"] == "flat is undefined here"


def test_ledger_scoring_checks_both_margins_and_the_shape(tmp_path):
    """A2 (d): the scoring path reads matrices back OUT of the ledger.

    `_as_matrix` checks row sums — "every club must finish somewhere" — and
    stops. A stored matrix whose COLUMNS have drifted is inadmissible and scored
    silently, and scoring is the path that turns a stored row into a published
    number.
    """
    clubs, realised = _clubs_and_realised()
    runner = _CountingRunner(clubs)
    rows = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner))
    scored = simretro.score_retro(rows, n_boot=50)
    assert scored["rows"][0]["matrix_col_max_error"] < 1e-8

    # a column-corrupt matrix: rows STILL sum to 1, columns do not
    broken = [dict(r) for r in rows]
    matrix = np.asarray(broken[0]["matrix"], float)
    matrix[0] = np.roll(matrix[0], 1)               # one club's row, permuted
    assert np.allclose(matrix.sum(axis=1), 1.0)
    assert not np.allclose(matrix.sum(axis=0), 1.0)
    broken[0]["matrix"] = matrix.tolist()
    with pytest.raises(Exception) as caught:
        simretro.score_retro(broken, n_boot=50)
    assert "column" in str(caught.value).lower() or "stochastic" in str(
        caught.value).lower()

    # ... and a non-square one is refused as a shape, not scored as a ranking
    stretched = [dict(r) for r in rows]
    stretched[0]["matrix"] = np.asarray(rows[0]["matrix"], float)[:, :19].tolist()
    with pytest.raises(Exception):
        simretro.score_retro(stretched, n_boot=50)


def test_trps_carries_a_monte_carlo_error_and_the_columns_are_renamed(tmp_path):
    """A2 (c), and past it: the column is renamed AND TRPS gets its own SE.

    A2 pre-stated a TRPS Monte-Carlo error as an open item and OUT of scope for
    v2. It is supplied here anyway, by the delta method on the run's own
    per-cell cluster SE; the deviation is recorded as a dated note under A2.
    """
    clubs, realised = _clubs_and_realised()
    runner = _CountingRunner(clubs)
    rows = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner))
    scored = simretro.score_retro(rows, n_boot=50)

    native = [r for r in scored["rows"] if r["arm"] == "dc_native"]
    assert native and all(r["trps_se"] is not None and r["trps_se"] > 0
                          for r in native)
    assert all("delta method" in r["trps_se_method"] for r in native)
    # the nulls record no per-cell error, and the SE is `None` rather than 0
    assert all(r["trps_se"] is None for r in scored["rows"] if r["arm"] == "flat")

    text = simretro.report(scored)
    assert "| TRPS MC SE (diagonal approx.) |" in text
    assert "| mean cell SE |" in text and "| max cell SE |" in text
    assert "| MC SE |" not in text, "the misnamed column is gone"
    assert "Neither is an error on TRPS" in text
    # A2-N4 withdrew "conservative rather than exact" of this quantity; the
    # replacement sentence, and its absence, are pinned in the v3 section below.
    assert "conservative" not in text.lower()

    # the SE really is proportional to the per-cell error it propagates
    doubled = [dict(r) for r in rows]
    for row in doubled:
        if row.get("matrix_se") is not None:
            row["matrix_se"] = (np.asarray(row["matrix_se"], float) * 2).tolist()
    twice = simretro.score_retro(doubled, n_boot=50)
    pairs = {(r["season"], r["cutoff_label"], r["arm"]): r["trps_se"]
             for r in twice["rows"]}
    for row in native:
        key = (row["season"], row["cutoff_label"], row["arm"])
        assert pairs[key] == pytest.approx(2.0 * row["trps_se"], rel=1e-9)


# ==========================================================================
# harness v2.1 — the completeness identity, on the path it was never driven on
# ==========================================================================

def _r1_shaped_ledger(tmp_path, clubs, realised, runner):
    """Three seasons x two cutoffs, scored sharp, in R1's own shape.

    R1's grid was 42 (season, cutoff) cells and its ledger held 34: one season
    refused entirely (`UnverifiedAdjustment`, all six cutoffs) and two openers
    refused under the D11 truncation ceiling. This reproduces that shape small:
    `2099/02` is absent altogether and `2099/01`'s opener is absent, so the
    ledger holds 3 of 6 requested cells and nothing in it says so.
    """
    grid = {"MW0": pd.Timestamp("2099-08-10"), "MW10": pd.Timestamp("2099-11-20")}
    rows = simretro.run_retro(
        seasons=("2099/00", "2099/01"), cutoffs=("MW0", "MW10"),
        arms=("dc_native",), nulls=("flat",), n_sims=64, seed=SEED,
        ledger_path=tmp_path / "r1_shaped.jsonl", runner=runner,
        schedules={"2099/00": grid, "2099/01": grid},
        realised={"2099/00": realised,
                  "2099/01": simretro.Realised(
                      season="2099/01", position=dict(realised.position),
                      span=dict(realised.span), points=dict(realised.points),
                      adjustments={}, n_shared=0)},
        verbose=False, allow_unrecorded_harness=True)
    # dc_native must genuinely beat the flat null, or the flag would be False
    # for a reason that has nothing to do with the accounting.
    sharp = 0.6 * np.eye(len(clubs)) + 0.4 / len(clubs)
    rows = [dict(r, matrix=sharp.tolist()) if r["arm"] == "dc_native" else r
            for r in rows]
    held = [r for r in rows if not (r["season"] == "2099/01"
                                    and r["cutoff_label"] == "MW0")]
    requested = simretro.requested_cells(
        seasons=("2099/00", "2099/01", "2099/02"), cutoffs=("MW0", "MW10"),
        arms=("dc_native",), nulls=("flat",))
    return held, requested


def test_completeness_is_not_derived_from_the_rows_it_was_handed(tmp_path):
    """A2 (b) again, on the ONLY in-repo call path — the default one.

    A2 (b) pre-states `n_expected` as "the requested (season, cutoff) cells"
    and the flag as True only when
    `n_checked + n_documented_refusals == n_expected`. With `expected_cells`
    left at its default the grid was DERIVED from the rows just handed in, so
    every row present was a cell expected and the identity could not fail:
    scored through this path the real 170-row R1 ledger reported n_expected=34,
    n_checked=34, n_missing=0, complete=True,
    dc_native_beats_flat_everywhere=True and STOP_AND_INSPECT=False — on a run
    eight cells short of its preregistered 42. That is A2 (b)'s own sentence,
    "reported True on ANY non-empty subset", reproduced under v2.
    """
    clubs, realised = _clubs_and_realised()
    runner = _CountingRunner(clubs)
    held, requested = _r1_shaped_ledger(tmp_path, clubs, realised, runner)
    assert len(requested) == 12, "three seasons x two cutoffs x two arms"
    assert {(r["season"], r["cutoff_label"]) for r in held} == {
        ("2099/00", "MW0"), ("2099/00", "MW10"), ("2099/01", "MW10")}

    # THE DEFAULT PATH. A4 (ii) retires v2.1's `None`: an unstated request is
    # held against the WHOLE preregistered schedule, which is the most
    # demanding grid available, so it can only ever report more missing.
    derived = simretro.score_retro(held, n_boot=50)
    sanity = derived["sanity"]
    assert sanity["n_expected"] == 210, "seven seasons x six cutoffs x five arms"
    assert "whole preregistered schedule" in sanity["n_expected_source"]
    assert sanity["complete"] is False, "never `None` — the branch is retired"
    assert sanity["dc_native_beats_flat_everywhere"] is False
    assert sanity["STOP_AND_INSPECT"] is True

    # the same rows, with the request stated: six of twelve triples are holes
    stated = simretro.score_retro(held, n_boot=50, expected_triples=requested)
    sanity = stated["sanity"]
    assert sanity["n_expected"] == 12 and sanity["n_scored"] == 6
    assert sanity["n_expected_source"] == "supplied by the caller"
    assert sanity["complete"] is False
    assert sanity["dc_native_beats_flat_everywhere"] is False
    assert sanity["STOP_AND_INSPECT"] is True
    assert {(m["season"], m["cutoff_label"]) for m in sanity["missing"]} == {
        ("2099/01", "MW0"), ("2099/02", "MW0"), ("2099/02", "MW10")}
    assert all(m["documented"] is False for m in sanity["missing"])
    assert sanity["n_typed_refusals"] == 0

    # POSITIVE CONTROL: state the grid the ledger really does fill and the flag
    # can be True — so it is the accounting moving it, not the fix disabling it.
    whole = simretro.score_retro(
        held, n_boot=50,
        expected_triples=[(s, c, a)
                          for s, c in (("2099/00", "MW0"), ("2099/00", "MW10"),
                                       ("2099/01", "MW10"))
                          for a in ("dc_native", "flat")])
    assert whole["sanity"]["n_expected"] == 6
    assert whole["sanity"]["n_scored"] == 6
    assert whole["sanity"]["n_cells_compared"] == 3
    assert whole["sanity"]["complete"] is True
    assert whole["sanity"]["dc_native_beats_flat_everywhere"] is True
    assert whole["sanity"]["STOP_AND_INSPECT"] is False

    # and the report says which of the two it is reading, in words
    text = simretro.report(derived)
    assert "the accounting closes: **False**" in text
    assert "whole preregistered schedule" in text
    assert simretro.report(whole).count("the accounting closes: **True**") == 1


def test_run_retro_returns_the_documented_refusals_it_wrote(tmp_path):
    """A2 (b)'s other half: `n_documented_refusals` was structurally zero.

    `run_retro` returned only rows that are NOT `not_applicable`, so the
    documented-refusal term of the identity could never be non-zero on the path
    that produces rows: a cell the runner legitimately declined, and wrote a
    reason for, was indistinguishable from a hole. The marker is bookkeeping
    for the resume AND the only evidence the accounting has that a missing cell
    was refused on purpose.
    """
    clubs, realised = _clubs_and_realised()
    runner = _CountingRunner(clubs, undefined_at=(("flat", "MW10"),))
    rows = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner))
    sharp = 0.6 * np.eye(len(clubs)) + 0.4 / len(clubs)
    rows = [dict(r, matrix=sharp.tolist()) if r["arm"] == "dc_native" else r
            for r in rows]

    refusals = [r for r in rows if r.get("refusal_kind")]
    assert len(refusals) == 1, "the refusal comes back beside the forecasts"
    assert (refusals[0]["arm"], refusals[0]["cutoff_label"]) == ("flat", "MW10")
    assert refusals[0]["refusal_kind"] == "arm_not_defined"
    assert refusals[0]["reason"]

    cells = simretro.requested_cells(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                                     arms=("dc_native",), nulls=("flat",))
    scored = simretro.score_retro(rows, n_boot=50, expected_triples=cells)
    sanity = scored["sanity"]
    assert sanity["n_scored"] == 3
    assert sanity["n_typed_refusals"] == 1
    assert sanity["complete"] is True, "3 scored + 1 refused == 4 expected"
    assert sanity["STOP_AND_INSPECT"] is False
    assert sanity["missing"][0]["documented"] is True

    # POSITIVE CONTROL: hide the marker — the same shape becomes an
    # undocumented hole, which is exactly what the harness used to do to itself.
    hidden = [r for r in rows if not r.get("refusal_kind")]
    blind = simretro.score_retro(hidden, n_boot=50, expected_triples=cells)
    assert blind["sanity"]["n_typed_refusals"] == 0
    assert blind["sanity"]["complete"] is False
    assert blind["sanity"]["dc_native_beats_flat_everywhere"] is False
    assert blind["sanity"]["STOP_AND_INSPECT"] is True


def test_requested_cells_is_the_grid_run_retro_fills(tmp_path):
    """The request has to be statable, and stated the same way twice.

    `expected_cells` is only worth anything if the caller can name the grid
    without restating the harness's own defaults by hand — a second, drifting
    copy of the schedule would close the identity against the wrong thing.
    """
    assert simretro.requested_cells() == tuple(
        (s, c, a) for s in simretro.SEASONS
        for c in simretro.COMPARISON_CUTOFFS
        for a in (*simretro.ARMS, *simretro.NULLS))
    assert len(simretro.requested_cells()) == 175
    assert simretro.requested_cells(smoke=True) == tuple(
        ("2025/26", c, a) for c in ("MW0", "MW10")
        for a in (*simretro.ARMS, *simretro.NULLS))
    assert len(simretro.requested_cells(
        cutoffs=simretro.CUTOFF_LABELS)) == 210, "the whole preregistered grid"
    with pytest.raises(simretro.RetroError, match="not in the fixed schedule"):
        simretro.requested_cells(cutoffs=("MW7",))

    # POSITIVE CONTROL: it is the grid the run really fills, not a parallel list
    clubs, realised = _clubs_and_realised()
    runner = _CountingRunner(clubs)
    rows = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner))
    assert {(r["season"], r["cutoff_label"], r["arm"]) for r in rows} == set(
        simretro.requested_cells(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                                 arms=("dc_native",), nulls=("flat",)))


R1_LEDGER = paths.DATA_DIR / "sim" / "retro_r1.jsonl"
needs_r1_ledger = pytest.mark.skipif(
    not R1_LEDGER.exists(), reason="the R1 ledger is not in this checkout")


@needs_r1_ledger
def test_the_real_r1_ledger_does_not_certify_itself(tmp_path):
    """The artifact the defect was found on, held against the fixed harness.

    The R1 ledger is 170 rows covering 34 of the 42 preregistered
    (season, cutoff) cells: 2023/24 refused entirely (`UnverifiedAdjustment`,
    six cutoffs) and two openers refused under the D11 ceiling. Scored through
    the DEFAULT path it used to report n_expected=34, n_checked=34, n_missing=0,
    complete=True, dc_native_beats_flat_everywhere=True, STOP_AND_INSPECT=False.

    Gitignored, so this skips on a clean checkout; where the file exists it is
    the only test here whose rows were produced by real fits.
    """
    rows = [json.loads(line) for line in R1_LEDGER.read_text().splitlines()
            if line.strip()]
    assert len(rows) == 170
    assert not any(r.get("refusal_kind") for r in rows), (
        "v1 wrote no typed markers — that is the point of this test")

    # 1. the default path is now the WHOLE preregistered schedule (A4 (ii)),
    #    which is the most demanding grid available and reports more missing.
    derived = simretro.score_retro(rows, n_boot=20)["sanity"]
    assert derived["n_expected"] == 210
    assert derived["n_scored"] == 166, "170 rows, 4 of them untyped markers"
    assert derived["n_typed_refusals"] == 0
    assert derived["complete"] is False
    assert derived["dc_native_beats_flat_everywhere"] is False
    assert derived["STOP_AND_INSPECT"] is True

    # 2. against the preregistered grid it is incomplete, and NAMES the holes
    whole = simretro.requested_cells(cutoffs=simretro.CUTOFF_LABELS)
    assert len(whole) == 210, "42 cells x five arms"
    stated = simretro.score_retro(rows, n_boot=20,
                                  expected_triples=whole)["sanity"]
    assert stated["n_expected"] == 210 and stated["n_scored"] == 166
    assert stated["n_cells_compared"] == 34
    assert stated["complete"] is False
    assert stated["dc_native_beats_flat_everywhere"] is False
    cells = sorted({(m["season"], m["cutoff_label"]) for m in stated["missing"]
                    if len({m2["arm"] for m2 in stated["missing"]
                            if (m2["season"], m2["cutoff_label"])
                            == (m["season"], m["cutoff_label"])}) == 5})
    assert cells == sorted(
        [("2023/24", label) for label in simretro.CUTOFF_LABELS]
        + [("2019/20", "MW0"), ("2020/21", "MW0")]), (
        "exactly the two refusals reports/epl_sim_retro_v1_1.md §2 describes")

    # 3. A4 (i) re-reads R1's own four `ppg_pointmass` markers: they carry
    #    `not_applicable` TEXT and no `refusal_kind`, because v1 wrote no typed
    #    field. Under v3 they are holes, so even the admissible grid R1 scopes
    #    its numbers to no longer closes — which is exactly what A4 says: "the
    #    first retrospective run under v3 is the first run that can report
    #    complete = True against a stated triple-level grid". No R1 number
    #    moves; R1 stands under v1 and is not re-scored.
    hole_cells = set(cells)
    admissible = [t for t in whole if (t[0], t[1]) not in hole_cells]
    assert len(admissible) == 170
    under_v3 = simretro.score_retro(rows, n_boot=20,
                                    expected_triples=admissible)["sanity"]
    assert under_v3["n_expected"] == 170 and under_v3["n_scored"] == 166
    assert under_v3["n_typed_refusals"] == 0, "v1 markers are untyped"
    assert under_v3["complete"] is False
    assert under_v3["dc_native_beats_flat_everywhere"] is False
    assert {(m["arm"], m["cutoff_label"]) for m in under_v3["missing"]} == {
        ("ppg_pointmass", "MW0")}

    # 4. POSITIVE CONTROL: against the 166 triples R1 really scored the
    #    accounting closes and the hard check is True — so it is the typed-marker
    #    rule moving the flag above, not the fix disabling it.
    scored_triples = [(r["season"], r["cutoff_label"], r["arm"]) for r in rows
                      if not r.get("not_applicable")]
    assert len(scored_triples) == 166
    closed = simretro.score_retro(rows, n_boot=20,
                                  expected_triples=scored_triples)["sanity"]
    assert closed["n_expected"] == 166 and closed["n_scored"] == 166
    assert closed["complete"] is True
    assert closed["dc_native_beats_flat_everywhere"] is True
    assert closed["STOP_AND_INSPECT"] is False


# ==========================================================================
# harness v3 — amendment A4, recorded before this code existed
# ==========================================================================
#
# A4 rules four things and pre-states every one of them before a line of
# `epl/simretro.py` changed under it:
#
#   (i)   refusals are TYPED, written by the runner, and only typed markers
#         count as documented refusals;
#   (ii)  `n_expected` is the schedule — seasons x cutoffs x ARMS — on every
#         path, and the accounting unit is the (season, cutoff, arm) triple;
#   (iii) a row with no producer refuses the run unless `allow_legacy_rows`;
#   (iv)  an unrecorded harness pair refuses the run before any fit, unless
#         `allow_unrecorded_harness` — which the suite passes, and which makes
#         the run uncitable.
#
# Every test below drives the guard RED on the thing it exists to refuse, not
# merely green on a good run.

def _v3_kwargs(tmp_path, clubs, realised, runner, ledger=None, **extra):
    """`_v2_kwargs` plus what A4 (iv) requires of a development run."""
    kwargs = _v2_kwargs(tmp_path, clubs, realised, runner, ledger)
    kwargs["allow_unrecorded_harness"] = True
    kwargs.update(extra)
    return kwargs


class _TypedRunner(_CountingRunner):
    """A runner that SAYS what it refused, in a typed field.

    A4 (i): a refusal is a fact the runner knows and the scorer does not. Under
    v2.1 the caller wrote the alibi — any arm missing from `CutoffResult.arms`
    became a `not_applicable` marker with a reason the CALLER invented — so an
    accidentally dropped `flat` was indistinguishable from a null that is
    undefined by rule. `refuse_at` names refusals the runner declares;
    `drop_at` names arms it silently loses, which must NOT be documented.
    """

    def __init__(self, clubs, refuse_at: tuple = (), drop_at: tuple = (),
                 raise_at: dict | None = None):
        super().__init__(clubs)
        self.refuse_at = {(a, c): k for a, c, k in refuse_at}
        self.drop_at = set(drop_at)
        self.raise_at = dict(raise_at or {})

    def __call__(self, *, season, cutoff_label, cutoff, arms, nulls, n_sims, seed):
        self.calls.append((season, cutoff_label, seed))
        if cutoff_label in self.raise_at:
            raise self.raise_at[cutoff_label]
        rng = np.random.default_rng(abs(hash((season, cutoff_label, seed))) % 2**32)
        out, refusals = {}, {}
        for arm in arms:
            if (arm, cutoff_label) in self.drop_at:
                continue
            if (arm, cutoff_label) in self.refuse_at:
                refusals[arm] = (self.refuse_at[(arm, cutoff_label)],
                                 f"{arm} refused at {cutoff_label}")
                continue
            out[arm] = _fake_arm(rng, len(self.clubs), n_sims)
        for null in nulls:
            if (null, cutoff_label) in self.drop_at:
                continue
            if (null, cutoff_label) in self.refuse_at:
                refusals[null] = (self.refuse_at[(null, cutoff_label)],
                                  f"{null} refused at {cutoff_label}")
                continue
            out[null] = simretro.ArmResult.from_null(
                bridge_mod.flat_matrix(len(self.clubs)), n_sims=n_sims)
        return simretro.CutoffResult(clubs=self.clubs, arms=out,
                                     provenance={"synthetic": True,
                                                 "wall_seconds": rng.random()},
                                     refusals=refusals)


def _sharpen(rows, clubs):
    """dc_native beats the flat null, so only the ACCOUNTING can move a flag."""
    sharp = 0.6 * np.eye(len(clubs)) + 0.4 / len(clubs)
    return [dict(r, matrix=sharp.tolist())
            if r["arm"] == "dc_native" and not r.get("refusal_kind") else r
            for r in rows]


def test_only_a_typed_marker_the_runner_wrote_is_a_documented_refusal(tmp_path):
    """A4 (i): the harness stops writing its own alibi.

    Under v2.1 `run_retro` manufactured a `not_applicable` marker for ANY arm
    the runner did not return, with the reason "{arm} is not defined at
    {label}" — for the required `dc_native` and the always-defined `flat` too.
    An accidentally dropped `flat` therefore produced a marker, a "documented
    refusal", and `complete = True` on a run that had silently lost the
    comparison the retrospective exists to make.
    """
    clubs, realised = _clubs_and_realised()
    grid = simretro.requested_cells(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                                    arms=("dc_native",), nulls=("flat",))

    # 1. a refusal the RUNNER declares is typed, and it closes the accounting
    runner = _TypedRunner(clubs, refuse_at=(("flat", "MW10", "arm_not_defined"),))
    rows = _sharpen(simretro.run_retro(
        **_v3_kwargs(tmp_path / "typed", clubs, realised, runner)), clubs)
    marker = [r for r in rows if r.get("refusal_kind")]
    assert len(marker) == 1
    assert marker[0]["refusal_kind"] == "arm_not_defined"
    assert marker[0]["reason"] == "flat refused at MW10"
    assert (marker[0]["arm"], marker[0]["cutoff_label"]) == ("flat", "MW10")

    sanity = simretro.score_retro(rows, n_boot=50, expected_triples=grid)["sanity"]
    assert sanity["n_expected"] == 4
    assert sanity["n_scored"] == 3
    assert sanity["n_typed_refusals"] == 1
    assert sanity["complete"] is True
    assert sanity["STOP_AND_INSPECT"] is False

    # 2. THE DEFECT: the same shape, but the runner never said anything. No
    #    marker may be written on its behalf, and the accounting must not close.
    dropped = _TypedRunner(clubs, drop_at=(("flat", "MW10"),))
    lost = _sharpen(simretro.run_retro(
        **_v3_kwargs(tmp_path / "dropped", clubs, realised, dropped)), clubs)
    assert not any(r.get("refusal_kind") for r in lost), (
        "the caller must not invent a reason the runner never gave")
    assert not any(r.get("not_applicable") for r in lost)
    sanity = simretro.score_retro(lost, n_boot=50, expected_triples=grid)["sanity"]
    assert sanity["n_scored"] == 3
    assert sanity["n_typed_refusals"] == 0
    assert sanity["complete"] is False
    assert sanity["dc_native_beats_flat_everywhere"] is False
    assert sanity["STOP_AND_INSPECT"] is True
    assert [(m["season"], m["cutoff_label"], m["arm"]) for m in sanity["missing"]] \
        == [("2099/00", "MW10", "flat")]

    # 3. and a v1-shaped marker — `not_applicable` text, no `refusal_kind` —
    #    is a HOLE, not a documented refusal. This is the row R1 wrote.
    legacy = dict(lost[0])
    legacy.update({"arm": "flat", "cutoff_label": "MW10", "matrix": None,
                   "not_applicable": "flat is not defined at MW10"})
    legacy.pop("refusal_kind", None)
    blind = simretro.score_retro(lost + [legacy], n_boot=50,
                                 expected_triples=grid)["sanity"]
    assert blind["n_typed_refusals"] == 0, "untyped text is not a typed marker"
    assert blind["complete"] is False


def test_a_whole_cell_refusal_is_typed_for_every_requested_arm(tmp_path):
    """A4 (i), second half: the refusals that matter most reach the accounting.

    The two refusals R1 actually hit — `UnverifiedAdjustment` and
    `ExcludedMassTooLarge` — are raised INSIDE the cell, before any row is
    written, and propagated out of `run_retro`. Nothing wrote a marker; the
    cell was simply absent, and the accounting could only call it a hole. R1's
    eight missing cells are documented in PROSE, by a human, which is exactly
    the class of guarantee this ledger exists to convert into a check.
    """
    clubs, realised = _clubs_and_realised()
    ceiling = particles.ExcludedMassTooLarge("excluded mass 3.1e-2 > 2e-2")
    runner = _TypedRunner(clubs, raise_at={"MW10": ceiling})
    rows = _sharpen(simretro.run_retro(
        **_v3_kwargs(tmp_path / "ceiling", clubs, realised, runner)), clubs)

    marked = [r for r in rows if r.get("refusal_kind")]
    assert {(r["arm"], r["cutoff_label"]) for r in marked} == {
        ("dc_native", "MW10"), ("flat", "MW10")}, "every requested arm of the cell"
    assert {r["refusal_kind"] for r in marked} == {"excluded_mass_ceiling"}
    assert all("2e-2" in r["reason"] for r in marked)

    grid = simretro.requested_cells(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                                    arms=("dc_native",), nulls=("flat",))
    sanity = simretro.score_retro(rows, n_boot=50, expected_triples=grid)["sanity"]
    assert sanity["n_scored"] == 2 and sanity["n_typed_refusals"] == 2
    assert sanity["complete"] is True, "the run continues and the hole is NAMED"

    # a season-level refusal — R1's 2023/24, all six cutoffs — is marked too.
    # `realised_positions` raises before any cutoff of the season is reached.
    def _refusing_runner(**kwargs):                          # pragma: no cover
        raise AssertionError("no cell may be fitted for a refused season")

    def _unverified(*a, **k):
        raise season_mod.UnverifiedAdjustment("everton -10 is unverified")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(simretro, "realised_positions", _unverified)
        season_rows = simretro.run_retro(
            seasons=("2099/00",), cutoffs=("MW0", "MW10"), arms=("dc_native",),
            nulls=("flat",), n_sims=64, seed=SEED,
            ledger_path=tmp_path / "season.jsonl", runner=_refusing_runner,
            schedules={"2099/00": {"MW0": pd.Timestamp("2099-08-10"),
                                   "MW10": pd.Timestamp("2099-11-20")}},
            # `realised={}` and not `None`: the season is absent from it, so
            # `realised_positions` IS called and refuses — without making this
            # test load the (gitignored) archive parquet to get there.
            realised={}, verbose=False, allow_unrecorded_harness=True)
    assert len(season_rows) == 4, "two cutoffs x two arms, every one marked"
    assert {r["refusal_kind"] for r in season_rows} == {"unverified_adjustment"}
    assert all("everton" in r["reason"] for r in season_rows)


def test_an_unexpected_error_is_marked_and_then_re_raised(tmp_path):
    """A4 (i): `runner_error` names the hole AND stops the run.

    The marker exists so the hole is named in the ledger and can be seen by the
    resumed run — not so that an unknown error can be swallowed.
    """
    clubs, realised = _clubs_and_realised()
    boom = ZeroDivisionError("the fit fell over")
    runner = _TypedRunner(clubs, raise_at={"MW10": boom})
    ledger = tmp_path / "boom.jsonl"
    with pytest.raises(ZeroDivisionError):
        simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner, ledger))

    written = [json.loads(line) for line in ledger.read_text().splitlines()
               if line.strip()]
    marked = [r for r in written if r.get("refusal_kind")]
    assert {(r["arm"], r["cutoff_label"]) for r in marked} == {
        ("dc_native", "MW10"), ("flat", "MW10")}
    assert {r["refusal_kind"] for r in marked} == {"runner_error"}
    assert all("ZeroDivisionError" in r["reason"] for r in marked)

    # POSITIVE CONTROL: the three EXPECTED kinds do not stop the run — only
    # this one does, and only because nothing explains it.
    quiet = _TypedRunner(clubs, raise_at={
        "MW10": particles.ExcludedMassTooLarge("excluded mass too large")})
    simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, quiet,
                                    tmp_path / "quiet.jsonl"))


def test_the_expected_grid_is_the_schedule_on_every_path(tmp_path):
    """A4 (ii): the unit is the triple, and an unstated request is not a licence.

    v2.1 answered an unstated grid with `None` — NOT EVALUATED. A4 retires that
    branch: the default is the WHOLE preregistered schedule, which is the most
    demanding grid available, so an unstated request can only ever report more
    missing and never fewer.
    """
    assert simretro.requested_cells()[0] == ("2019/20", "MW0", "dc_native")
    assert len(simretro.requested_cells()) == 7 * 5 * 5
    assert len(simretro.requested_cells(cutoffs=simretro.CUTOFF_LABELS)) == 210
    assert simretro.requested_cells(smoke=True)[:2] == (
        ("2025/26", "MW0", "dc_native"), ("2025/26", "MW0", "dc_wdl_bridge"))
    assert len(simretro.requested_cells(smoke=True)) == 10
    with pytest.raises(simretro.RetroError, match="not in the fixed schedule"):
        simretro.requested_cells(cutoffs=("MW7",))

    clubs, realised = _clubs_and_realised()
    runner = _TypedRunner(clubs)
    rows = _sharpen(simretro.run_retro(
        **_v3_kwargs(tmp_path, clubs, realised, runner)), clubs)
    assert {(r["season"], r["cutoff_label"], r["arm"]) for r in rows} == set(
        simretro.requested_cells(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                                 arms=("dc_native",), nulls=("flat",)))

    # THE DEFAULT PATH: scored against the whole preregistered schedule
    derived = simretro.score_retro(rows, n_boot=50)["sanity"]
    assert derived["n_expected"] == 210
    assert "whole preregistered schedule" in derived["n_expected_source"]
    assert derived["n_scored"] == 0, "none of these triples is in the schedule"
    assert derived["complete"] is False, "never `None` again — the branch is gone"
    assert derived["dc_native_beats_flat_everywhere"] is False
    assert derived["STOP_AND_INSPECT"] is True

    # ... and the report says so in words, without printing 210 holes
    text = simretro.report(simretro.score_retro(rows, n_boot=50))
    assert "NOT EVALUATED" not in text
    assert "the accounting closes: **False**" in text

    # POSITIVE CONTROL: state the grid this run really asked for and it closes
    stated = simretro.score_retro(rows, n_boot=50, expected_triples=(
        simretro.requested_cells(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                                 arms=("dc_native",), nulls=("flat",))))["sanity"]
    assert stated["n_expected"] == 4 and stated["n_scored"] == 4
    assert stated["complete"] is True
    assert stated["dc_native_beats_flat_everywhere"] is True
    assert stated["STOP_AND_INSPECT"] is False

    # an ARM lost inside a cell that IS present is what the cell unit could not
    # see: three of four triples scored, and the identity fails on the arm.
    thin = [r for r in rows if not (r["arm"] == "flat"
                                    and r["cutoff_label"] == "MW10")]
    lost = simretro.score_retro(thin, n_boot=50, expected_triples=(
        simretro.requested_cells(seasons=("2099/00",), cutoffs=("MW0", "MW10"),
                                 arms=("dc_native",), nulls=("flat",))))["sanity"]
    assert lost["n_scored"] == 3 and lost["n_expected"] == 4
    assert lost["complete"] is False


def test_a_producer_less_row_refuses_the_run_unless_it_is_allowed(tmp_path):
    """A4 (iii): the provenance guard's own escape hatch.

    The refusal skipped rows whose `producer` is absent — and an absent
    producer is precisely the v1 schema, so a v1 ledger was appended to
    silently by a later run. The keys cannot collide, but the file ends up
    holding two producers' rows with nothing recording it.
    """
    clubs, realised = _clubs_and_realised()
    ledger = tmp_path / "legacy.jsonl"
    legacy = {"schema_version": "epl-simretro-1",
              "run_key": "2099/00|MW0|2099-08-10|dc_native|n64|s20260611",
              "season": "2099/00", "cutoff_label": "MW0", "arm": "dc_native"}
    ledger.write_text(json.dumps(legacy) + "\n")

    runner = _TypedRunner(clubs)
    with pytest.raises(simretro.RetroError, match="no producer") as caught:
        simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner, ledger))
    assert runner.calls == [], "it refused BEFORE paying for a fit"
    assert legacy["run_key"] in str(caught.value), "it names the offending key"

    # the override is explicit, is recorded on every row the run writes, and is
    # counted separately from the foreign-producer override it is not
    mixed = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner,
                                            ledger, allow_legacy_rows=True))
    assert runner.calls, "the override really did run"
    assert all(r.get("allow_legacy_rows") for r in mixed)
    scored = simretro.score_retro(_sharpen(mixed, clubs), n_boot=50)["sanity"]
    assert scored["n_legacy_row_overrides"] == 4
    assert scored["n_foreign_producer_overrides"] == 0
    text = simretro.report(simretro.score_retro(_sharpen(mixed, clubs), n_boot=50))
    assert "legacy" in text.lower() and "override" in text.lower()



def test_run_retro_refuses_an_unrecorded_harness_before_any_fit(tmp_path,
                                                                monkeypatch):
    """A4 (iv): the §12 invalidation condition finally has code behind it.

    A2-N1 and A2-N2 both say "a run whose harness hashes match none of the
    pairs recorded here refuses, exactly as prereg §12 requires."
    `producer_identity` hashed both files and folded the digest into the key —
    which makes rows from different harnesses non-interchangeable, and is worth
    having — but it never COMPARED those hashes to the recorded pairs. A fresh
    ledger under an arbitrarily modified harness ran to completion and reported
    nothing unusual.
    """
    clubs, realised = _clubs_and_realised()
    runner = _TypedRunner(clubs)
    kwargs = _v2_kwargs(tmp_path, clubs, realised, runner)   # no override

    # 1. the running pair is not one of the recorded pairs -> refuse, by name
    fake = ({"version": "v0", "simretro_sha256": "0" * 64,
             "simmetrics_sha256": "1" * 64, "recorded_in": "nowhere"},)
    monkeypatch.setattr(simretro, "recorded_harness_versions", lambda: fake)
    with pytest.raises(simretro.UnrecordedHarness) as caught:
        simretro.run_retro(**kwargs)
    assert runner.calls == [], "it refused BEFORE paying for a fit"
    message = str(caught.value)
    assert simretro.harness_hashes()[0][:12] in message
    assert "allow_unrecorded_harness" in message

    # 2. the override is explicit, recorded on every row, and printed
    rows = _sharpen(simretro.run_retro(**kwargs, allow_unrecorded_harness=True),
                    clubs)
    assert all(r.get("allow_unrecorded_harness") for r in rows)
    scores = simretro.score_retro(rows, n_boot=50)
    assert scores["sanity"]["n_unrecorded_harness_overrides"] == 4
    text = simretro.report(scores)
    assert "not a citable run" in text

    # 3. POSITIVE CONTROL: record the running pair and no override is needed
    running = simretro.harness_hashes()
    monkeypatch.setattr(simretro, "recorded_harness_versions", lambda: (
        {"version": "vX", "simretro_sha256": running[0],
         "simmetrics_sha256": running[1], "recorded_in": "this test"},))
    clean = simretro.run_retro(**_v2_kwargs(tmp_path, clubs, realised,
                                            _TypedRunner(clubs),
                                            tmp_path / "clean.jsonl"))
    assert clean and not any(r.get("allow_unrecorded_harness") for r in clean)


def _ledger_harness_versions(text: str) -> dict[str, tuple[str, str]]:
    """Every (version -> hash pair) amendment A4 records, table or dated note.

    A4 (iv) says "the code's list must equal this ledger's list — a test reads
    this file and fails if they diverge". Hashes are recorded abbreviated in
    A4's ruling table (`2b25ab35…`) and in full in the dated note appended
    after the Fix commit; both shapes are read, and a cell that is not
    hash-shaped — the ruling table's placeholder row for v3 — is skipped.
    """
    import re

    start = text.find("## A4 —")
    assert start >= 0, "amendment A4 is not in the ledger"
    entry = text[start:]
    nxt = entry.find("\n## ", 1)
    entry = entry if nxt < 0 else entry[:nxt]

    def _hash(cell: str) -> str | None:
        cell = cell.strip().strip("`").strip()
        cell = cell.split(" ")[0].rstrip("…").strip("`")
        return cell if re.fullmatch(r"[0-9a-f]{8,64}", cell) else None

    out: dict[str, tuple[str, str]] = {}
    for line in entry.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        version = cells[0].strip().strip("`")
        if not re.fullmatch(r"v\d+(\.\d+)?", version):
            continue
        one, two = _hash(cells[1]), _hash(cells[2])
        if one and two:
            out[version] = (one, two)
    return out


def test_the_recorded_harness_list_in_the_code_equals_the_one_in_the_ledger():
    """A4 (iv): put the check where the claim is.

    The pattern this ledger was created to catch is a guarantee stated in a
    document, satisfied in fact, and unenforced in code. The recorded pairs
    live in `epl/retro_harness_versions.json`; amendment A4 states them; this
    is the check that the two cannot drift.
    """
    ledger_path = (Path(simretro.__file__).resolve().parents[1] / "reports"
                   / "epl_sim_amendments.md")
    if not ledger_path.exists():                            # pragma: no cover
        pytest.skip("reports/ is not in this checkout")
    stated = _ledger_harness_versions(ledger_path.read_text(encoding="utf-8"))
    coded = {v["version"]: (v["simretro_sha256"], v["simmetrics_sha256"])
             for v in simretro.recorded_harness_versions()}

    assert set(coded) == set(stated), (
        f"code records {sorted(coded)}, the ledger records {sorted(stated)}")
    for version, (one, two) in stated.items():
        assert coded[version][0].startswith(one), f"{version} epl/simretro.py"
        assert coded[version][1].startswith(two), f"{version} epl/simmetrics.py"
        assert len(coded[version][0]) == 64 and len(coded[version][1]) == 64

    # And HEAD's own harness pair is one of them. A4 (iv) makes a run under an
    # unrecorded pair invalid, so a checkout whose harness is not recorded can
    # only produce uncitable runs — which is a state worth failing on, not a
    # state to be discovered by a run that refuses. The Fix commit that created
    # v3 is followed by the commit that records it; this is what makes that
    # second commit mandatory rather than a promise.
    assert simretro.harness_hashes() in {
        (v["simretro_sha256"], v["simmetrics_sha256"]) for v in
        simretro.recorded_harness_versions()}, (
        "epl/simretro.py or epl/simmetrics.py has changed without being "
        "recorded in epl/retro_harness_versions.json and amendment A4")

    # POSITIVE CONTROL: the parser reads the LEDGER, not the code, and the
    # comparison above really fails when the two disagree — on a hash, and on
    # the set of versions.
    drifted = ledger_path.read_text(encoding="utf-8").replace(
        "e449c78d", "dddddddd")
    moved = _ledger_harness_versions(drifted)
    assert moved["v2.1"][0].startswith("dddddddd")
    assert not coded["v2.1"][0].startswith(moved["v2.1"][0]), (
        "a drifted hash must fail the startswith check this test makes")
    dropped = ledger_path.read_text(encoding="utf-8").replace(
        "| v2.1 | `e449c78d", "| REMOVED | `e449c78d")
    assert set(_ledger_harness_versions(dropped)) != set(coded), (
        "a version missing from the ledger must fail the set equality")


def test_the_trps_se_is_a_diagonal_approximation_of_unknown_direction(tmp_path):
    """A2-N4 item 2: the word "conservative" is WITHDRAWN of this quantity.

    A2-N1 wrote that a club's cells are predominantly negatively correlated —
    true — and concluded that the diagonal sum OVERSTATES the variance — which
    does not follow. What the estimator drops is `g · g' · Cov`, not `Cov`, and
    the TRPS gradient changes sign within a club's row, so a negative
    covariance times two gradient components of opposite sign contributes a
    POSITIVE term. The direction of the approximation is not known, and
    "conservative" is exactly the word a reader uses to decide whether a tight
    SE can be trusted.
    """
    clubs, realised = _clubs_and_realised()
    runner = _TypedRunner(clubs)
    rows = simretro.run_retro(**_v3_kwargs(tmp_path, clubs, realised, runner))
    scored = simretro.score_retro(rows, n_boot=50)

    native = [r for r in scored["rows"] if r["arm"] == "dc_native"]
    assert native and all(r["trps_se"] is not None and r["trps_se"] > 0
                          for r in native)
    method = native[0]["trps_se_method"]
    assert "diagonal" in method
    assert "can raise or lower the variance" in method
    assert "not known" in method

    text = simretro.report(scored)
    assert "| TRPS MC SE (diagonal approx.) |" in text
    assert "| MC SE |" not in text, "the misnamed column is still gone"
    assert "the direction of the approximation is not known" in text

    # the withdrawn word is gone from every surface this quantity appears on
    for surface in (text, method, simmetrics.trps_se.__doc__):
        assert "conservative" not in surface.lower(), (
            "A2-N4 withdrew 'conservative' of the TRPS MC SE; it is back")
    assert "overstates" not in text.lower()


def test_the_cluster_bootstrap_se_needs_no_independence_assumption():
    """A2-N4 item 3: the estimator that answers the question, per particle.

    The delta method approximates a variance it cannot sign. Resampling the
    PARTICLES — the same cluster the stored per-cell error is built on — and
    recomputing TRPS on each resample needs no independence assumption, no
    gradient and no covariance matrix, and it is an error ON TRPS rather than
    one propagated from the cells. B and the resampling seed are deliberately
    NOT chosen here: A2-N4 pre-states them in the amendment accompanying the
    first run that reports the number, so both are required arguments with no
    default and nothing in the harness calls this yet.
    """
    import inspect

    signature = inspect.signature(simmetrics.trps_se_cluster)
    for name in ("n_boot", "seed"):
        assert signature.parameters[name].default is inspect.Parameter.empty, (
            f"{name} must be chosen by the amendment, not by this module")

    # two particles, two clubs; each particle is a permutation tally
    first = np.array([[1.0, 0.0], [0.0, 1.0]])
    second = np.array([[0.0, 1.0], [1.0, 0.0]])
    positions = [1, 2]

    # every particle identical -> every resample identical -> exactly zero
    same = np.stack([first, first, first])
    assert simmetrics.trps_se_cluster(same, positions, n_boot=64, seed=1) == 0.0

    # two distinct particles: a resample draws k copies of the first, k ~ Bin(2,
    # 1/2), and TRPS is a function of k alone. The exact standard deviation over
    # that three-point law is computed here without touching the estimator.
    pair = np.stack([first, second])
    exact_values, weights = [], [0.25, 0.5, 0.25]
    for k in (0, 1, 2):
        matrix = (k * first + (2 - k) * second) / 2.0
        exact_values.append(simmetrics.trps(matrix, positions))
    mean = sum(w * v for w, v in zip(weights, exact_values))
    exact = math.sqrt(sum(w * (v - mean) ** 2 for w, v in zip(weights, exact_values)))
    got = simmetrics.trps_se_cluster(pair, positions, n_boot=20_000, seed=7)
    assert got == pytest.approx(exact, rel=0.05)
    assert got > 0

    # deterministic in the seed, and the seed is load-bearing
    assert simmetrics.trps_se_cluster(pair, positions, n_boot=500, seed=7) == \
        simmetrics.trps_se_cluster(pair, positions, n_boot=500, seed=7)
    assert simmetrics.trps_se_cluster(pair, positions, n_boot=500, seed=8) != \
        simmetrics.trps_se_cluster(pair, positions, n_boot=500, seed=7)

    # and it refuses what it cannot resample
    with pytest.raises(simmetrics.MetricError):
        simmetrics.trps_se_cluster(pair, positions, n_boot=1, seed=1)
    with pytest.raises(simmetrics.MetricError):
        simmetrics.trps_se_cluster(first, positions, n_boot=8, seed=1)
    with pytest.raises(simmetrics.MetricError):
        simmetrics.trps_se_cluster(-1.0 * pair, positions, n_boot=8, seed=1)
    lopsided = np.stack([first, 3.0 * second])
    with pytest.raises(simmetrics.MetricError, match="unequal"):
        simmetrics.trps_se_cluster(lopsided, positions, n_boot=8, seed=1)
