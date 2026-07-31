"""Orchestration + report-assembly tests for ``scripts/sweep_altitude.py`` (P2a gate).

The script is THIN: a pure CONMEBOL-qualifier slice selector, a per-fixture covariate
builder, a pure ``assemble_report``, and a pure ``_verdict``. These tests pin the PURE
pieces (slice selection, the markdown shape, the ADOPT/NO-LIFT logic) WITHOUT running a
real fit, plus a source-level grep that pins the zero-Odds-API-credit invariant.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "sweep_altitude.py"


def _load():
    spec = importlib.util.spec_from_file_location("sweep_altitude", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# Zero Odds-API credits (source grep).                                          #
# --------------------------------------------------------------------------- #
def test_no_live_fetch_surface():
    src = _MODULE_PATH.read_text()
    assert "fetch_live_odds" not in src
    assert "odds_live" not in src
    assert "THE_ODDS_API_KEY" not in src
    assert "httpx.get" not in src
    assert "_load_env_key" not in src


# --------------------------------------------------------------------------- #
# CONMEBOL-qualifier slice selector (pure).                                     #
# --------------------------------------------------------------------------- #
def test_conmebol_qualifier_slice_selector(mod):
    # WC-qualifier + both CONMEBOL -> in the slice.
    assert mod.is_conmebol_qualifier(
        {"match_type": "wc_qualifier", "home_team": "Bolivia", "away_team": "Brazil"})
    # WC-qualifier but a non-CONMEBOL team -> NOT in the slice.
    assert not mod.is_conmebol_qualifier(
        {"match_type": "wc_qualifier", "home_team": "Bolivia", "away_team": "Germany"})
    # CONMEBOL pair but NOT a qualifier (e.g. a friendly) -> NOT in the slice.
    assert not mod.is_conmebol_qualifier(
        {"match_type": "friendly", "home_team": "Bolivia", "away_team": "Brazil"})
    # Continental championship (Copa) -> NOT a WC qualifier -> excluded.
    assert not mod.is_conmebol_qualifier(
        {"match_type": "continental_championship", "home_team": "Argentina", "away_team": "Chile"})


# --------------------------------------------------------------------------- #
# Per-fixture covariate builder (pure).                                         #
# --------------------------------------------------------------------------- #
def test_fixture_covariates_per_arm(mod):
    import math
    # OFF arm -> None (baseline, supplies nothing).
    assert mod._fixture_covariates([], "La Paz", "Bolivia", "Brazil") is None
    # accl_alt arm -> per-team home + away gaps off the venue city.
    cov = mod._fixture_covariates(["accl_alt"], "La Paz", "Bolivia", "Brazil")
    assert set(cov) == {"accl_alt", "accl_alt__away"}
    assert abs(cov["accl_alt"]) < 50.0                 # Bolivia at La Paz: acclimatized
    assert abs(cov["accl_alt__away"] - 3640.0) < 50.0  # Brazil at La Paz: full gap
    # altitude_m arm -> per-match single venue altitude.
    cov2 = mod._fixture_covariates(["altitude_m"], "La Paz", "Bolivia", "Brazil")
    assert set(cov2) == {"altitude_m"}
    assert cov2["altitude_m"] > 3000.0
    # Unknown city -> NaN (masked downstream, never imputed).
    cov3 = mod._fixture_covariates(["accl_alt"], "Nowhere-City", "Bolivia", "Brazil")
    assert math.isnan(cov3["accl_alt"]) and math.isnan(cov3["accl_alt__away"])


# --------------------------------------------------------------------------- #
# Verdict logic (pure).                                                         #
#                                                                               #
# Canned RPS values (pre-OA-F16 [0, 2] magnitudes), so these pin the ADOPT /     #
# NO-LIFT BRANCHING only — never the SCALE of `TOL` or `TOO_GOOD`, which is why  #
# they stayed green through the ÷2 rescale that halved every real delta. The     #
# thresholds are pinned through `baselines.rps` in                               #
# `tests/eval/test_rps_scale_consumers.py`; keep both.                           #
# --------------------------------------------------------------------------- #
def _arms(off_con, accl_con, off_all=0.330, accl_all=0.330):
    return [
        {"label": "OFF", "enabled": [], "rps_overall": off_all, "n_overall": 100,
         "rps_conmebol": off_con, "n_conmebol": 20},
        {"label": "accl_alt", "enabled": ["accl_alt"], "rps_overall": accl_all,
         "n_overall": 100, "rps_conmebol": accl_con, "n_conmebol": 20},
        {"label": "altitude_m", "enabled": ["altitude_m"], "rps_overall": 0.331,
         "n_overall": 100, "rps_conmebol": off_con, "n_conmebol": 20},
    ]


def test_verdict_adopt_when_conmebol_improves_and_overall_not_worse(mod):
    v, notes = mod._verdict(_arms(off_con=0.350, accl_con=0.340, accl_all=0.330))
    assert v.startswith("ADOPT")
    assert "enabled: []" in notes  # the phase still leaves it off pending sim threading


def test_verdict_no_lift_when_conmebol_does_not_improve(mod):
    v, _ = mod._verdict(_arms(off_con=0.340, accl_con=0.345))
    assert v.startswith("NO-LIFT")


def test_verdict_no_lift_when_overall_regresses(mod):
    # CONMEBOL improves but overall regresses past tolerance -> NO-LIFT.
    v, _ = mod._verdict(_arms(off_con=0.350, accl_con=0.340, off_all=0.330, accl_all=0.340))
    assert v.startswith("NO-LIFT")


def test_verdict_too_good_flags_audit(mod):
    v, notes = mod._verdict(_arms(off_con=0.400, accl_con=0.300))  # Δ = -0.10, absurd
    assert v.startswith("ADOPT")
    assert "TOO-GOOD" in notes


# --------------------------------------------------------------------------- #
# Report assembler (pure).                                                      #
# --------------------------------------------------------------------------- #
def test_report_has_tables_coverage_and_verdict(mod):
    part = {
        "arms": _arms(off_con=0.350, accl_con=0.340),
        "n_overall": 100, "n_conmebol": 20, "coverage_pct": 87.5,
        "verdict": "ADOPT (CONMEBOL-q RPS improves, overall does not regress)",
        "notes": "accl_alt improves the slice.",
    }
    md = mod.assemble_report(part, cutoff="2024-06-01T00:00:00Z", today="2026-06-10")
    assert "Held-out RPS Gate" in md
    assert "CONMEBOL-q RPS" in md         # the paired table header
    assert "87.5%" in md                  # coverage stated
    assert "ADOPT" in md                  # the verdict line
    assert "accl_alt" in md and "altitude_m" in md   # both candidate arms in the table
