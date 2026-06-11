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
    bootstrap_support,
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


# --------------------------------------------------------------------------- #
# bootstrap_support (ADDENDUM-2 evidence #2): % of paired resamples favouring  #
# k>0, i.e. % with delta = mean(b) - mean(a) < 0 (b = the k>0 arm, lower=better)#
# --------------------------------------------------------------------------- #
def test_support_all_negative_delta_is_100pct():
    # b is uniformly LOWER (better) than a on every match -> every resample favours
    # k>0 -> support == 100%.
    a = list(np.linspace(0.30, 0.60, 50))
    b = [x - 0.05 for x in a]
    sup = bootstrap_support(a, b, seed=0, n_boot=500)
    assert sup == 100.0


def test_support_all_positive_delta_is_0pct():
    # b uniformly WORSE (higher RPS) -> no resample favours k>0 -> support 0%.
    a = list(np.linspace(0.30, 0.60, 50))
    b = [x + 0.05 for x in a]
    sup = bootstrap_support(a, b, seed=0, n_boot=500)
    assert sup == 0.0


def test_support_symmetric_is_about_half():
    # A symmetric per-match difference (mean ~0, balanced signs) -> ~50% support.
    rng = np.random.default_rng(0)
    n = 400
    a = rng.uniform(0.2, 0.6, n)
    diff = rng.normal(0.0, 0.05, n)            # zero-mean, symmetric
    b = a + diff
    sup = bootstrap_support(list(a), list(b), seed=3, n_boot=2000)
    assert 40.0 <= sup <= 60.0                 # near 50%, tolerant of MC noise


def test_support_is_deterministic_for_seed():
    a = list(np.linspace(0.2, 0.6, 30))
    b = [x - 0.01 for x in a]
    assert (bootstrap_support(a, b, seed=7, n_boot=400)
            == bootstrap_support(a, b, seed=7, n_boot=400))


def test_support_empty_is_nan():
    assert np.isnan(bootstrap_support([], [], seed=0, n_boot=10))


def test_support_matches_paired_bootstrap_field():
    # evaluate_gates' paired delta dict now also carries `support`; a standalone
    # bootstrap_support call with the same seed/n_boot must agree.
    a = list(np.linspace(0.30, 0.60, 60))
    b = [x - 0.02 for x in a]
    d = paired_bootstrap_delta(a, b, seed=11, n_boot=500)
    sup = bootstrap_support(a, b, seed=11, n_boot=500)
    assert d["support"] == sup


# --------------------------------------------------------------------------- #
# evaluate_gates — ADDENDUM-2 decision rule (support-gated, MORNING-CALL band) #
# --------------------------------------------------------------------------- #
def _cells_for_support(knee_bump, seed=0, n=200, slice_bump=-0.001, sanity=0.6,
                       noise=0.0):
    """Build a 4-k grid where k=0.4 is the knee with a tunable overall improvement
    so the bootstrap support over k=0 lands in a target band. ``knee_bump`` is the
    MEAN per-match RPS change (negative = better); ``noise`` adds ZERO-MEAN per-
    match scatter on the knee's difference so the paired bootstrap has realistic
    variance (a pure constant shift snaps support to 0/100). ``sanity`` is the
    max-favourite probability stamped on every cell (<=0.95 keeps sanity passing)."""
    rng = np.random.default_rng(seed)
    base = rng.uniform(0.2, 0.6, n)
    jitter = rng.normal(0.0, noise, n) if noise else np.zeros(n)
    cells = [
        {"k": 0.0, "overall_rps": list(base), "slice_rps": list(base[:40]),
         "max_favorite": sanity},
        {"k": 0.2, "overall_rps": list(base + knee_bump / 3 + jitter / 3),
         "slice_rps": list(base[:40] + slice_bump / 2), "max_favorite": sanity},
        {"k": 0.4, "overall_rps": list(base + knee_bump + jitter),
         "slice_rps": list(base[:40] + slice_bump), "max_favorite": sanity},
        {"k": 0.6, "overall_rps": list(base + knee_bump * 0.8 + jitter * 0.8),
         "slice_rps": list(base[:40] + slice_bump * 0.8), "max_favorite": sanity},
    ]
    return cells


def test_adopt_requires_at_least_75pct_support():
    # A strong, consistent improvement at the knee -> high support -> ADOPT.
    cells = _cells_for_support(knee_bump=-0.04, seed=0)
    v = evaluate_gates(cells, seed=0, n_boot=800)
    assert v["support"] >= 75.0
    assert v["g2_pass"] is True and v["sanity_pass"] is True
    assert v["verdict"] == "ADOPT"


def test_no_lift_when_support_below_60():
    # A tiny edge buried in heavy per-match noise -> support under 60% -> NO-LIFT
    # (point estimate alone never adopts). Search seeds for a sub-60% draw (the
    # near-zero mean edge makes ~half of draws land low-support).
    found = None
    for seed in range(60):
        cells = _cells_for_support(knee_bump=-0.0005, seed=seed, noise=0.12)
        v = evaluate_gates(cells, seed=0, n_boot=800)
        if v["support"] < 60.0:
            found = v
            break
    assert found is not None, "no sub-60% support case constructed"
    assert found["verdict"] == "NO-LIFT"
    assert found["k"] is None


def test_morning_call_in_60_to_75_band():
    # Tune the edge (mean) against the scatter (noise) so support lands in
    # [60, 75) -> MORNING-CALL, never adopt. Search bumps/seeds for an in-band hit.
    found = None
    for seed in range(60):
        for bump in (-0.004, -0.006, -0.008, -0.010, -0.012):
            cells = _cells_for_support(knee_bump=bump, seed=seed, noise=0.08)
            v = evaluate_gates(cells, seed=0, n_boot=800)
            if 60.0 <= v["support"] < 75.0:
                found = v
                break
        if found:
            break
    assert found is not None, "no in-band (60-75%) support case constructed"
    assert found["verdict"] == "MORNING-CALL"
    assert found["k"] is None             # the harness never adopts in this band


def test_sanity_gate_blocks_adopt_on_over_anchored_favorite():
    # Strong support + slice ok, but the knee cell shows a >95% match favourite
    # (over-anchoring) -> sanity fails -> NOT adopt even with high support.
    cells = _cells_for_support(knee_bump=-0.04, seed=0, sanity=0.97)
    v = evaluate_gates(cells, seed=0, n_boot=800)
    assert v["support"] >= 75.0
    assert v["sanity_pass"] is False
    assert v["verdict"] != "ADOPT"


def test_g2_slice_regression_blocks_adopt_even_with_support():
    # High overall support, but the has_squad=0 slice regresses hard (CI above 0)
    # -> G2 fails -> not ADOPT.
    cells = _cells_for_support(knee_bump=-0.04, seed=0, slice_bump=+0.10)
    v = evaluate_gates(cells, seed=0, n_boot=800)
    assert v["support"] >= 75.0
    assert v["g2_pass"] is False
    assert v["verdict"] != "ADOPT"


def test_support_is_for_the_knee_arm_vs_zero():
    # The reported `support` is the knee arm's support over k=0 (evidence #2).
    cells = _cells_for_support(knee_bump=-0.04, seed=0)
    v = evaluate_gates(cells, seed=0, n_boot=800)
    knee = next(c for c in cells if abs(c["k"] - v["knee_k"]) < 1e-9)
    expect = bootstrap_support(cells[0]["overall_rps"], knee["overall_rps"],
                               seed=0, n_boot=800)
    assert v["support"] == expect


def test_sanity_defaults_pass_when_no_max_favorite_field():
    # Back-compat: cells without a max_favorite field -> sanity vacuously passes
    # (so the existing pure-helper tests keep their meaning).
    rng = np.random.default_rng(0)
    base = rng.uniform(0.2, 0.6, 200)
    cells = [
        _cell(0.0, base, base[:40]),
        _cell(0.4, base - 0.04, base[:40] - 0.001),
        _cell(0.2, base - 0.01, base[:40]),
        _cell(0.6, base - 0.02, base[:40]),
    ]
    v = evaluate_gates(cells, seed=0, n_boot=800)
    assert v["sanity_pass"] is True
