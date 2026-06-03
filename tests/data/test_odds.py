import json
from wcmodel.data.sources.odds import parse_snapshot, extract_closing_prices


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
    monkeypatch.setattr(m.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    parse_snapshot(_sample()["close"])   # parse path never touches the network


def test_fetch_historical_raises_without_key():
    import pytest
    from wcmodel.data.sources.odds import fetch_historical
    with pytest.raises(RuntimeError):
        fetch_historical(event_id="evt_BRA_CRO", ts="2026-06-11T18:55:00Z", api_key=None)
