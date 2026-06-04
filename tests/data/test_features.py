import re

import numpy as np
import pandas as pd

import wcmodel.data.features as features_mod
from wcmodel.data.features import build
from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy


class _TzResultsStore:
    """Minimal store stub whose ``results`` table carries TZ-AWARE dates.

    A real parquet/DuckDB round-trip hands ``build`` tz-naive timestamps, so it
    cannot exercise the tz-aware RESULT-date path. This stub emits result dates
    as ``...T00:00:00Z`` (UTC, tz-aware) — exactly the "a source emits a `Z`
    timestamp" case — so the comparison ``results["date"] < cutoff_day`` and the
    later age-days calc would raise a tz-aware-vs-tz-naive TypeError unless
    ``build`` coerces the date side to tz-naive UTC too. ``xg`` / ``venues`` are
    absent (FileNotFoundError) so the NULL-safe no-op path is taken.
    """

    def __init__(self, results: pd.DataFrame):
        self._results = results

    def read(self, name: str, *, cutoff):  # noqa: D401 - store-shaped read
        if name == "results":
            return self._results.copy()
        raise FileNotFoundError(name)


def _tz_aware_results() -> pd.DataFrame:
    """Two matches with tz-aware (UTC) midnight dates: one same-day as the
    cutoff (must be EXCLUDED), one the prior day (must be INCLUDED)."""
    return pd.DataFrame({
        "match_id": ["m_prior", "m_same"],
        # TZ-AWARE midnights — the `...T00:00:00Z` source case.
        "date": pd.to_datetime(["2024-06-19T00:00:00Z", "2024-06-20T00:00:00Z"]),
        "home_team": ["Brazil", "Argentina"],
        "away_team": ["Argentina", "Brazil"],
        "home_score": [1, 2],
        "away_score": [0, 2],
        "tournament": ["Friendly", "Friendly"],
        "neutral": [False, False],
        "city": ["London", "Paris"],
        "country": ["England", "France"],
        "revision_contaminated": [False, False],
    })


def test_build_handles_tz_aware_result_dates_against_tz_aware_cutoff():
    """FIX 1 regression: tz-aware RESULT dates + a tz-aware cutoff must NOT raise.

    Symmetric tz-coercion (date side AND cutoff side) means the day-floor filter
    and the age/decay calc both run on tz-naive UTC. Day-boundary semantics are
    preserved: a same-day match is EXCLUDED, the prior-day match is INCLUDED.
    """
    store = _TzResultsStore(_tz_aware_results())
    # TZ-AWARE cutoff (e.g. an Odds API `Z`/UTC instant) on the same calendar day
    # as the same-day match.
    cutoff = pd.Timestamp("2024-06-20T12:00:00Z")

    df = build(cutoff=cutoff, store=store)  # must not raise

    ids = set(df["match_id"])
    assert "m_prior" in ids          # prior-day match INCLUDED
    assert "m_same" not in ids       # same-day match EXCLUDED (day-floor bites)
    # The age/decay calc ran cleanly on the tz-naive date (no tz-aware path left).
    # cutoff (naive) 2024-06-20 12:00 - date (naive) 2024-06-19 00:00 = 1d12h;
    # `.dt.days` truncates the timedelta to whole days -> 1.0 (a finite float,
    # which only happens if the date side is tz-naive like the cutoff).
    assert df["age_days"].notna().all()
    assert np.isclose(df.loc[df["match_id"] == "m_prior", "age_days"].iloc[0], 1.0)


def test_build_returns_only_matches_strictly_before_cutoff(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    assert (pd.to_datetime(df["date"]) < pd.Timestamp("2025-03-01")).all()


# --- PLAYED FILTER: an UNPLAYED (NaN-score) fixture is NOT a result -----------
#
# A fixture with a null home_score/away_score has no outcome, so it must NOT
# enter the feature panel OR the Elo input — EVEN when its date is before the
# cutoff (an in-progress group match on day D-2 with no score yet). The played
# filter sits AFTER the date<cutoff_day filter and BEFORE compute_elo_history.

def _played_unplayed_store(tmp_path) -> BitemporalStore:
    """A store with one PLAYED and one UNPLAYED fixture, BOTH dated before the
    test cutoff. The unplayed row models an in-progress / scheduled fixture
    whose score is still NaN at cutoff time."""
    raw = pd.DataFrame([
        # date, home, away, hs, as, tournament, city, country, neutral
        ("2024-06-10", "Brazil", "Argentina", 2, 1, "Friendly", "London",
         "England", False),
        # UNPLAYED: NaN scores, but dated BEFORE the cutoff below.
        ("2024-06-12", "Croatia", "Brazil", np.nan, np.nan, "FIFA World Cup",
         "Paris", "France", True),
    ], columns=["date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral"])
    store = BitemporalStore(root=tmp_path)
    store.write("results", normalize_results(raw), policy=Policy.POINT_IN_TIME,
                keys=["match_id"], source="martj42", source_version="test")
    return store


def test_unplayed_fixture_excluded_from_panel_even_before_cutoff(tmp_path):
    """The NaN-score fixture (dated < cutoff) must NOT appear in the panel, and
    NO NaN-score row may survive anywhere — yet the PLAYED fixture stays."""
    store = _played_unplayed_store(tmp_path)
    df = build(cutoff="2024-06-20", store=store)  # cutoff AFTER both dates

    # The unplayed Croatia-vs-Brazil match (2024-06-12) is gone from the panel.
    unplayed = df[pd.to_datetime(df["date"]) == pd.Timestamp("2024-06-12")]
    assert unplayed.empty, "an UNPLAYED (NaN-score) fixture leaked into the panel"
    # No surviving row carries a NaN label score.
    assert df["home_score"].notna().all() and df["away_score"].notna().all()
    # The genuinely PLAYED fixture is still present (filter excludes UNPLAYED,
    # not all rows).
    played = df[pd.to_datetime(df["date"]) == pd.Timestamp("2024-06-10")]
    assert not played.empty


def test_unplayed_fixture_excluded_from_elo_input(tmp_path):
    """The unplayed fixture must not enter the Elo recompute either: with only
    one PLAYED match (Brazil beat Argentina) in scope, Brazil's emitted row must
    carry the debutant initial rating (1500) PRE-match — proving the later
    NaN-score Croatia match never produced a (poisoned) rating update that
    reached the panel."""
    store = _played_unplayed_store(tmp_path)
    df = build(cutoff="2024-06-20", store=store)
    # Exactly the two teams of the single played match appear.
    assert set(df["team"]) == {"Brazil", "Argentina"}
    # elo_pre is finite everywhere (no NaN rating injected by the unplayed row).
    assert df["elo_pre"].notna().all()
    # Both teams are at the initial 1500 PRE their (first, only) played match.
    assert np.allclose(df["elo_pre"], 1500.0)


def test_elo_feature_is_pre_match_rating(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    assert "elo_pre" in df.columns and df["elo_pre"].notna().all()


def test_missing_xg_is_null_not_imputed(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    uncov = df[df["xg_covered"] == False]
    assert uncov["xg_for"].isna().all()          # NULL, never filled


def test_contamination_exposure_zero_for_clean_core(small_store):
    df = build(cutoff="2025-03-01", store=small_store)
    assert (df["revision_contaminated_exposure"] == 0.0).all()


def test_time_decay_weight_decreases_with_age(small_store):
    df = build(cutoff="2025-03-01", store=small_store).sort_values("date")
    assert df["decay_weight"].iloc[0] <= df["decay_weight"].iloc[-1]   # older -> smaller weight


def test_build_emits_provisional_column(small_store):
    """RIDER 1 propagation: the data-driven `provisional` flag must carry from
    `compute_elo_history` through `build` to the panel — otherwise the flag is
    decorative and Phase 2 cannot widen its prior for low-information teams."""
    df = build(cutoff="2025-03-01", store=small_store)
    assert "provisional" in df.columns
    assert df["provisional"].dtype == bool          # a real per-row boolean flag
    # Non-vacuous: the panel's early-history teams trip the count branch, so at
    # least one row is flagged provisional (not all-False / not all-True).
    assert df["provisional"].any()


# --- DELIVERABLE #1: the closing line is WALLED OFF from FEATURES --------------
#
# The catastrophic leak is post-cutoff MARKET information (the closing line)
# entering the model's FEATURE set — independent of timestamp fidelity. Even a
# perfectly point-in-time-resolved close is a leak if it becomes a feature. Two
# guards: (1) no emitted feature COLUMN is market-named; (2) build() structurally
# reads ONLY the clean-core tables and never the odds table. Together they make a
# future edit that joins odds into features fail loudly.

# Any feature column matching one of these (case-insensitive) substrings would
# signal market info bleeding into the panel.
_MARKET_SUBSTRINGS = ("close", "closing", "odds", "bet_time", "snapshot",
                      "price", "h2h")
_MARKET_RE = re.compile("|".join(_MARKET_SUBSTRINGS), re.IGNORECASE)


def test_close_absent_from_feature_columns(small_store):
    """No emitted FEATURE column may carry market/closing-line provenance.

    The closing line entering the feature set is the catastrophic leak (the model
    would peek at post-cutoff market consensus). Assert no column name contains
    any of close/closing/odds/bet_time/snapshot/price/h2h, case-insensitive.
    """
    df = build(cutoff="2025-03-01", store=small_store)
    offenders = [c for c in df.columns if _MARKET_RE.search(c)]
    # Failing-if-violated assertion (quoted in the report):
    assert offenders == [], (
        f"market/closing-line columns leaked into the FEATURE panel: {offenders} "
        f"(matched one of {_MARKET_SUBSTRINGS})"
    )


def test_build_reads_only_clean_core_store_tables(small_store):
    """Structural guard: build() requests ONLY the clean-core store tables.

    We wrap ``BitemporalStore.read`` to RECORD every ``name`` it is asked for
    during a build, then assert the recorded set is a subset of
    ``{"results","xg","venues"}`` and that ``"odds"`` is NOT among them. This is
    a STRUCTURAL guard independent of column naming: a future edit that joins the
    odds table into features (even under an innocuous column name) would surface
    here as a new requested table and fail loudly.
    """
    requested: list[str] = []
    orig_read = BitemporalStore.read

    def _recording_read(self, name, *, cutoff):
        requested.append(name)
        return orig_read(self, name, cutoff=cutoff)

    original = BitemporalStore.read
    BitemporalStore.read = _recording_read
    try:
        build(cutoff="2025-03-01", store=small_store)
    finally:
        BitemporalStore.read = original

    requested_set = set(requested)
    clean_core = {"results", "xg", "venues"}
    # Failing-if-violated assertions (quoted in the report):
    assert requested_set <= clean_core, (
        f"build() read store tables outside the clean core: "
        f"{requested_set - clean_core} (allowed: {clean_core})"
    )
    assert "odds" not in requested_set, (
        "build() read the 'odds' table — the closing line must NEVER enter "
        "features"
    )
    # Non-vacuous: build() must actually have read the core results table (else
    # the subset check passes trivially on an empty set).
    assert "results" in requested_set


# --- DELIVERABLE #2: explicit per-cutoff Elo invariance to FUTURE matches ------


def test_elo_pre_invariant_to_future_matches(small_store):
    """A match's ``elo_pre`` at cutoff C1 must not change when a LATER match is
    appended to the store (future matches must not bleed into the as-of rating).

    Build at an early cutoff C1 and record a shared team's ``elo_pre`` for a
    specific match M dated < C1. Append a NEW match dated AFTER C1 (same teams),
    rebuild at C1, and assert M's ``elo_pre`` is BYTE-IDENTICAL. A precompute-
    then-slice leak that assigns each match the team's latest/global rating would
    read the appended future match and break this. (The Elo recompute is per-
    cutoff causal, so appending a strictly-later match leaves the < C1 slice — and
    hence M's pre-match rating — bit-for-bit unchanged.)
    """
    c1 = pd.Timestamp("2023-08-01")
    # M: the 2023-06-10 Brazil vs Croatia match (dated < C1); Brazil is shared
    # with the future match appended below.
    m_date = pd.Timestamp("2023-06-10")
    team = "Brazil"

    def elo_pre_for_M(store) -> float:
        df = build(cutoff=c1, store=store)
        row = df[(df["date"] == m_date) & (df["team"] == team)]
        assert len(row) == 1, "expected exactly one (M, Brazil) row at C1"
        return float(row["elo_pre"].iloc[0])

    before = elo_pre_for_M(small_store)

    # Append a NEW match dated AFTER C1, same teams (Brazil vs Croatia). It must
    # not touch M's as-of-C1 pre-match rating. Reuses the store's normalize +
    # write path so the appended row is a real point-in-time result.
    from wcmodel.data.sources.results import normalize_results

    future = normalize_results(pd.DataFrame([
        ("2024-09-01", "Brazil", "Croatia", 5, 0, "Friendly", "London",
         "England", False),
    ], columns=["date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral"]))
    from wcmodel.data.store import Policy
    small_store.write("results", future, policy=Policy.POINT_IN_TIME,
                      keys=["match_id"], source="martj42", source_version="test")

    after = elo_pre_for_M(small_store)

    # BYTE-IDENTICAL: a future match must not bleed into the as-of-C1 rating.
    assert after == before, (
        f"elo_pre for M leaked future information: was {before!r}, became "
        f"{after!r} after appending a post-C1 match"
    )
