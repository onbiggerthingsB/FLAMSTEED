#!/usr/bin/env python
"""Out-of-sample test of the confederation hypothesis.

THE HYPOTHESIS, stated before this script computes anything
------------------------------------------------------------
Formed on the 217-fixture EVAL pool (reports/oa_gap_diagnostic.md), where
fixtures with both teams in UEFA/CONMEBOL showed the model level with the
market (+0.0003) while everything else showed it losing (-0.0182):

    H1  The model's deficit against the market is concentrated in fixtures
        involving a team outside UEFA/CONMEBOL, where its rating history is
        thinnest.
    H0  The deficit is uniform; the eval-pool split was small-cell noise.

DIRECTION IS PRE-COMMITTED: H1 predicts delta_non_core < delta_core, i.e.
the non-core group loses MORE. A result in the other direction refutes H1
and must not be re-narrated as support for anything.

WHY THIS IS WORTH RUNNING
-------------------------
The dev slate is 259 fixtures the hypothesis was NOT drawn from, and it is
confederation-diverse by construction: AFCON is entirely CAF, UEFA Nations
League entirely UEFA, and Copa América 2024 splits because of its CONCACAF
guests. That makes the split ~135 non-core against ~124 core in data that
played no part in generating H1.

This is still NOT preregistered in the OA lock's sense, and it cannot adopt
anything. What it can do is tell us whether a hypothesis formed on one pool
survives contact with another — which is the difference between a lead and
a finding.

KNOWN CONTAMINATION
-------------------
There is no verified 90' regulation table for AFCON or Copa América, so a
knockout tie decided by an extra-time GOAL is scored on its ET-inclusive
final. Shootouts are detectable (the store's winner_override) and are
excluded. The residual is small and, more importantly, affects the RPS of
BOTH arms on the same fixture, so it adds noise to the paired difference
rather than a direction. It is reported, not hidden.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from wcmodel.data.tiers import confederation                  # noqa: E402
from wcmodel.eval.ledger import load_ledger                   # noqa: E402
from wcmodel.model.calibration import outcome_1x2, rps        # noqa: E402

DEV_LEDGER = _ROOT / "data" / "oa_dev_ledger.parquet"
STORE = _ROOT / "data" / "stores" / "full_final" / "results.parquet"
OUT = _ROOT / "reports" / "oa_confed_test.md"
MODEL_ARM, BOOK_ARM = "dev_dc", "dev_odds_multiplicative"
OUTCOMES = ("home", "draw", "away")
N_BOOT, SEED = 10000, 20260611


def build() -> tuple[pd.DataFrame, int]:
    ledger = load_ledger(DEV_LEDGER)
    wide = ledger.pivot_table(
        index=["fixture_id", "pool", "date", "home", "away"], columns="arm",
        values=["p_home", "p_draw", "p_away"], aggfunc="first")

    store = pd.read_parquet(STORE)
    store["date"] = pd.to_datetime(store["date"]).dt.date.astype(str)
    res = {(str(r.date), str(r.home_team), str(r.away_team)):
           (r.home_score, r.away_score, r.winner_override)
           for r in store.itertuples(index=False)}

    rows, dropped = [], 0
    for (fid, pool, date, home, away) in wide.index:
        got = res.get((str(date), str(home), str(away)))
        if got is None:
            continue
        hs, as_, override = got
        if override is not None and not pd.isna(override):
            dropped += 1        # decided past 90' -> no 90' label available
            continue
        try:
            model = {k: float(wide.loc[(fid, pool, date, home, away),
                                       (f"p_{k}", MODEL_ARM)])
                     for k in OUTCOMES}
            book = {k: float(wide.loc[(fid, pool, date, home, away),
                                      (f"p_{k}", BOOK_ARM)])
                    for k in OUTCOMES}
        except KeyError:
            continue
        if any(np.isnan(v) for v in (*model.values(), *book.values())):
            continue            # fixture without an odds comparator
        actual = outcome_1x2(int(hs), int(as_))
        rows.append({
            "fixture_id": fid, "pool": pool, "date": date,
            "home": home, "away": away, "outcome": actual,
            "core": (confederation(home) in ("UEFA", "CONMEBOL")
                     and confederation(away) in ("UEFA", "CONMEBOL")),
            "rps_model": rps(model, actual), "rps_book": rps(book, actual),
            "fav_p_book": max(book.values()),
        })
    frame = pd.DataFrame(rows)
    frame["delta"] = frame["rps_book"] - frame["rps_model"]
    return frame, dropped


def ci(values, rng) -> tuple[float, float]:
    boot = np.array([rng.choice(values, len(values), replace=True).mean()
                     for _ in range(N_BOOT)])
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def main() -> int:
    frame, dropped = build()
    rng = np.random.default_rng(SEED)
    core = frame[frame["core"]]["delta"].to_numpy()
    non = frame[~frame["core"]]["delta"].to_numpy()
    gap = non.mean() - core.mean()

    # The test is on the DIFFERENCE of the two group means. Resampling each
    # group independently is the paired-free null: if H1 is false the gap is
    # centred on zero.
    boot_gap = np.array([
        rng.choice(non, len(non), replace=True).mean()
        - rng.choice(core, len(core), replace=True).mean()
        for _ in range(N_BOOT)])
    lo, hi = np.percentile(boot_gap, [2.5, 97.5])
    # one-sided against the PRE-COMMITTED direction (H1: gap < 0)
    p_one_sided = float((boot_gap >= 0).mean())

    verdict = ("SUPPORTED" if hi < 0 else
               "NOT SUPPORTED" if lo > 0 else "INCONCLUSIVE")

    lines = [
        "# Confederation hypothesis — out-of-sample test on the dev slate", "",
        f"## {verdict}", "",
        "H1 (pre-committed, formed on the 217-fixture eval pool): the model's "
        "deficit against the market is concentrated in fixtures involving a "
        "team outside UEFA/CONMEBOL. H1 predicts a NEGATIVE gap "
        "(non-core loses more).", "",
        f"- fixtures scored: **{len(frame)}** "
        f"({int((~frame['core']).sum())} non-core, "
        f"{int(frame['core'].sum())} core)",
        f"- excluded as decided past 90' (shootouts, no 90' label): {dropped}",
        f"- gap (non-core − core): **{gap:+.5f}**  "
        f"95% CI [{lo:+.5f}, {hi:+.5f}]",
        f"- one-sided p against the pre-committed direction: {p_one_sided:.4f}",
        "",
        "| group | n | RPS model | RPS book | book − model | 95% CI |",
        "|---|---|---|---|---|---|",
    ]
    for label, sub in (("non-core", frame[~frame["core"]]),
                       ("core", frame[frame["core"]])):
        d = sub["delta"].to_numpy()
        a, b = ci(d, rng)
        lines.append(f"| {label} | {len(d)} | {sub['rps_model'].mean():.4f} | "
                     f"{sub['rps_book'].mean():.4f} | {d.mean():+.5f} | "
                     f"[{a:+.5f}, {b:+.5f}] |")

    lines += ["", "### By competition", "",
              "| tournament | n | book − model |", "|---|---|---|"]
    for pool, grp in frame.groupby("pool", observed=True):
        lines.append(f"| {pool} | {len(grp)} | {grp['delta'].mean():+.5f} |")

    lines += ["", "### Held at fixed favourite strength", "",
              "Favourite strength partly confounded the eval-pool version, so "
              "the same control is applied here.", "",
              "| favourite band | non-core mean (n) | core mean (n) |",
              "|---|---|---|"]
    frame = frame.assign(band=pd.cut(
        frame["fav_p_book"], [0, 0.40, 0.50, 0.60, 0.75, 1.01],
        labels=["<40%", "40-50%", "50-60%", "60-75%", ">75%"], right=False))
    for band, grp in frame.groupby("band", observed=True):
        a, b = grp[~grp["core"]]["delta"], grp[grp["core"]]["delta"]
        lines.append(f"| {band} | {a.mean():+.5f} ({len(a)}) | "
                     f"{b.mean():+.5f} ({len(b)}) |")

    lines += ["", "Contamination note: no verified 90' table exists for AFCON "
              "or Copa América, so a knockout tie decided by an extra-time "
              "GOAL is scored on its ET-inclusive final. Shootouts are "
              f"excluded ({dropped} fixtures). The residual perturbs both "
              "arms on the same fixture, so it adds noise to the paired "
              "difference rather than a direction.", ""]

    OUT.write_text("\n".join(lines))
    print(f"{verdict} | gap {gap:+.5f} [{lo:+.5f}, {hi:+.5f}] "
          f"| n={len(frame)} | wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
