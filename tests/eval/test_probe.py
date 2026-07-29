"""The gated OA-0a probe runner (spec finding 13) — the SPEND GATE.

``scripts/oa_probe.py`` is the ONLY code path that could ever spend Odds-API
credits, so the tests here pin the gates harder than the happy path: dry-run is
the default and spends nothing (mocked transport, sentinel key — never the env
key); ``--live`` refuses to start without BOTH ``ODDS_API_KEY`` and
``--max-credits``; a cap below the full-plan projection aborts BEFORE the first
transport call (zero requests recorded); and every failure string that could
reach the COMMITTED report is exercised through the T3 key-redaction path.

NO test here touches the network: every request goes through an
``httpx.MockTransport`` (live-path tests monkeypatch the transport factory).
The real ``--live`` run is the USER's decision at the plan-end STOP gate and is
never executed by tests or agents.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _ROOT / "scripts" / "oa_probe.py"
_STORE = _ROOT / "data" / "stores" / "full_final"

# Same idiom as tests/eval/test_regulation.py: /data/ is gitignored, so the
# store-join spelling check skips (with a reason) where the local store is
# absent — the always-on structural tests still hold the fixture list.
_needs_store = pytest.mark.skipif(
    not _STORE.exists(),
    reason=f"{_STORE} absent (gitignored local artifact) — rebuild it to re-arm "
           "the probe-fixture-vs-store spelling check")

_SPORT_KEYS = {
    "wc2022": "soccer_fifa_world_cup",
    "euro2024": "soccer_uefa_european_championship",
    "wc2026": "soccer_fifa_world_cup",
}


def _load():
    spec = importlib.util.spec_from_file_location("oa_probe", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(tmp_path, monkeypatch, isolated_odds_raw_dir):
    # Load from an unrelated cwd: the report default is cwd-relative, so any
    # module-level file access (or accidental probe run) surfaces here instead
    # of silently touching the committed reports/oa_probe.md. The explicit
    # isolated_odds_raw_dir dependency (autouse anyway) guarantees the source
    # module is patched BEFORE this load binds oa_probe's own ODDS_RAW_DIR.
    monkeypatch.chdir(tmp_path)
    return _load()


def _files_under(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------- #
# Import safety + the pre-listed fixture panel.                                 #
# --------------------------------------------------------------------------- #
def test_import_runs_no_probe_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mod = _load()
    assert callable(mod.main)
    assert list(tmp_path.iterdir()) == []


def test_probe_fixture_panel_is_15_stratified_5_per_pool(mod):
    fixtures = mod.PROBE_FIXTURES
    assert len(fixtures) == 15
    by_pool: dict[str, list] = {}
    for fx in fixtures:
        by_pool.setdefault(fx["pool"], []).append(fx)
    assert set(by_pool) == set(_SPORT_KEYS)
    # The plan's stratification: opening day / mid-group / last group day /
    # one KO / the final — per pool, exactly once each.
    want = {"opening_day", "mid_group", "last_group_day", "knockout", "final"}
    for pool, rows in by_pool.items():
        assert len(rows) == 5, pool
        assert {r["stratum"] for r in rows} == want, pool


@_needs_store
def test_probe_fixtures_join_the_store_spelling_exactly():
    # Team spellings must match the martj42 store (the same ground truth the
    # T2 regulation table joins) — a misspelled probe fixture would burn live
    # credits discovering an event the report then can't tie back to a pool
    # fixture. Mechanical, not by eye.
    import pandas as pd
    from wcmodel.data.store import BitemporalStore
    mod = _load()
    store = BitemporalStore(root=_STORE).read(
        "results", cutoff="2026-07-28T00:00:00Z")
    store = store.assign(date=pd.to_datetime(store["date"]).dt.date.astype(str))
    keys = set(zip(store["date"], store["home_team"], store["away_team"]))
    missing = [fx for fx in mod.PROBE_FIXTURES
               if (fx["date"], fx["home"], fx["away"]) not in keys]
    assert missing == [], f"probe fixtures not in the store: {missing}"


# --------------------------------------------------------------------------- #
# The credit arithmetic (the load-bearing 315) + the extrapolation formula.     #
# --------------------------------------------------------------------------- #
def test_projected_probe_cost_is_315_and_matches_the_call_plan(mod):
    # 15 fixtures x (1 discovery @ 1 credit + 2 snapshots @ 10 credits per
    # region-market; h2h x eu = 1 region-market) = 315. The plan's Step-5
    # expected projection — pinned so a silent change to the call plan or the
    # per-call prices cannot drift the number the user approves at the gate.
    assert mod.projected_probe_cost() == 315
    plan = mod.build_call_plan(_SPORT_KEYS)
    assert len(plan) == 45                       # 15 discovery + 30 snapshots
    assert sum(row["credits"] for row in plan) == mod.projected_probe_cost()


def test_full_program_budget_keeps_n_dev_an_explicit_input(mod):
    # (217 eval + N_dev) x 2 snapshots x 10 credits — 217 = the 185-pool plus
    # the 32 WC-2026 knockout fixtures. N_dev is the OA-0b sizing decision and
    # must stay a formula input, never a baked-in assumption.
    assert mod.full_program_budget(0) == 4340
    assert mod.full_program_budget(100) == 4340 + 100 * 2 * 10


def test_spend_gate_aborts_when_projection_exceeds_cap_and_tracks_skips(mod):
    # The pre-call check is against the FULL projected total (modeled spend so
    # far + modeled remainder), so a cap below the whole plan trips on the
    # FIRST precall — before any transport call — not after burning cap-many
    # credits one call at a time.
    gate = mod.SpendGate(cap=314, remaining_planned=315)
    with pytest.raises(mod.CreditCapError, match="315"):
        gate.precall(1, "discovery")
    ok = mod.SpendGate(cap=315, remaining_planned=315)
    ok.precall(1, "discovery")                  # == cap: proceeds (<= semantics)
    assert (ok.spent, ok.remaining) == (1, 314)
    # Skipped calls (event not found -> no snapshots) SHRINK the projection:
    # a run that skips work must not stay blocked on the original plan size.
    tight = mod.SpendGate(cap=20, remaining_planned=21)
    tight.skip(10)
    tight.precall(1, "discovery")
    assert tight.spent == 1


# --------------------------------------------------------------------------- #
# Dry-run end-to-end: the default, from mocks, zero credits.                    #
# --------------------------------------------------------------------------- #
def test_dry_run_is_the_default_and_writes_the_report_from_mocks(
        mod, tmp_path, capsys):
    rc = mod.main([])                            # no flags at all == dry-run
    assert rc == 0
    out = capsys.readouterr().out
    # The plan requires the dry-run to PRINT the full call plan + projection.
    assert "projected 315 credits" in out
    assert "45 calls" in out
    report = tmp_path / "reports" / "oa_probe.md"
    assert _files_under(tmp_path) == {"reports/oa_probe.md"}   # nothing else —
    # in particular no data/odds_raw: mock bytes must never be archived.
    md = report.read_text()
    assert "DRY-RUN" in md
    assert "NOT measurements" in md              # mock values can't masquerade
    assert "**315 credits**" in md
    # "modeled spend this run: 315" sits in a ZERO-credits report — a skim
    # reader at the spend gate must not read 315 as money spent.
    assert "(dry-run: 0 actually billed)" in md
    # Per-fixture rows: all 15, with the four required observables. Scoped to
    # the results section — the call-plan table also carries a pool column.
    results_section = md.split("## Per-fixture results")[1].split("Provenance")[0]
    for pool, n in (("wc2022", 5), ("euro2024", 5), ("wc2026", 5)):
        assert results_section.count(f"| {pool} |") == n
    assert "event found" in md and "Pinnacle" in md
    assert "drift" in md and "staleness" in md
    # The deterministic mock geometry: snapshots trail the requested ts by
    # 3 min; Pinnacle's strictest stamp (the h2h market's) is 5 min older
    # again -> staleness at T-1h = 8 min. Pins the drift/staleness arithmetic.
    assert md.count("3.0") >= 30
    assert md.count("8.0") >= 15
    # Extrapolated full-program budget with N_dev explicit.
    assert "217" in md and "N_dev" in md and "4340" in md


def test_dry_run_never_touches_the_env_api_key(mod, tmp_path, monkeypatch):
    # A dry-run must spend nothing even when a real key sits in the env: the
    # sentinel key goes on the wire (to the MOCK transport), and the real key
    # appears in neither the requests nor the committed report.
    monkeypatch.setenv("ODDS_API_KEY", "SECRET-env-key-777")
    requests: list[httpx.Request] = []
    real_factory = mod._dry_run_transport

    def capturing(sport_keys):
        inner = real_factory(sport_keys)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return inner.handler(request)

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_dry_run_transport", capturing)
    assert mod.main([]) == 0
    assert len(requests) == 45
    assert all(r.url.params["apiKey"] == mod._DRY_RUN_KEY for r in requests)
    assert all(r.url.params["apiKey"] != "SECRET-env-key-777" for r in requests)
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    assert "SECRET-env-key-777" not in md


def test_dry_run_snapshot_calls_use_config_sport_keys(mod, monkeypatch):
    # Config-driven keys are the point of OA F13: the probe VERIFIES the exact
    # strings in config odds.sport_keys, so its own calls must be built from
    # them — euro2024 traffic must hit the euros key, not a generic one.
    requests: list[httpx.Request] = []
    real_factory = mod._dry_run_transport

    def capturing(sport_keys):
        inner = real_factory(sport_keys)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return inner.handler(request)

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_dry_run_transport", capturing)
    assert mod.main([]) == 0
    euro = [r for r in requests
            if "soccer_uefa_european_championship" in r.url.path]
    assert len(euro) == 15                       # 5 fixtures x (1 disc + 2 snap)
    assert not any("/sports/soccer/" in r.url.path for r in requests)


# --------------------------------------------------------------------------- #
# The --live gates: BOTH requirements, or no start at all.                      #
# --------------------------------------------------------------------------- #
def _bomb(*args, **kwargs):
    raise AssertionError("run_probe must not be reached")


def test_live_without_max_credits_exits_nonzero_with_usage(
        mod, monkeypatch, capsys):
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-for-arg-test")
    monkeypatch.setattr(mod, "run_probe", _bomb)
    with pytest.raises(SystemExit) as err:
        mod.main(["--live"])
    assert err.value.code != 0
    assert "--max-credits" in capsys.readouterr().err


def test_live_without_env_key_exits_nonzero_naming_the_env_var(
        mod, monkeypatch, capsys):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    monkeypatch.setattr(mod, "run_probe", _bomb)
    with pytest.raises(SystemExit) as err:
        mod.main(["--live", "--max-credits", "400"])
    assert err.value.code != 0
    assert "ODDS_API_KEY" in capsys.readouterr().err


def test_live_and_dry_run_together_rejected(mod, monkeypatch, capsys):
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-for-arg-test")
    monkeypatch.setattr(mod, "run_probe", _bomb)
    with pytest.raises(SystemExit) as err:
        mod.main(["--live", "--dry-run", "--max-credits", "400"])
    assert err.value.code != 0
    assert "mutually exclusive" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The spend gate end-to-end: cap below projection => ZERO transport calls.      #
# --------------------------------------------------------------------------- #
def test_live_cap_below_projection_aborts_before_any_transport_call(
        mod, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-cap-test")
    requests: list[httpx.Request] = []

    def recording_transport():
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"timestamp": "t", "data": []})

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_live_transport", recording_transport)
    rc = mod.main(["--live", "--max-credits", "10"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "315" in err and "10" in err          # projection vs cap, plainly
    assert requests == []                        # aborted BEFORE the first call
    assert _files_under(tmp_path) == set()       # and no report written


def test_live_cap_at_projection_runs_via_mock_and_reports_usage_headers(
        mod, tmp_path, monkeypatch):
    # Boundary contrast for the abort above (cap == projection proceeds), and
    # the actual-usage readback: x-requests-used / x-requests-remaining from
    # every response land in the report. The transport is an injected mock —
    # zero network, zero credits — and the report must SAY so: a mocked
    # transport can never masquerade as real live measurements.
    monkeypatch.setenv("ODDS_API_KEY", "SECRET-live-key-999")
    requests: list[httpx.Request] = []
    used = iter(range(5001, 5001 + 45))

    def mock_live_transport():
        inner = mod._dry_run_transport(_SPORT_KEYS)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            resp = inner.handler(request)
            n = next(used)
            resp.headers["x-requests-used"] = str(n)
            resp.headers["x-requests-remaining"] = str(20000 - n)
            return resp

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_live_transport", mock_live_transport)
    rc = mod.main(["--live", "--max-credits", "315"])
    assert rc == 0
    assert len(requests) == 45
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    assert "MOCKED TRANSPORT" in md              # not real measurements
    assert "5001" in md and "5045" in md         # first and last used-readings
    assert "SECRET-live-key-999" not in md       # the key never enters the report
    # The dry-run billing clarifier is dry-run ONLY: on a real live run it
    # would falsely claim nothing was billed.
    assert "(dry-run: 0 actually billed)" not in md


def test_mocked_live_run_never_archives_into_the_real_raw_store(
        mod, tmp_path, monkeypatch):
    # T3's transport-aware raw_dir default keeps fabricated bytes out of
    # data/odds_raw — but the probe's live branch must pass an EXPLICIT
    # raw_dir (its usage-recording wrapper makes the transport non-None even
    # on real runs), which re-opens the hole for mocked --live tests: without
    # this guard, the two e2e tests above would archive 45 mock payloads into
    # the REAL paid-evidence store. Only a genuinely real transport may
    # resolve to the archive.
    archive = tmp_path / "odds_raw_guard"
    monkeypatch.setattr(mod, "ODDS_RAW_DIR", archive)
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-archive-guard")
    monkeypatch.setattr(
        mod, "_live_transport",
        lambda: mod._dry_run_transport(_SPORT_KEYS))
    assert mod.main(["--live", "--max-credits", "315"]) == 0
    assert not archive.exists()                  # mock bytes: never archived
    # The selection is a pure function of the transport, so the REAL branch
    # is provable without a network call: only the genuine network transport
    # archives — an ALLOWLIST, matching the adapter's _resolve_raw_dir
    # polarity (any injected transport -> no archive). A denylist on
    # MockTransport would wave every OTHER injected fake — a plain
    # BaseTransport subclass, the probe's own _UsageRecorder wrapper — into
    # the real paid-evidence store.
    assert mod._live_raw_dir(mod._dry_run_transport(_SPORT_KEYS)) is None

    class _FakeTransport(httpx.BaseTransport):
        def handle_request(self, request):
            raise AssertionError("never called")

    assert mod._live_raw_dir(_FakeTransport()) is None
    assert mod._live_raw_dir(
        mod._UsageRecorder(mod._dry_run_transport(_SPORT_KEYS))) is None
    real = httpx.HTTPTransport()                 # constructed, never used
    assert mod._live_raw_dir(real) == archive


def test_live_snapshot_failure_is_recorded_redacted_and_run_continues(
        mod, tmp_path, monkeypatch):
    # The probe is a COVERAGE instrument: a 429/401 on one fixture is a
    # finding, not a crash — the run continues, and the recorded failure text
    # rides the T3 redaction (no key, no query string) into the committed
    # report.
    monkeypatch.setenv("ODDS_API_KEY", "SECRET-live-key-429")
    poisoned = "mock_wc2022_2022-12-18"          # the wc2022 final's event id

    def mock_live_transport():
        inner = mod._dry_run_transport(_SPORT_KEYS)

        def handler(request: httpx.Request) -> httpx.Response:
            if poisoned in request.url.path:
                return httpx.Response(429, json={"message": "quota"})
            return inner.handler(request)

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_live_transport", mock_live_transport)
    rc = mod.main(["--live", "--max-credits", "315"])
    assert rc == 0
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    assert "429" in md
    assert "SECRET-live-key-429" not in md
    assert "apiKey" not in md                    # query string never survives
    # The other 14 fixtures were still probed (their rows carry mock drift).
    assert md.count("3.0") >= 28
    # The failure text must RIDE the table, not break it: httpx's 429 message
    # is TWO lines, and an unflattened cell splits the row exactly on the
    # 401/429 findings this report exists to surface. Pin: the results section
    # is nothing but table rows, all with the header's pipe count.
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    rows = [ln for ln in results.splitlines() if ln.strip()]
    assert len(rows) == 17                       # header + separator + 15 rows
    assert {ln.count("|") for ln in rows} == {rows[0].count("|")}
    assert all(ln.startswith("|") and ln.rstrip().endswith("|") for ln in rows)


# --------------------------------------------------------------------------- #
# The ACTUAL-usage cap: modeled prices are hypotheses under test; the billing  #
# headers are facts — the cap must bound the facts, not just the model.        #
# --------------------------------------------------------------------------- #
def test_live_actual_billing_above_cap_aborts_midrun_with_partial_report(
        mod, tmp_path, monkeypatch, capsys):
    # The SpendGate bounds the MODELED cost, but the per-call prices are the
    # very thing this probe exists to measure — when the server's own
    # x-requests-used counter shows billing above the model (here 10 credits
    # for EVERY call, discovery included), the run must stop near the cap
    # instead of placing all 45 calls (~450 credits against a 315 cap).
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-overbilled")
    requests: list[httpx.Request] = []
    used = iter(range(1010, 1010 + 45 * 10, 10))     # +10 per response

    def overbilling_transport():
        inner = mod._dry_run_transport(_SPORT_KEYS)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            resp = inner.handler(request)
            n = next(used)
            resp.headers["x-requests-used"] = str(n)
            resp.headers["x-requests-remaining"] = str(20000 - n)
            return resp

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_live_transport", overbilling_transport)
    rc = mod.main(["--live", "--max-credits", "315"])
    assert rc != 0
    # Refused BEFORE call 34: after 33 responses the used-delta is
    # 1330 - 1010 = 320 > 315 (the first call's own cost is invisible until
    # the counter moves), so exactly 33 of the 45 planned calls were placed.
    assert len(requests) == 33
    err = capsys.readouterr().err
    assert "ABORT" in err and "315" in err and "320" in err
    # Paid calls happened, so the PARTIAL report is still written — an abort
    # that discarded it would forfeit the fixtures already paid for (the T3
    # rule: a paid response is never lost, and the report is its deliverable).
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    assert "ABORT" in md and "320" in md
    assert "1330" in md                          # last billed counter reported


def test_actual_consumed_needs_two_parseable_counters(mod):
    # Headers are evidence, never assumed: absent/garbage x-requests-used
    # values mean the actual spend is UNKNOWN (None) — the modeled gate still
    # holds, but no phantom delta may abort a run (the mocked failure e2e
    # serves headerless responses and must keep running).
    rec = mod._UsageRecorder(mod._dry_run_transport(_SPORT_KEYS), cap=10)
    assert rec.actual_consumed() is None
    rec.usage.append({"path": "/a", "requests_used": None,
                      "requests_remaining": None})
    rec.usage.append({"path": "/b", "requests_used": "garbage",
                      "requests_remaining": "-"})
    assert rec.actual_consumed() is None
    rec.usage.append({"path": "/c", "requests_used": "100",
                      "requests_remaining": "900"})
    assert rec.actual_consumed() is None         # one parseable point: no delta
    rec.usage.append({"path": "/d", "requests_used": "130",
                      "requests_remaining": "870"})
    assert rec.actual_consumed() == 30


# --------------------------------------------------------------------------- #
# The coverage-MISS branch: the observable the probe exists for.               #
# --------------------------------------------------------------------------- #
def test_event_not_found_shrinks_projection_and_survives_hostile_names(
        mod, tmp_path, monkeypatch):
    # When discovery lists events but OURS is not among them, the row must
    # say n, suppress both snapshots (gate.skip shrinks the modeled spend to
    # 295), and quote what discovery DID list — team names straight off the
    # live wire, so a "Foo | Bar" (pipe) or an embedded newline must ride the
    # table cell exactly like an error message does (a680aca closed the error
    # branch; this pins the MISS branch).
    real_factory = mod._dry_run_transport
    poisoned_date = "2026-07-19"                 # the wc2026 final's discovery

    def missing_event(sport_keys):
        inner = real_factory(sport_keys)

        def handler(request: httpx.Request) -> httpx.Response:
            if (request.url.path.endswith("/events")
                    and request.url.params["date"].startswith(poisoned_date)):
                return httpx.Response(200, json={
                    "timestamp": request.url.params["date"],
                    "data": [
                        {"id": "someone_else",
                         "commence_time": f"{poisoned_date}T18:00:00Z",
                         "home_team": "Foo | Bar",
                         "away_team": "Baz\nQux"}]})
            return inner.handler(request)

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_dry_run_transport", missing_event)
    assert mod.main([]) == 0
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    # The gate.skip observable: 2 planned snapshots dropped from the model.
    assert "modeled spend this run: 295" in md
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    row = next(ln for ln in results.splitlines()
               if "Spain v Argentina" in ln)
    assert "| n | - | - | - | - | - |" in row    # found: n; snapshots suppressed
    assert "not among 1 listed events" in row
    assert "Foo \\| Bar v Baz Qux" in row        # escaped pipe, flattened \n
    # The hostile names must not have split the row: uniform DELIMITER count
    # (escaped pipes excluded) across the whole results table.
    rows = [ln for ln in results.splitlines() if ln.strip()]
    assert len(rows) == 17
    delims = {ln.count("|") - ln.count("\\|") for ln in rows}
    assert delims == {rows[0].count("|")}


# --------------------------------------------------------------------------- #
# Post-fetch shape surprises: findings, never crashes that discard the report. #
# --------------------------------------------------------------------------- #
def test_post_fetch_shape_surprises_are_findings_not_crashes(
        mod, tmp_path, monkeypatch):
    # Both repros from review: (a) a snapshot 200 with the documented
    # {timestamp, data} wrapper whose data is NOT an event dict (KeyError out
    # of parse_snapshot), and (b) a discovery 200 whose event lacks
    # commence_time (KeyError out of the adapter's comprehension). Each is a
    # paid response already archived — a per-call failure is "a FINDING for
    # the coverage report, not a crash", so neither may kill the run and
    # discard the report the other fixtures' calls paid for.
    real_factory = mod._dry_run_transport
    bad_snap_event = "mock_wc2022_2022-11-20"    # wc2022 opener's snapshots
    bad_disc_date = "2024-06-14"                 # euro2024 opener's discovery

    def shape_surprises(sport_keys):
        inner = real_factory(sport_keys)

        def handler(request: httpx.Request) -> httpx.Response:
            if bad_snap_event in request.url.path:
                return httpx.Response(200, json={
                    "timestamp": request.url.params["date"],
                    "data": {"unexpected": True}})
            if (request.url.path.endswith("/events")
                    and request.url.params["date"].startswith(bad_disc_date)):
                return httpx.Response(200, json={
                    "timestamp": request.url.params["date"],
                    "data": [{"id": "half-an-event"}]})
            return inner.handler(request)

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_dry_run_transport", shape_surprises)
    assert mod.main([]) == 0                     # findings, not a crash
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    snap_row = next(ln for ln in results.splitlines()
                    if "Qatar v Ecuador" in ln)
    disc_row = next(ln for ln in results.splitlines()
                    if "Germany v Scotland" in ln)
    assert "KeyError" in snap_row                # (a) recorded per-snapshot
    assert "KeyError" in disc_row                # (b) recorded per-fixture
    # The discovery failure drops its 2 planned snapshots from the model; the
    # snapshot failures were PLACED calls and still count as modeled spend.
    assert "modeled spend this run: 295" in md
    # The other 13 fixtures' drift values prove the run continued.
    assert md.count("3.0") >= 26
    rows = [ln for ln in results.splitlines() if ln.strip()]
    assert len(rows) == 17
    assert {ln.count("|") for ln in rows} == {rows[0].count("|")}


# --------------------------------------------------------------------------- #
# Cell hygiene + the orientation-flip match: small branches the committed      #
# report's integrity rides on.                                                 #
# --------------------------------------------------------------------------- #
def test_err_cell_flattens_whitespace_and_escapes_pipes(mod):
    # Both halves are load-bearing for table integrity: httpx's 429 message
    # spans two lines (whitespace), and a message carrying "|" would add a
    # phantom cell — either alone splits the committed report's results row.
    exc = ValueError("first line\nsecond | third")
    assert mod._err_cell(exc) == "ValueError: first line second \\| third"


def test_flipped_discovery_orientation_still_matches_and_is_reported(
        mod, tmp_path, monkeypatch):
    # Neutral-venue sources disagree on home/away orientation: a flipped
    # listing must still count as "event found" (a MISS here would report
    # missing coverage for an event the API does list, and skip both paid
    # snapshots) — but the flip itself is a finding the report must carry.
    real_factory = mod._dry_run_transport
    target = "mock_euro2024_2024-07-14"          # the euro2024 final's event

    def flipping(sport_keys):
        inner = real_factory(sport_keys)

        def handler(request: httpx.Request) -> httpx.Response:
            resp = inner.handler(request)
            if request.url.path.endswith("/events"):
                payload = json.loads(resp.content)
                for ev in payload["data"]:
                    if ev["id"] == target:
                        ev["home_team"], ev["away_team"] = (
                            ev["away_team"], ev["home_team"])
                return httpx.Response(200, json=payload)
            return resp

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_dry_run_transport", flipping)
    assert mod.main([]) == 0
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    row = next(ln for ln in results.splitlines() if "Spain v England" in ln)
    assert "| y |" in row                        # found DESPITE the flip
    assert "orientation flipped vs store" in row
    # All 30 snapshots still probed: the flip must not suppress the fixture.
    assert "modeled spend this run: 315" in md
