"""The season snapshot: 380 immutable fixtures, three known-at ledgers, one state.

This module answers exactly one question, and answers it point-in-time:

    at cutoff C, what has actually happened in this season?

Two rules are load-bearing, and both are here because the obvious implementation
of each is wrong.

**A fixture is identified by `(season_code, home_key, away_key)`, never by date.**
`epl.parse._match_id` hashes the kickoff date, which is right for an archive row
(a historical result happened on a day) and wrong for a fixture that can be
moved: rescheduling Palace-City to a Friday would mint a second fixture and the
season would hold 381. Kickoff date and time are *metadata*, carried in a
known-at amendments overlay. Because the league table is order-invariant and
"played" comes from results, kickoffs never enter the numbers — they drive
display and the unresolved/lag flags only.

**"Played" is derived from the results ledger, never from the clock.** A fixture
whose scheduled date has passed is not a result. If the calendar decided, a
postponed match would silently drop out of the simulation and the season would
be scored as if 379 matches were the whole of it. So a fixture with no visible
result is `unresolved` when its known kickoff has passed and `scheduled`
otherwise — and either way it is still simulated.

All three ledgers are bitemporal and append-only. A result row carries
`observed_at` (when *we* learned it) as well as `date_played` (when it
happened), and the state at cutoff C sees a row only if `date_played <
C.normalize()` **and** `observed_at <= C`. Where several rows describe one
fixture the latest observation wins, whether it carries a scoreline or a status:
a result filed and later abandoned is unplayed, and a postponement later
answered by the rearranged match is played. A kickoff amendment and a
points-adjustment row each carry `known_at` and apply only if `known_at <= C`;
an adjustment may also supersede an earlier row, so the applicable set at C is
the rows known by C that no row known by C supersedes.

**Two clocks, and each ledger is read by exactly one of them.**

* `observed_by` is the KNOWLEDGE clock, and it bounds ALL THREE ledgers: a
  result is visible iff `observed_at <= observed_by`, a kickoff amendment and a
  points adjustment iff `known_at <= observed_by`. It defaults to the cutoff.
* `cutoff` is the PLAY clock, and it bounds one thing: a visible result counts
  as played iff `date_played < cutoff.normalize()`.

`Season.at(C, observed_by=O)` therefore reruns an old forecast as the forecast it
was — one knowledge state, read consistently — rather than as a stale results
ledger against a fresh schedule. Splitting the two (results at O, schedule and
deductions at `min(C, O)`) is the shape this had first, and it is wrong in the
`O > C` direction: it produced a snapshot that knew Saturday's results and
Friday's schedule, which is no moment that ever existed. Rewriting history is
still impossible without an explicit, reviewable ledger row — which is the point.

Every stamp on every row is read through :func:`_require_stamp`, which refuses
`NaT`. `pd.Timestamp` turns `None`, `nan`, `""` and `NaT` into `NaT` rather than
raising, and `NaT` compares False against every bound — so a row carrying one
would be visible at EVERY cutoff (a results row) or at NONE (a `known_at` row).
Both are silent, and the first is exactly the leak the stamps exist to prevent.

Layout under `epl/season/` (tracked in git, so the commit history IS the
known-at record of what the operator entered and when):

    points_adjustments.jsonl                 shared across seasons
    2026_27/manifest.json                    club set, boundaries, rule id
    2026_27/fixtures_openfootball_2026-27.txt  vendored CC0 bytes, sha256-pinned
    2026_27/kickoff_amendments.jsonl         known-at schedule moves
    2026_27/results_ledger.jsonl             known-at results

Fixture source: openfootball/england, CC0-1.0.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from wcmodel.data.features import valid_played_results

from epl import teams

#: `epl/season/` — the data directory beside this module. The two coexist by
#: design: Python's finder prefers `season.py` over a directory with no
#: `__init__.py`, and `epl/tests/test_season.py` asserts it still does.
SEASON_ROOT = Path(__file__).resolve().parent / "season"

#: Shared across seasons, because a deduction is a league event, not a fixture.
ADJUSTMENTS_FILENAME = "points_adjustments.jsonl"
AMENDMENTS_FILENAME = "kickoff_amendments.jsonl"
RESULTS_FILENAME = "results_ledger.jsonl"
MANIFEST_FILENAME = "manifest.json"

#: A fixture with a known kickoff this many days before the cutoff and still no
#: result sets `results_lag` — the operator is behind, or the match moved and
#: nobody filed the amendment (plan v2 D4).
RESULTS_LAG_DAYS = 2

#: Orientation guard (plan v2 D3). A result that lands this far from its own
#: fixture's kickoff AND this close to the reverse fixture's kickoff is very
#: probably home/away-flipped at the source. The World Cup sim auto-flips; a
#: league may not, because the reverse pair is a real, separate fixture.
ORIENTATION_FAR_DAYS = 45
ORIENTATION_NEAR_DAYS = 3

#: Statuses a fixture can hold at a cutoff. `awarded` and `void` are out of v1
#: scope and fail closed rather than being guessed at (plan v2 D3, Q6).
STATUS_PLAYED = "played"
STATUS_SCHEDULED = "scheduled"
STATUS_UNRESOLVED = "unresolved"
STATUS_POSTPONED = "postponed"
STATUS_ABANDONED = "abandoned"
_LEDGER_STATUSES = {STATUS_POSTPONED, STATUS_ABANDONED}


class SeasonError(RuntimeError):
    """Anything wrong with a season snapshot that must stop the run."""


class ParseError(SeasonError):
    """A line in an openfootball file that we will not guess at."""


class ResultConflict(SeasonError):
    """Two sources disagree about a scoreline. STOP; do not pick a winner."""


class OrientationSuspect(SeasonError):
    """A result may be home/away-flipped relative to the fixture it joined to."""


class UnverifiedAdjustment(SeasonError):
    """A points adjustment that has not been checked against the league's record."""


class UnsupportedResultStatus(SeasonError):
    """An `awarded`/`void` result, which v1 does not model."""


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def season_code(season: str) -> str:
    """`"2026/27"` -> `"2627"`, matching the archive's `season_code` column."""
    text = str(season).strip()
    m = re.fullmatch(r"(\d{4})/(\d{2})", text)
    if not m:
        raise SeasonError(f"season must look like '2026/27', got {season!r}")
    return f"{m.group(1)[2:]}{m.group(2)}"


def season_dir_name(season: str) -> str:
    """`"2026/27"` -> `"2026_27"`, the on-disk directory."""
    text = str(season).strip()
    if not re.fullmatch(r"\d{4}/\d{2}", text):
        raise SeasonError(f"season must look like '2026/27', got {season!r}")
    return text.replace("/", "_")


def fixture_id(season_code_: str, home_key: str, away_key: str) -> str:
    """The stable id: `"2627:arsenal:coventry"`.

    Deliberately date-free (plan v2 D3). Unique in a double round-robin, so it
    survives every reschedule, and two runs at different cutoffs address the
    same fixture by the same name.
    """
    if not (season_code_ and home_key and away_key):
        raise SeasonError("fixture_id needs season_code, home_key and away_key")
    if home_key == away_key:
        raise SeasonError(f"a club cannot play itself: {home_key!r}")
    return f"{season_code_}:{home_key}:{away_key}"


def openfootball_source_id(text: str) -> str:
    """`"openfootball@<sha256 of the file>"` — the D4 provenance string."""
    return "openfootball@" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# the openfootball adapter
# --------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_WEEKDAYS = {d: i for i, d in enumerate(
    ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}

_ROUND_RE = re.compile(
    r"^(?:Matchday|Round|Regular\s+Season)\s*[-–—]?\s*(\d{1,2})$", re.IGNORECASE)
_DAY_RE = re.compile(
    r"^(?P<dow>[A-Za-z]{3,9})\.?,?\s+(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2})"
    r"(?:\s+(?P<year>\d{4}))?$")
_TIME_RE = re.compile(r"^(?P<time>\d{1,2}:\d{2})\s+(?P<rest>.+)$")
_RESULT_RE = re.compile(
    r"^(?P<home>\S.*?)\s\s*(?P<hg>\d{1,2})\s*-\s*(?P<ag>\d{1,2})"
    r"(?:\s*\(\s*\d{1,2}\s*-\s*\d{1,2}\s*\))?\s\s*(?P<away>\S.*?)$")
# openfootball writes the score in TWO places and the layout tracks the fixture
# separator. A `v`-separated line gets the score APPENDED:
#     "Liverpool FC            v AFC Bournemouth          4-2 (1-0)"
# while the archival regeneration puts it in the MIDDLE:
#     "Liverpool FC            4-2 (1-0)  AFC Bournemouth"
# Only the middle form was ever handled, and every result fixture in the suite was
# hand-written in it, so 543 green tests never saw real upstream result bytes. On the
# END layout `_RESULT_RE` swallows " v Away" into the home name and hands back the
# half-time bracket as the away team, which dies at team resolution.
# The discriminator is the column gap: openfootball aligns the score at least two
# spaces clear of the away name, while the `v` separator can be a single space
# ("Brighton & Hove Albion FC v Fulham FC"). END is tried first because `_RESULT_RE`
# would otherwise match these lines and mis-split them.
# The half-time bracket is absent on a goalless draw, hence the optional group.
_RESULT_END_RE = re.compile(
    r"^(?P<home>\S.*?)\s+v(?:s|\.)?\s+(?P<away>\S.*?)\s\s+(?P<hg>\d{1,2})\s*-\s*(?P<ag>\d{1,2})"
    r"(?:\s*\(\s*\d{1,2}\s*-\s*\d{1,2}\s*\))?\s*$")
_FIXTURE_RE = re.compile(r"^(?P<home>\S.*?)\s+v(?:s|\.)?\s+(?P<away>\S.*?)$")
# Any score-shaped token, used only to decide whether a `v`-separated line is
# claiming to be a result at all. Deliberately looser than the result regexes.
_SCORE_TOKEN_RE = re.compile(r"\d{1,2}\s*-\s*\d{1,2}")


@dataclass(frozen=True)
class FixtureRow:
    """One line of an openfootball file, resolved no further than the raw names."""

    matchday: int
    date: _dt.date | None
    time: str | None
    home_raw: str
    away_raw: str
    hg: int | None = None
    ag: int | None = None


def _parse_day_header(match: re.Match, prev: _dt.date | None) -> _dt.date:
    mon = _MONTHS.get(match.group("mon")[:3].lower())
    dow = _WEEKDAYS.get(match.group("dow")[:3].lower())
    if mon is None or dow is None:
        raise ParseError(f"unrecognised day header {match.group(0)!r}")
    day = int(match.group("day"))
    year_text = match.group("year")
    if year_text is not None:
        year = int(year_text)
    elif prev is None:
        raise ParseError(
            f"day header {match.group(0)!r} carries no year and none was printed "
            f"before it — refusing to guess the season's calendar year")
    else:
        # openfootball prints the year only when it changes; a month that goes
        # backwards is the December -> January rollover.
        year = prev.year + (1 if mon < prev.month else 0)
    date = _dt.date(year, mon, day)
    if date.weekday() != dow:
        # A carried-down year that is wrong lands on the wrong weekday. This is
        # the positive control on the whole date-carry: the file states both.
        raise ParseError(
            f"day header {match.group(0)!r} resolves to {date.isoformat()}, which is a "
            f"{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][date.weekday()]}")
    return date


def parse_openfootball(text: str) -> list[FixtureRow]:
    """Parse an openfootball league file into rows, fixtures or results.

    Handles both header styles the source uses (`▪ Matchday 5` in the 2026/27
    file, `▪ Regular Season - 5` in 2025/26), day headers at any indentation with
    the year printed only when it changes, `H v A` fixtures and
    `H 2-1 (1-0) A` results, and times that are printed once per kickoff slot and
    carried down the block. Goalscorer continuation lines — parenthesised, often
    wrapped over two lines — are ignored.

    Anything else raises `ParseError`. A silently skipped line is how a season
    quietly becomes 379 fixtures.
    """
    rows: list[FixtureRow] = []
    matchday: int | None = None
    date: _dt.date | None = None      # the current day block; reset each round
    carry: _dt.date | None = None     # last date seen anywhere, for the year carry
    time: str | None = None
    depth = 0

    for lineno, raw in enumerate(str(text).splitlines(), start=1):
        if depth > 0:                                   # inside a scorers block
            depth += raw.count("(") - raw.count(")")
            continue
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue
        if line.startswith("("):                        # scorers block opens
            depth = line.count("(") - line.count(")")
            continue

        header = line.lstrip("▪»•-–— \t").strip()
        m = _ROUND_RE.match(header)
        if m:
            matchday = int(m.group(1))
            date, time = None, None
            continue

        m = _DAY_RE.match(line)
        if m:
            # The year carries across round headers: openfootball prints it only
            # when it changes, which for a league season is once, in January.
            date = carry = _parse_day_header(m, carry)
            time = None
            continue

        body = line
        m = _TIME_RE.match(line)
        if m:
            time = m.group("time")
            body = m.group("rest").strip()

        if matchday is None:
            raise ParseError(f"line {lineno}: match line before any round header: {line!r}")
        if date is None:
            raise ParseError(
                f"line {lineno}: match line before any day header in round {matchday}: {line!r}")

        # A `v`-separated line that carries a score MUST parse as the END layout.
        # If it does not, we cannot tell where the away name stops and the score
        # starts, and both fallbacks below would invent an answer: `_RESULT_RE`
        # returns home="Arsenal FC v Chelsea FC" / away="(1-0)", and `_FIXTURE_RE`
        # returns away="Chelsea FC 2-0 (1-0)". Refuse instead. This catches the
        # one-space boundary (openfootball's spec requires two) and the Football.TXT
        # forms this parser does not model, e.g. "1-1 aet (1-1, 0-0) 3-4 pen".
        if (_SCORE_TOKEN_RE.search(body) and _FIXTURE_RE.match(body)
                and not _RESULT_END_RE.match(body)):
            raise ParseError(
                f"line {lineno}: a 'v'-separated result this parser cannot split "
                f"unambiguously: {line!r}")

        m = _RESULT_END_RE.match(body) or _RESULT_RE.match(body)
        if m:
            rows.append(FixtureRow(
                matchday=matchday, date=date, time=time,
                home_raw=m.group("home").strip(), away_raw=m.group("away").strip(),
                hg=int(m.group("hg")), ag=int(m.group("ag"))))
            continue

        m = _FIXTURE_RE.match(body)
        if m:
            rows.append(FixtureRow(
                matchday=matchday, date=date, time=time,
                home_raw=m.group("home").strip(), away_raw=m.group("away").strip()))
            continue

        raise ParseError(f"line {lineno}: not a round, day, fixture or result: {line!r}")

    if depth != 0:
        raise ParseError("unterminated goalscorer block at end of file")
    return rows


def detect_kickoff_amendments(
    base_rows: list[FixtureRow],
    fresh_rows: list[FixtureRow],
    known_at,
    source_id: str,
    *,
    season_code: str,
) -> list[dict]:
    """Diff two parses of the same season into known-at amendment rows.

    `season_code` is required because a fixture id is season-scoped and a parsed
    row does not carry the season. Returns `[]` when nothing moved, so a routine
    re-fetch does not append noise to the overlay.
    """
    def index(rows):
        out = {}
        for r in rows:
            fid = fixture_id(season_code, teams.team_key(r.home_raw),
                             teams.team_key(r.away_raw))
            out[fid] = r
        return out

    base, fresh = index(base_rows), index(fresh_rows)
    known_at_text = _require_stamp(known_at, "known_at").isoformat()
    amendments: list[dict] = []
    for fid, new in fresh.items():
        old = base.get(fid)
        if old is None:
            continue                                    # not an amendment; a new fixture
        if (old.date, old.time) == (new.date, new.time):
            continue
        amendments.append({
            "fixture_id": fid,
            "date": new.date.isoformat() if new.date else None,
            "time": new.time,
            "source": source_id,
            "known_at": known_at_text,
            "note": (f"auto-detected: {old.date} {old.time or ''}".strip()
                     + f" -> {new.date} {new.time or ''}".rstrip()),
        })
    amendments.sort(key=lambda row: row["fixture_id"])
    return amendments


# --------------------------------------------------------------------------
# the manifest
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Manifest:
    season: str
    season_code: str
    clubs: tuple[str, ...]
    promoted: tuple[str, ...]
    relegated: tuple[str, ...]
    prev_season: str
    prev_season_clubs: tuple[str, ...]
    fixtures_filename: str
    fixtures_sha256: str
    tiebreak_rule_id: str
    material_boundaries: tuple[tuple[int, int], ...]
    orientation_spotcheck: dict
    raw: dict = field(repr=False, default_factory=dict)


def load_manifest(season: str, root: Path | str = SEASON_ROOT) -> Manifest:
    """Read and validate one season's manifest.

    The promoted/relegated sets are *checked* against the club-set difference
    rather than trusted: a manifest that disagrees with its own club lists is a
    transition bug waiting to happen in `epl.liveanchor`.
    """
    path = Path(root) / season_dir_name(season) / MANIFEST_FILENAME
    if not path.exists():
        raise SeasonError(f"no manifest for {season} at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))

    clubs = tuple(raw["clubs"])
    prev = tuple(raw["prev_season_clubs"])
    promoted = tuple(raw["promoted"])
    relegated = tuple(raw["relegated"])
    if len(set(clubs)) != 20:
        raise SeasonError(f"{season}: manifest holds {len(set(clubs))} clubs, expected 20")
    if len(set(prev)) != 20:
        raise SeasonError(f"{season}: prev_season_clubs holds {len(set(prev))}, expected 20")
    unknown = sorted({k for k in (*clubs, *prev) if k not in _known_keys()})
    if unknown:
        raise SeasonError(
            f"{season}: manifest club keys {unknown} are not in the epl.teams registry — "
            f"register them there rather than inventing a key here")
    if set(promoted) != set(clubs) - set(prev):
        raise SeasonError(f"{season}: promoted {promoted} != clubs - prev_season_clubs")
    if set(relegated) != set(prev) - set(clubs):
        raise SeasonError(f"{season}: relegated {relegated} != prev_season_clubs - clubs")
    if raw["season_code"] != season_code(season):
        raise SeasonError(f"{season}: manifest season_code {raw['season_code']!r} is wrong")

    return Manifest(
        season=raw["season"],
        season_code=raw["season_code"],
        clubs=clubs,
        promoted=promoted,
        relegated=relegated,
        prev_season=raw["prev_season"],
        prev_season_clubs=prev,
        fixtures_filename=raw["fixtures_filename"],
        fixtures_sha256=raw["fixtures_sha256"],
        tiebreak_rule_id=raw["tiebreak_rule_id"],
        material_boundaries=tuple(tuple(b) for b in raw["material_boundaries"]),
        orientation_spotcheck=raw["orientation_spotcheck"],
        raw=raw,
    )


def _known_keys() -> set[str]:
    """Every stable key the club registry will hand out."""
    return {key for _, key in teams.known_spellings().values()}


# --------------------------------------------------------------------------
# the season and its state
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    season: str
    season_code: str
    matchday: int
    home_key: str
    away_key: str
    home_team: str
    away_team: str
    base_date: _dt.date
    base_time: str | None


@dataclass(frozen=True)
class TableRow:
    played: int = 0
    w: int = 0
    d: int = 0
    l: int = 0
    gf: int = 0
    ga: int = 0
    adjustment: int = 0

    @property
    def gd(self) -> int:
        return self.gf - self.ga

    @property
    def pts(self) -> int:
        return 3 * self.w + self.d + self.adjustment


@dataclass(frozen=True)
class SeasonState:
    """Everything the fit and the simulator may see at one cutoff."""

    season: str
    season_code: str
    cutoff: pd.Timestamp
    observed_by: pd.Timestamp
    clubs: tuple[str, ...]
    fixtures: dict[str, Fixture]
    played: dict[str, tuple[int, int]]
    unplayed: tuple[str, ...]
    unresolved: tuple[str, ...]
    statuses: dict[str, str]
    kickoffs_known: dict[str, tuple[_dt.date, str | None]]
    adjustments_known: dict[str, int]
    table_so_far: dict[str, TableRow]
    results_lag: bool


def _timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tz is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _require_stamp(value, what: str) -> pd.Timestamp:
    """A point-in-time stamp, or a refusal. Never `NaT`.

    `pd.Timestamp` maps `None`, `nan`, `""` and `NaT` to `NaT` instead of
    raising, and `NaT` compares False against every bound: `observed_at >
    observed_by`, `date_played >= cutoff_day` and `known_at <= cutoff` are ALL
    False for it. So an unstamped results row is visible at every cutoff — a
    status row with a null `observed_at` would postpone a fixture in a snapshot
    taken years before anyone filed it — and an unstamped `known_at` row is
    visible at none, silently dropping a deduction from every table. Both fail
    closed here rather than passing through the one branch a presence check does
    not cover.
    """
    try:
        ts = _timestamp(value)
    except (TypeError, ValueError) as exc:
        raise SeasonError(f"{what}={value!r} is not a timestamp") from exc
    if pd.isna(ts):
        raise SeasonError(
            f"{what}={value!r} resolves to NaT, which compares False against "
            "every point-in-time bound — the row it stamps would be visible at "
            "every cutoff or at none. Fix the ledger row rather than letting it "
            "through")
    return ts


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SeasonError(f"{path}:{lineno} is not JSON: {exc}") from exc
    return rows


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def load_adjustments(root: Path | str = SEASON_ROOT) -> list[dict]:
    """The shared points-adjustments ledger, in file order."""
    return _read_jsonl(Path(root) / ADJUSTMENTS_FILENAME)


def adjustments_at(rows: list[dict], season: str, cutoff,
                   *, require_verified: bool = False) -> dict[str, int]:
    """Deductions in force for `season` at `cutoff` (plan v2 D16).

    A row applies if `known_at <= cutoff` and no row with `known_at <= cutoff`
    supersedes it. `delta` is the row's FULL deduction, so an appeal that
    replaces -10 with -6 leaves -6, not -16; a second, separate breach is its
    own unsuperseded row and adds.

    `require_verified` is the scoring gate: the retrospective refuses to score a
    season against a deduction nobody has checked against the league's record.
    """
    at = _require_stamp(cutoff, "cutoff")
    mine = [r for r in rows if r["season"] == season]
    # `.get`, and fail closed: a `known_at` that resolves to `NaT` is never
    # `<= at`, so the deduction would vanish from every table ever built — the
    # quietest of the three point-in-time failures and the one nobody would
    # notice. An absent key raises `SeasonError` for the same reason it does in
    # `_kickoffs_known`: a `KeyError` escapes the callers that catch this layer.
    known = [r for r in mine
             if _require_stamp(r.get("known_at"),
                               f"adjustment {r.get('id', '<row>')!r} known_at") <= at]
    superseded = {r["supersedes"] for r in known if r.get("supersedes")}
    live = [r for r in known if r["id"] not in superseded]

    if require_verified:
        unverified = sorted(r["id"] for r in live if not r.get("verified", False))
        if unverified:
            raise UnverifiedAdjustment(
                f"{season}: points-adjustment rows {unverified} are not verified. "
                f"Check them against the league's published record and set "
                f"\"verified\": true in {ADJUSTMENTS_FILENAME} before scoring.")

    out: dict[str, int] = {}
    for row in live:
        out[row["club_key"]] = out.get(row["club_key"], 0) + int(row["delta"])
    return {k: v for k, v in sorted(out.items()) if v != 0}


@dataclass(frozen=True)
class Season:
    """One season's immutable fixtures plus its three known-at ledgers."""

    manifest: Manifest
    fixtures: tuple[Fixture, ...]
    amendments: tuple[dict, ...]
    results: tuple[dict, ...]
    adjustments: tuple[dict, ...]
    root: Path
    fixtures_text: str = field(repr=False, default="")

    # --- construction ----------------------------------------------------

    @classmethod
    def load(cls, season: str, root: Path | str = SEASON_ROOT) -> Season:
        root = Path(root)
        manifest = load_manifest(season, root=root)
        sdir = root / season_dir_name(season)

        raw = (sdir / manifest.fixtures_filename).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != manifest.fixtures_sha256:
            raise SeasonError(
                f"{season}: {manifest.fixtures_filename} hashes to {digest}, "
                f"manifest pins {manifest.fixtures_sha256}. The vendored bytes changed; "
                f"re-verify the source and bump the manifest deliberately.")
        text = raw.decode("utf-8")
        fixtures = _build_fixtures(parse_openfootball(text), manifest)

        return cls(
            manifest=manifest,
            fixtures=fixtures,
            amendments=tuple(_read_jsonl(sdir / AMENDMENTS_FILENAME)),
            results=tuple(_read_jsonl(sdir / RESULTS_FILENAME)),
            adjustments=tuple(load_adjustments(root)),
            root=root,
            fixtures_text=text,
        )

    # --- lookups ---------------------------------------------------------

    @property
    def season(self) -> str:
        return self.manifest.season

    @property
    def season_code(self) -> str:
        return self.manifest.season_code

    def fixture(self, fid: str) -> Fixture:
        for f in self.fixtures:
            if f.fixture_id == fid:
                return f
        raise SeasonError(f"{self.season}: no fixture {fid!r}")

    def by_matchday(self, matchday: int) -> list[Fixture]:
        return [f for f in self.fixtures if f.matchday == matchday]

    # --- the state -------------------------------------------------------

    def at(self, cutoff, observed_by=None, *,
           require_verified_adjustments: bool = False) -> SeasonState:
        """The point-in-time snapshot at `cutoff` (see the module docstring)."""
        return _state(
            season=self.season,
            season_code_=self.season_code,
            clubs=self.manifest.clubs,
            fixtures=self.fixtures,
            amendments=self.amendments,
            results=self.results,
            adjustments=self.adjustments,
            cutoff=cutoff,
            observed_by=observed_by,
            require_verified_adjustments=require_verified_adjustments,
        )

    # --- ingest ----------------------------------------------------------

    def ingest_openfootball_results(self, text: str, observed_at, source_id: str,
                                    *, write: bool = False,
                                    allow_revisions: bool = False) -> list[dict]:
        return ingest_openfootball_results(
            self, text, observed_at=observed_at, source_id=source_id, write=write,
            allow_revisions=allow_revisions)


def _build_fixtures(rows: list[FixtureRow], manifest: Manifest) -> tuple[Fixture, ...]:
    """Resolve parsed rows to the manifest's 20 clubs and validate the round-robin."""
    fixtures: list[Fixture] = []
    for row in rows:
        if row.date is None:
            raise SeasonError(
                f"{manifest.season}: fixture {row.home_raw} v {row.away_raw} has no date; "
                f"the file is missing a day header")
        home_name, home_key = teams.resolve(row.home_raw)
        away_name, away_key = teams.resolve(row.away_raw)
        for key, spelling in ((home_key, row.home_raw), (away_key, row.away_raw)):
            if key not in manifest.clubs:
                raise SeasonError(
                    f"{manifest.season}: {spelling!r} resolves to {key!r}, which is not "
                    f"in the manifest's 20 clubs")
        fixtures.append(Fixture(
            fixture_id=fixture_id(manifest.season_code, home_key, away_key),
            season=manifest.season,
            season_code=manifest.season_code,
            matchday=row.matchday,
            home_key=home_key,
            away_key=away_key,
            home_team=home_name,
            away_team=away_name,
            base_date=row.date,
            base_time=row.time,
        ))

    _validate_round_robin(fixtures, manifest.season, manifest.clubs)
    # Sorted by id: `fixture_ordinal` (the RNG stream key, plan v2 D14) must not
    # depend on the order the source happened to print the fixtures in.
    return tuple(sorted(fixtures, key=lambda f: f.fixture_id))


def _validate_round_robin(fixtures, season: str, clubs: tuple[str, ...]) -> None:
    n = len(clubs)
    expected = n * (n - 1)
    if len(fixtures) != expected:
        raise SeasonError(f"{season}: {len(fixtures)} fixtures, expected {expected}")
    ids = {f.fixture_id for f in fixtures}
    if len(ids) != expected:
        raise SeasonError(f"{season}: duplicate fixture ids")
    pairs = {(f.home_key, f.away_key) for f in fixtures}
    if pairs != {(h, a) for h in clubs for a in clubs if h != a}:
        raise SeasonError(f"{season}: fixtures are not a complete double round-robin")


# --------------------------------------------------------------------------
# state assembly (shared by the live season and the archive)
# --------------------------------------------------------------------------

def _kickoffs_known(fixtures, amendments, cutoff: pd.Timestamp
                    ) -> dict[str, tuple[_dt.date, str | None]]:
    """Base kickoffs with every amendment known by `cutoff` applied, in order.

    `known_at` has no deferred reading: it is not an event that happened on a
    day, it is the moment the schedule move became knowable, so it is what
    "visible" MEANS for this ledger and there is no earlier filter to hide
    behind. A missing or `NaT` stamp therefore stops the load — `NaT <= cutoff`
    is False, so the amendment would apply at NO cutoff and the fixture would
    keep a date the league had moved, silently. `.get`, not `[...]`: an absent
    key must raise the season layer's own error, because the callers that mean
    "this snapshot is unusable" catch :class:`SeasonError` and a bare `KeyError`
    would go straight past them.
    """
    out = {f.fixture_id: (f.base_date, f.base_time) for f in fixtures}
    def known(row):
        return _require_stamp(
            row.get("known_at"),
            f"kickoff amendment {row.get('fixture_id', '<row>')!r} known_at")

    rows = [r for r in amendments if known(r) <= cutoff]
    for row in sorted(rows, key=known):
        fid = row["fixture_id"]
        if fid not in out:
            raise SeasonError(f"kickoff amendment for unknown fixture {fid!r}")
        date = (_require_stamp(row["date"], f"kickoff amendment {fid!r} date").date()
                if row.get("date") else out[fid][0])
        out[fid] = (date, row.get("time", out[fid][1]))
    return out


def goal_count(value, label: str) -> int:
    """`value` as a goal count, or :class:`SeasonError`. NEVER a coercion.

    `int(1.9)` is `1`, and a ledger that stores `1` for a source that said `1.9`
    holds a scoreline nobody ever reported — read-time validation then sees a
    perfectly good integer and passes it. So the check happens where the value
    arrives: an exact integer (`2` or `2.0` or `"2"`) is a goal count, and
    anything else — `1.9`, `nan`, `inf`, `True`, a negative, a word — is
    refused before a byte is written.

    `valid_played_results` stays THE definition (finite, non-negative,
    integral); this is that definition applied one value at a time, at write
    time, where a bad value can still be rejected rather than dropped.
    """
    if isinstance(value, bool):
        raise SeasonError(f"{label}: {value!r} is not a goal count")
    if isinstance(value, (int, np.integer)):
        n = int(value)
    elif isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)) or not float(value).is_integer():
            raise SeasonError(
                f"{label}: {value!r} is not an integral goal count — it is not "
                "rounded, it is refused")
        n = int(value)
    elif isinstance(value, str):
        try:
            n = int(value.strip())
        except (TypeError, ValueError) as exc:
            raise SeasonError(
                f"{label}: {value!r} is not an integral goal count") from exc
    else:
        raise SeasonError(f"{label}: {value!r} is not a goal count")
    if n < 0:
        raise SeasonError(f"{label}: {value!r} is negative")
    return n


def _validate_scores(rows: list[dict]) -> None:
    """Reject a ledger score that `wcmodel` would silently drop.

    `valid_played_results` is THE definition of a valid played match in this
    codebase (finite, non-negative, integral). The archive path lets it drop bad
    rows, as it does everywhere else; a hand-maintained ledger instead fails
    closed, because a dropped row there is a missing match nobody would notice.
    """
    if not rows:
        return
    frame = pd.DataFrame({
        "home_score": [r.get("hg") for r in rows],
        "away_score": [r.get("ag") for r in rows],
    })
    kept = valid_played_results(frame)
    bad = sorted({rows[i]["fixture_id"] for i in set(range(len(rows))) - set(kept.index)})
    if bad:
        raise SeasonError(
            f"results ledger rows {bad} carry a score that is not a valid goal count "
            f"(finite, non-negative, integral)")


@dataclass(frozen=True)
class LedgerView:
    """One bitemporal reading of a results ledger — see :func:`resolve_ledger`.

    ``winners`` is fixture id -> the row that WINS at ``(cutoff, observed_by)``:
    a score row or a status row, whichever was observed last. ``scored`` is
    every visible score row inside the cutoff day in ledger order, including the
    ones a later row supersedes — a caller that validates scorelines must see
    all of them, because a bad score is a bad ledger row whether or not another
    row happens to beat it.
    """

    winners: dict[str, dict]
    scored: tuple[dict, ...]

    @property
    def played_rows(self) -> dict[str, dict]:
        """The winning rows that are RESULTS, in ledger-id order."""
        return {fid: row for fid, row in self.winners.items()
                if row.get("status") is None}

    @property
    def statuses(self) -> dict[str, str]:
        """The winning rows that are STATES (`postponed` / `abandoned`)."""
        return {fid: row["status"] for fid, row in self.winners.items()
                if row.get("status") is not None}


def resolve_ledger(results, *, cutoff_day=None, observed_by=None,
                   identify) -> LedgerView:
    """THE bitemporal resolution of a results ledger. One implementation.

    Both readers of this project's results ledger go through here: the season
    table (:func:`_visible_results`, and so ``Season.at``) and the live Elo walk
    (:func:`epl.liveanchor.normalise_rows`). They used to resolve it separately,
    and the two answers could differ in the direction that matters most: the
    walk dropped every status row before resolving, so a score followed by a
    later ``abandoned`` stayed PLAYED for the anchor while the table it is
    scored against called it unplayed. A rating walked past a result the league
    took away is not a smaller version of that bug; it is the whole of it.

    Bitemporal: a row is visible iff it happened before the cutoff DAY and was
    observed by ``observed_by``. Where several rows describe one fixture, the
    latest observation wins — corrections are appended, never edited in place.

    "Latest observation wins" is resolved over scores and statuses TOGETHER, in
    one pass. Two passes with the score winning at the end is the obvious
    implementation and it is wrong in one direction: a match filed with a
    scoreline and later abandoned or voided would keep the result the league
    took away, because the status row it was corrected by never gets to win. The
    other direction — a postponement corrected by the result of the rearranged
    match — still resolves to the result, because that row is the later
    observation, not because scores are privileged.

    ``identify(row) -> fixture id`` is the caller's registry check, and it is
    called ONLY once the row is visible. The ledger is append-only, so a row
    filed tomorrow sits in the same file as yesterday's; validating it before
    the known-at filter would make today's typo retroactively break every
    earlier snapshot — the same class of bug as reading its content early. The
    unsupported-status check sits behind the same filter for the same reason,
    and is applied HERE rather than by each caller so the two cannot drift about
    which statuses the project models.

    The `observed_at` stamp itself is read BEFORE any of that and cannot be
    skipped, because it is what "visible" means: a row whose stamp resolves to
    `NaT` compares False against every bound and would otherwise be visible at
    every cutoff (see :func:`_require_stamp`). Nothing else about the row —
    `fixture_id` included — is read until the stamp has placed it in time.

    ``cutoff_day=None`` drops the play-clock bound; ``observed_by=None`` drops
    the knowledge bound.
    """
    obs = pd.Timestamp.max if observed_by is None else _require_stamp(
        observed_by, "observed_by")
    day = None if cutoff_day is None else _require_stamp(
        cutoff_day, "cutoff").normalize()

    scored: list[dict] = []
    latest: dict[str, tuple[pd.Timestamp, int, dict]] = {}

    for order, row in enumerate(results):
        # `.get`, and only for the message: the label must not be the thing
        # that raises, or a future row missing its id breaks earlier snapshots.
        label = row.get("fixture_id") or "<row>"
        observed = _require_stamp(row.get("observed_at"), f"{label} observed_at")
        if observed > obs:
            continue
        fid = identify(row)
        status = row.get("status")
        if status is not None and status not in _LEDGER_STATUSES:
            raise UnsupportedResultStatus(
                f"{fid}: results ledger status {status!r} is out of v1 scope "
                f"(only {sorted(_LEDGER_STATUSES)} are modelled)")
        if status is None:
            played_on = _require_stamp(row.get("date_played"), f"{fid} date_played")
            if day is not None and played_on >= day:
                continue
            scored.append(row)
        key = (observed, order)
        if fid not in latest or key > latest[fid][:2]:
            latest[fid] = (observed, order, row)

    return LedgerView(winners={fid: row for fid, (_, _, row) in latest.items()},
                      scored=tuple(scored))


def _fixture_registry_identity(fixtures_by_id):
    """`identify` for the season table: the id must name a fixture it holds."""
    def identify(row: dict) -> str:
        fid = row.get("fixture_id")
        if not fid:
            raise SeasonError(f"results ledger row {row!r} has no fixture_id")
        fid = str(fid)
        if fid not in fixtures_by_id:
            raise SeasonError(f"results ledger row for unknown fixture {fid!r}")
        return fid
    return identify


def _visible_results(results: list[dict], fixtures_by_id, cutoff_day: pd.Timestamp,
                     observed_by: pd.Timestamp, kickoffs) -> tuple[dict, dict]:
    """(played scorelines, ledger statuses) visible at the cutoff.

    A thin reading of :func:`resolve_ledger` — the resolution itself lives there
    because the live Elo walk must get the same answer from the same code.
    """
    view = resolve_ledger(results, cutoff_day=cutoff_day, observed_by=observed_by,
                          identify=_fixture_registry_identity(fixtures_by_id))
    _validate_scores(list(view.scored))

    played: dict[str, tuple[int, int]] = {}
    for fid, row in view.played_rows.items():
        played[fid] = (int(row["hg"]), int(row["ag"]))
        _check_orientation(fid, row, fixtures_by_id, kickoffs)
    return played, view.statuses


def _check_orientation(fid: str, row: dict, fixtures_by_id, kickoffs) -> None:
    """Fail closed on a result that looks home/away-flipped (plan v2 D3)."""
    fixture = fixtures_by_id[fid]
    played = _require_stamp(row.get("date_played"), f"{fid} date_played").date()
    own = kickoffs[fid][0]
    if abs((played - own).days) <= ORIENTATION_FAR_DAYS:
        return
    reverse_id = fixture_id(fixture.season_code, fixture.away_key, fixture.home_key)
    reverse = kickoffs.get(reverse_id)
    if reverse is None:
        return
    if abs((played - reverse[0]).days) <= ORIENTATION_NEAR_DAYS:
        raise OrientationSuspect(
            f"{fid}: result dated {played} is {abs((played - own).days)}d from its own "
            f"kickoff ({own}) and {abs((played - reverse[0]).days)}d from the reverse "
            f"fixture {reverse_id} ({reverse[0]}). The source may have home and away "
            f"the wrong way round — a league sim must not guess: fix the ledger row.")


def _table_so_far(clubs, played, fixtures_by_id, adjustments) -> dict[str, TableRow]:
    acc = {c: {"played": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0} for c in clubs}
    for fid, (hg, ag) in played.items():
        f = fixtures_by_id[fid]
        h, a = acc[f.home_key], acc[f.away_key]
        h["played"] += 1
        a["played"] += 1
        h["gf"] += hg
        h["ga"] += ag
        a["gf"] += ag
        a["ga"] += hg
        if hg > ag:
            h["w"] += 1
            a["l"] += 1
        elif hg < ag:
            a["w"] += 1
            h["l"] += 1
        else:
            h["d"] += 1
            a["d"] += 1
    return {c: TableRow(adjustment=int(adjustments.get(c, 0)), **acc[c]) for c in clubs}


def _state(*, season, season_code_, clubs, fixtures, amendments, results, adjustments,
           cutoff, observed_by, require_verified_adjustments) -> SeasonState:
    cut = _require_stamp(cutoff, "cutoff")
    obs = cut if observed_by is None else _require_stamp(observed_by, "observed_by")
    cutoff_day = cut.normalize()
    fixtures_by_id = {f.fixture_id: f for f in fixtures}

    # `observed_by` is the KNOWLEDGE clock and it bounds all three ledgers, not
    # the results alone. A schedule move and a points deduction each carry
    # `known_at` for the same reason a result carries `observed_at`, and a
    # snapshot that read a stale results ledger against a fresh schedule and a
    # fresh deductions table would not be any moment that ever existed — a rerun
    # of an old forecast would then not be that forecast.
    #
    # `obs`, NOT `min(cut, obs)`. The cutoff is the PLAY clock: it decides what
    # has HAPPENED (`date_played < cutoff_day`, below), which is the one thing an
    # amendment or an adjustment has no equivalent of — neither is an event that
    # occurs on a pitch on a day, and each is applicable from the moment it is
    # known. Clamping their known-at bound to the cutoff made `observed_by > C`
    # read the results ledger as of `O` and the other two as of `C`: a snapshot
    # that knew Saturday's results and Friday's schedule. `observed_by <= C`,
    # which is the case every rerun of an old forecast uses, is unaffected —
    # `min(C, O) == O` there.
    known_by = obs

    kickoffs = _kickoffs_known(fixtures, amendments, known_by)
    played, ledger_statuses = _visible_results(
        list(results), fixtures_by_id, cutoff_day, obs, kickoffs)

    statuses: dict[str, str] = {}
    unplayed: list[str] = []
    unresolved: list[str] = []
    lag = False
    for fid in fixtures_by_id:
        if fid in played:
            statuses[fid] = STATUS_PLAYED
            continue
        unplayed.append(fid)
        if fid in ledger_statuses:
            statuses[fid] = ledger_statuses[fid]
            continue
        if kickoffs[fid][0] < cutoff_day.date():
            statuses[fid] = STATUS_UNRESOLVED
            unresolved.append(fid)
            if (cutoff_day.date() - kickoffs[fid][0]).days > RESULTS_LAG_DAYS:
                lag = True
        else:
            statuses[fid] = STATUS_SCHEDULED

    known_adjustments = adjustments_at(
        list(adjustments), season, known_by,
        require_verified=require_verified_adjustments)
    unknown = set(known_adjustments) - set(clubs)
    if unknown:
        raise SeasonError(
            f"{season}: points adjustment for {sorted(unknown)}, not in the club set")

    return SeasonState(
        season=season,
        season_code=season_code_,
        cutoff=cut,
        observed_by=obs,
        clubs=tuple(sorted(clubs)),
        fixtures=fixtures_by_id,
        played=dict(sorted(played.items())),
        unplayed=tuple(sorted(unplayed)),
        unresolved=tuple(sorted(unresolved)),
        statuses=dict(sorted(statuses.items())),
        kickoffs_known=kickoffs,
        adjustments_known=known_adjustments,
        table_so_far=_table_so_far(sorted(clubs), played, fixtures_by_id, known_adjustments),
        results_lag=lag,
    )


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------

def source_family(source) -> str:
    """`"openfootball@<sha>"` -> `"openfootball"`; `"manual"` -> `"manual"`.

    A source id names a source AND the exact bytes it came from, so two fetches
    of the same file a week apart are two ids. The FAMILY is what decides whether
    an ingest is revising its own earlier statement or overruling somebody
    else's, which is the distinction plan v2 D4 turns on.
    """
    return str(source or "").split("@", 1)[0]


def current_ledger_view(season: Season) -> LedgerView:
    """The season's ledger resolved with NO bounds — what it says right now.

    The ingest has to know the ledger's CURRENT reading of a fixture, not
    "some row somewhere carries a score for it": a result that a later status row
    has already withdrawn is not a result, and treating it as one made a
    re-ingest of the replayed match a silent no-op.
    """
    return resolve_ledger(
        season.results,
        identify=_fixture_registry_identity({f.fixture_id: f for f in season.fixtures}))


def _refuse_a_stale_revision(fid: str, winner: dict, observed: pd.Timestamp) -> None:
    """A row that cannot win the resolution is not written at all.

    The ledger is append-only. A "correction" stamped at or before the row it
    corrects is a permanent no-op that reads like a correction in the file, and
    the only moment it can still be refused is before it is written.
    """
    was = _require_stamp(winner.get("observed_at"), f"{fid} observed_at")
    if observed <= was:
        raise SeasonError(
            f"{fid}: the row being superseded was observed at {was.isoformat()} and "
            f"this one at {observed.isoformat()}. A correction observed no later "
            "than the row it corrects never wins the resolution, so writing it "
            "would append a line that changes nothing.")


def ingest_openfootball_results(season: Season, text: str, observed_at, source_id: str,
                                *, write: bool = False,
                                allow_revisions: bool = False) -> list[dict]:
    """Turn a refreshed openfootball file into new ledger rows.

    Three kinds of row can come out of one file, and all three are APPENDED —
    the ledger is never edited, and the latest-observation resolution in
    :func:`resolve_ledger` is what makes the newest row win:

    * a **new result**, as before;
    * a **correction**, when the source now reports a different scoreline for a
      fixture it already reported. This needs ``allow_revisions``;
    * a **withdrawal**, when a fixture the source previously scored is carried
      unscored in the refreshed file. That appends a ``postponed`` STATUS row, so
      the fixture reads as unplayed from the new observation on. This needs
      ``allow_revisions`` too, because it takes a result away.

    Plan v2 D4 is kept exactly, and is the reason ``allow_revisions`` is not a
    licence to overwrite anything: a source may revise its OWN earlier statement,
    and may never overrule another's. openfootball meeting a hand-entered row it
    disagrees with still STOPs with :class:`ResultConflict`, and the remedy is a
    deliberate manual correction row — the human deciding, which is what D4 asks
    for. The same rule is what stops a source that has simply not caught up from
    "withdrawing" the round an operator entered by hand.

    Residual, stated rather than hidden: a fixture the ledger reads as
    ``abandoned`` is revived by a later score only under ``allow_revisions``,
    while one it reads as ``postponed`` is revived by any ingest. A postponement
    says "not played yet", so the result of the rearranged match is new
    information; an abandonment is a deliberate strike, so overturning it is a
    revision. Idempotent throughout: a file that agrees with the ledger appends
    nothing. Nothing is written unless ``write=True``.
    """
    view = current_ledger_view(season)
    winners = view.winners
    family = source_family(source_id)

    stamp = _require_stamp(observed_at, "observed_at")
    observed = stamp.isoformat()
    fixtures_by_id = {f.fixture_id: f for f in season.fixtures}
    new: list[dict] = []
    seen: set[str] = set()
    unscored: set[str] = set()

    for row in parse_openfootball(text):
        fid = fixture_id(season.season_code, teams.team_key(row.home_raw),
                         teams.team_key(row.away_raw))
        if row.hg is None or row.ag is None:
            # A fixture line, not a result. It cannot be an unknown-fixture
            # error — a refreshed file may legitimately list a match this
            # season's registry does not hold — but for a fixture we DO hold it
            # is how a withdrawal announces itself.
            if fid in fixtures_by_id:
                unscored.add(fid)
            continue
        if fid not in fixtures_by_id:
            raise SeasonError(f"{season.season}: ingested result for unknown fixture {fid!r}")
        if fid in seen:
            raise ResultConflict(f"{fid}: the ingested file holds it twice")
        seen.add(fid)
        if row.date is None:
            raise SeasonError(f"{fid}: ingested result has no date")
        hg, ag = goal_count(row.hg, f"{fid} hg"), goal_count(row.ag, f"{fid} ag")

        winner = winners.get(fid)
        note = ""
        if winner is not None:
            status = winner.get("status")
            if status is None:
                have = (goal_count(winner.get("hg"), f"{fid} hg"),
                        goal_count(winner.get("ag"), f"{fid} ag"))
                if have == (hg, ag):
                    continue                                # idempotent
                if source_family(winner.get("source")) != family:
                    raise ResultConflict(
                        f"{fid}: ledger holds {have[0]}-{have[1]} from "
                        f"{winner.get('source')!r}, {source_id} says {hg}-{ag}. A "
                        "source may revise its own earlier statement; it may not "
                        "overrule another's (plan v2 D4). STOP: file a manual "
                        "correction row deliberately.")
                if not allow_revisions:
                    raise ResultConflict(
                        f"{fid}: ledger holds {have[0]}-{have[1]}, {source_id} says "
                        f"{hg}-{ag}. STOP: check which is right, then re-run with "
                        "allow_revisions to append the correction.")
                _refuse_a_stale_revision(fid, winner, stamp)
                note = (f"correction: supersedes {have[0]}-{have[1]} observed "
                        f"{winner.get('observed_at')}")
            elif status == STATUS_ABANDONED and not allow_revisions:
                continue
            else:
                _refuse_a_stale_revision(fid, winner, stamp)
                note = (f"supersedes {status} observed "
                        f"{winner.get('observed_at')}")

        new.append({
            "fixture_id": fid,
            "date_played": row.date.isoformat(),
            "hg": hg,
            "ag": ag,
            "source": source_id,
            "observed_at": observed,
            "note": note,
        })

    if allow_revisions:
        for fid in sorted(unscored):
            winner = winners.get(fid)
            if winner is None or winner.get("status") is not None:
                continue
            if source_family(winner.get("source")) != family:
                # Not a withdrawal: a source with nothing to say about a row it
                # never filed. Treating it as one would empty the ledger of every
                # hand-entered round the moment the cron next ran.
                continue
            _refuse_a_stale_revision(fid, winner, stamp)
            new.append({
                "fixture_id": fid,
                "status": STATUS_POSTPONED,
                "source": source_id,
                "observed_at": observed,
                "note": (f"withdrawn upstream: supersedes "
                         f"{winner.get('hg')}-{winner.get('ag')} observed "
                         f"{winner.get('observed_at')}"),
            })

    new.sort(key=lambda r: r["fixture_id"])
    if write and new:
        _append_jsonl(
            Path(season.root) / season_dir_name(season.season) / RESULTS_FILENAME, new)
    return new


# --------------------------------------------------------------------------
# the archive (2019/20-2025/26), for the retrospective
# --------------------------------------------------------------------------

def archive_season_state(matches: pd.DataFrame, season: str, cutoff,
                         *, root: Path | str = SEASON_ROOT,
                         require_verified_adjustments: bool = True) -> SeasonState:
    """A `SeasonState` for a completed archive season, through the same code path.

    The archive IS the observed record (there is no separate `observed_at`), so
    only the `date < cutoff.normalize()` rule applies. Adjustments come from the
    same shared ledger, and by default an unverified row REFUSES to score —
    the retrospective must not credit or debit a season against a deduction
    nobody has checked (plan v2 D16).
    """
    frame = matches[matches["season"] == season]
    if frame.empty:
        raise SeasonError(f"no archive rows for {season}")
    code = str(frame["season_code"].iloc[0])
    clubs = tuple(sorted(set(frame["home_key"]) | set(frame["away_key"])))

    fixtures = tuple(sorted((
        Fixture(
            fixture_id=fixture_id(code, r.home_key, r.away_key),
            season=season,
            season_code=code,
            matchday=0,                      # the archive does not carry rounds
            home_key=r.home_key,
            away_key=r.away_key,
            home_team=r.home_key,
            away_team=r.away_key,
            base_date=pd.Timestamp(r.date).date(),
            base_time=None,
        ) for r in frame.itertuples()), key=lambda f: f.fixture_id))
    _validate_round_robin(fixtures, season, clubs)

    slim = pd.DataFrame({
        "home_score": frame["fthg"].to_numpy(),
        "away_score": frame["ftag"].to_numpy(),
        "date": pd.to_datetime(frame["date"]).to_numpy(),
        "home_team": frame["home_key"].to_numpy(),
        "away_team": frame["away_key"].to_numpy(),
    })
    valid = valid_played_results(slim)
    results = [{
        "fixture_id": fixture_id(code, r.home_team, r.away_team),
        "date_played": pd.Timestamp(r.date).isoformat(),
        "hg": int(r.home_score),
        "ag": int(r.away_score),
        "source": "archive",
        "observed_at": pd.Timestamp(r.date).isoformat(),
        "note": "",
    } for r in valid.itertuples()]

    return _state(
        season=season, season_code_=code, clubs=clubs, fixtures=fixtures,
        amendments=(), results=results, adjustments=load_adjustments(root),
        cutoff=cutoff, observed_by=None,
        require_verified_adjustments=require_verified_adjustments,
    )


__all__ = [
    "ADJUSTMENTS_FILENAME", "AMENDMENTS_FILENAME", "MANIFEST_FILENAME",
    "RESULTS_FILENAME", "SEASON_ROOT", "Fixture", "FixtureRow", "LedgerView",
    "Manifest", "OrientationSuspect", "ParseError", "ResultConflict", "Season",
    "SeasonError", "SeasonState", "TableRow", "UnsupportedResultStatus",
    "UnverifiedAdjustment",
    "adjustments_at", "archive_season_state", "current_ledger_view",
    "detect_kickoff_amendments", "fixture_id", "goal_count",
    "ingest_openfootball_results", "load_adjustments", "load_manifest",
    "openfootball_source_id", "parse_openfootball", "resolve_ledger", "season_code",
    "season_dir_name", "source_family",
]
