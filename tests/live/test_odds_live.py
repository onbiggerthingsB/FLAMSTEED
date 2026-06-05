import json

import pytest

from wcmodel.live.odds_live import (
    LIVE_ODDS_ROUTE, fetch_live_odds, live_snapshot_from_fixture,
    CallBudget, BudgetExhaustedError, wrap_live_response,
)


def test_live_route_is_the_regular_no_date_endpoint():
    # The NEW live route is the regular GET /v4/sports/{sport}/odds (no `date`),
    # DISTINCT from the gated historical /v4/historical/... route fetch_historical
    # uses. ODDSAPI_BASE already ends in /v4, so the ROUTE must NOT repeat it (a
    # doubled /v4 would 404 when funded) — it appends to give .../v4/sports/{sport}/odds.
    from wcmodel.data.sources.odds import ODDSAPI_BASE
    assert LIVE_ODDS_ROUTE == "/sports/{sport}/odds"
    joined = f"{ODDSAPI_BASE}{LIVE_ODDS_ROUTE.format(sport='soccer_fifa_world_cup')}"
    assert joined == "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"
    assert joined.count("/v4") == 1


def test_fetch_live_odds_is_gated_without_api_key():
    # GATED like fetch_historical: raises without a key, never hits the network.
    # dry_run=False isolates the api_key gate (the dry_run gate is tested separately).
    with pytest.raises(RuntimeError, match="(?i)gated|api_key|funding"):
        fetch_live_odds(api_key=None, sport="soccer_fifa_world_cup",
                        regions="eu", market="h2h", dry_run=False)


def test_dry_run_reads_fixture_not_network(odds_fixture_path):
    # Dry-run path: NO network. It loads the fixture's CURRENT (bet_time) snapshot
    # and wraps it as a single-snapshot live mapping the real parse path consumes.
    sample = json.load(open(odds_fixture_path))
    live = live_snapshot_from_fixture(sample, which="bet_time")
    # The wrapped mapping has exactly one snapshot under the "live" key, plus the
    # dry-run flag and the non-real (_is_synthetic) taint — no other snapshot keys.
    assert set(k for k in live if k not in ("_dry_run", "_is_synthetic")) == {"live"}
    assert live["_dry_run"] is True
    assert live["live"]["data"][0]["home_team"] == "Brazil"


def test_wrap_live_response_shapes_a_raw_event_list_into_a_snapshot():
    # The regular route returns a LIST of events (no bet_time/close mapping). We wrap
    # it into a {timestamp, data:[...]} snapshot so parse_snapshot/entry_close_prices
    # consume it unchanged.
    raw_events = [{
        "id": "evt_X_Y", "sport_key": "soccer_fifa_world_cup",
        "commence_time": "2026-06-12T19:00:00Z", "home_team": "X", "away_team": "Y",
        "bookmakers": [{"key": "pinnacle", "last_update": "2026-06-12T12:00:00Z",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "X", "price": 2.0}, {"name": "Draw", "price": 3.4},
                            {"name": "Y", "price": 4.0}]}]}],
    }]
    snap = wrap_live_response(raw_events, observed_ts="2026-06-12T12:00:00Z")
    assert snap["timestamp"] == "2026-06-12T12:00:00Z"
    assert snap["data"] == raw_events


def test_call_budget_blocks_overspend_and_counts():
    budget = CallBudget(max_calls_per_day=2)
    budget.charge(); budget.charge()
    assert budget.spent == 2
    with pytest.raises(BudgetExhaustedError):
        budget.charge()                       # third call over the pinned budget => refused


def test_dry_run_never_charges_the_budget(odds_fixture_path):
    # A dry-run read does NOT consume the real-call budget (no real call happened).
    budget = CallBudget(max_calls_per_day=1)
    sample = json.load(open(odds_fixture_path))
    live_snapshot_from_fixture(sample, which="close", budget=budget)
    assert budget.spent == 0                  # dry-run is free


# --- Hardening tests (L1 spend gate / feed-agnostic / cost discipline / non-real taint).
# Additive to the six above; these pin the invariants the independent review probes.
import wcmodel.live.odds_live as _ol  # noqa: E402
from wcmodel.live.odds_live import with_backoff  # noqa: E402
from wcmodel.backtest.odds_ingest import (  # noqa: E402
    entry_close_prices, synthetic_odds_sample, _SYNTHETIC_KEY,
)


def test_no_key_call_does_not_touch_the_network(monkeypatch):
    # Belt-and-braces on the gate: with httpx.get booby-trapped to fail on contact,
    # a no-key fetch still raises the GATE error (never reaches the network).
    def _boom(*a, **k):  # pragma: no cover - must NOT be called
        raise AssertionError("network was contacted on a gated/no-key live fetch")
    monkeypatch.setattr(_ol.httpx, "get", _boom)
    # dry_run=False isolates the api_key gate; the booby-trap still proves the no-key
    # path never reaches the network (the gate raises before httpx.get).
    with pytest.raises(RuntimeError, match="(?i)gated|api_key|funding"):
        fetch_live_odds(api_key=None, sport="soccer_fifa_world_cup",
                        regions="eu", market="h2h", dry_run=False)


def test_dry_run_path_touches_no_network(monkeypatch, odds_fixture_path):
    # The dry-run harness reads the fixture; httpx.get is booby-trapped so any
    # accidental network call fails the test. The default config path is dry-run.
    def _boom(*a, **k):  # pragma: no cover - must NOT be called
        raise AssertionError("network was contacted on a dry-run live read")
    monkeypatch.setattr(_ol.httpx, "get", _boom)
    sample = json.load(open(odds_fixture_path))
    live = live_snapshot_from_fixture(sample, which="bet_time")
    assert live["_dry_run"] is True
    assert live["live"]["data"][0]["home_team"] == "Brazil"


def test_feed_agnostic_bookmaker_is_config_driven(odds_fixture_path):
    # No hard-coded book: the SAME wrapped live snapshot prices against EITHER book
    # the fixture carries (pinnacle OR betfair_ex_eu), selected by the caller/config.
    sample = json.load(open(odds_fixture_path))
    live = live_snapshot_from_fixture(sample, which="bet_time")
    pin = entry_close_prices(live, "pinnacle")
    bf = entry_close_prices(live, "betfair_ex_eu")
    # Both resolve and the two books give DISTINCT prices (genuinely book-selected).
    assert pin["entry"] != bf["entry"]
    assert set(pin["entry"]) == {"home", "draw", "away"}
    # And nothing about the route/source hard-codes a single book.
    src = inspect_module_source()
    assert '"pinnacle"' not in src and "'pinnacle'" not in src


def inspect_module_source() -> str:
    import pathlib
    return pathlib.Path(_ol.__file__).read_text()


class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        import httpx
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=None, response=self,
            )

    def json(self):
        return [{"ok": True}]


def test_backoff_retries_429_then_succeeds_with_mocked_sleep(monkeypatch):
    # 429 twice, then 200: with_backoff retries (sleeping, mocked) and returns.
    sleeps: list[float] = []
    monkeypatch.setattr(_ol.time, "sleep", lambda s: sleeps.append(s))
    seq = [_FakeResp(429), _FakeResp(429), _FakeResp(200)]
    calls = {"n": 0}

    def _fn():
        r = seq[calls["n"]]
        calls["n"] += 1
        r.raise_for_status()
        return r.json()

    out = with_backoff(_fn, max_retries=4, base_backoff=2.0)
    assert out == [{"ok": True}]
    assert calls["n"] == 3                 # two retries then success
    assert sleeps == [2.0, 4.0]            # exponential: base*2**0, base*2**1 — NO real sleep


def test_backoff_gives_up_after_max_retries_on_persistent_5xx(monkeypatch):
    import httpx
    monkeypatch.setattr(_ol.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        _FakeResp(503).raise_for_status()

    with pytest.raises(httpx.HTTPStatusError):
        with_backoff(_fn, max_retries=2, base_backoff=1.0)
    assert calls["n"] == 3                 # initial + 2 retries, then re-raise


def test_backoff_does_not_retry_a_real_client_error(monkeypatch):
    # A 404 (a real client error, not 429/5xx) is NOT retried — re-raised immediately.
    import httpx
    monkeypatch.setattr(_ol.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        _FakeResp(404).raise_for_status()

    with pytest.raises(httpx.HTTPStatusError):
        with_backoff(_fn, max_retries=4, base_backoff=1.0)
    assert calls["n"] == 1                 # NO retry on a 4xx-other-than-429


def test_synthetic_marker_propagates_through_the_live_wrapper():
    # The non-real taint rides WITH the dry-run snapshot: a synthetic sample produces
    # a live mapping carrying _is_synthetic on BOTH the wrapper and the nested snap,
    # so entry_close_prices reports is_synthetic and the store-write refuses it.
    syn = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2026-06-12T19:00:00Z",
        entry=(2.0, 3.4, 4.0), close=(1.9, 3.5, 4.2),
    )
    live = live_snapshot_from_fixture(syn["sample"], which="bet_time")
    assert live[_SYNTHETIC_KEY] is True
    assert live["live"][_SYNTHETIC_KEY] is True
    assert entry_close_prices(live, "pinnacle")["is_synthetic"] is True


def test_synthetic_live_snapshot_is_refused_by_the_store_write(small_store):
    # Defense-in-depth at the store boundary: a synthetic-tainted live mapping can
    # never be persisted as a REAL odds snapshot (load_odds_snapshots refuses it).
    from wcmodel.data.sources.odds import load_odds_snapshots
    syn = synthetic_odds_sample(
        home="Brazil", away="Croatia", commence="2026-06-12T19:00:00Z",
        entry=(2.0, 3.4, 4.0), close=(1.9, 3.5, 4.2),
    )
    live = live_snapshot_from_fixture(syn["sample"], which="bet_time")
    with pytest.raises(ValueError, match="(?i)synthetic"):
        load_odds_snapshots(small_store, live)


# --- Review-finding fixes (FIX 1-4): the spend gate (dry_run) in the fetch itself,
# dry-run output tainted non-real, budget charged PER http call, single /v4 in URL.


def test_fetch_live_odds_refuses_network_when_dry_run(monkeypatch):
    # FIX 1 (HIGH — the spend gate is incomplete). The whole-phase spend gate is
    # dry_run; with a KEY present but dry_run=true the fetch must STILL refuse the
    # network (defense-in-depth, not just the caller's dispatch). The ONLY path to
    # httpx.get is dry_run=false AND a key present. Booby-trap httpx.get: it must
    # NEVER be contacted.
    def _boom(*a, **k):  # pragma: no cover - must NOT be called
        raise AssertionError("network was contacted with dry_run=true (spend gate breached)")
    monkeypatch.setattr(_ol.httpx, "get", _boom)
    with pytest.raises(RuntimeError, match="(?i)dry.?run|gated|spend"):
        fetch_live_odds(api_key="FAKE_KEY_NOT_REAL", sport="soccer_fifa_world_cup",
                        regions="eu", market="h2h", dry_run=True)


def test_dry_run_fixture_output_is_tainted_non_real(small_store, odds_fixture_path):
    # FIX 2 (HIGH — a dry-run number can be mistaken for real). The fixture dry-run
    # output must carry the synthetic marker so entry_close_prices reports it AND
    # load_odds_snapshots refuses it (the store boundary). A dry-run number is then
    # unmistakably non-real even off the REAL fixture (not just the synthetic harness).
    from wcmodel.data.sources.odds import load_odds_snapshots
    sample = json.load(open(odds_fixture_path))
    live = live_snapshot_from_fixture(sample, which="bet_time")
    assert entry_close_prices(live, "pinnacle")["is_synthetic"] is True
    with pytest.raises(ValueError, match="(?i)synthetic"):
        load_odds_snapshots(small_store, live)


def test_budget_counts_each_retry_attempt(monkeypatch):
    # FIX 3 (HIGH — call-budget bypass on retries). The budget caps PAID api calls,
    # not decisions: each retry is another real (paid) httpx.get, so N retries must
    # count N+1 against max_calls_per_day. Persistent 503 with max_retries=2 (mocked
    # sleep) => budget.spent == total http attempts (3), not 1.
    import httpx
    monkeypatch.setattr(_ol.time, "sleep", lambda s: None)
    http_calls = {"n": 0}

    def _boom(*a, **k):
        http_calls["n"] += 1
        _FakeResp(503).raise_for_status()
    monkeypatch.setattr(_ol.httpx, "get", _boom)

    budget = CallBudget(max_calls_per_day=10)
    with pytest.raises(httpx.HTTPStatusError):
        fetch_live_odds(api_key="FAKE_KEY_NOT_REAL", sport="soccer_fifa_world_cup",
                        regions="eu", market="h2h", dry_run=False,
                        budget=budget, max_retries=2, base_backoff=1.0)
    assert http_calls["n"] == 3          # initial + 2 retries = 3 PAID http calls
    assert budget.spent == 3             # budget charged PER http call, not once

    # And exhausting the budget mid-retry refuses further attempts: a budget of 2
    # with persistent 503 makes exactly 2 http calls, then BudgetExhaustedError.
    http_calls["n"] = 0
    tight = CallBudget(max_calls_per_day=2)
    with pytest.raises(BudgetExhaustedError):
        fetch_live_odds(api_key="FAKE_KEY_NOT_REAL", sport="soccer_fifa_world_cup",
                        regions="eu", market="h2h", dry_run=False,
                        budget=tight, max_retries=5, base_backoff=1.0)
    assert http_calls["n"] == 2          # stopped at the budget ceiling mid-retry
    assert tight.spent == 2


def test_live_url_has_exactly_one_v4(monkeypatch):
    # FIX 4 (doubled /v4 — funded path 404s). ODDSAPI_BASE ends in /v4 and the route
    # must NOT also start with /v4 (…/v4/v4/… would 404 when funded). Capture the url
    # arg before raising (booby-trap the send so NO real call happens). This is the
    # one test that needs dry_run=false + a fake key to reach url construction.
    captured = {}

    def _capture(url, *a, **k):
        captured["url"] = url
        raise AssertionError("send booby-trapped after url capture (no real call)")
    monkeypatch.setattr(_ol.httpx, "get", _capture)

    with pytest.raises(AssertionError):
        fetch_live_odds(api_key="FAKE_KEY_NOT_REAL", sport="soccer_fifa_world_cup",
                        regions="eu", market="h2h", dry_run=False, max_retries=0)
    url = captured["url"]
    assert url.count("/v4") == 1
    assert url.endswith("/sports/soccer_fifa_world_cup/odds")
