#!/usr/bin/env python
"""Build a REAL WC-2026 dashboard snapshot at a single cutoff, from the EXISTING pipeline.

OPS-ONLY SCRIPT. This file adds NO model/pipeline behaviour — it is a thin operator
harness that ASSEMBLES the real bitemporal store from the canonical martj42 source and
then calls the existing, already-leakage-gated orchestrator ``dashboard.build.build_snapshot``.
Every number in the bundle is produced by the unchanged pipeline (posterior fit -> MC sim ->
schedule/why assembly); this script only wires the real store + the verified 2026 draw into
that orchestrator and prints the resulting bundle path.

WHAT IT DOES (and nothing more)
-------------------------------
1. Build a fresh ``BitemporalStore`` and load the REAL martj42 international results into it
   via the canonical ``data.sources.results.load_results`` (fetch-from-cache -> normalize ->
   attach shootout winners -> ``store.write(..., POINT_IN_TIME, keys=["match_id"])``). This is
   the SAME write path Phase-1 and the tests use; the store therefore enforces the bitemporal
   ``observed_at <= cutoff AND valid_as_of <= cutoff`` read gate.
2. Call ``build_snapshot`` with:
     * ``tournament=None``  -> the verified ``config/tournament_2026.yaml`` 48-team draw,
     * ``items=[]``         -> NO odds feed (there are no real odds), so every edge is a
                               coverage_gap and the whole bundle is fail-safe-tainted NON-REAL,
     * ``backtest_records=None`` -> ``track.json`` is an honest coverage_gap,
     * ``config=load_config()``  -> the production config (n_sims, seed, model block, ...),
     * ``out_root=data/dashboard`` (gitignored).

LEAKAGE (the binding rule). The martj42 cache parquet contains rows dated through 2026-06-27
(the WC-2026 GROUP FIXTURES as schedule rows — NaN scores — not played results). The snapshot
at ``cutoff=2026-06-07`` must use ONLY rows knowable at the cutoff. That gate is NOT in this
script: it is ``store.read("results", cutoff)`` (``observed_at/valid_as_of <= cutoff``) plus the
strict ``date < cutoff_day`` + valid-played filter inside ``features.build`` / ``sim.run``. The
verification at the bottom RE-READS the store at the cutoff and asserts the max training date is
strictly before the cutoff and that no future WC fixture leaks in — fail-loud if it ever does.

WC GROUP FIXTURES — NOT ingested into the store. ``build_snapshot`` reads the bracket + the
group fixtures straight from the tournament dict (``sim.run._fixture_dates`` /
``dashboard.build.build_schedule``); the per-cutoff sim conditioning matches played results to
fixtures by ``(home, away, date)`` against the store, and at this cutoff NO WC fixture is played
yet, so nothing needs to be in the store for the schedule/forecast/why path. We therefore do
NOT call ``ingest_wc_group_fixtures`` (it is only relevant mid-tournament, to condition on
played WC results). Scoreline + progression come from the posterior + the YAML bracket; xG /
rest_days honestly coverage-gap on these future fixtures (no StatsBomb / no played row).

RUN: ``PYTHONPATH=src uv run python scripts/build_real_snapshot.py``
(Expect minutes: a 48-team posterior fit + a 20k-sim Monte-Carlo tournament.)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

from wcmodel.config import load_config
from wcmodel.dashboard.build import build_snapshot
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore

# The snapshot as-of instant. UTC ``Z`` form so the store's tz-coercion path is exercised.
CUTOFF = "2026-06-07T00:00:00Z"
# The canonical content-addressed source cache (the real martj42 parquet lives here).
CACHE_DIR = Path("data/cache")


def build_real_store(store_root: Path) -> BitemporalStore:
    """Assemble the real bitemporal store from martj42 via the canonical load path.

    Uses ``data.sources.results.load_results`` unchanged: it reads the pinned-commit results
    CSV from the content-addressed cache (no re-pull when cached), normalizes, attaches the
    shootout winners, and ``store.write``s as POINT_IN_TIME keyed on ``match_id`` — the exact
    write the Phase-1 ingest + the model/leakage tests use. A fresh store dir is used so the
    write is deterministic and isolated from any prior store state."""
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=CACHE_DIR)
    return store


def verify_cutoff_gate(store: BitemporalStore) -> None:
    """LEAKAGE GUARD (fail-loud). Re-read the store at the cutoff and assert no post-cutoff
    result leaked into the training set. This re-asserts at run time the same gate the fit/sim
    rely on, so a build can never silently train on a future WC result.

    Raises ``SystemExit`` if any read row is dated on/after the cutoff (the build is aborted
    BEFORE the expensive fit, with the offending evidence printed)."""
    asof = store.read("results", cutoff=CUTOFF)
    dates = pd.to_datetime(asof["date"])
    cut_day = pd.Timestamp(CUTOFF).tz_convert("UTC").tz_localize(None).normalize()
    leaked = asof[dates >= cut_day]
    played = valid_played_results(asof)
    played_max = pd.to_datetime(played["date"]).max()
    print(f"[leakage] read(results, cutoff={CUTOFF}): {len(asof)} rows; "
          f"max date = {dates.max()}; max VALID-PLAYED date = {played_max}")
    if len(leaked) > 0:
        print(f"[leakage] ABORT: {len(leaked)} row(s) dated >= cutoff leaked into the "
              f"as-of read — refusing to build a contaminated snapshot:", file=sys.stderr)
        print(leaked[["date", "home_team", "away_team", "home_score", "away_score"]]
              .head(20).to_string(), file=sys.stderr)
        raise SystemExit(1)
    if played_max >= cut_day:
        print(f"[leakage] ABORT: max valid-played date {played_max} is not strictly before "
              f"the cutoff {cut_day}.", file=sys.stderr)
        raise SystemExit(1)
    print("[leakage] OK: every training row is strictly before the cutoff "
          "(no post-cutoff WC result leaks in).")


def main() -> int:
    cfg = load_config()
    out_root = Path(cfg["dashboard"]["output_dir"])  # data/dashboard (gitignored)

    # Fresh, isolated store dir so this build is reproducible and never mutates a shared store.
    store_root = Path(tempfile.mkdtemp(prefix="wc-real-snapshot-store-"))
    print(f"[store] assembling real martj42 store at {store_root} ...")
    store = build_real_store(store_root)

    # Fail-loud leakage check BEFORE the expensive fit/sim.
    verify_cutoff_gate(store)

    print(f"[build] running build_snapshot(cutoff={CUTOFF}) over the verified 2026 draw — "
          "this takes minutes (48-team posterior fit + 20k-sim MC) ...")
    bundle = build_snapshot(
        CUTOFF,
        store=store,
        config=cfg,
        tournament=None,        # -> config/tournament_2026.yaml (the verified 48-team draw)
        items=[],               # NO real odds -> every edge coverage-gaps; bundle NON-REAL
        backtest_records=None,  # -> track.json is an honest coverage_gap
        out_root=out_root,
    )
    print(f"[done] bundle written to: {bundle}")
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
