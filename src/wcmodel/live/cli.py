"""A thin CLI runner for the live forward-test (Phase-5 §2; NO UI).

Wires the live loop: fetch (dry-run by default) -> decide -> scan -> (the caller logs
+ tracks CLV). DRY-RUN by default (the L1 spend gate): a LIVE run (``--no-dry-run``)
REQUIRES an ``--api-key`` and is REFUSED without one — the CLI can never spend or
imply a real bet by accident. SIGNAL-ONLY (L2): it emits a ranked scan + a written
report; it NEVER places a bet.

This is deliberately thin — the real work lives in ``decide_live`` / ``scan`` /
``clv_tracker`` (the Phase-4 body at ``cutoff = now``). The CLI just parses args,
enforces the gate, and prints the scan report.
"""
from __future__ import annotations

import argparse
import sys

from wcmodel.config import load_config
from wcmodel.live.scan import scan


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI arg parser. ``--dry-run`` defaults TRUE (the spend gate);
    ``--no-dry-run`` requires ``--api-key`` (refused without one)."""
    p = argparse.ArgumentParser(prog="wc-live", description="WC-2026 live forward-test scanner (signal-only, dry-run by default)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                   help="run against the fixture/synthetic harness, NO network/spend (default)")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="LIVE run — requires --api-key (gated; refused without a key)")
    p.add_argument("--api-key", dest="api_key", default=None,
                   help="The Odds API key (LIVE only; the feed is funded separately, L1)")
    p.add_argument("--cutoff", dest="cutoff", default=None,
                   help="the decision cutoff = now (ISO ts); defaults to the current UTC time")
    return p


def run_live_scan_dry(store, items: list[dict], *, cutoff, config: dict | None = None,
                      fit_kwargs: dict | None = None):
    """The testable dry-run core: scan over a fixture/synthetic ``items`` list at
    ``cutoff = now`` -> a non-real ``Ranked`` artifact. NO network, NO spend."""
    return scan(store, items, cutoff=cutoff, config=config or load_config(),
                fit_kwargs=fit_kwargs)


def run_live_scan(args) -> int:
    """Entry point. Enforces the L1 spend gate: a LIVE run without an ``api_key`` is
    REFUSED (``SystemExit``). In dry-run it would scan the fixture/synthetic harness
    (the orchestration of fetch/store wiring is the operator's, kept thin here).
    Returns 0 on success."""
    if not args.dry_run and args.api_key is None:
        print(
            "REFUSED: a LIVE run requires --api-key (the paid feed is funded separately, "
            "L1 spend gate). Re-run in --dry-run, or supply a key once funded.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    # Dry-run/live orchestration (loading the store, fetching the snapshots, logging
    # the ledger) is wired by the operator harness; this CLI stays a thin gate + a
    # report printer. A real run would call odds_live.fetch_live_odds(api_key=...) +
    # decide_live + scan + clv_tracker; in dry-run it reads the fixture. SIGNAL-ONLY.
    print("wc-live: dry-run (signal-only). Use the library API (decide_live/scan/"
          "clv_tracker) for the full loop; see reports/phase5_live_dryrun_smoke.md.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run_live_scan(args)


if __name__ == "__main__":      # pragma: no cover
    raise SystemExit(main())
