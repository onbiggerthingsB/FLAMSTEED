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

from epl import bridge as bridge_mod, leaguesim, liveanchor, particles
from epl import season as season_mod, simcli
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
                 "cutoff_table", "matrix_and_markets", "serial_equals_chunked",
                 "mc_uncertainty", "limitations"):
        assert gate["criteria"][name]["PASS"] is True, (name, gate["criteria"][name])

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
def test_cli_check_reproduces_the_last_issuance(issuance, book):
    report = simcli.check_issuance(issuance["directory"], verbose=False)
    assert report["PASS"] is True
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
    assert report["PASS"] is True

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
    assert record["schema_version"] == "epl-issuance-3"
    assert record.pop("arms_manifest_hash")
    path.write_text(json.dumps(record))

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
    record = json.loads(path.read_text())
    record["schema_version"] = "epl-issuance-2"
    del record["arms_manifest_hash"]
    path.write_text(json.dumps(record))
    lenient = simcli.check_issuance(older, verbose=False)
    assert lenient["PASS"] is True
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
    assert narrowed["PASS"] is True
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
    assert report["PASS"] is True
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
    assert record["schema_version"] == "epl-issuance-3"
    assert set(record["output_digests"]) == set(record["arms"])
    assert set(record["provider_hashes"]) == set(record["arms"])
    assert simcli.check_issuance(directory, verbose=False)["PASS"] is True

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
    (swapped / "issuance.json").write_text(json.dumps(record))

    report = simcli.check_issuance(swapped, verbose=False)
    assert report["PASS"] is False
    assert report["arms"]["dc_native"]["detail"]["provider_hash_matches"] is False

    # POSITIVE CONTROL: an `epl-issuance-1` record recorded no provider hash at
    # all, and a missing record is reported as unrecorded rather than failed.
    older = directory.parent / "older_schema"
    shutil.copytree(directory, older)
    record = json.loads((older / "issuance.json").read_text())
    record.pop("provider_hashes")
    record.pop("output_digests")
    record["schema_version"] = "epl-issuance-1"
    (older / "issuance.json").write_text(json.dumps(record))
    legacy = simcli.check_issuance(older, verbose=False)
    assert legacy["PASS"] is True
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
        (stripped / "issuance.json").write_text(json.dumps(record))

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
