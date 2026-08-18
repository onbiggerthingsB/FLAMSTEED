# v3 result — the break-widening lever is real and too small

**Run 2026-08-15, branch `epl-probe`.** Rule fixed in advance at
`reports/epl_prereg_v3.md`, committed `f5a6e3a` before any number below existed.

**Verdict: DO NOT ADOPT.** Two of four preregistered conditions pass, two fail.
The question is now closed rather than deferred.

## Why v3 was run

v2 rejected the season-break widening lever, but on an endpoint. Strength 0.35 was
simultaneously its best value and the largest tested, so the sweep had never found
where the effect turns over. Rejecting on an untested range is not a real rejection.
The owner pushed back on exactly this, correctly.

## Design

Nine configurations, summer-only (v2 measured the January window as actively
harmful), two seeds so every effect is read against optimiser noise measured on this
run rather than assumed. Tuning window only, 1,520 matches, 142 cutoffs per seed.
The 2025/26 holdout was not touched.

Break widening is a predict-time gate, so the whole grid costs one fit per cutoff
per seed rather than one per configuration.

## The curve

Mean RPS delta against control, averaged over both seeds. Negative is better.

| strength | half-life 3 | half-life 6 |
|---|---|---|
| 0.35 | **-0.000056** | -0.000056 |
| 0.50 | **-0.000058** (peak) | -0.000042 |
| 0.70 | -0.000040 | +0.000014 |
| 1.00 | +0.000030 | +0.000175 |

Per-seed, at the peak: -0.000056 (seed 20260611) and -0.000060 (seed 987654).

**The endpoint problem is solved.** The optimum is interior at strength 0.5, the
effect decays past it, and at 1.0 the lever is worse than not using it at all. There
is no untested range left to appeal to.

## The rule, applied

Measured noise: mean absolute seed-to-seed spread across the grid = **0.000038**.
This is lower than the 0.000074 measured in v2, so the lever was given its best
available chance.

| # | Condition | Observed | |
|---|---|---|---|
| 1 | mean d <= -0.00025 | -0.000058 | **FAIL** (4.3x too small) |
| 2 | \|d\| >= 2 x noise (0.000077) | 0.000058 | **FAIL** (1.5x noise) |
| 3 | same sign under both seeds | -0.000056 / -0.000060 | PASS |
| 4 | not an endpoint optimum | best = 0.5, interior | PASS |

## What this establishes

**The lever is real.** Both seeds agree in sign at every strength. The curve has a
coherent interior maximum rather than a monotone drift. The mechanism is
interpretable: widen uncertainty after the summer window, moderately, and leave
January alone. Conditions 3 and 4 are exactly the checks that distinguish a real
effect from a lucky draw, and both pass.

**It is far too small to use.** At 0.000058 it captures 0.8% of the 0.0077
Elo-to-market headroom, and it does not reach twice the optimiser noise on the same
objective. Shipping it would mean adopting an effect a reader could not distinguish
from which random numbers the fit happened to draw.

**The question is closed.** v2 left it open because the range was truncated. v3
found the peak. No v4 is warranted, and none should be run on this lever.

## Provenance

All 18 ledgers verified: each carries the seed its filename claims and `window=tune`;
1,520 matches scored per cell; control forecasts differ between seeds
(`e9203ba8` vs `897aff0f`), confirming the seed is not a silent no-op.

This is the third preregistration on this branch. The count matters: the best of many
draws flatters itself, which is why adoption required clearing a measured noise floor
rather than merely ranking first. Here the rule refused a lever that curve shape
alone would have argued for.
