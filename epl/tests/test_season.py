"""Season snapshot: fixtures, the known-at ledgers, and the point-in-time state.

Two failure modes are what this file exists to prevent.

1. *A fixture identified by its date.* `epl.parse._match_id` hashes the kickoff
   date, which is correct for an archive row and wrong for a fixture that may be
   moved: rescheduling would mint a second fixture and the season would hold 381.
   So `fixture_id` is `(season_code, home_key, away_key)` and the tests assert the
   date is nowhere in it.

2. *"Played" inferred from the calendar.* A fixture whose scheduled date has
   passed is not a result. Deriving `played` from the clock would silently drop a
   postponed match out of the simulation and score a season that never happened.
   `played` is derived from the results ledger and from nothing else, and the
   fixture whose date has passed with no result is reported `unresolved` — and
   still simulated.

Every known-at test carries its positive control: the same row is asserted
INVISIBLE before it was known and VISIBLE after. A canary that cannot fail is a
bug, and a leakage guard that never sees the leak is exactly that.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_season.py -q
"""

from __future__ import annotations

import hashlib
import itertools
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from epl import paths, season as season_mod, teams

SEASON = "2026/27"
SEASON_CODE = "2627"
OPENER = "2026-08-21"

#: The vendored openfootball file, pinned in the plan (openfootball/england,
#: CC0-1.0, `2026-27/1-premierleague.txt`).
FIXTURES_SHA256 = "ec7f37c90517fe8d697bff0e8be9ce87d2bb54e11c67c0883c5bf5c955aa9e91"
FIXTURES_BYTES = 21584

#: The 20 clubs of 2023/24, for the synthetic archive frame used by the
#: adjustment-refusal test (the real parquet is gitignored).
CLUBS_2023_24 = [
    "arsenal", "aston_villa", "bournemouth", "brentford", "brighton", "burnley",
    "chelsea", "crystal_palace", "everton", "fulham", "liverpool", "luton",
    "man_city", "man_united", "newcastle", "nottm_forest", "sheffield_united",
    "tottenham", "west_ham", "wolves",
]

# A faithful excerpt of the 2025/26 openfootball style: "Regular Season - N"
# headers, un-indented day headers, results with a half-time score, and
# goalscorer continuation lines (including one that wraps onto a second line).
STYLE_2025_26 = """\
= England | Premier League 2025/26

# Dates    Fri Aug 15 2025 - Sun May 24 2026 (282d)
# Teams    20
# Matches  380


▪ Regular Season - 1
Fri Aug 15 2025
  19:00   Liverpool  4-2 (1-0)  Bournemouth
                  (Hugo EKITIKE 37', Cody GAKPO 49', Federico Chiesa 88', MOHAMED SALAH 90+4';
                   Antoine SEMENYO 64', 76')
Sat Aug 16
  12:30   Aston Villa  0-0 (0-0)  Newcastle United
  15:00   Brighton & Hove Albion  1-1 (0-0)  Fulham
                  (Matt ORILEY 55'(p); RODRIGO MUNIZ 90+7')
Sun Aug 17
  14:00   Chelsea FC  0-0 (0-0)  Crystal Palace
"""


# --- helpers --------------------------------------------------------------

def _vendored_path() -> Path:
    return season_mod.SEASON_ROOT / "2026_27" / "fixtures_openfootball_2026-27.txt"


@pytest.fixture()
def season_root(tmp_path: Path) -> Path:
    """A writable copy of `epl/season/`, so ledger tests never touch the repo."""
    dst = tmp_path / "season"
    shutil.copytree(season_mod.SEASON_ROOT, dst)
    return dst


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _result_row(fid: str, date_played: str, hg: int, ag: int, observed_at: str,
                **extra) -> dict:
    row = {
        "fixture_id": fid,
        "date_played": date_played,
        "hg": hg,
        "ag": ag,
        "source": "manual",
        "observed_at": observed_at,
        "note": "test",
    }
    row.update(extra)
    return row


def _synthetic_archive(season: str, season_code: str, clubs: list[str],
                       start: str) -> pd.DataFrame:
    """A complete 380-match double round-robin, one match per day, 0-0 throughout."""
    rows = []
    day = pd.Timestamp(start)
    for home, away in itertools.permutations(clubs, 2):
        rows.append({
            "season": season,
            "season_code": season_code,
            "date": day,
            "home_key": home,
            "away_key": away,
            "fthg": 0,
            "ftag": 0,
        })
        day += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


# --- fixture identity -----------------------------------------------------

def test_fixture_id_has_no_date():
    """The id is (season, home, away). Moving the kickoff must not mint a fixture."""
    fid = season_mod.fixture_id(SEASON_CODE, "arsenal", "coventry")
    assert fid == "2627:arsenal:coventry"
    assert not any(ch.isdigit() for ch in fid.split(":", 1)[1])

    # Positive control: the ARCHIVE id does move with the date, which is exactly
    # why the sim may not reuse it as fixture identity.
    from epl import parse

    a = parse._match_id(SEASON_CODE, pd.Timestamp("2026-08-21"), "arsenal", "coventry")
    b = parse._match_id(SEASON_CODE, pd.Timestamp("2026-08-22"), "arsenal", "coventry")
    assert a != b


def test_vendored_file_hash_pinned():
    raw = _vendored_path().read_bytes()
    assert len(raw) == FIXTURES_BYTES
    assert hashlib.sha256(raw).hexdigest() == FIXTURES_SHA256
    assert season_mod.load_manifest(SEASON).fixtures_sha256 == FIXTURES_SHA256


def test_season_load_refuses_a_tampered_vendored_file(season_root: Path):
    """The PIN is checked above; this checks the RUNTIME REFUSAL.

    `test_vendored_file_hash_pinned` reads the repo's own bytes and compares
    them to the manifest, so it passes whether or not `Season.load` ever looks.
    Flipping one byte of a writable copy is what makes the guard itself
    falsifiable: the load has to stop, and stop ON THE HASH.
    """
    path = season_root / "2026_27" / "fixtures_openfootball_2026-27.txt"
    raw = path.read_bytes()

    # Positive control: the untampered copy loads its 380 fixtures.
    assert len(season_mod.Season.load(SEASON, root=season_root).fixtures) == 380

    i = raw.index(b"Arsenal")
    path.write_bytes(raw[:i] + b"B" + raw[i + 1:])
    assert len(path.read_bytes()) == len(raw)        # ONE byte, not a truncation
    with pytest.raises(season_mod.SeasonError, match="hashes to"):
        season_mod.Season.load(SEASON, root=season_root)


def test_season_module_not_shadowed_by_data_dir():
    """`epl/season.py` and the `epl/season/` data directory coexist by design."""
    assert Path(season_mod.__file__).name == "season.py"
    assert season_mod.SEASON_ROOT.is_dir()
    assert not (season_mod.SEASON_ROOT / "__init__.py").exists()


# --- the openfootball adapter --------------------------------------------

def test_parse_2026_27_is_380_38x10_20clubs_19h_19a_all_ordered_pairs_once():
    rows = season_mod.parse_openfootball(_vendored_path().read_text(encoding="utf-8"))
    assert len(rows) == 380

    by_md: dict[int, int] = {}
    for r in rows:
        by_md[r.matchday] = by_md.get(r.matchday, 0) + 1
    assert sorted(by_md) == list(range(1, 39))
    assert set(by_md.values()) == {10}

    keys = {teams.team_key(r.home_raw) for r in rows} | {
        teams.team_key(r.away_raw) for r in rows}
    assert len(keys) == 20

    pairs = [(teams.team_key(r.home_raw), teams.team_key(r.away_raw)) for r in rows]
    assert len(set(pairs)) == 380
    assert set(pairs) == {(h, a) for h in keys for a in keys if h != a}

    for club in keys:
        assert sum(1 for h, _ in pairs if h == club) == 19
        assert sum(1 for _, a in pairs if a == club) == 19

    # Fixtures, not results; dates carry down from the day headers, and the
    # year carries down too (only the first day header prints one).
    assert all(r.hg is None and r.ag is None for r in rows)
    assert all(r.date is not None for r in rows)
    assert min(r.date for r in rows) == pd.Timestamp("2026-08-21").date()
    assert max(r.date for r in rows) == pd.Timestamp("2027-05-30").date()


def test_every_openfootball_name_resolves_to_manifest_keys():
    rows = season_mod.parse_openfootball(_vendored_path().read_text(encoding="utf-8"))
    spellings = {r.home_raw for r in rows} | {r.away_raw for r in rows}
    assert len(spellings) == 20

    resolved = {teams.team_key(s) for s in spellings}
    manifest = season_mod.load_manifest(SEASON)
    assert resolved == set(manifest.clubs)
    assert "coventry" in resolved
    assert len(manifest.clubs) == 20


def test_parse_2025_26_style_results_and_headers():
    rows = season_mod.parse_openfootball(STYLE_2025_26)
    assert len(rows) == 4
    assert {r.matchday for r in rows} == {1}

    first = rows[0]
    assert (first.home_raw, first.away_raw) == ("Liverpool", "Bournemouth")
    assert (first.hg, first.ag) == (4, 2)
    assert first.date == pd.Timestamp("2025-08-15").date()
    assert first.time == "19:00"

    # Year carries down from the only dated header; goalscorer lines are ignored.
    assert [r.date.isoformat() for r in rows] == [
        "2025-08-15", "2025-08-16", "2025-08-16", "2025-08-17"]
    assert all(teams.team_key(r.home_raw) for r in rows)
    assert teams.team_key(rows[3].home_raw) == "chelsea"


def test_unparseable_line_fails_closed():
    with pytest.raises(season_mod.ParseError):
        season_mod.parse_openfootball("▪ Matchday 1\nFri Aug 21 2026\n  20:00  gibberish\n")


# --- the manifest ---------------------------------------------------------

def test_manifest_diff_prev_season_gives_3_promoted_3_relegated():
    m = season_mod.load_manifest(SEASON)
    assert len(m.clubs) == 20 and len(m.prev_season_clubs) == 20
    assert set(m.promoted) == set(m.clubs) - set(m.prev_season_clubs)
    assert set(m.relegated) == set(m.prev_season_clubs) - set(m.clubs)
    assert set(m.promoted) == {"coventry", "hull", "ipswich"}
    assert set(m.relegated) == {"burnley", "west_ham", "wolves"}
    assert m.season_code == SEASON_CODE
    assert "material=" in m.tiebreak_rule_id
    assert [tuple(b) for b in m.material_boundaries] == [
        (1, 2), (4, 5), (5, 6), (6, 7), (7, 8), (17, 18)]
    assert set(m.orientation_spotcheck) >= {"matchweeks", "checked_at", "by"}


# --- point-in-time state --------------------------------------------------

def test_state_at_opener_has_zero_played_380_unplayed_no_unresolved():
    state = season_mod.Season.load(SEASON).at(OPENER)
    assert len(state.played) == 0
    assert len(state.unplayed) == 380
    assert len(state.unresolved) == 0
    assert len(state.clubs) == 20
    assert set(state.statuses.values()) == {"scheduled"}
    assert all(row.played == 0 and row.pts == 0 for row in state.table_so_far.values())
    assert state.results_lag is False


def test_played_iff_result_never_by_date(season_root: Path):
    """A fixture whose date has passed with no result is unresolved, not played."""
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"  # 2026-08-21, the opener
    cutoff = "2026-08-24"

    bare = season_mod.Season.load(SEASON, root=season_root).at(cutoff)
    assert fid not in bare.played
    assert fid in bare.unresolved
    assert fid in bare.unplayed          # unresolved fixtures are still simulated
    assert bare.statuses[fid] == "unresolved"

    # Positive control: the same fixture, same cutoff, WITH a result.
    _append_jsonl(ledger, [_result_row(fid, "2026-08-21", 2, 1, "2026-08-21T22:00")])
    with_result = season_mod.Season.load(SEASON, root=season_root).at(cutoff)
    assert with_result.played[fid] == (2, 1)
    assert fid not in with_result.unresolved
    assert fid not in with_result.unplayed
    assert with_result.statuses[fid] == "played"
    assert with_result.table_so_far["arsenal"].pts == 3
    assert with_result.table_so_far["coventry"].pts == 0
    assert with_result.table_so_far["arsenal"].gd == 1


def test_table_so_far_covers_home_away_draw_and_adjustment(season_root: Path):
    """Every branch of the results ladder, asserted for BOTH clubs, plus D16.

    `table_so_far` is the first surface the operator reads on matchday one, and
    a single home win exercises barely a third of it. Four independent sign
    errors survive a home-win-only fixture: an away win credited to the home
    club, a draw scored as a home win, the away club's GF and GA swapped, and
    the points deduction dropped from the row. One outcome of each kind — plus
    an archive season carrying a real deduction — is what makes them visible.
    """
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    home_win = "2627:arsenal:coventry"        # 2026-08-21
    away_win = "2627:brentford:tottenham"     # 2026-08-22
    drawn = "2627:hull:man_united"            # 2026-08-22
    _append_jsonl(ledger, [
        _result_row(home_win, "2026-08-21", 2, 1, "2026-08-21T22:00"),
        _result_row(away_win, "2026-08-22", 0, 2, "2026-08-22T22:00"),
        _result_row(drawn, "2026-08-22", 1, 1, "2026-08-22T22:00"),
    ])
    state = season_mod.Season.load(SEASON, root=season_root).at("2026-08-25")
    assert (state.played[home_win], state.played[away_win],
            state.played[drawn]) == ((2, 1), (0, 2), (1, 1))

    def row(club):
        r = state.table_so_far[club]
        return (r.played, r.w, r.d, r.l, r.gf, r.ga, r.gd, r.pts)

    # a home win, 2-1
    assert row("arsenal") == (1, 1, 0, 0, 2, 1, 1, 3)
    assert row("coventry") == (1, 0, 0, 1, 1, 2, -1, 0)
    # an AWAY win, 0-2 — the three points belong to the visiting club
    assert row("brentford") == (1, 0, 0, 1, 0, 2, -2, 0)
    assert row("tottenham") == (1, 1, 0, 0, 2, 0, 2, 3)
    # a draw, 1-1 — one point each, no win and no defeat anywhere
    assert row("hull") == (1, 0, 1, 0, 1, 1, 0, 1)
    assert row("man_united") == (1, 0, 1, 0, 1, 1, 0, 1)

    # THE UNTOUCHED CLUBS WERE THE VACUOUS HALF OF THIS TEST. `all(...)` over
    # "the clubs the table happens to hold" is True for a `table_so_far` that
    # simply omits every club with nothing played yet — and a table that is
    # missing fourteen rows on matchday one is one the operator reads as a
    # six-club league, with fourteen clubs silently unrankable. So the KEY SET
    # is asserted first, against the season's own club list, and only then the
    # zeros; and the untouched clubs are counted, so an empty comprehension
    # cannot stand in for fourteen all-zero rows.
    touched = {"arsenal", "coventry", "brentford", "tottenham", "hull", "man_united"}
    assert len(touched) == 6
    assert set(state.table_so_far) == set(state.clubs)
    assert len(state.table_so_far) == 20
    untouched = sorted(set(state.table_so_far) - touched)
    assert len(untouched) == 14
    assert all(row(c) == (0, 0, 0, 0, 0, 0, 0, 0) for c in untouched)

    # D16: the deduction has to reach the ROW, not just `adjustments_known`.
    # 2023/24 is the season that carries one (Everton -8, Forest -4), so the
    # archive path is where that is asserted. Everton's record is seeded to be
    # non-trivial — 9 wins, 27 draws, 2 defeats — so `3w + d - 8` is a real sum
    # rather than an identity that holds at zero.
    frame = _synthetic_archive("2023/24", "2324", CLUBS_2023_24, "2023-08-11")
    at_home = frame.index[frame["home_key"] == "everton"]
    away = frame.index[frame["away_key"] == "everton"]
    frame.loc[at_home[:5], ["fthg", "ftag"]] = [3, 1]     # 5 home wins
    frame.loc[at_home[5:7], ["fthg", "ftag"]] = [0, 1]    # 2 home defeats
    frame.loc[away[:4], ["fthg", "ftag"]] = [0, 2]        # 4 away wins
    # The gate is ON: the four 2023/24 rows carry their attestation as of
    # 2026-08-20, so this call no longer has to opt out of D16 to run.
    archive = season_mod.archive_season_state(frame, "2023/24", "2025-01-01")
    assert len(archive.played) == 380

    ev = archive.table_so_far["everton"]
    assert (ev.played, ev.w, ev.d, ev.l) == (38, 9, 27, 2)
    assert (ev.gf, ev.ga, ev.gd) == (23, 7, 16)
    assert ev.adjustment == -8
    assert ev.pts == 3 * ev.w + ev.d - 8 == 46
    assert archive.table_so_far["nottm_forest"].adjustment == -4
    assert archive.table_so_far["arsenal"].adjustment == 0    # no deduction, no shift


def test_results_lag_flag(season_root: Path):
    state = season_mod.Season.load(SEASON, root=season_root).at("2026-08-23")
    assert state.results_lag is False        # opener is 2 days old
    later = season_mod.Season.load(SEASON, root=season_root).at("2026-08-24")
    assert later.results_lag is True         # > 2 days with no result


def test_kickoff_amendment_known_at_respected(season_root: Path):
    amendments = season_root / "2026_27" / "kickoff_amendments.jsonl"
    fid = "2627:arsenal:coventry"
    _append_jsonl(amendments, [{
        "fixture_id": fid, "date": "2026-09-15", "time": "20:00",
        "source": "test", "known_at": "2026-08-20T09:00", "note": "moved",
    }])

    before = season_mod.Season.load(SEASON, root=season_root).at("2026-08-19")
    assert before.kickoffs_known[fid][0] == pd.Timestamp("2026-08-21").date()

    after = season_mod.Season.load(SEASON, root=season_root).at("2026-08-24")
    assert after.kickoffs_known[fid][0] == pd.Timestamp("2026-09-15").date()
    # ... and the moved fixture is no longer overdue.
    assert fid not in after.unresolved
    assert after.statuses[fid] == "scheduled"


def test_results_ledger_observed_at_respected(season_root: Path):
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"
    _append_jsonl(ledger, [_result_row(fid, "2026-08-21", 2, 1, "2026-08-25T10:00")])

    late = season_mod.Season.load(SEASON, root=season_root)
    # Observed AFTER the cutoff: invisible, even though the match date is before it.
    assert fid not in late.at("2026-08-24").played
    # Positive control: same row, a cutoff after it was observed.
    assert late.at("2026-08-26").played[fid] == (2, 1)
    # ... and the explicit bitemporal knob reproduces the first reading.
    assert fid not in late.at("2026-08-26", observed_by="2026-08-24").played


def test_a_later_status_supersedes_an_earlier_score(season_root: Path):
    """Latest OBSERVATION wins across scores AND statuses, not scores alone.

    A match played, filed with a scoreline, and then struck from the record is
    the case: the correction is appended (the ledger is never edited in place)
    and a snapshot that sees both rows must read the fixture as UNPLAYED.
    Resolving statuses and scores in two independent passes — with the score
    always winning at the end — keeps a result the league has taken away, and
    keeps it silently: nothing downstream re-reads the ledger.
    """
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"
    _append_jsonl(ledger, [
        _result_row(fid, "2026-08-21", 2, 1, "2026-08-21T22:00"),
        {"fixture_id": fid, "status": "abandoned", "source": "manual",
         "observed_at": "2026-08-23T09:00", "note": "struck from the record"},
    ])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    seeing_both = loaded.at("2026-08-25")
    assert fid not in seeing_both.played
    assert fid in seeing_both.unplayed
    assert seeing_both.statuses[fid] == "abandoned"
    assert seeing_both.table_so_far["arsenal"] == season_mod.TableRow()
    assert seeing_both.table_so_far["coventry"] == season_mod.TableRow()

    # ...and the known-at bound still holds: before the correction was observed
    # the scoreline is what the ledger said it was.
    assert loaded.at("2026-08-25", observed_by="2026-08-22").played[fid] == (2, 1)

    # POSITIVE CONTROL: the same two rows with the observations the other way
    # round — the SCORE is the later correction — and the fixture IS played.
    ledger.write_text("", encoding="utf-8")
    _append_jsonl(ledger, [
        {"fixture_id": fid, "status": "abandoned", "source": "manual",
         "observed_at": "2026-08-21T22:00", "note": "abandoned at 70 mins"},
        _result_row(fid, "2026-08-21", 2, 1, "2026-08-23T09:00"),
    ])
    replayed = season_mod.Season.load(SEASON, root=season_root).at("2026-08-25")
    assert replayed.played[fid] == (2, 1)
    assert replayed.statuses[fid] == "played"
    assert replayed.table_so_far["arsenal"].pts == 3


def test_a_later_observed_correction_wins_over_the_row_it_corrects(season_root: Path):
    """Two scorelines for one fixture: the later OBSERVATION wins, not the later line."""
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"
    # Written in the file the "wrong" way round on purpose: the correction is
    # the FIRST line and the row it corrects the second, so a resolution that
    # reads file order rather than observation order gets the stale scoreline.
    _append_jsonl(ledger, [
        _result_row(fid, "2026-08-21", 3, 1, "2026-08-23T09:00", note="correction"),
        _result_row(fid, "2026-08-21", 2, 1, "2026-08-21T22:00"),
    ])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    assert loaded.at("2026-08-25").played[fid] == (3, 1)
    assert loaded.at("2026-08-25").table_so_far["arsenal"].gf == 3
    # POSITIVE CONTROL: bounded to before the correction was observed, the row
    # it corrects is what a snapshot sees.
    assert loaded.at("2026-08-25", observed_by="2026-08-22").played[fid] == (2, 1)


def test_observed_by_bounds_amendments_and_adjustments_not_just_results(
        season_root: Path):
    """`observed_by` is a bound on the SNAPSHOT, so it bounds all three ledgers.

    Bounding results only reproduces a stale reading of one ledger against a
    fresh reading of the other two: the deduction that was ruled on Saturday and
    the fixture that moved on Saturday would both be in a snapshot taken as of
    Friday. A rerun of an old forecast would then not be that forecast.
    """
    amendments = season_root / "2026_27" / "kickoff_amendments.jsonl"
    adjustments = season_root / "points_adjustments.jsonl"
    fid = "2627:arsenal:coventry"
    _append_jsonl(amendments, [{
        "fixture_id": fid, "date": "2026-09-15", "time": "20:00",
        "source": "test", "known_at": "2026-08-22T09:00", "note": "moved",
    }])
    _append_jsonl(adjustments, [{
        "id": "adj-2627-test-01", "season": SEASON, "club_key": "arsenal",
        "delta": -3, "known_at": "2026-08-22T09:00", "source": "test",
        "supersedes": None, "verified": True, "note": "test",
    }])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    # As of Friday, neither had happened — even asking about Monday.
    bounded = loaded.at("2026-08-24", observed_by="2026-08-21")
    assert bounded.kickoffs_known[fid][0] == pd.Timestamp("2026-08-21").date()
    assert bounded.adjustments_known == {}
    assert bounded.table_so_far["arsenal"].adjustment == 0
    assert bounded.table_so_far["arsenal"].pts == 0

    # POSITIVE CONTROL: the same cutoff with no known-at bound sees both.
    unbounded = loaded.at("2026-08-24")
    assert unbounded.kickoffs_known[fid][0] == pd.Timestamp("2026-09-15").date()
    assert unbounded.adjustments_known == {"arsenal": -3}
    assert unbounded.table_so_far["arsenal"].pts == -3


def test_result_conflict_stops(season_root: Path):
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"
    _append_jsonl(ledger, [_result_row(fid, "2026-08-21", 2, 1, "2026-08-22T09:00")])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    agreeing = "▪ Matchday 1\nFri Aug 21 2026\n  20:00  Arsenal FC  2-1 (1-0)  Coventry City FC\n"
    # Idempotent: an agreeing re-ingest appends nothing and raises nothing.
    assert loaded.ingest_openfootball_results(
        agreeing, observed_at="2026-08-23T09:00", source_id="openfootball@x") == []

    disagreeing = agreeing.replace("2-1", "3-1")
    with pytest.raises(season_mod.ResultConflict):
        loaded.ingest_openfootball_results(
            disagreeing, observed_at="2026-08-23T09:00", source_id="openfootball@x")


def test_ingest_openfootball_results_appends_new_rows(season_root: Path):
    loaded = season_mod.Season.load(SEASON, root=season_root)
    text = "▪ Matchday 1\nFri Aug 21 2026\n  20:00  Arsenal FC  2-1 (1-0)  Coventry City FC\n"
    rows = loaded.ingest_openfootball_results(
        text, observed_at="2026-08-22T09:00",
        source_id=season_mod.openfootball_source_id(text), write=True)

    assert len(rows) == 1
    assert rows[0]["fixture_id"] == "2627:arsenal:coventry"
    assert rows[0]["source"].startswith("openfootball@")
    reloaded = season_mod.Season.load(SEASON, root=season_root)
    assert reloaded.at("2026-08-24").played["2627:arsenal:coventry"] == (2, 1)
    # Second ingest of the same text is a no-op.
    assert reloaded.ingest_openfootball_results(
        text, observed_at="2026-08-23T09:00", source_id="openfootball@x", write=True) == []


def test_orientation_suspect_fails_closed(season_root: Path):
    loaded = season_mod.Season.load(SEASON, root=season_root)
    fid = "2627:arsenal:coventry"
    reverse = loaded.fixture("2627:coventry:arsenal")
    ledger = season_root / "2026_27" / "results_ledger.jsonl"

    # A result for the FORWARD fixture, dated next to the REVERSE fixture's
    # kickoff and months from its own: the sources disagree on orientation.
    _append_jsonl(ledger, [_result_row(
        fid, (reverse.base_date - pd.Timedelta(days=1)).isoformat(), 1, 0,
        "2027-06-01T09:00")])
    with pytest.raises(season_mod.OrientationSuspect):
        season_mod.Season.load(SEASON, root=season_root).at("2027-06-02")

    # Positive control: the same row dated at its own kickoff is accepted.
    ledger.write_text("", encoding="utf-8")
    _append_jsonl(ledger, [_result_row(fid, "2026-08-21", 1, 0, "2026-08-22T09:00")])
    ok = season_mod.Season.load(SEASON, root=season_root).at("2027-06-02")
    assert ok.played[fid] == (1, 0)


def test_postponed_row_is_a_status_and_awarded_fails_closed(season_root: Path):
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"
    _append_jsonl(ledger, [{
        "fixture_id": fid, "status": "postponed", "source": "manual",
        "observed_at": "2026-08-21T18:00", "note": "test",
    }])
    state = season_mod.Season.load(SEASON, root=season_root).at("2026-08-24")
    assert state.statuses[fid] == "postponed"
    assert fid not in state.played and fid in state.unplayed
    assert fid not in state.unresolved

    ledger.write_text("", encoding="utf-8")
    _append_jsonl(ledger, [{
        "fixture_id": fid, "status": "awarded", "hg": 3, "ag": 0,
        "source": "manual", "observed_at": "2026-08-21T18:00", "note": "test",
    }])
    with pytest.raises(season_mod.UnsupportedResultStatus):
        season_mod.Season.load(SEASON, root=season_root).at("2026-08-24")


def test_unsupported_status_is_checked_only_once_the_row_is_visible(
        season_root: Path):
    """An `awarded` row must not break a snapshot taken BEFORE it was filed.

    The ledger is append-only, so tomorrow's row sits in the same file as
    yesterday's; validating every line before the known-at filter runs makes a
    row filed today retroactively unloadable at every earlier cutoff, which is
    the same class of bug as reading its content early. It must still fail
    closed the moment it IS visible — v1 does not model an awarded result.
    """
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"
    _append_jsonl(ledger, [{
        "fixture_id": fid, "status": "awarded", "hg": 3, "ag": 0,
        "source": "manual", "observed_at": "2026-09-01T12:00", "note": "test",
    }])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    early = loaded.at("2026-08-24")                       # not yet observed
    assert early.statuses[fid] == "unresolved"
    assert fid not in early.played
    # ... and the explicit bound reproduces that reading from a later cutoff.
    assert loaded.at("2026-09-02", observed_by="2026-08-24").statuses[fid] == "unresolved"

    # POSITIVE CONTROL: once visible it fails closed, exactly as before.
    with pytest.raises(season_mod.UnsupportedResultStatus):
        loaded.at("2026-09-02")


def test_detect_kickoff_amendments_finds_the_moved_fixture():
    base = season_mod.parse_openfootball(_vendored_path().read_text(encoding="utf-8"))
    fresh = list(base)
    moved = fresh[0]
    fresh[0] = season_mod.FixtureRow(
        matchday=moved.matchday, date=pd.Timestamp("2026-08-28").date(), time="20:00",
        home_raw=moved.home_raw, away_raw=moved.away_raw, hg=None, ag=None)

    rows = season_mod.detect_kickoff_amendments(
        base, fresh, known_at="2026-08-19T12:00", source_id="openfootball@y",
        season_code=SEASON_CODE)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-28"
    assert rows[0]["known_at"] == "2026-08-19T12:00:00"   # normalised ISO
    assert rows[0]["fixture_id"] == season_mod.fixture_id(
        SEASON_CODE, teams.team_key(moved.home_raw), teams.team_key(moved.away_raw))
    # No diff -> no rows (the detector must not fire on every fetch).
    assert season_mod.detect_kickoff_amendments(
        base, base, known_at="2026-08-19T12:00", source_id="openfootball@y",
        season_code=SEASON_CODE) == []


def test_detect_kickoff_amendments_sees_a_time_only_move():
    """A kickoff that moves only its TIME is an amendment too.

    Diffing dates alone would miss a 20:00 -> 12:30 move; the overlay is what
    the display and the unresolved/lag flags read, so a missed time move is a
    schedule the operator cannot see.
    """
    base = season_mod.parse_openfootball(_vendored_path().read_text(encoding="utf-8"))
    fresh = list(base)
    moved = fresh[0]
    assert moved.time == "20:00"                          # the file states it
    fresh[0] = season_mod.FixtureRow(
        matchday=moved.matchday, date=moved.date, time="12:30",
        home_raw=moved.home_raw, away_raw=moved.away_raw, hg=None, ag=None)

    rows = season_mod.detect_kickoff_amendments(
        base, fresh, known_at="2026-08-19T12:00", source_id="openfootball@z",
        season_code=SEASON_CODE)
    assert len(rows) == 1
    assert rows[0]["time"] == "12:30"
    assert rows[0]["date"] == moved.date.isoformat()      # the DAY did not move
    assert rows[0]["fixture_id"] == season_mod.fixture_id(
        SEASON_CODE, teams.team_key(moved.home_raw), teams.team_key(moved.away_raw))


# --- points adjustments ---------------------------------------------------

def test_adjustments_supersession_known_at():
    rows = season_mod.load_adjustments()

    def at(cutoff):
        return season_mod.adjustments_at(rows, "2023/24", cutoff)

    assert at("2023-11-01") == {}                                 # before any ruling
    assert at("2023-12-01") == {"everton": -10}                   # first deduction
    assert at("2024-03-01") == {"everton": -6}                    # appeal supersedes
    assert at("2024-03-20") == {"everton": -6, "nottm_forest": -4}
    assert at("2024-05-20") == {"everton": -8, "nottm_forest": -4}  # second breach
    assert at("2024-05-20") != at("2024-03-01")                   # the ledger moves


def test_2023_24_adjustments_final_state_everton_minus_8_forest_minus_4():
    """T3 asserts the resulting 15th/17th finish; T1 owns the deduction totals."""
    rows = season_mod.load_adjustments()
    final = season_mod.adjustments_at(rows, "2023/24", "2024-06-30")
    assert final == {"everton": -8, "nottm_forest": -4}


def test_the_2023_24_rows_carry_the_attestation_that_verified_them():
    """The 2026-08-20 attestation, asserted against the ledger file itself.

    Each of the four 2023/24 rows was checked against the Premier League's own
    published statement, and each carries the three fields that say so:
    `verified_at`, `verified_by` and a `source_url` pointing at the statement it
    was checked against. A `verified: true` with no record of what it was
    checked against is exactly the decoration D16's gate exists to refuse, so
    the flag alone is not what this asserts.
    """
    rows = {r["id"]: r for r in season_mod.load_adjustments()
            if r["season"] == "2023/24"}
    assert set(rows) == {"adj-2324-everton-01", "adj-2324-everton-02",
                         "adj-2324-everton-03", "adj-2324-nottm-forest-01"}
    for row in rows.values():
        assert row["verified"] is True
        assert row["verified_at"] == "2026-08-19"
        assert "premierleague.com" in row["verified_by"]
        assert row["source_url"].startswith("https://www.premierleague.com/")
        assert "UNVERIFIED" not in row["note"]

    # The attestation records a CHECK; it does not restate the ledger. The four
    # deltas, dates and the supersession are byte-for-byte what they were.
    assert [(rows[i]["delta"], rows[i]["known_at"], rows[i]["supersedes"])
            for i in ("adj-2324-everton-01", "adj-2324-everton-02",
                      "adj-2324-nottm-forest-01", "adj-2324-everton-03")] == [
        (-10, "2023-11-17", None),
        (-6, "2024-02-26", "adj-2324-everton-01"),
        (-4, "2024-03-18", None),
        (-2, "2024-04-08", None)]


def test_the_real_2023_24_ledger_now_scores_under_the_gate():
    """T3's archive test, un-deferred: the gate is ON and 2023/24 goes through.

    Before the attestation this call raised `UnverifiedAdjustment` and every
    2023/24 assertion in this file had to pass `require_verified_adjustments=
    False` to get past it. Nothing is opted out here.
    """
    frame = _synthetic_archive("2023/24", "2324", CLUBS_2023_24, "2023-08-11")
    state = season_mod.archive_season_state(frame, "2023/24", "2024-06-30")
    assert state.adjustments_known == {"everton": -8, "nottm_forest": -4}
    assert state.table_so_far["everton"].adjustment == -8
    assert state.table_so_far["nottm_forest"].adjustment == -4


def test_unverified_adjustment_rows_refused_for_scoring(tmp_path: Path):
    """The gate, driven RED on a SYNTHETIC unverified row.

    Until 2026-08-20 this test drove the gate on the real 2023/24 rows, which
    were seeded `verified: false`. They are verified now, so pointing the guard
    at them would leave it with nothing to refuse and this test would pass
    vacuously — a canary that cannot fail is the bug it exists to catch. The
    unverified row is synthetic from here on; the real ledger appears below
    only as the control that says the guard is not simply always firing.
    """
    frame = _synthetic_archive("2023/24", "2324", CLUBS_2023_24, "2023-08-11")
    root = tmp_path / "season"
    root.mkdir()
    ledger = root / "points_adjustments.jsonl"
    unverified = {"id": "adj-2324-synthetic-01", "season": "2023/24",
                  "club_key": "everton", "delta": -10, "known_at": "2023-11-17",
                  "source": "test", "supersedes": None, "verified": False,
                  "note": "synthetic: checked against nothing"}
    _append_jsonl(ledger, [unverified])

    with pytest.raises(season_mod.UnverifiedAdjustment) as caught:
        season_mod.archive_season_state(frame, "2023/24", "2024-06-30", root=root)
    assert "adj-2324-synthetic-01" in str(caught.value)

    # POSITIVE CONTROL 1: the same row, verified, scores — so the refusal is
    # the FLAG and not the row's presence.
    ledger.write_text("")
    _append_jsonl(ledger, [dict(unverified, verified=True)])
    assert season_mod.archive_season_state(
        frame, "2023/24", "2024-06-30", root=root
    ).adjustments_known == {"everton": -10}

    # POSITIVE CONTROL 2: the unverified row again, with the operator opting
    # out of the gate explicitly.
    ledger.write_text("")
    _append_jsonl(ledger, [unverified])
    assert season_mod.archive_season_state(
        frame, "2023/24", "2024-06-30", root=root,
        require_verified_adjustments=False
    ).adjustments_known == {"everton": -10}

    # POSITIVE CONTROL 3: the REAL ledger, gate on, no longer refuses; and a
    # season with no adjustment rows at all scores under the gate as it always
    # did.
    assert season_mod.archive_season_state(
        frame, "2023/24", "2024-06-30"
    ).adjustments_known == {"everton": -8, "nottm_forest": -4}
    clean = _synthetic_archive("2021/22", "2122", CLUBS_2023_24, "2021-08-13")
    assert season_mod.archive_season_state(clean, "2021/22", "2022-06-30").adjustments_known == {}


def test_archive_season_state_is_point_in_time():
    frame = _synthetic_archive("2021/22", "2122", CLUBS_2023_24, "2021-08-13")
    # One match per day from 2021-08-13; 10 days in => 10 played.
    state = season_mod.archive_season_state(frame, "2021/22", "2021-08-23")
    assert len(state.played) == 10
    assert len(state.unplayed) == 370
    assert sum(r.played for r in state.table_so_far.values()) == 20
    full = season_mod.archive_season_state(frame, "2021/22", "2023-01-01")
    assert len(full.played) == 380


@pytest.mark.skipif(not paths.MATCHES_PARQUET.exists(), reason="archive parquet absent")
def test_archive_season_state_matches_the_real_archive():
    frame = pd.read_parquet(paths.MATCHES_PARQUET)
    state = season_mod.archive_season_state(
        frame, "2022/23", "2022-09-01", require_verified_adjustments=False)
    rows = frame[(frame.season == "2022/23") & (frame.date < pd.Timestamp("2022-09-01"))]
    assert len(state.played) == len(rows)
    assert len(state.played) + len(state.unplayed) == 380
    assert len(state.clubs) == 20


# --- round 2: the two clocks, NaT, and when a bad row may break a snapshot ---

def test_a_stamp_that_resolves_to_nat_fails_closed(season_root: Path, monkeypatch):
    """`NaT` compares False against every bound, so an unstamped row leaks.

    This is the same hole `epl.liveanchor._stamp` closes, reached through the
    other reader of the same ledger. A status row with a null `observed_at` is
    the sharpest case: `NaT > observed_by` is False, so the row is visible at
    EVERY cutoff and postpones a fixture in a snapshot taken years before anyone
    filed it. A null `date_played` is the mirror image — `NaT >= cutoff_day` is
    False, so the row counts as played before it was played.

    `known_at` fails the other way (`NaT <= cutoff` is False, so the row is
    visible at no cutoff and a deduction silently vanishes from every table),
    which is quieter and equally wrong. All three stop the load.
    """
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"

    # POSITIVE CONTROL first: the same row, properly stamped, is invisible
    # before it was observed and visible after — so the refusals below are
    # refusals of the stamp, not of the row.
    _append_jsonl(ledger, [_result_row(fid, "2026-08-21", 2, 1, "2026-08-22T09:00")])
    loaded = season_mod.Season.load(SEASON, root=season_root)
    assert fid not in loaded.at("2026-08-22T08:00").played
    assert loaded.at("2026-08-23").played[fid] == (2, 1)

    # (a) a status row with no `observed_at`: under the old rule `NaT >
    #     observed_by` is False, so the row was visible at every cutoff — here,
    #     three weeks before the season starts.
    for bad in (None, "", float("nan")):
        ledger.write_text("")
        _append_jsonl(ledger, [{
            "fixture_id": fid, "status": "postponed", "source": "manual",
            "observed_at": bad, "note": "test"}])
        loaded = season_mod.Season.load(SEASON, root=season_root)
        with pytest.raises(season_mod.SeasonError, match="observed_at"):
            loaded.at("2026-08-01")

    # (b) a result row with no `date_played`: "played" before it was played.
    #
    #     Asserted with `_check_orientation` STUBBED OUT. It reads the very same
    #     `date_played` through the very same `_require_stamp` two steps later,
    #     so an assertion that merely matches "date_played" here passes whether
    #     or not the play-clock filter holds a guard of its own — the second
    #     line of defence answering for the first, which is a test that cannot
    #     fail. With the stub in place the refusal can only come from the
    #     visibility filter under test.
    for bad in (None, "", float("nan"), "NaT"):
        ledger.write_text("")
        _append_jsonl(ledger, [dict(
            _result_row(fid, "2026-08-21", 2, 1, "2026-08-22T09:00"),
            date_played=bad)])
        loaded = season_mod.Season.load(SEASON, root=season_root)
        with monkeypatch.context() as patch:
            patch.setattr(season_mod, "_check_orientation",
                          lambda *a, **k: None)
            with pytest.raises(season_mod.SeasonError, match="date_played"):
                loaded.at("2026-08-23")
    # POSITIVE CONTROL for the stub: under the same stub a properly stamped row
    # still loads and is still played, so the four refusals above are the guard
    # firing and not the stub breaking the call.
    ledger.write_text("")
    _append_jsonl(ledger, [_result_row(fid, "2026-08-21", 2, 1, "2026-08-22T09:00")])
    loaded = season_mod.Season.load(SEASON, root=season_root)
    with monkeypatch.context() as patch:
        patch.setattr(season_mod, "_check_orientation", lambda *a, **k: None)
        assert loaded.at("2026-08-23").played[fid] == (2, 1)

    # (c) a `known_at` ledger — the other direction, and the quiet one:
    #     `NaT <= cutoff` is False, so the row applies at NO cutoff and its
    #     effect silently disappears from every table ever built. Both known-at
    #     ledgers, and an ABSENT key as well as an unusable one: a bare
    #     `KeyError` is not a closed failure here, because every caller that
    #     means "this snapshot is unusable" catches `SeasonError`.
    amendments = season_root / "2026_27" / "kickoff_amendments.jsonl"
    adjustments = season_root / "points_adjustments.jsonl"
    ledger.write_text("")

    amend = {"fixture_id": fid, "date": "2026-09-15", "time": "20:00",
             "source": "test", "known_at": "2026-08-01T09:00", "note": "moved"}
    deduct = {"id": "adj-2627-nat", "season": SEASON, "club_key": "arsenal",
              "delta": -3, "known_at": "2026-08-01T09:00", "source": "test",
              "supersedes": None, "verified": True, "note": "test"}

    # POSITIVE CONTROL first: properly stamped, both rows apply.
    amendments.write_text("")
    _append_jsonl(amendments, [amend])
    _append_jsonl(adjustments, [deduct])
    control = season_mod.Season.load(SEASON, root=season_root).at(OPENER)
    assert control.kickoffs_known[fid][0] == pd.Timestamp("2026-09-15").date()
    assert control.adjustments_known["arsenal"] == -3

    for bad in (None, "", float("nan"), "NaT"):
        amendments.write_text("")
        _append_jsonl(amendments, [dict(amend, known_at=bad)])
        with pytest.raises(season_mod.SeasonError, match="known_at"):
            season_mod.Season.load(SEASON, root=season_root).at(OPENER)
    amendments.write_text("")
    _append_jsonl(amendments, [{k: v for k, v in amend.items() if k != "known_at"}])
    with pytest.raises(season_mod.SeasonError, match="known_at"):
        season_mod.Season.load(SEASON, root=season_root).at(OPENER)

    amendments.write_text("")
    original = [r for r in season_mod._read_jsonl(adjustments)
                if r["id"] != deduct["id"]]
    broken = [dict(deduct, known_at=b) for b in (None, "", float("nan"), "NaT")]
    broken.append({k: v for k, v in deduct.items() if k != "known_at"})
    for row in broken:
        adjustments.write_text("")
        _append_jsonl(adjustments, original + [row])
        with pytest.raises(season_mod.SeasonError, match="known_at"):
            season_mod.Season.load(SEASON, root=season_root).at(OPENER)


def test_a_ledger_row_with_no_fixture_id_breaks_only_once_it_is_visible(
        season_root: Path):
    """`fixture_id` is read AFTER the stamp, not before it.

    The resolution's first act must be to place a row in time; everything else
    about it — the id included — is content, and content is read only once the
    row is visible. Reading `row["fixture_id"]` first made a future row that is
    missing the field raise at EVERY earlier cutoff, which is the same defect
    the unknown-fixture check was already moved to avoid, arriving one line
    earlier.
    """
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    _append_jsonl(ledger, [{
        "date_played": "2026-08-21", "hg": 2, "ag": 1, "source": "manual",
        "observed_at": "2026-09-01T12:00", "note": "no fixture_id"}])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    # not yet observed: the snapshot is unaffected, and nothing raises
    assert len(loaded.at("2026-08-24").played) == 0
    assert len(loaded.at("2026-09-02", observed_by="2026-08-24").played) == 0

    # POSITIVE CONTROL: once visible it fails closed, as a `SeasonError`
    with pytest.raises(season_mod.SeasonError, match="fixture_id"):
        loaded.at("2026-09-02")


def test_a_row_for_an_unknown_fixture_breaks_only_once_it_is_visible(
        season_root: Path):
    """The unknown-fixture check moves after the known-at filter (A3's reasoning).

    A results row naming a fixture this season does not hold is a hand-entry
    error and must stop the run. But the ledger is append-only, so the row filed
    today sits in the same file as every earlier row: checking it before the
    known-at filter makes today's typo retroactively unloadable at every cutoff
    that came before it — the same class of bug as reading a row's content early.
    """
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    _append_jsonl(ledger, [_result_row(
        "2627:arsenal:notaclub", "2026-08-21", 2, 1, "2026-09-01T12:00")])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    # not yet observed: the snapshot is unaffected
    early = loaded.at("2026-08-24")
    assert len(early.played) == 0
    # ... and the explicit bound reproduces that reading from a later cutoff
    assert len(loaded.at("2026-09-02", observed_by="2026-08-24").played) == 0

    # POSITIVE CONTROL: once visible it fails closed
    with pytest.raises(season_mod.SeasonError, match="unknown fixture"):
        loaded.at("2026-09-02")


def test_observed_by_is_the_knowledge_clock_for_all_three_ledgers(
        season_root: Path):
    """`observed_by > cutoff`: one knowledge state, read consistently.

    The first shape of this bounded amendments and adjustments by
    `min(cutoff, observed_by)` while the results ledger used `observed_by`
    alone. Asking "what do we know NOW about the table as it stood on the 24th"
    then read Saturday's results against Friday's schedule and Friday's
    deductions — no moment that ever existed, and the failure is silent.

    The two clocks are separate and each ledger is read by exactly one:
    `observed_by` decides what is KNOWN (all three ledgers), `cutoff` decides
    what has HAPPENED (a visible result is played iff `date_played < cutoff`).
    """
    amendments = season_root / "2026_27" / "kickoff_amendments.jsonl"
    adjustments = season_root / "points_adjustments.jsonl"
    ledger = season_root / "2026_27" / "results_ledger.jsonl"
    fid = "2627:arsenal:coventry"
    later = "2627:aston_villa:brentford"

    _append_jsonl(amendments, [{
        "fixture_id": fid, "date": "2026-09-15", "time": "20:00",
        "source": "test", "known_at": "2026-08-30T09:00", "note": "moved"}])
    _append_jsonl(adjustments, [{
        "id": "adj-2627-test-02", "season": SEASON, "club_key": "arsenal",
        "delta": -3, "known_at": "2026-08-30T09:00", "source": "test",
        "supersedes": None, "verified": True, "note": "test"}])
    _append_jsonl(ledger, [
        # played before the cutoff, learned after it
        _result_row(fid, "2026-08-21", 2, 1, "2026-08-30T09:00"),
        # learned by the same clock, but played AFTER the cutoff
        _result_row(later, "2026-08-29", 1, 0, "2026-08-30T09:00")])
    loaded = season_mod.Season.load(SEASON, root=season_root)

    known_now = loaded.at("2026-08-24", observed_by="2026-08-31")
    assert known_now.played == {fid: (2, 1)}, "the play clock is the cutoff"
    assert later in known_now.unplayed
    assert known_now.kickoffs_known[fid][0] == pd.Timestamp("2026-09-15").date()
    assert known_now.adjustments_known == {"arsenal": -3}
    assert known_now.table_so_far["arsenal"].pts == 0            # 3 for the win, -3

    # POSITIVE CONTROL, both directions.
    # (i) at the cutoff itself nothing above is known yet — so the three
    #     assertions are reading a bound, not a constant.
    at_cutoff = loaded.at("2026-08-24")
    assert at_cutoff.played == {}
    assert at_cutoff.kickoffs_known[fid][0] == pd.Timestamp("2026-08-21").date()
    assert at_cutoff.adjustments_known == {}
    # (ii) `observed_by <= cutoff` is unchanged by the two clocks: it is the
    #      rerun-an-old-forecast case and `min(C, O) == O` there.
    rerun = loaded.at("2026-09-30", observed_by="2026-08-24")
    assert rerun.played == {} and rerun.adjustments_known == {}
    assert rerun.kickoffs_known[fid][0] == pd.Timestamp("2026-08-21").date()
