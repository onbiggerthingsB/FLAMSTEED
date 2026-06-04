import pandas as pd
from pandas.testing import assert_frame_equal
from wcmodel.model.volatility_diagnostic import count_volatility_arm


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
