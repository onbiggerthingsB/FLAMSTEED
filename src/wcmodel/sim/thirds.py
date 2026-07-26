"""Third-place qualification + knockout slot assignment (format-generic).

rank_thirds: rank the group third-placers (points -> GD -> GF -> seeded random
tail) and return the best ``best_n`` groups. The default ``best_n=8`` is the
frozen WC-2026 path (best 8 of 12 groups, FIFA criteria). AC-2027 passes
``best_n=4`` (best 4 of 6, regs Art. 9.5.1); its ranking criteria — AFC ops
manual (Edition 2026) Appendix 2 clause 1.1, points -> GD -> GF -> cards ->
lots — coincide with this body, with the unmodeled cards/lots tail standing in
as the seeded random draw (config/afc2027_rules_extract.md).

assign_thirds_to_slots: a LOOKUP in the edition's sourced pairing table under
``config/`` mapping the set of qualifying groups -> {KO match number: group}.
Default ``table_file="third_place_assignment.json"`` = FIFA's Annex C
(495 = C(12,8) rows -> R32 slots); ``"third_place_assignment_ac2027.json"`` =
the AFC regs Art. 9.9 table (15 = C(6,4) rows -> R16 slots). The assignment is
NOT a computed matching: the eligible-set perfect matching is non-unique (I
verified this for all 495 WC combinations), so the governing body's published
lookup is authoritative and required (a matching would pick arbitrary
differing assignments). Tables are sourced + validated by
``scripts/verify_thirds_table.py`` (full C(n,k) coverage, bijection,
eligibility, match-number pinning to ``_meta``)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np  # noqa: F401  (kept: rank_thirds consumes a numpy Generator rng)

# thirds.py lives at src/wcmodel/sim/ -> the repo root (which holds config/) is
# parents[3] (sim -> wcmodel -> src -> repo). NB: the deeper subpackage means this is
# one more level than wcmodel/config.py's parents[2].
_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
_DEFAULT_TABLE = "third_place_assignment.json"


@lru_cache(maxsize=8)
def load_assignment_table(table_file: str = _DEFAULT_TABLE) -> dict:
    """The sourced pairing table for one edition (read once per file, cached).
    Shape: ``{"_meta": {"columns_winner_slot_to_match": {...}, ...},
    "table": {"<sorted-qualifier-letters>": {"<KO match no>": "<group>"}}}``
    with ALL C(n_groups, best_n) combinations present (validated by
    ``scripts/verify_thirds_table.py``).

    ``table_file`` is a BARE file name resolved under the repo ``config/``
    directory — path separators, parent references and absolute paths are
    rejected (traversal guard: the name is config data threaded from the
    tournament yaml's ``format.assignment_table``, so it must never escape
    ``config/``)."""
    if (not table_file or table_file in (".", "..")   # NB: Path("..").name == ".."
            or Path(table_file).name != table_file):
        raise ValueError(
            f"table_file must be a bare file name under config/, got {table_file!r}")
    return json.loads((_CONFIG_DIR / table_file).read_text())


def rank_thirds(thirds: dict, *, rng, best_n: int = 8) -> list:
    """``thirds``: ``{group: {points, gd, gf}}`` for each group's 3rd-placer. Return
    the best ``best_n`` groups by points -> gd -> gf, with a seeded random draw ONLY
    for a tie that straddles the best_n/(best_n+1) qualification boundary (8/9 in
    WC-2026, 4/5 in AC-2027). Output is consumed as a SET (the qualifying groups ->
    ``assign_thirds_to_slots``), so internal order is irrelevant; a list of best_n
    is returned for compatibility.

    RNG locality (closes Codex T3). ``rng`` (a numpy Generator) is consumed IFF a
    (points, gd, gf) tie straddles the qualification boundary -- i.e. more groups
    share the boundary group's key than there are remaining best-N slots, so a draw
    genuinely decides WHICH of the tied groups qualify. This mirrors the governing
    bodies' drawing-of-lots (FIFA; AFC ops manual Appendix 2 clause 1.1.5), which is
    invoked only when lots actually decide qualification. A tie wholly INSIDE the
    top N (all those groups qualify regardless of order) or wholly OUTSIDE it (none
    qualify) is deterministic and consumes NO RNG -- so it never shifts the shared
    per-sim RNG stream and never perturbs unrelated downstream draws (scoreline
    sampling, knockout coin-flips). No global state, no per-group tilt."""
    if len(thirds) < best_n:
        raise ValueError(
            f"need at least {best_n} third-place records, got {len(thirds)}")

    def key(g):
        return (thirds[g]["points"], thirds[g]["gd"], thirds[g]["gf"])

    order = sorted(thirds, key=key, reverse=True)
    boundary = key(order[best_n - 1])                    # the boundary group's key

    strictly_better = [g for g in order if key(g) > boundary]  # auto-qualify, no RNG
    boundary_tied = [g for g in order if key(g) == boundary]   # share the cutoff key
    slots_left = best_n - len(strictly_better)           # >= 1 (the Nth is tied)

    if slots_left >= len(boundary_tied):
        # No straddle: every boundary-tied group fits (slots_left == len here, since
        # the Nth group's key is the boundary). Deterministic -> consume NO RNG.
        chosen = boundary_tied
    else:
        # Genuine straddle: more groups tied at the cutoff key than slots remaining. A
        # seeded draw decides which of them take the last qualification slot(s). This is
        # the ONLY RNG consumption in rank_thirds.
        perm = rng.permutation(len(boundary_tied))
        chosen = [boundary_tied[p] for p in perm[:slots_left]]

    return strictly_better + chosen


def assign_thirds_to_slots(qualifying_groups, *, table_file: str = _DEFAULT_TABLE) -> dict:
    """LOOKUP: the qualifying groups (a set/iterable of letters) -> ``{KO match no:
    group whose 3rd fills that slot}``, per the edition's published table. The
    required group count is the table's own slot count
    (``len(_meta.columns_winner_slot_to_match)``: 8 for WC-2026 Annex C, 4 for
    AC-2027 regs Art. 9.9). Raises if the count is wrong or the combination is
    absent.

    This is a dict lookup in the sourced ``config/<table_file>`` -- it NEVER
    computes a perfect matching over the slot eligible-sets. The matching is
    non-unique, so any matching algorithm would return an arbitrary valid
    assignment that differs from the published one. The sourced table is the
    authoritative oracle and is reproduced verbatim here."""
    data = load_assignment_table(table_file)
    expected = len(data["_meta"]["columns_winner_slot_to_match"])
    key = "".join(sorted(qualifying_groups))
    if len(set(qualifying_groups)) != expected:
        raise ValueError(f"need exactly {expected} qualifying groups, got {key!r}")
    table = data["table"]
    if key not in table:
        raise KeyError(f"combination {key!r} not in assignment table {table_file}")
    return {int(m): g for m, g in table[key].items()}
