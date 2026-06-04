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
    best-8 groups by points -> gd -> gf -> seeded random draw for a boundary tie.

    Pure + seeded: ``rng`` (a numpy Generator) is consulted ONLY to break a cluster of
    groups level on (points, gd, gf) -- mirroring the group-stage seeded random tail in
    ``groups.rank_group``. No global state, no per-group tilt."""
    groups = list(thirds)

    def key(g):
        return (thirds[g]["points"], thirds[g]["gd"], thirds[g]["gf"])

    order = sorted(groups, key=key, reverse=True)
    out, i = [], 0
    while i < len(order):
        j = i
        while j < len(order) and key(order[j]) == key(order[i]):
            j += 1
        cluster = order[i:j]
        if len(cluster) > 1:
            perm = rng.permutation(len(cluster))
            cluster = [cluster[p] for p in perm]
        out.extend(cluster)
        i = j
    return out[:8]


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
