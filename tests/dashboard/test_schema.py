import math
import pytest
from wcmodel.dashboard.schema import (
    validate_progression_coherence, assert_uncertainty_companion, coverage_gap, no_impute,
)


def test_coherence_accepts_monotone_ladder():
    validate_progression_coherence({
        "champion": 0.10, "reach_final": 0.18, "reach_sf": 0.30,
        "reach_qf": 0.45, "advance_from_group": 0.70,
    })  # no raise


def test_coherence_rejects_a_broken_ladder():
    with pytest.raises(ValueError, match="coherence"):
        validate_progression_coherence({
            "champion": 0.20, "reach_final": 0.18,
            "reach_sf": 0.30, "reach_qf": 0.45, "advance_from_group": 0.70,
        })


def test_coherence_includes_reach_r16_in_the_ladder():
    """reach_r16 sits between advance_from_group and reach_qf on the cumulative ladder
    (champion <= reach_final <= reach_sf <= reach_qf <= reach_r16 <= advance_from_group),
    and team_progression emits it — so the coherence gate must check it. A table where
    reach_r16 EXCEEDS advance_from_group (a deeper stage more likely than a shallower one)
    while every other rung is coherent must RAISE. RED before reach_r16 is in _LADDER
    (the rung is silently skipped, so the violation slips through GREEN); GREEN after."""
    with pytest.raises(ValueError, match="coherence"):
        validate_progression_coherence({
            "champion": 0.10, "reach_final": 0.18, "reach_sf": 0.30, "reach_qf": 0.45,
            "reach_r16": 0.80,            # > advance_from_group (0.70): incoherent
            "advance_from_group": 0.70,
        })


def test_coherence_accepts_a_coherent_ladder_with_reach_r16():
    """The full ladder including reach_r16, all monotone -> no raise."""
    validate_progression_coherence({
        "champion": 0.10, "reach_final": 0.18, "reach_sf": 0.30, "reach_qf": 0.45,
        "reach_r16": 0.60, "advance_from_group": 0.70,
    })  # no raise


def test_uncertainty_companion_required_on_every_probability():
    assert_uncertainty_companion({"value": 0.14, "se": 0.02})
    assert_uncertainty_companion({"value": 0.58, "ci": [0.52, 0.63]})
    with pytest.raises(ValueError, match="naked"):
        assert_uncertainty_companion({"value": 0.14})


def test_coverage_gap_is_explicit_not_a_number():
    g = coverage_gap("no outright odds")
    assert g == {"coverage_gap": True, "reason": "no outright odds", "value": None}


def test_no_impute_passes_nan_through_as_null_never_zero():
    assert no_impute(float("nan")) is None
    assert no_impute(1.7) == 1.7


def test_se_zero_is_a_valid_companion_certain_market():
    # an eliminated team: champion prob 0 -> binomial SE exactly 0 -> legitimate, NOT naked
    assert_uncertainty_companion({"value": 0.0, "se": 0.0})   # no raise


def test_degenerate_companions_are_rejected_as_naked():
    for bad in ({"value": 0.1, "se": float("nan")},
                {"value": 0.1, "se": float("inf")},
                {"value": 0.1, "ci": []},
                {"value": 0.1, "ci": [0.5]},
                {"value": 0.1, "ci": [0.5, float("nan")]}):
        with pytest.raises(ValueError, match="naked"):
            assert_uncertainty_companion(bad)


def test_valid_companions_still_pass():
    assert_uncertainty_companion({"value": 0.14, "se": 0.02})        # finite se
    assert_uncertainty_companion({"value": 0.58, "ci": [0.52, 0.63]}) # 2 finite bounds


from wcmodel.dashboard.schema import gate_fixture_forecast, gate_track


def test_coverage_gap_node_is_exempt_from_naked_check():
    assert_uncertainty_companion(coverage_gap("no odds"))      # no raise (value is None)
    assert_uncertainty_companion({"value": None})              # explicit null is not naked


def test_gate_fixture_forecast_requires_distribution_and_paired_score():
    good = {"most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12},
            "shortlist": [{"home_goals": 1, "away_goals": 0, "prob": 0.12}],
            "grid": [[0.5, 0.2], [0.2, 0.1]],
            "one_x_two": {"home": 0.7, "draw": 0.2, "away": 0.1}}
    gate_fixture_forecast(good)                                # grid sums ~1, all three 1X2, paired score
    with pytest.raises(ValueError, match="(?i)grid|1x2|naked"):
        gate_fixture_forecast({"most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12}})


def test_gate_fixture_forecast_rejects_a_lone_1x2_outcome():
    f = {"most_likely": {"home_goals": 1, "away_goals": 0, "prob": 0.12},
         "grid": [[0.5, 0.2], [0.2, 0.1]], "one_x_two": {"home": 0.7}}   # only one outcome
    with pytest.raises(ValueError, match="(?i)1x2|three"):
        gate_fixture_forecast(f)


def test_gate_track_rejects_a_nan_metric():
    gate_track({"beat_close_rate": 0.56, "avg_clv": 0.018, "rps": {"model": 0.1}})  # ok
    with pytest.raises(ValueError, match="(?i)nan|finite"):
        gate_track({"beat_close_rate": float("nan")})
