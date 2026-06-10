#!/usr/bin/env python
"""One-command idempotent daily forecast update (Phase 0). ZERO Odds-API credits.

ingest (martj42, cached/pinned) -> leakage gate -> build_snapshot (panel+fit+20k sim via the
content-addressed caches; same-day re-run = cache HITs, byte-identical bundle) -> stage viewer
bundles -> provenance summary + run log. Designed for ``nohup``; safe to re-run any time.
The value scan (scripts/scan_value.py) is SEPARATE and manual — this script NEVER touches odds.

This is a THIN operator harness: it adds NO model/pipeline behaviour. Every number in the bundle
is produced by the unchanged, already-leakage-gated orchestrator ``dashboard.build.build_snapshot``.
The store-assembly + leakage gate below mirror ``scripts/build_real_snapshot.py`` verbatim,
parameterized by ``--cutoff`` (default: today 00:00 UTC).

RUN: ``PYTHONPATH=src .venv/bin/python scripts/daily_update.py [--cutoff 2026-06-12T00:00:00Z] [--dry-run]``
(NEVER ``uv run`` a script — it breaks the editable install.)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from wcmodel.config import load_config
from wcmodel.dashboard.build import build_snapshot
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.results import load_results
from wcmodel.data.store import BitemporalStore

# The canonical content-addressed source cache (the real martj42 parquet lives here).
CACHE_DIR = Path("data/cache")
# The viewer-staging script (already picks the newest bundle dir by mtime).
STAGE_CWD = Path("dashboard-ui")
STAGE_SCRIPT = "scripts/copy-bundle.mjs"
# The run log (logs/ is gitignored). One JSON line appended per successful run.
DEFAULT_LOG_PATH = Path("logs/daily_update.jsonl")

# The ordered step plan (names only) — printed by --dry-run, asserted by the orchestration tests.
STEP_PLAN = ["ingest", "gate", "snapshot", "stage", "provenance"]


def _today() -> str:
    """Today's date in UTC as ``YYYY-MM-DD`` (monkeypatched in tests to freeze 'today')."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _resolve_cutoff(cutoff: str | None) -> str:
    """The snapshot as-of instant. Default: today 00:00 UTC (``YYYY-MM-DDT00:00:00Z``)."""
    if cutoff:
        return cutoff
    return f"{_today()}T00:00:00Z"


def step_ingest(cache_dir: Path) -> BitemporalStore:
    """Assemble the real bitemporal store from martj42 via the canonical load path.

    Mirrors ``build_real_snapshot.build_real_store``: a fresh, isolated ``BitemporalStore``
    loaded via ``data.sources.results.load_results`` (fetch-from-cache -> normalize -> attach
    shootout winners -> POINT_IN_TIME write keyed on ``match_id``). Keyed writes make re-ingest
    duplicate-free; the pinned-commit cache makes the fetch a no-op when already cached."""
    store_root = Path(tempfile.mkdtemp(prefix="wc-daily-update-store-"))
    print(f"[ingest] assembling real martj42 store at {store_root} ...")
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=cache_dir)
    print("[ingest] store assembled.")
    return store


def step_gate(store: BitemporalStore, cutoff: str) -> None:
    """LEAKAGE GUARD (fail-loud). Re-read the store at the cutoff and assert no post-cutoff
    result leaked into the training set. Mirrors ``build_real_snapshot.verify_cutoff_gate``
    verbatim (parameterized by ``cutoff``): a build can never silently train on a future
    result. Raises ``SystemExit`` if any read row is dated on/after the cutoff."""
    asof = store.read("results", cutoff=cutoff)
    dates = pd.to_datetime(asof["date"])
    cut_day = pd.Timestamp(cutoff).tz_convert("UTC").tz_localize(None).normalize()
    leaked = asof[dates >= cut_day]
    played = valid_played_results(asof)
    played_max = pd.to_datetime(played["date"]).max()
    print(f"[gate] read(results, cutoff={cutoff}): {len(asof)} rows; "
          f"max date = {dates.max()}; max VALID-PLAYED date = {played_max}")
    if len(leaked) > 0:
        print(f"[gate] ABORT: {len(leaked)} row(s) dated >= cutoff leaked into the "
              f"as-of read — refusing to build a contaminated snapshot:", file=sys.stderr)
        print(leaked[["date", "home_team", "away_team", "home_score", "away_score"]]
              .head(20).to_string(), file=sys.stderr)
        raise SystemExit(1)
    if played_max >= cut_day:
        print(f"[gate] ABORT: max valid-played date {played_max} is not strictly before "
              f"the cutoff {cut_day}.", file=sys.stderr)
        raise SystemExit(1)
    print("[gate] OK: every training row is strictly before the cutoff.")


def step_snapshot(cutoff: str, store: BitemporalStore, cfg: dict) -> Path:
    """Build the FULL dashboard bundle at ``cutoff``. Mirrors ``build_real_snapshot.main``'s
    ``build_snapshot(...)`` call verbatim (parameterized by ``cutoff``): the real 2026 draw
    (``tournament=None``), NO odds feed (``items=[]`` -> every edge coverage-gaps, bundle
    NON-REAL), no backtest records, the production config. ``build_snapshot`` internally
    composes panel -> fit -> 20k-sim -> gated-write through the content-addressed caches, so a
    same-day re-run is a cache HIT and the bundle is byte-identical."""
    out_root = Path(cfg["dashboard"]["output_dir"])  # data/dashboard (gitignored)
    print(f"[snapshot] build_snapshot(cutoff={cutoff}) over the verified 2026 draw — "
          "this takes minutes (48-team posterior fit + 20k-sim MC) ...")
    bundle = build_snapshot(
        cutoff,
        store=store,
        config=cfg,
        tournament=None,        # -> config/tournament_2026.yaml (the verified 48-team draw)
        items=[],               # NO real odds -> every edge coverage-gaps; bundle NON-REAL
        backtest_records=None,  # -> track.json is an honest coverage_gap
        out_root=out_root,
    )
    print(f"[snapshot] bundle written to: {bundle}")
    return bundle


def step_stage() -> None:
    """Stage the newest bundle into the viewer's ``public/bundle/`` via the existing node
    script (it already picks the newest bundle dir by mtime). A thin subprocess shell-out —
    no new staging logic here."""
    print(f"[stage] node {STAGE_SCRIPT} (cwd={STAGE_CWD}) ...")
    subprocess.run(["node", STAGE_SCRIPT], cwd=str(STAGE_CWD), check=True)
    print("[stage] staged newest bundle into dashboard-ui/public/bundle/.")


def step_provenance(bundle_path: Path, *, log_path: Path = DEFAULT_LOG_PATH,
                    duration_s: float | None = None) -> dict:
    """Read back ``<bundle>/meta.json``, print the provenance summary, and append ONE JSON
    line to the run log. Returns the appended row (so the caller can print a summary)."""
    meta = json.loads((Path(bundle_path) / "meta.json").read_text())
    prov = meta.get("provenance", {})
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cutoff": prov.get("as_of"),
        "bundle": str(bundle_path),
        "posterior_key": prov.get("posterior_key"),
        "git": prov.get("git"),
        "n_sims": prov.get("n_sims"),
        "duration_s": duration_s,
    }
    print(f"[provenance] as_of={row['cutoff']} posterior_key={row['posterior_key']} "
          f"git={row['git']} n_sims={row['n_sims']}")
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"[provenance] run-log line appended to {log_path}")
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Idempotent daily forecast update (zero Odds-API credits).")
    ap.add_argument("--cutoff", default=None,
                    help="as-of instant YYYY-MM-DDT00:00:00Z (default: today 00:00 UTC)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved plan and exit 0 — no network, no fit, no writes")
    args = ap.parse_args(argv)
    cutoff = _resolve_cutoff(args.cutoff)

    if args.dry_run:
        print("[daily_update] DRY-RUN — printing the plan, executing nothing.")
        print(f"  cutoff   : {cutoff}")
        print(f"  store    : fresh tempdir (martj42 cache: {CACHE_DIR})")
        print(f"  out_root : {load_config()['dashboard']['output_dir']}")
        print(f"  log      : {DEFAULT_LOG_PATH}")
        print(f"  steps    : {' -> '.join(STEP_PLAN)}")
        return 0

    started = time.monotonic()
    cfg = load_config()
    print(f"[daily_update] cutoff={cutoff}; steps: {' -> '.join(STEP_PLAN)}")
    store = step_ingest(CACHE_DIR)
    step_gate(store, cutoff)
    bundle = step_snapshot(cutoff, store, cfg)
    step_stage()
    step_provenance(bundle, duration_s=round(time.monotonic() - started, 1))
    print("[daily_update] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
