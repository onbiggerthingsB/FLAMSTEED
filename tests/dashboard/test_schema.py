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
