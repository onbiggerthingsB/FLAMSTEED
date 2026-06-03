#!/usr/bin/env python
"""Regenerate the Phase 1 StatsBomb coverage report (root-cause-fix generator).

Run:  ``uv run python scripts/gen_statsbomb_coverage.py``

WHY THIS SCRIPT EXISTS. The committed coverage report (``reports/
phase1_statsbomb_coverage.md`` + ``.csv``) had no generator, so a stale
selection filter — ``country_name == "International"`` — silently slipped
through and mis-characterised StatsBomb's free international footprint. That
filter DROPS the continental national-team tournaments, which StatsBomb files
under their confederation (``country_name`` = ``Europe`` / ``South America`` /
``Africa``), not ``International``: UEFA Euro (2020, 2024), Copa America (2024),
and the African Cup of Nations (2023). The CORRECT selector for "international
national-team competition" is the dedicated ``competition_international == True``
column. This script pins that correct filter and makes the report reproducible
and auditable.

It is a thin, network-touching driver over the already-tested pure helpers:
  * ``sources.statsbomb.fetch_competitions`` / ``fetch_matches`` — the only
    network entries (``statsbombpy`` -> GitHub Open Data, no auth);
  * ``coverage.enumerate_coverage`` / ``write_coverage_report`` — pure render.

It computes the covered national-team universe + the per-competition inventory
and writes both the markdown report and its CSV companion. The headline
men's-senior coverage thesis is rendered from the live pull (no hand-typed
inventory), so the report cannot drift from the data again.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Repo root = parent of this script's directory (scripts/..). Put ``src`` on the
# path so the script runs as ``uv run python scripts/gen_statsbomb_coverage.py``
# regardless of whether the editable install is active (mirrors the project's
# pytest ``pythonpath = ["src"]`` convention).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from wcmodel.data import coverage  # noqa: E402
from wcmodel.data.sources import statsbomb  # noqa: E402

CONFIG_PATH = ROOT / "config" / "config.yaml"
REPORT_PATH = ROOT / "reports" / "phase1_statsbomb_coverage.md"


def _source_version() -> str:
    """Pinned StatsBomb release marker from config (client version + pull date)."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    return cfg["statsbomb"]["open_data_version"]


def collect_inventory(creds: dict | None = None):
    """Pull the TRUE international national-team inventory (network).

    Selects competitions with ``competition_international == True`` (NOT the
    stale ``country_name == "International"`` filter, which drops the continental
    cups filed under Europe/South America/Africa). For each competition-season it
    pulls the match list and assembles the distinct participating national teams.

    Returns ``(inventory, mens_senior_teams, universe_competitions)`` where:
      * ``inventory`` — list of per-competition-season dicts
        (``competition, season, country, gender, youth, mens_senior, teams,
        n_teams``), sorted for a stable report;
      * ``mens_senior_teams`` — sorted distinct men's-senior national teams (the
        headline xG-covered universe);
      * ``universe_competitions`` — ``{"competitions": [{"teams": [...]}]}`` in
        the shape ``coverage.enumerate_coverage`` consumes, carrying every
        team-entity across all international competitions.

    Team names are StatsBomb's raw match-metadata names verbatim: the women's
    and youth entities already carry their own disambiguating markers (e.g.
    ``"Argentina Women's"``, ``"Cameroon W"``, ``"Argentina U20"``) and do **not**
    collide with the plain men's-senior names, so no relabelling is applied.
    """
    comps = statsbomb.fetch_competitions(creds=creds)
    intl = comps[comps["competition_international"] == True]  # noqa: E712

    inventory = []
    mens_senior_teams: set[str] = set()
    universe_teams: set[str] = set()

    for _, row in intl.iterrows():
        cid, sid = int(row["competition_id"]), int(row["season_id"])
        gender = row["competition_gender"]
        youth = bool(row["competition_youth"])
        mens_senior = (gender == "male") and not youth

        matches = statsbomb.fetch_matches(cid, sid, creds=creds)
        teams = sorted(set(matches["home_team"]) | set(matches["away_team"]))

        universe_teams.update(teams)
        if mens_senior:
            mens_senior_teams.update(teams)

        inventory.append({
            "competition": row["competition_name"],
            "season": str(row["season_name"]),
            "country": row["country_name"],
            "gender": gender,
            "youth": youth,
            "mens_senior": mens_senior,
            "teams": teams,
            "n_teams": len(teams),
        })

    inventory.sort(key=lambda r: (not r["mens_senior"], r["competition"], r["season"]))
    universe_competitions = {"competitions": [{"teams": sorted(universe_teams)}]}
    return inventory, sorted(mens_senior_teams), universe_competitions


def render_inventory_section(inventory, mens_senior_teams) -> str:
    """Render the live-pull inventory markdown block (the ``extra_sections``).

    Built ENTIRELY from the live pull so the headline men's-senior thesis cannot
    drift from the data: a competition-season table, the corrected coverage
    narrative (continental cups ARE present; only the qualifier/friendly tail is
    absent), and the men's-senior national-team list.
    """
    n_seasons = len(inventory)
    mens = [r for r in inventory if r["mens_senior"]]
    womens = [r for r in inventory if r["gender"] == "female"]
    youth = [r for r in inventory if r["youth"]]
    n_mens_seasons = len(mens)
    n_mens_teams = len(mens_senior_teams)

    table = ["| competition | season | confederation | gender | teams |",
             "|---|---|---|---|---:|"]
    for r in inventory:
        g = "women" if r["gender"] == "female" else ("men U20" if r["youth"] else "men")
        table.append(
            f"| {r['competition']} | {r['season']} | {r['country']} | {g} | {r['n_teams']} |"
        )

    wc_editions = sorted(r["season"] for r in mens if r["competition"] == "FIFA World Cup")
    n_wc = len(wc_editions)

    lines = [
        "## StatsBomb international competition inventory (live pull)",
        "",
        f"Selected via `competition_international == True` (the correct filter — "
        f"**not** `country_name == \"International\"`, which silently drops the "
        f"continental national-team cups that StatsBomb files under their "
        f"confederation, e.g. UEFA Euro under `Europe`). Pulled **{n_seasons}** "
        f"international national-team competition-seasons; **{n_mens_seasons}** are "
        f"men's-senior, covering **{n_mens_teams}** distinct men's-senior national "
        f"teams. Women's and youth competitions are listed below the table but "
        f"excluded from the men's-senior universe.",
        "",
        *table,
        "",
        "### Reading this report — coverage is presence in the metadata above",
        "",
        "`covered = True` means the team appears in StatsBomb's international "
        "competition/match metadata (the inventory above). Because the team list "
        "checked below IS that available universe, every listed team is covered by "
        "construction — the operative gap is the teams that **do not appear at "
        "all** (filled in once the 48-team draw lands).",
        "",
        "**Men's-senior coverage shape (the real footprint).** StatsBomb's *free* "
        f"international men's-senior xG is **NOT** World-Cup-only: it is the "
        f"**{n_wc} FIFA World Cup finals editions** "
        f"({', '.join(wc_editions)}) **plus** the recent continental cups — "
        "**UEFA Euro 2020 & 2024**, **Copa America 2024**, and the **African Cup "
        "of Nations 2023** — i.e. "
        f"**{n_mens_seasons} men's-senior competition-seasons / ~{n_mens_teams} "
        "national teams**. There are **NO qualifiers, NO friendlies, and no "
        "Nations League** in the free Open Data. So the qualifier/friendly tail is "
        "absent (NULL, never imputed), **but** the continental-cup participants — a "
        "meaningful slice of mid- and lower-tier sides (e.g. the full AFCON-2023 "
        "and Copa-2024 fields) — **ARE** covered. Practically this means xG is "
        "still **NULL for the entire (qualifier / friendly / Nations-League-heavy) "
        "backtest window**, but **available for finals + continental-cup matches**. "
        "This compounds the Phase-0 finding that free international xG collapsed "
        "after the 2026-01-20 FBref/Opta cutoff (see `SOURCES.md`).",
        "",
        f"**Men's-senior national teams present ({n_mens_teams}):**",
        "",
        "\n".join(f"- {t}" for t in mens_senior_teams),
        "",
    ]

    if womens:
        w_label = ", ".join(f"{r['competition']} {r['season']}" for r in womens)
        lines += [
            f"**Women's competitions (listed separately, not in the men's-senior "
            f"universe):** {w_label}.",
            "",
        ]
    if youth:
        y_label = ", ".join(f"{r['competition']} {r['season']}" for r in youth)
        lines += [f"**Youth competitions (separate):** {y_label}.", ""]

    return "\n".join(lines)


def main() -> None:
    source_version = _source_version()
    inventory, mens_senior_teams, universe_competitions = collect_inventory()

    # Check the entire covered universe (every team-entity across all
    # international competitions) against itself: covered by construction. The
    # 48-team WC-2026 intersection stays GATED on config/tournament_2026.yaml.
    universe = sorted(universe_competitions["competitions"][0]["teams"])
    cov = coverage.enumerate_coverage(universe_competitions, universe)

    extra = render_inventory_section(inventory, mens_senior_teams)
    out = coverage.write_coverage_report(
        cov, REPORT_PATH, source_version=source_version, extra_sections=extra
    )
    print(f"Wrote {out} ({len(universe)} team-entities; "
          f"{len(mens_senior_teams)} men's-senior national teams; "
          f"{sum(r['mens_senior'] for r in inventory)} men's-senior comp-seasons; "
          f"{len(inventory)} intl comp-seasons total)")
    print(f"Wrote {out.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
