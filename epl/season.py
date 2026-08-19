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

`Season.at(C, observed_by=O)` moves the known-at bound off the cutoff and onto O
for ALL THREE ledgers — results by `observed_at <= O`, amendments and
adjustments by `known_at <= min(C, O)` — so an old forecast reruns as the
forecast it was rather than as a stale results ledger read against a fresh
schedule. Rewriting history is therefore impossible without an explicit,
reviewable ledger row — which is the point.

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
import re
from dataclasses import dataclass, field
from pathlib import Path

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
_FIXTURE_RE = re.compile(r"^(?P<home>\S.*?)\s+v(?:s|\.)?\s+(?P<away>\S.*?)$")


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

        m = _RESULT_RE.match(body)
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
    known_at_text = _timestamp(known_at).isoformat()
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
    at = _timestamp(cutoff)
    mine = [r for r in rows if r["season"] == season]
    known = [r for r in mine if _timestamp(r["known_at"]) <= at]
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
                                    *, write: bool = False) -> list[dict]:
        return ingest_openfootball_results(
            self, text, observed_at=observed_at, source_id=source_id, write=write)


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
    """Base kickoffs with every amendment known by `cutoff` applied, in order."""
    out = {f.fixture_id: (f.base_date, f.base_time) for f in fixtures}
    rows = [r for r in amendments if _timestamp(r["known_at"]) <= cutoff]
    for row in sorted(rows, key=lambda r: _timestamp(r["known_at"])):
        fid = row["fixture_id"]
        if fid not in out:
            raise SeasonError(f"kickoff amendment for unknown fixture {fid!r}")
        date = (_timestamp(row["date"]).date() if row.get("date")
                else out[fid][0])
        out[fid] = (date, row.get("time", out[fid][1]))
    return out


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


def _visible_results(results: list[dict], fixtures_by_id, cutoff_day: pd.Timestamp,
                     observed_by: pd.Timestamp, kickoffs) -> tuple[dict, dict]:
    """(played scorelines, ledger statuses) visible at the cutoff.

    Bitemporal: a row is visible iff it happened before the cutoff DAY and was
    observed by the cutoff. Where several rows describe one fixture, the latest
    observation wins — corrections are appended, never edited in place.

    "Latest observation wins" is resolved over scores and statuses TOGETHER, in
    one pass. Two passes with the score winning at the end is the obvious
    implementation and it is wrong in one direction: a match filed with a
    scoreline and later abandoned or voided would keep the result the league
    took away, because the status row it was corrected by never gets to win. The
    other direction — a postponement corrected by the result of the rearranged
    match — still resolves to the result, because that row is the later
    observation, not because scores are privileged.

    The unsupported-status check runs AFTER the known-at filter, deliberately.
    The ledger is append-only, so a row filed tomorrow sits in the same file as
    yesterday's; validating it before the filter would make today's entry
    retroactively break every earlier snapshot — the same class of bug as
    reading its content early. It still fails closed the moment it is visible.
    """
    scored: list[dict] = []
    latest: dict[str, tuple[pd.Timestamp, int, dict]] = {}

    for order, row in enumerate(results):
        fid = row["fixture_id"]
        if fid not in fixtures_by_id:
            raise SeasonError(f"results ledger row for unknown fixture {fid!r}")
        observed = _timestamp(row["observed_at"])
        if observed > observed_by:
            continue
        status = row.get("status")
        if status is not None and status not in _LEDGER_STATUSES:
            raise UnsupportedResultStatus(
                f"{fid}: results ledger status {status!r} is out of v1 scope "
                f"(only {sorted(_LEDGER_STATUSES)} are modelled)")
        if status is None:
            if _timestamp(row["date_played"]) >= cutoff_day:
                continue
            scored.append(row)
        key = (observed, order)
        if fid not in latest or key > latest[fid][:2]:
            latest[fid] = (observed, order, row)

    _validate_scores(scored)

    played: dict[str, tuple[int, int]] = {}
    statuses: dict[str, str] = {}
    for fid, (_, _, row) in latest.items():
        status = row.get("status")
        if status is not None:
            statuses[fid] = status
            continue
        played[fid] = (int(row["hg"]), int(row["ag"]))
        _check_orientation(fid, row, fixtures_by_id, kickoffs)
    return played, statuses


def _check_orientation(fid: str, row: dict, fixtures_by_id, kickoffs) -> None:
    """Fail closed on a result that looks home/away-flipped (plan v2 D3)."""
    fixture = fixtures_by_id[fid]
    played = _timestamp(row["date_played"]).date()
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
    cut = _timestamp(cutoff)
    obs = cut if observed_by is None else _timestamp(observed_by)
    cutoff_day = cut.normalize()
    fixtures_by_id = {f.fixture_id: f for f in fixtures}

    # `observed_by` bounds the SNAPSHOT, so it bounds all three ledgers, not the
    # results alone. A schedule move and a points deduction each carry `known_at`
    # for the same reason a result carries `observed_at`, and a snapshot that
    # read a stale results ledger against a fresh schedule and a fresh
    # deductions table would not be any moment that ever existed — a rerun of an
    # old forecast would then not be that forecast. `min` because a cutoff
    # earlier than `observed_by` still bounds what has HAPPENED.
    known_by = min(cut, obs)

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

def ingest_openfootball_results(season: Season, text: str, observed_at, source_id: str,
                                *, write: bool = False) -> list[dict]:
    """Turn the scored lines of an openfootball file into new ledger rows.

    Idempotent: a row whose scoreline already sits in the ledger is skipped. A
    row that CONTRADICTS the ledger raises `ResultConflict` — when a manual entry
    and openfootball disagree, the run stops and a human decides (plan v2 D4).
    Nothing is written unless `write=True`.
    """
    existing: dict[str, tuple[int, int]] = {}
    for row in season.results:
        if row.get("status") is None and row.get("hg") is not None:
            existing[row["fixture_id"]] = (int(row["hg"]), int(row["ag"]))

    observed = _timestamp(observed_at).isoformat()
    fixtures_by_id = {f.fixture_id: f for f in season.fixtures}
    new: list[dict] = []
    seen: set[str] = set()

    for row in parse_openfootball(text):
        if row.hg is None or row.ag is None:
            continue
        fid = fixture_id(season.season_code, teams.team_key(row.home_raw),
                         teams.team_key(row.away_raw))
        if fid not in fixtures_by_id:
            raise SeasonError(f"{season.season}: ingested result for unknown fixture {fid!r}")
        if fid in seen:
            raise ResultConflict(f"{fid}: the ingested file holds it twice")
        seen.add(fid)
        if fid in existing:
            if existing[fid] != (row.hg, row.ag):
                raise ResultConflict(
                    f"{fid}: ledger holds {existing[fid][0]}-{existing[fid][1]}, "
                    f"{source_id} says {row.hg}-{row.ag}. STOP: check which is right and "
                    f"correct the ledger deliberately.")
            continue
        if row.date is None:
            raise SeasonError(f"{fid}: ingested result has no date")
        new.append({
            "fixture_id": fid,
            "date_played": row.date.isoformat(),
            "hg": int(row.hg),
            "ag": int(row.ag),
            "source": source_id,
            "observed_at": observed,
            "note": "",
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
    "RESULTS_FILENAME", "SEASON_ROOT", "Fixture", "FixtureRow", "Manifest",
    "OrientationSuspect", "ParseError", "ResultConflict", "Season", "SeasonError",
    "SeasonState", "TableRow", "UnsupportedResultStatus", "UnverifiedAdjustment",
    "adjustments_at", "archive_season_state", "detect_kickoff_amendments",
    "fixture_id", "ingest_openfootball_results", "load_adjustments", "load_manifest",
    "openfootball_source_id", "parse_openfootball", "season_code", "season_dir_name",
]
