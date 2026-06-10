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
from wcmodel.live.manual_results import (
    ingest_manual_rows,
    manual_file_sha256,
    validate_manual_csv,
)

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


def _now() -> pd.Timestamp:
    """The operator's wall-clock instant as a tz-NAIVE-UTC Timestamp (the store's
    timestamp convention). Stamped ONCE per run in ``main`` and threaded into BOTH
    the manual-cutoff rule and the manual rows' ``observed_at`` — the SAME instant,
    so 'visible at the resolved cutoff' is checkable, never racy. Monkeypatched in
    tests to freeze time."""
    return pd.Timestamp(datetime.now(timezone.utc)).tz_convert("UTC").tz_localize(None)


def _resolve_cutoff(cutoff: str | None) -> str:
    """The snapshot as-of instant. Default: today 00:00 UTC (``YYYY-MM-DDT00:00:00Z``)."""
    if cutoff:
        return cutoff
    return f"{_today()}T00:00:00Z"


def _resolve_cutoff_with_manual(cutoff: str | None, manual_rows, *,
                                now: str | pd.Timestamp | None = None) -> str:
    """Resolve the as-of cutoff, accounting for the manual-results CONDITIONING rule.

    THE LOAD-BEARING CORRECTNESS DETAIL. Both the training panel (``features.build``)
    and the sim conditioning (``sim.run._played_as_of``) filter results with the
    strict, DAY-FLOORED predicate ``date < cutoff_day`` (``cutoff_day =
    cutoff.normalize()``). So a match played on day ``D`` (``date = D 00:00``) is NOT
    ``< D 00:00`` — it is EXCLUDED at the default cutoff ``D 00:00`` AND at
    ``cutoff = now`` (whose ``cutoff_day`` is still ``D 00:00``). To make a day-``D``
    match condition the sim, ``cutoff_day`` must be STRICTLY AFTER ``D``, i.e.
    ``cutoff >= D+1 00:00 UTC``.

    Therefore, when manual rows are present and the operator did NOT pass an explicit
    ``--cutoff``, we IMPLY ``cutoff = (max manual-row date).normalize() + 1 day`` at
    ``00:00:00Z`` so TODAY's finals condition. This stays leakage-safe: nothing dated
    on/after that cutoff day exists (the manual rows ARE the latest results), and the
    leakage gate still asserts the max valid-played date is strictly before it.

    BOTH bitemporal axes must clear the cutoff (the 2026-06-10 dress-rehearsal
    finding). The PIT read (``store.read(cutoff)``) returns only rows with
    ``observed_at <= cutoff`` — and a manual row's ``observed_at`` is the ENTRY
    instant ``now``. A result entered AFTER the date-implied midnight (a 02:00Z
    kickoff hand-entered at 05:00Z — routine at a North-American World Cup) would be
    INVISIBLE at that cutoff: gate green, bundle silently UNconditioned. So the
    implied cutoff is the next UTC midnight after BOTH the latest match date AND
    ``now``; day-flooring keeps training/conditioning correct either way.

    If the operator DID pass an explicit ``--cutoff`` that is NOT strictly after some
    manual row's date, that row can NEVER condition at the chosen cutoff — an operator
    error, so we FAIL LOUD (``SystemExit``) rather than silently no-op. Likewise an
    explicit ``--cutoff`` EARLIER than the entry instant ``now``: the rows' observed_at
    would be past the PIT read — same silent hole, same loud abort."""
    if not manual_rows:
        return _resolve_cutoff(cutoff)
    now_ts = _now() if now is None else pd.Timestamp(now)
    if now_ts.tz is not None:
        now_ts = now_ts.tz_convert("UTC").tz_localize(None)
    max_date = max(pd.Timestamp(r.date).normalize() for r in manual_rows)
    by_date = max_date + pd.Timedelta(days=1)
    if cutoff is None:
        by_entry = now_ts.normalize() + pd.Timedelta(days=1)  # next UTC midnight > now
        implied_ts = max(by_date, by_entry)
        implied = implied_ts.strftime("%Y-%m-%dT00:00:00Z")
        if implied_ts == by_date:
            print(f"[manual] --manual-results given without --cutoff: implying cutoff="
                  f"{implied} (= max manual date {max_date.date()} + 1 day) so today's "
                  f"played results CONDITION the sim (strict `date < cutoff_day` rule).")
        else:
            print(f"[manual] --manual-results given without --cutoff: LATE ENTRY — now "
                  f"({now_ts}) is past (max manual date)+1d ({by_date.date()} 00:00Z), so "
                  f"the rows' observed_at would be INVISIBLE to the PIT read there. "
                  f"Implying cutoff={implied} (next UTC midnight after the entry time) so "
                  f"the hand-entered results are BOTH PIT-visible AND condition the sim.")
        return implied
    # Explicit cutoff: enforce it is strictly after EVERY manual row's date, else the
    # row would be silently excluded from conditioning — fail loud.
    cut = pd.Timestamp(cutoff)
    if cut.tz is not None:
        cut = cut.tz_convert("UTC").tz_localize(None)
    cut_day = cut.normalize()
    if cut_day <= max_date:
        print(f"[manual] ABORT: --cutoff {cutoff} (day {cut_day.date()}) is not strictly "
              f"after the latest manual-row match date {max_date.date()} — that result "
              f"can NEVER condition the sim (the strict `date < cutoff_day` rule excludes "
              f"a same-day-or-later match). Use --cutoff >= {(max_date + pd.Timedelta(days=1)).date()}"
              f"T00:00:00Z, or omit --cutoff to auto-imply it.", file=sys.stderr)
        raise SystemExit(2)
    # Explicit cutoff: enforce it is at/after the entry instant, else the manual rows
    # (observed_at = now) are invisible to the PIT read — silently unconditioned.
    if cut < now_ts:
        print(f"[manual] ABORT: --cutoff {cutoff} is EARLIER than the entry time "
              f"({now_ts}). The manual rows are written observed_at=now, and the "
              f"bitemporal PIT read at the cutoff only sees observed_at <= cutoff — "
              f"the hand-entered results would be INVISIBLE and the bundle would build "
              f"silently UNconditioned. Use --cutoff >= now, or omit --cutoff to "
              f"auto-imply the next UTC midnight.", file=sys.stderr)
        raise SystemExit(2)
    return cutoff


def step_ingest(cache_dir: Path, *, commit: str | None = None,
                manual_results: str | Path | None = None,
                manual_observed_at: str | pd.Timestamp | None = None,
                tournament: dict | None = None) -> BitemporalStore:
    """Assemble the real bitemporal store from martj42 via the canonical load path.

    Mirrors ``build_real_snapshot.build_real_store``: a fresh, isolated ``BitemporalStore``
    loaded via ``data.sources.results.load_results`` (fetch-from-cache -> normalize -> attach
    shootout winners -> POINT_IN_TIME write keyed on ``match_id``). Keyed writes make re-ingest
    duplicate-free; the pinned-commit cache makes the fetch a no-op when already cached.

    ``commit`` (default ``None`` -> the source pin) is the RUNTIME override threaded
    straight into ``load_results`` — the same sha used for the cache key + the store's
    ``source_version``. No constant is mutated.

    ``manual_results`` (default ``None``) is a validated-on-read CSV of hand-entered
    played WC fixtures threaded — AFTER the martj42 assembly — through the EXISTING
    leakage-safe ``ingest_live_result`` POINT_IN_TIME path (``manual_observed_at`` =
    the operator's entry time ``now``). This is the matchday-1 fallback: it composes
    with ``--latest``/``--cutoff`` because it runs after ``load_results``, regardless
    of which commit the martj42 fetch used. Returns the store; the manual row count is
    available via the caller's pre-validation (``validate_manual_csv``)."""
    store_root = Path(tempfile.mkdtemp(prefix="wc-daily-update-store-"))
    print(f"[ingest] assembling real martj42 store at {store_root} "
          f"(commit={commit or PINNED_COMMIT}) ...")
    store = BitemporalStore(root=store_root)
    load_results(store, cache_dir=cache_dir, commit=commit)
    if manual_results is not None:
        # Validate the WHOLE file (fail-loud) BEFORE writing any row, then thread each
        # validated row through ingest_live_result (observed_at = the operator's now).
        rows = validate_manual_csv(manual_results, tournament=tournament)
        n = ingest_manual_rows(store, rows, observed_at=manual_observed_at)
        print(f"[ingest] manual results: ingested {n} hand-entered row(s) from "
              f"{manual_results} (observed_at={manual_observed_at}).")
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
                    commit_source: str | None = None,
                    manual_rows: int = 0,
                    manual_file_sha: str | None = None) -> dict:
    """Read back ``<bundle>/meta.json``, print the provenance summary, and append ONE JSON
    line to the run log. Returns the appended row (so the caller can print a summary).

    ``commit`` is the martj42 sha actually ingested and ``commit_source`` is how it
    was chosen (``"pinned"`` or ``"latest-resolved"``) — recorded for provenance
    honesty so the log never claims freshness it didn't fetch.

    ``manual_rows`` / ``manual_file_sha`` record the matchday-1 manual fallback: the
    count of hand-entered results threaded into the store and the sha256 of the CSV
    file (``None``/0 when ``--manual-results`` was not used) — so a run that hand-
    entered scores is auditable."""
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
        "manual_rows": manual_rows,
        "manual_file_sha256": manual_file_sha,
    }
    print(f"[provenance] as_of={row['cutoff']} posterior_key={row['posterior_key']} "
          f"git={row['git']} n_sims={row['n_sims']} "
          f"martj42_commit={row['commit']} ({row['commit_source']}) "
          f"manual_rows={row['manual_rows']} manual_file_sha256={row['manual_file_sha256']}")
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
    ap.add_argument("--manual-results", default=None, metavar="CSV",
                    help="hand-entered played WC fixtures (matchday-1 fallback, "
                         "independent of upstream timing). STRICT CSV: "
                         "date,home_team,away_team,home_score,away_score[,shootout_winner]. "
                         "Threaded through the leakage-safe ingest_live POINT_IN_TIME path "
                         "AFTER the martj42 assembly so the sim conditions on them. With no "
                         "--cutoff, implies the next UTC midnight after BOTH the max manual "
                         "date AND your entry time, so today's finals condition (strict "
                         "date<cutoff_day rule) and stay PIT-visible (observed_at<=cutoff).")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved plan and exit 0 — no network, no fit, no writes")
    args = ap.parse_args(argv)

    # Pre-VALIDATE the manual CSV up-front (fail-loud BEFORE anything else) so both the
    # dry-run plan and the cutoff auto-resolution can see the rows. This also makes a
    # bad CSV abort with a clear message and a non-zero exit, never a partial run.
    manual_rows = None
    manual_file_sha = None
    if args.manual_results is not None:
        manual_rows = validate_manual_csv(args.manual_results)
        manual_file_sha = manual_file_sha256(args.manual_results)

    # Resolve the cutoff, accounting for the manual-conditioning rule (the load-bearing
    # `date < cutoff_day` detail — see _resolve_cutoff_with_manual). With manual rows and
    # no explicit --cutoff, this implies (max manual date)+1 day so today's finals condition.
    # ONE wall-clock stamp per run: the SAME instant is the manual rows' observed_at
    # AND the `now` the cutoff rule guards against — so "PIT-visible at the resolved
    # cutoff" holds by construction (no second now() call can race past the cutoff).
    run_now = _now()
    cutoff = _resolve_cutoff_with_manual(args.cutoff, manual_rows, now=run_now)

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
        if manual_rows is not None:
            print(f"  manual   : {args.manual_results} -> {len(manual_rows)} validated "
                  f"row(s) WOULD be ingested (sha256={manual_file_sha}); no ingest in dry-run:")
            for r in manual_rows:
                tag = "KO" if r.is_knockout else "group"
                so = f" shootout_winner={r.shootout_winner}" if r.shootout_winner else ""
                print(f"             - [{tag}] {r.date} {r.home_team} {r.home_score}-"
                      f"{r.away_score} {r.away_team}{so}")
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
    # The operator's entry time `now` — the manual rows' observed_at (the real-ingest
    # vector: a result is observed when hand-entered; valid_as_of stays the match date).
    manual_observed_at = run_now.isoformat()
    print(f"[daily_update] cutoff={cutoff}; martj42_commit={commit} ({commit_source}); "
          f"manual_rows={0 if manual_rows is None else len(manual_rows)}; "
          f"steps: {' -> '.join(STEP_PLAN)}")
    store = step_ingest(CACHE_DIR, commit=commit,
                        manual_results=args.manual_results,
                        manual_observed_at=manual_observed_at)
    step_gate(store, cutoff)
    bundle = step_snapshot(cutoff, store, cfg)
    step_stage()
    step_provenance(bundle, duration_s=round(time.monotonic() - started, 1),
                    commit=commit, commit_source=commit_source,
                    manual_rows=0 if manual_rows is None else len(manual_rows),
                    manual_file_sha=manual_file_sha)
    print("[daily_update] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
