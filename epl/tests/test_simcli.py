"""T9 — the CLI, the issuance it writes, and the acceptance gate.

Every check in :mod:`epl.simcli` is a guard, and a guard that cannot fail is a
bug. So each test here pairs the passing case with the input that must break it:
a season missing a fixture, a promoted club absent from the matrix, a corrupted
`table_so_far`, a headline with no standard error, a limitations note with a
section deleted, a re-run at a different seed. The forecast path itself is
exercised on a synthetic particle book so the test costs seconds rather than a
fit — what is under test is the CLI's plumbing and its gate, not the model.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import bridge as bridge_mod, leaguesim, liveanchor, matchboard
from epl import particles, season as season_mod, simcli
# The T6 acceptance run's league-shaped book: one definition, reused, so the
# smoke path here and the canary path there cannot drift apart.
from epl.simcanary import _synthetic_book as synthetic_book

SEASON = "2026/27"
OPENER = "2026-08-21"
SEED = 20260611
N_SIMS = 64
N_PARTICLES = 16
CHUNK = 32

#: Gate options that keep the unit tests to seconds: the tiebreak oracle shells
#: out to pytest and the repo checks shell out to git and the lock chain. Both
#: are exercised for real in the issuance run, and both are asserted here to
#: come back SKIPPED rather than silently PASS.
FAST_GATE = {"tiebreak_oracle": False, "repo": False, "repro_n_sims": N_SIMS}

#: A fixed ingest clock. `ingest_results` defaults `observed_at` to
#: `pd.Timestamp.now()`, which makes the ledger bytes a function of when the
#: test ran; every call below passes this instead.
INGEST_CLOCK = "2026-08-22T09:00:00"


# ==========================================================================
# fixtures
# ==========================================================================
@pytest.fixture(scope="module")
def season_obj() -> season_mod.Season:
    return season_mod.Season.load(SEASON)


@pytest.fixture(scope="module")
def state(season_obj) -> season_mod.SeasonState:
    return season_obj.at(OPENER)


@pytest.fixture(scope="module")
def book(state) -> particles.ParticleBook:
    return synthetic_book(state.clubs, n_particles=N_PARTICLES)


@pytest.fixture(scope="module")
def issuance(tmp_path_factory, book) -> dict:
    """One synthetic-book issuance, reused by the tests that read artifacts."""
    return simcli.forecast(
        season=SEASON, cutoff=OPENER, arms=("dc_native",), n_sims=N_SIMS,
        seed=SEED, chunk_size=CHUNK, n_particles=N_PARTICLES,
        out_root=tmp_path_factory.mktemp("issuances"),
        fit=simcli.FitBundle(post=None, book=book, info={"synthetic": True}),
        gate_kwargs=FAST_GATE, verbose=False)


# ==========================================================================
# 1. the forecast writes the whole issuance   (plan v2 T9)
# ==========================================================================
def test_cli_forecast_smoke_on_synthetic_book_writes_all_artifacts(issuance):
    directory = Path(issuance["directory"])
    for name in ("output_dc_native.json", "rows_dc_native.npz", "envelope.json",
                 "limitations.md", "particles.npz", "summary.md",
                 "acceptance.json"):
        assert (directory / name).exists(), f"{name} was not written"

    payload = json.loads((directory / "output_dc_native.json").read_text())
    assert payload["season"] == SEASON
    assert payload["cutoff"].startswith(OPENER)
    assert len(payload["clubs"]) == 20

    matrix = np.array([payload["matrix"][club] for club in payload["clubs"]])
    assert matrix.shape == (20, 20)
    np.testing.assert_allclose(matrix.sum(axis=1), 1.0, atol=1e-8)
    np.testing.assert_allclose(matrix.sum(axis=0), 1.0, atol=1e-8)

    # the envelope beside it is the PUBLISHED arm's, not some other arm's
    envelope = json.loads((directory / "envelope.json").read_text())
    assert envelope["arm"] == simcli.PUBLISHED_ARM
    assert envelope["season"] == SEASON

    # the book that priced it is persisted, and it is the same book
    reloaded = particles.ParticleBook.load(directory / "particles.npz")
    assert reloaded.content_hash() == issuance["runs"]["dc_native"].envelope[
        "effective_posterior_hash"]

    # the gate is recorded in full, every criterion named
    gate = json.loads((directory / "acceptance.json").read_text())
    assert set(gate["criteria"]) == set(simcli.GATE_CRITERIA)
    assert gate["criteria"]["tiebreak_oracle"]["status"] == "SKIPPED"
    assert gate["criteria"]["src_scripts_untouched"]["status"] == "SKIPPED"
    for name in ("clubs_and_fixtures", "promoted_complete", "marginal_parity",
                 "cutoff_table", "matrix_and_thresholds", "serial_equals_chunked",
                 "mc_uncertainty", "limitations"):
        assert gate["criteria"][name]["PASS"] is True, (name, gate["criteria"][name])
    assert gate["schema_version"] == simcli.GATE_SCHEMA_VERSION

    # the summary a human reads names the arm, the cutoff and the gate verdict
    summary = (directory / "summary.md").read_text()
    assert SEASON in summary and OPENER in summary
    assert "dc_native" in summary


def test_forecast_refuses_an_unknown_arm(book, tmp_path):
    with pytest.raises(simcli.CliError):
        simcli.forecast(season=SEASON, cutoff=OPENER, arms=("dc_native", "wat"),
                        n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
                        n_particles=N_PARTICLES, out_root=tmp_path,
                        fit=simcli.FitBundle(post=None, book=book),
                        gate=False, verbose=False)


def test_forecast_refuses_a_bridge_arm_without_the_archive(book, tmp_path):
    """The bridge is fitted on pre-cutoff history; with none, STOP, never guess."""
    with pytest.raises(simcli.CliError):
        simcli.forecast(season=SEASON, cutoff=OPENER, arms=("dc_wdl_bridge",),
                        n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
                        n_particles=N_PARTICLES, out_root=tmp_path,
                        fit=simcli.FitBundle(post=None, book=book),
                        matches=None, gate=False, verbose=False)


# ==========================================================================
# 2. the ledger refuses to be dirtied   (plan v2 D4, T9)
# ==========================================================================
def _openfootball_line(home: str, away: str, hg: int, ag: int) -> str:
    return ("▪ Matchday 1\n"
            "  Fri Aug 21 2026\n"
            f"    20:00  {home}  {hg}-{ag}  {away}\n")


def test_cli_refuses_dirty_ledger_conflict(tmp_path):
    root = tmp_path / "season"
    shutil.copytree(season_mod.SEASON_ROOT, root)
    ledger = root / "2026_27" / "results_ledger.jsonl"
    ledger.write_text(json.dumps({
        "fixture_id": "2627:arsenal:coventry", "date_played": "2026-08-21",
        "hg": 2, "ag": 1, "source": "manual",
        "observed_at": "2026-08-21T23:00:00", "note": "operator entry"}) + "\n")
    before = ledger.read_text()

    conflict = tmp_path / "conflict.txt"
    conflict.write_text(_openfootball_line("Arsenal FC", "Coventry City FC", 1, 1))

    with pytest.raises(season_mod.ResultConflict):
        simcli.ingest_results(season=SEASON, root=root,
                              openfootball_file=conflict, write=True)
    assert ledger.read_text() == before, "a refused ingest wrote to the ledger"

    code = simcli.main(["ingest-results", "--season", SEASON, "--root", str(root),
                        "--openfootball-file", str(conflict), "--write"])
    assert code != 0
    assert ledger.read_text() == before

    # POSITIVE CONTROL 1 — the same file with the ledger's own scoreline is fine
    agrees = tmp_path / "agrees.txt"
    agrees.write_text(_openfootball_line("Arsenal FC", "Coventry City FC", 2, 1))
    assert simcli.main(["ingest-results", "--season", SEASON, "--root", str(root),
                        "--openfootball-file", str(agrees), "--write",
                        "--observed-at", INGEST_CLOCK]) == 0
    assert ledger.read_text() == before, "an agreeing row was appended twice"

    # POSITIVE CONTROL 2 — a NEW fixture is accepted and written, so the refusal
    # above is specific to the contradiction and not a blanket refusal to ingest.
    #
    # `--observed-at` is passed on every call above and below. Without it the
    # ingest stamps the row with `pd.Timestamp.now()`, so the bytes this test
    # writes depend on the wall clock: the row is different on every run, the
    # `observed_at` nobody asserted was whatever the machine believed the time
    # was, and a test of an append-only point-in-time ledger cannot say what the
    # point in time was. With the clock controlled, the stamp is an assertion.
    fresh = tmp_path / "fresh.txt"
    fresh.write_text(_openfootball_line("Hull City AFC", "Manchester United FC", 0, 3))
    assert simcli.main(["ingest-results", "--season", SEASON, "--root", str(root),
                        "--openfootball-file", str(fresh), "--write",
                        "--observed-at", INGEST_CLOCK]) == 0
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line]
    assert len(rows) == 2
    assert rows[1]["fixture_id"] == "2627:hull:man_united"
    assert rows[1]["hg"] == 0 and rows[1]["ag"] == 3
    assert rows[1]["source"].startswith("openfootball@")
    assert rows[1]["observed_at"] == pd.Timestamp(INGEST_CLOCK).isoformat(), (
        "the row carries the clock it was given, not the machine's")

    # ... and the whole appended line is byte-reproducible, which is what a
    # controlled clock buys: a second identical ingest into a fresh ledger
    # writes the same bytes.
    again = tmp_path / "season2"
    shutil.copytree(season_mod.SEASON_ROOT, again)
    (again / "2026_27" / "results_ledger.jsonl").write_text(before)
    assert simcli.main(["ingest-results", "--season", SEASON, "--root", str(again),
                        "--openfootball-file", str(fresh), "--write",
                        "--observed-at", INGEST_CLOCK]) == 0
    assert (again / "2026_27" / "results_ledger.jsonl").read_text() == \
        ledger.read_text()


def test_ingest_manual_rows_validate_and_append(tmp_path):
    root = tmp_path / "season"
    shutil.copytree(season_mod.SEASON_ROOT, root)
    ledger = root / "2026_27" / "results_ledger.jsonl"

    good = tmp_path / "manual.jsonl"
    good.write_text(json.dumps({
        "fixture_id": "2627:arsenal:coventry", "date_played": "2026-08-21",
        "hg": 3, "ag": 0}) + "\n")
    new = simcli.ingest_results(season=SEASON, root=root, manual_file=good,
                                write=True, observed_at="2026-08-22T09:00:00")
    assert len(new) == 1 and new[0]["source"] == "manual"
    assert len(ledger.read_text().splitlines()) == 1

    # POSITIVE CONTROL — a row for a fixture that does not exist is refused,
    # and nothing is written
    before = ledger.read_text()
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({
        "fixture_id": "2627:arsenal:atlantis", "date_played": "2026-08-21",
        "hg": 1, "ag": 0}) + "\n")
    with pytest.raises(season_mod.SeasonError):
        simcli.ingest_results(season=SEASON, root=root, manual_file=bad, write=True)
    assert ledger.read_text() == before


def test_manual_ingest_refuses_a_bad_stamp_at_WRITE_time(tmp_path):
    """A malformed `observed_at` is refused before a byte reaches the ledger.

    `_timestamp` maps `None`, `""`, `nan` and the string `"NaT"` to `NaT`
    instead of raising, and the row-level override was not parsed at all — it
    was `str(...)`-ed straight into the file. So a poison stamp was COMMITTED to
    an append-only ledger and only refused the next time something read it, at
    which point every snapshot fails closed on a row whose whole point is that
    it is never edited. `NaT` compares False against every bound, so such a row
    is visible at every cutoff: the leak the stamp exists to prevent, written
    down and kept.

    Both levels: the run-wide `--observed-at`, and a row's own override.
    """
    root = tmp_path / "season"
    shutil.copytree(season_mod.SEASON_ROOT, root)
    ledger = root / "2026_27" / "results_ledger.jsonl"
    before = ledger.read_text()

    def manual(name: str, **over) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps({
            "fixture_id": "2627:arsenal:coventry", "date_played": "2026-08-21",
            "hg": 3, "ag": 0, **over}) + "\n")
        return path

    # POSITIVE CONTROL: the well-formed row, with a row-level override, writes.
    rows = simcli.ingest_results(
        season=SEASON, root=root, write=True, observed_at="2026-08-22T09:00:00",
        manual_file=manual("ok.jsonl", observed_at="2026-08-23T10:00:00"))
    assert rows[0]["observed_at"] == "2026-08-23T10:00:00"
    written = ledger.read_text()
    assert len(written.splitlines()) == len(before.splitlines()) + 1

    # (a) the run-wide clock
    for bad in ("", "not a timestamp", "NaT", float("nan")):
        with pytest.raises(season_mod.SeasonError, match="observed_at"):
            simcli.ingest_results(season=SEASON, root=root, write=True,
                                  observed_at=bad,
                                  manual_file=manual("a.jsonl"))
        assert ledger.read_text() == written, "a refused ingest wrote anyway"

    # (b) the row's own override, which was never parsed at all
    for bad in ("NaT", "not a timestamp", ""):
        with pytest.raises(season_mod.SeasonError):
            simcli.ingest_results(
                season=SEASON, root=root, write=True,
                observed_at="2026-08-22T09:00:00",
                manual_file=manual("b.jsonl", fixture_id="2627:chelsea:arsenal",
                                   observed_at=bad))
        assert ledger.read_text() == written

    # (c) and `date_played`, the mirror image: `NaT >= cutoff_day` is False too
    for bad in ("NaT", "not a timestamp"):
        with pytest.raises(season_mod.SeasonError):
            simcli.ingest_results(
                season=SEASON, root=root, write=True,
                observed_at="2026-08-22T09:00:00",
                manual_file=manual("c.jsonl", fixture_id="2627:chelsea:arsenal",
                                   date_played=bad))
        assert ledger.read_text() == written


# ==========================================================================
# 3. the limitations note carries this run's own numbers   (plan v2 T9)
# ==========================================================================
def test_limitations_lists_unresolved_masses(issuance):
    run = issuance["runs"]["dc_native"]
    text = (Path(issuance["directory"]) / "limitations.md").read_text()

    playoff = float(run.unresolved_playoff_mass.sum() / len(run.clubs))
    multiway = float(run.unresolved_multiway_mass.sum() / len(run.clubs))
    assert f"{playoff:.5f}" in text
    assert f"{multiway:.5f}" in text
    assert "results lag" in text.lower()
    assert "table positions" in text
    assert "Monte-Carlo" in text

    # POSITIVE CONTROL — a run whose unresolved mass differs writes different
    # digits, so the two numbers above are read from the run and not printed
    # from a template.
    moved = dataclasses.replace(
        run,
        unresolved_playoff_mass=run.unresolved_playoff_mass + 0.0125,
        unresolved_multiway_mass=run.unresolved_multiway_mass + 0.0037)
    other = leaguesim.limitations_markdown(moved)
    assert other != text
    moved_playoff = float(moved.unresolved_playoff_mass.sum() / len(moved.clubs))
    moved_multiway = float(moved.unresolved_multiway_mass.sum() / len(moved.clubs))
    assert moved_playoff != playoff and moved_multiway != multiway
    assert f"{moved_playoff:.5f}" in other
    assert f"{moved_multiway:.5f}" in other


def test_check_limitations_fails_when_a_required_section_is_missing(issuance):
    text = (Path(issuance["directory"]) / "limitations.md").read_text()
    run = issuance["runs"]["dc_native"]
    assert simcli.check_limitations(text, run)["PASS"] is True

    for heading in simcli.LIMITATIONS_SECTIONS:
        stripped = text.replace(heading, "")
        assert simcli.check_limitations(stripped, run)["PASS"] is False, heading


# ==========================================================================
# 4. the gate criteria, each with the input that must break it
# ==========================================================================
def test_check_clubs_and_fixtures_passes_and_fails_when_a_fixture_is_missing(
        state, season_obj):
    ok = simcli.check_clubs_and_fixtures(state, season_obj.manifest)
    assert ok["PASS"] is True
    assert ok["detail"]["n_clubs"] == 20
    assert ok["detail"]["n_fixtures"] == 380

    # POSITIVE CONTROL — drop one fixture and the check must notice
    fewer = dataclasses.replace(
        state,
        fixtures={k: v for k, v in list(state.fixtures.items())[1:]},
        unplayed=tuple(sorted(state.fixtures))[1:])
    assert simcli.check_clubs_and_fixtures(fewer, season_obj.manifest)["PASS"] is False

    # POSITIVE CONTROL — a club missing from the manifest set
    short = dataclasses.replace(state, clubs=state.clubs[:-1])
    assert simcli.check_clubs_and_fixtures(short, season_obj.manifest)["PASS"] is False


def test_check_promoted_complete_fails_when_a_promoted_club_is_absent(
        issuance, season_obj):
    run = issuance["runs"]["dc_native"]
    ok = simcli.check_promoted_complete(run, season_obj.manifest)
    assert ok["PASS"] is True
    assert set(ok["detail"]["promoted"]) == set(season_obj.manifest.promoted)
    for club in season_obj.manifest.promoted:
        assert ok["detail"]["fixtures_per_club"][club] == 38

    # POSITIVE CONTROL — a manifest naming a club the run never simulated
    invented = dataclasses.replace(season_obj.manifest,
                                   promoted=("coventry", "atlantis_fc"))
    assert simcli.check_promoted_complete(run, invented)["PASS"] is False


def test_check_cutoff_table_detects_a_corrupted_table_so_far(state):
    ok = simcli.check_cutoff_table(state)
    assert ok["PASS"] is True
    assert ok["detail"]["n_played"] == 0
    assert ok["detail"]["non_degenerate"] is False   # an opener has no results

    # POSITIVE CONTROL — award a club points it never played for
    club = state.clubs[0]
    corrupted = dataclasses.replace(
        state,
        table_so_far={**state.table_so_far,
                      club: season_mod.TableRow(played=1, w=1, gf=3, ga=0)})
    broken = simcli.check_cutoff_table(corrupted)
    assert broken["PASS"] is False
    assert club in broken["detail"]["mismatched"]


def test_check_cutoff_table_is_non_degenerate_on_a_played_season():
    """The opener has nothing to reconstruct; a mid-season state does."""
    pytest.importorskip("pyarrow")
    from epl import baseline

    matches = baseline.load_matches()
    played = matches.loc[matches["played"]]
    if not (played["season"] == "2025/26").any():
        pytest.skip("no 2025/26 rows in the archive")
    witness = season_mod.archive_season_state(
        matches, "2025/26", "2026-01-01", require_verified_adjustments=False)
    ok = simcli.check_cutoff_table(witness)
    assert ok["PASS"] is True
    assert ok["detail"]["n_played"] > 100
    assert ok["detail"]["non_degenerate"] is True

    # POSITIVE CONTROL — perturb one club's goals and the reconstruction bites
    club = sorted(witness.table_so_far)[0]
    row = witness.table_so_far[club]
    corrupted = dataclasses.replace(
        witness,
        table_so_far={**witness.table_so_far,
                      club: dataclasses.replace(row, gf=row.gf + 1)})
    assert simcli.check_cutoff_table(corrupted)["PASS"] is False


def test_check_mc_uncertainty_fails_when_a_headline_has_no_se(issuance):
    run = issuance["runs"]["dc_native"]
    assert simcli.check_mc_uncertainty(run)["PASS"] is True

    # POSITIVE CONTROL — strip the standard error off one published market
    club = run.clubs[0]
    consequences = {c: {m: dict(cell) for m, cell in markets.items()}
                    for c, markets in run.consequences.items()}
    consequences[club]["champion"].pop("se")
    assert simcli.check_mc_uncertainty(
        dataclasses.replace(run, consequences=consequences))["PASS"] is False

    # POSITIVE CONTROL — a NaN standard error is not a standard error
    consequences2 = {c: {m: dict(cell) for m, cell in markets.items()}
                     for c, markets in run.consequences.items()}
    consequences2[club]["relegated"]["se"] = float("nan")
    assert simcli.check_mc_uncertainty(
        dataclasses.replace(run, consequences=consequences2))["PASS"] is False


def test_reproducibility_serial_equals_chunked_and_a_different_seed_changes_it(
        state, book):
    report = simcli.check_reproducibility(
        "dc_native", state, book, n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
        n_particles=N_PARTICLES)
    detail = report["detail"]
    assert report["PASS"] is True, detail
    assert detail["n_chunks"] == N_SIMS // CHUNK
    assert detail["serial_digest"] == detail["repeat_digest"]
    assert detail["chunk_concatenation_matches"] is True
    assert detail["parallel_digest"] == detail["serial_digest"]
    assert detail["parallel_error"] is None
    # the seed control is the proof the digest is capable of moving at all
    assert detail["seed_control_digest"] != detail["serial_digest"]
    assert detail["seed_control_changed"] is True


def test_reproducibility_reports_the_chunking_as_part_of_the_run(state, book):
    """Two chunk sizes are two runs: the streams are keyed by chunk index."""
    a = leaguesim.simulate("dc_native", state, book, N_SIMS, SEED, CHUNK,
                           n_particles=N_PARTICLES)
    b = leaguesim.simulate("dc_native", state, book, N_SIMS, SEED, N_SIMS,
                           n_particles=N_PARTICLES)
    assert a.plan.chunk_size != b.plan.chunk_size
    assert a.envelope["chunk_size"] != b.envelope["chunk_size"]
    # documented, not incidental: the envelope records the chunk size precisely
    # because it is part of the specification a re-run must match.
    assert "chunk_size" in leaguesim.ENVELOPE_FIELDS


class StubProvider:
    """A ScorelineProvider that is NOT a ParticleBook.

    Module level, so a spawned worker can import it: the gate's re-run goes
    through a process pool and everything it touches must pickle.
    """

    name = "elo_wdl_bridge"

    def __init__(self, n_particles: int):
        self.n_particles = int(n_particles)

    def sample(self, fixture, particle_idx, u):
        hg = np.floor(np.asarray(u[0]) * 4).astype(np.int8)
        ag = np.floor(np.asarray(u[1]) * 3).astype(np.int8)
        return hg, ag

    def content_hash(self) -> str:
        return "stub-provider"


def test_gate_reruns_the_published_arm_with_its_own_provider_not_the_book(
        state, book, season_obj):
    """A bridge arm's re-run must use the bridge, not the particle book."""
    stub = StubProvider(N_PARTICLES)
    run = leaguesim.simulate("elo_wdl_bridge", state, stub, N_SIMS, SEED, CHUNK,
                             n_particles=N_PARTICLES)
    limitations = leaguesim.limitations_markdown(run)

    ok = simcli.acceptance_gate(
        run=run, state=state, manifest=season_obj.manifest, book=book, post=None,
        provider=stub, limitations=limitations, **FAST_GATE)
    assert ok["criteria"]["serial_equals_chunked"]["PASS"] is True, (
        ok["criteria"]["serial_equals_chunked"])

    # POSITIVE CONTROL — with no provider the gate falls back to the book, which
    # builds a DIFFERENT arm; it must fail loudly rather than re-run dc_native
    # and report the agreement as this run's.
    fallback = simcli.acceptance_gate(
        run=run, state=state, manifest=season_obj.manifest, book=book, post=None,
        limitations=limitations, **FAST_GATE)
    cell = fallback["criteria"]["serial_equals_chunked"]
    assert cell["PASS"] is False
    assert "would label the run as something it is not" in cell["detail"]["error"]


def test_marginal_parity_is_skipped_for_a_bridge_arm_not_silently_passed(
        issuance, state, book, season_obj):
    """Per-fixture parity is a DC-native question; a bridge arm samples another
    law on purpose, so the criterion is SKIPPED (and the gate then cannot pass)
    rather than reported as agreement or as a failure."""
    run = issuance["runs"]["dc_native"]
    native = simcli.acceptance_gate(
        run=run, state=state, manifest=season_obj.manifest, book=book, post=None,
        limitations=leaguesim.limitations_markdown(run), **FAST_GATE)
    assert native["criteria"]["marginal_parity"]["status"] == "PASS"

    relabelled = dataclasses.replace(run, arm="elo_wdl_bridge")
    bridged = simcli.acceptance_gate(
        run=relabelled, state=state, manifest=season_obj.manifest, book=book,
        post=None, limitations=leaguesim.limitations_markdown(run), **FAST_GATE)
    cell = bridged["criteria"]["marginal_parity"]
    assert cell["status"] == "SKIPPED"
    assert cell["PASS"] is False
    assert "marginal_parity" in bridged["skipped"]
    assert bridged["PASS"] is False


def test_acceptance_gate_names_every_criterion_and_fails_when_one_fails(
        issuance, state, book, season_obj):
    gate = issuance["gate"]
    assert tuple(gate["criteria"]) == simcli.GATE_CRITERIA
    assert gate["PASS"] is False           # two criteria were deliberately skipped
    assert set(gate["skipped"]) == {"tiebreak_oracle", "src_scripts_untouched",
                                    "lock_valid"}

    # POSITIVE CONTROL — the same gate over a state with a fixture removed fails
    fewer = dataclasses.replace(
        state,
        fixtures={k: v for k, v in list(state.fixtures.items())[1:]},
        unplayed=tuple(sorted(state.fixtures))[1:])
    broken = simcli.acceptance_gate(
        run=issuance["runs"]["dc_native"], state=fewer, manifest=season_obj.manifest,
        book=book, post=None, limitations=(Path(issuance["directory"])
                                           / "limitations.md").read_text(),
        **FAST_GATE)
    assert broken["PASS"] is False
    assert "clubs_and_fixtures" in broken["failed"]


# ==========================================================================
# 5. `check` re-runs the last issuance and must reproduce it
# ==========================================================================
def _blocked_only_by_the_gate(report: dict) -> bool:
    """Everything reproduced; the only thing not shown is the acceptance gate.

    A6 (b.3) makes a bundle that cannot show it passed its gate not-a-pass, and
    every fast test issuance here either runs no gate at all or runs the fast
    gate, which SKIPs two criteria and therefore does not pass. That is the new
    rule working, so these tests assert it explicitly rather than asserting a
    top-level PASS the rule no longer allows.
    """
    return (report["PASS"] is False
            and not report["failed"] and not report["refused"]
            and set(report["record_failed"]) <= {"acceptance_verdict"}
            and set(report["record_refused"]) <= {"acceptance_verdict"})


def _as_older_schema(record: dict, schema: str) -> dict:
    """The record as an OLDER schema really was — without the fields it lacked.

    A record edited into the past while still carrying `epl-issuance-4`'s
    anchors is not a legacy record, it is a tampered one, and `record_digest`
    says so. Dropping them is what makes the leniency test about the leniency.
    """
    record = dict(record)
    record["schema_version"] = schema
    for name in simcli.A6_RECORD_FIELDS:
        record.pop(name, None)
    return record


def _restamp(record: dict) -> dict:
    """Re-digest an edited record, so exactly ONE thing about it is wrong.

    A6 (b.1) is explicit that a self-carried digest is a checksum against
    accident and not a seal against an editor who updates every copy. These
    tests are that editor on purpose: the point of each is the OTHER anchor.
    """
    record = dict(record)
    record[simcli.RECORD_DIGEST_FIELD] = simcli.record_digest(record)
    return record


def test_cli_check_reproduces_the_last_issuance(issuance, book):
    report = simcli.check_issuance(issuance["directory"], verbose=False)
    assert _blocked_only_by_the_gate(report)
    assert report["detail"]["digest_matches"] is True
    assert report["coherence"]["PASS"] is True

    # POSITIVE CONTROL — tamper with the persisted book and the digest must move
    tampered = Path(issuance["directory"]).parent / "tampered"
    shutil.copytree(issuance["directory"], tampered)
    shifted = dataclasses.replace(book, att=book.att + 0.05)
    shifted.save(tampered / "particles.npz")
    broken = simcli.check_issuance(tampered, verbose=False)
    assert broken["PASS"] is False
    assert broken["detail"]["digest_matches"] is False


# ==========================================================================
# 6. D18 — the live bridge sees the season's OWN results
# ==========================================================================
#
# Verifier finding (a): `live_fit` set `FitBundle.matches` to the football-data
# archive, and `forecast` fitted the empirical bridge on it. The archive has NO
# rows of a season in progress, so mid-season the bridge estimating
# P(scoreline | outcome) had never seen a match of the season it was pricing —
# while the Dixon-Coles fit beside it trained on archive PLUS the results
# ledger. D18 requires the bridge to see every valid played match before the
# cutoff. The frame is now built once, by `simcli.live_training_frame`, and both
# read it.

def _archive_frame(n: int = 900, *, seed: int = 11) -> pd.DataFrame:
    """League-shaped completed-season rows, all well before the opener."""
    rng = np.random.default_rng(seed)
    hg = rng.poisson(1.55, n)
    ag = rng.poisson(1.20, n)
    dates = pd.Timestamp("2023-01-01") + pd.to_timedelta(
        np.sort(rng.integers(0, 1100, n)), unit="D")
    return pd.DataFrame({
        "match_id": [f"arch{i:05d}" for i in range(n)],
        "season": "2025/26",
        "date": dates,
        "kickoff": pd.NaT,
        "home_key": "aaa",
        "away_key": "bbb",
        "fthg": hg, "ftag": ag,
        "ftr": np.where(hg > ag, "H", np.where(hg == ag, "D", "A")),
        "played": True,
    })


def _ledger_rows(day: str):
    """Three results-ledger rows of the target season, played on `day`."""
    return tuple(
        liveanchor.LiveRow(
            fixture_id=f"2627:h{i}:a{i}", home_key=f"h{i}", away_key=f"a{i}",
            date_played=pd.Timestamp(day), observed_at=pd.Timestamp(day),
            hg=4 + i, ag=0)
        for i in range(3))


def test_live_training_frame_adds_the_seasons_results_and_respects_the_cutoff():
    archive = _archive_frame()

    empty, seen_none = simcli.live_training_frame(archive, (), SEASON, OPENER)
    assert seen_none == () and len(empty) == len(archive)

    before, seen_before = simcli.live_training_frame(
        archive, _ledger_rows("2026-08-19"), SEASON, OPENER)
    assert len(seen_before) == 3
    assert len(before) == len(archive) + 3
    # the ledger rows arrive in the shape the bridge reads
    for column in ("date", "fthg", "ftag", "ftr", "played"):
        assert column in before.columns
    assert int((before["season"].astype(str) == SEASON).sum()) == 3

    # POINT-IN-TIME POSITIVE CONTROL — the same three results dated ON or AFTER
    # the cutoff are not in the frame at all.
    after, seen_after = simcli.live_training_frame(
        archive, _ledger_rows(OPENER), SEASON, OPENER)
    assert seen_after == () and len(after) == len(archive)
    later, seen_later = simcli.live_training_frame(
        archive, _ledger_rows("2026-08-22"), SEASON, OPENER)
    assert seen_later == () and len(later) == len(archive)

    # ...and that is what moves the bridge: the three pre-cutoff results change
    # the estimated conditional; the three post-cutoff ones cannot.
    base = bridge_mod.EmpiricalBridge.fit(empty, OPENER).hash
    assert bridge_mod.EmpiricalBridge.fit(before, OPENER).hash != base
    assert bridge_mod.EmpiricalBridge.fit(after, OPENER).hash == base
    assert bridge_mod.EmpiricalBridge.fit(later, OPENER).hash == base


def test_forecast_fits_the_bridge_on_the_frame_the_fit_trained_on(book, tmp_path):
    archive = _archive_frame()
    trained, _ = simcli.live_training_frame(
        archive, _ledger_rows("2026-08-19"), SEASON, OPENER)

    def bridge_hash(training, where):
        record = simcli.forecast(
            season=SEASON, cutoff=OPENER, arms=("dc_wdl_bridge",),
            n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
            n_particles=N_PARTICLES, out_root=tmp_path / where, gate=False,
            verbose=False,
            fit=simcli.FitBundle(post=None, book=book, matches=archive,
                                 training=training))
        return record["runs"]["dc_wdl_bridge"].envelope["bridge_hash"]

    # `matches` is IDENTICAL in both calls; only `training` differs. A forecast
    # that fitted the bridge on the archive would return the same hash twice.
    plain = bridge_hash(archive, "plain")
    with_ledger = bridge_hash(trained, "with_ledger")
    assert with_ledger != plain, (
        "the bridge must be fitted on the frame the fit trained on "
        "(archive + the season's own observed results), not on the archive")


# ==========================================================================
# 7. the reproducibility check must be able to FAIL
# ==========================================================================
#
# Verifier finding (e): `check_reproducibility` reported PASS on every input it
# had ever been handed, so nothing showed that its three flags were computed
# rather than written down. Two stubs, each breaking exactly one of them:
#
#   * `_CounterProvider` ignores its uniforms and reads a process-global
#     counter, so two runs of the same specification differ -> `deterministic`
#     and `chunk_concatenation_matches` must both go False;
#   * `_ConstantProvider` is perfectly deterministic and chunk-consistent but
#     blind to the seed -> `seed_control_changed` must go False.
#
# Together with the real arm's PASS they pin all three flags in both directions:
# hardcoding any of them to a constant fails one of these three assertions.

#: A process-global stream, advanced once per `sample` call. A plain modular
#: counter is not safe here: the number of calls between two passes is a
#: multiple of the fixture count, so a small modulus can realign by accident and
#: hand the stub back its determinism. A generator's period cannot.
_TICK = np.random.default_rng(20260819)


class _CounterProvider:
    """A sampler that ignores `u` and advances a process-global stream instead."""

    name = "dc_native"
    n_particles = N_PARTICLES

    def sample(self, fixture, particle_idx, u):
        n = len(np.asarray(particle_idx))
        goals = _TICK.integers(0, 4, size=(2, n)).astype(np.int8)
        return goals[0], goals[1]

    def content_hash(self) -> str:
        return "counter-stub"


class _ConstantProvider:
    """A sampler that ignores `u` entirely: same season at every seed."""

    name = "dc_native"
    n_particles = N_PARTICLES

    def sample(self, fixture, particle_idx, u):
        n = len(np.asarray(particle_idx))
        return np.ones(n, np.int8), np.zeros(n, np.int8)

    def content_hash(self) -> str:
        return "constant-stub"


def test_check_reproducibility_can_fail_and_its_flags_are_computed(state, book):
    common = dict(n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
                  n_particles=N_PARTICLES, parallel_workers=0)

    counter = simcli.check_reproducibility("dc_native", state,
                                           _CounterProvider(), **common)
    assert counter["PASS"] is False
    assert counter["detail"]["deterministic"] is False
    assert counter["detail"]["chunk_concatenation_matches"] is False

    constant = simcli.check_reproducibility("dc_native", state,
                                            _ConstantProvider(), **common)
    assert constant["PASS"] is False
    assert constant["detail"]["seed_control_changed"] is False
    # ...and it fails for THAT reason only: the other two flags are still True,
    # so `PASS` is not just "something went wrong somewhere".
    assert constant["detail"]["deterministic"] is True
    assert constant["detail"]["chunk_concatenation_matches"] is True

    # POSITIVE CONTROL — the real arm passes the same check with all three
    # flags True, so none of the assertions above can be met by a flag that is
    # hardcoded False.
    real = simcli.check_reproducibility("dc_native", state, book, **common)
    assert real["PASS"] is True
    for flag in ("deterministic", "chunk_concatenation_matches",
                 "seed_control_changed"):
        assert real["detail"][flag] is True, flag


# ==========================================================================
# 8. v1.1 R2 — `check` re-derives a BRIDGE arm from its own bundle
# ==========================================================================
#
# Before this section `check` refused any issuance whose published arm was not
# `dc_native`, and never looked at the other arms at all: a three-arm issuance
# was checked one-third of the way and reported PASS. The bridge arms are now
# rebuilt from the sidecars `forecast` writes beside them (`epl.simbundle`), and
# an arm that cannot be rebuilt is REFUSED — never silently skipped, and never
# counted as agreement.

@pytest.fixture(scope="module")
def live_anchor(season_obj):
    """The real transition anchor at the 2026/27 opener, on the real archive."""
    from epl import baseline, freeze
    from epl.schema import sort_for_walk_forward

    matches = baseline.load_matches()
    played = sort_for_walk_forward(matches.loc[matches["played"]])
    archive = played.loc[played["season"].astype(str) != SEASON]
    return liveanchor.LiveAnchor(archive, season_obj.results,
                                 season_obj.manifest,
                                 freeze.frozen_elo_config()), archive


@pytest.fixture(scope="module")
def three_arm_issuance(tmp_path_factory, book, live_anchor) -> dict:
    """One issuance carrying all three arms — synthetic book, real everything else."""
    anchor, archive = live_anchor
    return simcli.forecast(
        season=SEASON, cutoff=OPENER, arms=simcli.ARMS, n_sims=N_SIMS,
        seed=SEED, chunk_size=CHUNK, n_particles=N_PARTICLES,
        out_root=tmp_path_factory.mktemp("three_arm"), gate=False, verbose=False,
        fit=simcli.FitBundle(post=None, book=book, anchor=anchor,
                             matches=archive, training=archive,
                             info={"synthetic": True, "cold_start_teams": []}))


def _copy(issuance, name: str) -> Path:
    directory = Path(issuance["directory"])
    target = directory.parent / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(directory, target)
    return target


def test_forecast_writes_the_sidecars_a_bridge_arm_needs(three_arm_issuance):
    from epl import simbundle

    directory = Path(three_arm_issuance["directory"])
    for name in (simbundle.ARMS_SIDECAR, simbundle.BRIDGE_SIDECAR,
                 simbundle.ELO_SIDECAR):
        assert (directory / name).exists(), f"{name} was not written"

    # the bridge sidecar IS the bridge the forecast used
    payload = json.loads((directory / simbundle.BRIDGE_SIDECAR).read_text())
    assert payload["hash"] == three_arm_issuance["bridge_hash"]


def test_check_reproduces_every_arm_from_its_own_bundle(three_arm_issuance):
    report = simcli.check_issuance(three_arm_issuance["directory"], verbose=False)
    assert set(report["arms"]) == set(simcli.ARMS)
    for arm in simcli.ARMS:
        cell = report["arms"][arm]
        assert cell["status"] == "PASS", (arm, cell)
        assert cell["detail"]["digest_matches"] is True, arm
        assert cell["detail"]["recomputed_digest"] == \
            three_arm_issuance["numbers_digests"][arm]
        assert cell["coherence"]["PASS"] is True, arm
    assert _blocked_only_by_the_gate(report)

    # per-fixture parity is a DC-native question and is NOT claimed for an arm
    # that samples another law on purpose
    assert report["arms"]["dc_native"]["marginal_parity"]["PASS"] is True
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        assert report["arms"][arm]["marginal_parity"]["status"] == "NOT_APPLICABLE"


def test_a_perturbed_bridge_cdf_cell_fails_check_naming_both_bridge_arms(
        three_arm_issuance):
    from epl import simbundle

    tampered = _copy(three_arm_issuance, "cdf_cell")
    path = tampered / simbundle.BRIDGE_SIDECAR
    payload = json.loads(path.read_text())
    payload["cdf"][1][30] = payload["cdf"][1][30] + 0.02
    path.write_text(json.dumps(payload))

    report = simcli.check_issuance(tampered, verbose=False)
    assert report["PASS"] is False
    assert report["arms"]["dc_native"]["status"] == "PASS"
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        cell = report["arms"][arm]
        assert cell["status"] == "FAIL", arm
        assert arm in cell["detail"]["error"]
        assert "cdf" in cell["detail"]["error"]
    assert set(report["failed"]) == {"dc_wdl_bridge", "elo_wdl_bridge"}


def test_a_changed_elo_rating_fails_check_naming_the_elo_arm(three_arm_issuance):
    from epl import simbundle

    tampered = _copy(three_arm_issuance, "elo_rating")
    path = tampered / simbundle.ELO_SIDECAR
    payload = json.loads(path.read_text())
    club = sorted(payload["ratings"])[0]
    payload["ratings"][club] += 30.0
    path.write_text(json.dumps(payload))

    report = simcli.check_issuance(tampered, verbose=False)
    assert report["PASS"] is False
    assert report["failed"] == ["elo_wdl_bridge"]
    error = report["arms"]["elo_wdl_bridge"]["detail"]["error"]
    assert "elo_wdl_bridge" in error
    # the other two arms do not depend on the Elo sidecar and still reproduce
    for arm in ("dc_native", "dc_wdl_bridge"):
        assert report["arms"][arm]["status"] == "PASS", arm


def test_a_coherent_cross_file_tamper_fails_check_against_the_issuance_record(
        three_arm_issuance, book):
    """Every hash INSIDE the bundle can be made to agree; the record cannot.

    Doubling every count in `bridge.json` leaves the cdf bit-for-bit identical —
    each row is divided by its own total — so an editor who also rewrites that
    file's `hash`, the `content_hash` in `elo_arm.json` and both arm hashes in
    `arms.json` produces a bundle nothing inside it disagrees with. What refuses
    it is `issuance.json`: the bridge rebuilt from those counts is not the one
    whose hash the forecast recorded when it ran.
    """
    from epl import ordlogit, simbundle

    tampered = _copy(three_arm_issuance, "coherent_tamper")
    record = json.loads((tampered / "issuance.json").read_text())
    assert record["arms_manifest_hash"], "the manifest anchor was not recorded"

    path = tampered / simbundle.BRIDGE_SIDECAR
    payload = json.loads(path.read_text())
    cdf_before = [list(row) for row in payload["cdf"]]
    doubled = bridge_mod.EmpiricalBridge(
        counts=np.asarray(payload["counts"], np.int64) * 2,
        max_goals=int(payload["max_goals"]), cutoff=str(payload["cutoff"]),
        n_rows=int(payload["n_rows"]) * 2,
        n_excluded=int(payload["n_excluded"]) * 2)
    payload.update(counts=doubled.counts.tolist(), cdf=doubled.cdf.tolist(),
                   n_rows=int(doubled.n_rows),
                   n_excluded=int(doubled.n_excluded),
                   hash=doubled.content_hash())
    path.write_text(json.dumps(payload))
    assert payload["cdf"] == cdf_before, "the tamper was supposed to be invisible"

    elo_path = tampered / simbundle.ELO_SIDECAR
    elo_payload = json.loads(elo_path.read_text())
    elo = bridge_mod.EloOutcomeProvider(
        probs=np.asarray(elo_payload["probs"], float),
        fixture_ids=elo_payload["fixture_ids"], bridge=doubled,
        params=ordlogit.OrdLogitParams(
            **{k: v for k, v in elo_payload["params"].items() if k != "c2"}),
        cutoff=elo_payload["cutoff"],
        n_fit_rows=int(elo_payload["n_fit_rows"]),
        n_particles=int(elo_payload["n_particles"]),
        ratings=elo_payload["ratings"])
    elo_payload["content_hash"] = elo.content_hash()
    elo_path.write_text(json.dumps(elo_payload))

    arms_path = tampered / simbundle.ARMS_SIDECAR
    arms = json.loads(arms_path.read_text())
    arms["arms"]["dc_wdl_bridge"]["content_hash"] = bridge_mod.DCWDLProvider(
        book, doubled).content_hash()
    arms["arms"]["elo_wdl_bridge"]["content_hash"] = elo.content_hash()
    arms_path.write_text(json.dumps(arms))

    report = simcli.check_issuance(tampered, verbose=False)
    assert report["PASS"] is False
    assert set(report["failed"]) == {"dc_wdl_bridge", "elo_wdl_bridge"}
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        error = report["arms"][arm]["detail"]["error"]
        assert "bridge_hash" in error and "issuance.json" in error, (arm, error)
        assert record["bridge_hash"] in error, arm
        # ...and the arm that reads no sidecar is unaffected
    assert report["arms"]["dc_native"]["status"] == "PASS"
    # the anchors are named in the report, so a reader can see what was checked
    assert report["arms"]["dc_native"]["detail"]["sidecar_anchors"] == []
    assert set(report["arms"]["dc_wdl_bridge"]["detail"]["sidecar_anchors"]) == {
        "bridge_hash", "arms_manifest_hash", "provider_hash"}


def test_a_v3_record_stripped_of_the_manifest_anchor_fails_and_names_it(
        three_arm_issuance):
    """The fail-closed anchor was DOWNGRADEABLE by deleting a line (Codex 04b26a2).

    `arms_manifest_hash` arrived with `epl-issuance-3` and is what holds
    `arms.json` — the file whose arm hashes an editor has to rewrite to make a
    doctored bridge look coherent — against the run that wrote it. Reporting a
    missing one as "unanchored" meant a CURRENT record could opt out of the
    strongest check in the bundle by dropping the field, and `check` still
    returned PASS. On -3 every anchor is required, per bridge arm.
    """
    stripped = _copy(three_arm_issuance, "no_manifest_anchor")
    path = stripped / "issuance.json"
    record = json.loads(path.read_text())
    assert record["schema_version"] == simcli.ISSUANCE_SCHEMA_VERSION
    assert record.pop("arms_manifest_hash")
    path.write_text(json.dumps(_restamp(record)))

    report = simcli.check_issuance(stripped, verbose=False)
    assert report["PASS"] is False
    assert set(report["failed"]) == {"dc_wdl_bridge", "elo_wdl_bridge"}
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        detail = report["arms"][arm]["detail"]
        assert detail["missing_mandatory_anchors"] == ["arms_manifest_hash"], arm
        assert detail["digest_matches"] is True, (
            f"{arm} reproduces its numbers exactly; the FAIL is the missing "
            "anchor and nothing else, which is the point")
    # `dc_native` reads no sidecar, so neither hash exists for it and demanding
    # them would be a criterion no honest record could satisfy
    assert report["arms"]["dc_native"]["status"] == "PASS"
    assert report["arms"]["dc_native"]["detail"]["missing_mandatory_anchors"] == []

    # ...and the same absence on the schema that PREDATES the field is still
    # reported as unanchored, because that leniency is what it exists for
    older = _copy(three_arm_issuance, "schema_2_no_manifest_anchor")
    path = older / "issuance.json"
    record = _as_older_schema(json.loads(path.read_text()), "epl-issuance-2")
    del record["arms_manifest_hash"]
    path.write_text(json.dumps(record))
    lenient = simcli.check_issuance(older, verbose=False)
    assert _blocked_only_by_the_gate(lenient)
    assert lenient["failed"] == [] and lenient["refused"] == []
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        anchors = lenient["arms"][arm]["detail"]["sidecar_anchors"]
        assert "arms_manifest_hash" not in anchors, arm
        assert "bridge_hash" in anchors, arm


def test_an_edited_bridge_row_count_fails_an_otherwise_intact_v3_bundle(
        three_arm_issuance):
    """`n_rows` was evidence no hash covered (Codex 04b26a2).

    The bridge's content hash is over schema, cutoff, grid bound and counts —
    not over how many pre-cutoff matches were read to build them — so before
    the sidecar carried a hash of its own content, multiplying `n_rows` by a
    hundred left `bridge.json`'s `hash`, the `bridge_hash` in `issuance.json`,
    every provider hash and every simulation digest exactly where they were. A
    reader was told the conditional rested on a hundred times the history it
    did, by a bundle that reproduces perfectly.
    """
    from epl import simbundle

    tampered = _copy(three_arm_issuance, "row_count")
    path = tampered / simbundle.BRIDGE_SIDECAR
    payload = json.loads(path.read_text())
    before = dict(payload)
    payload["n_rows"] = payload["n_rows"] * 100
    path.write_text(json.dumps(payload))

    # the premise: nothing the OLD checks read has moved
    assert payload["hash"] == before["hash"]
    assert payload["counts"] == before["counts"]
    assert payload["cdf"] == before["cdf"]

    report = simcli.check_issuance(tampered, verbose=False)
    assert report["PASS"] is False
    assert set(report["failed"]) == {"dc_wdl_bridge", "elo_wdl_bridge"}
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        error = report["arms"][arm]["detail"]["error"]
        assert simbundle.BRIDGE_SIDECAR in error, (arm, error)
        assert "n_rows" in error, (arm, error)
    assert report["arms"]["dc_native"]["status"] == "PASS"


def test_a_missing_sidecar_makes_check_refuse_that_arm_and_not_pass(
        three_arm_issuance):
    from epl import simbundle

    stripped = _copy(three_arm_issuance, "no_sidecars")
    for name in (simbundle.ARMS_SIDECAR, simbundle.BRIDGE_SIDECAR,
                 simbundle.ELO_SIDECAR):
        (stripped / name).unlink()

    report = simcli.check_issuance(stripped, verbose=False)
    assert report["PASS"] is False
    assert report["arms"]["dc_native"]["status"] == "PASS"
    assert report["arms"]["dc_native"]["detail"]["digest_matches"] is True
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        cell = report["arms"][arm]
        assert cell["status"] == "REFUSED"
        assert cell["PASS"] is False
        assert simbundle.BRIDGE_SIDECAR in cell["detail"]["error"]
    assert set(report["refused"]) == {"dc_wdl_bridge", "elo_wdl_bridge"}

    # ...and narrowing to the arm that CAN be rebuilt is an explicit act
    narrowed = simcli.check_issuance(stripped, arms=("dc_native",), verbose=False)
    assert _blocked_only_by_the_gate(narrowed)
    assert set(narrowed["arms"]) == {"dc_native"}


def test_check_of_a_bridge_published_arm_no_longer_refuses_outright(
        tmp_path_factory, book, live_anchor):
    """The old `check` bailed on ANY non-native published arm before looking."""
    anchor, archive = live_anchor
    issued = simcli.forecast(
        season=SEASON, cutoff=OPENER, arms=("dc_wdl_bridge",), n_sims=N_SIMS,
        seed=SEED, chunk_size=CHUNK, n_particles=N_PARTICLES,
        out_root=tmp_path_factory.mktemp("published_bridge"), gate=False,
        verbose=False,
        fit=simcli.FitBundle(post=None, book=book, anchor=anchor,
                             matches=archive, training=archive, info={}))
    assert issued["published_arm"] == "dc_wdl_bridge"

    report = simcli.check_issuance(issued["directory"], verbose=False)
    assert _blocked_only_by_the_gate(report)
    assert report["arm"] == "dc_wdl_bridge"
    assert report["detail"]["digest_matches"] is True


# ==========================================================================
# round 2 — the gate's own checks, and the artefacts `check` reads back
# ==========================================================================

def test_check_lock_requires_exit_zero_AND_the_text(monkeypatch):
    """Either half alone passes a run in which the chain did not verify.

    The text alone passes a script that printed LOCK VALID and then died on the
    next link. The exit code alone passes a script replaced by anything that
    exits 0. The claim being made is that the whole chain verified.
    """
    class _Proc:
        def __init__(self, code, out, err=""):
            self.returncode, self.stdout, self.stderr = code, out, err

    cases = {
        (0, "LOCK VALID\n"): True,                      # the real thing
        (1, "LOCK VALID\n"): False,                     # printed, then died
        (0, "LOCK BROKEN at commit deadbeef\n"): False,  # exited 0, said no
        (0, ""): False,                                  # said nothing at all
        (2, "traceback\n"): False,
    }
    for (code, out), expected in cases.items():
        monkeypatch.setattr(simcli.subprocess, "run",
                            lambda *a, _c=code, _o=out, **k: _Proc(_c, _o))
        report = simcli.check_lock()
        assert report["PASS"] is expected, (code, out)
        assert report["detail"]["returncode"] == code


def test_check_mc_uncertainty_fails_on_a_negative_standard_error(issuance):
    """A standard error is a square root: below zero it is a broken estimator.

    `outer` and `inner` are variance COMPONENTS, not standard errors — an
    unbiased `outer` can legitimately come out negative — so the check requires
    them finite and NOT non-negative, and that distinction is asserted here so a
    later tightening cannot quietly break the decomposition.
    """
    run = issuance["runs"]["dc_native"]
    assert simcli.check_mc_uncertainty(run)["PASS"] is True

    for label in ("market_se", "matrix_se", "points_se", "mc_cluster"):
        broken = copy.copy(run)
        if label == "market_se":
            broken.consequences = copy.deepcopy(run.consequences)
            broken.consequences[run.clubs[0]]["champion"]["se"] = -1e-6
        elif label == "matrix_se":
            broken.matrix_se = run.matrix_se.copy()
            broken.matrix_se[2, 3] = -1e-9
        elif label == "points_se":
            broken.points_summary = copy.deepcopy(run.points_summary)
            broken.points_summary[run.clubs[0]]["se"] = -0.5
        else:
            broken.mc = dict(run.mc, cluster_se_max=-1e-12)
        report = simcli.check_mc_uncertainty(broken)
        assert report["PASS"] is False, label
        assert report["detail"]["problems"], label

    # POSITIVE CONTROL: a negative `outer` is legal and must NOT fail the check.
    legal = copy.copy(run)
    legal.consequences = copy.deepcopy(run.consequences)
    legal.consequences[run.clubs[0]]["champion"]["outer"] = -1e-9
    legal.mc = dict(run.mc, outer=-1e-9)
    assert simcli.check_mc_uncertainty(legal)["PASS"] is True


def test_check_reads_the_published_output_file_back(issuance):
    """An edited cell in `output_<arm>.json` is what a reader downloads.

    `numbers_digests` is taken over live arrays: it says the re-run agrees with
    the run, and cannot see the file. `check` now digests the published payload
    off disk and holds it against both the record and the re-run.
    """
    directory = Path(issuance["directory"])
    record = json.loads((directory / "issuance.json").read_text())
    assert record["schema_version"] == simcli.ISSUANCE_SCHEMA_VERSION
    assert set(record["output_digests"]) == set(record["arms"])
    assert set(record["provider_hashes"]) == set(record["arms"])
    assert _blocked_only_by_the_gate(
        simcli.check_issuance(directory, verbose=False))

    edited = directory.parent / "edited_output"
    shutil.copytree(directory, edited)
    path = edited / "output_dc_native.json"
    payload = json.loads(path.read_text())
    club = sorted(payload["matrix"])[0]
    payload["matrix"][club][0] += 1e-9          # one cell, invisible to a reader
    path.write_text(json.dumps(payload))

    report = simcli.check_issuance(edited, verbose=False)
    assert report["PASS"] is False
    detail = report["arms"]["dc_native"]["detail"]
    assert detail["output_file_matches"] is False
    # ... and the live-array digest still agrees, which is exactly why the file
    # needed its own check.
    assert detail["digest_matches"] is True


def test_check_refuses_a_provider_hash_that_is_not_the_recorded_one(issuance,
                                                                   book):
    """A different provider claiming the arm is not a reproduction."""
    directory = Path(issuance["directory"])
    swapped = directory.parent / "swapped_provider"
    shutil.copytree(directory, swapped)
    record = json.loads((swapped / "issuance.json").read_text())
    record["provider_hashes"]["dc_native"] = "not-the-provider-that-made-it"
    (swapped / "issuance.json").write_text(json.dumps(_restamp(record)))

    report = simcli.check_issuance(swapped, verbose=False)
    assert report["PASS"] is False
    assert report["arms"]["dc_native"]["detail"]["provider_hash_matches"] is False

    # POSITIVE CONTROL: an `epl-issuance-1` record recorded no provider hash at
    # all, and a missing record is reported as unrecorded rather than failed.
    older = directory.parent / "older_schema"
    shutil.copytree(directory, older)
    record = _as_older_schema(json.loads((older / "issuance.json").read_text()),
                              "epl-issuance-1")
    record.pop("provider_hashes")
    record.pop("output_digests")
    (older / "issuance.json").write_text(json.dumps(record))
    legacy = simcli.check_issuance(older, verbose=False)
    assert _blocked_only_by_the_gate(legacy)
    # ...and a pre-A6 record can never claim to be fully anchored.
    assert legacy["fully_anchored"] is False
    assert legacy["arms"]["dc_native"]["detail"]["provider_hash_matches"] is None
    assert legacy["arms"]["dc_native"]["detail"]["legacy_schema_leniency"] is True
    assert legacy["arms"]["dc_native"]["detail"]["missing_mandatory_anchors"] == []

    # ...AND THE LENIENCY IS THE SCHEMA'S, NOT THE ABSENCE'S. `output_digests`
    # and `provider_hashes` arrived with `epl-issuance-2` and are mandatory from
    # there on, but "absent" was read as "no anchor to hold this against"
    # whatever the version said — so a schema-2 or -3 record stripped of both
    # mandatory anchors passed exactly as an honest schema-1 record does.
    for dropped in (("provider_hashes",), ("output_digests",),
                    ("provider_hashes", "output_digests")):
        stripped = directory.parent / ("stripped_" + "_".join(dropped))
        shutil.copytree(directory, stripped)
        record = json.loads((stripped / "issuance.json").read_text())
        assert record["schema_version"] != "epl-issuance-1"
        for key in dropped:
            record.pop(key)
        (stripped / "issuance.json").write_text(json.dumps(_restamp(record)))

        report = simcli.check_issuance(stripped, verbose=False)
        cell = report["arms"]["dc_native"]
        assert report["PASS"] is False, dropped
        assert cell["detail"]["legacy_schema_leniency"] is False
        assert cell["detail"]["missing_mandatory_anchors"] == sorted(dropped)
        # every other leg still holds, so the FAIL is the missing anchor alone
        assert cell["detail"]["digest_matches"] is True, dropped


def test_gate_refuses_a_provider_that_is_not_the_one_that_made_the_run(
        state, book, season_obj):
    """The gate's re-run must reproduce THE RUN, not merely itself.

    `check_reproducibility` re-ran whatever provider it was handed and compared
    it to itself, so a caller could gate an issuance with a different book
    entirely and the criterion would pass on internal consistency alone.
    """
    run = leaguesim.simulate("dc_native", state, book, N_SIMS, SEED, CHUNK,
                             n_particles=N_PARTICLES)
    limitations = leaguesim.limitations_markdown(run)
    other = dataclasses.replace(book, att=book.att + 0.05)

    honest = simcli.acceptance_gate(
        run=run, state=state, manifest=season_obj.manifest, book=book, post=None,
        provider=book, limitations=limitations, **FAST_GATE)
    cell = honest["criteria"]["serial_equals_chunked"]
    assert cell["PASS"] is True, cell["detail"]
    assert cell["detail"]["provider_identity_gap"] == {}
    assert cell["detail"]["reproduces_the_gated_run"] is True

    swapped = simcli.acceptance_gate(
        run=run, state=state, manifest=season_obj.manifest, book=other, post=None,
        provider=other, limitations=limitations, **FAST_GATE)
    cell = swapped["criteria"]["serial_equals_chunked"]
    assert cell["PASS"] is False
    assert "effective_posterior_hash" in cell["detail"]["provider_identity_gap"]
    assert cell["detail"]["reproduces_the_gated_run"] is False

    # THE ENVELOPE'S OWN `provider_hash`, compared exactly. The described-field
    # comparison is partial: a provider whose `describe()` carries none of those
    # keys (or raises) matched everything by matching nothing, and the
    # reproduction leg comes back `None` whenever the gate re-runs at a
    # different N or chunk size — so a DIFFERENT provider could self-reproduce
    # and pass. `content_hash()` covers the whole provider by construction.
    class _Mute:
        """The other book, with nothing to say about itself."""

        name = "dc_native"

        def __init__(self, inner):
            self._inner = leaguesim.DCNativeProvider(inner)
            self.book = inner

        @property
        def n_particles(self):
            return self._inner.n_particles

        def sample(self, fixture, particle_idx, u):
            return self._inner.sample(fixture, particle_idx, u)

        def excluded_mass_for(self, fixture):
            return self._inner.excluded_mass_for(fixture)

        def content_hash(self):
            return self._inner.content_hash()

        def describe(self):
            return {}                       # says nothing, so matches nothing

    mute = _Mute(other)
    assert mute.content_hash() != run.envelope["provider_hash"]
    gap = simcli._provider_identity_gap(mute, run)
    assert "provider_hash" in gap, (
        "a provider that describes nothing matched everything: the identity "
        "check was reading `describe()` and never the envelope's own hash")
    assert gap["provider_hash"] == [mute.content_hash(),
                                    run.envelope["provider_hash"]]
    # POSITIVE CONTROL: the provider that DID make the run has no gap, through
    # the same door, so the key is not simply always present.
    assert "provider_hash" not in simcli._provider_identity_gap(
        leaguesim.DCNativeProvider(book), run)


def test_check_reproducibility_requires_the_parallel_leg_to_have_run(state, book,
                                                                    monkeypatch):
    """`parallel_ok` was True whenever the parallel leg did not run.

    Including when it was asked for: `digest is None or digest == serial` reads
    a skipped leg as an agreeing one. The report now records whether it was
    requested and whether it ran, and a requested leg that produced nothing
    fails.
    """
    base = simcli.check_reproducibility(
        "dc_native", state, book, n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
        n_particles=N_PARTICLES)
    assert base["PASS"] is True
    assert base["detail"]["parallel_requested"] is True
    assert base["detail"]["parallel_ran"] is True

    # NEGATIVE CONTROL 1: the pool computes something else. `parallel_ok` must
    # see it — this is the only assertion that says the digests are compared.
    real = leaguesim.simulate

    def different_in_parallel(arm, st, provider, n_sims, seed, *args, **kwargs):
        if kwargs.get("executor") is not None:
            seed = int(seed) + 1
        return real(arm, st, provider, n_sims, seed, *args, **kwargs)

    monkeypatch.setattr(leaguesim, "simulate", different_in_parallel)
    disagreeing = simcli.check_reproducibility(
        "dc_native", state, book, n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
        n_particles=N_PARTICLES)
    assert disagreeing["PASS"] is False
    assert disagreeing["detail"]["parallel_equals_serial"] is False
    assert disagreeing["detail"]["parallel_ran"] is True
    monkeypatch.undo()

    # NEGATIVE CONTROL 2: the pool raises, so the leg produces no digest at all.
    def explodes_in_parallel(arm, st, provider, n_sims, seed, *args, **kwargs):
        if kwargs.get("executor") is not None:
            raise RuntimeError("no workers today")
        return real(arm, st, provider, n_sims, seed, *args, **kwargs)

    monkeypatch.setattr(leaguesim, "simulate", explodes_in_parallel)
    missing = simcli.check_reproducibility(
        "dc_native", state, book, n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
        n_particles=N_PARTICLES)
    assert missing["PASS"] is False
    assert missing["detail"]["parallel_ran"] is False
    assert missing["detail"]["parallel_equals_serial"] is False


def test_forecast_bridge_ignores_an_explicit_matches_frame(book, tmp_path):
    """D18: `matches` does not override the frame the fit trained on.

    `matches` is the archive a caller hands in for the season state and the fit;
    `fit.training` is what the fit actually saw, which mid-season is the archive
    PLUS the season's own results ledger. Letting `matches` win re-opened the
    exact defect D18 closed — a bridge that has never seen a match of the season
    it is pricing — and did it only on the path that passes `matches`, which is
    every retrospective and every test that supplies an archive.
    """
    archive = _archive_frame()
    trained, _ = simcli.live_training_frame(
        archive, _ledger_rows("2026-08-19"), SEASON, OPENER)
    assert len(trained) > len(archive), "the ledger rows must really be added"

    def bridge_hash(where, **kwargs):
        record = simcli.forecast(
            season=SEASON, cutoff=OPENER, arms=("dc_wdl_bridge",),
            n_sims=N_SIMS, seed=SEED, chunk_size=CHUNK,
            n_particles=N_PARTICLES, out_root=tmp_path / where, gate=False,
            verbose=False,
            fit=simcli.FitBundle(post=None, book=book, matches=archive,
                                 training=trained),
            **kwargs)
        return record["runs"]["dc_wdl_bridge"].envelope["bridge_hash"]

    # the same fit, with and without an explicit `matches` that is NOT what the
    # fit trained on: the bridge must be the training frame's either way.
    without = bridge_hash("without")
    with_matches = bridge_hash("with_matches", matches=archive)
    assert with_matches == without, (
        "an explicit `matches` overrode `fit.training` and refitted the bridge "
        "on a frame the fit never saw")

    # POSITIVE CONTROL: the two frames really do produce different bridges, so
    # the equality above is not two names for one hash. This is the same call
    # with a fit that trained on the archive alone.
    record = simcli.forecast(
        season=SEASON, cutoff=OPENER, arms=("dc_wdl_bridge",), n_sims=N_SIMS,
        seed=SEED, chunk_size=CHUNK, n_particles=N_PARTICLES,
        out_root=tmp_path / "archive_training", gate=False, verbose=False,
        fit=simcli.FitBundle(post=None, book=book, matches=archive,
                             training=archive))
    assert record["runs"]["dc_wdl_bridge"].envelope["bridge_hash"] != without


def test_check_limitations_validates_the_truncation_record(issuance):
    """The flagged ids and the max/mean/p90 must be THIS run's, not a template.

    The heading check passes on a section that says the opposite of what the
    envelope holds: "none" under a run that flagged five fixtures, or a max the
    note simply states. Both numbers and ids are now read out of the envelope
    and required verbatim, and an id listed in the note that the envelope does
    not flag is a failure in the other direction.
    """
    run = issuance["runs"]["dc_native"]
    text = leaguesim.limitations_markdown(run)
    assert simcli.check_limitations(text, run)["PASS"] is True

    block = run.envelope["excluded_mass"]
    assert block["measured"] and block["n_fixtures"] == 380

    # (a) the max is restated as something else
    wrong = text.replace(f"{block['max']:.3g}", "0.001")
    assert wrong != text
    report = simcli.check_limitations(wrong, run)
    assert report["PASS"] is False
    assert "excluded_mass_max" in report["detail"]["numbers_not_found"]

    # (b) a fixture the envelope does not flag is listed as flagged
    invented = text.replace(
        "* **none** — no fixture exceeds the flag threshold.",
        "* `2627:arsenal:coventry` — particle-mean **0.006**, median particle "
        "0.0002, worst particle 0.4, particles over 1%: 22")
    assert invented != text
    report = simcli.check_limitations(invented, run)
    assert report["PASS"] is False
    assert report["detail"]["flagged_in_note_not_in_envelope"] == \
        ["2627:arsenal:coventry"]

    # (c) THE OTHER DIRECTION: a note that lists the flagged fixtures AND says
    #     there are none. Every check above is a presence check over the whole
    #     document, so a note keeping every required id and statistic while also
    #     claiming "no fixture exceeds the flag threshold" satisfied all of them
    #     — the required strings were there, and so was their denial. Presence
    #     cannot see a contradiction.
    flagged_run = _run_with_flagged_fixture(run)
    flagged_block = flagged_run.envelope["excluded_mass"]
    assert flagged_block["flagged"], "the fixture must really be flagged"
    honest = leaguesim.limitations_markdown(flagged_run)
    assert simcli.check_limitations(honest, flagged_run)["PASS"] is True

    denying = honest.replace(
        "## Monte-Carlo error",
        "* **none** — no fixture exceeds the flag threshold.\n\n"
        "## Monte-Carlo error")
    assert denying != honest
    report = simcli.check_limitations(denying, flagged_run)
    assert report["PASS"] is False
    assert report["detail"]["denies_its_own_flags"] == [
        "no fixture exceeds the flag threshold"]
    # ... and every OTHER leg still passes, so the failure is the denial alone
    assert report["detail"]["numbers_not_found"] == []
    assert report["detail"]["flagged_in_note_not_in_envelope"] == []

    # POSITIVE CONTROL: the note the run itself writes carries every number the
    # envelope holds, so (a), (b) and (c) are corruptions and not a stricter
    # reading — and an UNFLAGGED run may still say "none" without failing.
    assert simcli.check_limitations(text, run)["detail"]["numbers_not_found"] == []
    assert simcli.check_limitations(text, run)["detail"][
        "flagged_in_note_not_in_envelope"] == []
    assert simcli.check_limitations(text, run)["detail"][
        "denies_its_own_flags"] == []


def _run_with_flagged_fixture(run):
    """The same run with one fixture flagged in its envelope and report.

    The gate reads the envelope, so the flag is put there rather than re-fitting
    a hot book: what is under test is whether the NOTE may contradict the
    record, not how the record came to hold a flag.
    """
    flagged = {"fixture": run.plan.fixtures[0].fixture_id, "mean": 0.0061,
               "median": 0.00019, "worst": 0.44, "n_over_1pct": 21}
    envelope = dict(run.envelope)
    block = dict(envelope["excluded_mass"])
    block["flagged"] = [flagged]
    block["n_flagged"] = 1
    block["max"] = max(float(block["max"]), flagged["worst"])
    envelope["excluded_mass"] = block
    out = copy.copy(run)
    out.envelope = envelope
    return out


# ==========================================================================
# G1 — manual corrections and statuses, integral goals, and the kickoff move
# the refreshed source carries (`live-ingest.md` #2 #3, `live-forecast.md` #2)
# ==========================================================================

def _season_copy(tmp_path) -> Path:
    root = tmp_path / "season"
    shutil.copytree(season_mod.SEASON_ROOT, root)
    return root


def _manual_file(tmp_path, name: str, *rows: dict) -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_manual_ingest_refuses_a_non_integral_goal_at_WRITE_time(tmp_path):
    """`hg: 1.9` is refused, not silently stored as 1.

    `int()` on a JSON float is a coercion that cannot be undone: read-time
    validation sees an integer and passes it, so the ledger ends up holding a
    scoreline nobody ever reported. The refusal has to happen before the byte
    is written.
    """
    root = _season_copy(tmp_path)
    ledger = root / "2026_27" / "results_ledger.jsonl"
    before = ledger.read_text()
    bad = _manual_file(tmp_path, "bad.jsonl", {
        "fixture_id": "2627:arsenal:coventry", "date_played": "2026-08-21",
        "hg": 1.9, "ag": 0})
    with pytest.raises(season_mod.SeasonError, match="integral|goal count"):
        simcli.ingest_results(season=SEASON, root=root, manual_file=bad,
                              write=True, observed_at=INGEST_CLOCK, verbose=False)
    assert ledger.read_text() == before

    # POSITIVE CONTROL: the same row with an exact score writes.
    good = _manual_file(tmp_path, "good.jsonl", {
        "fixture_id": "2627:arsenal:coventry", "date_played": "2026-08-21",
        "hg": 2, "ag": 0})
    assert len(simcli.ingest_results(
        season=SEASON, root=root, manual_file=good, write=True,
        observed_at=INGEST_CLOCK, verbose=False)) == 1


def test_manual_ingest_accepts_a_status_row_and_a_marked_correction(tmp_path):
    """The hand overlay can do what the ledger's resolution already supports.

    A postponement and a correction are the two things a human operator needs to
    file when the source is wrong or the league moves a match, and neither was
    expressible: `_manual_rows` demanded integer goals from every row and
    refused any score that disagreed with the ledger.
    """
    root = _season_copy(tmp_path)
    fid = "2627:arsenal:coventry"
    first = _manual_file(tmp_path, "first.jsonl", {
        "fixture_id": fid, "date_played": "2026-08-21", "hg": 2, "ag": 1})
    simcli.ingest_results(season=SEASON, root=root, manual_file=first, write=True,
                          observed_at="2026-08-22T09:00", verbose=False)

    # An unmarked disagreement is still a conflict: a typo must not rewrite history.
    typo = _manual_file(tmp_path, "typo.jsonl", {
        "fixture_id": fid, "date_played": "2026-08-21", "hg": 3, "ag": 1})
    with pytest.raises(season_mod.ResultConflict):
        simcli.ingest_results(season=SEASON, root=root, manual_file=typo, write=True,
                              observed_at="2026-08-23T09:00", verbose=False)

    fixed = _manual_file(tmp_path, "fixed.jsonl", {
        "fixture_id": fid, "date_played": "2026-08-21", "hg": 3, "ag": 1,
        "correction": True, "note": "league confirmed"})
    rows = simcli.ingest_results(season=SEASON, root=root, manual_file=fixed,
                                 write=True, observed_at="2026-08-23T09:00",
                                 verbose=False)
    assert (rows[0]["hg"], rows[0]["ag"]) == (3, 1)
    assert season_mod.Season.load(SEASON, root=root).at("2026-08-25").played[fid] \
        == (3, 1)

    status = _manual_file(tmp_path, "status.jsonl", {
        "fixture_id": fid, "status": "postponed", "note": "waterlogged"})
    rows = simcli.ingest_results(season=SEASON, root=root, manual_file=status,
                                 write=True, observed_at="2026-08-24T09:00",
                                 verbose=False)
    assert rows[0]["status"] == "postponed" and "hg" not in rows[0]
    reread = season_mod.Season.load(SEASON, root=root).at("2026-08-25")
    assert fid not in reread.played and reread.statuses[fid] == "postponed"

    # Both write-time refusals: a status v1 does not model, and a status row
    # that also carries goals (which of the two is the row saying?).
    for bad_row in ({"fixture_id": fid, "status": "awarded"},
                    {"fixture_id": fid, "status": "postponed", "hg": 1, "ag": 0}):
        bad = _manual_file(tmp_path, "badstatus.jsonl", bad_row)
        with pytest.raises(season_mod.SeasonError):
            simcli.ingest_results(season=SEASON, root=root, manual_file=bad,
                                  write=True, observed_at="2026-08-25T09:00",
                                  verbose=False)


def test_ingest_results_records_a_moved_kickoff_from_the_refreshed_source(tmp_path):
    """A refreshed source that moved a fixture appends a kickoff amendment.

    `detect_kickoff_amendments` existed and nothing called it, so a moved
    kickoff left the old date in place — and a fixture whose old date has passed
    reads as `unresolved`, and past two days sets `results_lag`. The ingest is
    the only place that sees a fresh parse, so it is the place that must diff.
    """
    root = _season_copy(tmp_path)
    fid = "2627:arsenal:coventry"
    moved = ("▪ Matchday 1\n  Sat Aug 22 2026\n"
             "    17:30  Arsenal FC  v Coventry City FC\n")
    path = tmp_path / "refreshed.txt"
    path.write_text(moved, encoding="utf-8")

    simcli.ingest_results(season=SEASON, root=root, openfootball_file=path,
                          write=True, observed_at="2026-08-20T09:00", verbose=False)

    reloaded = season_mod.Season.load(SEASON, root=root)
    assert reloaded.at("2026-08-25").kickoffs_known[fid] == (
        pd.Timestamp("2026-08-22").date(), "17:30")
    # known_at is the INGEST time, so a snapshot taken before it still reads the
    # date the league had published then.
    assert reloaded.at("2026-08-25", observed_by="2026-08-19").kickoffs_known[fid] \
        == (pd.Timestamp("2026-08-21").date(), "20:00")

    # Idempotent: re-ingesting the same refreshed file appends no second row.
    amendments = root / "2026_27" / "kickoff_amendments.jsonl"
    before = amendments.read_text()
    simcli.ingest_results(season=SEASON, root=root, openfootball_file=path,
                          write=True, observed_at="2026-08-21T09:00", verbose=False)
    assert amendments.read_text() == before

    # POSITIVE CONTROL: the vendored file itself moves nothing.
    root2 = _season_copy(tmp_path / "second")
    vendored = season_mod.SEASON_ROOT / "2026_27" / "fixtures_openfootball_2026-27.txt"
    simcli.ingest_results(season=SEASON, root=root2, openfootball_file=vendored,
                          write=True, observed_at="2026-08-20T09:00", verbose=False)
    assert (root2 / "2026_27" / "kickoff_amendments.jsonl").read_text() == ""


# ==========================================================================
# G2 — `observed_by` binds the WHOLE forecast (A6 (c); every review's P0:
# `engine-pricing.md` #1, `gate-retro.md` #1, `live-forecast.md` #1,
# `live-ingest.md` #1)
#
# The bound reached the season state and the training frame and was then
# dropped when the DC fit built its Elo covariates and when the Elo arm was
# built. `gate-retro.md` #1's probe is reproduced here: C = 2026-08-26,
# O = 2026-08-22, one result played 2026-08-24 and filed as observed
# 2026-08-25. The state sees zero results; at HEAD the anchor saw the match.
# ==========================================================================

PROBE_CUTOFF = "2026-08-26"
PROBE_OBSERVED_BY = "2026-08-22"
PROBE_FIXTURE = "2627:arsenal:coventry"


@pytest.fixture(scope="module")
def leaked_season(tmp_path_factory) -> season_mod.Season:
    """The real season with ONE result filed after the knowledge bound."""
    root = tmp_path_factory.mktemp("probe") / "season"
    shutil.copytree(season_mod.SEASON_ROOT, root)
    (root / "2026_27" / "results_ledger.jsonl").write_text(json.dumps({
        "fixture_id": PROBE_FIXTURE, "date_played": "2026-08-24",
        "hg": 5, "ag": 0, "source": "manual",
        "observed_at": "2026-08-25T09:00:00", "note": "the probe"}) + "\n")
    return season_mod.Season.load(SEASON, root=root)


@pytest.fixture(scope="module")
def leaked_anchor(live_anchor, leaked_season):
    from epl import freeze

    _, archive = live_anchor
    return liveanchor.LiveAnchor(archive, leaked_season.results,
                                 leaked_season.manifest,
                                 freeze.frozen_elo_config())


def test_a_result_observed_after_the_bound_does_not_move_the_anchor(
        live_anchor, leaked_anchor, season_obj):
    """The DC fit's Elo covariates are built under the run's knowledge bound.

    `dcfit.fit_epl` re-entered the anchor with the cutoff alone, so a result
    filed between O and C moved `elo_z` while being absent from the declared
    snapshot — and the persisted bundle reproduced the leak, so `check` passed
    it.
    """
    from epl import dcfit

    anchor, _ = live_anchor                      # the repo ledger is empty
    teams = list(season_obj.manifest.clubs)

    bounded = dcfit.anchor_state_at(leaked_anchor, PROBE_CUTOFF, teams,
                                    observed_by=PROBE_OBSERVED_BY)
    clean = dcfit.anchor_state_at(anchor, PROBE_CUTOFF, teams,
                                  observed_by=PROBE_OBSERVED_BY)
    assert bounded.ratings == clean.ratings
    np.testing.assert_array_equal(bounded.elo_z(teams), clean.elo_z(teams))

    # POSITIVE CONTROL — the row is really there and really does move the
    # anchor. Drop the bound, which is what HEAD did, and Arsenal moves.
    unbounded = dcfit.anchor_state_at(leaked_anchor, PROBE_CUTOFF, teams)
    assert unbounded.ratings["arsenal"] != clean.ratings["arsenal"]
    assert not np.array_equal(unbounded.elo_z(teams), clean.elo_z(teams))


def test_live_fit_hands_the_knowledge_bound_to_the_dc_fit(
        live_anchor, season_obj, monkeypatch):
    """`live_fit` forwards `observed_by`; it does not stop at the frame.

    Exercised, not read: the fit is replaced by a recorder, so what is asserted
    is the argument the real `live_fit` body actually passes.
    """
    from epl import dcfit

    class _Stop(RuntimeError):
        pass

    seen: dict = {}

    def _recorder(cutoff, store, anchor, cfg, **kw):
        seen["cutoff"] = cutoff
        seen["observed_by"] = kw.get("observed_by", "<not passed>")
        raise _Stop

    monkeypatch.setattr(dcfit, "fit_epl", _recorder)
    monkeypatch.setattr(simcli, "_fitted_teams",
                        lambda cutoff, store, cfg: list(season_obj.manifest.clubs))
    _, archive = live_anchor
    with pytest.raises(_Stop):
        simcli.live_fit(season_obj, PROBE_CUTOFF, matches=archive,
                        store=object(), observed_by=PROBE_OBSERVED_BY,
                        verbose=False)
    assert seen["cutoff"] == PROBE_CUTOFF
    assert seen["observed_by"] == PROBE_OBSERVED_BY


def test_the_elo_arm_is_built_under_the_forecasts_knowledge_bound(
        live_anchor, leaked_anchor, leaked_season, book):
    """The Elo arm's anchor state AND its history frame respect the bound.

    Two surfaces, and both were unbounded: `fit.anchor.state(cutoff, clubs)` and
    `fit.anchor.history_frame(cutoff)`. The ratings feed the fixture edges and
    the history feeds the ordered logit, so a result filed after O changed the
    arm's prices twice over.
    """
    anchor, archive = live_anchor
    state = leaked_season.at(PROBE_CUTOFF, PROBE_OBSERVED_BY)
    assert state.played == {}, "the state itself already excludes the probe row"

    bridge = bridge_mod.EmpiricalBridge.fit(archive, PROBE_CUTOFF)
    fixtures = [state.fixtures[fid] for fid in sorted(state.fixtures)]

    def provider(anchor_obj):
        return simcli._provider(
            "elo_wdl_bridge",
            simcli.FitBundle(post=None, book=book, anchor=anchor_obj,
                             matches=archive, training=archive),
            bridge, state, PROBE_CUTOFF, N_PARTICLES)

    assert provider(leaked_anchor).content_hash() == provider(anchor).content_hash()

    # POSITIVE CONTROL — exactly what HEAD built: the anchor state and the
    # history frame taken at the cutoff with no knowledge bound at all.
    head = bridge_mod.EloOutcomeProvider.fit(
        leaked_anchor.state(PROBE_CUTOFF, list(state.clubs)),
        leaked_anchor.history_frame(PROBE_CUTOFF), fixtures, bridge,
        n_particles=N_PARTICLES)
    clean = provider(anchor)
    assert head.content_hash() != clean.content_hash()
    assert head.ratings["arsenal"] != clean.ratings["arsenal"]
    assert head.n_fit_rows != clean.n_fit_rows, (
        "the ordered logit's own fitting frame must be bounded too")


def test_an_archive_anchor_takes_no_knowledge_bound_and_is_not_refused(
        live_anchor):
    """A completed record has no known-at dimension, and says so by its signature.

    `epl.anchor.Anchor` is the archive's own snapshot table: there is nothing a
    later observation could reveal about a season that finished, so it takes no
    `observed_by` and needs none. Which of the two anchors we hold is read off
    the signature rather than guessed, and an object that answers to neither
    call is refused rather than quietly re-entered without the bound.
    """
    from epl import anchor as anchor_mod, dcfit, freeze

    _, archive = live_anchor
    arch = anchor_mod.Anchor(archive, freeze.frozen_elo_config())
    # Clubs the ARCHIVE holds: a promoted side has no archive rating, which is
    # the cold-start path and a different question from this one.
    teams = ["arsenal", "chelsea", "everton"]
    got = dcfit.anchor_state_at(arch, "2026-05-01", teams,
                                observed_by="2026-04-01")
    assert got.ratings == arch.state("2026-05-01", teams).ratings

    class _Opaque:
        def state(self, cutoff, teams):
            raise AssertionError("must not be called")

    with pytest.raises(season_mod.SeasonError, match="knowledge bound"):
        dcfit.anchor_state_at(_Opaque(), "2026-05-01", teams,
                              observed_by="2026-04-01")


# ==========================================================================
# G3 — what a `check` PASS is allowed to mean (amendment A6 (b);
# `gate-retro.md` #3 #4, `engine-pricing.md` #4, `live-forecast.md` #3 #4)
#
# Six coats on one defect: a check whose inputs are chosen by the thing being
# checked. The record's full digest was carried and never read, the two sidecars
# were written and never hashed, the gate report was never consulted, parity
# compared the sampler to a reference derived from the sampler's own book, and
# the issuance was written in place with `issuance.json` first.
# ==========================================================================

COMMITTED_OPENER = Path("data/epl/sim/issuances/2026_27/2026-08-21")


def _edit_json(path: Path, mutate) -> None:
    payload = json.loads(path.read_text())
    mutate(payload)
    path.write_text(leaguesim.canonical_json(payload) + "\n")


def test_check_reads_the_full_record_digest_and_an_edited_observed_by_FAILS(
        three_arm_issuance):
    """`gate-retro.md` #3: an edited `observed_by` left every check passing.

    `output_numbers_digest` covers the NUMBERS and excludes the envelope on
    purpose, so provenance — `observed_by`, `git_commit`, the results snapshot —
    was outside every comparison. The record already carried a digest over the
    whole payload; nothing read it.
    """
    directory = _copy(three_arm_issuance, "full_digest")
    clean = simcli.check_issuance(directory, verbose=False)
    cell = clean["arms"]["dc_native"]
    assert _criterion(cell, "published_output_full_digest")["status"] == "PASS"

    _edit_json(directory / "output_dc_native.json",
               lambda p: p["envelope"].__setitem__("observed_by", "2099-01-01"))
    tampered = simcli.check_issuance(directory, verbose=False)
    cell = tampered["arms"]["dc_native"]
    assert _criterion(cell, "published_output_full_digest")["status"] == "FAIL"
    assert _criterion(cell, "envelope_agrees_with_record")["status"] == "FAIL"
    assert tampered["PASS"] is False
    assert "dc_native" in tampered["failed"]


def _criterion(cell: dict, name: str) -> dict:
    for row in cell["criteria"]:
        if row["name"] == name:
            return row
    raise AssertionError(f"{name} is not among {[r['name'] for r in cell['criteria']]}")


def test_check_anchors_both_sidecars_and_recomputes_the_truncation_vector(
        three_arm_issuance):
    """`engine-pricing.md` #4: the retained rows and the full truncation vector
    were written and then excluded from the digest and the check.

    Two independent legs, exactly as A6 (b.2) states: the anchored bytes
    (`sidecar_digests`, new in `epl-issuance-4`), and a re-derivation that works
    on every schema. The residual — a doctored per-fixture vector that preserves
    every statistic the envelope carries — is what the anchor exists for.
    """
    directory = _copy(three_arm_issuance, "sidecars")
    record = json.loads((directory / "issuance.json").read_text())
    assert set(record["sidecar_digests"]) == set(simcli.ARMS)
    # A6 (b.2) pinned two sidecars per arm; A7 (b.1) adds the matchboard's two
    # to the PUBLISHED NATIVE ARM and to no other, which is (a)'s dc_native-only
    # rule showing up in the record rather than only in the check.
    assert set(record["sidecar_digests"]["dc_native"]) == {
        "rows", "excluded_mass", "matchboard", "matchboard_md"}
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        assert set(record["sidecar_digests"][arm]) == {"rows", "excluded_mass"}

    clean = simcli.check_issuance(directory, verbose=False)["arms"]["dc_native"]
    for name in ("retained_rows_anchored", "retained_rows_reproduce",
                 "truncation_sidecar_anchored", "truncation_sidecar_consistent"):
        assert _criterion(clean, name)["status"] == "PASS", name

    # (a) the retained rows: one flipped scoreline byte
    rows_path = directory / "rows_dc_native.npz"
    arrays = {k: v.copy() for k, v in np.load(rows_path).items()}
    arrays["scorelines"][0, 0, 0] += 1
    np.savez_compressed(rows_path, **arrays)
    broken = simcli.check_issuance(directory, verbose=False)["arms"]["dc_native"]
    assert _criterion(broken, "retained_rows_anchored")["status"] == "FAIL"
    assert _criterion(broken, "retained_rows_reproduce")["status"] == "FAIL"

    # (b) the truncation sidecar: a summary that no longer matches its vector
    directory = _copy(three_arm_issuance, "sidecars_b")
    _edit_json(directory / "excluded_mass_dc_native.json",
               lambda p: p["summary"].__setitem__("n_flagged", 99))
    broken = simcli.check_issuance(directory, verbose=False)["arms"]["dc_native"]
    assert _criterion(broken, "truncation_sidecar_anchored")["status"] == "FAIL"
    assert _criterion(broken, "truncation_sidecar_consistent")["status"] == "FAIL"


def test_check_refuses_a_bundle_that_cannot_show_it_passed_its_gate(
        three_arm_issuance, issuance):
    """`live-forecast.md` #3: a `--skip-oracle` issuance exits 3 on a failed gate
    and then `check`ed PASS afterwards, because `check` never read the gate.

    Three states, all of them not-a-pass: no gate report at all (REFUSED), a
    report whose own verdict is false (FAIL), and a report that disagrees with
    the record (FAIL).
    """
    # (a) `gate=False`: nothing to show. A refusal is not a pass.
    directory = _copy(three_arm_issuance, "no_gate")
    report = simcli.check_issuance(directory, verbose=False)
    verdict = _record_criterion(report, "acceptance_verdict")
    assert verdict["status"] == "REFUSED"
    assert report["PASS"] is False

    # (b) a gate that ran and did not pass — the fast gate SKIPs two criteria,
    #     and a SKIPPED criterion is not a passing one.
    directory = _copy(issuance, "failed_gate")
    assert json.loads((directory / "acceptance.json").read_text())["PASS"] is False
    report = simcli.check_issuance(directory, verbose=False)
    assert _record_criterion(report, "acceptance_verdict")["status"] == "FAIL"
    assert report["PASS"] is False

    # (c) a gate report edited to claim a pass the record does not record
    _edit_json(directory / "acceptance.json", lambda p: p.__setitem__("PASS", True))
    report = simcli.check_issuance(directory, verbose=False)
    assert _record_criterion(report, "acceptance_verdict")["status"] == "FAIL"

    # (d) POSITIVE CONTROL: agreeing and true.
    _edit_json(directory / "issuance.json", lambda p: p.__setitem__("gate_PASS", True))
    report = simcli.check_issuance(directory, verbose=False)
    assert _record_criterion(report, "acceptance_verdict")["status"] == "PASS"


def _record_criterion(report: dict, name: str) -> dict:
    for row in report["criteria"]:
        if row["name"] == name:
            return row
    raise AssertionError(f"{name} is not among {[r['name'] for r in report['criteria']]}")


def test_check_time_parity_uses_the_production_grid_or_refuses(three_arm_issuance):
    """`gate-retro.md` #4: parity passed `post=None`, so the reference was the
    book's own mixture and the production adapter was never called at check time.

    A CURRENT record that names a training frame but cannot be handed a
    posterior reproducing its anchored book REFUSES; hand it that posterior and
    the criterion is evaluated against `draw_api.production_grid`.
    """
    directory = _copy(three_arm_issuance, "parity")
    record = json.loads((directory / "issuance.json").read_text())
    # the version this criterion arrived with was `-4`; it is read from the
    # constant so a later bump moves the test rather than breaking it
    assert record["schema_version"] == simcli.ISSUANCE_SCHEMA_VERSION
    assert simcli.schema_ordinal(record["schema_version"]) >= 4
    # This issuance was made from a synthetic book with no posterior, so the
    # record pins no training frame and the criterion has nothing to hold it to.
    assert record["training_frame_sha256"] is None
    cell = simcli.check_issuance(directory, verbose=False)["arms"]["dc_native"]
    assert _criterion(cell, "parity_reference_is_production_grid")["status"] \
        == "UNANCHORED"

    # A record that DOES pin one, with no posterior available: REFUSED, which is
    # not a pass, and the arm is not a pass.
    _edit_json(directory / "issuance.json",
               lambda p: p.__setitem__("training_frame_sha256", "0" * 64))
    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    assert _criterion(cell, "parity_reference_is_production_grid")["status"] \
        == "REFUSED"
    assert cell["PASS"] is False


def test_an_interrupted_issuance_leaves_no_selectable_partial(book, tmp_path,
                                                              monkeypatch):
    """`live-forecast.md` #4: writes were in place and `issuance.json` came
    first, so an interruption left a stale or missing `summary.md` beside a
    record that `_last_issuance` still selected.

    Everything is written to a staging directory OUTSIDE the season's issuance
    folder and moved into place in one step, with `issuance.json` written last.
    """
    out_root = tmp_path / "issuances"
    good = simcli.forecast(
        season=SEASON, cutoff=OPENER, arms=("dc_native",), n_sims=N_SIMS,
        seed=SEED, chunk_size=CHUNK, n_particles=N_PARTICLES, out_root=out_root,
        gate=False, verbose=False, fit=simcli.FitBundle(post=None, book=book))
    before = (Path(good["directory"]) / "issuance.json").read_text()

    boom = RuntimeError("the machine went away mid-issuance")

    def _explode(*args, **kwargs):
        raise boom

    monkeypatch.setattr(simcli, "summary_markdown", _explode)
    with pytest.raises(RuntimeError):
        simcli.forecast(
            season=SEASON, cutoff=OPENER, arms=("dc_native",), n_sims=N_SIMS,
            seed=SEED + 1, chunk_size=CHUNK, n_particles=N_PARTICLES,
            out_root=out_root, gate=False, verbose=False,
            fit=simcli.FitBundle(post=None, book=book))

    # The last issuance is still the one that completed, byte for byte.
    selected = simcli._last_issuance(SEASON, out_root)
    assert (selected / "issuance.json").read_text() == before
    # ...and nothing half-written is sitting in the season's folder.
    season_dir = out_root / season_mod.season_dir_name(SEASON)
    assert sorted(p.name for p in season_dir.iterdir()) == [
        pd.Timestamp(OPENER).date().isoformat()]


def test_the_record_digest_is_written_in_both_copies_and_checked(
        three_arm_issuance):
    """A6 (b.1): the record's own fields — `published_arm`, `arms`, `files`,
    `gate_PASS` — are covered by `record_digest`, written into `issuance.json`
    and printed in `summary.md`, and `check` requires both copies to agree.

    A6 states the limit rather than overselling it: a digest a file carries about
    itself is a checksum against accident, not a seal against an editor who
    updates every copy. The repository history is what catches that.
    """
    directory = _copy(three_arm_issuance, "record_digest")
    report = simcli.check_issuance(directory, verbose=False)
    assert _record_criterion(report, "record_digest")["status"] == "PASS"
    record = json.loads((directory / "issuance.json").read_text())
    assert record["record_digest"] in (directory / "summary.md").read_text()

    # Edit one field the digest covers and leave both copies of the digest alone.
    _edit_json(directory / "issuance.json",
               lambda p: p.__setitem__("published_arm", "elo_wdl_bridge"))
    report = simcli.check_issuance(directory, verbose=False)
    assert _record_criterion(report, "record_digest")["status"] == "FAIL"
    assert report["PASS"] is False


@pytest.mark.skipif(not COMMITTED_OPENER.exists(),
                    reason="the committed opener bundle is not present")
def test_the_committed_opener_reports_exactly_the_pre_A6_criteria_unanchored():
    """A6 (b.5), pre-stated by criterion, held against the bundle as committed.

    The published issuance is `epl-issuance-1`. It is not re-issued, not re-run
    and not edited: it stays verifiable for exactly what its record can support,
    and it can never report `fully_anchored`.
    """
    report = simcli.check_issuance(COMMITTED_OPENER, arms=("dc_native",),
                                   verbose=False)
    assert report["fully_anchored"] is False
    assert set(report["unanchored"]) == {
        "record_digest", "acceptance_digest",
        "dc_native.retained_rows_anchored",
        "dc_native.truncation_sidecar_anchored",
        "dc_native.parity_reference_is_production_grid",
        "dc_native.matchboard_anchored",
        "dc_native.matchboard_reproduces"}

    # A7: the record predates TWO rounds now, so a blanket
    # `note == PRE_A6_NOTE` is no longer true and "one of the two notes" is not
    # an acceptable replacement — that is the shape of check that stops being
    # able to fail. Every UNANCHORED entry is named, with the note it must
    # carry, and the two matchboard entries carry PRE_A7_NOTE specifically.
    assert _unanchored_notes(report) == {
        "record_digest": simcli.PRE_A6_NOTE,
        "acceptance_digest": simcli.PRE_A6_NOTE,
        "dc_native.retained_rows_anchored": simcli.PRE_A6_NOTE,
        "dc_native.truncation_sidecar_anchored": simcli.PRE_A6_NOTE,
        "dc_native.parity_reference_is_production_grid": simcli.PRE_A6_NOTE,
        "dc_native.matchboard_anchored": simcli.PRE_A7_NOTE,
        "dc_native.matchboard_reproduces": simcli.PRE_A7_NOTE,
    }
    assert simcli.PRE_A7_NOTE != simcli.PRE_A6_NOTE

    cell = report["arms"]["dc_native"]
    assert cell["detail"]["digest_matches"] is True
    for name in ("published_output_full_digest", "envelope_agrees_with_record",
                 "truncation_sidecar_consistent", "retained_rows_reproduce"):
        assert _criterion(cell, name)["status"] == "PASS", name
    assert _record_criterion(report, "acceptance_verdict")["status"] == "PASS"


#: Every UNANCHORED entry the DEFAULT `check` command reports for the committed
#: opener. A6 (b.5) pre-stated five criterion NAMES; the landed code reports
#: those five names as NINE per-arm entries. The deviation is recorded in the
#: ledger's "What landed for A6 (b)" note and pinned by the test below.
#:
#: A7 pre-stated the move from nine to ELEVEN: two additions, both namespaced to
#: `dc_native` and neither to a bridge arm, which is (a)'s `dc_native`-only rule
#: showing up in the output. The `--arm dc_native` run goes from five to seven.
COMMITTED_OPENER_UNANCHORED = {
    "record_digest",
    "acceptance_digest",
    "dc_native.retained_rows_anchored",
    "dc_native.truncation_sidecar_anchored",
    "dc_native.parity_reference_is_production_grid",
    "dc_native.matchboard_anchored",
    "dc_native.matchboard_reproduces",
    "dc_wdl_bridge.retained_rows_anchored",
    "dc_wdl_bridge.truncation_sidecar_anchored",
    "elo_wdl_bridge.retained_rows_anchored",
    "elo_wdl_bridge.truncation_sidecar_anchored",
}


def _unanchored_notes(report: dict) -> dict[str, str]:
    """Every UNANCHORED entry the report carries, mapped to its own note.

    Record-level entries keep their bare name and arm-level entries are
    namespaced `<arm>.<criterion>`, exactly as `check` writes them into
    `report["unanchored"]` — so a test written against this map is written
    against the strings a reader sees.
    """
    notes = {row["name"]: row["note"] for row in report["criteria"]
             if row["status"] == simcli.UNANCHORED}
    notes.update({f"{arm}.{row['name']}": row["note"]
                  for arm, cell in report["arms"].items()
                  for row in cell["criteria"]
                  if row["status"] == simcli.UNANCHORED})
    return notes


def _ledger_section(head: str) -> str:
    """One `###` section of the amendment ledger, alone.

    The window ends at the next heading of either level, which is why A7's own
    sections must stay at the END of the file: a `## A7` heading dropped inside
    the A6 (b) window would truncate that note at the heading and the
    ledger-coupled tests below would be quoting half a transcript.
    """
    path = (Path(simcli.__file__).resolve().parents[1] / "reports"
            / "epl_sim_amendments.md")
    if not path.exists():                                   # pragma: no cover
        pytest.skip("reports/ is not in this checkout")
    text = path.read_text(encoding="utf-8")
    start = text.find(head)
    assert start != -1, f"{path} carries no {head!r} section"
    rest = text[start + len(head):]
    for nxt in ("\n### ", "\n## "):
        cut = rest.find(nxt)
        if cut != -1:
            rest = rest[:cut]
    return rest


#: The A6 (b) landed note — the record of what `check` emitted on 2026-08-20,
#: under the code as it then stood. A1-C1's rule applies to it: it is not edited
#: when the output moves. A7 appends a NEW dated note instead.
A6_B_HEAD = "### What landed for A6 (b) — `check` semantics"
A7_HEAD = "### What landed for A7 — `check` under the matchboard"


def _a6_b_note() -> str:
    return _ledger_section(A6_B_HEAD)


def _a7_note() -> str:
    return _ledger_section(A7_HEAD)


def _check_stderr_lines(report: dict) -> list[str]:
    """Exactly the lines `_cmd_check` writes to stderr for `report`.

    Built from the report the command prints them from (`epl/simcli.py:2474`),
    so a transcript quoted in the ledger is held against what the code emits
    rather than against a memory of what it emitted.
    """
    lines = []
    for arm, cell in report["arms"].items():
        error = cell["detail"].get("error")
        suffix = f" — {error}" if cell["status"] != "PASS" and error else ""
        lines.append(f"[check] {arm}: {cell['status']}{suffix}")
    for row in report["criteria"]:
        if row["status"] != "PASS":
            suffix = f" — {row['note']}" if row["note"] else ""
            lines.append(f"[check] {row['name']}: {row['status']}{suffix}")
    line = f"[check] {report['headline']}"
    if not report["fully_anchored"]:
        line += "; unanchored: " + ", ".join(report["unanchored"])
    lines.append(line)
    return lines


def test_the_committed_opener_whole_bundle_check_is_FAIL_and_the_ledger_says_so():
    """A6 (b.5) held against the DOCUMENTED command, and against the note that
    quotes it.

    The narrowed test above passes `arms=("dc_native",)`, which is a different
    question with a different answer. The documented command asks about the
    whole bundle, whose two bridge arms are REFUSED for want of sidecars: its
    headline is `FAIL`, its exit code is 4, and its unanchored list is
    namespaced per arm and nine entries long. The ledger's "What landed for
    A6 (b)" note quoted the NARROWED transcript under the whole-bundle command
    and called the headline a PASS — a report saying something the code does
    not say, which is the failure class `a2b1ead` was written to close, and one
    the narrowed test could not catch because it narrows the same way. So this
    measures both runs and holds every line of the note's two fenced blocks
    against them.

    **A7 moved the output and NOT A6's record of it.** Two criteria that report
    UNANCHORED on this pre-A7 record take the whole-bundle list from nine
    entries to eleven and the narrowed list from five to seven, and the
    narrowed headline's parenthetical now names two rounds. A6 (b)'s fenced
    blocks are what the command emitted on 2026-08-20 under the code as it then
    stood, and A1-C1 says a superseded statement stays where it was written. So
    the ledger source here moves to a NEW dated note under A7, and
    `test_the_A6_b_transcripts_are_present_and_unedited` holds A6's blocks in
    place — the A2-N3 pattern.
    """
    whole = simcli.check_issuance(COMMITTED_OPENER, verbose=False)
    narrowed = simcli.check_issuance(COMMITTED_OPENER, arms=("dc_native",),
                                     verbose=False)

    # 1. THE BUNDLE FAILS — and not for a new reason. Nothing FAILED; the two
    #    bridge arms are REFUSED exactly as they were before A6 existed, that
    #    bundle carrying no arm sidecars to be rebuilt from.
    assert whole["PASS"] is False
    assert whole["headline"] == "FAIL"
    assert whole["fully_anchored"] is False
    assert whole["failed"] == [] and whole["record_failed"] == []
    assert whole["record_refused"] == []
    assert sorted(whole["refused"]) == ["dc_wdl_bridge", "elo_wdl_bridge"]
    assert whole["arms"]["dc_native"]["status"] == "PASS"
    assert whole["arms"]["dc_native"]["detail"]["digest_matches"] is True

    # 2. SEVEN NAMES, ELEVEN ENTRIES — A6 (b.5)'s deviation (criteria counted,
    #    entries reported) carried forward, with A7's two additions namespaced
    #    to `dc_native` and to no bridge arm.
    assert set(whole["unanchored"]) == COMMITTED_OPENER_UNANCHORED
    assert len(COMMITTED_OPENER_UNANCHORED) == 11
    assert {entry.rsplit(".", 1)[-1]
            for entry in COMMITTED_OPENER_UNANCHORED} == {
        "record_digest", "acceptance_digest", "retained_rows_anchored",
        "truncation_sidecar_anchored", "parity_reference_is_production_grid",
        "matchboard_anchored", "matchboard_reproduces"}
    assert {e for e in whole["unanchored"] if "matchboard" in e} == {
        "dc_native.matchboard_anchored", "dc_native.matchboard_reproduces"}

    # 3. The narrowed run reports a strict subset of them, under a PASS
    #    headline that belongs to it and not to the bundle. The parenthetical
    #    is the sorted distinct set of the entries' own reasons, so it names
    #    both rounds this record predates.
    assert narrowed["PASS"] is True
    assert narrowed["headline"] == \
        "PASS (7 criteria unanchored: pre-A6 record, pre-A7 record)"
    assert set(narrowed["unanchored"]) < COMMITTED_OPENER_UNANCHORED
    assert len(narrowed["unanchored"]) == 7

    # 4. THE LEDGER QUOTES BOTH RUNS, LINE FOR LINE, AND NAMES THE NARROWING.
    note = _a7_note()
    for report in (whole, narrowed):
        for line in _check_stderr_lines(report):
            assert line in note, f"the A7 note does not carry: {line}"
    record = json.loads((COMMITTED_OPENER / "issuance.json").read_text())
    assert (f"[check] re-running dc_native at {record['cutoff']} "
            f"(N={record['n_sims']}, seed={record['seed']})") in note
    assert "--arm dc_native" in note, \
        "the note quotes a narrowed run without naming the option that narrows it"

    # 5. TWO BLOCKS, IN THAT ORDER, EACH CLAIMING THE EXIT CODE `_cmd_check`
    #    returns for it (`epl/simcli.py:2487`). The narrowed block is the one
    #    that carries the option that narrows it.
    blocks = [b for i, b in enumerate(note.split("```")) if i % 2 == 1]
    assert len(blocks) == 2, f"the note carries {len(blocks)} fenced blocks, not 2"
    assert "--arm dc_native" not in blocks[0]
    assert "--arm dc_native" in blocks[1]
    for block, report in zip(blocks, (whole, narrowed)):
        assert block.rstrip().splitlines()[-1].strip() == \
            ("0" if report["PASS"] else "4")

    # POSITIVE CONTROLS: the containment checks are not vacuous, and the note
    # is not merely long enough to contain anything shaped like a transcript.
    whole_headline = _check_stderr_lines(whole)[-1]
    drifted = note.replace("dc_wdl_bridge.retained_rows_anchored",
                           "dc_wdl_bridge.retained_rows_unanchored")
    assert whole_headline not in drifted, \
        "a drifted entry name must break the quotation this test checks"
    assert whole_headline.replace("FAIL", "PASS") not in note, \
        "the whole-bundle line must be quoted with the headline the code emits"


def test_the_A6_b_transcripts_are_present_and_unedited():
    """A1-C1 and the A2-N3 pattern: a superseded statement stays where it was
    written and is superseded rather than erased.

    A7 changed what `check` emits for the committed opener, and the honest way
    to record that is a new dated note — not a quiet edit to the block that says
    what the command emitted on 2026-08-20. So A6 (b)'s two blocks are held
    here, exactly as they stood: nine entries, the five pre-A6 names, and the
    narrowed headline naming one round. Every one of those strings is now FALSE
    of the running code, which is precisely why nothing may rewrite them.
    """
    note = _a6_b_note()
    blocks = [b for i, b in enumerate(note.split("```")) if i % 2 == 1]
    assert len(blocks) == 2, f"the note carries {len(blocks)} fenced blocks, not 2"

    # the 2026-08-20 whole-bundle list: NINE entries, and no matchboard among them
    assert ("[check] FAIL; unanchored: acceptance_digest, "
            "dc_native.parity_reference_is_production_grid, "
            "dc_native.retained_rows_anchored, "
            "dc_native.truncation_sidecar_anchored, "
            "dc_wdl_bridge.retained_rows_anchored, "
            "dc_wdl_bridge.truncation_sidecar_anchored, "
            "elo_wdl_bridge.retained_rows_anchored, "
            "elo_wdl_bridge.truncation_sidecar_anchored, "
            "record_digest") in blocks[0]
    # the 2026-08-20 narrowed headline: FIVE, one round named
    assert "PASS (5 criteria unanchored: pre-A6 record)" in blocks[1]
    assert "matchboard" not in note
    assert "five names, nine entries" in note

    # POSITIVE CONTROL, and it needs no bundle: those strings are STALE. The
    # live entry set is eleven and names A7's two criteria, and the note that
    # quotes nine knows nothing about the note A7 added — which is what makes
    # this an unedited record rather than a maintained one.
    assert len(COMMITTED_OPENER_UNANCHORED) == 11
    assert simcli.PRE_A7_NOTE not in note
    assert simcli.PRE_A6_NOTE in note


# ==========================================================================
# G5 — the vocabulary rename is a rename, and the cut lines carry an error
# (`engine-pricing.md` #5 #6, `gate-retro.md` #5, `ranker.md` #4)
# ==========================================================================

def test_a_pre_rename_acceptance_report_is_still_recognised():
    """`matrix_and_markets` became `matrix_and_thresholds` under the standing
    vocabulary rule, and an `acceptance.json` written before the rename is a
    RECORD of a gate that ran — not a file to be rewritten to match a later
    vocabulary.

    So: nothing WRITES the old spelling, and everything that READS an acceptance
    report accepts either.
    """
    assert "matrix_and_thresholds" in simcli.GATE_CRITERIA
    assert "matrix_and_markets" not in simcli.GATE_CRITERIA
    assert simcli.GATE_CRITERIA_COMPAT["matrix_and_thresholds"] == \
        "matrix_and_markets"

    old = {"criteria": {name: {"status": "PASS", "PASS": True}
                        for name in simcli.GATE_CRITERIA}}
    old["criteria"]["matrix_and_markets"] = old["criteria"].pop(
        "matrix_and_thresholds")
    assert simcli.acceptance_criterion(old, "matrix_and_thresholds") == {
        "status": "PASS", "PASS": True}
    assert simcli.acceptance_criteria_present(old) == set(simcli.GATE_CRITERIA)

    new = {"criteria": {name: {"status": "PASS", "PASS": True}
                        for name in simcli.GATE_CRITERIA}}
    assert simcli.acceptance_criteria_present(new) == set(simcli.GATE_CRITERIA)

    # POSITIVE CONTROL: the compat map is not a wildcard. A report that is
    # genuinely missing a criterion is genuinely missing it, under either name.
    holed = {"criteria": {k: v for k, v in new["criteria"].items()
                          if k != "mc_uncertainty"}}
    assert "mc_uncertainty" not in simcli.acceptance_criteria_present(holed)
    assert simcli.acceptance_criterion(holed, "mc_uncertainty") is None


def test_check_refuses_an_acceptance_report_missing_a_criterion(tmp_path):
    """A6 (b.3) + the rename: `check` reads the gate report, and a report that
    does not cover the eleven criteria has not shown the gate ran.
    """
    directory = tmp_path / "issuance"
    directory.mkdir()
    record = {"gate_PASS": True}

    full = {"schema_version": simcli.GATE_SCHEMA_VERSION, "PASS": True,
            "failed": [], "skipped": [],
            "criteria": {name: {"status": "PASS", "PASS": True}
                         for name in simcli.GATE_CRITERIA}}
    (directory / "acceptance.json").write_text(json.dumps(full))
    assert simcli._check_acceptance(directory, record)["status"] == "PASS"

    # the SAME report under the pre-rename spelling still passes
    old = json.loads(json.dumps(full))
    old["criteria"]["matrix_and_markets"] = old["criteria"].pop(
        "matrix_and_thresholds")
    old["schema_version"] = "epl-acceptance-1"
    (directory / "acceptance.json").write_text(json.dumps(old))
    assert simcli._check_acceptance(directory, record)["status"] == "PASS"

    # a report genuinely short of a criterion FAILs and names it
    holed = json.loads(json.dumps(full))
    holed["criteria"].pop("lock_valid")
    (directory / "acceptance.json").write_text(json.dumps(holed))
    verdict = simcli._check_acceptance(directory, record)
    assert verdict["status"] == "FAIL"
    assert verdict["detail"]["criteria_absent"] == ["lock_valid"]


def test_the_summary_cut_line_table_states_its_monte_carlo_method():
    """`engine-pricing.md` #5: the cut-line headlines carried no error at all.

    The rendered table now carries a bracket per quantile AND the method under
    it — an interval whose method is not stated is a decoration (A2-N4).
    """
    method = leaguesim.CUT_LINE_INTERVAL_METHOD
    assert "order-statistic" in method
    assert "Binomial" in method
    assert "exchangeable" in method
    assert "cluster-robust" in method
    assert "model error" in method


# ==========================================================================
# A7 — the matchboard is published, anchored, and re-derived by `check`
# ==========================================================================
#
# The matchboard is exactly the kind of file A6 found six coats of one defect
# on: a derived, human-readable artefact that no digest covers and that a reader
# trusts because it looks like output. So it arrives with both legs at once —
# its bytes under `sidecar_digests`, and a re-derivation from the rows on the
# way in — and each test below pairs the leg with the tampering only that leg
# can catch.

def test_forecast_publishes_the_matchboard_and_the_record_anchors_it(issuance):
    """A7 (a) + (b.1): a required sidecar, hashed AS WRITTEN, and named in
    `files` so `record_digest` covers that it was published at all."""
    directory = Path(issuance["directory"])
    board_path = directory / matchboard.JSON_FILENAME
    md_path = directory / matchboard.MD_FILENAME
    assert board_path.exists() and md_path.exists()

    record = json.loads((directory / "issuance.json").read_text())
    assert record["schema_version"] == "epl-issuance-5"
    sidecars = record["sidecar_digests"]["dc_native"]
    assert sidecars["matchboard"] == simcli.sha256_file(board_path)
    assert sidecars["matchboard_md"] == simcli.sha256_file(md_path)
    assert matchboard.JSON_FILENAME in record["files"]["dc_native"]
    assert matchboard.MD_FILENAME in record["files"]["dc_native"]

    board = json.loads(board_path.read_text())
    assert board["schema_version"] == matchboard.SCHEMA_VERSION
    assert board["arm"] == "dc_native"
    # A7 (a): a matchboard that prices a different number of fixtures than the
    # run had is not the run's matchboard.
    assert board["n_fixtures"] == record["n_unplayed"] == len(board["rows"])
    assert board["n_sims"] == record["n_sims"] == N_SIMS
    assert board["n_particles"] == record["n_particles"] == N_PARTICLES
    assert board["run_digest"] == record["digests"]["dc_native"]
    assert board["effective_posterior_hash"] == \
        record["effective_posterior_hash"]
    # the rows ARE anchored for a post-A7 record, and the render says the right
    # one of A7 (d)'s two sentences
    assert board["rows_provenance"] == "anchored"
    assert matchboard.ROWS_ANCHORED_NOTE in md_path.read_text()

    # POSITIVE CONTROL for every tamper test below: untampered, both criteria
    # PASS and nothing about the matchboard is unanchored.
    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    for name in ("matchboard_anchored", "matchboard_reproduces"):
        assert _criterion(cell, name)["status"] == "PASS", name
    assert [e for e in report["unanchored"] if "matchboard" in e] == []
    assert _blocked_only_by_the_gate(report)


def test_a_matchboard_whose_numbers_moved_fails_both_legs(issuance):
    """A7 (b.3): tampering that touches a number fails the re-derivation as well
    as the bytes."""
    directory = _copy(issuance, "matchboard_number")
    _edit_json(directory / matchboard.JSON_FILENAME,
               lambda p: p["rows"][0]["probs"].__setitem__("home", 0.99))
    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    assert _criterion(cell, "matchboard_anchored")["status"] == "FAIL"
    reproduces = _criterion(cell, "matchboard_reproduces")
    assert reproduces["status"] == "FAIL"
    assert reproduces["detail"]["differing_rows"], \
        "the re-derivation must name what moved, not merely disagree"
    assert report["PASS"] is False
    assert "dc_native" in report["failed"]


def test_a_matchboard_doctored_to_preserve_every_number_still_fails(issuance):
    """A7 (b.3): the bit-level leg is *the only one that catches a doctored file
    preserving every recomputable quantity*.

    Rewritten with different bytes and identical content — pretty-printed rather
    than canonical. Every number a re-derivation could check is still exactly
    right, and the file is still not the file the record published.
    """
    directory = _copy(issuance, "matchboard_bytes")
    path = directory / matchboard.JSON_FILENAME
    payload = json.loads(path.read_text())
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    anchored = _criterion(cell, "matchboard_anchored")
    assert anchored["status"] == "FAIL"
    assert anchored["detail"]["recorded"] != anchored["detail"]["recomputed"]
    # ...and the semantic leg is untroubled, which is the point of having two
    assert _criterion(cell, "matchboard_reproduces")["status"] == "PASS"
    assert report["PASS"] is False


def test_an_edited_matchboard_render_fails_the_anchor(issuance):
    """`matchboard_md` is anchored too: the human-readable half is the half a
    reader quotes."""
    directory = _copy(issuance, "matchboard_md")
    path = directory / matchboard.MD_FILENAME
    path.write_text(path.read_text().replace(matchboard.NO_CLAIM,
                                             "these numbers are accurate"))
    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    anchored = _criterion(cell, "matchboard_anchored")
    assert anchored["status"] == "FAIL"
    assert matchboard.MD_FILENAME in anchored["note"]
    # the JSON is untouched, so the re-derivation has nothing to complain about
    assert _criterion(cell, "matchboard_reproduces")["status"] == "PASS"


def test_a_deleted_matchboard_on_a_post_A7_record_fails_naming_the_file(issuance):
    """A7 (b.3): a deleted sidecar on a record whose schema requires one is a
    FAIL naming the missing file — never a silent pass and never UNANCHORED."""
    directory = _copy(issuance, "matchboard_gone")
    (directory / matchboard.JSON_FILENAME).unlink()
    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    anchored = _criterion(cell, "matchboard_anchored")
    assert anchored["status"] == "FAIL"
    assert matchboard.JSON_FILENAME in anchored["note"]
    assert _criterion(cell, "matchboard_reproduces")["status"] == "FAIL"
    assert [e for e in report["unanchored"] if "matchboard" in e] == []
    assert report["PASS"] is False


def test_a_post_A7_record_carrying_a_null_matchboard_digest_fails(issuance):
    """A7 (b.4): A6's absent-vs-present-and-null leniency does NOT apply here.

    `null` is the issuer saying there was nothing to pin, and for `dc_native`
    there is always something to pin — a season with no unplayed fixtures writes
    `n_fixtures: 0` and an empty row array, which is present.
    """
    for label, mutate in (
            ("matchboard_null",
             lambda p: p["sidecar_digests"]["dc_native"].__setitem__(
                 "matchboard", None)),
            ("matchboard_absent",
             lambda p: p["sidecar_digests"]["dc_native"].pop("matchboard")),
            ("matchboard_md_null",
             lambda p: p["sidecar_digests"]["dc_native"].__setitem__(
                 "matchboard_md", None))):
        directory = _copy(issuance, label)
        path = directory / "issuance.json"
        record = json.loads(path.read_text())
        mutate(record)
        path.write_text(json.dumps(_restamp(record)))

        report = simcli.check_issuance(directory, verbose=False)
        cell = report["arms"]["dc_native"]
        anchored = _criterion(cell, "matchboard_anchored")
        assert anchored["status"] == "FAIL", label
        assert "sidecar_digests" in anchored["note"] or \
            "matchboard" in anchored["note"], label
        assert report["PASS"] is False, label


def test_a_pre_A7_record_reports_the_matchboard_criteria_unanchored(issuance):
    """A7 (c): a pre-A7 record has no matchboard BY CONSTRUCTION, and `check`
    says exactly that. Never FAIL, and never a pass either."""
    directory = _copy(issuance, "pre_a7")
    path = directory / "issuance.json"
    record = json.loads(path.read_text())
    record["schema_version"] = "epl-issuance-4"
    for key in ("matchboard", "matchboard_md"):
        record["sidecar_digests"]["dc_native"].pop(key)
    record["files"]["dc_native"] = [
        n for n in record["files"]["dc_native"] if "matchboard" not in n]
    path.write_text(json.dumps(_restamp(record)))
    (directory / matchboard.JSON_FILENAME).unlink()
    (directory / matchboard.MD_FILENAME).unlink()

    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    for name in ("matchboard_anchored", "matchboard_reproduces"):
        row = _criterion(cell, name)
        assert row["status"] == simcli.UNANCHORED, name
        assert row["note"] == simcli.PRE_A7_NOTE, name
    assert simcli.PRE_A7_NOTE == "unanchored (pre-A7 record)"
    assert report["fully_anchored"] is False
    assert {"dc_native.matchboard_anchored",
            "dc_native.matchboard_reproduces"} <= set(report["unanchored"])
    # UNANCHORED is not FAIL: the record predates the field, and saying the
    # published issuance is wrong for lacking it would be false.
    assert report["failed"] == []
    assert "matchboard_anchored" not in str(report["record_failed"])

    # ...and the A6 fields on the same -4 record are still MANDATORY, so the
    # schema bump did not downgrade the round before this one.
    stripped = _copy(issuance, "pre_a7_no_sidecars")
    path = stripped / "issuance.json"
    record = json.loads(path.read_text())
    record["schema_version"] = "epl-issuance-4"
    record.pop("sidecar_digests")
    path.write_text(json.dumps(_restamp(record)))
    downgraded = simcli.check_issuance(stripped, verbose=False)
    rows = downgraded["arms"]["dc_native"]["criteria"]
    assert _criterion({"criteria": rows}, "retained_rows_anchored")["status"] \
        == "FAIL"


def test_a_derived_artifact_inside_a_bundle_is_refused(issuance):
    """A7 (c): a derived artifact can never drift into a bundle and be mistaken
    for a sidecar the record anchors."""
    directory = _copy(issuance, "derived_inside")
    stray = matchboard.derived_filename(SEASON, OPENER, "json")
    (directory / stray).write_text("{}")
    report = simcli.check_issuance(directory, verbose=False)
    anchored = _criterion(report["arms"]["dc_native"], "matchboard_anchored")
    assert anchored["status"] == "FAIL"
    assert stray in anchored["note"]
    assert anchored["detail"]["derived_artifacts"] == [stray]
    assert report["PASS"] is False


def test_check_never_namespaces_a_matchboard_criterion_to_a_bridge_arm(
        three_arm_issuance):
    """A7 (a), on A6 (d): a bridge arm's SCORELINES are the bridge's league-wide
    conditional wearing a fixture's name, and every margin field is computed
    from scorelines. So there is no bridge matchboard and no bridge criterion —
    not a partial surface with three meaningful columns and four decorative
    ones."""
    directory = Path(three_arm_issuance["directory"])
    assert {p.name for p in directory.glob("matchboard*")} == {
        matchboard.JSON_FILENAME, matchboard.MD_FILENAME}

    record = json.loads((directory / "issuance.json").read_text())
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        assert set(record["sidecar_digests"][arm]) == {"rows", "excluded_mass"}, arm

    report = simcli.check_issuance(directory, verbose=False)
    for arm in ("dc_wdl_bridge", "elo_wdl_bridge"):
        names = [row["name"] for row in report["arms"][arm]["criteria"]]
        assert [n for n in names if "matchboard" in n] == [], arm
    assert [n for n in (row["name"] for row in
                        report["arms"]["dc_native"]["criteria"])
            if "matchboard" in n] == ["matchboard_anchored",
                                      "matchboard_reproduces"]


def test_the_matchboard_is_byte_identical_when_derived_from_the_bundle_again(
        issuance):
    """Determinism, on the file that was actually published: `check`'s
    re-derivation is only a check if deriving twice gives the same answer."""
    directory = Path(issuance["directory"])
    published = (directory / matchboard.JSON_FILENAME).read_bytes()
    for _ in range(2):
        again = (leaguesim.canonical_json(matchboard.derive(directory))
                 + "\n").encode("utf-8")
        assert again == published


def test_a_failure_to_write_the_matchboard_aborts_the_whole_issuance(
        book, tmp_path, monkeypatch):
    """A7 (a): the matchboard is REQUIRED, and (b.2) puts it on the staged path.

    So a matchboard that cannot be written leaves no issuance at all — not a
    bundle missing one sidecar, and not a half-written file in the season's
    folder. The previous issuance stays selectable, byte for byte.
    """
    out_root = tmp_path / "issuances"
    good = simcli.forecast(
        season=SEASON, cutoff=OPENER, arms=("dc_native",), n_sims=N_SIMS,
        seed=SEED, chunk_size=CHUNK, n_particles=N_PARTICLES, out_root=out_root,
        gate=False, verbose=False, fit=simcli.FitBundle(post=None, book=book))
    directory = Path(good["directory"])
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert matchboard.JSON_FILENAME in before

    def _explode(*args, **kwargs):
        raise RuntimeError("the matchboard could not be rendered")

    monkeypatch.setattr(matchboard, "render_markdown", _explode)
    with pytest.raises(RuntimeError):
        simcli.forecast(
            season=SEASON, cutoff=OPENER, arms=("dc_native",), n_sims=N_SIMS,
            seed=SEED + 1, chunk_size=CHUNK, n_particles=N_PARTICLES,
            out_root=out_root, gate=False, verbose=False,
            fit=simcli.FitBundle(post=None, book=book))

    season_dir = out_root / season_mod.season_dir_name(SEASON)
    assert sorted(p.name for p in season_dir.iterdir()) == [
        pd.Timestamp(OPENER).date().isoformat()]
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_the_matchboard_subcommand_derives_from_a_bundle_without_touching_it(
        issuance, tmp_path):
    """`simcli matchboard --directory <bundle> --out <dir>`.

    A post-A7 bundle already carries its own, so the derivation goes to `--out`
    under the derived name and the bundle is not written to at all.
    """
    directory = Path(issuance["directory"])
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    out = tmp_path / "derived"
    code = simcli.main(["matchboard", "--directory", str(directory),
                        "--out", str(out)])
    assert code == 0
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before

    name = matchboard.derived_filename(SEASON, OPENER, "json")
    payload = json.loads((out / name).read_text())
    assert payload["derived"] is True
    assert payload["source_bundle"] == str(directory)
    assert payload["derived_at"]
    record = json.loads((directory / "issuance.json").read_text())
    # the source bundle's RECORDED hashes, copied from its record rather than
    # recomputed here: a hash this run computes today is not a hash that record
    # made when it was written
    assert payload["source_recorded_hashes"]["digests"]["dc_native"] == \
        record["digests"]["dc_native"]
    assert payload["source_recorded_hashes"]["effective_posterior_hash"] == \
        record["effective_posterior_hash"]

    md = (out / matchboard.derived_filename(SEASON, OPENER, "md")).read_text()
    first = md.splitlines()[0]
    assert "derived" in first.lower() and "not part of" in first.lower()

    # A7 (d): TWO kinds of provenance, and the text says BOTH. The law's kind is
    # computed from this repository's history rather than asserted; the rows'
    # kind comes out of the record. A post-A7 bundle pins its own rows, so this
    # one says so — and the two sentences are never the same sentence.
    anchor = payload["law_anchor"]
    assert {h["name"] for h in anchor["hashes"]} == {
        "effective_posterior_hash", "run_digest"}
    assert anchor["cutoff"] == record["cutoff"]
    assert payload["rows_provenance"] == "anchored"
    assert matchboard.ROWS_ANCHORED_NOTE in md
    assert matchboard.ROWS_REPRODUCTION_NOTE not in md
    note = (matchboard.LAW_ANCHORED_NOTE if anchor["pre_kickoff"]
            else matchboard.LAW_UNANCHORED_NOTE)
    assert note in md
    other = (matchboard.LAW_UNANCHORED_NOTE if anchor["pre_kickoff"]
             else matchboard.LAW_ANCHORED_NOTE)
    assert other not in md
    # a test bundle's hashes are in no tracked file, so this one anchors nothing
    # — which is the honest answer and the one that makes the MW0 answer mean
    # something
    assert anchor["pre_kickoff"] is False

    # the rows of a DERIVED artifact are the rows of the bundle it came from
    assert [r["fixture_id"] for r in payload["rows"]] == [
        r["fixture_id"] for r in
        json.loads((directory / matchboard.JSON_FILENAME).read_text())["rows"]]


def test_the_matchboard_subcommand_scores_results_into_ledger_rows(
        issuance, tmp_path):
    """`--score <results.jsonl>` — A7 (e), which reports and decides nothing."""
    directory = Path(issuance["directory"])
    board = json.loads((directory / matchboard.JSON_FILENAME).read_text())
    first = board["rows"][0]

    results = tmp_path / "results.jsonl"
    results.write_text(json.dumps({
        "fixture_id": first["fixture_id"], "home_goals": 2, "away_goals": 1,
        "matchweek": 1, "ingest": "manual/day1"}) + "\n")

    out = tmp_path / "scored"
    assert simcli.main(["matchboard", "--directory", str(directory),
                        "--out", str(out), "--score", str(results)]) == 0
    rows = [json.loads(line) for line in
            (out / "matchboard_scorecard.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["fixture_id"] == first["fixture_id"]
    assert row["outcome"] == "home" and row["realized_margin"] == 1
    assert row["probs"] == first["probs"]
    assert row["rps"] == pytest.approx(
        matchboard.rps(first["probs"], "home"), abs=1e-12)
    assert row["rps_uniform"] == pytest.approx(5 / 18, abs=1e-12)
    assert row["cutoff"] == board["cutoff"]
    assert row["observed_by"] == board["observed_by"]
    assert row["run_digest"] == board["run_digest"]
    # (f): no benchmark column anywhere on this surface
    assert not [k for k in row if "benchmark" in k]


def test_the_schema_bump_did_not_downgrade_the_round_before_it():
    """A7 bumps `ISSUANCE_SCHEMA_VERSION` to `-5`, and the A6 leniency was
    decided by `schema == ISSUANCE_SCHEMA_VERSION`.

    Left alone, that one line would have sent every `-4` record back to the
    leniency A6 wrote for records that PREDATE its fields — the fail-closed
    anchor becoming downgradeable by a version bump, which is exactly the defect
    the Codex review of `04b26a2` closed one round earlier. The comparison is on
    the ordinal, and an unparseable version is the NEWEST schema there is and
    not the oldest, so writing nonsense into `schema_version` is not a way out
    of a check.
    """
    assert simcli.schema_ordinal("epl-issuance-1") == 1
    assert simcli.schema_ordinal("epl-issuance-4") == simcli.A6_SCHEMA_ORDINAL
    assert simcli.schema_ordinal(simcli.ISSUANCE_SCHEMA_VERSION) == \
        simcli.A7_SCHEMA_ORDINAL
    for hostile in ("", None, "epl-issuance-", "epl-issuance-4x", "banana"):
        assert simcli.schema_ordinal(hostile) > simcli.A7_SCHEMA_ORDINAL, hostile

    # A -4 record missing an A6 field FAILs naming it, on the schema that is no
    # longer the current one...
    stale = simcli._unanchored("retained_rows_anchored", "sidecar_digests",
                               "epl-issuance-4")
    assert stale["status"] == "FAIL"
    assert stale["detail"]["missing_field"] == "sidecar_digests"
    # ...and so does a -5 one, and an unrecognised one.
    for schema in (simcli.ISSUANCE_SCHEMA_VERSION, "banana"):
        assert simcli._unanchored("x", "sidecar_digests", schema)["status"] \
            == "FAIL", schema

    # ...while a record that genuinely predates the field keeps the leniency
    # that exists for exactly that, under the note of ITS round.
    for schema in ("epl-issuance-1", "epl-issuance-2", "epl-issuance-3"):
        lenient = simcli._unanchored("x", "sidecar_digests", schema)
        assert lenient["status"] == simcli.UNANCHORED, schema
        assert lenient["note"] == simcli.PRE_A6_NOTE, schema
    a7 = simcli._unanchored("x", "sidecar_digests.matchboard", "epl-issuance-4",
                            since=simcli.A7_SCHEMA_ORDINAL,
                            note=simcli.PRE_A7_NOTE)
    assert a7["status"] == simcli.UNANCHORED and a7["note"] == simcli.PRE_A7_NOTE


def test_the_pass_headline_names_the_reasons_the_entries_carry():
    """A7 pre-stated the shape: `PASS (<n> criteria unanchored: <reasons>)`,
    where `<reasons>` is the sorted distinct set of the entries' own notes.

    Hardcoding "pre-A6 record" is what made the old headline wrong the moment a
    second round existed, so the reasons are read off the entries.
    """
    assert simcli._unanchored_reason(simcli.PRE_A6_NOTE) == "pre-A6 record"
    assert simcli._unanchored_reason(simcli.PRE_A7_NOTE) == "pre-A7 record"
    # a note that is not in the `unanchored (...)` shape is carried whole rather
    # than mangled into something shorter and wrong
    other = "this issuance ran no gate, so there are no gate bytes to anchor"
    assert simcli._unanchored_reason(other) == other
    assert simcli._unanchored_reason("") == "no reason recorded"


def test_the_summary_names_where_the_published_per_fixture_forecast_is(issuance):
    """A7 (a): the gate's `marginal_parity` sentence in `summary.md` claimed a
    published per-fixture forecast the bundle did not contain.

    It contains one now, so the file that carries the sentence names the file
    that answers it — and names its digest, so a reader who quotes the sentence
    can check the object it is about.
    """
    directory = Path(issuance["directory"])
    summary = (directory / "summary.md").read_text()
    assert "ARE the published per-fixture forecast" in summary, \
        "the sentence A7 is about is not in this summary"
    assert matchboard.JSON_FILENAME in summary
    assert matchboard.MD_FILENAME in summary
    assert matchboard.SCHEMA_VERSION in summary
    record = json.loads((directory / "issuance.json").read_text())
    assert record["sidecar_digests"]["dc_native"]["matchboard"] in summary


def test_the_matchboard_criteria_cannot_be_switched_off_by_a_version_string(
        issuance):
    """The `04b26a2` lesson, applied to A7's two criteria before it can bite.

    Reporting a criterion UNANCHORED purely on the schema string makes it
    DOWNGRADEABLE: edit `schema_version` back to `-4` and the strongest check on
    the file goes quiet. `record_digest` covers `schema_version`, but A6 (b.1)
    is explicit that a self-carried digest is a checksum against accident and
    not a seal against an editor who updates every copy — so the criteria look
    at whether the record PINS a matchboard, not only at what version it claims
    to be. A record that pins one is held to it whatever it says its version is.
    """
    directory = _copy(issuance, "matchboard_downgrade")
    path = directory / "issuance.json"
    record = json.loads(path.read_text())
    assert record["sidecar_digests"]["dc_native"]["matchboard"]
    record["schema_version"] = "epl-issuance-4"
    path.write_text(json.dumps(_restamp(record)))

    # untampered: still CHECKED, and still passing — the criteria did not go
    # quiet and did not start failing honest files either
    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    for name in ("matchboard_anchored", "matchboard_reproduces"):
        assert _criterion(cell, name)["status"] == "PASS", name
    assert [e for e in report["unanchored"] if "matchboard" in e] == []

    # ...and a tamper under the downgraded version is still caught
    _edit_json(directory / matchboard.JSON_FILENAME,
               lambda p: p["rows"][0]["probs"].__setitem__("home", 0.99))
    report = simcli.check_issuance(directory, verbose=False)
    cell = report["arms"]["dc_native"]
    assert _criterion(cell, "matchboard_anchored")["status"] == "FAIL"
    assert _criterion(cell, "matchboard_reproduces")["status"] == "FAIL"
    assert report["PASS"] is False
