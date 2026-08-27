# Evidence-mass widening — preregistration of the provisional re-key experiment

**Written:** 2026-08-27 · **Branch:** `main` · **Corpus:** frozen, pinned below
**Queued by:** the owner-pinned standing queue ("Hull widening") and the design
record `docs/superpowers/specs/2026-08-25-evolving-model-design.md`, Part 5
hypothesis 1 ("key widening on effective evidence mass, not promotion
category") and its v2 ruling: *"co-priority-2 RESEARCH (effective-evidence
walk-forward + table retro) — NOT shipped this season without it."* This
document is that research, both legs, preregistered.
**Status when written:** **no harness exists.** There is no `epl/evwiden.py`,
no runner, no shard, no ledger, no result file, and not one fit under a
re-keyed predicate has been run. No paired delta for any fixture of this
experiment exists anywhere in this repository, and none can, because the code
that would compute one has not been written.

This document fixes the rule, its one frozen constant, the estimand, the
resampling, the secondaries, the two-gate adoption rule, the refusal semantics
and the scope **before** the harness that answers it. It follows
[`reports/epl_anchoring_prereg.md`](epl_anchoring_prereg.md) (1b52623), which
follows [`reports/epl_freshness_prereg.md`](epl_freshness_prereg.md) (5ba83e7),
which follows [`reports/epl_sim_prereg_retro.md`](epl_sim_prereg_retro.md)
(07b5871). Like both predecessors it precedes its code, so **the harness hashes
are frozen by a follow-up commit, after the harness is written and audited and
before any real fit is run** — §6 says exactly what that commit must contain.
Both predecessors ended protocol-deviant on the same clause pair (§6 ordered an
audit before the freeze, §7 forbade fits before the freeze, and a fitting
harness cannot be audited without fitting); this document carries the corrected
clause they both asked for: **pre-freeze audit runs are permitted on synthetic
corpora only, are enumerated in the freeze commit, and may not enter any
estimand. Not one fit on the real archive precedes the freeze commit.** The
widening predicate is arithmetic and the mix is deterministic, so this harness
— unlike a market-window or matchday-schedule harness — genuinely can be
audited end to end on synthetic data, and the strong form of the guarantee is
therefore held rather than merely wished for.

Every number below was computed on 2026-08-27 from the pinned artifacts by the
recipes given beside them, before this document was committed and before any
harness code was written. Where a number from the design record was
re-derived, the re-derivation is stated; where a motivating number **cannot**
be independently re-derived from committed artifacts, that is stated too
(§1.2 — the reader should not skip it).

---

## 0. What is pinned

### 0.1 The corpus, the archive, and the configuration

| | |
|---|---|
| Corpus | `data/epl/fit/walkforward_predictions.parquet` |
| SHA-256 | `f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a` |
| Rows | **2,280** — 6 seasons × 380; seasons 2019/20 … 2024/25; blocks `(season, ISO week)` **212** |
| Outcome counts (`y` = 0/1/2) | 993 / 525 / 762 — adopted from `epl/recalfit.py:91-98` (A8), as both predecessors adopt them |
| Walk-forward ledger | `data/epl/fit/walkforward_ledger.jsonl`, SHA-256 `869a558ce7f84ef0f4a4ebdd8f781a4a72213fd5946b4e7088d716d99e82ba9e` — 212 rows, one per block opening, each carrying `provisional_teams` and `cold_start_teams` **as the published fits actually computed them** |
| Archive | `data/epl/matches.parquet`, SHA-256 `323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf` — **4,560** matches, 12 seasons 2014/15 … 2025/26, 380 per season |
| Frozen config | `epl/config_frozen.json`, SHA-256 `9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc` |
| Realised config | `epl.freeze.frozen_wcmodel_config()` — `seed` **20260611**, `windows.decay_half_life_days` **365**, `model.widening` `{mechanism: c, strength: 0.5}`, `model.inference` `{backend: advi, draws: 1000, tune: 1000, advi_iters: 30000}` |
| Table-retro anchor | `data/epl/sim/retro_r1.jsonl` (**protected, read-only**) and `epl.simretro`'s public constants: `SEASONS` (7, 2019/20 … **2025/26**), `COMPARISON_CUTOFFS` (MW0/MW3/MW6/MW10/MW19), `DEFAULT_N_SIMS` **20,000**, `SEED` **20260611** |

Verify with:

```
shasum -a 256 data/epl/fit/walkforward_predictions.parquet \
              data/epl/fit/walkforward_ledger.jsonl \
              data/epl/matches.parquet epl/config_frozen.json
```

The corpus is read-only to this experiment; three standing preregistrations
now check its digest (`epl/recalfit.py`, `epl/freshsweep.py`,
`epl/mktprior.py`). The archive digest is pinned here because — unlike in
the freshness and anchoring experiments — the archive is an **input to the
predicate under test**, not only to the fits: the effective-evidence quantity
of §2.1 is a sum over its rows. A parquet whose bytes have moved is a
different predicate input, and `ArchiveDigestMismatch` (§5.1) refuses it.

### 0.2 The incumbent predicate, read from the code

Mechanism-(c) widening is a **predict-time** mix and nothing else. At predict
time (`src/wcmodel/model/draw_api.py`, `production_grid` → `finalize_grid`),
a fixture is widened iff either club is in `posterior.provisional_teams`, by
one call to `inflate_predictive(grid, is_provisional=True, strength=0.5)` —
the mean-preserving-in-expected-goals mix toward the exponentially-tilted
max-entropy product grid (`src/wcmodel/model/widening.py:109-183`). Under
mechanism (c) the likelihood weight is untouched: `likelihood_weight` copies
`d.weight` and modifies it only for mechanism "a" (`widening.py:48-62`). **The
fitted posterior is therefore identical for any provisional set**, which is
the fact the whole design below stands on.

Membership is decided by `epl/dcfit.py:273-274`:

```
arm  = count_volatility_arm(store, cutoff, d.teams, config=cfg)
prov = set(arm.loc[arm["volatility_flag"] | arm["few_games_flag"], "team"])
```

plus the cold-start union (`dcfit.py:139`: `ColdStartPosterior` sets
`provisional_teams = set(base.provisional_teams) | set(cold)`). And
`count_volatility_arm` (`src/wcmodel/model/volatility_diagnostic.py:104-113`)
keys on **raw** quantities only: `games` is the count of a club's prior Elo
rows, `few = games < 5`, and `volatility_flag = (not few) and (vol > 16.5)`
where `vol` is the sd of the last 10 rating deltas. **Nothing in the predicate
reads a decay weight.** The status is as-of-cutoff, per
`ASSUMPTIONS.md:356-360`, and this experiment keeps that semantics (§2.2).

`epl/fit.py:98-100` recorded the risk in advance: the 16.5-point volatility
threshold was derived from international deltas at K up to 40 and "at club
K=20 it may flag nobody, in which case mechanism-(c) widening is inert.
Reported, not tuned." `reports/epl_walkforward.md:370-384` then corrected the
"flags nobody" half at scale: over the 212 scored cutoffs, 39 cutoffs carried
a provisional club, 45 team-cutoff flags fired — **13 from the volatility arm**
(Aston Villa, Brighton, Leicester) and 32 from the few-games arm (the six
cold-start clubs). The volatility arm is live, and §2.2 rules accordingly.

### 0.3 Effective evidence — the quantity, defined once

For a club `t` and cutoff `C` (midnight):

```
e(t, C)  =  Σ  0.5 ** (age_days / 365)     over archive matches of t with date < C,
                                            age_days = (C − date) in whole days
```

This is **the fit's own likelihood weight**, not a new number:
`src/wcmodel/data/features.py:297` computes `decay_weight = 0.5 **
(age_days / half_life)` with `half_life = 365`, and
`src/wcmodel/model/panel.py:34-36` renames it to the panel's `weight` — the
weight every training match carries in the likelihood. `e(t, C)` is the summed
weight of the club's own matches: **how much decayed evidence about this club
the likelihood actually holds.** It is venue-blind, covers every archive row
(deliberately **not** restricted to `in_feature_window` — the likelihood is
not), is computed on the same played frame the fit trains on, and is
recomputed at every cutoff, so it drifts upward within a season as the club
plays. Units: match-equivalents at full weight.

### 0.4 The blindness, measured at the live opener and across the corpus

At the 2026/27 opener (cutoff 2026-08-21), recomputed from the pinned archive
and confirmed against `count_volatility_arm` run mechanically on the same
store and frozen config:

| club | raw archive matches | last played | `e` at cutoff | incumbent flags | widened? |
|---|---:|---|---:|---|---|
| coventry | 0 | — | 0.0000 | cold-start (0 archive rows) | **YES**, α = 0.5 |
| **hull** | **76** | **2017-05-21** | **0.0607** | games 76, vol 11.872 < 16.5 — **none** | **NO** |
| ipswich | 38 | 2025-05-25 | 12.5208 | games 38, vol 8.986 — none | NO (correctly) |

Hull carries **six hundredths of one match** of decayed evidence — 206× less
than Ipswich — and is treated as a known club because its 76 raw matches from
2014/15 and 2016/17 clear the raw-count arm. The published issuance surface
showed the symptom before the cause was named:
`reports/epl_sim_issuance_2026-08-21.md` §4 records Hull's E[points] sd at
**14.11** against 8.6–10.2 for every other club and a 5–95% band 46 points
wide, and its limitation 4 states: *"Hull's dispersion is unexplained, not
excused… nothing has tested whether that width is correct."* And
`reports/epl_matchboard_2026_27_2026-08-21_derived.md` records **"38 of the
380 fixtures carried provisional widening"** — Coventry's 38 exactly; Hull's
38 got none.

Across the pinned corpus, recomputed today (4,240 club-cutoff cells = 20
season clubs × 212 cutoffs; widening status from the ledger's own
`provisional_teams`):

| quantity | value |
|---|---|
| `e` per cell: min / p1 / p5 / median / max | 0.00 / 5.70 / 18.76 / 51.97 / 60.21 |
| cells with `e < 3` | **25 — every one already widened** (cold-start clubs) |
| cells with `e < 1` | 13, all already widened |
| fixtures carrying incumbent widening | **46 of 2,280 (2.02%)** |

**No cell in the scoring window is Hull-shaped**: thin evidence without
widening does not occur there. Where it does occur is §1.1.

### 0.5 The archive's thin-history census, and the one true analogue

Promoted club-seasons 2015/16–2025/26: **33** (11 openers × 3), of which
**15 are cold-start** (zero archive rows — already widened at their opener)
and **18 are returning**. Effective evidence of every returning promoted club
at its own opener, recomputed:

| | | | |
|---|---|---|---|
| 2016/17 burnley 12.66 | 2016/17 hull 12.67 | 2017/18 newcastle 18.95 | 2019/20 aston_villa **4.74** |
| 2019/20 norwich **3.15** | 2020/21 fulham 11.77 | 2020/21 west_brom 11.09 | 2021/22 norwich 13.87 |
| 2021/22 watford 24.81 | 2022/23 bournemouth 12.59 | 2022/23 fulham 16.40 | 2023/24 burnley 25.71 |
| 2023/24 sheffield_united **9.84** | 2024/25 leicester 25.43 | 2024/25 southampton 25.32 | 2025/26 burnley 18.96 |
| 2025/26 leeds 11.17 | **2025/26 sunderland 0.172** | | |

**Exactly one historical club-season matches the Hull pattern** (raw ≥ 5,
`e` < 1): Sunderland at the 2025/26 opener — 114 raw matches, last played
2017-05-21, `e` = 0.172. Verified mechanically today: `count_volatility_arm`
at 2025-08-15 returns games 114, recent_volatility 8.737, both flags False —
**not provisional, zero widening**, the Hull configuration one season early.
2025/26 is outside the walk-forward corpus (excluded by `epl/windows.py` for
odds-coverage bias, a reason that does not bear on this market-free question)
and **inside** `epl.simretro.SEASONS`, where `allow_excluded=True` is passed
explicitly and stated in the module docstring. **The table-retro can see the
one true analogue; the match-level walk-forward cannot.** That asymmetry
shapes the whole design and is confronted in §1.4 rather than discovered by
the run.

---

## 1. The question, and the honest motivation

### 1.1 The finding

The predicate that decides predict-time widening is keyed on raw match count
and rating-delta volatility and is blind to the likelihood's own decay
weighting — so a returning club with a decade-old top-flight spell (Hull,
`e` = 0.0607) is treated as a well-known club while a true debutant
(Coventry, `e` = 0) is widened at α = 0.5. The candidate fix, as the design
record states it: **key widening on effective evidence mass, not promotion
category.** The quantity is already computed by every fit (§0.3); nothing
reads it for widening.

### 1.2 The motivating counterfactual is an observation, not evidence — ruled

The number that elevated this work: counterfactually adding Hull alone to the
provisional set of the 2026-08-25 issuance — identical particles, streams,
seed, strength, ranker — moves Hull's relegation probability from **27.885%**
to about **15.9%** (the design record's v2 ruling: *"the Hull widening
counterfactual moves relegation 27.9%→15.9% — product-scale, not a patch"*);
the same counterfactual against the 2026-08-21 opener moved the recorded
**58.71%** by about six points. What could be verified today was verified:
the 2026-08-25 issuance's `output_dc_native.json` records `relegated
p = 0.27885` and its `fit.json` records `provisional_teams: ["coventry"]`;
the 58.71% is committed at `reports/epl_sim_issuance_2026-08-21.md` §4.

Three things are ruled about this number, here, before any harness exists:

1. **It is a motivating observation outside the evidence base.** It was
   computed on the live 2026/27 season — the very object a verdict would
   change. It is not the estimand, not a secondary, not an input to either
   gate, and the harness does not recompute it.
2. **It is a claim about forecast surgery, not accuracy.** Mean-preserving
   widening in expected goals does not preserve win probabilities or table
   position; moving a weak club's relegation probability by 12 points says the
   lever is product-scale, and says nothing about whether the moved number is
   better. The accuracy evidence is what this experiment exists to produce.
3. **Its provenance is weaker than this repository's standard, in two
   tiers.** The base sides are on this machine but gitignored
   (`git ls-files data/` returns nothing), so a reader of this repository
   cannot check the 27.885% today. The **treated** sides — the 15.9% and its
   opener twin — exist only as the design record's prose: the counterfactual
   run that produced them was never committed as an artifact anywhere, and
   this document could not re-derive them without re-running the
   counterfactual, which it declines to do (point 1). They are quoted with
   that limitation named, and the evidence contract of §6 exists so that no
   number this experiment itself produces shares it.

### 1.3 The counter-hypothesis, stated before the run

**Widening Hull may be double-counting, not repair.** Hull's posterior is
already diffuse (points sd 14.11 vs 8.6–10.2, §0.4) *because* its effective
evidence is 0.06 — the hierarchical prior is already doing the work the
widening would claim to do. The design's own assumptions file rules that the
tournament simulator never applies (c) in-sim precisely because "re-widening
per draw would double-count the parameter uncertainty already carried by the
draw" (`ASSUMPTIONS.md:465-472`). A club whose predictive is already wide may
need no second widening, and adding one would push an honest interval past
honest. §3.4 pre-states the diagnostic that could show this — per-club
points-interval coverage (`epl.simmetrics.interval_coverage`, cov50/cov90)
for the treated clubs, both arms — **with its reading direction fixed now**:
if the control arm's coverage for treated clubs already sits at or above
nominal and the treatment pushes it further above, that is evidence *for*
double-counting and *against* this rule, and the result document must say so
in those words. No sign is assumed.

### 1.4 The power problem, computed before the design was chosen

The evidence-mass rule at any threshold near Hull's own 0.06 is **inert on
the pinned corpus**. Recomputed today, per candidate threshold `e*`, with
"thin" meaning a fixture whose thinner side has `e < e*` and "treated" the
thin fixtures the incumbent predicate does not already widen:

| `e*` | thin fixtures | already widened (delta ≡ 0) | **treated** | blocks holding a thin fixture |
|---:|---:|---:|---:|---:|
| 1 | 12 | 12 | **0** | 12 |
| 3 | 24 | 24 | **0** | 24 |
| 5 | 39 | 32 | 7 | 34 |
| 8 | 66 | 33 | 33 | 50 |
| **10** | **85** | **33** | **52** | **62** |
| 12 | 110 | 33 | 77 | 78 |

A threshold small enough to be "the Hull rule alone" (`e* ≤ 3`) changes **zero
of 2,280 fixtures**: a walk-forward at such a threshold cannot pass and
cannot fail — it can only print 0.000000. And any threshold large enough to
move fixtures is no longer a rule about decade-stale returners only; it is a
rule about **thin evidence in general**, whose historical bite is mostly the
cold-start clubs' matchweek-5-to-11 tail (raw count ≥ 5 switches the
few-games arm off while `e` is still single-digit) plus three genuinely thin
returning club-seasons. This document therefore preregisters the **general
rule** — thin evidence ⇒ widen, of which Hull is the extreme member — tests
it at match level where it has support, and tests the extreme member itself
only where the archive holds its one analogue: the table-retro's 2025/26
Sunderland cells (§3). Stated bluntly so the run cannot discover it: **the
match-level result, whatever it is, is evidence about the rule family, not
about Hull specifically.**

### 1.5 Why this is not the dead break-widening experiment

The design record's graves clause warns that "the ask must not re-run a dead
experiment under new vocabulary," and the nearest grave is I2 season-break
widening — closed at `reports/epl_v3_result.md` (peak −0.000058 mean RPS,
1.5× the 0.000038 optimiser noise, 0.8% of headroom; "the question is now
closed"). Three structural differences, stated for the reader who should ask:

* **Different trigger.** I2's trigger was a clock — matches since a squad
  break — that fires for *every* club *every* August and decays over weeks.
  This trigger is a fixed property of a club's whole archive history that
  fires for almost nobody: 51 club-cutoff cells across six seasons (§2.2),
  concentrated on nine club-seasons, zero on established clubs.
* **Different mechanism composition.** I2 stacked a *second, new* strength on
  top of the incumbent widening via `combine_widening`. This experiment adds
  **no strength and no new mix**: a treated fixture receives exactly the one
  incumbent mix at the frozen α = 0.5 — the identical treatment Coventry's 38
  fixtures already receive — through the identical code path.
* **Different question.** I2 asked "does a club get temporarily harder to
  predict after a break?" This asks "is the predicate that decides who counts
  as low-information keyed on the wrong quantity?" — a claim about membership,
  not about a new uncertainty source.

What is honestly shared with I2 is the noise floor, and §4 inherits its
lesson: the effect is measured against pre-stated noise scales, and a result
inside them is a miss however suggestive the sign.

---

## 2. The rule and the estimand

### 2.1 The rule, exactly

> **A club is provisional at cutoff `C` iff the incumbent predicate flags it
> OR `e(club, C) < e*`, with `e* = 10.0` frozen and `α = 0.5` unchanged.**

```
provisional′(C) = provisional_incumbent(C) ∪ { t : e(t, C) < 10.0 }
```

Everything downstream is the incumbent machinery, untouched: the per-fixture
predicate (either club provisional), the single mix at strength 0.5, the
per-fixture Bernoulli branch in the simulator (D12), the as-of-cutoff
semantics. The fitted posterior is bit-identical between arms (§0.2), so the
treatment is a pure predict-time re-key.

**ADD, not REPLACE — ruled, with the measurement that rules it.** A
replacement rule (`provisional = thin-evidence only`) would *remove* widening
from the volatility arm's clubs — Aston Villa (`e` 31.3–33.5), Leicester
(48.4–49.6), Brighton (51.0–57.5), all data-rich — stripping 22 fixtures of
widening at `e* = 3` (34 at `e* = 1`) and making the model **more** confident
on the historical corpus, the opposite of the motivating direction, while
silently retiring an arm that is live on 13 team-cutoff flags (§0.2). The
few-games arm is likewise kept: at raw counts 1–4 it fires before the
evidence rule adds anything, and removing it would change cold-start
semantics this experiment has no business touching. The evidence rule adds;
it removes nothing.

**Binary, not continuous — ruled.** A continuous `α(e)` touches every fixture
and would need a per-fixture strength. The machinery exists
(`epl/improve.py:473-494` proves the exact `(1−s1)(1−s2)` composition;
`:688-710` is the sanctioned per-fixture override), but the shape is refused
here because it breaks three published identities for one experiment's
convenience: the envelope's scalar `widening_mode =
"per_fixture_bernoulli@alpha={g}"` (`epl/leaguesim.py:774-775`), compared
field-by-field by `simcli`'s provider-identity check and `simbundle`'s
provisional-set check (`epl/simbundle.py:730-735`); the `epl-particlebook-1`
schema's scalar `alpha` field (`epl/particles.py:201-204`); and the issuance
gate's marginal-parity criterion, whose 4σ headroom (worst cell 3.865σ of
14,225) rests on the per-fixture mixture identity `marginal = (1−α)·ḡ + α·q`
holding exactly per fixture. Under the binary ADD shape at the incumbent α,
every one of those identities is preserved without modification: a treated
fixture is mechanically indistinguishable from an incumbent provisional
fixture. A continuous shape is a different, larger experiment and may not be
presented as this one.

**`e* = 10.0`, frozen, and where it comes from.** Ten is not tuned and not
swept: it is `config/config.yaml`'s `elo.volatility_window: 10` — the
ten-match window this codebase already uses, twice, as its operational
definition of the informative recent past (the incumbent volatility arm reads
the last 10 rating deltas; the anchoring preregistration §2.1 fixed its
market window at M = 10 by the same citation). The reading: **a club is
evidence-thin when the likelihood's entire decayed knowledge of it weighs
less than ten fresh matches.** What the constant separates, on the pinned
archive: it catches every Hull-analogue with a 58× margin or more (0.06–0.17
against 10) and misses every continuously-present club by 5× (median cell
51.97). Its nearest decisions: **caught** — Sheffield United 2023/24 (9.84:
two archive seasons, the fresher ending 27 months before its opener);
**missed** — West Brom 2020/21 (11.09: four seasons, ending 28 months
before), Leeds 2025/26 (11.17: three seasons, ending 26 months before),
Ipswich 2026/27 (12.52: one season, three months old). That the
config-derived constant lands inside the archive's own gap between those two
groups (9.84 … 11.09) is a fact about the archive noticed **after** the
constant was chosen from the config, and it is disclosed as such; the grid's
neighbours 8 and 12 straddle the gap and are reported (§3.1).

**No parameter is selected anywhere in this experiment.** The grid
`e* ∈ {1, 3, 5, 8, 12}` exists to be *reported*, never selected from: every
grid point's estimand analogue is published as a secondary with zero decision
weight (§3.1). This is stricter than the prequential-selection precedent
(anchoring's LOSO) on purpose: with three biting grid points and a population
this small, in-fold selection is noise-chasing, and a frozen constant with
the full grid on the record is the honest version. The cost is equally
frozen: **if `e* = 10` misses and a neighbour's secondary looks better, that
neighbour is selection-on-outcome, may not be adopted, and a future
preregistration that chooses it must say its choice was informed by these
numbers and carries exploratory standing only.**

### 2.2 The frozen membership

At `e* = 10` on the pinned corpus: **51 newly-flagged club-cutoff cells** (a
cell is any of the 4,240 of §0.4 with `e < 10` and no incumbent flag in the
ledger; **47 of the 51 sit in blocks where the flagged club itself plays**,
and those 47 are the flags that reach a fixture). They concentrate on nine
club-seasons — three returning-thin (aston_villa 2019/20, `e` 4.74 at the
opener; norwich 2019/20, 3.15; sheffield_united 2023/24, 9.84) and six
cold-start tails (sheffield_united 2019/20, leeds 2020/21, brentford 2021/22,
nottm_forest 2022/23, luton 2023/24, ipswich 2024/25 — each in the weeks
after its fifth raw match, while `e` is still below 10). For 2026/27 the rule
widens Coventry (already widened) and **Hull**, and does not widen Ipswich.
The status is **as-of-cutoff, recomputed at every cutoff** — a club leaves
the set as its evidence accumulates (a cold-start club crosses `e = 10`
around its eleventh match; Hull, entering at 0.06, would cross at the same
pace, around its own eleventh 2026/27 match) — preserving
`ASSUMPTIONS.md:356-360`'s refusal to widen a club forever. The freeze
commit (§6) pins the enumerated cells and fixtures by digest.

### 2.3 The arms and the estimand

**The arm's name is `dc_evwiden`.** Ruled here; grep confirms no existing use.
It names the mechanism (evidence-keyed widening), collides with no benchmark
column, and — unlike `dc_1x2_recal` — defines a full scoreline law, so it can
carry a table (§4.5).

* **Arm B — `dc_native`.** For each corpus fixture, the probabilities and RPS
  **already in the corpus** (`dc_home`, `dc_draw`, `dc_away`, `dc_rps`), at
  the 8 decimals they were written with. Not recomputed.
* **Arm A — `dc_evwiden`.** One fit at each of the **78 block openings whose
  block holds a thin fixture at any grid `e*`** (the `e* < 12` union; the
  primary's 62 are a subset), through the identical pipeline:
  `freeze.frozen_wcmodel_config()`, seed 20260611, `epl.fit.build_store`,
  `epl.anchor.Anchor` with `freeze.frozen_elo_config()`, `epl.dcfit.fit_epl`
  with `feature_cache_dir=paths.FIT_CACHE_DIR`, `fast_panel=True`. From each
  fitted posterior, **first** the incumbent-predicate predictions for **every
  fixture of the block** must equal the corpus's stored rows **exactly at
  their 8 decimals** (the identity control, §3.2 — 820 fixtures across the 78
  blocks); **then** `post.provisional_teams` is enlarged per §2.1 and the
  block's fixtures re-predicted, rounded by the same `round(v, 8)`. A fixture
  outside the treated set whose re-prediction differs from the corpus at 8
  decimals is `UntreatedMoved` and stops the run — the treatment must touch
  exactly the fixtures the rule names.
* **The delta** — `rps(A) − rps(B)` per fixture, RPS by `epl.score.rps` on
  the corpus's `y`. The harness recomputes Arm B's RPS from stored
  probabilities and refuses at > 1e-12 disagreement (`ScoreMismatch`).

> **THE ESTIMAND: the mean paired RPS delta, `dc_evwiden` minus `dc_native`,
> over the 85 thin fixtures of the pinned corpus at `e* = 10`. Negative means
> the re-keyed widening helps.**

* **The population is fixed at 85 and no fixture may be dropped.** Thin =
  min-side `e < 10` at the block cutoff. By season: 26 / 11 / 12 / 12 / 12 /
  12 (2019/20 … 2024/25). **33 of the 85 are already widened by the incumbent
  predicate and carry a delta of exactly 0.0 by construction** — stated now
  so the dilution cannot be discovered later: the estimand's sign equals the
  treated-subset (n = 52) mean's sign by arithmetic, at 52/85 of its size.
  The treated-subset mean is a pre-stated secondary, not the estimand,
  because "thin" is the rule and the rule includes fixtures it happens not to
  change.
* **The statistic** — the pooled mean over the 85 deltas.
* **The primary interval** — `epl.score.block_bootstrap_ci`
  (`epl/score.py:193`) on the 85 deltas, blocks = the corpus's own `block`
  labels (the **62** blocks holding a thin fixture), B = 10,000, percentile,
  `alpha = 0.05`, resampling seed **20260814**.
* **The season interval** — same function, same B, same seed, blocks = the
  **6 seasons**. Both are reported; §4.1 requires both. The season interval's
  job is to refuse a result carried by one season, and the risk is real and
  quantified now: 2019/20 holds 26 of the 85 thin fixtures and 21 of the 52
  treated ones.
* **The full-population secondary** — the mean over all 2,280 fixtures. Under
  ADD this is the estimand × 85/2280 **as an arithmetic identity** (untreated
  deltas are exactly zero), printed as context, never a gate.

**No power claim is made in advance.** The paired SD of treated deltas is
unknown until the fits exist. The realised SD, SE and the MDE at 80% power
are reported **with** the result; no threshold in §4 moves in response.

### 2.4 The compute budget, stated so it cannot later become a reason to redesign

78 fits (identity control and every grid point ride the same fits; a `w`-style
per-arm refit does not exist here because the posterior is arm-invariant). At
the walk-forward's realised warm rate (≈ 8.8 s/fit) ≈ **12 minutes**; at the
measured cold rate (57.24 s, `data/epl/fit/single_fit.json`) ≈ **75
minutes**. The table leg (§3.3): 35 fits plus 70 runs of 20,000 simulated
seasons — bounded by ~2 hours. Shards run **sequentially** (the featpanel
`.tmp` rename race in the locked path crashes parallel shards; the fix is
held for lock-v11), with `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1`
pinned at the entry point before numpy import, `python -u`, launched from a
**nohup'd script file, never a stdin heredoc** (macOS spawn re-imports
`<stdin>` and kills the gate's parallel leg), waited **per PID**. A failed
fit poisons its shard and a failed shard poisons the merge (§5.1). The run
may not be thinned: dropping cutoffs, fixtures, cells or grid points to fit a
clock is an amendment, not an optimisation.

---

## 3. Secondaries, controls, and the table-retro leg

Everything in §3.1 and §3.4 is published with the result and **decides
nothing**. No secondary may adopt, block, or qualify an adoption. A stratum
or grid point that clears §4's bar while the estimand misses it licenses
nothing.

### 3.1 Reported, never deciding

* **The grid** `e* ∈ {1, 3, 5, 8, 12}`: each point's thin-population mean
  delta, treated count, and week-block CI, from the same 78 fits. At
  `e* ∈ {1, 3}` the delta is 0.000000 with a degenerate interval **by
  construction** (zero treated fixtures) — pre-stated here so an identically
  zero row cannot be presented as either a finding or a failure.
* **Strata of the 85**: by season (6); by club category of the thin side —
  *returning-thin* vs *cold-start tail* (2). Eight intervals; some will
  exclude zero by chance; none decides, and that is the correction.
* **The treated-subset mean** (n = 52), beside the estimand it determines.
* **Movement diagnostic**: mean and max |Δp| between arms over the 52 treated
  fixtures, printed beside the ADVI re-seed scale (per-match mean 0.0032, p99
  0.0139, max 0.0229) and the pooled re-seed shift (+0.000075) from
  `reports/epl_walkforward.md`, so "did the treatment move more than
  re-seeding does" is on the record whichever way the estimand lands.

### 3.2 The identity control — 820 fixtures, exact equality

Every fitted opening's incumbent-predicate predictions must reproduce the
corpus's own rows **exactly at their 8 decimals** — all **820** fixtures of
the 78 affected blocks, a strictly stronger control than the predecessors'
20-date samples because this experiment must refit these very cutoffs anyway.
The demand is exact for the reasons the predecessors proved: the seed does
not vary by cutoff, a fit is a pure function of `(cutoff, store, frozen
config)`, and the project gets bit equality from repeated `fit_epl` calls
(`point_in_time_canary`, `verify_fast_path_is_inert`). The fit's own
recomputed provisional set must equal the ledger's recorded
`provisional_teams` at that cutoff (`PredicateMismatch` otherwise) — the
control that the incumbent arm being re-keyed is the incumbent arm that
published. A mismatch anywhere is most likely archive drift and is a STOP
(`ControlMismatch`) either way; the control runs **first**, and not one
treated prediction is produced until it passes. Max and mean |Δp| are
reported even when zero.

### 3.3 The table-retro leg — the second gate's measurement

**Why it exists:** the queue binds it ("historical walk-forward + table retro
before adoption"), the product impact lives at table level, and the one
Hull-analogue (§0.5) is visible only here.

**Mechanics.** `epl/simretro.py` is protected, its `ARMS` tuple is closed,
and `ArchiveRunner._provider` raises on any other arm — so the table leg is a
**new** `epl/` module that reuses `epl.leaguesim` / `epl.particles` /
`epl.season` / `epl.table` / `epl.simmetrics` (all read-only imports) and
reproduces `simretro`'s schedule through `simretro`'s own public surface:
`SEASONS` × `COMPARISON_CUTOFFS` = **35 cells**, cutoffs from
`cutoff_schedule`, realised tables through `realised_positions` /
`realised_hash`, 20,000 simulated seasons per arm per cell, seed **20260611**.
`data/epl/sim/retro_r1.jsonl` is read-only and never appended; the leg writes
its own ledger. Per cell: **one fit** serves both arms (the posterior is
arm-invariant, §0.2); the control book carries the incumbent provisional set,
the treatment book the §2.1 union; identical particle draws and identical RNG
streams, so the arms are CRN-paired and the **only** divergence is the D12
per-fixture Bernoulli widening branch on treated fixtures. D2 stays
static-within-fit and D12 stays per-fixture — the two standing open owner
rulings this experiment explicitly does not touch.

**The treated cells, enumerated now** (computed today from the pinned archive
by the §0.3 recipe and `count_volatility_arm` at each scheduled cutoff;
predicate strict `<`, values at 2 dp): **16 of the 35 cells change** —
2019/20 MW0 (aston_villa 4.74, norwich 3.15), MW3 (7.47, 5.94), MW6 (9.997,
8.54, sheffield_united 5.68), MW10 (sheffield_united 9.16); 2020/21 MW6
(leeds 5.66); 2021/22 MW6 (brentford 6.52), MW10 (9.92); 2022/23 MW6
(nottm_forest 5.72); 2023/24 MW0 (sheffield_united 9.84), MW6 (luton 5.73),
MW10 (luton 9.23); 2024/25 MW6 (ipswich 6.52), MW10 (9.92); **2025/26 MW0
(sunderland 0.17), MW3 (3.05), MW6 (6.67)** — the Hull-analogue cells. The
other **19 cells are unchanged by construction, and the harness must prove
it**: an untouched cell whose treatment-arm table digest differs from its
control's is `TableIdentityBreak` and stops the run.

### 3.4 Table-side secondaries — reported, never deciding

Per-cell paired ΔTRPS and ΔwTRPS for all 35 cells, published in full; pooled
Δ per cutoff label; per-club points-interval coverage (cov50 / cov90,
`epl.simmetrics.interval_coverage`) for the treated clubs under both arms,
read as §1.3 pre-states; and the **Sunderland 2025/26 cells** (relegation
probability, points mean and 5–95 band, both arms) printed under the label
*"the one Hull-analogue — illustrative, no decision weight."* TRPS is proper
**for the displayed marginals only** (`epl/simmetrics.py` says so in its own
docstring): two forecasts with the same position matrix and different
correlation structure score identically, widening changes the joint too, and
no table metric here can see that. Disclosed, not solved.

---

## 4. The adoption rule

### 4.1 The rule

> **ADOPT the evidence-mass re-key (as a shadow arm, §4.5) if and only if ALL
> FOUR:**
>
> **(i) the point estimate of the estimand is `Δ ≤ −0.0010` RPS over the 85
> thin fixtures, and**
> **(ii) the 95% `(season, ISO week)` block bootstrap CI (62 blocks) excludes
> zero — its upper bound is strictly < 0, and**
> **(iii) the 95% season block bootstrap CI (6 blocks) also excludes zero,
> and**
> **(iv) the table gate holds: the pooled mean paired ΔTRPS (treatment −
> control, equal weights over the 35 cells) is ≤ +0.0002, AND it is not the
> case that the pooled ΔTRPS is > 0 with its 95% season-block CI (7 blocks)
> excluding zero.**
>
> **Otherwise `dc_native` stands unchanged, Hull's forecast included.**

All four are required and none is sufficient. (i)–(iii) are the benefit gate;
(iv) is the do-no-harm gate the queue binds.

### 4.2 Why `−0.0010` on the thin population, argued against precedent

The house bar for a **model change** is Δ ≤ −0.0010
(`reports/epl_improved.md` §5.2 — 45 challengers, all missed, best
−0.000065). Freshness argued its bar down to −0.00030 because a cadence
change is operational: zero new parameters, one pre-stated candidate, no
grid. This experiment shares both of those properties — zero fitted
parameters, one frozen constant, no selection — but it is **not**
operational: it changes the published probabilities themselves on the
fixtures it touches, i.e. the law, which is the thing the full bar protects.
The full bar applies, **on the preregistered population**.

And the population restriction is not a concession — it is the only honest
placement. A passing result (−0.0010 × 85/2280 = −0.000037 pooled) is
**smaller than the corpus-level re-seed shift (+0.000075)**: a pooled-corpus
bar would be unclearable by construction for any rule this targeted, and
pre-registering one would be pre-registering a guaranteed miss. Conversely
the thin-population bar is a real ask: −0.0010 over 85 fixtures of which 33
are structural zeros means the treated 52 must improve by ≥ 0.0016 on
average — a per-fixture demand 28 times the entire pooled peak effect of the
I2 lever (−0.000058, §1.5). The bar is committed here, before any delta
exists, and does not move — not for the realised SD, not for the MDE, not
for a suggestive sign.

### 4.3 The table gate's tolerance is invented, and says so

R1 has **no pass rule** — `reports/epl_sim_retro_v1_1.md` §10: *"Nothing, by
itself"* — so a table-level bar has no house precedent and one must be
invented for the queue's binding to be checkable. It is invented from R1's
own recorded scale, before any widened table exists: the retro's paired
dc-family TRPS differences that its report calls "two parts in a thousand" on
a TRPS of order 0.08 are ~2e-4, and the gate caps degradation at that scale —
**+0.0002 pooled** — plus the significance clause, so a small-but-resolvable
worsening fails and an unresolvable wiggle does not. A 7-block percentile
bootstrap has poor coverage and is not claimed to have good coverage; its job
is the narrow one both predecessors gave season blocks: to refuse a verdict
carried by one season. This paragraph is the disclosure that (iv)'s numbers
are choices, made blind, in a place where the house had none.

### 4.4 What happens on a miss, and what publishes either way

`dc_native` stands unchanged. **The result publishes either way** —
`reports/epl_widening_result.md` and the §6 evidence files are written
whatever the signs, including the two embarrassing cases pre-named: the
estimand positive (widening thin clubs *hurts*), and the estimand negative
with the table gate failing (better matches, worse tables — which the joint-
vs-marginal disclosure of §3.4 makes possible). There is no file drawer. A
miss is not re-litigated: not at a second seed, not at a neighbouring grid
point, not by REPLACE, not by a continuous α, not by dropping 2019/20, not by
the treated subset promoted to estimand, not by extending the corpus into
2025/26, not by a one-sided interval, not by a bar rewritten after the
number. Each appears in §7.

### 4.5 What adoption would and would not change

Adoption is **shadow-first and this season ships nothing**, per the design
record's own ruling ("NOT shipped this season without it" — and passing the
gates is necessary, not sufficient). On ADOPT, `dc_evwiden` becomes a shadow
arm in the A8/A12 pattern — own ledger, own arm-tagged schema, own verify,
scored beside `dc_native` at `epl/livecycle.py`'s challenger step, no
matchboard, no gate, no pass rule — with the one difference A8's objection
carves out: `dc_evwiden` defines a full scoreline law, so it **can** carry a
shadow table. The published arm, `ISSUANCE_SCHEMA_VERSION`, the matchboard
and every published surface stay exactly as they are. Switching the published
arm is a separate, later owner ruling with its own amendment — the next free
slot is **A13** — and this document does not pre-authorise it.

**The invalidation cascade is named now.** A8's frozen recalibration constant
carries the clause "any change to decay, **widening**, inference or
scoreline-model semantics invalidates `a` until it is revalidated"
(`reports/epl_recal_grounding.md`). Research-phase runs here change no shipped
semantics, so `a` stands throughout this experiment. If the re-key is ever
adopted into the **published** arm, that adoption invalidates `a` until refit
under A8's own schedule, marks the A12 availability arm's downstream ledger
rows as pre-change history, and lands batched into the next lock version if
any production wiring touches `src/` — none is needed for the shadow shape,
which reaches the predicate the way `epl/dcfit.py` reaches the anchor: an
explicit call sequence, never a patched import. Under the adopted per-matchday
live cadence, the predicate recomputes at every fit's own cutoff, same rule,
same constant.

**Who decides.** Adoption is an owner ruling, recorded as a dated entry in
[`reports/epl_sim_amendments.md`](epl_sim_amendments.md). No script, agent or
report may change any arm on the strength of these numbers.

---

## 5. Refusal semantics for the run

### 5.1 Typed refusals, by name

All derive from **`EvWidenError`**, caught by `main()`, printing `STOP: …`
with the type and offending key, exit **2** — the `RecalError` convention.

| type | fires when |
|---|---|
| `CorpusMissing` / `CorpusDigestMismatch` / `CorpusShapeMismatch` | the pinned parquet is absent / not `f31580073e…` / not 2,280 rows, 6 seasons, 212 blocks, `y` (993, 525, 762) |
| `ArchiveDigestMismatch` | `data/epl/matches.parquet` is not `323aa54af0…` or not 4,560 rows |
| `LedgerDigestMismatch` | `data/epl/fit/walkforward_ledger.jsonl` is not `869a558ce7…` or not 212 rows |
| `ConfigNotFrozen` | `epl/config_frozen.json` is not `9f2e086d…`, seed ≠ 20260611, or widening ≠ `{mechanism: c, strength: 0.5}` |
| `MembershipMismatch` | the recomputed thin/treated enumeration differs from the §6 frozen digests (85 / 52 / 51 / 78 and the byte-listed keys) |
| `PredicateMismatch` | a fit's own provisional set ≠ the ledger's recorded `provisional_teams` at that cutoff |
| `EvidenceLeak` | a match dated ≥ its cutoff contributes to any `e(t, C)` (§5.3's canary proves the code, not the claim) |
| `CutoffLeak` | a training frame holds a match dated ≥ its cutoff, or a fixture appears in the fit that prices it |
| `CanaryFailed` / `EvidenceCanaryFailed` | `point_in_time_canary` fails / either leg of the evidence canary fails (§5.3) |
| `ControlMismatch` | any of the 820 identity-control probabilities differs from the corpus at 8 dp (§3.2) |
| `UntreatedMoved` | an Arm-A fixture outside the treated set differs from the corpus at 8 dp |
| `TableIdentityBreak` | an untouched table cell's treatment digest differs from its control's (§3.3) |
| `FitFailed` / `UnpriceableFixture` / `ScoreMismatch` | as the predecessors define them, verbatim |
| `SchemaMismatch` / `RowConflict` | a ledger row lacks a required field / duplicate keys disagree on a non-volatile field |
| `ShardFailed` / `MergeIncomplete` | a shard exits non-zero or writes nothing / the merged key set is not exactly the pre-stated keys — not a superset, not a subset |

A failed fit poisons its shard, a failed shard poisons the merge, shards are
waited on per PID, and a partial ledger is never scored. The merge refuses
rows stamped `harness_frozen: false`, by name — the predecessors' back-dating
guard, kept.

### 5.2 Provenance and resumability

Every row records `cutoff` · `e_star` · `seed` · `config_sha256` ·
`archive_sha256` (the corrected module-level digest over
`match_id, date, fthg, ftag` — the freshness §6-step-4 lesson, adopted from
day one) · `ledger_sha256` · per-club `e` at 8 dp · incumbent and enlarged
provisional sets · `match_ids` · `probs` (8 dp) · `health` ·
`harness_sha256` · `harness_frozen` · `blas_threads` · `shard_id` · clocks.
Volatile fields (`wall_seconds`, `seconds`, `shard_id`, `started_at`, `host`)
are excluded from the canonical form; `run_digest` is SHA-256 over the
canonical form; a resumed run's digest must equal an uninterrupted run's byte
for byte; the loader refuses disagreeing duplicates. The runner is resumable
per fit, keyed `cutoff|seed|config_sha256`.

### 5.3 The canaries — synthetic-only before the freeze

* **Results canary.** `epl.walkforward.point_in_time_canary`, run once as a
  precondition on the real archive **after** the freeze; `PASS: false` stops
  the run.
* **Evidence canary**, two-legged, because the existing canary rewrites
  results and cannot see the predicate input. Negative leg: corrupt every
  archive row dated on/after a cutoff and demand every `e(t, C)` and both
  provisional sets bit-identical. Positive control: corrupt rows before the
  cutoff and demand `e` moves by > 1e-9. A canary that cannot fail is not a
  canary.
* **Identity canary.** An `e*` low enough to add nobody must yield
  `np.array_equal` with the corpus rows.
* **Direction canary.** Every treated grid must equal
  `inflate_predictive(base_grid, is_provisional=True, strength=0.5)` exactly,
  and carry strictly higher entropy than its base — the mechanism's own
  guarantee, checked rather than assumed.
* **Seeded defects.** The adversarial audit seeds each defect class of §5.1
  alone and demands red under the harness's own tests — **on synthetic
  corpora only**. Pre-freeze, no harness code touches the real archive, the
  real corpus, or the real ledger except to hash them; the freeze commit
  enumerates every pre-freeze run, and the merge would refuse their rows
  anyway.

---

## 6. What this does not decide, and the hash commit that must follow

**Not decided here, by anything this experiment can produce:** no change to
α (0.5), decay (365), `k_att`/`k_def`, D2 (static-within-fit), D12
(per-fixture Bernoulli), the volatility or few-games arms, the published arm,
`ISSUANCE_SCHEMA_VERSION`, the matchboard, A8's constant or ledger, A12's arm
or capture bounds, the freshness or anchoring verdicts, or the market-prior
question. No REPLACE variant and no continuous α is licensed. The lock chain
is untouched by design — all code lands in `epl/evwiden.py` and
`epl/tests/test_evwiden.py`; the run writes only `data/epl/fit/evwiden*`,
`data/epl/sim/evwiden*`, `reports/epl_widening_result.md` and the evidence
files below; `src/`, `scripts/`, `site/`, `tools/`, `config/`, `.github/`,
`epl/simretro.py`, `epl/simmetrics.py`, the season ledgers,
`epl/season/points_adjustments.jsonl`, `data/epl/sim/retro_r1.jsonl` and the
pinned corpus are not written. `PYTHONPATH=src scripts/oa_lock.py` must print
`LOCK VALID` after every commit this work produces — checked, not assumed.

**The evidence contract, regardless of outcome** (ultra-review lesson 1 —
the verdict's machine-readable basis is committed, not gitignored):

| file | contents |
|---|---|
| `reports/evidence/widening.json` | the verdict verbatim: estimand, all four gate values, both CIs, grid secondaries, strata, movement, coverage, power |
| `reports/evidence/widening_per_fixture.csv` | the 85 thin-fixture rows: key, season, block, cutoff, clubs, `e` both sides, treated flag, both arms' probabilities, `y`, both RPS, delta |
| `reports/evidence/widening_table_cells.csv` | 35 cells × both arms: TRPS, wTRPS, coverage, treated clubs, digests |
| `reports/evidence/widening_grid_means.csv` | every grid point's population, treated count, mean delta, CI |
| `reports/evidence/MANIFEST.sha256` | updated with the bulky local artifacts' digests and byte sizes |

**This commit adds this document. Nothing else — the harness does not
exist.** Unlike the two predecessors, no amendment-ledger cross-reference is
appended in the same commit: that file is append-only under standing
protection, its numbered entries mark changes to what a published surface or
frozen rule means, and a research preregistration that touches nothing
shipped binds by its own commit. If this experiment adopts, the adoption
ruling is the numbered entry. Then, in the predecessors' order with their
jointly-won correction:

1. The harness is written and audited — seeded defects and canaries on
   synthetic corpora only.
2. **A follow-up commit appends the hash table to this document** — file,
   line count, SHA-256 for every harness file, schema identifier
   `epl-evwiden-1` — plus the frozen membership digests: the 85 thin fixture
   keys, the 52 treated keys, the 51 newly-flagged club-cutoff cells (§2.2),
   the 78 fit openings, and the 16 treated / 19 untouched table cells, each
   serialised canonically and hashed, recomputed by the harness's own code
   from the pinned artifacts. It enumerates every pre-freeze synthetic run.
   *If any hash differs at the time the run is executed, it is not the run
   this document preregisters.*
3. **Only then does the first real fit run.**
4. Any change to a hashed file thereafter requires a dated note appended to
   this document **before** the change, with the hashes reissued.

---

## 7. What would invalidate this preregistration

* Any pinned digest of §0.1 differs at run time without a prior dated note.
* A real-archive fit runs before the §6 freeze commit, or a hashed file
  differs at run time without a prior note.
* `e*` moves off 10.0, any grid point is promoted to the estimand, or a
  REPLACE or continuous-α variant is reported as this experiment.
* A fixture is dropped from the 85, a cell from the 35, or a season from
  either leg after the run starts.
* The treated-subset mean, a stratum, a grid point, or any secondary decides
  anything.
* A second seed, bootstrap seed, B, or block definition is reported as this
  experiment.
* Any threshold or CI condition in §4 moves after any delta exists.
* The identity control's tolerance is widened after a mismatch, anywhere.
* The 27.9→15.9 counterfactual, or any live-2026/27 quantity, enters any gate.
* The result is not published, or publishes without the §6 evidence files.

---

## 8. Standing disclaimers

* **Small population, pre-picked.** 85 fixtures — 52 carrying the treatment —
  in 62 blocks, selected by a rule that targets exactly where the effect
  should be largest. The estimand answers only the question asked: the value
  of the re-key **on the fixtures the re-key touches**.
* The intervals are percentile block bootstraps over correlated fixtures —
  not moving-block, not exact tests; the 6- and 7-block season resamples have
  poor coverage and serve only to refuse single-season verdicts. One ADVI
  seed; mean-field under-dispersion is a known, separately scheduled
  limitation.
* **Sampler noise is not model error**, and on 85 fixtures the noise floor is
  proportionally higher than the corpus-level +0.000075 — both are reported;
  neither shrinks with a better argument.
* TRPS is proper for the displayed marginals only; the widening also changes
  the joint law, and no metric in this experiment sees that.
* The match-level result is evidence about the rule family, not about Hull:
  the Hull configuration itself has zero support in the scoring window and
  one analogue in the table leg, and nothing here may be quoted as "the Hull
  fix was validated" — or refuted — at match level.
* Six-to-seven seasons, one league, one model, one configuration, one frozen
  constant. Nothing generalises beyond them and nothing may be quoted as if
  it does.

---

*Preregistered 2026-08-27, before any line of the evidence-widening harness
existed. The archive census, the incumbent-predicate readings, the grid
membership table, the 51 newly-flagged cells, the 16 treated table cells and
every figure in §0–§3 were computed from the pinned artifacts on that date by
the recipes given beside them, including mechanical re-runs of
`count_volatility_arm` for Hull (games 76, vol 11.872, unflagged), Sunderland
at 2025-08-15 (games 114, vol 8.737, unflagged) and Ipswich (games 38, vol
8.986, unflagged), and the cold-start identification of Coventry (0 archive
rows). The harness hashes and membership digests that make "the design was
fixed first" checkable arrive in the §6 follow-up commit, and no real fit
runs before it.*
