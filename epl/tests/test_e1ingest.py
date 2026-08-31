"""The E1 (EFL Championship) ingest, and the six blockers it had to clear.

The design reference is `reports/epl_lowerdiv_prereg.md` §0.6 (B1-B6); the
acquisition record that publishes the club enumeration these tests are written
against is `reports/epl_e1_acquisition.md`. Neither the fit nor the store is in
scope here: this is an archive builder and it stops at the parquet.

Every test below is behavioural. The six blockers, in the order the scout named
them:

    B1  fetch hardcodes E0            -> a division parameter, E0 the default
    B2  provenance keyed by code      -> {division}_{code}, in its own sidecar
    B3  380/20/19 assumed everywhere  -> per-division constants, E1 at 552/24/23
    B4  Championship spellings absent -> registry entries + the collision guard
    B5  a null key becomes club "None"-> it REFUSES at parse time instead
    B6  match_id carries no division  -> it does for E1; E0 ids are untouched

plus the constraint that outranks all six: the E0 path's behaviour, its bytes
and its ids do not move. Run with

    PYTHONPATH=src:. .venv/bin/pytest epl/tests/test_e1ingest.py -q
"""

from __future__ import annotations

import hashlib
import json
import re

import pandas as pd
import pytest

from epl import build, fetch, parse, paths, schema, teams, validate


# --------------------------------------------------------------------------
# The declared census, transcribed from reports/epl_e1_acquisition.md §2.
#
# It is the acquisition record's own table, pinned in code so a registry edit
# that drifts from the published enumeration fails a test rather than passing
# silently. When the network pass runs and MEASURES the census, a spelling it
# finds that is not here is an AcquisitionIncomplete, not a licence to edit
# this list into agreement.
# --------------------------------------------------------------------------
DECLARED_E1_MEMBERSHIP: dict[str, tuple[str, ...]] = {
    "1415": ("Birmingham", "Blackburn", "Blackpool", "Bolton", "Bournemouth",
             "Brentford", "Brighton", "Cardiff", "Charlton", "Derby", "Fulham",
             "Huddersfield", "Ipswich", "Leeds", "Middlesbrough", "Millwall",
             "Norwich", "Nott'm Forest", "Reading", "Rotherham",
             "Sheffield Weds", "Watford", "Wigan", "Wolves"),
    "1516": ("Birmingham", "Blackburn", "Bolton", "Brentford", "Brighton",
             "Bristol City", "Burnley", "Cardiff", "Charlton", "Derby",
             "Fulham", "Huddersfield", "Hull", "Ipswich", "Leeds",
             "Middlesbrough", "Milton Keynes Dons", "Nott'm Forest", "Preston",
             "QPR", "Reading", "Rotherham", "Sheffield Weds", "Wolves"),
    "1617": ("Aston Villa", "Barnsley", "Birmingham", "Blackburn", "Brentford",
             "Brighton", "Bristol City", "Burton", "Cardiff", "Derby", "Fulham",
             "Huddersfield", "Ipswich", "Leeds", "Newcastle", "Norwich",
             "Nott'm Forest", "Preston", "QPR", "Reading", "Rotherham",
             "Sheffield Weds", "Wigan", "Wolves"),
    "1718": ("Aston Villa", "Barnsley", "Birmingham", "Bolton", "Brentford",
             "Bristol City", "Burton", "Cardiff", "Derby", "Fulham", "Hull",
             "Ipswich", "Leeds", "Middlesbrough", "Millwall", "Norwich",
             "Nott'm Forest", "Preston", "QPR", "Reading", "Sheffield United",
             "Sheffield Weds", "Sunderland", "Wolves"),
    "1819": ("Aston Villa", "Birmingham", "Blackburn", "Bolton", "Brentford",
             "Bristol City", "Derby", "Hull", "Ipswich", "Leeds",
             "Middlesbrough", "Millwall", "Norwich", "Nott'm Forest", "Preston",
             "QPR", "Reading", "Rotherham", "Sheffield United",
             "Sheffield Weds", "Stoke", "Swansea", "West Brom", "Wigan"),
    "1920": ("Barnsley", "Birmingham", "Blackburn", "Brentford", "Bristol City",
             "Cardiff", "Charlton", "Derby", "Fulham", "Huddersfield", "Hull",
             "Leeds", "Luton", "Middlesbrough", "Millwall", "Nott'm Forest",
             "Preston", "QPR", "Reading", "Sheffield Weds", "Stoke", "Swansea",
             "West Brom", "Wigan"),
    "2021": ("Barnsley", "Birmingham", "Blackburn", "Bournemouth", "Brentford",
             "Bristol City", "Cardiff", "Coventry", "Derby", "Huddersfield",
             "Luton", "Middlesbrough", "Millwall", "Norwich", "Nott'm Forest",
             "Preston", "QPR", "Reading", "Rotherham", "Sheffield Weds",
             "Stoke", "Swansea", "Watford", "Wycombe"),
    "2122": ("Barnsley", "Birmingham", "Blackburn", "Blackpool", "Bournemouth",
             "Bristol City", "Cardiff", "Coventry", "Derby", "Fulham",
             "Huddersfield", "Hull", "Luton", "Middlesbrough", "Millwall",
             "Nott'm Forest", "Peterboro", "Preston", "QPR", "Reading",
             "Sheffield United", "Stoke", "Swansea", "West Brom"),
    "2223": ("Birmingham", "Blackburn", "Blackpool", "Bristol City", "Burnley",
             "Cardiff", "Coventry", "Huddersfield", "Hull", "Luton",
             "Middlesbrough", "Millwall", "Norwich", "Preston", "QPR",
             "Reading", "Rotherham", "Sheffield United", "Stoke", "Sunderland",
             "Swansea", "Watford", "West Brom", "Wigan"),
    "2324": ("Birmingham", "Blackburn", "Bristol City", "Cardiff", "Coventry",
             "Huddersfield", "Hull", "Ipswich", "Leeds", "Leicester",
             "Middlesbrough", "Millwall", "Norwich", "Plymouth", "Preston",
             "QPR", "Rotherham", "Sheffield Weds", "Southampton", "Stoke",
             "Sunderland", "Swansea", "Watford", "West Brom"),
    "2425": ("Blackburn", "Bristol City", "Burnley", "Cardiff", "Coventry",
             "Derby", "Hull", "Leeds", "Luton", "Middlesbrough", "Millwall",
             "Norwich", "Oxford", "Plymouth", "Portsmouth", "Preston", "QPR",
             "Sheffield United", "Sheffield Weds", "Stoke", "Sunderland",
             "Swansea", "Watford", "West Brom"),
    "2526": ("Birmingham", "Blackburn", "Bristol City", "Charlton", "Coventry",
             "Derby", "Hull", "Ipswich", "Leicester", "Middlesbrough",
             "Millwall", "Norwich", "Oxford", "Portsmouth", "Preston", "QPR",
             "Sheffield United", "Sheffield Weds", "Southampton", "Stoke",
             "Swansea", "Watford", "West Brom", "Wrexham"),
}

#: The 22 clubs the registry commit added, with the key each must resolve to.
#: Four canonical names deliberately differ from football-data's spelling
#: (§3.1 of the acquisition record); the source spelling stays an alias.
DECLARED_NEW_CLUBS: dict[str, str] = {
    "Barnsley": "barnsley",
    "Birmingham": "birmingham",
    "Blackburn": "blackburn",
    "Blackpool": "blackpool",
    "Bolton": "bolton",
    "Bristol City": "bristol_city",
    "Burton": "burton",
    "Charlton": "charlton",
    "Derby": "derby",
    "Millwall": "millwall",
    "Milton Keynes Dons": "mk_dons",
    "Oxford": "oxford",
    "Peterboro": "peterborough",
    "Plymouth": "plymouth",
    "Portsmouth": "portsmouth",
    "Preston": "preston",
    "Reading": "reading",
    "Rotherham": "rotherham",
    "Sheffield Weds": "sheffield_wednesday",
    "Wigan": "wigan",
    "Wrexham": "wrexham",
    "Wycombe": "wycombe",
}

#: Every club the pinned E0 archive can contain, as the registry held them
#: before the Championship entries landed. Pinned so an E1 registry edit that
#: moved an E0 key would fail here rather than in a fit six weeks from now.
E0_KEYS_BEFORE_E1 = frozenset({
    "arsenal", "aston_villa", "bournemouth", "brentford", "brighton", "burnley",
    "cardiff", "chelsea", "coventry", "crystal_palace", "everton", "fulham",
    "huddersfield", "hull", "ipswich", "leeds", "leicester", "liverpool",
    "luton", "man_city", "man_united", "middlesbrough", "newcastle", "norwich",
    "nottm_forest", "qpr", "sheffield_united", "southampton", "stoke",
    "sunderland", "swansea", "tottenham", "watford", "west_brom", "west_ham",
    "wolves",
})


# ==========================================================================
# B4 — the Championship registry, and the collision guard that makes it safe
# ==========================================================================

def test_every_declared_e1_spelling_resolves():
    """The whole point of the registry commit: no Championship club is unknown.

    A spelling that does not resolve is `AcquisitionIncomplete` at build time,
    never a new club — but it should not get that far, so it is caught here.
    """
    unresolved = []
    for clubs in DECLARED_E1_MEMBERSHIP.values():
        for name in clubs:
            try:
                teams.resolve(name)
            except teams.UnknownTeamError:
                unresolved.append(name)
    assert sorted(set(unresolved)) == []


def test_the_declared_census_is_twelve_complete_seasons():
    """288 = 12 x 24. A list of remembered clubs would not sum."""
    assert len(DECLARED_E1_MEMBERSHIP) == 12
    assert all(len(v) == 24 for v in DECLARED_E1_MEMBERSHIP.values())
    assert all(len(set(v)) == 24 for v in DECLARED_E1_MEMBERSHIP.values())
    assert sum(len(v) for v in DECLARED_E1_MEMBERSHIP.values()) == 288


def test_the_new_clubs_resolve_to_the_published_keys():
    for spelling, key in DECLARED_NEW_CLUBS.items():
        assert teams.team_key(spelling) == key, spelling


def test_the_new_keys_are_disjoint_from_every_e0_key():
    """A Championship club may not land on a Premier League club's key."""
    assert set(DECLARED_NEW_CLUBS.values()) & E0_KEYS_BEFORE_E1 == set()


def test_no_e0_key_moved_when_the_championship_entries_landed():
    """The E0 archive's keys are pinned in artifacts everywhere. None moved."""
    live = {key for _, key in teams.known_spellings().values()}
    assert E0_KEYS_BEFORE_E1 <= live
    for spelling in ("Man Utd", "Nott'm Forest", "Sheffield Utd", "West Brom",
                     "Wolves", "Spurs", "Man City"):
        assert teams.resolve(spelling)[1] in E0_KEYS_BEFORE_E1


def test_the_registry_holds_exactly_the_published_club_count():
    """36 E0 clubs + 22 Championship clubs = 58, as published."""
    assert teams.registry_size() == 58


def test_sheffield_wednesday_did_not_fold_onto_sheffield_united():
    """The near miss the acquisition record names by name."""
    assert teams.team_key("Sheffield Weds") == "sheffield_wednesday"
    assert teams.team_key("Sheffield Wednesday") == "sheffield_wednesday"
    for united in ("Sheffield United", "Sheffield Utd", "Sheff Utd",
                   "Sheff United"):
        assert teams.team_key(united) == "sheffield_united"


def test_burton_did_not_fold_onto_burnley():
    assert teams.team_key("Burton") == "burton"
    assert teams.team_key("Burnley") == "burnley"


def test_football_datas_abbreviations_are_aliases_not_canonical_names():
    """`Sheffield Weds` is what the source prints; it is not a display name."""
    assert teams.canonical_name("Sheffield Weds") == "Sheffield Wednesday"
    assert teams.canonical_name("Peterboro") == "Peterborough"
    assert teams.canonical_name("Burton") == "Burton Albion"


def test_an_unregistered_lower_division_club_still_raises():
    """The registry grew; it did not become permissive."""
    for name in ("Accrington Stanley", "Barcelona", "Salford City"):
        with pytest.raises(teams.UnknownTeamError):
            teams.resolve(name)


def test_the_collision_guard_refuses_a_fold_that_maps_two_clubs():
    """B4's safety net, exercised rather than asserted about.

    The guard is what makes a DECLARED census safe: a wrong spelling whose fold
    lands on a registered club stops every import of `epl.teams`, loudly.
    """
    poisoned = dict(teams._REGISTRY)
    poisoned["Sheffield  Weds."] = ("some_other_club", ())
    with pytest.raises(ValueError, match="registry collision"):
        teams._build_index(poisoned)


# ==========================================================================
# The constraint that outranks the six blockers: the E0 archive does not move
# ==========================================================================

#: The pinned E0 archive. `data/` is gitignored, so a fresh clone has no file to
#: check and the guard skips rather than failing for the wrong reason — but on
#: any machine that HAS the archive, this is the byte check.
E0_MATCHES_SHA256 = (
    "323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf"
)


def _e0_archive() -> pd.DataFrame:
    if not paths.MATCHES_PARQUET.exists():
        pytest.skip(f"no E0 archive at {paths.MATCHES_PARQUET} (data/ is gitignored)")
    return pd.read_parquet(paths.MATCHES_PARQUET)


def test_the_pinned_e0_archive_is_byte_identical():
    """The hard constraint, as a test. Nothing in the E1 build rewrites it."""
    if not paths.MATCHES_PARQUET.exists():
        pytest.skip("no E0 archive on this machine (data/ is gitignored)")
    digest = hashlib.sha256(paths.MATCHES_PARQUET.read_bytes()).hexdigest()
    assert digest == E0_MATCHES_SHA256


def test_every_e0_raw_spelling_still_resolves_to_the_same_key():
    """B4's own guard: 22 new clubs, and not one E0 row's key moved.

    Re-resolves the archive's verbatim source spellings through the ENLARGED
    registry and compares against the keys the archive was built with.
    """
    archive = _e0_archive()
    for raw_col, key_col in (("home_team_raw", "home_key"),
                             ("away_team_raw", "away_key")):
        pairs = archive[[raw_col, key_col]].drop_duplicates()
        for raw, key in pairs.itertuples(index=False):
            assert teams.team_key(raw) == key, raw


def test_the_e0_archive_contains_no_championship_only_club():
    """The Elo anchor reads this file. No E1 row, and no E1 key, is in it."""
    archive = _e0_archive()
    keys = set(archive["home_key"]) | set(archive["away_key"])
    assert keys <= E0_KEYS_BEFORE_E1
    assert keys & set(DECLARED_NEW_CLUBS.values()) == set()


# ==========================================================================
# A synthetic season, built to the shape the validator asserts
# ==========================================================================

def _synthetic_season(
    club_keys: list[str],
    season_code: str = "2425",
    *,
    start: str = "2024-08-10",
    null_key_at: int | None = None,
) -> pd.DataFrame:
    """A complete double round-robin over `club_keys`, in schema column order.

    Every ordered (home, away) pair once; matchdays of `n/2` fixtures spaced a
    week apart so the whole season lands inside the validator's date window.
    `null_key_at` nulls one row's home key, which is the phantom-club input.
    """
    pairs = [(h, a) for h in club_keys for a in club_keys if h != a]
    per_day = max(1, len(club_keys) // 2)
    base = pd.Timestamp(start)
    dates = [base + pd.Timedelta(days=7 * (i // per_day)) for i in range(len(pairs))]

    home_keys = [h for h, _ in pairs]
    away_keys = [a for _, a in pairs]
    if null_key_at is not None:
        home_keys = list(home_keys)
        home_keys[null_key_at] = None

    fthg = [(i % 4) for i in range(len(pairs))]
    ftag = [(i % 3) for i in range(len(pairs))]
    ftr = ["H" if h > a else ("A" if h < a else "D") for h, a in zip(fthg, ftag)]

    frame = pd.DataFrame({
        "match_id": [f"synthetic{i:06d}" for i in range(len(pairs))],
        "season": f"20{season_code[:2]}/{season_code[2:]}",
        "season_code": season_code,
        "date": pd.to_datetime(dates),
        "time": pd.Series([pd.NA] * len(pairs), dtype="string"),
        "kickoff": pd.Series([pd.NaT] * len(pairs), dtype="datetime64[ns]"),
        "home_team_raw": home_keys,
        "away_team_raw": away_keys,
        "home_team": home_keys,
        "away_team": away_keys,
        "home_key": home_keys,
        "away_key": away_keys,
        "fthg": pd.array(fthg, dtype="Int16"),
        "ftag": pd.array(ftag, dtype="Int16"),
        "ftr": pd.Series(ftr, dtype="string"),
        "played": True,
    })
    for col in schema.ODDS_COLUMNS:
        frame[col] = pd.Series([pd.NA] * len(pairs), dtype="string") \
            if col == "odds_source" else float("nan")
    return frame[schema.COLUMNS]


E0_CLUBS = [f"club_e0_{i:02d}" for i in range(20)]
E1_CLUBS = [f"club_e1_{i:02d}" for i in range(24)]


# ==========================================================================
# B3 — the shape constants are per division; E0 keeps 380/20/19
# ==========================================================================

def test_the_e0_shape_constants_did_not_move():
    assert schema.TEAMS_PER_SEASON == 20
    assert schema.MATCHES_PER_SEASON == 380


def test_the_division_shapes_are_the_published_arithmetic():
    e0 = schema.division_shape("E0")
    assert (e0.teams, e0.matches, e0.opponents) == (20, 380, 19)
    e1 = schema.division_shape("E1")
    assert (e1.teams, e1.matches, e1.opponents) == (24, 552, 23)
    assert e1.matches == e1.teams * (e1.teams - 1)


def test_the_default_division_is_e0():
    assert schema.DEFAULT_DIVISION == "E0"
    assert schema.division_shape() == schema.division_shape("E0")


def test_an_unknown_division_refuses_rather_than_guessing_a_shape():
    with pytest.raises(KeyError):
        schema.division_shape("E2")


def test_a_championship_season_validates_at_552_24_23():
    frame = _synthetic_season(E1_CLUBS)
    report = validate.validate_season(frame, "2425", "2024/25", division="E1")
    assert report.passed, [c.to_json() for c in report.failures]
    names = {c.name for c in report.checks}
    assert "match_count_552" in names
    assert "distinct_teams_24" in names


def test_the_same_championship_season_FAILS_the_e0_validator():
    """The blocker, stated as behaviour: 552/24 is not 380/20.

    Before the shape was a parameter this was the only answer available, and a
    real Championship season would have been reported as a broken one.
    """
    frame = _synthetic_season(E1_CLUBS)
    report = validate.validate_season(frame, "2425", "2024/25")
    failed = {c.name for c in report.failures}
    assert "match_count_380" in failed
    assert "distinct_teams_20" in failed


def test_the_e0_validator_is_unchanged_on_an_e0_season():
    frame = _synthetic_season(E0_CLUBS)
    report = validate.validate_season(frame, "2425", "2024/25")
    assert report.passed, [c.to_json() for c in report.failures]
    names = [c.name for c in report.checks]
    assert names[:4] == ["all_fixtures_played", "match_count_380",
                         "teams_resolved", "distinct_teams_20"]


def test_a_championship_season_one_club_short_fails_the_round_robin_check():
    frame = _synthetic_season(E1_CLUBS[:23])
    report = validate.validate_season(frame, "2425", "2024/25", division="E1")
    failed = {c.name for c in report.failures}
    assert "match_count_552" in failed
    assert "distinct_teams_24" in failed


def test_the_opponent_count_is_23_not_19():
    """A club with 19 home fixtures is a defect in E1, not a complete season."""
    frame = _synthetic_season(E1_CLUBS)
    trimmed = frame[~((frame["home_key"] == E1_CLUBS[0])
                      & (frame["away_key"].isin(E1_CLUBS[1:5])))]
    report = validate.validate_season(trimmed, "2425", "2024/25", division="E1")
    failed = {c.name for c in report.failures}
    assert "double_round_robin" in failed


# ==========================================================================
# B1/B2 — the output and provenance paths, per division and disjoint
# ==========================================================================

def test_the_e0_output_paths_are_exactly_what_they_were():
    assert paths.matches_parquet("E0") == paths.MATCHES_PARQUET
    assert paths.manifest_path("E0") == paths.MANIFEST_PATH
    assert paths.team_mapping_path("E0") == paths.TEAM_MAPPING_PATH
    assert paths.provenance_path("E0") == paths.PROVENANCE_PATH
    assert paths.matches_parquet() == paths.MATCHES_PARQUET


def test_the_e1_outputs_are_their_own_files():
    assert paths.matches_parquet("E1").name == "matches_e1.parquet"
    assert paths.manifest_path("E1").name == "manifest_e1.json"
    assert paths.team_mapping_path("E1").name == "team_name_mapping_e1.json"
    assert paths.provenance_path("E1").name == "provenance_e1.json"


def test_no_e1_artifact_path_collides_with_an_e0_one():
    """B2's file half: the E1 build cannot land on top of an E0 artifact."""
    e0 = {paths.matches_parquet("E0"), paths.manifest_path("E0"),
          paths.team_mapping_path("E0"), paths.provenance_path("E0"),
          paths.MATCHES_CSV}
    e1 = {paths.matches_parquet("E1"), paths.manifest_path("E1"),
          paths.team_mapping_path("E1"), paths.provenance_path("E1")}
    assert e0 & e1 == set()


# ==========================================================================
# B1 — the source URL and the cache path take the division
# ==========================================================================

def test_the_e0_url_is_byte_for_byte_what_it_was():
    """`epl.livecycle` composes its refetch URL from this pattern."""
    assert fetch.BASE_URL == (
        "https://www.football-data.co.uk/mmz4281/{season_code}/E0.csv"
    )
    for code in fetch.SEASON_CODES:
        assert fetch.url_for(code) == fetch.BASE_URL.format(season_code=code)


def test_the_e1_url_names_the_e1_file():
    assert fetch.url_for("1415", division="E1") == (
        "https://www.football-data.co.uk/mmz4281/1415/E1.csv"
    )
    assert fetch.url_for("2526", division="E1").endswith("/2526/E1.csv")


def test_the_cache_path_carries_the_division_and_e0_is_unchanged():
    assert fetch.raw_path("1415").name == "E0_1415.csv"
    assert fetch.raw_path("1415", division="E1").name == "E1_1415.csv"
    assert fetch.raw_path("1415") != fetch.raw_path("1415", division="E1")


def test_an_unknown_division_has_no_url():
    with pytest.raises(KeyError):
        fetch.url_for("1415", division="E2")


# ==========================================================================
# B2 — the provenance key, and the record an E1 fetch would have overwritten
# ==========================================================================

def test_the_provenance_key_carries_the_division_for_e1_only():
    """E0 keeps the bare code: twelve records on disk are keyed that way."""
    assert fetch.provenance_key("1415") == "1415"
    assert fetch.provenance_key("1415", division="E0") == "1415"
    assert fetch.provenance_key("1415", division="E1") == "E1_1415"


def _place_cached_csv(
    raw_dir, division: str, code: str, clubs: list[str], *, pad: bool = False
) -> None:
    """A cached football-data CSV for one season, written straight to the cache.

    Hand-placed rather than downloaded: there is no network in this phase, and
    `fetch_season` treats an unrecorded cached file as an observation to record,
    which is the exact path being tested.

    `pad=True` appends the line of bare commas football-data ends its real files
    with — `data/epl/raw/E0_1415.csv` line 382 is exactly this — so a test can
    exercise the vendor's own formatting rather than an idealised file.
    """
    pairs = [(h, a) for h in clubs for a in clubs if h != a]
    header = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR"
    lines = [header]
    per_day = max(1, len(clubs) // 2)
    base = pd.Timestamp("20%s-08-10" % code[:2])
    for i, (h, a) in enumerate(pairs):
        day = base + pd.Timedelta(days=7 * (i // per_day))
        hg, ag = i % 4, i % 3
        res = "H" if hg > ag else ("A" if hg < ag else "D")
        lines.append(f"{division},{day:%d/%m/%Y},{h},{a},{hg},{ag},{res}")
    if pad:
        lines.append("," * (header.count(",")))
    (raw_dir / f"{division}_{code}.csv").write_text("\n".join(lines) + "\n")


class NetworkReached(AssertionError):
    """A test tried to download something. It must not."""


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    """A throwaway data root with the network wired shut and the archive fenced.

    THREE guarantees, and every one of them was learned the hard way.

    1.  **No network.** A `build()` call that fell through to the twelve default
        season codes found eleven of them uncached and went to football-data for
        them. The real download is a separate, once-only, deliberate act — so
        `_download` raises here, and a cache miss in a test is a test bug rather
        than a quiet HTTP request.
    2.  **A temporary data root.** `paths.DATA_DIR` and `paths.RAW_DIR` are
        repointed, which is enough for anything that resolves a path through
        `epl.paths`' accessors, because they read those names at CALL time.
    3.  **The pinned archive is fenced anyway.** (2) is NOT enough on its own.
        `paths.MATCHES_PARQUET` and its siblings are bound at IMPORT, so
        repointing `DATA_DIR` does not move them: code that writes through a
        constant writes to the REAL `data/epl/matches.parquet` from inside a
        test with a temporary root. That is not hypothetical — an earlier draft
        of `build()` did exactly this and overwrote the pinned 4,560-row archive
        with a 380-row synthetic season. So this fixture snapshots the real file
        and, at teardown, RESTORES it and fails loudly if anything moved it.
        The guard is the containment; `test_an_e0_build_cannot_reach_the_pinned
        _archive` is the test that the discipline itself holds.
    """
    data = tmp_path / "epl"
    raw = data / "raw"
    raw.mkdir(parents=True)
    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setattr(paths, "RAW_DIR", raw)

    def _refuse(url: str):
        raise NetworkReached(
            f"a test tried to download {url}. The ingest is tested against "
            f"synthetic CSVs; the real fetch is a deliberate, separate act."
        )

    monkeypatch.setattr(fetch, "_download", _refuse)

    fenced = paths.MATCHES_PARQUET
    before = fenced.read_bytes() if fenced.exists() else None

    yield raw

    after = fenced.read_bytes() if fenced.exists() else None
    if after != before:
        if before is not None:
            fenced.write_bytes(before)          # put it back before failing
        raise AssertionError(
            f"a test wrote to the pinned archive at {fenced}. It has been "
            f"restored. Something resolved an output path through a module "
            f"constant instead of a `paths.*(division)` accessor — the "
            f"constants are bound at import and this fixture's temporary "
            f"DATA_DIR does not move them."
        )


def test_the_fixture_really_does_close_the_network(cache_dir):
    """The guard itself, exercised. A cache miss must not become a request."""
    with pytest.raises(NetworkReached):
        fetch.fetch_season("1415", division="E1")


def test_an_e1_fetch_does_not_overwrite_the_e0_record_for_the_same_season(cache_dir):
    """B2 as behaviour: one sidecar keyed by bare code held ONE record per code.

    Both divisions publish a `1415` file. Under the old scheme the second one
    recorded would have replaced the first, and the manifest would then have
    attested the wrong URL, the wrong bytes and the wrong digest for a season
    that was still on disk and still being parsed.
    """
    _place_cached_csv(cache_dir, "E0", "1415", ["A", "B", "C", "D"])
    _place_cached_csv(cache_dir, "E1", "1415", ["W", "X", "Y", "Z"])

    e0 = fetch.fetch_season("1415")
    e0_sidecar_after_e0 = paths.provenance_path("E0").read_bytes()

    e1 = fetch.fetch_season("1415", division="E1")

    assert e0.division == "E0" and e1.division == "E1"
    assert e0.url.endswith("/1415/E0.csv")
    assert e1.url.endswith("/1415/E1.csv")
    assert e0.sha256 != e1.sha256

    # Two sidecars, disjoint key sets, and the E0 file untouched by the E1 pass.
    e0_records = json.loads(paths.provenance_path("E0").read_text())
    e1_records = json.loads(paths.provenance_path("E1").read_text())
    assert set(e0_records) == {"1415"}
    assert set(e1_records) == {"E1_1415"}
    assert set(e0_records) & set(e1_records) == set()
    assert paths.provenance_path("E0").read_bytes() == e0_sidecar_after_e0
    assert e0_records["1415"]["sha256"] == e0.sha256


def test_a_cached_e1_file_that_changed_underneath_us_refuses(cache_dir):
    """The cache-first, hash-pinned discipline, carried to E1 unweakened."""
    _place_cached_csv(cache_dir, "E1", "2425", ["W", "X", "Y", "Z"])
    fetch.fetch_season("2425", division="E1")

    target = fetch.raw_path("2425", division="E1")
    target.write_text(target.read_text() + "E1,01/01/2025,W,X,9,9,D\n")
    with pytest.raises(fetch.FetchError, match="changed on disk"):
        fetch.fetch_season("2425", division="E1")


def test_a_second_e1_fetch_reads_the_cache_and_re_verifies(cache_dir):
    _place_cached_csv(cache_dir, "E1", "2425", ["W", "X", "Y", "Z"])
    first = fetch.fetch_season("2425", division="E1")
    second = fetch.fetch_season("2425", division="E1")
    assert second.from_cache is True
    assert second.sha256 == first.sha256
    assert second.fetched_at == first.fetched_at


def test_read_raw_reads_the_division_it_is_asked_for(cache_dir):
    _place_cached_csv(cache_dir, "E0", "1415", ["A", "B", "C", "D"])
    _place_cached_csv(cache_dir, "E1", "1415", ["W", "X", "Y", "Z"])
    assert "A,B" in fetch.read_raw("1415")
    assert "A,B" not in fetch.read_raw("1415", division="E1")
    assert "W,X" in fetch.read_raw("1415", division="E1")


# ==========================================================================
# B6 — the match_id carries the division for E1, and E0 ids do not move
# ==========================================================================

#: sha256("2425|2024-08-16|arsenal|chelsea")[:16]. Pinned because E0 match_ids
#: are recorded in artifacts all over the repository — a change to the recipe
#: would silently orphan every one of them.
PINNED_E0_MATCH_ID = "3326fa3323ba4b53"


def test_the_e0_match_id_recipe_is_unchanged():
    got = parse._match_id("2425", pd.Timestamp("2024-08-16"), "arsenal", "chelsea")
    assert got == PINNED_E0_MATCH_ID
    assert got == hashlib.sha256(
        b"2425|2024-08-16|arsenal|chelsea").hexdigest()[:16]
    # Naming E0 explicitly must give the same id as not naming a division.
    assert parse._match_id(
        "2425", pd.Timestamp("2024-08-16"), "arsenal", "chelsea",
        division="E0") == PINNED_E0_MATCH_ID


def test_the_e1_match_id_carries_the_division():
    date = pd.Timestamp("2024-08-16")
    e1 = parse._match_id("2425", date, "derby", "preston", division="E1")
    assert e1 == hashlib.sha256(
        b"E1|2425|2024-08-16|derby|preston").hexdigest()[:16]
    assert e1 != parse._match_id("2425", date, "derby", "preston")


def test_the_same_fixture_in_two_divisions_gets_two_ids():
    """The merge hazard: without the division these collide exactly.

    Two clubs can meet on the same date in both a cup-relegated season's E0 file
    and an E1 file only in principle — but `match_id` is the key a union store
    is built on, and a key that CAN collide is one that eventually does.
    """
    date = pd.Timestamp("2025-01-18")
    assert (parse._match_id("2425", date, "leeds", "burnley")
            != parse._match_id("2425", date, "leeds", "burnley", division="E1"))


def test_every_id_in_the_pinned_e0_archive_still_reproduces():
    """B6's real proof, against the real archive rather than one pinned string.

    `PINNED_E0_MATCH_ID` fixes the recipe at one point. This fixes it at all
    4,560 of them: every `match_id` the pinned archive was built with is
    recomputed from that row's own (season_code, date, home_key, away_key) and
    must come back identical. Those ids are the join key for every artifact in
    the repository that references a Premier League match, so a recipe change
    would not break a fit — it would silently orphan the lot.
    """
    archive = _e0_archive()
    recomputed = [
        parse._match_id(r.season_code, r.date, r.home_key, r.away_key)
        for r in archive.itertuples()
    ]
    assert recomputed == archive["match_id"].tolist()


def test_the_division_prefix_would_have_moved_every_one_of_those_ids():
    """The same 4,560 rows, and why E0's absent prefix is not cosmetic.

    Had E0 taken the prefix too, not one archived id would have survived. The
    guard above therefore has teeth: it is not passing because the two recipes
    happen to agree.
    """
    archive = _e0_archive()
    prefixed = {
        parse._match_id(r.season_code, r.date, r.home_key, r.away_key,
                        division="E1")
        for r in archive.itertuples()
    }
    assert prefixed & set(archive["match_id"]) == set()
    assert len(prefixed) == len(archive)


# ==========================================================================
# B5 — a null club key REFUSES; it never becomes the phantom club "None"
# ==========================================================================

def test_an_unregistered_club_in_an_e1_file_refuses_at_parse_time(cache_dir):
    """E1 refuses at parse time, before the projector's independent guard.

    The projector now also refuses null keys as defense-in-depth, but that does
    not weaken the E1 ingest contract: an unregistered Championship club never
    becomes a tidy archive row in the first place.
    """
    _place_cached_csv(cache_dir, "E1", "2425",
                      ["Derby", "Preston", "Millwall", "Not A Real Club"])
    fetch.fetch_season("2425", division="E1")
    with pytest.raises(parse.PhantomClub) as exc:
        parse.parse_season("2425", division="E1")
    message = str(exc.value)
    assert "Not A Real Club" in message
    assert "2024/25" in message


def test_the_refusal_names_the_date_and_the_side(cache_dir):
    """The message has to be enough to write the registry entry from."""
    _place_cached_csv(cache_dir, "E1", "2425",
                      ["Derby", "Preston", "Millwall", "Nonesuch Rovers"])
    fetch.fetch_season("2425", division="E1")
    with pytest.raises(parse.PhantomClub) as exc:
        parse.parse_season("2425", division="E1")
    message = str(exc.value)
    assert re.search(
        r"\d{4}-\d{2}-\d{2} (home|away)='Nonesuch Rovers'", message
    ), message
    assert "epl/teams.py" in message
    assert "do not drop the season" in message


def test_a_fully_registered_e1_season_parses(cache_dir):
    clubs = ["Derby", "Preston", "Millwall", "Sheffield Weds"]
    _place_cached_csv(cache_dir, "E1", "2425", clubs)
    fetch.fetch_season("2425", division="E1")
    parsed = parse.parse_season("2425", division="E1")
    assert parsed.division == "E1"
    assert len(parsed.frame) == 12
    assert parsed.unknown_teams == []
    assert set(parsed.frame["home_key"]) == {
        "derby", "preston", "millwall", "sheffield_wednesday"}
    assert list(parsed.frame.columns) == schema.COLUMNS


def test_e0_still_retains_the_row_and_reports_the_issue(cache_dir):
    """E0's behaviour is NOT changed by B5. It reports; it does not refuse.

    The daily live cycle depends on an unmapped E0 name being a reported issue
    rather than an exception, so the refusal is scoped to divisions whose
    archive this build introduces.
    """
    _place_cached_csv(cache_dir, "E0", "2425",
                      ["Arsenal", "Chelsea", "Everton", "Not A Real Club"])
    fetch.fetch_season("2425")
    parsed = parse.parse_season("2425")
    assert parsed.unknown_teams == ["Not A Real Club"]
    assert parsed.frame["home_key"].isna().any()
    assert any("unregistered club spelling" in i for i in parsed.issues)


def test_the_store_projection_is_a_second_phantom_club_boundary():
    """A null key refuses even if an upstream parser retained the row.

    E1 still refuses earlier in :func:`epl.parse.parse_season`; this is
    defense-in-depth for E0 and for any hand-built frame that reaches the model
    adapter without passing that division-specific guard.
    """
    from epl import fit

    # Exactly the shape `epl.parse` produces for E0: an object column of keys
    # with a None wherever a spelling did not resolve. `home_team_raw` carries
    # the two spellings that failed, so the frame going IN can still tell the
    # two clubs apart — which is what makes the frame coming OUT damning.
    frame = pd.DataFrame({
        "match_id": ["a", "b", "c"],
        "date": pd.to_datetime(["2024-08-10", "2024-08-11", "2024-08-12"]),
        "home_team_raw": ["Nonesuch Rovers", "Utterly Different FC", "Derby"],
        "home_key": pd.Series([None, None, "derby"], dtype="object"),
        "away_key": pd.Series(["preston", "millwall", "preston"], dtype="object"),
        "fthg": [1, 2, 0],
        "ftag": [0, 1, 0],
        "played": [True, True, True],
    })

    with pytest.raises(ValueError, match="null/unresolved") as exc:
        fit.to_store_frame(frame)
    assert "home_key" in str(exc.value)
    assert "a" in str(exc.value) and "b" in str(exc.value)


# ==========================================================================
# The orchestrator — `python -m epl.build --division E1`
#
# THE HAZARD THESE TESTS EXIST INSIDE. `epl.paths` exposes both module-level
# constants (`paths.MATCHES_PARQUET`) and call-time accessors
# (`paths.matches_parquet(division)`). The constants are bound to `DATA_DIR` at
# IMPORT, so monkeypatching `DATA_DIR` does not move them — a `build()` that
# wrote through a constant would write to the REAL, pinned archive from inside a
# test with a temporary data root. `test_an_e0_build_cannot_reach_the_pinned
# _archive` is the test that says so, and it is the reason `build` resolves
# every output through an accessor.
# ==========================================================================

#: 20 registered E0 spellings — a synthetic Premier League season.
E0_SEASON_SPELLINGS = (
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton",
    "Burnley", "Chelsea", "Crystal Palace", "Everton", "Fulham", "Ipswich",
    "Liverpool", "Man City", "Man United", "Newcastle", "Nott'm Forest",
    "Southampton", "Tottenham", "West Ham", "Wolves",
)

#: 24 registered E1 spellings — the declared 2024/25 Championship, verbatim.
E1_SEASON_SPELLINGS = DECLARED_E1_MEMBERSHIP["2425"]


def _e1_artifacts_present() -> dict[str, bool]:
    return {
        kind: getter("E1").exists()
        for kind, getter in (
            ("matches", paths.matches_parquet),
            ("manifest", paths.manifest_path),
            ("team_mapping", paths.team_mapping_path),
        )
    }


def _e0_artifacts_present() -> dict[str, bool]:
    return {
        kind: getter("E0").exists()
        for kind, getter in (
            ("matches", paths.matches_parquet),
            ("manifest", paths.manifest_path),
            ("team_mapping", paths.team_mapping_path),
        )
    }


def test_an_e1_build_writes_its_own_artifacts_and_no_e0_one(cache_dir):
    """B1+B2+B3 at the orchestrator: one command, three E1 files, no E0 file."""
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    manifest = build.build(("2425",), division="E1")

    assert all(_e1_artifacts_present().values()), _e1_artifacts_present()
    assert not any(_e0_artifacts_present().values()), _e0_artifacts_present()
    assert manifest["totals"]["matches"] == 552
    assert manifest["totals"]["distinct_clubs"] == 24


def test_the_e1_build_writes_552_rows_and_the_declared_24_clubs(cache_dir):
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    build.build(("2425",), division="E1")

    frame = pd.read_parquet(paths.matches_parquet("E1"))
    assert len(frame) == 552
    keys = set(frame["home_key"]) | set(frame["away_key"])
    assert len(keys) == 24
    assert keys == {teams.team_key(s) for s in E1_SEASON_SPELLINGS}
    assert list(frame.columns) == schema.COLUMNS
    assert frame["home_key"].notna().all() and frame["away_key"].notna().all()


def test_the_e1_season_passes_every_structural_check(cache_dir):
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    manifest = build.build(("2425",), division="E1")

    entry = manifest["seasons"][0]
    assert entry["validation"]["passed"], entry["validation"]
    assert entry["validation"]["division"] == "E1"
    names = {c["name"] for c in entry["validation"]["checks"]}
    assert "match_count_552" in names
    assert "distinct_teams_24" in names
    assert entry["matches"] == 552
    assert entry["teams"] == 24


def test_every_id_the_e1_build_writes_carries_the_division(cache_dir):
    """B6 end to end: the archive's own ids, not a recipe call in isolation."""
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    build.build(("2425",), division="E1")

    frame = pd.read_parquet(paths.matches_parquet("E1"))
    for row in frame.itertuples():
        assert row.match_id == parse._match_id(
            row.season_code, row.date, row.home_key, row.away_key, division="E1")
        assert row.match_id != parse._match_id(
            row.season_code, row.date, row.home_key, row.away_key)
    assert frame["match_id"].is_unique


def test_the_e1_manifest_names_the_e1_source_and_the_e1_paths(cache_dir):
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    manifest = build.build(("2425",), division="E1")

    assert manifest["source"]["division"] == "E1 (EFL Championship)"
    assert manifest["source"]["url_pattern"] == (
        "https://www.football-data.co.uk/mmz4281/{season_code}/E1.csv"
    )
    assert manifest["output"]["matches"]["path"].endswith("matches_e1.parquet")
    assert manifest["output"]["provenance"].endswith("provenance_e1.json")
    assert manifest["output"]["team_name_mapping"].endswith(
        "team_name_mapping_e1.json")
    # And the record on disk is the manifest that was returned.
    assert json.loads(paths.manifest_path("E1").read_text()) == manifest


# --------------------------------------------------------------------------
# The strict gate — an E1 build REFUSES rather than writing a partial archive
# --------------------------------------------------------------------------

def test_an_incomplete_e1_season_refuses_and_writes_nothing(cache_dir):
    """§5.4 of the acquisition record, as behaviour.

    Four clubs is 12 matches, not 552. The E0 orchestrator would have written
    the parquet anyway and recorded the failure in the manifest; for a division
    whose archive this build introduces, a partial archive is worse than none —
    it would be pinned as-found by an experiment that cannot tell it is short.
    """
    _place_cached_csv(cache_dir, "E1", "2425", ["Derby", "Preston", "Millwall",
                                                "Sheffield Weds"])
    with pytest.raises(build.AcquisitionIncomplete) as exc:
        build.build(("2425",), division="E1")

    assert "match_count_552" in str(exc.value)
    assert not any(_e1_artifacts_present().values()), _e1_artifacts_present()


def test_the_refusal_happens_before_the_parquet_is_written(cache_dir):
    """A pre-existing E1 archive is not truncated by a build that then refuses."""
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    build.build(("2425",), division="E1")
    good = paths.matches_parquet("E1").read_bytes()

    _place_cached_csv(cache_dir, "E1", "2324", ["Derby", "Preston", "Millwall",
                                                "Sheffield Weds"])
    with pytest.raises(build.AcquisitionIncomplete):
        build.build(("2425", "2324"), division="E1")

    assert paths.matches_parquet("E1").read_bytes() == good


def test_an_unregistered_e1_club_refuses_at_build_time_too(cache_dir):
    """B5 through the orchestrator: `PhantomClub` propagates, nothing is written."""
    _place_cached_csv(cache_dir, "E1", "2425", ["Derby", "Preston", "Millwall",
                                                "Not A Real Club"])
    with pytest.raises(parse.PhantomClub):
        build.build(("2425",), division="E1")
    assert not any(_e1_artifacts_present().values())


def test_the_strict_gate_lets_the_vendors_blank_trailing_row_through(cache_dir):
    """The one issue that is the parser working, not the data failing.

    Every football-data season file ends with a line of bare commas. If the gate
    treated that as a defect, no real season would ever build. The gate and the
    parser derive the string from the SAME function, so this stays true when the
    wording changes.
    """
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS),
                      pad=True)
    manifest = build.build(("2425",), division="E1")

    assert paths.matches_parquet("E1").exists()
    assert manifest["totals"]["matches"] == 552
    assert any(parse.blank_rows_issue(1) in i for i in manifest["issues"])


def test_a_reworded_blank_row_issue_still_passes_the_gate(cache_dir, monkeypatch):
    """The gate recognises the issue by DERIVING it, never by matching prose."""
    monkeypatch.setattr(
        parse, "blank_rows_issue",
        lambda n: f"[vendor padding] {n} empty line(s) at end of file")
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS),
                      pad=True)
    manifest = build.build(("2425",), division="E1")

    assert paths.matches_parquet("E1").exists()
    assert any("[vendor padding]" in i for i in manifest["issues"])


# --------------------------------------------------------------------------
# The E0 orchestrator did not move
# --------------------------------------------------------------------------

def test_an_e0_build_still_writes_the_e0_artifacts(cache_dir):
    _place_cached_csv(cache_dir, "E0", "2425", list(E0_SEASON_SPELLINGS))
    manifest = build.build(("2425",))

    assert all(_e0_artifacts_present().values()), _e0_artifacts_present()
    assert not any(_e1_artifacts_present().values()), _e1_artifacts_present()
    assert manifest["totals"]["matches"] == 380
    assert manifest["source"]["division"] == "E0 (Premier League)"
    assert manifest["source"]["url_pattern"] == fetch.BASE_URL


def test_the_e0_build_reports_an_unregistered_club_and_does_NOT_refuse(cache_dir):
    """The behaviour the daily live cycle depends on. B5 did not change it.

    An unmapped E0 name is a reported issue and a retained row — never an
    exception — because the live cycle meets a new promoted club's spelling
    before anybody has registered it, and must still produce a table.
    """
    _place_cached_csv(cache_dir, "E0", "2425",
                      list(E0_SEASON_SPELLINGS[:19]) + ["Not A Real Club"])
    manifest = build.build(("2425",))          # no raise

    assert paths.matches_parquet("E0").exists()
    assert any("unregistered club spelling" in i for i in manifest["issues"])
    assert manifest["seasons"][0]["validation"]["passed"] is False


def test_an_e0_build_cannot_reach_the_pinned_archive(cache_dir):
    """THE HARD CONSTRAINT, as a test of the orchestrator's own plumbing.

    `paths.MATCHES_PARQUET` is bound to the real `data/epl/` at import and is
    NOT moved by the fixture's monkeypatched `DATA_DIR`. So if `build` wrote
    through that constant instead of through `paths.matches_parquet(division)`,
    this test — running with a temporary data root — would overwrite the pinned
    archive with a 380-row synthetic season. It asserts the bytes did not move.
    """
    if not paths.MATCHES_PARQUET.exists():
        pytest.skip("no E0 archive on this machine (data/ is gitignored)")
    before = hashlib.sha256(paths.MATCHES_PARQUET.read_bytes()).hexdigest()
    assert before == E0_MATCHES_SHA256, "archive already moved before this test"

    _place_cached_csv(cache_dir, "E0", "2425", list(E0_SEASON_SPELLINGS))
    build.build(("2425",))

    after = hashlib.sha256(paths.MATCHES_PARQUET.read_bytes()).hexdigest()
    assert after == E0_MATCHES_SHA256
    assert paths.matches_parquet("E0") != paths.MATCHES_PARQUET


def test_an_e1_build_leaves_the_pinned_archive_alone_too(cache_dir):
    if not paths.MATCHES_PARQUET.exists():
        pytest.skip("no E0 archive on this machine (data/ is gitignored)")
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    build.build(("2425",), division="E1")

    digest = hashlib.sha256(paths.MATCHES_PARQUET.read_bytes()).hexdigest()
    assert digest == E0_MATCHES_SHA256


def test_the_two_divisions_build_side_by_side_without_touching_each_other(cache_dir):
    """Both files for the same season code, both built, five separate artifacts."""
    _place_cached_csv(cache_dir, "E0", "2425", list(E0_SEASON_SPELLINGS))
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))

    build.build(("2425",))
    e0_bytes = paths.matches_parquet("E0").read_bytes()
    e0_manifest = paths.manifest_path("E0").read_bytes()

    build.build(("2425",), division="E1")

    assert paths.matches_parquet("E0").read_bytes() == e0_bytes
    assert paths.manifest_path("E0").read_bytes() == e0_manifest
    assert len(pd.read_parquet(paths.matches_parquet("E0"))) == 380
    assert len(pd.read_parquet(paths.matches_parquet("E1"))) == 552

    e0_ids = set(pd.read_parquet(paths.matches_parquet("E0"))["match_id"])
    e1_ids = set(pd.read_parquet(paths.matches_parquet("E1"))["match_id"])
    assert e0_ids & e1_ids == set()


# --------------------------------------------------------------------------
# The CSV mirror is per division too — `--csv` must not cross the streams
# --------------------------------------------------------------------------

def test_the_csv_mirror_is_its_own_file_per_division():
    assert paths.matches_csv("E0") == paths.MATCHES_CSV
    assert paths.matches_csv() == paths.MATCHES_CSV
    assert paths.matches_csv("E1").name == "matches_e1.csv"
    assert paths.matches_csv("E1") != paths.MATCHES_CSV


def test_an_e1_build_with_csv_does_not_write_the_e0_csv(cache_dir):
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    build.build(("2425",), division="E1", write_csv=True)

    assert paths.matches_csv("E1").exists()
    assert not paths.matches_csv("E0").exists()


# --------------------------------------------------------------------------
# The CLI
# --------------------------------------------------------------------------

def test_the_cli_refuses_a_division_with_no_registered_shape(capsys):
    with pytest.raises(SystemExit):
        build.main(["--division", "E2"])
    assert "E2" in capsys.readouterr().err


def test_the_cli_defaults_to_e0(cache_dir):
    _place_cached_csv(cache_dir, "E0", "2425", list(E0_SEASON_SPELLINGS))
    assert build.main(["--seasons", "2425"]) == 0
    assert paths.matches_parquet("E0").exists()
    assert not paths.matches_parquet("E1").exists()


def test_the_cli_builds_e1_when_asked(cache_dir):
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    assert build.main(["--division", "E1", "--seasons", "2425"]) == 0
    assert paths.matches_parquet("E1").exists()
    assert not paths.matches_parquet("E0").exists()


def test_the_summary_survives_a_season_with_no_odds_at_all(cache_dir, capsys):
    """A defect the E0 archive could not expose, because it always has prices.

    `overround_mean` is None when no row carries a usable odds triple, and
    `format(None, '>6')` raises. The crash came AFTER the parquet was written,
    so the build would have reported failure on a run that had in fact
    succeeded — the worst shape for an operator, and E1 coverage is not
    guaranteed the way E0's is.
    """
    _place_cached_csv(cache_dir, "E1", "2425", list(E1_SEASON_SPELLINGS))
    manifest = build.build(("2425",), division="E1")
    assert manifest["seasons"][0]["odds"]["overround_mean"] is None
    assert manifest["seasons"][0]["odds"]["usable_rows"] == 0

    build._print_summary(manifest)              # must not raise
    assert "2024/25" in capsys.readouterr().out


def test_the_cli_reports_a_refusal_rather_than_raising_a_traceback(cache_dir, capsys):
    """A refusal is an operator-facing message and a non-zero exit, not a crash."""
    _place_cached_csv(cache_dir, "E1", "2425", ["Derby", "Preston", "Millwall",
                                                "Sheffield Weds"])
    assert build.main(["--division", "E1", "--seasons", "2425"]) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert not paths.matches_parquet("E1").exists()
