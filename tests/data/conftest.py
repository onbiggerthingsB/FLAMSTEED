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

# Cutoff the future-result canary (test_leakage_sweep) builds at; the mutated
# match must sit strictly AFTER it so build() excludes it. Kept here next to the
# raw panel so the dates below stay self-consistent.
_CANARY_CUTOFF = pd.Timestamp("2024-06-01")


# Raw martj42-shaped results: a handful of teams, two seasons, varied
# tournaments (friendly / WC finals / qualifier / nations league / euro), a
# 2020 COVID-window match, and cities that do / do not appear in the venues
# table below. All core matches are < the 2025-03-01 cutoff the tests use; one
# 2025-06 match sits AFTER it to prove the strict cutoff filter bites.
#
# STRENGTH-BAND EDGE (canary teeth — Fix 2). The three core teams all rank in
# the top handful (all "Elite"), so a future-informed strength-band leak could
# shift ranks WITHOUT changing any emitted band — the frame-equality canary
# would pass vacuously. To give it teeth we add a 9-team "ladder" (France .. # Poland) that beats a punching-bag ("Malta") by staggered amounts so the panel
# has a REAL Elite/Strong (rank 10/11) boundary, plus a pivot team "Mexico"
# parked right at that edge. Mexico's LATEST result before the canary cutoff is
# a near-1500 anchor (-> rank ~12, "Strong"); a high-K post-cutoff chain
# (2024-06-05 WC-final, then 2024-06-25) is what the canary mutates. Under a
# full-panel strength-band leak, mutating the 2024-06-05 result lifts Mexico's
# leaked latest rating across the 10/11 boundary -> emitted band flips
# Strong->Elite (proven RED in the Fix-2 canary-teeth check). Leakage-safe,
# both core canary AND per-cutoff band test stay GREEN.
# Every ladder match gets a UNIQUE calendar date. This is deliberate: Elo is
# path-dependent WITHIN a date, and the store's point-in-time read orders ties
# by (observed_at, valid_as_of) only — for same-date matches that order is not
# stable across re-reads (e.g. after the canary rewrites the parquet). Unique
# dates make the < cutoff Elo input fully deterministic, so the canary's
# frame-equality compares like for like and only a genuine leak can break it.
_LADDER = [
    # date, home, away, hs, as, tournament, city, country, neutral
    ("2023-01-02", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-03", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-04", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-05", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-06", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-07", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-08", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-09", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-10", "France", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-11", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-12", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-13", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-14", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-15", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-16", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-17", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-18", "Spain", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-19", "Portugal", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-20", "Portugal", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-21", "Portugal", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-22", "Portugal", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-23", "Portugal", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-24", "Portugal", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-25", "Portugal", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-26", "England", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-27", "England", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-28", "England", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-29", "England", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-30", "England", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-01-31", "England", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-01", "Germany", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-02", "Germany", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-03", "Germany", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-04", "Germany", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-05", "Germany", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-06", "Netherlands", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-07", "Netherlands", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-08", "Netherlands", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-09", "Netherlands", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-10", "Italy", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-11", "Italy", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-12", "Italy", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-13", "Belgium", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-14", "Belgium", "Malta", 4, 0, "Friendly", "London", "England", False),
    ("2023-02-15", "Poland", "Malta", 4, 0, "Friendly", "London", "England", False),
    # Pivot anchor: Mexico's last PRE-cutoff result is a ~1500 draw -> parks it
    # at the Elite/Strong (10/11) edge in the < cutoff ranking ("Strong").
    ("2023-02-16", "Mexico", "Malta", 0, 0, "Friendly", "London", "England", False),
]

_RAW_RESULTS = pd.DataFrame([
    # date, home, away, hs, as, tournament, city, country, neutral
    ("2022-09-01", "Brazil", "Argentina", 1, 1, "Friendly", "London", "England", False),
    ("2022-12-09", "Croatia", "Brazil", 1, 1, "FIFA World Cup", "Doha", "Qatar", True),
    ("2023-03-25", "Argentina", "Croatia", 2, 0, "FIFA World Cup qualification", "Paris", "France", False),
    ("2023-06-10", "Brazil", "Croatia", 3, 0, "UEFA Nations League", "Glasgow", "Scotland", False),
    ("2023-09-07", "Argentina", "Brazil", 0, 2, "Friendly", "Mexico City", "Mexico", False),
    ("2024-01-15", "Croatia", "Argentina", 1, 2, "UEFA Euro", "Rio de Janeiro", "Brazil", True),
    # EARLIEST post-canary-cutoff match — this is the one mutate_future_result()
    # rewrites. A high-K WC-final for the pivot (Mexico) so a leaked full-panel
    # ranking would feel the score change at the 10/11 band edge.
    ("2024-06-05", "Mexico", "Malta", 1, 0, "FIFA World Cup", "Doha", "Qatar", True),
    ("2024-06-20", "Brazil", "Argentina", 2, 2, "FIFA World Cup", "Doha", "Qatar", True),
    # Mexico's post-cutoff "latest" result: its rating_pre here reflects the
    # 2024-06-05 score, so a full-panel leak would read the mutated rating.
    ("2024-06-25", "Mexico", "Poland", 0, 0, "Friendly", "London", "England", False),
    # COVID-window match (2020-03-01 .. 2021-06-30) — exercises is_covid tag.
    ("2020-04-10", "Brazil", "Croatia", 0, 0, "Friendly", "London", "England", False),
    # AFTER the test cutoff — must be filtered out by build().
    ("2025-06-01", "Argentina", "Brazil", 1, 0, "Friendly", "Paris", "France", False),
    *_LADDER,
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


class MutableStore(BitemporalStore):
    """A :class:`BitemporalStore` that can rewrite a *future* result in place.

    Used only by the future-result canary. ``mutate_future_result(after)``
    rewrites the ``results`` parquet so that the score of one match with
    ``date > after`` changes. The ``match_id`` key is ``sha1(date|home|away|
    city)`` (the score is NOT part of the key), so rewriting the score keeps the
    same ``match_id`` — exactly modelling a *revised result for a future match*.

    The point of the canary: that match is dated after ``after``, so it is
    excluded from ``build(cutoff=after)`` by the strict ``date < cutoff`` filter.
    A leakage-safe ``build`` therefore produces a BYTE-IDENTICAL panel before and
    after the mutation. If it does not, ``build`` is peeking past the cutoff —
    a real leak.
    """

    def mutate_future_result(self, after: str | pd.Timestamp) -> None:
        after = pd.Timestamp(after)
        path = self._path("results")
        df = pd.read_parquet(path)

        future = df.index[pd.to_datetime(df["date"]) > after]
        assert len(future) > 0, (
            f"canary misconfigured: no result dated after {after.date()} to "
            "mutate — the mutable_store panel must span before AND after the "
            "canary cutoff"
        )

        # Pick the earliest post-cutoff match (deterministic) and flip its score
        # to something provably different, so the mutation can never be a no-op.
        target = future[0]
        old_h = int(df.at[target, "home_score"])
        old_a = int(df.at[target, "away_score"])
        df.at[target, "home_score"] = old_h + 7
        df.at[target, "away_score"] = old_a + 3
        assert (df.at[target, "home_score"], df.at[target, "away_score"]) != (
            old_h, old_a), "mutation did not change the score"

        df.to_parquet(path, index=False)


@pytest.fixture
def mutable_store(tmp_path) -> MutableStore:
    """Future-result canary store: the same compact panel as ``small_store`` but
    backed by :class:`MutableStore`, so a post-cutoff match can be rewritten.

    The shared ``_RAW_RESULTS`` panel deliberately straddles the canary cutoff
    (2024-06-01): the core + ladder matches up to 2024-01-15 fall BEFORE it (and
    feed the cutoff-2024-06-01 panel), while the pivot's 2024-06-05 / 2024-06-25
    chain, 2024-06-20, and 2025-06-01 fall AFTER it. ``mutate_future_result``
    rewrites the EARLIEST post-cutoff match — the 2024-06-05 pivot (Mexico)
    WC-final — which sits at the strength-band edge so the canary has real teeth
    (a full-panel band leak would flip Mexico Strong->Elite). xG + venues are
    loaded too, so the canary exercises the full join path, not just the Elo
    core.
    """
    store = MutableStore(root=tmp_path)

    results = normalize_results(_RAW_RESULTS)
    store.write("results", results, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")

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
