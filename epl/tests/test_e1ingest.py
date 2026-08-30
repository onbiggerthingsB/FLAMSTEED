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

import pandas as pd
import pytest

from epl import fetch, paths, schema, teams, validate


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


def _place_cached_csv(raw_dir, division: str, code: str, clubs: list[str]) -> None:
    """A cached football-data CSV for one season, written straight to the cache.

    Hand-placed rather than downloaded: there is no network in this phase, and
    `fetch_season` treats an unrecorded cached file as an observation to record,
    which is the exact path being tested.
    """
    pairs = [(h, a) for h in clubs for a in clubs if h != a]
    lines = ["Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR"]
    per_day = max(1, len(clubs) // 2)
    base = pd.Timestamp("20%s-08-10" % code[:2])
    for i, (h, a) in enumerate(pairs):
        day = base + pd.Timedelta(days=7 * (i // per_day))
        hg, ag = i % 4, i % 3
        res = "H" if hg > ag else ("A" if hg < ag else "D")
        lines.append(f"{division},{day:%d/%m/%Y},{h},{a},{hg},{ag},{res}")
    (raw_dir / f"{division}_{code}.csv").write_text("\n".join(lines) + "\n")


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    """A throwaway data root, so no test can touch the real archive."""
    data = tmp_path / "epl"
    raw = data / "raw"
    raw.mkdir(parents=True)
    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setattr(paths, "RAW_DIR", raw)
    return raw


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
