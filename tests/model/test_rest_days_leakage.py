import numpy as np, pandas as pd
from wcmodel.model.rest import predict_rest_days


def test_rest_uses_only_matches_before_cutoff():
    # Team A's only PLAYED match existing at the cutoff is 2026-06-12; predict 2026-06-20.
    played = pd.DataFrame({"team": ["A"], "date": [pd.Timestamp("2026-06-12")]})
    r = predict_rest_days("A", fixture_date="2026-06-20", cutoff="2026-06-18", played_schedule=played)
    assert r == 8                                  # 2026-06-20 minus 2026-06-12


def test_rest_is_null_when_predecessor_is_unplayed_future_fixture():
    # A has NO played match existing at the 2026-06-18 cutoff (its prior fixture is future/unplayed).
    played = pd.DataFrame({"team": [], "date": pd.to_datetime([])})
    r = predict_rest_days("A", fixture_date="2026-06-22", cutoff="2026-06-18", played_schedule=played)
    assert r is None or (isinstance(r, float) and np.isnan(r))


def test_rest_excludes_a_match_dated_on_or_after_cutoff():
    # A match that exists in the schedule but is dated >= cutoff must NOT be used as the predecessor.
    played = pd.DataFrame({"team": ["A", "A"],
                           "date": [pd.Timestamp("2026-06-10"), pd.Timestamp("2026-06-19")]})
    r = predict_rest_days("A", fixture_date="2026-06-22", cutoff="2026-06-18", played_schedule=played)
    assert r == 12                                 # uses 2026-06-10 (the only < cutoff match), NOT 2026-06-19


def test_rest_tz_aware_schedule_and_fixture_do_not_crash():
    # tz-SAFE contract (docstring): a tz-AWARE schedule `date` column AND a
    # tz-aware fixture_date/cutoff (e.g. an Odds API `Z`/UTC kickoff routed
    # straight in) must coerce to tz-naive UTC and yield the SAME integer
    # day-count as the tz-naive equivalent — never crash on a mixed
    # tz-aware/tz-naive subtraction. RED against the pre-fix code: fixture_date
    # was not coerced AND `last` was recomputed from the original tz-aware
    # `date` column, so `(fixture_date - last)` raised TypeError.
    naive = pd.DataFrame({"team": ["A"], "date": [pd.Timestamp("2026-06-10")]})
    r_naive = predict_rest_days(
        "A", fixture_date="2026-06-22", cutoff="2026-06-18", played_schedule=naive
    )
    aware = pd.DataFrame({"team": ["A"], "date": [pd.Timestamp("2026-06-10", tz="UTC")]})
    r_aware = predict_rest_days(
        "A",
        fixture_date=pd.Timestamp("2026-06-22", tz="UTC"),
        cutoff=pd.Timestamp("2026-06-18", tz="UTC"),
        played_schedule=aware,
    )
    assert r_aware == r_naive == 12                # tz-aware path is byte-identical to the naive path


def test_rest_mixed_tz_schedule_column_does_not_crash():
    # MIXED tz-awareness in the schedule `date` column (Codex T9 re-review): a
    # real schedule can carry one tz-naive Timestamp and one tz-aware (Odds API
    # `Z`/UTC kickoff) Timestamp side by side. `pd.to_datetime(s["date"])` on
    # such a column raises `ValueError: Tz-aware datetime.datetime cannot be
    # converted to datetime64 unless utc=True` BEFORE any coercion runs. The fix
    # coerces with utc=True then drops tz, so naive/aware/mixed all collapse to
    # one tz-naive UTC clock. RED against the pre-fix code (ValueError); GREEN
    # after, returning the SAME integer as the all-naive equivalent.
    naive = pd.DataFrame({"team": ["A", "A"],
                          "date": [pd.Timestamp("2026-06-05"),
                                   pd.Timestamp("2026-06-10")]})
    r_naive = predict_rest_days(
        "A", fixture_date="2026-06-22", cutoff="2026-06-18", played_schedule=naive
    )
    mixed = pd.DataFrame({"team": ["A", "A"],
                          "date": [pd.Timestamp("2026-06-05"),                  # tz-naive
                                   pd.Timestamp("2026-06-10", tz="UTC")]})       # tz-aware
    r_mixed = predict_rest_days(
        "A", fixture_date="2026-06-22", cutoff="2026-06-18", played_schedule=mixed
    )
    assert r_mixed == r_naive == 12               # uses 2026-06-10; mixed path == naive path
