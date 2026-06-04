"""End-to-end leakage sweep — the Phase-1 capstone (north-star §2: "treat
too-good as a bug").

These four tests are the operational form of the leakage-safety invariant that
the whole data layer is built around. The headline is the **future-result
canary** (:func:`test_future_result_change_does_not_leak_into_earlier_cutoff`):
mutating a match that sits AFTER a cutoff must NOT change a single feature value
built at that earlier cutoff. If it does, ``build`` is peeking at the future and
that is a genuine leak — the test must NOT be weakened.

The other three assert the supporting guarantees: more history can only ADD
matches (monotonicity), no built row is dated on/after its cutoff (the strict
``date < cutoff`` filter), and the Elo feature is the PRE-match rating only
(``rating_post`` must never reach the panel).
"""
import json

import pandas as pd
import pytest

from wcmodel.data.features import build
from wcmodel.data.sources.odds import extract_closing_prices
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy


def test_match_count_monotonic_in_cutoff(small_store):
    early = build(cutoff="2023-01-01", store=small_store)
    late = build(cutoff="2025-06-01", store=small_store)
    assert len(late) >= len(early)


def test_no_row_dated_on_or_after_cutoff(small_store):
    for c in ["2022-01-01", "2024-01-01", "2025-06-01"]:
        df = build(cutoff=c, store=small_store)
        assert (pd.to_datetime(df["date"]) < pd.Timestamp(c)).all()


def test_elo_feature_is_pre_match_never_post(small_store):
    df = build(cutoff="2025-06-01", store=small_store)
    # elo_pre must be the pre-match rating; assert it is present and finite.
    assert "elo_pre" in df.columns and df["elo_pre"].notna().all()
    assert "rating_post" not in df.columns  # post-match rating must NOT be a feature


def test_future_result_change_does_not_leak_into_earlier_cutoff(mutable_store):
    f_before = build(cutoff="2024-06-01", store=mutable_store)
    mutable_store.mutate_future_result(after="2024-06-01")  # change a match AFTER the cutoff
    f_after = build(cutoff="2024-06-01", store=mutable_store)
    pd.testing.assert_frame_equal(
        f_before.reset_index(drop=True), f_after.reset_index(drop=True))


# --- Fix 1: sub-day cutoff is day-floored for date-only match knowability -----

@pytest.fixture
def store_with_prior_and_same_day(tmp_path) -> BitemporalStore:
    """A two-match store: a prior-day (2024-06-19) match and a same-day
    (2024-06-20, vs the noon cutoff) match, both date-resolution (stored
    midnight). Shared by the tz-naive sub-day boundary test and the tz-aware
    boundary test below."""
    raw = pd.DataFrame([
        # date, home, away, hs, as, tournament, city, country, neutral
        ("2024-06-19", "Brazil", "Argentina", 1, 0, "Friendly", "London", "England", False),
        ("2024-06-20", "Croatia", "Brazil", 2, 1, "Friendly", "Paris", "France", False),
    ], columns=["date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral"])
    store = BitemporalStore(root=tmp_path)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def test_sub_day_cutoff_excludes_same_day_keeps_prior_day_odds_stay_intraday(
        store_with_prior_and_same_day):
    """The three leakage-boundary guarantees, in one test:

    (a) a noon cutoff EXCLUDES a match dated that same day (date-only data: a
        match on day D is not knowable until D+1 00:00 — midnight < noon must
        NOT leak the kickoff-day result);
    (b) it STILL INCLUDES the PRIOR day's match (guard against an off-by-one
        that over-excludes the day before);
    (c) the ODDS path is NOT day-normalized: the close snapshot is returned at
        its TRUE intraday timestamp, distinct from the bet_time snapshot.
    """
    store = store_with_prior_and_same_day
    df = build(cutoff="2024-06-20 12:00", store=store)  # tz-NAIVE noon cutoff
    built_days = set(pd.to_datetime(df["date"]).dt.normalize())

    # (a) same-day match (kickoff-day result) is NOT knowable at a noon cutoff.
    assert pd.Timestamp("2024-06-20") not in built_days
    # (b) prior-day match IS included (no over-exclusion of D-1).
    assert pd.Timestamp("2024-06-19") in built_days

    # (c) odds timestamps are read at TRUE intraday resolution (NOT floored):
    #     the close is the 18:55Z snapshot, distinct from the 12:00Z bet_time.
    sample = json.load(open("fixtures/oddsapi_historical_sample.json"))
    close = extract_closing_prices(sample, bookmaker="pinnacle")
    assert close["snapshot_ts"] == "2026-06-11T18:55:00Z"
    assert close["snapshot_ts"] != sample["bet_time"]["timestamp"]
    # Intraday (not midnight) — proves no day-normalization on the odds path.
    assert pd.Timestamp(close["snapshot_ts"]).normalize() != pd.Timestamp(
        close["snapshot_ts"])


def test_tz_aware_cutoff_does_not_crash_and_keeps_boundary(
        store_with_prior_and_same_day):
    """A tz-AWARE (UTC `Z`) cutoff must build without crashing and keep the same
    day-boundary semantics as the tz-naive case.

    Odds API timestamps are `Z`/UTC, so a caller can hand `build` a tz-aware
    cutoff. The result/match dates are tz-NAIVE date-only (midnight), so before
    this fix the tz-aware `cutoff_day` raised on the tz-naive-vs-tz-aware
    comparison. `build` now coerces the cutoff to UTC-naive before day-flooring,
    so the comparison is clean and the boundary is unchanged: same UTC day
    excluded, prior day still included.
    """
    df = build(cutoff=pd.Timestamp("2024-06-20T12:00:00Z"),  # tz-aware UTC
               store=store_with_prior_and_same_day)
    days = set(pd.to_datetime(df["date"]).dt.normalize())
    assert pd.Timestamp("2024-06-20") not in days   # same UTC day excluded
    assert pd.Timestamp("2024-06-19") in days        # prior day still included


# --- Fix 2: a post-cutoff result must not change an earlier-cutoff band -------

def test_post_cutoff_result_does_not_change_earlier_cutoff_strength_band(
        mutable_store):
    """Per-cutoff strength-band regression (Fix 2).

    The strength band is ranked over the ``< cutoff`` Elo slice. A result dated
    AFTER the cutoff must therefore leave every earlier-cutoff emitted
    ``strength_band`` untouched. The mutable_store fixture sits a pivot team at
    the Elite/Strong (10/11) boundary so a future-informed (leaked) ranking
    WOULD flip its band — making this a non-vacuous guard, not a tautology.
    """
    def band_by_team(store):
        df = build(cutoff="2024-06-01", store=store)
        return (df[["team", "strength_band"]]
                .drop_duplicates().set_index("team")["strength_band"].to_dict())

    before = band_by_team(mutable_store)
    mutable_store.mutate_future_result(after="2024-06-01")
    after = band_by_team(mutable_store)
    assert before == after
