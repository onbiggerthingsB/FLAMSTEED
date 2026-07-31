#!/usr/bin/env python
"""Scored-fixture inventory generator (OA Plan 2 v2, V0 — finding 9, ratified
2026-08-01 pre-lock rule correction).

Emits ``config/oa_scored_inventory.yaml``: the FROZEN identity list of every
odds-scored fixture — the bk harness's 185-pool (its windows and tournament
labels VERBATIM, ``reports/bk_levers/bk_sweep.py``) plus the 32 WC-2026
knockout fixtures (the same labels, the wc2026 window extended through the
final). The development slate excludes EXACTLY these fixtures by canonical
``match_id`` — never by calendar window: the euro2024 window blanketed Copa
America 2024, killing an entire eligible development competition that shares
not one fixture with the scored pools.

The derivation is mechanical and cross-checked before anything is written:
the 185 keys of the committed ``reports/bk_levers/bk_rps_k0.6.json`` must be
EXACTLY the non-knockout subset of the derived inventory (same
``pool|date|home|away`` key construction), and the 32 extras must all be
WC-2026 fixtures after the group stage. A derivation that disagrees with the
harness it claims to mirror is refused, not committed.

Usage: PYTHONPATH=src .venv/bin/python scripts/oa_scored_inventory.py --emit
(run from the repo root; the default action prints the derivation summary
without writing).
"""
# No `from __future__ import annotations`: loaded by PATH in tests (scripts/
# is not on sys.path), matching the oa_probe.py convention.
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

#: The martj42 store the inventory is derived from, read at a PINNED cutoff so
#: the derivation is reproducible against the same bitemporal state.
STORE_DEFAULT = "data/stores/full_final"
CUTOFF = "2026-08-01T00:00:00Z"

#: The bk harness's windows/labels (reports/bk_levers/bk_sweep.py), verbatim
#: for wc2022/euro2024 — including the EXCLUSIVE lower bound (`>` in the
#: harness: the opening-day fixtures are not in the 185-pool and are therefore
#: not scored) — with wc2026 extended through the final to take in the 32
#: knockout fixtures the harness's July-2 sweep predated.
WINDOWS = (
    ("wc2022", "2022-11-20", "2022-12-18", False),
    ("euro2024", "2024-06-14", "2024-07-14", False),
    ("wc2026", "2026-06-11", "2026-07-19", True),
)
LABELS = {"wc2022": "fifa world cup", "euro2024": "uefa euro",
          "wc2026": "fifa world cup"}

#: The committed harness scores the cross-check runs against, and the day the
#: WC-2026 group stage ends (the harness's own wc2026 upper bound): every
#: derived fixture after it must be a knockout fixture the harness never saw.
BK_SCORES = "reports/bk_levers/bk_rps_k0.6.json"
WC2026_GROUP_END = "2026-06-27"

OUT_DEFAULT = "config/oa_scored_inventory.yaml"

_HEADER = """\
# OA scored-fixture inventory — the FROZEN identity list of every odds-scored
# fixture (OA Plan 2 v2, V0 / Codex batch-1 finding 9, RATIFIED).
#
# 2026-08-01 PRE-LOCK RULE CORRECTION: the development slate excludes EXACTLY
# these fixtures by canonical match_id — never by calendar window. The old
# window exclusion blanketed Copa America 2024 (entirely inside the euro2024
# window) although it shares not one fixture with the scored pools.
#
# Derived mechanically by scripts/oa_scored_inventory.py from the bk
# harness's windows/labels (reports/bk_levers/bk_sweep.py) applied to the
# martj42 store, cross-checked against the committed bk_rps_k0.6.json keys
# before emission. DO NOT EDIT BY HAND: the dev manifest generator and the
# select-time guard both assert dev_ids ∩ these ids = ∅, and the V8 lock
# hash-binds this file.
"""


class ScoredInventoryError(RuntimeError):
    """The derivation disagrees with the harness it claims to mirror."""


def derive_inventory(results: pd.DataFrame) -> list:
    """The scored fixtures, one dict per fixture, in (pool, date, match_id)
    order. Pure — the caller supplies the results frame."""
    frame = results.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    lowered = frame["tournament"].str.lower()
    rows = []
    for pool, lo, hi, inclusive in WINDOWS:
        sel = lowered.str.contains(LABELS[pool]) \
            & ~lowered.str.contains("qualif")
        sel &= (frame["date"] >= lo) if inclusive else (frame["date"] > lo)
        sel &= frame["date"] <= hi
        pool_rows = frame[sel].dropna(subset=["home_score", "away_score"])
        for row in pool_rows.itertuples():
            rows.append({
                "match_id": str(row.match_id), "pool": pool,
                "date": row.date.date().isoformat(),
                "home_team": str(row.home_team),
                "away_team": str(row.away_team),
                "tournament": str(row.tournament)})
    rows.sort(key=lambda r: (r["pool"], r["date"], r["match_id"]))
    ids = [r["match_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ScoredInventoryError(
            "duplicate match_id in the derived inventory — the exclusion is "
            "keyed by it")
    return rows


def cross_check(rows, bk_scores_path=BK_SCORES) -> None:
    """The derivation must reproduce the harness EXACTLY: the committed
    per-match keys are the non-knockout subset of the inventory, and every
    extra is a WC-2026 knockout fixture."""
    bk_keys = set(json.loads(Path(bk_scores_path).read_text()))
    derived = {f"{r['pool']}|{r['date']}|{r['home_team']}|{r['away_team']}": r
               for r in rows}
    missing = bk_keys - set(derived)
    if missing:
        raise ScoredInventoryError(
            f"{len(missing)} bk-harness key(s) absent from the derived "
            f"inventory (e.g. {sorted(missing)[:3]}) — the windows/labels "
            "do not reproduce the harness")
    extras = [derived[k] for k in set(derived) - bk_keys]
    bad = [r for r in extras
           if r["pool"] != "wc2026" or r["date"] <= WC2026_GROUP_END]
    if bad:
        raise ScoredInventoryError(
            f"{len(bad)} derived fixture(s) beyond the harness keys are not "
            f"WC-2026 knockouts (e.g. {bad[:3]}) — refusing to freeze an "
            "inventory wider than the scored pools")
    if len(extras) != 32:
        raise ScoredInventoryError(
            f"expected exactly 32 WC-2026 knockout fixtures beyond the "
            f"harness's 185; got {len(extras)}")


def emit(rows, out_path) -> Path:
    doc = {
        "derived_by": "scripts/oa_scored_inventory.py",
        "store": STORE_DEFAULT, "cutoff": CUTOFF,
        "windows": {pool: {"start": lo, "end": hi,
                           "start_inclusive": inclusive}
                    for pool, lo, hi, inclusive in WINDOWS},
        "labels": dict(LABELS),
        "cross_checked_against": BK_SCORES,
        "n_fixtures": len(rows),
        "fixtures": rows,
    }
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_HEADER + yaml.safe_dump(doc, sort_keys=False,
                                             allow_unicode=True))
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit", action="store_true",
                    help="write the inventory (default: derivation summary "
                         "only)")
    ap.add_argument("--store", default=STORE_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args(argv)

    from wcmodel.data.store import BitemporalStore

    results = BitemporalStore(root=args.store).read("results", cutoff=CUTOFF)
    try:
        rows = derive_inventory(results)
        cross_check(rows)
    except ScoredInventoryError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1
    pools = {}
    for r in rows:
        pools[r["pool"]] = pools.get(r["pool"], 0) + 1
    print(f"derived {len(rows)} scored fixtures: "
          + ", ".join(f"{p}={n}" for p, n in sorted(pools.items()))
          + f" (cross-checked against {BK_SCORES})")
    if args.emit:
        path = emit(rows, args.out)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
