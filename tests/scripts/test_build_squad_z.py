"""Orchestration tests for ``scripts/build_squad_z.py`` (P3 v0).

The script is OFFLINE + READ-ONLY (reads only the committed CSVs under
``config/squads/``). These pin the PURE pieces WITHOUT any network / store / fit:

- the no-live-fetch source grep (zero Odds-API credits, no run-time clubelo fetch),
- the per-confederation coverage aggregator on hand-built dicts,
- the report assembler (markdown shape) on hand-built dicts,
- the sanity-tripwire flagger (a fabricated minnow-on-top input trips it).

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``), the
``sweep_altitude`` precedent.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_squad_z.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_squad_z", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# Zero credits / no run-time network (source grep).                             #
# --------------------------------------------------------------------------- #
def test_no_live_fetch_surface():
    src = _MODULE_PATH.read_text()
    # No Odds-API.
    assert "fetch_live_odds" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "odds_live" not in src
    # No run-time clubelo / generic HTTP fetch (snapshots are committed CSVs).
    assert "api.clubelo.com" not in src
    assert "httpx" not in src
    assert "requests.get" not in src
    assert "urllib" not in src


# --------------------------------------------------------------------------- #
# Per-confederation coverage aggregator.                                        #
# --------------------------------------------------------------------------- #
def test_per_confederation_coverage_aggregates(mod):
    # Two UEFA teams (one fully covered, one thin) + one CAF team (uncovered).
    per_team = {
        "France": {"confederation": "UEFA", "n_squad": 23, "n_matched": 23, "has_squad": 1},
        "Scotland": {"confederation": "UEFA", "n_squad": 23, "n_matched": 12, "has_squad": 1},
        "Ghana": {"confederation": "CAF", "n_squad": 23, "n_matched": 5, "has_squad": 0},
    }
    agg = mod.per_confederation_coverage(per_team)
    uefa = agg["UEFA"]
    assert uefa["n_teams"] == 2
    assert uefa["n_has_squad"] == 2
    # mean player-match % = mean(23/23, 12/23) = mean(100, 52.17) ~ 76.09
    assert abs(uefa["mean_match_pct"] - ((100.0 + 12 / 23 * 100) / 2)) < 1e-6
    caf = agg["CAF"]
    assert caf["n_teams"] == 1
    assert caf["n_has_squad"] == 0
    assert abs(caf["mean_match_pct"] - (5 / 23 * 100)) < 1e-6


def test_per_confederation_handles_zero_squad_team(mod):
    # A coverage-gap team with n_squad=0 must not divide-by-zero.
    per_team = {
        "Curacao": {"confederation": "CONCACAF", "n_squad": 0, "n_matched": 0, "has_squad": 0},
    }
    agg = mod.per_confederation_coverage(per_team)
    assert agg["CONCACAF"]["n_teams"] == 1
    assert agg["CONCACAF"]["n_has_squad"] == 0
    assert agg["CONCACAF"]["mean_match_pct"] == 0.0


# --------------------------------------------------------------------------- #
# Sanity tripwire (binding rule 2: too-good = bug).                             #
# --------------------------------------------------------------------------- #
def test_sanity_tripwire_flags_minnow_on_top(mod):
    # A fabricated ranking with a minnow (not in the elite set) ranked #1 trips it.
    squad_z = {"San Marino": 2.5, "France": 1.0, "England": 0.5, "Spain": 0.2, "Brazil": 0.1}
    flags = mod.flag_sanity(squad_z, top_k=3)
    assert flags  # non-empty -> tripped
    assert any("San Marino" in f for f in flags)


def test_sanity_tripwire_silent_on_plausible_ranking(mod):
    # An elite nation on top -> no flag.
    squad_z = {"France": 2.0, "Spain": 1.5, "England": 1.2, "Brazil": 1.0, "Ghana": -0.5}
    flags = mod.flag_sanity(squad_z, top_k=3)
    assert flags == []


# --------------------------------------------------------------------------- #
# Report assembler (markdown shape).                                            #
# --------------------------------------------------------------------------- #
def test_assemble_report_markdown_shape(mod):
    tournaments = {
        "wc2026": {
            "per_tournament": {"n_teams": 2, "n_has_squad": 1, "mean_match_pct": 75.0},
            "per_confederation": {
                "UEFA": {"n_teams": 1, "n_has_squad": 1, "mean_match_pct": 100.0},
                "CAF": {"n_teams": 1, "n_has_squad": 0, "mean_match_pct": 50.0},
            },
            "squad_z": {"France": 1.0, "Ghana": 0.0},
            "has_squad": {"France": 1, "Ghana": 0},
            "gaps": {"Ghana": "thin coverage (5 matched < 11)"},
            "flags": [],
        },
        "wc2022": {
            "per_tournament": {"n_teams": 1, "n_has_squad": 1, "mean_match_pct": 90.0},
            "per_confederation": {"UEFA": {"n_teams": 1, "n_has_squad": 1, "mean_match_pct": 90.0}},
            "squad_z": {"France": 0.0},
            "has_squad": {"France": 1},
            "gaps": {},
            "flags": [],
        },
        "euro2024": {
            "per_tournament": {"n_teams": 1, "n_has_squad": 1, "mean_match_pct": 95.0},
            "per_confederation": {"UEFA": {"n_teams": 1, "n_has_squad": 1, "mean_match_pct": 95.0}},
            "squad_z": {"France": 0.0},
            "has_squad": {"France": 1},
            "gaps": {},
            "flags": [],
        },
    }
    md = mod.assemble_report(tournaments, alias_map_size=42, as_of="2026-06-11")
    assert md.startswith("# ")
    # Per-confederation table present.
    assert "Confederation" in md
    assert "UEFA" in md and "CAF" in md
    # squad_z ranking present.
    assert "France" in md
    # alias-map footprint reported.
    assert "42" in md
    # gapped-team list present with the reason.
    assert "Ghana" in md and "thin coverage" in md


def test_assemble_report_surfaces_sanity_flags(mod):
    tournaments = {
        "wc2026": {
            "per_tournament": {"n_teams": 1, "n_has_squad": 1, "mean_match_pct": 100.0},
            "per_confederation": {"OFC": {"n_teams": 1, "n_has_squad": 1, "mean_match_pct": 100.0}},
            "squad_z": {"New Zealand": 3.0},
            "has_squad": {"New Zealand": 1},
            "gaps": {},
            "flags": ["SUSPECTED JOIN BUG: New Zealand atop squad_z"],
        },
    }
    md = mod.assemble_report(tournaments, alias_map_size=0, as_of="2026-06-11")
    assert "SUSPECTED JOIN BUG" in md
