"""Thin CLI: build a dashboard snapshot. Dry-run/synthetic by default (spec §D5)."""
from __future__ import annotations

import argparse


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wc-dashboard-build",
                                description="Build a leakage-safe dashboard JSON snapshot (dry-run default)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                   help="synthetic-odds posture, NON-REAL (default)")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="real feed (GATED — requires the funded pre-flip checklist)")
    p.add_argument("--cutoff", default=None, help="as-of ISO ts; defaults to now")
    return p
