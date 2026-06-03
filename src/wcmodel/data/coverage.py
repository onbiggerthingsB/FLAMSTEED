"""StatsBomb coverage enumeration + report.

xG is **coverage-gated**: StatsBomb Open Data is rich for big nations and
sparse/absent for minnows, and we **NEVER impute** the gap. Before any xG
feature is trusted we enumerate, for a given team list, which teams actually
appear in the StatsBomb competition/match metadata (``covered``) and which do
not (the **gap set**) — so the absence is explicit and auditable, never a
silently-zeroed feature (north-star §4.2; see ``sources/statsbomb.py``).

``enumerate_coverage`` is a **pure** function over already-pulled metadata (no
network), so it runs OFFLINE against fixtures. The 48-team WC-2026 intersection
is GATED on the user-provided ``config/tournament_2026.yaml`` draw file; this
module reports coverage for whatever team list it is handed and the report notes
the 48-team gap analysis finalizes when that file lands (Task 13).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def _covered_team_universe(competitions) -> set[str]:
    """Set of every team appearing anywhere in the StatsBomb metadata.

    Accepts several shapes, tolerant of how the metadata was assembled:
      - ``{"competitions": [...]}`` or a bare list of competition rows;
      - each competition row may embed a ``teams`` list (as assembled by
        iterating ``matches`` per competition-season);
      - or a top-level ``{"teams": [...]}`` roster (flat covered-team list).

    Real ``statsbombpy.sb.competitions()`` carries no team column, so the live
    path assembles the per-competition ``teams`` rosters from ``fetch_matches``
    before calling here (the fixture mirrors that assembled shape).
    """
    teams: set[str] = set()

    if isinstance(competitions, dict):
        for t in competitions.get("teams", []) or []:
            teams.add(t)
        rows = competitions.get("competitions", [])
    else:
        rows = competitions

    for row in rows or []:
        for t in row.get("teams", []) or []:
            teams.add(t)
        # Defensive: some assembled shapes carry home/away on the row directly.
        for k in ("home_team", "away_team"):
            v = row.get(k)
            if isinstance(v, str):
                teams.add(v)

    return teams


def enumerate_coverage(competitions, teams) -> pd.DataFrame:
    """Per-team StatsBomb coverage flags. Pure; no network.

    Returns a DataFrame with one row per requested team (input order preserved)
    and columns ``team, covered``, where ``covered`` is ``True`` iff the team
    appears in the StatsBomb competition/match metadata. Coverage is a presence
    signal only — nothing about xG is imputed for uncovered teams.
    """
    universe = _covered_team_universe(competitions)
    return pd.DataFrame(
        {"team": list(teams),
         "covered": [t in universe for t in teams]}
    )


def write_coverage_report(cov: pd.DataFrame, path: str | Path,
                          *, source_version: str | None = None,
                          extra_sections: str | None = None) -> Path:
    """Write a markdown coverage report (+ a CSV companion) and return the path.

    The markdown lists the covered teams, the uncovered **gap set**, and the
    headline counts; the CSV is the raw ``team, covered`` table next to it
    (same stem, ``.csv``). Explicitly notes that the 48-team WC-2026 gap analysis
    finalizes when ``config/tournament_2026.yaml`` lands (Task 13).

    ``source_version`` (the pinned release marker) and ``extra_sections`` (a
    pre-rendered markdown block, e.g. the live competition inventory pulled by
    the generator) are optional enrichments — the function stays pure either way.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    covered = sorted(cov.loc[cov["covered"], "team"].tolist())
    uncovered = sorted(cov.loc[~cov["covered"], "team"].tolist())
    n_total = len(cov)
    n_cov = len(covered)

    ver_line = (f"- Pinned release marker: `{source_version}`"
                if source_version else None)

    lines = [
        "# Phase 1 — StatsBomb xG coverage report",
        "",
        "StatsBomb Open Data xG is **point-in-time** (static + versioned; "
        "`valid_as_of == observed_at == match_date`) and **coverage-gated**: "
        "rich for big nations, sparse/absent for minnows. Uncovered teams are "
        "**absent / NULL**, never imputed.",
        "",
        *( [ver_line] if ver_line else [] ),
        f"- Teams checked: **{n_total}**",
        f"- Covered: **{n_cov}**",
        f"- Uncovered (gap set): **{n_total - n_cov}**",
        "",
        *( [extra_sections, ""] if extra_sections else [] ),
        "## Covered",
        "",
        ("\n".join(f"- {t}" for t in covered) if covered else "_(none)_"),
        "",
        "## Uncovered — gap set (xG absent / NULL, never imputed)",
        "",
        ("\n".join(f"- {t}" for t in uncovered) if uncovered else "_(none)_"),
        "",
        "## 48-team WC-2026 intersection — GATED",
        "",
        "The 48-team WC-2026 coverage intersection is **gated** on the "
        "user-provided `config/tournament_2026.yaml` draw file (Task 13). This "
        "report covers the team list it was handed; the final 48-team gap "
        "analysis is produced once the draw file lands.",
        "",
    ]
    path.write_text("\n".join(lines))

    csv_path = path.with_suffix(".csv")
    cov.to_csv(csv_path, index=False)

    return path
