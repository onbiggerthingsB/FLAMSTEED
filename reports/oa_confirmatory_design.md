# OA confirmatory design — what a confirmatory test would actually cost

**Written 2026-08-11, recording analysis done 2026-08-09.**

> **STATUS: NOT SEALED. NOT IN FORCE. NO RULING HAS BEEN MADE.**
>
> This is a development-time design analysis. Nothing in it is preregistered,
> nothing in it constrains any future decision, and no number here may be cited
> as a result about the model. It exists because the reasoning below was
> produced, argued over, and then lived only in a conversation — and a project
> that seals its analysis plans by hash should not lose the analysis that would
> have decided whether to write one.

## Why this document exists

The V10 development verdict is ADOPT at mean ΔRPS −0.01018, bootstrap support
0.995, on n=217 covered fixtures. What that measures is the **market beating the
model**: the winning arm E′ is w=0.95, which is 95% bookmaker and statistically
indistinguishable from the pure market. `reports/oa_conclusion.md` says so
plainly, and nothing here revises it.

The open question was never that result. It was whether the finding could be
**confirmed** — reproduced live, under a rule fixed in advance, at a venue where
nobody could know the answer. Three attempts to draft that preregistration were
reviewed and none survived. The objections moved from clerical to structural,
and the structural ones are recorded here.

## Finding 1 — no confirmatory rule was ever sealed

The −0.002 floor and the 0.80 support requirement (`GATE_FLOOR`,
`GATE_SUPPORT_REQ` in `src/wcmodel/eval/power.py:35-36`) are titled, in the
sealed corpus, as the gate for **entry into** a confirmatory test. The analysis
spec states that α *does not apply* at that gate. There is therefore no sealed
α, no sealed sample size, and no sealed stopping rule for a confirmatory test.

This matters more than it sounds. It means the programme has not been "paused
before its final step" — the final step was never specified.

## Finding 2 — the sealed sign-flip veto is uncontrolled, and makes accumulation self-defeating

The sealed veto fires if **any** pool has mean > 0 and opposite-direction
support ≥ 0.60. That is a family of K tests with no multiplicity control, so its
false-fire rate climbs with the number of pools.

The consequence is the important part. Under a **homogeneous truth** — every
pool genuinely at −δ, so the veto *should* never fire — adding venues raises the
numeric gate's power but raises the veto's false-fire rate faster, and the
probability of a CONFIRMED verdict **falls**:

| K pools | n | gate power | sealed veto fires | **P(CONFIRMED)** |
|---:|---:|---:|---:|---:|
| 3 | 108 | 0.521 | 0.115 | **0.461** |
| 5 | 180 | 0.661 | 0.340 | **0.436** |
| 8 | 288 | 0.837 | 0.602 | **0.333** |
| 10 | 360 | 0.900 | 0.708 | **0.263** |

Collecting more evidence makes the test *less* likely to confirm a true effect.
Any design that accumulates fixtures across venues under this veto is
self-defeating, and the more patient the design, the worse it performs.

## Finding 3 — Bonferroni fixes the noise and destroys the veto's purpose

The obvious repair is to replace the fixed 0.60 bar with a Bonferroni bound,
firing iff `mean_pool > 0` and `opposite_support ≥ 1 − α_v/K`. It works on
noise, restoring CONFIRMED power to almost exactly the gate's power:

| K | sealed veto (noise) | Bonferroni veto (noise) | sealed CONFIRMED | Bonferroni CONFIRMED |
|---:|---:|---:|---:|---:|
| 3 | 0.115 | 0.001 | 0.461 | 0.520 |
| 5 | 0.340 | 0.003 | 0.436 | 0.659 |
| 8 | 0.602 | 0.012 | 0.333 | 0.827 |
| 10 | 0.708 | 0.023 | 0.263 | 0.879 |

But a veto that never fires is not a veto. Tested against a pool that is
**genuinely reversed**, Bonferroni barely notices:

| scenario | K | sealed fires | Bonferroni fires |
|---|---:|---:|---:|
| one pool at +δ | 3 | 0.389 | 0.061 |
| one pool at +δ | 5 | 0.699 | 0.082 |
| one pool at +δ | 8 | 0.854 | 0.115 |
| one pool at **+3δ** | 3 | 0.881 | 0.500 |
| one pool at **+3δ** | 8 | 0.990 | 0.591 |

A correction that restores power by refusing to detect the thing it exists to
detect has not solved the problem. Note also that the sealed veto's apparent
detection strength is largely an artifact of it firing constantly.

## Finding 4 — an omnibus heterogeneity test, and it must be calibrated

The repair that survives is to stop asking K separate per-pool questions and ask
one: *are the pools mutually consistent?* With per-pool effects θₖ and bootstrap
standard errors SEₖ,

    Q = Σ wₖ (θₖ − θ̄)² ,   wₖ = 1/SEₖ² ,   θ̄ = Σwₖθₖ / Σwₖ

**Q is not χ²-distributed here.** The SEₖ come from a block bootstrap on a small,
unbalanced block structure, so the nominal table is wrong — materially, and in
the anticonservative direction. Both constants must therefore be *computed* from
the realised block structure by a sealed deterministic procedure, not read off:

| K | b\* (5% type-I support bar) | q\* (10% veto on noise) | χ²(K−1) nominal 10% |
|---:|---:|---:|---:|
| 8 | 0.9525 | **14.878** | 12.017 |
| 10 | 0.9576 | **18.523** | 14.684 |
| 12 | 0.9563 | **22.279** | 17.275 |

Two things to read off this table. The calibrated support bar is ≈0.95, far
above the sealed 0.80 *entry* gate — which is another way of seeing that the
entry gate was never a confirmatory criterion. And q\* exceeds the χ² value at
every K, so using the table would have inflated the veto rate.

With the omnibus in place the pathology inverts and more data helps again:

| K | n | gate | veto \| gate | **P(CONFIRMED)** |
|---:|---:|---:|---:|---:|
| 8 | 288 | 0.829 | 0.113 | **0.736** |
| 10 | 360 | 0.883 | 0.112 | **0.784** |
| 12 | 432 | 0.923 | 0.098 | **0.833** |

And it still does its job, better than Bonferroni though not as loudly as the
uncontrolled rule: it catches a strongly reversed pool (+3δ) 0.722 of the time
at K=8 and 0.698 at K=12, and a modestly reversed one (+δ) 0.299 and 0.262.
That is the honest trade, stated rather than hidden.

## Finding 5 — the sample size, and why AC2027 alone cannot carry it

Powering against the observed development effect δ = 0.010177 (n=217,
sd = 0.068315), by normal approximation for 80% power one-sided:

| α | support bar | n needed | ≈ group stages |
|---:|---:|---:|---:|
| 0.01 | 0.99 | 452 | 12.6 |
| **0.05** | **0.95** | **279** | **7.7** |
| 0.10 | 0.90 | 203 | 5.6 |
| 0.20 | 0.80 | 128 | 3.5 |

The block bootstrap agrees for the **gate alone**, but the gate alone is not the
rule. The complete rule — gate *and* calibrated omnibus veto — crosses 80% power
between K=10 (n=360, 0.784) and K=12 (n=432, 0.833). Rounding to the nearest
defensible design point gives

> **n\* ≈ 400 covered fixtures.**

Against that, the sealed venue supplies:

| design | n | power at bar 0.95 | at 0.90 | at 0.80 |
|---|---:|---:|---:|---:|
| **AC2027 group stage (1 venue, 14 blocks)** | **36** | **0.284** | 0.385 | 0.539 |
| 2 venues | 72 | 0.396 | 0.521 | 0.666 |
| 3 venues | 108 | 0.496 | 0.631 | 0.766 |
| 6 venues | 216 | 0.717 | 0.832 | 0.921 |
| 8 venues | 288 | 0.844 | 0.919 | 0.963 |

The sealed confirmatory venue is a single 36-fixture group stage. At the
calibrated bar it has **0.284** power against the effect it was chosen to
confirm — and that figure is for the gate alone, before the veto takes its cut.

## What this adds up to

A defensible confirmatory test needs roughly **400 covered fixtures across
8–12 pools**, spanning several tournaments and therefore several years. Over
that span the incumbent model cannot be frozen — and a confirmatory test of a
model that changed underneath it is not confirmatory.

So the three constraints are jointly binding: the venue is too small by an order
of magnitude, the multi-venue design that would fix it takes years, and the
years are exactly what invalidates it.

**This document makes no recommendation and records no decision.** The ruling on
whether the programme continues, stops, or narrows belongs to the repo owner and
has not been made. What is settled is only this: the cost is now known, it is
written down, and it is reproducible.

## Reproducing every number above

All figures were regenerated on 2026-08-11 from a clean checkout. The scripts
live in `analysis/` (outside `CODE_PATHS`, so they do not touch the lock chain):

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
PYTHONPATH=analysis .venv/bin/python -u analysis/oa_confirmatory_veto.py       # Findings 2, 3
PYTHONPATH=analysis .venv/bin/python -u analysis/oa_confirmatory_calibrate.py  # Finding 4
PYTHONPATH=analysis .venv/bin/python -u analysis/oa_confirmatory_required_n.py # Finding 5
```

`analysis/oa_confirmatory_power.py` holds the shared machinery and carries a
`validate()` that checks the vectorised bootstrap against the shipped
`block_bootstrap_support`. It reports a mid-range case (0.6536 vs 0.6532)
alongside the two saturated ones, and labels the saturated ones "degenerate —
proves nothing", because a check that passes at 1.000 on both sides is not a
check. Simulation counts and seeds are fixed in each script; Monte-Carlo noise
of ±0.01 on the power figures is expected and does not move any conclusion.

## Corrections made while producing this

Recorded because the house rule is that a corrected error stays visible.

- Power at the sealed bar was first reported as 0.345 by pairing the 0.90-bar
  power with the 0.80-bar null. Wrong; caught on independent recomputation.
- A first cut of the design was quoted at K=11 (n=396) as satisfying n\*=400.
  396 < 400, so that design can never trigger the criterion it was proposed for.
- An early power figure omitted the veto entirely and asserted the numeric
  gate's power as the whole rule's. That is the mistake Finding 2 is about, made
  while analysing it.
- The first validation of the bootstrap returned exactly 1.000 on both sides —
  degenerate, and it proved nothing. Replaced with the mid-range case above.
