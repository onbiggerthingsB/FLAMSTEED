"""WC-2026 tournament structure: loader + validator (GATED).

The 2026 World Cup is the first 48-team edition: **12 groups of 4** (48 teams),
**104 fixtures**, top two of each group plus the **8 best third-placed teams**
advancing to a 32-team knockout, with the bracket split into two halves
("paths") that only meet in the final.

This module deliberately ships **no draw data**. Authoring or fabricating the
groups/fixtures here would invent facts; the verified draw is supplied by the
user as ``config/tournament_2026.yaml`` (Phase-0 decision 2). What lives here is
purely the *structure contract* — a strict ``validate_tournament`` plus a thin
``load_tournament`` that reads the YAML and validates it — so that whenever the
real file lands it is checked against the known 2026 format before anything
downstream consumes it.

The third-place tiebreaker ORDER is the published FIFA sequence and is enforced
exactly: ``goal_difference``, ``goals_scored``, ``head_to_head``, ``fair_play``,
``drawing_of_lots``. No network, no store dependency — pure validation + a YAML
read.
"""
from __future__ import annotations

from pathlib import Path

import yaml

#: 2026 is the first 48-team World Cup.
N_TEAMS = 48
#: Twelve groups...
N_GROUPS = 12
#: ...of four teams each.
TEAMS_PER_GROUP = 4
#: 104 matches across group stage + knockouts (the published 2026 count).
N_FIXTURES = 104
#: Top two of every group advance directly.
ADVANCE_PER_GROUP = 2
#: Plus the eight best third-placed teams.
BEST_THIRDS = 8
#: Published FIFA third-place tiebreaker sequence — order is significant.
THIRD_PLACE_TIEBREAKERS = [
    "goal_difference",
    "goals_scored",
    "head_to_head",
    "fair_play",
    "drawing_of_lots",
]


def validate_tournament(data: dict) -> dict:
    """Validate a WC-2026 tournament structure against the known 2026 format.

    Enforces, raising :class:`ValueError` with a clear message on any violation:

      - exactly 12 ``groups``, each with exactly 4 ``teams``;
      - 48 teams total across the groups, all distinct;
      - exactly 104 ``fixtures``;
      - ``advancement.per_group == 2`` and ``advancement.best_thirds == 8``;
      - ``third_place_tiebreakers`` equal to the published FIFA sequence, in the
        exact order ``[goal_difference, goals_scored, head_to_head, fair_play,
        drawing_of_lots]``;
      - a ``bracket`` with exactly two ``paths`` (the two knockout halves).

    Returns ``data`` unchanged when valid. This does NOT author or infer any
    draw content — it only checks the shape of a user-supplied structure.
    """
    groups = data.get("groups")
    if not isinstance(groups, list) or len(groups) != N_GROUPS:
        n = len(groups) if isinstance(groups, list) else "missing"
        raise ValueError(f"expected exactly {N_GROUPS} groups, got {n}")

    all_teams: list[str] = []
    for group in groups:
        teams = group.get("teams") if isinstance(group, dict) else None
        if not isinstance(teams, list) or len(teams) != TEAMS_PER_GROUP:
            name = group.get("name") if isinstance(group, dict) else group
            n = len(teams) if isinstance(teams, list) else "missing"
            raise ValueError(
                f"group {name!r}: expected exactly {TEAMS_PER_GROUP} teams, got {n}"
            )
        all_teams.extend(teams)

    if len(all_teams) != N_TEAMS:
        raise ValueError(
            f"expected {N_TEAMS} teams total across groups, got {len(all_teams)}"
        )
    if len(set(all_teams)) != N_TEAMS:
        dupes = sorted({t for t in all_teams if all_teams.count(t) > 1})
        raise ValueError(f"team names must be distinct; duplicates: {dupes}")

    fixtures = data.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != N_FIXTURES:
        n = len(fixtures) if isinstance(fixtures, list) else "missing"
        raise ValueError(f"expected exactly {N_FIXTURES} fixtures, got {n}")

    advancement = data.get("advancement")
    if not isinstance(advancement, dict):
        raise ValueError("missing 'advancement' block")
    if advancement.get("per_group") != ADVANCE_PER_GROUP:
        raise ValueError(
            f"advancement.per_group must be {ADVANCE_PER_GROUP}, "
            f"got {advancement.get('per_group')!r}"
        )
    if advancement.get("best_thirds") != BEST_THIRDS:
        raise ValueError(
            f"advancement.best_thirds must be {BEST_THIRDS}, "
            f"got {advancement.get('best_thirds')!r}"
        )

    tiebreakers = data.get("third_place_tiebreakers")
    if tiebreakers != THIRD_PLACE_TIEBREAKERS:
        raise ValueError(
            "third_place_tiebreakers must be exactly "
            f"{THIRD_PLACE_TIEBREAKERS}, got {tiebreakers!r}"
        )

    bracket = data.get("bracket")
    paths = bracket.get("paths") if isinstance(bracket, dict) else None
    if not isinstance(paths, list) or len(paths) != 2:
        n = len(paths) if isinstance(paths, list) else "missing"
        raise ValueError(f"bracket must declare exactly two paths, got {n}")

    return data


def load_tournament(path: str | Path) -> dict:
    """Read a WC-2026 draw YAML, validate it, and return the parsed structure.

    GATED: the verified ``config/tournament_2026.yaml`` is provided by the user
    (Phase-0 decision 2) and is intentionally absent from the repo; nothing here
    fabricates it. Reads the file, runs :func:`validate_tournament`, and returns
    the validated dict.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return validate_tournament(data)
