#!/usr/bin/env python
"""Development-slate manifest generator — STUB until the evidence exists.

Applies the FROZEN rule (``wcmodel.eval.dev_slate.THE_RULE``) to the martj42
store and emits ``config/oa_dev_manifest.yaml``, which is committed and
hash-bound into the V8 prereg lock.

It cannot run yet, and says so instead of guessing: the rule's two evidence
inputs — the competition keys (from the ``--slate`` mini-probe, then the G-B
acquisition) and the per-fixture coverage admissibility (from the acquisition
itself) — do not exist before V4. Everything else about the selection IS
frozen now, which is the point: when those inputs land, the manifest is a
mechanical consequence, not a choice.

Default action prints readiness. ``--emit`` writes the manifest and refuses,
loudly, while any input is still missing.
"""
# No `from __future__ import annotations`: loaded by PATH in tests (scripts/ is
# not on sys.path), matching the oa_probe.py / oa_mde.py convention.
import argparse
import sys
from pathlib import Path

import yaml

from wcmodel.eval.dev_slate import (
    DEV_WINDOW,
    SCORED_INVENTORY_PATH,
    SCORED_POOL_WINDOWS,
    THE_RULE,
    eligible_dev_fixtures,
    load_dev_slate_config,
    scored_fixture_ids,
    truncate_to_n_dev,
)

OUT_DEFAULT = "config/oa_dev_manifest.yaml"


def _config_matches_constants(cfg: dict) -> list:
    """The config comment is the human freeze, the constants are the machine
    one: a drift between them means the committed manifest was built to a rule
    nobody reviewed."""
    problems = []
    want_window = {"start": DEV_WINDOW[0].isoformat(),
                   "end": DEV_WINDOW[1].isoformat()}
    if cfg.get("window") != want_window:
        problems.append(f"window {cfg.get('window')} != frozen {want_window}")
    want_pools = {pool: [start.isoformat(), end.isoformat()]
                  for pool, start, end in SCORED_POOL_WINDOWS}
    if cfg.get("scored_pool_windows") != want_pools:
        problems.append(
            f"scored_pool_windows {cfg.get('scored_pool_windows')} != frozen "
            f"{want_pools}")
    return problems


def emit_manifest(results, *, competitions, admissible, n_dev: int,
                  out_path) -> Path:
    """Write the manifest. Pure w.r.t. the store: the caller supplies the
    frame, so the selection is testable without a local store."""
    ordered = eligible_dev_fixtures(results, competitions=competitions)
    slate = truncate_to_n_dev(ordered, admissible=admissible, n_dev=n_dev)
    doc = {
        "rule": THE_RULE,
        "window": {"start": DEV_WINDOW[0].isoformat(),
                   "end": DEV_WINDOW[1].isoformat()},
        # The exclusion is exact membership in this inventory (2026-08-01
        # pre-lock correction); the windows below are informational only.
        "scored_inventory": "config/oa_scored_inventory.yaml",
        "scored_pool_windows": {pool: [start.isoformat(), end.isoformat()]
                                for pool, start, end in SCORED_POOL_WINDOWS},
        "competitions": list(competitions),
        "n_dev": int(n_dev),
        "n_candidates_before_truncation": int(len(ordered)),
        "fixtures": [
            {"match_id": row.match_id, "date": row.date.isoformat(),
             "home_team": row.home_team, "away_team": row.away_team,
             "tournament": row.tournament}
            for row in slate.itertuples()],
    }
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys=False: the header (rule, window, exclusions) must read first —
    # this file is reviewed by a human before it is hashed into the lock.
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit", action="store_true",
                    help="write the manifest (refuses while any evidence "
                         "input is still missing)")
    ap.add_argument("--out", default=OUT_DEFAULT,
                    help=f"manifest path (default {OUT_DEFAULT})")
    args = ap.parse_args(argv)

    cfg = load_dev_slate_config()
    print("Frozen development-slate rule (OA Plan 2 v2, V0; corrected "
          "2026-08-01, finding 9):")
    print(f"  {THE_RULE}")
    print(f"  window: {DEV_WINDOW[0]} .. {DEV_WINDOW[1]}")
    print(f"  excluded: the {len(scored_fixture_ids())} fixtures of "
          f"{SCORED_INVENTORY_PATH.name} (exact membership, never calendar "
          "windows)")
    for pool, start, end in SCORED_POOL_WINDOWS:
        print(f"  scored pool {pool} spans {start} .. {end} (informational; "
              "not an exclusion)")
    print(f"  competitions (config): {cfg.get('competitions') or 'NOT YET SET'}")
    print(f"  n_dev (config): {cfg.get('n_dev') if cfg.get('n_dev') else 'NOT YET SET'}")

    drift = _config_matches_constants(cfg)
    if drift:
        print("ABORT: config/config.yaml has drifted from the frozen "
              "constants: " + "; ".join(drift), file=sys.stderr)
        return 1

    missing = []
    if not cfg.get("competitions"):
        missing.append(
            "oa_dev_slate.competitions (chosen by coverage evidence: the "
            "`oa_probe.py --slate` mini-probe, then G-B)")
    if not cfg.get("n_dev"):
        missing.append(
            "oa_dev_slate.n_dev (sized against the G-B cap by the same "
            "mini-probe)")
    missing.append(
        "per-fixture coverage admissibility (produced by the V4/G-B "
        "acquisition run; there is no way to know it before the odds exist)")
    if args.emit:
        print("ABORT: cannot emit the manifest yet — still missing:\n  - "
              + "\n  - ".join(missing), file=sys.stderr)
        return 1
    print("\nStatus: STUB. Still missing before `--emit` can run:")
    for item in missing:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
