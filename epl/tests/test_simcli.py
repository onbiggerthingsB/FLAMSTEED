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

    # POSITIVE CONTROL: the note the run itself writes carries every number the
    # envelope holds, so (a) and (b) are corruptions and not a stricter reading.
    assert simcli.check_limitations(text, run)["detail"]["numbers_not_found"] == []
    assert simcli.check_limitations(text, run)["detail"][
        "flagged_in_note_not_in_envelope"] == []
