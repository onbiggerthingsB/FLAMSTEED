#!/usr/bin/env python
"""On-demand WC-2026 +EV VALUE SCANNER entry — fetch -> scan -> bundle -> write + ledger.

THE SIGNAL-ONLY VALUE BOARD. This is the thin script around the PURE scanner core
(``wcmodel.value.{scanner,bundle,types}``): de-vig the sharp (Pinnacle) line, flag where
a soft book beats it, write a provenance-stamped NON-REAL/SIGNAL-ONLY JSON bundle, and
append each bettable spot to a paper, append-only ledger. There is NO model in the edge
path (market-vs-market only) and NO bet/broker/order path anywhere — the ledger is paper.

Two layers, cleanly split so the e2e test runs with NO network:
  * ``run_scan(events, ...)`` — PURE: ``scanner.scan`` -> ``bundle.build_value_bundle`` ->
    ``bundle.gate_value`` (a violating bundle is NEVER written) -> write the bundle JSON ->
    append the bettable ValueBets to the paper ledger. Returns the bundle path.
  * ``main()`` — the on-demand fetch: load config, capture ``now`` ONCE, ONE
    ``fetch_live_odds`` per market in ``cfg.markets`` (HARD-capped by ``CallBudget``), MERGE
    events across markets by id (so each event carries both h2h + totals books), then
    ``run_scan``. The API key is read via the same ``.env`` loader and NEVER printed.

REUSE: ``scripts/scan_totals_forward.py`` helpers (``_load_env_key`` /
``_install_credit_capture`` / ``_credit_line``) and ``wcmodel.live.odds_live``
(``fetch_live_odds`` / ``CallBudget``). The settle pass (``settle_one`` /
``main_settle``) reuses ``wcmodel.live.clv_tracker.PaperClvTracker`` (paper, signal-only).

RUN: ``PYTHONPATH=src .venv/bin/python scripts/scan_value.py``  (NOT ``uv run`` — it
re-syncs and breaks the editable ``wcmodel`` install).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# `scripts` is not an importable package, so reuse scan_totals_forward's verified helpers by
# loading it as a module (the same six-line .env loader + httpx credit-capture hook). Done at
# import time so `main()` can call them; `run_scan` is pure and needs none of this.
import importlib.util as _ilu

_STF_PATH = Path(__file__).resolve().with_name("scan_totals_forward.py")
_stf_spec = _ilu.spec_from_file_location("scan_totals_forward", _STF_PATH)
scan_totals_forward = _ilu.module_from_spec(_stf_spec)

from wcmodel.config import load_config
from wcmodel.value import bundle as value_bundle
from wcmodel.value import scanner as value_scanner
from wcmodel.value.types import ValueConfig

#: Where the on-demand value bundles land (the viewer points at the latest).
OUT_DIR = Path("data/dashboard/value")


def _scan_ts_safe(scan_ts: str) -> str:
    """A filesystem-safe stem from an ISO scan timestamp (``:`` and ``+`` are not portable)."""
    return scan_ts.replace(":", "-").replace("+", "Z")


def run_scan(events: list[dict], *, cfg: ValueConfig, now: str, credits_used: int,
             credits_remaining: int, out_dir, ledger_path) -> Path:
    """PURE (no network): scan the events, build + GATE the bundle, write it, and append the
    bettable spots to the paper ledger. Returns the written bundle path.

    The gate runs BEFORE any write, so a bundle that violates the signal-only / NON-REAL
    invariant is NEVER persisted. The ledger is append-only (open mode ``"a"``): each call
    appends, never truncates.
    """
    out_dir = Path(out_dir)
    ledger_path = Path(ledger_path)

    result = value_scanner.scan(events, cfg=cfg, now=now)
    bundle = value_bundle.build_value_bundle(
        result, scan_ts=now, sharp=cfg.sharp_book, regions=cfg.regions,
        credits_used=credits_used, credits_remaining=credits_remaining,
    )
    # GATE before writing anything: a bundle missing the signal_only / NON-REAL stamp, or
    # carrying a malformed ValueBet node, raises here and nothing is written.
    value_bundle.gate_value(bundle)

    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / f"{_scan_ts_safe(now)}.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, default=str))

    # Append-only paper ledger: one JSON line per bettable spot. No truncation.
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a") as fh:
        for spot in result["bettable"]:
            fh.write(json.dumps(spot, default=str) + "\n")

    return bundle_path


def _merge_events_by_id(per_market: list[list[dict]]) -> list[dict]:
    """Merge the per-market event lists into ONE list keyed by event id, so each merged event
    carries the union of all markets' bookmakers (h2h + totals together).

    Each ``fetch_live_odds(market=m)`` call returns the same events but with only market ``m``
    priced per bookmaker. We union the bookmakers' ``markets`` arrays per (event, bookmaker)
    so the scanner sees both markets on one event. An event id seen in any pull is kept; its
    top-level fields come from the first pull that carried it.
    """
    merged: dict[str, dict] = {}
    for events in per_market:
        for ev in events:
            eid = ev.get("id")
            if eid is None:
                # No id to merge on — keep as a standalone event (best effort, never drop).
                merged[f"_anon_{len(merged)}"] = json.loads(json.dumps(ev))
                continue
            if eid not in merged:
                merged[eid] = json.loads(json.dumps(ev))  # deep copy: never mutate the input
                continue
            base = merged[eid]
            base_books = {bk.get("key"): bk for bk in base.get("bookmakers", []) or []}
            for bk in ev.get("bookmakers", []) or []:
                bkey = bk.get("key")
                if bkey in base_books:
                    # Union this bookmaker's markets into the already-merged one.
                    base_books[bkey].setdefault("markets", [])
                    base_books[bkey]["markets"].extend(bk.get("markets", []) or [])
                else:
                    base.setdefault("bookmakers", []).append(json.loads(json.dumps(bk)))
                    base_books[bkey] = base["bookmakers"][-1]
    return list(merged.values())


def settle_one(tracker, *, event_key, staked, entry_odds, close_odds, stake, won,
               match_type) -> None:
    """Settle ONE paper value signal via ``PaperClvTracker.log_signal`` (realized CLV +
    beat-close + paper P&L). Thin wrapper: it SUPPLIES the extra ``log_signal`` kwargs the
    paper value ledger always uses, so the caller only passes the value-bet fields.

    The extras are fixed because this is a PAPER / NON-REAL value ledger:
      * ``is_synthetic=True``    — NON-REAL until a feed is funded (so ``clv_report`` stamps
        its NOT-REAL banner; a paper number can never be mistaken for a funded one).
      * ``confederation="unknown"`` — the value scanner does not carry confederation tags;
        a real string (never a missing key) keeps the by-confederation stratifier from
        KeyError-ing while honestly labelling the tier unknown.
      * ``venue="pinnacle"`` + ``commission={"pinnacle": 0.0}`` — a fixed-odds soft bet pays
        NO exchange commission. ``settle_bet`` reads ``commission.get(venue, 0.0)``, so this
        pair yields commission 0 (gross winnings unreduced); the close benchmark IS Pinnacle.
    """
    tracker.log_signal(
        event_key=event_key, staked=staked, entry_odds=entry_odds, close_odds=close_odds,
        stake=stake, won=won, match_type=match_type,
        confederation="unknown",
        venue="pinnacle", commission={"pinnacle": 0.0},
        is_synthetic=True,
    )


def main() -> int:
    """On-demand value scan: fetch the live board (ONE call per market, HARD-capped),
    merge across markets, then run the pure scan/bundle/ledger pipeline. Key NEVER printed."""
    ap = argparse.ArgumentParser(description="On-demand +EV value scan (signal-only).")
    ap.add_argument("--out-dir", default=str(OUT_DIR),
                    help=f"Directory for the value bundle JSON (default {OUT_DIR}).")
    ap.parse_args()

    # Load the verified scan_totals_forward helpers (its module-level code is import-safe).
    _stf_spec.loader.exec_module(scan_totals_forward)

    cfg_dict = load_config()
    cfg = ValueConfig.from_config(cfg_dict)

    # Import the live-fetch primitives here so the e2e test (which never calls main) does not
    # require the network stack at import time.
    import wcmodel.live.odds_live as odds_live
    from wcmodel.live.odds_live import CallBudget, fetch_live_odds

    # Capture `now` ONCE so every market's edge ages against the same instant.
    now = datetime.now(timezone.utc).isoformat()

    print("=" * 80)
    print("ON-DEMAND +EV VALUE SCAN — WC-2026 (SIGNAL-ONLY, no bet).")
    print(f"  scan_ts = {now}")
    print(f"  sport = {cfg.sports[0]}  regions = {cfg.regions}  sharp = {cfg.sharp_book}")
    print(f"  markets = {cfg.markets}  max_calls = {cfg.max_calls_per_scan}")
    print("=" * 80)

    api_key = scan_totals_forward._load_env_key()  # read from env/.env; NEVER printed
    budget = CallBudget(max_calls_per_day=cfg.max_calls_per_scan)
    orig_get = scan_totals_forward._install_credit_capture()
    per_market: list[list[dict]] = []
    try:
        for m in cfg.markets:
            print(f"[odds] ONE live pull: market={m} (budget {budget.spent}/"
                  f"{cfg.max_calls_per_scan}) ...")
            events = fetch_live_odds(
                api_key=api_key, sport=cfg.sports[0], regions=cfg.regions, market=m,
                dry_run=False, budget=budget,
                base_backoff=cfg_dict["live"]["call_budget"]["rate_limit_backoff_seconds"],
                max_retries=cfg_dict["live"]["call_budget"]["max_retries"],
            )
            per_market.append(events)
    finally:
        odds_live.httpx.get = orig_get  # restore the unwrapped httpx.get
        del api_key                     # drop the key reference promptly

    events = _merge_events_by_id(per_market)
    print(f"[odds] pulled+merged {len(events)} events; PAID calls spent="
          f"{budget.spent}/{cfg.max_calls_per_scan}; {scan_totals_forward._credit_line()}")

    used = int(scan_totals_forward._HEADERS.get("x-requests-used", 0) or 0)
    remaining = int(scan_totals_forward._HEADERS.get("x-requests-remaining", 0) or 0)

    bundle_path = run_scan(
        events, cfg=cfg, now=now, credits_used=used, credits_remaining=remaining,
        out_dir=Path(OUT_DIR), ledger_path=Path(cfg.ledger_path),
    )

    bundle = json.loads(Path(bundle_path).read_text())
    data = bundle["data"]
    print("\n" + "=" * 80)
    print(f"VALUE BOARD — {len(data['bettable'])} bettable / {len(data['filtered'])} "
          f"filtered / {len(data['coverage_gaps'])} coverage gaps")
    print("=" * 80)
    for b in data["bettable"]:
        ln = "" if b["line"] is None else f" {b['line']}"
        print(f"  {b['event']:<34} {b['market']}{ln} {b['side']:<10} "
              f"edge={b['edge']:+.3f} @ {b['soft_odds']:.2f} ({b['soft_book']}) "
              f"stake={b['suggested_stake']:.4f}")
    print(f"\n  bundle  = {bundle_path}")
    print(f"  ledger  = {cfg.ledger_path} (paper, append-only)")
    print(f"  credits = {scan_totals_forward._credit_line()}")
    print("\nNOTE: SIGNAL-ONLY — no bet is placed; you execute manually. Edges are "
          "point-in-time; soft books move/limit fast. Key never printed.")
    return 0


if __name__ == "__main__":
    # Ensure the repo root is importable + cwd (so relative config/data paths resolve).
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    os.chdir(repo_root)
    raise SystemExit(main())
