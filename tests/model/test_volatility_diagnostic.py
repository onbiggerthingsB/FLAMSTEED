import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from wcmodel.model.volatility_diagnostic import count_volatility_arm


class _RawResultsStore:
    """Minimal store stub returning a fixed ``results`` frame verbatim.

    Bypasses ``normalize_results`` (which carries scores through untouched) so a
    deliberately INVALID score (non-integral / inf / negative) lands in the
    table exactly as a garbage feed would — letting us assert that
    ``count_volatility_arm`` applies the SAME score-validity + played filter as
    ``features.build`` (the shared ``valid_played_results`` helper), so an
    invalid-score match never inflates a team's games count. ``xg`` / ``venues``
    are absent (FileNotFoundError) — irrelevant to this diagnostic anyway.
    """

    def __init__(self, results: pd.DataFrame):
        self._results = results

    def read(self, name: str, *, cutoff):  # noqa: D401 - store-shaped read
        if name == "results":
            return self._results.copy()
        raise FileNotFoundError(name)


def test_invalid_score_row_excluded_from_games_count(tmp_path):
    """FIX A: ``count_volatility_arm`` must EXCLUDE a row with an invalid score
    EXACTLY as ``features.build`` would — so the provisional set is computed on
    the IDENTICAL valid-played row set the model fit consumes.

    Brazil has two PLAYED, valid matches plus one row with a NON-INTEGRAL score
    (1.5) and one with an ``inf`` score. ``pd.to_numeric(errors="coerce")`` alone
    would let those through (they are numeric), so a plain-notna filter would
    count FOUR Brazil games. The shared ``valid_played_results`` helper forces
    each score to be finite / non-negative / integral, dropping the two invalid
    rows — so Brazil's ``games`` is exactly 2 (the two valid matches), proving
    ``count_volatility_arm``, ``features.build`` and the calibration baseline now
    agree on the row set.
    """
    results = pd.DataFrame({
        "match_id": ["m_ok1", "m_ok2", "m_frac", "m_inf"],
        "date": pd.to_datetime(["2024-05-01", "2024-05-05", "2024-05-10",
                                "2024-05-15"]),
        "home_team": ["Brazil", "Brazil", "Brazil", "Brazil"],
        "away_team": ["Argentina", "Croatia", "Mexico", "Spain"],
        # Two valid integer scores, then a non-integral (1.5) and an inf score —
        # both numeric but NOT valid goal counts, so both must be excluded.
        "home_score": [2, 1, 1.5, "inf"],
        "away_score": [0, 1, 0, 0],
        "tournament": ["Friendly", "Friendly", "Friendly", "Friendly"],
        "neutral": [False, False, False, False],
        "city": ["London", "Paris", "Madrid", "Rome"],
        "country": ["England", "France", "Spain", "Italy"],
        "revision_contaminated": [False, False, False, False],
    })
    store = _RawResultsStore(results)
    res = count_volatility_arm(
        store=store, cutoff="2024-06-01",
        field_teams=["Brazil", "Argentina", "Croatia", "Mexico", "Spain"],
    )
    brazil = res.loc[res["team"] == "Brazil"].iloc[0]
    # Exactly the TWO valid matches counted — the 1.5 and inf rows were dropped
    # by the shared valid-played filter (a plain-notna filter would count 4).
    assert int(brazil["games"]) == 2, (
        "an invalid-score match inflated Brazil's games count — "
        "count_volatility_arm is NOT applying the shared valid-played filter"
    )
    # Spain appeared ONLY in the inf-score (excluded) match, so it has 0 games
    # and trips the few-games arm — proving that team never entered the Elo
    # recompute via the invalid row.
    spain = res.loc[res["team"] == "Spain"].iloc[0]
    assert int(spain["games"]) == 0
    assert bool(spain["few_games_flag"]) is True


def test_counts_only_volatility_arm_not_few_games(small_store):
    res = count_volatility_arm(
        store=small_store, cutoff="2024-06-01",
        field_teams=["Brazil", "Argentina", "Croatia", "Mexico"],
    )
    assert set(res.columns) >= {"team", "games", "recent_volatility",
                                "volatility_flag", "few_games_flag"}
    vol = res[res["volatility_flag"]]
    assert (vol["games"] >= 5).all()


def test_count_volatility_arm_tz_aware_cutoff_does_not_crash(small_store):
    """A tz-AWARE cutoff (e.g. an Odds API `Z`/UTC timestamp) must not crash and
    must yield the SAME result as the tz-naive equivalent.

    `fit()` routes the raw `cutoff` straight into `count_volatility_arm` to size
    the as-of-cutoff provisional set. `features.build` already coerces a
    tz-aware cutoff to tz-naive UTC before its `date < cutoff_day` filter; this
    diagnostic must mirror that coercion exactly, or a tz-aware cutoff raises a
    tz-aware-vs-tz-naive comparison error in pandas (the same Phase-1 tz bug,
    re-surfaced via the new fit() code path). A UTC-noon cutoff floors to the
    same day as the bare date string, so the boundary semantics (same-day
    excluded / prior-day included) — and therefore the flagged teams and `games`
    counts — must be byte-identical to the naive call.
    """
    field = ["Brazil", "Argentina", "Croatia", "Mexico"]
    naive = count_volatility_arm(small_store, "2024-06-01", field)
    aware = count_volatility_arm(
        small_store, pd.Timestamp("2024-06-01T12:00:00Z"), field)
    # Same flagged teams, same games counts, same volatility — identical frame.
    assert_frame_equal(aware, naive)
