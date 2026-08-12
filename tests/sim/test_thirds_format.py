"""Phase 2A Task 3: best-N thirds + AC-2027 pairing table.

tests/sim/test_thirds.py (the frozen WC-2026 path: 12 groups, best-8, FIFA
Annex C table) stays untouched and must remain green. This file covers the
format-generic surface added for AC-2027:

- ``rank_thirds(..., best_n=4)`` (regs Art. 9.5.1: four best third-placed of
  six groups; ranking criteria = ops manual Appendix 2 clause 1.1, pages
  104-105: points -> GD -> GF, with cards/lots as the seeded random tail);
- ``load_assignment_table(table_file)`` traversal guard (bare file name only);
- ``assign_thirds_to_slots(..., table_file=...)`` against the transcribed
  ``config/third_place_assignment_ac2027.json`` (regs Arts. 9.8-9.9, pages
  28-29: the complete 15-row C(6,4) pairing table);
- ``scripts/verify_thirds_table.py`` on BOTH real tables (the WC run is the
  verifier's own regression check) and its F12 match-number-vs-_meta pinning.
"""
import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from wcmodel.sim.thirds import (assign_thirds_to_slots, load_assignment_table,
                                rank_thirds)

_AC_TABLE = "third_place_assignment_ac2027.json"
_WC_TABLE = "third_place_assignment.json"
_VERIFIER = "scripts/verify_thirds_table.py"

# Regs Art. 9.8 (page 28): the four third-facing R16 slots and their eligible
# third-place groups — 1A vs 3rd of C/D/E, 1B vs A/C/D, 1C vs A/B/F, 1D vs B/E/F.
_ELIGIBLE = {"1A": set("CDE"), "1B": set("ACD"), "1C": set("ABF"), "1D": set("BEF")}


class _NoRNG:
    """Sentinel: rank_thirds must not consume RNG without a boundary straddle."""

    def permutation(self, *a, **k):  # pragma: no cover - asserted not-called
        raise AssertionError("rank_thirds consumed RNG without a boundary straddle")


class _SeqRNG:
    """Deterministic recorder: permutation(n) returns identity and logs n."""

    def __init__(self):
        self.calls = []

    def permutation(self, n):
        self.calls.append(n)
        return np.arange(n)


# ---------------------------------------------------------------- rank_thirds

def test_rank_thirds_best4_of_6():
    thirds = {g: {"points": p, "gd": d, "gf": f} for g, (p, d, f) in zip(
        "ABCDEF", [(9, 5, 9), (7, 3, 7), (6, 2, 5), (4, 0, 4), (3, -2, 2), (1, -8, 1)])}
    best4 = rank_thirds(thirds, rng=_NoRNG(), best_n=4)
    assert len(best4) == 4 and set(best4) == set("ABCD")


def test_rank_thirds_best4_tie_inside_top4_no_rng():
    # A,B tie on (9,0,0) but both qualify regardless of order: no 4/5-boundary
    # straddle -> RNG must not be consumed (same locality contract as WC best-8).
    thirds = {g: {"points": p, "gd": 0, "gf": 0}
              for g, p in zip("ABCDEF", [9, 9, 7, 5, 4, 1])}
    best4 = rank_thirds(thirds, rng=_NoRNG(), best_n=4)
    assert set(best4) == set("ABCD")


def test_rank_thirds_best4_boundary_straddle_consumes_rng_once():
    # A,B,C strictly better; D,E share the 4th-place key exactly -> 1 slot for
    # 2 tied groups: a genuine 4/5 straddle. Identity permutation -> D (stable
    # sort order), and exactly one permutation(2) call.
    thirds = {g: {"points": p, "gd": 0, "gf": 0}
              for g, p in zip("ABCDEF", [9, 8, 7, 5, 5, 1])}
    rng = _SeqRNG()
    best4 = rank_thirds(thirds, rng=rng, best_n=4)
    assert rng.calls == [2]
    assert set(best4) == set("ABCD")
    # Seeded Generator: same seed -> same qualifying set, always {A,B,C}+one of D/E.
    s0 = set(rank_thirds(thirds, rng=np.random.default_rng(0), best_n=4))
    assert s0 == set(rank_thirds(thirds, rng=np.random.default_rng(0), best_n=4))
    assert set("ABC") <= s0 and len(s0 - set("ABC")) == 1 and s0 - set("ABC") <= set("DE")


def test_rank_thirds_default_best8_unchanged():
    # WC-2026 default path: best_n omitted == best 8 of 12, no RNG off-straddle.
    thirds = {g: {"points": p, "gd": 0, "gf": 0}
              for g, p in zip("ABCDEFGHIJKL", [9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 0, 0])}
    assert set(rank_thirds(thirds, rng=_NoRNG())) == set("ABCDEFGH")


def test_rank_thirds_too_few_groups_raises():
    thirds = {g: {"points": 1, "gd": 0, "gf": 0} for g in "ABC"}
    with pytest.raises(ValueError, match="at least 4"):
        rank_thirds(thirds, rng=_NoRNG(), best_n=4)


# ------------------------------------------------------------- the AC table

def _ac_raw():
    return json.loads(Path("config", _AC_TABLE).read_text())


def test_ac_table_full_coverage_c6_4():
    t = _ac_raw()
    expected = {"".join(c) for c in itertools.combinations("ABCDEF", 4)}
    assert set(t["table"]) == expected
    assert len(t["table"]) == 15                       # C(6,4), complete per regs


def test_ac_table_bijection_eligibility_and_meta_pin():
    t = _ac_raw()
    slot_to_match = {s: int(m)
                     for s, m in t["_meta"]["columns_winner_slot_to_match"].items()}
    assert set(slot_to_match) == set(_ELIGIBLE)
    match_to_slot = {m: s for s, m in slot_to_match.items()}
    assert len(match_to_slot) == 4                     # distinct match numbers
    for combo, row in t["table"].items():
        assert sorted(row.values()) == sorted(combo)   # bijection onto the 4 thirds
        assert {int(m) for m in row} == set(match_to_slot)  # F12: keys == _meta set
        for m, g in row.items():
            assert g in _ELIGIBLE[match_to_slot[int(m)]]    # regs Art. 9.8
    # Declared eligibility in _meta must equal the regs sets verbatim.
    declared = {s: set(v) for s, v in t["_meta"]["slot_eligible_groups"].items()}
    assert declared == _ELIGIBLE


def test_ac_table_worked_example_from_regs():
    # Art. 9.9 prose (page 28): if thirds of A, B, C, D qualify, the pairings
    # are 1A vs 3C, 1B vs 3D, 1C vs 3A and 1D vs 3B.
    t = _ac_raw()
    s2m = t["_meta"]["columns_winner_slot_to_match"]
    row = t["table"]["ABCD"]
    assert row[str(s2m["1A"])] == "C"
    assert row[str(s2m["1B"])] == "D"
    assert row[str(s2m["1C"])] == "A"
    assert row[str(s2m["1D"])] == "B"


# ------------------------------------------- assign_thirds_to_slots(table_file)

def test_assign_ac_lookup_exact_and_int_keys():
    t = _ac_raw()
    for key in ["ABCD", "BCEF", "CDEF"]:
        got = assign_thirds_to_slots(set(key), table_file=_AC_TABLE)
        assert got == {int(m): g for m, g in t["table"][key].items()}
        assert all(isinstance(m, int) for m in got)


def test_assign_ac_wrong_count_raises():
    with pytest.raises(ValueError, match="need exactly 4"):
        assign_thirds_to_slots(set("ABCDEFGH"), table_file=_AC_TABLE)
    with pytest.raises(ValueError, match="need exactly 4"):
        assign_thirds_to_slots(set("ABC"), table_file=_AC_TABLE)


def test_assign_wc_default_unchanged():
    # No table_file argument -> the frozen WC-2026 Annex C lookup, verbatim.
    tbl = load_assignment_table()
    expected = {int(m): g for m, g in tbl["table"]["ABCDEFGH"].items()}
    assert assign_thirds_to_slots(set("ABCDEFGH")) == expected
    with pytest.raises(ValueError, match="need exactly 8"):
        assign_thirds_to_slots(set("ABCD"))


def test_table_file_traversal_rejected():
    for bad in ("../third_place_assignment.json", "sub/dir.json",
                "/etc/passwd", "..", ""):
        with pytest.raises(ValueError, match="bare file name"):
            load_assignment_table(bad)
    with pytest.raises(ValueError, match="bare file name"):
        assign_thirds_to_slots(set("ABCD"), table_file="../evil.json")


# ------------------------------------------------------------- the verifier

def test_verifier_passes_both_real_tables():
    # The WC run is the verifier's own regression check (it must accept the
    # long-frozen Annex C table); the AC run gates the new transcription.
    for table, n_groups, best_n in [(f"config/{_WC_TABLE}", "12", "8"),
                                    (f"config/{_AC_TABLE}", "6", "4")]:
        proc = subprocess.run(
            [sys.executable, _VERIFIER, table, n_groups, best_n],
            env={"PYTHONPATH": "src"}, capture_output=True, text=True)
        assert proc.returncode == 0, f"{table}: {proc.stdout}{proc.stderr}"


def test_verifier_rejects_wrong_match_set(tmp_path):
    raw = json.loads(Path("config/third_place_assignment_ac2027.json").read_text())
    bad = {"_meta": raw["_meta"],
           "table": {k: {str(int(m) + 100): g for m, g in v.items()}
                     for k, v in raw["table"].items()}}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    rc = subprocess.run([sys.executable, "scripts/verify_thirds_table.py",
                         str(p), "6", "4"], env={"PYTHONPATH": "src"},
                        capture_output=True).returncode
    assert rc != 0
