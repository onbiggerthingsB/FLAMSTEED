"""The journaled acquisition runner (OA Plan 2 v2, V1).

``scripts/oa_acquire.py`` is the second — and much larger — code path that can
spend Odds-API credits, so the gates are pinned harder than the happy path:

* the intent/receipt journal is append-only and fsync'd, and a bare INTENT
  (a call that may or may not have billed) FAILS CLOSED on resume;
* ``--max-credits`` caps the GATE across resumed invocations, not one
  invocation — the cumulative spend is restored from the journal's receipts;
* a concurrent runner refuses (exclusive ``flock`` on a journal sidecar);
* the T_issue-cut snapshot is REQUESTED at 08:29:00Z and a returned stamp of
  exactly 08:30:00Z is INADMISSIBLE (strict ``<``, OA F2);
* every request instant derives from the config's venue-LOCAL matchday, never
  from ``commence_time.date()`` (the South Korea UTC-rollover case);
* discovery is keyed by ``(sport_key, requested_instant)`` — shared within a
  key, isolated across keys;
* four crash points (after wire / archive / receipt / ingest) never
  double-bill and never lose provenance.

NO test here touches the network: every request goes through an
``httpx.MockTransport``, behind the conftest ``no_live_network`` autouse guard
(env key cleared, the genuine transport's entrypoint replaced with a
BaseException sentinel). The real ``--live`` run is the USER's decision at the
G-A / G-B spend gates and is never executed by tests or agents.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``).
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _ROOT / "scripts" / "oa_acquire.py"

_SPORT_KEYS = {
    "wc2022": "soccer_fifa_world_cup",
    "euro2024": "soccer_uefa_european_championship",
    "wc2026": "soccer_fifa_world_cup",
}


def _load():
    spec = importlib.util.spec_from_file_location("oa_acquire", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(tmp_path, monkeypatch, isolated_odds_raw_dir):
    # Load from an unrelated cwd: the journal/report defaults are cwd-relative,
    # so any module-level file access surfaces here instead of touching the
    # repo's real (gitignored) acquisition journal.
    monkeypatch.chdir(tmp_path)
    return _load()


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fx(fixture_id, pool, date, home, away, kickoff_utc):
    return {"fixture_id": fixture_id, "pool": pool, "date": date,
            "home": home, "away": away, "kickoff_utc": kickoff_utc}


#: The plan's own worked example of the venue-local/UTC split: South Korea v
#: Czech Republic is a Mexico City 20:00 UTC-6 kickoff on venue-local matchday
#: 2026-06-11, so ``commence_time`` lands on 2026-06-12 (verbatim from the
#: committed config/tournament_2026.yaml).
_KOREA = _fx("wc2026-2026-06-11-kor-cze", "wc2026", "2026-06-11",
             "South Korea", "Czech Republic", "2026-06-12T02:00:00Z")


def _ev(fixture_id: str) -> str:
    return f"ev_{fixture_id}"


class _Api:
    """Recorded-shape mock: discovery by ``(sport_key, date)``, snapshots by
    event id. Records every request (path + the ``date`` param) so a test can
    prove WHICH instants were bought, and serves the billing headers the
    cumulative cap is enforced against."""

    def __init__(self, fixtures, sport_keys=None, *, snap_ts=None,
                 used_start=5000):
        self.fixtures = list(fixtures)
        self.sport_keys = dict(sport_keys or _SPORT_KEYS)
        self.requests: list[tuple[str, str]] = []
        self.used = used_start
        self._snap_ts = snap_ts or (lambda r: r - timedelta(minutes=1))
        self.by_event = {_ev(f["fixture_id"]): f for f in self.fixtures}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    @property
    def dates(self) -> list[str]:
        return [date for _path, date in self.requests]

    def _respond(self, payload, price):
        self.used += price
        return httpx.Response(200, json=payload, headers={
            "x-requests-last": str(price),
            "x-requests-used": str(self.used),
            "x-requests-remaining": str(20000 - self.used)})

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        date = request.url.params["date"]
        self.requests.append((path, date))
        parts = path.split("/")
        if path.endswith("/events"):
            key = parts[4]
            rows = [f for f in self.fixtures
                    if self.sport_keys[f["pool"]] == key
                    and f"{f['date']}T00:00:00Z" == date]
            data = [{"id": _ev(f["fixture_id"]), "sport_key": key,
                     "commence_time": f["kickoff_utc"],
                     "home_team": f["home"], "away_team": f["away"]}
                    for f in rows]
            return self._respond(
                {"timestamp": date, "previous_timestamp": date,
                 "next_timestamp": date, "data": data}, 1)
        fixture = self.by_event[parts[6]]
        stamp = self._snap_ts(_ts(date))
        older = _iso(stamp - timedelta(minutes=5))
        outcomes = [{"name": fixture["home"], "price": 2.10},
                    {"name": "Draw", "price": 3.30},
                    {"name": fixture["away"], "price": 3.60}]
        return self._respond({
            "timestamp": _iso(stamp), "previous_timestamp": _iso(stamp),
            "next_timestamp": _iso(stamp),
            "data": {"id": parts[6],
                     "sport_key": self.sport_keys[fixture["pool"]],
                     "commence_time": fixture["kickoff_utc"],
                     "home_team": fixture["home"],
                     "away_team": fixture["away"],
                     "bookmakers": [
                         {"key": "pinnacle", "last_update": older,
                          "markets": [{"key": "h2h", "last_update": older,
                                       "outcomes": outcomes}]}]}}, 10)


def _run(mod, fixtures, *, gate_id="ga", api=None, journal, raw_dir,
         max_credits=None, store_root=None, transport=None):
    api = api if api is not None else _Api(fixtures)
    return mod.run_acquisition(
        gate_id=gate_id, fixtures=fixtures, sport_keys=_SPORT_KEYS,
        api_key="test-key", transport=transport or api.transport(),
        max_credits=max_credits, raw_dir=raw_dir, journal_path=journal,
        store_root=store_root, aliases={})


# --------------------------------------------------------------------------- #
# Import safety + the frozen call plan's mechanical projection.                 #
# --------------------------------------------------------------------------- #
def test_import_places_no_call_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = {p for p in tmp_path.rglob("*")}
    mod = _load()
    assert callable(mod.run_acquisition)
    assert {p for p in tmp_path.rglob("*")} == before


def test_frozen_eval_projection_is_77_discovery_plus_434_snapshots(mod):
    # The plan's spend model (finding 8), which G-A's 4,800 cap is set
    # against: 217 fixtures x 2 snapshots x 10cr + 77 discovery calls.
    assert mod.EVAL_FIXTURES == 217
    assert mod.EVAL_DISCOVERY_DAYS == {"wc2022": 22, "euro2024": 21,
                                       "wc2026": 34}
    assert sum(mod.EVAL_DISCOVERY_DAYS.values()) == 77
    assert mod.projected_eval_credits() == 4417


def test_mechanical_projection_reproduces_the_frozen_eval_number(mod):
    # The projection the runner enforces is built by the SAME code that builds
    # the calls — never hand-estimated. An inventory with the frozen plan's
    # shape (217 fixtures over 22 + 21 + 34 distinct (sport_key, matchday)
    # keys) must price at exactly the frozen 4,417.
    days = []
    for pool, start, n in (("wc2022", "2022-11-20", 22),
                           ("euro2024", "2024-06-14", 21),
                           ("wc2026", "2026-06-11", 34)):
        base = datetime.fromisoformat(start).date()
        days += [(pool, (base + timedelta(days=i)).isoformat())
                 for i in range(n)]
    assert len(days) == 77
    fixtures = []
    for i in range(mod.EVAL_FIXTURES):
        pool, date = days[i % len(days)]
        fixtures.append(_fx(f"f{i}", pool, date, f"H{i}", f"A{i}",
                            f"{date}T18:00:00Z"))
    rows = mod.plan_rows(mod.build_plan(fixtures, _SPORT_KEYS, "ga"))
    assert sum(1 for r in rows if r["kind"] == "discovery") == 77
    assert sum(1 for r in rows if r["kind"] == "snapshot") == 434
    assert mod.project_credits(rows) == mod.projected_eval_credits() == 4417


# --------------------------------------------------------------------------- #
# Boundary correctness (finding 7).                                             #
# --------------------------------------------------------------------------- #
def test_cut_request_is_0829_one_minute_before_the_strict_0830_cut(mod):
    from wcmodel.eval.ledger import T_ISSUE_UTC_TIME

    assert T_ISSUE_UTC_TIME == (9, 0, 0, 0)          # the prereg estimand
    assert mod.CUT_BUFFER_MINUTES == 30
    assert mod.t_issue_for("2026-06-11") == _ts("2026-06-11T09:00:00Z")
    assert mod.cut_instant("2026-06-11") == _ts("2026-06-11T08:30:00Z")
    # STRICT <: a stamp AT the cut is inadmissible, so the paid request must
    # sit strictly before it — 08:29:00Z, not 08:30:00Z.
    assert mod.cut_request_instant("2026-06-11") == _ts("2026-06-11T08:29:00Z")
    assert mod.cut_request_instant("2026-06-11") < mod.cut_instant("2026-06-11")


def test_snapshot_returned_exactly_at_0830_is_inadmissible(mod, tmp_path):
    # The equality boundary the 08:29 request exists to avoid: a snapshot
    # whose own timestamp is EXACTLY the 08:30 cut fails `snapshot_ts < cut`
    # and must never be counted as an admissible T_issue quote.
    fixtures = [_fx("f1", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]

    def at_the_cut(requested):
        # 08:29 request -> a returned stamp of exactly 08:30:00Z.
        if (requested.hour, requested.minute) == (8, 29):
            return requested + timedelta(minutes=1)
        return requested - timedelta(minutes=1)

    out = _run(mod, fixtures, api=_Api(fixtures, snap_ts=at_the_cut),
               journal=tmp_path / "j.jsonl", raw_dir=tmp_path / "raw")
    cut = out["results"][0]["snapshots"]["cut"]
    assert cut["snapshot_ts"] == "2026-06-20T08:30:00Z"
    assert cut["requested_instant"] == "2026-06-20T08:29:00Z"
    assert cut["admissible"] is False
    assert out["results"][0]["eligible"] is False

    # Contrast: the ordinary (one-minute-stale) snapshot IS admissible.
    ok = _run(mod, fixtures, journal=tmp_path / "j2.jsonl",
              raw_dir=tmp_path / "raw2")
    assert ok["results"][0]["snapshots"]["cut"]["snapshot_ts"] == \
        "2026-06-20T08:28:00Z"
    assert ok["results"][0]["snapshots"]["cut"]["admissible"] is True
    assert ok["results"][0]["eligible"] is True


def test_requests_derive_from_venue_local_matchday_not_commence_date(
        mod, tmp_path):
    # South Korea v Czech Republic: venue-local matchday 2026-06-11, kickoff
    # 2026-06-12T02:00:00Z. Deriving the requests from commence_time.date()
    # would buy the 08:29 snapshot on 2026-06-12 — six and a half hours AFTER
    # kickoff (an in-play price) — and discover the wrong day.
    api = _Api([_KOREA])
    out = _run(mod, [_KOREA], api=api, journal=tmp_path / "j.jsonl",
               raw_dir=tmp_path / "raw")
    assert out["results"][0]["snapshots"]["cut"]["requested_instant"] == \
        "2026-06-11T08:29:00Z"
    assert out["results"][0]["snapshots"]["T-24h"]["requested_instant"] == \
        "2026-06-11T02:00:00Z"
    # Nothing on the wire may carry the UTC-rolled calendar day.
    assert api.dates == ["2026-06-11T00:00:00Z", "2026-06-11T02:00:00Z",
                         "2026-06-11T08:29:00Z"]
    assert not any(d.startswith("2026-06-12") for d in api.dates)


def test_fixture_whose_cut_request_is_not_pre_kickoff_is_refused(mod):
    # A morning kickoff on its own venue-local matchday: t_issue (09:00Z) is
    # already in play, so there is no admissible cut quote to buy. Refuse at
    # plan time rather than spend 10 credits on an in-play price.
    early = _fx("f-early", "wc2026", "2026-06-20", "A", "B",
                "2026-06-20T08:00:00Z")
    with pytest.raises(mod.FixtureManifestError, match="kickoff"):
        mod.build_plan([early], _SPORT_KEYS, "ga")


# --------------------------------------------------------------------------- #
# Discovery keying (finding 8).                                                 #
# --------------------------------------------------------------------------- #
def test_discovery_is_shared_within_one_sport_key_and_matchday(mod, tmp_path):
    fixtures = [
        _fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
            "2026-06-20T19:00:00Z"),
        _fx("b", "wc2026", "2026-06-20", "Spain", "Peru",
            "2026-06-20T22:00:00Z"),
    ]
    api = _Api(fixtures)
    out = _run(mod, fixtures, api=api, journal=tmp_path / "j.jsonl",
               raw_dir=tmp_path / "raw")
    discovery = [p for p, _d in api.requests if p.endswith("/events")]
    assert len(discovery) == 1                       # ONE call, two fixtures
    assert out["projected"] == 1 + 2 * 2 * 10
    assert all(r["event_found"] for r in out["results"])


def test_discovery_is_isolated_across_sport_keys_on_the_same_day(
        mod, tmp_path):
    # Same calendar day, two competitions: the listings are different
    # resources, so keying discovery on the DATE alone would buy one call and
    # then look for euro2024's fixture in the World Cup listing.
    fixtures = [
        _fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
            "2026-06-20T19:00:00Z"),
        _fx("b", "euro2024", "2026-06-20", "Spain", "England",
            "2026-06-20T22:00:00Z"),
    ]
    api = _Api(fixtures)
    out = _run(mod, fixtures, api=api, journal=tmp_path / "j.jsonl",
               raw_dir=tmp_path / "raw")
    discovery = [p for p, _d in api.requests if p.endswith("/events")]
    assert len(discovery) == 2
    assert {p.split("/")[4] for p in discovery} == {
        "soccer_fifa_world_cup", "soccer_uefa_european_championship"}
    assert out["projected"] == 2 + 2 * 2 * 10
    assert all(r["event_found"] for r in out["results"])


# --------------------------------------------------------------------------- #
# The journal: intent -> receipt, append-only, fsync'd.                          #
# --------------------------------------------------------------------------- #
def test_journal_writes_intent_then_receipt_per_call_and_fsyncs(
        mod, tmp_path, monkeypatch):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    journal = tmp_path / "j.jsonl"
    synced: list[int] = []
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync",
                        lambda fd: (synced.append(fd), real_fsync(fd))[1])
    _run(mod, fixtures, journal=journal, raw_dir=tmp_path / "raw")
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [r["type"] for r in records] == [
        "intent", "receipt", "intent", "receipt", "intent", "receipt"]
    assert {r["gate"] for r in records} == {"ga"}
    intents = [r for r in records if r["type"] == "intent"]
    receipts = [r for r in records if r["type"] == "receipt"]
    assert [r["call_id"] for r in intents] == [r["call_id"] for r in receipts]
    assert [r["modeled_credits"] for r in intents] == [1, 10, 10]
    assert [r["billed_credits"] for r in receipts] == [1, 10, 10]
    # Provenance + the requested/returned instant split.
    assert all(len(r["raw_sha256"]) == 64 for r in receipts)
    assert receipts[0]["requests_used"] == "5001"
    snap = [r for r in receipts if r["kind"] == "snapshot"]
    assert {r["requested_instant"] for r in snap} == {
        "2026-06-19T19:00:00Z", "2026-06-20T08:29:00Z"}
    assert {r["returned_instant"] for r in snap} == {
        "2026-06-19T18:59:00Z", "2026-06-20T08:28:00Z"}
    assert len(synced) >= len(records)               # every record fsync'd


def test_journal_is_append_only_across_invocations(mod, tmp_path):
    first = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                 "2026-06-20T19:00:00Z")]
    second = first + [_fx("b", "wc2026", "2026-06-21", "Spain", "Peru",
                          "2026-06-21T19:00:00Z")]
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    _run(mod, first, journal=journal, raw_dir=raw)
    head = journal.read_text()
    _run(mod, second, api=_Api(second), journal=journal, raw_dir=raw)
    assert journal.read_text().startswith(head)      # nothing rewritten


def test_resume_refuses_when_an_intent_has_no_receipt(mod, tmp_path):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    journal = tmp_path / "j.jsonl"
    journal.write_text(json.dumps({
        "type": "intent", "gate": "ga", "call_id": "ga|discovery|x|y|-|-",
        "kind": "discovery", "modeled_credits": 1}) + "\n")
    api = _Api(fixtures)
    with pytest.raises(mod.OrphanIntentError, match="data/odds_raw"):
        _run(mod, fixtures, api=api, journal=journal, raw_dir=tmp_path / "raw")
    assert api.requests == []                        # fail CLOSED: no call


def test_a_receipted_intent_does_not_block_resume(mod, tmp_path):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    _run(mod, fixtures, journal=journal, raw_dir=raw)
    assert mod.orphan_intents(mod.read_journal(journal)) == []
    _run(mod, fixtures, api=_Api(fixtures), journal=journal, raw_dir=raw)


# --------------------------------------------------------------------------- #
# Cumulative per-gate caps (finding 4).                                         #
# --------------------------------------------------------------------------- #
def test_gate_spend_sums_receipts_and_pending_intents(mod, tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text("\n".join(json.dumps(r) for r in [
        {"type": "intent", "gate": "ga", "call_id": "a", "kind": "snapshot",
         "modeled_credits": 10},
        {"type": "receipt", "gate": "ga", "call_id": "a", "kind": "snapshot",
         "billed_credits": 10, "raw_sha256": "0" * 64},
        {"type": "intent", "gate": "ga", "call_id": "b", "kind": "snapshot",
         "modeled_credits": 10},
        {"type": "intent", "gate": "gb", "call_id": "c", "kind": "discovery",
         "modeled_credits": 1},
        {"type": "receipt", "gate": "gb", "call_id": "c", "kind": "discovery",
         "billed_credits": 1, "raw_sha256": "1" * 64},
    ]) + "\n")
    records = mod.read_journal(journal)
    assert mod.gate_spend(records, "ga") == 20       # 10 billed + 10 pending
    assert mod.gate_spend(records, "gb") == 1


def test_max_credits_caps_the_gate_across_invocations(mod, tmp_path):
    first = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                 "2026-06-20T19:00:00Z")]
    second = first + [_fx("b", "wc2026", "2026-06-21", "Spain", "Peru",
                          "2026-06-21T19:00:00Z")]
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    out = _run(mod, first, journal=journal, raw_dir=raw, max_credits=21)
    assert out["spent"] == 21 and out["prior_spent"] == 0

    # Second invocation, SAME gate: 21 credits are already spent, so a fresh
    # 21-credit budget must NOT be granted — the cap is the gate total.
    api = _Api(second)
    with pytest.raises(mod.CreditCapError, match="42"):
        _run(mod, second, api=api, journal=journal, raw_dir=raw,
             max_credits=21)
    assert api.requests == []                        # refused before the wire

    # Raise the GATE cap to the full plan and the resumed run proceeds,
    # placing ONLY the outstanding calls.
    api = _Api(second)
    out = _run(mod, second, api=api, journal=journal, raw_dir=raw,
               max_credits=42)
    assert out["prior_spent"] == 21 and out["spent"] == 42
    assert len(api.requests) == 3                    # the second fixture only


def test_gate_ids_isolate_cumulative_spend(mod, tmp_path):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    _run(mod, fixtures, gate_id="ga", journal=journal, raw_dir=raw,
         max_credits=21)
    records = mod.read_journal(journal)
    assert mod.gate_spend(records, "ga") == 21
    assert mod.gate_spend(records, "gb") == 0
    # G-B's own budget is untouched by G-A's spend (a dev-slate fixture on a
    # different day, so its calls are distinct).
    dev = [_fx("d", "wc2026", "2025-03-25", "Brazil", "Chile",
               "2025-03-25T19:00:00Z")]
    out = _run(mod, dev, gate_id="gb", api=_Api(dev), journal=journal,
               raw_dir=raw, max_credits=21)
    assert out["prior_spent"] == 0 and out["spent"] == 21
    assert {r["gate"] for r in mod.read_journal(journal)} == {"ga", "gb"}


def test_cap_below_the_projection_aborts_before_the_first_call(mod, tmp_path):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    api = _Api(fixtures)
    with pytest.raises(mod.CreditCapError):
        _run(mod, fixtures, api=api, journal=tmp_path / "j.jsonl",
             raw_dir=tmp_path / "raw", max_credits=20)
    assert api.requests == []
    assert not (tmp_path / "j.jsonl").exists()       # no intent either


# --------------------------------------------------------------------------- #
# Concurrency.                                                                  #
# --------------------------------------------------------------------------- #
def test_a_concurrent_runner_refuses(mod, tmp_path):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    journal = tmp_path / "j.jsonl"
    lock = mod.journal_lock_path(journal)
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        api = _Api(fixtures)
        with pytest.raises(mod.ConcurrentAcquisitionError):
            _run(mod, fixtures, api=api, journal=journal,
                 raw_dir=tmp_path / "raw")
        assert api.requests == []
    finally:
        os.close(fd)
    # Released: the runner proceeds.
    _run(mod, fixtures, journal=journal, raw_dir=tmp_path / "raw")


# --------------------------------------------------------------------------- #
# Atomic store rebuild from receipts.                                           #
# --------------------------------------------------------------------------- #
def test_store_is_rebuilt_atomically_from_the_receipts(mod, tmp_path):
    import pandas as pd

    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    store = tmp_path / "store"
    store.mkdir()
    # A torn leftover from an interrupted earlier rebuild must be REPLACED,
    # never appended to.
    (store / "odds.parquet").write_bytes(b"torn-not-a-parquet")
    out = _run(mod, fixtures, journal=journal, raw_dir=raw, store_root=store)
    assert out["store_rows"] == 6                    # 2 snapshots x 3 outcomes
    df = pd.read_parquet(store / "odds.parquet")
    assert set(df["event_id"]) == {_ev("a")}
    assert set(df["bookmaker"]) == {"pinnacle"}
    assert sorted(df["snapshot_ts"].unique()) == [
        "2026-06-19T18:59:00Z", "2026-06-20T08:28:00Z"]
    assert not list(store.parent.glob(".*rebuild*"))  # tmp cleaned up


# --------------------------------------------------------------------------- #
# The four crash points.                                                        #
# --------------------------------------------------------------------------- #
def _one_fixture():
    return [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                "2026-06-20T19:00:00Z")]


def test_crash_after_wire_before_archive_fails_closed_on_resume(
        mod, tmp_path, monkeypatch):
    # The response arrived (credits moved) but its bytes never reached the
    # archive: the intent is bare, so the rerun REFUSES rather than re-buying
    # a call that may already have billed.
    from wcmodel.data.sources import odds as adapter

    fixtures = _one_fixture()
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    real_persist = adapter._persist_raw
    first = {"run": True}

    def explode(content, raw_dir):
        if first["run"]:
            first["run"] = False
            raise OSError("disk full")
        return real_persist(content, raw_dir)

    monkeypatch.setattr(adapter, "_persist_raw", explode)
    with pytest.raises(OSError):
        _run(mod, fixtures, journal=journal, raw_dir=raw)
    records = mod.read_journal(journal)
    assert [r["type"] for r in records] == ["intent"]
    api = _Api(fixtures)
    with pytest.raises(mod.OrphanIntentError):
        _run(mod, fixtures, api=api, journal=journal, raw_dir=raw)
    assert api.requests == []


def test_crash_after_archive_before_receipt_keeps_provenance(
        mod, tmp_path, monkeypatch):
    # The bytes ARE archived but the receipt never landed: the rerun still
    # fails closed, and the orphan's hash is recoverable from the archive the
    # refusal points the operator at.
    fixtures = _one_fixture()
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    real_append = mod.append_record

    def die_on_receipt(path, record):
        if record["type"] == "receipt":
            raise KeyboardInterrupt("killed after archive, before receipt")
        return real_append(path, record)

    monkeypatch.setattr(mod, "append_record", die_on_receipt)
    with pytest.raises(KeyboardInterrupt):
        _run(mod, fixtures, journal=journal, raw_dir=raw)
    monkeypatch.setattr(mod, "append_record", real_append)
    assert [r["type"] for r in mod.read_journal(journal)] == ["intent"]
    assert list(raw.glob("*.json"))                  # provenance survived
    api = _Api(fixtures)
    with pytest.raises(mod.OrphanIntentError):
        _run(mod, fixtures, api=api, journal=journal, raw_dir=raw)
    assert api.requests == []


def test_crash_after_receipt_before_ingest_reruns_without_double_billing(
        mod, tmp_path, monkeypatch):
    # Receipts are the durable record; the store is a pure, idempotent
    # rebuild FROM them. A crash before the rebuild costs nothing: the rerun
    # places no call and repairs the store.
    import pandas as pd

    fixtures = _one_fixture()
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    store = tmp_path / "store"
    real_rebuild = mod.rebuild_store_from_receipts
    first = {"run": True}

    def crash_once(*args, **kwargs):
        if first["run"]:
            first["run"] = False
            raise KeyboardInterrupt("killed after receipt, before ingest")
        return real_rebuild(*args, **kwargs)

    # NB no monkeypatch.undo(): the conftest's network sentinel and archive
    # isolation share this monkeypatch instance, and undoing them mid-test
    # would disarm the suite's spend backstop.
    monkeypatch.setattr(mod, "rebuild_store_from_receipts", crash_once)
    with pytest.raises(KeyboardInterrupt):
        _run(mod, fixtures, journal=journal, raw_dir=raw, store_root=store)
    assert not (store / "odds.parquet").exists()
    receipts = [r for r in mod.read_journal(journal) if r["type"] == "receipt"]
    assert len(receipts) == 3
    api = _Api(fixtures)
    out = _run(mod, fixtures, api=api, journal=journal, raw_dir=raw,
               store_root=store)
    assert api.requests == []                        # zero re-billing
    assert out["prior_spent"] == 21 and out["spent"] == 21
    assert len(pd.read_parquet(store / "odds.parquet")) == 6


def test_crash_after_ingest_reruns_idempotently(mod, tmp_path):
    import pandas as pd

    fixtures = _one_fixture()
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    store = tmp_path / "store"
    _run(mod, fixtures, journal=journal, raw_dir=raw, store_root=store)
    before = pd.read_parquet(store / "odds.parquet")
    lines = len(journal.read_text().splitlines())
    api = _Api(fixtures)
    out = _run(mod, fixtures, api=api, journal=journal, raw_dir=raw,
               store_root=store)
    assert api.requests == []
    assert len(journal.read_text().splitlines()) == lines
    assert out["store_rows"] == 6
    assert pd.read_parquet(store / "odds.parquet").equals(before)


def test_resume_reuses_the_archived_discovery_instead_of_re_buying(
        mod, tmp_path):
    # The first run bought a matchday's listing for one fixture; the resumed
    # run adds a SECOND fixture on the same (sport_key, matchday) key. The
    # already-paid listing must come back out of the archive, not off the
    # wire — and the first fixture's eligibility must be reconstructible from
    # its archived snapshots without spending anything.
    a = _fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
            "2026-06-20T19:00:00Z")
    b = _fx("b", "wc2026", "2026-06-20", "Spain", "Peru",
            "2026-06-20T22:00:00Z")
    journal, raw = tmp_path / "j.jsonl", tmp_path / "raw"
    api = _Api([a, b])
    out = _run(mod, [a], api=api, journal=journal, raw_dir=raw,
               max_credits=21)
    assert len(api.requests) == 3                    # discovery + 2 snapshots
    api = _Api([a, b])
    out = _run(mod, [a, b], api=api, journal=journal, raw_dir=raw,
               max_credits=41)
    assert [p.endswith("/events") for p, _d in api.requests] == [False, False]
    assert out["prior_spent"] == 21 and out["spent"] == 41
    assert all(r["eligible"] for r in out["results"])


# --------------------------------------------------------------------------- #
# Coverage findings + the CLI gates.                                            #
# --------------------------------------------------------------------------- #
def test_absent_event_costs_no_snapshot_credit(mod, tmp_path):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    api = _Api([])                                   # listing carries nothing
    out = _run(mod, fixtures, api=api, journal=tmp_path / "j.jsonl",
               raw_dir=tmp_path / "raw")
    assert out["spent"] == 1                         # discovery only
    assert out["results"][0]["event_found"] is False
    assert out["results"][0]["eligible"] is False
    assert len(api.requests) == 1


def test_ambiguous_match_is_a_per_fixture_error_never_a_pick(mod, tmp_path):
    fixtures = [_fx("a", "wc2026", "2026-06-20", "Brazil", "Japan",
                    "2026-06-20T19:00:00Z")]
    twins = [dict(fixtures[0], fixture_id="a"),
             dict(fixtures[0], fixture_id="a-twin")]
    api = _Api(twins)                                # two events, one pairing
    out = _run(mod, fixtures, api=api, journal=tmp_path / "j.jsonl",
               raw_dir=tmp_path / "raw")
    assert "AmbiguousFixtureMatch" in out["results"][0]["error"]
    assert out["spent"] == 1                         # no snapshot bought


def test_live_requires_both_the_env_key_and_a_cap(mod, tmp_path, capsys):
    manifest = tmp_path / "fx.yaml"
    manifest.write_text(yaml.safe_dump({"fixtures": _one_fixture()}))
    with pytest.raises(SystemExit):
        mod.main(["--live", "--gate-id", "ga", "--fixtures", str(manifest)])
    assert "ODDS_API_KEY" in capsys.readouterr().err


def test_dry_run_never_writes_the_live_journal_or_the_paid_archive(
        mod, tmp_path, monkeypatch, isolated_odds_raw_dir):
    manifest = tmp_path / "fx.yaml"
    manifest.write_text(yaml.safe_dump({"fixtures": _one_fixture()}))
    monkeypatch.setenv("ODDS_API_KEY", "SECRET-should-not-be-read")
    assert mod.main(["--gate-id", "ga", "--fixtures", str(manifest)]) == 0
    # Mock receipts must never enter the PAID journal: the cumulative gate cap
    # is computed from it, so a fabricated billing row would authorize real
    # money against imaginary spend. Same for the paid-evidence archive.
    assert not (tmp_path / mod.JOURNAL_DEFAULT).exists()
    assert (tmp_path / mod.JOURNAL_DRY_RUN_DEFAULT).exists()
    assert not isolated_odds_raw_dir.exists()
    assert not (tmp_path / mod.STORE_DEFAULT).exists()
    report = (tmp_path / "reports" / "oa_acquire_ga.md").read_text()
    assert "DRY-RUN" in report
    assert "SECRET-should-not-be-read" not in report


def test_live_with_a_non_network_transport_refuses_for_want_of_evidence(
        mod, tmp_path, monkeypatch, capsys):
    # The receipts name archived bytes, the store is rebuilt from them and a
    # resumed run reads them instead of re-buying. A transport that cannot
    # produce paid evidence must not run the live path at all — the probe's
    # allowlist, escalated from "do not archive" to "do not run".
    manifest = tmp_path / "fx.yaml"
    manifest.write_text(yaml.safe_dump({"fixtures": _one_fixture()}))
    monkeypatch.setenv("ODDS_API_KEY", "fake-key-evidence-guard")
    api = _Api(_one_fixture())
    monkeypatch.setattr(mod, "_live_transport", api.transport)
    rc = mod.main(["--live", "--gate-id", "ga", "--fixtures", str(manifest),
                   "--max-credits", "21"])
    assert rc == 1
    assert "paid evidence" in capsys.readouterr().err
    assert api.requests == []
    assert not (tmp_path / mod.JOURNAL_DEFAULT).exists()
