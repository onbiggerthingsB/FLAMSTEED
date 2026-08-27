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

---

## Repairs of 2026-08-27 — pre-freeze, pre-fit, on the cross-model review

**Standing.** This section is appended, not merged: every word above it stands
exactly as committed at f26b760, and this section supersedes named clauses of
it, clause by clause. Where a repair and the original text conflict, **the
repair governs**. Where this section is silent, the original governs.

**Why a repair is permitted at all.** The house lifecycle allows a
preregistration to be repaired only while it has decided nothing. That
condition holds and is checkable: **no freeze commit exists** (§6 step 2 has
not landed; `epl.evwiden.harness_freeze_status` reports the harness unfrozen),
**not one fit of this experiment has been run on the real archive**, no
`data/epl/fit/evwiden*` or `data/epl/sim/evwiden*` file exists, no delta
exists anywhere, and the harness's own guards refuse to produce one until the
freeze block is committed. Nothing below is informed by an outcome, because
there is no outcome. After the freeze commit and the first real fit, **R-B6**
applies and no further repair is possible.

**What prompted it.** An independent cross-model review (Codex `gpt-5.6-sol`,
ultra) of f26b760 returned UNSOUND with six blocking, six important and five
minor defects. Every one of the seventeen is ruled below, by its own
identifier, and every ruling is REPAIRED — none was contested, because each was
checkable against this repository and each check confirmed it. The harness
builder's four standing concerns are ruled in **R-H**.

---

### R-B1 — the arms are paired on the fitted object, not on a rounded projection

**Supersedes** §2.3's `Arm B` bullet, its `The delta` bullet, and §3.2's role.

The defect is real: Arm A came from a new fit while Arm B was an old rounded
1X2 projection, and mechanism (c) acts on the **full scoreline grid** before
that projection. Two grids can agree at eight decimals after projection and
respond differently to `inflate_predictive`, so "same draws, only membership
differs" was asserted about an object the control never bound.

**The repaired definition.** Both arms are computed from the SAME newly fitted
posterior and the SAME base grid, at every one of the 78 block openings:

* **Arm B — `dc_native`** — the block's fixtures predicted from the fitted
  posterior under **the fit's own recomputed incumbent provisional set**. This
  is the harness's predict pass 1. Nothing about it is read from the corpus.
* **Arm A — `dc_evwiden`** — the same block's fixtures predicted from **the
  same posterior object** under the §2.1 union. This is predict pass 2. No
  refit, no re-seed, no second sampler call: the two passes differ only in the
  set handed to `provisional_as`.
* **The delta** — `rps(Arm A) − rps(Arm B)` per fixture, `epl.score.rps` on the
  corpus's `y`, both arms from the same posterior.

**The corpus is demoted to an external identity control.** The stored
`dc_home` / `dc_draw` / `dc_away` / `dc_rps` no longer enter the estimand at
all. They remain the §3.2 control at full strength: all **820** fixtures of the
78 openings must equal Arm B at their eight decimals (`ControlMismatch`), and
each stored `dc_rps` must equal the RPS of its own stored probabilities to
1e-12 (`ScoreMismatch`). The control is now what its name always claimed — an
**external** check that the refit reproduces the published arm — rather than
one leg of the contrast.

**Pre-stated consequence, so it cannot be discovered later.** Because the
control demands eight-decimal equality and stops the run otherwise, the
repaired delta can differ from the superseded one by at most the eighth
decimal, per fixture. This repair is not expected to move the number; it moves
what the number is *guaranteed* to be. Both are published: the per-fixture
evidence file carries `delta` (the estimand's, Arm A minus Arm B) and
`delta_vs_corpus` (Arm A minus the stored row) side by side, so a reader can
confirm the equality rather than take it.

---

### R-B2 — the table gate is per-horizon; nothing decides on a cross-horizon average

**Supersedes** §4.1 clause (iv), §3.3's "pooled" language, §3.4's "pooled Δ per
cutoff label", and §4.3.

The defect is real and it is a violation of protected code's own stated law.
`epl/simretro.py:41` and `epl/simmetrics.py:44` both freeze **"Never averaged
across cutoffs"** — a forecast at the opener and one at matchweek 19 answer
different questions and their average describes neither. The superseded gate
(iv) made exactly that average deciding, and it diluted twice over: 19 of 35
cells are structural zeros, and all seven MW19 cells are among them, so harm at
the horizons where the treatment actually fires was averaged against cells
where it cannot.

**The census the repair is built on** (recomputed 2026-08-27 by the read-only
pass authorised in R-B5, from the pinned archive; it reproduces §3.3's
enumeration exactly):

| cutoff label | cells | treated cells |
|---|---:|---:|
| MW0 | 7 | 3 |
| MW3 | 7 | 2 |
| MW6 | 7 | **7** |
| MW10 | 7 | 4 |
| MW19 | 7 | **0** |

**The repaired gate (iv), in three parts, all required.**

> **(iv-a) The named-horizon gate — MW6.** The statistic is the **equal-weight
> mean over the seven MW6 cells of ΔTRPS = TRPS(treatment) − TRPS(control)**.
> It must be **≤ +0.0002**.
>
> **(iv-b) The per-horizon point gates.** At each of MW0, MW3 and MW10, the
> equal-weight mean of ΔTRPS **over that label's treated cells only** (3, 2 and
> 4 cells respectively) must be **≤ +0.0002**. No interval is computed at these
> labels and none is required; two cells do not carry one. MW19 holds zero
> treated cells, is a structural zero by construction, is reported as such, and
> decides nothing.
>
> **(iv-c) The significance-and-precision clause, at MW6 only.** Defined in
> R-B3.

**Why MW6 is the named horizon, and why naming it now is not selection.** It is
named before any fit exists, on two grounds neither of which is an outcome.
*Support:* MW6 is the only one of the five labels at which **every** cell is
treated, so it is the only horizon at which the do-no-harm question is asked
with no structural zero in the denominator. *Product:* the early-season table
forecast is where a thin-evidence club's dispersion is widest and where the
issuance surface that motivated this work is published (§0.4). The choice is
frozen here; §7 makes replacing it after any table run an invalidation.

**The tolerance, recalibrated to the new estimand.** +0.0002 came from R1's own
recorded scale — paired dc-family TRPS differences of "two parts in a thousand"
on a TRPS of order 0.08, i.e. ~2e-4 **per cell**. The superseded gate applied
that per-cell scale to an average over 35 cells of which 19 are exact zeros,
which permitted about **+0.0004375** of average degradation across the 16
changed cells. The repaired gates apply it to treated-cell means directly, so
it permits at most **+0.0002** where the treatment fires — **2.19× tighter**
than the clause it replaces. The number is unchanged; the estimand it governs
is the one it was calibrated for.

**Withdrawn.** The 35-cell pooled ΔTRPS and pooled ΔwTRPS are **withdrawn from
the published outputs entirely**, not demoted to secondaries. Publishing an
aggregate that protected code forbids as a verdict invites it to be quoted as
one. What publishes in their place: every cell's ΔTRPS and ΔwTRPS individually,
and the four treated-cell label means above.

**§4.3 is superseded and reissued.** The disclosure it made stands and grows:
R1 has no pass rule (`reports/epl_sim_retro_v1_1.md` §10: *"Nothing, by
itself"*), so both the tolerance and the significance construction are
**invented**, invented blind, in a place where the house had none. What is new
is that they are now invented for a **single named horizon** rather than for a
forbidden average, and that R-B3 makes the simulation error of that horizon a
published, deciding-capable quantity rather than an unstated one.

---

### R-B3 — the deciding table uncertainty is frozen, and simulation noise may only refuse

**Supersedes** §4.1's "95% season-block CI (7 blocks)" phrase and §3.3's silence
on Monte Carlo error.

The defect is real: unlike the two match CIs, the table CI named no function,
no B, no bootstrap seed, no quantile convention; `simretro.score_retro` cannot
supply one because it refuses cross-cutoff aggregation; and the standing
amendment **A2-N4** requires a TRPS Monte Carlo error that the document never
mentioned. A gate whose tolerance is the same order as the simulation's own
error is a gate that noise can decide.

**The interval, frozen in full.**

| | |
|---|---|
| statistic | the equal-weight mean of the seven MW6 per-cell ΔTRPS |
| function | `epl.score.block_bootstrap_ci` (`epl/score.py:193`), the same function both match legs use |
| deltas | the 7 MW6 cell deltas, in season order |
| block labels | the seven season strings `2019/20 … 2025/26`, one cell per block, so `n_blocks = 7` |
| B | **10,000** |
| alpha | **0.05** |
| resampling seed | **20260814** |
| quantile convention | `np.quantile(means, [alpha/2, 1 − alpha/2])` on the function's own pooled-mean resample, NumPy's default linear interpolation |

Clause (iv-c) fails if the MW6 mean is `> 0` **and** the interval's lower bound
is `> 0`. A seven-block percentile bootstrap has poor coverage, is not claimed
to have good coverage, and has the narrow job both predecessors gave season
blocks: to refuse a verdict carried by one season.

**The paired Monte Carlo error, frozen in full.** `epl/simmetrics.py` is
protected and its `trps_se_cluster` is a **single-arm** estimator; the quantity
this gate needs is the error of a **paired difference** under common random
numbers. It is defined here, to be implemented in the harness module, mirroring
the protected estimator's convention exactly:

* the run retains per-particle rank tallies, built from
  `SimRun.retained_rows.particle` and `.order` (plan v2 D20 already retains
  both), shaped `[n_particles, n_clubs, n_ranks]`;
* every particle must carry the same number of simulated seasons
  (`sims_per_particle_min == sims_per_particle_max`) — the equal-cluster
  assumption the protected estimator enforces. Unequal counts are the new
  refusal `TableMCImprecise`;
* `rng = np.random.default_rng(MC_SEED)`; for each of `MC_BOOT` replicates,
  `picked = rng.integers(0, n_particles, n_particles)`;
* **the same `picked` is applied to both arms' tallies** — this is the whole
  point: the arms share particles, share `(chunk, fixture)` RNG streams and
  differ only on the D12 branch at treated fixtures, so most of the simulation
  noise cancels in the difference and only a paired estimator sees what is
  left;
* each arm's resampled total is row-normalised and scored with
  `epl.simmetrics.trps(matrix, positions, spans=spans)` — the same call, with
  the same spans, the cell's point estimate uses;
* the cell's paired MC SE is the standard deviation (`ddof=1`) of the `MC_BOOT`
  differences.

**`MC_BOOT = 2,000` and `MC_SEED = 20260827`**, pre-stated here, before any
table run exists. A2-N4 leaves B and the resampling seed to "the amendment that
accompanies the first run to report the bootstrap SE, before that run"; this is
that document and this is that statement.

The MW6 mean's MC SE is `sqrt(Σ_c se_c²) / 7` over its seven cells — they are
independent runs at different seasons with different fits and different
streams, so their errors add in quadrature.

**The precision rule, one-directional.** Gate (iv) is **UNRESOLVED**, and
ADOPT is refused, if **either**

* `mc_se_mean > 0.25 × 0.0002 = 5e-5`, **or**
* `|mean_MW6 − 0.0002| < 2 × mc_se_mean` — the comparison to the tolerance
  falls inside the simulation's own error.

An UNRESOLVED gate blocks adoption; it can never grant one. Simulation noise is
therefore only ever able to *refuse*, which is the direction that cannot be
gamed. `n_sims` stays at **20,000**: the precision rule does **not** license a
larger run, because enlarging a preregistered constant after a number exists is
exactly what §7 forbids. An UNRESOLVED verdict publishes as UNRESOLVED, with
every number, under §4.4's no-file-drawer rule.

---

### R-B4 — a conformance oracle against protected code, and a defined substantive digest

**Supersedes** §3.3's "reproduces `simretro`'s schedule through `simretro`'s own
public surface" as a sufficiency claim, and §5.1's undefined "table digest".

The defect is real. Binding the *schedule* to protected code binds neither
`ArchiveRunner`'s semantics — verified adjustments, `config_read_once`,
particle-book construction, boundaries, chunking, refusal handling, ranker
checks, provenance — nor its call. The 19-untouched-cell control compares two
arms produced by the **same new code**, so any drift shared by both arms passes
it silently.

**The oracle, required before any treated table run.** The new runner must
reproduce protected `epl.simretro.ArchiveRunner`'s `dc_native` output at **all
thirty-five cells** — native parity, every cell, no sampling — before one
treated simulation is executed. A difference at any cell is
`TableIdentityBreak` and stops the leg. `data/epl/sim/retro_r1.jsonl` stays
read-only and is not the comparison object: the parity run is executed, not
read off the archive ledger.

**The substantive digest, defined.** SHA-256 over the canonical JSON
(`epl.leaguesim.canonical_json`) of, in this order:

1. the club list;
2. the scored position matrix at full stored precision;
3. the per-particle rank tallies;
4. the retained points, goal-difference and goals-for vectors;
5. the tie-block record — `block_start`, `block_span`, `resolution_code`;
6. the consequence weights and the boundary definition;
7. the realised-truth identity — `realised_hash`, the realised position vector
   and the realised points vector;
8. `effective_posterior_hash`, `n_sims`, `n_particles`, `seed`;
9. the provisional set actually carried by the book.

**Excluded by name:** the arm label, wall clocks, host, shard id, and any
free-text note. Those are the labels the digest must not bind; everything
substantive is bound.

**Both arms are labelled `dc_native` to `leaguesim`.** That is now the
document's rule and not a harness convenience: the provider *is*
`DCNativeProvider` in both arms — a `ParticleBook` may not wear another arm's
name — and what differs between them is the **book**, which is the treatment.
The experiment's own arm name `dc_evwiden` names the re-keyed book and is
recorded on the row. Because the label is shared, the arm field cannot differ
between the two runs of a cell, and the digests of an untouched cell are
comparable by construction.

**The two-sided cell identity is required** — see R-H(4).

**This oracle is not hypothetical.** At the time of this repair,
`epl/evwiden.py` calls `leaguesim.simulate` in its table runner with the
particle book in `state`'s argument position and no `seed` argument at all;
protected `epl/simretro.py:555` calls it as `simulate(arm, state, provider,
n_sims, seed, …)`. A 35-cell parity run against the protected runner catches
that on its first cell, and nothing else in the harness does — no test
exercises the real call, and no fit has run. That is precisely the class of
drift the oracle exists to catch, and it is recorded here rather than fixed
quietly.

---

### R-B5 — the pre-freeze read-only passes, authorised by name and date

**Supersedes** §5.3's sentence *"Pre-freeze, no harness code touches the real
archive, the real corpus, or the real ledger except to hash them"*.

The defect is real: §6 step 2 requires the membership digests to be
"recomputed by the harness's own code from the pinned artifacts", which cannot
be done by hashing them. As written, the document mandated its own deviation
before any harness work began.

**The superseding clause.** *Before the §6 freeze commit, no harness code
**fits** and no harness code **simulates**. Reading the pinned artifacts is
permitted and enumerated.*

**Authorised, retroactively and by name, on 2026-08-27** — every one read-only,
no `dcfit.fit_epl`, no `leaguesim.simulate`, nothing written inside the
repository:

1. `python -m epl.evwiden --membership` and `--plan` — read the pinned corpus,
   archive and ledger; compute §2.2's cells, §2.3's population, §3.3's table
   cells and the digests the freeze commit records.
2. `python -m epl.evwiden --canary --no-results-canary --dir <scratch>` —
   §5.3's evidence canary on the real archive, with the point-in-time store
   built in a `tempfile.TemporaryDirectory` and never under `paths.STORE_DIR`.
3. `pytest epl/tests/test_evwiden.py`, including the `@pinned` tests that
   re-derive the census, the grid table, the membership and the table cells.
4. One partial engine pass at the first opening (2019-08-09): construction,
   `fit_points`, the enlarged set, `assert_cutoff_clean` and
   `assert_point_in_time` — the whole of the fit path **except** the call to
   `dcfit.fit_epl`. No sampler ran; the shared point-in-time store was
   byte-identical afterwards.
5. `--freeze-block` itself, which reads the pinned artifacts to render §6's
   commit rather than have a human transcribe digests.
6. **This repair round's two exports**, run 2026-08-27 into the session
   scratchpad: the 85-fixture block-and-season structure used by R-I2's power
   simulation, and the 35-cell per-label census tabulated in R-B2. Both call
   only `membership` and `table_cells`; both fit nothing and simulate nothing;
   neither wrote inside the repository.

**The rule for any further pre-freeze pass.** It must be read-only; it may not
call `dcfit.fit_epl` or `leaguesim.simulate`, and may not build a store under
`paths.STORE_DIR`; it may write nothing under `data/`, `reports/` or anywhere
in the repository; and it must be **added to the freeze block's enumeration
before the freeze commit is made**. The freeze block's list stays binding and
must be complete — an unenumerated pre-freeze pass is a protocol deviation
whether or not it touched anything. `epl.evwiden.freeze_block`'s default
enumeration currently names four runs and must be extended to name all six
above before the freeze commit is generated.

---

### R-B6 — after the first real fit, a hashed file cannot be changed at all

**Supersedes** §6 step 4 in its entirety, and adds to §7.

The defect is real and it is the most dangerous of the six. "Any change to a
hashed file thereafter requires a dated note appended to this document before
the change, with the hashes reissued" was not limited to the pre-fit period,
and §7 invalidated only an *unnoted* hash difference. As written, an author who
had seen a real delta could append a note, alter deciding code, reissue the
hashes and remain nominally inside this preregistration. Disclosure after an
outcome does not restore blindness.

**The superseding clause, in two regimes.**

> **Before the first real fit.** A hashed file may change. The freeze block is
> regenerated by `--freeze-block` and re-committed, and the run that follows is
> the run this document preregisters. No note is required, because nothing has
> been observed.
>
> **After any real fit on the real archive exists** — whether or not it
> produced a delta, whether or not it was merged, whether or not anyone looked
> at it — **any change to any hashed file invalidates this preregistration.**
> No note, no dated appendix, no disclosure and no owner ruling restores it.
> The invalidated run **publishes**, with its numbers and with the reason it
> was invalidated, and a new preregistration begins in a new document with its
> own freeze.
>
> Notes appended to this document after results exist may correct **prose
> only** — a typo, a citation, a clarification of what was already meant. A
> note may not change a threshold, a population, a statistic, a seed, a digest,
> a gate, or one line of code this document hashes.

**§7 gains, and these are invalidations:** any change to a hashed file after
the first real fit, with or without a note; gate (iv) evaluated on any
cross-horizon average; the MW6 horizon replaced after any table run; the paired
MC error omitted or computed with different constants; the 35-cell parity
oracle skipped or sampled; and the estimand's delta computed against the corpus
rather than against the same-posterior incumbent pass.

---

### R-I1 — the realised configuration is pinned, not only the frozen file

**Supersedes** §0.1's configuration row and §5.1's `ConfigNotFrozen`.

The defect is real. `epl.freeze.frozen_wcmodel_config()` loads the **live**
`config/config.yaml` and overlays only the frozen EPL Elo block; the digest
check bound `epl/config_frozen.json`, the realised seed and the realised
widening block, and nothing else. The decay half-life — which *defines* `e` —
the volatility window from which `e* = 10.0` is taken, the likelihood and the
whole ADVI inference block all came from a file no check bound. Drift there
would change `e`, the posteriors, or reproducibility while the documented
refusal passed.

**The repaired pin.** `realised_config_sha256` is the SHA-256 of
`json.dumps(freeze.frozen_wcmodel_config(), sort_keys=True, default=str)`. Its
value, computed 2026-08-27 under the pinned frozen file, is

`78a51cd92c48838a57e3d6832b7661aad7a5b231425572214a067c2a35edbdcd`

and it is **pinned here**. `ConfigNotFrozen` now fires on four conditions, not
three: the frozen file's digest, the realised seed, the realised widening
block, and this realised digest. The §6 freeze commit records it beside the
membership digests. Every ledger row continues to carry both `config_sha256`
(the frozen file) and `realised_config_sha256`, so a reader can tell which
moved.

What this now binds, all of which §0.1 quoted and none of which the superseded
check held: `windows.decay_half_life_days = 365`, `elo.volatility_window = 10`,
`model.widening = {mechanism: c, strength: 0.5}`, `model.inference = {backend:
advi, draws: 1000, tune: 1000, advi_iters: 30000}`, and `seed = 20260611`.

---

### R-I2 — the power analysis, done, with the joint-gate MDE

**Supersedes** §2.3's *"No power claim is made in advance"* and §1.4's implicit
claim that a support census is a power analysis.

The defect is real: §1.4 counted where the rule *bites*, which is support, not
power, and the document then declined to say whether its own three conjunctive
match gates could jointly pass at any plausible effect. The bar demands a
treated-fixture mean of −0.0016346 (`0.0010 × 85/52`), and the repository's own
committed paired contrasts sit at variances where that is a stretch.

**The scenarios, frozen blind.** No delta of this experiment exists, so none of
these is informed by one.

| scenario | paired SD | source |
|---|---:|---|
| **A — freshness-scale** | **0.005262** | `reports/epl_freshness_result.json`'s own `sd` over its 1,699 paired deltas — same corpus, same model, a predict-time change of comparable reach |
| **B — anchoring-scale** | **0.014449** | `reports/epl_anchoring_result.md`'s past-only estimand, paired sd over 2,280 fixtures — a larger predict-time change |
| **C — mechanism-scale** | **0.036** | a deliberately pessimistic extrapolation, named as invented, argued below |

Scenario C is grounded rather than guessed. The anchoring contrast's paired SD
scales with the size of its treatment, and the ladder is committed in
`reports/evidence/anchoring_per_fixture.csv` (recomputed 2026-08-27):

| market weight `w` | 0.15 | 0.30 | 0.50 | 0.75 | 1.00 |
|---|---:|---:|---:|---:|---:|
| paired SD | 0.003025 | 0.005832 | 0.009181 | 0.012690 | 0.015479 |

The relation is close to linear in the treatment's size, and mixing a fitted
scoreline grid halfway toward a max-entropy product grid is a larger
perturbation of the 1X2 law than any point on that ladder. Scenario C at 0.036
sits about 2.3× beyond the largest committed point. It is an extrapolation and
it is labelled one; a power analysis that tests only optimistic variances is
not a power analysis.

**The method, frozen.** On the frozen structure — 85 fixtures, 52 treated, 62
week blocks, 6 seasons, by season 26 / 11 / 12 / 12 / 12 / 12 with treated
21 / 4 / 7 / 6 / 7 / 7 — inject a constant treated effect δ plus Gaussian noise
at SD `s`, at within-block correlations ρ ∈ {0, 0.5}, leaving untreated deltas
at exactly zero as the design makes them; then evaluate **all three deciding
match gates exactly as §4.1 states them**, using `epl.score.block_bootstrap_ci`
at B = 10,000, α = 0.05, seed 20260814. The bootstrap shortcut used for speed
was asserted equal to the real function to 1e-15 before any number was
reported, and the block counts it produces are 62 and 6. R = 2,000 replicates,
simulation seed 20260827.

**The MDE definition, frozen:** the injected treated effect at which **all
three deciding match gates pass with probability 0.80**. Reported on the
estimand's scale (treated effect × 52/85).

| scenario | ρ | power at the bar | joint MDE (estimand) | ratio to the −0.0010 bar | power at 2× the bar |
|---|---:|---:|---:|---:|---:|
| A freshness-scale | 0.0 | 0.461 | −0.001440 | 1.44× | 0.977 |
| A freshness-scale | 0.5 | 0.425 | −0.001553 | 1.55× | 0.944 |
| B anchoring-scale | 0.0 | 0.103 | −0.003738 | 3.74× | 0.326 |
| B anchoring-scale | 0.5 | 0.103 | −0.004160 | 4.16× | 0.274 |
| C mechanism-scale | 0.0 | 0.058 | −0.009200 | 9.20× | 0.083 |
| C mechanism-scale | 0.5 | 0.044 | −0.010635 | 10.63× | 0.081 |

**A structural fact, stated so no one reads the table as a defect in the
simulation.** Gate (i) is a threshold **at** the bar, not a test against zero,
so at a true effect exactly equal to the bar the probability of clearing it is
about one half whatever the variance is. **An 80%-power MDE equal to the bar is
unattainable by construction**, at any SD; the honest quantity is the ratio,
which is what the table reports. (This also corrects the review's
`MDE80 = 2.802·s/√52`, which is the two-sided-test-against-zero MDE and does
not describe gate (i). The direction of its conclusion survives the
correction.)

**The ruling. Nothing in §4 moves.** The bar stays −0.0010, the CIs stay, the
population stays 85, the constant stays 10.0. What changes is that the document
now says, before any delta exists:

> **This design is underpowered against effects near its own bar unless the
> realised paired SD comes in at or below the freshness scale.** At the
> anchoring scale a true treated effect of −0.0016 would be missed about nine
> times in ten. A MISS IS THEREFORE SUBSTANTIALLY UNINFORMATIVE: "no adoption"
> here means "not detected at this power", not "no effect", and the result
> document must say so in those words.

§4.4's refusal to re-litigate a miss is unchanged, and this is not a licence to
re-run at a second seed, a larger corpus or a lower bar. It is the reader's
warning, frozen in advance, so that the size of the null cannot be argued
about after it arrives.

**Required publication.** `reports/evidence/widening.json` carries a `power`
object holding these scenarios, the frozen structure, the MDE definition, R,
both seeds, the six rows above, and — after the run — the **realised** paired
SD of the treated deltas and the MDE recomputed at it. The realised numbers
decide nothing and no threshold moves in response; §2.3's sentence to that
effect stands.

---

### R-I3 — the bar is an invented thin-population threshold, and says so

**Supersedes** §4.2's sentence *"The full bar applies, **on the preregistered
population**."*

The defect is real in its claim of authority, though not in its disclosure:
§4.2 already published the 85/2280 arithmetic and the −0.000037 pooled figure.
What it did wrong was to present the numeral as the house bar **applied**,
when the house bar was set over a full evaluation window and this one is set
over 85 fixtures chosen to be where the effect is largest — a difference in
system-level materiality of about 26.8×.

**The repaired sentence.** *−0.0010 over the 85 thin fixtures is an **invented
thin-population threshold**. It takes its numeral from
`reports/epl_improved.md` §5.2's model-change bar; the numeral is borrowed, the
authority is not.* It is justified on four grounds, the fourth of which was
computed only in this repair section and is marked as such:

1. **Noise.** The corpus-level re-seed shift is +0.000075 and the per-match
   ADVI re-seed scale is mean 0.0032 / p99 0.0139 / max 0.0229
   (`reports/epl_walkforward.md`). A bar that a re-seed could clear is not a
   bar; −0.0016 per treated fixture is well outside that scale.
2. **Power.** R-I2's table. A materially lower bar would sit inside the noise
   of scenario B; a materially higher one is unreachable under every scenario.
   The bar is at the edge of what this population can resolve, which is where a
   preregistered bar belongs.
3. **Product.** The rule changes the published law on the fixtures it touches
   (§4.2), which is what the full model-change scale protects — this is not an
   operational change and the freshness discount to −0.00030 does not apply.
4. **System-level materiality**, and this is the concession: a passing result
   is **−0.000037 pooled over the corpus**, smaller in magnitude than the
   +0.000075 re-seed shift. **This experiment cannot demonstrate a
   corpus-level improvement and does not claim one.**

**Required disclosure, in the result document, in these words:** *"the rule's
corpus-level effect is below this model's own re-seed noise, and its value is a
claim about the fixtures it touches, not about the model's aggregate
accuracy."*

**A corpus-level materiality *condition* is refused**, on §4.2's own argument:
a pooled bar would be unclearable by construction for any rule this targeted,
and preregistering one would be preregistering a guaranteed miss. The
disclosure is required; the gate is not added.

---

### R-I4 — the evidence canary's perturbation, frozen exactly

**Supersedes** §5.3's *"corrupt every archive row"* / *"corrupt rows before the
cutoff"*.

The defect is real: "corrupt" named no field, no transformation, no magnitude
and no comparison, and `e` reads only club participation and date — so
corrupting scores alone would be a canary that cannot fail. The anchoring
experiment's canary was substituted in flight and became a disclosed deviation;
this one is frozen before the freeze.

**The mutation, frozen.** Rows are selected by normalised date: `after` selects
`date ≥ cutoff`, `before` selects `date < cutoff`. For the i-th selected row,
0-based in frame order:

* `home_key := "__canary_corrupt__h{i}"`, `away_key := "__canary_corrupt__a{i}"`
* `fthg := 9`, `ftag := 9`
* **dates are not touched.** The cutoff partition must survive the mutation or
  the canary tests a different thing.

Per-row unique sentinels are required, not decorative: `wcmodel.data.features`'
duplicate-match dedup collapses content-identical rows, and a shared sentinel
deleted the rows it meant to rewrite (fixed at 06bd431). A canary that crashes
is not a canary that fails.

**The comparisons, frozen.** *Negative leg:* the evidence vector `e(t, C)` over
the corpus's clubs, compared with `numpy.array_equal` on the float64 values
**before rounding** — bit equality, not a tolerance — and both provisional sets
(incumbent and enlarged) compared by set equality. Any difference is
`EvidenceCanaryFailed`. *Positive control:* `max_t |e_corrupt − e_clean| >
1e-9`; the realised value is recorded on the canary record. *Both legs* record
the number of rows the mask selected; an empty mask is a refusal, never a pass.

The record from the authorised 2026-08-27 run stands as the reference: at
cutoff 2022-08-13 the negative leg moved `e` by 0.0 and the positive control by
52.53, with both provisional sets identical.

---

### R-I5 — "synthetic" has an enforceable definition

**Supersedes** §5.3's and §6 step 1's unqualified *"synthetic corpora only"*.

The defect is real: nothing in the document excluded copied, sampled or
transformed real rows from being labelled synthetic, and enumerating a command
afterwards does not prove input ancestry.

**The definition, frozen.** A corpus, archive or ledger is **SYNTHETIC** iff
every one of its values is written literally in `epl/tests/test_evwiden.py`, or
generated there by arithmetic over literals written there. **No value may be
read, copied, sampled, transformed, or otherwise derived from**
`data/epl/matches.parquet`, `data/epl/fit/walkforward_predictions.parquet`,
`data/epl/fit/walkforward_ledger.jsonl`, `data/epl/sim/retro_r1.jsonl`, or any
artifact derived from them.

The generators are `_archive()` and `_corpus()` in that module. Their four
clubs — `rich`, `mid`, `stale`, `cold` — are invented, and a test asserts that
none of the four appears in the pinned archive's club columns, which is the
ancestry check made mechanical. Both generators are hashed by the §6 hash
table, because the test module is one of the two hashed harness files.

**The `@pinned` tests are not synthetic and are not covered by this
definition.** They read the pinned artifacts deliberately, to re-derive the
document's own census; they fit nothing and simulate nothing, and they are
authorised under R-B5.

---

### R-I6 — the evidence schema, frozen field by field

**Supersedes** §6's evidence-contract table.

The defect is real: the table said "both CIs" where there are **three**
deciding intervals, left the 820-fixture control without a committed home,
promised Sunderland and coverage diagnostics no column held, and froze no
MANIFEST membership.

**`reports/evidence/widening.json`** carries, at minimum, and by these names:

* `schema`, `generated_at`, `prereg_commit`, `repairs_section`;
* `pins` — corpus / archive / ledger / frozen-config digests, the realised
  config digest, and the row and season counts;
* `estimand` — `{n: 85, mean, sd, se_iid}`;
* `ci_week` and `ci_season` — each `{function, n_blocks, B, alpha, seed, lo,
  hi}`; `ci_table_mw6` likewise, with `n_blocks: 7`;
* `gate_i`, `gate_ii`, `gate_iii` — each `{value, bar, PASS}`;
* `gate_iv` — `{mw6: {n: 7, mean, ci, mc_se_mean, per_cell: [...]},
  per_label: {MW0, MW3, MW10: {n_treated, mean, PASS}}, mw19:
  {structural_zero: true, decides: "nothing"}, precision: {mc_se_mean,
  rule, resolved: bool}, PASS_or_UNRESOLVED}`;
* `controls` — `{identity: {n: 820, max_abs_diff, mean_abs_diff, PASS},
  untreated_moved, predicate_mismatch, table_parity: {n_cells: 35, PASS,
  per_cell_digests}}`;
* `canaries` — results, evidence (both legs, both row counts, the positive
  control's realised magnitude), identity, direction (with the branch each
  fixture took);
* `grid` — five points, each `{n_thin, n_treated, mean, ci, degenerate,
  decides: "nothing"}`;
* `strata` — six seasons and two club categories, each `decides: "nothing"`;
* `movement` — mean and max `|Δp|` over the treated fixtures, beside the
  re-seed reference scale;
* `coverage` — per treated club, per arm, cov50 and cov90;
* `sunderland` — the three 2025/26 cells, both arms: relegation probability,
  points mean, 5–95 band, under the label §3.4 fixes;
* `power` — R-I2's object, frozen scenarios plus realised;
* `materiality` — the pooled corpus figure and R-I3's required sentence;
* `verdict` — `ADOPT` / `NO ADOPT` / `UNRESOLVED`, and which gate decided.

**`widening_per_fixture.csv`** — 85 rows: `key, match_id, season, block,
cutoff, date, home_key, away_key, e_home, e_away, e_min, thin_at, treated,
incumbent_widened, p_home_B, p_draw_B, p_away_B, p_home_A, p_draw_A, p_away_A,
p_home_corpus, p_draw_corpus, p_away_corpus, y, rps_B, rps_A, delta,
delta_vs_corpus, max_abs_dp_vs_corpus`.

**`widening_table_cells.csv`** — 35 rows: `season, cutoff_label, cutoff,
treated_clubs, n_treated_clubs, trps_control, trps_treatment, delta_trps,
wtrps_control, wtrps_treatment, delta_wtrps, mc_se_paired, identical,
substantive_digest_control, substantive_digest_treatment,
parity_digest_simretro, cov50_control, cov90_control, cov50_treatment,
cov90_treatment, cov50_treated_control, cov90_treated_control,
cov50_treated_treatment, cov90_treated_treatment, realised_hash`.

**`widening_grid_means.csv`** — `e_star, n_thin, n_treated, mean_delta, ci_lo,
ci_hi, n_blocks, degenerate, decides`.

**`reports/evidence/MANIFEST.sha256`** must carry an entry, with byte size, for
each of the four files above **and** for every bulky local artifact: each shard
ledger, the merged fit ledger and the table ledger. `--verify` refuses if any
promised entry is missing or any digest disagrees. "Bulky local artifacts" is
no longer a category; it is a list.

---

### R-M1 — the union is through `e* = 12`, not below it

**Supersedes** §2.3's phrase *"the `e* < 12` union"*. §1.4's table gives 78
blocks at `e* = 12` and 50 at `e* = 8`, so the union of grid points strictly
below 12 cannot be 78. The correct phrase is **"the union through `e* = 12`
(that is, `e* ≤ 12`)"**. The count **78** is right and stays binding, as do the
62 primary blocks it contains.

---

### R-M2 — the direction canary, bound to the production path and honest about edges

**Supersedes** §5.3's direction-canary bullet.

The defect is real on both halves. `finalize_grid`
(`src/wcmodel/model/draw_api.py:218-231`) applies `inflate_predictive` and then
an **unconditional** renormalisation, so a comparison against
`inflate_predictive` alone is a comparison against something the production map
does not emit; and `inflate_predictive` documents an edge no-op — a marginal
mean at ~0 or at the largest representable score has no interior max-entropy
solution and the grid is returned **unchanged**, so "strictly higher entropy"
is not unconditional.

**The repaired canary.** The comparator is the production path:
`finalize_grid(grid, posterior, provisional=True)`, against the base
`finalize_grid(grid, posterior, provisional=False)` computed from the same
pre-widening `grid`. Equality is **bit equality** (`numpy.array_equal`).
Entropy must be strictly higher than the base **except** where the documented
edge branch fires, in which case unchanged grid and equal entropy are the
correct result. The canary records which branch every treated fixture took and
**requires at least one treated fixture in the interior branch** with strictly
higher entropy and a strictly positive `max |Δp|`. A direction canary in which
every fixture took the edge branch is `CanaryFailed`: it proved nothing.

---

### R-M3 — the anchoring LOSO is not a precedent, and nothing is selected here

**Supersedes** §2.1's *"stricter than the prequential-selection precedent
(anchoring's LOSO)"*.

The defect is real. `reports/epl_anchoring_result.md` §1 rules that label false
in its own words — the folds are honest about a season's fixtures but not about
its **results**, because the information travels through training ancestry
rather than through the fold split, and the honest name is *"in-fold weight
selection with shared training ancestry"*. It is a failed attempt, not a
precedent.

**The repaired sentence.** *The nearest thing this repository has to a
prequential selector is the anchoring experiment's **failed** leave-one-season-out
attempt, whose own result document rules the label false; it is a precedent for
nothing. The correct statement here is simpler and stronger: **this experiment
performs no outcome-based selection at all.** `e*` is fixed at 10.0 from
`config/config.yaml`'s `elo.volatility_window`, the grid is reported and never
selected from, and `epl.evwiden.adoption` takes four arguments none of which is
a grid point.*

---

### R-M4 — the disclaimer distinguishes the thin population from the treated one

**Supersedes** §8's first bullet's closing sentence.

**The repaired sentence.** *The estimand answers only the question asked: the
value of the re-key over **all 85 thin fixtures**, 33 of which the incumbent
predicate already widens and which therefore carry a delta of exactly zero by
construction. Only 52 fixtures are touched.*

---

### R-M5 — the identity control's support citation is corrected

**Supersedes** §3.2's citation of `verify_fast_path_is_inert`.

The defect is real: that function builds the feature panel twice and compares
the two with `DataFrame.equals` (`epl/walkforward.py:321-329`). It is a check on
feature frames, not on repeated fitted forecasts, and it cannot support a claim
about bit-equal predictions.

**The repaired support**, which is narrower and true: `epl.walkforward.point_in_time_canary`
(`epl/walkforward.py:450-460`) runs the whole pipeline this experiment runs —
anchor, fit, cold start, `predict_1x2` — and compares **probabilities**, with a
positive control proving the corruption landed; and `dcfit.fit_epl` draws from
the frozen configuration's single `seed`, which does not vary by cutoff. Beyond
that, **the 820-fixture control is not supported by an assumption; it is the
claim under test.** If repeated fits do not reproduce the published
probabilities at eight decimals, this experiment stops, and that is the point
of running the control first.

---

### R-H — the harness builder's four concerns, ruled

**(1) The freeze stays unpasted. CONFIRMED.** §6's order is unchanged — harness
written and audited, then the freeze commit, then the first real fit — and the
freeze block may not be generated until the harness carries these repairs. A
hash table committed now would freeze code that does not implement the
document, which is the one thing a hash table must never do.

**(2) The sampler leg is unexercised, and its first exercise is named here.
BLESSED.** The **first post-freeze act** of this experiment is:

> `python -m epl.evwiden --run --limit 1 --dir <scratch>` — one fit at the
> **first opening by date, 2019-08-09** (10 fixtures; ledger incumbent set
> `{sheffield_united}`; the §2.1 union adds exactly `{aston_villa, norwich}`),
> written to a scratch directory outside the preregistered run directory.

Its purpose is to exercise, once and end to end, the one path no test can
execute without a real fit: the identity control at that opening, the cutoff
and point-in-time assertions, the three predict passes, the direction canary
and the row schema. **Its numbers enter no estimand**; its rows are never
merged; the opening is named here, before the fit, and it is first by date and
not by anything else, so it is not a selection step. Its console output and row
count are recorded in the result document.

**This is a real fit on the real archive.** It runs after the freeze commit,
and from the moment it completes **R-B6 is in force**: the harness is frozen for
good. If its identity control fails, the run stops and the failure publishes.

**(3) §5.3's "except to hash them". RULED** — see R-B5. The builder's reading is
adopted as the document's own, with "and simulations" added: the clause is
about fits and simulations, reading is enumerated, and the six authorised
passes are listed by name and date.

**(4) The two-sided cell identity. RULED, and adopted into the document.** §3.3
demanded only one direction — an untouched cell whose arms differ is
`TableIdentityBreak`. The other direction is now equally required: **a cell
whose rule-named treated clubs produced a byte-identical run is
`TableIdentityBreak` too.** The builder's reason is the document's reason: a
treatment that changes nothing where the rule says it should is not a null
result, it is a treatment that never reached the sampler, and reporting its
zero delta as evidence of no harm would be reporting the absence of the
experiment.

---

### R-X — the refusal inventory, and what this section does not change

**§5.1 gains exactly one type and loses none.** `TableMCImprecise` — the paired
Monte Carlo error cannot be computed (unequal per-particle season counts), or
the precision rule of R-B3 leaves gate (iv) UNRESOLVED. The inventory is
therefore **twenty-three** types. `ConfigNotFrozen`, `ControlMismatch` and
`TableIdentityBreak` gain the conditions named in R-I1, R-B1 and R-B4/R-H(4)
respectively.

**Unchanged by this section, and still binding:** the rule of §2.1 and its one
frozen constant `e* = 10.0`; ADD-not-REPLACE and binary-not-continuous;
α = 0.5 and mechanism (c); the populations 85 / 52 / 51 / 78 and the table's
16 / 19; the seeds 20260611 and 20260814; B = 10,000; §4.1 clauses (i), (ii)
and (iii) and their bars; the conjunction "ALL FOUR"; §4.4's publish-either-way
and its refusal to re-litigate a miss; §4.5's shadow-first adoption and the
owner ruling that alone can take it; §6's closed write set and the lock check;
§7's other invalidations; §8's other disclaimers; and the fact that no
secondary, stratum or grid point decides anything.

*Repaired 2026-08-27, before the freeze commit, before the first fit, and
before any delta of this experiment existed anywhere.*

---

## Repairs of 2026-08-27, round two — on the re-review

**Standing.** This section is appended, not merged. Every word above it — the
original 889 lines committed at `f26b760` and the first repair section committed
at `1b79cc5` — stands exactly as committed, and this section supersedes named
clauses of both, clause by clause and **by quote**. Where a round-two repair and
any earlier text conflict, **the round-two repair governs**. Where this section
is silent, the earlier text governs, round one over the original.

**Why a repair is still permitted, stated more carefully than round one stated
it.** The house lifecycle allows a preregistration to be repaired only while it
has decided nothing, and that condition still holds: no freeze commit exists
(§6 step 2 has not landed), no `data/epl/fit/evwiden*` or `data/epl/sim/evwiden*`
file exists, no result, delta or evidence file of this experiment exists, and
nothing below is informed by an outcome because there is no outcome.

Round one also wrote, in its preamble, *"and the harness's own guards refuse to
produce one until the freeze block is committed."* **That sentence is superseded
and withdrawn — it is false.** `epl/evwiden.py`'s pre-freeze guard is keyed to
the run directory: a `--run` or `--table` invocation pointed at a `--dir`
outside the default directories can fit the real archive and produce a real
delta with no freeze block anywhere. The correct statement is:

> **No fit of this experiment has been run on the real archive. That is an
> attestation by the author, not a fact the repository can prove.** `data/` is
> gitignored, so a scratch run leaves no Git trace, and the committed tree can
> establish only that *nothing was committed*. The repair-in-place premise rests
> on the attestation, and a reader is entitled to weigh it as one.

**A binding obligation follows from that, on the harness revision.** Before the
freeze commit, `epl.evwiden` must refuse to fit or simulate on the real archive
**anywhere** while unfrozen — the refusal must be keyed to the freeze state and
to the artifact identity being read, never to the output directory — and
`--freeze-block` must refuse to render until the harness implements this
document. The pre-freeze guard must additionally verify a **committed** freeze:
the Git object identity of the prereg blob whose hash table it reads, the
membership and schema digests that block records, and a recorded first-real-fit
event. Round one's freeze guard parses current prose against current filesystem
bytes, which an uncommitted two-line paste satisfies; that is not a freeze and
this document does not accept it as one.

**What prompted this round.** A second independent cross-model review (Codex
`gpt-5.6-sol`, ultra) of `1b79cc5` returned UNSOUND. It discharged **M1, M3, M4
and M5**; it found **B1–B6, I1–I6 and M2 STILL-OPEN** — almost all of them
because `epl/evwiden.py` and `epl/tests/test_evwiden.py` predate the round-one
repairs and still implement the superseded document; and it located **nine new
blocking defects and four new important ones in the repair text itself**, plus
four supersession-hygiene failures.

### R2-0 — the division of labour this section observes

This round repairs **text only**. Not one line of `epl/evwiden.py` or
`epl/tests/test_evwiden.py` is touched by the commit that carries this section.
That is deliberate and it is the correct order: the harness must be revised
against a document that is coherent, and the document was not coherent.

Every repair below is therefore **simultaneously two things**: a correction to
this preregistration, and a **binding obligation on the harness revision that
must land before the freeze commit**. §6 step 1 ("the harness is written and
audited") is not satisfied until the harness implements this document as
repaired in both rounds; §6 step 2's freeze block may not be generated before
that; and R-H(1)'s ruling ("the freeze stays unpasted") is reaffirmed.

The re-review's implementation-lag findings — B1, B2, B4's call mismatch, B5's
directory-keyed guard, B6's note-repairs-drift message, I1's unchecked realised
digest, I4's max-abs comparator, I6's stale writer, M2's direct-`inflate`
comparator — are **not repaired here and are not thereby discharged**. They are
the harness revision's work list, and the freeze block may not be rendered while
any of them stands.

---

### R2-B3 — the paired particle bootstrap, redesigned: tie-aware, jointly resampled, covariance carried by construction

**Supersedes**, by quote, three parts of R-B3:

1. the tally bullet — *"the run retains per-particle rank tallies, built from
   `SimRun.retained_rows.particle` and `.order` (plan v2 D20 already retains
   both), shaped `[n_particles, n_clubs, n_ranks]`;"*
2. the quadrature sentence — *"The MW6 mean's MC SE is `sqrt(Σ_c se_c²) / 7`
   over its seven cells — they are independent runs at different seasons with
   different fits and different streams, so their errors add in quadrature."*
3. the precision rule's two conditions — *"`mc_se_mean > 0.25 × 0.0002 = 5e-5`,
   **or** … `|mean_MW6 − 0.0002| < 2 × mc_se_mean` — the comparison to the
   tolerance falls inside the simulation's own error."*

Everything else in R-B3 stands: the season-block interval of the MW6 mean and
every constant in its table, `MC_BOOT = 2,000`, `MC_SEED = 20260827`, the
one-directional principle that simulation noise may only refuse, and
`n_sims = 20,000` binding.

The three defects were real.

* **The wrong statistic.** `.order` is the ladder sequence, and `epl/table.py`
  says of it in its own docstring that *"inside a shared block its sequence
  carries no meaning and is only the deterministic club-index order"*
  (`epl/table.py:374-377`). The matrix TRPS actually scores is built from
  **fractional rank mass**: `epl.table.position_mass` / `position_mass_sums`
  spread `1/span` across the `span` positions a tie block occupies
  (`epl/table.py:550-593`, the arithmetic at `:587-593`). A bootstrap over
  `.order` would resample a different object from the one the point estimate
  scores.
* **The false independence.** `epl.leaguesim.streams(seed, chunk,
  fixture_ordinal)` reads **only** those three things (`epl/leaguesim.py:199-207`)
  — not the season, not the cutoff, not the cell — and all 35 cells run at the
  same `seed = 20260611`. Simulated season *n* of one cell and simulated season
  *n* of another therefore consume the **same uniforms** and are priced by the
  **same particle index** `n mod S` (`epl.leaguesim.particle_index`, the
  stratified `i mod S`). The cells' Monte-Carlo errors are correlated by
  construction and the size of that correlation is unknown. `sqrt(Σse²)/7`
  assumed it away.
* **The unguarded boundary.** The precision rule guarded the comparison to
  `+0.0002` and nothing else. Clause (iv-c) decides on two further boundaries —
  the MW6 mean against **zero**, and the interval's lower bound against **zero**
  — and (iv-b) decides on three more comparisons to `+0.0002` at MW0, MW3 and
  MW10. Noise at any of those could turn a failing gate into a passing one,
  which is the direction that must never be available.

#### The estimator, frozen in full

**Deciding cells.** The estimator runs over the **16 treated cells** — the exact
cells §3.3 enumerates: MW6's seven, MW0's three, MW3's two, MW10's four. MW19
holds no treated cell, is a structural zero by construction, and enters nothing.

**Step 1 — the per-particle fractional rank-mass tally, through the protected
code that defines it.** For each deciding cell and each of its two arms, from
the run's own `retained_rows` and `plan`:

```
ranking = epl.table.Ranking(
    block_start     = run.retained_rows.block_start,
    block_span      = run.retained_rows.block_span,
    resolution_code = run.retained_rows.resolution_code,
    order           = run.retained_rows.order,
    boundaries      = run.plan.boundaries,
    rule_id         = run.plan.rule_id)
mass = epl.table.position_mass(ranking)                    # [N, C, C] float64
T[s] = mass[run.retained_rows.particle == s].sum(axis=0)   # [P, C, C] float64
```

`order` is passed because the dataclass requires the field; **it is never
read** — `position_mass` reads `block_start` and `block_span` and nothing else
(`epl/table.py:550-558,587-593`), and no other step of this estimator touches
it. The harness may accumulate in chunks the way `position_mass_sums` does
(`epl/table.py:561-585`) provided the chunks are visited in ascending season
order, which makes the per-particle sums bit-identical to the whole-array form;
a committed test asserts that equality at 0.0.

Two committed checks bind the tally to the point estimate it must describe:

* `max |T.sum(axis=0) − run.matrix| ≤ 1e-9` — the tally reproduces the scored
  matrix (the tolerance, not bit equality, because the protected accumulator
  sums in chunk order and this one sums in particle order);
* every particle's tally has **every row and every column** equal to
  `k = n_sims / P` to within 1e-9 — a league season is a bijection between clubs
  and ranks, and this is the same equal-cluster condition the protected
  `epl.simmetrics.trps_se_cluster` enforces on its own input
  (`epl/simmetrics.py:230-250`).

**Step 2 — the preconditions, and the refusal that guards them.** All 32 tallies
(16 cells × 2 arms) must report the **same** `n_particles` `P`, and every
particle must carry the same whole number of simulated seasons. Under the pinned
configuration `P = 1,000` at every cell (`model.inference.draws = 1000`, bound by
R-I1's `realised_config_sha256`) and `n_sims / P = 20`. Any violation — unequal
per-particle season counts, or unequal `P` across cells or arms — raises
**`TableMCImprecise`** and stops the table leg. Joint resampling is undefined
without a common index space, and this document will not approximate one.

**Step 3 — one resample per replicate, applied to all thirty-two tallies.**

```
rng = numpy.random.default_rng(MC_SEED)          # MC_SEED = 20260827
for r in range(MC_BOOT):                          # MC_BOOT = 2,000
    picked = rng.integers(0, P, P)                # ONE draw, this replicate
    for cell c in the 16 deciding cells:
        for arm a in (control, treatment):
            M = T[c][a][picked].sum(axis=0)
            M = M / M.sum(axis=1, keepdims=True)  # row-normalise
            s[c][a] = epl.simmetrics.trps(M, positions_c, spans=spans_c)
        d_r[c] = s[c][treatment] − s[c][control]
    mw6_r  = mean(d_r[c] for the 7 MW6 cells)
    mw0_r  = mean(d_r[c] for the 3 treated MW0 cells)
    mw3_r  = mean(d_r[c] for the 2 treated MW3 cells)
    mw10_r = mean(d_r[c] for the 4 treated MW10 cells)
```

`positions_c` and `spans_c` are the cell's own realised position vector and
realised block widths from `epl.simretro.realised_positions` — the same two
arrays the cell's point estimate is scored with (`epl/simretro.py:1246,1261`).

**Step 4 — the standard errors, read off the replicate stream and nowhere
else.**

```
mc_se_mw6  = std(mw6_r,  ddof=1)      mc_se_mw0  = std(mw0_r,  ddof=1)
mc_se_mw3  = std(mw3_r,  ddof=1)      mc_se_mw10 = std(mw10_r, ddof=1)
mc_se_cell[c] = std(d_r[c], ddof=1)                    # reported, decides nothing
```

**There is no quadrature step and no independence claim anywhere in this
estimator.** The label means are computed *inside* each replicate and their
spread is read directly; whatever covariance the shared RNG streams induce
between cells is reproduced within every replicate rather than modelled. The
per-cell SEs are published as diagnostics and are never combined into a label
SE.

**Why one index draw across cells is the right construction, and what it does
not claim.** It does **not** claim that particle *s* of one cell is the same
posterior draw as particle *s* of another — it plainly is not; the cells are
different seasons with different fits. What it uses is the fact established
above: the shared randomness of two cells is indexed by
`(particle index, chunk, fixture_ordinal)`, and the particle index is
deterministic in the season index. Resampling the particle **index** jointly
therefore resamples the same simulation slots in every cell at once, so two
cells that share uniforms move together inside a replicate exactly as they move
together in the run. Within a cell, the same `picked` applied to both arms is
the CRN pairing R-B3 already argued for: the arms share particles, share
streams, and differ only on the D12 branch at treated fixtures, so most of the
simulation noise cancels in the difference.

**Honest limits of the construction, stated now.** The particle is the cluster,
as it is in every Monte-Carlo error this repository publishes (plan v2 D15).
Within-particle match randomness at fixed particle is resampled only through the
20 seasons each particle carries, and a 7-, 4-, 3- or 2-cell label mean is a
small average however it is estimated. This estimator is a bound on how much of
the gate's margin is simulation noise; it is not a model of the fit's own
uncertainty, which no table statistic in this experiment sees.

#### The precision and refusal rule, at every deciding boundary of gate (iv)

Gate (iv) is **UNRESOLVED**, and ADOPT is refused, if **any** of the following
holds. Every condition is one-directional: UNRESOLVED blocks adoption and can
never grant one.

* **(P1) Resolution.** Any deciding MC SE exceeds `0.25 × 0.0002 = 5e-5` — that
  is, any of `mc_se_mw6`, `mc_se_mw0`, `mc_se_mw3`, `mc_se_mw10`.
* **(P2) iv-a's tolerance boundary.** `|mean_MW6 − 0.0002| < 2 × mc_se_mw6`.
* **(P3) iv-b's tolerance boundaries.** At each of MW0, MW3 and MW10 separately:
  `|mean_L − 0.0002| < 2 × mc_se_L`.
* **(P4) iv-c's zero boundary on the mean.** `|mean_MW6 − 0| < 2 × mc_se_mw6`.
* **(P5) iv-c's zero boundary on the interval.** `|ci_lo_MW6 − 0| <
  2 × mc_se_mw6`, where `ci_lo_MW6` is the lower bound of the season-block
  interval frozen in R-B3's table.
* **(P6) Structure.** The `TableMCImprecise` conditions of Step 2. This one is a
  refusal, not an UNRESOLVED verdict: it stops the table leg.

(P5) is deliberately a **conservative proxy and is labelled one**: the interval
is a season-block resample of the seven cells' *point* deltas and the MC SE is
the scale on which each of those points is itself uncertain, so the comparison
bounds rather than propagates. It can only ever refuse, which is why an
approximate guard is admissible here and would not be admissible on a clause
that could grant.

**Why (P4) and (P5) exist at all.** Clause (iv-c) is a **failure** clause: gate
(iv) fails when the MW6 mean is `> 0` **and** its interval excludes zero.
Simulation noise that pushes the mean or the lower bound below zero converts a
failure into a passage. That is the one direction this document may not leave
open, and UNRESOLVED closes it without ever opening the other.

`n_sims` stays at **20,000** and the precision rule does not license a larger
run: enlarging a preregistered constant after a number exists is exactly what §7
forbids. An UNRESOLVED verdict publishes as UNRESOLVED, with every number, under
§4.4's no-file-drawer rule, and the result document names which of (P1)–(P5)
fired.

**`reports/evidence/widening.json`'s `gate_iv.precision` object** carries, by
these names: `mc_boot`, `mc_seed`, `n_particles`, `sims_per_particle`,
`mc_se_mw6`, `mc_se_mw0`, `mc_se_mw3`, `mc_se_mw10`, `mc_se_per_cell` (16
entries), `conditions` (P1–P6, each with its computed value and a boolean), and
`resolved`. R-I6's schema gains those names; its `mc_se_mean` field is superseded
by them.

---

### R2-B4 — the digest split that ends the tautology, the plan state the digest must bind, and the budget the oracle actually costs

**Supersedes**, by quote:

1. R-B4's substantive-digest item — *"9. the provisional set actually carried by
   the book."*
2. R-B4's cross-reference — *"**The two-sided cell identity is required** — see
   R-H(4)."*
3. §2.4's budget sentence — *"The table leg (§3.3): 35 fits plus 70 runs of
   20,000 simulated seasons — bounded by ~2 hours."*

#### (a) The tautology, and the two digests that replace one

The re-review is right and the contradiction was internal to round one. R-B4's
digest **included** the provisional set; R-H(4) then required every treated
cell's two digests to **differ** as proof that the treatment reached the sampler.
Those two clauses together prove nothing: the digests differ because the metadata
names a different set, whether or not one scoreline changed. A test that cannot
fail is not a test — the same sentence this document applies to canaries.

**Two digests are defined, with disjoint jobs.**

> **`sampler_digest` — sampler output only.** SHA-256 over the canonical JSON
> (`epl.leaguesim.canonical_json`) of, in this order:
>
> 1. the scored position matrix at full stored precision;
> 2. the per-particle fractional rank-mass tallies of R2-B3 Step 1;
> 3. the retained points, goal-difference and goals-for vectors;
> 4. the tie-block record — `block_start`, `block_span`, `resolution_code`.
>
> **Nothing else.** No club list, no plan, no seed, no posterior hash, **no
> provisional set**, no arm label, no clocks, no host, no shard id, no free
> text. It is comparable only **within one cell, between its two arms**, and
> that is its only use.

> **`substantive_digest` — everything a rerun must reproduce.** SHA-256 over the
> canonical JSON of `sampler_digest`'s four items **plus**:
>
> 5. the club list;
> 6. the consequence weights and the boundary definition;
> 7. the realised-truth identity — `realised_hash`, the realised position vector
>    and the realised points vector;
> 8. `effective_posterior_hash`, `n_sims`, `n_particles`, `seed`;
> 9. **the full `SimPlan` state** (see (b) below).
>
> **Excluded by name:** the arm label, the provisional set, wall clocks, host,
> shard id, and any free-text note.

**The provisional set leaves both digests and becomes a compared field.** Each
table row records `provisional_control` and `provisional_treatment` as sorted
club lists. They are checked directly, three ways: the parity oracle requires
`provisional_control` to equal protected `ArchiveRunner`'s own
`provenance["provisional_teams"]` at that cell; the treated-cell census requires
`provisional_treatment ⊋ provisional_control` at exactly the 16 named cells and
`provisional_treatment == provisional_control` at the other 19; and any
disagreement is `TableIdentityBreak`. Metadata is checked as metadata, and the
sampler is checked by its output.

**The two-sided cell identity, restated on `sampler_digest`** — this supersedes
R-B4's cross-reference and re-states R-H(4)'s substance so that it can actually
fail:

> * An **untouched** cell (one of the 19) whose two arms' `sampler_digest`s
>   differ is `TableIdentityBreak`.
> * A **treated** cell (one of the 16) whose two arms' `sampler_digest`s are
>   **equal** is `TableIdentityBreak`. A treatment that changes no sampler output
>   where the rule says it must is not a null result; it is a treatment that
>   never reached the sampler, and reporting its zero delta as evidence of no
>   harm would be reporting the absence of the experiment.

Because the provisional set is now outside the digest, the second condition is a
statement about scorelines, tie blocks and points — the things the D12 branch
actually moves — and it can fail. That is the whole repair.

#### (b) The `SimPlan` state the substantive digest binds

Item 9 is the complete field set of `epl.leaguesim.SimPlan`
(`epl/leaguesim.py:559-654`), serialised canonically: `season`, `season_code`,
`cutoff`, `observed_by`, `clubs`, the fixture tuple (per fixture:
`fixture_id`, `ordinal`, `home_key`, `away_key`, and `result` as the played
snapshot — `null` for unplayed), `adjustments` (the int16 vector, by club),
`boundaries`, `rule_id`, `n_sims`, `n_particles`, `seed`, `chunk_size`,
`n_unresolved`, `results_lag`.

That closes every gap the re-review named: the season/cutoff/`observed_by`
identity, the fixture-and-result snapshot the run was built on, the points
adjustments, the ranking rule id, the chunking (which fixes the RNG chunk keys
and therefore the numbers), and the results-lag state. A run that differs from
another in any of them is a different run, and the digest now says so.

#### (c) The budget, superseded with the oracle's true cost

R-B4 required a 35-cell native-parity run against protected
`epl.simretro.ArchiveRunner` and did not supersede §2.4's table-leg budget, which
still read *"35 fits plus 70 runs of 20,000 simulated seasons — bounded by ~2
hours."* That was incoherent: `ArchiveRunner` owns its own fit
(`epl/simretro.py:520-527,536`), exposes no posterior and no `ParticleBook` for
reuse, and returns `CutoffResult`/`ArmResult` — so the parity leg cannot ride
the new runner's fits and needs its own.

**The superseding budget for the table leg:**

| leg | fits | 20,000-season simulations |
|---|---:|---:|
| protected `ArchiveRunner`, `dc_native` at all 35 cells (the oracle) | 35 | 35 |
| the new runner, control + treatment at all 35 cells | 35 | 70 |
| **table leg total** | **70** | **105** |

**The whole experiment is therefore 148 fits** — §2.3's 78 match-level openings
plus these 70 — **and 105 simulations of 20,000 seasons.** At the measured cold
fit rate (57.24 s, `data/epl/fit/single_fit.json`) the 70 table fits are ≈ 67
minutes; the superseded 2-hour bound implied ≈ 1.24 minutes per 20,000-season
simulation, so 105 simulations are ≈ 130 minutes. **The table leg is bounded by
~4 hours, not ~2.** Everything else in §2.4 stands unchanged: sequential shards,
BLAS pinned to one thread, `python -u`, a nohup'd script file and never a stdin
heredoc, waited per PID, and the run may not be thinned — *"dropping cutoffs,
fixtures, cells or grid points to fit a clock is an amendment, not an
optimisation"*, which now includes sampling the parity oracle.

**The parity comparator, named.** `ArchiveRunner`'s `CutoffResult` retains the
`SimRun` on `ArmResult.run` (`epl/simretro.py:441-456`), so the oracle compares
**`substantive_digest`s**, computed by the same harness function from the
protected runner's `SimRun` and from the new runner's control-arm `SimRun`. All
35 cells, no sampling; a difference at any cell is `TableIdentityBreak` and stops
the leg. `data/epl/sim/retro_r1.jsonl` stays read-only and is not the comparison
object.

---

### R2-H — the post-freeze order: the results canary first, because it is the first real fit

**Supersedes**, by quote:

1. R-H(2)'s first sentence — *"The **first post-freeze act** of this experiment
   is:"* — and the blockquote naming
   `python -m epl.evwiden --run --limit 1 --dir <scratch>`;
2. R-H(2)'s closing paragraph — *"**This is a real fit on the real archive.** It
   runs after the freeze commit, and from the moment it completes **R-B6 is in
   force**: the harness is frozen for good."*

The defect is real and it is an ordering impossibility, not a preference.
`epl.walkforward.point_in_time_canary` performs **four real fits** on the real
archive: `_forecasts` is called four times — clean and dirty at the cutoff,
clean and dirty at the later date (`epl/walkforward.py:490-495`). §5.3 requires
that canary as a precondition of the run and §5.3 places it *"after the
freeze"*. `--run` will not proceed without a post-freeze results canary in its
own directory. So `--run --limit 1` cannot be the first post-freeze act: the
canary is, and the canary is where the first real fit of this experiment
happens.

**The superseding order, in three named steps.** Nothing else may run on the
real archive between them.

> **Step 1 — the post-freeze results canary. This is the first post-freeze act
> and it performs the first real fits of this experiment.**
> `python -m epl.evwiden --canary --dir <the preregistered run directory>`, run
> once, after the freeze commit. It executes
> `epl.walkforward.point_in_time_canary` (four fits) and the evidence, identity
> and direction canaries. `PASS: false` on any leg stops the experiment and the
> failure publishes. Its record is written to the run directory's `canary.json`
> and its digest is recorded in the result document.
>
> **Step 2 — the single-opening exercise.**
> `python -m epl.evwiden --run --limit 1 --dir <scratch>` — one fit at the
> **first opening by date, 2019-08-09** (10 fixtures; ledger incumbent set
> `{sheffield_united}`; the §2.1 union adds exactly `{aston_villa, norwich}`),
> written to a scratch directory outside the preregistered run directory. Its
> purpose is unchanged: to exercise, once and end to end, the one path no test
> can execute without a real fit — the identity control at that opening, the
> cutoff and point-in-time assertions, the three predict passes, the direction
> canary and the row schema. **Its numbers enter no estimand**; its rows are
> never merged; the opening is named here, before the fit, and it is first by
> date and not by anything else, so it is not a selection step. Because §5.3's
> results canary is a same-directory precondition of `--run`, this step's
> scratch directory carries its own copy of the Step 1 canary record; that copy
> is a precondition artifact and enters nothing.
>
> **Step 3 — the shards, then the table leg.**
> `data/epl/fit/evwiden/launch.sh` runs the **four** shards sequentially
> (R2-I6), then the merge, then the table leg's parity oracle, then the table
> leg's 35 cells.

**R-B6 comes into force at the completion of Step 1**, not Step 2. From the
moment the results canary's first fit completes, a real fit on the real archive
exists, and any change to any hashed file invalidates this preregistration — no
note, no dated appendix, no disclosure and no owner ruling restores it. R-B6's
two regimes are otherwise unchanged.

**§5.3's results-canary bullet is not superseded; it is promoted.** Its text —
*"**Results canary.** `epl.walkforward.point_in_time_canary`, run once as a
precondition on the real archive **after** the freeze; `PASS: false` stops the
run."* — was always correct and always ordered first. Round one contradicted it
by naming `--run --limit 1` the first post-freeze act; this repair restores the
document's own order and states the reason: the canary is a fitting canary.

**R-H(1), (3) and (4) stand**, (4) as re-stated on `sampler_digest` in R2-B4(a).

---

### R2-B5 — the introduction's synthetic-only clause, superseded by quote

**Supersedes**, by quote, the introduction's clause (§ preamble, the paragraph
beginning *"Both predecessors ended protocol-deviant on the same clause
pair…"*):

> *"this document carries the corrected clause they both asked for: **pre-freeze
> audit runs are permitted on synthetic corpora only, are enumerated in the
> freeze commit, and may not enter any estimand. Not one fit on the real archive
> precedes the freeze commit.**"*

R-B5 authorised six named read-only passes over the **real** pinned archive,
corpus and ledger, and superseded only §5.3's later sentence. The introduction
kept saying synthetic-only, so the document contradicted itself about its own
pre-freeze regime — the exact failure mode round one was written to end.

**The superseding clause.**

> *This document carries the corrected clause both predecessors asked for, in
> its repaired form: **pre-freeze, no harness code fits and no harness code
> simulates. Reading the pinned artifacts is permitted, is read-only, and is
> enumerated by name and date in the freeze commit. Seeded-defect audits and
> the canaries' adversarial legs run on synthetic corpora only, as R-I5 defines
> "synthetic". No pre-freeze pass may enter any estimand. Not one fit and not
> one simulation on the real archive precedes the freeze commit.***

R-B5's six authorised passes, its rule for any further pass, and its requirement
that `epl.evwiden.freeze_block`'s enumeration be extended from four names to all
six before the freeze commit, all stand unchanged.

---

### R2-X — the refusal inventory, counted so the count cannot be read two ways

**Supersedes**, by quote, R-X's sentence *"The inventory is therefore
**twenty-three** types."*

The sentence was true on one reading and false on another, and the harness's
exact-inventory test enforces the other one. `epl/evwiden.py` today defines
`EvWidenError` plus **22** subclasses — 23 classes in the module, 22 named
refusals in §5.1's table.

**The superseding statement, counted both ways so neither reading is wrong.**

> §5.1's table names **22** refusals. R-B3 adds **`TableMCImprecise`**, so the
> repaired inventory is **23 named refusals**, which is **24 classes** counting
> the `EvWidenError` base they all derive from. `TableMCImprecise` fires on
> R2-B3 Step 2's structural conditions — unequal per-particle season counts, or
> an `n_particles` that differs across the 16 deciding cells or between a cell's
> two arms — and it stops the table leg. Gate (iv) being left UNRESOLVED by the
> precision rule (P1)–(P5) is **not** a refusal and raises nothing: it is a
> verdict, it publishes, and it blocks adoption.

That is a correction of round one on a second point: R-X folded "the precision
rule leaves gate (iv) UNRESOLVED" into `TableMCImprecise`'s firing conditions.
UNRESOLVED is a published verdict, not an exception; conflating them would make
the harness raise on a result it is required to publish.

**Binding obligation on the harness revision.** `epl/evwiden.py` must define
`TableMCImprecise(EvWidenError)`; `epl/tests/test_evwiden.py`'s two inventory
tests must name **23** refusals in both their tuple and their set, so that the
"invents no refusal the document never wrote" test still closes the inventory
exactly. `ConfigNotFrozen`, `ControlMismatch` and `TableIdentityBreak` gain the
conditions named in R-I1, R-B1 and R2-B4 respectively.

---

### R2-I5 — the ancestry check is an obligation, not a fact; and the generator inventory is corrected

**Supersedes**, by quote, two sentences of R-I5:

> *"The generators are `_archive()` and `_corpus()` in that module. Their four
> clubs — `rich`, `mid`, `stale`, `cold` — are invented, and a test asserts that
> none of the four appears in the pinned archive's club columns, which is the
> ancestry check made mechanical."*

Both halves were wrong as statements of fact. There are **three** generators, not
two, and there are **five** invented club names, not four; and **the asserting
test does not exist** — `epl/tests/test_evwiden.py`'s pinned-artifact tests check
other properties, and none of them proves disjointness. Round one asserted a
check into existence, which is the failure this document exists to prevent.

**The corrected inventory of fact.** The synthetic generators in
`epl/tests/test_evwiden.py` are **`_archive()`**, **`_corpus()`** and
**`_ledger()`** (with `_world()` returning the three together). The invented club
names they use are **`rich`, `mid`, `stale`, `cold` and `other`** — five; `other`
appears in `_archive()` as the counterparty club and is not in the module's
`CLUBS` tuple, which is why round one missed it.

**The corrected clause, phrased as what it is — a binding obligation on the
harness revision, unmet at the time of writing.**

> *R-I5's definition of SYNTHETIC stands unchanged. It is **not** currently
> enforced by any test. Before the §6 freeze commit,
> `epl/tests/test_evwiden.py` must carry a test that asserts, mechanically,
> that none of the five invented club names — `rich`, `mid`, `stale`, `cold`,
> `other` — appears in the pinned archive's `home_key` or `away_key` columns or
> in the pinned corpus's club columns, and that the three generators
> `_archive()`, `_corpus()` and `_ledger()` read nothing from the pinned
> artifacts. Until that test exists and passes, the ancestry claim is an
> assertion about the code and not a check on it, and the freeze block may not
> be rendered.*

R-I5's remaining rulings stand: the SYNTHETIC definition itself, that both
generators are hashed because the test module is one of the two hashed harness
files, and that the `@pinned` tests are not synthetic, read the pinned artifacts
deliberately, fit and simulate nothing, and are authorised under R-B5.

---

### R2-I6 — the shard count and the ledger filenames, frozen as a list

**Supersedes**, by quote, R-I6's closing paragraph:

> *"`reports/evidence/MANIFEST.sha256` must carry an entry, with byte size, for
> each of the four files above **and** for every bulky local artifact: each
> shard ledger, the merged fit ledger and the table ledger. `--verify` refuses
> if any promised entry is missing or any digest disagrees. "Bulky local
> artifacts" is no longer a category; it is a list."*

The paragraph declared a list and then wrote a category: *"each shard ledger"*
names no count and no filename, while the shard count is a CLI argument and the
shard filename is a format string (`epl/evwiden.py:1182-1184`), so the promised
MANIFEST membership was not decidable from the document.

**The shard count, frozen: `SHARDS = 4`.** Four is the harness's own default and
it is fixed here as a preregistered constant, not a runtime choice. `--shards`
may not be passed a different value for the preregistered run; a run at any other
shard count is not the run this document preregisters. Shards run
**sequentially** (§2.4, unchanged) — the partition buys resumability and
per-shard poisoning, not parallelism. The 78 openings are partitioned strided,
as the harness already does, so every shard carries the same mix of early and
late cutoffs.

**The MANIFEST membership, frozen as an exact list of eleven paths.**
`reports/evidence/MANIFEST.sha256` must carry an entry, with SHA-256 and byte
size, for exactly these and no fewer:

| # | path |
|---:|---|
| 1 | `reports/evidence/widening.json` |
| 2 | `reports/evidence/widening_per_fixture.csv` |
| 3 | `reports/evidence/widening_table_cells.csv` |
| 4 | `reports/evidence/widening_grid_means.csv` |
| 5 | `data/epl/fit/evwiden/shard_00_of_04.jsonl` |
| 6 | `data/epl/fit/evwiden/shard_01_of_04.jsonl` |
| 7 | `data/epl/fit/evwiden/shard_02_of_04.jsonl` |
| 8 | `data/epl/fit/evwiden/shard_03_of_04.jsonl` |
| 9 | `data/epl/fit/evwiden.json` |
| 10 | `data/epl/sim/evwiden/table_cells.jsonl` |
| 11 | `data/epl/fit/evwiden/canary.json` |

`--verify` refuses if any of the eleven is missing from the MANIFEST, if any
digest disagrees, or if the MANIFEST carries an entry outside the eleven. It may
not skip a file it cannot find: a missing artifact is a refusal, never a silent
omission. Files 5–11 are the bulky local artifacts and are **not** committed —
what is committed is their digest and byte size, which is the point of the
MANIFEST.

The rest of R-I6 stands: the `widening.json` field list (extended by R2-B3's
`gate_iv.precision` names), the per-fixture CSV's 85 rows and columns, the
grid-means CSV, and the table-cells CSV — whose `substantive_digest_control` /
`substantive_digest_treatment` columns are joined by
`sampler_digest_control` / `sampler_digest_treatment` and
`provisional_control` / `provisional_treatment` per R2-B4, and whose
`mc_se_paired` column is R2-B3's per-cell `mc_se_cell`.

---

### R2-I3 — the bar's justification, rebuilt in coherent units, with what it concedes

**Supersedes**, by quote, R-I3's first ground:

> *"1. **Noise.** The corpus-level re-seed shift is +0.000075 and the per-match
> ADVI re-seed scale is mean 0.0032 / p99 0.0139 / max 0.0229
> (`reports/epl_walkforward.md`). A bar that a re-seed could clear is not a bar;
> −0.0016 per treated fixture is well outside that scale."*

The defect is real and it is a unit error. `−0.0016` is a **mean RPS** demand per
treated fixture. `0.0032 / 0.0139 / 0.0229` are **absolute probability shifts**
`|Δp|`. They are different quantities on different scales, and calling 0.0016
"well outside" a scale that begins at 0.0032 was not merely incomparable — read
literally it was backwards. The two numbers may not be compared and the
comparison is withdrawn.

**Ground 1, rebuilt in RPS against RPS.** The only committed per-fixture
RPS-scale quantities for this corpus are paired-delta standard deviations, and
R-I2 already froze three of them. The demand the bar makes of the treated
population is a **mean** of 52 paired RPS deltas, so the like-for-like comparison
is with the standard error of that mean:

| scenario | paired SD (RPS) | SE of the 52-fixture mean | the bar `−0.0016346` in SEs |
|---|---:|---:|---:|
| A freshness-scale | 0.005262 | 0.000730 | **2.24** |
| B anchoring-scale | 0.014449 | 0.002004 | **0.82** |
| C mechanism-scale | 0.036 | 0.004992 | **0.33** |

**What that says, and it is weaker than round one claimed.** The bar sits at
about 2.2 standard errors of its own estimator under the optimistic scenario and
**inside one standard error** under both pessimistic ones. It is not "well
outside" the noise; under scenarios B and C it is inside it. This is R-I2's power
finding restated in the units the bar is written in, and it points the same way.

**There is no committed per-fixture RPS-unit re-seed noise figure for this
corpus**, only the pooled corpus-level shift of `+0.000075` — which *is* an RPS
quantity and *is* comparable, and which ground 4 already uses. The
`0.0032 / 0.0139 / 0.0229` triple keeps its one legitimate home: §3.1's movement
diagnostic, where it is compared with this experiment's own `|Δp|` between arms,
like for like. It justifies nothing about the bar and is removed from the bar's
justification.

**Ground 2 — Power. Stands**, and now carries ground 1 as well: R-I2's table is
the evidence that a materially lower bar would sit inside scenario B's noise and
a materially higher one is unreachable under every scenario.

**Ground 3 — Product. Corrected and narrowed.** Round one wrote "Product" and
argued only that this is a law change rather than an operational one. That
argument is sound and it stands, but it establishes **only that the freshness
discount to −0.00030 does not apply** — it is a floor argument, not a valuation.
**The product value of this rule is not quantified anywhere in this repository
and this experiment does not quantify it.** The one product-scale number in
sight — the 27.9%→15.9% relegation counterfactual — is ruled out of the evidence
base entirely by §1.2 and may not be borrowed here. Ground 3 is therefore
renamed **"Law, not cadence"** and claims nothing more.

**Ground 4 — System-level materiality. Stands as the concession it always was:**
a passing result is `−0.000037` pooled over the corpus, smaller in magnitude than
the `+0.000075` re-seed shift; this experiment cannot demonstrate a corpus-level
improvement and does not claim one. R-I3's required disclosure sentence for the
result document is unchanged, and the refusal to add a corpus-level materiality
*condition* is unchanged.

**What this experiment can claim, stated exhaustively so that nothing broader is
read into a pass.** On a pass at all four gates it may claim, and only claim:

1. that on **85 pre-specified thin-evidence fixtures** of the pinned corpus the
   re-keyed predicate changed the mean paired RPS by the reported amount, with
   the two reported intervals, at the power R-I2 states for the realised SD; and
2. that on the **16 pre-specified treated table cells** the paired ΔTRPS did not
   exceed `+0.0002` at MW6 or at any of MW0, MW3 and MW10, and that the MW6 mean
   was not resolvably positive.

**What it may never claim, on any result:** a corpus-level accuracy improvement
(ground 4); a quantified product value (ground 3 as corrected); anything about
Hull specifically at match level (§8, unchanged — one analogue, and it is in the
table leg); anything about the joint law, which no table metric here sees (§3.4);
or anything about a threshold other than `e* = 10.0` (§2.1's grid is reported and
never selected from).

---

### R2-I2 — the power simulation becomes committed code, with its grid and interpolation frozen

**Supersedes**, by quote, R-I2's implementation sentences:

> *"The bootstrap shortcut used for speed was asserted equal to the real
> function to 1e-15 before any number was reported, and the block counts it
> produces are 62 and 6. R = 2,000 replicates, simulation seed 20260827."*

The defect is real. R-I2's six power numbers were produced by uncommitted
scratch code. Their correlated-Gaussian construction, their correlation scope,
their MDE search grid, their interpolation rule, their tie rule and the claimed
`1e-15` shortcut equivalence exist nowhere a reader can run. A preregistration
that publishes six deciding-adjacent numbers from code no one can execute is
doing the thing it exists to stop.

**The module and the CLI, named and frozen.** The power simulation becomes part
of the committed harness — which §6 closes to two files, so it lands in the only
place it can:

| | |
|---|---|
| module | **`epl/evwiden.py`** |
| function | **`epl.evwiden.power_simulation()`** |
| CLI | **`python -m epl.evwiden --power`** |
| tests | **`epl/tests/test_evwiden.py`**, which asserts the frozen structure, the bootstrap equivalence below, and the six published rows |
| writes | **nothing.** It prints the table and emits the `power` object that `reports/evidence/widening.json` carries |

Both files are already in §6's hash table, so freezing the power code costs no
new hashed file and no lock-chain exposure.

**The construction, frozen.**

* **Structure** (unchanged, from R-I2): 85 fixtures, 52 treated, 62 week blocks,
  6 seasons; by season 26 / 11 / 12 / 12 / 12 / 12 with treated
  21 / 4 / 7 / 6 / 7 / 7. Untreated deltas are **exactly 0.0**, never noisy, as
  the ADD design makes them.
* **Noise.** For a treated fixture *i* in week block *b*, the delta is
  `δ + s · ( sqrt(ρ)·u_b + sqrt(1−ρ)·z_i )` with `u_b` and `z_i` independent
  standard normals — an equicorrelated Gaussian whose correlation scope is **the
  week block and nothing else**. Season correlation is not modelled and is not
  claimed; ρ ∈ {0, 0.5} brackets it.
* **Scenarios.** A `s = 0.005262`, B `s = 0.014449`, C `s = 0.036`, sourced as
  R-I2's table states.
* **Replicates.** `R = 2,000`, simulation seed **20260827**, one
  `numpy.random.default_rng(20260827)` consumed in scenario order
  (A ρ=0, A ρ=0.5, B ρ=0, B ρ=0.5, C ρ=0, C ρ=0.5), and within a scenario one
  noise draw per replicate **reused across every grid point of δ** — common
  random numbers, so the power curve is monotone in δ up to Monte-Carlo error
  and the interpolation below is not reading noise.
* **Gates.** All three deciding match gates exactly as §4.1 states them, using
  `epl.score.block_bootstrap_ci` at `B = 10,000`, `alpha = 0.05`, seed
  **20260814**, on the 62 week blocks and on the 6 seasons.
* **The bootstrap shortcut.** The committed implementation calls
  `epl.score.block_bootstrap_ci` directly. A vectorised inner loop is permitted
  **only** if a committed test asserts that its `(lo, hi, n_blocks)` equals the
  protected function's on the frozen structure, at three named noise draws, to
  `1e-15` — and reports `n_blocks` of 62 and 6. Absent that test, the shortcut
  is removed, not trusted.

**The MDE search grid and interpolation, frozen.**

* **Grid:** `δ ∈ {0, −0.0002, −0.0004, …, −0.0200}` — 101 points, step
  `2e-4`, δ the injected **treated-fixture** effect in RPS.
* **Power at a grid point:** the fraction of the R replicates at which **all
  three** deciding match gates pass.
* **MDE80:** scanning from `δ = 0` downward, the **first** adjacent pair of grid
  points that brackets power 0.80 is taken, and the MDE is the **linear
  interpolation in δ** between them. **Tie rule:** if a grid point's power is
  exactly 0.80, that grid point is the MDE and no interpolation is done.
  **Exhaustion rule:** if power does not reach 0.80 anywhere on the grid, the
  MDE is reported as `< −0.0200` with no interpolated value, and the table says
  so rather than extrapolating.
* **Reported scale:** the estimand's — the treated effect × 52/85 — as R-I2
  states.
* **Power at the bar** is evaluated at `δ = −0.0016346153846153847` exactly
  (`0.0010 × 85 / 52`), which is not on the grid and is not interpolated from
  it: it is its own evaluation at the same seed and replicates. **Power at 2× the
  bar** likewise, at `δ = −0.0032692307692307695`.

**The published numbers are provisional until the committed code reproduces
them.** R-I2's six-row table stays exactly as published — it is not restated,
not adjusted and not removed — under this binding condition:

> **These six rows are to be reproduced by the committed implementation before
> the freeze commit. If they do not reproduce, this section's numbers are
> corrected by a dated note appended to this document BEFORE the freeze
> commit**, stating the scratch value, the reproduced value, and what in the
> frozen construction above the scratch code did differently. No freeze block
> may be rendered while an unreproduced power number stands in this document.

That note, if it is needed, is a pre-freeze correction and is permitted: it lands
before the first real fit, so R-B6 is not yet in force and nothing has been
observed. After the first real fit, R-B6 forbids it absolutely — which is why
this must be settled now.

**R-I2's ruling is unchanged and is not weakened by any of this.** Nothing in §4
moves; the bar stays −0.0010; and the frozen warning stands in its own words:
*"This design is underpowered against effects near its own bar unless the
realised paired SD comes in at or below the freshness scale… A MISS IS THEREFORE
SUBSTANTIALLY UNINFORMATIVE."*

---

### R2-Z — what round two does not change

Unchanged and still binding: the rule of §2.1 and its one frozen constant
`e* = 10.0`; ADD-not-REPLACE and binary-not-continuous; α = 0.5 and mechanism
(c); the populations 85 / 52 / 51 / 78 and the table's 16 / 19; the seeds 20260611,
20260814 and 20260827; `B = 10,000`; `MC_BOOT = 2,000`; `n_sims = 20,000`; §4.1
clauses (i), (ii) and (iii) and their bars; the repaired gate (iv)'s three parts
and its `+0.0002` tolerance; the conjunction "ALL FOUR"; §4.4's publish-either-way
and its refusal to re-litigate a miss; §4.5's shadow-first adoption and the owner
ruling that alone can take it; §6's closed write set and the lock check; §7's
invalidations including the six R-B6 added; §8's disclaimers as R-M4 repaired
them; and the fact that no secondary, stratum or grid point decides anything.

**§7 gains one further invalidation:** gate (iv) evaluated with an MC estimator
that is not the jointly-resampled, tie-aware estimator of R2-B3 — including any
estimator that combines per-cell standard errors in quadrature, any estimator
built on `.order`, and any run whose 16 deciding cells do not share a common
`n_particles`.

---

### Supersession index — complete, both rounds

Every clause either repair round supersedes, by section and by quote. A clause
appearing twice is superseded by the later row.

| # | superseded clause, located | quoted opening | superseded by |
|---:|---|---|---|
| 1 | §2.3, the `Arm B` bullet | *"the probabilities and RPS **already in the corpus**… Not recomputed."* | R-B1 |
| 2 | §2.3, the `The delta` bullet | *"`rps(A) − rps(B)` per fixture…"* | R-B1 |
| 3 | §3.2, its role as one leg of the contrast | *"Every fitted opening's incumbent-predicate predictions must reproduce…"* | R-B1 (demoted to external control) |
| 4 | §4.1 clause (iv) | *"the pooled mean paired ΔTRPS (treatment − control, equal weights over the 35 cells) is ≤ +0.0002"* | R-B2 |
| 5 | §3.3, its "pooled" language | *"pooled"* | R-B2 |
| 6 | §3.4, the pooled-per-label line | *"pooled Δ per cutoff label"* | R-B2 |
| 7 | §4.3 in its entirety | *"The table gate's tolerance is invented, and says so"* | R-B2 (reissued) |
| 8 | §4.1, the table CI phrase | *"95% season-block CI (7 blocks)"* | R-B3 |
| 9 | §3.3, its silence on Monte-Carlo error | — (an omission) | R-B3 |
| 10 | R-B3, the tally bullet | *"built from `SimRun.retained_rows.particle` and `.order`"* | **R2-B3** |
| 11 | R-B3, the quadrature sentence | *"The MW6 mean's MC SE is `sqrt(Σ_c se_c²) / 7`…"* | **R2-B3** |
| 12 | R-B3, the precision rule's two conditions | *"`mc_se_mean > 0.25 × 0.0002 = 5e-5`, **or**…"* | **R2-B3** (P1–P6) |
| 13 | §3.3, the sufficiency claim | *"reproduces `simretro`'s schedule through `simretro`'s own public surface"* | R-B4 |
| 14 | §5.1, the undefined "table digest" | *"table digest"* | R-B4, then **R2-B4** (split in two) |
| 15 | R-B4, digest item 9 | *"the provisional set actually carried by the book."* | **R2-B4** (excluded; becomes a compared field) |
| 16 | R-B4, the cross-reference | *"**The two-sided cell identity is required** — see R-H(4)."* | **R2-B4** (re-stated on `sampler_digest`) |
| 17 | §2.4, the table-leg budget | *"35 fits plus 70 runs of 20,000 simulated seasons — bounded by ~2 hours."* | **R2-B4** (70 fits, 105 simulations, ~4 hours) |
| 18 | §5.3, the pre-freeze sentence | *"Pre-freeze, no harness code touches the real archive, the real corpus, or the real ledger except to hash them"* | R-B5 |
| 19 | the introduction's synthetic-only clause | *"pre-freeze audit runs are permitted on synthetic corpora only… Not one fit on the real archive precedes the freeze commit."* | **R2-B5** |
| 20 | §6 step 4 in its entirety | *"Any change to a hashed file thereafter requires a dated note…"* | R-B6 |
| 21 | §0.1, the configuration row | *"`epl.freeze.frozen_wcmodel_config()` — `seed` **20260611**, `windows.decay_half_life_days` **365**…"* | R-I1 |
| 22 | §5.1, `ConfigNotFrozen`'s conditions | *"`epl/config_frozen.json` is not `9f2e086d…`, seed ≠ 20260611, or widening ≠…"* | R-I1 |
| 23 | §2.3, the power sentence | *"**No power claim is made in advance.**"* | R-I2 |
| 24 | §1.4, its implicit claim to be a power analysis | *"The power problem, computed before the design was chosen"* | R-I2 |
| 25 | R-I2, the implementation sentences | *"The bootstrap shortcut used for speed was asserted equal to the real function to 1e-15…"* | **R2-I2** |
| 26 | §4.2, the authority sentence | *"The full bar applies, **on the preregistered population**."* | R-I3 |
| 27 | R-I3, ground 1 | *"**Noise.** The corpus-level re-seed shift is +0.000075 and the per-match ADVI re-seed scale is mean 0.0032…"* | **R2-I3** |
| 28 | R-I3, ground 3's name and reach | *"**Product.** The rule changes the published law on the fixtures it touches (§4.2), which is what the full model-change scale protects"* | **R2-I3** (renamed "Law, not cadence") |
| 29 | §5.3, the evidence canary's mutation | *"corrupt every archive row"* / *"corrupt rows before the cutoff"* | R-I4 |
| 30 | §5.3 and §6 step 1, "synthetic corpora only" | *"seeded defects and canaries on synthetic corpora only."* | R-I5 |
| 31 | R-I5, the generator and ancestry sentences | *"The generators are `_archive()` and `_corpus()`… a test asserts that none of the four appears…"* | **R2-I5** |
| 32 | §6, the evidence-contract table | *"the verdict verbatim: estimand, all four gate values, both CIs…"* | R-I6 |
| 33 | R-I6, the MANIFEST paragraph | *"each shard ledger, the merged fit ledger and the table ledger… it is a list."* | **R2-I6** (eleven named paths, `SHARDS = 4`) |
| 34 | §2.3, the union phrase | *"the `e* < 12` union"* | R-M1 |
| 35 | §5.3, the direction-canary bullet | *"Every treated grid must equal `inflate_predictive(base_grid, is_provisional=True, strength=0.5)` exactly, and carry strictly higher entropy than its base"* | R-M2 |
| 36 | §2.1, the LOSO precedent | *"stricter than the prequential-selection precedent (anchoring's LOSO)"* | R-M3 |
| 37 | §8, the first bullet's closing sentence | *"the value of the re-key **on the fixtures the re-key touches**."* | R-M4 |
| 38 | §3.2, the support citation | *"(`point_in_time_canary`, `verify_fast_path_is_inert`)"* | R-M5 |
| 39 | R-H(2), the first-act sentence and its blockquote | *"The **first post-freeze act** of this experiment is:"* | **R2-H** |
| 40 | R-H(2), the R-B6-in-force paragraph | *"**This is a real fit on the real archive.** It runs after the freeze commit, and from the moment it completes **R-B6 is in force**…"* | **R2-H** (in force at the results canary) |
| 41 | R-X, the inventory count | *"The inventory is therefore **twenty-three** types."* | **R2-X** (23 named refusals, 24 classes; UNRESOLVED is not a refusal) |
| 42 | the round-one preamble, the guard sentence | *"and the harness's own guards refuse to produce one until the freeze block is committed."* | **R2** standing paragraph (withdrawn as false) |

*Repaired 2026-08-27, round two: before the freeze commit, before the first real
fit, before the harness revision that these repairs oblige, and before any delta
of this experiment existed anywhere. Round one's repairs stand except where a row
of the index above supersedes them; the harness implements neither round yet, and
§6's freeze block may not be rendered until it implements both.*

---

## Dated note — 2026-08-28, before the freeze commit: the six power rows corrected, as R2-I2 prescribed

R2-I2 ordered: *"These six rows are to be reproduced by the committed
implementation before the freeze commit. If they do not reproduce, this
section's numbers are corrected by a dated note appended to this document
BEFORE the freeze commit."* They did not reproduce exactly, and this is that
note. No freeze block has been rendered; no real fit of this experiment has
run; the correction conditions on no outcome — a power simulation reads only
the frozen SDs and the frozen 85/52/62/6 structure, which the committed
implementation recomputed from the pinned artifacts and matched exactly
(by season 26/11/12/12/12/12, treated 21/4/7/6/7/7).

**What the scratch code did differently:** R2-I2 froze R = 2,000, both seeds,
the scenario order, and CRN-across-delta — but not the order in which the
block effects `u_b` and the fixture effects `z_i` are consumed inside a
replicate, nor the fixture-to-block assignment beyond its counts. The scratch
stream is therefore unrecoverable, and exact reproduction was never
attainable. The committed implementation freezes the consumption order (per
scenario: `u = rng.standard_normal((R, n_blocks))` then
`z = rng.standard_normal((R, n_treated))`, documented at
`epl.evwiden.power_simulation`), and its numbers are now the document's
numbers. Every difference is inside Monte-Carlo error at R = 2,000
(SE ≈ 0.011 at p ≈ 0.45; ≈ 0.007 at p ≈ 0.10), and the MDEs agree to
0.02–1.2%: the construction reproduced, the stream did not.

**The corrected table (supersedes the six rows of the R-I2 table above;
scratch values retained for the record):**

| Scenario | ρ | power@bar scratch → corrected | MDE(estimand) scratch → corrected | ratio | power@2× scratch → corrected |
|---|---|---|---|---|---|
| A freshness-scale | 0.0 | 0.461 → 0.451 | −0.001440 → −0.001446 | 1.45× | 0.977 → 0.976 |
| A freshness-scale | 0.5 | 0.425 → 0.408 | −0.001553 → −0.001571 | 1.57× | 0.944 → 0.950 |
| B anchoring-scale | 0.0 | 0.103 → 0.122 | −0.003738 → −0.003741 | 3.74× | 0.326 → 0.321 |
| B anchoring-scale | 0.5 | 0.103 → 0.091 | −0.004160 → −0.004180 | 4.18× | 0.274 → 0.267 |
| C mechanism-scale | 0.0 | 0.058 → 0.050 | −0.009200 → −0.009309 | 9.31× | 0.083 → 0.087 |
| C mechanism-scale | 0.5 | 0.044 → 0.047 | −0.010635 → −0.010522 | 10.52× | 0.081 → 0.080 |

The R2-I2 conclusions stand unchanged and slightly strengthened: the design
remains underpowered against effects near its own bar under scenarios B and C
(now 0.091–0.122 at the bar under B), and the POWER_WARNING's required
sentence for a miss is unaffected.

**Attestation coverage (recorded here so the R2 attestation is complete):**
during test construction of the conformance round, before the `assert_may_fit`
guard landed at b112b51, two evidence tests invoked the real parity path and
protected `simretro.ArchiveRunner` performed real ADVI fits before crashing on
`epl.particles.ExcludedMassTooLarge` (man_city v sheffield_united, 2019/20
MW0). Those fits ran through the protected retro machinery, not through this
experiment's treatment path; they produced no delta, no ledger row and no
artifact of this experiment (`data/epl/fit/evwiden*` and
`data/epl/sim/evwiden*` do not exist; the shared store's
`results.parquet` is byte-untouched, mtime 2026-08-14). The guard now refuses
exactly this invocation, and the tests stub the oracle. The "no fit of this
experiment anywhere" attestation is made WITH this event on the record.
