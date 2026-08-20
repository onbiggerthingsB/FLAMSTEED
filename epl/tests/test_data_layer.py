"""Unit tests for the two places a silent bug would be most expensive.

Date parsing and team resolution both fail quietly by nature: a month/day swap
still produces valid dates, and a permissive slugger still produces a valid key.
Neither would raise; both would corrupt every downstream fit. Run with:

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests -q
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl import parse, schema, teams


# --- dates ---------------------------------------------------------------

def test_parses_both_source_date_formats():
    got = parse.parse_dates(pd.Series(["16/08/14", "16/08/2014"]))
    assert list(got) == [pd.Timestamp("2014-08-16")] * 2


def test_day_month_order_not_month_day():
    """01/02/2015 is 1 February, not 2 January."""
    got = parse.parse_dates(pd.Series(["01/02/2015"]))
    assert got.iloc[0] == pd.Timestamp("2015-02-01")


def test_unparseable_date_becomes_nat_rather_than_a_guess():
    got = parse.parse_dates(pd.Series(["2015-02-01", "not a date", ""]))
    assert got.isna().all()


def test_two_digit_years_land_in_the_ingest_window():
    got = parse.parse_dates(pd.Series(["01/08/14", "31/05/26"]))
    assert [t.year for t in got] == [2014, 2026]


# --- teams ---------------------------------------------------------------

def test_aliases_collapse_to_one_key():
    """The failure this guards: two spellings becoming two clubs."""
    for spelling in ("Man United", "Man Utd", "Manchester United"):
        assert teams.team_key(spelling) == "man_united"


def test_apostrophe_variants_resolve_to_the_same_club():
    for spelling in ("Nott'm Forest", "Nott’m Forest", "Nottingham Forest"):
        assert teams.resolve(spelling) == ("Nottingham Forest", "nottm_forest")


def test_unknown_spelling_raises_rather_than_inventing_a_club():
    with pytest.raises(teams.UnknownTeamError):
        teams.resolve("Barcelona")


def test_resolution_is_case_and_whitespace_insensitive():
    assert teams.team_key("  man   city  ") == "man_city"


def test_every_registry_key_is_unique():
    keys = [teams.team_key(s) for s in teams.known_spellings()]
    canonicals = {teams.canonical_name(s) for s in teams.known_spellings()}
    assert len(set(keys)) == len(canonicals) == teams.registry_size()


# --- ordering ------------------------------------------------------------

def test_sort_is_chronological_and_deterministic():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-02", "2020-01-01", "2020-01-02"]),
            "kickoff": pd.to_datetime(
                ["2020-01-02 15:00", None, "2020-01-02 12:30"]
            ),
            "home_key": ["b", "a", "c"],
            "away_key": ["x", "y", "z"],
        }
    )
    got = schema.sort_for_walk_forward(df)
    assert list(got["home_key"]) == ["a", "c", "b"]
    assert got.equals(schema.sort_for_walk_forward(got))
