#!/usr/bin/env python
"""OA-0a probe runner — the SPEND GATE (spec finding 13).

Measures (never assumes) Odds-API coverage and cost before any purchase is
approved: 15 pre-listed fixtures (5 per pool, stratified opening day /
mid-group / last group day / one KO / the final; team spellings match the
martj42 store), each probed with 1 discovery call + 2 snapshot calls (T-24h
and T-1h before the DISCOVERED kickoff), ``h2h`` market, ``eu`` region.

Modes (hard gates in code, pinned by tests/eval/test_probe.py):

- DEFAULT ``--dry-run``: recorded-shape payloads served by an in-process
  ``httpx.MockTransport`` — ZERO network, ZERO credits, and the env
  ``ODDS_API_KEY`` is never read (a sentinel key goes to the mock). The
  report is written but LOUDLY labeled: its values prove the pipeline, they
  are NOT measurements.
- ``--live``: real paid calls. Requires BOTH the ``ODDS_API_KEY`` env var AND
  ``--max-credits N``. Before EVERY transport call the full-plan projected
  total (modeled spend so far + modeled remainder) is checked against N — a
  cap below the projection aborts before the FIRST call. Actual usage is read
  back from the ``x-requests-used`` / ``x-requests-remaining`` headers,
  reported, AND enforced: the modeled per-call prices are hypotheses this
  probe exists to verify, so once the billing counters show actual
  consumption above N the next call is refused (mid-run abort, non-zero
  exit) — with the PARTIAL report still written, because the calls already
  placed were already paid for. In that partial report every refused or
  unreached call is marked "not attempted" — our own gate's refusal must
  never read as a measured coverage miss. A breach first revealed by the
  FINAL response (no next call left to refuse) still fails the run: the
  report states actual-billed vs cap vs modeled and the exit is non-zero.
  NEVER run by agents: the live probe is the user's decision at the
  plan-end STOP gate.

Output: ``reports/oa_probe.md`` (cwd-relative — run from the repo root, like
``scripts/oa_mde.py``).
"""
# No `from __future__ import annotations`: loaded by PATH in tests
# (scripts/ is not on sys.path), matching the oa_mde.py convention.
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from wcmodel.config import load_config
from wcmodel.data.sources.odds import (
    ODDS_RAW_DIR,
    fetch_historical,
    fetch_historical_events,
    parse_snapshot,
    strictest_last_update,
)

# ---------------------------------------------------------------- cost model
# Published Odds-API prices for the historical routes: the events (discovery)
# endpoint bills 1 credit per call; an odds snapshot bills 10 credits per
# region-market — h2h x eu is exactly one region-market. The probe MEASURES
# whether these hold (the usage headers are the readback); the projection the
# spend gate enforces is built from them.
DISCOVERY_CREDITS = 1
SNAPSHOT_CREDITS = 10
SNAPSHOTS_PER_FIXTURE = 2            # T-24h and T-1h before kickoff
MARKET = "h2h"
REGIONS = "eu"
SHARP_BOOK = "pinnacle"

# Full-program extrapolation base: the 185-pool (wc2022 + euro2024 + wc2026
# group) plus the 32 WC-2026 knockout fixtures = 217 odds-scored fixtures.
# N_dev (the OA-0b development-slate size) stays an explicit formula input.
EVAL_FIXTURES = 217

OUT_DEFAULT = "reports/oa_probe.md"

#: The dry-run's wire key. NEVER the env ``ODDS_API_KEY``: a dry-run spends
#: nothing and must not touch real credentials even when one is available.
_DRY_RUN_KEY = "dry-run-no-key"

# 15 pre-listed probe fixtures — 5 per pool, stratified per the plan. Dates
# and team spellings are taken from the martj42 store (data/stores/full_final)
# and pinned against it by tests/eval/test_probe.py, so a live discovery
# result can always be tied back to the pool fixture it probes.
PROBE_FIXTURES = (
    # wc2022 — group 2022-11-20..12-02, R16 from 12-03, final 12-18
    {"pool": "wc2022", "stratum": "opening_day",
     "date": "2022-11-20", "home": "Qatar", "away": "Ecuador"},
    {"pool": "wc2022", "stratum": "mid_group",
     "date": "2022-11-26", "home": "Argentina", "away": "Mexico"},
    {"pool": "wc2022", "stratum": "last_group_day",
     "date": "2022-12-02", "home": "South Korea", "away": "Portugal"},
    {"pool": "wc2022", "stratum": "knockout",
     "date": "2022-12-03", "home": "Netherlands", "away": "United States"},
    {"pool": "wc2022", "stratum": "final",
     "date": "2022-12-18", "home": "Argentina", "away": "France"},
    # euro2024 — group 2024-06-14..06-26, R16 from 06-29, final 07-14
    {"pool": "euro2024", "stratum": "opening_day",
     "date": "2024-06-14", "home": "Germany", "away": "Scotland"},
    {"pool": "euro2024", "stratum": "mid_group",
     "date": "2024-06-19", "home": "Germany", "away": "Hungary"},
    {"pool": "euro2024", "stratum": "last_group_day",
     "date": "2024-06-26", "home": "Georgia", "away": "Portugal"},
    {"pool": "euro2024", "stratum": "knockout",
     "date": "2024-06-30", "home": "Spain", "away": "Georgia"},
    {"pool": "euro2024", "stratum": "final",
     "date": "2024-07-14", "home": "Spain", "away": "England"},
    # wc2026 — group 2026-06-11..06-27, R32 from 06-28, final 07-19
    {"pool": "wc2026", "stratum": "opening_day",
     "date": "2026-06-11", "home": "Mexico", "away": "South Africa"},
    {"pool": "wc2026", "stratum": "mid_group",
     "date": "2026-06-18", "home": "Canada", "away": "Qatar"},
    {"pool": "wc2026", "stratum": "last_group_day",
     "date": "2026-06-27", "home": "Colombia", "away": "Portugal"},
    {"pool": "wc2026", "stratum": "knockout",
     "date": "2026-06-29", "home": "Brazil", "away": "Japan"},
    {"pool": "wc2026", "stratum": "final",
     "date": "2026-07-19", "home": "Spain", "away": "Argentina"},
)


def _ts(s: str) -> datetime:
    # A NAIVE parse is refused, not guessed at: ``astimezone`` reinterprets a
    # naive datetime as MACHINE-LOCAL time, so a wire ``commence_time``
    # lacking a UTC designator would shift both PAID snapshot requests by the
    # host's UTC offset — credits on the wrong instants, and a report that
    # varies by machine timezone.
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(
            f"naive timestamp {s!r}: no UTC designator/offset — refusing to "
            "guess the machine timezone for a paid snapshot request")
    return dt


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _label(fx: dict) -> str:
    return f"{fx['home']} v {fx['away']} ({fx['date']})"


def _event_id(fx: dict) -> str:
    """Mock event id for the dry-run payloads (stable per fixture)."""
    return f"mock_{fx['pool']}_{fx['date']}"


def projected_probe_cost() -> int:
    """The modeled cost of the whole probe: 15 x (1 + 2x10) = 315 credits."""
    return len(PROBE_FIXTURES) * (
        DISCOVERY_CREDITS + SNAPSHOTS_PER_FIXTURE * SNAPSHOT_CREDITS)


def full_program_budget(n_dev: int) -> int:
    """(217 eval + N_dev) fixtures x 2 snapshots x 10 credits."""
    return (EVAL_FIXTURES + n_dev) * SNAPSHOTS_PER_FIXTURE * SNAPSHOT_CREDITS


def build_call_plan(sport_keys: dict) -> list:
    """One row per planned call (45 = 15 discovery + 30 snapshots). Snapshot
    timestamps depend on the DISCOVERED kickoff, so their ``at`` is symbolic."""
    rows = []
    for fx in PROBE_FIXTURES:
        key = sport_keys[fx["pool"]]
        base = {"fixture": _label(fx), "pool": fx["pool"],
                "stratum": fx["stratum"]}
        rows.append({**base, "call": "discovery",
                     "endpoint": f"/v4/historical/sports/{key}/events",
                     "at": f"{fx['date']}T00:00:00Z",
                     "credits": DISCOVERY_CREDITS})
        for tag in ("T-24h", "T-1h"):
            rows.append({**base, "call": f"snapshot {tag}",
                         "endpoint": (f"/v4/historical/sports/{key}"
                                      "/events/{event_id}/odds"),
                         "at": f"discovered kickoff {tag}",
                         "credits": SNAPSHOT_CREDITS})
    return rows


class CreditCapError(RuntimeError):
    """Projected spend would exceed --max-credits: refuse to place the call."""


class SpendGate:
    """Pre-call projected-cost abort (the plan's hard gate).

    The projection checked before EVERY call is the full-plan total — modeled
    spend so far plus the modeled remainder — NOT a running sum: a running sum
    would happily place cap-many credits of calls before tripping, while this
    gate trips on the FIRST precall whenever the whole plan cannot fit under
    the cap (zero transport calls, zero credits). ``precall`` keeps that
    projection constant and nothing ever raises it, so the modeled gate is a
    START gate — only the first precall can trip; it still runs before every
    call purely as an invariant guard against future plan-growing edits.
    (A ``skip`` hook that shrank the remainder for dropped calls used to live
    here: with a non-increasing projection it could never affect any check —
    dead logic that read as a live safety mechanism, so it was removed.)
    Mid-run aborts belong to the ACTUAL-usage check (``_UsageRecorder``),
    which enforces the billing headers this model exists to verify.
    ``cap=None`` (dry-run) never aborts — the gate still accounts: ``spent``
    is the modeled spend the report cites, and it counts only precalled
    calls, so suppressed snapshots (event not found, discovery failure)
    never inflate it.
    """

    def __init__(self, cap, remaining_planned: int):
        self.cap = cap
        self.remaining = remaining_planned
        self.spent = 0

    def precall(self, credits: int, what: str) -> None:
        projected = self.spent + self.remaining
        if self.cap is not None and projected > self.cap:
            raise CreditCapError(
                f"projected total {projected} credits exceeds "
                f"--max-credits {self.cap} (before {what}; modeled spend so "
                f"far {self.spent}) — aborting, no call placed")
        self.spent += credits
        self.remaining -= credits


class _UsageRecorder(httpx.BaseTransport):
    """Wraps the real transport to read back ``x-requests-used`` /
    ``x-requests-remaining`` from every response — and to ENFORCE the cap
    against them: the SpendGate bounds the MODELED cost, but the model's
    per-call prices are exactly what this probe exists to verify, so before
    every call the ACTUAL billed consumption (the ``x-requests-used`` delta
    since the first response; the first call's own cost is invisible until
    the counter moves) is checked too and a breach refuses the call. The
    check sits BEFORE the transport is invoked, never after — a received
    response is already paid for and must always reach the adapter's archive.
    Lives here rather than widening the adapter (which returns parsed
    payloads, not responses). ``close`` is a no-op: the adapter opens a
    short-lived ``httpx.Client`` PER call, and letting it close the shared
    inner transport would kill the connection pool between calls (harmless
    for MockTransport, fatal for the live HTTPTransport)."""

    def __init__(self, inner: httpx.BaseTransport, cap=None):
        self._inner = inner
        self.cap = cap
        self.usage: list = []

    @staticmethod
    def _as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def actual_consumed(self):
        """Credits the API says were billed since the FIRST response, from
        the ``x-requests-used`` counter — ``None`` until two responses carry
        a parseable value (headers are evidence, never assumed present)."""
        used = [u for u in (self._as_int(entry["requests_used"])
                            for entry in self.usage) if u is not None]
        if len(used) < 2:
            return None
        return used[-1] - used[0]

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        actual = self.actual_consumed()
        if self.cap is not None and actual is not None and actual > self.cap:
            raise CreditCapError(
                f"actual billed usage {actual} credits (x-requests-used "
                f"delta since the first response) exceeds --max-credits "
                f"{self.cap} — aborting before {request.url.path}, no "
                "further call placed")
        response = self._inner.handle_request(request)
        self.usage.append({
            "path": request.url.path,
            "requests_used": response.headers.get("x-requests-used"),
            "requests_remaining": response.headers.get("x-requests-remaining"),
        })
        return response

    def close(self) -> None:
        pass


# ------------------------------------------------------- dry-run mock payloads
# Deterministic recorded-shape payloads. The geometry is fixed so the report's
# drift/staleness arithmetic is pinned by tests: a snapshot's own timestamp
# trails the requested ts by 3 min; Pinnacle's bookmaker stamp is 10 min older
# than the snapshot ts and the h2h market stamp 5 min older, so the strictest
# stamp is the market's -> staleness at T-1h = 3 + 5 = 8 min.
_MOCK_SNAPSHOT_LAG = timedelta(minutes=3)
_MOCK_BOOK_LAG = timedelta(minutes=10)
_MOCK_MARKET_LAG = timedelta(minutes=5)


def _mock_commence(fx: dict) -> str:
    return f"{fx['date']}T18:00:00Z"     # placeholder kickoff for mock events


def _mock_discovery(fx: dict, requested_ts: str) -> dict:
    # A decoy event on the same day makes the probe's name-matching
    # non-trivial: "event found" must mean OUR fixture, not "any event".
    return {
        "timestamp": requested_ts,
        "previous_timestamp": requested_ts,
        "next_timestamp": requested_ts,
        "data": [
            {"id": f"{_event_id(fx)}_decoy",
             "commence_time": f"{fx['date']}T21:00:00Z",
             "home_team": "Mock Decoy A", "away_team": "Mock Decoy B"},
            {"id": _event_id(fx), "commence_time": _mock_commence(fx),
             "home_team": fx["home"], "away_team": fx["away"]},
        ],
    }


def _mock_snapshot(fx: dict, requested_ts: str) -> dict:
    ts = _ts(requested_ts) - _MOCK_SNAPSHOT_LAG
    outcomes = [{"name": fx["home"], "price": 2.10},
                {"name": "Draw", "price": 3.30},
                {"name": fx["away"], "price": 3.60}]
    return {
        "timestamp": _iso(ts),
        "previous_timestamp": _iso(ts - timedelta(minutes=5)),
        "next_timestamp": _iso(ts + timedelta(minutes=5)),
        "data": {
            "id": _event_id(fx),
            "commence_time": _mock_commence(fx),
            "home_team": fx["home"], "away_team": fx["away"],
            "bookmakers": [
                {"key": SHARP_BOOK, "last_update": _iso(ts - _MOCK_BOOK_LAG),
                 "markets": [{"key": MARKET,
                              "last_update": _iso(ts - _MOCK_MARKET_LAG),
                              "outcomes": outcomes}]},
                {"key": "unibet_eu",
                 "last_update": _iso(ts - timedelta(minutes=2)),
                 "markets": [{"key": MARKET,
                              "last_update": _iso(ts - timedelta(minutes=2)),
                              "outcomes": outcomes}]},
            ],
        },
    }


def _dry_run_handler(sport_keys: dict):
    by_discovery = {(sport_keys[fx["pool"]], f"{fx['date']}T00:00:00Z"): fx
                    for fx in PROBE_FIXTURES}
    by_event = {_event_id(fx): fx for fx in PROBE_FIXTURES}

    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")
        requested = request.url.params["date"]
        if request.url.path.endswith("/events"):
            fx = by_discovery[(parts[4], requested)]
            return httpx.Response(200, json=_mock_discovery(fx, requested))
        return httpx.Response(200, json=_mock_snapshot(by_event[parts[6]],
                                                       requested))

    return handler


def _dry_run_transport(sport_keys: dict) -> httpx.MockTransport:
    return httpx.MockTransport(_dry_run_handler(sport_keys))


def _live_transport() -> httpx.BaseTransport:
    """The real-network transport for --live (constructing it opens no
    connection). Tests monkeypatch this factory with a MockTransport — the
    only way the live code path ever runs under test."""
    return httpx.HTTPTransport()


def _live_raw_dir(transport: httpx.BaseTransport):
    """Where a --live run archives raw responses: the repo paid-evidence store
    ONLY for the genuine network transport, nowhere for anything else. An
    ALLOWLIST on ``httpx.HTTPTransport`` — matching the polarity of the
    adapter's ``_resolve_raw_dir`` (ANY injected transport means no archive):
    a denylist on MockTransport would wave every other injected fake (a plain
    ``BaseTransport`` subclass, the probe's own ``_UsageRecorder`` wrapper)
    into the real store with fabricated bytes. The adapter's own
    transport-aware default cannot make this call — the usage-recording
    wrapper makes the transport non-None even on real runs, so the probe must
    pass raw_dir explicitly."""
    return ODDS_RAW_DIR if isinstance(transport, httpx.HTTPTransport) else None


# ----------------------------------------------------------------- the probe
def _norm(name: str) -> str:
    return name.casefold().strip()


def _table_text(text) -> str:
    """Collapse whitespace and escape pipes: EVERY interpolated string —
    error messages, live team names straight off the wire — must survive a
    markdown table cell, or an embedded newline/``|`` splits the committed
    report's results row."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _err_cell(exc: Exception) -> str:
    """Failure text shaped to survive a markdown table cell: httpx messages
    can span lines (the 429's does) and could carry ``|`` — exactly the
    401/429/timeout findings the probe exists to surface."""
    return f"{type(exc).__name__}: {_table_text(exc)}"


def _match_event(rows: list, fx: dict):
    """Find the probed fixture among discovered events by team names; a
    flipped home/away orientation still matches (neutral-venue sources
    disagree on orientation) but is reported."""
    want = (_norm(fx["home"]), _norm(fx["away"]))
    for row in rows:
        got = (_norm(row["home"] or ""), _norm(row["away"] or ""))
        if got == want:
            return row, False
        if got == (want[1], want[0]):
            return row, True
    return None, None


def _probe_snapshot(fx: dict, event, tag: str, requested: datetime, *,
                    sport_key: str, api_key: str, transport, raw_dir) -> dict:
    # Every RETURNED entry was attempted: the only pre-wire refusal is
    # CreditCapError, which propagates instead of returning — the caller's
    # pre-seeded ``attempted: False`` entry then stands.
    entry = {"tag": tag, "requested_ts": _iso(requested), "attempted": True}
    try:
        snap = fetch_historical(
            event["event_id"], _iso(requested), api_key, market=MARKET,
            regions=REGIONS, sport_key=sport_key, raw_dir=raw_dir,
            transport=transport)
        # Provenance FIRST: the archived hash must survive any parse or
        # arithmetic surprise below — the bytes it names are already paid for.
        entry["raw_sha256"] = snap.get("raw_sha256")
        rows = parse_snapshot(snap)
        pin = [r for r in rows if r["bookmaker"] == SHARP_BOOK]
        entry.update({
            "snapshot_ts": snap["timestamp"],
            "drift_min": round(
                (requested - _ts(snap["timestamp"])).total_seconds() / 60.0,
                1),
            "pinnacle_present": bool(pin),
            "n_bookmakers": len({r["bookmaker"] for r in rows}),
        })
        if pin:
            lu = strictest_last_update(pin[0], snap["timestamp"])
            entry["pinnacle_staleness_min"] = round(
                (requested - lu).total_seconds() / 60.0, 1)
    except CreditCapError:
        raise                    # the spend gate is an abort, never a note
    except Exception as exc:
        # A 401/429/timeout — or a 200 whose body trips the parse/arithmetic
        # legs above — is a FINDING for the coverage report, not a crash that
        # discards the fixtures already paid for. str(exc) is safe here: the
        # adapter's redaction strips the query string (the key) from every
        # HTTP-layer message it lets escape, and non-HTTP failures carry only
        # payload-derived text (the key never enters a payload).
        entry["error"] = _err_cell(exc)
    return entry


def run_probe(*, api_key: str, transport: httpx.BaseTransport,
              max_credits, raw_dir, sport_keys: dict) -> dict:
    """Run the 15-fixture probe through ``transport``. Every call passes the
    SpendGate AND the actual-usage check FIRST. Returns ``{"results",
    "usage", "spent", "projected", "aborted", "actual", "overrun"}`` —
    ``aborted`` carries the cap breach's message when the run stopped
    mid-flight AFTER paid calls (their partial results are still the user's,
    so they still get reported, with every refused or unreached call marked
    ``attempted: False`` — never rendered as a measured miss); a breach
    before ANY call re-raises, since there is nothing paid for to report.
    ``overrun`` flags the case the pre-call checks cannot see: actual billed
    usage above the cap first revealed by the FINAL response, when no next
    call remains to refuse."""
    recorder = _UsageRecorder(transport, cap=max_credits)
    projected = projected_probe_cost()
    gate = SpendGate(max_credits, projected)
    results = []
    aborted = None
    try:
        for fx in PROBE_FIXTURES:
            key = sport_keys[fx["pool"]]
            # Appended BEFORE any gate, ``attempted: False`` until the
            # discovery call actually goes to the wire: a cap refusal must
            # read "not attempted" in the report, never "not among the
            # listed events" (a refusal is OUR gate; a miss is THEIR data).
            row = {"pool": fx["pool"], "stratum": fx["stratum"],
                   "fixture": _label(fx), "sport_key": key,
                   "attempted": False, "snapshots": []}
            results.append(row)
            try:
                gate.precall(DISCOVERY_CREDITS, f"discovery {_label(fx)}")
                events = fetch_historical_events(
                    key, f"{fx['date']}T00:00:00Z", api_key,
                    raw_dir=raw_dir, transport=recorder)
                row["attempted"] = True
                row["n_events_listed"] = len(events)
                event, flipped = _match_event(events, fx)
                row["event_found"] = event is not None
                if event is None:
                    # No event id -> the snapshot precalls simply never
                    # happen (the modeled spend never counts them). Record
                    # what discovery DID return — that listing is the
                    # coverage evidence read at the gate.
                    row["listed"] = [f"{e['home']} v {e['away']}"
                                     for e in events[:5]]
                    continue
                row.update({"event_id": event["event_id"],
                            "commence_time": event["commence_time"],
                            "orientation_flipped": flipped,
                            "discovery_sha256": event.get("raw_sha256")})
                commence = _ts(event["commence_time"])
            except CreditCapError:
                raise            # the spend gate is an abort, never a note
            except Exception as exc:
                # ANY per-fixture surprise — HTTP, refused shape, a field the
                # adapter's comprehension trips on — is a FINDING, not a
                # crash that discards the fixtures already paid for. Only the
                # cap refuses pre-wire (and it re-raises above), so this call
                # was attempted.
                row["attempted"] = True
                row["error"] = _err_cell(exc)
                continue
            for tag, delta in (("T-24h", timedelta(hours=24)),
                               ("T-1h", timedelta(hours=1))):
                requested = commence - delta
                # Appended BEFORE the gates: a refused snapshot call keeps
                # an explicit not-attempted marker instead of vanishing into
                # the same "-"/blank a measured miss renders.
                entry = {"tag": tag, "requested_ts": _iso(requested),
                         "attempted": False}
                row["snapshots"].append(entry)
                gate.precall(SNAPSHOT_CREDITS, f"snapshot {tag} {_label(fx)}")
                entry.update(_probe_snapshot(
                    fx, event, tag, requested, sport_key=key,
                    api_key=api_key, transport=recorder, raw_dir=raw_dir))
    except CreditCapError as exc:
        if not recorder.usage:
            raise                # zero calls placed: nothing paid, no report
        aborted = str(exc)
        # Every fixture the loop never reached still gets a row — explicitly
        # not-attempted, so the PARTIAL report keeps the full 15-fixture
        # frame instead of silently dropping the tail.
        for fx in PROBE_FIXTURES[len(results):]:
            results.append({"pool": fx["pool"], "stratum": fx["stratum"],
                            "fixture": _label(fx),
                            "sport_key": sport_keys[fx["pool"]],
                            "attempted": False, "snapshots": []})
    actual = recorder.actual_consumed()
    overrun = None
    if (aborted is None and max_credits is not None and actual is not None
            and actual > max_credits):
        # The pre-call checks can only refuse the NEXT call — a breach first
        # revealed by the FINAL response has no next call, so it is caught
        # here: the completed run still fails loudly instead of exiting 0.
        overrun = (
            f"actual billed usage {actual} credits (x-requests-used delta "
            f"since the first response) exceeds --max-credits {max_credits} "
            "and no further call remained to refuse — the plan completed, "
            "but the cap did not hold")
    return {"results": results, "usage": recorder.usage,
            "spent": gate.spent, "projected": projected, "aborted": aborted,
            "actual": actual, "overrun": overrun}


# ------------------------------------------------------------------ reporting
def _mode_banner(mode: str, mocked: bool) -> list:
    if mode == "dry-run":
        return [
            "**MODE: DRY-RUN.** Every response below came from recorded-shape "
            "MOCK payloads served by an in-process transport: ZERO network "
            "calls, ZERO credits spent, and the env `ODDS_API_KEY` was never "
            "read. Coverage/freshness values prove the pipeline and are NOT "
            "measurements — the user-gated live probe overwrites this report "
            "with real ones."]
    if mocked:
        return [
            "**MODE: LIVE ARGS, MOCKED TRANSPORT (test only).** The live gates "
            "ran, but responses came from an injected mock: NOT real "
            "measurements, no credits spent."]
    return ["**MODE: LIVE.** Real paid responses from The Odds API."]


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "y" if value else "n"
    return str(value)


def _snapshot_cell(row: dict, tag: str, field: str):
    for snap in row.get("snapshots", []):
        if snap["tag"] == tag:
            if not snap.get("attempted", True):
                # A refused call is OUR gate, not their coverage: it must
                # never render like a measured miss ("-") or an API failure
                # ("ERR") — the observables the purchase decision turns on.
                return "not attempted"
            if "error" in snap and field != "error":
                return "ERR"
            return snap.get(field)
    return None


def assemble_report(*, mode: str, mocked: bool, sport_keys: dict, plan: list,
                    projected: int, spent: int, results: list,
                    usage: list, aborted=None, cap=None, actual=None,
                    overrun=None) -> str:
    """Pure: canned inputs -> the full markdown report."""
    n_disc = sum(1 for r in plan if r["call"] == "discovery")
    n_snap = len(plan) - n_disc
    lines = ["# OA-0a probe — Odds API coverage + cost (spec finding 13)", ""]
    lines += _mode_banner(mode, mocked)
    if aborted:
        lines += ["", f"**RUN ABORTED MID-FLIGHT: {aborted}** Partial "
                  "results: only the calls placed before the abort appear "
                  "below; every refused or unreached call is marked \"not "
                  "attempted\" — a refusal by our own gate, never a "
                  "measured miss."]
        never = [r["fixture"] for r in results
                 if not r.get("attempted", True)]
        if never:
            lines += ["", f"Never attempted ({len(never)} of {len(results)} "
                      "fixtures — no call placed): " + "; ".join(never) + "."]
    lines += ["", "## Sport keys under test (config `odds.sport_keys`)", ""]
    lines += [f"- {pool}: `{key}` — the probe VERIFIES this exact string; a "
              "wrong key is corrected in config, no code change"
              for pool, key in sport_keys.items()]
    lines += [
        "", "## Call plan + projected credit cost", "",
        f"{len(PROBE_FIXTURES)} fixtures x (1 discovery @ "
        f"{DISCOVERY_CREDITS} credit + {SNAPSHOTS_PER_FIXTURE} snapshots "
        f"[T-24h, T-1h; {MARKET} x {REGIONS} = 1 region-market] @ "
        f"{SNAPSHOT_CREDITS} credits): "
        f"{n_disc} discovery + {n_snap} snapshot calls = "
        f"**{projected} credits** projected; modeled spend this run: "
        # A skim-reader at the spend gate must not read the modeled figure as
        # money spent — but only a dry-run may claim zero billing.
        f"{spent}"
        + (" (dry-run: 0 actually billed)." if mode == "dry-run" else "."),
        "",
        "| # | fixture | pool | stratum | call | endpoint | at | credits |",
        "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {i} | {r['fixture']} | {r['pool']} | {r['stratum']} | "
              f"{r['call']} | `{r['endpoint']}` | {r['at']} | {r['credits']} |"
              for i, r in enumerate(plan, 1)]
    lines += [
        "", "## Per-fixture results", "",
        "| pool | stratum | fixture | event found | Pinnacle T-24h | "
        "Pinnacle T-1h | snapshot drift T-24h (min) | drift T-1h (min) | "
        "Pinnacle last_update staleness at T-1h (min) | notes |",
        "|---|---|---|---|---|---|---|---|---|---|"]
    for row in results:
        if "error" in row:
            notes = row["error"]
        elif not row.get("attempted", True):
            # The probe never asked: rendering this row through the MISS
            # branch would claim "not among the listed events" for a listing
            # that was never fetched.
            notes = ("not attempted: the run aborted before this fixture's "
                     "discovery call was placed")
        elif not row.get("event_found"):
            # Team names straight off the live wire: _table_text, or a name
            # carrying "|" or a newline splits this row — the same corruption
            # _err_cell guards on the error branches, on the branch the probe
            # exists to surface.
            notes = _table_text(
                "not among " + str(row.get("n_events_listed")) +
                " listed events: " + "; ".join(row.get("listed", [])))
        else:
            notes = "; ".join(
                (["orientation flipped vs store"]
                 if row.get("orientation_flipped") else [])
                + [s["error"] for s in row["snapshots"] if "error" in s]
                + [f"snapshot {s['tag']} not attempted (run aborted)"
                   for s in row["snapshots"]
                   if not s.get("attempted", True)])
        cells = [row["pool"], row["stratum"], row["fixture"],
                 _fmt(row.get("event_found")),
                 _fmt(_snapshot_cell(row, "T-24h", "pinnacle_present")),
                 _fmt(_snapshot_cell(row, "T-1h", "pinnacle_present")),
                 _fmt(_snapshot_cell(row, "T-24h", "drift_min")),
                 _fmt(_snapshot_cell(row, "T-1h", "drift_min")),
                 _fmt(_snapshot_cell(row, "T-1h", "pinnacle_staleness_min")),
                 notes or "-"]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "Provenance (sha256 of the archived raw response; dry-run "
              "hashes are of MOCK bytes and are not persisted):", ""]
    for row in results:
        shas = [f"discovery {row['discovery_sha256'][:12]}"] \
            if row.get("discovery_sha256") else []
        shas += [f"{s['tag']} {s['raw_sha256'][:12]}"
                 for s in row.get("snapshots", []) if s.get("raw_sha256")]
        lines.append(f"- {row['fixture']}: " + (", ".join(shas) or "-"))
    lines += ["", "## Actual usage (`x-requests-used` / "
              "`x-requests-remaining` headers)", ""]
    if mode == "dry-run":
        lines += ["Not available: dry-run serves no live responses, so no "
                  "usage headers exist (and none are fabricated)."]
    elif not usage:
        lines += ["No responses received."]
    else:
        lines += ["| call | path | x-requests-used | x-requests-remaining |",
                  "|---|---|---|---|"]
        lines += [f"| {i} | `{u['path']}` | {_fmt(u['requests_used'])} | "
                  f"{_fmt(u['requests_remaining'])} |"
                  for i, u in enumerate(usage, 1)]
        # The deliverable STATES actual-billed vs cap vs modeled — the
        # reader at the spend gate must never hand-subtract the table.
        lines += [
            "",
            "Actual billed this run: "
            + (f"**{actual} credits**" if actual is not None
               else "unknown (fewer than two parseable `x-requests-used` "
                    "counters)")
            + " — the `x-requests-used` delta since the first response, so "
              "the first call's own price is invisible and the true spend "
              "is up to one call price higher — vs `--max-credits` "
            + f"{_fmt(cap)}; modeled spend {spent} credits."]
        if overrun:
            lines += ["", f"**ACTUAL BILLING EXCEEDED THE CAP: {overrun}**"]
    lines += [
        "", "## Extrapolated full-program budget", "",
        f"({EVAL_FIXTURES} eval + N_dev) fixtures x {SNAPSHOTS_PER_FIXTURE} "
        f"snapshots x {SNAPSHOT_CREDITS} credits = "
        f"**{full_program_budget(0)} + {SNAPSHOTS_PER_FIXTURE * SNAPSHOT_CREDITS}"
        " x N_dev credits**", "",
        f"- {EVAL_FIXTURES} = the 185-pool (wc2022 + euro2024 + wc2026 group) "
        "+ the 32 WC-2026 knockout fixtures.",
        "- N_dev = the development-slate size — an OA-0b sizing decision and "
        "an explicit formula input, never assumed here.",
        "- Per-event discovery, if needed, adds ~1 credit per fixture-day "
        "on top of the formula.", "",
        "| N_dev (illustrative) | credits |", "|---|---|"]
    lines += [f"| {n} | {full_program_budget(n)} |"
              for n in (0, 100, 200, 400)]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="mocked transport, zero network, zero credits "
                         "(the DEFAULT when no mode flag is given)")
    ap.add_argument("--live", action="store_true",
                    help="REAL PAID CALLS — requires the ODDS_API_KEY env var "
                         "AND --max-credits; user decision at the STOP gate")
    ap.add_argument("--max-credits", type=int, default=None,
                    help="hard cap for --live: the full-plan projected cost "
                         "is checked against this BEFORE every call")
    ap.add_argument("--out", default=OUT_DEFAULT,
                    help=f"report path (default {OUT_DEFAULT})")
    args = ap.parse_args(argv)
    if args.live and args.dry_run:
        ap.error("--live and --dry-run are mutually exclusive")

    sport_keys = load_config()["odds"]["sport_keys"]
    plan = build_call_plan(sport_keys)
    projected = sum(r["credits"] for r in plan)
    print(f"call plan: {len(plan)} calls "
          f"({sum(1 for r in plan if r['call'] == 'discovery')} discovery + "
          f"{sum(1 for r in plan if r['call'] != 'discovery')} snapshots), "
          f"projected {projected} credits")
    for row in plan:
        print(f"  {row['pool']:8s} {row['call']:14s} {row['at']:26s} "
              f"{row['credits']:3d}cr  {row['fixture']}")

    if args.live:
        api_key = os.environ.get("ODDS_API_KEY")
        if not api_key:
            ap.error("--live requires the ODDS_API_KEY environment variable "
                     "(AND --max-credits N); the live probe is the user's "
                     "spend decision at the STOP gate")
        if args.max_credits is None:
            ap.error("--live requires --max-credits N (the pre-call "
                     "projected-cost abort cap) in addition to ODDS_API_KEY")
        mode, transport, cap = "live", _live_transport(), args.max_credits
        # Paid responses are evidence: archive them — but only off a REAL
        # transport (_live_raw_dir): a monkeypatched mock serving fabricated
        # bytes must never write into the paid-evidence store.
        raw_dir = _live_raw_dir(transport)
    else:
        mode, transport, cap = "dry-run", _dry_run_transport(sport_keys), None
        api_key, raw_dir = _DRY_RUN_KEY, None    # mock bytes: never archived

    try:
        out = run_probe(api_key=api_key, transport=transport,
                        max_credits=cap, raw_dir=raw_dir,
                        sport_keys=sport_keys)
    except CreditCapError as exc:
        # Aborted before ANY call was placed: nothing was paid for, so there
        # is nothing to report (a mid-run breach returns partial results
        # instead — those calls were paid for and their report is owed).
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1

    md = assemble_report(
        mode=mode, mocked=isinstance(transport, httpx.MockTransport),
        sport_keys=sport_keys, plan=plan, projected=out["projected"],
        spent=out["spent"], results=out["results"], usage=out["usage"],
        aborted=out["aborted"], cap=cap, actual=out["actual"],
        overrun=out["overrun"])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"wrote {out_path}")
    if out["aborted"]:
        print(f"ABORT: {out['aborted']}", file=sys.stderr)
        return 1
    if out["overrun"]:
        # A completed run that ended over the cap must not exit 0: nothing
        # was left to refuse, but the cap still did not hold.
        print(f"OVER CAP: {out['overrun']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
