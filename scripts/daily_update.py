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

import httpx
import pandas as pd

from wcmodel.config import load_config
from wcmodel.dashboard.build import build_snapshot
from wcmodel.data.features import valid_played_results
from wcmodel.data.sources.results import MARTJ42_COMMIT, load_results
from wcmodel.data.store import BitemporalStore

# The canonical content-addressed source cache (the real martj42 parquet lives here).
CACHE_DIR = Path("data/cache")
# The viewer-staging script (already picks the newest bundle dir by mtime).
STAGE_CWD = Path("dashboard-ui")
STAGE_SCRIPT = "scripts/copy-bundle.mjs"
# The run log (logs/ is gitignored). One JSON line appended per successful run.
DEFAULT_LOG_PATH = Path("logs/daily_update.jsonl")

# The reproducibility anchor: the source-pinned martj42 commit. Default ingest uses
# it (byte-identical). ``--latest`` resolves a fresher sha at RUNTIME and threads it
# as an override — it NEVER edits this or the source constant.
PINNED_COMMIT = MARTJ42_COMMIT
# The free GitHub commits API (NOT the Odds API). One GET resolves the newest
# ``master`` sha. This is the SAME pattern the P0 Task-1 pin-bump used by hand.
MARTJ42_COMMITS_API = (
    "https://api.github.com/repos/martj42/international_results/commits/master"
)

# The ordered step plan (names only) — printed by --dry-run, asserted by the orchestration tests.
STEP_PLAN = ["ingest", "gate", "snapshot", "stage", "provenance"]


def resolve_latest_commit() -> str:
    """Resolve the newest martj42 ``master`` commit sha via ONE free GitHub-API GET.

    This is the runtime automation of the manual P0 Task-1 pin-bump (it hits
    ``api.github.com/.../commits/master`` — the FREE GitHub API, never the Odds
    API). Raises on any transport/HTTP/shape error so the caller can ABORT loudly;
    it must NEVER return the stale pin while claiming freshness."""
    resp = httpx.get(
        MARTJ42_COMMITS_API,
        timeout=10.0,
        follow_redirects=True,
        headers={"Accept": "application/vnd.github+json"},
    )
    resp.raise_for_status()
    sha = resp.json().get("sha")
    if not sha or not isinstance(sha, str):
        raise ValueError(
            f"GitHub commits API returned no 'sha' (got: {resp.json()!r:.200})")
    return sha


def _today() -> str:
    """Today's date in UTC as ``YYYY-MM-DD`` (monkeypatched in tests to freeze 'today')."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _resolve_cutoff(cutoff: str | None) -> str:
    """The snapshot as-of instant. Default: today 00:00 UTC (``YYYY-MM-DDT00:00:00Z``)."""
    if cutoff:
        return cutoff
    return f"{_today()}T00:00:00Z"


def step_ingest(cache_dir: Path, *, commit: str | None = None) -> BitemporalStore:
    """Assemble the real bitemporal store from martj42 via the canonical load path.

    Mirrors ``build_real_snapshot.build_real_store``: a fresh, isolated ``BitemporalStore``
    loaded via ``data.sources.results.load_results`` (fetch-from-cache -> normalize -> attach
    shootout winners -> POINT_IN_TIME write keyed on ``match_id``). Keyed writes make re-ingest
    duplicate-free; the pinned-commit cache makes the fetch a no-op when already cached.

    ``commit`` (default ``None`` -> the source pin) is the RUNTIME override threaded
    straight into ``load_results`` — the same sha used for the cache key + the store's
    ``source_version``. No constant is mutated."""
    store_root = Path(tempfile.mkdtemp(prefix="wc-daily-update-store-"))
    print(f"[ingest] assembling real martj42 store at {store_root} "
          f"(commit={commit or PINNED_COMMIT}) ...")
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=cache_dir, commit=commit)
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
                    duration_s: float | None = None,
                    commit: str | None = None,
                    commit_source: str | None = None) -> dict:
    """Read back ``<bundle>/meta.json``, print the provenance summary, and append ONE JSON
    line to the run log. Returns the appended row (so the caller can print a summary).

    ``commit`` is the martj42 sha actually ingested and ``commit_source`` is how it
    was chosen (``"pinned"`` or ``"latest-resolved"``) — recorded for provenance
    honesty so the log never claims freshness it didn't fetch."""
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
        "commit": commit,
        "commit_source": commit_source,
    }
    print(f"[provenance] as_of={row['cutoff']} posterior_key={row['posterior_key']} "
          f"git={row['git']} n_sims={row['n_sims']} "
          f"martj42_commit={row['commit']} ({row['commit_source']})")
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
    ap.add_argument("--latest", action="store_true",
                    help="resolve the freshest martj42 master commit via ONE GitHub-API "
                         "call (free, NOT the Odds API) and ingest it, instead of the "
                         "source pin. Aborts loudly on any API error — never silently "
                         "falls back to the stale pin.")
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
        if args.latest:
            # NO API call under --dry-run: only announce that a real run WOULD resolve.
            print(f"  commit   : --latest -> WOULD resolve newest master via "
                  f"{MARTJ42_COMMITS_API} (no call made in dry-run)")
        else:
            print(f"  commit   : {PINNED_COMMIT} (pinned)")
        return 0

    # Resolve the commit override BEFORE any expensive step. Under --latest a clean
    # API failure must ABORT here (non-zero exit) rather than fall back to the pin.
    if args.latest:
        print(f"[daily_update] --latest: resolving newest martj42 master commit via "
              f"{MARTJ42_COMMITS_API} ...")
        try:
            commit = resolve_latest_commit()
        except Exception as exc:  # transport / HTTP / shape error
            print(f"[daily_update] ABORT: could not resolve the latest martj42 commit "
                  f"({type(exc).__name__}: {exc}). Re-run WITHOUT --latest to use the "
                  f"pin ({PINNED_COMMIT}), or bump MARTJ42_COMMIT manually. Refusing to "
                  f"silently fall back to the stale pin while claiming freshness.",
                  file=sys.stderr)
            raise SystemExit(1)
        commit_source = "latest-resolved"
        if commit == PINNED_COMMIT:
            print(f"[daily_update] --latest resolved {commit} == the current pin — no "
                  f"new data; proceeding (idempotent).")
        else:
            print(f"[daily_update] --latest resolved {commit} (pin is {PINNED_COMMIT}).")
    else:
        commit = PINNED_COMMIT
        commit_source = "pinned"

    started = time.monotonic()
    cfg = load_config()
    print(f"[daily_update] cutoff={cutoff}; martj42_commit={commit} ({commit_source}); "
          f"steps: {' -> '.join(STEP_PLAN)}")
    store = step_ingest(CACHE_DIR, commit=commit)
    step_gate(store, cutoff)
    bundle = step_snapshot(cutoff, store, cfg)
    step_stage()
    step_provenance(bundle, duration_s=round(time.monotonic() - started, 1),
                    commit=commit, commit_source=commit_source)
    print("[daily_update] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
