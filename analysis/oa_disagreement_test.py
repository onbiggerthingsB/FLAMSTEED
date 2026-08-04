#!/usr/bin/env python
"""H2 — are the model's disagreements with the market signal or noise?

TWICE-CORRECTED RERUN, same upstream fixes as H1 (round-level settlement
population; joint pool-stratified block bootstrap; a pivotal interval exactly
dual to the one-sided test — see oa_confed_test.py's header for the full
two-round correction history), plus one specific to this file: the previous
version's "power, not signal" conclusion and its ~811-fixture figure are
WITHDRAWN. Both rested on plugging the observed effect into a power formula,
which cannot establish that a real effect exists — a large observed-effect
power number is guaranteed whenever the estimate is noisy. Replaced with a
POST-HOC sensitivity grid over a fixed span of effect sizes (chosen while
writing the repair, with the estimate already known — see the note on
``SENSITIVITY_EFFECTS``). It answers "what would this design detect?", which
is design guidance, not evidence about which effect is real.

THE HYPOTHESIS (unchanged, still pre-committed)
-----------------------------------------------
    H2  the model's deviations from the market are NOISE, so its deficit
        widens when it disagrees. Predicts gap < 0, where
        gap = mean(delta | |disagreement| >= 10pp) − mean(delta | < 4pp).

NOISE OR BIAS — the part that decides the remedy
------------------------------------------------
Both tails losing implies VARIANCE: nothing directional to correct, so the
remedy is shrinkage. One tail losing implies a BIAS, which is correctable and
a completely different fix. Absence of a detected asymmetry is NOT evidence of
symmetry, and this report no longer claims it is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "analysis"))

from oa_devslate import build                                  # noqa: E402
from oa_stats import ALPHA, block_ci, two_group_gap             # noqa: E402

OUT = _ROOT / "reports" / "oa_disagreement_test.md"
WIDE, NARROW = 0.10, 0.04
#: A POST-HOC sensitivity grid. These sizes were chosen while writing the
#: repair, with the observed estimate already known — so this is NOT a
#: predeclared design, and the earlier docstring saying otherwise was wrong.
#: What it can honestly answer is "at this sample and this block structure,
#: how detectable would an effect of size X be?", which is design guidance.
SENSITIVITY_EFFECTS = (-0.01, -0.02, -0.03, -0.05)


def sensitivity_curve(extreme, agree, *, n_boot=400, trials=200,
                      seed=20260611) -> list:
    """Detection rate at this sample for each grid effect, BLOCK-resampled.

    The previous implementation sampled individual rows and then reused their
    original dates, manufacturing duplicate and missing pseudo-blocks — it
    destroyed the very structure the test depends on. This resamples whole
    (pool, matchday) blocks, centres both groups to a common mean so the null
    is true, then injects the effect.
    """
    rng = np.random.default_rng(seed)
    ex = extreme.copy()
    ag = agree.copy()
    # Centre both groups: under the null the two have the same mean.
    ex["delta"] = ex["delta"] - ex["delta"].mean()
    ag["delta"] = ag["delta"] - ag["delta"].mean()
    ex_blocks = [g for _, g in ex.groupby(["pool", "date"], observed=True)]
    ag_blocks = [g for _, g in ag.groupby(["pool", "date"], observed=True)]

    out = []
    for eff in SENSITIVITY_EFFECTS:
        hits = 0
        for _ in range(trials):
            a = pd.concat([ex_blocks[i] for i in
                           rng.integers(0, len(ex_blocks), len(ex_blocks))])
            b = pd.concat([ag_blocks[i] for i in
                           rng.integers(0, len(ag_blocks), len(ag_blocks))])
            a = a.copy()
            a["delta"] = a["delta"] + eff
            try:
                res = two_group_gap(a, b, n_boot=n_boot,
                                    seed=int(rng.integers(1 << 31)),
                                    alternative="less")
            except ValueError:
                continue
            hits += int(res.significant and res.gap < 0)
        out.append((eff, hits / trials))
    return out


def main() -> int:
    frame, counts = build()
    extreme = frame[frame["absdis"] >= WIDE]
    agree = frame[frame["absdis"] < NARROW]
    res = two_group_gap(extreme, agree, alternative="less")

    clears = res.significant and res.gap < 0
    verdict = ("DIRECTION REPLICATED, CLEARS THE BAR — BUT NOT CERTIFIED"
               if clears else "NOT SUPPORTED (direction reversed)"
               if res.gap > 0 else "NOT SUPPORTED")

    lines = [
        "# H2 — are the model's disagreements signal or noise?", "",
        f"## {verdict}", "",
    ]
    if clears:
        lines += [
            "> **Why this is not a certification, despite clearing the bar.**",
            "> The first run of this test used an internally inconsistent "
            "rule: it reported a 5% tail beside a 97.5th-percentile gate. "
            "Under it H2 narrowly MISSED. The rule was then corrected to a "
            "single one-sided α — which is the defensible construction, and "
            "would have been the right choice from the start — but it was "
            "chosen AFTER the near-miss was visible. Adopting a rule that "
            "turns a miss into a pass, once the data are seen, is precisely "
            "the move that invalidates a test.",
            ">",
            "> So the numbers below are a repaired ESTIMATE, not a passed "
            "test. The interval also only barely excludes zero. H2 stays "
            "UNCERTIFIED until an independent sample decides it under a rule "
            "fixed in advance.", "",
        ]
    lines += [
        "H2 predicts a NEGATIVE gap: the deficit widens with disagreement. "
        "delta = RPS(book) − RPS(model); negative means the market won.", "",
        "### Population", "",
        f"- dev-slate fixtures **{counts['total']}**, knockout excluded "
        f"**{counts["extra_time_excluded"]}**, admitted "
        f"**{counts['admitted']}**", "",
        "### Result", "",
        f"- gap (|disagreement| ≥ {WIDE:.0%} minus < {NARROW:.0%}): "
        f"**{res.gap:+.5f}**",
        f"- {int((1 - 2 * ALPHA) * 100)}% block-bootstrap CI (dual to the "
        f"one-sided α={ALPHA} test): [{res.ci_low:+.5f}, {res.ci_high:+.5f}]",
        f"- one-sided null-centred p: **{res.p:.4f}**",
        f"- blocks: {res.n_blocks} pool × matchday, of which "
        f"{res.n_shared_blocks} contain BOTH groups and are drawn whole", "",
        "The interval is two-sided at 1−2α, which is the interval DUAL to a "
        "one-sided α test, so significance and interval-exclusion cannot "
        "disagree. The previous version paired a 5% tail with a "
        "97.5th-percentile gate and reported an exclusion that a "
        "higher-precision run put on the other side of zero.", "",
        "| disagreement band | n | mean delta | CI | model wins |",
        "|---|---|---|---|---|",
    ]
    banded = frame.assign(band=pd.cut(
        frame["disagree"], [-1.01, -WIDE, -NARROW, NARROW, WIDE, 1.01],
        labels=["model much lower", "model lower", f"agree (±{NARROW:.0%})",
                "model higher", "model much higher"], right=False))
    for band, grp in banded.groupby("band", observed=True):
        mean, lo, hi = block_ci(grp)
        lines.append(f"| {band} | {len(grp)} | {mean:+.5f} | "
                     f"[{lo:+.5f}, {hi:+.5f}] | "
                     f"{(grp['delta'] > 0).mean():.0%} |")

    low = frame[frame["disagree"] <= -WIDE]
    high = frame[frame["disagree"] >= WIDE]
    lines += ["", "### Noise or bias?", ""]
    if len(low) and len(high):
        # No direction was pre-committed for the asymmetry question, so
        # it must be two-sided; a one-sided tail read off whichever
        # way the estimate points is not a test.
        asym = two_group_gap(high, low, alternative="two_sided")
        detected = asym.significant
        lines += [
            f"- model much LOWER than market (n={len(low)}): "
            f"{low['delta'].mean():+.5f}",
            f"- model much HIGHER than market (n={len(high)}): "
            f"{high['delta'].mean():+.5f}",
            f"- difference between tails: {asym.gap:+.5f} "
            f"[{asym.ci_low:+.5f}, {asym.ci_high:+.5f}], p "
            f"{asym.p:.4f} (two-sided)",
            "", ("**Asymmetry detected** — that would indicate a correctable "
                 "BIAS, not pure variance." if detected else
                 "**No asymmetry detected.** This is NOT evidence of "
                 "symmetry: the interval is far too wide to exclude a "
                 "meaningful bias, and bias and variance can coexist. It "
                 "means the data cannot separate them."), ""]

    lines += ["### What would it take to see this? (sensitivity grid)", "",
              "Detection rate at the CURRENT sample and block structure for "
              "each effect size. This grid is POST-HOC — chosen while writing "
              "the repair, with the estimate already known — so read it as "
              "design guidance, not as evidence about which effect is real. "
              "It is still preferable to the withdrawn ~811-fixture "
              "figure, which plugged the observed noisy estimate into an "
              "iid power formula and then treated the answer as evidence the "
              "effect was real.", "",
              "| effect | detected |", "|---|---|"]
    for eff, rate in sensitivity_curve(extreme, agree):
        lines.append(f"| {eff:+.3f} | {rate:.0%} |")
    lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"{verdict} | gap {res.gap:+.5f} "
          f"[{res.ci_low:+.5f}, {res.ci_high:+.5f}] p {res.p:.4f} "
          f"| n={len(frame)} | wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
