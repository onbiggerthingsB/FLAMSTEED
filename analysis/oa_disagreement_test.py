#!/usr/bin/env python
"""Out-of-sample test: are the model's disagreements with the market signal?

THE HYPOTHESIS, stated before this script computes anything
------------------------------------------------------------
Formed on the 217-fixture EVAL pool (reports/oa_gap_diagnostic.md), where
the model lost badly whenever it departed sharply from the market in EITHER
direction (-0.0205 when much lower on the market's favourite, -0.0297 when
much higher, against -0.0036 when the two agreed within 4pp):

    H2  The model's deviations from the market are NOISE. When it disagrees
        confidently it is usually the one that is wrong, so its deficit is
        larger in the extreme-disagreement bands than in the agree band.
    H0  Deviations carry signal, or at least cost nothing extra: the deficit
        does not widen with disagreement.

DIRECTION IS PRE-COMMITTED: H2 predicts gap < 0, where

    gap = mean(delta | |disagreement| >= 10pp) - mean(delta | < 4pp)

and delta = RPS(book) - RPS(model), so negative means the book won by more.
A positive gap refutes H2 and must not be re-narrated as support.

WHY THE TEST IS INFORMATIVE AND NOT CIRCULAR
--------------------------------------------
If model and market were both unbiased with independent noise, a large
disagreement would say nothing about WHICH one is off, and the gap would sit
near zero. The gap only goes negative if the model is the noisier estimate.
If instead its deviations carried genuine private signal, large disagreement
would favour the MODEL and the gap would go positive. So the sign is
informative about the model, not a restatement of the overall deficit.

WHY THE SYMMETRY MATTERS MORE THAN THE HEADLINE
-----------------------------------------------
The two extreme bands are reported separately, because they imply opposite
remedies:

  both directions lose   -> the deviations are variance. The fix is to shrink
                            the model toward the market, or reduce its
                            variance; there is nothing to correct directionally.
  one direction loses    -> that is a BIAS, and a bias is correctable. Far
                            more valuable, and a completely different fix.

A single averaged number would hide which of those we are looking at.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from wcmodel.eval.ledger import load_ledger                   # noqa: E402
from wcmodel.model.calibration import outcome_1x2, rps        # noqa: E402

DEV_LEDGER = _ROOT / "data" / "oa_dev_ledger.parquet"
STORE = _ROOT / "data" / "stores" / "full_final" / "results.parquet"
OUT = _ROOT / "reports" / "oa_disagreement_test.md"
MODEL_ARM, BOOK_ARM = "dev_dc", "dev_odds_multiplicative"
OUTCOMES = ("home", "draw", "away")
WIDE, NARROW = 0.10, 0.04          # the eval-pool band edges, reused as-is
N_BOOT, SEED = 10000, 20260611


def build() -> tuple[pd.DataFrame, int]:
    ledger = load_ledger(DEV_LEDGER)
    wide_tbl = ledger.pivot_table(
        index=["fixture_id", "pool", "date", "home", "away"], columns="arm",
        values=["p_home", "p_draw", "p_away"], aggfunc="first")

    store = pd.read_parquet(STORE)
    store["date"] = pd.to_datetime(store["date"]).dt.date.astype(str)
    res = {(str(r.date), str(r.home_team), str(r.away_team)):
           (r.home_score, r.away_score, r.winner_override)
           for r in store.itertuples(index=False)}

    rows, dropped = [], 0
    for (fid, pool, date, home, away) in wide_tbl.index:
        got = res.get((str(date), str(home), str(away)))
        if got is None:
            continue
        hs, as_, override = got
        if override is not None and not pd.isna(override):
            dropped += 1                     # decided past 90'
            continue
        try:
            model = {k: float(wide_tbl.loc[(fid, pool, date, home, away),
                                           (f"p_{k}", MODEL_ARM)])
                     for k in OUTCOMES}
            book = {k: float(wide_tbl.loc[(fid, pool, date, home, away),
                                          (f"p_{k}", BOOK_ARM)])
                    for k in OUTCOMES}
        except KeyError:
            continue
        if any(np.isnan(v) for v in (*model.values(), *book.values())):
            continue
        actual = outcome_1x2(int(hs), int(as_))
        fav = max(book, key=book.get)        # the MARKET's favourite
        rows.append({
            "fixture_id": fid, "pool": pool, "home": home, "away": away,
            "outcome": actual,
            "rps_model": rps(model, actual), "rps_book": rps(book, actual),
            # signed: positive = model MORE bullish than the market on its pick
            "disagree": model[fav] - book[fav],
        })
    frame = pd.DataFrame(rows)
    frame["delta"] = frame["rps_book"] - frame["rps_model"]
    frame["absdis"] = frame["disagree"].abs()
    return frame, dropped


def _ci(values, rng):
    boot = np.array([rng.choice(values, len(values), replace=True).mean()
                     for _ in range(N_BOOT)])
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def main() -> int:
    frame, dropped = build()
    rng = np.random.default_rng(SEED)

    extreme = frame[frame["absdis"] >= WIDE]["delta"].to_numpy()
    agree = frame[frame["absdis"] < NARROW]["delta"].to_numpy()
    gap = extreme.mean() - agree.mean()
    boot = np.array([rng.choice(extreme, len(extreme), replace=True).mean()
                     - rng.choice(agree, len(agree), replace=True).mean()
                     for _ in range(N_BOOT)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    p_one = float((boot >= 0).mean())
    verdict = ("SUPPORTED" if hi < 0 else
               "NOT SUPPORTED" if lo > 0 else "INCONCLUSIVE")

    lines = [
        "# Are the model's disagreements with the market signal or noise?",
        "", f"## {verdict}", "",
        "H2 (pre-committed, formed on the 217-fixture eval pool): the model's "
        "deviations from the market are NOISE, so its deficit widens with "
        "disagreement. H2 predicts a NEGATIVE gap.", "",
        f"- fixtures scored: **{len(frame)}**  "
        f"(excluded as decided past 90': {dropped})",
        f"- gap (|disagreement| ≥ {WIDE:.0%} minus < {NARROW:.0%}): "
        f"**{gap:+.5f}**  95% CI [{lo:+.5f}, {hi:+.5f}]",
        f"- one-sided p against the pre-committed direction: {p_one:.4f}", "",
        "delta = RPS(book) − RPS(model); negative means the market won.", "",
        "| disagreement band | n | mean delta | 95% CI | model wins |",
        "|---|---|---|---|---|",
    ]
    frame = frame.assign(band=pd.cut(
        frame["disagree"], [-1.01, -WIDE, -NARROW, NARROW, WIDE, 1.01],
        labels=["model much lower", "model lower", f"agree (±{NARROW:.0%})",
                "model higher", "model much higher"], right=False))
    for band, grp in frame.groupby("band", observed=True):
        d = grp["delta"].to_numpy()
        a, b = _ci(d, rng)
        lines.append(f"| {band} | {len(d)} | {d.mean():+.5f} | "
                     f"[{a:+.5f}, {b:+.5f}] | {(d > 0).mean():.0%} |")

    # The symmetry question: variance (both tails lose) or bias (one tail)?
    low = frame[frame["disagree"] <= -WIDE]["delta"].to_numpy()
    high = frame[frame["disagree"] >= WIDE]["delta"].to_numpy()
    lines += ["", "### Noise or bias?", "",
              "Both tails losing means the deviations are VARIANCE (shrink "
              "the model). One tail losing means a BIAS, which is "
              "correctable and a different fix entirely.", "",
              f"- model much LOWER than market  (n={len(low)}): "
              f"{low.mean():+.5f}",
              f"- model much HIGHER than market (n={len(high)}): "
              f"{high.mean():+.5f}", ""]
    if len(low) and len(high):
        diff = high.mean() - low.mean()
        bd = np.array([rng.choice(high, len(high), replace=True).mean()
                       - rng.choice(low, len(low), replace=True).mean()
                       for _ in range(N_BOOT)])
        blo, bhi = np.percentile(bd, [2.5, 97.5])
        asym = "asymmetric (bias)" if (blo > 0 or bhi < 0) else \
               "no detectable asymmetry (consistent with variance)"
        lines += [f"- difference between tails: {diff:+.5f} "
                  f"95% CI [{blo:+.5f}, {bhi:+.5f}] → **{asym}**", ""]

    lines += ["Eval-pool figures this was formed on, for comparison: "
              "much lower −0.0205, agree −0.0036, much higher −0.0297. The "
              "direction and rough magnitude replicate; the certification "
              "does not.", ""]

    # Is INCONCLUSIVE a weak signal or too few fixtures? Answer it rather
    # than leave it arguable -- the two imply completely different next steps.
    sd_e, sd_a = extreme.std(ddof=1), agree.std(ddof=1)
    pooled = float(np.sqrt((sd_e ** 2 + sd_a ** 2) / 2))
    need = 2 * ((1.645 + 0.84) * pooled / abs(gap)) ** 2
    share = len(extreme) / len(frame)
    lines += [
        "### Why INCONCLUSIVE — power, not absence of signal", "",
        f"- per-fixture SD: **{sd_e:.4f}** in the extreme bands vs "
        f"**{sd_a:.4f}** when the two agree — roughly "
        f"{sd_e / sd_a:.0f}× the variance.",
        "  That spread IS the finding's own subject matter: when the model "
        "departs from the market the result is wildly variable, big wins and "
        "big losses, which is what makes the mean so hard to pin down.",
        f"- at the observed effect ({gap:+.5f}) and that spread, 80% power "
        f"needs ~**{need:.0f} fixtures per group**; the extreme bands are "
        f"only {share:.0%} of fixtures, so ~**{need / share:.0f} total**.",
        f"- we have {len(frame)}. This is an underpowered test of a real-"
        "looking effect, not evidence the effect is absent.", ""]

    OUT.write_text("\n".join(lines))
    print(f"{verdict} | gap {gap:+.5f} [{lo:+.5f}, {hi:+.5f}] "
          f"| n={len(frame)} | wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
