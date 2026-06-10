"""P3 v0 — the cached squad-anchor loader (tag -> (squad_z, has_squad) per team).

This is the LIBRARY-side mirror of ``model.strength.team_elo_z``: a pure,
offline, cached function that turns a tournament tag into the per-team
``squad_z`` (z-scored top-18 club-Elo mean over covered teams) + ``has_squad``
(coverage mask) the model wiring threads into the att/def prior anchor
(``k_squad·squad_z·has_squad``).

It reads ONLY the committed ``config/squads/`` reference CSVs — the squad list,
the point-in-time clubelo snapshot for that tag, and the explicit alias map —
exactly the same offline inputs ``scripts/build_squad_z.py`` uses, and composes
the TDD'd pure primitives in ``wcmodel.data.sources.squad_z`` (the EXACT join,
the top-18 mean, the ``has_squad`` mask, the covered-set z-score). NO network, NO
store, NO fit, ZERO Odds-API credits.

LEAKAGE contract (P3 prereg §5, ADDENDUM): each tag maps to the snapshot whose
endpoint date D is strictly pre-cutoff for that tournament — the committed
snapshots are pinned no-look-ahead by the content tests in
``tests/data/test_squad_z.py`` (no ``From > D`` rating window). The fit-level
leakage canary (``tests/model/test_fit_squad_leakage.py``) asserts a historical
fit only ever consumes the tag whose snapshot endpoint <= its cutoff's start.

CACHED: ``functools.lru_cache`` keyed by tag — repeated fits at the same cutoff
reuse the parse. The cached return is an immutable ``SquadAnchor`` named tuple of
two frozen-by-convention dicts (callers must not mutate).
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from wcmodel.data.sources.squad_z import (
    compute_has_squad,
    match_squad_to_elo,
    top18_mean,
    zscore_covered,
)

# Repo root: src/wcmodel/data/sources/squad_anchor.py -> parents[4] == repo.
_REPO = Path(__file__).resolve().parents[4]
_SQUADS = _REPO / "config" / "squads"

#: tournament tag -> the point-in-time clubelo snapshot (the prereg cutoffs).
#: WC-2022 / Euro-2024 are the sweep's historical held-out cutoffs; wc2026 is the
#: 2026 live path. Each snapshot endpoint is strictly pre-cutoff (prereg §5).
SNAPSHOT_FOR_TAG: dict[str, str] = {
    "wc2022": "clubelo_20221120.csv",
    "euro2024": "clubelo_20240614.csv",
    "wc2026": "clubelo_20260610.csv",
}


class SquadAnchor(NamedTuple):
    """Per-team squad anchor: ``squad_z[team]`` (z, 0.0 if uncovered) + ``has_squad[team]`` (0/1)."""

    squad_z: dict[str, float]
    has_squad: dict[str, int]


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read a '#'-commented CSV into dict rows (header = first non-'#' line)."""
    lines = [ln for ln in path.read_text().splitlines() if not ln.lstrip().startswith("#")]
    lines = [ln for ln in lines if ln.strip() != ""]
    return list(csv.DictReader(lines))


def _load_elo_table(snapshot: str) -> dict[str, float]:
    table: dict[str, float] = {}
    for row in _read_rows(_SQUADS / snapshot):
        club = (row.get("Club") or "").strip()
        if club:
            table[club] = float(row["Elo"])
    return table


def _load_squad(csv_name: str) -> dict[str, list[str]]:
    path = _SQUADS / csv_name
    if not path.exists():
        return {}
    by_team: dict[str, list[str]] = {}
    for row in _read_rows(path):
        team = (row.get("team") or "").strip()
        club = (row.get("club") or "").strip()
        by_team.setdefault(team, [])
        if club:
            by_team[team].append(club)
    return by_team


def _load_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _read_rows(_SQUADS / "club_aliases.csv"):
        s = (row.get("squad_club") or "").strip()
        c = (row.get("clubelo_club") or "").strip()
        if s and c:
            out[s] = c
    return out


@lru_cache(maxsize=None)
def load_squad_anchor(tag: str) -> SquadAnchor:
    """Tournament tag -> ``SquadAnchor(squad_z, has_squad)`` over that tag's teams.

    Composes the pure §3 join, §4 top-18 mean + ``has_squad`` mask, and §4.4
    covered-set z-score. An uncovered team gets ``squad_z == 0.0`` AND
    ``has_squad == 0`` (the model also multiplies by ``has_squad``, so the squad
    term is zero either way — belt-and-suspenders). Raises ``KeyError`` for an
    unknown tag (the only valid tags are the three pre-registered snapshots).
    """
    snapshot = SNAPSHOT_FOR_TAG[tag]                      # KeyError on unknown tag
    squad_by_team = _load_squad(f"{tag}.csv")
    elo_by_club = _load_elo_table(snapshot)
    aliases = _load_aliases()

    club_elo_mean: dict[str, float] = {}
    has_squad: dict[str, int] = {}
    for team, clubs in squad_by_team.items():
        matched, _gaps = match_squad_to_elo(clubs, elo_by_club, aliases)
        club_elo_mean[team] = top18_mean(matched)
        has_squad[team] = compute_has_squad(len(matched))

    squad_z = zscore_covered(club_elo_mean, has_squad)
    return SquadAnchor(squad_z=squad_z, has_squad=has_squad)


def squad_anchor_arrays(tag: str, teams: list[str]):
    """``(squad_z_arr, has_squad_arr)`` aligned to ``teams`` (the design index).

    A team absent from the tag's squad table -> ``squad_z=0.0, has_squad=0`` (it
    keeps the pure-Elo anchor; the squad term is zero). This is the array form the
    ``fit`` path threads into ``build_design`` alongside ``elo_z``.
    """
    import numpy as np

    anchor = load_squad_anchor(tag)
    sz = np.array([float(anchor.squad_z.get(t, 0.0)) for t in teams], dtype=float)
    hs = np.array([float(anchor.has_squad.get(t, 0)) for t in teams], dtype=float)
    return sz, hs
