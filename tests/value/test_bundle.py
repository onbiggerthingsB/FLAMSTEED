import json, inspect
from wcmodel.value import scanner, bundle as vb
from wcmodel.value.bundle import build_value_bundle, gate_value

def test_bundle_is_signal_only_and_stamped():
    res = {"bettable": [], "filtered": [], "coverage_gaps": []}
    out = build_value_bundle(res, scan_ts="2026-06-08T23:10:00Z", sharp="pinnacle",
                             regions="us,uk,eu", credits_used=6, credits_remaining=19000)
    assert out["provenance"]["signal_only"] is True
    assert out["provenance"]["is_synthetic"] is True          # NON-REAL until a feed is funded
    assert out["provenance"]["banner"]                        # NOT-REAL banner present
    assert out["data"]["bettable"] == []
    gate_value(out)                                           # must not raise

def test_no_bet_or_broker_path_exists():
    """Signal-only invariant: the value package must contain NO execution path."""
    for mod in (scanner, vb):
        src = inspect.getsource(mod).lower()
        for forbidden in ("place_bet", "broker", "order", "stake_real", "execute_bet"):
            assert forbidden not in src, f"{forbidden} in {mod.__name__}"

def test_gate_rejects_naked_value_node():
    bad = {"provenance": {"signal_only": True, "is_synthetic": True, "banner": "x"},
           "data": {"bettable": [{"event": "A v B"}], "filtered": [], "coverage_gaps": []}}
    try:
        gate_value(bad); assert False, "expected ValueError"
    except ValueError:
        pass
