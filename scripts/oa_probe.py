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
  ``--max-credits N`` — and N is a HARD cap. Before EVERY transport call two
  modeled checks run: the full-plan projected total (modeled spend so far +
  modeled remainder) AND the spend so far plus the call's own price must
  both fit under N — a cap below the projection aborts before the FIRST
  call, and an unmodeled extra call is refused while spend is still under N,
  never one call after. Storage is preflighted (raw archive dir + report
  destination proven writable) before the first call, and any
  archive/persistence failure mid-run is FATAL — a paid response we cannot
  durably archive stops all further spending. Actual usage is read back from
  the ``x-requests-last`` / ``x-requests-used`` / ``x-requests-remaining``
  headers, reported, AND enforced: the modeled per-call prices are
  hypotheses this probe exists to verify, so before every call the actual
  billed consumption (summed per-call ``x-requests-last`` costs
  cross-checked against the ``x-requests-used`` counter delta, the larger
  standing) plus the next call's modeled price must fit under N or the call
  is refused (mid-run abort, non-zero exit) — with the PARTIAL report still
  written, because the calls already placed were already paid for. In that
  partial report every refused or unreached call is marked "not attempted"
  — our own gate's refusal must never read as a measured coverage miss. A
  breach first revealed by the FINAL response (no next call left to refuse)
  still fails the run: the report states actual-billed vs cap vs modeled
  and the exit is non-zero.
  NEVER run by agents: the live probe is the user's decision at the
  plan-end STOP gate.

``--slate`` swaps the 15-fixture eval panel for the DEV-SLATE mini-probe
(``SLATE_PROBES``): 13 candidate development competitions, 2022-2025, one
discovery + one T-1h snapshot each — 143 credits projected against the plan's
150-credit budget. It answers a different question (does the archive carry
this competition at all?), so it has its own panel and its own report, but
runs through the SAME gates: dry-run by default, ``--live`` refused without
both ``ODDS_API_KEY`` and ``--max-credits``, the SpendGate and the
billing-header check before every call. LIVE slate runs route through
``oa_acquire``'s canonical G-A journal (plan2 batch-1, finding 1): exclusive
flock, fail-closed orphan check, INTENT/RECEIPT around every paid call, and
the mini-probe's spend counted into the G-A cumulative cap — the unjournaled
live path no longer exists. Its output is what turns config
``oa_dev_slate.competitions`` from empty into chosen; fixture SELECTION within
those competitions is the frozen rule in ``src/wcmodel/eval/dev_slate.py`` and
is untouched by anything measured here.

Output: ``reports/oa_probe.md``, or ``reports/oa_slate_probe.md`` with
``--slate`` (cwd-relative — run from the repo root, like
``scripts/oa_mde.py``).
"""
# No `from __future__ import annotations`: loaded by PATH in tests
# (scripts/ is not on sys.path), matching the oa_mde.py convention.
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from wcmodel.config import load_config
from wcmodel.data.sources.odds import (
    ODDS_RAW_DIR,
    event_list,
    fetch_historical,
    fetch_historical_events,
    parse_snapshot,
    strictest_last_update,
)

# ---------------------------------------------------------------- cost model
# Published Odds-API prices for the historical routes: the events (discovery)
# endpoint bills 1 credit per call; an odds snapshot bills 10 credits PER
# REGION-MARKET. The probe MEASURES whether these hold (the usage headers are
# the readback); the projection the spend gate enforces is built from them.
DISCOVERY_CREDITS = 1
_CREDITS_PER_REGION_MARKET = 10
SNAPSHOTS_PER_FIXTURE = 2            # T-24h and T-1h before kickoff
MARKET = "h2h"
REGIONS = "eu"
# MARKET/REGIONS are comma-joinable strings passed straight to the API, so
# the per-snapshot price is DERIVED from them, never a flat constant: with a
# flat 10, widening REGIONS to "eu,us" left the projection at 315 while the
# true bill would be 615 — the gate would authorize half the real spend.
# Widening now reprices the projection, which trips the pinned 315 loudly.
N_REGION_MARKETS = len(MARKET.split(",")) * len(REGIONS.split(","))
SNAPSHOT_CREDITS = _CREDITS_PER_REGION_MARKET * N_REGION_MARKETS
SHARP_BOOK = "pinnacle"

# Full-program extrapolation base: the 185-pool (wc2022 + euro2024 + wc2026
# group) plus the 32 WC-2026 knockout fixtures = 217 odds-scored fixtures.
# N_dev (the OA-0b development-slate size) stays an explicit formula input.
EVAL_FIXTURES = 217

OUT_DEFAULT = "reports/oa_probe.md"
OUT_SLATE_DEFAULT = "reports/oa_slate_probe.md"

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


# ------------------------------------------- the dev-slate mini-probe (V0)
# A SECOND, much smaller panel answering a DIFFERENT question from
# PROBE_FIXTURES: not "do these 15 known fixtures price?" but "does the
# historical archive carry these candidate DEVELOPMENT competitions at all?".
# Its answer is what turns config `oa_dev_slate.competitions` from empty into
# chosen — the frozen slate rule (src/wcmodel/eval/dev_slate.py) selects
# fixtures WITHIN competitions, never the competitions themselves.
#
# The sport keys below are CANDIDATES — hypotheses this probe exists to
# verify, exactly like `odds.sport_keys` for the eval panel. A wrong key costs
# ONE discovery credit and lands in the report as a finding; correcting it is
# a one-line data edit here, no logic change. Each `date` is a day the martj42
# store actually holds senior men's internationals of that `tournament`
# (pinned by tests/eval/test_probe_slate.py), each sits inside the frozen dev
# window [2022-01-01, 2025-12-31], and no probed (tournament, date) names a
# day holding a SCORED fixture of that competition (exact scored-fixture
# membership — the 2026-08-01 pre-lock correction, finding 9) — a probe there
# would measure coverage for fixtures the slate can never hold.
SLATE_PROBES = (
    {"competition": "UEFA Nations League (2022 group stage)",
     "tournament": "UEFA Nations League",
     "sport_key": "soccer_uefa_nations_league", "date": "2022-06-14"},
    {"competition": "UEFA Nations League (2025 quarter-finals)",
     "tournament": "UEFA Nations League",
     "sport_key": "soccer_uefa_nations_league", "date": "2025-03-20"},
    # 2026-08-01 USER-APPROVED addition (G-B sizing): the deterministic
    # earliest-kickoff rule above sampled the 17:00 League-C playout
    # (Armenia v Georgia) and found no Pinnacle — but the G-B question is
    # whether Pinnacle quotes MARQUEE NL ties. Same (sport_key, date): the
    # receipted listing is REUSED (0cr), so this entry costs one snapshot.
    # `teams` precommits the exact fixture — a rule, never wire order.
    {"competition": "UEFA Nations League (2025 QF, marquee tier)",
     "tournament": "UEFA Nations League",
     "sport_key": "soccer_uefa_nations_league", "date": "2025-03-20",
     "teams": ("Netherlands", "Spain")},
    {"competition": "CONCACAF Nations League (2023)",
     "tournament": "CONCACAF Nations League",
     "sport_key": "soccer_concacaf_nations_league", "date": "2023-11-21"},
    # Copa America 2024: ADDED by the 2026-08-01 pre-lock rule correction
    # (Codex batch-1 finding 9, ratified). It ran 2024-06-20..07-14, inside
    # the euro2024 scored-pool CALENDAR window — which the original
    # window-based exclusion read as "contributes nothing", killing an entire
    # eligible development competition that shares not one FIXTURE with the
    # scored pools. Under exact scored-fixture membership its fixtures are
    # all eligible, so the panel probes it.
    {"competition": "Copa América (2024)",
     "tournament": "Copa América",
     "sport_key": "soccer_conmebol_copa_america", "date": "2024-06-22"},
    {"competition": "Africa Cup of Nations qualification (2024)",
     "tournament": "African Cup of Nations qualification",
     "sport_key": "soccer_africa_cup_of_nations_qualification",
     "date": "2024-10-11"},
    {"competition": "AFC Asian Cup (2023/24 finals)",
     "tournament": "AFC Asian Cup",
     "sport_key": "soccer_afc_asian_cup", "date": "2024-01-23"},
    {"competition": "Africa Cup of Nations (2023/24 finals)",
     "tournament": "African Cup of Nations",
     "sport_key": "soccer_africa_cup_of_nations", "date": "2024-01-22"},
    {"competition": "CONCACAF Gold Cup (2023)",
     "tournament": "Gold Cup",
     "sport_key": "soccer_concacaf_gold_cup", "date": "2023-07-16"},
    {"competition": "UEFA Euro 2024 qualification",
     "tournament": "UEFA Euro qualification",
     "sport_key": "soccer_uefa_euro_qualification",
     "date": "2023-06-16"},
    {"competition": "FIFA WC qualification — UEFA (2025)",
     "tournament": "FIFA World Cup qualification",
     "sport_key": "soccer_fifa_world_cup_qualifiers_europe",
     "date": "2025-03-21"},
    {"competition": "FIFA WC qualification — CONMEBOL (2025)",
     "tournament": "FIFA World Cup qualification",
     "sport_key": "soccer_fifa_world_cup_qualifiers_south_america",
     "date": "2025-03-25"},
    {"competition": "FIFA WC qualification — AFC (2024)",
     "tournament": "FIFA World Cup qualification",
     "sport_key": "soccer_fifa_world_cup_qualifiers_asia",
     "date": "2024-06-06"},
    {"competition": "International friendlies (2024 March window)",
     "tournament": "Friendly",
     "sport_key": "soccer_international_friendlies", "date": "2024-03-26"},
)

#: The plan's mini-probe cap, asked alongside G-A. The projection is DERIVED
#: from the panel, so adding a probe reprices it and trips the pinned budget
#: test rather than being discovered at the spend gate.
#: 2026-08-01: 150 -> 165 with the user-approved marquee-NL entry (its
#: modeled 11cr is a ceiling — the shared listing is reused, so it bills 10).
SLATE_CREDIT_BUDGET = 165
SLATE_SNAPSHOT_TAG = "T-1h"
SLATE_SNAPSHOT_DELTA = timedelta(hours=1)


def projected_slate_cost() -> int:
    """13 x (1 discovery + 1 snapshot @ 10) = 143 credits, under the 150 cap.

    The snapshot leg is the CEILING, not a promise: a competition whose
    listing comes back empty never has a snapshot precalled, so an
    uncovered probe costs 1 credit, not 11."""
    return len(SLATE_PROBES) * (DISCOVERY_CREDITS + SNAPSHOT_CREDITS)


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
    """Pre-call modeled-cost abort (the plan's hard gate).

    TWO checks run before EVERY call, and the call is authorized only when
    BOTH fit under the cap:

    - the full-plan projection — modeled spend so far plus the modeled
      remainder, clamped at ``spent + max(remaining, 0)`` — NOT a running
      sum: a running sum would happily place cap-many credits of calls
      before tripping, while this leg trips on the FIRST precall whenever
      the whole plan cannot fit under the cap (zero transport calls, zero
      credits); and
    - the HARD per-call leg, ``spent + credits`` (Codex finding 1): the
      projection alone goes FLAT once actual calls exhaust the modeled
      remainder (``spent + max(remaining, 0) == spent`` when ``remaining <=
      0``), so after the full 315-credit plan an unmodeled ``precall(10)``
      was authorized — spent 325 against cap 315. Counting the call's own
      price before authorization makes the cap a ceiling ``spent`` can
      NEVER cross: an overrunning loop (15 x [1 discovery + THREE
      snapshots] where the model priced two) is refused while ``spent <=
      cap``, not one call after.

    While the calls placed match the modeled plan the two legs coincide
    (``spent + remaining`` is invariant and ``remaining >= credits`` for
    every modeled call), so on the model's own terms only the first precall
    can trip.
    (A ``skip`` hook that shrank the remainder for dropped calls used to live
    here: with a non-increasing projection it could never affect any check —
    dead logic that read as a live safety mechanism, so it was removed.)
    Mid-run aborts on BILLED evidence belong to the ACTUAL-usage check
    (``_UsageRecorder``), which enforces the billing headers this model
    exists to verify.
    ``cap=None`` (dry-run) never aborts — the gate still accounts: ``spent``
    is the modeled spend the report cites, and it counts only calls actually
    HANDED to the transport — suppressed snapshots (event not found,
    discovery failure) are never precalled, and a precalled call the
    actual-usage gate then refuses is refunded (``refund``) by the caller.
    """

    def __init__(self, cap, remaining_planned: int):
        self.cap = cap
        self.remaining = remaining_planned
        self.spent = 0

    def precall(self, credits: int, what: str) -> None:
        # max(remaining, 0): the plan-overrun clamp; spent + credits: the
        # hard per-call leg — BOTH must fit (class docstring).
        projected = max(self.spent + max(self.remaining, 0),
                        self.spent + credits)
        if self.cap is not None and projected > self.cap:
            raise CreditCapError(
                f"projected total {projected} credits exceeds "
                f"--max-credits {self.cap} (before {what}; modeled spend so "
                f"far {self.spent}, this call {credits}) — aborting, no "
                "call placed")
        self.spent += credits
        self.remaining -= credits

    def refund(self, credits: int) -> None:
        """Reverse a precall whose call was then REFUSED before reaching the
        transport (``_UsageRecorder.handle_request`` raises BEFORE placing
        the request): the abort report invites an actual-vs-modeled
        comparison to expose the true per-call price, and a ``spent`` that
        counted the refused call would overstate the modeled side by exactly
        that call's price. Keeps ``spent + remaining`` — the projection —
        unchanged."""
        self.spent -= credits
        self.remaining += credits


class _UsageRecorder(httpx.BaseTransport):
    """Wraps the real transport to read back the billing headers from every
    response — ``x-requests-last`` (the API's own price for that very call),
    ``x-requests-used`` / ``x-requests-remaining`` (the account counters) —
    and to ENFORCE the cap against them: the SpendGate bounds the MODELED
    cost, but the model's per-call prices are exactly what this probe exists
    to verify. Before every call the ACTUAL billed consumption
    (``actual_spent``: summed per-call ``x-requests-last`` costs
    cross-checked against the ``x-requests-used`` counter delta, the LARGER
    standing — the delta alone cannot see the first response's own cost,
    which is how a completed 315-credit run once read back as 314, Codex
    finding 2) PLUS the modeled price of the call about to be placed
    (``next_call_credits``, threaded in by the probe loop) must fit under
    the cap — refusing BEFORE the overspend, never reacting one billed call
    later. The check sits BEFORE the transport is invoked, never after — a
    received response is already paid for and must always reach the
    adapter's archive.
    Lives here rather than widening the adapter (which returns parsed
    payloads, not responses). ``close`` is a no-op: the adapter opens a
    short-lived ``httpx.Client`` PER call, and letting it close the shared
    inner transport would kill the connection pool between calls (harmless
    for MockTransport, fatal for the live HTTPTransport)."""

    def __init__(self, inner: httpx.BaseTransport, cap=None):
        self._inner = inner
        self.cap = cap
        self.usage: list = []
        #: Modeled price of the call about to be placed — set by the probe
        #: loop right before each fetch (DISCOVERY_CREDITS or
        #: SNAPSHOT_CREDITS). Defaults to the LARGEST modeled price so a
        #: future call site that forgets to thread it errs toward refusal,
        #: never toward an authorized overspend.
        self.next_call_credits = SNAPSHOT_CREDITS

    @staticmethod
    def _as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def actual_consumed(self):
        """The ``x-requests-used`` counter delta since the FIRST response —
        ``None`` until two responses carry a parseable value (headers are
        evidence, never assumed present). A LOWER bound on its own: the
        first response's cost predates the first counter reading, so
        ``actual_spent`` folds in the per-call ``x-requests-last`` costs
        that do count it."""
        used = [u for u in (self._as_int(entry["requests_used"])
                            for entry in self.usage) if u is not None]
        if len(used) < 2:
            return None
        return used[-1] - used[0]

    def actual_spent(self):
        """Best evidence of the credits billed to THIS run: the sum of the
        per-call ``x-requests-last`` costs (complete — it counts the first
        call) cross-checked against the counter delta, the LARGER standing
        (partial headers can only ever undercount, so the stricter figure
        wins). ``None`` when neither source has parseable evidence."""
        last = [v for v in (self._as_int(entry.get("requests_last"))
                            for entry in self.usage) if v is not None]
        evidence = [sum(last)] if last else []
        delta = self.actual_consumed()
        if delta is not None:
            evidence.append(delta)
        return max(evidence) if evidence else None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        actual = self.actual_spent()
        if (self.cap is not None and actual is not None
                and actual + self.next_call_credits > self.cap):
            raise CreditCapError(
                f"actual billed usage {actual} credits (summed "
                f"x-requests-last costs cross-checked against the "
                f"x-requests-used delta) plus the next call's modeled price "
                f"{self.next_call_credits} exceeds --max-credits {self.cap} "
                f"— aborting before {request.url.path}, no further call "
                "placed")
        response = self._inner.handle_request(request)
        self.usage.append({
            "path": request.url.path,
            "requests_last": response.headers.get("x-requests-last"),
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
    EXACT-TYPE allowlist on ``httpx.HTTPTransport`` (Codex finding 9):
    ``isinstance`` waved a canned-response HTTPTransport SUBCLASS — pedigree
    without the network, since a subclass overrides ``handle_request`` —
    into the real store with fabricated bytes, exactly the fake the
    allowlist exists to refuse; polarity still matches the adapter's
    ``_resolve_raw_dir`` (ANY injected transport means no archive). The
    adapter's own transport-aware default cannot make this call — the
    usage-recording wrapper makes the transport non-None even on real runs,
    so the probe must pass raw_dir explicitly."""
    return ODDS_RAW_DIR if type(transport) is httpx.HTTPTransport else None


def _preflight_writable(*dirs) -> None:
    """Prove report/provenance storage writable BEFORE any paid call (Codex
    finding 5): persistence runs AFTER a response arrives, so an unwritable
    archive or report destination would otherwise be discovered only once
    money was already spent. Create-then-remove a sentinel file in each
    directory (creating the directory itself if needed) — existence or mode
    checks alone cannot prove writability (ACLs, read-only mounts, full
    disks). ``None`` entries (no archive for this transport) are skipped;
    any OSError propagates to the caller, which aborts at zero credits."""
    for d in dirs:
        if d is None:
            continue
        directory = Path(d)
        directory.mkdir(parents=True, exist_ok=True)
        sentinel = directory / f".writable-preflight.{os.getpid()}.tmp"
        sentinel.write_bytes(b"oa_probe storage preflight")
        sentinel.unlink()


# ----------------------------------------------------------------- the probe
def _norm(name: str) -> str:
    return name.casefold().strip()


def _table_text(text) -> str:
    """Collapse whitespace and escape pipes: EVERY interpolated string —
    error messages, live team names straight off the wire — must survive a
    markdown table cell, or an embedded newline/``|`` splits the committed
    report's results row."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _err_cell(exc: Exception, api_key: str) -> str:
    """Failure text shaped to survive a markdown table cell: httpx messages
    can span lines (the 429's does) and could carry ``|`` — exactly the
    401/429/timeout findings the probe exists to surface. The ACTIVE
    ``api_key`` is redacted here, at the final report sink, for EVERY error
    cell regardless of the exception's origin (Codex finding 8): the
    adapter's redaction covers HTTP-layer messages, but a malformed 200 that
    ECHOES the key back in its payload (e.g. as its timestamp) surfaces it
    in payload-derived ValueError text no HTTP-layer scrub ever sees.
    Redaction runs on the RAW message before pipe-escaping, so a key
    carrying ``|`` still matches. An empty key is skipped —
    ``str.replace("", ...)`` would mangle the message char-by-char."""
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    return f"{type(exc).__name__}: {_table_text(text)}"


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


_LISTED_CAP = 8


def _closest_listed(events: list, fx: dict) -> list:
    """The listing sample a MISS note carries — ranked closest-name-first
    against the probed pair (either orientation), all of it when the slate
    fits under ``_LISTED_CAP``. The Odds API spells teams its own way ("USA",
    "Korea Republic") while the probe spells them like the martj42 store, so
    a spelling mismatch and genuinely absent coverage BOTH read "event
    found: n" — this listing is the ONLY diagnostic separating them, and a
    whole-slate discovery day used to truncate to the FIRST five events,
    dropping the near-miss spelling the reader needed most."""
    want_h, want_a = _norm(fx["home"]), _norm(fx["away"])

    def closeness(event: dict) -> float:
        got_h, got_a = _norm(event["home"] or ""), _norm(event["away"] or "")
        straight = (SequenceMatcher(None, want_h, got_h).ratio()
                    + SequenceMatcher(None, want_a, got_a).ratio())
        flipped = (SequenceMatcher(None, want_h, got_a).ratio()
                   + SequenceMatcher(None, want_a, got_h).ratio())
        return max(straight, flipped)

    ranked = sorted(events, key=closeness, reverse=True)
    return [f"{e['home']} v {e['away']}" for e in ranked[:_LISTED_CAP]]


def _probe_snapshot(fx: dict, event, tag: str, requested: datetime, *,
                    commence: datetime, sport_key: str, api_key: str,
                    transport, raw_dir) -> dict:
    # Every RETURNED entry was attempted: the only pre-wire refusal is
    # CreditCapError, which propagates instead of returning — the caller's
    # pre-seeded ``attempted: False`` entry then stands. (An OSError also
    # propagates, but it is POST-wire — the archive failed on a placed,
    # paid call — and the caller marks it attempted+error before aborting,
    # Codex finding 5.)
    entry = {"tag": tag, "requested_ts": _iso(requested), "attempted": True}
    try:
        snap = fetch_historical(
            event["event_id"], _iso(requested), api_key, market=MARKET,
            regions=REGIONS, sport_key=sport_key, raw_dir=raw_dir,
            transport=transport)
        # Provenance FIRST: the archived hash must survive any parse or
        # arithmetic surprise below — the bytes it names are already paid for.
        entry["raw_sha256"] = snap.get("raw_sha256")
        # Event identity (Codex finding 3): a paid per-event response for
        # the WRONG fixture must never read as coverage — the T3 shape guard
        # proves {timestamp, data}, not WHICH event was priced. Whenever the
        # payload names an event id or sport_key, it must match the
        # request/discovery row; a mismatch is a loud per-fixture error
        # naming both sides and citing the archived hash (the bytes are
        # paid for and auditable), caught below as an ERR cell.
        got_events = event_list(snap.get("data"))
        got_ids = {e.get("id") for e in got_events if e.get("id")}
        if got_ids and got_ids != {event["event_id"]}:
            raise ValueError(
                "event identity mismatch on a PAID snapshot: requested "
                f"event_id {event['event_id']} but the response answers for "
                f"{', '.join(sorted(got_ids))} (archived raw_sha256="
                f"{snap.get('raw_sha256')}) — never coverage for this "
                "fixture")
        got_sports = {e.get("sport_key") for e in got_events
                      if e.get("sport_key")}
        if got_sports and got_sports != {sport_key}:
            raise ValueError(
                "sport_key mismatch on a PAID snapshot: requested "
                f"{sport_key} but the response answers for "
                f"{', '.join(sorted(got_sports))} (archived raw_sha256="
                f"{snap.get('raw_sha256')}) — never coverage for this "
                "fixture")
        rows = parse_snapshot(snap)
        pin = [r for r in rows if r["bookmaker"] == SHARP_BOOK]
        snap_dt = _ts(snap["timestamp"])
        entry.update({
            "snapshot_ts": snap["timestamp"],
            "drift_min": round((requested - snap_dt).total_seconds() / 60.0,
                               1),
            "pinnacle_present": bool(pin),
            "n_bookmakers": len({r["bookmaker"] for r in rows}),
        })
        stamps = [("snapshot ts", snap_dt)]
        if pin:
            lu = strictest_last_update(pin[0], snap["timestamp"])
            entry["pinnacle_staleness_min"] = round(
                (requested - lu).total_seconds() / 60.0, 1)
            stamps.append(("Pinnacle strictest last_update", lu))
        # The strict pre-kickoff rule (admissible_quote's convention, OA F2):
        # an at/after-kickoff stamp on EITHER leg is an in-play price, never
        # a pre-kickoff quote. Without this guard a snapshot taken mid-match
        # reports "Pinnacle present: y" with empty notes — a false positive
        # on the exact claim the purchase decision rests on, signaled only by
        # a negative drift the report would not define. _iso re-renders the
        # parsed stamps, so no raw wire string enters the table cell.
        late = [f"{what} {_iso(dt)}" for what, dt in stamps
                if dt >= commence]
        if late:
            entry["in_play"] = (
                f"IN-PLAY {tag}: " + " and ".join(late)
                + f" at/after kickoff {_iso(commence)} — an in-play price, "
                "never a pre-kickoff quote (strict <, OA F2)")
    except CreditCapError:
        raise                    # the spend gate is an abort, never a note
    except OSError:
        # Archive/persistence failure on a PLACED, PAID call: provenance
        # storage is broken, so this is FATAL — never a coverage note that
        # lets spending continue (Codex finding 5). The caller records it
        # and aborts the run.
        raise
    except Exception as exc:
        # A 401/429/timeout — or a 200 whose body trips the identity/parse/
        # arithmetic legs above — is a FINDING for the coverage report, not
        # a crash that discards the fixtures already paid for. _err_cell
        # redacts the active key from the text (Codex finding 8): the
        # adapter strips it from HTTP-layer messages, but payload-derived
        # text can ECHO it (a malformed 200 with the key as its timestamp).
        entry["error"] = _err_cell(exc, api_key)
    return entry


def run_probe(*, api_key: str, transport: httpx.BaseTransport,
              max_credits, raw_dir, sport_keys: dict) -> dict:
    """Run the 15-fixture probe through ``transport``. Every call passes the
    SpendGate AND the actual-usage check FIRST. Returns ``{"results",
    "usage", "spent", "projected", "aborted", "actual", "overrun"}`` —
    ``aborted`` carries the abort's message when the run stopped mid-flight
    AFTER paid calls: a cap breach, or an archive/persistence OSError (Codex
    finding 5 — provenance storage broke, so spending stops at the FIRST
    one). The partial results are still the user's, so they still get
    reported, with every refused or unreached call marked ``attempted:
    False`` — never rendered as a measured miss; a cap breach before ANY
    call re-raises, since there is nothing paid for to report.
    ``overrun`` flags the case the pre-call checks cannot see: actual billed
    usage above the cap first revealed by the FINAL response, when no next
    call remains to refuse."""
    recorder = _UsageRecorder(transport, cap=max_credits)
    projected = projected_probe_cost()
    gate = SpendGate(max_credits, projected)
    results = []
    aborted = None

    def _pad_unreached():
        # Every fixture the loop never reached still gets a row — explicitly
        # not-attempted, so the PARTIAL report keeps the full 15-fixture
        # frame instead of silently dropping the tail.
        for fx in PROBE_FIXTURES[len(results):]:
            results.append({"pool": fx["pool"], "stratum": fx["stratum"],
                            "fixture": _label(fx),
                            "sport_key": sport_keys[fx["pool"]],
                            "attempted": False, "snapshots": []})

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
                recorder.next_call_credits = DISCOVERY_CREDITS
                try:
                    discovery = fetch_historical_events(
                        key, f"{fx['date']}T00:00:00Z", api_key,
                        raw_dir=raw_dir, transport=recorder)
                except CreditCapError:
                    # Refused by the ACTUAL-usage gate BEFORE reaching the
                    # transport (handle_request checks first): never placed,
                    # so the modeled spend must not count it — the abort
                    # report invites an actual-vs-modeled comparison and one
                    # phantom call distorts the per-call price it exposes.
                    gate.refund(DISCOVERY_CREDITS)
                    raise
                row["attempted"] = True
                # Response-level provenance FIRST (Codex finding 4): the
                # archived discovery hash must survive EVERY branch below —
                # an empty listing, a miss, a naive-timestamp parse failure.
                # Attached per-event it died with the rows exactly where a
                # coverage dispute needs it ("event found: n" cited nothing).
                row["discovery_sha256"] = discovery["raw_sha256"]
                events = discovery["events"]
                row["n_events_listed"] = len(events)
                event, flipped = _match_event(events, fx)
                row["event_found"] = event is not None
                if event is None:
                    # No event id -> the snapshot precalls simply never
                    # happen (the modeled spend never counts them). Record
                    # what discovery DID return — that listing is the
                    # coverage evidence read at the gate, ranked so a
                    # near-miss spelling survives the cap.
                    row["listed"] = _closest_listed(events, fx)
                    continue
                row.update({"event_id": event["event_id"],
                            "commence_time": event["commence_time"],
                            "orientation_flipped": flipped})
                commence = _ts(event["commence_time"])
            except CreditCapError:
                raise            # the spend gate is an abort, never a note
            except OSError as exc:
                # The discovery call was PLACED and paid, but its raw bytes
                # could not be archived: record it honestly, then abort —
                # FATAL, never a coverage note (Codex finding 5).
                row["attempted"] = True
                row["error"] = _err_cell(exc, api_key)
                raise
            except Exception as exc:
                # ANY per-fixture surprise — HTTP, refused shape, a field the
                # adapter's comprehension trips on — is a FINDING, not a
                # crash that discards the fixtures already paid for. Only the
                # cap refuses pre-wire (and it re-raises above), so this call
                # was attempted.
                row["attempted"] = True
                row["error"] = _err_cell(exc, api_key)
                continue
            planned = []
            for tag, delta in (("T-24h", timedelta(hours=24)),
                               ("T-1h", timedelta(hours=1))):
                requested = commence - delta
                # BOTH entries appended BEFORE the FIRST gate: an abort
                # landing on the T-24h call must leave the T-1h entry
                # standing as an explicit not-attempted marker — appended
                # per-iteration it would not exist at all, and _snapshot_cell
                # would render the "-" of a measured miss on the closing-line
                # proxy itself, with no textual disambiguation in the row.
                entry = {"tag": tag, "requested_ts": _iso(requested),
                         "attempted": False}
                row["snapshots"].append(entry)
                planned.append((tag, requested, entry))
            for tag, requested, entry in planned:
                gate.precall(SNAPSHOT_CREDITS, f"snapshot {tag} {_label(fx)}")
                recorder.next_call_credits = SNAPSHOT_CREDITS
                try:
                    entry.update(_probe_snapshot(
                        fx, event, tag, requested, commence=commence,
                        sport_key=key, api_key=api_key, transport=recorder,
                        raw_dir=raw_dir))
                except CreditCapError:
                    gate.refund(SNAPSHOT_CREDITS)   # same contract as discovery
                    raise
                except OSError as exc:
                    # Placed and paid (the response arrived; only its
                    # archival failed) — NO refund, recorded as attempted
                    # with the failure, then FATAL (Codex finding 5).
                    entry.update({"attempted": True,
                                  "error": _err_cell(exc, api_key)})
                    raise
    except CreditCapError as exc:
        if not recorder.usage:
            raise                # zero calls placed: nothing paid, no report
        aborted = str(exc)
        _pad_unreached()
    except OSError as exc:
        # Archive/persistence failure (Codex finding 5): provenance storage
        # is broken, so no further paid call may be placed — an ABORT in the
        # report, never a coverage cell that lets the run march on. The call
        # that hit it was paid (its response arrived), so the partial report
        # is owed regardless.
        aborted = ("archive/persistence failure — provenance storage is "
                   "broken, so no further paid call may be placed: "
                   + _err_cell(exc, api_key))
        _pad_unreached()
    actual = recorder.actual_spent()
    overrun = None
    if (aborted is None and max_credits is not None and actual is not None
            and actual > max_credits):
        # The pre-call checks can only refuse the NEXT call — a breach first
        # revealed by the FINAL response has no next call, so it is caught
        # here: the completed run still fails loudly instead of exiting 0.
        overrun = (
            f"actual billed usage {actual} credits (summed x-requests-last "
            "costs cross-checked against the x-requests-used delta) exceeds "
            f"--max-credits {max_credits} and no further call remained to "
            "refuse — the plan completed, but the cap did not hold")
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
        f"[T-24h, T-1h; {MARKET} x {REGIONS} = {N_REGION_MARKETS} "
        f"region-market{'s' if N_REGION_MARKETS != 1 else ''}] @ "
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
    # The instants the probe actually bought, per fixture — WITH the
    # discovered kickoff, so a reader can reconstruct the pre-kickoff check
    # by hand instead of trusting an unlabeled negative drift.
    lines += [
        "", "## Requested instants (discovered kickoff -> the two snapshot "
        "requests)", "",
        "Sign convention in the results table: drift = requested - snapshot "
        "ts, staleness = requested - Pinnacle's strictest last_update (both "
        "in minutes; NEGATIVE means the stamp postdates the requested "
        "instant). The strict pre-kickoff rule (OA F2, admissible_quote): a "
        "snapshot ts or last_update at/after the discovered kickoff is an "
        "IN-PLAY price and is flagged in the notes column — never a clean "
        "pre-kickoff quote.", "",
        "| fixture | discovered kickoff | requested T-24h | requested T-1h |",
        "|---|---|---|---|"]
    for row in results:
        req = {s["tag"]: s.get("requested_ts")
               for s in row.get("snapshots", [])}
        kick = row.get("commence_time")
        lines.append("| " + " | ".join([
            row["fixture"],
            _table_text(kick) if kick else "-",     # a wire string: cell-safe
            req.get("T-24h") or "-", req.get("T-1h") or "-"]) + " |")
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
            # exists to surface. The caveat is load-bearing: the API spells
            # teams its own way, so without it a spelling mismatch reads as
            # absent coverage on the observable the purchase decision rests
            # on.
            notes = _table_text(
                "not among " + str(row.get("n_events_listed")) +
                " listed events (closest names first, up to "
                f"{_LISTED_CAP}; the API spells teams its own way — e.g. "
                "'USA'/'Korea Republic' for the store's 'United States'/"
                "'South Korea' — so a spelling mismatch here reads exactly "
                "like absent coverage; rule that out against these names "
                "before concluding the event is missing): "
                + "; ".join(row.get("listed", [])))
        else:
            notes = "; ".join(
                (["orientation flipped vs store"]
                 if row.get("orientation_flipped") else [])
                + [s["error"] for s in row["snapshots"] if "error" in s]
                + [s["in_play"] for s in row["snapshots"] if "in_play" in s]
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
    # FULL digests (Codex finding 4): a truncated 12-hex prefix cannot be
    # re-verified against the content-addressed archive — the whole point of
    # citing the hash is that the exact bytes can be re-audited by name.
    lines += ["", "Provenance (full sha256 of the archived raw response; "
              "dry-run hashes are of MOCK bytes and are not persisted):", ""]
    for row in results:
        shas = [f"discovery {row['discovery_sha256']}"] \
            if row.get("discovery_sha256") else []
        shas += [f"{s['tag']} {s['raw_sha256']}"
                 for s in row.get("snapshots", []) if s.get("raw_sha256")]
        lines.append(f"- {row['fixture']}: " + (", ".join(shas) or "-"))
    lines += ["", "## Actual usage (`x-requests-last` / `x-requests-used` / "
              "`x-requests-remaining` headers)", ""]
    if mode == "dry-run":
        lines += ["Not available: dry-run serves no live responses, so no "
                  "usage headers exist (and none are fabricated)."]
    elif not usage:
        lines += ["No responses received."]
    else:
        lines += ["| call | path | x-requests-last | x-requests-used | "
                  "x-requests-remaining |",
                  "|---|---|---|---|---|"]
        lines += [f"| {i} | `{u['path']}` | {_fmt(u.get('requests_last'))} | "
                  f"{_fmt(u['requests_used'])} | "
                  f"{_fmt(u['requests_remaining'])} |"
                  for i, u in enumerate(usage, 1)]
        # The deliverable STATES actual-billed vs cap vs modeled — the
        # reader at the spend gate must never hand-subtract the table.
        lines += [
            "",
            "Actual billed this run: "
            + (f"**{actual} credits**" if actual is not None
               else "unknown (no parseable `x-requests-last` cost and fewer "
                    "than two parseable `x-requests-used` counters)")
            + " — the LARGER of the summed per-call `x-requests-last` costs "
              "and the `x-requests-used` counter delta (the delta alone "
              "cannot see the first response's own cost, so where "
              "`x-requests-last` is absent the true spend can be up to one "
              "call price higher) — vs `--max-credits` "
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


# ------------------------------------------------- the dev-slate mini-probe
def build_slate_call_plan() -> list:
    """One row per planned call (26 = 13 discovery + 13 snapshots). The
    snapshot's ``at`` is symbolic: it depends on the DISCOVERED kickoff of the
    deterministically chosen event."""
    rows = []
    for probe in SLATE_PROBES:
        key = probe["sport_key"]
        base = {"competition": probe["competition"], "sport_key": key,
                "tournament": probe["tournament"]}
        rows.append({**base, "call": "discovery",
                     "endpoint": f"/v4/historical/sports/{key}/events",
                     "at": f"{probe['date']}T00:00:00Z",
                     "credits": DISCOVERY_CREDITS})
        rows.append({**base, "call": f"snapshot {SLATE_SNAPSHOT_TAG}",
                     "endpoint": (f"/v4/historical/sports/{key}"
                                  "/events/{event_id}/odds"),
                     "at": f"discovered kickoff {SLATE_SNAPSHOT_TAG}",
                     "credits": SNAPSHOT_CREDITS})
    return rows


def _slate_dry_run_transport() -> httpx.MockTransport:
    """Recorded-shape mock payloads for the slate panel — same geometry as the
    eval dry-run (3-min snapshot lag, Pinnacle 10 min older), so the report's
    arithmetic is pinned by the same conventions."""
    # A (sport_key, instant) can be shared by several probes (the marquee-NL
    # entry reuses the QF listing), so the mock listing carries EVERY sharing
    # probe's events — exactly as one real listing serves them all.
    by_key: dict = {}
    for p in SLATE_PROBES:
        by_key.setdefault(
            (p["sport_key"], f"{p['date']}T00:00:00Z"), []).append(p)

    def _mock_event(probe: dict, index: int) -> dict:
        # ids carry the date too: two probes on one sport key must never
        # collide in `by_event`.
        if probe.get("teams") and index == 0:
            home, away = probe["teams"]
        else:
            home = f"Mock {probe['tournament']} Home {index}"
            away = f"Mock {probe['tournament']} Away {index}"
        return {"id": f"mock_slate_{probe['sport_key']}_{probe['date']}"
                      f"_{'t' if probe.get('teams') else 'p'}_{index}",
                "commence_time": f"{probe['date']}T{18 + index}:00:00Z",
                "home_team": home, "away_team": away}

    by_event = {_mock_event(p, i)["id"]: (p, i)
                for p in SLATE_PROBES for i in (0, 1)}

    def handler(request: httpx.Request) -> httpx.Response:
        requested = request.url.params["date"]
        parts = request.url.path.split("/")
        if request.url.path.endswith("/events"):
            probes = by_key[(parts[4], requested)]
            # Listed out of chronological order on purpose: the deterministic
            # pick must not inherit the wire's ordering.
            listed = [_mock_event(p, i) for p in probes for i in (1, 0)]
            return httpx.Response(200, json={
                "timestamp": requested, "previous_timestamp": requested,
                "next_timestamp": requested, "data": listed})
        probe, index = by_event[parts[6]]
        event = _mock_event(probe, index)
        ts = _ts(requested) - _MOCK_SNAPSHOT_LAG
        outcomes = [{"name": event["home_team"], "price": 2.10},
                    {"name": "Draw", "price": 3.30},
                    {"name": event["away_team"], "price": 3.60}]
        return httpx.Response(200, json={
            "timestamp": _iso(ts), "previous_timestamp": _iso(ts),
            "next_timestamp": _iso(ts),
            "data": {**event, "bookmakers": [
                {"key": SHARP_BOOK, "last_update": _iso(ts - _MOCK_BOOK_LAG),
                 "markets": [{"key": MARKET,
                              "last_update": _iso(ts - _MOCK_MARKET_LAG),
                              "outcomes": outcomes}]}]}})

    return httpx.MockTransport(handler)


def _pick_slate_event(events: list, teams=None):
    """The event whose snapshot gets bought — chosen by a RULE, never by wire
    order: earliest kickoff, ties broken by event id. Without this, WHICH
    fixture a paid snapshot priced would depend on how the API happened to
    sort its listing, and the probe would not be reproducible.
    Events with an unparseable/absent kickoff are skipped: the snapshot
    instant is derived from it, so there is nothing to request.

    ``teams`` (a probe's optional precommitted pair) restricts the pick to
    events naming exactly that fixture, either orientation — how a panel
    entry targets a SPECIFIC tie (the 2026-08-01 marquee-NL question)
    instead of whatever kicks off first."""
    wanted = {str(t) for t in teams} if teams else None
    usable = []
    for event in events:
        try:
            if wanted is not None and \
                    {str(event.get("home")), str(event.get("away"))} != wanted:
                continue
            usable.append((_ts(event["commence_time"]),
                           str(event["event_id"]), event))
        except (KeyError, TypeError, ValueError):
            continue
    if not usable:
        return None
    return min(usable, key=lambda row: (row[0], row[1]))[2]


def _slate_snapshot_entry(snap: dict, requested: datetime, *,
                          commence: datetime) -> dict:
    """PURE evaluation of one slate snapshot payload -> the report fields.
    Split from the fetch (finding 1) so the journaled acquisition path can
    evaluate an ARCHIVE-REUSED payload identically to a fresh wire one."""
    entry = {"raw_sha256": snap.get("raw_sha256")}
    rows = parse_snapshot(snap)
    pin = [r for r in rows if r["bookmaker"] == SHARP_BOOK]
    snap_dt = _ts(snap["timestamp"])
    entry.update({
        "snapshot_ts": snap["timestamp"],
        "drift_min": round((requested - snap_dt).total_seconds() / 60.0, 1),
        "pinnacle_present": bool(pin),
        "n_bookmakers": len({r["bookmaker"] for r in rows}),
    })
    stamps = [("snapshot ts", snap_dt)]
    if pin:
        lu = strictest_last_update(pin[0], snap["timestamp"])
        entry["pinnacle_staleness_min"] = round(
            (requested - lu).total_seconds() / 60.0, 1)
        stamps.append(("Pinnacle strictest last_update", lu))
    late = [f"{what} {_iso(dt)}" for what, dt in stamps if dt >= commence]
    if late:
        entry["in_play"] = (
            "IN-PLAY: " + " and ".join(late)
            + f" at/after kickoff {_iso(commence)} — an in-play price, "
            "never a pre-kickoff quote (strict <, OA F2)")
    return entry


def _slate_snapshot(event: dict, requested: datetime, *, commence: datetime,
                    sport_key: str, api_key: str, transport, raw_dir) -> dict:
    """One pre-kickoff snapshot on the chosen event: does the sharp book quote
    this competition at all, and how stale is the line? Same failure contract
    as ``_probe_snapshot`` — the cap aborts, an archive failure is fatal,
    anything else is a per-competition finding."""
    entry = {"tag": SLATE_SNAPSHOT_TAG, "requested_ts": _iso(requested),
             "attempted": True}
    try:
        snap = fetch_historical(
            event["event_id"], _iso(requested), api_key, market=MARKET,
            regions=REGIONS, sport_key=sport_key, raw_dir=raw_dir,
            transport=transport)
        # Provenance FIRST (the eval probe's rule): the archived hash must
        # survive any parse surprise in the evaluator below.
        entry["raw_sha256"] = snap.get("raw_sha256")
        entry.update(_slate_snapshot_entry(snap, requested,
                                           commence=commence))
    except CreditCapError:
        raise
    except OSError:
        raise
    except Exception as exc:
        entry["error"] = _err_cell(exc, api_key)
    return entry


def run_slate_probe(*, api_key: str, transport: httpx.BaseTransport,
                    max_credits, raw_dir) -> dict:
    """Run the dev-slate mini-probe. Same gates and same return shape as
    ``run_probe`` (``results``/``usage``/``spent``/``projected``/``aborted``/
    ``actual``/``overrun``), so the CLI, the cap enforcement and the abort
    reporting are shared rather than re-derived."""
    recorder = _UsageRecorder(transport, cap=max_credits)
    projected = projected_slate_cost()
    gate = SpendGate(max_credits, projected)
    results = []
    aborted = None

    def _pad_unreached():
        for probe in SLATE_PROBES[len(results):]:
            results.append({"competition": probe["competition"],
                            "sport_key": probe["sport_key"],
                            "date": probe["date"],
                            "tournament": probe["tournament"],
                            "attempted": False, "snapshot": None})

    try:
        for probe in SLATE_PROBES:
            key = probe["sport_key"]
            row = {"competition": probe["competition"], "sport_key": key,
                   "date": probe["date"], "tournament": probe["tournament"],
                   "attempted": False, "snapshot": None}
            results.append(row)
            try:
                gate.precall(DISCOVERY_CREDITS, f"discovery {probe['competition']}")
                recorder.next_call_credits = DISCOVERY_CREDITS
                try:
                    discovery = fetch_historical_events(
                        key, f"{probe['date']}T00:00:00Z", api_key,
                        raw_dir=raw_dir, transport=recorder)
                except CreditCapError:
                    gate.refund(DISCOVERY_CREDITS)
                    raise
                row["attempted"] = True
                row["discovery_sha256"] = discovery["raw_sha256"]
                events = discovery["events"]
                row["n_events_listed"] = len(events)
                event = _pick_slate_event(events, teams=probe.get("teams"))
                if event is None:
                    # No listing -> no snapshot precall at all: an uncovered
                    # competition costs ONE credit, and "no coverage" is
                    # reported from what discovery actually returned.
                    continue
                row.update({"event_id": event["event_id"],
                            "commence_time": event["commence_time"],
                            "sample_fixture": f"{event['home']} v {event['away']}"})
                commence = _ts(event["commence_time"])
            except CreditCapError:
                raise
            except OSError as exc:
                row["attempted"] = True
                row["error"] = _err_cell(exc, api_key)
                raise
            except Exception as exc:
                # A wrong candidate sport key is exactly what this probe is
                # for: a finding for the report, never a crash that discards
                # the competitions already measured.
                row["attempted"] = True
                row["error"] = _err_cell(exc, api_key)
                continue
            requested = commence - SLATE_SNAPSHOT_DELTA
            entry = {"tag": SLATE_SNAPSHOT_TAG, "requested_ts": _iso(requested),
                     "attempted": False}
            row["snapshot"] = entry
            gate.precall(SNAPSHOT_CREDITS,
                         f"snapshot {SLATE_SNAPSHOT_TAG} {probe['competition']}")
            recorder.next_call_credits = SNAPSHOT_CREDITS
            try:
                entry.update(_slate_snapshot(
                    event, requested, commence=commence, sport_key=key,
                    api_key=api_key, transport=recorder, raw_dir=raw_dir))
            except CreditCapError:
                gate.refund(SNAPSHOT_CREDITS)
                raise
            except OSError as exc:
                entry.update({"attempted": True,
                              "error": _err_cell(exc, api_key)})
                raise
    except CreditCapError as exc:
        if not recorder.usage:
            raise
        aborted = str(exc)
        _pad_unreached()
    except OSError as exc:
        aborted = ("archive/persistence failure — provenance storage is "
                   "broken, so no further paid call may be placed: "
                   + _err_cell(exc, api_key))
        _pad_unreached()
    actual = recorder.actual_spent()
    overrun = None
    if (aborted is None and max_credits is not None and actual is not None
            and actual > max_credits):
        overrun = (
            f"actual billed usage {actual} credits (summed x-requests-last "
            "costs cross-checked against the x-requests-used delta) exceeds "
            f"--max-credits {max_credits} and no further call remained to "
            "refuse — the plan completed, but the cap did not hold")
    return {"results": results, "usage": recorder.usage,
            "spent": gate.spent, "projected": projected, "aborted": aborted,
            "actual": actual, "overrun": overrun}


def _slate_notes(row: dict) -> str:
    if "error" in row:
        return row["error"]
    if not row.get("attempted", True):
        return ("not attempted: the run aborted before this competition's "
                "discovery call was placed")
    if not row.get("event_id"):
        return _table_text(
            f"no usable event in the {row.get('n_events_listed')} listed for "
            f"`{row['sport_key']}` on {row['date']} — either the archive does "
            "not carry this competition or the CANDIDATE sport key is wrong; "
            "both read the same here, so rule the key out before concluding "
            "the competition is absent")
    snap = row.get("snapshot") or {}
    parts = [f"sample fixture: {_table_text(row.get('sample_fixture'))}"]
    if not snap.get("attempted", True):
        parts.append("snapshot not attempted (run aborted)")
    for field in ("error", "in_play"):
        if field in snap:
            parts.append(snap[field])
    return "; ".join(parts)


def assemble_slate_report(*, mode: str, mocked: bool, plan: list,
                          projected: int, spent: int, results: list,
                          usage: list, aborted=None, cap=None, actual=None,
                          overrun=None) -> str:
    """Pure: canned inputs -> the full markdown mini-probe report."""
    lines = ["# OA dev-slate mini-probe — which development competitions does "
             "the archive carry? (OA Plan 2 v2, V0)", ""]
    lines += _mode_banner(mode, mocked)
    lines += [
        "", "Every `sport_key` below is a **CANDIDATE**: a hypothesis this "
        "probe exists to verify, exactly as `odds.sport_keys` were for the "
        "OA-0a eval panel. A wrong key costs one discovery credit and shows "
        "up here as a finding — correcting it is a one-line edit to "
        "`SLATE_PROBES`, not a logic change. Competitions are named in the "
        "martj42 store's vocabulary (`tournament`), because that is what "
        "`oa_dev_slate.competitions` is keyed by.", "",
        "This probe chooses the COMPETITIONS. Fixture SELECTION within them "
        "is the frozen rule in `src/wcmodel/eval/dev_slate.py` and is not "
        "affected by anything measured here."]
    if aborted:
        lines += ["", f"**RUN ABORTED MID-FLIGHT: {aborted}** Partial "
                  "results only; every refused or unreached call is marked "
                  "\"not attempted\" — a refusal by our own gate, never a "
                  "measured miss."]
    lines += [
        "", "## Call plan + projected credit cost", "",
        f"{len(SLATE_PROBES)} competitions x (1 discovery @ "
        f"{DISCOVERY_CREDITS} credit + 1 snapshot [{SLATE_SNAPSHOT_TAG}; "
        f"{MARKET} x {REGIONS}] @ {SNAPSHOT_CREDITS} credits) = "
        f"**{projected} credits** projected, against the plan's "
        f"{SLATE_CREDIT_BUDGET}-credit mini-probe budget; modeled spend this "
        f"run: {spent}"
        + (" (dry-run: 0 actually billed)." if mode == "dry-run" else "."),
        "", "The snapshot leg is a CEILING: a competition whose listing comes "
        "back empty never has its snapshot precalled, so an uncovered probe "
        "costs 1 credit, not 11.", "",
        "| # | competition | store tournament | candidate sport_key | call | "
        "endpoint | at | credits |",
        "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {i} | {r['competition']} | {r['tournament']} | "
              f"`{r['sport_key']}` | {r['call']} | `{r['endpoint']}` | "
              f"{r['at']} | {r['credits']} |"
              for i, r in enumerate(plan, 1)]
    lines += [
        "", "## Per-competition coverage", "",
        "| competition | candidate sport_key | probed date | events listed | "
        f"Pinnacle {SLATE_SNAPSHOT_TAG} | drift (min) | staleness (min) | "
        "notes |", "|---|---|---|---|---|---|---|---|"]
    for row in results:
        snap = row.get("snapshot") or {}
        if snap and not snap.get("attempted", True):
            pinnacle = drift = stale = "not attempted"
        elif "error" in snap:
            pinnacle = drift = stale = "ERR"
        else:
            pinnacle = _fmt(snap.get("pinnacle_present"))
            drift = _fmt(snap.get("drift_min"))
            stale = _fmt(snap.get("pinnacle_staleness_min"))
        lines.append("| " + " | ".join([
            row["competition"], f"`{row['sport_key']}`", row["date"],
            _fmt(row.get("n_events_listed")), pinnacle, drift, stale,
            _slate_notes(row) or "-"]) + " |")
    lines += ["", "Provenance (full sha256 of the archived raw response; "
              "dry-run hashes are of MOCK bytes and are not persisted):", ""]
    for row in results:
        shas = [f"discovery {row['discovery_sha256']}"] \
            if row.get("discovery_sha256") else []
        snap = row.get("snapshot") or {}
        if snap.get("raw_sha256"):
            shas.append(f"{SLATE_SNAPSHOT_TAG} {snap['raw_sha256']}")
        lines.append(f"- {row['competition']}: " + (", ".join(shas) or "-"))
    lines += ["", "## Actual usage (`x-requests-last` / `x-requests-used` / "
              "`x-requests-remaining` headers)", ""]
    if mode == "dry-run":
        lines += ["Not available: dry-run serves no live responses, so no "
                  "usage headers exist (and none are fabricated)."]
    elif not usage:
        lines += ["No responses received."]
    else:
        lines += ["| call | path | x-requests-last | x-requests-used | "
                  "x-requests-remaining |", "|---|---|---|---|---|"]
        lines += [f"| {i} | `{u['path']}` | {_fmt(u.get('requests_last'))} | "
                  f"{_fmt(u['requests_used'])} | "
                  f"{_fmt(u['requests_remaining'])} |"
                  for i, u in enumerate(usage, 1)]
        lines += [
            "", "Actual billed this run: "
            + (f"**{actual} credits**" if actual is not None
               else "unknown (no parseable `x-requests-last` cost and fewer "
                    "than two parseable `x-requests-used` counters)")
            + f" — vs `--max-credits` {_fmt(cap)}; modeled spend {spent} "
              "credits."]
        if overrun:
            lines += ["", f"**ACTUAL BILLING EXCEEDED THE CAP: {overrun}**"]
    lines += [
        "", "## What this decides", "",
        "- `oa_dev_slate.competitions` (config): the competitions above with "
        "a listing AND a sharp quote. A competition the archive does not "
        "carry cannot contribute dev fixtures at any price.",
        "- `oa_dev_slate.n_dev`: sized from those competitions' fixture "
        "counts against the G-B cap, then frozen — the manifest is hash-bound "
        "into the V8 lock, so N_dev is pre-registered, never a yield.",
        "- Neither is decided here by an agent: both land in config as the "
        "user's call at the spend gate."]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------- CLI
def _acquire_module():
    """``oa_acquire``, loaded lazily (``scripts/`` is not a package on
    ``sys.path``): the LIVE slate path routes through ITS journal machinery
    (plan2 batch-1, finding 1) — the exclusive flock, the fail-closed orphan
    check, intent->receipt around every paid call, and the cumulative G-A
    gate cap. Lazy so importing the probe never imports the runner."""
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import oa_acquire
    return oa_acquire


def _run_slate_cli(args, ap) -> int:
    """The ``--slate`` branch: same gates as the eval probe, its own panel,
    its own report. DRY-RUN runs the in-process mini-probe as ever; LIVE
    routes through the canonical G-A journal (finding 1) — the old
    unjournaled live path no longer exists: its spend was invisible to the
    4,800-credit cumulative cap and unprotected by the flock."""
    plan = build_slate_call_plan()
    projected = sum(r["credits"] for r in plan)
    print(f"slate call plan: {len(plan)} calls "
          f"({len(SLATE_PROBES)} discovery + {len(SLATE_PROBES)} snapshots), "
          f"projected {projected} credits (budget {SLATE_CREDIT_BUDGET})")
    for row in plan:
        print(f"  {row['sport_key']:52s} {row['call']:16s} {row['at']:28s} "
              f"{row['credits']:3d}cr  {row['competition']}")

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
        raw_dir = _live_raw_dir(transport)
        if raw_dir is None:
            # The journal's receipts must cite archived paid evidence, and a
            # resumed run reads it instead of re-buying: a transport that
            # cannot produce it must not run the live path at all (the
            # acquisition runner's rule, adopted with its journal).
            print("ABORT: --live with a non-network transport cannot produce "
                  "paid evidence (no raw archive) — refusing to place any "
                  "call", file=sys.stderr)
            return 1
        acq = _acquire_module()
        journal = Path(acq.JOURNAL_DEFAULT)
        try:
            _preflight_writable(raw_dir, Path(args.out).parent,
                                journal.parent)
        except OSError as exc:
            print("ABORT: storage preflight failed — refusing to place any "
                  f"paid call: {exc}", file=sys.stderr)
            return 1
        try:
            out = acq.run_slate_acquisition(
                api_key=api_key, transport=transport, max_credits=cap,
                raw_dir=raw_dir, journal_path=journal)
        except (acq.CreditCapError, acq.AcquisitionError) as exc:
            print(f"ABORT: {exc}", file=sys.stderr)
            return 1
    else:
        mode, transport, cap = "dry-run", _slate_dry_run_transport(), None
        api_key, raw_dir = _DRY_RUN_KEY, None
        try:
            out = run_slate_probe(api_key=api_key, transport=transport,
                                  max_credits=cap, raw_dir=raw_dir)
        except CreditCapError as exc:
            print(f"ABORT: {exc}", file=sys.stderr)
            return 1

    md = assemble_slate_report(
        mode=mode, mocked=type(transport) is not httpx.HTTPTransport,
        plan=plan, projected=out["projected"], spent=out["spent"],
        results=out["results"], usage=out["usage"], aborted=out["aborted"],
        cap=cap, actual=out["actual"], overrun=out["overrun"])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"wrote {out_path}")
    if out["aborted"]:
        print(f"ABORT: {out['aborted']}", file=sys.stderr)
        return 1
    if out["overrun"]:
        print(f"OVER CAP: {out['overrun']}", file=sys.stderr)
        return 1
    return 0


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
    ap.add_argument("--slate", action="store_true",
                    help="run the DEV-SLATE mini-probe instead of the "
                         "15-fixture eval panel: which candidate development "
                         "competitions (2022-2025) does the historical "
                         "archive carry? Same gates, its own panel and "
                         f"report (default {OUT_SLATE_DEFAULT})")
    ap.add_argument("--out", default=None,
                    help=f"report path (default {OUT_DEFAULT}, or "
                         f"{OUT_SLATE_DEFAULT} with --slate)")
    args = ap.parse_args(argv)
    if args.live and args.dry_run:
        ap.error("--live and --dry-run are mutually exclusive")
    if args.out is None:
        args.out = OUT_SLATE_DEFAULT if args.slate else OUT_DEFAULT
    if args.slate:
        return _run_slate_cli(args, ap)

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
        # Storage preflight (Codex finding 5): persistence runs AFTER a
        # response arrives, so writability must be PROVEN before the first
        # paid call — an unwritable archive or report destination aborts
        # here, at zero credits, not after money has nowhere to land.
        try:
            _preflight_writable(raw_dir, Path(args.out).parent)
        except OSError as exc:
            print("ABORT: storage preflight failed — refusing to place any "
                  f"paid call: {exc}", file=sys.stderr)
            return 1
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

    # The banner's mocked/LIVE split runs the SAME EXACT-TYPE ALLOWLIST as
    # _live_raw_dir: only the genuine network transport may print
    # "**MODE: LIVE.**" — the strongest claim on the page, first line read
    # at the spend gate. A denylist on MockTransport waved every OTHER
    # injected fake into the LIVE banner, and isinstance still waved a
    # canned-response HTTPTransport SUBCLASS through (Codex finding 9) —
    # pedigree is not the network when handle_request is overridden.
    md = assemble_report(
        mode=mode, mocked=type(transport) is not httpx.HTTPTransport,
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
