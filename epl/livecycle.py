"""THE ONE COMMAND. The live matchday cycle, sequenced and refusing.

    PYTHONPATH=src:. .venv/bin/python -m epl.livecycle
    PYTHONPATH=src:. .venv/bin/python -m epl.livecycle --dry-run
    PYTHONPATH=src:. .venv/bin/python -m epl.livecycle --allow-single-source

WHAT THIS IS. The owner adopted the matchday cadence by ruling (freshness-prereg
§4.5, recorded 2026-08-26): "effective when the automated one-command cycle runs
green". This module is that automation. It ORCHESTRATES — it computes no
forecast, no table and no score of its own, and every number it prints was
produced by machinery that already has its own suite and its own refusals. Its
job is sequencing, sourcing, cross-checking, and stopping.

Nine steps, each gated on the one before it:

  1. the odds snapshot, on Tuesdays and Fridays (UTC), via `epl.oddscapture`
  2. fetch BOTH result sources
  3. determine the NEW results and cross-check the two sources
  4. ingest — dry run first, then `--write` only if the dry run is clean
  5. forecast, if anything was written or no issuance exists for today's cutoff
  6. `check` the new bundle, and demand EXACTLY the designed refusal
  7. score the matchboard of the PRIOR issuance that priced those fixtures
  8. score the A8 shadow ledger from the same bundle
  9. print one screen: ingested, issued, the headline moves, rows appended

A NO-OP DAY IS THE COMMON CASE. No new results and a fresh issuance means the
cycle says so and exits 0. Running it daily has to be safe, or it will not be
run daily.

THE TWO CLOCKS, WHICH ARE THE THING THIS BUILD EXISTS TO GET RIGHT
------------------------------------------------------------------
``--cutoff`` is the fit's DATE boundary — midnight, the day. ``--observed-by``
is the KNOWLEDGE instant, and it must be at or after the ingest's
``observed_at`` or the fit is blind to the ingest that just ran. That exact
mistake produced a bundle that had to be discarded on MW1 day, and the reason
it is easy to make is arithmetic: `--observed-by` is written to minute
precision, and a minute FLOORED lands before an ingest stamped seconds earlier
inside it. :func:`knowledge_clock` takes both instants and CEILS, so the
knowledge clock cannot precede the knowledge.

LAUNCH MODE
-----------
A gate-running forecast must never be launched from a stdin heredoc: on macOS
the spawn kills the gate's parallel leg (`BrokenProcessPool`, with the serial,
repeat and chunk digests identical because nothing ran in parallel at all).
Module invocation or a real script file only. This module is invoked as
``python -m epl.livecycle`` — safe — and :func:`refuse_an_unsafe_launch`
refuses the other way in before anything runs, rather than after the ingest has
written.

THE SOURCES, AND THE RULE THAT DECIDES A RESULT IS REAL
-------------------------------------------------------
* **A — openfootball**, the season's own vendored source, refetched from the
  URL the manifest names. It MAY LAG: zero results is normal for it and is not
  an error.
* **B — football-data.co.uk `E0.csv`**, which appears about two hours after a
  round closes. Its short club spellings go through :mod:`epl.teams`, the
  registry the archive ingest already uses — never a new mapping, and never a
  slugger, because a slugger gives one club two keys the first time the feed
  changes a spelling.

POLICY. A result is ingestable **only** where both sources agree exactly on the
final score, **or** where exactly one source covers it and the operator passes
``--allow-single-source``. The default is OFF: missing-from-one is a STOP that
lists the uncovered fixtures. ANY disagreement on a covered fixture is an
unconditional STOP naming the fixture and both scores, and no flag turns it
off. A fixture the ledger ALREADY resolves, with sources agreeing, is nothing
to do — not a conflict; the sources catch up to a round days after it is
ingested and that is the ordinary weekly picture.

The season ledger's own conflict and revision machinery
(:func:`epl.season.ingest_openfootball_results`) stays the final arbiter. This
module never edits it, never bypasses it, and reads what it currently says
through :func:`epl.season.current_ledger_view` rather than through a private
reading of the file.

REFUSAL SEMANTICS
-----------------
One typed family, :class:`LiveCycleError`, caught by :func:`main` and printed as
``STOP: <TypeName>: <message>`` on stderr with exit **2** — the convention
:mod:`epl.simcli` and :mod:`epl.recal` already use, because a refusal an
operator cannot tell from a crash teaches them to ignore crashes. A source that
is down is :class:`SourceUnreachable` and stops the run; it is never a silent
skip.

THE FLIGHT LOG. Every run appends exactly one canonical-JSON line to
``reports/epl_livecycle_journal.jsonl``: when it ran, what ran, what was
refused, and the digests of whatever it wrote. ``--dry-run`` writes nothing
else, and it writes this — a flight log with holes in it is not a flight log,
and the line records ``"dry_run": true`` so the two are never confused.

NOT IN SCOPE, DELIBERATELY. No FPL capture (a separate queued build; A11 is not
recorded). No scraping beyond the two public files above. No cadence note in
the amendments ledger — the owner flips the cadence after this runs green in
production, and the switch date is his to record.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from epl import (fetch, leaguesim, matchboard, oddscapture, paths, recal,
                 recalfit, recalshadow, season as season_mod, simcli, teams)

__all__ = [
    "LiveCycleError", "SourceUnreachable", "SourceMalformed",
    "SourceDisagreement", "CoverageGap", "LedgerConflict", "GateNotPassed",
    "CheckUnexpected", "ScorecardMismatch", "OddsSnapshotFailed",
    "LaunchModeUnsafe", "SOURCE_A", "SOURCE_B", "SourceResult", "CrossCheck",
    "JOURNAL_PATH", "ODDS_SNAPSHOT_DIR", "DEFAULT_FETCHERS",
    "openfootball_url", "football_data_url", "fetch_openfootball",
    "fetch_football_data", "read_openfootball", "read_football_data",
    "knowledge_clock", "latest_stamp", "cross_check", "parse_check_report",
    "append_journal", "headline_moves", "issuance_days", "prior_issuance_for",
    "refuse_an_unsafe_launch", "run_cycle", "main",
]


# ==========================================================================
# 0. the typed family
# ==========================================================================

class LiveCycleError(RuntimeError):
    """Anything this cycle refuses. Printed as STOP, exit 2."""


class SourceUnreachable(LiveCycleError):
    """A result source could not be fetched. Never a silent skip."""


class SourceMalformed(LiveCycleError):
    """A source was fetched and could not be read as what it claims to be."""


class SourceDisagreement(LiveCycleError):
    """The two sources report different things about one covered fixture."""


class CoverageGap(LiveCycleError):
    """A result exactly one source covers, without --allow-single-source."""


class LedgerConflict(LiveCycleError):
    """A source contradicts what the season ledger already resolves, or an
    ingest offered rows the cross-check did not authorise."""


class GateNotPassed(LiveCycleError):
    """The forecast ran and its acceptance gate did not pass."""


class CheckUnexpected(LiveCycleError):
    """`check` on the new bundle said something other than the designed
    refusal — in either direction."""


class ScorecardMismatch(LiveCycleError):
    """A result cannot be scored against any issuance that preceded it, or a
    scoring step refused."""


class OddsSnapshotFailed(LiveCycleError):
    """The Tuesday/Friday capture could not be taken."""


class LaunchModeUnsafe(LiveCycleError):
    """This process was launched in a way that breaks the gate's parallel leg."""


#: Every typed refusal this command may print, its own and the ones it
#: delegates to. A `SeasonError` surfacing as a traceback would be exactly the
#: defect the STOP convention exists to prevent.
REFUSALS: tuple[type[BaseException], ...] = (
    LiveCycleError, season_mod.SeasonError, simcli.CliError,
    matchboard.MatchboardError, recalfit.RecalError, oddscapture.CaptureError,
    leaguesim.SimError, teams.UnknownTeamError,
)


# ==========================================================================
# 1. the sources
# ==========================================================================

SOURCE_A = "openfootball"
SOURCE_B = "football-data"

#: Where the flight log lives. Tracked, human-readable, append-only.
JOURNAL_PATH = paths.REPO_ROOT / "reports" / "epl_livecycle_journal.jsonl"

#: Where the Tuesday/Friday captures actually live. `epl.oddscapture` computes
#: its own default as `paths.DATA_DIR / "epl" / "odds_snapshots"`, and
#: `paths.DATA_DIR` is ALREADY `data/epl` — so that constant names
#: `data/epl/epl/odds_snapshots`, which does not exist and never has. The
#: operator's captures are in `data/epl/odds_snapshots`, so the cycle passes
#: the directory explicitly rather than inheriting a path that would start a
#: second, empty archive beside the real one. Left as a finding rather than
#: edited: changing that module's default would move where a bare
#: `python -m epl.oddscapture` writes, which is the operator's call.
ODDS_SNAPSHOT_DIR = paths.DATA_DIR / "odds_snapshots"

_TIMEOUT_S = 60
_USER_AGENT = "worldcup-epl-livecycle/1.0 (research; contact via repository)"

#: The football-data columns a result needs. Odds are not read here — §2.3
#: rules what may reach `z_mkt` and this cycle does not touch it.
_E0_REQUIRED = ("Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG")

#: How many fixture ids the flight log NAMES in a set it only counts. The count
#: and the digest are exact; the list is a sample. A tracked, append-only log
#: that carried 248 moved kickoffs and 380 resolved fixtures every day would
#: grow by megabytes a season and be read by nobody.
_IDS_SHOWN = 12
_E0_DIVISION = "E0"
_E0_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y")


@dataclass(frozen=True)
class SourceResult:
    """One final score, as ONE source reports it, resolved to a fixture id."""

    fixture_id: str
    home_key: str
    away_key: str
    home_raw: str
    away_raw: str
    hg: int
    ag: int
    date: str
    source: str

    @property
    def score(self) -> tuple[int, int]:
        return (self.hg, self.ag)

    def as_dict(self) -> dict[str, Any]:
        return {"fixture_id": self.fixture_id, "hg": self.hg, "ag": self.ag,
                "date": self.date, "source": self.source}


def openfootball_url(season_obj: season_mod.Season) -> str:
    """The season's OWN source url, out of its manifest. Not a new constant:
    the vendored bytes and the refetch must name the same file."""
    url = (season_obj.manifest.raw.get("fixtures_source") or {}).get("url")
    if not url:
        raise SourceUnreachable(
            f"{season_obj.season}: the manifest names no fixtures_source.url — "
            "there is nothing to refetch, and inventing a URL here would be "
            "this cycle deciding where the season's results come from")
    return str(url)


def football_data_url(season_obj: season_mod.Season) -> str:
    """`https://www.football-data.co.uk/mmz4281/<code>/E0.csv`, built from the
    pattern :mod:`epl.fetch` already publishes for the archive."""
    return fetch.BASE_URL.format(season_code=season_obj.season_code)


def _get(url: str, *, timeout: int = _TIMEOUT_S) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            ValueError) as exc:
        raise SourceUnreachable(
            f"{url}: {type(exc).__name__}: {exc}. A source being down is a "
            "STOP, not a skip — a cycle that quietly ran on one source would "
            "make the two-source rule an accident of the network") from exc


def fetch_openfootball(url: str) -> str:
    """Source A's bytes, decoded. Timeouts and explicit failure, no retries."""
    text = _get(url).decode("utf-8", errors="strict")
    if len(text) < 1000 or ("Matchday" not in text
                            and "Regular Season" not in text):
        raise SourceMalformed(
            f"{url} did not return an openfootball league file ({len(text)} "
            "characters, no round header). That is an error page, and parsing "
            "it would report a season with no fixtures in it")
    return text


def fetch_football_data(url: str) -> str:
    """Source B's bytes, decoded through `utf-8-sig`: the feed ships a BOM."""
    return _get(url).decode("utf-8-sig", errors="strict")


#: The real adapters, which is what the operator gets. Every test injects.
DEFAULT_FETCHERS: dict[str, Callable[[str], str]] = {
    SOURCE_A: fetch_openfootball,
    SOURCE_B: fetch_football_data,
}


def _one_per_fixture(rows: list[SourceResult], source: str
                     ) -> dict[str, SourceResult]:
    out: dict[str, SourceResult] = {}
    for row in rows:
        if row.fixture_id in out:
            first = out[row.fixture_id]
            raise SourceMalformed(
                f"{source} reports {row.fixture_id} twice: "
                f"{first.hg}-{first.ag} and {row.hg}-{row.ag}. One fixture, "
                "one final score — a source that files two is not a source "
                "this cycle can cross-check")
        out[row.fixture_id] = row
    return out


def read_openfootball(text: str, season_code: str) -> dict[str, SourceResult]:
    """Source A's RESULTS. Fixtures with no score are not results.

    The parse is :func:`epl.season.parse_openfootball`'s — the same one the
    ingest uses, which reads both the END layout (``Home  v Away   2-0 (1-0)``)
    and the middle one, and refuses a `v`-separated line it cannot split
    unambiguously. Nothing about the file is re-parsed here.
    """
    out: list[SourceResult] = []
    for row in season_mod.parse_openfootball(text):
        if row.hg is None or row.ag is None:
            continue
        home_key = _resolve(row.home_raw, SOURCE_A)
        away_key = _resolve(row.away_raw, SOURCE_A)
        if row.date is None:
            raise SourceMalformed(
                f"{SOURCE_A}: a result for {row.home_raw} v {row.away_raw} "
                "carries no date")
        out.append(SourceResult(
            fixture_id=season_mod.fixture_id(season_code, home_key, away_key),
            home_key=home_key, away_key=away_key,
            home_raw=row.home_raw, away_raw=row.away_raw,
            hg=season_mod.goal_count(row.hg, f"{SOURCE_A} hg"),
            ag=season_mod.goal_count(row.ag, f"{SOURCE_A} ag"),
            date=row.date.isoformat(), source=SOURCE_A))
    return _one_per_fixture(out, SOURCE_A)


def read_football_data(text: str, season_code: str) -> dict[str, SourceResult]:
    """Source B's RESULTS out of `E0.csv`: `Div`-filtered, dd/mm/yyyy dates.

    Club spellings go through :func:`epl.teams.resolve`, the registry the
    archive ingest already uses. `Nott'm Forest` is an alias there; an
    unregistered spelling is refused rather than slugged into a new club.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    columns = tuple(reader.fieldnames or ())
    missing = [c for c in _E0_REQUIRED if c not in columns]
    if missing:
        raise SourceMalformed(
            f"{SOURCE_B}: the feed no longer carries {missing}; it published "
            f"{list(columns)[:12]}. A results reader that guessed which column "
            "held the score would be guessing about the record")

    out: list[SourceResult] = []
    for lineno, row in enumerate(reader, start=2):
        if str(row.get("Div") or "").strip() != _E0_DIVISION:
            continue
        home_goals = str(row.get("FTHG") or "").strip()
        away_goals = str(row.get("FTAG") or "").strip()
        if not home_goals or not away_goals:
            continue                      # a fixture row, not a result row yet
        home_raw = str(row.get("HomeTeam") or "").strip()
        away_raw = str(row.get("AwayTeam") or "").strip()
        home_key = _resolve(home_raw, SOURCE_B, where=f"line {lineno}")
        away_key = _resolve(away_raw, SOURCE_B, where=f"line {lineno}")
        out.append(SourceResult(
            fixture_id=season_mod.fixture_id(season_code, home_key, away_key),
            home_key=home_key, away_key=away_key,
            home_raw=home_raw, away_raw=away_raw,
            hg=_e0_goals(home_goals, f"{SOURCE_B} line {lineno} FTHG"),
            ag=_e0_goals(away_goals, f"{SOURCE_B} line {lineno} FTAG"),
            date=_e0_date(str(row.get("Date") or "").strip(), lineno),
            source=SOURCE_B))
    return _one_per_fixture(out, SOURCE_B)


def _resolve(raw: str, source: str, where: str = "") -> str:
    """The club's STABLE KEY, through the repository's own registry.

    `epl.teams.resolve` is strict on purpose: an unregistered spelling raises
    rather than being slugged into a new club, because a slugger gives one club
    two keys the first time a feed changes a spelling and the model then looks
    fine while quietly splitting that club's history in half.
    """
    try:
        return teams.resolve(raw)[1]
    except teams.UnknownTeamError as exc:
        raise SourceMalformed(
            f"{source}{(' ' + where) if where else ''}: {exc}") from exc


def _e0_goals(value: str, label: str) -> int:
    try:
        return season_mod.goal_count(value, label)
    except season_mod.SeasonError as exc:
        raise SourceMalformed(f"{SOURCE_B}: {exc}") from exc


def _e0_date(value: str, lineno: int) -> str:
    for form in _E0_DATE_FORMATS:
        try:
            return _dt.datetime.strptime(value, form).date().isoformat()
        except ValueError:
            continue
    raise SourceMalformed(
        f"{SOURCE_B} line {lineno}: {value!r} is not a dd/mm/yyyy date. The "
        "feed's dates are day-first, and reading one month-first would file a "
        "result on the wrong side of a cutoff")


# ==========================================================================
# 2. the two clocks
# ==========================================================================

def knowledge_clock(now, ingest_at) -> pd.Timestamp:
    """The forecast's ``--observed-by``: minute precision, and never early.

    ``--cutoff`` is the fit's DATE boundary; this is the KNOWLEDGE instant, and
    it must be at or after the ingest that just wrote — otherwise the fit is
    blind to it. Both instants go in and the LATER one is CEILED to the minute:

    * flooring `12:55:03` when the ingest stamped `12:55:44` gives `12:55:00`,
      which is before the ingest. That is the MW1 bundle that was discarded.
    * ceiling gives `12:56:00`, which is after everything either clock knows.

    Both arguments go through the season's own stamp reader, so a `NaT` in
    either is refused here rather than silently comparing False forever.
    """
    stamp = max(season_mod._require_stamp(now, "now"),
                season_mod._require_stamp(ingest_at, "ingest observed_at"))
    return stamp.ceil("min")


# ==========================================================================
# 3. the cross-check
# ==========================================================================

@dataclass(frozen=True)
class CrossCheck:
    """What the two sources, held against the ledger, authorise for ingest."""

    #: fixture id -> the agreeing result, from source A where both carry it
    agreed: dict[str, SourceResult]
    #: fixture id -> the result exactly one source carries (--allow-single-source)
    single_source: dict[str, SourceResult]
    #: fixtures a source carries that the ledger ALREADY resolves, agreeing
    already_resolved: tuple[str, ...]

    @property
    def ingestable(self) -> dict[str, SourceResult]:
        return {**self.agreed, **self.single_source}

    @property
    def by_source(self) -> dict[str, list[str]]:
        """Which fixtures each source is the WRITER for, for the ingest step."""
        out: dict[str, list[str]] = {SOURCE_A: [], SOURCE_B: []}
        for fid in sorted(self.agreed):
            # Both sources agree, so source A's FILE is what gets ingested and
            # the ledger row carries its `openfootball@<sha>` provenance —
            # honest about which bytes it came from, with B's agreement being
            # the reason it was allowed through rather than a second author.
            out[SOURCE_A].append(fid)
        for fid, row in sorted(self.single_source.items()):
            out[row.source].append(fid)
        return out


def cross_check(season_obj: season_mod.Season,
                source_a: Mapping[str, SourceResult],
                source_b: Mapping[str, SourceResult],
                *, allow_single_source: bool = False) -> CrossCheck:
    """The MW1 protocol, encoded. What may be ingested, and what must STOP.

    The ledger's current reading comes from
    :func:`epl.season.current_ledger_view` — the season's OWN resolution, with
    no bounds, which is what the ingest itself consults. A private reading of
    the file would answer differently the first time a status row withdrew a
    result, and the two answers disagreeing is the whole class of bug the
    single resolution exists to close.
    """
    resolved = season_mod.current_ledger_view(season_obj).played_rows
    fixtures = {f.fixture_id for f in season_obj.fixtures}

    agreed: dict[str, SourceResult] = {}
    single: dict[str, SourceResult] = {}
    already: list[str] = []
    gaps: list[tuple[str, str]] = []

    for fid in sorted(set(source_a) | set(source_b)):
        a, b = source_a.get(fid), source_b.get(fid)
        covering = [r for r in (a, b) if r is not None]
        if fid not in fixtures:
            # A source may legitimately carry a match this season's registry
            # does not hold (openfootball's file has carried cup rounds), and
            # the ingest already tolerates that. Nothing to cross-check.
            continue
        if a is not None and b is not None:
            if a.score != b.score:
                raise SourceDisagreement(
                    f"{fid}: {SOURCE_A} says {a.hg}-{a.ag} and {SOURCE_B} says "
                    f"{b.hg}-{b.ag}. STOP: one of them is wrong and this cycle "
                    "does not get to pick. Check the fixture, then either wait "
                    "for the wrong one to correct itself or file the result by "
                    "hand with `simcli ingest-results --manual`.")
            if a.date != b.date:
                raise SourceDisagreement(
                    f"{fid}: {SOURCE_A} played it on {a.date} and {SOURCE_B} on "
                    f"{b.date}. STOP: `date_played` is what puts a result on "
                    "one side of a cutoff, so a cycle that picked a date would "
                    "be picking which forecasts the result scores against.")

        row = resolved.get(fid)
        if row is not None:
            have = (season_mod.goal_count(row.get("hg"), f"{fid} hg"),
                    season_mod.goal_count(row.get("ag"), f"{fid} ag"))
            for source in covering:
                if source.score != have:
                    raise LedgerConflict(
                        f"{fid}: the season ledger resolves {have[0]}-{have[1]} "
                        f"and {source.source} now says {source.hg}-{source.ag}. "
                        "STOP: that is either an upstream correction or a bad "
                        "ledger row, and which one it is a human decides. The "
                        "remedy is a deliberate correction row, never a cycle "
                        "that overwrote the record on its own.")
            already.append(fid)
            continue

        if a is not None and b is not None:
            agreed[fid] = a
        else:
            only = covering[0]
            if allow_single_source:
                single[fid] = only
            else:
                gaps.append((fid, only.source))

    if gaps:
        listing = "\n".join(f"  {fid}  (only {source} carries it)"
                            for fid, source in gaps)
        raise CoverageGap(
            f"{len(gaps)} result(s) exactly one source covers:\n{listing}\n"
            "STOP: the default is both-sources-agree. openfootball lags, and "
            "the honest answer to a lag is to wait for it — re-run in an hour. "
            "Pass --allow-single-source to take these on one source, "
            "deliberately, this run.")

    return CrossCheck(agreed=agreed, single_source=single,
                      already_resolved=tuple(already))


# ==========================================================================
# 4. the check-report parser
# ==========================================================================

#: THE DESIGNED REFUSAL, exactly. `check` re-runs the bundle with no posterior
#: in hand, so `dc_native`'s parity rerun cannot exercise the production grid
#: adapter and `parity_reference_is_production_grid` is REFUSED — a refusal is
#: not a pass, the arm is REFUSED with it, and the command exits 4. That is the
#: expected shape of a healthy live bundle. Everything else, in EITHER
#: direction, is a STOP: an extra failure means the bundle moved, and a full
#: PASS means the parity reference became reconstructable, which is a change in
#: the world the operator rules on rather than a green light the cycle takes.
EXPECTED_REFUSED_ARMS: tuple[str, ...] = ("dc_native",)
EXPECTED_REFUSED_CRITERIA: dict[str, tuple[str, ...]] = {
    "dc_native": ("parity_reference_is_production_grid",),
}


def parse_check_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Demand the designed refusal and nothing else. STRICT in both directions.

    Reads the report `simcli.check_issuance` returns rather than scraping the
    command's output, and compares it field by field against
    :data:`EXPECTED_REFUSED_ARMS` and :data:`EXPECTED_REFUSED_CRITERIA`. Every
    deviation is collected before anything raises, so an operator sees the
    whole disagreement at once instead of one line of it per re-run.
    """
    arms = dict(report.get("arms") or {})
    deviations: list[str] = []

    def listed(key: str) -> list[str]:
        return sorted(str(x) for x in (report.get(key) or []))

    if report.get("PASS"):
        deviations.append(
            "the check reports PASS in full. The designed refusal "
            f"({EXPECTED_REFUSED_CRITERIA['dc_native'][0]}) is absent, which "
            "means the parity reference became reconstructable at check time — "
            "a change in what this command can prove, and one to be ruled on "
            "rather than absorbed")
    for key in ("record_failed", "record_refused", "failed"):
        if listed(key):
            deviations.append(f"{key} = {listed(key)}, expected []")
    if listed("refused") != sorted(EXPECTED_REFUSED_ARMS):
        deviations.append(
            f"refused = {listed('refused')}, expected "
            f"{sorted(EXPECTED_REFUSED_ARMS)}")

    for arm, cell in sorted(arms.items()):
        failed = sorted(str(x) for x in (cell.get("criterion_failed") or []))
        refused = sorted(str(x) for x in (cell.get("criterion_refused") or []))
        want = sorted(EXPECTED_REFUSED_CRITERIA.get(arm, ()))
        if failed:
            deviations.append(f"{arm}.criterion_failed = {failed}, expected []")
        if refused != want:
            deviations.append(
                f"{arm}.criterion_refused = {refused}, expected {want}")

    if deviations:
        raise CheckUnexpected(
            "`check` on the new bundle did not say what a healthy live bundle "
            "says:\n" + "\n".join(f"  - {d}" for d in deviations)
            + f"\nheadline: {report.get('headline')!r}\nSTOP: the bundle is "
            "written and unaltered; read the report before re-issuing.")

    return {
        "exit_code": 0 if report.get("PASS") else 4,
        "PASS": bool(report.get("PASS")),
        "headline": report.get("headline"),
        "fully_anchored": report.get("fully_anchored"),
        "unanchored": listed("unanchored"),
        "refused": listed("refused"),
        "failed": listed("failed"),
        "record_failed": listed("record_failed"),
        "record_refused": listed("record_refused"),
        "designed_refusal": True,
    }


# ==========================================================================
# 5. the flight log
# ==========================================================================

def append_journal(path, entry: Mapping[str, Any]) -> str:
    """Append ONE canonical-JSON line. Returns the line, without its newline.

    Canonical because the log is compared across runs and machines: sorted
    keys, no incidental whitespace, no NaN. Append-only because it is a flight
    log — the run that went wrong is the one worth keeping.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = leaguesim.canonical_json(entry)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return line


# ==========================================================================
# 6. the launch-mode guard
# ==========================================================================

#: The season's own clock. `--cutoff` is a DAY, and which day it is has to be
#: the league's, not the machine's: a cycle run at 00:30 UTC in a British
#: summer is still the previous day in Europe/London, and issuing under
#: tomorrow's cutoff would put the fit a day ahead of the table it is scored
#: against. One definition, taken from `epl.simcli`.
SEASON_TIMEZONE = simcli.SEASON_TIMEZONE

#: `sys.argv[0]` when python was handed a script on stdin (`python - <<EOF`)
#: or a command string (`python -c '...'`).
_STDIN_ARGV = ("-", "-c", "")


def refuse_an_unsafe_launch(argv: Sequence[str] | None = None) -> None:
    """Refuse a launch mode that breaks the acceptance gate's parallel leg.

    HARD-WON, ON MW1 DAY. A forecast whose gate runs is a forecast that forks a
    process pool, and on macOS a python launched from a stdin heredoc cannot:
    the pool comes back ``BrokenProcessPool`` and the reproducibility criterion
    reports serial, repeat and chunk digests that are identical *because
    nothing ever ran in parallel*. A gate that cannot fail is worse than no
    gate, so the launch mode is refused at the door — before the ingest writes,
    not after — and the remedy is one line long.
    """
    argv = sys.argv if argv is None else argv
    zero = argv[0] if argv else ""
    if str(zero) in _STDIN_ARGV:
        raise LaunchModeUnsafe(
            f"this process was launched with argv[0]={zero!r} — a stdin "
            "heredoc or `python -c`. The acceptance gate forks a process pool "
            "and on macOS that spawn dies (BrokenProcessPool), with the "
            "serial, repeat and chunk digests all equal because nothing ran in "
            "parallel: a gate that cannot fail. Run it as "
            "`python -m epl.livecycle` or from a real script file.")


# ==========================================================================
# 7. the four heavy steps, as the cycle calls them
# ==========================================================================
# Each is a thin wrapper over machinery that already has its own suite. They
# are parameters of `run_cycle` with these as defaults, so the tests can drive
# the ORDER and the CLOCKS without running a simulation — and so this file can
# never grow a second implementation of any of them.

def _step_forecast(*, season, root, cutoff, observed_by, out_root, arms,
                   verbose: bool) -> dict:
    """Step 5 — `simcli.forecast`, every arm, with the gate running inside.

    IN PROCESS, never a subprocess: see :func:`refuse_an_unsafe_launch` for why
    the launch mode of the process that runs the gate matters at all.
    """
    return simcli.forecast(season=season, root=root, cutoff=cutoff, arms=arms,
                           observed_by=observed_by, out_root=out_root,
                           gate=True, verbose=verbose)


def _step_check(directory, *, verbose: bool) -> dict:
    """Step 6 — `simcli.check_issuance`, whose REPORT is parsed, not scraped."""
    return simcli.check_issuance(directory, verbose=verbose)


def _step_matchboard(*, directory, results_file, out_dir, season_root,
                     derived_at, verbose: bool) -> dict:
    """Step 7 — `simcli matchboard --score` (A7 (e)), on the PRIOR bundle."""
    return simcli.derive_matchboard(directory, out_dir, results_file=results_file,
                                    season_root=season_root,
                                    derived_at=derived_at, verbose=verbose)


def _step_shadow(*, directory, results_file, ledger, season_root,
                 verbose: bool) -> dict:
    """Step 8 — `python -m epl.recal score` (A8 (d)), the shadow challenger.

    Called through the module's own ``main`` so the operator's command and the
    cycle's step cannot answer differently; a non-zero exit is this cycle's
    refusal, and `recal` has already printed its own STOP line above it.
    """
    del verbose
    before = _count_lines(ledger)
    argv = ["score", "--directory", str(directory), "--results",
            str(results_file), "--ledger", str(ledger)]
    if season_root is not None:
        argv += ["--season-root", str(season_root)]
    code = recal.main(argv)
    if code != 0:
        raise ScorecardMismatch(
            f"`python -m epl.recal score` refused (exit {code}) for {directory}. "
            "Its own STOP line is printed above this one; nothing further in "
            "the cycle ran.")
    appended = _count_lines(ledger) - before
    return {"appended": appended, "repeated": 0, "ledger": str(ledger)}


DEFAULT_STEPS: dict[str, Callable[..., Any]] = {
    "forecast": _step_forecast,
    "check": _step_check,
    "matchboard": _step_matchboard,
    "shadow": _step_shadow,
}


def _count_lines(path) -> int:
    path = Path(path)
    if not path.exists():
        return 0
    return len([ln for ln in path.read_text(encoding="utf-8").splitlines()
                if ln.strip()])


# ==========================================================================
# 8. which issuance a result is scored against
# ==========================================================================

def prior_issuance_for(fixture_ids: Sequence[str], *, season, kickoffs,
                       out_root=None, exclude: Sequence[Path] = (),
                       board_reader: Callable[[Path], dict] | None = None,
                       ) -> dict[str, Path]:
    """fixture id -> the issuance whose matchboard may score it.

    THE FRESHEST FORECAST THAT STILL PRECEDED THE MATCH. Newest first, and the
    admissibility rule is :func:`epl.matchboard.score`'s own, applied here so
    the cycle picks a bundle that will be accepted rather than discovering at
    the door that it chose one that will not: the issuance's ``cutoff`` AND its
    ``observed_by`` must both be at or before the kickoff DAY the board
    records, and the board must actually carry the fixture.

    The issuance this cycle has just written is EXCLUDED, and cannot qualify
    anyway — its knowledge clock is this afternoon and the match was this
    morning. A fixture no bundle can score is a :class:`ScorecardMismatch`
    naming it, never a row filed against a forecast made after the fact.
    """
    board_reader = matchboard.derive if board_reader is None else board_reader
    excluded = {Path(p).resolve() for p in exclude}
    candidates = [p for p in reversed(issuance_days(season, out_root))
                  if p.resolve() not in excluded]

    cache: dict[Path, dict] = {}
    chosen: dict[str, Path] = {}
    unplaced: list[str] = []
    for fid in sorted(fixture_ids):
        kickoff_day = kickoffs[fid][0].isoformat()
        for candidate in candidates:
            # The directory name IS the cutoff day, so a bundle issued after
            # the match is skipped without reading it.
            if candidate.name > kickoff_day:
                continue
            board = cache.get(candidate)
            if board is None:
                board = cache[candidate] = board_reader(candidate)
            row = next((r for r in board.get("rows") or ()
                        if r.get("fixture_id") == fid), None)
            if row is None:
                continue
            kickoff = pd.Timestamp(row["date"])
            if (pd.Timestamp(board["cutoff"]) <= kickoff
                    and pd.Timestamp(board["observed_by"]) <= kickoff):
                chosen[fid] = candidate
                break
        else:
            unplaced.append(fid)

    if unplaced:
        raise ScorecardMismatch(
            "no issuance priced these fixtures before they kicked off, so "
            "there is no forecast for them to score against:\n"
            + "\n".join(f"  {fid}  (kicked off {kickoffs[fid][0]})"
                        for fid in unplaced)
            + f"\nconsidered {[p.name for p in candidates]}. STOP: the results "
            "ARE in the ledger; what is missing is a bundle that preceded them.")
    return chosen


# ==========================================================================
# 9. the cycle
# ==========================================================================

def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bounded(ids: Sequence[str]) -> dict[str, Any]:
    """A set of fixture ids for the flight log: counted, digested, sampled.

    The count and the digest are exact and the sample is a sample. By May a
    season resolves 380 fixtures and the source carries hundreds of kickoff
    moves, and a tracked append-only log that listed both every day would grow
    by megabytes and be read by nobody. The sources' own sha256s are recorded
    beside these, so the full sets are recoverable from the bytes the run saw.
    """
    ids = sorted(ids)
    return {"n": len(ids), "first": ids[:_IDS_SHOWN],
            "sha256": _sha256_text(leaguesim.canonical_json(ids))}


def _manual_rows_file(directory: Path, rows: Sequence[SourceResult],
                      note: str) -> Path:
    """The single-source results, as the season's own hand-entry format.

    They enter through `--manual`, which validates every row against the
    fixture list, the ledger's current reading and the goal-count rule before a
    byte is written — the same door the operator used for MW1. The note says
    which source they came from and that the run was deliberate, because the
    ledger row's `source` field will read `manual` and that is only half of
    where it came from.
    """
    path = directory / "single_source.jsonl"
    path.write_text("".join(
        json.dumps({"fixture_id": row.fixture_id, "date_played": row.date,
                    "hg": row.hg, "ag": row.ag,
                    "note": f"{note} ({row.source} only)"}) + "\n"
        for row in sorted(rows, key=lambda r: r.fixture_id)), encoding="utf-8")
    return path


def _expect(rows: Sequence[Mapping[str, Any]], want: Sequence[str],
            what: str) -> None:
    """An ingest that offers rows the cross-check did not authorise is a STOP.

    The dry run is not a rehearsal, it is a CONTRACT: these fixtures, and no
    others. A source that grew a row between the cross-check and the ingest —
    or a ledger the cross-check read differently from the ingest — must not be
    able to write it just because the ingest happened to accept it.
    """
    got = sorted(str(r.get("fixture_id")) for r in rows)
    if got != sorted(want):
        raise LedgerConflict(
            f"the {what} ingest offered {got} and the cross-check authorised "
            f"{sorted(want)}. STOP: nothing was written. The two readings of "
            "the ledger disagree, and an ingest that wrote the difference "
            "would be writing rows nothing checked.")


#: Enough for any timezone a hand-entered stamp could have been read on, and
#: nowhere near enough for a mistyped year.
_LEDGER_CLOCK_SLACK = pd.Timedelta(days=1)


def latest_stamp(season_obj: season_mod.Season, now) -> pd.Timestamp:
    """The latest ``observed_at`` on the season's results ledger, refusing one
    that is not merely on another clock.

    THE KNOWLEDGE CLOCK CLEARS THE WHOLE LEDGER, not only the rows one run
    wrote. This cycle stamps UTC; MW1 was entered by hand, and a hand-entered
    stamp is whatever clock the operator was reading — Europe/London runs an
    hour ahead of UTC for most of a season. An ``observed_by`` computed from
    ``now`` alone can therefore land BEFORE a row that is already on file, and
    a row observed after the knowledge bound is invisible to the fit: the same
    blindness the MW1 bundle had, arriving by a different route. Everything the
    ledger holds is known, so the bound is at or after the latest thing in it.

    A stamp more than a day out is not another timezone, it is a bad row.
    Reaching the bound out to meet it would publish an issuance whose knowledge
    clock is in the future and bury the typo inside it, so it is refused —
    before anything writes, because a ledger no bound can be computed over is
    one nothing should be added to.
    """
    now = season_mod._require_stamp(now, "now")
    stamps = {season_mod._require_stamp(
        row.get("observed_at"), f"{row.get('fixture_id')} observed_at"):
        str(row.get("fixture_id")) for row in season_obj.results}
    if not stamps:
        return now
    newest = max(stamps)
    if newest > now + _LEDGER_CLOCK_SLACK:
        raise LedgerConflict(
            f"the results ledger holds a row for {stamps[newest]!r} observed at "
            f"{newest.isoformat()}, more than {_LEDGER_CLOCK_SLACK} after now "
            f"({now.isoformat()} UTC). STOP: the knowledge clock has to clear "
            "every stamp on file, and clearing that one would put this "
            "issuance's observed_by in the future. Fix the row.")
    return max(newest, now)


def run_cycle(*, now=None, season: str = simcli.DEFAULT_SEASON, root=None,
              allow_single_source: bool = False, dry_run: bool = False,
              skip_odds_snapshot: bool = False,
              out_root=None, derived_root=None, snapshot_dir=None,
              shadow_ledger=None, journal=None,
              fetchers: Mapping[str, Callable[[str], str]] | None = None,
              odds_fetcher: Callable[[str], bytes] | None = None,
              steps: Mapping[str, Callable[..., Any]] | None = None,
              board_reader: Callable[[Path], dict] | None = None,
              arms: Sequence[str] | None = None,
              stream=None, verbose: bool = True) -> dict[str, Any]:
    """THE CYCLE. Nine steps, each gated on the one before it.

    ``now`` is an INPUT and the only clock this function reads: the boundary
    (:func:`main`) reads the wall clock, the library does not. Move the machine's
    clock with ``now`` fixed and every byte this produces is unchanged, which is
    what makes a re-run of a recorded cycle a re-run rather than a new one.

    Everything that touches the world is injectable and defaults to the real
    thing: the two result fetchers, the odds fetcher, the four heavy steps, and
    the matchboard reader that decides which bundle scores a result. That is
    how the suite runs without a network and without a simulation, and it is
    also how an operator can rehearse one step at a time.

    Returns the flight-log entry with the printed summary added to it.
    """
    refuse_an_unsafe_launch()
    stream = sys.stdout if stream is None else stream
    fetchers = dict(DEFAULT_FETCHERS) | dict(fetchers or {})
    steps = dict(DEFAULT_STEPS) | dict(steps or {})
    root = season_mod.SEASON_ROOT if root is None else Path(root)
    journal = JOURNAL_PATH if journal is None else Path(journal)
    snapshot_dir = ODDS_SNAPSHOT_DIR if snapshot_dir is None else Path(snapshot_dir)
    derived_root = (simcli.DERIVED_ROOT if derived_root is None
                    else Path(derived_root))
    shadow_ledger = (recalshadow.SHADOW_PATH if shadow_ledger is None
                     else Path(shadow_ledger))
    arms = tuple(simcli.ARMS if arms is None else arms)

    now = pd.Timestamp.now("UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    # Second precision throughout: the knowledge clock is a MINUTE and the
    # ledger's stamps are seconds, so microseconds are noise that would make
    # two records of the same cycle differ in a field nothing reads.
    now = now.floor("s")
    # The ledger's stamps are naive and mean UTC; the season's own clock is
    # what decides which DAY the cutoff is.
    observed_at = now.tz_localize(None).floor("s")
    cutoff = now.tz_convert(SEASON_TIMEZONE).date().isoformat()

    entry: dict[str, Any] = {
        "at": now.isoformat(),
        "season": season,
        "cutoff": cutoff,
        "observed_at": observed_at.isoformat(),
        "observed_by": None,
        "dry_run": bool(dry_run),
        "allow_single_source": bool(allow_single_source),
        "outcome": "STOP",
        "refused": None,
        "odds_snapshot": None,
        "sources": {},
        "already_resolved": None,
        "kickoff_moves": None,
        "ingested": {"fixtures": [], "single_source": [], "written": False,
                     "dry_run_rows": 0},
        "issuance": None,
        "headline_moves": None,
        "check": None,
        "scorecard": None,
        "shadow": None,
        "digests": {},
    }

    try:
        result = _run(entry, now=now, observed_at=observed_at, cutoff=cutoff,
                      season=season, root=root, arms=arms,
                      allow_single_source=allow_single_source, dry_run=dry_run,
                      skip_odds_snapshot=skip_odds_snapshot, out_root=out_root,
                      derived_root=derived_root, snapshot_dir=snapshot_dir,
                      shadow_ledger=shadow_ledger, fetchers=fetchers,
                      odds_fetcher=odds_fetcher, steps=steps,
                      board_reader=board_reader, verbose=verbose)
    except REFUSALS as exc:
        entry["outcome"] = "STOP"
        entry["refused"] = {"type": type(exc).__name__, "message": str(exc)}
        append_journal(journal, entry)
        raise

    append_journal(journal, entry)
    result["journal"] = paths.rel(journal)
    result["summary"] = render_summary(result)
    if verbose:
        print(result["summary"], file=stream, flush=True)
    return result


def _run(entry, *, now, observed_at, cutoff, season, root, arms,
         allow_single_source, dry_run, skip_odds_snapshot, out_root,
         derived_root, snapshot_dir, shadow_ledger, fetchers, odds_fetcher,
         steps, board_reader, verbose) -> dict[str, Any]:
    """The nine steps. Mutates `entry` as it goes, so a STOP is journalled with
    everything that had already run rather than with an empty record."""
    season_obj = season_mod.Season.load(season, root=root)
    # Read the ledger's clocks BEFORE anything writes: a ledger this cycle
    # cannot compute a knowledge bound over is a ledger it must not add to.
    latest_stamp(season_obj, observed_at)

    # --- 1. the odds snapshot (Tuesday and Friday, UTC) -------------------
    if not skip_odds_snapshot and oddscapture.is_capture_day(now):
        if dry_run:
            entry["odds_snapshot"] = {"planned": True, "capture_day": True,
                                      "day_name": now.day_name()}
        else:
            try:
                snap = oddscapture.capture(fetcher=odds_fetcher,
                                           directory=snapshot_dir, when=now)
            except oddscapture.CaptureError as exc:
                raise OddsSnapshotFailed(
                    f"the {now.day_name()} capture failed: {exc}. STOP: the "
                    "snapshot is step one and everything else is gated on it — "
                    "the source overwrites one file a week, so a capture "
                    "skipped is a publication that no longer exists."
                ) from exc
            entry["odds_snapshot"] = {**snap.as_dict(), "capture_day": True,
                                      "day_name": now.day_name()}
            entry["digests"]["odds_snapshot"] = snap.sha256

    # --- 2. both sources, or nothing --------------------------------------
    urls = {SOURCE_A: openfootball_url(season_obj),
            SOURCE_B: football_data_url(season_obj)}
    texts = {name: fetchers[name](urls[name]) for name in (SOURCE_A, SOURCE_B)}
    source_a = read_openfootball(texts[SOURCE_A], season_obj.season_code)
    source_b = read_football_data(texts[SOURCE_B], season_obj.season_code)
    entry["sources"] = {
        name: {"url": urls[name], "sha256": _sha256_text(texts[name]),
               "n_results": len(rows)}
        for name, rows in ((SOURCE_A, source_a), (SOURCE_B, source_b))}

    # Kickoff moves the refreshed source carries. ALWAYS REPORTED; written
    # only as a side effect of an openfootball RESULTS ingest, which is
    # `simcli.ingest_results`'s own documented behaviour and the reason a moved
    # kickoff does not leave a stale date behind — a fixture whose stale date
    # has passed reads `unresolved` and, past two days, raises `results_lag`.
    # So on a day with no new results the operator SEES the moves and nothing
    # is filed; on a day with results they are filed with the results, by the
    # one step that has a fresh parse of the source in its hands.
    moves = simcli.new_kickoff_amendments(
        season_obj, texts[SOURCE_A], known_at=observed_at,
        source_id=season_mod.openfootball_source_id(texts[SOURCE_A]))
    # COUNTED AND DIGESTED, not listed in full. On 2026-08-26 this is 248 of
    # 380 fixtures — openfootball has replaced the placeholder kickoff times
    # the vendored file was published with — and a journal line carrying 248
    # ids every day until somebody files them is a log nobody reads. The source
    # sha256 is recorded beside it, so the full list is recoverable from the
    # bytes this run actually saw.
    move_ids = sorted(m["fixture_id"] for m in moves)
    entry["kickoff_moves"] = {
        **_bounded(move_ids), "written": False}

    # --- 3. the new results, cross-checked --------------------------------
    plan = cross_check(season_obj, source_a, source_b,
                       allow_single_source=allow_single_source)
    entry["already_resolved"] = _bounded(plan.already_resolved)
    ingestable = plan.ingestable
    entry["ingested"]["fixtures"] = sorted(ingestable)
    entry["ingested"]["single_source"] = sorted(plan.single_source)

    # --- 4. the ingest: dry, then write -----------------------------------
    written: list[dict] = []
    resolved: dict[str, dict] = {}
    if ingestable:
        by_source = plan.by_source
        with tempfile.TemporaryDirectory(prefix="livecycle-") as tmp:
            manual = None
            if by_source[SOURCE_B]:
                manual = _manual_rows_file(
                    Path(tmp), [plan.single_source[f] for f in by_source[SOURCE_B]],
                    f"{SOURCE_B} E0.csv, taken on one source by "
                    f"--allow-single-source on {cutoff}")

            def ingest(write: bool) -> list[dict]:
                rows: list[dict] = []
                if by_source[SOURCE_A]:
                    got = simcli.ingest_results(
                        season=season, root=root,
                        openfootball_text=texts[SOURCE_A],
                        observed_at=observed_at, write=write, verbose=verbose)
                    _expect(got, by_source[SOURCE_A], SOURCE_A)
                    rows += got
                if manual is not None:
                    got = simcli.ingest_results(
                        season=season, root=root, manual_file=manual,
                        observed_at=observed_at, write=write, verbose=verbose)
                    _expect(got, by_source[SOURCE_B], SOURCE_B)
                    rows += got
                return rows

            entry["ingested"]["dry_run_rows"] = len(ingest(write=False))
            if not dry_run:
                written = ingest(write=True)
                entry["ingested"]["written"] = True
                # `ingest_results` files the source's kickoff moves alongside
                # the results it writes. Recorded rather than glossed: the
                # amendments overlay grew by this many rows on this run.
                entry["kickoff_moves"]["written"] = bool(by_source[SOURCE_A])

    if written:
        # The ledger is the source of truth, so what was written is read BACK
        # out of it rather than assumed from what was offered.
        season_obj = season_mod.Season.load(season, root=root)
        resolved = season_mod.current_ledger_view(season_obj).played_rows
        missing = sorted(set(ingestable) - set(resolved))
        if missing:
            raise LedgerConflict(
                f"the ingest wrote {len(written)} row(s) and the season ledger "
                f"still does not resolve {missing}. STOP: read the ledger "
                "before re-running; something superseded rows that were just "
                "filed.")
    entry["digests"]["results_ledger"] = simcli.sha256_file(
        Path(root) / season_mod.season_dir_name(season)
        / season_mod.RESULTS_FILENAME)

    # --- 5. the forecast, under the two clocks ----------------------------
    today = simcli.issuance_dir(season, cutoff, out_root)
    # THE KNOWLEDGE CLOCK CLEARS THE WHOLE LEDGER, not only this run's rows.
    # The ledger's stamps are naive and this cycle writes UTC, but MW1 was
    # entered by hand and a hand-entered stamp is whatever clock the operator
    # was reading — Europe/London is an hour ahead of UTC for most of a season.
    # An `observed_by` computed from `now` alone can therefore land BEFORE a
    # row that is already on file, and a row observed after the knowledge bound
    # is invisible to the fit: the same blindness as the MW1 bundle, arriving
    # by a different route. Everything the ledger holds is known, so the bound
    # is at or after the latest thing it holds.
    observed_by = knowledge_clock(observed_at, latest_stamp(season_obj,
                                                            observed_at))
    why = ("new results were written" if written
           else "no issuance exists for this cutoff")
    if written or not (today / "issuance.json").exists():
        entry["observed_by"] = observed_by.isoformat()
        if dry_run:
            entry["issuance"] = {"planned": True, "directory": paths.rel(today),
                                 "cutoff": cutoff,
                                 "observed_by": observed_by.isoformat(),
                                 "why": why}
        else:
            record = steps["forecast"](
                season=season, root=root, cutoff=cutoff,
                observed_by=observed_by.isoformat(), out_root=out_root,
                arms=arms, verbose=verbose)
            gate = record.get("gate")
            if gate is not None and not gate.get("PASS"):
                raise GateNotPassed(
                    f"the acceptance gate did not pass for "
                    f"{record.get('directory')}: failed "
                    f"{gate.get('failed') or 'none'}, skipped "
                    f"{gate.get('skipped') or 'none'}. STOP: the bundle is "
                    "written and must not be published; read `acceptance.json` "
                    "in it.")
            directory = Path(record["directory"])
            entry["issuance"] = {
                # Repo-relative: this log is TRACKED, and an absolute path
                # makes it a record of one laptop rather than of one repo.
                # `paths.rel` falls back to the absolute path for anything
                # outside the tree, so nothing is ever silently wrong.
                "directory": paths.rel(directory),
                "cutoff": str(record["cutoff"]),
                "observed_by": str(record["observed_by"]),
                "published_arm": record.get("published_arm"),
                "gate_PASS": bool((gate or {}).get("PASS", True)), "why": why}
            entry["digests"]["issuance_record"] = record.get("record_digest")

            # What this issuance moved against the one before it. REPORTED and
            # nothing else (A7 (f)): the daily cadence exists so a round's
            # effect on the title and the relegation picture is visible on the
            # day, and a number nobody can see is a number nobody checks.
            days = issuance_days(season, out_root)
            previous = next((p for p in reversed(days) if p.name < directory.name),
                            None)
            if previous is not None:
                entry["headline_moves"] = headline_moves(
                    directory, previous,
                    arm=record.get("published_arm") or matchboard.ARM)

            # --- 6. the check, which must say exactly one thing ------------
            entry["check"] = parse_check_report(steps["check"](
                directory, verbose=verbose))

    # --- 7 + 8. score the forecasts that priced what was just ingested ----
    if written:
        kickoffs = season_mod._kickoffs_known(
            season_obj.fixtures, season_obj.amendments, observed_at)
        chosen = prior_issuance_for(
            sorted(ingestable), season=season, kickoffs=kickoffs,
            out_root=out_root, exclude=[today], board_reader=board_reader)
        groups: dict[Path, list[str]] = {}
        for fid, bundle in sorted(chosen.items()):
            groups.setdefault(bundle, []).append(fid)

        board_tally = {"appended": 0, "repeated": 0, "bundles": []}
        shadow_tally = {"appended": 0, "repeated": 0, "bundles": []}
        tag = f"livecycle/{cutoff}"
        with tempfile.TemporaryDirectory(prefix="livecycle-score-") as tmp:
            for bundle, fids in sorted(groups.items()):
                results_file = Path(tmp) / f"results_{bundle.name}.jsonl"
                results_file.write_text("".join(
                    json.dumps({
                        "fixture_id": fid,
                        "home_goals": season_mod.goal_count(
                            resolved[fid].get("hg"), f"{fid} hg"),
                        "away_goals": season_mod.goal_count(
                            resolved[fid].get("ag"), f"{fid} ag"),
                        "matchweek": season_obj.fixture(fid).matchday,
                        "ingest": tag}) + "\n" for fid in fids),
                    encoding="utf-8")
                board = steps["matchboard"](
                    directory=bundle, results_file=results_file,
                    out_dir=derived_root, season_root=root,
                    derived_at=str(now.floor("s")), verbose=verbose)
                shadow = steps["shadow"](
                    directory=bundle, results_file=results_file,
                    ledger=shadow_ledger, season_root=root, verbose=verbose)
                for tally, got in ((board_tally, board), (shadow_tally, shadow)):
                    tally["appended"] += int(got.get("appended", 0))
                    tally["repeated"] += int(got.get("repeated", 0))
                    tally["bundles"].append(paths.rel(bundle))
        entry["scorecard"] = board_tally
        entry["shadow"] = shadow_tally
        entry["digests"]["matchboard_scorecard"] = simcli.sha256_file(
            Path(derived_root) / simcli.SCORECARD_FILENAME)
        entry["digests"]["recal_shadow"] = simcli.sha256_file(shadow_ledger)

    # --- 9. what happened -------------------------------------------------
    if dry_run:
        entry["outcome"] = "planned"
    elif written or entry["issuance"] is not None:
        entry["outcome"] = "ran"
    else:
        entry["outcome"] = "no-op"
    return entry


# ==========================================================================
# 10. the one screen a human reads
# ==========================================================================

def issuance_days(season: str, out_root=None) -> list[Path]:
    """Every written issuance for the season, oldest first.

    `simcli._is_issuance_day` is what decides whether a directory IS one, and
    it is reused rather than re-expressed: a staging directory and a
    hand-renamed `…-superseded-…` folder are not issuances, and two places
    deciding that separately is how one of them starts saying yes.
    """
    root = ((simcli.ISSUANCE_ROOT if out_root is None else Path(out_root))
            / season_mod.season_dir_name(season))
    if not root.exists():
        return []
    return sorted((p for p in root.glob("*")
                   if simcli._is_issuance_day(p.name)
                   and (p / "issuance.json").exists()),
                  key=lambda p: p.name)


def _consequences(directory: Path, arm: str) -> dict | None:
    path = Path(directory) / f"output_{arm}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())["consequences"]
    except (OSError, ValueError, KeyError):                 # pragma: no cover
        return None


def headline_moves(directory, previous, *, arm: str = matchboard.ARM,
                   top: int = 3) -> dict | None:
    """What this issuance moved, against the one before it.

    Reported, and nothing else: A7 (f) — this whole surface decides nothing,
    triggers nothing and gates nothing. It exists so the operator can see at a
    glance whether a round moved the title or the relegation picture, which is
    the question a daily cadence is for.
    """
    new, old = _consequences(directory, arm), _consequences(previous, arm)
    if new is None or old is None:
        return None
    out: dict[str, list[dict]] = {}
    for outcome in ("champion", "relegated"):
        rows = []
        for club in sorted(set(new) & set(old)):
            try:
                p, was = new[club][outcome]["p"], old[club][outcome]["p"]
            except (KeyError, TypeError):                   # pragma: no cover
                continue
            rows.append({"club": club, "p": float(p), "was": float(was),
                         "delta": round(float(p) - float(was), 6)})
        rows.sort(key=lambda r: (-abs(r["delta"]), r["club"]))
        out[outcome] = rows[:top]
    return out


_RULE = "=" * 72


def render_summary(entry: Mapping[str, Any]) -> str:
    """One screen: what was ingested, what was issued, what moved, what was
    appended. Deterministic given the entry — no clock is read here."""
    at = pd.Timestamp(entry["at"])
    verb = "PLAN" if entry["dry_run"] else "RUN"
    lines = [_RULE,
             f"epl live cycle — {verb} — {entry['season']} — cutoff "
             f"{entry['cutoff']} ({at.day_name()}, {at.isoformat()})",
             _RULE]

    snap = entry.get("odds_snapshot")
    if snap is None:
        lines.append("odds        no capture (not a Tuesday or Friday, or skipped)")
    elif snap.get("planned"):
        lines.append(f"odds        WOULD capture the {snap['day_name']} fixtures file")
    elif snap.get("written"):
        lines.append(f"odds        captured {snap['path']}  ({snap['n_epl_rows']} "
                     f"E0 rows, sha {snap['sha256'][:12]})")
    else:
        lines.append("odds        nothing new published since the last capture")

    for name in (SOURCE_A, SOURCE_B):
        cell = (entry.get("sources") or {}).get(name)
        if cell:
            lines.append(f"source      {name:<14} {cell['n_results']:>3} result(s)  "
                         f"sha {cell['sha256'][:12]}")

    moved = entry.get("kickoff_moves") or {}
    if moved.get("n"):
        shown = moved["first"][:4]
        lines.append(f"kickoffs    {moved['n']} move(s) the source now carries "
                     f"and the season does not")
        lines.append(
            f"              {', '.join(shown)}"
            + (" …" if moved["n"] > len(shown) else "")
            + ("  — FILED with this run's results ingest" if moved.get("written")
               else "  — not filed; `simcli ingest-results --from-openfootball "
                    "--write` files them"))

    ingested = entry["ingested"]
    if not ingested["fixtures"]:
        lines.append(f"ingest      nothing new — "
                     f"{(entry['already_resolved'] or {}).get('n', 0)} "
                     "fixture(s) both sources carry are already resolved and "
                     "agreeing")
    else:
        how = "WOULD ingest" if entry["dry_run"] else "ingested"
        single = ingested["single_source"]
        lines.append(f"ingest      {how} {len(ingested['fixtures'])} result(s)"
                     + (f", {len(single)} of them on ONE source"
                        if single else ", both sources agreeing"))
        for fid in ingested["fixtures"]:
            lines.append(f"              {fid}"
                         + ("  (single source)" if fid in single else ""))

    issuance = entry.get("issuance")
    if issuance is None:
        lines.append("issuance    fresh — an issuance already exists for this "
                     "cutoff and no result moved")
    elif issuance.get("planned"):
        lines.append(f"issuance    WOULD issue {issuance['directory']}")
        lines.append(f"              cutoff {issuance['cutoff']}  observed-by "
                     f"{issuance['observed_by']}  ({issuance['why']})")
    else:
        lines.append(f"issuance    {issuance['directory']}")
        lines.append(f"              cutoff {issuance['cutoff']}  observed-by "
                     f"{issuance['observed_by']}  gate "
                     f"{'PASS' if issuance['gate_PASS'] else 'NOT PASSED'}")

    check = entry.get("check")
    if check is not None:
        lines.append(f"check       exit {check['exit_code']} — {check['headline']}")
        lines.append(f"              refused {check['refused']}: the designed "
                     "parity refusal, and nothing else")

    for outcome, label in (("champion", "title"), ("relegated", "relegation")):
        rows = ((entry.get("headline_moves") or {}).get(outcome)) or []
        if rows:
            lines.append(f"{label:<11} " + "  ".join(
                f"{r['club']} {r['was']:.3f}->{r['p']:.3f} "
                f"({r['delta']:+.3f})" for r in rows))

    for key, label in (("scorecard", "scorecard"), ("shadow", "shadow")):
        cell = entry.get(key)
        if cell is None:
            lines.append(f"{label:<11} nothing to score")
        else:
            lines.append(
                f"{label:<11} {cell['appended']} row(s) appended"
                + (f", {cell['repeated']} already filed" if cell["repeated"] else "")
                + f"  from {', '.join(Path(b).name for b in cell['bundles'])}")

    lines.append(f"outcome     {entry['outcome'].upper()}")
    lines.append(_RULE)
    return "\n".join(lines)


# ==========================================================================
# 11. the command
# ==========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m epl.livecycle",
        description="the live matchday cycle: snapshot, fetch, cross-check, "
                    "ingest, forecast, check, score — or refuse.")
    parser.add_argument(
        "--allow-single-source", action="store_true",
        help="ingest a result exactly one source covers. The default refuses "
             "and lists the uncovered fixtures: openfootball lags, and waiting "
             "an hour is usually the right answer. This never relaxes the "
             "disagreement rule.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="stop before any write and print the plan. The one thing it does "
             "write is the cycle journal line, marked dry_run — a flight log "
             "with holes in it is not a flight log.")
    parser.add_argument(
        "--skip-odds-snapshot", action="store_true",
        help="do not take the Tuesday/Friday fixtures capture this run")
    parser.add_argument("--season", default=simcli.DEFAULT_SEASON)
    parser.add_argument("--root", default=None,
                        help=f"the season ledgers (default {season_mod.SEASON_ROOT})")
    parser.add_argument("--out-root", default=None,
                        help=f"where issuances are written (default "
                             f"{simcli.ISSUANCE_ROOT})")
    parser.add_argument("--derived-root", default=None,
                        help=f"where the matchboard scorecard lives (default "
                             f"{simcli.DERIVED_ROOT})")
    parser.add_argument("--snapshot-dir", default=None,
                        help=f"the odds snapshots (default {ODDS_SNAPSHOT_DIR})")
    parser.add_argument("--journal", default=None,
                        help=f"the cycle journal (default {JOURNAL_PATH})")
    return parser


def main(argv: Sequence[str] | None = None, **overrides) -> int:
    """`STOP: <TypeName>: <message>` on stderr, exit 2 — simcli's convention.

    ``**overrides`` go straight to :func:`run_cycle` and are the seam the tests
    drive: the clock, the fetchers and the four heavy steps. Nothing on the
    command line can set them, because a cadence command whose sources could be
    swapped from the shell is a cadence command that can be told what happened.
    """
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    kwargs: dict[str, Any] = {
        "season": args.season, "root": args.root, "out_root": args.out_root,
        "derived_root": args.derived_root, "snapshot_dir": args.snapshot_dir,
        "journal": args.journal,
        "allow_single_source": args.allow_single_source,
        "dry_run": args.dry_run,
        "skip_odds_snapshot": args.skip_odds_snapshot,
    }
    kwargs.update(overrides)
    try:
        run_cycle(**kwargs)
    except REFUSALS as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
