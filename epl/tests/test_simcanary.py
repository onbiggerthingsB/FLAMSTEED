"""Leakage, parity and coherence — the checks that say the engine is honest (T6).

What these tests are actually for
---------------------------------
`epl/tests/test_leaguesim.py` pins the engine's *internal* contracts. This file
pins the three ways the engine could still be wrong while every internal
contract holds:

1. **Leakage.** A result the cutoff cannot see must not touch a single number.
   The negative control (post-cutoff mutation -> byte-identical run) is worthless
   on its own: a canary that mutated nothing, or a builder that silently dropped
   the mutation, would sail through it. So the canary carries two positive
   controls in the same call — the *same* mutation at a later cutoff moves the
   numbers, and a *pre-cutoff* mutation at the *same* cutoff moves them too.
   Only all three together mean anything.
2. **Cutoff-semantics drift.** The simulator decides "played" from the results
   ledger; the fit decides it from `wcmodel.data.features.build`. Those are two
   independent implementations of one rule, and they are asserted equal on the
   real archive rather than assumed equal — with a mismatched-cutoff negative
   control, so a green parity is evidence and not a tautology.
3. **Coherence.** A display matrix whose columns do not sum to one is not a badly
   calibrated forecast, it is an inadmissible one. Every D10 identity is checked,
   and every check is shown to fire on a deliberately corrupted run.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_simcanary.py -q
"""

from __future__ import annotations

import copy
import dataclasses

import numpy as np
import pandas as pd
import pytest

from epl import (baseline, freeze, leaguesim, particles, paths,
                 season as season_mod, simcanary, table as table_mod)
from wcmodel.data import features as wc_features
from wcmodel.data.store import BitemporalStore, Policy

SEED = 20260611

#: Plan v2 §5's schedule resolved against this archive: MW0 is the season's
#: first weekly walk-forward cutoff, MWk the earliest weekly cutoff with >= 10k
#: of the season's fixtures behind it.
CUT_2425_MW0 = "2024-08-16"
CUT_2425_MW6 = "2024-10-19"
CUT_2425_MW10 = "2024-11-23"
CUT_2526_MW0 = "2025-08-15"


# --------------------------------------------------------------------------
# fixtures — synthetic books, real season states, no fit cost
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def matches() -> pd.DataFrame:
    return baseline.load_matches()


@pytest.fixture(scope="module")
def store() -> BitemporalStore:
    return BitemporalStore(paths.STORE_DIR)


def _book(clubs, n_particles=16, *, provisional=(), alpha=0.5, tilt=0.0):
    """A league-shaped `ParticleBook` built by hand.

    Every particle bumps a different club's attack, so the book carries real
    between-particle spread and the cluster standard errors are not degenerate.
    `tilt` shifts every attack at once and exists only to build a *different*
    book for a positive control.
    """
    clubs = tuple(clubs)
    n_teams = len(clubs)
    ladder = np.linspace(-0.20, 0.20, n_teams)
    att = np.repeat((ladder + float(tilt))[:, None], n_particles, axis=1)
    defe = np.repeat(ladder[:, None], n_particles, axis=1)
    for s in range(n_particles):
        att[s % n_teams, s] += 0.25
    return particles.ParticleBook(
        teams=clubs, idx={c: i for i, c in enumerate(clubs)},
        att=att, defe=defe,
        mu=np.zeros(n_particles), home_adv=np.full(n_particles, 0.25),
        rho=np.full(n_particles, -0.03),
        sigma_att=np.full(n_particles, 0.4), sigma_def=np.full(n_particles, 0.4),
        provisional=frozenset(provisional), cold_start=frozenset(provisional),
        likelihood="dixon_coles", alpha=alpha,
        max_goals=particles.PRODUCTION_MAX_GOALS, cfg_hash="test-cfg",
    )


@pytest.fixture(scope="module")
def builder_2425(matches):
    return simcanary.archive_state_builder(matches, "2024/25")


@pytest.fixture(scope="module")
def state_2425_mw6(builder_2425):
    return builder_2425(CUT_2425_MW6, None)


@pytest.fixture(scope="module")
def small_run(state_2425_mw6):
    clubs = state_2425_mw6.clubs
    book = _book(clubs, n_particles=16, provisional=(clubs[0], clubs[7]))
    return leaguesim.simulate("dc_native", state_2425_mw6, book, 256, SEED, 128)


@pytest.fixture(scope="module")
def parity(state_2425_mw6):
    """One run with real particle spread and a live widening branch."""
    clubs = state_2425_mw6.clubs
    provisional = (clubs[0], clubs[3])
    book = _book(clubs, n_particles=25, provisional=provisional, alpha=0.5)
    run = leaguesim.simulate("dc_native", state_2425_mw6, book, 5000, SEED, 2500)
    return book, run, set(provisional)


def _split_by_widening(book, run):
    """Unplayed fixture ids, split into those production would widen and the rest."""
    widened, plain = [], []
    for position in run.plan.unplayed_positions:
        fixture = run.plan.fixtures[position]
        target = (widened if book.is_provisional(fixture.home_key, fixture.away_key)
                  else plain)
        target.append(fixture.fixture_id)
    return widened, plain


# ==========================================================================
# 1. the leakage canary (the `walkforward.point_in_time_canary` pattern)
# ==========================================================================

def test_leakage_canary_negative_identical_positive_changed(builder_2425,
                                                            state_2425_mw6):
    book = _book(state_2425_mw6.clubs, n_particles=8)
    report = simcanary.leakage_canary(builder_2425, book, CUT_2425_MW6, SEED,
                                      n_sims=96, chunk_size=48)

    # the negative control: a result the cutoff cannot see moves NOTHING
    assert report["negative_identical"] is True
    assert report["negative_digest_identical"] is True
    assert report["max_abs_matrix_diff_negative"] == 0.0

    # positive control A — the same mutation, at a cutoff that CAN see it
    assert report["positive_changed"] is True
    assert report["max_abs_matrix_diff_positive"] > 0.0
    # positive control B — a mutation the cutoff CAN see, at the SAME cutoff
    assert report["pre_cutoff_changed"] is True
    assert report["max_abs_matrix_diff_pre_cutoff"] > 0.0

    assert report["PASS"] is True
    assert report["states_identical_at_cutoff"] is True
    assert report["target"] not in state_2425_mw6.played, "target must be invisible"
    assert report["pre_cutoff_target"] in state_2425_mw6.played
    assert report["n_mutated"] == 1


def test_leakage_canary_mutation_really_lands(builder_2425):
    """The canary PROVES its mutation exists rather than assuming it."""
    state = builder_2425(CUT_2425_MW6, None)
    report = simcanary.leakage_canary(builder_2425, _book(state.clubs, 8),
                                      CUT_2425_MW6, SEED, n_sims=96, chunk_size=48)
    target, mutation = report["target"], tuple(report["mutation"])

    assert target not in state.played
    dirty_at_cutoff = builder_2425(CUT_2425_MW6, {target: mutation})
    assert target not in dirty_at_cutoff.played, "still invisible at the cutoff"

    clean_later = builder_2425(report["later"], None)
    dirty_later = builder_2425(report["later"], {target: mutation})
    assert dirty_later.played[target] == mutation
    assert clean_later.played[target] == tuple(report["true_result"])
    assert clean_later.played[target] != mutation


class _LeakyProvider:
    """The bug the canary exists to find, made concrete.

    A results map that was never cutoff-gated is shared between the state layer
    and the engine, so a fixture the state calls UNPLAYED is nevertheless pinned
    to its real scoreline. Nothing about the run looks wrong: it completes, the
    matrix sums to one, the retained/pinned partition is intact. The only thing
    that betrays it is that the run moves when a post-cutoff result is rewritten.
    """

    name = "dc_native"

    def __init__(self, book, shared: dict):
        self.book = book
        self._shared = shared
        self._inner = leaguesim.DCNativeProvider(book)

    @property
    def n_particles(self) -> int:
        return self.book.n_particles

    def content_hash(self) -> str:
        return self.book.content_hash()

    def sample(self, fixture, particle_idx, u):
        home, away = self._inner.sample(fixture, particle_idx, u)
        leaked = self._shared.get(fixture.fixture_id)
        if leaked is None:
            return home, away
        return np.full_like(home, leaked[0]), np.full_like(away, leaked[1])


def _ungated_cache_builder(builder, shared: dict):
    """A builder that fills `shared` with the WHOLE record, cutoff ignored."""
    def build(cutoff, mutations=None):
        shared.clear()
        shared.update(builder(simcanary.FAR_FUTURE, mutations).played)
        return builder(cutoff, mutations)
    return build


def test_leakage_canary_catches_a_leaking_engine(builder_2425, state_2425_mw6):
    """The negative control is shown to FAIL — a canary that cannot fail is a bug."""
    shared: dict = {}
    provider = _LeakyProvider(_book(state_2425_mw6.clubs, n_particles=8), shared)
    report = simcanary.leakage_canary(_ungated_cache_builder(builder_2425, shared),
                                      provider, CUT_2425_MW6, SEED,
                                      n_sims=64, chunk_size=32)

    assert report["negative_identical"] is False, (
        "a post-cutoff result reached the numbers and the canary did not notice")
    assert report["negative_digest_identical"] is False
    assert report["PASS"] is False
    # the state itself is still honest: this is an ENGINE leak, not a state one,
    # and the played-set parity would not have seen it either.
    assert report["states_identical_at_cutoff"] is True
    # No assertion on the display matrix: with the whole record leaked the run
    # is deterministic, and one changed scoreline need not reorder the final
    # table. That is exactly why `_numbers_digest` covers the retained rows and
    # the reconstructed scorelines and not just the published summary.


def test_leakage_canary_refuses_a_vacuous_run(builder_2425):
    """Nothing after the cutoff to mutate -> the canary fails closed."""
    book = _book(builder_2425(CUT_2425_MW6, None).clubs, n_particles=4)
    with pytest.raises(simcanary.CanaryError):
        # every 2024/25 result is behind this cutoff, so there is no post-cutoff
        # result to mutate and the canary would be asserting nothing
        simcanary.leakage_canary(builder_2425, book, "2026-01-01", SEED,
                                 n_sims=32, chunk_size=32)


def test_leakage_canary_at_an_opener_reports_the_missing_control(builder_2425):
    """Nothing is visible at MW0, so the pre-cutoff control is absent, not faked.

    The `later` positive control still proves the mutation was real, so the
    canary is not vacuous — it just says which leg it could not run.
    """
    book = _book(builder_2425(CUT_2425_MW0, None).clubs, n_particles=4)
    report = simcanary.leakage_canary(builder_2425, book, CUT_2425_MW0, SEED,
                                      n_sims=32, chunk_size=32)
    assert report["n_played_at_cutoff"] == 0
    assert report["pre_cutoff_control_available"] is False
    assert report["pre_cutoff_changed"] is None
    assert report["negative_identical"] is True
    assert report["positive_changed"] is True
    assert report["PASS"] is True


def test_ledger_state_builder_mutates_a_live_season():
    """The live-season builder is the same contract over the results ledger."""
    live = season_mod.Season.load("2026/27")
    fixture = live.fixtures[0]
    row = {"fixture_id": fixture.fixture_id,
           "date_played": fixture.base_date.isoformat(), "hg": 2, "ag": 1,
           "source": "test", "observed_at": fixture.base_date.isoformat(),
           "note": ""}
    seeded = simcanary.ledger_state_builder(
        dataclasses.replace(live, results=(row,)))
    after = str(pd.Timestamp(fixture.base_date) + pd.Timedelta(days=1))
    assert seeded(after, None).played[fixture.fixture_id] == (2, 1)
    assert seeded(after, {fixture.fixture_id: (0, 5)}).played[fixture.fixture_id] == (0, 5)
    with pytest.raises(simcanary.CanaryError):
        seeded(after, {"2627:nobody:nobody": (1, 1)})


# ==========================================================================
# 2. played-set parity with the fit's own definition of "played"
# ==========================================================================

def test_played_as_of_day_floors_and_drops_unplayed(tmp_path):
    """The mirrored predicate: same-day out, prior-day in, unplayed dropped."""
    frame = pd.DataFrame({
        "match_id": ["a", "b", "c"],
        "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2023-12-31"]),
        "valid_as_of": pd.to_datetime(["2024-01-01", "2024-01-02", "2023-12-31"]),
        "observed_at": pd.to_datetime(["2024-01-01", "2024-01-02", "2023-12-31"]),
        "home_team": ["x", "y", "z"],
        "away_team": ["y", "z", "x"],
        "home_score": [1.0, 2.0, np.nan],
        "away_score": [0.0, 2.0, np.nan],
        "tournament": "epl", "neutral": False, "city": ["x", "y", "z"],
    })
    store = BitemporalStore(tmp_path)
    store.write("results", frame, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="test", source_version="v1")

    got = set(simcanary.played_as_of(store, "2024-01-02 23:00")["match_id"])
    assert got == {"a"}, "same-day excluded, prior-day included, unplayed dropped"
    assert set(simcanary.played_as_of(store, "2024-01-03")["match_id"]) == {"a", "b"}


@pytest.mark.slow
def test_played_set_parity_with_features_build_at_three_cutoffs(store, matches):
    """The sim's played set IS the row set the fit consumes. Real archive."""
    # built once and handed to both the MW10 assertion and the negative control
    # below; the other two cutoffs go through the function's own build path.
    panel_mw10 = wc_features.build(CUT_2425_MW10, store,
                                   freeze.frozen_wcmodel_config())
    seen = []
    for season, cutoff, panel in (("2024/25", CUT_2425_MW0, None),
                                  ("2024/25", CUT_2425_MW10, panel_mw10),
                                  ("2025/26", CUT_2526_MW0, None)):
        state = season_mod.archive_season_state(matches, season, cutoff)
        report = simcanary.played_set_parity(store, cutoff, state, matches,
                                             panel=panel)
        assert report["PASS"] is True, report
        assert report["mirror_equals_panel"] is True
        assert report["only_in_sim"] == [] and report["only_in_panel"] == []
        seen.append(report["n_played"])

    assert seen == [0, 110, 0], (
        "the cutoffs must actually differ in what is played, or the parity "
        f"above is the same assertion three times: {seen}")

    # negative control: the SAME panel against the state at an EARLIER cutoff
    # must FAIL, so a green parity is evidence and not a tautology.
    earlier = season_mod.archive_season_state(matches, "2024/25", CUT_2425_MW0)
    bad = simcanary.played_set_parity(store, CUT_2425_MW10, earlier, matches,
                                      panel=panel_mw10)
    assert bad["PASS"] is False
    assert len(bad["only_in_panel"]) == 110
    assert bad["only_in_sim"] == []


def test_played_set_parity_refuses_a_season_the_archive_lacks(store, matches):
    """A live season has no archive rows: the parity would be vacuous, so it stops."""
    live = season_mod.Season.load("2026/27").at("2026-08-21")
    with pytest.raises(simcanary.CanaryError):
        simcanary.played_set_parity(store, "2026-08-21", live, matches)


# ==========================================================================
# 3. marginal parity with what production issues (D12)
# ==========================================================================

def test_marginal_parity_incl_provisional_fixture(parity):
    book, run, provisional = parity
    widened, plain = _split_by_widening(book, run)
    assert len(widened) >= 3, "the D12 widening branch must actually be exercised"
    checked = widened[:3] + plain[:2]

    report = simcanary.marginal_parity(book, None, run, checked)
    assert report["PASS"] is True, report["failures"][:5]
    assert report["n_fixtures"] == 5
    assert report["n_provisional"] == 3
    assert report["n_cells_compared"] > 5 * 3, "scoreline cells, not just 1X2"
    assert report["max_sigma"] <= report["z_star"]

    # positive control: score the SAME run against a book with the widening
    # switched off. The widened fixtures' scoreline marginals must then
    # disagree — otherwise the mixture branch is not in the numbers at all.
    off = simcanary.marginal_parity(
        _book(run.clubs, n_particles=25, provisional=tuple(provisional), alpha=0.0),
        None, run, checked)
    assert off["PASS"] is False
    # per-cell lines only: since A3 the failure list can also carry the global
    # chi-squared leg's one-line verdict, which names no fixture.
    failed = {line.split(" | ")[0] for line in off["failures"] if " | " in line}
    assert failed == set(widened[:3]), (
        "only the widened fixtures may move when alpha is switched off")


def test_marginal_parity_detects_a_wrong_book(parity):
    """A book that is not the one that produced the run must fail the parity."""
    book, run, provisional = parity
    _widened, plain = _split_by_widening(book, run)
    other = _book(run.clubs, n_particles=25, provisional=tuple(provisional),
                  alpha=0.5, tilt=0.60)
    report = simcanary.marginal_parity(other, None, run, plain[:3])
    assert report["PASS"] is False
    assert report["max_sigma"] > 10.0


def test_marginal_parity_refuses_an_unstratified_run(parity):
    """N not a multiple of S -> the estimator is biased, so it refuses to run."""
    book, run, _provisional = parity
    broken = copy.copy(run)
    broken.plan = _plan_with(run.plan, n_particles=7)
    with pytest.raises(simcanary.CanaryError):
        simcanary.marginal_parity(book, None, broken, [])


def test_marginal_parity_refuses_a_played_fixture(parity):
    book, run, _provisional = parity
    played = next(f.fixture_id for f in run.plan.fixtures if f.result is not None)
    with pytest.raises(simcanary.CanaryError):
        simcanary.marginal_parity(book, None, run, [played])


def _plan_with(plan, **overrides):
    fields = dict(
        season=plan.season, season_code=plan.season_code, cutoff=plan.cutoff,
        observed_by=plan.observed_by, clubs=plan.clubs, fixtures=plan.fixtures,
        adjustments=plan.adjustments, boundaries=plan.boundaries,
        rule_id=plan.rule_id, n_sims=plan.n_sims, n_particles=plan.n_particles,
        seed=plan.seed, chunk_size=plan.chunk_size,
        n_unresolved=plan.n_unresolved, results_lag=plan.results_lag)
    fields.update(overrides)
    return leaguesim.SimPlan(**fields)


# ==========================================================================
# 4. coherence (D10)
# ==========================================================================

def test_coherence_identities(small_run):
    report = simcanary.coherence(small_run)
    assert report["PASS"] is True, report["failures"]
    assert report["failures"] == []
    for key in ("matrix_rows_ok", "matrix_cols_ok", "markets_ok", "identities_ok",
                "pinned_ok", "double_round_robin_ok", "mass_ok",
                "retained_totals_ok"):
        assert report[key] is True, key
    assert report["market_totals"] == pytest.approx(
        {"champion": 1.0, "top4": 4.0, "top5": 5.0, "top7": 7.0, "relegated": 3.0},
        abs=1e-9)


@pytest.mark.parametrize("break_it,expect", [
    ("row", "matrix_rows_ok"),
    ("column", "matrix_cols_ok"),
    ("market", "markets_ok"),
    ("retained_points", "retained_totals_ok"),
    ("retained_gd", "identities_ok"),
    ("pinned", "pinned_ok"),
    ("mass", "mass_ok"),
])
def test_coherence_fires_on_every_corruption(small_run, break_it, expect):
    """Each guard is shown to fail — a check that cannot fail is not a check."""
    run = copy.copy(small_run)
    run.retained_rows = copy.copy(small_run.retained_rows)

    if break_it == "row":
        run.matrix = small_run.matrix.copy()
        run.matrix[0, 0] += 0.01
        run.matrix[0, 1] -= 0.02              # the row no longer sums to 1
    elif break_it == "column":
        run.matrix = small_run.matrix.copy()
        run.matrix[0, 0] += 0.01
        run.matrix[0, 1] -= 0.01              # row still 1, columns are not
    elif break_it == "market":
        run.consequences = copy.deepcopy(small_run.consequences)
        run.consequences[small_run.clubs[0]]["top4"]["p"] += 0.05
    elif break_it == "retained_points":
        run.retained_rows.points = (small_run.retained_rows.points + 1).astype(np.int16)
    elif break_it == "retained_gd":
        gd = small_run.retained_rows.gd.copy()
        gd[:, 0] += 1                          # sum over clubs is no longer zero
        run.retained_rows.gd = gd
    elif break_it == "pinned":
        pinned = next(f.ordinal for f in small_run.plan.fixtures
                      if f.result is not None)
        ordinals = small_run.retained_rows.fixture_ordinals.copy()
        ordinals[0] = pinned                   # a played fixture was "simulated"
        run.retained_rows.fixture_ordinals = ordinals
    elif break_it == "mass":
        run.shared_mass = small_run.shared_mass + 0.5

    report = simcanary.coherence(run)
    assert report["PASS"] is False
    assert report[expect] is False, report["failures"]
    assert report["failures"], "a failure must be named, not just flagged"


@pytest.mark.parametrize("field,value", [
    ("se", -0.5), ("se", float("nan")), ("se", None),
    ("mean", float("inf")), ("mean", None),
])
def test_coherence_checks_the_expected_points_headline(small_run, field, value):
    """E[points] carries a `+/-` in the summary, so its SE is checked here.

    `points_summary` is printed beside every club at the top of the issuance
    report as `mean +/- se`, and it was the one published standard error
    coherence never looked at: a NEGATIVE E[points] SE reached the headline
    while this check reported PASS. The separate guard in `epl.simcli` rejects
    only missing or non-finite values, so a negative one passed both.
    """
    # POSITIVE CONTROL: untouched, the real run's points summary is coherent.
    assert simcanary.coherence(small_run)["PASS"] is True

    run = copy.copy(small_run)
    run.points_summary = copy.deepcopy(small_run.points_summary)
    club = small_run.clubs[0]
    assert np.isfinite(run.points_summary[club]["se"]) >= 0
    run.points_summary[club][field] = value

    report = simcanary.coherence(run)
    assert report["PASS"] is False
    assert report["standard_errors_ok"] is False
    assert any("E[points]" in line and club in line
               for line in report["failures"]), report["failures"]


def test_coherence_identity_leg_is_the_tables_own_checker(small_run):
    """The identity leg reuses `epl.table.check_identities`, not a second copy."""
    plan = small_run.plan
    totals = table_mod.accumulate(small_run.full_scorelines(), plan.home_idx,
                                  plan.away_idx, n_clubs=len(plan.clubs),
                                  adjustments=plan.adjustments)
    table_mod.check_identities(totals)             # the run really is coherent
    assert np.array_equal(totals.pts, small_run.retained_rows.points)


# ==========================================================================
# 5. the runnable acceptance surface
# ==========================================================================

def test_check_run_bundles_coherence_and_parity(parity):
    book, run, provisional = parity
    widened, _plain = _split_by_widening(book, run)
    report = simcanary.check_run(run, book=book, post=None, fixtures=widened[:2])
    assert set(report) == {"coherence", "marginal_parity", "PASS"}
    assert report["PASS"] is True

    assert simcanary.check_run(run)["marginal_parity"] is None


def test_acceptance_cutoffs_are_the_planned_two():
    assert simcanary.ACCEPTANCE_CUTOFFS == {
        "2024/25 MW10": ("2024/25", CUT_2425_MW10),
        "2025/26 MW0": ("2025/26", CUT_2526_MW0),
    }


def test_run_acceptance_without_the_panel(matches):
    """The whole acceptance set, minus the 45s-a-cutoff feature panel.

    MARGINAL PARITY IS IN THE SET. It was not, and a report headed "acceptance"
    that omits the one criterion saying the sampled law IS the published one
    reads as a full gate while being three quarters of one. The check set is
    pinned here by name so removing a criterion is a test failure rather than a
    quieter report.
    """
    report = simcanary.run_acceptance(matches=matches, n_sims=64,
                                      skip_panel=True)
    assert report["PASS"] is True
    for label, entry in report["checks"].items():
        assert set(entry) == {"leakage", "coherence", "marginal_parity",
                              "played_set_parity", "PASS"}, label
        assert entry["leakage"]["PASS"] is True, label
        assert entry["coherence"]["PASS"] is True, label
        assert entry["coherence"]["standard_errors_ok"] is True, label
        assert entry["marginal_parity"]["PASS"] is True, (
            label, entry["marginal_parity"]["failures"][:5])
        assert entry["marginal_parity"]["n_cells_compared"] > 0
        assert entry["played_set_parity"] is None


def test_run_acceptance_propagates_a_FAILING_parity(matches, monkeypatch):
    """The NEGATIVE control the set had none of: a failing leg must reach PASS.

    `test_run_acceptance_without_the_panel` supplies only passing checks, so
    deleting the marginal-parity conjunct from `run_acceptance`'s verdict left
    it green — the criterion was in the report and out of the arithmetic, which
    is precisely the shape the fix was supposed to close. Here parity is forced
    to fail and the verdict has to follow it, per entry and overall.
    """
    real = simcanary.marginal_parity
    calls = []

    def failing(*args, **kwargs):
        report = dict(real(*args, **kwargs))
        calls.append(report["PASS"])
        report["PASS"] = False
        report["failures"] = ["forced failure (negative control)"]
        return report

    monkeypatch.setattr(simcanary, "marginal_parity", failing)
    report = simcanary.run_acceptance(matches=matches, n_sims=64, skip_panel=True)

    assert calls and all(calls), (
        "the real parity passed on every cutoff, so the False below is the "
        "forced one and not a genuinely failing sampler")
    assert report["PASS"] is False
    for label, entry in report["checks"].items():
        assert entry["marginal_parity"]["PASS"] is False, label
        assert entry["leakage"]["PASS"] is True, label
        assert entry["coherence"]["PASS"] is True, label
        assert entry["PASS"] is False, (
            f"{label}: every other leg passed, so this entry's verdict is "
            "reading marginal parity or it is reading nothing")


# ==========================================================================
# round 2 — criterion 3 under amendment A3, and the coherence gaps
# ==========================================================================

def test_marginal_parity_threshold_is_family_wise_in_m(parity):
    """The per-cell threshold moves with the size of the family, and is printed.

    A fixed 4.0 sigma applied to m cells at once is not a 4-sigma rule: at the
    14,225 cells of a real issuance the two-sided normal tail at 4 sigma is
    6.334e-05, so a CORRECT sampler produces 0.90 expected exceedances and fails
    about three runs in five. A3 replaces it with
    `z* = Phi^-1(1 - alpha/(2m))`, alpha = 0.01.
    """
    from scipy.stats import norm

    book, run, _provisional = parity
    _widened, plain = _split_by_widening(book, run)

    small = simcanary.marginal_parity(book, None, run, plain[:2])
    large = simcanary.marginal_parity(book, None, run, plain[:20])

    for report in (small, large):
        m = report["n_cells_compared"]
        assert report["alpha"] == pytest.approx(0.01)
        assert report["z_star"] == pytest.approx(
            float(norm.isf(0.01 / (2 * m))), rel=1e-12)
        assert report["df"] == m
        # all six numbers the amendment requires, on a PASSING run too
        for key in ("n_cells_compared", "z_star", "max_sigma", "chi2", "df",
                    "p_value"):
            assert key in report and np.isfinite(report[key]), key
        assert report["PASS"] is True, report["failures"][:5]

    # the threshold really does move with m, and in the conservative direction
    assert large["n_cells_compared"] > small["n_cells_compared"]
    assert large["z_star"] > small["z_star"] > 3.0

    # the retired constant is gone from the report and from the module
    assert "n_sigma" not in small
    assert not hasattr(simcanary, "DEFAULT_N_SIGMA")

    # and the pre-stated number: at m = 14,225, z* = 4.9605
    assert float(norm.isf(0.01 / (2 * 14225))) == pytest.approx(4.9605, abs=5e-5)


def test_marginal_parity_leg2_is_reported_and_gates_nothing(parity):
    """A3-N1 (2026-08-20): leg 2 is a diagnostic, and it is still PRINTED.

    A book tilted slightly against the one that produced the run moves every
    cell a little and no cell past `z*`, so leg 1 sees nothing while the omnibus
    over the same deviations lands at p ~ 1e-25. The omnibus was a PASS/FAIL leg
    and is no longer one: `sum(Z^2)` is not chi2_m — the cells are dependent
    (multinomial within a fixture, one particle set across fixtures) and each Z
    divides by an estimated, floored SE — so `p <= 1e-3` was a threshold on an
    uncalibrated distribution. A3 asserted the direction of that miscalibration
    without computing it.

    What this test now pins is the demotion done properly: the statistic is
    still computed, still reported, still moves with the tilt, and the run's
    verdict does not depend on it. The old shape asserted `PASS is False` here,
    which was the gate failing a run on a number nobody has calibrated.
    """
    book, run, provisional = parity
    _widened, plain = _split_by_widening(book, run)
    checked = plain[:40]

    honest = simcanary.marginal_parity(book, None, run, checked)
    assert honest["PASS"] is True
    assert honest["leg2_chi2_above_reference"] is True

    # tilt = 0.04 lifts every rate by 4%: at m ~ 950 that is max |Z| ~ 3.6
    # against z* ~ 4.41 — comfortably inside leg 1 — and chi2 ~ 1488 on
    # df ~ 964, p ~ 4e-25. The old fixed 4-sigma rule would have missed it too.
    tilted = simcanary.marginal_parity(
        _book(run.clubs, n_particles=25, provisional=tuple(provisional),
              alpha=0.5, tilt=0.04),
        None, run, checked)
    assert tilted["leg1_per_cell_PASS"] is True, (
        "the tilt must be small enough that no single cell trips z*: "
        f"max |Z| = {tilted['max_sigma']:.2f} vs z* = {tilted['z_star']:.2f}")
    assert tilted["max_sigma"] < 4.0, (
        "and small enough that the RETIRED 4-sigma rule would have missed it: "
        f"max |Z| = {tilted['max_sigma']:.2f}")

    # THE DEMOTION: the diagnostic sees it, the verdict does not read it, and
    # nothing about it reaches `failures` (which is what the gate reads).
    assert tilted["leg2_chi2_above_reference"] is False
    assert tilted["chi2"] > honest["chi2"]
    assert tilted["PASS"] is True, "leg 2 must not fail a run (A3-N1)"
    assert tilted["failures"] == []
    assert tilted["leg2_global_PASS"] is None, (
        "the old boolean is kept as None so a reader finds the demotion, not "
        "a missing field")

    # ...and it is REPORTED, not silently dropped: every number the amendment
    # requires is present on both runs, and the note says what it is.
    for report in (honest, tilted):
        for key in ("chi2", "df", "p_value", "chi2_min_p"):
            assert np.isfinite(report[key]), key
        assert "UNCALIBRATED DIAGNOSTIC" in report["leg2_note"]
        assert f"{report['chi2']:.1f}" in report["leg2_note"]


def test_marginal_parity_refuses_a_threshold_outside_its_own_range(parity):
    """`alpha` and `chi2_min_p` are validated: the gate must not fail OPEN.

    With `alpha <= 0`, `z* = Phi^-1(1 - alpha/(2m))` is `inf` or NaN, every
    `|Z| > z*` is False, and leg 1 — the one criterion saying the sampled law IS
    the published one — passes whatever the sampler did. It is reachable by a
    single mistyped keyword, which is why it is refused rather than documented.
    """
    book, run, provisional = parity
    _widened, plain = _split_by_widening(book, run)
    checked = plain[:20]

    # POSITIVE CONTROL: the defaults, and legitimate non-default values, work.
    assert simcanary.marginal_parity(book, None, run, checked)["PASS"] is True
    assert simcanary.marginal_parity(book, None, run, checked, alpha=0.05,
                                     chi2_min_p=0.0)["PASS"] is True

    for bad in (-1.0, 0.0, 1.0, 2.0, float("nan")):
        with pytest.raises(simcanary.CanaryError, match="alpha"):
            simcanary.marginal_parity(book, None, run, checked, alpha=bad)
    for bad in (-1.0, 1.0, 2.0, float("nan")):
        with pytest.raises(simcanary.CanaryError, match="chi2_min_p"):
            simcanary.marginal_parity(book, None, run, checked, chi2_min_p=bad)

    # THE FAIL-OPEN ITSELF, demonstrated on the arithmetic the guard protects:
    # a tilted sampler that leg 1 rightly catches at the real z* is passed by
    # every cell once alpha goes non-positive.
    hot = _book(run.clubs, n_particles=25, provisional=tuple(provisional),
                alpha=0.5, tilt=0.25)
    caught = simcanary.marginal_parity(hot, None, run, checked)
    assert caught["PASS"] is False and caught["failures"]
    from scipy.stats import norm as _norm
    assert not np.isfinite(float(_norm.isf(-1.0 / (2 * caught["df"])))), (
        "z* at alpha = -1 is not a number, so no |Z| can exceed it")


def test_marginal_parity_refuses_an_empty_fixture_set(parity):
    """An empty comparison is not a passing comparison."""
    book, run, _provisional = parity
    with pytest.raises(simcanary.CanaryError, match="no fixtures"):
        simcanary.marginal_parity(book, None, run, [])

    # POSITIVE CONTROL: one fixture is enough to run
    _widened, plain = _split_by_widening(book, run)
    assert simcanary.marginal_parity(book, None, run, plain[:1])["PASS"] is True


def test_coherence_fires_on_a_missing_or_negative_standard_error(small_run):
    """Every published SE must be present, finite and non-negative.

    This project's rule is a Monte-Carlo error beside every headline number. A
    run whose `matrix_se` is absent, or whose consequence-market SE is NaN,
    publishes headline numbers with nothing beside them — and the matrix can be
    perfectly doubly stochastic while that is true, which is why coherence is
    where it has to be caught.
    """
    base = simcanary.coherence(small_run)
    assert base["standard_errors_ok"] is True and base["PASS"] is True

    for label in ("missing_matrix_se", "nan_matrix_se", "negative_matrix_se",
                  "nan_mc", "negative_market_se"):
        run = copy.copy(small_run)
        if label == "missing_matrix_se":
            run.matrix_se = None
        elif label == "nan_matrix_se":
            run.matrix_se = small_run.matrix_se.copy()
            run.matrix_se[0, 0] = np.nan
        elif label == "negative_matrix_se":
            run.matrix_se = small_run.matrix_se.copy()
            run.matrix_se[3, 2] = -1e-9
        elif label == "nan_mc":
            run.mc = dict(small_run.mc, cluster_se_max=float("nan"))
        else:
            run.consequences = copy.deepcopy(small_run.consequences)
            run.consequences[small_run.clubs[0]]["champion"]["se"] = -0.01

        report = simcanary.coherence(run)
        assert report["standard_errors_ok"] is False, label
        assert report["PASS"] is False, label
        assert report["failures"], label


def test_coherence_fires_on_a_negative_mass_component(small_run):
    """Per component, not just on the sum.

    The three allocated-mass components are published separately, and checking
    only their sum lets one go negative behind another going positive: two bugs
    reported as none.
    """
    run = copy.copy(small_run)
    run.shared_mass = small_run.shared_mass - 0.05
    run.unresolved_playoff_mass = small_run.unresolved_playoff_mass + 0.05

    # the SUM is exactly what it was, so the old check saw nothing
    old_sum = (small_run.shared_mass + small_run.unresolved_playoff_mass
               + small_run.unresolved_multiway_mass)
    new_sum = (run.shared_mass + run.unresolved_playoff_mass
               + run.unresolved_multiway_mass)
    assert np.allclose(old_sum, new_sum)

    report = simcanary.coherence(run)
    assert report["mass_ok"] is False
    assert report["PASS"] is False
    assert any("shared_mass" in line and "negative" in line
               for line in report["failures"])
