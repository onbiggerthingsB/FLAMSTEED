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

    touched = {"arsenal", "coventry", "brentford", "tottenham", "hull", "man_united"}
    assert len(touched) == 6
    assert all(row(c) == (0, 0, 0, 0, 0, 0, 0, 0)
               for c in state.table_so_far if c not in touched)

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
    archive = season_mod.archive_season_state(
        frame, "2023/24", "2025-01-01", require_verified_adjustments=False)
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


def test_unverified_adjustment_rows_refused_for_scoring():
    frame = _synthetic_archive("2023/24", "2324", CLUBS_2023_24, "2023-08-11")
    with pytest.raises(season_mod.UnverifiedAdjustment):
        season_mod.archive_season_state(frame, "2023/24", "2024-06-30")

    # Positive control: the same call is fine once the operator opts out of the
    # gate explicitly, and fine for a season with no adjustment rows at all.
    state = season_mod.archive_season_state(
        frame, "2023/24", "2024-06-30", require_verified_adjustments=False)
    assert state.adjustments_known == {"everton": -8, "nottm_forest": -4}
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
