# EPL baseline: walk-forward Elo against the closing market

**Branch** `epl-probe` · **Date** 2026-08-14 · **Code** `epl/elo.py`, `epl/ordlogit.py`,
`epl/devig.py`, `epl/score.py`, `epl/walk.py`, `epl/baseline.py`
**Reproduce**

```
PYTHONPATH=src:. .venv/bin/python -m epl.baseline --tune            # 130 s
PYTHONPATH=src:. .venv/bin/python -m epl.baseline --score --sensitivity   # 60 s
PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests -q            # 42 tests
```

---

## The answer

On 2,870 Premier League matches from 2018/19 to 2025/26, scored complete-case
against Pinnacle closing prices:

| forecaster | n | **RPS** | log loss | accuracy |
|---|---:|---:|---:|---:|
| de-vigged market (proportional) | 2,870 | **0.1943** | 0.9494 | 55.6% |
| de-vigged market (Shin) | 2,870 | 0.1943 | 0.9492 | 55.6% |
| walk-forward Elo + ordered logit | 2,870 | **0.2011** | 0.9701 | 54.6% |
| base rate (walk-forward H/D/A) | 2,870 | **0.2344** | 1.0649 | 44.2% |

**Elo − market = +0.00679** mean RPS (positive = Elo worse).
Paired per-match SD **0.0577**, iid SE 0.00108.
Block-bootstrapped 95% CI, 10,000 resamples:

* by (season, ISO week) — 266 blocks: **[+0.0047, +0.0089]**
* by season — 8 blocks: [+0.0041, +0.0093]

The market beats naive Elo by about seven thousandths of RPS, and the interval
is nowhere near zero. Elo beats the base rate by 0.0333 [−0.0380, −0.0285]; the
market beats it by 0.0401. **So the entire headroom a Premier League model can
compete for, above naive Elo, is 0.0068 RPS** — and that is what the Bayesian
architecture would have to close to be worth building. For scale, it tied Elo at
the World Cup and lost to the market by ~0.010 there.

## Cross-check against the research figures

The bar was established externally before any of this ran. Both sets of numbers:

| | research | measured here | Δ |
|---|---:|---:|---:|
| de-vigged market RPS | ~0.196 | 0.1943 | −0.0017 |
| walk-forward Elo RPS | ~0.203 | 0.2011 | −0.0019 |
| base rate RPS | ~0.234 | 0.2344 | +0.0004 |
| Elo − market gap | ~0.007 | 0.0068 | −0.0002 |
| paired SD | ~0.0619 | 0.0577 | −0.0042 |

**They agree.** The base rate lands within 0.0004 and the gap within 0.0002 —
the two numbers that matter most, since the base rate pins the scale (a wrong
RPS convention would show up here as a factor of two) and the gap is the
conclusion. The two levels each sit ~0.0018 below research and the paired SD
~7% below.

That is not a discrepancy worth chasing, and here is why: the two levels moved
*together and in the same direction*, which is what a different season set
produces, not what a bug produces. Per-season market RPS in this window ranges
from 0.1805 (2023/24) to 0.2111 (2020/21) — a spread of 0.031, eighteen times
the 0.0017 difference in question. Any eight-season window will land somewhere
in that band. The published figures also do not name their exact seasons or
their book; these are Pinnacle closing prices, the sharpest available, so if
anything they should score slightly better than a study using a softer book or
an average across books. The gap surviving intact while both levels shift is
the signature of a level effect, not a modelling one.

The paired SD being 7% lower is the same story: the SD of a difference depends
on how often the two forecasters disagree, which depends on the sample.

## What was measured, exactly

**RPS convention.** The normalised (halved) three-outcome ranked probability
score, over the ordered categories `(home, draw, away)`:

```
              1      r-1  /  i          i        \ 2
RPS  =    ---------   SUM |  SUM p_j  -  SUM o_j  |          r = 3
            r - 1     i=1 \ j=1        j=1       /
```

With `r = 3` the leading factor is `1/2`. A uniform forecast scores 5/18 =
0.2778 on a home or away result and 1/9 = 0.1111 on a draw. The un-normalised
convention omits `1/(r−1)` and is exactly twice these numbers; publications use
both, so this one is pinned by unit test against hand-computed values and
against `wcmodel.model.calibration.rps` (the World Cup model's own
implementation, same convention, agreement to 1e-12).

**Log loss** is natural-log, `−ln P(realised)`, clipped at 1e-15.
**Accuracy** is top-pick, reported because it is legible and not because it is
proper — it ignores everything about a forecast except its argmax.

**Complete case.** One index, 2,870 matches: every match in the scoring seasons
that has an Elo forecast, a base-rate forecast, and all three closing prices.
`epl.score.paired_gap` refuses arrays of different length rather than aligning
them, so a partial-coverage forecaster cannot quietly be scored on an easier
subset than its rival.

**Blocks for the bootstrap** are (season, ISO calendar week) — 266 of them. The
source has no matchweek column, so the calendar week within a season stands in
for it; weeks containing a midweek round are simply larger blocks, which is
correct, since those matches are more dependent, not less. As it happens the
blocking barely matters: a season-clustered analytic SE is 0.001076 against the
iid 0.001077, i.e. the per-match differences are close to uncorrelated within a
season. The week-block CI and the iid interval agree to the fourth decimal. The
blocking was done anyway — finding out that dependence is negligible is not the
same as assuming it.

## The protocol, fixed before anything was scored

```
TUNE    2014/15 – 2017/18   K, home advantage, promoted seed, carryover
                            chosen here and only here, on mean RPS over
                            2015/16–2017/18 (first season is Elo burn-in)
FREEZE                      written to data/epl/baseline/tuning.json
SCORE   2018/19 – 2025/26   never touched during tuning; 2,870 matches
```

`epl.baseline.tune` raises if the frame it is handed contains a scoring season.
The Elo walk itself always covers the whole archive — a 2018/19 forecast needs
2014/15 in its history — but the *objective* only ever saw the tuning seasons.

## Elo: the choices, and which of them the data actually made

Textbook update, `E_home = 1/(1 + 10^(−(R_h + H − R_a)/400))`,
`R ± K(S − E)`, zero-sum. **No margin-of-victory multiplier in the headline**:
the ~0.203 bar is plain Elo, and quietly including a goal-difference term would
be a different, stronger baseline wearing the same name. It is implemented and
reported below as a sensitivity.

A domestic division is a closed 20-club pool with three clubs swapped every
summer, so two rules have no counterpart in the international model:

**1. Promoted clubs are seeded BELOW the division mean**, at
`division_mean + promoted_offset` where the division mean is taken over the 20
clubs that just completed the season. Seeding them *at* the mean would assert
that a club arriving from the second tier is an average Premier League club,
which the table refutes every year. **The tuning chose −75 rating points**, and
this is the one hyperparameter with a clear, interior optimum:

| promoted_offset | 0 | −75 | −150 | −225 |
|---|---:|---:|---:|---:|
| best tune RPS at that offset | 0.19837 | **0.19753** | 0.19844 | 0.19954 |

Seeding at the mean and seeding 150 points down are about equally wrong, in
opposite directions. On the scoring window, removing the penalty entirely costs
0.0030 RPS (0.2011 → 0.2041) — the single largest configuration effect measured
here. So this is not a convention adopted for tidiness; it is worth about half
the Elo-to-market gap on its own.

A club returning after a spell in the second tier gets the same seed as any
other promotion — its old top-flight rating is **not** restored. That rating is
at least a season stale, and the Championship season that earned the promotion
is not in this dataset, so "remembered" would mean remembered from before the
evidence we do not have. This is a choice worth revisiting: shrinking a
remembered rating toward the seed is equally defensible and untested here.

**2. Season carryover.** `R ← mean + carryover·(R − mean)` at each boundary.
The grid included `carryover = 1.0` (no regression at all) so the rule could
lose, **and it did**: 1.0 won (0.19753) over 0.85 (0.19761) and 0.75 (0.19778).
Summer regression buys nothing here. It stays in the code, switched off.

**K = 20**, with real curvature around it — 0.19839 at K=10, 0.19753 at K=20,
0.19850 at K=40. This is the one parameter the tuning genuinely determined.

**Home advantage = 100 rating points, and this number is not identified.** The
tuning surface across the whole grid is flat to six decimal places:

| home_advantage | 40 | 60 | 80 | 100 |
|---|---:|---:|---:|---:|
| best tune RPS | 0.1975309 | 0.1975309 | 0.1975303 | 0.1975292 |

A 2e-6 spread is noise, and the 100 was effectively picked by a coin flip among
the four. **This is expected and not a defect**: in a league every match has a
home side, so home advantage on the prediction side is absorbed exactly into
the ordered logit's thresholds. `home_advantage` therefore only affects the
*update* — how surprising a home win is — and that is a second-order effect the
objective cannot see. Reported explicitly because a reader who sees "tuned home
advantage = 100" is entitled to know the tuner had no opinion. The sensitivity
table confirms it: H=80 versus H=100 moves the score-window RPS by 0.0001.

**Seeding drift, since the docs promised to show it.** Starting from 1500 in
2014/15, the 20-club mean after each summer runs
1500 → 1500.9 → 1509.0 → 1517.9 → 1522.2 → 1534.9 → 1544.4 → 1553.7 → 1564.7 →
1572.2 → 1586.1 → 1602.4. It rises ~9 points a season because the 17 surviving
clubs are by construction better than the 20 that started, and a −75 seed does
not fully offset that (−150 would). Harmless — the head reads only rating
*differences* — but visible rather than silent, and it is a reminder that the
tuned offset is not the mean-neutral one. The data preferred the smaller
penalty anyway.

## Elo → 1X2: a three-parameter ordered logit, refit at every cutoff

```
eta             = b · (elo_home − elo_away) / 400
P(away)         = sigmoid(c1 − eta)
P(away or draw) = sigmoid(c2 − eta)      with c2 = c1 + exp(s)
```

Three parameters, not four. The international version of this head carries a
coefficient on a home-advantage indicator because at a World Cup only the host
plays at home; in a league that indicator is constant at 1 and is absorbed
exactly into the thresholds, so fitting it would identify `c1 − b_hfa` and
`c2 − b_hfa` but neither separately, and the optimizer would return an
arbitrary point of that ridge. Home advantage is not missing here — it is
carried by the asymmetry of the thresholds against the distribution of the Elo
edge. `c2 = c1 + exp(s)` makes the threshold ordering structural, so no
parameter value can put negative mass on the draw.

Fitted walk-forward: at every cutoff block the head is refit on **strictly
earlier matches only**, 1,818 fits across the scoring window. The final fit
(4,550 matches of history) gives `b = 2.408`, `c1 = −0.864`, `c2 = +0.272`;
across the whole walk `b` stays in 2.40–2.86. That slope is worth noting: Elo's
own expected-score curve is `logit = ln(10) · d/400 = 2.303 · d/400`, so the
head has independently landed within a few per cent of the rating system's own
scale, having been told nothing about it. The mapping is doing the job it
should and no more — which is exactly what makes this a *naive Elo* baseline
rather than a model with an Elo feature.

Convergence is judged on the gradient (‖∇‖∞ ≤ 1e-7 after a deterministic
restart loop), not on the optimizer's status flag: with an exact analytic
gradient and tight tolerances, L-BFGS-B reports `ABNORMAL` at points that are
already stationary, and on real blocks it does. Across the 1,818 fits the
median achieved norm is 9e-11 and the worst is 2.1e-8. Four starting points a
hundredfold apart agree to 6e-9 in probability, so a reported number does not
depend on the path the walk took.

## De-vig

`proportional` (normalise inverse prices) is the headline, because it is the
convention the published ~0.196 is quoted on and it has no free choices in it.
`shin` is reported alongside and **not selected on score** — preferring
whichever de-vig flattered the model would be choosing the benchmark to suit
the answer. They are indistinguishable here: 0.194316 versus 0.194278, a
difference of 4e-5, and the Elo gap moves by 4e-5 with them. Season overrounds
are 1.020–1.030, so there is very little vig to disagree about.

Both are re-implemented in `epl/devig.py` rather than imported from
`wcmodel.data.devig`, and the tests assert they agree with it to 1e-12 on the
real prices. The duplication is the point: an independent implementation that
agrees is evidence, where an import would only be a re-export.

## Per season

| season | n | Elo | market | base | Elo − market |
|---|---:|---:|---:|---:|---:|
| 2018/19 | 380 | 0.1896 | 0.1849 | 0.2375 | +0.0046 |
| 2019/20 | 380 | 0.2014 | 0.1984 | 0.2300 | +0.0031 |
| 2020/21 | 380 | 0.2234 | 0.2111 | 0.2449 | +0.0123 |
| 2021/22 | 380 | 0.1959 | 0.1890 | 0.2350 | +0.0069 |
| 2022/23 | 380 | 0.2021 | 0.1975 | 0.2285 | +0.0046 |
| 2023/24 | 380 | 0.1910 | 0.1805 | 0.2338 | +0.0106 |
| 2024/25 | 380 | 0.2061 | 0.1961 | 0.2354 | +0.0101 |
| 2025/26 | 210 | 0.1979 | 0.1994 | 0.2266 | **−0.0015** |

The market wins in seven of eight seasons. 2020/21 — the closed-doors COVID
season, when home advantage collapsed — is the worst for both forecasters and
the worst for Elo relative to the market, which is what you would expect of a
rating system carrying a home-advantage assumption through a regime change.

**The 2025/26 row must be read with care.** Its odds coverage is 210 of 380,
and the gap is *not random*: prices stop after 2026-01-08, so the covered rows
are the first part of the season, and they have a home-win rate of 0.452
against 0.394 for the uncovered rows. The *paired* comparison is unaffected —
both forecasters see the same fixtures — but the levels are computed on a
first-half slice. Excluding the season entirely:

| subset | n | Elo | market | base | gap | 95% CI |
|---|---:|---:|---:|---:|---:|---|
| all | 2,870 | 0.2011 | 0.1943 | 0.2344 | +0.0068 | [+0.0047, +0.0089] |
| excl. 2025/26 | 2,660 | 0.2014 | 0.1939 | 0.2350 | +0.0074 | [+0.0054, +0.0096] |
| ≥1 promoted club | 816 | 0.1886 | 0.1810 | 0.2369 | +0.0076 | [+0.0041, +0.0112] |
| no promoted club | 2,054 | 0.2061 | 0.1996 | 0.2334 | +0.0065 | [+0.0039, +0.0090] |

Dropping the partial season *widens* the gap. And the promoted split is worth a
line: both forecasters do better on matches involving a promoted club (those
matches are more predictable — the promoted club usually loses), and Elo's
deficit there is no worse than elsewhere, so the −75 seed is not visibly
leaving anything on the table.

## Calibration smell test

Mean forecast against realised frequency over the 2,870:

| | home | draw | away |
|---|---:|---:|---:|
| realised | 0.4422 | 0.2268 | 0.3310 |
| Elo | 0.4498 | 0.2296 | 0.3206 |
| market | 0.4379 | 0.2394 | 0.3227 |
| base rate | 0.4494 | 0.2377 | 0.3129 |

Everything is within about a point of realised (the SE on a frequency at
n=2,870 is 0.009), so nothing here is broken. Both model and market slightly
over-price the draw and under-price the away win on this sample.

## Sensitivity — a diagnostic, and it selected nothing

Score-window results under alternative Elo configurations, computed *after* the
frozen configuration was scored. Reading a winner off this table would be
tuning on the scoring window with extra steps; its only job is to answer "how
much of the headline is the tuning?"

| config | K | H | carry | offset | Elo RPS | gap |
|---|---:|---:|---:|---:|---:|---:|
| **chosen** | 20 | 100 | 1.0 | −75 | **0.2011** | **+0.0068** |
| 2nd on tune | 20 | 80 | 1.0 | −75 | 0.2010 | +0.0067 |
| median of grid | 10 | 60 | 0.75 | −75 | 0.2008 | +0.0065 |
| worst on tune | 10 | 40 | 0.75 | −225 | 0.2046 | +0.0103 |
| no promoted penalty | 20 | 100 | 1.0 | 0 | 0.2041 | +0.0098 |
| K = 10 | 10 | 100 | 1.0 | −75 | 0.2028 | +0.0085 |
| K = 40 | 40 | 100 | 1.0 | −75 | 0.2017 | +0.0074 |
| margin-of-victory on | 150 | 100 | 1.0 | −75 | 0.2021 | +0.0077 |

Two things to take from this. First, **the conclusion is robust**: across every
configuration tried, including the worst point of the tuning grid, the gap
stays between +0.0065 and +0.0103 and never approaches zero. No plausible Elo
tuning closes it.

Second, **the tuning bought essentially nothing on the scoring window** — the
grid's *median* configuration scores 0.2008 against the chosen 0.2011. That is
an honest negative and it should be said plainly rather than buried: with 1,140
tuning matches and a surface this flat, hyperparameter selection is within
noise, and the only choice that carried real weight was the promoted-club seed,
which the sensitivity table confirms independently (removing it costs 0.0030).
Margin of victory does not help either.

## Point-in-time discipline

One implementation of the cutoff (`epl/walk.py`) serves the ratings, the head,
and the base rate, so there is one place to get it wrong rather than three. A
*block* is a set of matches sharing a cutoff key — the kickoff where one exists,
the date at midnight where none does — and a match may use every match in every
strictly earlier block and nothing else. Collapsing the two-clause ordering rule
onto one key is exact only while no date carries both a timed and an untimed
match; that precondition is checked in code, not assumed, so a future
half-timed season fails loudly instead of leaking same-day results backwards.

The tests attack it rather than describe it:

* **Rewrite the future, check the past.** Every result after 2021-01-01 becomes
  a 9–0 home win; every pre-cutoff `elo_*_pre` must be bit-identical. A
  positive control asserts the post-cutoff ratings *did* move, so the test
  cannot pass vacuously. The same attack is run through the whole stack —
  ratings, head, and base rate — with a 0–4 away rewrite.
* **The head's fit sample ends where its block begins.** Every one of the 1,818
  fits is asserted to satisfy `n == block_start_row`.
* **The tuner refuses a scoring season.**

42 tests, all passing.

## Cost

| | |
|---|---|
| Elo walk, 4,560 matches | 20 ms |
| one ordered-logit fit | 1.0 ms @ 500 rows → 5.6 ms @ 4,560 rows |
| full walk-forward scoring run (1,818 fits) | 6.5 s |
| tuning grid, 288 configurations | 130 s |

The whole baseline is a two-minute job. That is the number the Bayesian
alternative gets compared against: the PyMC/ADVI scoreline model costs minutes
*per fit*, and a walk-forward EPL backtest at anything like this granularity
would be a different order of undertaking — which is why establishing that the
target is a 0.0068 RPS improvement, before building it, was the right first
step.

## What this does and does not settle

**Settled.** The bar is real and reproduced in-repo: market 0.1943, Elo 0.2011,
base 0.2344, gap 0.0068 [0.0047, 0.0089], and the research figures are
corroborated. Naive Elo on EPL is a genuinely strong baseline — it captures 83%
of the market's edge over the base rate — and the remaining headroom is small
and now measured rather than assumed.

**Not settled.** Whether the Dixon-Coles/bivariate-Poisson architecture beats
*this* Elo. That is the next question and the whole point of the exercise.

What this report supplies is the yardstick and, more usefully, **the sample
size the next experiment will need.** At a paired SD of 0.0577, the minimum
improvement detectable at 80% power is:

| matches | 380 (1 season) | 760 | 2,870 (this window) | 6,536 |
|---|---:|---:|---:|---:|
| smallest detectable RPS gain | 0.0083 | 0.0059 | 0.0030 | 0.0020 |

Read that table before designing the model comparison. **A single season cannot
resolve anything smaller than 0.0083 — larger than the entire Elo-to-market
gap.** Even the full eight-season window here can only resolve 0.0030, less
than half that gap. So a plausible outcome of the next phase is a model that is
genuinely a little better than Elo and a backtest that cannot prove it; the
honest response to that will be to say so, not to reach for a shorter window
where the point estimate happens to look good. Detecting 0.002 — a realistic
size for a well-built scoreline model's edge over Elo — needs about 6,500
matches, i.e. seventeen Premier League seasons or a multi-league panel.

**Known caveats.**

1. 2025/26 contributes 210 rows from a biased, contiguous, first-half slice.
   Reported separately; excluding it widens the gap to +0.0074.
2. `home_advantage` is not identified by this objective (see above). The frozen
   100 should not be quoted as an estimate of anything.
3. Five seasons (2014/15–2018/19) have no kickoff times, so their same-day
   matches cannot inform one another. This is deliberately strict and costs a
   little information; three of those five seasons are tuning-only.
4. Promoted clubs returning from a spell down are seeded fresh, with no memory.
   Untested alternative.
5. The market benchmark is Pinnacle closing prices only. No second book is in
   the archive, so "the market" here means one sharp book, not a consensus.
