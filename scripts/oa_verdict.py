#!/usr/bin/env python
"""V10 — the verdict (OA Plan 2 v2). The programme's terminal step.

Runs only behind a valid lock chain, and implements the LOCKED analysis
spec with no latitude:

  gate      mean(ΔRPS) <= -0.002  AND  support >= 0.80   (both halves)
  p         one-sided block-bootstrap, the exact complement of support
  family    Holm at α=0.05 over EXACTLY four secondaries
  veto      sign-flip: any pool with mean>0 and opposite-support>=0.60
            downgrades a PASS to inconclusive-heterogeneous (never rescues
            a FAIL)
  jackknife leave-one-team-out on the primary mean
  ITT       whole-inventory sensitivity, PRIMARY CONTRAST ONLY

THE GATE IS THE DECISION. The p-value sits beside it descriptively and
never overrides it — a favourable point estimate that misses the floor is
a FAIL, which is the entire reason the floor was pre-registered.

Outcomes enter HERE and only here, from the verified 90′ regulation table.
A locked fixture that cannot be settled is an ERROR, never a silent drop:
eligibility was frozen without outcomes, so settlement availability must
not be allowed to reshape the population after the fact.
"""
# No `from __future__ import annotations`: loaded by PATH in tests.
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wcmodel.eval.ledger import load_ledger                   # noqa: E402
from wcmodel.eval.lock import require_lock                    # noqa: E402
from wcmodel.eval.power import (                              # noqa: E402
    GATE_FLOOR,
    GATE_SUPPORT_REQ,
    HOLM_ALPHA,
    HOLM_FAMILY,
    block_bootstrap_support,
    gate_pass,
    holm_adjust,
    sign_flip_veto,
    within_block_correlation,
)
from wcmodel.model.calibration import rps                     # noqa: E402

LEDGER_DEFAULT = "data/oa_scored_ledger.parquet"
RESULTS_DEFAULT = "config/regulation_time_results.yaml"
OUT_DEFAULT = "reports/oa_verdict.md"
N_BOOT = 10000
SEED = 20260611

INCUMBENT = "incumbent"
PRIMARY = "Eprime"


class VerdictError(RuntimeError):
    """The verdict cannot be computed as specified."""


def p_from_support(support: float, *, n_boot: int) -> float:
    """The locked one-sided p, derived from the SAME bootstrap support.

    Spec §2.1: ``p = (1 + #{b : m*_b >= 0}) / (B + 1)``. Support is
    ``#{m*_b < 0} / B``, so ``#{m*_b >= 0} = B(1 - support)`` exactly.
    Deriving p this way rather than re-bootstrapping guarantees the two can
    never disagree — the spec calls p "the exact complement of the gate's
    support", and this makes that an identity rather than a coincidence.
    """
    n_ge = int(round(n_boot * (1.0 - support)))
    return (1 + n_ge) / (n_boot + 1)


def load_outcomes(path) -> dict:
    doc = yaml.safe_load(Path(path).read_text()) or {}
    rows = doc.get("results") or doc.get("fixtures") or []
    out = {}
    for row in rows:
        fid = str(row.get("match_id") or row.get("fixture_id") or "")
        h, a = row.get("home_score"), row.get("away_score")
        if not fid or h is None or a is None:
            continue
        h, a = float(h), float(a)
        out[fid] = "home" if h > a else ("away" if a > h else "draw")
    return out


def paired_diffs(frame: pd.DataFrame, arm: str, outcomes) -> tuple:
    """(diffs, pool, day, fixture_ids) for ``arm`` minus the incumbent."""
    wide = frame.pivot_table(index=["fixture_id", "pool", "date"],
                             columns="arm",
                             values=["p_home", "p_draw", "p_away"],
                             aggfunc="first")
    diffs, pools, days, fids = [], [], [], []
    for (fid, pool, date) in wide.index:
        try:
            arm_p = {k: float(wide.loc[(fid, pool, date), (f"p_{k}", arm)])
                     for k in ("home", "draw", "away")}
            inc_p = {k: float(wide.loc[(fid, pool, date),
                                       (f"p_{k}", INCUMBENT)])
                     for k in ("home", "draw", "away")}
        except KeyError:
            raise VerdictError(
                f"fixture {fid} lacks the {arm}/{INCUMBENT} pair — the "
                "contrast is paired per match, so a gap is an error")
        outcome = outcomes.get(str(fid))
        if outcome is None:
            raise VerdictError(
                f"locked fixture {fid} has no verified 90' regulation "
                "outcome — eligibility was frozen WITHOUT outcomes, so a "
                "settlement gap must ERROR rather than reshape the "
                "population")
        diffs.append(rps(arm_p, outcome) - rps(inc_p, outcome))
        pools.append(str(pool))
        days.append(str(date))
        fids.append(str(fid))
    return (np.array(diffs), np.array(pools), np.array(days), fids)


def contrast(frame, arm, outcomes, *, n_boot=N_BOOT, seed=SEED) -> dict:
    d, pool, day, fids = paired_diffs(frame, arm, outcomes)
    support = block_bootstrap_support(d, pool, day, n_boot=n_boot, seed=seed)
    return {"arm": arm, "n": len(d), "mean": float(d.mean()),
            "support": support, "p": p_from_support(support, n_boot=n_boot),
            "diffs": d, "pool": pool, "day": day, "fixture_ids": fids}


def per_pool(res, *, n_boot=2000, seed=SEED) -> dict:
    out = {}
    for name in sorted(set(res["pool"])):
        m = res["pool"] == name
        d, day = res["diffs"][m], res["day"][m]
        blocks = len(set(zip(res["pool"][m], day)))
        sup = block_bootstrap_support(d, res["pool"][m], day,
                                      n_boot=n_boot, seed=seed)
        out[name] = {"n_blocks": blocks, "n": int(m.sum()),
                     "mean_diff": float(d.mean()),
                     # opposite_support = fraction of own-pool bootstrap
                     # means strictly > 0, i.e. the complement of support
                     "opposite_support": float(1.0 - sup)}
    return out


def jackknife(res) -> tuple:
    """Leave-one-team-out: delete EVERY match a team appears in."""
    # team identity is not in the diffs; recover it from the ledger frame
    means = []
    for team in sorted(res["teams_by_fixture"] and
                       {t for ts in res["teams_by_fixture"].values()
                        for t in ts}):
        keep = np.array([team not in res["teams_by_fixture"][f]
                         for f in res["fixture_ids"]])
        if keep.sum() == 0:
            continue
        means.append(float(res["diffs"][keep].mean()))
    return (min(means), max(means)) if means else (float("nan"),) * 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", default=LEDGER_DEFAULT)
    ap.add_argument("--results", default=RESULTS_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args(argv)

    head = require_lock()
    print(f"lock v{head['version']} verified")
    frame = load_ledger(args.ledger)
    outcomes = load_outcomes(args.results)

    covered = set(frame.loc[frame["odds_snapshot_hash"].notna(),
                            "fixture_id"].astype(str))
    primary_frame = frame[frame["fixture_id"].astype(str).isin(covered)]
    print(f"primary population: {len(covered)} covered of "
          f"{frame['fixture_id'].nunique()} locked")

    teams = {str(r.fixture_id): {str(r.home), str(r.away)}
             for r in frame.itertuples(index=False)}

    res = contrast(primary_frame, PRIMARY, outcomes)
    res["teams_by_fixture"] = teams
    passed = gate_pass(res["mean"], res["support"])
    pools = per_pool(res)
    vetoed = sign_flip_veto(pools) if passed else False
    verdict = ("inconclusive-heterogeneous" if (passed and vetoed)
               else ("ADOPT" if passed else "no-adopt"))

    secondaries = {}
    for member in HOLM_FAMILY:
        arm = "stacking" if member == "stacking" else member
        secondaries[member] = contrast(primary_frame, arm, outcomes)
    adjusted = holm_adjust({k: v["p"] for k, v in secondaries.items()})

    itt = contrast(frame, PRIMARY, outcomes)
    jk = jackknife(res)
    r_dev = within_block_correlation(res["diffs"], res["pool"], res["day"])

    lines = [
        "# OA verdict — the pre-registered decision (V10)", "",
        f"## {verdict}", "",
        f"Gate: `mean(ΔRPS) <= {GATE_FLOOR}` AND "
        f"`support >= {GATE_SUPPORT_REQ}` — both halves required.", "",
        f"- n (primary, covered-only): **{res['n']}**",
        f"- mean ΔRPS: **{res['mean']:+.5f}**  "
        f"(floor {GATE_FLOOR}: {'MET' if res['mean'] <= GATE_FLOOR else 'NOT MET'})",
        f"- support: **{res['support']:.3f}**  "
        f"(req {GATE_SUPPORT_REQ}: {'MET' if res['support'] >= GATE_SUPPORT_REQ else 'NOT MET'})",
        f"- one-sided p (descriptive, never overrides the gate): "
        f"{res['p']:.5f}",
        f"- sign-flip veto: {'FIRED' if vetoed else 'not fired'}",
        f"- jackknife (leave-one-team-out) mean range: "
        f"[{jk[0]:+.5f}, {jk[1]:+.5f}]",
        f"- within-block correlation r: {r_dev:.4f}", "",
        "## Per-pool", "", "| pool | n | blocks | mean ΔRPS | opp. support |",
        "|---|---|---|---|---|",
    ]
    for name, s in sorted(pools.items()):
        lines.append(f"| {name} | {s['n']} | {s['n_blocks']} | "
                     f"{s['mean_diff']:+.5f} | {s['opposite_support']:.3f} |")
    lines += ["", f"## Secondary family (Holm, α={HOLM_ALPHA}, one-sided)",
              "", "| member | n | mean ΔRPS | raw p | adj p | rejected |",
              "|---|---|---|---|---|---|"]
    for member in HOLM_FAMILY:
        s = secondaries[member]
        adj = adjusted[member]
        lines.append(f"| {member} | {s['n']} | {s['mean']:+.5f} | "
                     f"{s['p']:.5f} | {adj:.5f} | "
                     f"{'yes' if adj <= HOLM_ALPHA else 'no'} |")
    lines += [
        "", "## ITT sensitivity (primary contrast only)", "",
        f"Whole locked inventory, n={itt['n']}, mean "
        f"{itt['mean']:+.5f}, support {itt['support']:.3f}. Uncovered rows "
        "carry the incumbent bitwise so their ΔRPS is exactly 0, which "
        "dilutes toward the null by construction. It can never produce an "
        "adoption the primary did not.", "",
        f"Lock v{head['version']}, commit {head['code_commit'][:12]}.", "",
    ]
    Path(args.out).write_text("\n".join(lines))
    print(f"VERDICT: {verdict} | mean {res['mean']:+.5f} "
          f"support {res['support']:.3f} | wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
