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
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wcmodel.data.features import build
from wcmodel.data.sources.odds import extract_closing_prices
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.data.tournament import ingest_wc_group_fixtures, load_tournament


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


# --- #4 GATE: WC-2026 in-progress / TBD-knockout rows must not leak ------------
#
# The played filter + the structure-placeholder knockout exclusion, proven end
# to end. With the 72 future-dated, UNPLAYED WC-2026 group rows ingested into the
# SAME results store as real history, NO unplayed/future/placeholder row may
# enter a feature panel — at a mid-tournament cutoff (where June-11..19 fixtures
# are `date < cutoff` but scoreless → played-filter-excluded; June-20+ →
# date-excluded), at a pre-WC cutoff (all future → date-excluded), and the
# knockout placeholders never reach the store at all. The complementary
# played-INCLUSION check proves the filter excludes UNPLAYED, not all WC rows.

_REAL_DRAW = Path("config/tournament_2026.yaml")
_needs_draw = pytest.mark.skipif(
    not _REAL_DRAW.exists(),
    reason="awaiting user-provided verified draw file (decision 2)")

# Structure-placeholder shapes that must NEVER appear in any team column of the
# panel: group-position slots (`^[0-9][A-L]$`, e.g. 2A), winner/loser refs
# (`^W\d+$`/`^L\d+$`, e.g. W74/L101), and best-third slots (`^3rd-`, e.g.
# 3rd-ABCDF). Anchored, per the gate spec.
_PLACEHOLDER_PATTERNS = (r"^[0-9][A-L]$", r"^W\d+$", r"^L\d+$", r"^3rd-")
_PLACEHOLDER_RE = re.compile("|".join(_PLACEHOLDER_PATTERNS))
_PLACEHOLDER_TOKENS = ("2A", "W74", "3rd-ABCDF")  # explicit spot-checks

# A few historical PLAYED results (real martj42 keys, all scored), spanning
# 2022..2024 — the clean core the WC rows are layered on top of.
_HISTORY = pd.DataFrame([
    # date, home, away, hs, as, tournament, city, country, neutral
    ("2022-09-01", "Brazil", "Argentina", 1, 1, "Friendly", "London", "England", False),
    ("2022-12-09", "Mexico", "Brazil", 0, 2, "FIFA World Cup", "Doha", "Qatar", True),
    ("2023-06-10", "Germany", "Spain", 2, 0, "UEFA Nations League", "Glasgow", "Scotland", False),
    ("2023-09-07", "Argentina", "Mexico", 3, 0, "Friendly", "Mexico City", "Mexico", False),
    ("2024-01-15", "England", "Croatia", 1, 2, "UEFA Euro", "Berlin", "Germany", True),
], columns=["date", "home_team", "away_team", "home_score", "away_score",
            "tournament", "city", "country", "neutral"])


def _team_columns(df: pd.DataFrame) -> pd.Series:
    """Every value across all team-bearing columns of the panel, as one Series."""
    cols = [c for c in ("home_team", "away_team", "team", "opponent")
            if c in df.columns]
    return pd.concat([df[c].astype(str) for c in cols], ignore_index=True)


def _seed_history(store: BitemporalStore, history: pd.DataFrame = _HISTORY) -> None:
    store.write("results", normalize_results(history), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")


@_needs_draw
def test_wc2026_in_progress_rows_do_not_leak(tmp_path):
    """The #4 gate. A store of historical PLAYED results + the 72 ingested
    WC-2026 group fixtures (UNPLAYED, June-2026 dates).

    (1) MID-TOURNAMENT cutoff 2026-06-20 — NO unplayed WC fixture in the panel,
        NO NaN-score row anywhere, NO placeholder token in any team column.
    (2) PRE-WC cutoff 2025-06-01 — NO WC fixture at all (all future).
    (3) PLAYED-INCLUSION — give ONE WC group fixture a real score and a cutoff
        after its date; it DOES now appear (filter excludes UNPLAYED, not all WC).
    """
    store = BitemporalStore(root=tmp_path / "store")
    _seed_history(store)
    t = load_tournament(_REAL_DRAW)
    n = ingest_wc_group_fixtures(t, store, observed_at="2026-01-01")
    assert n == 72, "expected exactly the 72 group fixtures ingested"

    drawn = set(t["teams"])

    # --- (1) MID-TOURNAMENT cutoff: 2026-06-20 --------------------------------
    mid = build(cutoff="2026-06-20", store=store)

    # (a) NO unplayed WC fixture in the panel. The WC group rows span 2026-06-11
    #     .. 2026-06-27; at this cutoff the 2026-06-11..19 matches are
    #     `date < cutoff` (so the date filter ALONE would admit them) yet
    #     scoreless → the PLAYED filter drops them; 2026-06-20+ are date-excluded.
    #     Net: not a single 2026 WC date survives.
    assert (pd.to_datetime(mid["date"]) < pd.Timestamp("2026-06-11")).all(), (
        "a WC-2026 fixture leaked into the mid-tournament panel"
    )
    # (b) No NaN-score row anywhere in the panel (the unplayed rows are gone).
    assert mid["home_score"].notna().all() and mid["away_score"].notna().all()
    # (c) No placeholder token in ANY team column — the knockout structure
    #     placeholders were never ingested, so they cannot appear.
    vals_mid = _team_columns(mid)
    assert not vals_mid.str.match(_PLACEHOLDER_RE).any(), (
        "a structure-placeholder token leaked into a team column of the panel"
    )
    assert not vals_mid.isin(_PLACEHOLDER_TOKENS).any()
    # Every team in the panel is a real nation (no slot/ref tokens).
    assert set(vals_mid) <= drawn

    # --- (2) PRE-WC cutoff: 2025-06-01 — every WC fixture is in the future ----
    pre = build(cutoff="2025-06-01", store=store)
    assert (pd.to_datetime(pre["date"]) < pd.Timestamp("2026-01-01")).all(), (
        "a WC-2026 fixture appeared at a PRE-WC cutoff (all should be future)"
    )
    # And still no placeholder / NaN-score contamination at this cutoff.
    assert pre["home_score"].notna().all() and pre["away_score"].notna().all()
    assert not _team_columns(pre).str.match(_PLACEHOLDER_RE).any()

    # --- (3) PLAYED-INCLUSION: a SCORED WC fixture DOES appear ----------------
    # Take the earliest WC group fixture, give it a real score (revision keeps
    # the same match_id — score is not part of the key), re-stamp it as observed
    # on/after kickoff, and write it back. A cutoff after its date must now
    # surface it: this proves the played filter excludes UNPLAYED rows, not WC
    # rows wholesale.
    first = next(fx for fx in t["fixtures"]
                 if fx.get("home") in drawn and fx.get("away") in drawn)
    played = pd.DataFrame([(
        first["date"], first["home"], first["away"], 3, 1, "FIFA World Cup",
        first["venue"], None, True,
    )], columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "city", "country", "neutral"])
    played = normalize_results(played)
    # The result is observed AFTER the schedule row (which was stamped at the
    # fixture's midnight). Stamp this revision one day later so the store's
    # point-in-time read (latest observed_at wins) returns the SCORED row, not
    # the original NaN schedule row — exactly modelling "the result is confirmed
    # after kickoff". Still < the 2026-06-13 cutoff, so the read includes it.
    revised_at = pd.to_datetime(first["date"]) + pd.Timedelta(days=1)
    played["valid_as_of"] = revised_at
    played["observed_at"] = revised_at
    store.write("results", played, policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="wc2026_result", source_version="test")

    after_score = build(cutoff="2026-06-13", store=store)  # after the 06-11 date
    hit = after_score[
        (pd.to_datetime(after_score["date"]) == pd.to_datetime(first["date"]))
        & (after_score["team"] == first["home"])]
    assert len(hit) == 1, (
        "a NOW-PLAYED WC group fixture failed to enter the panel — the played "
        "filter must exclude only UNPLAYED rows, not all WC rows"
    )
    assert hit["home_score"].iloc[0] == 3 and hit["away_score"].iloc[0] == 1
    # The scored row is the ONLY surviving WC date; still no NaN/placeholder.
    assert after_score["home_score"].notna().all()
    assert not _team_columns(after_score).str.match(_PLACEHOLDER_RE).any()


@_needs_draw
def test_future_result_canary_and_elo_invariance_hold_with_wc_rows(tmp_path):
    """The existing leakage guarantees still hold with the WC group rows present.

    Future-result canary: mutating a result dated AFTER a cutoff must not change
    a single feature built at that earlier cutoff — re-proven here with the 72
    unplayed WC rows sitting in the store. Per-cutoff Elo invariance: a played
    match's pre-WC `elo_pre` is byte-identical whether or not the (future,
    unplayed) WC rows are present, since the played filter + `date < cutoff`
    strip them before the Elo recompute.
    """
    # Store A: history only. Store B: history + the 72 unplayed WC rows.
    store_a = BitemporalStore(root=tmp_path / "a")
    _seed_history(store_a)
    store_b = BitemporalStore(root=tmp_path / "b")
    _seed_history(store_b)
    t = load_tournament(_REAL_DRAW)
    ingest_wc_group_fixtures(t, store_b, observed_at="2026-01-01")

    # Per-cutoff Elo invariance: the unplayed/future WC rows must not perturb a
    # pre-WC panel at all — building at 2025-01-01 is BYTE-IDENTICAL with vs
    # without them in the store.
    cutoff = "2025-01-01"
    panel_a = build(cutoff=cutoff, store=store_a).reset_index(drop=True)
    panel_b = build(cutoff=cutoff, store=store_b).reset_index(drop=True)
    # check_dtype=False is the ONLY relaxation, and it is principled: store_a's
    # results have no NaN-score rows so its score columns are int64, while
    # store_b carries the (later-filtered) NaN WC rows so its score columns are
    # float64. The VALUES are identical — the WC rows change nothing in the
    # pre-WC panel — only the column dtype differs, an artifact of the source mix
    # (the real martj42 store always has float64 scores, like store_b).
    pd.testing.assert_frame_equal(panel_a, panel_b, check_dtype=False)

    # Future-result canary WITH the WC rows present: append a NEW played match
    # dated AFTER the cutoff to store_b, rebuild at the cutoff, and assert the
    # pre-cutoff panel is unchanged (a leak would let the post-cutoff result
    # bleed back).
    before = build(cutoff=cutoff, store=store_b).reset_index(drop=True)
    future = normalize_results(pd.DataFrame([
        ("2025-09-01", "Brazil", "Germany", 5, 0, "Friendly", "London",
         "England", False),
    ], columns=["date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral"]))
    store_b.write("results", future, policy=Policy.POINT_IN_TIME,
                  keys=["match_id"], source="martj42", source_version="test")
    after = build(cutoff=cutoff, store=store_b).reset_index(drop=True)
    pd.testing.assert_frame_equal(before, after)
