"""A8 (d) — the command the amendment named, before any of it existed.

    PYTHONPATH=src:. .venv/bin/python -m epl.recal verify
    PYTHONPATH=src:. .venv/bin/python -m epl.recal score \\
        --directory data/epl/sim/issuances/2026_27/2026-08-21 \\
        --results <results.jsonl>

WHY THIS FILE IS THIN
---------------------
A8 (d) pre-states `epl/recal.py` and `python -m epl.recal verify` by name, and
a command nobody can find under the name the ledger gives it is a command that
gets reinvented. The *subjects* underneath it are two, and they are kept apart
because they read different things:

* :mod:`epl.recalfit` — the frozen rule and the corpus. It reads a parquet and
  knows nothing about seasons, fixtures or results.
* :mod:`epl.recalshadow` — the shadow ledger. It reads a bundle and a season,
  and knows nothing about fitting.

This module is the operator's surface over both, and it holds no arithmetic of
its own: everything it prints is computed by one of those two, which is what
keeps `simcli recal` and this command from ever answering differently.

WHAT A REFUSAL LOOKS LIKE
-------------------------
`STOP: <TypeName>: …` on stderr, exit **2** — like every other typed refusal in
this project. **A refusal an operator cannot tell from a crash teaches them to
ignore crashes**, which is the correction the A7 round had to make once and
this one makes on the way in. CI has no `data/`, so `verify` refuses there
loudly and correctly: that is its job, not a defect in it.
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from epl import matchboard, recalfit, recalshadow, season as season_mod
from epl.recalshadow import SHADOW_PATH

#: The two modes A8 (d) and the build's naming both pre-state.
MODES = ("verify", "score")

#: Everything a refusal may be. `RecalError` is A8's own base; the other two
#: are the surfaces this command delegates to, and their refusals are refusals
#: of this command just the same — a `MatchboardError` printed as a traceback
#: would be exactly the defect the STOP convention exists to stop.
REFUSALS = (recalfit.RecalError, matchboard.MatchboardError,
            season_mod.SeasonError)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m epl.recal",
        description="the dc_1x2_recal shadow ledger: score it, and verify it")
    sub = parser.add_subparsers(dest="mode", required=True)

    v = sub.add_parser("verify", help="re-derive the constant and every row")
    v.add_argument("--ledger", default=None,
                   help=f"the shadow ledger to verify (default {SHADOW_PATH})")
    v.add_argument("--corpus", default=None,
                   help=f"the pinned corpus (default {recalfit.CORPUS_PATH}). "
                        "Its sha256 is checked against the frozen digest before "
                        "anything reads it.")

    s = sub.add_parser("score", help="derive rows from a bundle and score them")
    s.add_argument("--directory", required=True,
                   help="an issuance bundle, or a matchboard document already "
                        "derived from one. `probs_raw` is copied from its "
                        "published marginals and never re-priced.")
    s.add_argument("--results", required=True,
                   help="a JSONL of results (fixture_id, home_goals, "
                        "away_goals, matchweek, ingest). Every row must ALREADY "
                        "be in the season's results ledger, which is the source "
                        "of truth for what was played; this file is a request "
                        "to score rows the ledger carries, never a second door.")
    s.add_argument("--ledger", default=None,
                   help=f"the shadow ledger to append to (default "
                        f"{SHADOW_PATH}). Append-only and idempotent by "
                        "(fixture_id, run_digest).")
    s.add_argument("--season-root", default=None,
                   help=f"where the season ledger lives (default "
                        f"{season_mod.SEASON_ROOT}).")
    return parser


def _verify(args) -> int:
    report = recalshadow.verify(args.ledger, corpus=args.corpus)
    fit = report["fit"]
    print(f"[recal] {report['arm']} / {report['rule_version']} / "
          f"{report['schema_version']}")
    print(f"[recal] corpus {fit['sha256']} — {fit['n_rows']} rows")
    print(f"[recal] a_ledger {fit['a_ledger']!r}  a_refit {fit['a_refit']!r}  "
          f"gap {fit['gap']!r} (<= {fit['param_tolerance']})")
    print(f"[recal] mean RPS at the ledger's a {fit['mean_rps_at_ledger']!r}; "
          f"at the re-fit {fit['mean_rps_at_refit']!r}")
    print(f"[recal] {report['ledger']}: {report['n_rows']} row(s) re-derived, "
          f"matchweek(s) {report['matchweeks'] or 'none'}")
    # A8 (c) + (e): this ledger reports. It decides nothing, triggers nothing
    # and gates nothing, so there is no verdict line here to be read as one.
    return 0


def _score(args) -> int:
    result = recalshadow.score_bundle(
        args.directory, args.results, ledger_path=args.ledger,
        season_root=args.season_root)
    print(f"[recal] {len(result['rows'])} row(s) scored from "
          f"{args.directory}")
    print(f"[recal] appended {result['appended']} to {result['ledger']}"
          + (f"; {result['repeated']} already filed, unchanged"
             if result["repeated"] else ""))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.mode == "verify":
            return _verify(args)
        if args.mode == "score":
            return _score(args)
    except REFUSALS as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 1                                                # pragma: no cover


__all__ = ["MODES", "REFUSALS", "SHADOW_PATH", "main"]


if __name__ == "__main__":                                  # pragma: no cover
    sys.exit(main())
