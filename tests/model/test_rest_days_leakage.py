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
