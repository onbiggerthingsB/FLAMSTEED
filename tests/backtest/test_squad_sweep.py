"""P3 v0 — pure sweep-decision helpers (the two pre-registered gates, mechanical).

``wcmodel.backtest.squad_sweep`` holds the value-in/value-out decision logic the
sweep script orchestrates (prereg §3-§4):

  * ``paired_bootstrap_delta(per_match_a, per_match_b, seed, n_boot)`` — the
    seeded PAIRED bootstrap CI of mean(b) − mean(a) over MATCHED per-match RPS
    arrays (same matches, paired resample of the match index). Returns
    ``{delta, lo95, hi95}``. Deterministic for a fixed seed.

  * ``knee_index(rps_by_k)`` — the knee of an RPS-vs-k curve = argmin RPS (lower
    RPS is the better forecast); ties resolve to the SMALLEST k (least anchoring).

  * ``evaluate_gates(cells, *, seed, n_boot)`` — given the per-k cells (each with
    k, overall per-match RPS array, has_squad=0-slice per-match RPS array), apply:
      G1 knee-beats-zero: the chosen k is the knee AND its overall RPS strictly
         beats k=0 (paired-bootstrap delta vs k=0 has hi95 < 0).
      G2 slice non-regression: the chosen k's has_squad=0-slice RPS does NOT
         regress vs k=0 beyond noise. The prereg fixes NO numeric tolerance, so
         (as the prereg directs) we use paired-bootstrap CI OVERLAP: the slice
         delta(chosen − k0) lo95 must be <= 0 (its CI must include / sit at-or-
         below 0 — i.e. not a CI strictly above 0).
    Returns a verdict dict: ADOPT k=<knee> if both gates pass, else NO-LIFT.
"""
import numpy as np
import pytest

from wcmodel.backtest.squad_sweep import (
    evaluate_gates,
    knee_index,
    paired_bootstrap_delta,
)


# --------------------------------------------------------------------------- #
# paired_bootstrap_delta                                                       #
# --------------------------------------------------------------------------- #
def test_paired_delta_point_estimate_is_mean_difference():
    a = [0.40, 0.35, 0.50, 0.30]
    b = [0.30, 0.30, 0.45, 0.20]            # b uniformly lower
    out = paired_bootstrap_delta(a, b, seed=0, n_boot=500)
    assert abs(out["delta"] - (np.mean(b) - np.mean(a))) < 1e-12
    assert out["hi95"] < 0.0                # b clearly better -> CI below 0


def test_paired_delta_is_deterministic_for_seed():
    a = list(np.linspace(0.2, 0.6, 30))
    b = [x - 0.02 for x in a]
    o1 = paired_bootstrap_delta(a, b, seed=7, n_boot=400)
    o2 = paired_bootstrap_delta(a, b, seed=7, n_boot=400)
    assert o1 == o2


def test_paired_delta_zero_difference_ci_spans_zero():
    a = [0.40, 0.35, 0.50, 0.30, 0.45, 0.33]
    out = paired_bootstrap_delta(a, list(a), seed=1, n_boot=300)
    assert out["delta"] == 0.0
    assert out["lo95"] <= 0.0 <= out["hi95"]


def test_paired_delta_empty_is_nan():
    out = paired_bootstrap_delta([], [], seed=0, n_boot=10)
    assert np.isnan(out["delta"])


# --------------------------------------------------------------------------- #
# knee_index                                                                   #
# --------------------------------------------------------------------------- #
def test_knee_is_argmin_rps():
    # k=0:0.36, 0.2:0.34, 0.4:0.333, 0.6:0.34  -> knee at k=0.4 (index 2)
    assert knee_index([0.36, 0.34, 0.333, 0.34]) == 2


def test_knee_ties_resolve_to_smallest_k():
    # two equal minima -> the earlier (smaller-k) index wins (least anchoring)
    assert knee_index([0.34, 0.333, 0.333, 0.35]) == 1


def test_knee_monotone_decreasing_picks_edge():
    assert knee_index([0.36, 0.35, 0.34, 0.33]) == 3


# --------------------------------------------------------------------------- #
# evaluate_gates — the mechanical verdict                                      #
# --------------------------------------------------------------------------- #
def _cell(k, overall, slice_):
    return {"k": k, "overall_rps": list(overall), "slice_rps": list(slice_)}


def test_adopt_when_knee_beats_zero_and_slice_not_regressed():
    rng = np.random.default_rng(0)
    n = 200
    base = rng.uniform(0.2, 0.6, n)
    # k=0 overall is `base`; k=0.4 is uniformly better by 0.03 (knee + beats 0).
    cells = [
        _cell(0.0, base, base[:40]),
        _cell(0.2, base - 0.01, base[:40] - 0.005),
        _cell(0.4, base - 0.03, base[:40] - 0.002),   # knee, beats 0, slice better too
        _cell(0.6, base - 0.02, base[:40] - 0.001),
    ]
    v = evaluate_gates(cells, seed=0, n_boot=400)
    assert v["verdict"] == "ADOPT"
    assert v["k"] == 0.4
    assert v["g1_pass"] is True and v["g2_pass"] is True


def test_no_lift_when_knee_is_zero():
    rng = np.random.default_rng(1)
    n = 150
    base = rng.uniform(0.2, 0.6, n)
    # every k>0 is WORSE -> knee is k=0 -> cannot beat itself -> NO-LIFT.
    cells = [
        _cell(0.0, base, base[:30]),
        _cell(0.2, base + 0.02, base[:30] + 0.01),
        _cell(0.4, base + 0.03, base[:30] + 0.01),
        _cell(0.6, base + 0.04, base[:30] + 0.02),
    ]
    v = evaluate_gates(cells, seed=0, n_boot=300)
    assert v["verdict"] == "NO-LIFT"
    assert v["g1_pass"] is False


def test_no_lift_when_slice_regresses_even_if_overall_better():
    rng = np.random.default_rng(2)
    n = 200
    base = rng.uniform(0.2, 0.6, n)
    sl = rng.uniform(0.2, 0.6, 50)
    # overall better at k=0.4 (G1 ok), but the has_squad=0 slice is MUCH worse
    # (CI strictly above 0) -> G2 fails -> NO-LIFT.
    cells = [
        _cell(0.0, base, sl),
        _cell(0.2, base - 0.01, sl + 0.05),
        _cell(0.4, base - 0.03, sl + 0.10),     # knee + beats 0, but slice regressed
        _cell(0.6, base - 0.02, sl + 0.12),
    ]
    v = evaluate_gates(cells, seed=0, n_boot=400)
    assert v["g1_pass"] is True
    assert v["g2_pass"] is False
    assert v["verdict"] == "NO-LIFT"


def test_evaluate_gates_requires_a_k0_cell():
    with pytest.raises(ValueError):
        evaluate_gates([_cell(0.2, [0.3], [0.3])], seed=0, n_boot=10)
