"""THE AVAILABILITY CAPTURE. Who is fit, when the source said so, and when we
heard it — a fourth bitemporal ledger, standing entirely on its own.

WHAT AUTHORIZES THIS AND WHAT BOUNDS IT. Amendment A11 (2026-08-27) is the
ruling: automated collection from public sources, including sources whose terms
restrict it, at the owner's stated risk, scoped to INTERNAL MODEL INPUTS. The
independent reviewer's licence objection is preserved in that entry as the
standing counterpoint, not overwritten here. Four bounds come with the ruling
and all four are structural in this module:

* (a) inputs only — nothing this captures is republished on any surface, and
  the manifest below is written so that it *cannot* be: it carries digests and
  counts, never a byte of source text;
* (b) raw snapshots hashed and retained locally under gitignored `data/`, with
  a TRACKED manifest — attestation without redistribution;
* (c) the alternatives (written permission, the paid licence-clean feed) stay
  open, which is why nothing downstream may depend on this EXCEPT the one use
  a later amendment preregisters by name — today that is A12's `dc_1x2_avail`
  shadow arm and nothing else (see "WHAT IT FEEDS, AND UNDER WHAT RULING"
  below). Re-scoped by the appended note to A12, 2026-08-27; the bound itself
  is unchanged, and an unnamed dependency is still not authorised;
* (d) personal scale — one pull a day against one public endpoint. There is no
  cron here. The operator runs it; a scheduler committed by a harness is a
  standing side effect nobody reviewed.

NO MODEL INTEGRATION, AND THAT IS THE POINT. A11 pre-states that nothing enters
a model without its own preregistration through the covariate gate, whose only
verdict to date remains UNVALIDATED. So this module imports no model: the
capture is standalone by construction, and a test asserts it.

WHAT IT FEEDS, AND UNDER WHAT RULING. Amendment A12 (2026-08-27) is that
preregistration, for ONE use and no other: `dc_1x2_avail`, a match-only SHADOW
challenger that transforms the published `dc_native` 1X2 marginals in its own
ledger and touches no published number, no table, no issuance and no gate. A12
(e) moved the boundary this module's own test had drawn, and moved it exactly
as far as the arm needs: `epl.availarm` is the ONLY authorised bridge — it
imports this module's read side and the matchboard's scoring side — and
`epl.livecycle` still does not import this module. The covariate gate is
untouched and its only verdict remains UNVALIDATED; entry into the PUBLISHED
law would be a gate run plus its own amendment, and A12 pre-commits neither.

THE READ SIDE A12 ADDED. :func:`as_of` — given a clock, the latest snapshot OUR
pull clock observed at or before it, loaded from the raw bytes and grouped by
club key. It binds on `observed_at` only, never on the source's `news_added`;
it reads the derived ledger not at all (`minutes` and `now_cost` are not ledger
columns); and it changes nothing about `pull`, `verify`, `status`, the manifest
format or the three commands below.

TWO CLOCKS, THE SAME TWO AS `epl.season`. `observed_at` is OUR pull clock — the
instant this process fetched the payload. `news_added` is the SOURCE's own
clock — the instant FPL says the note was filed. They are different questions
and the ledger answers both, because the interesting one is answerable only
with both: a status row whose `news_added` postdates a fixture's kickoff is
refusable for that fixture at read time, and no single-clock archive can say
that. `observed_at` is an INPUT to everything here; the CLI reads a wall clock,
the library never does, and a test moves the clock to prove it.

DELTA ENCODING, BECAUSE A DAILY FULL DUMP IS A LIE ABOUT CHANGE. Six hundred
players a day is a quarter of a million rows a season, of which a few thousand
say anything. A row is appended only when a tracked field differs from that
player's last known state; the first snapshot appends everyone. Corrections and
regressions are new rows — a player flagged and then cleared has three rows and
the middle one still says what it said. Nothing edits. The consequence to hold
onto: the ledger's row count is a count of CHANGES, and a quiet day is attested
by a manifest line with `n_rows_appended: 0`, not by silence.

WHICH ARTIFACT IS THE TRUTH. The raw bytes are the record; the tracked manifest
is the attestation of those bytes; the ledger is DERIVED and rebuildable, which
is why it is gitignored and why `verify` re-derives it from the raw snapshots
and compares byte for byte. If the two ever disagree, the bytes win and the
ledger is the thing that was tampered with.

    data/epl/availability/raw/bootstrap_<UTC stamp>.json.gz   gitignored bytes
    data/epl/availability/availability_ledger.jsonl           gitignored, derived
    epl/season/2026_27/availability_manifest.jsonl            TRACKED attestation

EIGHT TYPED REFUSALS, NONE OF THEM A SILENT NARROW — five on the capture side
and three A12 added with the read side (`NoSnapshotAsOf`: nothing was observed
by the clock asked about, which is the arm's ABSTENTION and not a defect;
`SnapshotMissing`: the manifest attests bytes the archive no longer holds;
`SnapshotDigestMismatch`: the bytes on disk are not the attested bytes).
`SourceUnreachable` (no
bytes, or bytes that are not the feed), `AvailabilitySchemaDrift` (an asserted
field is GONE, or is still there and no longer carries what it asserted —
`news_added` that is not a timestamp is the live case; additions are tolerated,
because the raw snapshot keeps everything the ledger does not read),
`ClockRegression` (the source's own
high-water clock walked backwards: it restated history, and accepting that
silently would leave a ledger that disagrees with the archive it came from),
`ManifestConflict` (a line already exists for this stamp with a different
digest — two payloads cannot both be what one instant served), `TeamUnmapped`
(a club the season manifest does not contain; the club registry is strict on
purpose and a slugger would mint a second Tottenham).

    python -m epl.availability pull [--dry-run]
    python -m epl.availability verify
    python -m epl.availability status

Source: https://fantasy.premierleague.com/api/bootstrap-static/
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from epl import paths, season as season_mod, teams

__all__ = [
    "AvailabilityError", "SourceUnreachable", "AvailabilitySchemaDrift",
    "ClockRegression", "ManifestConflict", "TeamUnmapped",
    "BOOTSTRAP_URL", "SEASON", "AVAILABILITY_DIR", "RAW_DIR", "LEDGER_PATH",
    "MANIFEST_FILENAME", "PLAYER_FIELDS", "AVAILABILITY_FIELDS", "TEAM_FIELDS",
    "LEDGER_FIELDS", "TRACKED_FIELDS", "CLOCK_TOLERANCE",
    "Snapshot", "PullReport", "VerifyReport",
    "default_manifest_path", "sha256_bytes", "stamp_for", "iso_z",
    "read_manifest", "read_ledger", "latest_state", "assert_schema",
    "team_key_map", "snapshot_rows", "pull", "verify", "status",
    "render_status", "main",
    # the A12 as-of read side
    "NoSnapshotAsOf", "SnapshotMissing", "SnapshotDigestMismatch",
    "AS_OF_FIELDS", "AS_OF_PLAYER_FIELDS", "CHANCE_BOUNDS", "AsOfSnapshot",
    "select_manifest_line", "as_of", "instant", "instant_of_stamp",
    "read_payload_bytes", "parse_payload",
]

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
SEASON = "2026/27"

AVAILABILITY_DIR = paths.DATA_DIR / "availability"
RAW_DIR = AVAILABILITY_DIR / "raw"
LEDGER_PATH = AVAILABILITY_DIR / "availability_ledger.jsonl"
MANIFEST_FILENAME = "availability_manifest.jsonl"

#: The five availability fields A11 pre-states, asserted present on every row.
AVAILABILITY_FIELDS = ("status", "chance_of_playing_this_round",
                       "chance_of_playing_next_round", "news", "news_added")
#: Those five plus identity, club membership and price — the asserted set.
PLAYER_FIELDS = ("id", "web_name", "team", *AVAILABILITY_FIELDS, "now_cost")
TEAM_FIELDS = ("id", "name")

#: A12's read side needs two fields the CAPTURE never reads — `now_cost` is
#: already asserted (it is cheap and it is the price the source publishes) and
#: `minutes` is not. Asserted on the way OUT rather than on the way in, so the
#: capture's own contract is exactly A11's and this one is exactly A12's: a
#: payload that lost `minutes` is still a lawful capture and is not a lawful
#: input to the weighting.
AS_OF_FIELDS = ("minutes", "now_cost")

#: What :func:`as_of` hands a caller per player, in this order. Identity, club,
#: the status fields the rule binds on, both weighting fields, and the source's
#: own clock — which this rule never reads (A12 (h): the arm binds on
#: `observed_at` only) and which the (g) audit will want beside every flag.
AS_OF_PLAYER_FIELDS = ("player_id", "web_name", "team_key", "status",
                       "chance_next", "news", "news_added", "minutes",
                       "now_cost")

#: The ledger row. Everything in it except the two provenance stamps is
#: tracked, so "did anything change?" is exactly "did the row change?".
LEDGER_FIELDS = ("player_id", "web_name", "team_key", "status", "chance_this",
                 "chance_next", "news", "news_added", "observed_at",
                 "snapshot_sha256")
TRACKED_FIELDS = ("web_name", "team_key", "status", "chance_this",
                  "chance_next", "news", "news_added")

#: How far the source's high-water `news_added` may slip backwards before it is
#: a restatement rather than a rounding artefact. Deliberately tight: the feed
#: stamps to the microsecond and never goes back a minute by accident.
CLOCK_TOLERANCE = pd.Timedelta("60s")

_TIMEOUT_S = 30
_USER_AGENT = ("epl-availability-capture/1.0 (personal-scale; internal model "
               "inputs only; see reports/epl_sim_amendments.md A11)")


# --------------------------------------------------------------------------
# the refusal family
# --------------------------------------------------------------------------
class AvailabilityError(RuntimeError):
    """Base of everything this module refuses on."""


class SourceUnreachable(AvailabilityError):
    """No bytes, or bytes that are not the feed."""


class AvailabilitySchemaDrift(AvailabilityError):
    """An asserted field is gone. Additions are not drift."""


class ClockRegression(AvailabilityError):
    """A clock walked backwards. Either of the two, and the message says which:
    the SOURCE's (it restated history) or OURS (the pull clock jumped back)."""


class ManifestConflict(AvailabilityError):
    """A manifest line exists for this stamp carrying a different digest."""


class TeamUnmapped(AvailabilityError):
    """A club the season manifest does not contain. Refuse; never slug."""


class NoSnapshotAsOf(AvailabilityError):
    """No manifest line was observed at or before the clock asked about.

    NOT a defect and NOT a skip. A12 (b) makes this the arm's ABSTENTION case:
    the capture began on 2026-08-27 and every issuance older than that is a
    question this archive cannot answer. Typed so a caller can tell "we had not
    started looking" apart from "we looked and the bytes are gone".
    """


class SnapshotMissing(AvailabilityError):
    """The manifest attests a payload the archive no longer holds."""


class SnapshotDigestMismatch(AvailabilityError):
    """The bytes on disk are not the bytes the manifest attested."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _utc(value, what: str = "observed_at") -> pd.Timestamp:
    """UTC, second-resolution, and never NaT.

    `pd.Timestamp` turns `None`, `nan`, `""` and `NaT` into NaT rather than
    raising, and NaT compares False against every bound — the same silent leak
    `epl.season._require_stamp` exists to stop.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise AvailabilityError(
            f"{what}={value!r} is not a timestamp ({exc}) — our own clock is "
            "what every row this call writes is dated by, so a value we "
            "cannot read is a row nobody could reproduce") from exc
    if pd.isna(ts):
        raise AvailabilityError(
            f"{what}={value!r} resolves to NaT, which compares False against "
            "every bound — a snapshot stamped with it would sort nowhere and "
            "bound nothing")
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.floor("s")


def _source_clock(value, what: str) -> pd.Timestamp:
    """The SOURCE's clock, parsed for COMPARISON only — never for storage.

    `news_added` is FPL's stamp, not ours, and its format is FPL's to change.
    Two things used to escape this module untyped when it did: a value that is
    not a timestamp at all (pandas' `DateParseError`) and one row stamped
    without a zone beside six hundred stamped with one (`TypeError: Cannot
    compare tz-naive and tz-aware timestamps`). Neither is in the refusal
    family, and `main()` turns an `AvailabilityError` into `STOP` + exit 2 and
    lets everything else traceback — so the capture died without saying what it
    refused.

    An unreadable stamp is DRIFT: the field is still there and no longer
    carries what the capture asserts it carries. A stamp with no zone is read
    as UTC, the same rule `_utc` applies to our own clock — a bounded guess
    about someone else's, bounded because the string written to the ledger row
    is still the source's own, byte for byte. Only the comparison is normalised.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise AvailabilitySchemaDrift(
            f"{what} is {value!r}, which is not a timestamp ({exc}). The "
            "source's clock is half of what this ledger exists to record; a "
            "capture that cannot read it must refuse rather than store a "
            "high-water mark it made up") from exc
    if pd.isna(ts):
        raise AvailabilitySchemaDrift(
            f"{what} is {value!r}, which resolves to NaT — it compares False "
            "against every bound, so a clock regression could never be seen")
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def iso_z(value) -> str:
    """Our own stamps, printed one way: `2026-08-27T09:00:00Z`.

    Formatted from the timestamp's own fields rather than through `strftime`,
    which routes through the `time` module (and its locale) for a value that
    has nothing to do with the wall clock. The moved-clock test proves the
    point: with `time` swapped out, a strftime-formatted stamp came back
    "FROZEN" and every filename in the archive would have collided.
    """
    ts = _utc(value)
    return (f"{ts.year:04d}-{ts.month:02d}-{ts.day:02d}"
            f"T{ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}Z")


def instant(value, what: str = "clock") -> pd.Timestamp:
    """UTC, second-resolution, never NaT — the ONE clock reader both sides use.

    Public because A12's arm compares its own clocks (a snapshot's
    `observed_at` against an issuance's `observed_by`) and two modules parsing
    stamps two ways is how one of them starts answering a naive string
    differently from an aware one.
    """
    return _utc(value, what)


def stamp_for(value) -> str:
    """The filename stamp, which sorts in instant order."""
    ts = _utc(value)
    return (f"{ts.year:04d}{ts.month:02d}{ts.day:02d}"
            f"T{ts.hour:02d}{ts.minute:02d}{ts.second:02d}Z")


def instant_of_stamp(stamp) -> pd.Timestamp:
    """The exact inverse of :func:`stamp_for`: `20260827T023039Z` -> a UTC instant.

    A filed row carries the snapshot's STAMP, not its `observed_at`, and the
    write-time point-in-time guard has to answer "was this observed at or
    before the issuance's knowledge clock?" from the row alone — without the
    manifest, which is exactly the object a caller could substitute. The stamp
    is `observed_at` floored to the second by construction, so reading it back
    is a parse and not an inference.
    """
    text = str(stamp)
    if not re.fullmatch(r"\d{8}T\d{6}Z", text):
        raise AvailabilitySchemaDrift(
            f"{text!r} is not a snapshot stamp: the archive writes "
            "`YYYYMMDDThhmmssZ` and a value of another shape names no instant, "
            "so nothing can be said about when it was observed")
    return _utc(f"{text[0:4]}-{text[4:6]}-{text[6:8]}T"
                f"{text[9:11]}:{text[11:13]}:{text[13:15]}Z", "snapshot stamp")


def raw_name(stamp: str) -> str:
    return f"bootstrap_{stamp}.json.gz"


def default_manifest_path(season: str = SEASON,
                          root: Path | str | None = None) -> Path:
    root = Path(root) if root is not None else season_mod.SEASON_ROOT
    return root / season_mod.season_dir_name(season) / MANIFEST_FILENAME


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AvailabilityError(f"{path}:{lineno} is not JSON: {exc}") from exc
    return rows


def _jsonl_line(row: dict) -> str:
    """One row, one way. Byte-stability is what `verify` compares."""
    return json.dumps(row, sort_keys=True) + "\n"


def _append_jsonl(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(_jsonl_line(row))


def read_manifest(path: Path | str | None = None, *,
                  season: str = SEASON) -> list[dict]:
    """The tracked attestation, in file order."""
    return _read_jsonl(Path(path) if path is not None
                       else default_manifest_path(season))


def read_ledger(path: Path | str | None = None) -> list[dict]:
    """The derived ledger, in file order."""
    return _read_jsonl(Path(path) if path is not None else LEDGER_PATH)


def latest_state(rows: Sequence[dict]) -> dict[int, tuple]:
    """Each player's last known state, which is what a delta is measured from.

    Delta encoding makes the ledger's newest row per player the CURRENT state,
    so this doubles as "what does the archive believe right now".
    """
    out: dict[int, tuple] = {}
    for row in rows:
        out[int(row["player_id"])] = tuple(row[f] for f in TRACKED_FIELDS)
    return out


def _flagged(row: dict) -> bool:
    return row["status"] != "a" or bool(row["news"])


# --------------------------------------------------------------------------
# the payload: schema, clubs, rows
# --------------------------------------------------------------------------
def assert_schema(payload: Any, *, n_clubs: int) -> None:
    """Refuse a payload that lost a field. Additions are tolerated.

    The asymmetry is deliberate. The feed grows a column most months and the
    raw snapshot keeps every one of them whether the ledger reads it or not; a
    field that VANISHES is a ruling, because the alternative is a ledger full
    of nulls that read as "he is fine" and mean "we stopped being told".
    """
    if not isinstance(payload, dict):
        raise AvailabilitySchemaDrift(
            f"the feed returned a {type(payload).__name__}, not an object")
    for key in ("elements", "teams"):
        if key not in payload:
            raise AvailabilitySchemaDrift(
                f"the feed no longer carries a top-level {key!r}")
        if not isinstance(payload[key], list):
            raise AvailabilitySchemaDrift(
                f"top-level {key!r} is a {type(payload[key]).__name__}, not a list")

    if not payload["elements"]:
        raise AvailabilitySchemaDrift(
            "the feed carries an empty 'elements' list — that is a stub or an "
            "outage, and storing it would put a hole in the archive that looks "
            "like a capture")
    if len(payload["teams"]) != n_clubs:
        raise AvailabilitySchemaDrift(
            f"the feed carries {len(payload['teams'])} clubs, expected "
            f"{n_clubs}: the bootstrap of a {n_clubs}-club league carries "
            f"{n_clubs} clubs, and anything else is a different competition or "
            "a half-built pre-season payload")

    for i, team in enumerate(payload["teams"]):
        missing = [f for f in TEAM_FIELDS if f not in team]
        if missing:
            raise AvailabilitySchemaDrift(
                f"teams[{i}] no longer carries {missing}")
    for i, element in enumerate(payload["elements"]):
        if not isinstance(element, dict):
            raise AvailabilitySchemaDrift(
                f"elements[{i}] is a {type(element).__name__}, not an object")
        missing = [f for f in PLAYER_FIELDS if f not in element]
        if missing:
            raise AvailabilitySchemaDrift(
                f"elements[{i}] (id={element.get('id')!r}, "
                f"web_name={element.get('web_name')!r}) no longer carries "
                f"{missing} — the capture asserts {list(PLAYER_FIELDS)} and "
                "refuses rather than narrowing to what survived")


def team_key_map(payload: dict, manifest: season_mod.Manifest) -> dict[int, str]:
    """FPL team id -> the season's club key. Strict, like `epl.teams`.

    Two ways to fail and both refuse: a spelling the club registry does not
    know (register it there rather than inventing a key here) and a club the
    registry knows but this season does not field. The second is the one that
    matters in August — Burnley resolves perfectly well and is not in 2026/27.
    """
    out: dict[int, str] = {}
    for row in payload["teams"]:
        name = str(row["name"])
        try:
            _, key = teams.resolve(name)
        except Exception as exc:                            # noqa: BLE001
            raise TeamUnmapped(
                f"the feed's club {name!r} (id {row['id']}) resolves to no key "
                f"in the epl.teams registry: {exc}. Register the spelling "
                "there rather than slugging it here — a permissive slugger "
                "would mint a second club with its own history") from exc
        if key not in manifest.clubs:
            raise TeamUnmapped(
                f"the feed's club {name!r} maps to {key!r}, which is not one "
                f"of {manifest.season}'s twenty clubs. Refusing: a row filed "
                "against a club the season does not contain is a row nothing "
                "downstream can read")
        out[int(row["id"])] = key
    return out


def snapshot_rows(payload: dict, *, observed_at, snapshot_sha256: str,
                  team_keys: dict[int, str]) -> list[dict]:
    """Every player's full state at one snapshot, in player-id order."""
    stamp = iso_z(observed_at)
    rows = []
    for element in payload["elements"]:
        team_id = int(element["team"])
        if team_id not in team_keys:
            raise TeamUnmapped(
                f"player {element.get('web_name')!r} (id {element.get('id')}) "
                f"plays for team id {team_id}, which the payload's own teams "
                "list never declared")
        news_added = element["news_added"]
        if news_added:
            # read and thrown away: the row stores the source's own string, and
            # this asks only whether the source's clock is still a clock.
            _source_clock(
                news_added,
                f"news_added for {element.get('web_name')!r} "
                f"(id {element.get('id')})")
        rows.append({
            "player_id": int(element["id"]),
            "web_name": str(element["web_name"]),
            "team_key": team_keys[team_id],
            "status": element["status"],
            "chance_this": element["chance_of_playing_this_round"],
            "chance_next": element["chance_of_playing_next_round"],
            "news": element["news"],
            # the SOURCE's clock, stored verbatim: parsing and reprinting it
            # would make our formatting the record instead of theirs.
            "news_added": news_added,
            "observed_at": stamp,
            "snapshot_sha256": snapshot_sha256,
        })
    rows.sort(key=lambda r: r["player_id"])
    return rows


def _max_news_added(rows: Sequence[dict]) -> str | None:
    """The source's own high-water clock for this snapshot, verbatim.

    The maximum is taken over normalised timestamps and the string RETURNED is
    the source's own — the manifest attests what the source said, not what our
    parser made of it.
    """
    stamped = [r["news_added"] for r in rows if r["news_added"]]
    if not stamped:
        return None
    return max(stamped, key=lambda s: _source_clock(s, "news_added"))


def _delta(rows: Sequence[dict], previous: dict[int, tuple]) -> list[dict]:
    """The rows whose tracked state differs from the player's last known one."""
    out = []
    for row in rows:
        state = tuple(row[f] for f in TRACKED_FIELDS)
        if previous.get(row["player_id"]) != state:
            out.append(row)
    return out


def _regression(previous_max: str | None, current_max: str | None):
    """How far the source's clock walked backwards, or None if it did not."""
    if previous_max is None or current_max is None:
        return None
    slip = (_source_clock(previous_max,
                          "the previous snapshot's max_news_added")
            - _source_clock(current_max, "this snapshot's max news_added"))
    return slip if slip > CLOCK_TOLERANCE else None


# --------------------------------------------------------------------------
# the pull
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Snapshot:
    stamp: str
    observed_at: str
    sha256: str
    n_bytes: int
    n_players: int
    max_news_added: str | None
    raw_path: Path
    clock_regression: bool


@dataclass(frozen=True)
class PullReport:
    snapshot: Snapshot
    rows: tuple[dict, ...]
    written: bool
    dry_run: bool
    first_snapshot: bool
    n_flagged: int
    n_ledger_rows_before: int
    manifest_line: dict = field(repr=False, default_factory=dict)


def _download(url: str, *, timeout: int = _TIMEOUT_S) -> bytes:
    import urllib.error                              # deferred: CI has no net
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise SourceUnreachable(f"{url}: {exc}") from exc


def pull(*, now, fetcher: Callable[[str], bytes] | None = None,
         raw_dir: Path | str | None = None,
         ledger_path: Path | str | None = None,
         manifest_path: Path | str | None = None,
         season: str = SEASON, season_root: Path | str | None = None,
         url: str = BOOTSTRAP_URL, dry_run: bool = False,
         accept_restatement: bool = False) -> PullReport:
    """One capture: fetch, assert, hash, store, attest, append the deltas.

    `now` has no default and that is deliberate — it is the pull clock, it goes
    on every row this call writes, and a capture whose `observed_at` came from
    somewhere unstated is a row nobody can reproduce. The CLI reads the wall
    clock and passes it; this function reads no clock at all.

    Nothing is written until every refusal has had its chance: a drifted
    schema, an unmappable club, a backwards source clock and a conflicting
    manifest line all leave the archive exactly as they found it.
    """
    observed_at = _utc(now)
    raw_dir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    ledger_path = Path(ledger_path) if ledger_path is not None else LEDGER_PATH
    manifest_path = (Path(manifest_path) if manifest_path is not None
                     else default_manifest_path(season, season_root))
    manifest = season_mod.load_manifest(
        season, **({"root": season_root} if season_root is not None else {}))

    try:
        blob = (fetcher or _download)(url)
    except AvailabilityError:
        raise
    except Exception as exc:                                # noqa: BLE001
        raise SourceUnreachable(
            f"{url}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(blob, bytes):
        raise SourceUnreachable(
            f"the fetcher returned {type(blob).__name__}, not bytes: the raw "
            "payload IS the record, and anything decoded and re-encoded is a "
            "copy of it")
    try:
        payload = json.loads(blob)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceUnreachable(
            f"{url} returned {len(blob)} bytes that are not JSON ({exc}) — an "
            "error page is the source being unavailable in substance, not a "
            "schema change") from exc

    assert_schema(payload, n_clubs=len(manifest.clubs))
    team_keys = team_key_map(payload, manifest)

    digest = sha256_bytes(blob)
    stamp = stamp_for(observed_at)
    rows = snapshot_rows(payload, observed_at=observed_at,
                         snapshot_sha256=digest, team_keys=team_keys)
    high_water = _max_news_added(rows)

    lines = read_manifest(manifest_path)
    same_stamp = [l for l in lines if l["stamp"] == stamp]
    if same_stamp:
        if same_stamp[-1]["sha256"] != digest:
            raise ManifestConflict(
                f"a manifest line already exists for {stamp} carrying sha256 "
                f"{same_stamp[-1]['sha256'][:12]}…, and this pull hashes to "
                f"{digest[:12]}…. Two payloads cannot both be what one instant "
                "served; overwriting the line would destroy the attestation")
        return PullReport(
            snapshot=Snapshot(stamp=stamp, observed_at=iso_z(observed_at),
                              sha256=digest, n_bytes=len(blob),
                              n_players=len(rows), max_news_added=high_water,
                              raw_path=raw_dir / raw_name(stamp),
                              clock_regression=bool(
                                  same_stamp[-1].get("clock_regression", False))),
            rows=(), written=False, dry_run=dry_run, first_snapshot=False,
            n_flagged=sum(1 for r in rows if _flagged(r)),
            n_ledger_rows_before=len(read_ledger(ledger_path)),
            manifest_line=dict(same_stamp[-1]))

    if lines and _utc(lines[-1]["observed_at"]) > observed_at:
        raise ClockRegression(
            f"this pull's observed_at ({iso_z(observed_at)}) is EARLIER than "
            f"the last snapshot's ({lines[-1]['observed_at']}). Our own pull "
            "clock walked backwards — an NTP correction, or a machine that "
            "does not know what day it is. Nothing has been written: a delta "
            "dated before the state it changed from makes 'last row in the "
            "file' and 'latest row by observed_at' two different answers")

    slip = _regression(lines[-1]["max_news_added"] if lines else None,
                       high_water)
    if slip is not None and not accept_restatement:
        raise ClockRegression(
            f"the source's high-water news_added went BACKWARDS by {slip}: the "
            f"last snapshot saw {lines[-1]['max_news_added']} and this one "
            f"sees {high_water}. The source restated history. Nothing has been "
            "written; look at what changed, then re-run with "
            "--accept-restatement to record the restatement on the manifest")

    ledger_rows = read_ledger(ledger_path)
    previous = latest_state(ledger_rows)
    first_snapshot = not previous
    delta = _delta(rows, previous)

    line = {
        "stamp": stamp,
        "observed_at": iso_z(observed_at),
        "season": manifest.season,
        "sha256": digest,
        "n_bytes": len(blob),
        "n_players": len(rows),
        "max_news_added": high_water,
        "n_rows_appended": len(delta),
        "clock_regression": slip is not None,
        "raw": raw_name(stamp),
        "url": url,
    }
    snapshot = Snapshot(stamp=stamp, observed_at=line["observed_at"],
                        sha256=digest, n_bytes=len(blob), n_players=len(rows),
                        max_news_added=high_water,
                        raw_path=raw_dir / raw_name(stamp),
                        clock_regression=bool(line["clock_regression"]))
    report = PullReport(
        snapshot=snapshot, rows=tuple(delta), written=not dry_run,
        dry_run=dry_run, first_snapshot=first_snapshot,
        n_flagged=sum(1 for r in rows if _flagged(r)),
        n_ledger_rows_before=len(ledger_rows), manifest_line=line)
    if dry_run:
        return report

    raw_dir.mkdir(parents=True, exist_ok=True)
    # mtime=0: the container is reproducible, so the only thing that can make
    # two snapshots differ is the payload. It also means this writes no clock.
    snapshot.raw_path.write_bytes(gzip.compress(blob, mtime=0))
    _append_jsonl(manifest_path, [line])
    if delta:
        _append_jsonl(ledger_path, delta)
    return report


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    n_snapshots: int
    n_rows: int
    n_rows_rederived: int
    problems: tuple[str, ...]


def verify(*, raw_dir: Path | str | None = None,
           ledger_path: Path | str | None = None,
           manifest_path: Path | str | None = None,
           season: str = SEASON,
           season_root: Path | str | None = None) -> VerifyReport:
    """Re-derive everything derivable and compare it to what is on disk.

    Three questions, in the order that matters. Do the stored bytes still hash
    to what the tracked manifest says they hash to? Does the source's clock
    walk forwards across the archive, or does some line restate history without
    saying so? And does replaying every snapshot in order reproduce the ledger
    BYTE for byte — which is the only check that catches a hand-edited row,
    because a row edited to something plausible is still plausible.

    This returns a report rather than raising: a checker that stops at the
    first problem cannot tell the operator how much of the archive is sound.
    """
    raw_dir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    ledger_path = Path(ledger_path) if ledger_path is not None else LEDGER_PATH
    manifest_path = (Path(manifest_path) if manifest_path is not None
                     else default_manifest_path(season, season_root))
    manifest = season_mod.load_manifest(
        season, **({"root": season_root} if season_root is not None else {}))

    lines = read_manifest(manifest_path)
    on_disk = ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else ""
    problems: list[str] = []
    previous: dict[int, tuple] = {}
    rederived: list[str] = []
    previous_max: str | None = None

    seen: dict[str, str] = {}
    previous_observed: str | None = None
    for i, line in enumerate(lines, start=1):
        stamp = line["stamp"]
        try:
            # read before anything else uses it: `verify` promises a REPORT,
            # and a line whose own clock is unreadable used to escape through
            # `_utc` and abandon every later line unchecked — which is the one
            # thing a checker run against a suspect manifest must not do.
            expected_stamp = stamp_for(line["observed_at"])
            out_of_order = (previous_observed is not None
                            and _utc(line["observed_at"])
                            < _utc(previous_observed))
        except AvailabilityError as exc:
            problems.append(f"manifest line {i}: {exc}")
            continue
        if out_of_order:
            problems.append(
                f"manifest line {i}: observed_at {line['observed_at']} is "
                f"earlier than line {i - 1}'s {previous_observed} — the pull "
                "clock walked backwards, which `pull` refuses, so this "
                "manifest was not assembled by `pull`")
        previous_observed = line["observed_at"]
        if stamp in seen and seen[stamp] != line["sha256"]:
            problems.append(
                f"manifest line {i}: a second line for stamp {stamp} carries a "
                f"different sha256 ({seen[stamp][:12]}… vs "
                f"{line['sha256'][:12]}…)")
        seen[stamp] = line["sha256"]
        if stamp != expected_stamp:
            problems.append(
                f"manifest line {i}: stamp {stamp} does not match observed_at "
                f"{line['observed_at']}")

        path = raw_dir / line.get("raw", raw_name(stamp))
        if not path.exists():
            problems.append(f"manifest line {i}: raw snapshot {path.name} is "
                            "missing from the archive")
            continue
        try:
            blob = gzip.decompress(path.read_bytes())
        except OSError as exc:
            problems.append(f"{path.name}: not readable as gzip ({exc})")
            continue
        digest = sha256_bytes(blob)
        if digest != line["sha256"]:
            problems.append(
                f"{path.name}: sha256 {digest[:12]}… does not match the "
                f"manifest's {line['sha256'][:12]}… — the bytes changed after "
                "they were attested")
            continue
        if len(blob) != line["n_bytes"]:
            problems.append(f"{path.name}: {len(blob)} bytes, manifest says "
                            f"{line['n_bytes']}")

        try:
            payload = json.loads(blob)
            assert_schema(payload, n_clubs=len(manifest.clubs))
            team_keys = team_key_map(payload, manifest)
            rows = snapshot_rows(payload, observed_at=line["observed_at"],
                                 snapshot_sha256=digest, team_keys=team_keys)
        except AvailabilityError as exc:
            problems.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue

        if len(rows) != line["n_players"]:
            problems.append(f"{path.name}: {len(rows)} players, manifest says "
                            f"{line['n_players']}")
        high_water = _max_news_added(rows)
        if high_water != line["max_news_added"]:
            problems.append(
                f"{path.name}: max news_added {high_water!r}, manifest says "
                f"{line['max_news_added']!r}")
        slip = _regression(previous_max, high_water)
        if slip is not None and not line.get("clock_regression", False):
            problems.append(
                f"manifest line {i}: the source's max news_added went "
                f"backwards by {slip} ({previous_max} -> {high_water}) on a "
                "line that is not marked as a restatement")
        # the PREVIOUS line's high-water mark, not the last non-null one, so
        # this asks the same question `pull` asked and cannot fail a capture
        # that `pull` was right to accept.
        previous_max = high_water

        delta = _delta(rows, previous)
        if len(delta) != line.get("n_rows_appended", len(delta)):
            problems.append(
                f"{path.name}: re-derivation appends {len(delta)} rows, "
                f"manifest says {line['n_rows_appended']}")
        rederived.extend(_jsonl_line(row) for row in delta)
        # UPDATE, never replace: `pull` measures a delta against the player's
        # last known state (the ledger's newest row for him), which outlives his
        # absence from a payload. Replacing the map here would forget a vanished
        # player and re-derive a row on his return that no pull ever wrote.
        previous.update(latest_state(rows))

    attested = {line.get("raw", raw_name(line["stamp"])) for line in lines}
    for path in sorted(raw_dir.glob("bootstrap_*.json.gz")) if raw_dir.exists() else []:
        if path.name not in attested:
            problems.append(
                f"{path.name}: a raw snapshot no manifest line attests — "
                "either a pull died between writing the bytes and appending "
                "the line, or something put it there that was not a pull")

    text = "".join(rederived)
    if text != on_disk:
        problems.append(
            "the ledger on disk is not what re-deriving the raw snapshots "
            f"produces ({len(on_disk.splitlines())} rows on disk, "
            f"{len(rederived)} re-derived). The bytes are the record and the "
            "ledger is derived, so the ledger is the thing that changed")

    return VerifyReport(ok=not problems, n_snapshots=len(lines),
                        n_rows=len(on_disk.splitlines()),
                        n_rows_rederived=len(rederived),
                        problems=tuple(problems))


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
def status(*, raw_dir: Path | str | None = None,
           ledger_path: Path | str | None = None,
           manifest_path: Path | str | None = None,
           season: str = SEASON, season_root: Path | str | None = None,
           now=None, limit: int = 12) -> dict:
    """The operator's one screen: last pull, who is flagged, what just moved.

    `now` is optional and is used for one thing — the age of the last pull. It
    is an input, so this function reads no clock either; the CLI passes one.
    """
    ledger_path = Path(ledger_path) if ledger_path is not None else LEDGER_PATH
    manifest_path = (Path(manifest_path) if manifest_path is not None
                     else default_manifest_path(season, season_root))
    lines = read_manifest(manifest_path)
    rows = read_ledger(ledger_path)

    current: dict[int, dict] = {}
    for row in rows:
        current[int(row["player_id"])] = row
    flagged = sorted((r for r in current.values() if _flagged(r)),
                     key=lambda r: (r["team_key"], r["player_id"]))
    last = lines[-1] if lines else None
    since = (sum(1 for r in rows if r["snapshot_sha256"] == last["sha256"])
             if last else 0)
    age_h = None
    if last is not None and now is not None:
        age_h = round(
            (_utc(now) - _utc(last["observed_at"])).total_seconds() / 3600.0, 2)

    return {
        "season": season,
        "n_snapshots": len(lines),
        "last_pull": dict(last) if last else None,
        "age_hours": age_h,
        "n_players": last["n_players"] if last else 0,
        "n_ledger_rows": len(rows),
        "n_tracked_players": len(current),
        "n_changes_since_previous": since,
        "n_flagged": len(flagged),
        "flagged": [dict(r) for r in flagged[:limit]],
        "n_flagged_not_shown": max(0, len(flagged) - limit),
        "manifest_path": str(manifest_path),
        "ledger_path": str(ledger_path),
    }


def render_status(report: dict) -> str:
    """One screen. Never the whole flagged list — that is what the ledger is for."""
    out = [f"availability capture — {report['season']}"]
    if report["last_pull"] is None:
        out.append("  no snapshots yet: nothing has been pulled into "
                   f"{report['manifest_path']}")
        return "\n".join(out) + "\n"
    last = report["last_pull"]
    age = "" if report["age_hours"] is None else f"  ({report['age_hours']}h ago)"
    out += [
        f"  last pull   {last['stamp']}{age}",
        f"              {last['n_players']} players, {last['n_bytes']} bytes, "
        f"sha256 {last['sha256'][:12]}…",
        f"              source high-water news_added {last['max_news_added']}",
        f"  snapshots   {report['n_snapshots']}",
        f"  ledger      {report['n_ledger_rows']} rows over "
        f"{report['n_tracked_players']} players "
        f"({report['n_changes_since_previous']} appended by the last pull)",
        f"  flagged     {report['n_flagged']} players not fully available",
    ]
    for row in report["flagged"]:
        chance = "—" if row["chance_this"] is None else f"{row['chance_this']}%"
        out.append(f"    {row['team_key']:<15} {row['web_name']:<18} "
                   f"{row['status']} {chance:<5} {row['news']}")
    if report["n_flagged_not_shown"]:
        out.append(f"    … {report['n_flagged_not_shown']} more (the ledger has all of them)")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# the as-of read side (A12)
# --------------------------------------------------------------------------
# ONE READER, AND IT BINDS ON OUR CLOCK ONLY. A12 (b) selects the snapshot for
# a fixture by taking the manifest lines whose `observed_at` is at or before
# the issuance's `observed_by` and keeping the LATEST of them. `news_added` —
# the source's own clock — is never consulted here: not as a filter, not as a
# tiebreak. A12 (h) states the consequence plainly, and it is the reason this
# archive's point-in-time claim is a property of how the ledger was built
# rather than of the source's honesty: anything in a payload we pulled at or
# before `observed_by` was in our hands then, whatever the source later says
# about when it knew.
#
# THE BYTES ARE THE RECORD AND THE MANIFEST IS THE ATTESTATION. This reader
# loads the raw snapshot and checks its digest against the tracked line before
# reading a field out of it. THE DERIVED LEDGER IS NOT READ AT ALL, and could
# not be: `minutes` and `now_cost` are not ledger columns.
#
# NOTHING HERE CHANGES THE CAPTURE. `pull`, `verify`, `status`, the manifest
# format and the three CLI commands are exactly what A11 built; this is a
# second door onto the same archive, opened by A12 for the shadow arm and for
# nothing else.

@dataclass(frozen=True)
class AsOfSnapshot:
    """One archived payload, resolved at a clock and grouped by club.

    `line` is the tracked manifest line verbatim, so a caller can record WHICH
    snapshot it read by the archive's own identifiers rather than by a path.
    """
    stamp: str
    observed_at: str
    sha256: str
    raw_path: Path
    n_players: int
    line: dict
    squads: dict[str, tuple[dict, ...]]

    def squad(self, club_key: str) -> tuple[dict, ...]:
        """This club's players, or `()` — the CALLER decides what empty means.

        A12 makes an empty squad a refusal in the arm, where the feature is
        computed and where a zero would be mistaken for a fit side. Here it is
        just an answer about an archive.
        """
        return self.squads.get(club_key, ())


def select_manifest_line(lines: Sequence[dict], clock) -> dict | None:
    """The latest manifest line observed at or before `clock`, or None.

    Separated from :func:`as_of` because A12 (f) step 2 re-derives the
    SELECTION for a filed row — "is the snapshot this row names the one the
    rule would have chosen?" — and that question must be answerable from the
    tracked manifest alone, without the gitignored archive being present.

    File order is instant order (`pull` refuses a backwards pull clock), but
    the maximum is taken over parsed stamps anyway, with the later LINE winning
    a tie: a reader that trusted line order would answer a hand-assembled
    manifest confidently and wrongly.
    """
    bound = _utc(clock, "clock")
    best: dict | None = None
    best_at: pd.Timestamp | None = None
    for i, line in enumerate(lines):
        observed = _utc(line["observed_at"], f"manifest line {i + 1}'s observed_at")
        if observed > bound:
            continue
        if best_at is None or observed >= best_at:
            best, best_at = line, observed
    return best


#: The source's own ladder is 25/50/75 and its own bounds are 0 and 100.
#: A12 (b) writes `u_p = (100 - chance)/100` and then states that `feat_side` is
#: "a number in [0, 1]" — which is a claim about the SOURCE's domain as much as
#: about the arithmetic. A chance of 200 gives `u_p = -1` and a negative
#: feature: a tilt with the sign REVERSED, moving a side's probability the way
#: it moves when players are available.
CHANCE_BOUNDS = (0, 100)


def _domain(element: Any) -> None:
    """Refuse a payload outside the source's own domain. NEVER clamp it.

    A clamp is the worse failure of the two: it prices a payload this rule
    cannot read and files the result as if it could, where a refusal says the
    feed changed and stops. The three fields A12's weighting stands on are
    checked, and each names the player and the value.
    """
    chance = element["chance_of_playing_next_round"]
    if chance is not None:
        try:
            value = float(chance)
        except (TypeError, ValueError) as exc:
            raise AvailabilitySchemaDrift(
                f"elements[id={element.get('id')!r}, "
                f"web_name={element.get('web_name')!r}] carries "
                f"chance_of_playing_next_round={chance!r}, which is not a "
                "number — A12 (b) divides by it") from exc
        low, high = CHANCE_BOUNDS
        if not low <= value <= high:
            raise AvailabilitySchemaDrift(
                f"elements[id={element.get('id')!r}, "
                f"web_name={element.get('web_name')!r}] carries "
                f"chance_of_playing_next_round={chance!r}, outside the source's "
                f"own {low}..{high}. A12 (b) reads it as "
                "`u_p = (100 - chance)/100` and states the feature is a number "
                "in [0, 1]; this value puts `u_p` outside that interval and "
                "REVERSES the sign of the tilt. Refused, not clamped: a clamp "
                "prices a payload this rule cannot read and files the answer as "
                "if it could")
    for field in AS_OF_FIELDS:
        try:
            value = int(element[field])
        except (TypeError, ValueError) as exc:
            raise AvailabilitySchemaDrift(
                f"elements[id={element.get('id')!r}, "
                f"web_name={element.get('web_name')!r}] carries "
                f"{field}={element[field]!r}, which is not a whole number — "
                "A12 (b) sums it into a denominator") from exc
        if value < 0:
            raise AvailabilitySchemaDrift(
                f"elements[id={element.get('id')!r}, "
                f"web_name={element.get('web_name')!r}] carries "
                f"{field}={value}. A12 (b) makes both weighting fields SHARES "
                "of a club total, and a negative term can cancel another "
                "player's weight, shrink the denominator, or flip the branch "
                "the switchover picks — none of which is a share of anything")


def read_payload_bytes(path: Path) -> bytes:
    """The decompressed payload, or a TYPED refusal — never a traceback.

    A truncated or non-gzip container escaped the refusal family entirely and
    surfaced as `EOFError` / `BadGzipFile`, which `main()` does not catch. It is
    a digest question in substance: the bytes on disk are not the bytes that
    were attested, and here they are not even bytes anything can hash.
    """
    try:
        return gzip.decompress(path.read_bytes())
    except (OSError, EOFError, zlib.error) as exc:
        raise SnapshotDigestMismatch(
            f"{path.name} is not readable as gzip ({type(exc).__name__}: "
            f"{exc}). The bytes are the record, and a container this archive "
            "cannot open holds no record at all — so nothing read out of it is "
            "what the manifest attested") from exc


def parse_payload(blob: bytes, path: Path) -> Any:
    """The payload, or a TYPED refusal. Same reasoning, one layer up."""
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AvailabilitySchemaDrift(
            f"{path.name} decompresses to {len(blob)} bytes that are not JSON "
            f"({exc}) — an error page stored under a snapshot's name is the "
            "source having been unavailable in substance, and it is not a "
            "payload this rule can read") from exc


def _as_of_player(element: Any, team_keys: dict[int, str]) -> dict:
    team_id = int(element["team"])
    if team_id not in team_keys:
        raise TeamUnmapped(
            f"player {element.get('web_name')!r} (id {element.get('id')}) "
            f"plays for team id {team_id}, which the payload's own teams list "
            "never declared")
    missing = [f for f in AS_OF_FIELDS if f not in element]
    if missing:
        raise AvailabilitySchemaDrift(
            f"elements[id={element.get('id')!r}, "
            f"web_name={element.get('web_name')!r}] carries no {missing} — the "
            "as-of read asserts "
            f"{list(AS_OF_FIELDS)} on top of the capture's own set, because a "
            "weighting computed over a field that is not there would be a "
            "feature of zero wearing a fit squad's face")
    _domain(element)
    return {
        "player_id": int(element["id"]),
        "web_name": str(element["web_name"]),
        "team_key": team_keys[team_id],
        "status": element["status"],
        "chance_next": element["chance_of_playing_next_round"],
        "news": element["news"],
        # the SOURCE's clock, verbatim and unread by any rule: see A12 (h).
        "news_added": element["news_added"],
        "minutes": int(element["minutes"]),
        "now_cost": int(element["now_cost"]),
    }


def as_of(clock, *, raw_dir: Path | str | None = None,
          manifest_path: Path | str | None = None,
          season: str = SEASON,
          season_root: Path | str | None = None) -> AsOfSnapshot:
    """The archive's answer to "what did we know at `clock`?".

    `clock` is an INPUT and the only one: this reads no wall clock, so the same
    clock over the same archive returns the same view tomorrow. Four typed
    refusals and not one silent narrowing:

    * :class:`NoSnapshotAsOf` — nothing was observed by then. The capture began
      on 2026-08-27 and the honest answer for anything older is that we had not
      started looking. A12 (b) turns this into the arm's ABSTENTION.
    * :class:`SnapshotMissing` — the manifest attests bytes the archive lost.
    * :class:`SnapshotDigestMismatch` — the bytes are not the attested bytes.
    * :class:`AvailabilitySchemaDrift` / :class:`TeamUnmapped` — the payload is
      not one this rule can read, or a club is not one the season fields. Both
      are the capture's own refusals, raised by the capture's own code.
    """
    raw_dir = Path(raw_dir) if raw_dir is not None else RAW_DIR
    manifest_path = (Path(manifest_path) if manifest_path is not None
                     else default_manifest_path(season, season_root))
    lines = read_manifest(manifest_path)
    line = select_manifest_line(lines, clock)
    if line is None:
        earliest = min((l["observed_at"] for l in lines), default=None)
        raise NoSnapshotAsOf(
            f"no availability snapshot was observed at or before "
            f"{iso_z(clock)}: the archive holds {len(lines)} line(s)"
            + (f", the earliest observed at {earliest}" if earliest else "")
            + ". The archive cannot answer a question that predates it, and "
            "borrowing a later snapshot would claim knowledge we did not have")

    path = raw_dir / line.get("raw", raw_name(line["stamp"]))
    if not path.exists():
        raise SnapshotMissing(
            f"the manifest attests {path.name} at {line['observed_at']} and "
            f"the archive does not hold it ({path}). The bytes are the record; "
            "a reader that carried on without them would be reading the "
            "attestation instead")
    blob = read_payload_bytes(path)
    digest = sha256_bytes(blob)
    if digest != line["sha256"]:
        raise SnapshotDigestMismatch(
            f"{path.name} hashes to {digest[:12]}… and the tracked manifest "
            f"attests {line['sha256'][:12]}…. The bytes changed after they "
            "were attested, so nothing read out of them is the record")

    manifest = season_mod.load_manifest(
        season, **({"root": season_root} if season_root is not None else {}))
    payload = parse_payload(blob, path)
    assert_schema(payload, n_clubs=len(manifest.clubs))
    team_keys = team_key_map(payload, manifest)

    squads: dict[str, list[dict]] = {key: [] for key in team_keys.values()}
    for element in payload["elements"]:
        row = _as_of_player(element, team_keys)
        squads[row["team_key"]].append(row)
    for rows in squads.values():
        rows.sort(key=lambda r: r["player_id"])

    return AsOfSnapshot(
        stamp=str(line["stamp"]), observed_at=str(line["observed_at"]),
        sha256=digest, raw_path=path, n_players=len(payload["elements"]),
        line=dict(line),
        squads={key: tuple(rows) for key, rows in sorted(squads.items())})


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------
def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--raw-dir", default=None,
                        help=f"where the gzipped snapshots live (default {RAW_DIR})")
    parser.add_argument("--ledger", default=None,
                        help=f"the derived ledger (default {LEDGER_PATH})")
    parser.add_argument("--manifest", default=None,
                        help="the TRACKED manifest (default "
                             f"{default_manifest_path()})")
    parser.add_argument("--season", default=SEASON)
    parser.add_argument("--season-root", default=None)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m epl.availability",
        description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pull", help="one capture of the availability feed")
    _add_common(p)
    p.add_argument("--url", default=BOOTSTRAP_URL)
    p.add_argument("--dry-run", action="store_true",
                   help="fetch, check and report; write nothing")
    p.add_argument("--accept-restatement", action="store_true",
                   help="record a snapshot whose source clock walked backwards, "
                        "marking the restatement on the manifest line")

    v = sub.add_parser("verify", help="re-derive the ledger and recheck hashes")
    _add_common(v)

    s = sub.add_parser("status", help="the operator's one screen")
    _add_common(s)

    args = parser.parse_args(list(argv) if argv is not None else None)
    where = {"raw_dir": args.raw_dir, "ledger_path": args.ledger,
             "manifest_path": args.manifest, "season": args.season,
             "season_root": args.season_root}

    try:
        if args.command == "pull":
            # the CLI is the boundary that reads a clock; the library is not.
            report = pull(now=pd.Timestamp.now("UTC"), url=args.url,
                          dry_run=args.dry_run,
                          accept_restatement=args.accept_restatement, **where)
            snap = report.snapshot
            verb = ("would append" if report.dry_run
                    else "appended" if report.written else "already recorded;")
            print(f"[availability] {snap.stamp}  {snap.n_players} players, "
                  f"{snap.n_bytes} bytes, sha256 {snap.sha256[:12]}…")
            print(f"[availability] {verb} {len(report.rows)} ledger rows; "
                  f"{report.n_flagged} players flagged; source high-water "
                  f"news_added {snap.max_news_added}")
            if report.snapshot.clock_regression:
                print("[availability] RESTATEMENT recorded on the manifest line")
            return 0
        if args.command == "verify":
            report = verify(**where)
            print(f"[availability] {report.n_snapshots} snapshots, "
                  f"{report.n_rows} ledger rows, "
                  f"{report.n_rows_rederived} re-derived")
            if report.ok:
                print("[availability] VERIFIED: the ledger is exactly what the "
                      "raw bytes say it is")
                return 0
            for problem in report.problems:
                print(f"STOP: {problem}", file=sys.stderr)
            return 2
        if args.command == "status":
            print(render_status(status(now=pd.Timestamp.now("UTC"), **where)),
                  end="")
            return 0
    except (AvailabilityError, season_mod.SeasonError) as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 1                                                # pragma: no cover


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
