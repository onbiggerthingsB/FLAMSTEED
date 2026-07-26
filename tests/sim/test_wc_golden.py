"""WC-2026 byte-identity golden gate (Phase-2A Task 0, F9).

Phase 2A generalizes the tournament pipeline to other formats. The WC-2026 path
is FROZEN, and green suites are NOT sufficient proof of that: a refactor can
satisfy every existing assertion while shifting a probability in the 6th
decimal. This test is the sufficient proof — it re-runs the exact seeded
reference simulation of the REAL ``config/tournament_2026.yaml`` draw captured
on pre-change code and compares SHA-256 hashes of the full progression and SE
frames plus the market column ORDER.

If a later Phase-2A task changes WC output in any way, this FAILS. That is the
whole point: the golden is never to be updated to make a change pass — a hash
mismatch means the change is wrong.

The reference setup lives in ``scripts/capture_wc_golden.py`` (loaded here by
file path, the house convention for script tests) so capture and check can never
drift apart: both call the same :func:`run_reference_sim`.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _ROOT / "scripts" / "capture_wc_golden.py"
_GOLDEN_PATH = _ROOT / "tests" / "golden" / "wc2026_sim_golden.json"


def _capture_module():
    """Load ``scripts/capture_wc_golden.py`` by file path (house script-test pattern)."""
    spec = importlib.util.spec_from_file_location("capture_wc_golden", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wc2026_sim_is_byte_identical_to_golden(tmp_path):
    """The frozen WC-2026 path: same hashes, same columns, same MC params."""
    golden = json.loads(_GOLDEN_PATH.read_text())
    mod = _capture_module()

    assert golden["params"] == dict(mod.PARAMS), (
        "the golden was captured with different MC params than the reference "
        f"run: {golden['params']} vs {dict(mod.PARAMS)}")

    res = mod.run_reference_sim(tmp_root=tmp_path)
    got = mod.golden_payload(res)

    assert got["columns"] == golden["columns"], (
        "WC-2026 market columns changed (order or membership): "
        f"{got['columns']} != {golden['columns']}")
    assert got["progression_sha256"] == golden["progression_sha256"], (
        "WC-2026 progression frame changed — the frozen published path is NOT "
        "byte-identical any more. Do NOT re-capture the golden: fix the change.")
    assert got["se_sha256"] == golden["se_sha256"], (
        "WC-2026 SE frame changed — the frozen published path is NOT "
        "byte-identical any more. Do NOT re-capture the golden: fix the change.")
