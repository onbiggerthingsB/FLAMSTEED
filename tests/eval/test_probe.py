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
from datetime import timedelta
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


def test_snapshot_price_is_derived_from_the_market_and_region_lists(mod):
    # VERIFIED MUTATION (review): widening REGIONS to "eu,us" against a FLAT
    # SNAPSHOT_CREDITS = 10 left this suite green and the projection at 315
    # while the true bill would be 615 — the gate would authorize about half
    # the real spend. The per-snapshot price must be DERIVED from the
    # requested market/region lists (10 credits per region-market), so any
    # widening reprices the projection and trips the 315 pin above: the
    # number the user approves moves VISIBLY or not at all.
    n = len(mod.MARKET.split(",")) * len(mod.REGIONS.split(","))
    assert mod.N_REGION_MARKETS == n == 1
    assert mod.SNAPSHOT_CREDITS == 10 * n


def test_full_program_budget_keeps_n_dev_an_explicit_input(mod):
    # (217 eval + N_dev) x 2 snapshots x 10 credits — 217 = the 185-pool plus
    # the 32 WC-2026 knockout fixtures. N_dev is the OA-0b sizing decision and
    # must stay a formula input, never a baked-in assumption.
    assert mod.full_program_budget(0) == 4340
    assert mod.full_program_budget(100) == 4340 + 100 * 2 * 10


def test_spend_gate_aborts_when_projection_exceeds_cap_at_the_start(mod):
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
    # precall keeps the projection (spent + remaining) CONSTANT, so the
    # modeled gate is a START gate: once the first precall passes, no later
    # one can newly trip — mid-run aborts belong to the ACTUAL-usage check.
    ok.precall(10, "snapshot")
    assert ok.spent + ok.remaining == 315
    # No skip/re-projection hook: one shipped, and because the projection is
    # monotonically non-increasing it could never affect any check — dead
    # logic that READ as a live safety mechanism, so it was removed rather
    # than left presenting a judgment that cannot occur.
    assert not hasattr(mod.SpendGate, "skip")


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


def test_snapshot_requests_buy_kickoff_minus_24h_and_minus_1h(
        mod, tmp_path, monkeypatch):
    # The probe's entire deliverable is a measurement of PRE-KICKOFF
    # coverage, and the mapping fixture -> discovered kickoff -> the two
    # requested instants was unpinned: the mock echoes whatever `date` it is
    # given, so buying `commence + delta` (30 paid calls on IN-PLAY prices)
    # or swapping the tag/offset pairing both left the suite green with a
    # byte-for-byte-convincing report. Pin BOTH sides against the mock's own
    # kickoff: the outgoing wire `date` params (in plan order — T-24h is
    # requested first) and the report's tag-labeled requested instants (a
    # swapped pairing would relabel the columns, not just reorder calls).
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
    for fx in mod.PROBE_FIXTURES:
        commence = mod._ts(mod._mock_commence(fx))
        snaps = [r for r in requests
                 if f"/events/{mod._event_id(fx)}/odds" in r.url.path]
        assert len(snaps) == 2, fx
        assert snaps[0].url.params["date"] == mod._iso(
            commence - timedelta(hours=24)), fx
        assert snaps[1].url.params["date"] == mod._iso(
            commence - timedelta(hours=1)), fx
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    assert ("| Qatar v Ecuador (2022-11-20) | 2022-11-20T18:00:00Z | "
            "2022-11-19T18:00:00Z | 2022-11-20T17:00:00Z |") in md


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
    # The deliverable must STATE actual-billed vs cap vs modeled — the reader
    # at the spend gate never hand-subtracts the usage table (5045-5001=44).
    assert "Actual billed this run: **44 credits**" in md
    assert "vs `--max-credits` 315; modeled spend 315 credits" in md


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
    # Call 33 was fixture 11's T-1h snapshot, and its RESPONSE was received:
    # the check that refused call 34 sits BEFORE the transport, never after —
    # a received response is already paid for and must always reach the
    # adapter (parse + provenance). Pin both observables: fixture 11 is fully
    # measured, and its T-1h hash reaches the Provenance section.
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    row11 = next(ln for ln in results.splitlines()
                 if "Mexico v South Africa" in ln)
    assert row11.count(" 3.0 ") == 2             # both drifts measured
    assert "not attempted" not in row11
    prov11 = next(ln for ln in md.splitlines()
                  if ln.startswith("- Mexico v South Africa"))
    assert "T-24h" in prov11 and "T-1h" in prov11
    # Fixture 12's discovery is the call OUR gate refused: the probe never
    # asked, so its row must say NOT ATTEMPTED — never "not among the listed
    # events" (with a literal None count), which claims a coverage miss that
    # was never measured.
    row12 = next(ln for ln in results.splitlines() if "Canada v Qatar" in ln)
    assert "not attempted" in row12
    assert "not among" not in row12
    assert "None" not in results
    # Fixtures 13-15 were never reached: they must not silently vanish from
    # the table (12 rows where 15 belong) — the full 15-fixture frame stays,
    # with the tail explicitly not-attempted, plus the banner's list.
    rows = [ln for ln in results.splitlines() if ln.strip()]
    assert len(rows) == 17                       # header + separator + 15 rows
    assert {ln.count("|") for ln in rows} == {rows[0].count("|")}
    for label in ("Colombia v Portugal", "Brazil v Japan",
                  "Spain v Argentina"):
        assert "not attempted" in next(
            ln for ln in results.splitlines() if label in ln)
    assert "Never attempted (4 of 15 fixtures" in md
    # The partial report also states actual-billed vs cap vs modeled — and
    # the refused discovery precall is REFUNDED from the modeled figure: 33
    # calls were placed (fixtures 1-11 complete), modeled 11x21 = 231, so a
    # spent of 232 would count the very call the usage gate refused.
    assert "Actual billed this run: **320 credits**" in md
    assert "modeled spend this run: 231" in md
    assert "modeled spend 231 credits" in md


def test_midrun_abort_landing_on_a_snapshot_call_is_an_abort_not_a_note(
        mod, tmp_path, monkeypatch, capsys):
    # Overbill at 12 credits per response against a 315 cap: the delta first
    # breaches before call 29 (12 x 27 = 324 > 315) — fixture 10's T-24h
    # SNAPSHOT, not a discovery. The cap refusal must propagate as an ABORT
    # from the snapshot site too (_probe_snapshot's CreditCapError re-raise):
    # swallowed into the per-snapshot note instead, our own gate's refusal
    # would be reported as an Odds-API coverage failure ("ERR" cells with
    # CreditCapError notes) on the single observable the purchase decision
    # turns on.
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-overbilled-12")
    requests: list[httpx.Request] = []
    used = iter(range(1012, 1012 + 45 * 12, 12))     # +12 per response

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
    assert len(requests) == 28                   # fixtures 1-9 + one discovery
    err = capsys.readouterr().err
    assert "ABORT" in err and "324" in err
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    # The abort banner names the SNAPSHOT endpoint the gate refused — the
    # euro2024 final's odds route, not some later discovery.
    assert "RUN ABORTED MID-FLIGHT" in md
    assert "mock_euro2024_2024-07-14/odds" in md
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    # Fixture 10's discovery was measured (y) but BOTH snapshots were refused
    # by our own gate: ALL FIVE snapshot-derived cells must say "not
    # attempted" — the abort landed on the T-24h call, and an entry pre-seeded
    # only per-iteration would leave the three T-1h cells rendering the "-"
    # of a measured miss (on the closing-line proxy itself) with no textual
    # disambiguation anywhere in the row. Rendered "ERR" they would
    # masquerade as an API failure. Exact full row, all cells + per-tag notes.
    row10 = next(ln for ln in results.splitlines()
                 if "Spain v England" in ln)
    assert row10 == (
        "| euro2024 | final | Spain v England (2024-07-14) | y "
        "| not attempted | not attempted | not attempted | not attempted "
        "| not attempted | snapshot T-24h not attempted (run aborted); "
        "snapshot T-1h not attempted (run aborted) |")
    # Our own gate's refusal never appears as a per-fixture finding.
    assert "CreditCapError" not in results
    # The refused T-24h precall is REFUNDED: 28 calls were placed (fixtures
    # 1-9 complete + fixture 10's discovery), modeled 9x21 + 1 = 190 — a
    # spent figure of 200 would overstate the modeled side of the
    # actual-vs-modeled comparison by the refused call's price.
    assert "modeled spend this run: 190" in md
    assert "modeled spend 190 credits" in md
    # The unreached tail (fixtures 11-15) stays in the frame, marked.
    rows = [ln for ln in results.splitlines() if ln.strip()]
    assert len(rows) == 17
    assert {ln.count("|") for ln in rows} == {rows[0].count("|")}
    assert "Never attempted (5 of 15 fixtures" in md


def test_completed_run_billed_over_cap_is_flagged_and_exits_nonzero(
        mod, tmp_path, monkeypatch, capsys):
    # The pre-call checks can only refuse the NEXT call: when the breach is
    # first revealed by the FINAL response (last call bills 500 against a
    # trickle of 1s), there is no next call — without a post-loop comparison
    # the run ends far over --max-credits with exit code 0 and no flag
    # anywhere, and the reader must hand-subtract the usage table.
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-final-call-bomb")
    requests: list[httpx.Request] = []
    used = iter([1000 + n for n in range(1, 45)] + [1544])   # last: +500

    def final_bomb_transport():
        inner = mod._dry_run_transport(_SPORT_KEYS)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            resp = inner.handler(request)
            n = next(used)
            resp.headers["x-requests-used"] = str(n)
            resp.headers["x-requests-remaining"] = str(20000 - n)
            return resp

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_live_transport", final_bomb_transport)
    rc = mod.main(["--live", "--max-credits", "315"])
    assert len(requests) == 45                   # nothing left to refuse
    assert rc != 0                               # but the run still FAILS
    err = capsys.readouterr().err
    assert "OVER CAP" in err and "543" in err
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    # Not an abort (all calls placed, all results measured) — an explicit
    # over-cap statement with the actual-vs-cap-vs-modeled figures.
    assert "RUN ABORTED" not in md
    assert "ACTUAL BILLING EXCEEDED THE CAP" in md
    assert "Actual billed this run: **543 credits**" in md
    assert "vs `--max-credits` 315; modeled spend 315 credits" in md


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
    # The suppressed-precalls observable: the 2 planned snapshots are never
    # precalled, so the modeled spend never counts them (295, not 315).
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
    # Provenance survives the parse failure: the hash is recorded BEFORE
    # parse_snapshot, so both failed snapshots' archived-bytes hashes still
    # reach the Provenance section — those bytes are already paid for, and
    # the hash is what a coverage dispute gets audited from.
    prov = next(ln for ln in md.splitlines()
                if ln.startswith("- Qatar v Ecuador"))
    assert "T-24h" in prov and "T-1h" in prov
    # The discovery failure drops its 2 planned snapshots from the model; the
    # snapshot failures were PLACED calls and still count as modeled spend.
    assert "modeled spend this run: 295" in md
    # The other 13 fixtures' drift values prove the run continued.
    assert md.count("3.0") >= 26
    rows = [ln for ln in results.splitlines() if ln.strip()]
    assert len(rows) == 17
    assert {ln.count("|") for ln in rows} == {rows[0].count("|")}


def test_at_or_after_kickoff_snapshot_is_flagged_in_play_never_a_clean_y(
        mod, tmp_path, monkeypatch):
    # Review repro: the server answers the wc2022 final's T-1h request with a
    # snapshot stamped 30 minutes INTO the match (bookmaker/market stamps at
    # 18:29Z against an 18:00Z kickoff). Without a strict pre-kickoff guard
    # the row read "Pinnacle T-1h: y" with empty notes — a false positive on
    # exactly the claim the 4,340-credit purchase rests on — and the only
    # signal was a negative number in a column whose sign convention the
    # report never defined. The codebase rule (admissible_quote, OA F2): an
    # at/after-kickoff stamp on EITHER leg is an in-play price, never a
    # closing quote — so the row must carry an IN-PLAY finding naming both
    # offending stamps and the kickoff.
    real_factory = mod._dry_run_transport
    target = "mock_wc2022_2022-12-18"            # the wc2022 final's event id

    def in_play(sport_keys):
        inner = real_factory(sport_keys)

        def handler(request: httpx.Request) -> httpx.Response:
            resp = inner.handler(request)
            if (f"{target}/odds" in request.url.path
                    and request.url.params["date"] == "2022-12-18T17:00:00Z"):
                payload = json.loads(resp.content)
                payload["timestamp"] = "2022-12-18T18:30:00Z"
                for bk in payload["data"]["bookmakers"]:
                    bk["last_update"] = "2022-12-18T18:29:00Z"
                    for mkt in bk["markets"]:
                        mkt["last_update"] = "2022-12-18T18:29:00Z"
                return httpx.Response(200, json=payload)
            return resp

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_dry_run_transport", in_play)
    assert mod.main([]) == 0                     # a finding, not a crash
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    row = next(ln for ln in results.splitlines()
               if "Argentina v France" in ln)
    assert "IN-PLAY T-1h" in row
    assert "snapshot ts 2022-12-18T18:30:00Z" in row
    assert "last_update 2022-12-18T18:29:00Z" in row
    assert "kickoff 2022-12-18T18:00:00Z" in row
    assert row.count("IN-PLAY") == 1             # the clean T-24h leg is not
    assert "-90.0" in row and "-89.0" in row     # negative drift + staleness
    # The reader can reconstruct the check by hand: the report prints the
    # discovered kickoff and BOTH requested instants per fixture, and defines
    # the drift sign convention it prints numbers under.
    assert ("| Argentina v France (2022-12-18) | 2022-12-18T18:00:00Z | "
            "2022-12-17T18:00:00Z | 2022-12-18T17:00:00Z |") in md
    assert "drift = requested - snapshot ts" in md
    # The finding rides the table without splitting it.
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


def test_naive_wire_timestamps_are_refused_never_localized(
        mod, tmp_path, monkeypatch):
    # astimezone() on a NAIVE datetime silently reinterprets it as MACHINE-
    # LOCAL time: a commence_time off the wire lacking a UTC designator would
    # shift both PAID snapshot requests by the host's UTC offset (10 credits
    # each on the wrong instants, report varying by machine timezone). _ts
    # must refuse the naive parse instead of letting astimezone guess.
    with pytest.raises(ValueError, match="naive"):
        mod._ts("2022-11-20T18:00:00")
    assert mod._ts("2022-11-20T18:00:00Z").tzinfo is not None
    assert mod._ts("2022-11-20T18:00:00+00:00").tzinfo is not None
    # End to end: a discovery whose commence_time is naive becomes a per-
    # fixture FINDING and suppresses both snapshot calls — no credits are
    # ever spent on timestamps we could not pin to UTC.
    requests: list[httpx.Request] = []
    real_factory = mod._dry_run_transport
    poisoned_date = "2022-11-20"                 # the wc2022 opener

    def naive_commence(sport_keys):
        inner = real_factory(sport_keys)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if (request.url.path.endswith("/events")
                    and request.url.params["date"].startswith(poisoned_date)):
                return httpx.Response(200, json={
                    "timestamp": request.url.params["date"],
                    "data": [
                        {"id": "mock_wc2022_2022-11-20",
                         "commence_time": f"{poisoned_date}T18:00:00",
                         "home_team": "Qatar", "away_team": "Ecuador"}]})
            return inner.handler(request)

        return httpx.MockTransport(handler)

    monkeypatch.setattr(mod, "_dry_run_transport", naive_commence)
    assert mod.main([]) == 0                     # a finding, not a crash
    assert not any("mock_wc2022_2022-11-20/odds" in r.url.path
                   for r in requests)            # no snapshot ever requested
    md = (tmp_path / "reports" / "oa_probe.md").read_text()
    assert "modeled spend this run: 295" in md   # 2 snapshots never precalled
    results = md.split("## Per-fixture results")[1].split("Provenance")[0]
    row = next(ln for ln in results.splitlines() if "Qatar v Ecuador" in ln)
    assert "ValueError" in row and "naive" in row
    assert "2022-11-20T18:00:00" in row          # the offending value, named


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
