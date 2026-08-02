#!/usr/bin/env python
"""H2 — are the model's disagreements with the market signal or noise?

CORRECTED RERUN, same three upstream fixes as H1 (stage-based population,
block bootstrap, one alpha), plus one specific to this file: the previous
version's "power, not signal" conclusion and its ~811-fixture figure are
WITHDRAWN. Both rested on plugging the observed effect into a power formula,
which cannot establish that a real effect exists — a large observed-effect
power number is guaranteed whenever the estimate is noisy. Replaced with a
DESIGN CURVE over pre-declared effect sizes, which answers the same practical
question ("what would it take to see this?") without the circularity.

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
#: Effect sizes declared BEFORE looking, so the curve is not built around the
#: observed estimate the way the withdrawn 811 figure was.
DESIGN_EFFECTS = (-0.01, -0.02, -0.03, -0.05)


def design_curve(extreme, agree, *, n_boot=2000, seed=20260611) -> list:
    """How often would we detect an effect of each declared size, at this n?

    Resamples the observed blocks under the null, injects a known shift, and
    applies the SAME rule the test uses. No observed-effect plug-in: the
    injected effects are fixed in advance, so the curve describes the design
    rather than the result.
    """
    rng = np.random.default_rng(seed)
    out = []
    for eff in DESIGN_EFFECTS:
        hits = 0
        trials = 200
        for _ in range(trials):
            a = extreme.sample(len(extreme), replace=True,
                               random_state=int(rng.integers(1 << 31))).copy()
            b = agree.sample(len(agree), replace=True,
                             random_state=int(rng.integers(1 << 31))).copy()
            a["delta"] = a["delta"] - a["delta"].mean() + (
                b["delta"].mean() + eff)
            res = two_group_gap(a, b, n_boot=400,
                                seed=int(rng.integers(1 << 31)))
            hits += int(res.significant and res.gap < 0)
        out.append((eff, hits / trials))
    return out


def main() -> int:
    frame, counts = build()
    extreme = frame[frame["absdis"] >= WIDE]
    agree = frame[frame["absdis"] < NARROW]
    res = two_group_gap(extreme, agree)

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
        f"**{counts['knockout_excluded']}**, admitted "
        f"**{counts['admitted']}**", "",
        "### Result", "",
        f"- gap (|disagreement| ≥ {WIDE:.0%} minus < {NARROW:.0%}): "
        f"**{res.gap:+.5f}**",
        f"- {int((1 - ALPHA) * 100)}% block-bootstrap CI: "
        f"[{res.ci_low:+.5f}, {res.ci_high:+.5f}]",
        f"- one-sided null-centred p (α={ALPHA}): **{res.p_one_sided:.4f}**",
        f"- blocks: {res.blocks_a} extreme, {res.blocks_b} agree", "",
        "One α governs both the interval and the test. The earlier version "
        "reported a 5% tail beside a 97.5th-percentile gate — two different "
        "bars in one report.", "",
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
        asym = two_group_gap(high, low)
        detected = asym.significant
        lines += [
            f"- model much LOWER than market (n={len(low)}): "
            f"{low['delta'].mean():+.5f}",
            f"- model much HIGHER than market (n={len(high)}): "
            f"{high['delta'].mean():+.5f}",
            f"- difference between tails: {asym.gap:+.5f} "
            f"[{asym.ci_low:+.5f}, {asym.ci_high:+.5f}], p "
            f"{asym.p_one_sided:.4f}",
            "", ("**Asymmetry detected** — that would indicate a correctable "
                 "BIAS, not pure variance." if detected else
                 "**No asymmetry detected.** This is NOT evidence of "
                 "symmetry: the interval is far too wide to exclude a "
                 "meaningful bias, and bias and variance can coexist. It "
                 "means the data cannot separate them."), ""]

    lines += ["### What would it take to see this? (design curve)", "",
              "Detection probability at the CURRENT sample for effects "
              "declared in advance — not the observed estimate plugged into "
              "a power formula, which is what the withdrawn ~811-fixture "
              "figure did.", "",
              "| true effect | detected |", "|---|---|"]
    for eff, rate in design_curve(extreme, agree):
        lines.append(f"| {eff:+.3f} | {rate:.0%} |")
    lines += ["", "Read it as design guidance, not as evidence about which "
              "effect is real.", ""]

    OUT.write_text("\n".join(lines))
    print(f"{verdict} | gap {res.gap:+.5f} "
          f"[{res.ci_low:+.5f}, {res.ci_high:+.5f}] p {res.p_one_sided:.4f} "
          f"| n={len(frame)} | wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
