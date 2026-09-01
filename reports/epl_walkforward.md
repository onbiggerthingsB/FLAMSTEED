# The run: Bayesian Dixon-Coles against walk-forward Elo on 2019/20–2024/25

Executed 2026-08-14 on branch `epl-probe` under the preregistration committed at
`b416925` (`reports/epl_prereg.md`, `epl/config_frozen.json`). Not one frozen
value was changed, and no file under `src/` or `scripts/` was written.

**No betting.** The market column is an internal accuracy benchmark. It is never
displayed publicly, never turned into a signal, and never sized.

---

## The answer, in the first paragraph

The preregistered pass rule is **NOT MET**. The verdict is **INCONCLUSIVE
(precise null)** — which the preregistration named in advance as the most likely
outcome, and as a correct report rather than a failed one.

On all 2,280 scoring-window matches, the Dixon-Coles model scored a mean
normalised RPS of **0.201942** against walk-forward Elo's **0.203114**. The
paired difference is **Δ = −0.001172** (negative = the model is better), with a
95% block-bootstrap CI of **[−0.002809, +0.000466]** under the preregistered
(season, ISO-week) blocking. PASS required `Δ ≤ −0.0034` **and** `hi < 0`; Δ is
about a third of the threshold and the interval crosses zero. REJECT required
`lo > 0`; it does not. The interval lies strictly inside (−0.0034, +0.0034), so
this is the *precise null* branch: **the run rules out any improvement larger
than the minimum detectable effect.** It does not rule out a small one, and the
point estimate is in the model's favour.

The model did not come close to the market either. It lost to the de-vigged
Pinnacle close by **+0.006525** [+0.004099, +0.008982] — closing about 15% of
the 0.007696 Elo-to-market gap on this window, where a PASS needed roughly half.

---

## 1. A protocol deviation from the task instruction, declared up front

The instruction that launched this run specified a **fortnightly** cadence
("~143 fits, ~2.3 h"). **This run was executed weekly, at 212 fits**, because
the preregistration fixes the cadence and forbids exactly that substitution:

* §5 fixes "refit cadence | every matchweek of every scoring season" and
  "fits | **212** (35 + 34 + 36 + 34 + 37 + 36 matchweeks)".
* H1 itself is stated as "fitted walk-forward at **matchweek cadence**".
* STOP clause 6 says the run "does **not** shrink the window, coarsen the
  cadence, or thin the sample to fit the budget: any of those would change the
  preregistered design after seeing what it costs."

The instruction's own quoted pass rule agrees with the preregistration (it
specifies "212 (season, ISO-week) blocks"), so the conflict is with a single
parenthetical, not with the design. The "~143 fits" figure is traceable: it is
`epl.fit.cost_model` at cadence 2 over `epl.baseline.SCORE_SEASONS`, which is
the **eight**-season window 2018/19–2025/26 from the earlier baseline phase, not
the six-season preregistered scoring window. Fortnightly over the preregistered
window would have been 107 fits, not 143.

Running the coarser cadence would have handicapped the model — a fortnightly
posterior is up to a week staler than a weekly one, against a comparator that
re-rates after every kickoff block — and the result would then have been
"INCONCLUSIVE at a cadence we were not supposed to use". The weekly walk cost
**31 minutes**, well inside the preregistered 2.5–3 h estimate and nowhere near
the 8 h stop, so there was no budget reason to coarsen it either.

One further instruction detail, resolved the same way: the task asked for the CI
"block by season". The preregistration fixes **(season, ISO calendar week)**
blocks, 212 of them. **Both are computed and both are reported below**, and the
verdict is read off the preregistered one. They disagree about the sub-case, and
that disagreement is reported rather than resolved in the favourable direction
(§4).

---

## 2. What was run

| | |
|---|---:|
| scoring window | 2019/20 – 2024/25 |
| matches priced | **2,280** (380 × 6) |
| matches scored | **2,280** — complete case, nothing dropped |
| **unpriceable fixtures** | **0** |
| malformed forecasts (non-finite, or not summing to 1) | 0 |
| fits | **212**, one per (season, ISO calendar week) |
| cutoff | that matchweek's opening day, at midnight |
| training-set size | 1,900 → 4,167 pre-cutoff matches |
| median fit | 8.2 s; total 1,854 s of model time |
| wall clock, whole walk | **31 minutes** |
| ADVI convergence warnings | **0**, across all 212 fits |
| posteriors failing a health check | **0** |

Every one of the 2,280 fixtures received a finite, normalised forecast. The
preregistration made an unpriceable fixture a hard STOP (§4.2) precisely because
dropping one would bias the sample toward matches the model finds easy; Fix 3
(`epl.dcfit.ColdStartPosterior`) held, and the count is zero.

Artifacts: `epl/walkforward.py` (the runner),
`data/epl/fit/walkforward_ledger.jsonl` (one row per cutoff — forecasts,
timings, warnings, cold-start clubs, posterior health),
`data/epl/fit/walkforward.json` (the scored result),
`data/epl/fit/walkforward_predictions.parquet` (per-match probabilities for
every forecaster), `data/epl/fit/provisional_arm_split.json` (§8),
`data/epl/fit/walkforward_ledger_seed987654.jsonl` and
`data/epl/fit/walkforward_seed987654.json` (the seed replica, §9). Everything
under `data/` is gitignored; `epl/walkforward.py` and this report are the
committed artifacts.

### The comparator is the published one

The Elo and market columns come from `epl.baseline.evaluate` under the frozen
Elo configuration — the same function that produced `reports/epl_baseline.md`.
The frozen configuration differs from the baseline's in one parameter,
`home_advantage` 40 vs 100, which the preregistration flagged in advance as
**not identified** by the tuning objective. Measured here on this window: Elo
scores 0.203114 at H=40 and 0.203331 at H=100, a difference of 0.00022 — an
eighth of the MDE. The comparator is the published one in everything that
matters.

---

## 3. Headline scores

All five forecasters on the identical 2,280 matches:

| forecaster | n | **RPS** | log loss | accuracy |
|---|---:|---:|---:|---:|
| de-vigged market (proportional) | 2,280 | **0.195418** | 0.955675 | 55.57% |
| de-vigged market (Shin) | 2,280 | 0.195406 | 0.955706 | 55.57% |
| **Dixon-Coles (this run)** | 2,280 | **0.201942** | 0.975479 | 53.90% |
| walk-forward Elo + ordered logit | 2,280 | **0.203114** | 0.979158 | 54.12% |
| base rate (walk-forward H/D/A) | 2,280 | 0.234598 | 1.067828 | 43.55% |

### Paired gaps

| pair | mean Δ RPS | paired SD | 95% CI, week blocks (212) | 95% CI, season blocks (6) |
|---|---:|---:|---|---|
| **DC − Elo** | **−0.001172** | 0.039932 | **[−0.002809, +0.000466]** | [−0.003869, +0.002523] |
| DC − market | +0.006525 | 0.058858 | [+0.004099, +0.008982] | [+0.003694, +0.009161] |
| DC − market (Shin) | +0.006537 | 0.059307 | [+0.004104, +0.008989] | [+0.003670, +0.009145] |
| DC − base rate | −0.032655 | 0.150238 | [−0.038330, −0.026766] | [−0.039244, −0.025903] |
| Elo − market *(context)* | +0.007696 | 0.058200 | [+0.005489, +0.009960] | [+0.004911, +0.010336] |

### The same comparison on log loss

| pair | mean Δ log loss | 95% CI, week blocks | 95% CI, season blocks |
|---|---:|---|---|
| **DC − Elo** | **−0.003680** | **[−0.008902, +0.001602]** | [−0.010392, +0.006944] |
| DC − market | +0.019803 | [+0.012248, +0.027454] | [+0.009918, +0.028505] |
| DC − base rate | −0.092349 | [−0.109637, −0.074855] | [−0.114995, −0.069591] |

Log loss tells the same story with the same sign and the same failure to
separate: the model is ahead of Elo by 0.0037 and the interval crosses zero.

**A legibility note, not a result.** The Dixon-Coles forecast is better than
Elo's on 51.8% of individual matches. The mean absolute per-match RPS difference
is 0.0278 — twenty-four times the mean difference. Nearly everything these two
forecasters do is the same thing, and what separates them is a small residual on
a large amount of shared noise. That is exactly why the paired SD, not the
level SE, is the number that decides anything here.

---

## 4. The preregistered verdict, stated plainly

> **Rule (`reports/epl_prereg.md` §3).** PASS if `Δ ≤ −0.0034` **and** `hi < 0`.
> REJECT if `lo > 0`. Otherwise INCONCLUSIVE, split into *precise null*
> (`[lo, hi] ⊂ (−0.0034, +0.0034)`) and *underpowered* (the CI spans the MDE).

Δ = **−0.001172**, CI = **[−0.002809, +0.000466]** (preregistered blocking).

* PASS? **No.** Δ is 34% of the threshold, and `hi` is above zero.
* REJECT? **No.** `lo` is below zero.
* **Verdict: INCONCLUSIVE (precise null).** The interval sits strictly inside
  (−0.0034, +0.0034), so the run has ruled out any Dixon-Coles improvement over
  Elo larger than the minimum this design was built to detect.

**The pass rule is NOT MET.** No softening: the model did not clear the bar, and
the architecture has not earned a "worth building on EPL" on this evidence.

**And the honest counterweight, equally unsoftened:** the point estimate is
negative, log loss agrees, and the model wins on five of six seasons. The run
did not find nothing; it found something too small to certify.

### The two blockings disagree about the sub-case

| blocking | n blocks | CI | classification |
|---|---:|---|---|
| **(season, ISO week) — preregistered** | 212 | [−0.002809, +0.000466] | INCONCLUSIVE (**precise null**) |
| season — as the task instruction asked | 6 | [−0.003869, +0.002523] | INCONCLUSIVE (**underpowered**) |

Both are INCONCLUSIVE and neither is PASS or REJECT, so the headline verdict is
unaffected. The sub-case differs because a season-blocked bootstrap resamples
six units, which is too few for a stable percentile interval and inflates it. The
preregistration fixed the week blocking, so the week blocking decides; the
season interval is published beside it so a reader can see that the "precise
null" claim is the weaker of the two available readings of the same data and is
not robust to a coarser blocking.

### Power: better than assumed, still not enough

| quantity | preregistered | realised |
|---|---:|---:|
| paired SD (DC vs Elo) | 0.0577 (assumed, from Elo vs market) | **0.039932** |
| paired SE of the mean | 0.00121 | 0.000836 |
| 80%-power MDE, two-sided | **0.00339** | 0.00234 |

The preregistration predicted this: "the paired SD of 0.0577 is likely an
**over**-estimate here (both forecasters now share a rating anchor, so they will
agree more often than Elo and the market do); the run will report the realised
SD and achieved MDE but **may not use that recomputation to move the
threshold**." It has not. The threshold stayed at 0.0034 and the verdict is read
against it.

The recomputation matters anyway, and it does not rescue the result: even at the
achieved precision, Δ = −0.001172 is half the realised MDE of 0.00234. **This is
not a case of a real effect drowned by a badly chosen threshold.** It is a small
effect measured tightly enough to say it is small.

---

## 5. Per season

| season | n | DC | Elo | market | base | DC − Elo | DC − market |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019/20 | 380 | 0.19891 | 0.20106 | 0.19836 | 0.23004 | −0.00215 | +0.00055 |
| 2020/21 | 380 | 0.21773 | 0.22336 | 0.21106 | 0.24486 | **−0.00563** | +0.00666 |
| 2021/22 | 380 | 0.19381 | 0.19586 | 0.18904 | 0.23501 | −0.00205 | +0.00477 |
| 2022/23 | 380 | 0.20902 | 0.20183 | 0.19750 | 0.22847 | **+0.00719** | +0.01152 |
| 2023/24 | 380 | 0.18892 | 0.19102 | 0.18046 | 0.23383 | −0.00211 | +0.00846 |
| 2024/25 | 380 | 0.20327 | 0.20554 | 0.19608 | 0.23538 | −0.00228 | +0.00718 |

Log loss per season, the same three forecasters:

| season | DC | Elo | market |
|---|---:|---:|---:|
| 2019/20 | 0.97172 | 0.97743 | 0.97215 |
| 2020/21 | 1.02286 | 1.03675 | 0.99705 |
| 2021/22 | 0.94835 | 0.95672 | 0.93673 |
| 2022/23 | 0.99853 | 0.97716 | 0.96215 |
| 2023/24 | 0.92415 | 0.93018 | 0.89955 |
| 2024/25 | 0.98727 | 0.99671 | 0.96641 |

**The model beats Elo in five seasons of six, by a remarkably consistent
−0.002, and loses one season by +0.0072.** The five wins are so alike that the
season-to-season variation is essentially all in 2022/23. Two readings are
available and this run cannot choose between them:

* the model has a small, real, stable edge of about −0.002, and 2022/23 is one
  bad season; or
* the model and Elo are the same forecaster to within noise, and both the run of
  five and the one outlier are what noise looks like at 380 matches a season
  (the per-season SE of a paired mean is about 0.002).

The second is the null and the data do not refute it. **Nothing in this report
should be read as isolating 2022/23**; the preregistration explicitly forbade
hunting for a favourable subset, and dropping the one bad season would move Δ to
about −0.0028 and change nothing about what is licensed.

2020/21 is worth one line for the opposite reason. It is the closed-doors COVID
season, the worst season for every forecaster, and Elo's worst season relative
to the market (+0.0123 in the baseline). It is also the model's **best** season
against Elo (−0.0056). A hierarchical model with a fitted, continuously updated
home-advantage term should degrade more gracefully through a home-advantage
regime change than a rating system carrying a fixed home-advantage constant —
and it did. That is a mechanism-consistent observation from one season, not a
finding.

---

## 6. Subsets

| subset | n | DC | Elo | market | DC − Elo | 95% CI (week blocks) |
|---|---:|---:|---:|---:|---:|---|
| all | 2,280 | 0.20194 | 0.20311 | 0.19542 | −0.00117 | [−0.00281, +0.00047] |
| ≥1 promoted club | 648 | 0.18251 | 0.18577 | 0.17842 | −0.00326 | [−0.00745, +0.00095] |
| no promoted club | 1,632 | 0.20966 | 0.21000 | 0.20217 | −0.00034 | [−0.00194, +0.00128] |

The whole of the model's edge over Elo sits on matches involving a promoted
club, where it is −0.0033 — right at the MDE, on a quarter of the sample, with
an interval that still crosses zero. On established clubs the two forecasters are
indistinguishable (−0.0003).

This is the one place where the three fixes could plausibly have bought
something: Fix 2 seeds a promoted club at `division_mean − 75`, Fix 3 prices a
cold-start club from the model's own hierarchical prior at that seed and flags it
provisional, and the model then gets to *widen* on exactly those fixtures where
Elo cannot. The direction is right and the magnitude is the largest in the
report. It is also a subgroup, it was not preregistered as a primary, and its CI
includes zero. **It is a hypothesis for the next design, not a result of this
one.**

---

## 7. Calibration

Mean forecast against realised frequency over the 2,280:

| | home | draw | away |
|---|---:|---:|---:|
| **realised** | 0.4355 | 0.2303 | 0.3342 |
| **Dixon-Coles** | **0.4350** | 0.2273 | **0.3377** |
| Elo | 0.4489 | 0.2305 | 0.3206 |
| market | 0.4374 | 0.2384 | 0.3243 |
| base rate | 0.4487 | 0.2367 | 0.3146 |

The Dixon-Coles model is the **best-calibrated forecaster on the sample,
including the market**: 0.0005 off on home and 0.0035 off on away, against Elo's
+0.0134 / −0.0136. Elo systematically over-prices the home side and under-prices
the away side on this window; the model does not.

That is a real difference in a real property, and it converts into almost no
RPS. Marginal calibration is a weak condition — a forecaster can have perfect
marginals and be wrong on every individual fixture — and the ~0.0135 of
home/away bias Elo carries is worth only a fraction of a thousandth of RPS once
the ordered-logit head has absorbed it into its thresholds. Worth recording as a
qualitative property of the architecture; not worth confusing with the headline.

**Sharpness runs the other way.** The model's mean top-pick probability is
0.5543 against Elo's 0.5495 and the market's 0.5459, and its most confident
forecast is 0.9558 against the market's 0.9246. The Dixon-Coles model is
**more** confident than the sharpest available benchmark while being less
accurate than it — the same favourite-overconfidence signature this project
documented on the World Cup side. Better marginals, worse conditional
confidence.

---

## 8. Every preregistered STOP condition

| # | condition | status |
|---|---|---|
| 1 | **Too good.** DC beats de-vigged Pinnacle by ≤ −0.002 with CI below zero | **Not triggered.** DC − market = **+0.006525**, CI [+0.0041, +0.0090]. The model loses to the market by about six thousandths. No leak signature. |
| 2 | **An unpriceable fixture.** | **Not triggered.** 0 of 2,280. |
| 3 | **A failed point-in-time canary.** | **Not triggered — canary PASSED.** See below. |
| 4 | **A frozen value needing to change.** | **Not triggered.** `epl/config_frozen.json` is byte-identical to `b416925`; all 212 ledger rows carry the same anchor spec. |
| 5 | **ADVI non-convergence at >5% of cutoffs.** | **Not triggered**, with a caveat stated below. 0 warnings, 0 unhealthy posteriors. |
| 6 | **Realised cost above 8 h.** | **Not triggered.** 31 minutes. |

### The point-in-time canary

Run end to end through the pipeline this walk uses — anchor, fit, cold start,
`predict_1x2` — not on intermediate columns:

```
cutoff                                          2022-01-01
results rewritten to 9-0 from the cutoff on          1,717
forecasts bit-identical before the cutoff             TRUE   (max |Δp| = 0.0)
positive control: forecasts moved after the cutoff    TRUE   (max |Δp| = 0.812)
PASS                                                  TRUE
```

Rewriting every future result to a 9-0 home win moved the pre-cutoff forecasts
by exactly zero, and the positive control confirms the corruption really landed.
The negative result is therefore not vacuous.

### ADVI convergence: what was and was not verified

Across 212 fits: **zero** warnings of any category, **zero** posteriors with a
non-finite draw, a non-positive scale parameter, or an implausible `home_adv`.

The honest limitation: **pymc 6.0.1's `pm.fit(method="advi")`, as called by
`wcmodel.model.inference.sample`, installs no convergence callback.** There is no
package-level convergence boolean to read, so "0 non-convergent fits" means "no
fit raised, none produced an unusable posterior" — not "each variational
optimisation was certified converged". Silence from pymc is not evidence of
convergence, and it is not reported as such.

What *was* measured instead is the quantity that matters: **how much of the
result is optimiser noise.** See §9.

### One preregistered claim this run corrects

The preregistration recorded, from two tuning cutoffs, that "wcmodel's
provisional/volatility arm (16.5-point threshold, derived at international K up
to 40) flags **NOBODY** at club K — so mechanism-(c) widening is inert on this
data except where Fix 3 turns it on."

**That is wrong at scale.** Recomputed at every scoring cutoff that produced a
provisional club (`epl.walkforward.provisional_arm_split`):

| | |
|---|---:|
| cutoffs with at least one provisional club | 39 of 212 |
| team-cutoff flags | 45 |
| **from the volatility arm** | **13** (Aston Villa, Brighton, Leicester) |
| from the few-games arm | 32 (the six cold-start clubs) |

Leicester at the 2020-10-17 cutoff carried a recent volatility of 17.62 against
the 16.5 threshold, on 232 prior matches — the volatility arm, not the few-games
arm. So mechanism-(c) widening was **live** on this run, on about 6% of
cutoffs, and the preregistration's claim was an over-generalisation from two
observations. It is corrected here rather than left to be discovered. It does
not change any headline number — the affected fixtures are a small slice — but a
claim measured at two cutoffs is not a claim about 212, and the report should
say which one it is.

---

## 9. How much of this is ADVI noise?

The headline gap is 0.001172. A variational optimiser that lands in a slightly
different place on every run could manufacture or destroy a gap that small, so
it was measured rather than assumed.

**Seed-perturbation, per fit.** At twelve cutoffs spanning the window, the same
fit was run twice, changing only the RNG seed:

| | mean abs. shift | max abs. shift |
|---|---:|---:|
| across 12 cutoffs × 10 fixtures | **0.0034** | 0.0200 |

A 0.0034 mean shift in probability is not nothing, so the per-fit measurement
was not treated as sufficient.

**The whole walk, run twice.** All 212 fits were repeated end to end at seed
987654, changing nothing else, into a separate ledger
(`data/epl/fit/walkforward_ledger_seed987654.jsonl`). This is a diagnostic: the
reported result is the frozen configuration's own seed, and the replica never
feeds a headline number.

| | frozen seed (reported) | replica, seed 987654 | difference |
|---|---:|---:|---:|
| DC mean RPS | 0.201942 | 0.202017 | **+0.000075** |
| DC log loss | 0.975479 | 0.975790 | +0.000311 |
| DC accuracy | 53.904% | 53.947% | +0.04pp |
| **Δ (DC − Elo)** | **−0.001172** | **−0.001097** | **0.000075** |
| CI, week blocks | [−0.002809, +0.000466] | [−0.002736, +0.000541] | — |
| verdict (week / season) | precise null / underpowered | precise null / underpowered | identical |
| unpriceable fixtures | 0 | 0 | — |

Per-match probability distance between the two runs: mean 0.0032, p99 0.0139,
max 0.0229.

**So the ADVI optimiser moves the headline by 0.000075** — 6% of the measured
gap, 3% of the preregistered MDE, and about a thirtieth of the per-match
probability noise, because that noise is near zero-mean and averages out over
2,280 matches. Both runs land on the same verdict under both blockings. The
frozen seed happened to be marginally the luckier of the two, by 7.5 × 10⁻⁵.

**The conclusion is not an artefact of the sampler.** That is the strongest
statement available about ADVI here, and it is a stronger one than "pymc emitted
no warnings" — which, as §8 records, it could not have emitted anyway.

---

## 10. The three fixes, in the run

| fix | what it did here |
|---|---|
| **Fix 1 — league K** | The anchor was `epl.elo` under the frozen config at every one of the 212 cutoffs; all ledger rows carry the single anchor spec `epl.elo/carryover=1/debut_offset=0/home_advantage=40/initial_rating=1500/k=20/mov=False/...`. The model and its comparator ran one rating table, so a win could not have been a better rating system in disguise. As the freeze already recorded, this bought nothing in the *number* (the inherited nominal K was also 20) — only in provenance and in removing the confound. |
| **Fix 2 — promoted seed** | Six promoted clubs entered at `division_mean − 75`, one per season, with anchor z-scores from −0.360 (Sheffield United 2019/20) to −0.073 (Ipswich 2024/25). |
| **Fix 3 — cold start** | Six cold-start events, one per scoring season: Sheffield United (2019-08-09), Leeds (2020-09-12), Brentford (2021-08-13), Nottingham Forest (2022-08-05), Luton (2023-08-11), Ipswich (2024-08-16). Each would have raised `KeyError` in `predict_1x2`. **Zero unpriceable fixtures resulted.** |

The preregistration's own honest limitation on Fix 3 held: a prior draw is not a
posterior, and the model knows nothing about a promoted club beyond its Elo
seed. On the promoted subset the model is ahead of Elo by −0.0033 — the report's
largest gap and still not significant.

---

## 11. What this does and does not settle

**Settled.** On six Premier League seasons, 2,280 matches, priced weekly by the
architecture at a frozen configuration chosen without seeing any of them: the
hierarchical Dixon-Coles scoreline model of `src/wcmodel` **does not beat
walk-forward Elo by an amount this design can certify.** Any improvement larger
than 0.0034 RPS is ruled out; at the realised precision, larger than about
0.0023 is ruled out too. This is the third negative-to-null result for this
architecture against a naive rating baseline: it tied Elo at the World Cup, lost
to the market there by ~0.010, and here it is +0.0012 ahead of Elo and 0.0065
behind the market.

**Not settled.** Whether there is a real edge of 0.001–0.002. The point estimate
says maybe, log loss agrees, five of six seasons agree, and the design cannot
resolve it. The preregistration did the arithmetic in advance: resolving 0.0020
at 80% power needs about **6,500 matches** — seventeen Premier League seasons or
a multi-league panel. That is the honest design for this question and it is not
this run. **This run was built to answer "is there a large effect", and it
answered: no.**

**Also not settled, and named in advance as disfavouring the model.** The Elo
comparator re-rates after every kickoff block; the model refits once a week and
its feature layer is day-resolution, so it cannot see a 12:30 result before a
17:30 kickoff on the same day. The model worked from strictly staler information
throughout and this was not corrected for. A negative result should be read as
"this architecture at this cadence", not "this likelihood".

**What a next design would test, if there is one.** The promoted-club subset
(−0.0033 on 648 matches) and the calibration asymmetry (the model has the better
marginals and the worse conditional confidence) both point at the same place:
what the architecture adds over Elo is a better *uncertainty* representation
rather than a better *point* forecast, and 1X2 RPS is a blunt instrument for
that. Neither observation is licensed by this run. Both were generated by it.

---

## Reproduction

```bash
PYTHONPATH=src:. .venv/bin/python -m epl.walkforward --verify   # panel fast path is inert
PYTHONPATH=src:. .venv/bin/python -m epl.walkforward --canary   # point-in-time canary
PYTHONPATH=src:. .venv/bin/python -m epl.walkforward --walk     # 212 fits, ~31 min
PYTHONPATH=src:. .venv/bin/python -m epl.walkforward --score    # the tables above
```

**One implementation note that changes no number.** `wcmodel.data.features.build`
tags each panel row with `tiers.is_covid`, which opens and YAML-parses
`config/config.yaml` in its body — once per row, ~8,000 times per fit, which is
50 of the 57 seconds a fit costs. The walk ran inside
`epl.fit.config_read_once`, which serves that read from one already-parsed
config. It edits nothing under `src/`, and it is proven inert rather than assumed
so: at three cutoffs spanning the window (3,800 / 5,658 / 7,580 panel rows), the
panel built with it is `DataFrame.equals`-identical to the panel built without
it, at 24–48 s versus 0.07–0.12 s. Without it the same 212 fits would have cost
about 3.4 hours — still inside the 8 h stop, so this bought wall clock, not a
protocol concession.

The proper fix is one line in `src/wcmodel/data/features.py` or
`src/wcmodel/data/tiers.py` (memoise `load_config`, or hoist the COVID window out
of the per-row map). That path is attested by the preregistration lock and this
package may not write to it. Recorded as a finding, not applied.

---

## Appended note, 2026-09-01: these numbers stand, and the code will no longer re-publish them

**Nothing above changes.** Every figure in this report reproduces under today's
HEAD, exactly, and the two headline gaps reproduce to the last decimal a float
carries:

```
DC − market   +0.006524690900523155      (published above as +0.006525)
DC − Elo      −0.001171733325478302      (published above as −0.001172)
```

Both bootstrap interval sets come back identical as well — DC − Elo
`[−0.002809, +0.000466]` on week blocks and `[−0.003869, +0.002523]` on season
blocks, DC − market `[+0.004099, +0.008982]` and `[+0.003694, +0.009161]` — as
do all five forecasters' RPS, log loss and accuracy, and the STOP-1 arithmetic
in §8. This is a re-derivation from the committed 212-cutoff ledger, not a
re-read of this document.

**And the shipped code now refuses to publish them.** That is deliberate, it is
not a regression, and the two facts are not in tension.

### What changed underneath, and why

The 212-cutoff ledger this run wrote — `data/epl/fit/walkforward_ledger.jsonl`
— is a **v1 ledger**. It predates the evidence machinery `epl/walkforward.py`
now carries: an immutable run envelope as the first record, a per-record
`record_sha256`, a `previous_record_sha256` chaining every cutoff to the one
before it, and a terminal seal committing to the cutoff count, the fixture
count, the schedule digest and the chain head. None of that existed when this
walk ran. The ledger is not corrupt and it is not suspect; it is simply from
before, and there is no honest way to give it a chain after the fact. **It is
permanently legacy.**

Three refusals now stand between it and a re-published verdict, and each one is
doing a different job:

| refusal | what it stops |
|---|---|
| `load_ledger` without `allow_legacy=True` raises `EvidenceIntegrityError` — *"legacy ledger has no immutable run envelope; read it only with allow_legacy=True for non-verdict diagnostics"* | reading these rows at all on a publication path |
| `score_run(publishable=True)` handed the legacy rows explicitly raises `VerdictPublicationBlocked` — *"run_envelope=missing; chained_ledger=missing envelope"* | scoring them into a verdict once past the loader |
| `holdout.second_look_confirm` returns `verdict_publishable: False` and `verdict_under_v1_rule: None` | the second look re-deciding anything from them |

`python -m epl.walkforward --score` now points at the chained
`walkforward_ledger_v2.jsonl`, which does not exist and will not exist until a
chained forward run writes it. The Reproduction block above is unchanged as a
record of what was run in August 2026; the command that re-derives these numbers
**today** is the explicitly diagnostic one:

```bash
PYTHONPATH=src:. .venv/bin/python -m epl.walkforward --score --diagnostic-score
```

It prints the table above and labels its own conclusion `DIAGNOSTIC ONLY`. It
writes nothing.

### What this does and does not mean

**It does not retract a number.** The forecasts on that ledger are the
forecasts this walk produced, at the frozen configuration, at weekly cadence,
over the 2,280 matches §1 fixes. The verdict this report reached — **NOT MET**,
INCONCLUSIVE (precise null) — was reached correctly on them and is not
withdrawn. A ledger without a hash chain is a ledger whose *provenance* is
attested by the commit history rather than by its own bytes; that is a weaker
attestation than the current machinery gives, and it is not an absence of one.

**It does mean this run cannot be re-run into a fresh verdict.** The distinction
the code enforces is between reproducing a published result and publishing a
result. Reproduction is a diagnostic and is available, gated behind a flag that
names itself. Publication requires the chain, and the chain requires the run. A
future verdict on this question — the anchored arm, a widened window, a
multi-league panel, anything the closing section names as a next design — comes
from a chained forward run under `walkforward_ledger_v2.jsonl`, from its own
envelope, with its own terminal seal. It does not come from these 212 rows
scored again under a new name.

**It is the ordinary end state of an evidence plane that got stricter after it
was used, and the ordinary end state is worth writing down.** The alternative —
back-filling an envelope and a chain onto rows that were written without them —
would produce a ledger that verifies and an attestation that is false, which is
the exact failure the chain exists to make impossible. The numbers keep their
standing from this document and from the commit that carries them. The machinery
keeps its guarantee by refusing to lend them one they never had.
