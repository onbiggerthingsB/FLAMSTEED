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
import traceback
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
          last_update: str | None = None,
          market_last_update: str | None = None) -> dict:
    lu = last_update or ts
    mlu = market_last_update or lu
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
                "markets": [{"key": "h2h", "last_update": mlu,
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


def test_extract_closing_prices_rejects_post_kickoff_snapshot_with_stale_stamps():
    # Leg 1 in ISOLATION (mutation pin): the snapshot was PULLED at 19:05 —
    # five minutes into the match — while BOTH last_update stamps sit at 18:50,
    # the ordinary suspension pattern (after a book suspends, the historical
    # route keeps returning the last pre-match stamp unchanged). The stamp leg
    # alone would ADMIT this in-play snapshot — and, being the latest, CHOOSE
    # it as the closing line (OA F2). The snapshot-timestamp leg must reject it
    # on its own; dropping leg 1 survives every other test in this file.
    from wcmodel.data.sources.odds import extract_closing_prices
    sample = {"close": _snap("2026-06-11T19:05:00Z",
                             last_update="2026-06-11T18:50:00Z")}
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
    # (review round 4, fix 4) Decimal is load-bearing on a PAID param: a drift
    # to 'american' would archive moneyline integers (+150) that every
    # downstream de-vig/CLV/RPS consumer parses as decimal odds (150.0) —
    # silently corrupting every number computed from paid data.
    assert req.url.params["oddsFormat"] == "decimal"


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
    # Discovery is PAID too: every row carries the archived response's sha256,
    # so a probe's "event found y/n" claim has citable provenance instead of
    # discarding the hash the archive already computed (review fix 6c).
    (raw,) = tmp_path.glob("*.json")
    digest = raw.stem
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == digest
    assert rows == [
        {"event_id": "evt_NED_USA", "commence_time": "2022-12-03T15:00:00Z",
         "home": "Netherlands", "away": "United States", "raw_sha256": digest},
        {"event_id": "evt_ARG_AUS", "commence_time": "2022-12-03T19:00:00Z",
         "home": "Argentina", "away": "Australia", "raw_sha256": digest},
    ]


def test_fetch_historical_events_gated_without_key(tmp_path):
    # Same Phase-0 spend gate as fetch_historical: no key, no request.
    from wcmodel.data.sources.odds import fetch_historical_events
    transport, requests = _capture(_events_payload())
    with pytest.raises(RuntimeError, match="gated"):
        fetch_historical_events("soccer_fifa_world_cup", "2022-11-30T18:00:00Z",
                                None, raw_dir=tmp_path, transport=transport)
    assert requests == []


# ------------------------------------- (review fix 1) key never in an error


def _error_transport(status: int = 401) -> httpx.MockTransport:
    """Answers every request with a keyed-endpoint failure — the exact shapes
    (401 bad key / 429 quota) a live probe hits first."""
    return httpx.MockTransport(
        lambda request: httpx.Response(status, json={"message": "Invalid API key"}))


def test_fetch_historical_http_error_never_carries_the_api_key(tmp_path):
    # The probe's failure handler writes str(exc) into a COMMITTED report
    # (reports/oa_probe.md); httpx's stock HTTPStatusError message embeds the
    # full request URL, whose query is apiKey=<secret>. Render the FULL
    # traceback (message + context chain) — the key must appear nowhere, and
    # exc.request must not hold a resurrectable copy either.
    with pytest.raises(httpx.HTTPStatusError) as err:
        fetch_historical(
            "evt_NED_USA", "2022-11-30T18:00:00Z", "SECRET-abc123",
            sport_key="soccer_fifa_world_cup", raw_dir=tmp_path,
            transport=_error_transport())
    rendered = "".join(traceback.format_exception(err.value))
    assert "SECRET-abc123" not in rendered
    assert "SECRET-abc123" not in str(err.value.request.url)
    assert err.value.response.status_code == 401     # the probe still reads this


def test_fetch_historical_events_http_error_never_carries_the_api_key(tmp_path):
    from wcmodel.data.sources.odds import fetch_historical_events
    with pytest.raises(httpx.HTTPStatusError) as err:
        fetch_historical_events(
            "soccer_fifa_world_cup", "2022-11-30T18:00:00Z", "SECRET-abc123",
            raw_dir=tmp_path, transport=_error_transport(429))
    rendered = "".join(traceback.format_exception(err.value))
    assert "SECRET-abc123" not in rendered
    assert "SECRET-abc123" not in str(err.value.request.url)
    assert err.value.response.status_code == 429


def test_redaction_survives_empty_api_key(tmp_path):
    # api_key="" passes the None-gate, and str.replace("", "***") would mangle
    # the whole message char-by-char — the redaction must not depend on a
    # non-empty key (the query-strip already guarantees safety on its own).
    with pytest.raises(httpx.HTTPStatusError) as err:
        fetch_historical(
            "evt_NED_USA", "2022-11-30T18:00:00Z", "",
            sport_key="soccer_fifa_world_cup", raw_dir=tmp_path,
            transport=_error_transport())
    assert str(err.value).startswith("Client error '401")


def test_fetch_historical_archives_paid_error_body_before_raising(tmp_path):
    # "A paid response is never lost" must cover the failure case too: the body
    # of a non-2xx PAID response is the evidence (quota state, error cause) a
    # failed spend gets audited from, so it is archived BEFORE the status gate
    # raises (review fix 6b).
    with pytest.raises(httpx.HTTPStatusError):
        fetch_historical(
            "evt_NED_USA", "2022-11-30T18:00:00Z", "SECRET-abc123",
            sport_key="soccer_fifa_world_cup", raw_dir=tmp_path,
            transport=_error_transport())
    (raw,) = tmp_path.glob("*.json")
    assert json.loads(raw.read_bytes()) == {"message": "Invalid API key"}


def _transport_failure(exc: httpx.RequestError) -> httpx.MockTransport:
    """A transport whose GET dies BELOW the HTTP layer — the read-timeout /
    connection-failure class, against a paid API at least as likely as the
    401/429 the status-redaction tests cover."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc
    return httpx.MockTransport(handler)


def test_fetch_historical_transport_error_never_carries_the_api_key(tmp_path):
    # A transport-level failure escapes client.get BEFORE
    # _raise_for_status_redacted can run, and httpx attaches the UNMODIFIED
    # request — so exc.request.url carried apiKey=<secret> into the same
    # committed-report failure handlers the status-error tests protect.
    with pytest.raises(httpx.ReadTimeout) as err:
        fetch_historical(
            "evt_NED_USA", "2022-11-30T18:00:00Z", "SECRET-abc123",
            sport_key="soccer_fifa_world_cup", raw_dir=tmp_path,
            transport=_transport_failure(httpx.ReadTimeout("read timed out")))
    rendered = "".join(traceback.format_exception(err.value))
    assert "SECRET-abc123" not in rendered
    assert "SECRET-abc123" not in str(err.value.request.url)


def test_fetch_historical_events_transport_error_never_carries_the_api_key(tmp_path):
    from wcmodel.data.sources.odds import fetch_historical_events
    with pytest.raises(httpx.ConnectError) as err:
        fetch_historical_events(
            "soccer_fifa_world_cup", "2022-11-30T18:00:00Z", "SECRET-abc123",
            raw_dir=tmp_path,
            transport=_transport_failure(httpx.ConnectError("connection refused")))
    rendered = "".join(traceback.format_exception(err.value))
    assert "SECRET-abc123" not in rendered
    assert "SECRET-abc123" not in str(err.value.request.url)


# ----------------- (review fix 2) market_last_update is admissibility evidence


def test_extract_closing_prices_rejects_market_last_update_after_kickoff():
    # Snapshot 18:55, kickoff 19:00, bookmaker stamp 18:50 — but the h2h
    # market's own last_update (the age of the PRICE itself) is 19:05, five
    # minutes into the match. In-play under a pre-match wrapper: REJECT.
    from wcmodel.data.sources.odds import extract_closing_prices
    sample = {"close": _snap("2026-06-11T18:55:00Z",
                             last_update="2026-06-11T18:50:00Z",
                             market_last_update="2026-06-11T19:05:00Z")}
    with pytest.raises(ValueError, match="closing"):
        extract_closing_prices(sample, bookmaker="pinnacle")


def test_extract_closing_prices_uses_market_stamp_when_bookmaker_stamp_missing():
    # bookmaker last_update MISSING (a shape parse_snapshot deliberately
    # tolerates) while market last_update 19:05 is PRESENT: the fallback must
    # reach for the stricter evidence sitting in the row — falling back to the
    # snapshot timestamp would collapse the BOTH-legs rule into leg 1 exactly
    # when it matters.
    from wcmodel.data.sources.odds import extract_closing_prices
    snap = _snap("2026-06-11T18:55:00Z",
                 market_last_update="2026-06-11T19:05:00Z")
    del snap["data"][0]["bookmakers"][0]["last_update"]
    with pytest.raises(ValueError, match="closing"):
        extract_closing_prices({"close": snap}, bookmaker="pinnacle")


def test_extract_closing_prices_admits_missing_bookmaker_stamp_clean_market():
    # Non-regression control for the two rejections above: with NO bookmaker
    # stamp and a strictly pre-kickoff market stamp, the quote stays admissible.
    from wcmodel.data.sources.odds import extract_closing_prices
    snap = _snap("2026-06-11T18:55:00Z",
                 market_last_update="2026-06-11T18:54:00Z")
    del snap["data"][0]["bookmakers"][0]["last_update"]
    close = extract_closing_prices({"close": snap}, bookmaker="pinnacle")
    assert close["snapshot_ts"] == "2026-06-11T18:55:00Z"


def test_extract_closing_prices_checks_bookmaker_stamp_even_with_clean_market():
    # Mutation pin (the reviewer's probe): swapping the check ONTO the market
    # stamp alone must fail here — every stamp the row carries is evidence.
    from wcmodel.data.sources.odds import extract_closing_prices
    sample = {"close": _snap("2026-06-11T18:55:00Z",
                             last_update="2026-06-11T19:05:00Z",
                             market_last_update="2026-06-11T18:50:00Z")}
    with pytest.raises(ValueError, match="closing"):
        extract_closing_prices(sample, bookmaker="pinnacle")


# --------------------- (review fix 4) extract_closing_prices is single-event


def test_extract_closing_prices_refuses_multi_event_snapshot():
    # The return shape (ONE flat outcomes map) cannot describe two events: the
    # old code merged outcome names across events ('Draw' last-write-wins) and
    # let one kicked-off fixture veto the whole bookmaker. Single-event-only,
    # enforced loudly — multi-event snapshots must be split per event first.
    from wcmodel.data.sources.odds import extract_closing_prices
    snap = _snap("2026-06-11T18:55:00Z")
    snap["data"].append({
        "id": "evt_A_B", "sport_key": "soccer_fifa_world_cup",
        "commence_time": "2026-06-11T22:00:00Z",
        "home_team": "A", "away_team": "B",
        "bookmakers": [{
            "key": "pinnacle", "last_update": "2026-06-11T18:55:00Z",
            "markets": [{"key": "h2h", "last_update": "2026-06-11T18:55:00Z",
                         "outcomes": [{"name": "A", "price": 1.5},
                                      {"name": "Draw", "price": 4.2},
                                      {"name": "B", "price": 6.0}]}],
        }],
    })
    with pytest.raises(ValueError, match="single-event"):
        extract_closing_prices({"close": snap}, bookmaker="pinnacle")


# ------------------------ (review fix 5) admissible_quote None-stamp contract


def test_admissible_quote_refuses_none_last_update_loudly():
    # Documented policy (the T5 ledger imports this helper): None is a CALLER
    # error — resolve a missing stamp to the strictest available evidence
    # BEFORE calling, the way extract_closing_prices does. The helper never
    # guesses a quote's age, so weakening this to a silent fallback is a
    # contract change, not a convenience.
    from wcmodel.data.sources.odds import admissible_quote
    t_issue = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(TypeError):
        admissible_quote(t_issue - timedelta(hours=2), None, t_issue)


# ------------------- (review fix 6a) default raw_dir vs injected transports


def test_default_raw_dir_is_inert_under_an_injected_transport(monkeypatch):
    # raw_dir defaults to the REAL repo archive while transport is injectable:
    # a mocked test or dry-run that forgets raw_dir=tmp_path must not write
    # fabricated payloads into the repo tree. The default engages only for
    # real-network (paid) responses; an explicit raw_dir is always honored.
    import wcmodel.data.sources.odds as m
    seen: list = []
    real_persist = m._persist_raw

    def spy(content, raw_dir):
        seen.append(raw_dir)
        return real_persist(content, None)     # hash, never write

    monkeypatch.setattr(m, "_persist_raw", spy)
    transport, _ = _capture(_single_event_snapshot())
    out = m.fetch_historical(
        "evt_NED_USA", "2022-11-30T18:00:00Z", "test-key",
        sport_key="soccer_fifa_world_cup", transport=transport)  # raw_dir omitted
    assert "raw_sha256" in out                 # provenance hash still computed
    ev_transport, _ = _capture(_events_payload())
    m.fetch_historical_events(
        "soccer_fifa_world_cup", "2022-11-30T18:00:00Z", "test-key",
        transport=ev_transport)                                  # raw_dir omitted
    assert seen == [None, None]                # mock bytes never hit the archive


# ----------------- (review round 3, fix 1) raw archive is crash-consistent


def test_persist_raw_self_heals_a_torn_archive_file(tmp_path):
    # write_bytes is not atomic: an interrupt/ENOSPC mid-write leaves a file
    # NAMED <sha256>.json whose bytes hash to something else, and the old
    # skip-if-exists dedupe then trusted the torn file FOREVER — silently
    # breaking "the hash the ledger cites always resolves to the exact bytes",
    # on a response that costs credits to re-obtain. Same name must be
    # VERIFIED against the bytes, never assumed.
    from wcmodel.data.sources.odds import _persist_raw
    content = json.dumps(_single_event_snapshot()).encode()
    digest = hashlib.sha256(content).hexdigest()
    torn = tmp_path / f"{digest}.json"
    torn.write_bytes(content[: len(content) // 2])   # interrupted earlier write
    assert _persist_raw(content, tmp_path) == digest
    assert torn.read_bytes() == content              # healed, not skipped
    assert list(tmp_path.iterdir()) == [torn]        # and no tmp litter left


def test_persist_raw_crash_before_rename_never_taints_the_final_name(
        tmp_path, monkeypatch):
    # Atomicity pin: die between tmp-write and rename — the content-addressed
    # name must NOT exist afterwards. A torn <sha256>.json is exactly what the
    # dedupe would trust on every later fetch; a missing file just re-archives.
    import wcmodel.data.sources.odds as m

    def crash(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(m.os, "replace", crash)
    content = b'{"paid": "evidence"}'
    digest = hashlib.sha256(content).hexdigest()
    with pytest.raises(OSError):
        m._persist_raw(content, tmp_path)
    assert not (tmp_path / f"{digest}.json").exists()
    assert list(tmp_path.iterdir()) == []            # tmp cleaned up best-effort


# --------------- (review round 3, fix 2) empty data payload is zero events


def test_event_list_empty_payloads_are_zero_events():
    # {} is not an event: [{}] is a TRUTHY one-element list that turned the
    # previously-silent empty case into KeyError('id') in every consumer of
    # the ONE normalizer; clv_validation's real-shape builder already treats
    # falsy data as empty.
    from wcmodel.data.sources.odds import event_list
    assert event_list({}) == []
    assert event_list([]) == []
    assert event_list(None) == []


def test_parse_snapshot_empty_dict_data_yields_no_rows():
    # Pre-T3 code (`snapshot.get("data", [])` iteration) returned [] here.
    assert parse_snapshot({"timestamp": "2026-06-11T18:00:00Z",
                           "data": {}}) == []


def test_extract_closing_prices_skips_empty_data_snapshot():
    # An empty-data snapshot must be SKIPPED, not abort the whole call while
    # a perfectly good close sits right beside it in the sample.
    from wcmodel.data.sources.odds import extract_closing_prices
    empty = {"timestamp": "2026-06-11T18:50:00Z",
             "previous_timestamp": "2026-06-11T18:45:00Z",
             "next_timestamp": "2026-06-11T18:55:00Z",
             "data": {}}
    sample = {"empty": empty, "close": _snap("2026-06-11T18:55:00Z")}
    close = extract_closing_prices(sample, bookmaker="pinnacle")
    assert close["snapshot_ts"] == "2026-06-11T18:55:00Z"


# ------- (review round 3, fix 3) None-stamp TypeError on EVERY branch


def test_admissible_quote_refuses_none_last_update_on_every_branch():
    # The documented TypeError contract must not depend on short-circuit
    # order: with the snapshot leg already failing (snapshot_ts == t_issue),
    # `snapshot_ts < cut and last_update < cut` returned a QUIET False without
    # ever comparing None. T5's ledger is told it can lean on the loud failure
    # to catch an unresolved stamp, so the check precedes the comparison.
    from wcmodel.data.sources.odds import admissible_quote
    t_issue = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(TypeError):
        admissible_quote(t_issue, None, t_issue)


# ------- (review round 3, fix 4) discovery refuses unrecognized payloads


def test_fetch_historical_events_refuses_dict_payload_without_data(tmp_path):
    # A dict payload with NO 'data' key is an unexpected/changed response
    # shape. On a PAID discovery call, reading it as [] is indistinguishable
    # from a genuine "no events at this timestamp" — the probe would bill
    # credits and report zero coverage as truth. Refuse loudly, citing the
    # archived raw hash for audit.
    from wcmodel.data.sources.odds import fetch_historical_events
    transport, _ = _capture({"timestamp": "2022-11-30T18:00:00Z",
                             "message": "response shape changed"})
    with pytest.raises(ValueError, match="data"):
        fetch_historical_events(
            "soccer_fifa_world_cup", "2022-11-30T18:00:00Z", "test-key",
            raw_dir=tmp_path, transport=transport)


def test_fetch_historical_events_empty_data_is_a_genuine_no_events(tmp_path):
    # Contrast pin for the guard's boundary: 'data' PRESENT and empty is the
    # API's real "nothing scheduled here" answer — [] stays the result.
    from wcmodel.data.sources.odds import fetch_historical_events
    transport, _ = _capture({"timestamp": "2022-11-30T18:00:00Z", "data": []})
    assert fetch_historical_events(
        "soccer_fifa_world_cup", "2022-11-30T18:00:00Z", "test-key",
        raw_dir=tmp_path, transport=transport) == []


# ---------- (review round 4, fix 1) event identity holds ACROSS snapshots


def _event_snap(ts: str, *, event_id: str, home: str, away: str,
                commence: str, prices: tuple[float, float, float]) -> dict:
    """One SINGLE-event snapshot for an arbitrary fixture (``_snap`` hardcodes
    evt_X_Y, so it cannot express a mixed-fixture sample)."""
    h, d, a = prices
    return {
        "timestamp": ts, "previous_timestamp": ts, "next_timestamp": ts,
        "data": [{
            "id": event_id, "sport_key": "soccer_fifa_world_cup",
            "commence_time": commence, "home_team": home, "away_team": away,
            "bookmakers": [{
                "key": "pinnacle", "last_update": ts,
                "markets": [{"key": "h2h", "last_update": ts,
                             "outcomes": [{"name": home, "price": h},
                                          {"name": "Draw", "price": d},
                                          {"name": away, "price": a}]}],
            }],
        }],
    }


def test_extract_closing_prices_refuses_sample_spanning_two_fixtures():
    # The per-snapshot guard counts events WITHIN each snapshot only: a sample
    # holding SINGLE-event snapshots for two DIFFERENT fixtures sailed through,
    # and latest-timestamp-wins silently returned Spain-Japan's line for a
    # sample that also holds Brazil-Croatia — exactly the collision/substitution
    # the single-event refusal exists to prevent, one level up. A Plan-2
    # pipeline assembling samples by timestamp rather than by fixture would
    # attach another match's close to this fixture's CLV/ledger row.
    from wcmodel.data.sources.odds import extract_closing_prices
    sample = {
        "close_A": _event_snap("2026-06-11T18:55:00Z", event_id="evt_BRA_CRO",
                               home="Brazil", away="Croatia",
                               commence="2026-06-11T19:00:00Z",
                               prices=(1.5, 4.0, 7.0)),
        "close_B": _event_snap("2026-06-11T21:55:00Z", event_id="evt_ESP_JPN",
                               home="Spain", away="Japan",
                               commence="2026-06-11T22:00:00Z",
                               prices=(2.2, 3.3, 3.6)),
    }
    with pytest.raises(ValueError, match="single-event"):
        extract_closing_prices(sample, bookmaker="pinnacle")


def test_extract_closing_prices_returns_event_id_for_downstream_assertion():
    # Belt-and-braces for the same substitution class: the chosen line names
    # its fixture, so a caller can ASSERT it got the event it asked about
    # instead of trusting sample assembly it does not control.
    from wcmodel.data.sources.odds import extract_closing_prices
    close = extract_closing_prices(
        {"close": _snap("2026-06-11T18:55:00Z")}, bookmaker="pinnacle")
    assert close["event_id"] == "evt_X_Y"


# ----- (review round 4, fix 2) raw-dir default archives real-network calls


def test_resolve_raw_dir_defaults_real_network_calls_into_the_repo_archive(
        tmp_path):
    # transport=None is the ONLY path where credits are spent, and nothing
    # pinned it: mutating the resolver to `return None` (every PAID response
    # archived nowhere — "a paid response is never lost" silently void) left
    # the whole suite green. Pin all four (raw_dir, transport) quadrants.
    from wcmodel.data.sources.odds import (
        ODDS_RAW_DIR, _RAW_DIR_UNSET, _resolve_raw_dir)
    mock = httpx.MockTransport(lambda request: httpx.Response(200))
    assert _resolve_raw_dir(_RAW_DIR_UNSET, None) == ODDS_RAW_DIR
    assert _resolve_raw_dir(_RAW_DIR_UNSET, mock) is None
    assert _resolve_raw_dir(tmp_path, mock) == tmp_path
    assert _resolve_raw_dir(None, None) is None


# ---- (review round 4, fix 3) strictest_last_update is the public contract


def test_strictest_last_update_is_the_exported_stamp_resolution():
    # The T5 ledger must IMPORT this resolution, not re-invent the weakening —
    # the same reason event_list was de-privatized (five modules were keeping
    # private copies). Latest stamp present wins; the snapshot timestamp
    # stands in only when BOTH are absent.
    from wcmodel.data.sources.odds import strictest_last_update
    snap_ts = "2026-06-11T18:55:00Z"
    both = {"bookmaker_last_update": "2026-06-11T18:50:00Z",
            "market_last_update": "2026-06-11T18:57:00Z"}
    assert strictest_last_update(both, snap_ts) == datetime(
        2026, 6, 11, 18, 57, tzinfo=timezone.utc)
    one = {"bookmaker_last_update": "2026-06-11T18:50:00Z",
           "market_last_update": None}
    assert strictest_last_update(one, snap_ts) == datetime(
        2026, 6, 11, 18, 50, tzinfo=timezone.utc)
    neither = {"bookmaker_last_update": None, "market_last_update": None}
    assert strictest_last_update(neither, snap_ts) == datetime(
        2026, 6, 11, 18, 55, tzinfo=timezone.utc)
