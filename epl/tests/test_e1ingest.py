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

import pandas as pd
import pytest

from epl import paths, teams


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
