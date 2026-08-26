# The market-prior experiment — result (2026-08-26)

**DC NATIVE STANDS.** The preregistered estimand — the mean paired RPS change
from rotating the fit's prior toward market-implied strength, at the
leave-one-season-out weight, over all 2,280 corpus fixtures — came out at
**−0.000193**, against a bar of −0.0010 with both intervals required to exclude
zero. Week-block CI **[−0.000831, +0.000432]**; season-block CI
**[−0.000838, +0.000836]**. All three legs miss. No arm ships.

The selection saturated, and §3.4's pre-ruled diagnostic ran: four of six folds
chose w = 1.0, the grid maximum. At full market direction the arm scored
0.20024 against native's 0.20003 — indistinguishable — while the same-timing
opening market itself scored 0.19457. The arm did not collapse onto the market
(correlation 0.956, mean probability gap 4.1pp): the prior pointed where the
market points, and the likelihood — 4,570 matches of results at a frozen prior
strength of k = 0.6 — pulled the posterior back to what results say. Mean
probability movement was 0.88pp against a seed-replica floor of 0.32pp. The
mechanism the preregistration permitted is too gentle for the information it
carries; the data swamps the prior.

Read together with the design's grounding, the honest chain is now complete:
the output blend reaches the market's accuracy but saturates at w = 1 and
defines no scoreline law — publishing it would be publishing the market; the
input rotation defines a full scoreline law but cannot move the posterior at
frozen k. The +0.0050 opening-odds prize is real and remains unclaimed. What
would claim it is a stronger coupling — a swept prior strength, or odds
entering the likelihood itself — and every such path re-opens settled
preregistrations (k = 0.6 among them) or builds new model machinery. That is a
future preregistration's decision, recorded here as the open door it is,
walked through by nobody today.

The run's own integrity: sanity control 20 dates / 681 probabilities at exact
8-decimal parity; both leakage canaries PASS with live positive controls
(results canary 0.81, odds canary 4.98, zero vacuous legs); harness freeze
verified in-run; 1,060 fits, four shards, key set exact; the featpanel race of
the first launch answered operationally by sequential sharding, with the
concurrency fix queued for the next lock version. Machine-readable verdict:
data/epl/fit/anchoring.json; the arm's 2,280 predictions retained at
data/epl/fit/dc_market_prior_predictions.parquet (sha da685cf4…) for any future
comparison. Per §5, nothing here compares any arm to any market as a claim.

---

## Dated corrections and supplementary results (2026-08-26)

**Appended, not edited.** Everything above stands exactly as published; this
note corrects it by addition, in the house pattern. Four things are wrong or
missing above, and one recomputation was owed. Every number below is pure
arithmetic over the shard ledgers this run already wrote — **zero new fits** —
and all of it is reproducible from `reports/evidence/`.

### 1. The "leave-one-season-out" label is false

**The defect.** §2.4's selection scores each candidate `w` for season `s` on
the *other five seasons' forecasts*. Those forecasts are honest about season
`s`'s **fixtures** — no fold contains a match of the season it prices, and
`FoldLeak` enforces exactly that. But they are not independent of season `s`'s
**results**: a fit at a 2024/25 cutoff trains on everything before it, 2019/20
through 2023/24 included. So when the 2019/20 fold is scored on 2024/25
fixtures, it is scored on forecasts whose *training set contains 2019/20
results*. The information flows through training ancestry, not through the
fold split, and the fold split is the only thing that was guarded.

"Leave-one-season-out" names a guarantee this design does not provide. The
honest label is **in-fold weight selection with shared training ancestry**.
This is a **labelling defect, not an arithmetic one** — the reported estimand
is the number the stated procedure produces.

**The recomputation §2.4 should have specified.** A selector with no ancestry
problem at all: for season `s`, choose the `w` that minimises mean RPS over the
seasons **strictly before** `s`, ties to the smaller `w`. 2019/20 has no past,
so it takes `w = 0.00` — no market term — by construction rather than by
choice.

| Season | past-only `w` | published LOSO `w` |
|---|---:|---:|
| 2019/20 | **0.00** (no past) | 1.00 |
| 2020/21 | 1.00 | 0.50 |
| 2021/22 | 1.00 | 0.75 |
| 2022/23 | 1.00 | 1.00 |
| 2023/24 | 1.00 | 1.00 |
| 2024/25 | 1.00 | 1.00 |

**Past-only estimand: −0.000295**, n = 2,280, paired sd 0.014449; 95%
`(season, ISO week)` block CI **[−0.000944, +0.000329]** (212 blocks); 95%
season block CI **[−0.001171, +0.000854]** (6 blocks). Same B = 10,000, same
seed 20260814, same estimand definition.

**The verdict does not change, and it was checked rather than assumed.** The
bar is `Δ ≤ −0.0010` **and** both CIs excluding zero. The past-only point
estimate is *more* negative than the published one (−0.000295 against
−0.000193) and still misses the threshold by a factor of three, and both
intervals still contain zero. **DC NATIVE STANDS** under either selector. No
arm ships under either.

Per-season deltas at the past-only weights, for whoever wants the spread:
2019/20 **0.000000** (priced at `w = 0`, so Arm A *is* Arm B); 2020/21
−0.001698; 2021/22 −0.001294; 2022/23 **+0.002279**; 2023/24 −0.000639;
2024/25 −0.000420. The 2022/23 sign flip is the reason the pooled number is
small, and it was visible under the published selector too.

### 2. The saturation diagnostic ran on the wrong population

**The defect.** `_saturation_diagnostic` was handed `picked` — the
LOSO-selected rows — and then filtered them to `w = 1`. That is not "the arm at
full market direction"; it is "the arm at full market direction **in the four
seasons whose fold happened to select 1.0**", a 1,520-fixture subpopulation
chosen by the outcome being diagnosed. The ledger holds all 2,280 fixtures at
`w = 1`, and the diagnostic should have used them.

| | shipped (1,520) | **full population (2,280)** |
|---|---:|---:|
| arm mean RPS at `w = 1` | 0.20024 | **0.20158** |
| `dc_native` mean RPS | 0.20003 | **0.20194** |
| arm − native | **+0.00021** | **−0.00036** |
| same-timing opening market | 0.19457 | **0.19675** |
| correlation (arm, market) | 0.9564 | **0.9564** |
| mean abs probability gap | 4.06 pp | **4.04 pp** |
| collapsed onto market | no | **no** |

(The market column is over the 2,267 of 2,280 fixtures the opening panel
covers; 1,507 of 1,520 in the shipped column.)

**What changes and what does not.** The *sign flips*: on the population the
diagnostic should have used, the arm at `w = 1` is very slightly **better**
than native (−0.00036), not slightly worse (+0.00021). The paragraph above
that reads "the arm scored 0.20024 against native's 0.20003 — indistinguishable"
is arithmetically correct about the subpopulation it silently selected and
**should not be read as a statement about the arm**. "Indistinguishable"
survives either way: −0.00036 is a third of the adoption bar and well inside
the noise this run measured.

**What does not change at all** is the conclusion the diagnostic exists to
support. The arm has **not** collapsed onto the market on the full population
either — correlation 0.956, mean gap 4.04 pp — so §2.5's reading holds: at
`w = 1` the prior's direction is the market's and everything else is still the
model's.

### 3. The preregistered strata that were never published

§3.1 fixes **eleven intervals across three families**. Six seasons shipped in
`anchoring.json`; the other five did not exist anywhere. They do now, at the
published LOSO weights, same B and seed, `(season, ISO week)` blocks:

**By matchweek position** (§3.1, fixed before the run):

| Stratum | n | mean Δ | 95% CI |
|---|---:|---:|---|
| matchweeks 1–6 | 360 | −0.000575 | [−0.002214, +0.001092] |
| matchweeks 7–19 | 851 | +0.000146 | [−0.001147, +0.001423] |
| matchweeks 20–38 | 1,069 | −0.000333 | [−0.001008, +0.000395] |

**By promoted-club involvement:**

| Stratum | n | mean Δ | 95% CI |
|---|---:|---:|---|
| ≥ 1 promoted club | 648 | +0.000350 | [−0.001409, +0.002173] |
| no promoted club | 1,632 | −0.000408 | [−0.000880, +0.000062] |

**Every one of the five contains zero.** §3.1 pre-stated that some of eleven
would exclude zero by chance and that no multiplicity correction would be
applied "because none of them decides anything" — in the event, none of the
five new ones excludes zero at all, and §1.3's failed early-season /
promoted-club story is not rescued by them: the early-matchweek stratum is the
most negative of the three but its interval is the widest, and the
promoted-club stratum points the *wrong way*.

### 4. Movement, per weight, over the full population

The headline reported one movement number (0.88 pp) at the selected weights.
The grid's own dose-response was never shown. All 2,280 fixtures at each
fitted weight:

| `w` | mean abs prob shift | max | mean ΔRPS |
|---:|---:|---:|---:|
| 0.15 | 0.193 pp | 3.14 pp | −0.000107 |
| 0.30 | 0.370 pp | 6.12 pp | −0.000189 |
| 0.50 | 0.579 pp | 9.64 pp | −0.000266 |
| 0.75 | 0.795 pp | 13.30 pp | −0.000325 |
| 1.00 | 0.970 pp | 16.20 pp | −0.000361 |

Monotone in `w` in both movement and delta, against a seed-replica floor of
0.32 pp mean / 2.29 pp max (`reports/epl_walkforward.md`). The treatment is
real, ordered, and larger than seed noise at every weight from 0.30 up — and
still an order of magnitude short of the bar. That is the finding.

### 5. Three claims above that exceed their evidence

**(a) The causal prose.** The paragraph beginning "the prior pointed where the
market points, and the likelihood … pulled the posterior back to what results
say" narrates a mechanism this experiment did not isolate. It measured one
pipeline end to end; it did not decompose prior against likelihood, and it ran
no `k` sweep that could attribute the result to the prior's strength. What the
run supports, and all it supports:

> **The complete frozen pipeline at k = 0.6 moved forecasts but did not clear
> the RPS gate.**

The sentences above that assign the outcome to the likelihood "swamping" the
prior are **interpretation, not measurement**, and should be read as the
hypothesis they are. The open door §2.5 describes — a swept prior strength, or
odds in the likelihood — remains the way to test it.

**(b) "4,570 matches."** Wrong, and wrong in a way that flatters the argument.
There is no single likelihood size: the training set grows with the cutoff. The
run's actual `n_training_matches` runs from **1,900 to 4,167**, and the
preregistration's own pre-stated figure is **2,000–3,900 decay-weighted
matches** (§ the treatment-scale table). 4,570 is not any of these — it is
roughly the whole archive (4,560 rows), which is the pool the fits draw from,
not the likelihood at any cutoff.

**(c) The odds are archived snapshots, not proven as-known-then.** The
opening prices come from the football-data archive's `Avg`/`PS` opening
columns. Those are the archive's **final** record of the opening price. This
run verified that they are opening rather than closing columns, and that no
match contributed a price before it was played — it did **not**, and could
not from an archive, prove that the value stored today is byte-identical to
what a reader could have seen at the time. Archive revision, late
consolidation and source substitution are all unexcluded. The comparison in §2
above is therefore between the model and a **retrospectively archived opening
market**, and any future work that needs true as-known-then prices needs the
Tue+Fri live capture (A9's second pre-stated first use), not this archive.

### Reproducing all of it

`reports/evidence/anchoring_per_fixture.csv` (11,400 rows) and
`anchoring_fold_grids.csv` (both selectors) carry everything above.
Machine-readable: `reports/evidence/anchoring.json` is the shipped verdict
verbatim — it still carries the wrong-population saturation block and the
`method: "leave-one-season-out, in-fold"` label, both corrected here rather
than rewritten there.
