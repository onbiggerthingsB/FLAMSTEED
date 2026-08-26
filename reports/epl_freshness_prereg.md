# Fit freshness — preregistration of the paired matchday-refit experiment

**Written:** 2026-08-26 · **Branch:** `main` · **Corpus:** frozen, pinned below
**Status when written:** **no harness exists.** There is no `epl/freshness.py`, no
runner, no shard, no ledger, no result file, and not one matchday fit has been
run. No paired delta for any fixture in this experiment exists anywhere in this
repository, and none can, because the code that would compute one has not been
written.

This document fixes the question, the estimand, the resampling, the secondaries,
the adoption rule, the refusal semantics and the scope **before** the harness
that answers it. It follows the pattern of
[`reports/epl_sim_prereg_retro.md`](epl_sim_prereg_retro.md) (07b5871), with one
difference stated here so it is not discovered later: that document could hash
its harness because the harness already existed. This one cannot. **The harness
hashes are frozen by a follow-up commit, after the harness is written and
audited and before any fit is run** — §6 says exactly what that commit must
contain.

Every number below was computed on 2026-08-26 from the pinned corpus and the
frozen configuration, by the recipes given beside them, **before this document
was committed and before any harness code was written**. Where a figure from the
design review could not be reproduced, it is quoted and the failure to reproduce
it is recorded rather than smoothed over (§1.4).

This experiment reads exactly two families of numbers: the model's own 1X2
probabilities (`dc_home`, `dc_draw`, `dc_away`) and the realised outcome (`y`).
The corpus's other forecaster columns — `elo_*`, `base_*`, `market_*`,
`market_shin_*` — are **not read** by the estimand, by any secondary, or by the
adoption rule. Two adjacent things appear once each and are flagged where they
occur: §1.4's recomputation uses `elo_diff_pre`, a feature column and not a
forecaster, as a control; and §4.2 quotes a cadence effect measured on an Elo
proxy in a different artifact. Neither enters the estimand or the rule.

---

## 0. The corpus and the configuration, pinned

| | |
|---|---|
| Corpus | `data/epl/fit/walkforward_predictions.parquet` |
| SHA-256 | `f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a` |
| Rows | **2,280** — 6 seasons × 380 |
| Seasons | 2019/20, 2020/21, 2021/22, 2022/23, 2023/24, 2024/25 |
| Outcome counts (`y` = 0 home / 1 draw / 2 away) | 993 / 525 / 762 |
| Frozen config | `epl/config_frozen.json`, SHA-256 `9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc` |
| Realised config | `epl.freeze.frozen_wcmodel_config()` — `seed` **20260611**, `windows.decay_half_life_days` **365**, `windows.feature_years` **4**, `model.inference` `{backend: advi, draws: 1000, tune: 1000, advi_iters: 30000}`, `model.widening` `{mechanism: c, strength: 0.5}` |

The corpus digest, row count, season tuple and outcome counts are **already
pinned in code**, at `epl/recalfit.py:91-98` (`CORPUS_SHA256`, `CORPUS_ROWS`,
`CORPUS_SEASONS`, `CORPUS_Y_COUNTS`), by A8. This experiment adopts the same
constants rather than restating them, so there is one place where "which corpus"
is defined and one digest to break.

Verify with:

```
shasum -a 256 data/epl/fit/walkforward_predictions.parquet epl/config_frozen.json
```

**Precision.** Every probability in the corpus was written by
`epl/walkforward.py::_one_cutoff` as `round(v, 8)`. All 2,280 `dc_home` values
satisfy `round(v, 8) == v` exactly. Comparisons against the corpus in §3.2 are
therefore comparisons at eight decimals, which is all the corpus holds.

### 0.1 The structure the whole design rests on, recomputed

A walk-forward block is `(season, ISO week)`; the cutoff is that block's opening
day at midnight; `wcmodel.data.features.build` keeps `date < cutoff.normalize()`
(`epl/walkforward.py`, module docstring and `matchweek_cutoffs`). The corpus's
`block` column carries that label. Recomputing the cutoff as each block's
minimum fixture date reproduces the ledger's own `cutoff` field for **all 2,280
rows** (checked against `data/epl/fit/walkforward_ledger.jsonl`).

| quantity | value |
|---|---:|
| blocks | **212** |
| distinct match dates | **719** |
| block-opening dates (already fitted) | **212** |
| additional match dates (never fitted) | **507** |
| 212 + 507 | **719** — every match date is one or the other |
| fixtures priced on their block's opening day (*fresh*) | **581** |
| fixtures priced from an earlier cutoff (*stale*) | **1,699** (74.52%) |
| blocks holding at least one stale fixture | **203** of 212 |
| stale fixtures per block | min 1, median 9, max 19 |
| stale fixtures per additional fit date | median 3, max 10 |

Staleness in days, over all 2,280 rows:

| days | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| fixtures | 581 | 340 | 164 | 112 | 181 | 550 | 352 |

**Staleness is bounded at 6 days by construction**, because a block is an ISO
week and its cutoff is that week's first match day. There is no long-horizon
staleness anywhere in this corpus and this experiment measures none.

### 0.2 The size of the treatment

For a stale fixture, the matchday fit differs from the block fit by exactly the
matches its own block played strictly before its date — there are no other
league matches inside an ISO week of that season.

| stratum | n | extra training matches: median | mean | max |
|---|---:|---:|---:|---:|
| 1 day stale | 340 | 2 | 3.36 | 9 |
| 2 days stale | 164 | 5 | 4.76 | 10 |
| 3+ days stale | 1,195 | 6 | 5.53 | 18 |
| **all stale** | **1,699** | **4** | **5.02** | **18** |

**No stale fixture has a zero dose:** the minimum is one match, and the smallest
treatment in the experiment is "the block's own opening-day results are now in
the fit" — which is precisely what a live per-matchday cadence buys on a Sunday.

Five matches is ~0.13–0.25% of the ~2,000–3,900 matches in a training frame, but
the likelihood is decay-weighted — `decay_weight = 0.5 ** (age_days / 365)`
(`src/wcmodel/data/features.py:297`), which `to_match_panel` renames to the
panel's `weight` — so the *weighted* share is larger. At three representative
cutoffs, five matches at weight 1.0 against the summed decay weight of the whole
training frame. The training-match counts are **the walk-forward ledger's own
`n_training_matches`** at those cutoffs, and they equal every played match dated
before the cutoff exactly (1,989 / 2,851 / 3,879, checked both ways): the fit
crops nothing, it down-weights.

| cutoff | training matches | summed decay weight | 5 matches, raw share | 5 matches, weighted share |
|---|---:|---:|---:|---:|
| 2019-10-21 | 1,989 | 508.6 | 0.251% | **0.98%** |
| 2022-01-11 | 2,851 | 551.9 | 0.175% | **0.91%** |
| 2024-10-21 | 3,879 | 520.3 | 0.129% | **0.96%** |

**The median treatment is about a one-percent shift in effective likelihood
weight.** That is stated here, before the run, so that a small effect is not
later reported as a disappointment and a large one is not reported without
someone asking how one percent of the weight moved a forecast that much.

---

## 1. The question

### 1.1 As design v2 states it

Weekly refit blocks are a **harness convention**, not an architecture floor. The
preregistered walk-forward fixed one fit per `(season, ISO week)` because the
preregistration fixed it (`epl/walkforward.py`, `CADENCE_WEEKS = 1`, and the
module docstring's refusal to coarsen it). Nothing in the model requires it. In
the pinned corpus, **1,699 fixtures (74.5%) were priced from a fit whose cutoff
predates their match date** — by up to six days, with a median of four extra
matches unseen.

The question is therefore: **would pricing each fixture from a fit taken at its
own matchday have scored better, and by how much?**

### 1.2 Why the design is paired, and what the pairing buys

The cheap version of this question compares the RPS of stale fixtures to the RPS
of fresh ones. That comparison is **not the estimand**, and it cannot be made
into one, because stale and fresh fixtures are **different fixtures** — and on
this corpus they are different in a way that is not subtle. An ISO week starts on
Monday, so **105 of the 212 blocks open on a Monday** and go on to price that
week's weekend. The weekday composition of the two groups, recomputed:

| weekday | fresh (s = 0) | stale (s > 0) | total |
|---|---:|---:|---:|
| Mon | 132 | **0** | 132 |
| Tue | 78 | 44 | 122 |
| Wed | 23 | 166 | 189 |
| Thu | 21 | 73 | 94 |
| Fri | 17 | 52 | 69 |
| Sat | 304 | 734 | 1,038 |
| Sun | **6** | **630** | 636 |

**Every Monday fixture is fresh by construction** — Monday is day 0 of its own
ISO week, so its staleness cannot be anything but zero — and **630 of 636 Sunday
fixtures are stale**. A cross-sectional stale-versus-fresh contrast on this
corpus is therefore substantially a **Sunday-versus-Monday** contrast, which is a
contrast in broadcast selection, in the strength gap between the two clubs, in
congestion and in rest. Any of those moves RPS on its own, and none of them is
staleness.

The paired design removes the composition effect **exactly**, not
approximately: each of the 1,699 deltas is the same fixture, the same clubs, the
same date, the same realised outcome, scored by the same metric, differing in
**one thing only — the cutoff of the fit that priced it**. Nothing about which
fixtures are stale can enter the mean of a within-fixture difference.

### 1.3 What the pairing does NOT remove, named in advance

**(a) ADVI sampling noise between two fits.** The two arms are two separate
approximate-inference runs. They use the *same* seed value — 20260611, read from
`freeze.frozen_wcmodel_config()`, which `epl/walkforward.py` does **not** vary by
cutoff; there is no per-cutoff seed derivation anywhere in the walk — but they
are optimised against different data, so their optimiser trajectories are
different and their residual noise is effectively independent. Pairing cannot
subtract this. Its measured scale on this exact corpus and model, from
[`reports/epl_walkforward.md`](epl_walkforward.md):

* the whole 212-fit walk re-run at seed 987654 moved the pooled DC mean RPS by
  **+0.000075** over 2,280 fixtures;
* per-match probability distance between the two runs: **mean 0.0032, p99
  0.0139, max 0.0229**;
* a per-fit probe over 12 cutoffs × 10 fixtures: mean absolute shift 0.0034, max
  0.0200.

**The block bootstrap must absorb this, and the blocking is chosen so that it
can.** Every fit involved in pricing a fixture — its block fit (at the block's
opening day) and its matchday fit (at its own date) — has a cutoff **inside that
fixture's own `(season, ISO week)` block**, because the block *is* the ISO week
its date falls in. Fit-level noise is therefore nested strictly inside a
bootstrap block in **both** arms, and resampling whole blocks carries it. An iid
bootstrap would not: the block fit's noise realisation is shared by up to 19
fixtures at once, and an iid resample would count those as independent evidence.

**(b) The asymmetry that does have a direction.** The matchday fit's training
set is a strict superset of the block fit's. That is the treatment, not a
confound — but it means **any leak in the harness biases the result toward
freshness**, which is the direction the operational change would be adopted on.
Three guards, pre-stated:

1. The matchday cutoff is the fixture's own date **at midnight**, and
   `features.build` keeps `date < cutoff.normalize()`. A fixture is never in the
   fit that prices it, and neither is any other fixture kicking off the same
   day. This is not a convenience: it is exactly what a live per-matchday
   issuance could actually condition on — results through the previous day.
2. `epl.walkforward.point_in_time_canary` is re-run as a refusal check (§5.3).
   It rewrites every result from a cutoff onward to 9-0 and demands
   `np.array_equal` on the resulting forecasts; on the preregistered walk it
   returned **max |Δp| = 0.0** with a positive control of 0.812.
3. The §3.2 control re-fits block-opening dates and demands the corpus's own
   rows back. A fit that has quietly gained information would fail it.

**(c) The treatment is a bundle, and the design does not decompose it.** Moving
the cutoff advances *everything the pipeline conditions on*: the likelihood's
matches, the Elo anchor state read at that cutoff
(`epl.dcfit.anchor_state_at(anchor, cutoff, teams, observed_by)`), the cold-start
and provisional club sets, and the feature panel. The estimand is the value of
**a fit taken at the fixture's own matchday**, which is the operational object,
not the marginal value of five extra matches in the likelihood. Nothing here
attributes the effect to a component, and no such attribution may be read out of
the result afterwards.

**(d) Direction of bias, on balance.** Setting aside a harness leak (guarded
above), the residual is sampler noise, which is close to mean-zero and enters
both arms through the same optimiser, the same `advi_iters`, the same draw count
— so the approximation penalty is first-order equal in the two arms and cancels
in the difference. **The honest summary is that the design has no argued
direction of bias, and a variance floor of order 1e-4 that the threshold in §4
is built on top of.**

### 1.4 The cross-sectional number, and a discrepancy recorded rather than hidden

Design v2 reports a **cross-sectional staleness penalty of 0.00153 RPS**.
Recomputing the cross-section from the pinned corpus, this document could not
reproduce that figure under any of twenty recomputations — varying the
adjustment, the fixed effects, the reference forecaster and the season set. The
six most natural:

| definition (all on `dc_rps`, corpus as pinned) | value |
|---|---:|
| raw mean, stale − fresh | **−0.004703** |
| within-block per-day slope (block fixed effects, s in days) | **+0.001590 / day** |
| ...same, adding \|`elo_diff_pre`\| and both promoted flags as controls | +0.001933 / day |
| block-weighted mean of (block's stale mean − block's fresh mean) | −0.000887 |
| mean of (stale fixture − its own block's fresh mean) | +0.000151 |
| stale-indicator coefficient with block fixed effects | −0.004865 |

The closest quantity is the within-block per-day slope, **+0.00159**, which is
near 0.00153 but not equal to it, and is a *per-day* rate rather than a level.

**This document does not resolve the discrepancy and does not need to**, because
**no cross-sectional number is the estimand, is a secondary, or enters the
adoption rule**. It is recorded for the reason the amendment ledger exists: a
figure that motivated a design and cannot be reproduced from the pinned corpus
is a fact about the design's provenance, and the place to write it is before the
run, not after. If the design review's recipe is later supplied and reproduces
0.00153, that is a dated note, not a change to anything below.

And the recomputation makes the case for pairing **stronger, not weaker**. Six
adjustments of the *same 2,280 rows* disagree about both the sign and the size:
as levels they run from **−0.00487 to +0.00015**, and as rates from **+0.00159
to +0.00193 per day** — which over the mean staleness of 3.88 days would imply
about **+0.0075**, fifty times the figure being reproduced and pointing the
other way from the raw contrast. The raw contrast says stale fixtures score
*better*, which no one believes is causal; §1.2 shows why (it is largely Sunday
against Monday). **That spread is the confounding, made visible, and it is why
the estimand is paired.**

---

## 2. The estimand

> **The mean paired RPS delta, matchday-fit minus block-fit, over all 1,699
> stale fixtures of the pinned corpus. Negative means freshness helps.**

Precisely:

* **Arm B (block fit)** — for each of the 1,699 stale fixtures, the probabilities
  **already in the corpus** (`dc_home`, `dc_draw`, `dc_away`) and the RPS already
  in it (`dc_rps`). Arm B is **not recomputed**. It is the published
  walk-forward's own output, at the eight decimals it was written with.
* **Arm A (matchday fit)** — for each of the **507** match dates that are not
  block-opening dates, one fit at `cutoff = that date at midnight`, run through
  the identical pipeline: `freeze.frozen_wcmodel_config()`, seed **20260611**,
  `epl.fit.build_store` over the played frame, `epl.anchor.Anchor` with
  `freeze.frozen_elo_config()`, `epl.dcfit.fit_epl` with
  `feature_cache_dir=paths.FIT_CACHE_DIR`, `fast_panel=True` (proven inert at
  panel and forecast level, `verify_fast_path_is_inert`), then
  `post.predict_1x2(home, away, neutral=False)` for that date's fixtures,
  rounded to 8 decimals by the same `round(v, 8)` the ledger uses.
* **The delta** — `rps(A) − rps(B)` per fixture, with RPS computed by
  `epl.score.rps` (`epl/score.py:91`) on the same `y` encoding (0 home, 1 draw,
  2 away).
  Arm B's delta input is the stored `dc_rps`; the harness must also recompute
  RPS from the stored probabilities and refuse if the two disagree by more than
  **1e-12** (`ScoreMismatch`, §5.1). Checked on 2026-08-26 across all 2,280
  rows: the maximum difference is **0.0** — the check is a guard against a
  future corpus, not a tolerance the present one needs.
* **The statistic** — the mean over all 1,699 deltas, pooled over matches (not a
  mean of block means).
* **The interval** — `epl.score.block_bootstrap_ci` (`epl/score.py:193`), blocks
  = the corpus's own `block` column, i.e. **(season, ISO week)**, giving **203**
  blocks; **B = 10,000**; **percentile**; `alpha = 0.05`; resampling seed
  **20260814**, the function's default and the project's standard. Blocks are
  drawn with replacement and the statistic is the pooled mean, so unequal block
  sizes are weighted as the estimator weights them.

**The denominator is fixed at 1,699 and no fixture may be dropped.** A fixture
Arm A cannot price is a refusal (§5.1), never a deletion. On the preregistered
walk, unpriceable fixtures were **0 of 2,280**, and Arm A's fits see strictly
more data than Arm B's, so an unpriceable fixture in Arm A is a defect by
construction.

**No power claim is made in advance.** The paired SD of matchday-minus-block
deltas is unknown until the fits exist — it depends on how far a ~1% shift in
decayed likelihood weight moves an ADVI posterior, which nothing in this
repository measures. The realised paired SD, SE, and the MDE at 80% power are
reported **with** the result. **No threshold in §4 moves in response to them.**

---

## 3. Secondaries — reported, never deciding

Everything in this section is published with the result and **decides nothing**.
No secondary may adopt, block, or qualify an adoption. In particular, a
stratum that clears the §4 threshold while the estimand misses it **does not
license a staleness-conditional cadence**: that is a different rule, and it would
need its own preregistration and its own run.

### 3.1 Strata

**By days of staleness** — three strata, fixed here: **1 day (n = 340)**,
**2 days (n = 164)**, **3+ days (n = 1,195)**. The 3+ stratum is not split
further; its interior (3: 112, 4: 181, 5: 550, 6: 352) is printed for
completeness but is not a stratum, because splitting it after the fact is how a
subgroup gets chosen.

**By season** — six strata, as the corpus's seasons:

| season | fixtures | stale | stale share | blocks |
|---|---:|---:|---:|---:|
| 2019/20 | 380 | 259 | 68.2% | 35 |
| 2020/21 | 380 | 307 | 80.8% | 34 |
| 2021/22 | 380 | 283 | 74.5% | 36 |
| 2022/23 | 380 | 294 | 77.4% | 34 |
| 2023/24 | 380 | 285 | 75.0% | 37 |
| 2024/25 | 380 | 271 | 71.3% | 36 |

2020/21 has the highest stale share (80.8%) and 2019/20 the lowest (68.2%) — an
observation, not a tested claim; no season is excluded, re-weighted, or given a
reason in advance to be dropped later.

Each stratum reports n, mean delta, paired SD, and a **(season, ISO week)** block
bootstrap CI at the same B and seed. **Six seasons and three staleness strata
mean nine intervals; some will exclude zero by chance.** No multiplicity
correction is applied, because none of them decides anything — and that is the
correction.

### 3.2 The fresh-fixture sanity control

**What it is.** Twenty **block-opening** dates are re-fitted and their own-day
fixtures re-priced. Those fits are re-runs of a specification the corpus already
contains, so **they must return the corpus's own rows**.

**The twenty dates**, chosen now and printed so the choice cannot move: sort the
212 block-opening dates ascending as ISO strings, take indices
`numpy.random.default_rng(20260826).choice(212, size=20, replace=False)`, sort
the result.

```
2019-10-21  2019-12-03  2020-02-14  2020-03-07  2020-06-22
2020-07-20  2020-09-14  2021-10-16  2021-12-06  2022-01-11
2022-08-05  2022-10-01  2022-10-18  2023-04-01  2023-04-03
2023-09-01  2024-02-12  2024-02-26  2024-09-21  2024-10-21
```

They carry **56 own-day fixtures** — 168 probabilities — and cover all six
seasons.

**The tolerance ruled: exact equality at the corpus's own precision.** Not a
numeric tolerance. Every one of the 168 recomputed probabilities must equal the
stored `dc_home` / `dc_draw` / `dc_away` **exactly** as the 8-decimal values the
corpus holds, and the RPS recomputed from them must equal the stored `dc_rps` to
**1e-12** (arithmetic on identical inputs; the looser bound is for float
summation order only).

**The reasoning, read from the code rather than assumed.** The seed does not vary
by cutoff — it is the single constant 20260611 — and a fit is a pure function of
`(cutoff, store, frozen config)`. The project already demands and gets bit
equality from two separate `fit_epl` calls: `point_in_time_canary` compares two
fits with `np.array_equal` and returned **max |Δp| = 0.0** on the preregistered
walk, and `verify_fast_path_is_inert` compares panels with `DataFrame.equals`.
Asking for less here would be asking for less than the project already proves.

**The condition that makes the demand fair**, pre-stated: the control runs in the
same interpreter and virtual environment as the main run, with
`OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1` per worker, and with
`fast_panel=True`. The thread pinning is recorded in every row's provenance
(§5.2), so a run in a different threading environment is visible rather than
silent.

**What the control actually tests, and why it is not a formality.** The archive
has grown since the walk-forward run — 2025/26 and 2026/27 results have been
ingested. Arm A builds its store and anchor from the archive **as it stands at
run time**, exactly as `run_walk` does, and relies on the point-in-time property
to make later data irrelevant. The control is where that reliance becomes a
check. **A mismatch is most likely archive drift, not sampler noise**, and it is
a STOP either way.

**On failure: the run stops.** `ControlMismatch` (§5.1). The control runs
**first**; not one matchday fit is run until it passes. A tolerance is not
widened after seeing a difference — a difference is an amendment, written before
anything continues.

**Reported regardless:** the maximum and mean absolute probability difference
across the 168 comparisons, so the number is on the record even when it is zero.

### 3.3 Movement diagnostic

The mean and max absolute probability difference between Arm A and Arm B across
all 1,699 stale fixtures, printed beside the seed-replica scale from §1.3 (mean
0.0032, p99 0.0139, max 0.0229). It answers "did the treatment move the forecast
at all, or less than re-seeding does" — which is worth knowing whichever way the
estimand lands. It decides nothing.

---

## 4. The adoption rule for the live cadence

### 4.1 The rule

> **ADOPT per-matchday fits for the live cadence if and only if BOTH:**
>
> **(i) the point estimate of the estimand is `Δ ≤ −0.00030` RPS, and**
> **(ii) the 95% (season, ISO-week) block bootstrap CI excludes zero — that is,
> its upper bound is strictly < 0.**
>
> **Otherwise the weekly cadence stands.**

Both conditions are required, and neither is sufficient.

### 4.2 Why −0.00030, argued against house precedent

The improvement program's bar for a **model change** was **Δ ≤ −0.0010**
([`reports/epl_improved.md`](epl_improved.md) §5.2), and every one of 45
challengers missed it; the best was −0.000065. That bar buys three things: cover
against **selection over a grid**, cover against **new parameters that fit noise
and generalise worse**, and cover against **sampler noise**.

A cadence change is **operational**. It changes *when* the fit happens and
nothing about *what* is fitted: the same likelihood, the same priors, the same
hyperparameters, the same frozen config, zero new parameters. And there is
**exactly one pre-stated candidate** — per-matchday — not a grid. Two of the
three things the −0.0010 bar buys are therefore not being bought here. A lower
bar is arguable, and this document rules a lower bar.

**It is not zero, and it is anchored to the noise, not to an expected effect.**
The bar is **4 × 0.000075**, four times the measured shift in this model's
pooled RPS on this corpus when the whole walk is re-run at a different seed
(§1.3). The improvement program built its own noise gate the same way — B4 was
**3 ×** the measured ADVI seed-noise floor (0.0000454 → 0.000136). Four rather
than three, because there the two arms differed *only* in seed, while here they
differ in cutoff as well, so the perturbation between arms is at least as large
as a pure re-seed.

**And there is a real cost to clear.** Per-matchday fits mean **2.4 extra fits
per block** on this corpus's calendar (507 additional fits across 212 blocks), so
roughly **3.4× the weekly fit budget**, plus more failure surface in a live
pipeline that has to produce an issuance before kickoff. An operational change
should pay for itself by more than the sampler's own jitter.

**Stated in this order on purpose:** the threshold is derived from the noise
floor and the cost, *not* from any expectation about the answer. Only after
fixing it does this document note, for the reader who will ask, that the bar is
neither known-passable nor known-unreachable. The one measured cadence effect in
the project — `I1b`, on the Elo proxy — is that *a fortnightly refit costs*
**+0.000788 RPS, 95% CI [+0.000267, +0.001318]** (`epl_improved.md` §5.3), for
roughly seven extra days of staleness; scaled to this corpus's mean staleness of
3.88 days that is of order **+0.0004**, and `data/epl/fit/staleness.json` labels
that proxy an **upper bound** ("Elo learns faster per match than a 365-day-decayed
likelihood, so it has more to lose by going stale"). The confounded
cross-sectional slope of §1.4 would imply about **+0.0075**, nearly twenty times
larger.

So the bar sits **below** the proxy scaling and **far below** the cross-sectional
implication, and a reader is entitled to ask whether it was therefore chosen
where it would be passed. What can be checked, rather than asserted: the number
is 4 × 0.000075, and 0.000075 was measured and published in
`reports/epl_walkforward.md` months before this experiment was conceived; the
same arithmetic would have produced the same bar had the proxies pointed
anywhere at all; and the bar is committed **here**, before any delta exists, in a
commit that precedes every commit implementing the harness. **The direction and
size of the true effect are not known to anyone writing this.**

### 4.3 Why both conditions, and not either

A point estimate past the threshold with an interval straddling zero is exactly
the pattern the improvement program rejected four times over — every lever there
had a CI containing zero. An interval excluding zero at |Δ| < 0.00030 is a real
effect too small to buy 3.4× the fits: measurable and immaterial are different
findings, and this rule reports the difference instead of collapsing it.

### 4.4 What happens on a miss

**The weekly cadence stands**, unchanged, as `CADENCE_WEEKS = 1`.

**The result publishes either way.** `reports/epl_freshness_result.md` and
`data/epl/fit/freshness.json` are written whatever the sign, whatever the width,
including the case where the estimand is positive (freshness *hurts*, which a
~1% weight shift plus sampler noise can produce). **There is no file drawer**, and
no outcome of this experiment is a reason not to publish it.

A miss is not re-litigated: not by re-running at a second seed, not by dropping
2020/21, not by restricting to the 3+ stratum, not by moving to a one-sided
interval, and not by a bar chosen after the number exists. Each of those is
listed in §7 as an invalidation.

### 4.5 What adoption would and would not change

Adoption changes **when the fit happens**. It changes nothing about what is
computed from it: no schema, no threshold, no published content, no
`ISSUANCE_SCHEMA_VERSION`, no metric, no arm.

**Scope boundary.** This experiment scores **match-level 1X2 forecasts by RPS**.
It says nothing about the league-table simulator's TRPS, about table forecasts,
or about how often a table issuance should be re-issued. If the owner wants
table issuances to follow the fit cadence, that is an operational follow-through
of the same fit and is ruled separately; **this document does not license it.**

**A named limitation.** The corpus is 2019/20–2024/25 and the cadence decision
applies to 2026/27 and after. The *mechanism* generalises exactly — a live
per-matchday issuance conditions on results through the previous day, which is
what §2 measures — but the *magnitude* is measured on six past seasons with
different clubs. That is an argument, not evidence, and it is written here rather
than left implicit.

**Who decides.** Adoption is an owner ruling, recorded as a dated entry in
[`reports/epl_sim_amendments.md`](epl_sim_amendments.md). No script, no agent and
no report may change the live cadence on the strength of these numbers; the rule
above is what the ruling is checked against, not a switch that throws itself.

---

## 5. Refusal semantics for the run

### 5.1 Typed refusals, by name

All derive from **`FreshnessError`**, caught by `main()`, which prints
`STOP: …` naming the type and the offending key, and exits **2** — the
convention A8's `RecalError` set.

| type | fires when |
|---|---|
| `CorpusMissing` | the pinned parquet is absent |
| `CorpusDigestMismatch` | its SHA-256 is not `f31580073e…` |
| `CorpusShapeMismatch` | rows ≠ 2,280, seasons ≠ the pinned six, `y` counts ≠ (993, 525, 762) |
| `ConfigNotFrozen` | `epl/config_frozen.json` is not `9f2e086d…`, or the realised config's seed is not 20260611 |
| `ScheduleMismatch` | the recomputed schedule is not 212 blocks / 719 dates / 507 additional dates / 1,699 stale fixtures |
| `CutoffLeak` | a fit's training frame holds a match dated ≥ its own cutoff, or a fixture appears in the fit that prices it |
| `CanaryFailed` | `point_in_time_canary` returns `PASS: false` (§5.3) |
| `ControlMismatch` | any of the 168 control probabilities differs from the corpus (§3.2) |
| `FitFailed` | `fit_epl` raises, or `_health` reports a non-finite draw, a non-positive scale parameter, or an implausible `home_adv` |
| `UnpriceableFixture` | a club is absent from the posterior index at its own matchday |
| `ScoreMismatch` | RPS recomputed from stored probabilities differs from stored `dc_rps` by > 1e-12 |
| `SchemaMismatch` | a ledger row lacks a required field (§5.2) |
| `RowConflict` | two rows share a key and disagree on any non-volatile field |
| `ShardFailed` | a shard process exits non-zero, or writes no rows |
| `MergeIncomplete` | the merged ledger's key set is not exactly the 507 pre-stated fit keys |

**A failed fit poisons its shard, and a failed shard poisons the merge.** A shard
that raises does not write a partial ledger and does not exit 0. The merge takes
the union of shard ledgers **only if every shard exited 0** and the union's key
set equals the 507 expected keys exactly — not a superset, not a subset.
**Partial results never silently merge, and a partial ledger is never scored.**
Shards are waited on **per PID**, never by a bare `wait`, so a failed shard
cannot be lost behind a successful one.

### 5.2 What every fit row records

`cutoff` (ISO date) · `seed` (20260611) · `config_sha256` (of
`epl/config_frozen.json`) · `realised_config_sha256` (of the serialised
`frozen_wcmodel_config()`) · `n_training_matches` · `n_teams` ·
`wall_seconds` · `match_ids` · `probs` (8 dp) · `cold_start_teams` ·
`provisional_teams` · `anchor_spec` · `warnings` · `unpriceable` ·
`health` · `harness_sha256` · `archive_rows` and `archive_sha256` (which archive
this fit stood on) · `blas_threads` · `shard_id`.

`shard_id` and the clock fields are **recorded but excluded from the canonical
digest** (§5.4): the environment a row was produced in belongs on the record, and
it must not be able to change a number.

### 5.3 The canary

`epl.walkforward.point_in_time_canary` is run once as a precondition, at its
default cutoff, and its full dict is written into the run artifact. `PASS: false`
is `CanaryFailed` and the run does not start. It is a precondition and not a
result: it is the check that the direction-of-bias risk in §1.3(b) has not
materialised.

### 5.4 Resumability, and what "byte-identical" means here

The runner is **resumable per fit**, keyed by
`cutoff|seed|config_sha256`. A key already in the ledger is skipped — not
re-run, not re-scored, not appended twice.

**A resumed run must produce the same result as an uninterrupted one, and the
demand is made on the canonical form rather than on the raw file**, because a
row records its own wall clock and two runs will never agree on that. Pre-stated
now, before any row exists:

* **Volatile fields**, excluded from the canonical form and from every digest:
  `wall_seconds`, `fit_seconds`, `seconds`, `shard_id`, `started_at`, `host`.
  This is `epl/simretro.py`'s `_VOLATILE` pattern, and the list is fixed here.
* **Canonical form**: rows sorted by `cutoff` then by key, volatile fields
  removed, serialised with `sort_keys=True` and no whitespace variation.
* **`run_digest`**: SHA-256 over the canonical form. **A resumed run's
  `run_digest` must equal an uninterrupted run's, byte for byte**, and the
  scored result written from it must be identical.
* The scoring loader refuses duplicate keys that disagree (`RowConflict`), so
  append order cannot change a number.

---

## 6. What this does not decide, and the hash commit that must follow

**Not decided here, by anything this experiment can produce:**

* **No model change.** No parameter, prior, likelihood, widening mechanism or
  strength moves. The frozen config is frozen.
* **No decay change.** `decay_half_life_days` stays 365. Cadence and decay are
  different knobs — recency of information versus length of memory — and
  `epl_improved.md` §5.3 is explicit that they moved in opposite directions:
  *"Making the model's information fresher is worth something measurable; making
  its memory shorter is not."* A freshness result is **not** evidence about
  decay, in either direction, and may not be cited as any.
* **Nothing about the shadow challenger.** `dc_1x2_recal` (A8) is untouched: no
  constant is refitted, no row is written to `reports/epl_recal_shadow.jsonl`,
  and both arms here are **raw** `dc` probabilities. A8's corpus digest is
  *read*, never rewritten.
* **Nothing about the league-table simulator.** Not the published arm, not D2,
  not D12, not the harness-v5 hash pair, not TRPS, not the nulls, not `check`.
* **Nothing about the matchboard or the issuance surface.**
  `ISSUANCE_SCHEMA_VERSION` stays `epl-issuance-5`.
* **Where the code and its output may live.** All harness code is under `epl/`.
  The run writes only to `data/epl/fit/` (its ledger, its shards, its
  `freshness.json`, and the existing feature cache under
  `paths.FIT_CACHE_DIR`) and to `reports/epl_freshness_result.md`. It does **not**
  write `src/`, `scripts/`, `site/`, `tools/`, `.github/`, the season ledger,
  `epl/season/points_adjustments.jsonl`, `data/epl/sim/retro_r1.jsonl`,
  `reports/matchboard_scorecard.jsonl`, `reports/epl_recal_shadow.jsonl`, or the
  pinned corpus itself — `walkforward_predictions.parquet` is **read-only** to
  this experiment, and rewriting it would break A8's digest as well as this one.

**The harness hash commit.** This commit adds this document and a dated
cross-reference in the amendment ledger. **Nothing else. The harness does not
exist.** Following the 07b5871 pattern, and adapted to the fact that this
preregistration precedes its code:

1. The harness is written and audited.
2. **A follow-up commit adds a hash table to this document** — file, line count
   and SHA-256 for every harness file — and a schema identifier, carrying
   07b5871's own sentence with "either" widened to "any": *if any hash differs at
   the time the run is executed, it is not the run this document preregisters.*
3. **Only then does the first fit run.** Not one fit before that commit exists.
4. Any change to a hashed file after that commit requires an amendment in
   `reports/epl_sim_amendments.md` **before** the change, in that file's format
   (observation → ruling → rationale → what is pre-stated), with the hashes
   reissued alongside it.

**Cost, so the budget cannot become a reason to change the design later.** 507
matchday fits plus 20 control fits = **527 fits**. At the preregistered walk's
realised rate (212 fits in 31 minutes, ≈ 8.8 s/fit with the fast panel and a warm
feature cache) that is **≈ 77 minutes**; at the measured cold single-fit cost of
**57.24 s** (`data/epl/fit/single_fit.json`, cutoff 2025-01-25, 4,019 training
matches, `cache_hit: false`) it is **≈ 8.4 hours**. The run may be sharded by fit
date under §5.1's merge rule. **It may not be thinned.** Dropping dates, seasons
or strata to fit a clock is an amendment, not an optimisation.

---

## 7. What would invalidate this preregistration

* **The corpus digest differs** at run time, or its row count, season set or
  outcome counts differ.
* **`epl/config_frozen.json` differs**, or the realised seed is not 20260611.
* **A fit runs before the harness-hash commit of §6 exists**, or a hashed file
  differs at run time without a prior amendment.
* **A fixture is dropped** from the 1,699 for any reason. Refusals are reported;
  deletions are amendments.
* **A stratum or a season is excluded** after the run starts.
* **A second seed, a second bootstrap seed, a second B, or a second definition of
  the blocks** is run and reported as if it were this experiment.
* **The threshold or the CI condition in §4 moves** after any delta exists.
* **A secondary decides anything** — including a staleness-conditional cadence
  assembled from §3.1.
* **The control's tolerance is widened** after a control row fails.
* **Any cross-sectional number from §1.4 is presented as the effect of freshness.**
* **The result is not published** after a run completes.

---

## 8. Standing disclaimers

* **Sampler noise is not model error.** Both are reported; only one of them
  shrinks with more fits, and neither shrinks with a better argument.
* The posterior is mean-field ADVI at 1,000 draws. Its under-dispersion is a
  known, separately scheduled limitation and no "honest tails" language attaches
  to any number this experiment produces.
* **The estimand is a mean over 1,699 correlated fixtures in 203 blocks.** The
  interval is a percentile block bootstrap, not an exact test, and it inherits
  every assumption that resampling whole ISO weeks makes.
* **Six seasons, one league, one model, one configuration.** Nothing here
  generalises to another league, another model, or another decay setting, and
  nothing may be quoted as if it does.
* Every RPS in this experiment scores a **1X2 match forecast**. No table
  position, no threshold, and no consequence-ranked quantity appears anywhere in
  it.

---

*Preregistered 2026-08-26, before any line of the freshness harness existed. The
corpus digest, the schedule counts, the twenty control dates and every figure in
§0 and §1.4 were computed from the pinned artifacts on that date and are
reproducible from the recipes given beside them. The harness hashes that make
"the design was fixed first" checkable for the run itself arrive in the follow-up
commit named in §6, and no fit runs before it.*

---

## §6 step 2 — the harness-hash freeze (2026-08-26)

The harness named in §6 now exists and has passed the adversarial audit that §6
step 1 requires before this note may be written: seven seeded defects each went
red under the file's own tests (poison ignored by the merge; a torn tail
believed on resume; a shard predicate off by one; openings leaking into the
matchday schedule; the bootstrap seed drifting; a merge without this note; the
control tolerance widened), the pairing and leakage probes were caught by their
named refusals (`ScoreMismatch`, `CorpusDigestMismatch`, `MergeIncomplete`,
`RowConflict`, `CutoffLeak` — with the typed poison row on the ledger), the
§5.3 canary and a three-date §3.2 control were re-run and reproduced the
published values exactly (max |Δp| before the cutoff **0.0** against a positive
control of **0.811805376021185**; control max |Δp| **0.0** at the corpus's 8
decimals), and §0.1's claim was re-verified against
`data/epl/fit/walkforward_ledger.jsonl`: the corpus-derived block openings
equal the walk's own cutoffs for all 212 blocks. These are the bytes:

| File | Lines | SHA-256 |
|---|---:|---|
| `epl/freshsweep.py` | 1906 | `441e917b9821d919d08bb5c48377242f5028ed01d0ca1f7a77cf3d51d857745c` |
| `epl/tests/test_freshsweep.py` | 1351 | `cabdf81c2d8d2e09c85937f4d780a9ab4575569774a48230f461c3414efc8da0` |

Schema identifier: `epl-freshness-1`.

**The enumerated fit-point list is frozen with the harness.** The 507 matchday
fit points and their 1,699 fixtures, recomputed from the pinned corpus by
`fit_points` under the binding schedule counts of §0.1, serialised in cutoff
order as `json.dumps([{block, block_cutoff, cutoff, match_ids, season,
staleness_days}, …], sort_keys=True, separators=(",", ":"))`, hash to:

    fe6493bce3188c03c5eb3b9bfa0b0ad200ac3e3537202809b04901d69a018842

A run that fits any other set of points is not this experiment, and the digest
is reproducible from the pinned corpus alone.

Verify with:

    shasum -a 256 epl/freshsweep.py epl/tests/test_freshsweep.py

**If any hash differs at the time the run is executed, it is not the run this
document preregisters.** Any change to a hashed file after this commit requires
an amendment in `reports/epl_sim_amendments.md` **before** the change, with the
hashes reissued alongside it (§6 step 4). §6 step 3 now applies: only after
this commit does the first fit run.
