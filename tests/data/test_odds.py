import json

import pytest

from wcmodel.data.sources.odds import (
    parse_snapshot, extract_closing_prices, load_odds_snapshots,
)
from wcmodel.data.store import BitemporalStore


def _sample():
    return json.load(open("fixtures/oddsapi_historical_sample.json"))


def test_parse_snapshot_extracts_pinnacle_h2h():
    rows = parse_snapshot(_sample()["close"])
    pin = [r for r in rows if r["bookmaker"] == "pinnacle"]
    assert pin and {"event_id", "bookmaker", "outcome", "price", "snapshot_ts"} <= set(pin[0])


def test_extract_closing_prices_picks_snapshot_nearest_kickoff():
    close = extract_closing_prices(_sample(), bookmaker="pinnacle")
    assert close["snapshot_ts"] == _sample()["close"]["timestamp"]
    assert close["bookmaker"] == "pinnacle"


def test_no_network_call_in_tests(monkeypatch):
    import wcmodel.data.sources.odds as m

    def _boom(*a, **k):
        raise AssertionError("no network")

    # Both fetchers transport through httpx.Client (the module no longer calls
    # httpx.get anywhere); patch BOTH so the sentinel stays armed even if the
    # transport style drifts back.
    monkeypatch.setattr(m.httpx, "get", _boom)
    monkeypatch.setattr(m.httpx, "Client", _boom)
    parse_snapshot(_sample()["close"])   # parse path never touches the network
    # Non-vacuity: the armed sentinel really does intercept the network path.
    with pytest.raises(AssertionError, match="no network"):
        m.fetch_historical("evt_BRA_CRO", "2026-06-11T18:55:00Z", "k",
                           sport_key="soccer_fifa_world_cup", raw_dir=None)


def test_fetch_historical_raises_without_key():
    import pytest
    from wcmodel.data.sources.odds import fetch_historical
    with pytest.raises(RuntimeError):
        fetch_historical(event_id="evt_BRA_CRO", ts="2026-06-11T18:55:00Z", api_key=None)


def test_load_odds_snapshots_stores_real_fixture(tmp_path):
    # MUST-FIX 1(c): the real-ingest path is UNCHANGED — a real (non-synthetic)
    # sample still loads into the store without error.
    store = BitemporalStore(root=tmp_path)
    load_odds_snapshots(store, _sample())          # no marker => stores fine
    rows = store.read("odds", cutoff="2030-01-01T00:00:00Z")
    assert len(rows) > 0 and "pinnacle" in set(rows["bookmaker"])


def test_load_odds_snapshots_refuses_synthetic_wrapper_sample(tmp_path):
    # MUST-FIX 1(c): a synthetic harness sample must NEVER be persisted as real.
    # The store boundary refuses a sample carrying the synthetic marker (whether on
    # the wrapper or — see next test — on a nested snapshot).
    from wcmodel.backtest.odds_ingest import synthetic_odds_sample
    store = BitemporalStore(root=tmp_path)
    syn = synthetic_odds_sample(home="X", away="Y", commence="2024-06-20T19:00:00Z",
                                entry=(2.0, 3.4, 4.0), close=(1.9, 3.5, 4.3))
    with pytest.raises(ValueError, match="synthetic"):
        load_odds_snapshots(store, syn["sample"])


def test_load_odds_snapshots_refuses_synthetic_marked_nested_snapshot(tmp_path):
    # Defense-in-depth: even a sample WITHOUT a wrapper marker but with a snapshot
    # carrying the marker is refused — a synthetic snapshot can't sneak in.
    from wcmodel.backtest.odds_ingest import _SYNTHETIC_KEY
    store = BitemporalStore(root=tmp_path)
    sample = _sample()
    sample["close"][_SYNTHETIC_KEY] = True         # stamp a nested snapshot only
    with pytest.raises(ValueError, match="synthetic"):
        load_odds_snapshots(store, sample)
