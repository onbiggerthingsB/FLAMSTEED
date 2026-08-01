#!/usr/bin/env python
"""OA acquisition runner — the JOURNALED spend path (OA Plan 2 v2, V1).

The OA-0a probe (``scripts/oa_probe.py``) measured 45 calls once. This runner
places thousands across resumable invocations, so the probe's in-memory gates
are not enough: a crashed run must be resumable without re-buying a call that
may already have billed, a cap must bound the GATE rather than one
invocation, and two runners must never share a budget. Everything below exists
for one of those three reasons (Codex findings 4/7/8).

**The journal** (``data/oa_acquisition_journal.jsonl``, append-only, fsync'd
per record) is the durable spend ledger. Before every call an INTENT record
lands (gate id, call identity, modeled credits); immediately after the
response is archived a RECEIPT lands (the archived ``raw_sha256`` and the
billing headers). A bare INTENT means "a call that may or may not have been
billed", and on resume that FAILS CLOSED: the runner refuses to start and
points the operator at ``data/odds_raw`` for the orphan's bytes. Receipts are
also the skip list — a receipted call is never placed again — and the
cumulative per-gate spend restored into the ``SpendGate``, so
``--max-credits`` caps the GATE total across every resumed run.

**Ingest is a pure, idempotent, atomic rebuild FROM the receipts**, not a
side effect of the call loop. That is why the receipt lands right after the
archive rather than after the store write: a crash between the two costs
nothing (the rerun places no call and rebuilds the store), whereas a receipt
written only after ingest would turn every such crash into a fail-closed
orphan.

**Boundary correctness (finding 7).** The T_issue-cut snapshot is REQUESTED at
08:29:00Z — one minute before the 08:30Z cut — because ``admissible_quote``
is a STRICT ``<``: a returned stamp of exactly 08:30:00Z is inadmissible, and
the historical route answers with the snapshot at or before the requested
instant. Both instants are persisted separately (``requested_instant`` vs
``returned_instant``): what we asked for is a decision, what came back is
evidence. Every request instant derives from the config's venue-LOCAL
matchday and NEVER from ``commence_time.date()`` — South Korea v Czech
Republic is a 20:00 UTC-6 kickoff on matchday 2026-06-11 whose
``commence_time`` reads 2026-06-12, so the UTC calendar day would buy the cut
snapshot six and a half hours AFTER kickoff.

**Discovery is keyed by ``(sport_key, requested_instant)`` (finding 8)**, not
by date: fixtures sharing a key share one paid listing, while two
competitions on the same day are two different resources and stay isolated.
The credit projection is generated mechanically from that plan — never hand
estimated — and is what the cap is checked against.

Modes, exactly as the probe: DEFAULT ``--dry-run`` serves recorded-shape mock
payloads through an in-process transport (zero network, zero credits, the env
``ODDS_API_KEY`` never read) and writes to a SEPARATE dry-run journal, because
the cumulative gate cap is computed from the journal and a fabricated billing
row would authorize real money against imaginary spend. ``--live`` requires
BOTH ``ODDS_API_KEY`` and ``--max-credits`` and is the USER's decision at the
G-A / G-B spend gates — NEVER run by agents.
"""
# No `from __future__ import annotations`: loaded by PATH in tests
# (scripts/ is not on sys.path), matching the oa_probe.py convention.
import argparse
import fcntl
import json
import os
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from wcmodel.config import load_config
from wcmodel.data.sources.odds import (
    ODDS_RAW_DIR,
    admissible_quote,
    event_list,
    fetch_historical,
    fetch_historical_events,
    fsync_dir,
    load_odds_snapshots,
    parse_snapshot,
    strictest_last_update,
)
from wcmodel.data.store import BitemporalStore
from wcmodel.eval.aliases import (
    AmbiguousFixtureMatch,
    load_aliases,
    resolve_event,
    verify_alias_evidence,
)
from wcmodel.eval.dev_slate import (
    eligible_dev_fixtures,
    load_dev_slate_config,
)
from wcmodel.eval.implied import book_overround, is_coherent_book
from wcmodel.eval.ledger import T_ISSUE_UTC_TIME, lock_path

# scripts/ is not a package on sys.path -> path-insert then import (house
# pattern). The probe owns the spend gate, the billing-header enforcement and
# the storage preflight; re-implementing any of them here would be a second
# copy of the code that stands between us and the credit balance.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oa_probe import (  # noqa: E402  (script-local import, after sys.path)
    DISCOVERY_CREDITS,
    MARKET,
    REGIONS,
    SHARP_BOOK,
    SLATE_PROBES,
    SLATE_SNAPSHOT_DELTA,
    SLATE_SNAPSHOT_TAG,
    SNAPSHOT_CREDITS,
    SNAPSHOTS_PER_FIXTURE,
    CreditCapError,
    SpendGate,
    _MOCK_BOOK_LAG,
    _MOCK_SNAPSHOT_LAG,
    _err_cell,
    _fmt,
    _iso,
    _pick_slate_event,
    _preflight_writable,
    _slate_snapshot_entry,
    _table_text,
    _ts,
    _UsageRecorder,
    projected_slate_cost,
)

# ------------------------------------------------------------ the frozen plan
#: The eval-set spend model the G-A cap (4,800) is set against: 217 fixtures x
#: 2 snapshots x 10 credits + one discovery call per distinct
#: (sport_key, venue-local matchday). The day counts are the plan's, and they
#: are the reason discovery is keyed by sport_key as well as instant: wc2022
#: and wc2026 share ``soccer_fifa_world_cup`` (they never share a day), while
#: euro2024 is a different resource entirely.
EVAL_FIXTURES = 217
EVAL_DISCOVERY_DAYS = {"wc2022": 22, "euro2024": 21, "wc2026": 34}

#: 09:00 UTC issuance (the prereg estimand, ``ledger.T_ISSUE_UTC_TIME``) minus
#: ``admissible_quote``'s safety buffer = the 08:30Z cut.
CUT_BUFFER_MINUTES = 30
#: ...and the request sits one minute BEFORE the cut. The rule is a strict
#: ``<``, so a snapshot returned stamped exactly at the cut is inadmissible —
#: requesting the cut instant itself risks paying 10 credits for a quote the
#: analysis must then throw away (finding 7).
CUT_REQUEST_LEAD = timedelta(minutes=1)
#: The second snapshot: a T-24h reference line, off the DISCOVERED kickoff.
T24H_LEAD = timedelta(hours=24)

CUT_TAG = "cut"
T24H_TAG = "T-24h"
SNAPSHOT_TAGS = (T24H_TAG, CUT_TAG)

GATE_IDS = ("ga", "gb")

INTENT = "intent"
RECEIPT = "receipt"

#: cwd-relative like the probe's report path — run from the repo root.
JOURNAL_DEFAULT = "data/oa_acquisition_journal.jsonl"
#: Mock receipts must NEVER enter the paid journal: the cumulative gate cap is
#: computed from it, so a fabricated billing row would authorize real money
#: against imaginary spend.
JOURNAL_DRY_RUN_DEFAULT = "data/oa_acquisition_journal.dry-run.jsonl"
RAW_DIR_DRY_RUN_DEFAULT = "data/odds_raw_dry_run"
STORE_DEFAULT = "data/stores/oa_odds"
OUT_DEFAULT = "reports/oa_acquire_{gate}.md"

_DRY_RUN_KEY = "dry-run-no-key"

_REQUIRED_FIXTURE = ("fixture_id", "pool", "date", "home", "away",
                     "kickoff_utc")


class AcquisitionError(RuntimeError):
    """Base for the runner's own refusals (never a coverage finding)."""


class FixtureManifestError(AcquisitionError):
    """The fixture inventory cannot be turned into a call plan."""


class JournalError(AcquisitionError):
    """The journal is unreadable or self-inconsistent — refuse to spend
    against a spend ledger we cannot trust."""


class OrphanIntentError(AcquisitionError):
    """An INTENT with no RECEIPT: a call that may or may not have billed."""


class ConcurrentAcquisitionError(AcquisitionError):
    """Another runner holds the journal lock — two runners would each restore
    the same cumulative spend and each authorize the whole remaining cap."""


class ArchiveMissingError(AcquisitionError):
    """A receipt cites bytes the content-addressed archive does not hold."""


class AliasEvidenceError(AcquisitionError):
    """An alias record's cited archived evidence is missing or does not
    contain the claimed spelling — an unevidenced alias silently widens what
    counts as coverage, so no live call may be placed under it (finding 8)."""


# ------------------------------------------------------------ instants (F7)
def _day(value) -> str:
    """The venue-LOCAL matchday as padded ISO ``YYYY-MM-DD``.

    A ``datetime`` is REFUSED rather than truncated: passing a kickoff instant
    where the matchday belongs is exactly the bug the rollover test pins, and
    ``commence_time.date()`` would silently produce a plausible-looking day
    that is one calendar day late for every evening Americas kickoff."""
    if isinstance(value, datetime):
        raise FixtureManifestError(
            f"date must be the venue-LOCAL matchday, not a datetime: {value!r}"
            " — deriving it from a kickoff instant lands one day late for "
            "every kickoff that rolls past midnight UTC (finding 7)")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise FixtureManifestError(
            f"date must be ISO YYYY-MM-DD; got {value!r}") from None


def t_issue_for(date) -> datetime:
    """09:00:00 UTC on the venue-local matchday — the prereg issuance instant
    (``ledger.T_ISSUE_UTC_TIME``), imported rather than restated so a prereg
    amendment moves the paid requests with it."""
    hour, minute, second, micro = T_ISSUE_UTC_TIME
    day = datetime.strptime(_day(date), "%Y-%m-%d").date()
    return datetime(day.year, day.month, day.day, hour, minute, second, micro,
                    tzinfo=timezone.utc)


def cut_instant(date) -> datetime:
    """The admissibility cut: ``t_issue`` minus the safety buffer (08:30Z)."""
    return t_issue_for(date) - timedelta(minutes=CUT_BUFFER_MINUTES)


def cut_request_instant(date) -> datetime:
    """The instant the cut snapshot is REQUESTED at: 08:29:00Z."""
    return cut_instant(date) - CUT_REQUEST_LEAD


def discovery_instant(date) -> str:
    """The discovery call's requested instant: midnight UTC on the venue-local
    matchday. Half of the ``(sport_key, requested_instant)`` key."""
    return f"{_day(date)}T00:00:00Z"


# --------------------------------------------------------------- the call plan
def call_id(gate_id, kind, sport_key, requested_instant, fixture_id=None,
            tag=None) -> str:
    """The journal's identity for one paid call — deterministic, so a resumed
    run recognizes what it already bought. A discovery call carries NO fixture
    id: that is precisely how one listing is shared by every fixture on the
    ``(sport_key, requested_instant)`` key."""
    return "|".join([gate_id, kind, sport_key, requested_instant,
                     fixture_id or "-", tag or "-"])


def validate_fixture(fixture, sport_keys) -> dict:
    missing = [f for f in _REQUIRED_FIXTURE if f not in fixture]
    if missing:
        raise FixtureManifestError(
            f"fixture missing field(s) {missing}: {fixture!r}")
    pool = fixture["pool"]
    if pool not in sport_keys:
        raise FixtureManifestError(
            f"pool {pool!r} has no config odds.sport_keys entry "
            f"(known: {sorted(sport_keys)})")
    day = _day(fixture["date"])
    kickoff = _ts(str(fixture["kickoff_utc"]))
    t_issue = t_issue_for(day)
    if t_issue >= kickoff:
        raise FixtureManifestError(
            f"{fixture['fixture_id']}: t_issue {_iso(t_issue)} is not strictly "
            f"before kickoff {_iso(kickoff)} — there is no pre-kickoff quote "
            "to buy on this matchday, and the cut snapshot would be an "
            "in-play price (OA F2)")
    return {"fixture_id": str(fixture["fixture_id"]), "pool": pool,
            "date": day, "home": fixture["home"], "away": fixture["away"],
            "kickoff_utc": kickoff, "sport_key": sport_keys[pool],
            "t_issue": t_issue}


def build_plan(fixtures, sport_keys, gate_id) -> list:
    """The frozen call plan: one discovery group per distinct
    ``(sport_key, requested_instant)``, each carrying its fixtures' two
    snapshot calls. Pure — no journal, no network, no credits."""
    validated = [validate_fixture(fx, sport_keys) for fx in fixtures]
    seen = set()
    for fx in validated:
        if fx["fixture_id"] in seen:
            raise FixtureManifestError(
                f"duplicate fixture_id {fx['fixture_id']!r}: the journal is "
                "keyed by it, so two rows would share one call identity")
        seen.add(fx["fixture_id"])
    groups: dict = {}
    for fx in validated:
        key = (fx["sport_key"], discovery_instant(fx["date"]))
        group = groups.setdefault(key, {
            "gate": gate_id, "sport_key": key[0], "requested_instant": key[1],
            "credits": DISCOVERY_CREDITS, "fixtures": [],
            "call_id": call_id(gate_id, "discovery", key[0], key[1])})
        entry = dict(fx)
        entry["snapshots"] = [
            {"tag": tag,
             "requested_instant": _iso(_snapshot_request(fx, tag)),
             "credits": SNAPSHOT_CREDITS,
             "call_id": call_id(gate_id, "snapshot", fx["sport_key"],
                                _iso(_snapshot_request(fx, tag)),
                                fx["fixture_id"], tag)}
            for tag in SNAPSHOT_TAGS]
        group["fixtures"].append(entry)
    for group in groups.values():
        group["fixtures"].sort(key=lambda f: f["fixture_id"])
    return [groups[key] for key in sorted(groups)]


def _snapshot_request(fixture, tag) -> datetime:
    if tag == CUT_TAG:
        # From the venue-LOCAL matchday. NEVER kickoff_utc.date().
        return cut_request_instant(fixture["date"])
    return fixture["kickoff_utc"] - T24H_LEAD


def plan_rows(groups) -> list:
    """The plan flattened to one row per paid call, in acquisition order."""
    rows = []
    for group in groups:
        rows.append({"kind": "discovery", "gate": group["gate"],
                     "sport_key": group["sport_key"],
                     "requested_instant": group["requested_instant"],
                     "fixture_id": None, "tag": None,
                     "credits": group["credits"],
                     "call_id": group["call_id"]})
        for fixture in group["fixtures"]:
            for snap in fixture["snapshots"]:
                rows.append({"kind": "snapshot", "gate": group["gate"],
                             "sport_key": fixture["sport_key"],
                             "requested_instant": snap["requested_instant"],
                             "fixture_id": fixture["fixture_id"],
                             "tag": snap["tag"], "credits": snap["credits"],
                             "call_id": snap["call_id"]})
    return rows


def project_credits(rows) -> int:
    """The modeled cost of a call plan — mechanical, never hand-estimated."""
    return sum(row["credits"] for row in rows)


def projected_eval_credits() -> int:
    """4,417 = 77 discovery + 217 x 2 x 10 snapshot credits — the plan's FROZEN
    eval-set model, stated in the plan's own terms (``SNAPSHOTS_PER_FIXTURE``)
    rather than in this module's (``SNAPSHOT_TAGS``) on purpose: a third
    snapshot tag added here would reprice ``build_plan`` and diverge from the
    frozen figure, and ``test_acquire`` pins the two against each other so the
    divergence trips loudly instead of quietly re-planning the spend."""
    return (sum(EVAL_DISCOVERY_DAYS.values()) * DISCOVERY_CREDITS
            + EVAL_FIXTURES * SNAPSHOTS_PER_FIXTURE * SNAPSHOT_CREDITS)


# -------------------------------------------------------------- the journal
def journal_lock_path(path) -> Path:
    """The exclusive-lock sidecar (``ledger.lock_path``'s never-unlinked
    convention: unlinking would let a waiter hold the lock on a dead inode
    while the next process creates and locks a fresh one)."""
    return lock_path(path)


def exclusive_journal_lock(path):
    """Context manager: NON-BLOCKING exclusive flock for the whole run.

    Non-blocking on purpose. Two acquisition runners would each restore the
    same cumulative spend from the journal and each authorize the whole
    remaining cap — the cap would hold for neither. A waiting second runner
    would then start the moment the first finished, against a cumulative
    figure it read before the first wrote it. Refusing is the only safe
    answer."""

    @contextmanager
    def _lock():
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(journal_lock_path(target), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ConcurrentAcquisitionError(
                    "another acquisition runner holds "
                    f"{journal_lock_path(target)} — refusing to start: two "
                    "runners restore the same cumulative gate spend and each "
                    "authorize the whole remaining cap") from None
            yield
        finally:
            os.close(fd)     # releases the flock, including on the raising path

    return _lock()


def _write_all(fd, data: bytes) -> None:
    """``os.write`` until every byte lands: a single call may return short,
    and a short journal write is a torn record ``read_journal`` refuses —
    which would jam every future resume of a journal that was in fact fine."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def append_record(path, record) -> None:
    """Append ONE journal record durably.

    ``O_APPEND`` makes the write atomic against concurrent appenders, and the
    ``fsync`` is what makes the record survive the crash it exists to
    describe: an INTENT still in the page cache when the machine dies is an
    INTENT that never happened, and the resumed run would place a call that
    may already have billed. On the append that CREATES the journal the
    parent DIRECTORY is fsync'd too (finding 3): the new directory entry is
    metadata, and fsync'ing only the file leaves durable bytes that no name
    reaches after power loss — the first INTENT would vanish and permit
    rebilling a call that may have been paid."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    existed = target.exists()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        _write_all(fd, line.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    if not existed:
        fsync_dir(target.parent)


#: Fields a RECEIPT must carry (finding 6): a receipt missing any of them is
#: one the writers below could never have produced — spend accounting from it
#: would silently under-count. ``raw_sha256`` may be None (a transport-level
#: failure has no response bytes) but the KEY must be present: an absent key
#: means provenance was never even considered.
_RECEIPT_REQUIRED = ("kind", "requested_instant", "billed_credits",
                     "modeled_credits", "raw_sha256")
#: Fields that must AGREE between a receipt and the intent it settles.
_PAIRED_FIELDS = ("kind", "requested_instant", "fixture_id", "tag")


def _credits_ok(value) -> bool:
    """A journal credit figure: an int >= 1. A paid call is never free —
    a zero/negative/absent figure clears an intent while adding nothing to
    cumulative spend, authorizing real money against it (finding 6)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def read_journal(path) -> list:
    """Parse the journal, refusing anything it cannot fully account for.

    Hardened per finding 6: pairing is keyed by ``(gate, call_id)`` — a G-B
    receipt must never clear a G-A orphan that shares its call_id — every
    RECEIPT requires exactly one preceding still-pending matching INTENT,
    receipts carry all required fields with credits >= 1, and receipt/intent
    disagreement on kind/instant/fixture/tag is refused."""
    target = Path(path)
    if not target.exists():
        return []
    records = []
    pending, receipted = {}, set()          # keyed by (gate, call_id)
    for lineno, line in enumerate(target.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise JournalError(
                f"{target}:{lineno}: unparseable journal line — refusing to "
                "compute cumulative spend from a ledger with a hole in it"
            ) from None
        if not isinstance(record, dict) or record.get("type") not in (
                INTENT, RECEIPT) or not record.get("call_id") \
                or not record.get("gate"):
            raise JournalError(
                f"{target}:{lineno}: journal record must carry type "
                f"(intent|receipt), gate and call_id; got {record!r}")
        key = (record["gate"], record["call_id"])
        if record["type"] == INTENT:
            if not record.get("kind") or not record.get("requested_instant"):
                raise JournalError(
                    f"{target}:{lineno}: INTENT missing kind/"
                    f"requested_instant; got {record!r}")
            if not _credits_ok(record.get("modeled_credits")):
                raise JournalError(
                    f"{target}:{lineno}: INTENT modeled_credits must be an "
                    f"int >= 1 (a paid call is never free); got "
                    f"{record.get('modeled_credits')!r}")
            if key in pending:
                raise JournalError(
                    f"{target}:{lineno}: duplicate pending INTENT for "
                    f"{key} — two intents for one call identity make the "
                    "pending spend unaccountable")
            if key in receipted:
                raise JournalError(
                    f"{target}:{lineno}: INTENT for already-receipted {key} "
                    "— the runner never re-places a receipted call, so this "
                    "record was not written by it")
            pending[key] = record
        else:
            missing = [f for f in _RECEIPT_REQUIRED if f not in record]
            if missing:
                raise JournalError(
                    f"{target}:{lineno}: RECEIPT missing required field(s) "
                    f"{missing}: {record!r}")
            if not _credits_ok(record["billed_credits"]) \
                    or not _credits_ok(record["modeled_credits"]):
                raise JournalError(
                    f"{target}:{lineno}: RECEIPT billed/modeled credits must "
                    "be ints >= 1 (a zero-credit receipt clears an intent "
                    "while adding nothing to cumulative spend); got "
                    f"billed={record['billed_credits']!r} "
                    f"modeled={record['modeled_credits']!r}")
            intent = pending.pop(key, None)
            if intent is None:
                if key in receipted:
                    raise JournalError(
                        f"{target}:{lineno}: duplicate receipt for {key} — "
                        "cumulative spend would double-count a call that "
                        "was billed once")
                raise JournalError(
                    f"{target}:{lineno}: RECEIPT with no preceding pending "
                    f"INTENT for {key} — a receipt the runner never "
                    "intended cannot be spend evidence")
            for field in _PAIRED_FIELDS:
                if record.get(field) != intent.get(field):
                    raise JournalError(
                        f"{target}:{lineno}: RECEIPT disagrees with its "
                        f"INTENT on {field}: "
                        f"{record.get(field)!r} != {intent.get(field)!r} "
                        f"for {key}")
            receipted.add(key)
        records.append(record)
    return records


def orphan_intents(records) -> list:
    """INTENTs with no RECEIPT: calls that may or may not have billed.
    Keyed by ``(gate, call_id)`` — a receipt on the OTHER gate settles
    nothing here (finding 6)."""
    receipted = {(r["gate"], r["call_id"])
                 for r in records if r["type"] == RECEIPT}
    return [r for r in records if r["type"] == INTENT
            and (r["gate"], r["call_id"]) not in receipted]


def gate_spend(records, gate_id) -> int:
    """Cumulative credits charged to ONE gate: every receipt's billed credits
    plus every still-pending intent's modeled credits. The pending term is
    what keeps an ambiguous call on the spending side of the ledger — the
    resume refusal is the loud version of the same rule."""
    rows = [r for r in records if r.get("gate") == gate_id]
    receipted = {r["call_id"] for r in rows if r["type"] == RECEIPT}
    billed = sum(int(r.get("billed_credits") or 0)
                 for r in rows if r["type"] == RECEIPT)
    pending = {r["call_id"]: int(r.get("modeled_credits") or 0)
               for r in rows
               if r["type"] == INTENT and r["call_id"] not in receipted}
    return billed + sum(pending.values())


def _billed(usage_entry, modeled) -> int:
    """The credits a receipt records: the LARGER of the API's own
    ``x-requests-last`` price and our modeled price. Overstating spend only
    tightens a cap; understating it authorizes money we do not have."""
    try:
        actual = int(usage_entry.get("requests_last"))
    except (AttributeError, TypeError, ValueError):
        return modeled
    return max(actual, modeled)


# ------------------------------------------------------------- the acquisition
def _actual_precheck(recorder, credits, what) -> None:
    """The billing-header cap, checked BEFORE the intent is written.

    ``_UsageRecorder`` enforces the same rule inside ``handle_request`` (and
    still does — defense in depth), but it raises AFTER the intent record has
    landed, which would leave our own refusal looking like an ambiguous
    pending call and jam every future resume. Same predicate, one step
    earlier."""
    actual = recorder.actual_spent()
    if (recorder.cap is not None and actual is not None
            and actual + credits > recorder.cap):
        raise CreditCapError(
            f"actual billed usage {actual} credits this run plus the next "
            f"call's modeled price {credits} exceeds the remaining gate "
            f"budget {recorder.cap} — aborting before {what}, no call placed")


def _read_archived(raw_dir, digest, what) -> dict:
    """Re-read paid bytes from the content-addressed archive. Provenance loss
    is FATAL here, exactly as it is on the write side: the alternative is
    re-buying a call we already paid for."""
    if raw_dir is None:
        raise ArchiveMissingError(
            f"{what}: a receipt cites archived bytes but this run has no raw "
            "archive — refusing to re-buy an already-paid call")
    blob = Path(raw_dir) / f"{digest}.json"
    if not blob.exists():
        raise ArchiveMissingError(
            f"{what}: receipt cites raw_sha256={digest}, absent from {raw_dir}"
            " — the paid evidence is gone; restore it rather than re-buying")
    return json.loads(blob.read_text())


def _events_from_payload(payload) -> list:
    """The discovery envelope's event rows — the same projection
    ``fetch_historical_events`` returns, so a reused listing and a fresh one
    are indistinguishable downstream."""
    data = payload["data"] if isinstance(payload, dict) else payload
    return [{"event_id": event["id"],
             "commence_time": event["commence_time"],
             "home": event.get("home_team"), "away": event.get("away_team")}
            for event in event_list(data)]


def _identity_guard(payload, event_id, sport_key, digest) -> None:
    """A PAID per-event response for the wrong fixture must never read as
    coverage (the probe's finding-3 guard, kept here because this runner
    writes the eligibility inventory the V8 lock freezes)."""
    events = event_list(payload.get("data"))
    ids = {e.get("id") for e in events if e.get("id")}
    if ids and ids != {event_id}:
        raise ValueError(
            f"event identity mismatch on a PAID snapshot: requested "
            f"{event_id} but the response answers for {', '.join(sorted(ids))}"
            f" (archived raw_sha256={digest})")
    keys = {e.get("sport_key") for e in events if e.get("sport_key")}
    if keys and keys != {sport_key}:
        raise ValueError(
            f"sport_key mismatch on a PAID snapshot: requested {sport_key} "
            f"but the response answers for {', '.join(sorted(keys))} "
            f"(archived raw_sha256={digest})")


def _evaluate_snapshot(payload, *, tag, requested_instant, t_issue, event_id,
                       sport_key, digest) -> dict:
    """Turn one archived snapshot into the eligibility row the lock freezes.

    The admissibility verdict is computed ONLY for the cut snapshot, and it is
    the adapter's strict rule (``admissible_quote``) against the strictest
    stamp the row carries — a returned timestamp of exactly 08:30:00Z fails
    it, which is the whole reason the request sits at 08:29:00Z."""
    entry = {"tag": tag, "requested_instant": requested_instant,
             "attempted": True, "raw_sha256": digest}
    _identity_guard(payload, event_id, sport_key, digest)
    rows = parse_snapshot(payload)
    snapshot_ts = payload["timestamp"]
    entry["returned_instant"] = snapshot_ts
    entry["snapshot_ts"] = snapshot_ts
    sharp = [r for r in rows if r["bookmaker"] == SHARP_BOOK]
    entry["pinnacle_present"] = bool(sharp)
    entry["n_bookmakers"] = len({r["bookmaker"] for r in rows})
    if tag == CUT_TAG:
        stamp = _ts(snapshot_ts)
        timely = bool(sharp) and all(
            admissible_quote(stamp,
                             strictest_last_update(row, snapshot_ts),
                             t_issue, buffer_minutes=CUT_BUFFER_MINUTES)
            for row in sharp)
        # 2026-08-02: a quote must also be a COHERENT MARKET, not merely a
        # timely one. A 1X2 book's inverse-price sum is its overround and is
        # >= 1 by construction; below 1 is an arbitrage no operator posts, so
        # in archived data it is a corrupt price. De-vigging one would
        # manufacture a confident forecast from a number nobody quoted, and
        # because admissibility is what FREEZES the analysed population, the
        # check belongs here rather than only at pricing time.
        coherent = timely and is_coherent_book(
            [r["price"] for r in sharp])
        entry["admissible"] = coherent
        if timely and not coherent:
            entry["incoherent_book"] = (
                "sharp quote rejected: overround "
                f"{book_overround([r['price'] for r in sharp]):.3f} < 1 — "
                "an arbitrage against the book, i.e. a corrupt archived "
                "price, not a market")
    return entry


def _row_for(fixture) -> dict:
    return {"fixture_id": fixture["fixture_id"], "pool": fixture["pool"],
            "date": fixture["date"], "home": fixture["home"],
            "away": fixture["away"], "sport_key": fixture["sport_key"],
            "kickoff_utc": _iso(fixture["kickoff_utc"]),
            "t_issue": _iso(fixture["t_issue"]),
            "attempted": False, "event_found": None, "snapshots": {},
            "eligible": False}


def run_acquisition(*, gate_id, fixtures, sport_keys, api_key, transport,
                    max_credits, raw_dir, journal_path, store_root=None,
                    aliases=None, mode="live") -> dict:
    """Acquire (or resume acquiring) one gate's odds under the journal.

    Returns ``{"groups", "plan", "results", "usage", "spent", "prior_spent",
    "projected", "remaining", "aborted", "actual", "overrun", "store_rows"}``.
    ``spent`` is the CUMULATIVE modeled gate spend (prior invocations
    included) — the figure ``--max-credits`` bounds."""
    if gate_id not in GATE_IDS:
        raise ValueError(f"gate_id must be one of {GATE_IDS}; got {gate_id!r}")
    if aliases is None:
        if mode == "live":
            # Finding 8: every alias is verified against the CANONICAL paid
            # archive before any live call — an alias whose cited evidence is
            # missing or does not contain the claimed spelling widens what
            # counts as coverage, and no paid call may be placed under it.
            # Dry-runs load unverified: the archive is a gitignored local
            # artifact and a dry-run spends nothing through the map.
            problems = verify_alias_evidence(raw_dir=ODDS_RAW_DIR)
            if problems:
                raise AliasEvidenceError(
                    "alias evidence verification failed against "
                    f"{ODDS_RAW_DIR} — refusing before any paid call: "
                    + "; ".join(problems))
        aliases = load_aliases()
    journal_path = Path(journal_path)
    raw_dir = None if raw_dir is None else Path(raw_dir)
    groups = build_plan(fixtures, sport_keys, gate_id)
    rows = plan_rows(groups)
    projected = project_credits(rows)

    with exclusive_journal_lock(journal_path):
        records = read_journal(journal_path)
        orphans = orphan_intents(records)
        if orphans:
            raise OrphanIntentError(
                f"{len(orphans)} journal INTENT record(s) have no RECEIPT — a "
                "call that may or may not have billed. Refusing to resume: "
                "inspect data/odds_raw for the orphan's archived response "
                "(call_id(s): "
                + ", ".join(sorted(r["call_id"] for r in orphans))
                + ") and settle the journal by hand before re-running")
        prior = gate_spend(records, gate_id)
        if max_credits is not None and prior > max_credits:
            # Finding 4: a resumed run whose RESTORED spend already exceeds
            # the cap has nothing left for the SpendGate to refuse (every
            # planned call may be receipted) — without this check it would
            # exit 0 with the cap already breached.
            raise CreditCapError(
                f"cumulative journal spend {prior} credits for gate "
                f"{gate_id} already exceeds --max-credits {max_credits} — "
                "the gate's budget is spent; refusing to resume under a cap "
                "the ledger has passed")
        receipts = {r["call_id"]: r for r in records
                    if r["type"] == RECEIPT and r["gate"] == gate_id}
        remaining = sum(r["credits"] for r in rows
                        if r["call_id"] not in receipts)
        gate = SpendGate(max_credits, remaining)
        # The cumulative restore: the gate opens already holding what earlier
        # invocations spent, so its projection is prior + outstanding and
        # --max-credits bounds the GATE, not this invocation (finding 4).
        gate.spent = prior
        recorder = _UsageRecorder(
            transport,
            cap=None if max_credits is None else max_credits - prior)

        results, aborted = [], None
        try:
            for group in groups:
                _acquire_group(
                    group, results=results, receipts=receipts, gate=gate,
                    recorder=recorder, api_key=api_key, raw_dir=raw_dir,
                    journal_path=journal_path, aliases=aliases)
        except CreditCapError as exc:
            aborted = str(exc)
            if not recorder.usage:
                # This invocation placed no call, so it bought nothing to
                # report on: the refusal IS the answer, and it must be loud
                # (the probe's rule). A run that DID place calls returns its
                # partial results instead — those calls were paid for.
                raise
        _pad_unreached(groups, results)

        final_records = read_journal(journal_path)
        cumulative = gate_spend(final_records, gate_id)
        store_rows = 0
        if store_root is not None:
            store_rows = rebuild_store_from_receipts(
                final_records, raw_dir=raw_dir, store_root=store_root)

    actual = recorder.actual_spent()
    overrun = None
    if aborted is None and max_credits is not None:
        if actual is not None and prior + actual > max_credits:
            overrun = (
                f"actual billed usage {prior + actual} credits for gate "
                f"{gate_id} ({prior} restored from the journal + {actual} "
                f"this run) exceeds --max-credits {max_credits} and no "
                "further call remained to refuse — the plan completed, but "
                "the cap did not hold")
        elif cumulative > max_credits:
            # Finding 4: the header-derived figure can under-count (a
            # response with no billing headers is invisible to it, while its
            # RECEIPT still bills at least the modeled price) — the ledger
            # is the spend of record, so it gets the last word.
            overrun = (
                f"cumulative journal spend {cumulative} credits for gate "
                f"{gate_id} exceeds --max-credits {max_credits} (billing "
                f"headers saw only {_fmt(actual)}) — the plan completed, "
                "but the cap did not hold")
    return {"gate": gate_id, "mode": mode, "groups": groups, "plan": rows,
            "results": results, "usage": recorder.usage, "spent": gate.spent,
            "prior_spent": prior, "projected": projected,
            "remaining": remaining, "aborted": aborted, "actual": actual,
            "overrun": overrun, "store_rows": store_rows}


def _pad_unreached(groups, results) -> None:
    """Every fixture the loop never reached still gets a row — explicitly
    not-attempted, so a partial report keeps the full frame instead of
    silently dropping the tail (a refusal by OUR gate must never read as a
    coverage miss)."""
    seen = {row["fixture_id"] for row in results}
    for group in groups:
        for fixture in group["fixtures"]:
            if fixture["fixture_id"] not in seen:
                results.append(_row_for(fixture))


def _acquire_group(group, *, results, receipts, gate, recorder, api_key,
                   raw_dir, journal_path, aliases) -> None:
    listing = _acquire_discovery(
        group, receipts=receipts, gate=gate, recorder=recorder,
        api_key=api_key, raw_dir=raw_dir, journal_path=journal_path)
    for fixture in group["fixtures"]:
        row = _row_for(fixture)
        results.append(row)
        row["discovery_sha256"] = listing.get("raw_sha256")
        if "error" in listing:
            row["error"] = listing["error"]
            continue
        row["attempted"] = True
        try:
            event, flipped = resolve_event(
                listing["events"], fixture["home"], fixture["away"], aliases)
        except AmbiguousFixtureMatch as exc:
            # Never resolved by picking: a pick buys a paid snapshot for a
            # fixture nobody chose and then reports it as coverage.
            row["error"] = _err_cell(exc, api_key)
            continue
        row["event_found"] = event is not None
        if event is None:
            row["n_events_listed"] = len(listing["events"])
            continue
        row.update({"event_id": event["event_id"],
                    "commence_time": event["commence_time"],
                    "orientation_flipped": flipped})
        for snap in fixture["snapshots"]:
            row["snapshots"][snap["tag"]] = _acquire_snapshot(
                fixture, snap, gate_id=group["gate"],
                event_id=event["event_id"], receipts=receipts, gate=gate,
                recorder=recorder, api_key=api_key, raw_dir=raw_dir,
                journal_path=journal_path)
        cut = row["snapshots"].get(CUT_TAG, {})
        row["eligible"] = bool(cut.get("admissible"))


def _acquire_discovery(group, *, receipts, gate, recorder, api_key, raw_dir,
                       journal_path) -> dict:
    receipt = receipts.get(group["call_id"])
    if receipt is not None:
        digest = receipt.get("raw_sha256")
        if receipt.get("error") or not digest:
            # A receipted FAILURE is never re-bought; where the adapter
            # archived the paid error body the receipt names its digest
            # (finding 7), so the evidence stays locatable.
            return {"error": _table_text(
                "a paid discovery call for this key failed "
                f"({receipt.get('error') or 'no raw_sha256 on the receipt'}"
                + (f"; paid evidence archived as raw_sha256={digest}"
                   if digest else "")
                + ") — its fixtures cannot be resolved without re-buying "
                "the listing, which this runner never does")}
        payload = _read_archived(raw_dir, digest, group["call_id"])
        return {"raw_sha256": digest, "events": _events_from_payload(payload),
                "reused": True}

    what = f"discovery {group['sport_key']} {group['requested_instant']}"
    gate.precall(DISCOVERY_CREDITS, what)
    try:
        _actual_precheck(recorder, DISCOVERY_CREDITS, what)
    except CreditCapError:
        gate.refund(DISCOVERY_CREDITS)
        raise
    append_record(journal_path, {
        "type": INTENT, "gate": group["gate"], "call_id": group["call_id"],
        "kind": "discovery", "sport_key": group["sport_key"],
        "requested_instant": group["requested_instant"],
        "modeled_credits": DISCOVERY_CREDITS, "ts": _now()})
    before = len(recorder.usage)
    try:
        discovery = fetch_historical_events(
            group["sport_key"], group["requested_instant"], api_key,
            raw_dir=raw_dir, transport=recorder)
    except OSError:
        # A placed, PAID call whose bytes could not be archived: provenance
        # storage is broken, so no further paid call may be placed. The bare
        # intent stands and the resume fails closed.
        raise
    except Exception as exc:
        return _receipt_for_failure(
            exc, group["call_id"], group["gate"], "discovery",
            group["requested_instant"], recorder, before, DISCOVERY_CREDITS,
            api_key, journal_path)
    _write_receipt(journal_path, group["call_id"], group["gate"], "discovery",
                   group["requested_instant"], recorder, before,
                   DISCOVERY_CREDITS, raw_sha256=discovery["raw_sha256"],
                   returned_instant=None)
    return {"raw_sha256": discovery["raw_sha256"],
            "events": discovery["events"], "reused": False}


def _acquire_snapshot(fixture, snap, *, gate_id, event_id, receipts, gate,
                      recorder, api_key, raw_dir, journal_path) -> dict:
    receipt = receipts.get(snap["call_id"])
    if receipt is not None:
        digest = receipt.get("raw_sha256")
        if receipt.get("error") or not digest:
            # The receipted failure stands (never re-bought); its archived
            # error body — where one existed — stays citable (finding 7).
            entry = {"tag": snap["tag"],
                     "requested_instant": snap["requested_instant"],
                     "attempted": False, "reused": True,
                     "error": receipt.get("error")
                     or "paid, but no archived payload on the receipt"}
            if digest:
                entry["raw_sha256"] = digest
            return entry
        payload = _read_archived(raw_dir, digest, snap["call_id"])
        entry = _evaluate_snapshot(
            payload, tag=snap["tag"],
            requested_instant=snap["requested_instant"],
            t_issue=fixture["t_issue"], event_id=event_id,
            sport_key=fixture["sport_key"], digest=digest)
        entry.update({"attempted": False, "reused": True})
        return entry

    what = (f"snapshot {snap['tag']} {fixture['fixture_id']} "
            f"{snap['requested_instant']}")
    gate.precall(SNAPSHOT_CREDITS, what)
    try:
        _actual_precheck(recorder, SNAPSHOT_CREDITS, what)
    except CreditCapError:
        gate.refund(SNAPSHOT_CREDITS)
        raise
    append_record(journal_path, {
        "type": INTENT, "gate": gate_id, "call_id": snap["call_id"],
        "kind": "snapshot", "fixture_id": fixture["fixture_id"],
        "tag": snap["tag"], "sport_key": fixture["sport_key"],
        "requested_instant": snap["requested_instant"],
        "modeled_credits": SNAPSHOT_CREDITS, "ts": _now()})
    before = len(recorder.usage)
    try:
        payload = fetch_historical(
            event_id, snap["requested_instant"], api_key, market=MARKET,
            regions=REGIONS, sport_key=fixture["sport_key"], raw_dir=raw_dir,
            transport=recorder)
    except OSError:
        raise
    except Exception as exc:
        failure = _receipt_for_failure(
            exc, snap["call_id"], gate_id, "snapshot",
            snap["requested_instant"], recorder, before, SNAPSHOT_CREDITS,
            api_key, journal_path, fixture_id=fixture["fixture_id"],
            tag=snap["tag"])
        return {"tag": snap["tag"],
                "requested_instant": snap["requested_instant"],
                "attempted": True, "error": failure["error"]}
    digest = payload.get("raw_sha256")
    try:
        entry = _evaluate_snapshot(
            payload, tag=snap["tag"],
            requested_instant=snap["requested_instant"],
            t_issue=fixture["t_issue"], event_id=event_id,
            sport_key=fixture["sport_key"], digest=digest)
    except Exception as exc:
        # The bytes are archived and the call is billed either way, so the
        # receipt lands before the finding is reported.
        _write_receipt(journal_path, snap["call_id"], gate_id, "snapshot",
                       snap["requested_instant"], recorder, before,
                       SNAPSHOT_CREDITS, raw_sha256=digest,
                       returned_instant=None,
                       fixture_id=fixture["fixture_id"], tag=snap["tag"],
                       error=_err_cell(exc, api_key))
        return {"tag": snap["tag"],
                "requested_instant": snap["requested_instant"],
                "attempted": True, "raw_sha256": digest,
                "error": _err_cell(exc, api_key)}
    _write_receipt(journal_path, snap["call_id"], gate_id, "snapshot",
                   snap["requested_instant"], recorder, before,
                   SNAPSHOT_CREDITS, raw_sha256=digest,
                   returned_instant=entry.get("returned_instant"),
                   fixture_id=fixture["fixture_id"], tag=snap["tag"])
    return entry


def _now() -> str:
    return _iso(datetime.now(timezone.utc))


def _write_receipt(journal_path, cid, gate_id, kind, requested_instant,
                   recorder, before, modeled, *, raw_sha256,
                   returned_instant, fixture_id=None, tag=None,
                   error=None) -> dict:
    usage = recorder.usage[before:]
    entry = usage[-1] if usage else {}
    record = {
        "type": RECEIPT, "gate": gate_id, "call_id": cid, "kind": kind,
        "requested_instant": requested_instant,
        "returned_instant": returned_instant,
        "fixture_id": fixture_id, "tag": tag, "raw_sha256": raw_sha256,
        "billed_credits": _billed(entry, modeled),
        "modeled_credits": modeled,
        "requests_last": entry.get("requests_last"),
        "requests_used": entry.get("requests_used"),
        "requests_remaining": entry.get("requests_remaining"),
        "ts": _now()}
    if error is not None:
        record["error"] = error
    append_record(journal_path, record)
    return record


def _receipt_for_failure(exc, cid, gate_id, kind, requested_instant, recorder,
                         before, modeled, api_key, journal_path,
                         fixture_id=None, tag=None) -> dict:
    """A 401/429/timeout or a malformed 200 on a call that reached the wire.

    The response (if any) is already paid for, so the receipt lands: it stops
    the rerun from buying the same call twice, and it records the failure
    where the coverage report and the V8 inventory can see it. Only a call we
    cannot prove reached the wire is left as a bare intent — that is the
    ambiguity the resume refuses on.

    ``raw_sha256`` (finding 7): where the adapter archived the paid response
    bytes BEFORE raising — a non-2xx body, an undecodable/misshapen 200 —
    the raised exception carries the archive digest structurally
    (``exc.raw_sha256``) and the receipt records it, so the paid evidence
    stays locatable by hash. None ONLY when no response bytes existed (a
    transport-level failure). A fixture whose snapshot receipt carries an
    error is never eligible either way."""
    text = _err_cell(exc, api_key)
    _write_receipt(journal_path, cid, gate_id, kind, requested_instant,
                   recorder, before, modeled,
                   raw_sha256=getattr(exc, "raw_sha256", None),
                   returned_instant=None, fixture_id=fixture_id, tag=tag,
                   error=text)
    return {"error": text}


# ------------------------------------------- the journaled slate probe (F1)
#: Slate calls are DISTINCT journal kinds: they never collide with — and are
#: never mistaken for — the eval plan's discovery/snapshot identities, while
#: still billing the SAME gate, so ``gate_spend`` folds them into the one
#: cumulative G-A figure ``--max-credits`` bounds.
SLATE_DISCOVERY_KIND = "slate-discovery"
SLATE_SNAPSHOT_KIND = "slate-snapshot"
#: The mini-probe's spend is ASKED WITH G-A (the plan's 4,800 cap covers
#: eval 4,417 + slate 143), so it bills the G-A gate.
SLATE_GATE = "ga"


def _slate_discovery_cid(gate_id, probe) -> str:
    return call_id(gate_id, SLATE_DISCOVERY_KIND, probe["sport_key"],
                   f"{probe['date']}T00:00:00Z")


def _slate_snapshot_cid(gate_id, probe, requested, event=None) -> str:
    """A plain probe's snapshot identity is (sport_key, instant) — the shape
    every already-receipted slate snapshot carries, so it must not change.
    A `teams`-filtered probe (2026-08-01 marquee-NL) prices a SPECIFIC
    fixture that may share its kickoff instant with the plain probe's pick
    on the SAME key, so its identity carries the event id in the fixture
    slot — without it, one paid snapshot would silently answer for two
    different fixtures."""
    fixture = str(event["event_id"]) if (probe.get("teams") and event) \
        else None
    return call_id(gate_id, SLATE_SNAPSHOT_KIND, probe["sport_key"],
                   _iso(requested), fixture, SLATE_SNAPSHOT_TAG)


def _slate_outstanding(probe, gate_id, receipts, raw_dir) -> int:
    """The credits THIS run may still place for one probe — resolved against
    the journal exactly as the loop will resolve them, so the SpendGate's
    projection is the resumed plan's true remainder, not the full ceiling."""
    d_receipt = receipts.get(_slate_discovery_cid(gate_id, probe))
    if d_receipt is None:
        return DISCOVERY_CREDITS + SNAPSHOT_CREDITS      # snapshot = ceiling
    if d_receipt.get("error") or not d_receipt.get("raw_sha256"):
        return 0                     # failed listing: no snapshot is placed
    payload = _read_archived(raw_dir, d_receipt["raw_sha256"],
                             "slate discovery (outstanding)")
    event = _pick_slate_event(_events_from_payload(payload),
                              teams=probe.get("teams"))
    if event is None:
        return 0
    requested = _ts(event["commence_time"]) - SLATE_SNAPSHOT_DELTA
    if _slate_snapshot_cid(gate_id, probe, requested, event) in receipts:
        return 0
    return SNAPSHOT_CREDITS


def run_slate_acquisition(*, api_key, transport, max_credits, raw_dir,
                          journal_path, gate_id=SLATE_GATE) -> dict:
    """The dev-slate mini-probe under the CANONICAL journal (finding 1).

    ``run_slate_probe`` measured through an invocation-local SpendGate: no
    INTENT/RECEIPT, no flock, spend invisible to the G-A cumulative cap. This
    runner asks the SAME questions through the SAME machinery as the eval
    acquisition — exclusive flock, fail-closed orphan check, prior spend
    restored into the gate, INTENT before every call, RECEIPT after every
    archive, receipted calls reused from the archive instead of re-bought —
    so the mini-probe's credits are G-A credits in the one ledger the
    4,800-credit cap is computed from. Return shape matches
    ``run_slate_probe`` (plus ``prior_spent``) so ``assemble_slate_report``
    consumes it unchanged."""
    journal_path = Path(journal_path)
    raw_dir = None if raw_dir is None else Path(raw_dir)
    projected = projected_slate_cost()

    with exclusive_journal_lock(journal_path):
        records = read_journal(journal_path)
        orphans = orphan_intents(records)
        if orphans:
            raise OrphanIntentError(
                f"{len(orphans)} journal INTENT record(s) have no RECEIPT — a "
                "call that may or may not have billed. Refusing to resume: "
                "inspect data/odds_raw for the orphan's archived response "
                "(call_id(s): "
                + ", ".join(sorted(r["call_id"] for r in orphans))
                + ") and settle the journal by hand before re-running")
        prior = gate_spend(records, gate_id)
        if max_credits is not None and prior > max_credits:
            raise CreditCapError(
                f"cumulative journal spend {prior} credits for gate "
                f"{gate_id} already exceeds --max-credits {max_credits} — "
                "refusing to run the slate probe under a cap the ledger has "
                "passed")
        receipts = {r["call_id"]: r for r in records
                    if r["type"] == RECEIPT and r["gate"] == gate_id}
        remaining = sum(_slate_outstanding(p, gate_id, receipts, raw_dir)
                        for p in SLATE_PROBES)
        gate = SpendGate(max_credits, remaining)
        gate.spent = prior
        recorder = _UsageRecorder(
            transport,
            cap=None if max_credits is None else max_credits - prior)

        results, aborted = [], None

        def _pad_unreached_slate():
            for probe in SLATE_PROBES[len(results):]:
                results.append({"competition": probe["competition"],
                                "sport_key": probe["sport_key"],
                                "date": probe["date"],
                                "tournament": probe["tournament"],
                                "attempted": False, "snapshot": None})

        try:
            for probe in SLATE_PROBES:
                _acquire_slate_probe(
                    probe, results=results, receipts=receipts, gate=gate,
                    gate_id=gate_id, recorder=recorder, api_key=api_key,
                    raw_dir=raw_dir, journal_path=journal_path)
        except CreditCapError as exc:
            if not recorder.usage:
                raise
            aborted = str(exc)
            _pad_unreached_slate()
        except OSError as exc:
            aborted = ("archive/persistence failure — provenance storage is "
                       "broken, so no further paid call may be placed: "
                       + _err_cell(exc, api_key))
            _pad_unreached_slate()

        cumulative = gate_spend(read_journal(journal_path), gate_id)

    actual = recorder.actual_spent()
    overrun = None
    if aborted is None and max_credits is not None:
        if actual is not None and prior + actual > max_credits:
            overrun = (
                f"actual billed usage {prior + actual} credits for gate "
                f"{gate_id} ({prior} restored from the journal + {actual} "
                f"this run) exceeds --max-credits {max_credits} and no "
                "further call remained to refuse — the cap did not hold")
        elif cumulative > max_credits:
            overrun = (
                f"cumulative journal spend {cumulative} credits for gate "
                f"{gate_id} exceeds --max-credits {max_credits} (billing "
                f"headers saw only {_fmt(actual)}) — the cap did not hold")
    return {"results": results, "usage": recorder.usage, "spent": gate.spent,
            "projected": projected, "aborted": aborted, "actual": actual,
            "overrun": overrun, "prior_spent": prior}


def _acquire_slate_probe(probe, *, results, receipts, gate, gate_id, recorder,
                         api_key, raw_dir, journal_path) -> None:
    row = {"competition": probe["competition"],
           "sport_key": probe["sport_key"], "date": probe["date"],
           "tournament": probe["tournament"],
           "attempted": False, "snapshot": None}
    results.append(row)
    listing = _acquire_slate_discovery(
        probe, receipts=receipts, gate=gate, gate_id=gate_id,
        recorder=recorder, api_key=api_key, raw_dir=raw_dir,
        journal_path=journal_path, row=row)
    if listing is None:
        return
    row["attempted"] = True
    row["discovery_sha256"] = listing["raw_sha256"]
    events = listing["events"]
    row["n_events_listed"] = len(events)
    event = _pick_slate_event(events, teams=probe.get("teams"))
    if event is None:
        # No usable listing -> no snapshot call at all: an uncovered
        # competition costs one credit (or zero on reuse).
        return
    row.update({"event_id": event["event_id"],
                "commence_time": event["commence_time"],
                "sample_fixture": f"{event['home']} v {event['away']}"})
    try:
        commence = _ts(event["commence_time"])
    except ValueError as exc:
        row["error"] = _err_cell(exc, api_key)
        return
    requested = commence - SLATE_SNAPSHOT_DELTA
    _acquire_slate_snapshot(
        probe, event, requested, commence=commence, row=row,
        receipts=receipts, gate=gate, gate_id=gate_id, recorder=recorder,
        api_key=api_key, raw_dir=raw_dir, journal_path=journal_path)


def _acquire_slate_discovery(probe, *, receipts, gate, gate_id, recorder,
                             api_key, raw_dir, journal_path, row):
    """One slate listing: reused from the archive when receipted, else bought
    under intent->receipt. Returns ``{"raw_sha256", "events"}`` or None when
    the row already carries the terminal finding."""
    cid = _slate_discovery_cid(gate_id, probe)
    receipt = receipts.get(cid)
    if receipt is not None:
        digest = receipt.get("raw_sha256")
        if receipt.get("error") or not digest:
            row["attempted"] = True
            row["error"] = _table_text(
                "a paid slate discovery for this key failed "
                f"({receipt.get('error') or 'no raw_sha256 on the receipt'}"
                + (f"; paid evidence archived as raw_sha256={digest}"
                   if digest else "") + ") — never re-bought")
            return None
        payload = _read_archived(raw_dir, digest, cid)
        return {"raw_sha256": digest,
                "events": _events_from_payload(payload)}

    instant = f"{probe['date']}T00:00:00Z"
    what = f"slate discovery {probe['competition']}"
    gate.precall(DISCOVERY_CREDITS, what)
    try:
        _actual_precheck(recorder, DISCOVERY_CREDITS, what)
    except CreditCapError:
        gate.refund(DISCOVERY_CREDITS)
        raise
    recorder.next_call_credits = DISCOVERY_CREDITS
    append_record(journal_path, {
        "type": INTENT, "gate": gate_id, "call_id": cid,
        "kind": SLATE_DISCOVERY_KIND, "sport_key": probe["sport_key"],
        "requested_instant": instant,
        "modeled_credits": DISCOVERY_CREDITS, "ts": _now()})
    before = len(recorder.usage)
    try:
        discovery = fetch_historical_events(
            probe["sport_key"], instant, api_key, raw_dir=raw_dir,
            transport=recorder)
    except OSError as exc:
        # Placed and paid, but its bytes could not be archived: mark the row
        # honestly, leave the bare intent standing, and let the run abort —
        # the resume fails closed on it.
        row["attempted"] = True
        row["error"] = _err_cell(exc, api_key)
        raise
    except Exception as exc:
        failure = _receipt_for_failure(
            exc, cid, gate_id, SLATE_DISCOVERY_KIND, instant, recorder,
            before, DISCOVERY_CREDITS, api_key, journal_path)
        # Register in-run: a later probe SHARING this (sport_key, date) —
        # the marquee-NL entry — must see the receipt, or it would re-place
        # a receipted call and the journal validator would refuse the file.
        receipts[cid] = failure
        row["attempted"] = True
        row["error"] = failure["error"]
        return None
    _write_receipt(journal_path, cid, gate_id, SLATE_DISCOVERY_KIND, instant,
                   recorder, before, DISCOVERY_CREDITS,
                   raw_sha256=discovery["raw_sha256"], returned_instant=None)
    receipts[cid] = {"raw_sha256": discovery["raw_sha256"]}
    return {"raw_sha256": discovery["raw_sha256"],
            "events": discovery["events"]}


def _acquire_slate_snapshot(probe, event, requested, *, commence, row,
                            receipts, gate, gate_id, recorder, api_key,
                            raw_dir, journal_path) -> dict:
    cid = _slate_snapshot_cid(gate_id, probe, requested, event)
    receipt = receipts.get(cid)
    # Attached BEFORE any gate with ``attempted: False``: a cap refusal must
    # render "not attempted" — our gate's refusal, never a measured miss —
    # and an abort mid-snapshot must leave the entry standing on the row.
    entry = {"tag": SLATE_SNAPSHOT_TAG, "requested_ts": _iso(requested),
             "attempted": False}
    row["snapshot"] = entry
    if receipt is not None:
        digest = receipt.get("raw_sha256")
        entry.update({"attempted": True, "reused": True})
        if receipt.get("error") or not digest:
            entry["error"] = (receipt.get("error")
                              or "paid, but no archived payload on the "
                                 "receipt")
            if digest:
                entry["raw_sha256"] = digest
            return entry
        payload = _read_archived(raw_dir, digest, cid)
        entry["raw_sha256"] = digest
        try:
            entry.update(_slate_snapshot_entry(payload, requested,
                                               commence=commence))
        except Exception as exc:
            entry["error"] = _err_cell(exc, api_key)
        return entry

    what = f"slate snapshot {SLATE_SNAPSHOT_TAG} {probe['competition']}"
    gate.precall(SNAPSHOT_CREDITS, what)
    try:
        _actual_precheck(recorder, SNAPSHOT_CREDITS, what)
    except CreditCapError:
        gate.refund(SNAPSHOT_CREDITS)
        raise
    recorder.next_call_credits = SNAPSHOT_CREDITS
    append_record(journal_path, {
        "type": INTENT, "gate": gate_id, "call_id": cid,
        "kind": SLATE_SNAPSHOT_KIND, "sport_key": probe["sport_key"],
        "requested_instant": _iso(requested), "tag": SLATE_SNAPSHOT_TAG,
        "modeled_credits": SNAPSHOT_CREDITS, "ts": _now()})
    before = len(recorder.usage)
    entry["attempted"] = True        # the call is going to the wire now
    try:
        snap = fetch_historical(
            event["event_id"], _iso(requested), api_key, market=MARKET,
            regions=REGIONS, sport_key=probe["sport_key"], raw_dir=raw_dir,
            transport=recorder)
    except OSError as exc:
        entry["error"] = _err_cell(exc, api_key)
        raise
    except Exception as exc:
        failure = _receipt_for_failure(
            exc, cid, gate_id, SLATE_SNAPSHOT_KIND, _iso(requested),
            recorder, before, SNAPSHOT_CREDITS, api_key, journal_path,
            tag=SLATE_SNAPSHOT_TAG)
        receipts[cid] = failure
        entry["error"] = failure["error"]
        return entry
    digest = snap.get("raw_sha256")
    entry["raw_sha256"] = digest
    try:
        entry.update(_slate_snapshot_entry(snap, requested,
                                           commence=commence))
    except Exception as exc:
        _write_receipt(journal_path, cid, gate_id, SLATE_SNAPSHOT_KIND,
                       _iso(requested), recorder, before, SNAPSHOT_CREDITS,
                       raw_sha256=digest, returned_instant=None,
                       tag=SLATE_SNAPSHOT_TAG, error=_err_cell(exc, api_key))
        receipts[cid] = {"raw_sha256": digest,
                         "error": _err_cell(exc, api_key)}
        entry["error"] = _err_cell(exc, api_key)
        return entry
    _write_receipt(journal_path, cid, gate_id, SLATE_SNAPSHOT_KIND,
                   _iso(requested), recorder, before, SNAPSHOT_CREDITS,
                   raw_sha256=digest,
                   returned_instant=entry.get("snapshot_ts"),
                   tag=SLATE_SNAPSHOT_TAG)
    receipts[cid] = {"raw_sha256": digest}
    return entry


# ------------------------------------------------- ingest (atomic, from receipts)
def rebuild_store_from_receipts(records, *, raw_dir, store_root) -> int:
    """Rebuild the odds store from the archived snapshot payloads the receipts
    name — a pure function of the journal, so it is idempotent and a crash
    before it costs nothing.

    From EVERY gate's receipts (finding 5): the store is one COMMON artifact,
    and the rebuild REPLACES the whole parquet — filtered to the running gate
    it would erase the other gate's rows every time (running G-B wiped G-A's
    paid odds from the store, and vice versa). Failure receipts contribute
    nothing: an archived error body is evidence, not a snapshot.

    Built in a scratch root and moved into place with ``os.replace``: the
    store is a whole-table artifact, so an interrupted in-place write would
    leave a torn parquet where a complete one is expected (the ledger's
    tmp+rename contract, one directory up because ``BitemporalStore.write``
    APPENDS to whatever it finds)."""
    digests = [r["raw_sha256"] for r in records
               if r["type"] == RECEIPT and r.get("kind") == "snapshot"
               and r.get("raw_sha256") and not r.get("error")]
    store_root = Path(store_root)
    store_root.mkdir(parents=True, exist_ok=True)
    if not digests:
        return 0
    sample = {}
    for digest in dict.fromkeys(digests):
        sample[digest] = _read_archived(raw_dir, digest, "store rebuild")
    rows = sum(len(parse_snapshot(payload)) for payload in sample.values())
    scratch = store_root / f".rebuild.{os.getpid()}"
    if scratch.exists():
        shutil.rmtree(scratch)
    try:
        load_odds_snapshots(BitemporalStore(scratch), sample)
        built = scratch / "odds.parquet"
        if built.exists():
            os.replace(built, store_root / "odds.parquet")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return rows


# ------------------------------------------------------------------- reporting
def _banner(mode, mocked) -> list:
    """The report's first line — the strongest claim on the page. The probe's
    banner is not reused because it talks about the probe overwriting its own
    report; the EXACT-TYPE allowlist behind ``mocked`` is the same one."""
    if mode == "dry-run":
        return [
            "**MODE: DRY-RUN.** Every response below came from recorded-shape "
            "MOCK payloads served by an in-process transport: ZERO network "
            "calls, ZERO credits spent, and the env `ODDS_API_KEY` was never "
            "read. Coverage/admissibility values prove the pipeline and are "
            "NOT measurements; the receipts went to the SEPARATE dry-run "
            "journal, never the paid ledger the cumulative gate cap is "
            "computed from."]
    if mocked:
        return [
            "**MODE: LIVE ARGS, MOCKED TRANSPORT (test only).** The live gates "
            "ran, but responses came from an injected mock: NOT real "
            "measurements, no credits spent."]
    return ["**MODE: LIVE.** Real paid responses from The Odds API."]


def assemble_report(summary, *, cap, mocked) -> str:
    gate = summary["gate"]
    lines = [f"# OA acquisition run — gate {gate.upper()} "
             "(OA Plan 2 v2, V1)", ""]
    lines += _banner(summary["mode"], mocked)
    if summary["aborted"]:
        lines += ["", f"**RUN ABORTED MID-FLIGHT: {summary['aborted']}** The "
                  "journal is intact: every receipted call is already paid "
                  "for and will be SKIPPED on resume; every unreached fixture "
                  "is marked \"not attempted\" — a refusal by our own gate, "
                  "never a measured miss."]
    n_disc = sum(1 for r in summary["plan"] if r["kind"] == "discovery")
    n_snap = len(summary["plan"]) - n_disc
    lines += [
        "", "## Call plan + cumulative gate spend", "",
        f"{n_disc} discovery calls (one per distinct `(sport_key, "
        f"requested_instant)`) @ {DISCOVERY_CREDITS} credit + {n_snap} "
        f"snapshot calls [{', '.join(SNAPSHOT_TAGS)}; {MARKET} x {REGIONS}] @ "
        f"{SNAPSHOT_CREDITS} credits = **{summary['projected']} credits** "
        "projected for the whole plan (mechanical, from the plan itself).", "",
        f"- restored from the journal for gate `{gate}`: "
        f"{summary['prior_spent']} credits",
        f"- outstanding when this run started: {summary['remaining']} credits",
        f"- cumulative modeled spend after this run: {summary['spent']} "
        f"credits, against `--max-credits` {_fmt(cap)}",
        f"- actual billed THIS run (billing headers): "
        f"{_fmt(summary['actual'])} credits", "",
        "The T_issue-cut snapshot is requested at **08:29:00Z** on the "
        "venue-LOCAL matchday: the cut is 09:00Z minus a "
        f"{CUT_BUFFER_MINUTES}-minute buffer and the admissibility rule is a "
        "STRICT `<`, so a snapshot returned stamped exactly 08:30:00Z is "
        "inadmissible. Requested and returned instants are reported "
        "separately below — what we asked for is a decision, what came back "
        "is evidence.", "",
        "| fixture | pool | matchday | kickoff (UTC) | event | requested cut |"
        " returned cut | Pinnacle | admissible | notes |",
        "|---|---|---|---|---|---|---|---|---|---|"]
    for row in summary["results"]:
        cut = row["snapshots"].get(CUT_TAG, {})
        notes = row.get("error") or "; ".join(
            [s["error"] for s in row["snapshots"].values() if "error" in s])
        if not row["attempted"] and not notes:
            notes = ("not attempted: the run stopped before this fixture's "
                     "discovery call was placed")
        lines.append("| " + " | ".join([
            _table_text(f"{row['home']} v {row['away']}"), row["pool"],
            row["date"], row["kickoff_utc"], _fmt(row["event_found"]),
            _fmt(cut.get("requested_instant")), _fmt(cut.get("snapshot_ts")),
            _fmt(cut.get("pinnacle_present")), _fmt(cut.get("admissible")),
            _table_text(notes) if notes else "-"]) + " |")
    eligible = [r for r in summary["results"] if r["eligible"]]
    lines += ["", f"Population eligibility (admissible cut quote): "
              f"**{len(eligible)} / {len(summary['results'])}** fixtures. "
              "Solver success is applied on top of this at V8; the inventory "
              "is frozen into the lock there, never here.", "",
              "## Provenance (full sha256 of the archived raw response)", ""]
    for row in summary["results"]:
        shas = ([f"discovery {row['discovery_sha256']}"]
                if row.get("discovery_sha256") else [])
        shas += [f"{tag} {s['raw_sha256']}"
                 for tag, s in sorted(row["snapshots"].items())
                 if s.get("raw_sha256")]
        lines.append(f"- {_table_text(row['fixture_id'])}: "
                     + (", ".join(shas) or "-"))
    lines += ["", "## Actual usage (`x-requests-last` / `x-requests-used` / "
              "`x-requests-remaining` headers)", ""]
    if summary["mode"] == "dry-run":
        lines += ["Not available: dry-run serves no live responses, so no "
                  "usage headers exist (and none are fabricated)."]
    elif not summary["usage"]:
        lines += ["No responses received."]
    else:
        lines += ["| call | path | x-requests-last | x-requests-used | "
                  "x-requests-remaining |", "|---|---|---|---|---|"]
        lines += [f"| {i} | `{u['path']}` | {_fmt(u.get('requests_last'))} | "
                  f"{_fmt(u['requests_used'])} | "
                  f"{_fmt(u['requests_remaining'])} |"
                  for i, u in enumerate(summary["usage"], 1)]
    if summary["overrun"]:
        lines += ["", f"**ACTUAL BILLING EXCEEDED THE CAP: {summary['overrun']}**"]
    lines += ["", f"Store rows rebuilt from receipts: {summary['store_rows']}."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------- dry-run payloads
def _dry_run_transport(fixtures, sport_keys) -> httpx.MockTransport:
    """Recorded-shape mock payloads for the manifest's own fixtures: the
    pipeline proof, with the same geometry the probe's dry-run uses (snapshot
    3 min before the requested instant, sharp stamps 5 min older)."""
    by_day = {}
    for fixture in fixtures:
        validated = validate_fixture(fixture, sport_keys)
        by_day.setdefault(
            (validated["sport_key"], discovery_instant(validated["date"])),
            []).append(validated)

    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")
        requested = request.url.params["date"]
        if request.url.path.endswith("/events"):
            rows = by_day.get((parts[4], requested), [])
            return httpx.Response(200, json={
                "timestamp": requested, "previous_timestamp": requested,
                "next_timestamp": requested,
                "data": [{"id": f"mock_{f['fixture_id']}",
                          "sport_key": f["sport_key"],
                          "commence_time": _iso(f["kickoff_utc"]),
                          "home_team": f["home"], "away_team": f["away"]}
                         for f in rows]})
        wanted = parts[6]
        fixture = next(f for rows in by_day.values() for f in rows
                       if f"mock_{f['fixture_id']}" == wanted)
        stamp = _ts(requested) - timedelta(minutes=3)
        older = _iso(stamp - timedelta(minutes=5))
        outcomes = [{"name": fixture["home"], "price": 2.10},
                    {"name": "Draw", "price": 3.30},
                    {"name": fixture["away"], "price": 3.60}]
        return httpx.Response(200, json={
            "timestamp": _iso(stamp), "previous_timestamp": _iso(stamp),
            "next_timestamp": _iso(stamp),
            "data": {"id": wanted, "sport_key": fixture["sport_key"],
                     "commence_time": _iso(fixture["kickoff_utc"]),
                     "home_team": fixture["home"], "away_team": fixture["away"],
                     "bookmakers": [
                         {"key": SHARP_BOOK, "last_update": older,
                          "markets": [{"key": MARKET, "last_update": older,
                                       "outcomes": outcomes}]}]}})

    return httpx.MockTransport(handler)


def _live_transport() -> httpx.BaseTransport:
    """The real-network transport for --live (constructing it opens no
    connection). Tests monkeypatch this factory — the only way the live code
    path ever runs under test."""
    return httpx.HTTPTransport()


def _live_raw_dir(transport):
    """Paid evidence lands in the repo archive ONLY behind the genuine network
    transport — the probe's EXACT-TYPE allowlist (a canned-response
    ``HTTPTransport`` SUBCLASS is pedigree without the network)."""
    return ODDS_RAW_DIR if type(transport) is httpx.HTTPTransport else None


def load_fixture_manifest(path) -> list:
    import yaml

    doc = yaml.safe_load(Path(path).read_text()) or {}
    rows = doc.get("fixtures")
    if not isinstance(rows, list) or not rows:
        raise FixtureManifestError(
            f"{path}: expected a non-empty top-level 'fixtures' list")
    return rows


#: --dev reads THE_RULE's candidates from this results store.
DEV_RESULTS_STORE = "data/stores/full_final"
DEV_OUT_DEFAULT = "reports/oa_acquire_gb_dev.md"
#: The walk's machine-readable verdict: per-candidate admissibility with the
#: paid evidence digest behind each one. This is the "per-fixture coverage
#: admissibility" input `oa_dev_manifest.py --emit` has always refused
#: without — committed, and hash-bound into the V8 lock alongside the
#: manifest it produces.
DEV_COVERAGE_DEFAULT = "config/oa_dev_coverage.yaml"


def write_dev_coverage(out, *, path=DEV_COVERAGE_DEFAULT, mocked=False):
    """Emit the walk's admissibility verdicts as YAML.

    One row per WALKED candidate — including the misses, because "we looked
    and the archive did not carry it" is evidence the lock must record just
    as much as a success. Candidates the walk never reached (it stopped at
    n_dev) are absent by construction: nothing was bought for them, so
    nothing is claimed about them."""
    import yaml

    rows = []
    for row in out["results"]:
        cut = (row.get("snapshots") or {}).get(CUT_TAG) or {}
        rows.append({
            "match_id": row["match_id"], "date": row["date"],
            "home": row["home"], "away": row["away"],
            "tournament": row["tournament"],
            "sport_key": row["sport_key"],
            "listed": bool(row.get("event_found")),
            "admissible": bool(cut.get("admissible")),
            "cut_raw_sha256": cut.get("raw_sha256"),
            # An exclusion the lock cannot explain is worse than no
            # exclusion: `incoherent_book` names the ONE case where a
            # timely sharp quote was still refused (overround < 1, a
            # corrupt archived price), so the artifact says why rather
            # than leaving a silent 259-vs-260.
            "note": (row.get("error") or cut.get("incoherent_book")
                     or None)})
    doc = {
        "derived_by": "scripts/oa_acquire.py --dev (V4 / G-B walk)",
        "mode": "dry-run (MOCK verdicts)" if mocked else "live",
        "gate": out["gate"],
        "n_walked": len(rows),
        "n_admissible": sum(1 for r in rows if r["admissible"]),
        "n_dev_target": out["n_dev"],
        "coverage": rows,
    }
    header = (
        "# OA dev-slate COVERAGE — per-candidate admissibility from the G-B\n"
        "# walk, with the paid-evidence digest behind every verdict.\n"
        "# DERIVED from the journal + archive; regenerate by re-running the\n"
        "# walk (receipted calls are reused, so a rerun costs nothing).\n"
        "# Admissibility is OUTCOME-BLIND: it asks only whether a sharp quote\n"
        "# was posted before the 08:30Z cut, never what the fixture did.\n")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(header + yaml.safe_dump(doc, sort_keys=False,
                                                  allow_unicode=True))
    return path


# ---------------------------------------------------- the dev walk (V4 / G-B)
# The eval set was a FIXED plan: 217 known fixtures, kickoffs from a committed
# manifest, every call projectable upfront. The dev slate is the opposite by
# construction — THE_RULE truncates to "the first N_dev with admissible
# coverage", and admissibility is only knowable AFTER the cut snapshot is
# bought. So the dev acquisition is a chronological WALK, not a plan:
#
#   for each candidate in THE_RULE's order:
#     listing for (sport_key, matchday)   — bought lazily, shared by the day
#     resolve the candidate in it         — a miss costs nothing
#     CUT snapshot ONLY                   — see below; 10 credits per walked
#                                           candidate, nothing more
#     stop when n_dev are covered (or the cap refuses)
#
# CUT-ONLY (2026-08-01, before any dev credit was spent). The eval set buys
# TWO snapshots per fixture — the T_issue cut and a T-24h reference line. A
# pre-spend audit found the T-24h line has NO consumer: not in the prereg,
# not in the analysis spec, not in `blend.py`/`arms.py`, and not in V5's dev
# ledger schema (one odds vector per row, the cut-aligned de-vigged one that
# E' blends). Buying it for 300 dev fixtures would be 3,000 credits for data
# nothing reads. Dev odds are DEVELOPMENT data — outside the confirmatory
# lockbox and re-buyable at any time — so declining it now is reversible in
# a way that spending it is not, and the credits it frees are what lets the
# walk reach n_dev even if coverage runs thinner than the probe suggested.
# The EVAL set is untouched: its T-24h snapshots are already bought and its
# 2-per-fixture model is what G-A was approved against.
#
# Kickoffs come from the DISCOVERED listing (the API's own commence_time) —
# there is no committed dev kickoff manifest, and unlike the eval plan the
# T-24h instant is derived after discovery, exactly as the slate probe does.
# The SpendGate opens with remaining=0: an adaptive walk has no fixed
# outstanding total, so the cap binds per call (projected = spent + this
# call), plus the billing-header precheck — same two fences as everywhere.
DEV_GATE = "gb"


def dev_candidates(results, cfg) -> tuple:
    """THE_RULE's ordered candidates, split into (walkable, out_of_scope).

    ``eligible_dev_fixtures`` applies the frozen eligibility+ordering. The
    acquisition-scope filter (config ``oa_dev_slate.acquisition``) then
    splits off candidates whose competition key cannot carry them — the
    store label "FIFA World Cup qualification" spans every confederation,
    but the probed key is CONMEBOL-only. That split bounds SPEND (which
    listings get bought); it never re-orders or re-selects: out-of-scope
    candidates are exactly as if their listings never matched — eligible,
    never admissible."""
    ordered = eligible_dev_fixtures(results,
                                    competitions=cfg["competitions"])
    acq = cfg.get("acquisition") or {}
    sport_keys = acq.get("sport_keys") or {}
    participants = acq.get("participants") or {}
    missing = [c for c in cfg["competitions"] if c not in sport_keys]
    if missing:
        raise FixtureManifestError(
            f"oa_dev_slate.acquisition.sport_keys lacks {missing} — every "
            "chosen competition needs its probed key before any dev call")
    walkable, out_of_scope = [], []
    for row in ordered.itertuples():
        allowed = participants.get(row.tournament)
        entry = {"match_id": str(row.match_id),
                 "date": row.date.isoformat(),
                 "home": str(row.home_team), "away": str(row.away_team),
                 "tournament": str(row.tournament),
                 "sport_key": sport_keys[row.tournament]}
        if allowed is not None and not ({entry["home"], entry["away"]}
                                        <= set(allowed)):
            out_of_scope.append(entry)
        else:
            walkable.append(entry)
    return walkable, out_of_scope


def _dev_discovery(candidate, *, receipts, gate, gate_id, recorder, api_key,
                   raw_dir, journal_path) -> dict:
    """One dev listing — bought once per (sport_key, matchday), reused by
    every later candidate on the day (in-run receipt registration, the slate
    lesson). Returns {"raw_sha256", "events"} or {"error"}."""
    instant = f"{candidate['date']}T00:00:00Z"
    cid = call_id(gate_id, "discovery", candidate["sport_key"], instant)
    receipt = receipts.get(cid)
    if receipt is not None:
        digest = receipt.get("raw_sha256")
        if receipt.get("error") or not digest:
            return {"error": receipt.get("error")
                    or "paid, but no archived payload on the receipt",
                    "raw_sha256": digest}
        payload = _read_archived(raw_dir, digest, cid)
        return {"raw_sha256": digest,
                "events": _events_from_payload(payload)}
    what = f"dev discovery {candidate['sport_key']} {candidate['date']}"
    gate.precall(DISCOVERY_CREDITS, what)
    try:
        _actual_precheck(recorder, DISCOVERY_CREDITS, what)
    except CreditCapError:
        gate.refund(DISCOVERY_CREDITS)
        raise
    recorder.next_call_credits = DISCOVERY_CREDITS
    append_record(journal_path, {
        "type": INTENT, "gate": gate_id, "call_id": cid, "kind": "discovery",
        "sport_key": candidate["sport_key"], "requested_instant": instant,
        "modeled_credits": DISCOVERY_CREDITS, "ts": _now()})
    before = len(recorder.usage)
    try:
        discovery = fetch_historical_events(
            candidate["sport_key"], instant, api_key, raw_dir=raw_dir,
            transport=recorder)
    except OSError:
        raise                       # bare intent stands; resume fails closed
    except Exception as exc:
        failure = _receipt_for_failure(
            exc, cid, gate_id, "discovery", instant, recorder, before,
            DISCOVERY_CREDITS, api_key, journal_path)
        receipts[cid] = failure
        return {"error": failure["error"],
                "raw_sha256": failure.get("raw_sha256")}
    _write_receipt(journal_path, cid, gate_id, "discovery", instant,
                   recorder, before, DISCOVERY_CREDITS,
                   raw_sha256=discovery["raw_sha256"], returned_instant=None)
    receipts[cid] = {"raw_sha256": discovery["raw_sha256"]}
    return {"raw_sha256": discovery["raw_sha256"],
            "events": discovery["events"]}


def _dev_snap_spec(candidate, tag, requested, gate_id) -> dict:
    return {"tag": tag, "requested_instant": _iso(requested),
            "credits": SNAPSHOT_CREDITS,
            "call_id": call_id(gate_id, "snapshot", candidate["sport_key"],
                               _iso(requested), candidate["match_id"], tag)}


def run_dev_acquisition(*, api_key, transport, max_credits, raw_dir,
                        journal_path, candidates, n_dev,
                        gate_id=DEV_GATE, store_root=None,
                        aliases=None, mode="live") -> dict:
    """Walk THE_RULE's candidates under the canonical journal until ``n_dev``
    are covered (admissible cut quote) or the cap refuses.

    Same fences as ``run_acquisition``: exclusive flock, fail-closed orphans,
    cumulative prior restored, verified aliases before any paid call,
    INTENT->RECEIPT per call, receipted calls reused from the archive. On
    resume the walk re-derives every candidate's state (matched? cut bought?
    admissible? T-24h bought?) from receipts + archive — free — so the
    covered count picks up exactly where the ledger says it stopped."""
    if aliases is None:
        if mode == "live":
            problems = verify_alias_evidence(raw_dir=ODDS_RAW_DIR)
            if problems:
                raise AliasEvidenceError(
                    "alias evidence verification failed against "
                    f"{ODDS_RAW_DIR} — refusing before any paid call: "
                    + "; ".join(problems))
        aliases = load_aliases()
    journal_path = Path(journal_path)
    raw_dir = None if raw_dir is None else Path(raw_dir)

    with exclusive_journal_lock(journal_path):
        records = read_journal(journal_path)
        orphans = orphan_intents(records)
        if orphans:
            raise OrphanIntentError(
                f"{len(orphans)} journal INTENT record(s) have no RECEIPT — a "
                "call that may or may not have billed. Refusing to resume: "
                "inspect data/odds_raw for the orphan's archived response "
                "(call_id(s): "
                + ", ".join(sorted(r["call_id"] for r in orphans))
                + ") and settle the journal by hand before re-running")
        prior = gate_spend(records, gate_id)
        if max_credits is not None and prior > max_credits:
            raise CreditCapError(
                f"cumulative journal spend {prior} credits for gate "
                f"{gate_id} already exceeds --max-credits {max_credits} — "
                "the gate's budget is spent; refusing to resume under a cap "
                "the ledger has passed")
        receipts = {r["call_id"]: r for r in records
                    if r["type"] == RECEIPT and r["gate"] == gate_id}
        # remaining=0: the walk has no fixed outstanding plan — the cap
        # binds per call (precall projects spent + this call) plus the
        # billing-header precheck.
        gate = SpendGate(max_credits, 0)
        gate.spent = prior
        recorder = _UsageRecorder(
            transport,
            cap=None if max_credits is None else max_credits - prior)

        results, aborted = [], None
        covered = 0
        try:
            for candidate in candidates:
                if covered >= n_dev:
                    break
                row = dict(candidate)
                row.update({"attempted": False, "event_found": None,
                            "snapshots": {}, "covered": False})
                results.append(row)
                listing = _dev_discovery(
                    candidate, receipts=receipts, gate=gate, gate_id=gate_id,
                    recorder=recorder, api_key=api_key, raw_dir=raw_dir,
                    journal_path=journal_path)
                row["discovery_sha256"] = listing.get("raw_sha256")
                if "error" in listing:
                    row["error"] = listing["error"]
                    continue
                row["attempted"] = True
                try:
                    event, flipped = resolve_event(
                        listing["events"], candidate["home"],
                        candidate["away"], aliases)
                except AmbiguousFixtureMatch as exc:
                    row["error"] = _err_cell(exc, api_key)
                    continue
                row["event_found"] = event is not None
                if event is None:
                    row["n_events_listed"] = len(listing["events"])
                    continue
                try:
                    kickoff = _ts(event["commence_time"])
                except ValueError as exc:
                    row["error"] = _err_cell(exc, api_key)
                    continue
                t_issue = t_issue_for(candidate["date"])
                row.update({"event_id": event["event_id"],
                            "commence_time": event["commence_time"],
                            "orientation_flipped": flipped,
                            "kickoff_utc": _iso(kickoff),
                            "t_issue": _iso(t_issue)})
                if not t_issue < kickoff:
                    # No pre-issuance quote exists on this matchday: the cut
                    # would be an in-play price (OA F2). Recorded, unbought.
                    row["error"] = (
                        f"t_issue {_iso(t_issue)} is not strictly before "
                        f"kickoff {_iso(kickoff)} — the cut snapshot would "
                        "be an in-play price; skipped, nothing bought")
                    continue
                fixture = {"fixture_id": candidate["match_id"],
                           "sport_key": candidate["sport_key"],
                           "t_issue": t_issue}
                cut_spec = _dev_snap_spec(
                    candidate, CUT_TAG,
                    cut_request_instant(candidate["date"]), gate_id)
                cut = _acquire_snapshot(
                    fixture, cut_spec, gate_id=gate_id,
                    event_id=event["event_id"], receipts=receipts, gate=gate,
                    recorder=recorder, api_key=api_key, raw_dir=raw_dir,
                    journal_path=journal_path)
                row["snapshots"][CUT_TAG] = cut
                if cut.get("admissible"):
                    row["covered"] = True
                    covered += 1
        except CreditCapError as exc:
            aborted = str(exc)
            if not recorder.usage:
                raise

        final_records = read_journal(journal_path)
        cumulative = gate_spend(final_records, gate_id)
        store_rows = 0
        if store_root is not None:
            store_rows = rebuild_store_from_receipts(
                final_records, raw_dir=raw_dir, store_root=store_root)

    actual = recorder.actual_spent()
    overrun = None
    if aborted is None and max_credits is not None and \
            cumulative > max_credits:
        overrun = (
            f"cumulative journal spend {cumulative} credits for gate "
            f"{gate_id} exceeds --max-credits {max_credits} — the walk "
            "completed, but the cap did not hold")
    return {"gate": gate_id, "mode": mode, "results": results,
            "usage": recorder.usage, "spent": gate.spent,
            "prior_spent": prior, "covered": covered, "n_dev": n_dev,
            "walked": len(results), "aborted": aborted, "actual": actual,
            "overrun": overrun, "store_rows": store_rows,
            "cumulative": cumulative}


def load_dev_candidates(store_path, cfg) -> tuple:
    """Read the results store and apply THE_RULE + the acquisition scope."""
    import pandas as pd

    results = pd.read_parquet(Path(store_path) / "results.parquet")
    return dev_candidates(results, cfg)


def _dev_dry_run_transport(candidates) -> httpx.MockTransport:
    """Recorded-shape mocks for the dev walk: every candidate is listed on
    its own matchday (so resolution succeeds) with a 19:00Z kickoff, and
    every snapshot carries Pinnacle at the eval dry-run's geometry. A
    dry-run therefore covers the first n_dev candidates — the SHAPE of a
    successful walk, never a claim about real coverage."""
    by_day: dict = {}
    for c in candidates:
        by_day.setdefault((c["sport_key"], f"{c['date']}T00:00:00Z"),
                          []).append(c)

    def _event(c):
        return {"id": f"dev_{c['match_id'][:16]}", "sport_key": c["sport_key"],
                "commence_time": f"{c['date']}T19:00:00Z",
                "home_team": c["home"], "away_team": c["away"]}

    by_event = {_event(c)["id"]: c for c in candidates}

    def handler(request: httpx.Request) -> httpx.Response:
        requested = request.url.params["date"]
        parts = request.url.path.split("/")
        if request.url.path.endswith("/events"):
            listed = [_event(c) for c in by_day.get((parts[4], requested), [])]
            return httpx.Response(200, json={
                "timestamp": requested, "previous_timestamp": requested,
                "next_timestamp": requested, "data": listed})
        candidate = by_event[parts[6]]
        stamp = _ts(requested) - _MOCK_SNAPSHOT_LAG
        older = _iso(stamp - _MOCK_BOOK_LAG)
        event = _event(candidate)
        return httpx.Response(200, json={
            "timestamp": _iso(stamp), "previous_timestamp": _iso(stamp),
            "next_timestamp": _iso(stamp),
            "data": {**event, "bookmakers": [
                {"key": SHARP_BOOK, "last_update": older,
                 "markets": [{"key": MARKET, "last_update": older,
                              "outcomes": [
                                  {"name": candidate["home"], "price": 2.10},
                                  {"name": "Draw", "price": 3.30},
                                  {"name": candidate["away"],
                                   "price": 3.60}]}]}]}})

    return httpx.MockTransport(handler)


def assemble_dev_report(out, *, out_of_scope, cap, mocked) -> str:
    """The G-B walk report — per-candidate verdicts plus the admissible
    match_id list that feeds ``oa_dev_manifest.py --emit``."""
    lines = ["# OA dev-slate acquisition — the G-B walk (OA Plan 2 v2, V4)",
             ""]
    if mocked:
        lines += ["**MODE: DRY-RUN.** Mocked transport; every figure below "
                  "is recorded-shape MOCK data, not real coverage.", ""]
    else:
        lines += ["**MODE: LIVE.** Real paid responses from The Odds API.",
                  ""]
    lines += [
        "THE_RULE walks candidates chronologically and buys the CUT snapshot "
        "first (admissibility is its property alone); T-24h follows only for "
        "admissible fixtures, and the walk stops at n_dev covered — so an "
        "uncovered candidate costs 10 credits, an unmatched one nothing "
        "beyond its day's shared listing.",
        "",
        f"- covered: **{out['covered']} / {out['n_dev']}** "
        f"(walked {out['walked']} candidates)",
        f"- out-of-acquisition-scope candidates (never listed, by config "
        f"evidence scope): {len(out_of_scope)}",
        f"- cumulative gate spend: **{out['cumulative']}** vs cap {cap}",
        f"- aborted: {out['aborted'] or '-'}",
        f"- overrun: {out['overrun'] or '-'}",
        "",
        "| # | matchday | fixture | tournament | listed | cut admissible | "
        "covered | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(out["results"], 1):
        cut = row.get("snapshots", {}).get(CUT_TAG) or {}
        note = row.get("error") or ""
        lines.append(
            f"| {i} | {row['date']} | {row['home']} v {row['away']} | "
            f"{row['tournament']} | "
            f"{'y' if row.get('event_found') else 'n'} | "
            f"{'y' if cut.get('admissible') else 'n'} | "
            f"{'y' if row.get('covered') else 'n'} | "
            f"{_table_text(note) if note else '-'} |")
    lines += ["", "## Admissible match ids (the dev-manifest evidence)", ""]
    for row in out["results"]:
        if row.get("covered"):
            lines.append(f"- {row['match_id']}")
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate-id", choices=GATE_IDS, required=True,
                    help="which approved spend gate this run bills to; the "
                         "journal tags every row with it and --max-credits "
                         "caps the GATE total across resumed runs")
    ap.add_argument("--fixtures", default=None,
                    help="YAML manifest: fixtures: [{fixture_id, pool, date "
                         "(venue-LOCAL matchday), home, away, kickoff_utc}] "
                         "— the EVAL plan (required unless --dev)")
    ap.add_argument("--dev", action="store_true",
                    help="walk the DEVELOPMENT slate instead of a fixtures "
                         "manifest: candidates come from THE_RULE applied to "
                         "the results store, kickoffs from the discovered "
                         "listings, and the walk stops at "
                         "oa_dev_slate.n_dev covered (G-B / V4)")
    ap.add_argument("--results-store", default=str(DEV_RESULTS_STORE),
                    help=f"--dev only: results store THE_RULE reads "
                         f"(default {DEV_RESULTS_STORE})")
    ap.add_argument("--dry-run", action="store_true",
                    help="mocked transport, zero network, zero credits (the "
                         "DEFAULT when no mode flag is given)")
    ap.add_argument("--live", action="store_true",
                    help="REAL PAID CALLS — requires the ODDS_API_KEY env var "
                         "AND --max-credits; the user's decision at the spend "
                         "gate, never an agent's")
    ap.add_argument("--max-credits", type=int, default=None,
                    help="hard CUMULATIVE cap for this gate: journal-restored "
                         "spend plus the outstanding plan is checked against "
                         "it before every call")
    ap.add_argument("--journal", default=None,
                    help="journal path — DRY-RUN ONLY (default "
                         f"{JOURNAL_DRY_RUN_DEFAULT}; mock receipts must "
                         "never enter the paid ledger). Live mode always "
                         f"uses the canonical {JOURNAL_DEFAULT}: the "
                         "cumulative cap and the flock are properties of ONE "
                         "resolved journal, and a per-run override defeats "
                         "both")
    ap.add_argument("--raw-dir", default=None,
                    help="content-addressed raw-response archive; on --live "
                         "this is always the repo's paid-evidence store and "
                         f"the flag is ignored (dry-run default "
                         f"{RAW_DIR_DRY_RUN_DEFAULT})")
    ap.add_argument("--store", default=None,
                    help=f"odds store root rebuilt from the receipts "
                         f"(default {STORE_DEFAULT} on --live; never written "
                         "on a dry-run)")
    ap.add_argument("--out", default=None,
                    help=f"report path (default {OUT_DEFAULT})")
    args = ap.parse_args(argv)
    if args.live and args.dry_run:
        ap.error("--live and --dry-run are mutually exclusive")
    if args.dev and args.fixtures:
        ap.error("--dev and --fixtures are mutually exclusive: the dev walk "
                 "derives its candidates from THE_RULE + the results store, "
                 "never from a hand-supplied manifest")
    if not args.dev and not args.fixtures:
        ap.error("--fixtures is required (or --dev for the development walk)")
    if args.dev and args.gate_id != DEV_GATE:
        ap.error(f"--dev bills to gate {DEV_GATE!r} (the development-slate "
                 f"gate); got --gate-id {args.gate_id!r}")
    if args.out is None:
        args.out = (DEV_OUT_DEFAULT if args.dev
                    else OUT_DEFAULT.format(gate=args.gate_id))

    if args.store and not args.live:
        # A dry-run's prices are fabricated, and load_odds_snapshots labels
        # every row source=the_odds_api: mock quotes must never reach a store
        # that reads as real.
        ap.error("--store requires --live: a dry-run's mock prices must never "
                 "be written to an odds store labelled as real")
    if args.raw_dir and args.live:
        ap.error("--raw-dir cannot be combined with --live: paid evidence "
                 "belongs in the repo's content-addressed archive, which is "
                 "what the receipts, the resume path and the store rebuild "
                 "all read from")
    if args.journal and args.live:
        # Finding 2: two live runners pointed at two --journal paths would
        # each restore ZERO prior spend and each hold its own flock — the
        # cumulative gate cap and the concurrency refusal are properties of
        # ONE canonical journal, and an override defeats both.
        ap.error("--journal cannot be combined with --live: the cumulative "
                 f"gate cap is computed from the canonical {JOURNAL_DEFAULT} "
                 "and the flock guards that one path — a per-run journal "
                 "would restore zero spend and authorize the whole cap again")

    if args.dev:
        dev_cfg = load_dev_slate_config()
        n_dev = dev_cfg.get("n_dev")
        if not n_dev:
            print("ABORT: oa_dev_slate.n_dev is unset — the walk's stopping "
                  "rule is a PRE-REGISTERED number, never a yield",
                  file=sys.stderr)
            return 1
        candidates, out_of_scope = load_dev_candidates(
            args.results_store, dev_cfg)
        days = len({(c["sport_key"], c["date"]) for c in candidates})
        # The CEILING, printed so the cap is judged against a mechanical
        # number: every candidate day lists once and every walked candidate
        # buys ONE cut snapshot (cut-only, see the walk's header). This is
        # the cost of walking EVERY candidate — the walk stops at n_dev
        # covered, so real spend is at most this and usually far below.
        ceiling = (days * DISCOVERY_CREDITS
                   + len(candidates) * SNAPSHOT_CREDITS)
        print(f"gate {args.gate_id} DEV WALK: {len(candidates)} candidate(s) "
              f"across {days} (sport_key, matchday) listing(s), target "
              f"n_dev={n_dev}; worst-case ceiling {ceiling} credits "
              f"(walk stops at n_dev covered; {len(out_of_scope)} candidate(s)"
              " out of acquisition scope, never listed)")
        fixtures, sport_keys = [], {}
    else:
        sport_keys = load_config()["odds"]["sport_keys"]
        fixtures = load_fixture_manifest(args.fixtures)
        groups = build_plan(fixtures, sport_keys, args.gate_id)
        rows = plan_rows(groups)
        projected = project_credits(rows)
        n_disc = sum(1 for r in rows if r["kind"] == "discovery")
        print(f"gate {args.gate_id}: {n_disc} discovery call(s) + "
              f"{len(rows) - n_disc} snapshot call(s), projected {projected} "
              "credits (whole plan; already-receipted calls are skipped)")

    if args.live:
        api_key = os.environ.get("ODDS_API_KEY")
        if not api_key:
            ap.error("--live requires the ODDS_API_KEY environment variable "
                     "(AND --max-credits N); the live acquisition is the "
                     "user's spend decision at the G-A / G-B gate")
        if args.max_credits is None:
            ap.error("--live requires --max-credits N (the CUMULATIVE "
                     "per-gate cap) in addition to ODDS_API_KEY")
        mode, transport, cap = "live", _live_transport(), args.max_credits
        raw_dir = _live_raw_dir(transport)
        if raw_dir is None:
            # Provenance is not optional here: the receipts name archived
            # bytes, the store is rebuilt from them, and a resumed run reads
            # them instead of re-buying. A transport that cannot produce paid
            # evidence must not run the live path at all.
            print("ABORT: --live with a non-network transport cannot produce "
                  "paid evidence (no raw archive) — refusing to place any "
                  "call", file=sys.stderr)
            return 1
        journal = Path(args.journal or JOURNAL_DEFAULT)
        store = Path(args.store or STORE_DEFAULT)
    else:
        mode, cap = "dry-run", None
        transport = (_dev_dry_run_transport(candidates) if args.dev
                     else _dry_run_transport(fixtures, sport_keys))
        api_key = _DRY_RUN_KEY
        raw_dir = Path(args.raw_dir or RAW_DIR_DRY_RUN_DEFAULT)
        journal = Path(args.journal or JOURNAL_DRY_RUN_DEFAULT)
        # A dry-run must never write an odds store: mock prices with a real
        # source label are exactly what load_odds_snapshots refuses.
        store = Path(args.store) if args.store else None

    try:
        _preflight_writable(raw_dir, journal.parent, Path(args.out).parent,
                            store)
    except OSError as exc:
        print("ABORT: storage preflight failed — refusing to place any paid "
              f"call: {exc}", file=sys.stderr)
        return 1

    try:
        if args.dev:
            summary = run_dev_acquisition(
                api_key=api_key, transport=transport, max_credits=cap,
                raw_dir=raw_dir, journal_path=journal, candidates=candidates,
                n_dev=n_dev, gate_id=args.gate_id, store_root=store,
                mode=mode)
        else:
            summary = run_acquisition(
                gate_id=args.gate_id, fixtures=fixtures,
                sport_keys=sport_keys, api_key=api_key, transport=transport,
                max_credits=cap, raw_dir=raw_dir, journal_path=journal,
                store_root=store, mode=mode)
    except (CreditCapError, AcquisitionError) as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1

    mocked = type(transport) is not httpx.HTTPTransport
    md = (assemble_dev_report(summary, out_of_scope=out_of_scope, cap=cap,
                              mocked=mocked) if args.dev
          else assemble_report(summary, cap=cap, mocked=mocked))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"wrote {out_path}")
    if args.dev:
        # A dry-run's verdicts are MOCK: they must never be mistaken for the
        # coverage evidence the manifest is frozen from, so they go to a
        # clearly-separate path.
        cov = (DEV_COVERAGE_DEFAULT if not mocked
               else DEV_COVERAGE_DEFAULT.replace(".yaml", ".dry-run.yaml"))
        print(f"wrote {write_dev_coverage(summary, path=cov, mocked=mocked)}")
    if summary["aborted"]:
        print(f"ABORT: {summary['aborted']}", file=sys.stderr)
        return 1
    if summary["overrun"]:
        print(f"OVER CAP: {summary['overrun']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
