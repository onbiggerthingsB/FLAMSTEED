"""Shared fixtures for the Phase-1 data-layer tests.

``small_store`` is a tmp :class:`BitemporalStore` seeded with a compact but
representative panel: several teams, matches spanning a couple of years
(2022-2024), an explicit 2020 COVID-window match, a couple of StatsBomb xG rows
(so the xG left-join exercises BOTH covered and uncovered match-teams), and a
small ``venues`` table whose key is the results ``city`` (some match cities are
present -> coords join; others are absent -> NaN, the documented historical
city->coord sparsity). Everything is written through the real store with the
real source policies so ``features.build`` is integration-tested end to end.
"""
from __future__ import annotations

import pandas as pd
import pytest

from wcmodel.data.sources.results import normalize_results
from wcmodel.data.sources.statsbomb import normalize_match_xg
from wcmodel.data.store import BitemporalStore, Policy


# Raw martj42-shaped results: a handful of teams, two seasons, varied
# tournaments (friendly / WC finals / qualifier / nations league / euro), a
# 2020 COVID-window match, and cities that do / do not appear in the venues
# table below. All matches are < the 2025-03-01 cutoff the tests use; one
# 2025-06 match sits AFTER it to prove the strict cutoff filter bites.
_RAW_RESULTS = pd.DataFrame([
    # date, home, away, hs, as, tournament, city, country, neutral
    ("2022-09-01", "Brazil", "Argentina", 1, 1, "Friendly", "London", "England", False),
    ("2022-12-09", "Croatia", "Brazil", 1, 1, "FIFA World Cup", "Doha", "Qatar", True),
    ("2023-03-25", "Argentina", "Croatia", 2, 0, "FIFA World Cup qualification", "Paris", "France", False),
    ("2023-06-10", "Brazil", "Croatia", 3, 0, "UEFA Nations League", "Glasgow", "Scotland", False),
    ("2023-09-07", "Argentina", "Brazil", 0, 2, "Friendly", "Mexico City", "Mexico", False),
    ("2024-01-15", "Croatia", "Argentina", 1, 2, "UEFA Euro", "Rio de Janeiro", "Brazil", True),
    ("2024-06-20", "Brazil", "Argentina", 2, 2, "FIFA World Cup", "Doha", "Qatar", True),
    # COVID-window match (2020-03-01 .. 2021-06-30) — exercises is_covid tag.
    ("2020-04-10", "Brazil", "Croatia", 0, 0, "Friendly", "London", "England", False),
    # AFTER the test cutoff — must be filtered out by build().
    ("2025-06-01", "Argentina", "Brazil", 1, 0, "Friendly", "Paris", "France", False),
], columns=["date", "home_team", "away_team", "home_score", "away_score",
            "tournament", "city", "country", "neutral"])


# StatsBomb xG for ONE finals match only (Croatia vs Brazil, 2022-12-09).
# StatsBomb covers finals/continental matches and is sparse elsewhere, so the
# overwhelming majority of build() rows will have xg_covered == False / NaN xG
# — that is the correct, NULL-safe behaviour.
_RAW_XG = [{
    "match_id": "SB_DUMMY",          # overwritten below to the real match_id
    "match_date": "2022-12-09",
    "home_team": {"home_team_name": "Croatia"},
    "away_team": {"away_team_name": "Brazil"},
    "shots": [
        {"team": "Croatia", "shot_statsbomb_xg": 0.40},
        {"team": "Croatia", "shot_statsbomb_xg": 0.15},
        {"team": "Brazil", "shot_statsbomb_xg": 0.55},
        {"team": "Brazil", "shot_statsbomb_xg": 0.30},
    ],
}]


# Venue coords keyed by results `city`. Deliberately covers only SOME of the
# match cities (London/Paris/Doha/Mexico City/Rio present; Glasgow absent) so
# the travel/altitude join yields a mix of real values and NaN.
_VENUES = pd.DataFrame([
    ("London", 51.5074, -0.1278, 11.0),
    ("Paris", 48.8566, 2.3522, 35.0),
    ("Doha", 25.2854, 51.5310, 10.0),
    ("Mexico City", 19.4326, -99.1332, 2240.0),
    ("Rio de Janeiro", -22.9068, -43.1729, 2.0),
], columns=["city", "lat", "lon", "altitude_m"])


@pytest.fixture
def matches_df() -> pd.DataFrame:
    """Tiny match panel with a ``date`` column spanning ~2019->2025.

    Deliberately includes **pre-2021** rows so the backtest-window test is
    meaningful: a backtest from ``odds_start`` must KEEP this pre-feature-window
    history (it is NOT cropped to ``feature_years``), whereas a 4-year feature
    window cut at 2025-01-01 would drop everything before 2021-01-01.
    """
    return pd.DataFrame({
        "date": pd.to_datetime([
            "2019-09-01",   # pre-odds_start AND pre-feature-window -> in NEITHER window
            "2020-03-15",   # before the 2020-06-06 odds_start -> excluded from backtest too
            "2020-06-06",   # exactly odds_start (lower-bound boundary, included)
            "2020-11-20",   # pre-feature-window but >= odds_start -> the "not cropped" row
            "2021-06-10",   # inside feature window
            "2022-12-18",   # inside feature window
            "2024-07-14",   # inside feature window
            "2025-03-01",   # AFTER the 2025-01-01 feature cutoff
        ]),
        "home_team": ["A", "B", "C", "A", "B", "C", "A", "B"],
        "away_team": ["B", "C", "A", "C", "A", "B", "C", "A"],
    })


@pytest.fixture
def small_store(tmp_path) -> BitemporalStore:
    store = BitemporalStore(root=tmp_path)

    results = normalize_results(_RAW_RESULTS)
    store.write("results", results, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")

    # Point the xG fixture at the real, hashed match_id for the finals match.
    finals = results[(results["home_team"] == "Croatia")
                     & (results["away_team"] == "Brazil")
                     & (results["date"] == pd.Timestamp("2022-12-09"))].iloc[0]
    raw_xg = [dict(_RAW_XG[0], match_id=finals["match_id"])]
    xg = normalize_match_xg(raw_xg, source_version="test")
    store.write("xg", xg, policy=Policy.POINT_IN_TIME,
                keys=["match_id", "team"], source="statsbomb",
                source_version="test")

    venues = _VENUES.copy()
    venues["valid_as_of"] = pd.Timestamp("1900-01-01")
    venues["observed_at"] = pd.Timestamp("1900-01-01")
    store.write("venues", venues, policy=Policy.POINT_IN_TIME,
                keys=["city"], source="venues_ref", source_version="test")

    return store
