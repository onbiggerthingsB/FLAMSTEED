import pandas as pd
import pytest
from wcmodel.data.store import BitemporalStore, Policy


def _df(rows):
    return pd.DataFrame(rows)


def test_point_in_time_never_returns_future_observations(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("elo", _df([
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
        {"team": "BRA", "valid_as_of": "2025-06-01", "observed_at": "2025-06-01", "rating": 2050.0},
    ]), policy=Policy.POINT_IN_TIME, keys=["team"])
    out = store.read("elo", cutoff="2025-03-01")
    assert list(out["rating"]) == [2000.0]
    assert (out["observed_at"] <= pd.Timestamp("2025-03-01")).all()


def test_point_in_time_returns_latest_observation_at_or_before_cutoff(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("elo", _df([
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
        {"team": "BRA", "valid_as_of": "2025-06-01", "observed_at": "2025-06-01", "rating": 2050.0},
    ]), policy=Policy.POINT_IN_TIME, keys=["team"])
    out = store.read("elo", cutoff="2025-07-01")
    assert list(out["rating"]) == [2050.0]


def test_current_only_serves_snapshot_but_flags_contaminated(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("mktval", _df([
        {"team": "BRA", "valid_as_of": "2026-06-01", "observed_at": "2026-06-01", "value_eur": 1.2e9},
    ]), policy=Policy.CURRENT_ONLY, keys=["team"])
    out = store.read("mktval", cutoff="2025-03-01")
    assert list(out["value_eur"]) == [1.2e9]
    assert out["revision_contaminated"].all()


def test_point_in_time_does_not_set_contamination_flag(tmp_path):
    store = BitemporalStore(root=tmp_path)
    store.write("elo", _df([
        {"team": "BRA", "valid_as_of": "2025-01-01", "observed_at": "2025-01-01", "rating": 2000.0},
    ]), policy=Policy.POINT_IN_TIME, keys=["team"])
    out = store.read("elo", cutoff="2025-07-01")
    assert not out["revision_contaminated"].any()
