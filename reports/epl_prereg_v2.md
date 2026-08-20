# Preregistration v2: the selected stack, and what the fresh holdout can say about it

**Branch** `epl-probe` · **Written** 2026-08-14 · **Status** written and committed
BEFORE any 2025/26 holdout number exists and before any re-scoring of
2019/20–2024/25
**Code** `epl/select.py` (the sweep and the adoption rule), `epl/improve.py`
(the gates), `epl/config_frozen.json` (unchanged)
**Predecessors** `reports/epl_prereg.md` (v1, the design), `reports/epl_walkforward.md`
(run 1, the result this phase set out to improve on)

```
PYTHONPATH=src:. .venv/bin/python -m epl.select --sweep                    # the OFF arm + 9 predict variants
PYTHONPATH=src:. .venv/bin/python -m epl.select --sweep --decay 180        # one I1a arm
PYTHONPATH=src:. .venv/bin/python -m epl.select --sweep --congestion       # the I4 arm
PYTHONPATH=src:. .venv/bin/python -m epl.select --sweep --seed 987654 --control-only
PYTHONPATH=src:. .venv/bin/python -m epl.select --trace                    # executes the adoption rule
PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests -q
```

**NO BETTING.** No price is read or produced anywhere in this phase. The market
column does not appear in it at all: the DC-versus-Elo question needs no odds,
and requiring them would have re-imported the odds-coverage selection effect
that put 2025/26 outside both windows in the first place.

---

## The answer, in the first paragraph

**Nothing was adopted.** Forty-five specifications were evaluated on the tuning
window 2015/16–2018/19 under a rule fixed in code before the first sweep ran.
Not one cleared the adoption threshold of −0.0010 RPS; the best of them
gained **0.000065**, which is 6.5% of the threshold, 1.4 times the measured ADVI
seed noise, and carries a confidence interval that crosses zero. Two of the four
levers were not merely too small but **wrong-signed**: shortening the likelihood
half-life and speeding up the home term both made the tuning objective worse,
monotonically. The final stack is therefore the frozen configuration of
`epl/config_frozen.json`, byte for byte, and this document preregisters what the
fresh 2025/26 holdout will be asked — knowing in advance that it cannot answer
the question it is being asked.

The outcome does not depend on where the threshold was put. Even at a threshold
of zero — adopt anything with a favourable point estimate — the best candidate
still fails the season-stability and curve-shape conditions. That is stated here
because "we chose the threshold that gave this answer" is the obvious suspicion
and it happens not to be available.

---

## 1. What this phase did, and the one rule that governs it

Run 1 put the frozen Dixon-Coles model 0.00117 RPS below walk-forward Elo on
2019/20–2024/25, with a CI of [−0.00281, +0.00047]: a precise null, not a win.
`epl/improve.py` then built four config-reachable levers as gates, proved that
with every gate off the package is bit-identical to the frozen configuration,
and deliberately ran no sweep. This phase runs the sweep.

### The windows, which are load-bearing and must not blur

| window | seasons | n | what it is for here |
|---|---|---:|---|
| **TUNE** | 2015/16–2018/19 (walked from 2014/15) | **1,520** | every number in §3. All tuning, all adoption. |
| **CONFIRM** | 2019/20–2024/25 | 2,280 | scored ONCE, at run 1. Not re-scored in this phase. §6. |
| **FRESH HOLDOUT** | 2025/26 | 380 | never scored for the model. Touched once, after this document. §5. |

`epl.select.run_sweep` defaults to `window="tune"` and calls
`windows.assert_tuning_only` on the frame it actually built. `window="confirm"`
raises unless `second_look=True`; `window="holdout"` raises unless
`holdout=True`. The guard reads the data, not a flag, so a mis-sliced frame
fails loudly rather than quietly widening the window
(`epl/tests/test_select.py::test_the_tuning_frame_is_asserted_not_assumed`).

**Not one confirm-window or holdout number entered any decision in §3.** The
only confirm-window numbers quoted anywhere in this document are the ones run 1
already published.

---

## 2. The adoption rule, fixed before the first sweep ran

The rule lives in `epl/select.py` as `ADOPTION_RULE` and is **executed** by
`epl.select.adopt`, not merely described. That is deliberate: a rule that lives
only in prose can be rewritten to match the answer, and a rule that is executed
by the same code that produced the numbers cannot drift from them. The sweep
writes only under `data/` (gitignored), so the rule's presence in the committed
source is checkable evidence of the ordering.

### The objective

Mean normalised (halved) three-outcome RPS over 2015/16–2018/19, n = 1,520,
every fixture priced, complete case — the same metric, on the same convention,
as v1 §2. Secondary: mean natural-log loss, reported on every row, entering the
decision only through condition B3.

Comparisons are **paired, challenger minus current stack**, restricted to the
fixtures both priced, so a variant can never be scored on an easier subset than
the stack it is challenging (`epl.select.compare`; tested).

### The threshold: **Δ ≤ −0.0010**

Justified in advance, on three grounds:

* 0.0010 RPS is **13%** of the measured Elo-to-market headroom (0.0077) and
  **15%** of the gap the model still owed the market after run 1 (0.0065). A
  lever worth less than that cannot move the question this probe asks.
* It is more than **twenty times** the ADVI seed noise measured on this very
  objective (§3.1: 0.0000454), which was measured rather than assumed.
* It is **below the tuning window's own MDE**, and that is stated as a
  limitation rather than hidden. At n = 1,520 and a realised paired SD of
  0.03577 for DC versus Elo, the 80%-power two-sided MDE is **0.00257**. A gain
  at the threshold is therefore **not established** by the tuning window. This is
  exactly the position `promoted_offset` was in in v1 (0.00131 against an MDE of
  0.00415), and it was adopted there on curve shape plus independent replication
  rather than on the raw gap. Conditions B1–B4 are that same standard of
  evidence, written down in advance.

### Every condition, all required

| | condition |
|---|---|
| **A** | `delta <= -0.0010` on the tuning objective. |
| **B1** | **Curve shape.** For a continuous dial the chosen point must be an interior optimum of the swept grid, or an endpoint reached monotonically whose neighbour also beats the incumbent by at least half the threshold. No adoption off an isolated point. A **binary** gate (I4) has no curve and is judged on A, B2, B3 and B4. **Completing** a dial (running a missing INTERIOR point between values already swept) is allowed; **extending** one beyond the grid's ends after seeing results is forbidden. |
| **B2** | **Season stability.** The sign must hold in at least **3 of the 4** tuning seasons. |
| **B3** | **Sign agreement.** Mean log loss must move the same way as RPS. |
| **B4** | **Noise floor**, for fit-touching gates only (I1a, I4 re-run ADVI over a changed panel or design): `|delta|` must exceed **3×** the measured seed-replica `|delta|`. I2 and I3 act at predict time and share their arm's posterior *exactly*, so no optimiser noise separates them from their control and B4 does not apply to them. |

### The order: greedy, **I1a → I4 → I3 → I2**

Fixed before any tuning number was seen. Gates that change the **fit** are
settled first, so that every predict-time gate is tuned against the posterior it
will actually wrap rather than against one the final stack will not use. Within
each tier the order is by expected magnitude: recency weighting is the largest
lever in the literature; congestion is the weakest fit-level candidate but must
still be settled before the predict-time gates because it changes the posterior.

At each step the **best** point of that gate's grid is put to the rule. If no
point satisfies every condition the gate is **rejected and the stack is
unchanged** — that is the default, and it is what happened four times.

### One efficiency that is also a design choice

I2 and I3 act only at predict time, so `run_sweep` fits **once** per cutoff and
prices every predict-time variant off that one posterior. This is cheaper, but
the reason it is done is that it makes those comparisons exact: two predict-time
variants scored off one posterior differ by the lever and by nothing else, with
zero optimiser noise between them. That is why their paired SDs in §3 are so
small (0.0013–0.0075 against 0.0358 for DC versus Elo) and why B4 is not applied
to them. The sharing is proved inert — a real fit priced through the base and
through the shared view is compared with `np.array_equal`, and the control arm
of the real sweep was checked bit-for-bit against the bare
`dcfit.fit_epl` + `Posterior.predict_1x2` path that produced run 1.

### Two clauses added after launch, before any result

B1's binary-gate exemption and its completing-versus-extending clause were
written after the sweeps started and **before any scoring code had run**. They
are recorded as an amendment rather than presented as original, because the
alternative — silently improving a rule mid-flight — is the failure mode this
document exists to prevent. Neither clause affects the outcome: nothing reached
B1.

---

## 3. Every specification tried, with its tuning score

The anti-domain-shopping ledger. **45 specifications evaluated as challengers**
— 44 model variants across 5 fit arms (`OFF`, `decay 270`, `decay 180`,
`decay 120`, `congestion`), each arm carrying the same 9-point predict-time
grid, plus the fortnightly-cadence walk — across **47 walk-forward ledgers**
once the control and the ADVI seed replica are counted: **924 Dixon-Coles fits
producing 6,604 variant-cutoff rows**, all on disk under
`data/epl/fit/improve/`, one JSONL per variant, in the row schema
`epl.improve.run_walk` writes.

Deltas are versus the **OFF control** (the frozen configuration on the tuning
window) unless stated. Negative = better. `seas` is the number of the four
tuning seasons in which the sign held (condition B2).

**The control.** Frozen DC on the tuning window: RPS **0.195670**, against
walk-forward Elo's **0.195524**. DC − Elo = **+0.000146**, 95% CI
[−0.001763, +0.002044], paired SD 0.03577 over 142 (season, ISO-week) blocks.
On the tuning window the model is, if anything, a hair *worse* than Elo — the
opposite sign to run 1's −0.001172 on the confirmatory window. Both are deep
inside noise and they do not agree in sign. That, before any lever is
considered, is what "these are the same forecaster to within noise" looks like.

### 3.1 The noise floor, measured first

The whole 142-cutoff walk was repeated at ADVI seed 987654, changing nothing
else.

| | |
|---|---:|
| control RPS (frozen seed) | 0.1956699 |
| replica RPS (seed 987654) | 0.1957153 |
| **Δ from the seed alone** | **+0.0000454** |
| paired SD of the seed difference | 0.004497 |
| its own 80%-power MDE | 0.000323 |
| 95% CI | [−0.000187, +0.000259] |
| **3 × floor — the B4 bar for I1a and I4** | **0.000136** |

Per-match probabilities move by a paired SD of 0.0045 between seeds, and that
noise is near zero-mean, so it averages down to 4.5e-5 on the objective. This is
the number every fit-touching gate has to clear before its gain can be called a
lever rather than an optimiser.

### 3.2 I1a — the decay half-life (fit-level dial). REJECTED, wrong-signed

| `decay_half_life_days` | tuning RPS | Δ vs control | paired SD | its MDE | 95% CI | seas |
|---|---:|---:|---:|---:|---|---:|
| **365 (shipped, the control)** | **0.195670** | — | — | — | — | — |
| 270 | 0.195691 | **+0.000022** | 0.00903 | 0.000649 | [−0.000445, +0.000503] | 1/4 |
| 180 | 0.196235 | **+0.000565** | 0.02323 | 0.001669 | [−0.000651, +0.001797] | 0/4 |
| 120 | 0.197444 | **+0.001774** | 0.03797 | 0.002729 | [−0.000193, +0.003776] | 0/4 |

**Verdict: REJECTED on A**, and not narrowly — every point is on the wrong side
of zero, and the damage is **monotone in how much memory is removed**. The
executed rule also records B1 as failed, and it is worth being precise about
what that means here: the optimum of the swept dial is the **incumbent's own
point** (365 d, Δ = 0 by construction) at the grid's edge, so the shape test is
reporting "the incumbent wins this dial", which is redundant with A rather than
an independent objection. The independent failures at this step are A and B2
(1 of 4 seasons) and B4 (0.000022 against a 3× floor of 0.000136). At 120
days the cost (0.00177) is larger than the entire DC-versus-Elo gap run 1
measured. The paired SD grows with the deviation (0.009 → 0.023 → 0.038), which
is the signature of a real change to the fit rather than of noise.

The premise was wrong, and it is worth saying why, because it was a plausible
premise. `decay_half_life_days = 365` was chosen for international football
where a team plays ~10 matches a year, and an EPL club plays 38 — so 365 days
looked far too long. In *match* units it is not: 365 days of Premier League is
already about 38 matches, which is roughly one squad-lifetime. Shortening it
below that does not remove stale squads, it removes the data the hierarchical
model needs to separate 20 attack and 20 defence parameters. The lever's own
mechanism runs out before the calendar argument starts.

### 3.3 I4 — congestion / rest differential (fit-level binary gate)

Evaluated at the OFF arm, because I1a was rejected and the greedy order settles
the stack before moving on. `model.covariates.enabled = ["rest_days"]`, which
`wcmodel` threads end to end: `features.build` emits per-team `rest_days` from
prior fixtures only, `scoreline._build_covariates` fits one standardization on
the pre-cutoff training rows, and one shared beta multiplies each side's
standardized rest on its own rate, so only the **differential** moves the 1X2
split.

| | tuning RPS | Δ vs control | paired SD | its MDE | 95% CI | seas |
|---|---:|---:|---:|---:|---|---:|
| **off (the control)** | **0.195670** | — | — | — | — | — |
| `congestion` | 0.195772 | **+0.000102** | 0.00689 | 0.000495 | [−0.000173, +0.000410] | 2/4 |

Per season: 2015/16 −0.00032, 2016/17 +0.00064, 2017/18 +0.00018, 2018/19
−0.00009.

**Verdict: REJECTED on A** (wrong sign), and on **B2** (2 of 4) and **B4**
(0.000102 against a 3× floor of 0.000136 — the gain is *inside* the ADVI noise
band, so even its sign is not established). Note that `improve.py`'s plumbing
smoke had recorded congestion as the gate that moved the forecast most (mean
|Δp| 0.036); it wrote that number down with the warning that enabling it re-runs
ADVI over a changed design and part of the movement is optimiser noise. Measured
properly against the seed-replica floor, that is what it turns out to be: a
covariate that reshuffles individual forecasts and buys nothing on average.

That is not a surprising result for this covariate. Published rest/congestion
effects on match outcome are small once team strength is controlled for, and the
`rest_days` the archive supports is coarse: `predict_rest_days` filters
`date < cutoff` as well as `date < fixture`, so a Wednesday fixture priced by
Saturday's weekly fit measures rest from before Saturday. That is stale, never
leaky — the model sees strictly less — but it blunts the very differential the
covariate exists to capture. A finer answer needs a finer cadence, which §3.6
shows is itself worth more than this covariate is.

### 3.4 I3 — the faster-adapting home term (predict-time dial). REJECTED, wrong-signed

Shares the control's posterior exactly, so these comparisons carry no optimiser
noise at all — hence the very small paired SDs and MDEs.

| `home_term_blend` @ `half_life` | tuning RPS | Δ vs control | paired SD | its MDE | 95% CI | seas |
|---|---:|---:|---:|---:|---|---:|
| **0 (the control)** | **0.195670** | — | — | — | — | — |
| 1.0 @ 180 d | 0.195747 | **+0.000078** | 0.00262 | 0.000188 | [−0.000059, +0.000221] | 1/4 |
| 0.5 @ 90 d | 0.195755 | **+0.000085** | 0.00376 | 0.000271 | [−0.000114, +0.000290] | 1/4 |
| 1.0 @ 90 d | 0.195884 | **+0.000214** | 0.00752 | 0.000540 | [−0.000184, +0.000628] | 1/4 |

**Verdict: REJECTED on A** (wrong sign), and it would have failed **B2** too:
every variant improves exactly one season, 2016/17, and damages the other three.

A note on B1, because this is the one place the grid-completion clause could
have been invoked and was not needed. The best of the three sits at
`blend = 1.0 @ 180 d`, and that half-life carries only two points on its blend
dial (0 and 1.0), so `dial_shape` reports "only 2 points; a shape needs three".
B1's completion clause would have permitted running `blend = 0.5 @ 180 d` — an
interior point between values already swept — to settle it. It was not run,
because A had already failed on **sign**: no shape can rescue a lever whose
every point makes the objective worse. The clause is recorded as unused rather
than quietly dropped.
The harm scales cleanly with the blend and with how fast the fast half-life is —
0.5@90d ≈ half of 1.0@90d — which says the estimator is doing what it was built
to do and that what it is doing is not wanted here. The tuning window contains
no home-advantage regime change; the mechanism was motivated by 2020/21's
closed-doors step, which lies in the **confirmatory** window, and this
preregistration would not let it be tuned there. So the honest reading is
narrower than "the home term does not help": it is **"a faster home term does
not help on a window with no home-advantage shock, which is the only window that
may be used to choose it."** The lever remains untested where its motivation
lives, and it stays untested.

### 3.5 I2 — season-break / transfer-window widening (predict-time dial). REJECTED

| variant | tuning RPS | Δ vs control | paired SD | its MDE | 95% CI | seas |
|---|---:|---:|---:|---:|---|---:|
| **0 (the control)** | **0.195670** | — | — | — | — | — |
| 0.10 @ hl 3 | 0.195647 | **−0.000023** | 0.00135 | 0.000097 | [−0.000089, +0.000042] | 2/4 |
| 0.20 @ hl 3 | 0.195630 | **−0.000040** | 0.00270 | 0.000194 | [−0.000172, +0.000088] | 2/4 |
| **0.35 @ hl 3** | **0.195615** | **−0.000055** | 0.00471 | 0.000339 | [−0.000281, +0.000169] | 2/4 |
| 0.20 @ hl 6 | 0.195624 | −0.000046 | 0.00344 | 0.000247 | [−0.000207, +0.000113] | 2/4 |
| 0.20 @ hl 3 **+ January** | 0.195701 | **+0.000031** | 0.00351 | 0.000252 | [−0.000132, +0.000195] | 2/4 |

**Verdict: REJECTED on A** — the best point is 5.5e-5, i.e. **5.5% of the
threshold** and 1.2 times the seed-noise floor — **and on B1 and B2
independently.** B1: the strength dial is monotone with its optimum at the
grid's edge, and the neighbour (0.20, −0.000040) does not beat half the
threshold, so no shape supports 0.35. B2: two seasons of four.

Two mechanism-level observations, which are more informative than the magnitudes:

1. **The gain is proportional to the strength and nearly indifferent to the
   trigger's decay.** 0.35@hl3 (−0.000055) and 0.20@hl6 (−0.000046) are almost
   the same number, and both are close to a straight scaling of 0.10@hl3. That
   is the signature of **uniform blunting of an over-confident forecast**, not of
   a break-specific effect. Run 1 recorded exactly that over-confidence — the
   model's mean top-pick probability was higher than the market's while being
   less accurate. Turning any entropy dial up will buy a sliver of RPS from it.
2. **Adding the January window makes it worse.** The +January variant fires the
   same mechanism on *more* genuine squad-change events and loses 0.00007
   relative to the same strength without it. If the break trigger were locating
   real squad-turnover uncertainty, the January window is where it should have
   shown up most clearly. It did the opposite. That is evidence against the
   trigger, not merely evidence that the effect is small.

### 3.6 I1b — refit cadence. Measured for the record; **not eligible for adoption**

The preregistered weekly walk is already the finest cadence the day-resolution
feature layer supports, so the only reachable direction is staler, i.e. worse.
`ADOPTION_RULE["not_eligible"]` says so in advance. It was run once anyway,
because "staleness costs something" should be a number and not an assumption.

| | |
|---|---:|
| cadence | 2 matchweeks (72 fits instead of 142) |
| tuning RPS | 0.196458 |
| **Δ vs the weekly control** | **+0.000788** |
| 95% CI | **[+0.000267, +0.001318]** — excludes zero |
| its own MDE | 0.000759 |
| DC − Elo at this cadence | +0.000934 (against +0.000146 weekly) |

**A fortnightly refit costs 0.00079 RPS, and this window can resolve it.** It is
the only effect in the entire sweep whose CI excludes zero. That is worth
holding next to §3.2: making the model's information **fresher** is worth
something measurable, while making its **memory shorter** is not — which is a
coherent picture (recency of the *conditioning set* matters; the *weighting* of
old matches inside the likelihood was already at the right scale) and a small
vindication of run 1's decision to refuse the fortnightly cadence the task
instruction had suggested.

### 3.7 The complete ledger — all 45 challengers, ranked

Rows 1–45 are the model variants, sorted best to worst on the tuning objective;
row 9 is the control they are all measured against, so the 44 rows around it plus
the fortnightly walk are the **45 challengers**. The two footer rows — the
cadence walk and the seed replica — sit outside the sort because neither is a
model variant. The threshold is **−0.0010**; the best row is **−0.000065**.

The five fit arms are `off`, `decay=270d`, `decay=180d`, `decay=120d` and
`congestion`; a row combining an arm with a predict-time gate is an interaction
cell the greedy order never reached, recorded because it was run.

| # | specification | fit arm | tuning RPS | Δ vs control | Δ log loss | seas | Δ vs Elo |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | `decay=270d/break=0.35@hl3` | decay=270d | 0.195605 | -0.000065 | -0.000162 | 2/4 | +0.000081 |
| 2 | `decay=270d/break=0.2@hl6` | decay=270d | 0.195608 | -0.000062 | -0.000106 | 2/4 | +0.000084 |
| 3 | `break=0.35@hl3` | off | 0.195615 | -0.000055 | -0.000277 | 2/4 | +0.000091 |
| 4 | `break=0.2@hl6` | off | 0.195624 | -0.000046 | -0.000196 | 2/4 | +0.000100 |
| 5 | `break=0.2@hl3` | off | 0.195630 | -0.000040 | -0.000200 | 2/4 | +0.000106 |
| 6 | `decay=270d/break=0.2@hl3` | decay=270d | 0.195633 | -0.000037 | -0.000029 | 2/4 | +0.000109 |
| 7 | `break=0.1@hl3` | off | 0.195647 | -0.000023 | -0.000114 | 2/4 | +0.000123 |
| 8 | `decay=270d/break=0.1@hl3` | decay=270d | 0.195659 | -0.000011 | +0.000097 | 2/4 | +0.000135 |
| 9 | **`off` — THE CONTROL** | off | 0.195670 | — | — | — | +0.000146 |
| 10 | `decay=270d/break=0.2@hl3+jan` | decay=270d | 0.195687 | +0.000018 | +0.000242 | 2/4 | +0.000164 |
| 11 | `decay=270d` | decay=270d | 0.195691 | +0.000022 | +0.000254 | 1/4 | +0.000168 |
| 12 | `break=0.35@hl3/congestion` | congestion | 0.195698 | +0.000028 | +0.000139 | 1/4 | +0.000174 |
| 13 | `break=0.2@hl3+jan` | off | 0.195701 | +0.000031 | +0.000133 | 2/4 | +0.000177 |
| 14 | `break=0.2@hl6/congestion` | congestion | 0.195714 | +0.000044 | +0.000267 | 1/4 | +0.000190 |
| 15 | `break=0.2@hl3/congestion` | congestion | 0.195721 | +0.000051 | +0.000267 | 1/4 | +0.000197 |
| 16 | `decay=270d/home=1@hl180d` | decay=270d | 0.195738 | +0.000068 | +0.000379 | 1/4 | +0.000214 |
| 17 | `break=0.1@hl3/congestion` | congestion | 0.195743 | +0.000073 | +0.000390 | 2/4 | +0.000220 |
| 18 | `home=1@hl180d` | off | 0.195747 | +0.000078 | +0.000205 | 1/4 | +0.000224 |
| 19 | `home=0.5@hl90d` | off | 0.195755 | +0.000085 | +0.000202 | 1/4 | +0.000231 |
| 20 | `decay=270d/home=0.5@hl90d` | decay=270d | 0.195760 | +0.000090 | +0.000418 | 1/4 | +0.000236 |
| 21 | `congestion` | congestion | 0.195772 | +0.000102 | +0.000548 | 2/4 | +0.000248 |
| 22 | `break=0.2@hl3+jan/congestion` | congestion | 0.195790 | +0.000120 | +0.000594 | 1/4 | +0.000266 |
| 23 | `home=1@hl180d/congestion` | congestion | 0.195844 | +0.000174 | +0.000747 | 1/4 | +0.000320 |
| 24 | `home=0.5@hl90d/congestion` | congestion | 0.195849 | +0.000180 | +0.000747 | 1/4 | +0.000326 |
| 25 | `decay=270d/home=1@hl90d` | decay=270d | 0.195863 | +0.000193 | +0.000702 | 1/4 | +0.000339 |
| 26 | `home=1@hl90d` | off | 0.195884 | +0.000214 | +0.000558 | 1/4 | +0.000360 |
| 27 | `home=1@hl90d/congestion` | congestion | 0.195972 | +0.000302 | +0.001100 | 0/4 | +0.000448 |
| 28 | `decay=180d/break=0.2@hl6` | decay=180d | 0.196079 | +0.000409 | +0.002139 | 1/4 | +0.000555 |
| 29 | `decay=180d/break=0.35@hl3` | decay=180d | 0.196087 | +0.000417 | +0.002130 | 1/4 | +0.000563 |
| 30 | `decay=180d/break=0.2@hl3` | decay=180d | 0.196141 | +0.000471 | +0.002386 | 0/4 | +0.000617 |
| 31 | `decay=180d/break=0.2@hl3+jan` | decay=180d | 0.196165 | +0.000495 | +0.002523 | 0/4 | +0.000641 |
| 32 | `decay=180d/break=0.1@hl3` | decay=180d | 0.196185 | +0.000515 | +0.002600 | 0/4 | +0.000661 |
| 33 | `decay=180d` | decay=180d | 0.196235 | +0.000565 | +0.002854 | 0/4 | +0.000711 |
| 34 | `decay=180d/home=1@hl180d` | decay=180d | 0.196235 | +0.000565 | +0.002854 | 0/4 | +0.000711 |
| 35 | `decay=180d/home=0.5@hl90d` | decay=180d | 0.196277 | +0.000607 | +0.002954 | 0/4 | +0.000754 |
| 36 | `decay=180d/home=1@hl90d` | decay=180d | 0.196337 | +0.000667 | +0.003120 | 0/4 | +0.000813 |
| 37 | `decay=120d/break=0.2@hl6` | decay=120d | 0.197204 | +0.001534 | +0.007574 | 0/4 | +0.001680 |
| 38 | `decay=120d/break=0.35@hl3` | decay=120d | 0.197224 | +0.001554 | +0.007625 | 0/4 | +0.001700 |
| 39 | `decay=120d/break=0.2@hl3+jan` | decay=120d | 0.197296 | +0.001626 | +0.008011 | 0/4 | +0.001772 |
| 40 | `decay=120d/break=0.2@hl3` | decay=120d | 0.197309 | +0.001639 | +0.008056 | 0/4 | +0.001785 |
| 41 | `decay=120d/break=0.1@hl3` | decay=120d | 0.197373 | +0.001703 | +0.008398 | 0/4 | +0.001849 |
| 42 | `decay=120d/home=1@hl180d` | decay=120d | 0.197405 | +0.001735 | +0.008688 | 0/4 | +0.001881 |
| 43 | `decay=120d` | decay=120d | 0.197444 | +0.001774 | +0.008791 | 0/4 | +0.001920 |
| 44 | `decay=120d/home=0.5@hl90d` | decay=120d | 0.197459 | +0.001789 | +0.008826 | 0/4 | +0.001935 |
| 45 | `decay=120d/home=1@hl90d` | decay=120d | 0.197479 | +0.001809 | +0.008876 | 0/4 | +0.001955 |
| — | `cadence=2w` — the 45th challenger, not eligible (§3.6) | off | 0.196458 | +0.000788 | +0.002515 | 0/4 | +0.000934 |
| — | `off` at ADVI seed 987654 (diagnostic, §3.1) | off | 0.195715 | +0.000045 | +0.000242 | 1/4 | — |

Two readings of this table are worth stating.

**The arms dominate the levers.** Every row on the `decay=120d` arm is worse
than every row on `decay=180d`, which is worse than every row on the `off` and
`decay=270d` arms. The fit-level choice sets the level and the predict-time gates
move it by an order of magnitude less. Whatever the greedy order had adopted at
step 1 would have determined nearly everything; it adopted nothing.

**No interaction rescues anything.** The best cell in the entire table combines
the best two individually-non-significant moves (`decay=270d` + `break=0.35@hl3`)
and reaches −0.000065, which is essentially the sum of its parts (+0.000022 and
−0.000055 give −0.000033; the extra −0.000032 is 0.7 times the arm's own ADVI
noise floor, i.e. indistinguishable from additivity).
There is no combination on this grid where two levers together do something
neither does alone, which is the specific thing a full-factorial sweep exists to
look for. That is why the greedy order, which cannot see interactions, costs
nothing here — and it is a statement about this grid, not a general licence.

### 3.8 Rejected on design, deliberately not scored

* **I1c — a genuine time-varying-strength state.** Not attempted. A random walk
  on attack/defence is a different likelihood, not a gated variant of this
  model; it would have to be a separate model with its own fit, ledger and
  control arm. I1a was its cheap approximation and I1a made things worse, which
  lowers rather than raises the prior on the full version.
* **I5 — managerial change.** Feasibility investigated against the live Wikidata
  source (20 clubs, 116 spells since 2014-06-01, 114 at day precision; CC0;
  public SPARQL, no scraping) and dropped: today's statement set is
  CURRENT_ONLY, so pricing a 2019 fixture from it is unprovable in provenance,
  and the defensible model of a sacking is variance inflation, which I2 already
  implements from an observable the archive contains — and I2 did not work. The
  query and counts are pinned in `epl.improve.I5_WIKIDATA_QUERY` /
  `I5_FEASIBILITY` and asserted in a test.
* **Re-tuning the architecture's own priors** (`sigma_att`, `k_att`,
  `rho_scale`, `widening.strength`). Still out of scope, for v1 §7's reason: it
  would make this an EPL-flavoured variant that can no longer be read against
  the two negatives the World Cup version published.
* **Bivariate Poisson instead of Dixon-Coles.** Available and not run. Trying
  both and reporting the better one is a two-shot test reported as one.
* **Extending any dial past its grid** after seeing the results — e.g. decay 450
  or 550 once 270 < 365 was visible, or break strength 0.5 once the curve was
  seen rising. Forbidden by B1 and not done. The decay curve's monotone shape
  does *suggest* the optimum may lie above 365; that is a hypothesis for a
  future design with its own preregistration, not a result of this one.

### 3.9 The result does not depend on the threshold

The obvious suspicion about any threshold is that it was chosen to produce the
answer. Here it cannot have been. Move the threshold to **zero** — adopt
anything with a favourable point estimate — and re-run the same greedy order:

* **Step 1 (I1a)** still rejects, because every decay point is on the wrong side
  of zero. Nothing on the `decay=270d` arm is reachable thereafter, including the
  table's overall best cell.
* **Step 2 (I4)** and **step 3 (I3)** still reject, for the same reason.
* **Step 4 (I2)** now passes A at `0.35@hl3` (−0.000055) and still fails **B1**
  (endpoint optimum whose neighbour, −0.000040, does not support it) and **B2**
  (2 seasons of 4).

So no setting of A alone adopts anything, and the one gate that a
threshold of zero would let through is stopped by two conditions that were
written down before the sweep and have nothing to do with the threshold.

### 3.10 The greedy trace, as executed by `epl.select.selection_trace`

Four steps, in the preregistered order, each putting its gate's **best** point to
the rule. `epl.select.adopt` returns every condition's own answer, so a rejected
gate records *why*.

| step | gate | best point | Δ | A | B1 | B2 | B3 | B4 | **ADOPT** |
|---|---|---|---:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 | I1a decay | `decay=270d` | +0.000022 | ✗ | ✗ | ✗ (1/4) | ✓ | ✗ | **No** |
| 2 | I4 congestion | `congestion` | +0.000102 | ✗ | n/a | ✗ (2/4) | ✓ | ✗ | **No** |
| 3 | I3 home term | `home=1@hl180d` | +0.000078 | ✗ | ✗ | ✗ (1/4) | ✓ | n/a | **No** |
| 4 | I2 break widening | `break=0.35@hl3` | −0.000055 | ✗ | ✗ | ✗ (2/4) | ✓ | n/a | **No** |

Every gate fails **A**, and three of the four fail on two further conditions
independently. B3 passes everywhere, which is worth one line: log loss and RPS
agree on the *sign* of every gate's effect, including on the three gates whose
sign is unfavourable. The two metrics are not disagreeing about anything here —
they simply both say there is nothing.

The stack after step 4 is what it was before step 1.

---

## 4. The final frozen stack, verbatim

**The stack is `epl.improve.Improvements()` — every gate off — which
`epl.improve.wcmodel_config` returns as `epl.freeze.frozen_wcmodel_config()`
byte for byte** (`test_off_config_is_byte_identical`), over the Elo
configuration of `epl/config_frozen.json`, which is unchanged from `b416925`:

```json
{
  "decay_half_life_days": null,
  "refit_cadence_weeks": null,
  "break_widen_strength": 0.0,
  "break_widen_half_life_matches": 3.0,
  "break_widen_january": false,
  "home_term_blend": 0.0,
  "home_term_half_life_days": 120.0,
  "congestion": false
}
```

```json
{
  "k": 20.0,
  "home_advantage": 40.0,
  "initial_rating": 1500.0,
  "promoted_offset": -75.0,
  "carryover": 1.0,
  "debut_offset": 0.0,
  "mov": false,
  "mov_shape": 0.8,
  "mov_base": 7.5,
  "mov_autocorr": 0.006
}
```

Refit cadence: **weekly**, one fit per (season, ISO calendar week), as v1 §5.
Sampler seed: the frozen configuration's own. Cold start: Fix 3. Anchor: Fixes
1 and 2. Nothing about the model that ran in run 1 has changed.

**The consequence, stated plainly: this phase produced no improvement.** Four
levers were built, gated, proved inert when off, and swept; all four failed.
That is the finding. It is not a failed phase, but it is a null one, and the
holdout section below is written for a null stack rather than for a stack we
hope will look good.

---

## 5. The fresh 2025/26 holdout: the rule as a number, and the power reality

### 5.1 The power reality, stated before the rule

| quantity | value |
|---|---:|
| holdout matches (all played, complete season) | **380** |
| paired SD, DC − Elo, measured on TUNE | 0.03577 |
| paired SD, DC − Elo, measured on CONFIRM (run 1) | 0.03993 |
| implied paired SE of the mean on 380 | 0.00184 – 0.00205 |
| **80%-power two-sided MDE on the holdout** | **0.0051 – 0.0057** |
| the effect actually being chased | **~0.001 – 0.002** |

**The fresh holdout cannot resolve the expected effect. It is roughly three to
five times too small.** Run 1's point estimate was −0.00117 and the tuning
window's is +0.00015; the holdout's MDE is 0.0057. To resolve an effect of
0.0012 at 80% power would need about **8,700 matches — 23 Premier League
seasons**; to resolve 0.0020 would need about **3,130 matches, 8.2 seasons**.
This holdout is 380 matches.

So the holdout's role is **a directional sanity check and a guard against
catastrophic regression, not confirmation.** Any reading of it as confirmation
would be dishonest, and this paragraph exists so that no such reading can be
introduced afterwards.

There is a second reason it is weaker than it looks here, and it should be said
now: **because nothing was adopted, the holdout cannot test the selection at
all.** The contrast that would have been well powered — final stack versus
frozen stack, paired, sharing almost all their noise — is identically zero by
construction. What remains is a third independent estimate of run 1's own
question.

### 5.2 The rule, as numbers

Let `Δ_H = mean RPS(final stack) − mean RPS(walk-forward Elo)` over all 380
matches of 2025/26, with a 95% block-bootstrap CI over (season, ISO-week)
blocks, 10,000 resamples. Negative = the model is better.

> **REGRESSION — the guard fires, and the probe STOPS.**
> `Δ_H ≥ +0.0057` (the holdout's own 80%-power MDE at the confirm-window SD),
> **or** the 95% CI lies entirely above zero.
> Either says the holdout had enough power to see harm and saw it. The reported
> conclusion then becomes that the architecture is worse than Elo on fresh EPL
> data, and run 1's negative-to-null reading is revised downward.
>
> **DIRECTIONAL PASS — weak, and explicitly NOT confirmation.**
> `Δ_H ≤ 0`. The sign agrees with run 1 on data never used for anything. Under
> the null this happens half the time, so on its own it licenses nothing; it is
> recorded because a *disagreeing* sign would also have been recorded.
>
> **INDETERMINATE — everything else**, i.e. `0 < Δ_H < +0.0057` with a CI
> crossing zero. **This is the expected outcome** and it is the correct report,
> not a failed one.

Secondary, reported and deciding nothing: mean log loss on the same 380; the
per-season calibration table; and `Δ_S = mean RPS(final stack) − mean RPS(frozen
stack)`, which **is identically 0.000000 by construction** in this version and
is printed anyway, because a future version of this document with a non-empty
stack must report it and the slot should already exist.

### 5.3 One thing the holdout genuinely adds: a pooled estimate

Reported as a **secondary**, flagged for what it is.

The same paired quantity now has three independent measurements on disjoint
fixtures: TUNE (n = 1,520, Δ = +0.000146), CONFIRM (n = 2,280, Δ = −0.001172),
and the holdout to come (n = 380). Inverse-variance pooling of the first two
alone gives

> **Δ pooled over 3,800 matches = −0.000574, 95% CI [−0.001785, +0.000638]**,
> paired SE 0.000618, MDE 0.00173.

Adding the holdout moves the pooled SE only from 0.000618 to about 0.000592 —
another way of saying 380 matches is not much. The pool is a **secondary**
because its inputs have different provenance: the tuning window's Elo
hyperparameters were themselves chosen on the tuning window in an earlier phase
(which helps both forecasters and so should largely cancel in a paired
difference, but is not provably neutral), and the confirm window has been read
once. It is reported for its precision, never as a preregistered primary, and it
does not enter any pass rule.

### 5.4 How the holdout will be run, fixed here

| | |
|---|---|
| seasons | 2025/26 only |
| matches | **380**, all played, all priced — an unpriceable fixture is a STOP |
| fits | **36**, one per (season, ISO calendar week), weekly cadence |
| cutoff | that matchweek's opening day at midnight |
| forecaster | the final stack of §4 — i.e. the frozen configuration |
| comparator | walk-forward Elo + ordered logit under the same frozen Elo config |
| market | **none.** No odds are read. 2025/26's odds coverage is a biased contiguous tail (210 of 380, prices stop 2026-01-08, home-win rate 0.452 covered vs 0.394 uncovered) and the DC-versus-Elo question does not need them. |
| command | `epl.select.run_sweep(OFF, window="holdout", holdout=True)` |
| touched | **exactly once.** No tuning, no re-running, no second variant. |

---

## 6. The confirmatory window: a SECOND LOOK, declared and conditional

2019/20–2024/25 has been scored once, at run 1, under v1's preregistration. Any
further scoring of it is a **SECOND LOOK** and multiplies. `epl.improve.run_walk`
and `epl.select.run_sweep` both refuse that window unless `second_look=True` is
passed, and then stamp the flag on every ledger row so two ledgers can never be
silently pooled.

**It is not executed in this phase, and the reason is not that it looked
unfavourable.** The final stack is bit-identical to the stack run 1 already
scored there, so re-running it would reproduce run 1's numbers exactly — it
would not be a second look at all, merely the same look recomputed. Spending a
declared second look on a guaranteed-identical answer would manufacture the
appearance of a second test without the substance of one.

The rule is written down anyway, so that a future stack that *does* differ
inherits it instead of inventing one:

> **If the final stack ever differs from the frozen stack**, the second look
> reports `Δ = mean RPS(stack) − mean RPS(Elo)` on the 2,280 matches under v1
> §3's rule (PASS requires `Δ ≤ −0.0034` **and** `hi < 0`; REJECT requires
> `lo > 0`), **and** the far better-powered paired contrast
> `mean RPS(stack) − mean RPS(frozen stack)` on the same fixtures. Both are
> labelled SECOND LOOK in the report title, not in a footnote.

### The multiplicity that already exists, acknowledged

Even with no number recomputed, the confirmatory window is **not blind with
respect to this phase's design**. The four levers were chosen after reading run
1's report, and specifically after reading two of its observations: that the
model's whole apparent edge sat on matches involving a promoted club (−0.0033 on
648), and that the model was better calibrated in the marginals while being more
confident and less accurate on individual fixtures. I2 (variance inflation on
low-information squads) and I3 (a faster home term, motivated by 2020/21's
closed-doors step) are direct descendants of confirm-window observations.

So: **the confirm window has already informed this phase, and a nominal 95%
interval computed on it would not be a 95% interval.** That is why the tuning
window was used for every decision, why the holdout exists, and why this
paragraph is here rather than in a reader's head afterwards.

---

## 7. What makes us STOP

Any of these halts the holdout run and is reported as a stop, not worked around.

1. **Regression on the holdout.** §5.2's guard: `Δ_H ≥ +0.0057` or a CI entirely
   above zero. Reported as a downward revision of run 1, not as an anomaly to
   investigate until it goes away.
2. **An unpriceable fixture.** Any of the 380 coming back without a finite
   forecast. 2025/26's promoted clubs are the exposure; Fix 3 exists so the count
   is zero, and scoring 379 would bias the sample toward matches the model finds
   easy.
3. **A failed point-in-time canary.** `epl.walkforward.point_in_time_canary`
   re-run end to end, with its positive control. A failure makes every number
   meaningless in the flattering direction.
4. **A frozen value needing to change.** If the run cannot complete without
   editing `epl/config_frozen.json`, it stops and reports why.
5. **Too good.** Not applicable here — no market column is read on the holdout —
   but if the holdout ever showed the model beating Elo by more than 0.0057 (its
   own MDE, in the model's favour) on 380 matches while the two better-powered
   windows found ±0.001, the first hypothesis is a bug, not an edge, and the run
   stops for a leak investigation before the number is reported as a result.
6. **Cost.** 36 fits, budgeted at under 10 minutes from the measured 4–8 s per
   tuning-window fit. If it exceeds 1 hour the run stops and reports the cost; it
   does not coarsen the cadence to fit the clock.

And two things that are explicitly **not** stops: a disappointing `Δ_H` — that is
the result — and an INDETERMINATE verdict, which §5.1 predicts in advance.

---

## 8. What is blind, and what is not

**Blind.** No forecast has been produced at any 2025/26 cutoff by any variant.
Every number in §3 comes from 2015/16–2018/19. `epl.select.run_sweep` cannot
reach 2025/26 without `holdout=True`, which no command run in this phase passed.

**Not blind, and it matters.**

1. The confirm window informed the *choice of levers* (§6). No confirm number
   was recomputed, but the design is downstream of run 1's report.
2. The Elo comparator's per-season scores on the tuning window were already
   published in `reports/epl_baseline.md`, and the frozen Elo configuration was
   itself chosen on the tuning window in an earlier phase. This phase chose no
   Elo parameter, but the comparator is not naive to this window.
3. The tuning window screened **45 specifications** against a threshold below its
   own MDE. That is a screen, not a test, and its outputs would have been
   hypotheses even if something had passed. Nothing did, which makes the
   multiplicity moot in one direction: a *null* from 37 attempts is stronger than
   a null from one, not weaker.

**Carried-forward caveats, unchanged from v1:** five tuning seasons have no
kickoff times, so same-day matches cannot inform one another; the Elo comparator
re-rates after every kickoff block while the model refits weekly on
day-resolution features, so the model works from strictly staler information
throughout and this is not corrected for (§3.6 now puts a number on what one
step of that staleness costs: 0.00079 per extra week).

---

## 9. What gets published either way

One report, `reports/epl_holdout.md`, containing: the 380-match RPS for the
stack and for Elo with block-bootstrap CIs; `Δ_H` against §5.2's rule in the
words REGRESSION, DIRECTIONAL PASS, or INDETERMINATE; `Δ_S` (zero, by
construction, and said to be so); log loss; the per-season and calibration
tables; the pooled three-window estimate of §5.3 flagged as secondary; the fit
diagnostics; every STOP condition with its status; and the measured cost.

If the verdict is INDETERMINATE — the outcome §5.1 predicts — the report says so
in its first paragraph, repeats that the holdout was never able to resolve the
effect, and does **not** go looking for a subset where the sign is favourable.

And it will carry the finding of this document, which is not the holdout's to
change: **four config-reachable improvements were built, gated, swept on a
window reserved for the purpose, and all four failed; two of them failed by
making the model worse.**
