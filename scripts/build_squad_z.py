#!/usr/bin/env python3
"""P3 v0 — OFFLINE build of the club-Elo squad-strength anchor (``squad_z``).

Reads ONLY the committed CSVs under ``config/squads/`` (the three squad lists, the
three point-in-time clubelo.com snapshots, and the explicit club alias map) plus
``src/wcmodel/data/ref/confederations.csv``. NO network, NO store, NO fit, ZERO
Odds-API credits. Emits ``reports/squad_z_<as_of>.md`` with the per-tournament +
per-confederation coverage tables, the squad_z rankings, the alias-map footprint,
and the gapped-team list (spec
``docs/superpowers/specs/2026-06-10-p3v0-squad-anchor-design.md`` §7).

The numeric heavy lifting (the EXACT join, the top-18 mean, the has_squad mask,
the z-score) lives in the TDD'd pure module ``wcmodel.data.sources.squad_z``; this
script is the thin offline orchestrator + the pure report helpers tested in
``tests/scripts/test_build_squad_z.py``.

Usage (from the worktree):
    PYTHONPATH=<worktree>/src .venv/bin/python scripts/build_squad_z.py
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

# Pure join/aggregation primitives (no I/O).
from wcmodel.data.sources.squad_z import (
    MIN_MATCHED,
    compute_has_squad,
    match_squad_to_elo,
    top18_mean,
    zscore_covered,
)

_REPO = Path(__file__).resolve().parents[1]
_SQUADS = _REPO / "config" / "squads"
_CONF_CSV = _REPO / "src" / "wcmodel" / "data" / "ref" / "confederations.csv"

# Tournament -> clubelo snapshot (the point-in-time cutoff file).
_TOURNAMENTS = {
    "wc2026": "clubelo_20260610.csv",
    "wc2022": "clubelo_20221120.csv",
    "euro2024": "clubelo_20240614.csv",
}

# Elite footballing nations for the sanity tripwire (binding rule 2: too-good =
# bug). If a covered team OUTSIDE this set ranks above EVERY one of these in a
# tournament's squad_z, flag a suspected join bug. Deliberately small + obvious.
_ELITE = {
    "France", "England", "Spain", "Brazil", "Germany", "Argentina",
    "Portugal", "Netherlands", "Italy", "Belgium",
}


# --------------------------------------------------------------------------- #
# Offline CSV loaders (skip '#' comment lines).                                 #
# --------------------------------------------------------------------------- #
def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read a '#'-commented CSV into a list of dict rows (header = first non-'#')."""
    lines = [ln for ln in path.read_text().splitlines() if not ln.lstrip().startswith("#")]
    lines = [ln for ln in lines if ln.strip() != ""]
    return list(csv.DictReader(lines))


def load_elo_table(snapshot: str) -> dict[str, float]:
    """clubelo snapshot -> {Club: Elo} (the EXACT-match join target)."""
    table: dict[str, float] = {}
    for row in _read_rows(_SQUADS / snapshot):
        club = (row.get("Club") or "").strip()
        if club:
            table[club] = float(row["Elo"])
    return table


def load_squad(csv_name: str) -> dict[str, list[str]]:
    """Squad CSV -> {team: [club, ...]} (player dropped; the join is club-only).

    A not-yet-curated squad file (absent on disk) yields an empty mapping, so the
    build runs incrementally during curation rather than crashing.
    """
    path = _SQUADS / csv_name
    if not path.exists():
        return {}
    by_team: dict[str, list[str]] = {}
    for row in _read_rows(path):
        team = (row.get("team") or "").strip()
        club = (row.get("club") or "").strip()
        by_team.setdefault(team, [])
        # A coverage-gap sentinel row has an empty club -> keep the team but no clubs.
        if club:
            by_team[team].append(club)
    return by_team


def load_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _read_rows(_SQUADS / "club_aliases.csv"):
        s = (row.get("squad_club") or "").strip()
        c = (row.get("clubelo_club") or "").strip()
        if s and c:
            out[s] = c
    return out


def load_confederations() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _read_rows(_CONF_CSV):
        out[(row["team"]).strip()] = (row["confederation"]).strip()
    # Curacao is in the 2026 model field but absent from confederations.csv -> CONCACAF.
    out.setdefault("Curaçao", "CONCACAF")
    out.setdefault("Curacao", "CONCACAF")
    return out


# --------------------------------------------------------------------------- #
# Per-tournament build (composes the pure primitives).                          #
# --------------------------------------------------------------------------- #
def build_tournament(
    squad_by_team: dict[str, list[str]],
    elo_by_club: dict[str, float],
    aliases: dict[str, str],
    confed: dict[str, str],
) -> dict:
    """Run the §3 join, §4 aggregation, §4/§5 mask + z-score for one tournament."""
    club_elo_mean: dict[str, float] = {}
    has_squad: dict[str, int] = {}
    per_team: dict[str, dict] = {}
    gaps_detail: dict[str, list[str]] = {}

    for team, clubs in squad_by_team.items():
        matched, gap_clubs = match_squad_to_elo(clubs, elo_by_club, aliases)
        n_squad = len(clubs)
        n_matched = len(matched)
        club_elo_mean[team] = top18_mean(matched)
        has = compute_has_squad(n_matched)
        has_squad[team] = has
        per_team[team] = {
            "confederation": confed.get(team, "Unknown"),
            "n_squad": n_squad,
            "n_matched": n_matched,
            "has_squad": has,
        }
        if gap_clubs:
            gaps_detail[team] = gap_clubs

    squad_z = zscore_covered(club_elo_mean, has_squad)

    # Gapped-team list = teams masked OFF (has_squad=0), with a reason.
    gaps: dict[str, str] = {}
    for team, info in per_team.items():
        if info["has_squad"] == 0:
            if info["n_squad"] == 0:
                gaps[team] = "coverage gap: no squad found (sentinel; masked, never invented)"
            else:
                gaps[team] = (
                    f"thin coverage ({info['n_matched']} matched < {MIN_MATCHED}); "
                    f"{info['n_squad']} squad players, non-clubelo clubs"
                )

    flags = flag_sanity(squad_z, has_squad=has_squad)

    return {
        "per_team": per_team,
        "per_tournament": _per_tournament_summary(per_team),
        "per_confederation": per_confederation_coverage(per_team),
        "club_elo_mean": club_elo_mean,
        "squad_z": squad_z,
        "has_squad": has_squad,
        "gaps": gaps,
        "gaps_detail": gaps_detail,
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# Pure coverage / sanity / report helpers (TDD'd).                              #
# --------------------------------------------------------------------------- #
def _per_tournament_summary(per_team: dict[str, dict]) -> dict:
    n = len(per_team)
    n_has = sum(t["has_squad"] for t in per_team.values())
    pcts = [
        (t["n_matched"] / t["n_squad"] * 100.0) if t["n_squad"] else 0.0
        for t in per_team.values()
    ]
    mean_pct = sum(pcts) / len(pcts) if pcts else 0.0
    return {"n_teams": n, "n_has_squad": n_has, "mean_match_pct": mean_pct}


def per_confederation_coverage(per_team: dict[str, dict]) -> dict[str, dict]:
    """Aggregate per-team coverage into per-confederation rows (spec §7).

    For each confederation: # teams, mean player-match % (n_matched/n_squad), and
    # has_squad=1. A team with n_squad=0 contributes 0% (no div-by-zero).
    """
    groups: dict[str, list[dict]] = {}
    for info in per_team.values():
        groups.setdefault(info["confederation"], []).append(info)
    out: dict[str, dict] = {}
    for conf, members in groups.items():
        pcts = [
            (m["n_matched"] / m["n_squad"] * 100.0) if m["n_squad"] else 0.0
            for m in members
        ]
        out[conf] = {
            "n_teams": len(members),
            "n_has_squad": sum(m["has_squad"] for m in members),
            "mean_match_pct": sum(pcts) / len(pcts) if pcts else 0.0,
        }
    return out


def flag_sanity(
    squad_z: dict[str, float],
    has_squad: dict[str, int] | None = None,
    top_k: int = 5,
) -> list[str]:
    """Flag absurd rankings as suspected join bugs (binding rule 2).

    Trips if a NON-elite covered team appears in the top-``top_k`` of squad_z while
    an elite nation is present in the covered set (so the comparison is meaningful).
    Returns a list of human-readable flag strings ([] = clean).
    """
    covered = {
        t: z for t, z in squad_z.items()
        if has_squad is None or has_squad.get(t, 1) == 1
    }
    if not covered:
        return []
    elite_present = any(t in _ELITE for t in covered)
    if not elite_present:
        return []  # no elite yardstick in this set -> can't judge
    ranked = sorted(covered.items(), key=lambda kv: kv[1], reverse=True)
    flags: list[str] = []
    for team, z in ranked[:top_k]:
        if team not in _ELITE:
            flags.append(
                f"SUSPECTED JOIN BUG: non-elite '{team}' (squad_z={z:+.2f}) in the "
                f"top {top_k} — verify its club-Elo join."
            )
    # Also flag any elite nation that sinks to the bottom of the covered set.
    for team, z in ranked[-top_k:]:
        if team in _ELITE and z < 0:
            flags.append(
                f"SUSPECTED JOIN BUG: elite '{team}' (squad_z={z:+.2f}) at the "
                f"bottom — verify its squad/club spellings."
            )
    return flags


def _fmt_pct(x: float) -> str:
    return f"{x:.1f}%"


def _coverage_table(per_conf: dict[str, dict]) -> str:
    order = ["UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC", "Unknown"]
    rows = ["| Confederation | # teams | mean player-match % | # has_squad=1 |",
            "|---|---|---|---|"]
    for conf in order:
        if conf not in per_conf:
            continue
        c = per_conf[conf]
        rows.append(
            f"| {conf} | {c['n_teams']} | {_fmt_pct(c['mean_match_pct'])} | {c['n_has_squad']} |"
        )
    # Any confederation not in the canonical order (defensive).
    for conf, c in per_conf.items():
        if conf not in order:
            rows.append(
                f"| {conf} | {c['n_teams']} | {_fmt_pct(c['mean_match_pct'])} | {c['n_has_squad']} |"
            )
    return "\n".join(rows)


def _zscore_table(squad_z: dict[str, float], has_squad: dict[str, int],
                  top_n: int | None = None, bottom_n: int | None = None,
                  covered_only: bool = False) -> str:
    items = list(squad_z.items())
    if covered_only:
        items = [(t, z) for t, z in items if has_squad.get(t, 0) == 1]
    ranked = sorted(items, key=lambda kv: kv[1], reverse=True)
    sel = ranked
    if top_n is not None or bottom_n is not None:
        head = ranked[: (top_n or 0)]
        tail = ranked[-(bottom_n):] if bottom_n else []
        sel = head + ([("…", None)] if (top_n and bottom_n and len(ranked) > top_n + bottom_n) else []) + tail
    rows = ["| Rank | Team | squad_z | has_squad |", "|---|---|---|---|"]
    rank = 0
    for team, z in sel:
        if z is None:
            rows.append("| … | … | … | … |")
            continue
        rank += 1
        rows.append(f"| {rank} | {team} | {z:+.3f} | {has_squad.get(team, 0)} |")
    return "\n".join(rows)


def assemble_report(tournaments: dict[str, dict], alias_map_size: int, as_of: str) -> str:
    """Assemble the full markdown report (spec §7). Pure: dicts in, string out."""
    out: list[str] = []
    out.append(f"# Squad-strength anchor (`squad_z`) — P3 v0 coverage + rankings ({as_of})")
    out.append("")
    out.append(
        "Offline build from committed `config/squads/` CSVs (hand-curated squad lists + "
        "point-in-time clubelo.com snapshots). The join is EXACT club-name match + the "
        f"explicit `club_aliases.csv` map (**alias-map size: {alias_map_size}**), NEVER "
        "fuzzy. A team with < "
        f"{MIN_MATCHED} matched players is masked (`has_squad=0`) and keeps the pure-Elo "
        "anchor downstream (spec §5 — coverage correlates with strength, so a missing "
        "`squad_z` is NOT missing-at-random and is never imputed to the mean)."
    )
    out.append("")

    # Surface any sanity flags prominently at the top.
    all_flags = [f for t in tournaments.values() for f in t.get("flags", [])]
    out.append("## Sanity tripwire (binding rule 2: too-good = bug)")
    if all_flags:
        out.append("")
        out.append("**FLAGS RAISED — investigate before trusting these rankings:**")
        out.append("")
        for f in all_flags:
            out.append(f"- {f}")
    else:
        out.append("")
        out.append("No absurd rankings detected (no non-elite team atop a covered set, "
                   "no elite nation sunk to the bottom). Clean.")
    out.append("")

    label = {"wc2026": "WC-2026 (the 48-team model field)",
             "wc2022": "WC-2022 (32 teams)",
             "euro2024": "Euro-2024 (24 teams)"}
    for tkey in ("wc2026", "wc2022", "euro2024"):
        if tkey not in tournaments:
            continue
        t = tournaments[tkey]
        pt = t["per_tournament"]
        out.append(f"## {label.get(tkey, tkey)}")
        out.append("")
        out.append(
            f"**Coverage:** {pt['n_teams']} teams, **{pt['n_has_squad']} with "
            f"`has_squad=1`**, mean player-match {_fmt_pct(pt['mean_match_pct'])}."
        )
        out.append("")
        out.append("### Per-confederation coverage")
        out.append("")
        out.append(_coverage_table(t["per_confederation"]))
        out.append("")
        if tkey == "wc2026":
            out.append(
                "_The accepted-limits evidence (spec §0/§5): clubelo.com covers European "
                "club leagues densely and non-European leagues sparsely, so coverage tracks "
                "confederation — UEFA is near-complete while AFC / CONCACAF / OFC and the "
                "domestic-league CAF & CONMEBOL sides fall thin. This is **not** missing-at-"
                "random: coverage correlates with strength, so masked teams keep their "
                "pure-Elo anchor (squad_z×has_squad=0) rather than receiving an imputed "
                "average squad that would spuriously inflate weak all-domestic sides._"
            )
            out.append("")
            out.append("### 2026 `squad_z` — top 10 / bottom 5 (covered teams)")
            out.append("")
            out.append(_zscore_table(t["squad_z"], t["has_squad"], top_n=10, bottom_n=5,
                                     covered_only=True))
        else:
            out.append(f"### {tkey} `squad_z` (covered teams)")
            out.append("")
            out.append(_zscore_table(t["squad_z"], t["has_squad"], covered_only=True))
        out.append("")
        # Gapped teams.
        gaps = t.get("gaps", {})
        out.append(f"### Masked / gapped teams ({len(gaps)})")
        out.append("")
        if gaps:
            for team in sorted(gaps):
                out.append(f"- **{team}** — {gaps[team]}")
        else:
            out.append("- (none — every team cleared the `has_squad` threshold)")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "_Generated offline by `scripts/build_squad_z.py` (no network, no store, no fit). "
        "Inputs: `config/squads/{wc2026,wc2022,euro2024}.csv`, "
        "`config/squads/clubelo_{20260610,20221120,20240614}.csv`, "
        "`config/squads/club_aliases.csv`, `src/wcmodel/data/ref/confederations.csv`. "
        "The `k_squad` model wiring + sweep is a separate later step gated on this data._"
    )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Entry point (offline; reads committed CSVs, writes the report).               #
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    as_of = (argv or sys.argv[1:] or [date.today().isoformat()])[0]
    aliases = load_aliases()
    confed = load_confederations()

    tournaments: dict[str, dict] = {}
    for tkey, snapshot in _TOURNAMENTS.items():
        squad = load_squad(f"{tkey}.csv")
        elo = load_elo_table(snapshot)
        tournaments[tkey] = build_tournament(squad, elo, aliases, confed)

    md = assemble_report(tournaments, alias_map_size=len(aliases), as_of=as_of)
    out_path = _REPO / "reports" / f"squad_z_{as_of}.md"
    out_path.write_text(md)

    # Console summary for the operator.
    print(f"[build_squad_z] wrote {out_path.relative_to(_REPO)}")
    for tkey, t in tournaments.items():
        pt = t["per_tournament"]
        print(f"  {tkey}: {pt['n_has_squad']}/{pt['n_teams']} has_squad=1, "
              f"mean match {pt['mean_match_pct']:.1f}%, "
              f"{len(t['flags'])} sanity flag(s)")
        for f in t["flags"]:
            print(f"    ! {f}")
    print(f"  alias-map size: {len(aliases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
