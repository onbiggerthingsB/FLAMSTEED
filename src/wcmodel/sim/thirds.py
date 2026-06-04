"""Third-place qualification + R32 slot assignment.

rank_thirds: rank the 12 group third-placers (points -> GD -> GF -> seeded random
tail) and return the best 8 groups.

assign_thirds_to_slots: a LOOKUP in FIFA's Annex C table (config/third_place_
assignment.json) mapping the set of 8 qualifying groups -> {R32 match number:
group}. The assignment is NOT a computed matching: I verified the eligible-set
perfect matching is non-unique for all 495 combinations, so FIFA's Annex C lookup
is authoritative and required (a matching would pick arbitrary differing
assignments). The table is sourced + validated (495=C(12,8), bijection, eligibility)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np  # noqa: F401  (kept: rank_thirds consumes a numpy Generator rng)

# thirds.py lives at src/wcmodel/sim/ -> the repo root (which holds config/) is
# parents[3] (sim -> wcmodel -> src -> repo). NB: the deeper subpackage means this is
# one more level than wcmodel/config.py's parents[2].
_TABLE_PATH = Path(__file__).resolve().parents[3] / "config" / "third_place_assignment.json"


@lru_cache(maxsize=1)
def load_assignment_table() -> dict:
    """The sourced FIFA Annex C table (read once, cached). Shape:
    ``{"_meta": {...}, "table": {"<sorted-8-letters>": {"<R32 match no>": "<group>"}}}``
    with all 495 = C(12,8) combinations present (validated externally)."""
    return json.loads(_TABLE_PATH.read_text())


def rank_thirds(thirds: dict, *, rng) -> list:
    """``thirds``: ``{group: {points, gd, gf}}`` for the 12 groups' 3rd-placers. Return the
    best-8 groups by points -> gd -> gf, with a seeded random draw ONLY for a tie that
    straddles the 8/9 qualification boundary. Output is consumed as a SET (the 8
    qualifying groups -> ``assign_thirds_to_slots``), so internal order is irrelevant; a
    list of 8 is returned for compatibility.

    RNG locality (closes Codex T3). ``rng`` (a numpy Generator) is consumed IFF a
    (points, gd, gf) tie straddles the 8/9 boundary -- i.e. more groups share the 8th
    group's key than there are remaining best-8 slots, so a draw genuinely decides WHICH
    of the tied groups qualify. This mirrors FIFA's drawing-of-lots, which is invoked
    only when lots actually decide qualification. A tie wholly INSIDE the top 8 (all
    those groups qualify regardless of order) or wholly OUTSIDE it (none qualify) is
    deterministic and consumes NO RNG -- so it never shifts the shared per-sim RNG
    stream and never perturbs unrelated downstream draws (scoreline sampling, knockout
    coin-flips). No global state, no per-group tilt."""
    def key(g):
        return (thirds[g]["points"], thirds[g]["gd"], thirds[g]["gf"])

    order = sorted(thirds, key=key, reverse=True)
    boundary = key(order[7])                                  # the 8th group's key

    strictly_better = [g for g in order if key(g) > boundary]  # auto-qualify, no RNG
    boundary_tied = [g for g in order if key(g) == boundary]   # share the cutoff key
    slots_left = 8 - len(strictly_better)                      # >= 1 (the 8th is tied)

    if slots_left >= len(boundary_tied):
        # No straddle: every boundary-tied group fits (slots_left == len here, since the
        # 8th group's key is the boundary). Deterministic -> consume NO RNG.
        chosen = boundary_tied
    else:
        # Genuine straddle: more groups tied at the cutoff key than slots remaining. A
        # seeded draw decides which of them take the last qualification slot(s). This is
        # the ONLY RNG consumption in rank_thirds.
        perm = rng.permutation(len(boundary_tied))
        chosen = [boundary_tied[p] for p in perm[:slots_left]]

    return strictly_better + chosen


def assign_thirds_to_slots(qualifying_groups) -> dict:
    """LOOKUP: the 8 qualifying groups (a set/iterable of letters) -> ``{R32 match no:
    group whose 3rd fills that slot}``, per FIFA Annex C. Raises if not exactly 8 or
    the combination is absent from the table.

    This is a dict lookup in the sourced ``config/third_place_assignment.json`` -- it
    NEVER computes a perfect matching over the slot eligible-sets. The matching is
    non-unique for all 495 combinations, so any matching algorithm would return an
    arbitrary valid assignment that differs from FIFA's. The Annex C table is the
    authoritative oracle and is reproduced verbatim here."""
    key = "".join(sorted(qualifying_groups))
    if len(set(qualifying_groups)) != 8:
        raise ValueError(f"need exactly 8 qualifying groups, got {key!r}")
    table = load_assignment_table()["table"]
    if key not in table:
        raise KeyError(f"combination {key!r} not in Annex C table")
    return {int(m): g for m, g in table[key].items()}
