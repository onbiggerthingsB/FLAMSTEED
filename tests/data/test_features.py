import numpy as np
import pandas as pd
from wcmodel.data.features import build


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
