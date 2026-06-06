import math
import pytest
from wcmodel.dashboard.build import gate_artifact, sanitize_nans, stringify_keys


def test_gate_rejects_a_naked_or_incoherent_artifact():
    good = {"Brazil": {"champion": {"value": 0.10, "se": 0.002},
                       "reach_final": {"value": 0.18, "se": 0.003}}}
    gate_artifact(good)                                          # no raise
    naked = {"Brazil": {"champion": {"value": 0.10}}}           # no SE/CI companion
    with pytest.raises(ValueError, match="naked"):
        gate_artifact(naked)
    incoherent = {"Brazil": {"champion": {"value": 0.30, "se": 0.0},
                             "reach_final": {"value": 0.18, "se": 0.0}}}
    with pytest.raises(ValueError, match="coherence"):
        gate_artifact(incoherent)


def test_sanitize_nans_turns_nan_into_null_so_json_is_valid():
    import json
    out = sanitize_nans({"a": float("nan"), "b": [1.0, float("nan")], "c": {"d": 2.0}})
    assert out == {"a": None, "b": [1.0, None], "c": {"d": 2.0}}
    json.dumps(out, allow_nan=False)        # must NOT raise (no NaN tokens remain)


def test_stringify_keys_makes_tuple_keys_json_safe():
    out = stringify_keys({("Spain", "Morocco", "2026-06-11"): {"edge": 0.04}})
    assert "Spain|Morocco|2026-06-11" in out
