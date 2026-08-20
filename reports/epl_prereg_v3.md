# Preregistration v3 — extended break-widening sweep

**Written 2026-08-15, BEFORE any v3 number exists.** Branch `epl-probe`.
Tuning window only (2015/16–2018/19, n=1,520). The 2025/26 holdout is NOT touched.

## Why this exists

v2 rejected the season-break widening lever (I2). It was the only lever of four
with the right sign, it improved monotonically with strength, and the grid stopped
at 0.35, which was also its best value. So the sweep never found where the effect
turns over. Rejecting on an endpoint is rejecting on an untested range.

v2's best point: strength 0.35, half-life 3 matches, summer-only, delta **-0.000055**
against control. Rejected because that is 5.5% of the -0.001 adoption threshold, and
below the measured seed-replica noise of ~0.000074.

## Hypothesis

H1: the break-widening effect continues to improve past strength 0.35, and at some
strength the improvement exceeds the seed-noise floor.

H0: the effect is indistinguishable from optimiser noise at every strength.

## Design

- **Lever:** `break_widen_strength` in {0.0 control, 0.35, 0.5, 0.7, 1.0}
- **Half-life:** {3, 6} matches
- **January window: OFF.** v2 measured it as actively harmful (+0.000031 at the same
  strength where summer-only gave -0.000040), so it is excluded on evidence.
- **Seeds: two.** The production seed 20260611 and replica 987654. Every reported
  effect is read against the seed spread measured on the SAME configuration.
- **Window:** tuning only. `assert_tuning_only` enforces it.
- Break widening is a predict-time gate, so the whole grid costs one fit pass per
  seed, not one per configuration.

## The rule, fixed now

Let `d(c)` = mean RPS(config c) - mean RPS(control), on the tuning window, averaged
over the two seeds. Let `noise` = mean absolute seed-to-seed spread, measured across
the grid on this run rather than assumed.

ADOPT the best configuration only if ALL of:

1. **`d(best) <= -0.00025`** — at least 25% of the -0.001 threshold. A smaller effect
   is not worth the complexity even if it is real.
2. **`|d(best)| >= 2 x noise`** — the effect is at least twice the measured optimiser
   noise on this same objective.
3. **Sign agreement across both seeds** — `d` is negative under seed 20260611 AND
   under seed 987654 independently.
4. **Not an endpoint optimum** — the best strength is not the largest value tested.
   If 1.0 wins, the sweep is again truncated and the answer is "extend further",
   not "adopt".

Failing any of the four: DO NOT ADOPT. Report the curve and stop.

## What would make me stop entirely

If the curve turns over below 0.00025 improvement, the lever is real but too small
to matter, and no further extension is warranted. That is a finding and it closes
the question rather than inviting a v4.

## Anti-shopping note

This is the third preregistration on this branch. The count matters: the more
specifications tried, the more likely the best of them looks good by chance. Every
configuration run under v3 is listed in the results regardless of outcome, and the
v2 rejections stand as part of the search record. Adoption requires clearing the
noise floor, not merely ranking first.
