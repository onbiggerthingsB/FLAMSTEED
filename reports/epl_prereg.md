# Preregistration: does the Bayesian scoreline model beat walk-forward Elo on EPL?

**Branch** `epl-probe` · **Written** 2026-08-14 · **Status** written and committed
BEFORE any scoring-window model result exists
**Code** `epl/windows.py`, `epl/anchor.py`, `epl/dcfit.py`, `epl/freeze.py`,
`epl/config_frozen.json`
**Predecessor** `reports/epl_baseline.md` — the bar this is measured against

```
PYTHONPATH=src:. .venv/bin/python -m epl.freeze --tune          # 310 s, writes the freeze
PYTHONPATH=src:. .venv/bin/python -m epl.dcfit --cutoff 2016-08-13   # 16 s, one fit end to end
PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests -q        # 90 tests, the fixes attacked
```

---

## 0. Why this document exists

The result this probe is heading toward is a single number: the paired mean RPS
difference between a hierarchical Dixon-Coles scoreline model and walk-forward
Elo, on six Premier League seasons. That number has about seven thousandths of
RPS of room to move in — the entire distance between naive Elo and the de-vigged
closing market — and a paired standard error of about one and two-tenths
thousandths. A comparison that thin can be talked into almost any conclusion
after the fact: by choosing a window, by choosing a de-vig, by dropping the
fixtures the model finds hard, by tuning one more knob and calling it a bug fix.

So the analysis is fixed here, in writing, in the repository, before the model
has been run on a single scoring-window match. If the run then produces a
disappointing number, this document is what stops it from being rescued.

---

## 1. The hypothesis, as a falsifiable claim

> **H1.** On Premier League seasons 2019/20 through 2024/25 (2,280 matches),
> the hierarchical Dixon-Coles scoreline model of `src/wcmodel` — fitted
> walk-forward at matchweek cadence, anchored on the same frozen Elo the
> baseline uses — achieves a **lower mean normalised RPS than walk-forward Elo
> + ordered logit**, by a margin this sample can resolve.
>
> **H0.** It does not.

H1 is falsifiable in the strong sense: the scoring window is fixed, the metric
is fixed, the configuration is fixed and committed, the fixture set is fixed at
all 2,280 matches, and the decision threshold is a number stated in §3 before
the data are seen. There is no analyst degree of freedom left between running
the code and reading the answer.

**What H1 is not.** It is not a claim that the model beats the market. The
market benchmark is reported because a model that beat Elo but still lost to the
close would be an interesting negative, and because a model that *beat the
market* would almost certainly be a bug (see §4). Odds are an internal accuracy
benchmark only. Nothing here is a betting signal, and nothing here is displayed.

**Prior.** Low. The same architecture tied naive Elo over its 104-match World
Cup replay and lost to de-vigged prices by about 0.010 RPS. Nothing about club
football obviously rescues it: EPL Elo is a strong baseline that already
captures 83% of the market's edge over the base rate.

---

## 2. The metric, exactly

### Primary: normalised (halved) three-outcome ranked probability score

Over the **ordered** categories `(home, draw, away)`, with `o` the one-hot
realised outcome:

```
                1      r-1  /  i          i        \ 2
    RPS  =  ---------   SUM |  SUM p_j  -  SUM o_j  |          r = 3
              r - 1     i=1 \ j=1        j=1       /
```

With `r = 3` the leading factor is exactly `1/2`; the score lies in `[0, 1]`; a
uniform forecast scores 5/18 = 0.2778 on a home or away result and 1/9 = 0.1111
on a draw. The un-normalised convention omits `1/(r−1)` and is exactly twice
these numbers. **This convention is the one the published bar is quoted on**
(market ~0.194, Elo ~0.201, base rate ~0.234) and it is pinned by unit test
against hand-computed values and against `wcmodel.model.calibration.rps` to
1e-12 (`epl/score.py`, `epl/tests/test_baseline.py`).

The cumulation order is a module constant, not a caller choice. RPS is defined
on ordered categories and home < draw < away is the ordering of a result;
cumulating in any other order silently produces a larger score that punishes a
correct favourite.

### Secondary: natural-log loss

`−ln P(realised)`, clipped at 1e-15, averaged over matches. Reported alongside
RPS on every table. **It does not enter the decision.** It is here because RPS
and log loss disagree about how to punish confident errors, and a result that
holds on one but reverses on the other is a result that should be described
rather than declared.

### Also reported, deciding nothing

Top-pick accuracy (legible, not proper), mean forecast versus realised frequency
per outcome (a calibration smell test), and per-season and per-subset
breakdowns. Three subsets are fixed here, and only these three: **matches
involving a promoted club**; **matches involving a cold-start club** (a subset
of the first — the six season-opening fixtures of §6); and **matches involving
neither**. Naming them now is what stops a subset from being discovered after
the fact. No other slice will be reported, and none of them moves the verdict,
which rests on the full 2,280.

### The comparison

All three forecasters — Dixon-Coles, Elo + ordered logit, de-vigged market — are
scored on **one complete-case index of all 2,280 matches**. Odds coverage on the
scoring window is 2,280 of 2,280, verified, so complete-case costs nothing here.
`epl.score.paired_gap` refuses arrays of different length rather than aligning
them, so a partial-coverage forecaster cannot be scored on an easier subset than
its rival.

De-vig is **proportional** for the headline (the convention the published bar
uses, and it has no free choices in it); **Shin is reported alongside and selects
nothing**. On this archive the two differ by 4e-5.

---

## 3. The pass rule, as a number — and the power arithmetic that sets it

### The arithmetic first

| quantity | value |
|---|---:|
| scoring-window matches `n` | **2,280** |
| paired per-match SD, measured (Elo − market, this archive) | **0.0577** |
| implied paired SE of the mean | **0.00121** |
| design effect from week-block clustering (measured) | ≈ **1.00** |
| **minimum detectable effect, 80% power, two-sided α = 0.05** | **0.00339** |
| minimum detectable effect, 80% power, one-sided α = 0.05 | 0.00300 |
| total headroom between Elo and the market (measured) | **0.0068–0.0074** |

The paired SD used is the only one that exists before the model is run. It is
likely an **over**-estimate for the Dixon-Coles-versus-Elo difference, since the
two forecasters share a rating anchor and will therefore agree more often than
Elo and the market do; the run will report the realised paired SD and recompute
the achieved MDE, but it may not use that recomputation to move the threshold.

The block-bootstrap will use (season, ISO calendar week) blocks — **212 of them
on this scoring window**, counted — with 10,000 resamples.
The baseline established that clustering barely matters on this data (a
season-clustered analytic SE of 0.001076 against an iid 0.001077), so the CI is
expected to be close to the iid interval. The blocking is done anyway: finding
out that dependence is negligible is not the same as assuming it.

### The rule

Let `Δ = mean(RPS_dc) − mean(RPS_elo)` over the 2,280 matches (negative = the
model is better), and let `[lo, hi]` be its 95% block-bootstrap CI.

> **PASS (the architecture is worth building on EPL)**
> `Δ ≤ −0.0034` **and** `hi < 0`.
>
> **REJECT (the architecture is worse)**
> `lo > 0`.
>
> **INCONCLUSIVE (everything else)** — reported as such, in those words, with
> the CI quoted. Two sub-cases are distinguished because they say different
> things:
> * **precise null**: `[lo, hi] ⊂ (−0.0034, +0.0034)`. The run has ruled out any
>   improvement larger than the MDE. That is a real finding.
> * **underpowered**: the CI spans the MDE. The run has ruled out nothing much.

### Why −0.0034 and not something friendlier

−0.0034 is the two-sided 80%-power MDE at this sample size, rounded away from
zero. Setting the threshold there says: *we will not claim a win smaller than
the smallest win this design can reliably see.* Note that the CI condition alone
would fire at `|Δ| > 1.96 × SE = 0.0024`, so the threshold is the binding
constraint and it binds in the conservative direction — a point estimate of
−0.0025 with a CI of [−0.0049, −0.0001] technically excludes zero and still does
not pass.

### The uncomfortable consequence, stated because it is a finding

Total headroom above Elo is 0.0068–0.0074. **A PASS therefore requires the model
to capture roughly half of the entire Elo-to-market gap in one step.** The same
architecture tied Elo at the World Cup. A realistic expectation for a
well-specified scoreline model's edge over a well-tuned Elo on 1X2 is on the
order of 0.000–0.003.

**So: this sample probably cannot resolve the effect we expect.** That is not a
reason to widen the window — there is no more Premier League to widen into that
is not already in the tuning set or the excluded partial season — and it is not
a reason to lower the threshold, which would only trade a false negative for a
false positive. It is a reason to say in advance that **the most likely outcome
of this run is INCONCLUSIVE**, and that an INCONCLUSIVE outcome is the correct
report, not a failed one.

From the baseline's own power table, resolving 0.0020 at 80% power needs about
6,500 matches — seventeen Premier League seasons, or a multi-league panel. That
is the honest design for the question, and it is not this run. This run can
answer "is there a large effect", and it will answer that.

---

## 4. What would make us STOP

Any of these halts the run and is reported as a stop, not worked around:

1. **Too good.** `mean(RPS_dc) − mean(RPS_market) ≤ −0.002` with the CI below
   zero — the model detectably beating the de-vigged Pinnacle close out of
   sample. For this architecture that is implausible, so the first hypothesis is
   a leak, not an edge. This mirrors the World Cup project's own
   `backtest.foresight_red` guardrail: too-good is a bug signal.
2. **An unpriceable fixture.** If any of the 2,280 matches comes back without a
   finite Dixon-Coles forecast, the run stops. Scoring 2,279 would bias the
   sample toward matches the model finds easy — the exact failure Fix 3 exists
   to prevent — and silently reporting a smaller `n` would hide it.
3. **A failed point-in-time canary.** The run re-runs the existing canary
   (rewrite every post-cutoff result, assert every pre-cutoff forecast is
   bit-identical, with the positive control asserting post-cutoff forecasts DID
   move). A failure stops everything, because a leak makes every number
   meaningless in the flattering direction.
4. **A frozen value needing to change.** If the run cannot complete without
   altering `epl/config_frozen.json`, it stops and reports why. The file is
   committed before the run exists precisely so that this is detectable.
5. **Divergent inference.** If the ADVI fits do not converge by the package's
   own criteria at more than 5% of cutoffs, the run stops and reports the fit
   diagnostics rather than scoring an unconverged posterior.
6. **Cost.** The run is budgeted at 212 fits (§5), estimated at **2.5–3 hours**
   from two measured fits: 15.8 s on a 760-match panel and 30.6 s on a
   1,890-match panel, i.e. about 5.8 s fixed plus 0.0132 s per pre-cutoff
   match, which puts the scoring window's panels (1,900 → 4,180 matches) at
   30–61 s each. If the realised cost exceeds **8 hours**, the run stops and
   reports the cost. It does **not** shrink the window, coarsen the cadence, or
   thin the sample to fit the budget: any of those would change the
   preregistered design after seeing what it costs.

And one thing that is explicitly **not** a stop: a disappointing Δ. That is the
result.

---

## 5. The run design, fixed here

| | |
|---|---|
| scoring window | 2019/20, 2020/21, 2021/22, 2022/23, 2023/24, 2024/25 |
| matches | 2,280 (all of them; odds coverage 2,280/2,280) |
| excluded | 2025/26 entirely — see §7 |
| refit cadence | every matchweek of every scoring season |
| fits | **212** (35 + 34 + 36 + 34 + 37 + 36 matchweeks) |
| cutoff | the opening day of each matchweek, day-resolution |
| what a fit sees | matches strictly before the cutoff DAY, all pre-cutoff seasons, `decay_half_life_days = 365` |
| comparator | Elo + ordered logit under the identical frozen config, refit per cutoff block |
| market | Pinnacle close, de-vigged proportional (headline) and Shin (reported) |

A matchweek is (season, ISO calendar week) — the source has no matchweek column
and the feature layer's cutoff is day-resolution, so the calendar week within a
season is the natural round. Weeks carrying a midweek round are simply larger
rounds, which is correct: those matches are more dependent, not less.

**A structural asymmetry, named in advance because it disfavours the model.**
The Elo comparator re-rates after every kickoff block; the Dixon-Coles model
re-fits once a week and prices the whole week off one posterior, and its feature
layer is day-resolution so it cannot see a 12:30 result before a 17:30 kickoff
on the same day. The model is therefore working from strictly staler information
than its comparator, by up to a matchweek. This is inherent to a fit that costs
minutes rather than milliseconds; matchweek cadence is the finest the feature
layer supports. The Elo staleness proxy in `epl/fit.py::staleness_curve`
measures what that costs Elo and is an upper bound on what it costs a
365-day-decayed likelihood. **We are not correcting for it**, and a reader
should treat any negative result as "this architecture at this cadence", not
"this likelihood".

---

## 6. The frozen configuration

Chosen on 2014/15–2018/19 (objective: 2015/16–2018/19, 1,520 matches) and on
nothing else. Written to `epl/config_frozen.json` and committed before the run
phase exists. Verbatim:

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

Tuning-objective RPS at this configuration: **0.19552**, against a grid median
of 0.19700 and a grid worst of 0.20533 over 432 configurations. The
tuning window's own 80%-power MDE is **0.00415**, which is larger than every
gap in the grid except the extremes — so *most of this tuning is inside noise*,
and that is said here rather than discovered by a reader later. The two choices
with margins worth anything are K and the promoted seed.

### The three fixes, and what each is actually worth

**Fix 1 — the K factor.** `wcmodel.data.tiers.match_type` is a taxonomy of
international competitions; "Premier League" is not in it, so every EPL match
falls to the `other` bucket. The honest accounting is that `k_base` is 40 **and
the `other` multiplier is 0.5**, so the nominal K an EPL match inherits today is
**20 — which is also the K this search chose**. Fix 1 therefore buys essentially
nothing in the number:

| K | 10 | 15 | **20** | 25 | 30 | 40 |
|---|---:|---:|---:|---:|---:|---:|
| best tuning RPS | 0.19584 | 0.19558 | **0.19552** | 0.19565 | 0.19588 | 0.19652 |

There is real curvature (K = 40 costs 0.0010, K = 10 costs 0.0003) but the
inherited value sits at the optimum by coincidence. What Fix 1 does buy is
provenance and coherence: the number is now chosen rather than obtained by
falling off the end of a lookup table that a future edit could move silently,
and — the part that matters — **the model's anchor is now the same rating table
the Elo comparator prices with**, so a Dixon-Coles win cannot be a better rating
system wearing a Bayesian coat. `wcmodel`'s Elo also multiplies every update by
a margin-of-victory index (mean 1.2533 on this archive) that this package's Elo
does not, so even at equal nominal K the two update scales differ; after the
anchor substitution that difference reaches only the provisional/volatility arm.

**Fix 2 — the promoted-club prior.** `wcmodel`'s Elo has no season boundary,
so a promoted club enters at `initial_rating` and a returning club resumes a
rating earned before evidence the archive does not contain. The fix seeds a
promoted club at `division_mean + promoted_offset`. The grid contains
`promoted_offset = 0` — seeding AT the mean, i.e. the defect itself — so the
rule had to win on data:

| promoted_offset | 0 | −50 | **−75** | −100 | −150 | −225 |
|---|---:|---:|---:|---:|---:|---:|
| best tuning RPS | 0.19683 | 0.19558 | **0.19552** | 0.19569 | 0.19622 | 0.19735 |

A clean interior optimum, and the defect costs **0.00131** — the largest single
configuration effect in this search, and about a fifth of the total Elo-to-
market headroom. It is also below the tuning window's MDE of 0.00415, so even
this, the biggest effect here, is not resolved by the tuning window on its own;
what supports it is the shape of the curve (monotone on both sides of an
interior minimum, across two independent tuning windows — the previous baseline
found −75 on 2014/15–2017/18 too) rather than any single pairwise gap.

**Fix 3 — the cold start.** A club with no pre-cutoff match is absent from the
model's team index and `Posterior._idx[club]` raises `KeyError`. Six of the six
scoring seasons open with exactly one such club: Sheffield United 2019/20, Leeds
2020/21, Brentford 2021/22, Nottingham Forest 2022/23, Luton 2023/24, Ipswich
2024/25.

The club is priced from **the model's own hierarchical prior at the fitted
hyperparameters, anchored at its promoted seed**: per posterior draw `s`,

```
att_new[s] = k_att * z_new + sigma_att[s] * eps
def_new[s] = k_def * z_new + sigma_def[s] * eps'
```

which is exactly `wcmodel.model.scoreline._priors`' own
`att_raw ~ Normal(k_att · elo_z, sigma_att)` for a team it has no data on, with
`z_new` the Fix-2 promoted seed placed on the fitted teams' z-scale. `wcmodel`'s
soft sum-to-zero centering drops out identically, not approximately: the anchor
is z-scored over the fitted teams, so the estimator of the centering constant is
`k · mean(z) = 0`. The club is additionally flagged **provisional**, so the
package's existing predict-time mechanism-(c) widening applies.

Three properties make this defensible rather than convenient: it introduces no
parameter that was not already fitted; it is the architecture's own answer about
an exchangeable club it has no data on, not an answer bolted on beside it; and
it is strictly wider than a point estimate.

**The limitation, stated in advance.** A prior draw is not a posterior. On these
fixtures the model has nothing the Elo baseline does not have, so its forecast
is a smeared version of Elo's and should not be expected to beat it. The point
of Fix 3 is that every fixture gets a number.

**Demonstrated, not asserted.** One real fit at the 2016/17 opener
(`python -m epl.dcfit --cutoff 2016-08-13`, a TUNING-window date — the CLI
refuses a scoring season):

```
n_training_matches 760   n_teams 23   seconds 15.8
cold_start_teams   ["middlesbrough"]   cold_start_z  -0.802
provisional_teams  ["middlesbrough"]
n_fixtures 10   n_priced 10   would_raise_KeyError_without_fix_3  1
Middlesbrough v Stoke -> (0.2262, 0.2502, 0.5236)
```

Ten of ten priced, the tenth only because of Fix 3, and the newcomer is priced
as a clear underdog at home — which is what a seed 0.80 standard deviations
below the division should produce.

A separate seed for a club with **no prior match in the archive** was tested and
**rejected on data**: `debut_offset = 0` (no special case) won outright.

| debut_offset | +75 | **0** | −75 | −150 |
|---|---:|---:|---:|---:|
| tuning RPS | 0.19673 | **0.19552** | 0.19631 | 0.19812 |

It was rejected on principle too, and the two agree: "no prior match in this
archive" is a property of the archive, not of football. Bournemouth 2015/16 was
a genuine top-flight debut; Norwich 2015/16 was not — it simply had no season
inside a window that starts in 2014/15. A parameter that treated those two
identically-labelled cases as one football category would be fitting the
archive's left edge.

### One parameter that is not identified, and is reported as such

`home_advantage` = 40 is **not an estimate of anything**. The tuning surface is
flat across the whole grid:

| home_advantage | 40 | 60 | 80 | 100 |
|---|---:|---:|---:|---:|
| best tuning RPS | 0.195524 | 0.195526 | 0.195530 | 0.195537 |

A 1.3e-5 spread is noise. This is expected, not a defect: every league match has a
home side, so home advantage on the prediction side is absorbed exactly into the
ordered logit's thresholds, and the parameter only affects the *update*. The
grid is sorted with `home_advantage` ascending as an explicit last tie-break so
that an unidentified parameter is settled by a stated rule rather than by the
order the grid happened to be generated in.

---

## 7. Every specification tried and rejected

The anti-domain-shopping record. The machine-readable version, with the tuning
RPS of each, is `epl/config_frozen.json` → `rejected` and `grid` (all 432 rows).

### Rejected on a number (tuning window only)

| specification | tuning RPS | Δ vs chosen |
|---|---:|---:|
| K = 40 (`k_base` with the multiplier removed) | 0.19678 | +0.00126 |
| K = 20 inherited (`k_base` 40 × `other` 0.5) | 0.19552 | 0.00000 |
| K = 10 / 15 / 25 / 30 | 0.19642 / 0.19564 / 0.19569 / 0.19599 | +0.00090 / +0.00012 / +0.00016 / +0.00046 |
| `promoted_offset` = 0 — seed AT the division mean (the defect) | 0.19683 | +0.00131 |
| `promoted_offset` = −50 / −100 / −150 / −225 | 0.19562 / 0.19570 / 0.19662 / 0.19874 | +0.00010 / +0.00017 / +0.00109 / +0.00322 |
| `debut_offset` = +75 / −75 / −150 | 0.19673 / 0.19631 / 0.19812 | +0.00121 / +0.00078 / +0.00259 |
| `carryover` = 0.85 / 0.75 (summer regression) | 0.19580 / 0.19612 | +0.00027 / +0.00060 |
| margin-of-victory multiplier ON | 0.19569 | +0.00017 |
| anchor = last `elo_pre` (`wcmodel.model.strength.team_elo_z`) | 0.19654 | +0.00101 |
| cold start = league mean (`elo_z` = 0, `wcmodel`'s shrink-to-mean) | 0.19683 | +0.00131 |

Two of these deserve a sentence.

**The anchor's staleness.** `team_elo_z` takes each club's last `elo_pre` — the
rating it carried *into* its most recent match, not out of it — so `wcmodel`'s
anchor is one match behind the rating the Elo comparator prices with. Scored
through the identical head, that costs 0.00101. The frozen anchor uses the
rating standing at the cutoff.

**Margin of victory.** It is not adopted even though the tuning gap is small
(+0.00017), because the published ~0.203 bar is plain Elo and a goal-difference
term would make this a different, stronger baseline wearing the same name.

### Rejected on design, deliberately not scored

**Cold start = drop the fixture.** The dropped matches are exactly the ones
involving the club the model knows least about, so removing them moves the
model's score in its own favour against a market benchmark that prices them
fine. Scoring this alternative would require the scoring window; it is excluded
on design grounds, before any number exists.

**Monkey-patching `wcmodel.model.strength.team_elo_z` to inject the anchor.**
Technically the smallest change and the one `scoreline.fit` invites (it imports
the symbol inside the function body). Rejected for two reasons: it hides the
substitution from a reader of the code, and `wcmodel`'s posterior cache key
hashes the config and the match panel but **not the ratings**, so two different
anchors would collide on one key and the cache would silently serve one fit's
posterior for another's. `epl/dcfit.py` calls the same sequence explicitly, and
`epl/anchor.py` writes an `epl_anchor_spec` token into the hashed `elo` block so
the key can tell two anchors apart.

**Re-tuning the model's own priors (`sigma_att`, `k_att`, `rho_scale`,
`decay_half_life_days`, `widening.strength`) for club football.** Not touched.
Those are the architecture; re-tuning them would mean the probe measured an
EPL-flavoured variant and could no longer be read against the two negatives the
World Cup version already published. They stay at their shipped values and the
result is a result about *that* model.

**Enabling covariates.** `model.covariates.enabled` is `[]`, as in the published
World Cup baseline. `rest_days` / `travel_km` / `altitude_m` are not wired for
EPL. `epl/dcfit.fit_epl` raises rather than running with covariates enabled.

**Bivariate Poisson instead of Dixon-Coles.** Available in `src/wcmodel` and not
run. Trying both and reporting the better one would be a two-shot test reported
as one.

---

## 8. What is blind, and what is not

Stated plainly because a preregistration that overclaims its own blindness is
worse than none.

**Blind.** No Dixon-Coles model has been fitted at any scoring-window cutoff.
No scoring-window RPS, log loss, or accuracy has been computed for any
forecaster during this phase. Every number in §6 and §7 comes from
2014/15–2018/19.

**Not blind, and this matters.** The tuning window was moved for this phase:
the Elo baseline (`reports/epl_baseline.md`) tuned on 2014/15–2017/18 and scored
2018/19–2025/26, so **the Elo comparator's per-season scores on 2019/20–2024/25
are already published** — 0.2014, 0.2234, 0.1959, 0.2021, 0.1910, 0.2061 against
a market of 0.1984, 0.2111, 0.1890, 0.1975, 0.1805, 0.1961. The scoring window
is therefore blind with respect to the **model**, which is the thing under test,
and *not* blind with respect to **Elo and the market**, which are the fixed
comparators. Those published numbers were produced under a slightly different
frozen config (`home_advantage` 100 rather than 40, on a window that included
2018/19 and 2025/26) and will be re-derived under the frozen config in §6, so
they will move a little; but the level is known and it would be false to claim
otherwise.

The window move itself is a degree of freedom and is recorded as one. It was
made for two stated reasons — a fourth scored tuning season and three more
promoted-club events for Fix 2 to be identifiable at all, and the removal of a
partial season whose odds coverage is a biased contiguous tail (210 of 380
matches, prices stopping 2026-01-08, home-win rate 0.452 on the covered part
against 0.394 on the uncovered) — and it was made **before** any Dixon-Coles
scoring-window number existed. A reader who thinks that is too convenient can
check: `epl/windows.py` and `epl/config_frozen.json` are committed in the same
commit as this document, and the run phase does not exist yet in the history.

**Other known caveats, carried forward.**

1. Five seasons (2014/15–2018/19) have no kickoff times, so their same-day
   matches cannot inform one another. Deliberately strict; all five are
   tuning-only.
2. The market benchmark is Pinnacle closing prices only. "The market" here means
   one sharp book, not a consensus.
3. Promoted clubs returning from a spell in the second tier are seeded fresh,
   with no memory of an earlier top-flight rating. Shrinking a remembered rating
   toward the seed is equally defensible and remains untested.
4. `wcmodel`'s provisional/volatility arm carries a 16.5-point threshold derived
   from international rating deltas at K up to 40. **At club K it flags nobody**
   — measured at two tuning-window cutoffs, where the only provisional club is
   the cold-start one Fix 3 flags explicitly (2016-08-13: Middlesbrough alone;
   2019-05-12: the empty set). So predict-time mechanism-(c) widening is inert
   on this data except where Fix 3 turns it on. That is reported, not tuned:
   re-deriving the threshold for club football would be re-tuning the
   architecture, which §7 rules out.

---

## 9. What gets published either way

One report, `reports/epl_result.md`, containing: the three headline RPS numbers
with block-bootstrap CIs; the paired Δ and its CI against the rule in §3; the
realised paired SD and the achieved MDE; log loss and accuracy; the per-season
table; the three preregistered subsets; the calibration table; the fit
diagnostics; the measured cost; and the verdict in the words PASS, REJECT, or
INCONCLUSIVE (with sub-case).

If the verdict is INCONCLUSIVE — the most likely outcome, per §3 — the report
says so in the first paragraph, and says what sample size would have been
needed. It does not go looking for a subset where the sign is favourable.
