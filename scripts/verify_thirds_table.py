"""Verify a third-place assignment table: structure, coverage, bijection,
eligibility, and the F12 match-number pinning against ``_meta``.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/verify_thirds_table.py <table.json> <n_groups> <best_n>

    # WC-2026 (FIFA Annex C; the verifier's own regression check):
    ... scripts/verify_thirds_table.py config/third_place_assignment.json 12 8
    # AC-2027 (AFC regs Art. 9.9 transcription):
    ... scripts/verify_thirds_table.py config/third_place_assignment_ac2027.json 6 4

Checks (ALL must hold; exit 0 iff PASS, else exit 1 with every failure listed):
 1. shape: {"_meta": {"columns_winner_slot_to_match": {slot: match}}, "table": {...}}
 2. _meta maps exactly best_n winner slots to best_n DISTINCT match numbers
 3. table keys == ALL C(n_groups, best_n) sorted combinations of the first
    n_groups group letters (full coverage, no strays)
 4. every entry's match-number key set == set(_meta.columns_winner_slot_to_match
    .values())  [F12: a consistently wrong match-number set must fail]
 5. every entry is a bijection: its assigned groups are exactly its qualified set
 6. eligibility: the per-slot group sets DERIVED from the table (union over all
    entries) equal _meta.slot_eligible_groups when declared (AC-2027 declares the
    regs Art. 9.8 sets; the WC Annex C table declares none -> derived sets are
    printed for the record, not asserted against an external source)

Stdlib-only on purpose: this is the operator gate for hand-transcribed config
data, so it must not depend on the package under test."""
from __future__ import annotations

import itertools
import json
import math
import string
import sys
from pathlib import Path


def verify(table_path: str, n_groups: int, best_n: int) -> list[str]:
    """Return a list of failure messages (empty == PASS). Prints an info summary."""
    fails: list[str] = []
    try:
        data = json.loads(Path(table_path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot load {table_path}: {e}"]

    if not (1 <= best_n <= n_groups <= 26):
        return [f"nonsense args: n_groups={n_groups}, best_n={best_n}"]

    # -- 1. shape ------------------------------------------------------------
    meta = data.get("_meta")
    table = data.get("table")
    if not isinstance(meta, dict) or not isinstance(table, dict):
        return [f"{table_path}: top level must have dict '_meta' and 'table'"]
    slot_to_match = meta.get("columns_winner_slot_to_match")
    if not isinstance(slot_to_match, dict) or not slot_to_match:
        return [f"{table_path}: _meta.columns_winner_slot_to_match missing/empty"]

    # -- 2. _meta: best_n slots -> best_n distinct match numbers --------------
    try:
        meta_matches = {int(m) for m in slot_to_match.values()}
    except (TypeError, ValueError):
        return [f"_meta match numbers not integers: {slot_to_match!r}"]
    if len(slot_to_match) != best_n:
        fails.append(f"_meta has {len(slot_to_match)} winner slots, want {best_n}")
    if len(meta_matches) != len(slot_to_match):
        fails.append(f"_meta match numbers not distinct: {sorted(slot_to_match.values())}")

    # -- 3. full C(n_groups, best_n) coverage ---------------------------------
    letters = string.ascii_uppercase[:n_groups]
    expected_keys = {"".join(c) for c in itertools.combinations(letters, best_n)}
    n_expected = math.comb(n_groups, best_n)
    missing = expected_keys - set(table)
    strays = set(table) - expected_keys
    if missing:
        fails.append(f"{len(missing)} combination(s) missing, e.g. {sorted(missing)[:5]}")
    if strays:
        fails.append(f"{len(strays)} stray key(s), e.g. {sorted(strays)[:5]}")

    # -- 4 + 5. per entry: F12 match-number pin + bijection -------------------
    derived: dict[int, set[str]] = {m: set() for m in meta_matches}
    for combo in sorted(expected_keys & set(table)):
        row = table[combo]
        try:
            row_matches = {int(m) for m in row}
        except (TypeError, ValueError):
            fails.append(f"{combo}: non-integer match key in {sorted(row)}")
            continue
        if row_matches != meta_matches:
            fails.append(f"{combo}: match numbers {sorted(row_matches)} != "
                         f"_meta set {sorted(meta_matches)}")   # F12
        if sorted(row.values()) != sorted(combo):
            fails.append(f"{combo}: assigned groups {sorted(row.values())} are not "
                         f"a bijection onto the qualified set")
        for m, g in row.items():
            if int(m) in derived:
                derived[int(m)].add(g)

    # -- 6. eligibility ---------------------------------------------------------
    match_to_slot = {int(m): s for s, m in slot_to_match.items()}
    declared = meta.get("slot_eligible_groups")
    if declared is not None:
        if set(declared) != set(slot_to_match):
            fails.append(f"_meta.slot_eligible_groups slots {sorted(declared)} != "
                         f"winner slots {sorted(slot_to_match)}")
        else:
            for slot, groups in declared.items():
                m = int(slot_to_match[slot])
                if derived.get(m, set()) != set(groups):
                    fails.append(
                        f"slot {slot} (match {m}): derived eligible set "
                        f"{sorted(derived.get(m, set()))} != declared {sorted(groups)}")
    elig_note = "declared+checked" if declared is not None else "derived only (none declared)"

    print(f"{table_path}: {len(table)} entries (want C({n_groups},{best_n})={n_expected}), "
          f"slots {sorted(slot_to_match)} -> matches {sorted(meta_matches)}; "
          f"eligibility {elig_note}:")
    for m in sorted(derived):
        print(f"  match {m} ({match_to_slot.get(m, '?')}): "
              f"3rd of {{{', '.join(sorted(derived[m]))}}}")
    return fails


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    fails = verify(argv[1], int(argv[2]), int(argv[3]))
    if fails:
        for f in fails:
            print(f"FAIL: {f}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
