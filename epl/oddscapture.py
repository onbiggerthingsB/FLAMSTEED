"""THE TUESDAY-AND-FRIDAY CAPTURE. The opening prices of matches that have not
been played yet, saved with the timestamp the season file will never carry.

WHY THIS EXISTS AND WHAT IT IS NOT FOR. `reports/epl_anchoring_prereg.md` §2.3
rules that only the odds of matches **already played strictly before the
cutoff** may reach `z_mkt`, and it rules so conservatively on purpose: the
archive carries **no publication timestamp**, so "this opening price was
published before C" is a claim about the world that the file cannot support.
The measured price of that conservatism is in §1.5 — the correlation with the
model's own errors falls from +0.1712 to +0.0982, so the conservative rule
keeps about 57% of the signal and the backtested number is a LOWER BOUND.

**This module does not relax that rule and cannot.** It captures snapshots so
that a FUTURE preregistration could support a permissive rule on evidence
rather than on assertion: a file named with the UTC instant it was fetched is
the publication bound the season CSV lacks. §2.3 is explicit that a live arm
reading the coming round's prices is a DIFFERENT MODEL needing its own
document, and §7 lists shipping such an arm on this backtest as an
invalidation. Nothing here is wired into `epl.mktprior`, and that is deliberate.

THE CADENCE IS TUESDAY **AND** FRIDAY, AND THE SECOND DAY IS THE POINT.
football-data.co.uk publishes ONE `fixtures.csv` covering the coming week and
**overwrites it in place**. A Friday-only capture therefore silently drops
every midweek round: a Tuesday or Wednesday fixture is priced, played, and
overwritten between two Friday runs, and nothing in the resulting archive says
a round is missing. Two captures a week is the smallest cadence that sees both
the midweek and the weekend programme.

    Tuesday  ~06:00 UTC   the midweek round, before it kicks off
    Friday   ~06:00 UTC   the weekend round, before it kicks off

**No cron is wired here.** The operator runs it; this header says when. A
scheduler committed by a harness is a standing side effect nobody reviewed, and
the one thing worse than a missing snapshot is a snapshot nobody knew was being
taken.

WHAT IT WRITES, AND WHAT IT REFUSES TO WRITE. One immutable artifact per unique
byte payload under `data/epl/odds_snapshots/`, named
`fixtures_<UTC ISO basic>.csv`, plus one append-only `provenance.jsonl`
observation per accepted fetch carrying the SHA-256, byte count, receipt instant
and columns seen. If two observations have identical bytes, BOTH observations
remain on the record and point to the same artifact: equality says that the
same price was still observable at the later instant. A same-second changed
payload receives a digest suffix rather than overwriting an earlier file.

Every non-empty ledger also has `provenance.head.json`, an atomically replaced,
fsynced witness containing its record count and final chain hash. The ledger's
own hash chain detects changed or removed interior rows; the external head
detects removal of its final row, including a duplicate observation that adds
no new CSV artifact. Unchained legacy ledgers are refused pending an explicit
whole-ledger migration.

The CSV is published through a same-directory temporary file, and its complete
provenance row is appended with `O_APPEND` and `fsync` while the snapshot
directory is locked, then the external head advances atomically. A failure is
rolled back only when the ledger and head prove that the attempted row is
absent, and only if the snapshot pathname still names the exact inode and bytes
this invocation published. An uncertain append is NEVER blindly truncated: the
ledger and snapshot are preserved and all readers stop for manual
reconciliation. A hard process kill can still interrupt multi-file storage, so
every read re-hashes every referenced CSV and refuses missing, orphaned,
undeclared duplicate references, ledger/head disagreement, or
metadata-inconsistent files. Status is therefore an integrity check, not a
count of filenames.

**It is not a harness file.** §6 freezes the bytes that can change a number in
the backtest, and this module changes none: it reads nothing the experiment
reads and writes nothing the experiment reads. It is operational, it is live,
and it is versioned like any other operational script.

NO BETTING (A9 (d)). This module stores market prices as a model input and as
nothing else. It computes no stake, no edge and no recommendation, and it
scores nothing against any market.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from epl import paths

__all__ = ["CaptureError", "FIXTURES_URL", "SNAPSHOT_DIR", "PROVENANCE_PATH",
           "PROVENANCE_HEAD_PATH",
           "CAPTURE_DAYS", "CAPTURE_DAY_NAMES", "Snapshot", "snapshot_name",
           "is_capture_day", "next_capture_day", "next_capture_at",
           "sha256_bytes",
           "read_provenance", "latest_snapshot", "capture_status",
           "adopt_orphan", "capture", "main"]


class CaptureError(RuntimeError):
    """Anything this module refuses."""


#: The one file football-data publishes for the coming week, overwritten in
#: place. It covers every division it carries; the EPL rows are `Div == "E0"`.
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

SNAPSHOT_DIR = paths.DATA_DIR / "odds_snapshots"
PROVENANCE_PATH = SNAPSHOT_DIR / "provenance.jsonl"
PROVENANCE_HEAD_PATH = SNAPSHOT_DIR / "provenance.head.json"

#: Monday is 0. TUESDAY AND FRIDAY — see the module header for why Friday alone
#: is not enough.
CAPTURE_DAYS: tuple[int, ...] = (1, 4)
CAPTURE_DAY_NAMES: tuple[str, ...] = ("Tuesday", "Friday")
CAPTURE_HOUR_UTC = 6

#: The columns the anchor's own panel reads (§0.3), checked on every capture so
#: that a feed which stops publishing them is noticed on the day rather than
#: at the next backtest.
REQUIRED_COLUMNS: tuple[str, ...] = ("Div", "Date", "HomeTeam", "AwayTeam",
                                     "AvgH", "AvgD", "AvgA")

#: A fixtures file smaller than this is an error page, not data.
MIN_BYTES = 512

_TIMEOUT_S = 60
_USER_AGENT = "worldcup-epl/1.0 (research; contact via repository)"


@dataclass(frozen=True)
class Snapshot:
    """One capture: where it landed, what it held, and when it was fetched."""

    path: Path
    sha256: str
    n_bytes: int
    fetched_at: str
    n_rows: int
    n_epl_rows: int
    columns: tuple[str, ...]
    written: bool
    duplicate_of: str | None = None
    observation_recorded: bool = True
    recovered_orphan: bool = False
    adoption_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"path": paths.rel(self.path), "sha256": self.sha256,
                "n_bytes": self.n_bytes, "fetched_at": self.fetched_at,
                "n_rows": self.n_rows, "n_epl_rows": self.n_epl_rows,
                "columns": list(self.columns), "written": self.written,
                "artifact_created": self.written,
                "observation_recorded": self.observation_recorded,
                "duplicate_of": self.duplicate_of,
                "recovered_orphan": self.recovered_orphan,
                "adoption_reason": self.adoption_reason}


@dataclass(frozen=True)
class _PublishedArtifact:
    """Identity of the directory entry this invocation actually published.

    A boolean "we created something" flag is insufficient for rollback: an
    uncooperative process can replace the pathname after publication and before
    a later provenance failure.  The rollback path therefore carries the
    staged inode plus its immutable content identity and deletes only that exact
    object.
    """

    device: int
    inode: int
    n_bytes: int
    sha256: str


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def snapshot_name(when: pd.Timestamp | str) -> str:
    """`fixtures_<UTC ISO basic>.csv` — the artifact's first receipt bound.

    The season CSV this file eventually becomes carries no timestamp at all,
    which is the whole reason §2.3 refuses a permissive leakage rule. The
    first instant goes in the NAME so that it survives being copied or
    re-hashed. Later observations of identical bytes live in the ledger and
    point back to that immutable artifact.
    """
    ts = _utc(when)
    return f"fixtures_{ts.strftime('%Y-%m-%dT%H%M%SZ')}.csv"


def is_capture_day(when: pd.Timestamp | str) -> bool:
    return int(_utc(when).dayofweek) in CAPTURE_DAYS


def next_capture_day(when: pd.Timestamp | str) -> pd.Timestamp:
    """The next Tuesday or Friday strictly after ``when``, at midnight."""
    ts = _utc(when).normalize()
    for step in range(1, 8):
        candidate = ts + pd.Timedelta(days=step)
        if is_capture_day(candidate):
            return candidate
    raise CaptureError("a week holds no capture day")   # pragma: no cover


def next_capture_at(when: pd.Timestamp | str) -> pd.Timestamp:
    """The next nominal 06:00 UTC operator slot, including later today."""
    ts = _utc(when)
    today = ts.normalize() + pd.Timedelta(hours=CAPTURE_HOUR_UTC)
    if is_capture_day(ts) and ts <= today:
        return today
    return next_capture_day(ts) + pd.Timedelta(hours=CAPTURE_HOUR_UTC)


def _latest_capture_at(when: pd.Timestamp | str) -> pd.Timestamp:
    ts = _utc(when)
    for step in range(0, 8):
        day = ts.normalize() - pd.Timedelta(days=step)
        candidate = day + pd.Timedelta(hours=CAPTURE_HOUR_UTC)
        if is_capture_day(day) and candidate <= ts:
            return candidate
    raise CaptureError("a week holds no previous capture slot")  # pragma: no cover


def _scheduled_slots(first: pd.Timestamp,
                     last: pd.Timestamp) -> list[pd.Timestamp]:
    """Every nominal 06:00 UTC slot in ``[first, last]``, oldest first.

    `_latest_capture_at` answers "which slot is newest". This answers "which
    slots were there", which is the only question a hole BEHIND a later
    capture can be asked about (A17).
    """
    slots: list[pd.Timestamp] = []
    slot, last = _utc(first), _utc(last)
    while slot <= last:
        slots.append(slot)
        slot = next_capture_day(slot) + pd.Timedelta(hours=CAPTURE_HOUR_UTC)
    return slots


def _cadence_start(records: list[dict[str, Any]]) -> pd.Timestamp | None:
    """The first slot this archive is answerable for, or None if it has none.

    An archive is not answerable for the cadence that ran before it existed —
    A14's `archive_started` bound, asked per SLOT instead of per archive. The
    sequence therefore begins at the slot the EARLIEST observation itself
    observes, or, when that observation is off-cadence or before 06:00 and so
    satisfies no slot, at the first slot after it.
    """
    if not records:
        return None
    first = min(_utc(r["fetched_at"]) for r in records)
    floor = _latest_capture_at(first)
    if floor.date() == first.date() and first >= floor:
        return floor
    return next_capture_at(first)


_PROVENANCE_VERSION = 2
_HEAD_VERSION = 1
_CHAIN_GENESIS = "GENESIS"
_TEMP_PREFIX = ".oddscapture-"


def _utc(when: pd.Timestamp | str) -> pd.Timestamp:
    ts = pd.Timestamp(when)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _canonical_record(record: dict[str, Any]) -> bytes:
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _record_digest(record: dict[str, Any]) -> str:
    return sha256_bytes(_canonical_record(record))


def _observation_id(fetched_at: pd.Timestamp, digest: str,
                    previous: str) -> str:
    return sha256_bytes(
        f"{fetched_at.isoformat()}|{digest}|{previous}".encode("utf-8"))


@contextlib.contextmanager
def _directory_lock(directory: Path, *, exclusive: bool):
    """Advisory archive lock without creating a second lock artifact."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(directory, os.O_RDONLY)
    except OSError as exc:
        raise CaptureError(
            f"cannot open snapshot archive {paths.rel(directory)}: {exc}") \
            from exc
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        except OSError as exc:
            raise CaptureError(
                f"cannot lock snapshot archive {paths.rel(directory)}: "
                f"{exc}") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _snapshot_path(directory: Path, record_path: Any) -> Path:
    value = str(record_path)
    candidate = Path(value)
    if candidate.is_absolute() or candidate.name != value:
        raise CaptureError(
            f"provenance path {value!r} is not one snapshot filename")
    if not value.startswith("fixtures_") or candidate.suffix != ".csv":
        raise CaptureError(f"provenance path {value!r} is not a fixture CSV")
    return directory / candidate


def _name_matches_receipt(name: str, fetched_at: pd.Timestamp,
                          digest: str) -> bool:
    expected = snapshot_name(fetched_at)
    if name == expected:
        return True
    expected_path = Path(expected)
    prefix = f"{expected_path.stem}_"
    if not name.startswith(prefix) or not name.endswith(expected_path.suffix):
        return False
    token = Path(name).stem[len(prefix):]
    return len(token) in (12, 16, 24, 32, 48, 64) and digest.startswith(token)


def _parse_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise CaptureError(
            f"provenance {paths.rel(path)} is not a regular file")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CaptureError(f"cannot read {paths.rel(path)}: {exc}") from exc
    out: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CaptureError(
                f"{paths.rel(path)} line {i + 1} is not JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise CaptureError(
                f"{paths.rel(path)} line {i + 1} is not a JSON object")
        out.append(record)
    return out


def _head_path(path: Path) -> Path:
    return path.with_suffix(".head.json")


def _head_payload(path: Path, records: int, record_sha256: str) \
        -> dict[str, Any]:
    return {
        "schema_version": _HEAD_VERSION,
        "ledger": path.name,
        "n_records": int(records),
        "head_record_sha256": str(record_sha256),
    }


def _read_head(path: Path) -> dict[str, Any]:
    head_path = _head_path(path)
    if not head_path.exists():
        raise CaptureError(
            f"{paths.rel(path)} has observations but durable head "
            f"{paths.rel(head_path)} is missing; tail loss cannot be ruled out")
    if head_path.is_symlink() or not head_path.is_file():
        raise CaptureError(
            f"provenance head {paths.rel(head_path)} is not a regular file")
    try:
        head = json.loads(head_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaptureError(
            f"cannot read provenance head {paths.rel(head_path)}: {exc}") \
            from exc
    if not isinstance(head, dict):
        raise CaptureError(
            f"provenance head {paths.rel(head_path)} is not a JSON object")
    return head


def _verify_head(path: Path, records: list[dict[str, Any]]) -> None:
    head_path = _head_path(path)
    if not records:
        if head_path.exists():
            raise CaptureError(
                f"{paths.rel(head_path)} exists for an empty provenance "
                "ledger; the ledger may have lost its tail")
        return
    head = _read_head(path)
    expected = _head_payload(path, len(records),
                             str(records[-1]["record_sha256"]))
    if head != expected:
        raise CaptureError(
            f"{paths.rel(head_path)} disagrees with the provenance ledger: "
            f"expected count/head {expected['n_records']}/"
            f"{expected['head_record_sha256']}, found "
            f"{head.get('n_records')}/{head.get('head_record_sha256')}")


def _read_provenance_unlocked(path: Path, directory: Path, *,
                              allowed_orphans: set[str] | None = None) \
        -> list[dict[str, Any]]:
    """Parse, re-hash, and reconcile the ledger with the archive."""
    safety_quarantines = sorted(
        p.name for p in directory.glob(".oddscapture-rollback-*.tmp"))
    if safety_quarantines:
        raise CaptureError(
            f"{paths.rel(directory)} contains rollback safety quarantine(s) "
            f"{', '.join(safety_quarantines[:3])}; STOP: preserved evidence "
            "requires manual reconciliation before this archive can be read "
            "or appended")
    records = _parse_ledger(path)
    files = {p.name: p for p in directory.glob("fixtures_*.csv")}
    allowed_orphans = set(allowed_orphans or ())
    if not records:
        unowned = sorted(set(files) - allowed_orphans)
        if unowned:
            names = ", ".join(unowned[:3])
            raise CaptureError(
                f"{paths.rel(directory)} holds {len(unowned)} snapshot file(s) "
                f"but {paths.rel(path)} has no provenance: {names}. STOP: do "
                "not fabricate a receipt; explicitly verify and migrate a "
                "valid-EPL orphan, or quarantine an invalid/non-EPL artifact "
                "before the archive can resume")
        _verify_head(path, records)
        return []

    required = {"path", "sha256", "n_bytes", "fetched_at", "n_rows",
                "n_epl_rows", "columns"}
    referenced: set[str] = set()
    observation_ids: set[str] = set()
    previous = _CHAIN_GENESIS
    for i, record in enumerate(records, start=1):
        missing = sorted(required - record.keys())
        if missing:
            raise CaptureError(
                f"{paths.rel(path)} line {i} lacks provenance fields {missing}")
        if record.get("record_sha256") is None:
            raise CaptureError(
                f"{paths.rel(path)} line {i} is unchained legacy provenance; "
                "STOP: explicitly migrate the complete legacy ledger before "
                "any read, status, adoption, or append")

        target = _snapshot_path(directory, record["path"])
        was_referenced = target.name in referenced
        if was_referenced:
            if record.get("duplicate_of") != target.name:
                raise CaptureError(
                    f"{paths.rel(path)} line {i} repeats snapshot "
                    f"{target.name} without declaring duplicate_of")
        elif record.get("duplicate_of") is not None:
            raise CaptureError(
                f"{paths.rel(path)} line {i} declares duplicate_of before "
                f"{target.name} has appeared")
        referenced.add(target.name)
        if not target.exists():
            raise CaptureError(
                f"{paths.rel(path)} line {i} names missing {target.name}")
        if target.is_symlink() or not target.is_file():
            raise CaptureError(
                f"{paths.rel(path)} line {i} names non-regular "
                f"{target.name}")

        try:
            blob = target.read_bytes()
        except OSError as exc:
            raise CaptureError(f"cannot read {target.name}: {exc}") from exc
        digest = sha256_bytes(blob)
        if record["sha256"] != digest:
            raise CaptureError(
                f"{target.name} hash is {digest}, provenance line {i} says "
                f"{record['sha256']}")
        try:
            stated_bytes = int(record["n_bytes"])
            stated_rows = int(record["n_rows"])
            stated_epl_rows = int(record["n_epl_rows"])
        except (TypeError, ValueError) as exc:
            raise CaptureError(
                f"{paths.rel(path)} line {i} has non-integer counts") from exc
        if stated_bytes != len(blob):
            raise CaptureError(
                f"{target.name} has {len(blob)} bytes, provenance line {i} "
                f"says {record['n_bytes']}")

        try:
            frame = pd.read_csv(io_bytes(blob))
        except Exception as exc:                         # noqa: BLE001
            raise CaptureError(
                f"{target.name} no longer parses as CSV: "
                f"{type(exc).__name__}: {exc}") from exc
        columns = tuple(str(c) for c in frame.columns)
        missing_columns = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing_columns:
            raise CaptureError(
                f"{target.name} lacks required columns {missing_columns}")
        n_epl = int((frame["Div"].astype(str) == "E0").sum()) \
            if "Div" in columns else 0
        if list(columns) != list(record["columns"]):
            raise CaptureError(
                f"{target.name} columns disagree with provenance line {i}")
        if stated_rows != len(frame) or stated_epl_rows != n_epl:
            raise CaptureError(
                f"{target.name} row counts disagree with provenance line {i}")
        if n_epl <= 0:
            raise CaptureError(
                f"{target.name} provenance records zero EPL rows")

        try:
            fetched_at = _utc(record["fetched_at"])
        except Exception as exc:                         # noqa: BLE001
            raise CaptureError(
                f"{paths.rel(path)} line {i} has invalid fetched_at") from exc
        is_repeated_observation = (was_referenced and
                                   record.get("duplicate_of") == target.name)
        if not is_repeated_observation and not _name_matches_receipt(
                target.name, fetched_at, digest):
            raise CaptureError(
                f"{target.name} does not encode fetched_at "
                f"{record['fetched_at']}")
        if "capture_day" in record and \
                bool(record["capture_day"]) != is_capture_day(fetched_at):
            raise CaptureError(
                f"{target.name} capture_day disagrees with fetched_at")
        if "day_name" in record and \
                str(record["day_name"]) != fetched_at.day_name():
            raise CaptureError(
                f"{target.name} day_name disagrees with fetched_at")

        stated = record.get("record_sha256")
        if record.get("schema_version") != _PROVENANCE_VERSION:
            raise CaptureError(
                f"{paths.rel(path)} line {i} has unsupported chained "
                f"schema {record.get('schema_version')!r}")
        if record.get("prev_record_sha256") != previous:
            raise CaptureError(
                f"{paths.rel(path)} line {i} breaks the provenance chain")
        actual = _record_digest(record)
        if stated != actual:
            raise CaptureError(
                f"{paths.rel(path)} line {i} record hash is invalid")
        previous = str(stated)
        observation_id = str(record.get("observation_id", ""))
        if not observation_id:
            raise CaptureError(
                f"{paths.rel(path)} line {i} lacks observation_id")
        if observation_id in observation_ids:
            raise CaptureError(
                f"{paths.rel(path)} line {i} repeats observation_id "
                f"{observation_id}")
        observation_ids.add(observation_id)

    orphaned = sorted(set(files) - referenced - allowed_orphans)
    if orphaned:
        raise CaptureError(
            f"{paths.rel(directory)} holds snapshot file(s) absent from "
            f"provenance: {', '.join(orphaned[:3])}")
    _verify_head(path, records)
    return records


def read_provenance(path: Path | str | None = None, *,
                    directory: Path | str | None = None) \
        -> list[dict[str, Any]]:
    """Every verified observation, oldest first.

    Reading is an audit: every referenced CSV is re-hashed and re-parsed, the
    ledger and directory must name exactly the same snapshot set, and the
    external head/count must witness the final chain row.
    """
    if path is None:
        directory = (Path(directory) if directory is not None
                     else SNAPSHOT_DIR)
        path = directory / PROVENANCE_PATH.name
    else:
        path = Path(path)
        directory = Path(directory) if directory is not None else path.parent
    if path.parent.resolve() != directory.resolve():
        raise CaptureError(
            "provenance must live in the snapshot directory so one archive "
            "lock covers both the ledger and its artifacts")
    if not directory.exists():
        return []
    with _directory_lock(directory, exclusive=False):
        return _read_provenance_unlocked(path, directory)


def _latest_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return max(enumerate(records),
               key=lambda item: (_utc(item[1]["fetched_at"]), item[0]))[1]


def _observes_slot(record: dict[str, Any], slot: pd.Timestamp) -> bool:
    fetched_at = _utc(record["fetched_at"])
    return fetched_at.date() == slot.date() and fetched_at >= slot


def latest_snapshot(directory: Path | str | None = None) -> Path | None:
    """The artifact for the latest verified receipt instant."""
    directory = Path(directory) if directory is not None else SNAPSHOT_DIR
    records = read_provenance(directory=directory,
                              path=directory / PROVENANCE_PATH.name)
    latest = _latest_record(records)
    if latest is None:
        return None
    return directory / str(latest["path"])


def capture_status(*, when: pd.Timestamp | str | None = None,
                   directory: Path | str | None = None,
                   provenance: Path | str | None = None) -> dict[str, Any]:
    """Verified archive and cadence status; this schedules nothing."""
    now = pd.Timestamp.now("UTC") if when is None else _utc(when)
    directory = Path(directory) if directory is not None else SNAPSHOT_DIR
    provenance = (Path(provenance) if provenance is not None
                  else directory / PROVENANCE_PATH.name)
    records = read_provenance(provenance, directory=directory)
    # ``when`` is an as-of boundary, not just a clock used to label the report.
    # A later receipt may already be present during a historical replay (or
    # because an adopted orphan carries a future/incorrect clock); it must not
    # satisfy an earlier slot or become that earlier report's latest record.
    as_of_records = [r for r in records if _utc(r["fetched_at"]) <= now]
    future_records = [r for r in records if _utc(r["fetched_at"]) > now]
    scheduled = [r for r in as_of_records
                 if is_capture_day(_utc(r["fetched_at"]))]
    off_cadence = len(as_of_records) - len(scheduled)
    pre_slot = [r for r in scheduled
                if _utc(r["fetched_at"]) <
                _utc(r["fetched_at"]).normalize()
                + pd.Timedelta(hours=CAPTURE_HOUR_UTC)]
    today_slot = now.normalize() + pd.Timedelta(hours=CAPTURE_HOUR_UTC)
    observed_today = any(_observes_slot(r, today_slot) for r in as_of_records)
    latest_slot = _latest_capture_at(now)
    latest_slot_observed = any(
        _observes_slot(r, latest_slot) for r in as_of_records)
    # THE CADENCE IS A SEQUENCE, NOT A HEAD (A17). `missed_latest_slot` asks
    # about ONE slot, so a hole stopped being reported the instant the NEXT
    # slot was captured — the archive kept the hole and the report lost it.
    # `missed_slots` asks about every slot this archive is answerable for and
    # never stops naming one. It is a SUPERSET of `missed_latest_slot` by
    # construction, so nothing that refused before stops refusing.
    start = _cadence_start(as_of_records)
    missed_slots = [] if start is None else [
        slot for slot in _scheduled_slots(start, latest_slot)
        if not any(_observes_slot(r, slot) for r in as_of_records)]
    if as_of_records and not latest_slot_observed \
            and latest_slot not in missed_slots:
        # The archive began AFTER the newest slot (its first receipt is
        # off-cadence or pre-06:00), so the sequence is empty — but A14
        # refuses on that slot today, and the set must not say less than
        # the head boolean does.
        missed_slots.append(latest_slot)
        missed_slots.sort()
    latest = _latest_record(as_of_records)
    return {
        "archive_verified": True,
        "cadence": list(CAPTURE_DAY_NAMES),
        "scheduler_wired": False,
        "is_capture_day": is_capture_day(now),
        "capture_due_today": bool(is_capture_day(now) and now >= today_slot
                                  and not observed_today),
        "next_capture_day": str(next_capture_day(now).date()),
        "next_capture_at": next_capture_at(now).isoformat(),
        "latest_scheduled_slot": latest_slot.isoformat(),
        "latest_slot_observed": latest_slot_observed,
        "missed_latest_slot": not latest_slot_observed,
        "missed_slots": [slot.isoformat() for slot in missed_slots],
        "n_missed_slots": len(missed_slots),
        "n_observations": len(as_of_records),
        "n_future_observations": len(future_records),
        "n_snapshot_files": len(list(directory.glob("fixtures_*.csv")))
        if directory.exists() else 0,
        "n_off_cadence_observations": off_cadence,
        "n_pre_slot_observations": len(pre_slot),
        "latest": latest,
        "note": "the operator runs this; no cron is wired here",
    }


def _download(url: str) -> bytes:
    import requests                                  # deferred: CI has no net
    try:
        resp = requests.get(url, timeout=_TIMEOUT_S,
                            headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as exc:
        raise CaptureError(f"fetching {url} failed: {exc}") from exc


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _new_target(directory: Path, fetched_at: pd.Timestamp,
                digest: str) -> Path:
    base = directory / snapshot_name(fetched_at)
    if not base.exists():
        return base
    for width in (12, 16, 24, 32, 48, 64):
        candidate = base.with_name(
            f"{base.stem}_{digest[:width]}{base.suffix}")
        if not candidate.exists():
            return candidate
    raise CaptureError(
        f"no collision-safe snapshot name remains for {base.name}")


def _publish_new_file(target: Path, blob: bytes) -> _PublishedArtifact:
    """Durably publish ``blob`` without an overwrite-capable operation."""
    try:
        fd, temporary = tempfile.mkstemp(prefix=_TEMP_PREFIX, suffix=".tmp",
                                         dir=target.parent)
    except OSError as exc:
        raise CaptureError(
            f"cannot stage snapshot in {paths.rel(target.parent)}: {exc}") \
            from exc
    temp_path = Path(temporary)
    published: _PublishedArtifact | None = None
    linked_by_us = False
    try:
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
                staged = os.fstat(fh.fileno())
                published = _PublishedArtifact(
                    device=int(staged.st_dev), inode=int(staged.st_ino),
                    n_bytes=len(blob), sha256=sha256_bytes(blob))
            os.link(temp_path, target)
            linked_by_us = True
            linked = os.stat(target, follow_symlinks=False)
            if (int(linked.st_dev), int(linked.st_ino)) != (
                    published.device, published.inode):  # pragma: no cover
                raise CaptureError(
                    f"published snapshot {target.name} changed identity before "
                    "its directory entry could be committed")
            _fsync_directory(target.parent)
        except FileExistsError as exc:                 # pragma: no cover
            raise CaptureError(
                f"refusing to overwrite existing snapshot {target.name}") \
                from exc
        except OSError as exc:
            if linked_by_us and published is not None:
                try:
                    _rollback_published_file(target, published)
                except CaptureError as rollback:
                    raise CaptureError(
                        f"publishing {target.name} failed and safe rollback "
                        f"also refused: publish={exc}; rollback={rollback}") \
                        from exc
            raise CaptureError(
                f"cannot publish snapshot {target.name}: {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)
    assert published is not None                         # for type checkers
    return published


def _matches_published_artifact(path: Path,
                                published: _PublishedArtifact) -> bool:
    """Whether ``path`` is still the exact inode and bytes we published."""
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    if not stat.S_ISREG(current.st_mode):
        return False
    if (int(current.st_dev), int(current.st_ino), int(current.st_size)) != (
            published.device, published.inode, published.n_bytes):
        return False
    try:
        return sha256_bytes(path.read_bytes()) == published.sha256
    except OSError:
        return False


def _rollback_published_file(target: Path,
                             published: _PublishedArtifact) -> bool:
    """Remove only this invocation's still-owned artifact.

    Checking a pathname and then unlinking it is a TOCTOU deletion race.  Move
    the current directory entry atomically to a private quarantine name first,
    then inspect the stable quarantined object.  If another process replaced
    the name, restore that object (or preserve it under the quarantine name if
    the original name was concurrently occupied) and refuse to delete it.
    """
    try:
        fd, quarantine_name = tempfile.mkstemp(
            prefix=".oddscapture-rollback-", suffix=".tmp",
            dir=target.parent)
        os.close(fd)
    except OSError as exc:
        raise CaptureError(
            f"cannot stage safe rollback for {target.name}: {exc}") from exc
    quarantine = Path(quarantine_name)
    moved = False
    try:
        try:
            os.replace(target, quarantine)
            moved = True
            _fsync_directory(target.parent)
        except FileNotFoundError:
            return False
        except OSError as exc:
            if moved:
                raise CaptureError(
                    f"moved {target.name} to safety quarantine "
                    f"{quarantine.name}, but could not certify the directory "
                    f"update; preserved it for manual reconciliation: {exc}") \
                    from exc
            raise CaptureError(
                f"cannot quarantine {target.name} for safe rollback: {exc}") \
                from exc

        if _matches_published_artifact(quarantine, published):
            try:
                quarantine.unlink()
                _fsync_directory(target.parent)
            except OSError as exc:
                raise CaptureError(
                    f"cannot remove owned rollback artifact "
                    f"{quarantine.name}: {exc}") from exc
            moved = False
            return True

        # We atomically moved somebody else's replacement. Restore without an
        # overwrite-capable operation, but retain the quarantine hard link even
        # after a successful restore. A second replacement could otherwise land
        # between the restore and cleanup and make an apparently safe unlink
        # erase the only remaining name for the unexpected object.
        try:
            os.link(quarantine, target, follow_symlinks=False)
            _fsync_directory(target.parent)
            location = f"{target.name} (safety copy {quarantine.name})"
        except FileExistsError:
            location = quarantine.name
        except OSError as exc:
            raise CaptureError(
                f"rollback found a replacement for {target.name} and could "
                f"not restore it; preserved at {quarantine.name}: {exc}") \
                from exc
        raise CaptureError(
            f"rollback refused to delete a replacement for {target.name}; "
            f"preserved it at {location}")
    finally:
        # Before the atomic move this is only our empty staging file. After the
        # move, an unexpected object must never be removed by cleanup here.
        if not moved:
            quarantine.unlink(missing_ok=True)


def _ensure_provenance_file(path: Path) -> None:
    existed = path.exists()
    if existed and (path.is_symlink() or not path.is_file()):
        raise CaptureError(
            f"provenance {paths.rel(path)} is not a regular file")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
        os.close(fd)
        if not existed:
            _fsync_directory(path.parent)
    except OSError as exc:
        raise CaptureError(
            f"cannot create provenance {paths.rel(path)}: {exc}") from exc


def _append_provenance(path: Path, record: dict[str, Any]) -> None:
    """Append exactly one complete, durable JSONL record."""
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("utf-8") + b"\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            written = os.write(fd, raw)
            if written != len(raw):                    # pragma: no cover
                raise CaptureError(
                    f"short provenance append: wrote "
                    f"{written}/{len(raw)} bytes; the uncertain tail was "
                    "preserved for manual reconciliation")
            os.fsync(fd)
        finally:
            os.close(fd)
    except CaptureError:
        raise
    except OSError as exc:
        raise CaptureError(
            f"cannot append/fsync provenance {paths.rel(path)}: {exc}; "
            "the uncertain tail was preserved for manual reconciliation") \
            from exc


def _write_head(path: Path, payload: dict[str, Any]) -> None:
    head_path = _head_path(path)
    if head_path.exists() and (head_path.is_symlink()
                               or not head_path.is_file()):
        raise CaptureError(
            f"provenance head {paths.rel(head_path)} is not a regular file")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("utf-8") + b"\n"
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=".oddscapture-head-", suffix=".tmp", dir=head_path.parent)
    except OSError as exc:
        raise CaptureError(
            f"cannot stage provenance head in {paths.rel(head_path.parent)}: "
            f"{exc}") from exc
    temp_path = Path(temporary)
    try:
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(raw)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_path, head_path)
            _fsync_directory(head_path.parent)
        except OSError as exc:
            raise CaptureError(
                f"cannot publish provenance head {paths.rel(head_path)}: "
                f"{exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _commit_provenance(path: Path, record: dict[str, Any], *,
                       n_records: int) -> None:
    """Durably append a row and advance the external tail witness."""
    _append_provenance(path, record)
    payload = _head_payload(path, n_records, str(record["record_sha256"]))
    try:
        _write_head(path, payload)
    except Exception as exc:
        # A readable replacement is not proof its directory entry was durable.
        # Preserve the mutually consistent state if present, but never turn an
        # fsync error into a reported successful capture.
        head_state = "head does not match the attempted row"
        try:
            if _read_head(path) == payload:
                head_state = ("head currently matches the attempted row but "
                              "its durability is uncertain")
        except CaptureError:
            pass
        raise CaptureError(
            f"cannot advance provenance head {paths.rel(_head_path(path))}: "
            f"{exc}; {head_state}; the appended ledger row was preserved and "
            "the archive requires manual reconciliation") from exc


def _provenance_definitely_excludes(path: Path, record: dict[str, Any]) -> bool:
    """Whether ledger and head prove this attempted publication is absent."""
    try:
        records = _parse_ledger(path)
        _verify_head(path, records)
    except Exception:                                  # noqa: BLE001
        # Any malformed/partial ledger or head mismatch is an uncertain commit.
        return False
    attempted_hash = str(record.get("record_sha256", ""))
    attempted_path = str(record.get("path", ""))
    return not any(
        str(row.get("record_sha256", "")) == attempted_hash
        or str(row.get("path", "")) == attempted_path
        for row in records)


def _inspect_blob(blob: Any, *, source: str) \
        -> tuple[str, pd.DataFrame, tuple[str, ...], list[str], int]:
    if not isinstance(blob, bytes):
        raise CaptureError(f"the fetcher returned {type(blob).__name__}, not "
                           "bytes: a snapshot is the file's own bytes, and "
                           "anything decoded and re-encoded is a copy of it")
    if len(blob) < MIN_BYTES:
        raise CaptureError(
            f"{source} returned {len(blob)} bytes, under the {MIN_BYTES}-byte "
            "floor: that is an error page or an empty file, not a fixtures "
            "list, and storing it would put a hole in the archive that looks "
            "like a capture")
    digest = sha256_bytes(blob)
    try:
        frame = pd.read_csv(io_bytes(blob))
    except Exception as exc:                          # noqa: BLE001
        raise CaptureError(f"{source} did not parse as CSV: "
                           f"{type(exc).__name__}: {exc}") from exc
    columns = tuple(str(c) for c in frame.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise CaptureError(
            f"the fixtures feed no longer carries {missing}. §0.3 rules the "
            "anchor's odds column to be Avg at the open BECAUSE it is the one "
            "column present in every season read and in the live feed; a feed "
            "that stops publishing it needs a ruling, not a silent capture.")
    closing = [c for c in columns
               if len(c) > 2 and c[-1] in "HDA" and "C" in c[1:-1]]
    n_epl = int((frame["Div"].astype(str) == "E0").sum())
    if n_epl <= 0:
        raise CaptureError(
            f"{source} parsed as a fixtures CSV but contains zero Div=E0 "
            "rows; recording it would turn a failed EPL observation into "
            "apparent availability evidence")
    return digest, frame, columns, closing, n_epl


def adopt_orphan(orphan: Path | str, *, observed_at: pd.Timestamp | str,
                 reason: str, directory: Path | str | None = None,
                 provenance: Path | str | None = None) -> Snapshot:
    """Explicitly ledger one valid-EPL artifact left by an interrupted write.

    Adoption never invents source provenance: the new row is marked recovered,
    its URL is null, and the operator-supplied reason is permanent. The caller
    must supply the receipt instant, which must agree with the filename. A zero-
    EPL file cannot be adopted as healthy evidence.
    """
    orphan = Path(orphan)
    directory = Path(directory) if directory is not None else orphan.parent
    provenance = (Path(provenance) if provenance is not None
                  else directory / PROVENANCE_PATH.name)
    if not str(reason).strip():
        raise CaptureError("orphan adoption requires a non-empty reason")
    if provenance.parent.resolve() != directory.resolve():
        raise CaptureError(
            "provenance must live in the snapshot directory so the archive "
            "can be locked and reconciled as one unit")
    target = _snapshot_path(directory, orphan.name)
    try:
        if orphan.resolve() != target.resolve():
            raise CaptureError(
                f"orphan {orphan} is not directly inside {directory}")
    except OSError as exc:
        raise CaptureError(f"cannot resolve orphan {orphan}: {exc}") from exc
    fetched_at = _utc(observed_at)
    with _directory_lock(directory, exclusive=True):
        if not target.exists():
            raise CaptureError(f"orphan {target.name} does not exist")
        if target.is_symlink() or not target.is_file():
            raise CaptureError(f"orphan {target.name} is not a regular file")
        records = _read_provenance_unlocked(
            provenance, directory, allowed_orphans={target.name})
        if any(str(r["path"]) == target.name for r in records):
            raise CaptureError(f"{target.name} is already on the provenance ledger")
        try:
            blob = target.read_bytes()
        except OSError as exc:
            raise CaptureError(f"cannot read orphan {target.name}: {exc}") from exc
        digest, frame, columns, closing, n_epl = _inspect_blob(
            blob, source=f"orphan {target.name}")
        if not _name_matches_receipt(target.name, fetched_at, digest):
            raise CaptureError(
                f"{target.name} does not encode observed_at "
                f"{fetched_at.isoformat()} and its content digest")
        previous = (str(records[-1]["record_sha256"])
                    if records else _CHAIN_GENESIS)
        record: dict[str, Any] = {
            "schema_version": _PROVENANCE_VERSION,
            "path": target.name,
            "sha256": digest,
            "n_bytes": len(blob),
            "requested_at": None,
            "fetched_at": fetched_at.isoformat(),
            "url": None,
            "source_provenance": "unknown_preledger_artifact",
            "recovered_orphan": True,
            "adoption_reason": str(reason).strip(),
            "n_rows": int(len(frame)),
            "n_epl_rows": n_epl,
            "capture_day": bool(is_capture_day(fetched_at)),
            "day_name": fetched_at.day_name(),
            "closing_columns": closing,
            "columns": list(columns),
            "duplicate_of": None,
            "force_requested": False,
            "prev_record_sha256": previous,
        }
        record["observation_id"] = _observation_id(
            fetched_at, digest, previous)
        existing_ids = {str(r.get("observation_id")) for r in records
                        if r.get("observation_id") is not None}
        if record["observation_id"] in existing_ids:
            raise CaptureError(
                f"observation_id {record['observation_id']} is already on "
                "the provenance ledger; refusing a duplicate append")
        record["record_sha256"] = _record_digest(record)
        _ensure_provenance_file(provenance)
        _commit_provenance(provenance, record,
                           n_records=len(records) + 1)
        _read_provenance_unlocked(provenance, directory)

    return Snapshot(path=target, sha256=digest, n_bytes=len(blob),
                    fetched_at=fetched_at.isoformat(), n_rows=int(len(frame)),
                    n_epl_rows=n_epl, columns=columns, written=False,
                    observation_recorded=True, recovered_orphan=True,
                    adoption_reason=str(reason).strip())


def capture(*, fetcher: Callable[[str], bytes] | None = None,
            directory: Path | str | None = None,
            provenance: Path | str | None = None,
            when: pd.Timestamp | str | None = None,
            url: str = FIXTURES_URL,
            force: bool = False) -> Snapshot:
    """Fetch, validate, and durably record one availability observation.

    Identical bytes are still a distinct observation. ``force`` remains as a
    compatibility argument, but no longer changes that fail-safe behaviour.
    """
    directory = Path(directory) if directory is not None else SNAPSHOT_DIR
    provenance = (Path(provenance) if provenance is not None
                  else directory / PROVENANCE_PATH.name)
    requested_at = _utc(when) if when is not None else pd.Timestamp.now("UTC")
    try:
        blob = (fetcher or _download)(url)
    except CaptureError:
        raise
    except Exception as exc:                           # noqa: BLE001
        raise CaptureError(
            f"fetching {url} failed: {type(exc).__name__}: {exc}") from exc
    # The conservative availability bound is receipt completion, not request
    # start. Tests and replay callers inject ``when`` as that bound.
    fetched_at = requested_at if when is not None else pd.Timestamp.now("UTC")
    digest, frame, columns, closing, n_epl = _inspect_blob(blob, source=url)

    if provenance.parent.resolve() != directory.resolve():
        raise CaptureError(
            "provenance must live in the snapshot directory so the archive "
            "can be locked and reconciled as one unit")
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CaptureError(
            f"cannot create snapshot archive {paths.rel(directory)}: {exc}") \
            from exc

    with _directory_lock(directory, exclusive=True):
        records = _read_provenance_unlocked(provenance, directory)
        _ensure_provenance_file(provenance)
        duplicate = next((str(r["path"]) for r in reversed(records)
                          if r["sha256"] == digest), None)
        artifact_needed = duplicate is None
        published: _PublishedArtifact | None = None
        target = (directory / duplicate if duplicate is not None
                  else _new_target(directory, fetched_at, digest))
        previous = (str(records[-1]["record_sha256"])
                    if records else _CHAIN_GENESIS)
        record: dict[str, Any] = {
            "schema_version": _PROVENANCE_VERSION,
            "path": target.name,
            "sha256": digest,
            "n_bytes": len(blob),
            "requested_at": requested_at.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "url": url,
            "n_rows": int(len(frame)),
            "n_epl_rows": n_epl,
            "capture_day": bool(is_capture_day(fetched_at)),
            "day_name": fetched_at.day_name(),
            "closing_columns": closing,
            "columns": list(columns),
            "duplicate_of": duplicate,
            "force_requested": bool(force),
            "prev_record_sha256": previous,
        }
        record["observation_id"] = _observation_id(
            fetched_at, digest, previous)
        existing_ids = {str(r.get("observation_id")) for r in records
                        if r.get("observation_id") is not None}
        if record["observation_id"] in existing_ids:
            raise CaptureError(
                f"observation_id {record['observation_id']} is already on "
                "the provenance ledger; refusing a duplicate append")
        record["record_sha256"] = _record_digest(record)
        try:
            if artifact_needed:
                published = _publish_new_file(target, blob)
            _commit_provenance(provenance, record,
                               n_records=len(records) + 1)
            # Do not report a successful capture until the complete archive,
            # including the just-published bytes and new head, passes the same
            # audit every later reader will enforce.
            _read_provenance_unlocked(provenance, directory)
        except Exception as exc:
            # Destructive rollback is allowed only after the durable ledger and
            # head prove this row/path absent. An uncertain append may include a
            # concurrent writer's tail, so preserve everything and fail closed.
            if published is not None:
                if not _provenance_definitely_excludes(provenance, record):
                    raise CaptureError(
                        f"provenance commit failed and is not demonstrably "
                        f"rolled back; preserved {target.name} and the ledger "
                        f"for manual reconciliation: {exc}") \
                        from exc
                try:
                    _rollback_published_file(target, published)
                except CaptureError as rollback:
                    raise CaptureError(
                        f"provenance commit failed and safe snapshot rollback "
                        f"also refused: commit={exc}; rollback={rollback}") \
                        from exc
            if isinstance(exc, CaptureError):
                raise
            raise CaptureError(
                f"could not commit provenance for {target.name}: {exc}") \
                from exc

    return Snapshot(path=target, sha256=digest, n_bytes=len(blob),
                    fetched_at=fetched_at.isoformat(), n_rows=int(len(frame)),
                    n_epl_rows=n_epl, columns=columns,
                    written=published is not None,
                    duplicate_of=duplicate)


def io_bytes(blob: bytes):
    """A file-like over ``blob``. Named so the CSV read reads bytes, not text:
    the archive's files carry a UTF-8 BOM and decoding them here would make the
    stored bytes and the parsed bytes two different things."""
    import io
    return io.BytesIO(blob)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="deprecated compatibility flag; every valid "
                         "observation is stored")
    ap.add_argument("--dir", dest="directory", default=None)
    ap.add_argument("--url", default=FIXTURES_URL)
    action = ap.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true",
                        help="verify the archive and report cadence; fetches "
                             "nothing and schedules nothing")
    action.add_argument("--adopt-orphan", metavar="CSV",
                        help="explicitly ledger a valid-EPL orphan without "
                             "inventing its source provenance")
    ap.add_argument("--observed-at",
                    help="UTC-aware receipt instant for --adopt-orphan")
    ap.add_argument("--adoption-reason",
                    help="permanent explanation for --adopt-orphan")
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        if args.status:
            now = pd.Timestamp.now("UTC")
            status = capture_status(when=now, directory=args.directory)
            # Retain the old count name for operator-facing compatibility.
            status["n_captures"] = status["n_observations"]
            print(json.dumps(status, indent=2, default=str))
            return 0

        if args.adopt_orphan:
            if not args.observed_at or not args.adoption_reason:
                raise CaptureError(
                    "--adopt-orphan requires --observed-at and "
                    "--adoption-reason")
            orphan = Path(args.adopt_orphan)
            snap = adopt_orphan(
                orphan, observed_at=args.observed_at,
                reason=args.adoption_reason,
                directory=(Path(args.directory) if args.directory
                           else orphan.parent))
            print(json.dumps(snap.as_dict(), indent=2, default=str))
            return 0

        snap = capture(directory=args.directory, url=args.url,
                       force=args.force)
        print(json.dumps(snap.as_dict(), indent=2, default=str))
    except CaptureError as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
