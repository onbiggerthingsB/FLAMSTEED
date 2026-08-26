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

WHAT IT WRITES, AND WHAT IT REFUSES TO WRITE. One file per capture under
`data/epl/odds_snapshots/`, named `fixtures_<UTC ISO basic>.csv`, plus an
append-only `provenance.jsonl` carrying the SHA-256, the byte count, the fetch
instant and the columns seen. Bytes identical to the newest snapshot are NOT
written again — the source overwrites in place, so two runs between two
publications are the same file, and a directory of duplicates would make the
count of captures a lie about the count of publications.

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
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from epl import paths

__all__ = ["CaptureError", "FIXTURES_URL", "SNAPSHOT_DIR", "PROVENANCE_PATH",
           "CAPTURE_DAYS", "CAPTURE_DAY_NAMES", "Snapshot", "snapshot_name",
           "is_capture_day", "next_capture_day", "sha256_bytes",
           "read_provenance", "latest_snapshot", "capture", "main"]


class CaptureError(RuntimeError):
    """Anything this module refuses."""


#: The one file football-data publishes for the coming week, overwritten in
#: place. It covers every division it carries; the EPL rows are `Div == "E0"`.
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

SNAPSHOT_DIR = paths.DATA_DIR / "epl" / "odds_snapshots"
PROVENANCE_PATH = SNAPSHOT_DIR / "provenance.jsonl"

#: Monday is 0. TUESDAY AND FRIDAY — see the module header for why Friday alone
#: is not enough.
CAPTURE_DAYS: tuple[int, ...] = (1, 4)
CAPTURE_DAY_NAMES: tuple[str, ...] = ("Tuesday", "Friday")

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

    def as_dict(self) -> dict[str, Any]:
        return {"path": paths.rel(self.path), "sha256": self.sha256,
                "n_bytes": self.n_bytes, "fetched_at": self.fetched_at,
                "n_rows": self.n_rows, "n_epl_rows": self.n_epl_rows,
                "columns": list(self.columns), "written": self.written}


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def snapshot_name(when: pd.Timestamp | str) -> str:
    """`fixtures_<UTC ISO basic>.csv` — the filename IS the publication bound.

    The season CSV this file eventually becomes carries no timestamp at all,
    which is the whole reason §2.3 refuses a permissive leakage rule. The
    instant goes in the NAME so that it survives being copied, re-hashed or
    read by something that never opens the provenance ledger.
    """
    ts = pd.Timestamp(when)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return f"fixtures_{ts.strftime('%Y-%m-%dT%H%M%SZ')}.csv"


def is_capture_day(when: pd.Timestamp | str) -> bool:
    return int(pd.Timestamp(when).dayofweek) in CAPTURE_DAYS


def next_capture_day(when: pd.Timestamp | str) -> pd.Timestamp:
    """The next Tuesday or Friday strictly after ``when``, at midnight."""
    ts = pd.Timestamp(when).normalize()
    for step in range(1, 8):
        candidate = ts + pd.Timedelta(days=step)
        if is_capture_day(candidate):
            return candidate
    raise CaptureError("a week holds no capture day")   # pragma: no cover


def read_provenance(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Every capture on the record, oldest first."""
    path = Path(path) if path is not None else PROVENANCE_PATH
    if not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text().splitlines()):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise CaptureError(
                f"{paths.rel(path)} line {i + 1} is not JSON: {exc}") from exc
    return out


def latest_snapshot(directory: Path | str | None = None) -> Path | None:
    """The newest capture on disk, by filename — which sorts by instant."""
    directory = Path(directory) if directory is not None else SNAPSHOT_DIR
    if not directory.exists():
        return None
    files = sorted(directory.glob("fixtures_*.csv"))
    return files[-1] if files else None


def _download(url: str) -> bytes:
    import requests                                  # deferred: CI has no net
    resp = requests.get(url, timeout=_TIMEOUT_S,
                        headers={"User-Agent": _USER_AGENT})
    resp.raise_for_status()
    return resp.content


def capture(*, fetcher: Callable[[str], bytes] | None = None,
            directory: Path | str | None = None,
            provenance: Path | str | None = None,
            when: pd.Timestamp | str | None = None,
            url: str = FIXTURES_URL,
            force: bool = False) -> Snapshot:
    """Fetch the fixtures file, hash it, and store it if it is new.

    ``force`` writes a snapshot whose bytes match the newest one already on
    disk. The default refuses to: the source overwrites its single file in
    place, so two runs between two publications see the same bytes, and a
    directory of duplicates would make the count of captures a lie about the
    count of publications. It is a refusal to write, never a failure — the
    return value carries ``written = False`` and the run exits 0, because
    "nothing new was published" is the expected answer on most Tuesdays.
    """
    directory = Path(directory) if directory is not None else SNAPSHOT_DIR
    provenance = (Path(provenance) if provenance is not None
                  else directory / PROVENANCE_PATH.name)
    fetched_at = pd.Timestamp(when) if when is not None else \
        pd.Timestamp.now("UTC")
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.tz_localize("UTC")

    blob = (fetcher or _download)(url)
    if not isinstance(blob, bytes):
        raise CaptureError(f"the fetcher returned {type(blob).__name__}, not "
                           "bytes: a snapshot is the file's own bytes, and "
                           "anything decoded and re-encoded is a copy of it")
    if len(blob) < MIN_BYTES:
        raise CaptureError(
            f"{url} returned {len(blob)} bytes, under the {MIN_BYTES}-byte "
            "floor: that is an error page or an empty file, not a fixtures "
            "list, and storing it would put a hole in the archive that looks "
            "like a capture")

    digest = sha256_bytes(blob)
    try:
        frame = pd.read_csv(io_bytes(blob))
    except Exception as exc:                          # noqa: BLE001
        raise CaptureError(f"{url} did not parse as CSV: "
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

    newest = latest_snapshot(directory)
    duplicate = bool(newest is not None
                     and sha256_bytes(newest.read_bytes()) == digest)
    target = directory / snapshot_name(fetched_at)
    written = bool(force or not duplicate)
    if written:
        directory.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        with provenance.open("a") as fh:
            fh.write(json.dumps({
                "path": target.name, "sha256": digest, "n_bytes": len(blob),
                "fetched_at": fetched_at.isoformat(), "url": url,
                "n_rows": int(len(frame)), "n_epl_rows": n_epl,
                "capture_day": bool(is_capture_day(fetched_at)),
                "day_name": fetched_at.day_name(),
                "closing_columns": closing,
                "columns": list(columns),
            }) + "\n")
    else:
        target = newest                                # type: ignore[assignment]

    return Snapshot(path=target, sha256=digest, n_bytes=len(blob),
                    fetched_at=fetched_at.isoformat(), n_rows=int(len(frame)),
                    n_epl_rows=n_epl, columns=columns, written=written)


def io_bytes(blob: bytes):
    """A file-like over ``blob``. Named so the CSV read reads bytes, not text:
    the archive's files carry a UTF-8 BOM and decoding them here would make the
    stored bytes and the parsed bytes two different things."""
    import io
    return io.BytesIO(blob)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="store a snapshot whose bytes match the newest one")
    ap.add_argument("--dir", dest="directory", default=None)
    ap.add_argument("--url", default=FIXTURES_URL)
    ap.add_argument("--status", action="store_true",
                    help="print the capture record and the next capture day; "
                         "fetches nothing")
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        if args.status:
            now = pd.Timestamp.now("UTC")
            records = read_provenance(
                (Path(args.directory) / PROVENANCE_PATH.name)
                if args.directory else None)
            print(json.dumps({
                "cadence": list(CAPTURE_DAY_NAMES),
                "is_capture_day": is_capture_day(now),
                "next_capture_day": str(next_capture_day(now).date()),
                "n_captures": len(records),
                "latest": records[-1] if records else None,
                "note": "the operator runs this; no cron is wired here",
            }, indent=2, default=str))
            return 0

        snap = capture(directory=args.directory, url=args.url,
                       force=args.force)
        out = snap.as_dict()
        if not snap.written:
            out["why"] = ("the newest snapshot already holds these bytes; the "
                          "source overwrites one file in place, so nothing "
                          "new has been published since it")
        print(json.dumps(out, indent=2, default=str))
    except CaptureError as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
