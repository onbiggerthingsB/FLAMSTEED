#!/usr/bin/env python
"""V6 — run the FROZEN blend selection over the V5 dev ledger (OA Plan 2 v2).

Consumes the dev OOF ledger, joins the outcomes, and runs two pre-registered
procedures whose every knob was fixed before any dev odds were bought:

* ``select_w`` — monthly chronological folds, fold *t* scored with the
  candidate chosen on months < *t*, objective mean canonical RPS, grid
  w in {0.00 .. 1.00 step 0.05} x {shin, multiplicative}, ties to smaller w
  then lexicographic method. Output: the deployment ``(w, de-vig)``.
* ``oof_stacking`` — the stacking arm on the same folds and the same
  de-vig, so the two travel together into the lock.

THIS IS WHERE OUTCOMES ENTER, and nowhere earlier. V5 wrote forecasts and
provenance with no outcome column at all; the join happens here, once, at
scoring time. That ordering is the reason a V5 bug cannot be one that
peeked — and it is why this script reads the results store directly rather
than trusting anything the ledger carries.

The selection trace it writes is hash-bound into the V8 lock, so re-running
this on the same ledger must reproduce it byte for byte. It does: every
step is deterministic (fixed folds, fixed grid, fixed tie-break, an MLE
with fixed init and no RNG).
"""
# No `from __future__ import annotations`: loaded by PATH in tests.
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wcmodel.eval.arms import oof_stacking                   # noqa: E402
from wcmodel.eval.blend import select_w, write_selection_trace  # noqa: E402
from wcmodel.eval.ledger import load_ledger                  # noqa: E402

LEDGER_DEFAULT = "data/oa_dev_ledger.parquet"
MANIFEST_DEFAULT = "config/oa_dev_manifest.yaml"
STORE_DEFAULT = "data/stores/full_final"
TRACE_DEFAULT = "reports/oa_selection_trace.json"
OUT_DEFAULT = "reports/oa_select_w.md"

_OUTCOMES = ("home", "draw", "away")


class SelectionError(RuntimeError):
    """The selection cannot be run as specified."""


def outcomes_for(manifest_path, store_path) -> dict:
    """``{fixture_id: 'home'|'draw'|'away'}`` for every manifest fixture.

    Read from the RESULTS STORE by canonical match_id, never from the
    ledger — the ledger has no outcome column by construction, and this
    keeps the scoring join auditable in one place. 90-minute regulation
    scores are what the estimand is defined on (a knockout decided on
    penalties is a draw here), which is the store's own convention.
    """
    manifest = yaml.safe_load(Path(manifest_path).read_text())
    wanted = {str(f["match_id"]) for f in manifest["fixtures"]}
    frame = pd.read_parquet(Path(store_path) / "results.parquet")
    frame = frame.drop_duplicates(subset=["match_id"], keep="last")
    frame = frame[frame["match_id"].astype(str).isin(wanted)]
    out = {}
    for row in frame.itertuples(index=False):
        h, a = row.home_score, row.away_score
        if pd.isna(h) or pd.isna(a):
            continue
        h, a = float(h), float(a)
        out[str(row.match_id)] = ("home" if h > a else
                                  "away" if a > h else "draw")
    missing = sorted(wanted - set(out))
    if missing:
        raise SelectionError(
            f"{len(missing)} manifest fixture(s) have no settled score in "
            f"the store (e.g. {missing[:3]}) — the selection scores every "
            "covered fixture, so a gap is a refusal, never a silent drop")
    return out


def assemble_report(selection, stacking, *, ledger_path, trace_path) -> str:
    top = sorted(selection.grid_mean_rps, key=lambda r: r[2])[:8]
    lines = [
        "# OA blend selection — the frozen V6 procedure (OA Plan 2 v2)", "",
        f"**Deployment choice: w = {selection.w:.2f}, "
        f"de-vig = {selection.devig_method}**", "",
        f"- dev fixtures scored: **{selection.n_fixtures}**",
        f"- excluded (no admissible odds): {selection.n_excluded_no_odds}",
        f"- months: {len(selection.months)} "
        f"({selection.months[0]} .. {selection.months[-1]})",
        f"- scoreable folds (after the 2-month burn-in): "
        f"**{len(selection.folds)}**",
        f"- ledger: `{ledger_path}`",
        f"- trace (hash-bound at V8): `{trace_path}`", "",
        "## Walk-forward folds", "",
        "Each fold's candidate is chosen on the months STRICTLY BEFORE it, "
        "then scored on it — so no fold's RPS informed its own choice.", "",
        "| month | train fixtures | fold fixtures | w | de-vig | fold RPS |",
        "|---|---|---|---|---|---|",
    ]
    for f in selection.folds:
        lines.append(
            f"| {f.month} | {f.n_train_fixtures} | {f.n_fold_fixtures} | "
            f"{f.w:.2f} | {f.devig_method} | {f.fold_rps:.5f} |")
    lines += ["", "## Grid (mean canonical RPS over all dev months)", "",
              "Lower is better. w=0 IS the frozen incumbent, w=1 IS the "
              "de-vigged book, so this table brackets the whole question.",
              "", "| rank | de-vig | w | mean RPS |", "|---|---|---|---|"]
    for i, (method, w, mean) in enumerate(top, 1):
        lines.append(f"| {i} | {method} | {w:.2f} | {mean:.5f} |")
    incumbent = [r for r in selection.grid_mean_rps if r[1] == 0.0][0]
    book = sorted([r for r in selection.grid_mean_rps if r[1] == 1.0],
                  key=lambda r: r[2])[0]
    best = top[0]
    lines += [
        "", "## Reference points", "",
        f"- incumbent (w=0): **{incumbent[2]:.5f}**",
        f"- de-vigged book (w=1, {book[0]}): **{book[2]:.5f}**",
        f"- best grid point ({best[0]}, w={best[1]:.2f}): **{best[2]:.5f}**",
        f"- best vs incumbent: **{best[2] - incumbent[2]:+.5f}** RPS",
        "",
        "These are DEVELOPMENT numbers on the slate w was tuned on — they "
        "are not evidence of transfer and carry no verdict. The scored "
        "pools are untouched until the V8 lock closes and V9 issues.", "",
        "## Stacking arm (same folds, same de-vig)", "",
        f"- de-vig: {stacking.devig_method}",
        f"- fixtures: {stacking.n_fixtures} "
        f"(excluded, no odds: {stacking.n_excluded_no_odds})",
        f"- folds: {len(stacking.folds)}",
        f"- pooled OOF RPS: **{stacking.oof_rps:.5f}**",
        f"- deployment weights: dc {stacking.params.b_dc:+.3f}, "
        f"odds {stacking.params.b_odds:+.3f}, "
        f"elo {stacking.params.b_elo:+.3f}", "",
        "The stacking arm is a SECONDARY in the Holm family, not the "
        "primary contrast — it is reported here because the V8 lock binds "
        "it to the same trace as (w, de-vig).", "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", default=LEDGER_DEFAULT)
    ap.add_argument("--manifest", default=MANIFEST_DEFAULT)
    ap.add_argument("--store", default=STORE_DEFAULT)
    ap.add_argument("--trace", default=TRACE_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args(argv)

    try:
        outcomes = outcomes_for(args.manifest, args.store)
        frame = load_ledger(args.ledger)
        print(f"ledger: {len(frame)} rows, "
              f"{frame['fixture_id'].nunique()} fixtures, "
              f"{frame['arm'].nunique()} arms")
        selection = select_w(frame, outcomes=outcomes,
                             manifest=args.manifest)
        stacking = oof_stacking(frame, outcomes=outcomes,
                                manifest=args.manifest,
                                devig_method=selection.devig_method)
    except (SelectionError, ValueError) as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1

    write_selection_trace(args.trace, selection,
                          stacking=stacking.trace_payload())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(assemble_report(
        selection, stacking, ledger_path=args.ledger,
        trace_path=args.trace))
    print(f"SELECTED w={selection.w:.2f} devig={selection.devig_method} "
          f"over {len(selection.folds)} fold(s); wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
