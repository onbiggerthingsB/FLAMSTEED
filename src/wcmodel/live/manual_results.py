"""Matchday-1 MANUAL results-ingest fallback (Phase 0, PRIORITY ZERO).

Hand-enter a played WC fixture's final score in a strict CSV and thread it —
UNCHANGED — through the EXISTING leakage-safe POINT_IN_TIME ingest machinery
(:func:`wcmodel.live.ingest_live.ingest_live_result`) into the daily-update
run's store, so ``read(cutoff)`` sees it and the sim CONDITIONS on it.
Independent of upstream (martj42) timing.

This module is PURE VALIDATION + a thin ingest wrapper. It adds NO new store /
leakage behaviour: every row is written by ``ingest_live_result`` (which itself
re-validates the score and enforces ``observed_at >= match date``), keyed on the
SAME ``match_id`` identity the martj42 schedule/result rows use — so a manual row
and the eventual upstream row are the SAME logical key and the store's
deterministic supersede tie-break applies.

STRICT, fail-loud, NEVER fuzzy (spec §2.1). Team names must EXACTLY match the
``config/tournament_2026.yaml`` drawn-48 set; the ``(home, away, date)`` triple
must equal a real scheduled fixture; scores must be finite/non-negative/integral;
a KNOCKOUT-stage level score requires a ``shootout_winner`` in {home, away}.

The WHOLE file is validated before ANY row is written (no partial ingest).
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from wcmodel.data.features import valid_played_results
from wcmodel.data.tournament import load_tournament, tournament_format
from wcmodel.live.ingest_live import ingest_live_result

#: The required CSV columns (in order). ``shootout_winner`` is an OPTIONAL last
#: column — present in the documented example so the operator sees the field.
REQUIRED_COLUMNS = ["date", "home_team", "away_team", "home_score", "away_score"]
OPTIONAL_COLUMNS = ["shootout_winner"]

#: The canonical 2026 draw (resolved relative to this file's repo root).
_REAL_DRAW = Path(__file__).resolve().parents[3] / "config" / "tournament_2026.yaml"

#: The tournament tag stamped on a manual WC result (matches the schedule rows so
#: the ``match_id`` and downstream tier mapping are identical to the real fixture).
#: Phase-2A: the DEFAULT only — a draw loaded with ``tournament_path`` stamps its
#: own format ``competition_name`` instead (the WC format resolves to this exact
#: literal, so the default path is byte-identical).
MANUAL_TOURNAMENT = "FIFA World Cup"


class ManualResultsError(ValueError):
    """A manual-results CSV row failed STRICT validation (fail-loud, never fuzzy)."""


@dataclass(frozen=True)
class ManualRow:
    """One validated manual result, resolved against the draw fixture.

    Carries the fields ``ingest_live_result`` needs: the score, the fixture
    identity (``date``/``home_team``/``away_team``), the resolved venue
    ``city``/``country``/``neutral`` (so the ``match_id`` matches the schedule
    row), and the optional ``shootout_winner`` (a level-KO penalty winner, else
    ``None``)."""
    date: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    city: str
    country: str | None
    neutral: bool
    is_knockout: bool
    shootout_winner: str | None
    #: The competition tag the row is ingested under — the draw's format
    #: ``competition_name`` (WC default: exactly :data:`MANUAL_TOURNAMENT`).
    tournament: str = MANUAL_TOURNAMENT


def manual_file_sha256(csv_path: str | Path) -> str:
    """sha256 of the CSV file's raw bytes — the provenance fingerprint recorded in
    the run log + printed summary so a hand-entered run is auditable."""
    return hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()


def _load_draw(tournament: dict | None = None,
               tournament_path: str | Path | None = None) -> dict:
    """The validated draw dict.

    Resolution order: an explicit ``tournament`` dict (test escape hatch) >
    ``tournament_path`` (loaded + validated via ``load_tournament`` — the
    Phase-2A multi-edition hook, e.g. ``config/tournament_ac2027.yaml``) >
    the default ``config/tournament_2026.yaml`` (byte-identical WC path)."""
    if tournament is not None:
        return tournament
    if tournament_path is not None:
        return load_tournament(tournament_path)
    return load_tournament(_REAL_DRAW)


def _venue_country_map(draw: dict) -> dict:
    """``{city: ISO-country}`` from the draw's ``venues`` block (for ``neutral``)."""
    return {v["city"]: v.get("country") for v in draw.get("venues", [])}


def _fixture_index(draw: dict):
    """Two lookups over the draw's fixtures, keyed for exact (NEVER fuzzy) matching:

      * ``group_by_triple`` : ``{(home, away, date): fixture}`` for GROUP fixtures
        (``match is None`` — concrete drawn nations), the matchday-1 path;
      * ``ko_dates`` : the set of KNOCKOUT fixture dates (``match is not None``) —
        a concrete-team KO result can't match a placeholder KO fixture by triple,
        so it is accepted iff both teams are drawn AND its date is a KO date
        (spec §2.2).
    """
    group_by_triple = {}
    ko_dates = set()
    for fx in draw.get("fixtures", []):
        date = str(fx.get("date"))
        if fx.get("match") is not None:
            ko_dates.add(date)
        else:
            group_by_triple[(fx.get("home"), fx.get("away"), date)] = fx
    return group_by_triple, ko_dates


def _parse_int_score(raw, *, field: str, rownum: int):
    """Parse a score cell as a VALID goal count (finite/non-negative/integral) via
    the shared ``valid_played_results`` rule. Raises ``ManualResultsError`` on a
    fractional/negative/non-numeric value (NEVER ``int()``-truncated)."""
    probe = pd.DataFrame([{"home_score": raw, "away_score": 0}])
    if valid_played_results(probe).empty:
        raise ManualResultsError(
            f"row {rownum}: {field}={raw!r} is not a valid goal count — scores must "
            "be finite, non-negative, integral (no truncation, no fuzzy parse)"
        )
    return int(float(raw))


def validate_manual_csv(csv_path: str | Path,
                        tournament: dict | None = None,
                        tournament_path: str | Path | None = None) -> list[ManualRow]:
    """Parse + STRICTLY validate a manual-results CSV against a draw.

    The draw defaults to the 2026 World Cup yaml; ``tournament_path`` validates
    against another edition's committed draw instead (Phase-2A F11 — e.g.
    ``config/tournament_ac2027.yaml``), with the drawn-team set, fixture index,
    venue map, HOSTS (neutral flags) and the competition tag all taken from
    THAT document and its format block. The WC default resolves to the same
    hosts/tag literals as before — byte-identical behaviour.

    Returns the list of validated :class:`ManualRow`. Raises
    :class:`ManualResultsError` (fail-loud, naming the row + the violated rule) on
    the FIRST violation — the whole file is validated before any caller ingests,
    so a bad file never produces a partial write. Validation order (spec §2.1):
    header → team names (EXACT, drawn set) → scheduled-fixture match → scores →
    KO-level→shootout_winner.
    """
    draw = _load_draw(tournament, tournament_path)
    fmt = tournament_format(draw)
    drawn = set(draw["teams"])
    venue_country = _venue_country_map(draw)
    group_by_triple, ko_dates = _fixture_index(draw)
    host_by_country = {code: team for team, code in fmt["hosts"].items()}

    path = Path(csv_path)
    if not path.exists():
        raise ManualResultsError(f"manual-results CSV not found: {path}")

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        # (1) HEADER — must be exactly the required columns (+ the optional one).
        allowed = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        unknown = [c for c in header if c not in allowed]
        if missing or unknown:
            raise ManualResultsError(
                f"bad CSV header {header!r}: required={REQUIRED_COLUMNS} "
                f"(optional {OPTIONAL_COLUMNS}); missing={missing}, unknown={unknown}"
            )
        rows = list(reader)

    if not rows:
        raise ManualResultsError(f"manual-results CSV {path} has no data rows")

    out: list[ManualRow] = []
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        date = (r.get("date") or "").strip()
        home = (r.get("home_team") or "").strip()
        away = (r.get("away_team") or "").strip()
        shootout = (r.get("shootout_winner") or "").strip() or None

        # (2) TEAM NAMES — EXACT membership of the drawn set (NEVER fuzzy).
        for who, name in (("home_team", home), ("away_team", away)):
            if name not in drawn:
                raise ManualResultsError(
                    f"row {i}: {who}={name!r} is not a drawn nation of the "
                    f"{fmt['competition_name']} draw — names must EXACTLY match "
                    "the draw yaml (no fuzzy matching)"
                )
        if home == away:
            raise ManualResultsError(f"row {i}: home and away team are identical ({home!r})")

        # (3) SCHEDULED-FIXTURE match — exact (home, away, date) triple.
        fixture = group_by_triple.get((home, away, date))
        is_knockout = False
        if fixture is None:
            # Not a group fixture. Accept as a KNOCKOUT result iff the date is a
            # real KO fixture date (both teams already verified drawn). Otherwise
            # reject: a flipped home/away, wrong date, or non-fixture pairing.
            if date in ko_dates:
                is_knockout = True
                city = None
                country = None
                neutral = True
            else:
                raise ManualResultsError(
                    f"row {i}: ({home!r}, {away!r}, {date!r}) is not a scheduled "
                    f"{fmt['competition_name']} fixture — check the home/away order "
                    "and the date (no fuzzy match)"
                )
        else:
            city = fixture.get("venue")
            country = venue_country.get(city)
            host_team = host_by_country.get(country)
            neutral = not (host_team is not None and host_team in (home, away))

        # (4) SCORES — finite / non-negative / integral (shared rule, no truncation).
        hs = _parse_int_score(r.get("home_score"), field="home_score", rownum=i)
        as_ = _parse_int_score(r.get("away_score"), field="away_score", rownum=i)

        # (5) KO-level → shootout_winner required; group level → must be empty.
        level = hs == as_
        if shootout is not None and not level:
            raise ManualResultsError(
                f"row {i}: shootout_winner={shootout!r} given but the score "
                f"({hs}-{as_}) is not level — a shootout decides only a level match"
            )
        if is_knockout and level:
            if shootout is None:
                raise ManualResultsError(
                    f"row {i}: a level knockout score ({hs}-{as_}) requires "
                    "shootout_winner (the penalty winner)"
                )
            if shootout not in (home, away):
                raise ManualResultsError(
                    f"row {i}: shootout_winner={shootout!r} must be one of the two "
                    f"teams ({home!r}, {away!r})"
                )
        elif (not is_knockout) and level and shootout is not None:
            raise ManualResultsError(
                f"row {i}: a level GROUP score ({hs}-{as_}) is a draw — it must NOT "
                f"carry a shootout_winner ({shootout!r})"
            )

        out.append(ManualRow(
            date=date, home_team=home, away_team=away,
            home_score=hs, away_score=as_,
            city=city, country=country, neutral=neutral,
            is_knockout=is_knockout,
            shootout_winner=shootout if (is_knockout and level) else None,
            tournament=fmt["competition_name"],
        ))
    return out


def ingest_manual_rows(store, rows: list[ManualRow], *,
                       observed_at: str | pd.Timestamp) -> int:
    """Write each validated :class:`ManualRow` into ``results`` via the EXISTING
    ``ingest_live_result`` (the leakage-safe POINT_IN_TIME path). Returns the
    number of rows written.

    ``observed_at`` is the OPERATOR's entry time (``now``) — the real-ingest
    vector: a manual row's ``valid_as_of`` is the match date (set by
    ``ingest_live_result``) and its ``observed_at`` is ``now`` (later). The store
    therefore makes the row visible at/after ``now`` and supersedes/ is-superseded
    per the deterministic tie-break against the eventual upstream row (same
    ``match_id``)."""
    n = 0
    for row in rows:
        n += ingest_live_result(
            store,
            home_team=row.home_team, away_team=row.away_team,
            date=row.date, home_score=row.home_score, away_score=row.away_score,
            tournament=row.tournament, neutral=row.neutral,
            city=row.city if row.city is not None else "",
            country=row.country if row.country is not None else "",
            observed_at=observed_at,
            winner_override=row.shootout_winner,
        )
    return n
