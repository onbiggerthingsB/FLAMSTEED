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

import numpy as np
import pandas as pd
import pytest

from epl import baseline, bridge as bridge_mod, leaguesim, paths
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
    realised = simretro.realised_positions(matches, "2023/24", require_verified=False)

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
    without = simretro.realised_positions(matches, "2023/24", require_verified=False,
                                          adjustments={})
    assert without.position["everton"] < realised.position["everton"]

    # the scoring gate: an unverified row refuses to score the season
    with pytest.raises(season_mod.UnverifiedAdjustment):
        simretro.realised_positions(matches, "2023/24")

    # a season with no adjustment rows scores under the gate without complaint
    clean = simretro.realised_positions(matches, "2024/25")
    assert clean.adjustments == {}
    assert sorted(clean.position.values()) == list(range(1, 21))


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
    """

    def __init__(self, clubs, undefined_at: tuple = ()):
        self.clubs = tuple(clubs)
        self.calls: list[tuple] = []
        self.undefined_at = set(undefined_at)

    def __call__(self, *, season, cutoff_label, cutoff, arms, nulls, n_sims, seed):
        self.calls.append((season, cutoff_label, seed))
        rng = np.random.default_rng(abs(hash((season, cutoff_label, seed))) % 2**32)
        out = {arm: _fake_arm(rng, len(self.clubs), n_sims) for arm in arms}
        for null in nulls:
            if (null, cutoff_label) in self.undefined_at:
                continue
            out[null] = simretro.ArmResult.from_null(
                bridge_mod.flat_matrix(len(self.clubs)), n_sims=n_sims)
        return simretro.CutoffResult(clubs=self.clubs, arms=out,
                                     provenance={"synthetic": True,
                                                 "wall_seconds": rng.random()})


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
                  realised={"2099/00": realised}, verbose=False)

    first = simretro.run_retro(**kwargs)
    assert len(runner.calls) == 2, "one runner call per (season, cutoff)"
    assert len(first) == 7, "2 arms + flat at both cutoffs, ppg only at MW10"
    assert not any(r["arm"] == "ppg" and r["cutoff_label"] == "MW0" for r in first)
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
    scoreable = [r for r in rows if not r.get("not_applicable")]
    assert len(scoreable) == 14, "seven rows per seed"
    assert len(rows) - len(scoreable) == 2, "one not-applicable marker per seed"

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
        realised={"2099/00": realised}, verbose=False)
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
        smoke=True, verbose=False)


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
    seen = {(row["season"], row["cutoff_label"], row["arm"]) for row in smoke}
    assert {s for s, _, _ in seen} == {"2025/26"}
    assert {c for _, c, _ in seen} == {"MW0", "MW10"}
    for arm in simretro.ARMS:
        assert ("2025/26", "MW0", arm) in seen
        assert ("2025/26", "MW10", arm) in seen
    assert ("2025/26", "MW0", "flat") in seen
    assert ("2025/26", "MW10", "ppg_pointmass") in seen, "PPG is defined by MW10"
    assert ("2025/26", "MW0", "ppg_pointmass") not in seen, "PPG is NA at the opener"

    scores = simretro.score_retro(smoke, n_boot=1_000)
    by = {(r["season"], r["cutoff_label"], r["arm"]): r for r in scores["rows"]}
    for label in ("MW0", "MW10"):
        native = by[("2025/26", label, "dc_native")]
        flat = by[("2025/26", label, "flat")]
        assert native["trps"] < flat["trps"], (
            f"dc_native must beat the flat null at {label} (plan v2 §5 STOP)")
        assert native["wtrps"] > 0 and native["mc"]["cluster"] > 0
        assert native["points"]["crps"] > 0
        assert set(native["briers"]) == set(leaguesim.MARKETS)
    assert scores["sanity"]["STOP_AND_INSPECT"] is False

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
    first = simretro.run_retro(**_v2_kwargs(tmp_path, clubs, realised, runner,
                                            ledger))
    me = simretro.producer_identity()
    assert all(row["producer"] == me for row in first)
    assert all(row["run_key"].endswith(f"|p{me[:12]}") for row in first)

    # resuming with the SAME producer is free: no runner call at all
    calls = len(runner.calls)
    again = simretro.run_retro(**_v2_kwargs(tmp_path, clubs, realised, runner,
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
            simretro.run_retro(**_v2_kwargs(tmp_path, clubs, realised, other,
                                            ledger))
        assert other.calls == [], "it refused BEFORE paying for a fit"

        # ... and the override is explicit, and marks every row it writes
        mixed = simretro.run_retro(
            **_v2_kwargs(tmp_path, clubs, realised, other, ledger),
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
    rows = simretro.run_retro(**_v2_kwargs(tmp_path, clubs, realised, runner))
    # The fake runner's matrices are random and lose to the flat null, which
    # would make the flag False for the wrong reason and leave this test unable
    # to see the completeness identity at all. dc_native's matrix is replaced
    # with a doubly stochastic one concentrated on the realised order, so the
    # ONLY thing that can move the flag below is the accounting.
    sharp = 0.6 * np.eye(len(clubs)) + 0.4 / len(clubs)
    rows = [dict(r, matrix=sharp.tolist()) if r["arm"] == "dc_native" else r
            for r in rows]

    full = simretro.score_retro(rows, n_boot=50)
    sanity = full["sanity"]
    assert sanity["violations"] == [], "the fixture must beat the flat null"
    assert sanity["n_expected"] == 2 and sanity["n_checked"] == 2
    assert sanity["complete"] is True
    assert sanity["dc_native_beats_flat_everywhere"] is True

    # drop one cutoff's flat row: one cell survives, and the flag must not
    thin = [r for r in rows
            if not (r["arm"] == "flat" and r["cutoff_label"] == "MW10")]
    partial = simretro.score_retro(
        thin, n_boot=50, expected_cells=[("2099/00", "MW0"),
                                         ("2099/00", "MW10")])
    assert partial["sanity"]["n_checked"] == 1
    assert partial["sanity"]["n_expected"] == 2
    assert partial["sanity"]["complete"] is False
    assert partial["sanity"]["dc_native_beats_flat_everywhere"] is False
    assert partial["sanity"]["STOP_AND_INSPECT"] is True
    assert partial["sanity"]["missing"][0]["documented"] is False

    # a DOCUMENTED refusal is different from a hole: it closes the accounting
    documented = dict(thin[0])
    documented.update({"arm": "flat", "cutoff_label": "MW10",
                       "not_applicable": "flat is undefined here"})
    with_reason = simretro.score_retro(
        thin + [documented], n_boot=50,
        expected_cells=[("2099/00", "MW0"), ("2099/00", "MW10")])
    assert with_reason["sanity"]["n_documented_refusals"] == 1
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
    rows = simretro.run_retro(**_v2_kwargs(tmp_path, clubs, realised, runner))
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
    rows = simretro.run_retro(**_v2_kwargs(tmp_path, clubs, realised, runner))
    scored = simretro.score_retro(rows, n_boot=50)

    native = [r for r in scored["rows"] if r["arm"] == "dc_native"]
    assert native and all(r["trps_se"] is not None and r["trps_se"] > 0
                          for r in native)
    assert all("delta method" in r["trps_se_method"] for r in native)
    # the nulls record no per-cell error, and the SE is `None` rather than 0
    assert all(r["trps_se"] is None for r in scored["rows"] if r["arm"] == "flat")

    text = simretro.report(scored)
    assert "| TRPS SE |" in text and "| mean cell SE |" in text
    assert "| max cell SE |" in text
    assert "| MC SE |" not in text, "the misnamed column is gone"
    assert "Neither is an error on TRPS" in text
    assert "conservative rather than exact" in text

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
