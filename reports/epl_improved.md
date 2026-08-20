# The improved stack, scored: a SECOND LOOK at 2019/20–2024/25 and the fresh 2025/26 holdout

Executed 2026-08-15 on branch `epl-probe` under the preregistration committed at
`f4c16a8` (`reports/epl_prereg_v2.md`), which was itself written under
`reports/epl_prereg.md` at `b416925`. Not one frozen value was changed, and no
file under `src/` or `scripts/` was written. The full suite is green
(156 passed) and the preregistration lock reports **LOCK VALID**.

**NO BETTING.** On the confirmatory window the market column is an internal
accuracy benchmark, as it has been throughout. **On the holdout no odds are read
at all** — 2025/26's coverage is a biased contiguous tail (210 of 380, prices
stop 2026-01-08) and the DC-versus-Elo question needs no prices.

---

## The answer, in the first paragraph

**Nothing was adopted in the selection phase, so "the improved stack" is the
frozen configuration, byte for byte.** That is not a framing choice; it is
checked three ways in §1 before anything is scored. Two consequences follow and
neither is softened here. First, the **SECOND LOOK** at 2019/20–2024/25 is run
1's own answer recomputed from run 1's committed forecasts — DC 0.201942 against
Elo 0.203114, **Δ = −0.001172** [−0.002809, +0.000466] — and it is *not* a
second test, because the stack that would be tested is the stack already tested.
Second, on the **fresh 2025/26 holdout, touched exactly once, 380 of 380 priced**,
the model scored **0.209449 against walk-forward Elo's 0.208479**:
**Δ_H = +0.000971** (positive = the model is *worse*), 95% block-bootstrap CI
**[−0.002643, +0.004469]**. Against the preregistered rule that is
**INDETERMINATE** — the outcome v2 §5.2 named in advance as expected, on a
window v2 §5.1 said in advance could not resolve the effect.

The ablation asked for is therefore empty at the top and full underneath: **no
improvement contributed anything on held-out data, because none was adopted**,
and the four levers that were built all failed on the tuning window — two of
them by making the objective *worse*. §5 publishes every one of them with its
number.

One more fact belongs in this paragraph because it cuts against the model. The
same paired quantity has now been measured on three disjoint windows and **the
three do not agree in sign**: TUNE +0.000146 (n = 1,520), CONFIRM −0.001172
(n = 2,280), HOLDOUT +0.000971 (n = 380). Pooled over 4,180 matches:
**−0.000445, 95% CI [−0.001604, +0.000715]**. The fresh data did not confirm run
1's favourable point estimate; it pointed the other way, by an amount neither
window can resolve.

---

## 1. What "the improved stack" is, proved before it is scored

`epl.holdout.assert_stack_is_frozen()` runs before the walk and refuses to
continue unless all three of these hold:

| check | result |
|---|---|
| the selected stack has every gate off (`Improvements().is_off()`) | **True**, spec `off`, `gates_enabled = []` |
| `improve.wcmodel_config(OFF)` is byte-identical (JSON, sorted keys) to `freeze.frozen_wcmodel_config()` | **True** |
| `epl/config_frozen.json` on disk is byte-identical to the blob committed at `b416925` | **True** (compared against `git show`, not against a transcription) |

The Elo comparator's configuration, unchanged since `b416925`:

```json
{"k": 20.0, "home_advantage": 40.0, "initial_rating": 1500.0,
 "promoted_offset": -75.0, "carryover": 1.0, "debut_offset": 0.0,
 "mov": false, "mov_shape": 0.8, "mov_base": 7.5, "mov_autocorr": 0.006}
```

Gates, all off: `decay_half_life_days=null` (shipped 365), `refit_cadence_weeks=null`
(weekly), `break_widen_strength=0.0`, `break_widen_half_life_matches=3.0`,
`break_widen_january=false`, `home_term_blend=0.0`,
`home_term_half_life_days=120.0`, `congestion=false`.

**So `Δ_S = mean RPS(final stack) − mean RPS(frozen stack) = 0.000000` — not
approximately, identically.** The two forecasters are the same object. The slot
exists because a future version of this document with a non-empty stack must
report it, and because "we checked and it was zero" is a different statement
from "we assumed it was zero".

---

## 2. Deviations from the preregistration, declared up front

Four, all recorded before any holdout number was read.

**(a) The report's filename.** v2 §9 names `reports/epl_holdout.md`; the task
instruction that launched this run names `reports/epl_improved.md`. This file is
that report under the instruction's name. Nothing about its required contents
changed — §9's list is discharged item by item below.

**(b) The holdout command was run with the one-point grid.** v2 §5.4 names
`epl.select.run_sweep(OFF, window="holdout", holdout=True)`, but that function's
**default** grid prices nine predict-time variants off every fit, which
contradicts the same table's "touched **exactly once** … no second variant". The
inconsistency is resolved in favour of the stronger clause: the named function
was called with `grid=({},)` — the identical `--control-only` restriction the
selection phase used for its seed replica — so **exactly one forecaster ever saw
2025/26**. The restriction can only remove variants; it cannot move a number.

**(c) Each fit was wrapped in a warning recorder.** `run_sweep` does not record
ADVI warnings, and they are to be reported per fit. `epl.holdout.run_holdout`
therefore calls the preregistered function once per cutoff (its own resume logic
makes call *k* fit cutoff *k* and nothing else) inside
`warnings.catch_warnings(record=True)`, exactly as `epl.walkforward._one_cutoff`
does. The capture is passive.

**(d) The walk was started twice.** The first attempt fitted cutoff 1 and then
aborted on a check in the *runner*, not in the model: the ledger stores
probabilities rounded to 8 decimals, three of which can sum to 1 ± 1.5e-8, and
the runner was demanding 1e-9. Measured worst |sum − 1| on that block:
**1.0e-8**. The tolerance was corrected to 1e-7 with the arithmetic written down
beside it, and the walk resumed; cutoff 1's ledger row was reused unchanged
(35 of the 36 fits were run after the restart). No forecast was affected, and
the abort is recorded here rather than quietly rerun.

---

## 3. SECOND LOOK — 2019/20–2024/25 (n = 2,280)

> **Every number in this section is a SECOND LOOK at a window that has already
> been scored once.** They are labelled as such in the section title, not in a
> footnote, per v2 §6.

### 3.1 Why no new fit was run

v2 §6 makes the second look **conditional**: it is executed if the final stack
*differs* from the stack run 1 scored there. It does not differ (§1). Re-fitting
212 cutoffs would reproduce run 1's forecasts and therefore run 1's numbers —
the same look recomputed, not a second test — and spending a declared second
look on a guaranteed-identical answer would manufacture the appearance of a
second test without the substance of one.

What is reported instead is run 1's committed ledger
(`data/epl/fit/walkforward_ledger.jsonl`, 212 rows) **re-scored end to end**.
That is not free of content: it re-executes the scoring path at this commit and
confirms it reproduces the published numbers to the last digit, which a report
that merely quoted them could not.

### 3.2 The improved stack against Elo and the market (SECOND LOOK)

| forecaster | n | RPS | log loss | accuracy |
|---|---:|---:|---:|---:|
| de-vigged market (proportional) | 2,280 | **0.195418** | 0.955675 | 55.57% |
| de-vigged market (Shin) | 2,280 | 0.195406 | 0.955706 | 55.57% |
| **improved stack — i.e. the frozen stack** | 2,280 | **0.201942** | 0.975479 | 53.90% |
| run 1's Dixon-Coles | 2,280 | **0.201942** | 0.975479 | 53.90% |
| walk-forward Elo + ordered logit | 2,280 | **0.203114** | 0.979158 | 54.12% |
| base rate (walk-forward H/D/A) | 2,280 | 0.234598 | 1.067828 | 43.55% |

The third and fourth rows are the same row. **improved stack − run-1 DC =
0.000000 on all 2,280 fixtures, by construction.**

| pair (SECOND LOOK) | mean Δ RPS | paired SD | 95% CI, week blocks (212) | 95% CI, season blocks (6) |
|---|---:|---:|---|---|
| **stack − Elo** | **−0.001172** | 0.039932 | **[−0.002809, +0.000466]** | [−0.003869, +0.002523] |
| stack − market | +0.006525 | — | [+0.004099, +0.008982] | — |
| Elo − market *(context)* | +0.007696 | — | [+0.005489, +0.009960] | — |
| **stack − frozen stack** | **0.000000** | 0.000000 | — | — |

Log loss, same window: stack − Elo = **−0.003680** [−0.008902, +0.001602]. Same
sign as RPS, same failure to separate.

### 3.3 The verdict under v1's rule (SECOND LOOK)

v1 §3: PASS if `Δ ≤ −0.0034` **and** `hi < 0`; REJECT if `lo > 0`; otherwise
INCONCLUSIVE. Δ = −0.001172, CI [−0.002809, +0.000466].

* PASS? **No** — Δ is 34% of the threshold and `hi` is above zero.
* REJECT? **No** — `lo` is below zero.
* **INCONCLUSIVE (precise null)** under the preregistered week blocking;
  **INCONCLUSIVE (underpowered)** under season blocking. Both are reported;
  neither is PASS.

**The pass rule is NOT MET.** Realised paired SD 0.039932 → achieved 80%-power
MDE 0.00234, so Δ is half the smallest effect this window could see.

### 3.4 Per season, the two preregistered subsets, calibration (all SECOND LOOK)

| season | n | stack | Elo | market | stack − Elo |
|---|---:|---:|---:|---:|---:|
| 2019/20 | 380 | 0.19891 | 0.20106 | 0.19836 | −0.00215 |
| 2020/21 | 380 | 0.21773 | 0.22336 | 0.21106 | **−0.00563** |
| 2021/22 | 380 | 0.19381 | 0.19586 | 0.18904 | −0.00205 |
| 2022/23 | 380 | 0.20902 | 0.20183 | 0.19750 | **+0.00719** |
| 2023/24 | 380 | 0.18892 | 0.19102 | 0.18046 | −0.00211 |
| 2024/25 | 380 | 0.20327 | 0.20554 | 0.19608 | −0.00228 |

| subset (v1 §2, preregistered there) | n | stack | Elo | stack − Elo | 95% CI (week blocks) |
|---|---:|---:|---:|---:|---|
| all | 2,280 | 0.20194 | 0.20311 | −0.00117 | [−0.00281, +0.00047] |
| ≥1 promoted club | 648 | 0.18251 | 0.18577 | −0.00326 | [−0.00745, +0.00095] |
| no promoted club | 1,632 | 0.20966 | 0.21000 | −0.00034 | [−0.00194, +0.00128] |

Calibration (mean forecast vs realised): realised H/D/A 0.4355 / 0.2303 / 0.3342;
stack 0.4350 / 0.2273 / 0.3377; Elo 0.4489 / 0.2305 / 0.3206; market 0.4374 /
0.2384 / 0.3243.

Diagnostics from the ledger, unchanged: 212 cutoffs, one anchor spec across all
of them, 0 warnings, 0 unhealthy posteriors, 0 unpriceable, 0 malformed,
6 cold-start events, 39 cutoffs with a provisional club, median fit 8.17 s,
training panels 1,900 → 4,167 matches.

### 3.5 The multiplicity that already exists, acknowledged

Even with no number recomputed, **this window is not blind with respect to the
selection phase**. I2 (variance inflation on low-information squads) and I3 (a
faster home term) were designed after reading run 1's report — specifically its
promoted-club subset (−0.0033 on 648) and its calibration/over-confidence
finding. So a nominal 95% interval computed here is not a 95% interval, and the
tuning window is why every decision was made somewhere else.

---

## 4. THE FRESH HOLDOUT — 2025/26 (n = 380), touched exactly once

Never scored for this model before this run, and never tuned on.

### 4.1 What was run

| | |
|---|---:|
| season | 2025/26, complete (380 played) |
| fits | **36**, one per (season, ISO calendar week), weekly cadence |
| cutoff | that matchweek's opening day at midnight |
| forecaster | the final stack of §1 — the frozen configuration |
| comparator | walk-forward Elo + ordered logit, same frozen Elo config |
| matches priced | **380** |
| matches scored | **380** — complete case, nothing dropped |
| **unpriceable fixtures** | **0** |
| malformed forecasts | **0** (worst \|sum − 1\| = 1.0e-8, the ledger's own 8-dp rounding) |
| training panels | 4,180 → 4,547 pre-cutoff matches |
| median fit | **9.93 s**; total model time **455.1 s** |
| **ADVI warnings** | **0, across all 36 fits, none suppressed** |
| cold-start clubs | **0** |
| cutoffs with a provisional club | **0** |
| odds read | **none** |

**ADVI warnings per fit: every one of the 36 is zero.** They were captured with
`warnings.catch_warnings(record=True)` around each fit and written to
`data/epl/fit/improve/holdout_off_warnings.json`, one row per cutoff, so the
claim is checkable per fit rather than in aggregate. The honest limitation run 1
recorded still stands and is not restated as more than it is: pymc 6.0.1's
`pm.fit(method="advi")` installs no convergence callback, so "0 warnings" means
"no fit raised and none produced an unusable posterior", **not** "each
variational optimisation was certified converged".

**That exactly one forecaster saw the season is checkable from the ledger, not
just asserted.** All 36 rows carry `spec = "off"`, `fit_arm = "off"`,
`window = "holdout"`, `holdout = true`, `second_look = false`,
`cadence_weeks = 1`, `off_protocol = false` and `home_shift = 0.0`; the team
index is 35 clubs at every cutoff; all 380 forecasts are finite.

**Two structural facts about this season, worth stating because they differ from
the confirmatory window.** Its three promoted clubs — Burnley, Leeds, Sunderland
— all have prior matches in the archive (304, 114 and 114 respectively; Sunderland's
last top-flight season here is 2016/17), so **Fix 3 (the cold start) was never
exercised on the holdout**: there was no club the fit had never seen. And **no
club tripped the provisional arm at any cutoff**, so `wcmodel`'s predict-time
mechanism-(c) widening was inert throughout — where on the confirmatory window
it fired at 39 of 212 cutoffs. Fix 2 (the promoted seed at `division_mean − 75`)
was exercised, on all three clubs.

### 4.2 The numbers

| forecaster | n | RPS | log loss | accuracy |
|---|---:|---:|---:|---:|
| **final stack (Dixon-Coles, frozen)** | 380 | **0.209449** | 1.028732 | 46.84% |
| walk-forward Elo + ordered logit | 380 | **0.208479** | 1.026146 | 46.84% |

| quantity | value |
|---|---:|
| **Δ_H = stack − Elo** | **+0.000971** |
| paired SD | 0.039914 |
| paired SE | 0.002048 |
| **95% CI, (season, ISO-week) blocks, 36 blocks, 10,000 resamples** | **[−0.002643, +0.004469]** |
| realised 80%-power MDE | 0.005737 |
| Δ_H on log loss | +0.002586, CI [−0.009227, +0.014060] |
| **Δ_S = stack − frozen stack** | **0.000000** (by construction) |

### 4.3 The preregistered rule, executed

> **v2 §5.2.** REGRESSION (the guard fires, the probe STOPS): `Δ_H ≥ +0.0057`
> **or** the 95% CI lies entirely above zero. DIRECTIONAL PASS (weak, NOT
> confirmation): `Δ_H ≤ 0`. INDETERMINATE: everything else.

* REGRESSION? **No.** Δ_H = +0.000971 is 17% of the +0.0057 guard, and the CI
  crosses zero.
* DIRECTIONAL PASS? **No.** Δ_H is above zero: on fresh data the model is a
  hair *worse* than Elo, not better.
* **Verdict: INDETERMINATE.** This is the outcome v2 §5.1 predicted in advance
  and called "the correct report, not a failed one".

Log loss agrees in sign with RPS (+0.0026, Elo ahead) and its interval also
crosses zero. Accuracy is identical to four decimal places: both forecasters
top-pick 178 of 380 correctly.

### 4.4 Calibration on the holdout (deciding nothing)

| | home | draw | away |
|---|---:|---:|---:|
| **realised** | 0.4263 | **0.2737** | 0.3000 |
| final stack | **0.4276** | 0.2355 | 0.3369 |
| Elo | 0.4433 | 0.2386 | **0.3181** |

2025/26 drew 27.4% of its matches — 4.3 points above the confirmatory window's
23.0% — and **neither forecaster could have known that in advance**; both
under-price the draw by about the same amount. The model is nearer on the home
marginal (+0.0013 against Elo's +0.0170); Elo is nearer on the away marginal
(+0.0181 against the model's +0.0369). Run 1 found the model the better-calibrated
forecaster on every marginal; on this season that does not repeat. One season of
380 is not evidence about calibration, and it is reported because it would have
been reported had it fallen the other way.

Two legibility notes, deciding nothing. The model's forecast beats Elo's on
**48.7%** of individual matches (51.8% on the confirm window), and the mean
absolute per-match RPS difference is **0.0276** — twenty-eight times the mean
difference, the same "these are nearly the same forecaster" signature run 1
recorded. Mean top-pick probability: stack 0.5220, Elo 0.5266 — on this season
the model is slightly *less* confident than Elo, the reverse of the confirm
window's over-confidence signature.

### 4.5 The power reality, restated after the fact because it was stated before

v2 §5.1 said, before the run: 380 matches at a paired SD of 0.0358–0.0399 gives
an 80%-power two-sided MDE of **0.0051–0.0057**, against an effect being chased
of ~0.001–0.002, so **the holdout is three to five times too small and its role
is a directional sanity check and a guard against catastrophic regression, not
confirmation**.

The realised paired SD was 0.039914 and the realised MDE **0.005737** — within
1% of the preregistered upper figure. Nothing about the arithmetic moved. To
resolve 0.0012 at 80% power needs about 8,700 matches (23 Premier League
seasons); to resolve 0.0020, about 3,130 (8.2 seasons).

And the sharper limitation v2 §5.1 also stated in advance: **because nothing was
adopted, the holdout cannot test the selection at all.** The contrast that would
have been well powered — final stack versus frozen stack, paired, sharing almost
all of its noise — is identically zero. What the holdout delivered is a third
independent estimate of run 1's own question, at a third of run 1's precision.

### 4.6 What is deliberately *not* reported on the holdout

* **No subset.** v2 §9 fixes the report's contents and no subset is in it. In
  particular the **promoted-club slice** — run 1's largest gap and the
  observation that motivated two of the four levers — is **not computed**, even
  though this season has 108 such matches. It was generated by reading the
  confirm window; its holdout counterpart would carry an MDE near 0.010 on ~100
  matches; and computing it now would be exactly the post-hoc subgroup
  confirmation the preregistration exists to prevent. The count is stated so a
  reader knows the slice was available and declined.
* **No market column.** No odds were read for 2025/26 anywhere in this run.
* **No second variant, no re-run, no tuning.** One forecaster, one pass.

---

## 5. The ablation: every improvement's contribution, individually and cumulatively

### 5.1 The top of the table is empty, and that is the finding

| adopted improvement | individual contribution on the holdout | cumulative contribution on the holdout |
|---|---:|---:|
| *(none)* | — | — |
| **total** | **0.000000** | **0.000000** |

**The adopted set is empty**, so every adopted improvement's individual and
cumulative contribution on held-out data is 0.000000 *by construction*, and there
is no ablation arm to remove. Publishing the ones that lost is the point of an
ablation, so the rest of this section is the losers, in full.

### 5.2 The greedy trace, re-executed at this commit

`epl.select.selection_trace` was re-run over the tuning ledgers and reproduces
the selection phase exactly. Threshold: **Δ ≤ −0.0010**. Measured ADVI
seed-noise floor on this objective: **0.0000454** (control 0.1956699, replica at
seed 987654 0.1957153), so the B4 bar for fit-touching gates is **0.000136**.

| step | gate | best point | Δ on TUNE | Δ log loss | seasons | 95% CI | A | B1 | B2 | B3 | B4 | ADOPT | stack after |
|---|---|---|---:|---:|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| 1 | I1a decay half-life | `decay=270d` | **+0.000022** | +0.000254 | 1/4 | [−0.000444, +0.000507] | ✗ | ✗ | ✗ | ✓ | ✗ | **No** | `off` |
| 2 | I4 congestion | `congestion` | **+0.000102** | +0.000548 | 2/4 | [−0.000176, +0.000407] | ✗ | n/a | ✗ | ✓ | ✗ | **No** | `off` |
| 3 | I3 home term | `home=1@hl180d` | **+0.000078** | +0.000205 | 1/4 | [−0.000058, +0.000218] | ✗ | ✗ | ✗ | ✓ | n/a | **No** | `off` |
| 4 | I2 break widening | `break=0.35@hl3` | **−0.000055** | −0.000277 | 2/4 | [−0.000281, +0.000171] | ✗ | ✗ | ✗ | ✓ | n/a | **No** | `off` |

The "stack after" column *is* the cumulative ablation: it never changes, so the
cumulative contribution after every step is zero, and the final stack equals the
stack the trace started from.

Every candidate at every step, with its own tuning score — the individual
contributions:

| gate | candidate | tuning RPS | Δ vs control | seasons |
|---|---|---:|---:|:-:|
| I1a | `decay=270d` | 0.195691 | +0.000022 | 1/4 |
| I1a | `decay=180d` | 0.196235 | +0.000565 | 0/4 |
| I1a | `decay=120d` | 0.197444 | +0.001774 | 0/4 |
| I4 | `congestion` | 0.195772 | +0.000102 | 2/4 |
| I3 | `home=1@hl180d` | 0.195747 | +0.000078 | 1/4 |
| I3 | `home=0.5@hl90d` | 0.195755 | +0.000085 | 1/4 |
| I3 | `home=1@hl90d` | 0.195884 | +0.000214 | 1/4 |
| I2 | `break=0.35@hl3` | 0.195615 | **−0.000055** | 2/4 |
| I2 | `break=0.2@hl6` | 0.195624 | −0.000046 | 2/4 |
| I2 | `break=0.2@hl3` | 0.195630 | −0.000040 | 2/4 |
| I2 | `break=0.1@hl3` | 0.195647 | −0.000023 | 2/4 |
| I2 | `break=0.2@hl3+jan` | 0.195701 | +0.000031 | 2/4 |

Control (frozen DC on the tuning window): **0.195670**, against Elo's 0.195524,
i.e. **DC − Elo = +0.000146** on TUNE — the opposite sign to the confirmatory
window, before any lever is considered.

**Two of the four levers are wrong-signed, not merely small.** Shortening the
likelihood half-life (I1a) and speeding up the home term (I3) both make the
objective worse, monotonically in how hard they are pushed. Congestion (I4) is
wrong-signed and its gain sits *inside* the measured ADVI noise band. Only I2 has
a favourable point estimate at all, and it reaches −0.000055 — **5.5% of the
adoption threshold**, 1.2× the seed-noise floor — while failing the curve-shape
and season-stability conditions independently of any threshold.

The remaining 33 specifications — the interaction cells the greedy order never
reached (e.g. `decay=270d/break=0.35@hl3` at −0.000065, the best cell anywhere in
the grid), plus the cadence walk of §5.3 — are listed in full in
`reports/epl_prereg_v2.md` §3.7, with the machine-readable ledgers under
`data/epl/fit/improve/`. **45 challengers were evaluated in total; the best of
them was −0.000065, i.e. 6.5% of the adoption threshold.**

### 5.3 The one effect the sweep could resolve, which is not an improvement

`I1b`, refit cadence, is **not eligible for adoption** (weekly is already the
finest cadence the day-resolution feature layer supports, so the only reachable
direction is staler). It was measured once for the record: a fortnightly refit
costs **+0.000788 RPS**, 95% CI **[+0.000267, +0.001318]** — the only effect in
the entire sweep whose interval excludes zero. Making the model's information
**fresher** is worth something measurable; making its **memory shorter** is not.

### 5.4 Why the rejected levers were not ablated on the holdout

Scoring a rejected lever on 2025/26 would touch the holdout more than once and
would let a variant that failed the tuning window be re-tried on fresh data —
selection *on* the holdout, forbidden by v2 §5.4 in the same sentence that grants
the single touch. The levers were measured where the preregistration says levers
are measured, and the numbers are above.

---

## 6. The pooled three-window estimate (SECONDARY — decides nothing)

Every input is read from the artifact that produced it, not transcribed: TUNE
from its own OFF ledger, CONFIRM from run 1's saved result, HOLDOUT from §4.

| window | n | Δ (stack − Elo) | paired SD | paired SE |
|---|---:|---:|---:|---:|
| TUNE 2015/16–2018/19 | 1,520 | **+0.000146** | 0.03577 | 0.000917 |
| CONFIRM 2019/20–2024/25 (run 1) | 2,280 | **−0.001172** | 0.039932 | 0.000836 |
| HOLDOUT 2025/26 | 380 | **+0.000971** | 0.039914 | 0.002048 |
| **inverse-variance pooled** | **4,180** | **−0.000445** | — | 0.000592 |

95% CI on the pool: **[−0.001604, +0.000715]**; its own 80%-power MDE 0.001658.
It is a **secondary** because its inputs have different provenance — the tuning
window chose the Elo hyperparameters in an earlier phase, and the confirm window
has now been read twice — and it enters no pass rule.

The three signs are **+, −, +**. That is what "these are the same forecaster to
within noise" looks like when you measure it three times.

---

## 7. Every preregistered STOP condition (v2 §7)

| # | condition | status |
|---|---|---|
| 1 | **Regression on the holdout** (`Δ_H ≥ +0.0057` or CI entirely above zero) | **Not triggered.** Δ_H = +0.000971, CI [−0.002643, +0.004469]. |
| 2 | **An unpriceable fixture** | **Not triggered.** 0 of 380; every fixture priced. |
| 3 | **A failed point-in-time canary** | **Not triggered — canary PASSED.** Rewrote 1,717 post-cutoff results to 9-0: pre-cutoff forecasts bit-identical (max \|Δp\| = 0.0); positive control moved (max \|Δp\| = 0.8118). |
| 4 | **A frozen value needing to change** | **Not triggered.** `epl/config_frozen.json` byte-identical to `b416925`; the wcmodel config byte-identical to `freeze.frozen_wcmodel_config()`. |
| 5 | **Too good** (model beating Elo by more than 0.0057 on 380) | **Not triggered**, and not close: Δ_H is +0.000971, i.e. in Elo's favour. No leak signature. |
| 6 | **Cost above 1 hour** | **Not triggered.** Wall clock 40.2 min; see §8. |

---

## 8. Cost, reported honestly in two numbers

| | |
|---|---:|
| fits | 36 |
| **total model time** (sum of the fits themselves) | **455.1 s = 7.6 min** |
| median fit | 9.93 s |
| median per-call wall time | 12.0 s |
| **total wall clock** | **2,411.8 s = 40.2 min** |

The two numbers differ because **two of the 36 calls took ~16 minutes each**
(966 s and 960 s) while their own fits took 39.7 s and 42.0 s; a third took 84 s.
Those three account for 2,010 s of the 2,412 s. The machine was shared during the
run (load average ≈ 6.7, a macOS daemon at ~93% CPU, other user applications), so
the stalls are environmental and touch no forecast — every fit is a pure function
of (cutoff, store, frozen config). The preregistered budget was one hour of wall
clock and it was not exceeded, so nothing was coarsened; had it been exceeded,
the honest report would have been the stop plus both numbers, not a coarser
cadence.

The second look and the ablation ran no fit at all.

---

## 9. What this settles, and what it does not

**Settled.** The selection phase produced no improvement, and the holdout could
not have rescued one: with an empty adopted set the well-powered contrast is
identically zero. On a Premier League season never used for anything, priced
weekly by the frozen architecture, the hierarchical Dixon-Coles model is
**+0.00097 RPS behind walk-forward Elo**, with an interval that comfortably
contains zero and a design that could not have resolved the effect either way.
No regression guard fired; no leak signature appeared; every fixture got a
number; no fit warned.

**Settled negatively, and worth saying plainly.** Run 1's point estimate favoured
the model by 0.00117. The first genuinely fresh data since then favours **Elo**
by 0.00097. Pooling all 4,180 matches leaves −0.000445 with a CI spanning zero.
Anyone reading run 1's five-of-six-seasons pattern as a small real edge should
now also read this: the sixth independent season did not continue it.

**Not settled.** Whether there is a real edge of 0.001–0.002 either way. Three
windows, 4,180 matches and 390 control-arm fits later (924 counting the whole
selection sweep), the pooled interval is
[−0.0016, +0.0007] and the honest design for the question — a multi-league panel
or ~23 Premier League seasons — remains what it was.

**Not settled, and named in advance as disfavouring the model.** The Elo
comparator re-rates after every kickoff block; the model refits weekly on
day-resolution features. §5.3's cadence measurement now puts a number on one step
of that staleness: 0.00079 RPS per extra week. That is comparable in size to the
entire effect being argued about, and it is not corrected for. A negative result
here should still be read as "this architecture at this cadence".

**What a next design would test.** Not a config-reachable lever: this phase built
four, gated them, proved them inert when off, swept 45 specifications and found
nothing above its own noise floor. The two directions left standing are outside
this preregistration and would each need their own: a genuinely time-varying
strength state (a different likelihood, not a gate), and a fresher conditioning
set (the only thing measured here that clearly matters). The decay curve's
monotone shape also *suggests* the optimum may lie **above** 365 days; that is a
hypothesis for a future preregistration, not a result of this one.

---

## Reproduction

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests -q            # 156 passed
PYTHONPATH=src:. .venv/bin/python -m epl.holdout --assert-frozen    # the three identity checks
PYTHONPATH=src:. .venv/bin/python -m epl.holdout --canary           # STOP 3, with its positive control
PYTHONPATH=src:. .venv/bin/python -m epl.holdout --walk             # 36 fits, ~8 min of model time
PYTHONPATH=src:. .venv/bin/python -m epl.holdout --score            # the holdout tables above
PYTHONPATH=src:. .venv/bin/python -m epl.holdout --second-look      # the SECOND LOOK, no fit
PYTHONPATH=src:. .venv/bin/python -m epl.holdout --ablation         # re-executes the adoption rule
PYTHONPATH=src   .venv/bin/python scripts/oa_lock.py | head -1      # LOCK VALID
```

Artifacts (all under `data/`, gitignored): `improve/holdout_off.jsonl` (36 rows,
one per cutoff — forecasts, timings, cold-start and provisional clubs),
`improve/holdout_off_warnings.json` (per-fit ADVI warnings),
`improve/holdout_result.json`, `improve/second_look_confirm.json`,
`improve/ablation.json`. The committed artifacts are `epl/holdout.py` and this
report.
