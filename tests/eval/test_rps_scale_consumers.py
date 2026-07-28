"""Decision gates fire on the CANONICAL RPS scale (OA finding 16 — review fix).

``test_rps_canonical.py`` pins the PRODUCERS: every RPS adapter delegates to
``wcmodel.model.calibration.rps``. This file pins the CONSUMERS: every gate whose
constant is an absolute RPS LEVEL or an absolute RPS DIFFERENCE must trip on the
same true forecast difference it tripped on before the ÷2 rescale.

The rescale preserves sign, ordering and ratios but HALVES every difference
(Δ_new = Δ_old / 2), so a gate left on the pre-F16 constants silently needs TWICE
the true effect to fire — the failure mode that hit all three gates below, two of
them leakage tripwires.

Every RPS here is produced by ``baselines.rps`` over hand-checkable 1X2 forecasts,
never a canned RPS number: canned inputs are precisely why the existing gate tests
could not see the breaks. With ``outcome = home`` the canonical score is
``((1 - h)**2 + a**2) / 2``, so a pair sharing ``a`` has an exact decimal delta
``((1 - h_x)**2 - (1 - h_y)**2) / 2`` — quoted beside each fixture below.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from wcmodel.backtest.baselines import rps as baselines_rps
from wcmodel.backtest.headroom import bootstrap_delta_ci, paired_rps

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, str(_SCRIPTS / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rps(triple) -> float:
    """Score an ``(h, d, a)`` forecast on a HOME result through the pipeline's scorer."""
    h, d, a = triple
    return baselines_rps({"home": h, "draw": d, "away": a}, "home")


def _delta(model, ref) -> float:
    return _rps(model) - _rps(ref)


# --------------------------------------------------------------------------- #
# Gate G1 — scripts/model_market_gap.py: the headroom diagnostic's Phase-2 vs    #
# Phase-3 recommendation, keyed on the aggregate model-minus-market RPS gap.     #
# --------------------------------------------------------------------------- #
#                    model                market            canonical Δ
G1_MATERIAL = ((0.69, 0.22, 0.09), (0.71, 0.20, 0.09))   # +0.0060
G1_GREY = ((0.79, 0.12, 0.09), (0.81, 0.10, 0.09))       # +0.0040
G1_NEAR_CEILING = ((0.89, 0.06, 0.05), (0.91, 0.04, 0.05))  # +0.0020


def _part_a(model, market) -> dict:
    """A Part-A payload whose aggregate comes from ``headroom.paired_rps`` — i.e.
    through ``baselines.rps``, exactly as ``run_part_a`` builds it."""
    rows = [{"p_model": model, "p_ref": market, "outcome": "H"}]
    agg = paired_rps(rows)
    ci = bootstrap_delta_ci(rows, n_boot=100, seed=0)
    return {"n": agg["n"], "clusters": [], "per_match": [],
            "aggregate": {**agg, "lo95": ci["lo95"], "hi95": ci["hi95"]}}


@pytest.fixture
def gap_mod():
    return _load_script("model_market_gap")


@pytest.mark.parametrize("pair,expected", [
    (G1_MATERIAL, 0.0060),
    (G1_GREY, 0.0040),
    (G1_NEAR_CEILING, 0.0020),
])
def test_g1_fixtures_are_on_the_canonical_scale(pair, expected):
    """Guards the guard: if ``baselines.rps`` ever reverts to [0, 2] these fixtures
    carry twice the intended gap and the branch assertions below become vacuous."""
    model, market = pair
    assert _delta(model, market) == pytest.approx(expected, abs=1e-12)


def test_g1_material_headroom_recommends_phase_3(gap_mod):
    # A +0.0060 canonical gap is the pre-F16 +0.012 — the brief's "material
    # headroom to the sharp close" case, which must reach Phase 3.
    md = gap_mod.assemble_report(_part_a(*G1_MATERIAL), None, today="2026-07-28")
    assert "**Phase 3 is a priority.**" in md


def test_g1_grey_band_recommends_phase_2_first_and_reassess(gap_mod):
    # +0.0040 canonical = pre-F16 +0.008: modest headroom, Phase 2 first — but NOT
    # the "already at the ceiling, do NOT prioritise Phase 3" verdict.
    md = gap_mod.assemble_report(_part_a(*G1_GREY), None, today="2026-07-28")
    assert "grey band" in md
    assert "do NOT prioritise Phase 3" not in md


def test_g1_near_ceiling_recommends_phase_2_only(gap_mod):
    # +0.0020 canonical = pre-F16 +0.004: below the small threshold — the model is
    # already near the de-vigged sharp ceiling.
    md = gap_mod.assemble_report(_part_a(*G1_NEAR_CEILING), None, today="2026-07-28")
    assert "do NOT prioritise Phase 3" in md


# --------------------------------------------------------------------------- #
# Gate P2a — scripts/sweep_altitude.py: the altitude arm's ADOPT/NO-LIFT gate,   #
# its overall-no-regression tolerance and its TOO-GOOD leakage tripwire.         #
# --------------------------------------------------------------------------- #
ALT_OFF_CON = (0.68, 0.24, 0.08)          # OFF   CONMEBOL-q slice
ALT_CON_ABSURD = (0.72, 0.20, 0.08)       # Δ = -0.0120 — absurd, must flag TOO-GOOD
ALT_CON_PLAUSIBLE_OFF = (0.59, 0.33, 0.08)
ALT_CON_PLAUSIBLE = (0.61, 0.31, 0.08)    # Δ = -0.0080 — large but believable
ALT_ALL_FLAT = (0.70, 0.21, 0.09)         # same arm both sides -> Δ = 0
ALT_ALL_OFF_TIGHT = (0.75005, 0.15995, 0.09)
ALT_ALL_TIGHT = (0.74995, 0.16005, 0.09)  # Δ = +2.5e-5 — inside MC-noise tolerance
ALT_ALL_OFF_LOOSE = (0.700125, 0.209875, 0.09)
ALT_ALL_LOOSE = (0.699875, 0.210125, 0.09)  # Δ = +7.5e-5 — a real overall regression


@pytest.fixture
def alt_mod():
    return _load_script("sweep_altitude")


def _arms(*, off_all, accl_all, off_con, accl_con) -> list[dict]:
    return [
        {"label": "OFF", "enabled": [], "n_overall": 100, "n_conmebol": 20,
         "rps_overall": _rps(off_all), "rps_conmebol": _rps(off_con)},
        {"label": "accl_alt", "enabled": ["accl_alt"], "n_overall": 100,
         "n_conmebol": 20,
         "rps_overall": _rps(accl_all), "rps_conmebol": _rps(accl_con)},
    ]


@pytest.mark.parametrize("pair,expected", [
    ((ALT_CON_ABSURD, ALT_OFF_CON), -0.0120),
    ((ALT_CON_PLAUSIBLE, ALT_CON_PLAUSIBLE_OFF), -0.0080),
    ((ALT_ALL_TIGHT, ALT_ALL_OFF_TIGHT), 2.5e-5),
    ((ALT_ALL_LOOSE, ALT_ALL_OFF_LOOSE), 7.5e-5),
])
def test_altitude_fixtures_are_on_the_canonical_scale(pair, expected):
    arm, off = pair
    assert _delta(arm, off) == pytest.approx(expected, abs=1e-12)


def test_altitude_too_good_tripwire_fires_on_canonical_improvement(alt_mod):
    # -0.0120 canonical = pre-F16 -0.024: past the "audit for leakage" line. This
    # is a LEAKAGE detector — needing 2x the true effect to fire is the expensive
    # direction to be wrong in.
    v, notes = alt_mod._verdict(_arms(off_all=ALT_ALL_FLAT, accl_all=ALT_ALL_FLAT,
                                      off_con=ALT_OFF_CON, accl_con=ALT_CON_ABSURD))
    assert v.startswith("ADOPT")
    assert "TOO-GOOD" in notes


def test_altitude_too_good_tripwire_silent_on_believable_improvement(alt_mod):
    # -0.0080 canonical = pre-F16 -0.016: big, but inside what the gate has always
    # accepted without an audit. Pins the tripwire from below.
    v, notes = alt_mod._verdict(_arms(off_all=ALT_ALL_FLAT, accl_all=ALT_ALL_FLAT,
                                      off_con=ALT_CON_PLAUSIBLE_OFF,
                                      accl_con=ALT_CON_PLAUSIBLE))
    assert v.startswith("ADOPT")
    assert "TOO-GOOD" not in notes


def test_altitude_adopts_when_overall_regression_is_inside_mc_noise(alt_mod):
    v, _ = alt_mod._verdict(_arms(off_all=ALT_ALL_OFF_TIGHT, accl_all=ALT_ALL_TIGHT,
                                  off_con=ALT_OFF_CON, accl_con=ALT_CON_ABSURD))
    assert v.startswith("ADOPT")


def test_altitude_no_lift_when_overall_regression_exceeds_mc_noise(alt_mod):
    # +7.5e-5 canonical = pre-F16 +1.5e-4: a regression the gate used to REJECT.
    v, _ = alt_mod._verdict(_arms(off_all=ALT_ALL_OFF_LOOSE, accl_all=ALT_ALL_LOOSE,
                                  off_con=ALT_OFF_CON, accl_con=ALT_CON_ABSURD))
    assert v.startswith("NO-LIFT")


# --------------------------------------------------------------------------- #
# Gate CLV — scripts/clv_validation.py: "the de-vigged close is the accuracy     #
# ceiling", the repo's headline leakage detector on the accuracy path.           #
# --------------------------------------------------------------------------- #
CLV_MARKET_RED = (0.65, 0.27, 0.08)
CLV_MODEL_RED = (0.75, 0.17, 0.08)        # gap = -0.0300 — implausibly past the ceiling
CLV_MARKET_OK = (0.575, 0.345, 0.08)
CLV_MODEL_OK = (0.625, 0.295, 0.08)       # gap = -0.0200 — beats the close, not absurdly


@pytest.fixture
def clv_mod():
    return _load_script("clv_validation")


@pytest.mark.parametrize("pair,expected", [
    ((CLV_MODEL_RED, CLV_MARKET_RED), -0.0300),
    ((CLV_MODEL_OK, CLV_MARKET_OK), -0.0200),
])
def test_clv_fixtures_are_on_the_canonical_scale(pair, expected):
    model, market = pair
    assert _delta(model, market) == pytest.approx(expected, abs=1e-12)


def test_clv_red_fires_when_model_materially_beats_the_ceiling(clv_mod):
    # -0.0300 canonical = pre-F16 -0.060: a SUSPECTED BUG (leakage / de-vig error /
    # result-peek), never a win. n > 8 so the tiny-sample AMBER cannot mask a miss.
    line = clv_mod._adversarial_verdict(_rps(CLV_MODEL_RED), _rps(CLV_MARKET_RED), 20)
    assert "[RED]" in line
    assert "SUSPECTED BUG" in line


def test_clv_red_silent_when_the_beat_is_inside_plausibility(clv_mod):
    # -0.0200 canonical = pre-F16 -0.040: below the RED line both before and after
    # the rescale. Pins the threshold from below.
    line = clv_mod._adversarial_verdict(_rps(CLV_MODEL_OK), _rps(CLV_MARKET_OK), 20)
    assert "[RED]" not in line


def test_clv_near_perfect_rps_is_always_red(clv_mod):
    # The companion level guard: a mean RPS of ~0 is a result peeking into the model
    # whatever the market did.
    line = clv_mod._adversarial_verdict(1e-9, 0.06, 20)
    assert "[RED]" in line
    assert "peeking" in line
