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

import dataclasses
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from epl import leaguesim, particles, season as season_mod, simcli
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
                        "--openfootball-file", str(agrees), "--write"]) == 0
    assert ledger.read_text() == before, "an agreeing row was appended twice"

    # POSITIVE CONTROL 2 — a NEW fixture is accepted and written, so the refusal
    # above is specific to the contradiction and not a blanket refusal to ingest
    fresh = tmp_path / "fresh.txt"
    fresh.write_text(_openfootball_line("Hull City AFC", "Manchester United FC", 0, 3))
    assert simcli.main(["ingest-results", "--season", SEASON, "--root", str(root),
                        "--openfootball-file", str(fresh), "--write"]) == 0
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line]
    assert len(rows) == 2
    assert rows[1]["fixture_id"] == "2627:hull:man_united"
    assert rows[1]["hg"] == 0 and rows[1]["ag"] == 3
    assert rows[1]["source"].startswith("openfootball@")


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
