"""Historical-odds adapter (OA F2/F13): per-competition sport keys, the
single-event response shape, last_update retention, raw-response sha256
persistence, event discovery, and the strict admissibility rule.

Same no-network discipline as the P1-T8 odds tests, upgraded to transport
injection: every request here goes through an ``httpx.MockTransport`` that
records what WOULD have been sent — ZERO live calls, zero credits. The new
names (``admissible_quote``, ``fetch_historical_events``) are imported inside
their tests so the RED run reports each defect distinctly instead of one
collection-time ImportError.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from wcmodel.data.sources.odds import fetch_historical, parse_snapshot


def _single_event_snapshot() -> dict:
    """Recorded shape of ``GET /v4/historical/sports/{sport}/events/{id}/odds``:
    ``data`` is ONE event object, NOT a list (defect 2). The bookmaker- and
    market-level ``last_update`` values deliberately DIFFER so retention of the
    two fields is distinguishable."""
    return {
        "timestamp": "2022-11-30T18:00:00Z",
        "previous_timestamp": "2022-11-30T17:55:00Z",
        "next_timestamp": "2022-11-30T18:05:00Z",
        "data": {
            "id": "evt_NED_USA",
            "sport_key": "soccer_fifa_world_cup",
            "commence_time": "2022-12-03T15:00:00Z",
            "home_team": "Netherlands",
            "away_team": "United States",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "last_update": "2022-11-30T17:58:41Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2022-11-30T17:57:02Z",
                            "outcomes": [
                                {"name": "Netherlands", "price": 1.98},
                                {"name": "Draw", "price": 3.45},
                                {"name": "United States", "price": 4.35},
                            ],
                        }
                    ],
                }
            ],
        },
    }


def _events_payload() -> dict:
    """Recorded shape of the DISCOVERY route
    ``GET /v4/historical/sports/{sport}/events?date=…`` — here ``data`` IS a
    list (of events without odds)."""
    return {
        "timestamp": "2022-11-30T18:00:00Z",
        "previous_timestamp": "2022-11-30T17:55:00Z",
        "next_timestamp": "2022-11-30T18:05:00Z",
        "data": [
            {"id": "evt_NED_USA", "sport_key": "soccer_fifa_world_cup",
             "sport_title": "FIFA World Cup",
             "commence_time": "2022-12-03T15:00:00Z",
             "home_team": "Netherlands", "away_team": "United States"},
            {"id": "evt_ARG_AUS", "sport_key": "soccer_fifa_world_cup",
             "sport_title": "FIFA World Cup",
             "commence_time": "2022-12-03T19:00:00Z",
             "home_team": "Argentina", "away_team": "Australia"},
        ],
    }


def _capture(payload) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """MockTransport that records every request and answers with ``payload``."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler), requests


# ---------------------------------------------------------------- (a) shapes


def test_parse_snapshot_handles_single_event_dict_data():
    rows = parse_snapshot(_single_event_snapshot())
    assert len(rows) == 3
    assert {r["event_id"] for r in rows} == {"evt_NED_USA"}
    assert {r["outcome"]: r["price"] for r in rows} == {
        "Netherlands": 1.98, "Draw": 3.45, "United States": 4.35}


def test_parse_snapshot_retains_both_last_update_fields():
    rows = parse_snapshot(_single_event_snapshot())
    assert all(r["bookmaker_last_update"] == "2022-11-30T17:58:41Z" for r in rows)
    assert all(r["market_last_update"] == "2022-11-30T17:57:02Z" for r in rows)


def test_parse_snapshot_list_shape_still_works_and_carries_last_update():
    sample = json.load(open("fixtures/oddsapi_historical_sample.json"))
    rows = parse_snapshot(sample["close"])
    pin = [r for r in rows if r["bookmaker"] == "pinnacle"]
    assert pin
    assert all(r["bookmaker_last_update"] == "2026-06-11T18:54:40Z" for r in pin)
    assert all(r["market_last_update"] == "2026-06-11T18:54:40Z" for r in pin)


def test_parse_snapshot_tolerates_missing_last_update():
    # The live wrapper / older recordings may lack the field: None, not KeyError.
    snap = _single_event_snapshot()
    del snap["data"]["bookmakers"][0]["last_update"]
    del snap["data"]["bookmakers"][0]["markets"][0]["last_update"]
    rows = parse_snapshot(snap)
    assert rows
    assert all(r["bookmaker_last_update"] is None for r in rows)
    assert all(r["market_last_update"] is None for r in rows)


# ------------------------------------------------------- (b) admissibility


def test_admissible_quote_strict_boundary():
    from wcmodel.data.sources.odds import admissible_quote
    t_issue = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)
    cut = t_issue - timedelta(minutes=30)          # default buffer
    before = cut - timedelta(seconds=1)
    assert admissible_quote(before, before, t_issue) is True
    assert admissible_quote(cut, before, t_issue) is False    # snapshot == cut
    assert admissible_quote(before, cut, t_issue) is False    # last_update == cut
    assert admissible_quote(cut, cut, t_issue) is False


def test_admissible_quote_buffer_is_configurable():
    from wcmodel.data.sources.odds import admissible_quote
    t_issue = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)
    just_before = t_issue - timedelta(seconds=1)
    assert admissible_quote(just_before, just_before, t_issue,
                            buffer_minutes=0) is True
    assert admissible_quote(t_issue, just_before, t_issue,
                            buffer_minutes=0) is False        # == cut, strict <


# ------------------------------------------- (defect 3) closing-line strictness


_KICKOFF = "2026-06-11T19:00:00Z"


def _snap(ts: str, *, commence: str = _KICKOFF,
          last_update: str | None = None) -> dict:
    lu = last_update or ts
    return {
        "timestamp": ts,
        "previous_timestamp": ts,
        "next_timestamp": ts,
        "data": [{
            "id": "evt_X_Y", "sport_key": "soccer_fifa_world_cup",
            "commence_time": commence,
            "home_team": "X", "away_team": "Y",
            "bookmakers": [{
                "key": "pinnacle", "last_update": lu,
                "markets": [{"key": "h2h", "last_update": lu,
                             "outcomes": [{"name": "X", "price": 2.0},
                                          {"name": "Draw", "price": 3.4},
                                          {"name": "Y", "price": 4.0}]}],
            }],
        }],
    }


def test_extract_closing_prices_rejects_snapshot_at_kickoff():
    # OA F2: a snapshot stamped exactly AT kickoff is an in-play price, not a
    # pre-match closing quote — the old picker admitted it (<= vs strict <).
    from wcmodel.data.sources.odds import extract_closing_prices
    sample = {"close": _snap(_KICKOFF)}
    with pytest.raises(ValueError, match="closing"):
        extract_closing_prices(sample, bookmaker="pinnacle")


def test_extract_closing_prices_falls_back_to_strictly_pre_kickoff_snapshot():
    from wcmodel.data.sources.odds import extract_closing_prices
    sample = {
        "bet_time": _snap("2026-06-11T18:55:00Z"),
        "close": _snap(_KICKOFF),                 # inadmissible: == kickoff
    }
    close = extract_closing_prices(sample, bookmaker="pinnacle")
    assert close["snapshot_ts"] == "2026-06-11T18:55:00Z"


def test_extract_closing_prices_rejects_last_update_at_kickoff():
    # BOTH legs are checked: a pre-kickoff snapshot whose bookmaker last_update
    # is AT kickoff carries an in-play price under a pre-match timestamp.
    from wcmodel.data.sources.odds import extract_closing_prices
    sample = {"close": _snap("2026-06-11T18:55:00Z", last_update=_KICKOFF)}
    with pytest.raises(ValueError, match="closing"):
        extract_closing_prices(sample, bookmaker="pinnacle")


# ------------------------------------------------- (c) sport-key URL building


def test_fetch_historical_builds_config_driven_sport_key_url(tmp_path):
    transport, requests = _capture(_single_event_snapshot())
    fetch_historical(
        "evt_NED_USA", "2022-11-30T18:00:00Z", "test-key",
        sport_key="soccer_fifa_world_cup", raw_dir=tmp_path, transport=transport)
    (req,) = requests
    assert req.url.path == (
        "/v4/historical/sports/soccer_fifa_world_cup/events/evt_NED_USA/odds")
    assert req.url.params["date"] == "2022-11-30T18:00:00Z"
    assert req.url.params["markets"] == "h2h"
    assert req.url.params["regions"] == "eu"


def test_fetch_historical_refuses_missing_sport_key_before_any_call(tmp_path):
    # The old hardcoded generic `soccer` key is INVALID on The Odds API — a
    # keyed call without a per-competition key must refuse BEFORE spending.
    transport, requests = _capture(_single_event_snapshot())
    with pytest.raises(ValueError, match="sport_key"):
        fetch_historical("evt_NED_USA", "2022-11-30T18:00:00Z", "test-key",
                         raw_dir=tmp_path, transport=transport)
    assert requests == []


def test_config_carries_per_pool_sport_keys():
    # Config-driven so the OA-0a probe can correct a wrong key WITHOUT a code
    # change; these exact strings are the probe's job to verify.
    from wcmodel.config import load_config
    assert load_config()["odds"]["sport_keys"] == {
        "wc2022": "soccer_fifa_world_cup",
        "euro2024": "soccer_uefa_european_championship",
        "wc2026": "soccer_fifa_world_cup",
    }


# ------------------------------------------------ (d) raw-hash persistence


def test_fetch_historical_persists_raw_response_and_returns_hash(tmp_path):
    payload = _single_event_snapshot()
    transport, _ = _capture(payload)
    out = fetch_historical(
        "evt_NED_USA", "2022-11-30T18:00:00Z", "test-key",
        sport_key="soccer_fifa_world_cup", raw_dir=tmp_path, transport=transport)
    digest = out["raw_sha256"]
    raw = (tmp_path / f"{digest}.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest    # content-addressed name
    assert json.loads(raw) == payload                   # byte round-trip
    assert {k: v for k, v in out.items() if k != "raw_sha256"} == payload


# ------------------------------------------------------- (e) event discovery


def test_fetch_historical_events_discovers_event_rows(tmp_path):
    from wcmodel.data.sources.odds import fetch_historical_events
    transport, requests = _capture(_events_payload())
    rows = fetch_historical_events(
        "soccer_fifa_world_cup", "2022-11-30T18:00:00Z", "test-key",
        raw_dir=tmp_path, transport=transport)
    (req,) = requests
    assert req.url.path == "/v4/historical/sports/soccer_fifa_world_cup/events"
    assert req.url.params["date"] == "2022-11-30T18:00:00Z"
    assert rows == [
        {"event_id": "evt_NED_USA", "commence_time": "2022-12-03T15:00:00Z",
         "home": "Netherlands", "away": "United States"},
        {"event_id": "evt_ARG_AUS", "commence_time": "2022-12-03T19:00:00Z",
         "home": "Argentina", "away": "Australia"},
    ]


def test_fetch_historical_events_gated_without_key(tmp_path):
    # Same Phase-0 spend gate as fetch_historical: no key, no request.
    from wcmodel.data.sources.odds import fetch_historical_events
    transport, requests = _capture(_events_payload())
    with pytest.raises(RuntimeError, match="gated"):
        fetch_historical_events("soccer_fifa_world_cup", "2022-11-30T18:00:00Z",
                                None, raw_dir=tmp_path, transport=transport)
    assert requests == []
