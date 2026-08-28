# Evidence-mass widening — preregistration v3 of the provisional re-key experiment

**Written:** 2026-08-28 · **Branch:** `main` · **Schema:** `epl-evwiden-3`
**Supersedes:** [`reports/epl_widening_prereg_v2.md`](epl_widening_prereg_v2.md)
(v2), which **cannot be run as written** — its own §8.2 pass 7 was executed on
2026-08-28 and measured three of its mandatory thirty-five parity cells as
unpriceable on the shipped stack (§0.6). v2 is retained as lineage and decides
nothing; so is
[`reports/epl_widening_prereg.md`](epl_widening_prereg.md) (v1), invalidated the
same day under v1's own R-B6 (§8.1).
**Queued by:** the owner-pinned standing queue ("Hull widening") and the design
record `docs/superpowers/specs/2026-08-25-evolving-model-design.md`, Part 5
hypothesis 1 ("key widening on effective evidence mass, not promotion
category") and its v2 ruling: *"co-priority-2 RESEARCH (effective-evidence
walk-forward + table retro) — NOT shipped this season without it."* This
document is that research, both legs, preregistered.

**What this document is.** One coherent statement of the complete law of this
experiment: the rule, its one frozen constant, the estimand, the resampling,
the secondaries, the four-part adoption rule, the Monte-Carlo estimator and its
precision regime, the refusal semantics, the lifecycle, the evidence contract
and the scope. **There are no repair sections and no supersession index INSIDE
this document, because there is nothing inside it to supersede.** (This document
does supersede v2 and v1; that is a different statement and it is made in the
metadata above.) Every clause below is the operative clause. Where this document
is silent, nothing is implied.

**What it inherits.** Its substance is v2's law exactly as v2 stood at its last
commit — every ruling v2's four review rounds and two in-tree adversarial audits
reached is carried here as ordinary text — with the table leg's census replaced
by the one v2 §8.2 pass 7 **measured**, and with the residual findings that were
still open against v2's harness ruled as law here rather than left to the code
(§8.5, §8.6). The findings are named where they bite, so that a reader can check
the fix against the finding.

**Status.** The harness `epl/evwiden.py` and its tests
`epl/tests/test_evwiden.py` exist, are green, and implement **this** document;
§8.3 forbids rendering a freeze block until §8.5's conformance report is green on
behavioural predicates **produced by an independent pytest artifact**, and until
an independent dual audit reports no blocking finding.
**No estimand of this experiment has ever been fitted**: no
`data/epl/fit/evwiden*` or `data/epl/sim/evwiden*` file exists, no delta exists,
no evidence file exists, no verdict exists — §8.8 states that attestation in full,
with the qualifications it carries. Real ADVI fits *have* occurred on the
protected retro machinery: two during v1's conformance work, which killed v1, and
thirty-five during v2's authorised pass 7, which produced the census this document
is written against. Both events are named by name in §8.1 and counted in §2.4,
and this document is written with them on the record rather than around them.

Like its three predecessors — [`reports/epl_anchoring_prereg.md`](epl_anchoring_prereg.md)
(1b52623), [`reports/epl_freshness_prereg.md`](epl_freshness_prereg.md)
(5ba83e7), [`reports/epl_sim_prereg_retro.md`](epl_sim_prereg_retro.md)
(07b5871) — this preregistration precedes the run it binds, and its harness
hashes are frozen by a follow-up commit before the first fit of **this**
document. §8 says exactly what that commit must contain and exactly what order
must follow it.

Every number in §0–§3 was computed from the pinned artifacts by the recipes
given beside it, by read-only passes that fit nothing and simulate nothing.
Where a motivating number **cannot** be independently re-derived from committed
artifacts, that is stated (§1.2 — the reader should not skip it).

---

## 0. What is pinned

### 0.1 The corpus, the archive, and the configuration

| | |
|---|---|
| Corpus | `data/epl/fit/walkforward_predictions.parquet` |
| SHA-256 | `f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a` |
| Rows | **2,280** — 6 seasons × 380; seasons 2019/20 … 2024/25; blocks `(season, ISO week)` **212** |
| Outcome counts (`y` = 0/1/2) | 993 / 525 / 762 — adopted from `epl/recalfit.py:91-98` (A8), as all predecessors adopt them |
| Walk-forward ledger | `data/epl/fit/walkforward_ledger.jsonl`, SHA-256 `869a558ce7f84ef0f4a4ebdd8f781a4a72213fd5946b4e7088d716d99e82ba9e` — 212 rows, one per block opening, each carrying `provisional_teams` and `cold_start_teams` **as the published fits actually computed them** |
| Archive | `data/epl/matches.parquet`, SHA-256 `323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf` — **4,560** matches, 12 seasons 2014/15 … 2025/26, 380 per season |
| Frozen config file | `epl/config_frozen.json`, SHA-256 `9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc` |
| **Realised config** | `realised_config_sha256` = SHA-256 of `json.dumps(freeze.frozen_wcmodel_config(), sort_keys=True, default=str)` = **`78a51cd92c48838a57e3d6832b7661aad7a5b231425572214a067c2a35edbdcd`** |
| Table-retro anchor | `data/epl/sim/retro_r1.jsonl` (**protected, read-only**) and `epl.simretro`'s public constants: `SEASONS` (7, 2019/20 … **2025/26**), `COMPARISON_CUTOFFS` (MW0/MW3/MW6/MW10/MW19), `DEFAULT_N_SIMS` **20,000**, `SEED` **20260611** |
| **Feasibility census** | `data/epl/sim/evwiden_parity_feasibility.json`, SHA-256 **`07ee00d798cb0f01f29bc5bb5ba885c41e26d5494e9755c73a038a2777bad329`**, 18,128 bytes — v2 §8.2 pass 7's record, executed 2026-08-28 at HEAD `9adc3bc`. **This document's table leg is scoped by it** (§0.6, §3.3), so it is a pin and not a citation: `FeasibilityRecordMismatch` fires when its bytes move |

Verify with:

```
shasum -a 256 data/epl/fit/walkforward_predictions.parquet \
              data/epl/fit/walkforward_ledger.jsonl \
              data/epl/matches.parquet epl/config_frozen.json \
              data/epl/sim/evwiden_parity_feasibility.json
```

The census record is gitignored like everything under `data/`, and §8.6 is plain
about what that means: its digest is bound **into the committed freeze block**,
so a reader checks the block, not the file. A record whose bytes differ from the
block's is refused; an absent record is refused; and neither is treated as
"nothing to check" (§7.1).

**Why the realised digest and not only the frozen file.**
`epl.freeze.frozen_wcmodel_config()` loads the **live** `config/config.yaml`
and overlays only the frozen EPL Elo block (`epl/freeze.py:417-424`). A digest
of `epl/config_frozen.json` alone binds neither the decay half-life — which
*defines* `e` (§0.3) — nor the volatility window from which `e* = 10.0` is
taken, nor the likelihood, nor the ADVI inference block. Drift in any of them
would change `e`, the posteriors, or reproducibility while a check on the
frozen file passed. `realised_config_sha256` binds all of them:
`windows.decay_half_life_days = 365`, `elo.volatility_window = 10`,
`model.widening = {mechanism: c, strength: 0.5}`,
`model.inference = {backend: advi, draws: 1000, tune: 1000, advi_iters: 30000}`,
and `seed = 20260611`.

`ConfigNotFrozen` (§7.1) fires on **four** conditions: the frozen file's
digest, the realised seed, the realised widening block, and this realised
digest. Every ledger row carries both `config_sha256` and
`realised_config_sha256`, so a reader can tell which moved.

The corpus is read-only to this experiment; three standing preregistrations
already check its digest (`epl/recalfit.py`, `epl/freshsweep.py`,
`epl/mktprior.py`). The archive digest is pinned here because — unlike in the
freshness and anchoring experiments — the archive is an **input to the
predicate under test**, not only to the fits: the effective-evidence quantity
of §0.3 is a sum over its rows. A parquet whose bytes have moved is a different
predicate input, and `ArchiveDigestMismatch` refuses it.

### 0.2 The incumbent predicate, read from the code

Mechanism-(c) widening is a **predict-time** mix and nothing else. At predict
time (`src/wcmodel/model/draw_api.py`, `production_grid` → `finalize_grid`), a
fixture is widened iff either club is in `posterior.provisional_teams`, by one
call to `inflate_predictive(grid, is_provisional=True, strength=0.5)` — the
mean-preserving-in-expected-goals mix toward the exponentially-tilted
max-entropy product grid (`src/wcmodel/model/widening.py:109-183`). Under
mechanism (c) the likelihood weight is untouched: `likelihood_weight` copies
`d.weight` and modifies it only for mechanism "a" (`widening.py:48-62`). **The
fitted posterior is therefore identical for any provisional set**, which is the
fact the whole design below stands on.

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
"flags nobody" half at scale: over the 212 scored cutoffs, 39 cutoffs carried a
provisional club, 45 team-cutoff flags fired — **13 from the volatility arm**
(Aston Villa, Brighton, Leicester) and 32 from the few-games arm (the six
cold-start clubs). The volatility arm is live, and §2.1 rules accordingly.

### 0.3 Effective evidence — the quantity, defined once

For a club `t` and cutoff `C` (midnight):

```
e(t, C)  =  Σ  0.5 ** (age_days / 365)     over archive matches of t with date < C,
                                            age_days = (C − date) in whole days
```

This is **the fit's own likelihood weight**, not a new number:
`src/wcmodel/data/features.py:297` computes
`decay_weight = 0.5 ** (age_days / half_life)` with `half_life = 365`, and
`src/wcmodel/model/panel.py:34-36` renames it to the panel's `weight` — the
weight every training match carries in the likelihood. `e(t, C)` is the summed
weight of the club's own matches: **how much decayed evidence about this club
the likelihood actually holds.** It is venue-blind, covers every archive row
(deliberately **not** restricted to `in_feature_window` — the likelihood is
not), is computed on the same played frame the fit trains on, and is recomputed
at every cutoff, so it drifts upward within a season as the club plays. Units:
match-equivalents at full weight.

Strict `date < C` is binding: a match dated on or after its own cutoff
contributing to any `e(t, C)` is `EvidenceLeak`, and §7.3's evidence canary
proves the code rather than the claim.

### 0.4 The blindness, measured at the live opener and across the corpus

At the 2026/27 opener (cutoff 2026-08-21), recomputed from the pinned archive
and confirmed against `count_volatility_arm` run mechanically on the same store
and frozen config:

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
`reports/epl_matchboard_2026_27_2026-08-21_derived.md` records **"38 of the 380
fixtures carried provisional widening"** — Coventry's 38 exactly; Hull's 38 got
none.

Across the pinned corpus (4,240 club-cutoff cells = 20 season clubs × 212
cutoffs; widening status from the ledger's own `provisional_teams`):

| quantity | value |
|---|---|
| `e` per cell: min / p1 / p5 / median / max | 0.00 / 5.70 / 18.76 / 51.97 / 60.21 |
| cells with `e < 3` | **25 — every one already widened** (cold-start clubs) |
| cells with `e < 1` | 13, all already widened |
| fixtures carrying incumbent widening | **46 of 2,280 (2.02%)** |

**No cell in the scoring window is Hull-shaped**: thin evidence without widening
does not occur there. Where it does occur is §1.1.

### 0.5 The archive's thin-history census, and the one true analogue

Promoted club-seasons 2015/16–2025/26: **33** (11 openers × 3), of which **15
are cold-start** (zero archive rows — already widened at their opener) and **18
are returning**. Effective evidence of every returning promoted club at its own
opener:

| | | | |
|---|---|---|---|
| 2016/17 burnley 12.66 | 2016/17 hull 12.67 | 2017/18 newcastle 18.95 | 2019/20 aston_villa **4.74** |
| 2019/20 norwich **3.15** | 2020/21 fulham 11.77 | 2020/21 west_brom 11.09 | 2021/22 norwich 13.87 |
| 2021/22 watford 24.81 | 2022/23 bournemouth 12.59 | 2022/23 fulham 16.40 | 2023/24 burnley 25.71 |
| 2023/24 sheffield_united **9.84** | 2024/25 leicester 25.43 | 2024/25 southampton 25.32 | 2025/26 burnley 18.96 |
| 2025/26 leeds 11.17 | **2025/26 sunderland 0.172** | | |

**Exactly one historical club-season matches the Hull pattern** (raw ≥ 5,
`e` < 1): Sunderland at the 2025/26 opener — 114 raw matches, last played
2017-05-21, `e` = 0.172. Verified mechanically: `count_volatility_arm` at
2025-08-15 returns games 114, recent_volatility 8.737, both flags False —
**not provisional, zero widening**, the Hull configuration one season early.
2025/26 is outside the walk-forward corpus (excluded by `epl/windows.py` for
odds-coverage bias, a reason that does not bear on this market-free question)
and **inside** `epl.simretro.SEASONS`, where `allow_excluded=True` is passed
explicitly and stated in the module docstring. **The table-retro can see the one
true analogue; the match-level walk-forward cannot.** That asymmetry shapes the
whole design and is confronted in §1.4 rather than discovered by the run.

### 0.6 Why there is a v3: the measured census, and the three cells the stack cannot price

**v2 was not narrowed. v2 was executed against, and it lost.**

v2's §3.3 made a 35-cell parity oracle — protected
`epl.simretro.ArchiveRunner` at `dc_native`, every cell of
`SEASONS × COMPARISON_CUTOFFS` — a **mandatory** leg, and v2's §8.2 authorised
**one** pre-freeze pass, prospectively and by name, to find out whether the
shipped stack could actually run it. That pass was written as an *enumeration*
rather than a first-crash probe precisely so that a successor document would have
something to be written against. **It was executed once, on 2026-08-28**, opened
14:50:24Z and closed 14:54:37Z, at HEAD `9adc3bc`, into a quarantine outside the
repository which was deleted when it closed; all thirty-five cells were attempted
under `run_retro`'s own typed per-cell contract; `cells_expected: 35`,
`cells_attempted: 35`, `completed: true`, `error: null`, `feasible: false`. Its
record is §0.1's pinned `data/epl/sim/evwiden_parity_feasibility.json`, SHA-256
`07ee00d798cb0f01f29bc5bb5ba885c41e26d5494e9755c73a038a2777bad329`.

**Thirty-two cells price. Three do not.** All three refuse with the same typed
kind — `excluded_mass_ceiling`, raised as `epl.particles.ExcludedMassTooLarge`
against the 0.02 ceiling pre-stated in amendment A1 — and every one of them is a
Manchester City fixture against a promoted side:

| cell | refusal kind | fixture the protected code names | particle-mean excluded mass | ceiling |
|---|---|---|---:|---:|
| **2019/20 MW0** | `excluded_mass_ceiling` | man_city v sheffield_united | **0.0234** | 0.02 |
| **2020/21 MW0** | `excluded_mass_ceiling` | man_city v leeds | **0.0216** | 0.02 |
| **2023/24 MW3** | `excluded_mass_ceiling` | man_city v luton | **0.0328** | 0.02 |

No fourth cell refused, none of the three was cleared, and no cell failed as
`runner_error`. The refusal is a **capability limit of the shipped model**, not a
defect in this experiment's invocation of it: the 10-goal truncation discards
more probability mass than A1 permits, the run fails closed rather than quietly
dropping the tail, and the investigator's verdict on the finding that predicted
this was REAL-REGRESSION against the protected stack rather than against the
harness.

**v2's own pre-stated ruling then decided what happens next**, and it decided it
before the pass ran, which is the only reason this document may exist at all:

> *"If any cell is unpriceable — one is enough — then a mandatory leg of this
> experiment cannot be executed on the shipped stack, **this preregistration
> cannot be run as written**, and the remedy is a NEW preregistration (v3) whose
> table leg is scoped to what the protected runner can actually do. Not a quiet
> narrowing of the 35 cells here."* (v2 §8.2)

That is this document. **It was never open to v2 to shrink its own oracle after
the measurement** — v2's §2.4 and §10 both make dropping a cell an amendment
rather than an optimisation, and the census moves §3.3's constants, §4.1's
comparative ground for the deciding horizon, §5.2's tally count, §2.4's budget
and §9.3's manifest with it. Rewriting all of that inside v2, after its own pass
had produced a number, is exactly the discretionary post-hoc channel the whole
lifecycle exists to close. So v2 was closed, and this document was written against
the census instead. **The narrowing is measured, not chosen**, and the measurement
is pinned by digest so a later reader can check it rather than take it.

**What the census does to this design, in one place.**

| quantity | v2 | **v3** |
|---|---:|---:|
| table cells | 35 | **32** |
| treated cells | 16 | **15** |
| untouched cells | 19 | **17** |
| cells by label | MW0 7, MW3 7, MW6 7, MW10 7, MW19 7 | **MW0 5, MW3 6, MW6 7, MW10 7, MW19 7** |
| treated by label | MW0 3, MW3 2, MW6 7, MW10 4, MW19 0 | **MW0 2, MW3 2, MW6 7, MW10 4, MW19 0** |
| deciding tallies (§5.2) | 32 | **30** |
| parity-oracle rows | 35 | **32** |
| MANIFEST paths (§9.3) | 52 | **49** |
| post-freeze fits / simulations | 153 / 105 | **147 / 96** |

**The one thing that was not guaranteed in advance, and survived.** Exactly one
of v2's sixteen treated cells is lost — **2019/20 MW0**; the other two refusals,
2020/21 MW0 and 2023/24 MW3, were untouched cells and cost the design nothing but
denominator. **MW6 is 7 of 7 priceable and 7 of 7 treated, and it remains the
ONLY all-treated label** (MW0 2/5, MW3 2/6, MW10 4/7, MW19 0/7). §4.1's stated
comparative ground for naming MW6 the deciding horizon — *"the only horizon at
which the do-no-harm question is asked with no structural zero in the
denominator"* — therefore survives the census **intact and unchanged**, and it was
named in v2 before any of this was measured. Had MW6 lost a cell, the deciding
horizon would have had to be re-argued after a measurement, and this document
would not have been writable without the appearance of choosing a horizon to suit
a census. It did not, and the horizon is carried across unmoved.

**The three excluded cells are excluded by measurement and by nothing else.**
They are named here, named in §3.3, named in the freeze block, and named in §10:
adding one back is an invalidation, and so is dropping a thirty-third. A caller
cannot name them, reach them or restore them — the oracle takes no cell list
(§3.3's closure 2), and §8.6's closure refuses a truncated deciding population
from every public surface.

---

## 1. The question, and the honest motivation

### 1.1 The finding

The predicate that decides predict-time widening is keyed on raw match count
and rating-delta volatility and is blind to the likelihood's own decay
weighting — so a returning club with a decade-old top-flight spell (Hull,
`e` = 0.0607) is treated as a well-known club while a true debutant (Coventry,
`e` = 0) is widened at α = 0.5. The candidate fix, as the design record states
it: **key widening on effective evidence mass, not promotion category.** The
quantity is already computed by every fit (§0.3); nothing reads it for widening.

### 1.2 The motivating counterfactual is an observation, not evidence — ruled

The number that elevated this work: counterfactually adding Hull alone to the
provisional set of the 2026-08-25 issuance — identical particles, streams,
seed, strength, ranker — moves Hull's relegation probability from **27.885%**
to about **15.9%** (the design record's v2 ruling: *"the Hull widening
counterfactual moves relegation 27.9%→15.9% — product-scale, not a patch"*);
the same counterfactual against the 2026-08-21 opener moved the recorded
**58.71%** by about six points. What could be verified was verified: the
2026-08-25 issuance's `output_dc_native.json` records `relegated p = 0.27885`
and its `fit.json` records `provisional_teams: ["coventry"]`; the 58.71% is
committed at `reports/epl_sim_issuance_2026-08-21.md` §4.

Three things are ruled about this number, here, before any fit of this
document:

1. **It is a motivating observation outside the evidence base.** It was
   computed on the live 2026/27 season — the very object a verdict would
   change. It is not the estimand, not a secondary, not an input to any gate,
   and the harness does not recompute it.
2. **It is a claim about forecast surgery, not accuracy.** Mean-preserving
   widening in expected goals does not preserve win probabilities or table
   position; moving a weak club's relegation probability by 12 points says the
   lever is product-scale, and says nothing about whether the moved number is
   better. The accuracy evidence is what this experiment exists to produce.
3. **Its provenance is weaker than this repository's standard, in two tiers.**
   The base sides are on this machine but gitignored (`git ls-files data/`
   returns nothing), so a reader of this repository cannot check the 27.885%.
   The **treated** sides — the 15.9% and its opener twin — exist only as the
   design record's prose: the counterfactual run that produced them was never
   committed as an artifact anywhere, and this document could not re-derive
   them without re-running the counterfactual, which it declines to do
   (point 1). They are quoted with that limitation named, and the evidence
   contract of §9 exists so that no number this experiment itself produces
   shares it.

### 1.3 The counter-hypothesis, stated before the run

**Widening Hull may be double-counting, not repair.** Hull's posterior is
already diffuse (points sd 14.11 vs 8.6–10.2, §0.4) *because* its effective
evidence is 0.06 — the hierarchical prior is already doing the work the
widening would claim to do. The design's own assumptions file rules that the
tournament simulator never applies (c) in-sim precisely because "re-widening
per draw would double-count the parameter uncertainty already carried by the
draw" (`ASSUMPTIONS.md:465-472`). A club whose predictive is already wide may
need no second widening, and adding one would push an honest interval past
honest.

§3.4 pre-states the diagnostic that could show this — per-club points-interval
coverage (`epl.simmetrics.interval_coverage`, cov50/cov90) for the treated
clubs, both arms — **with its reading direction fixed now**: if the control
arm's coverage for treated clubs already sits at or above nominal and the
treatment pushes it further above, that is evidence *for* double-counting and
*against* this rule, and the result document must say so in those words. No
sign is assumed.

### 1.4 The support census — where the rule bites, and where it cannot

This section counts **support**, not power. Power is §6, and §6 is a
simulation, not a census. The distinction is made here because v1's first
review found the two conflated.

The evidence-mass rule at any threshold near Hull's own 0.06 is **inert on the
pinned corpus**. Per candidate threshold `e*`, with "thin" meaning a fixture
whose thinner side has `e < e*` and "treated" the thin fixtures the incumbent
predicate does not already widen:

| `e*` | thin fixtures | already widened (delta ≡ 0) | **treated** | blocks holding a thin fixture |
|---:|---:|---:|---:|---:|
| 1 | 12 | 12 | **0** | 12 |
| 3 | 24 | 24 | **0** | 24 |
| 5 | 39 | 32 | 7 | 34 |
| 8 | 66 | 33 | 33 | 50 |
| **10** | **85** | **33** | **52** | **62** |
| 12 | 110 | 33 | 77 | 78 |

A threshold small enough to be "the Hull rule alone" (`e* ≤ 3`) changes **zero
of 2,280 fixtures**: a walk-forward at such a threshold cannot pass and cannot
fail — it can only print 0.000000. And any threshold large enough to move
fixtures is no longer a rule about decade-stale returners only; it is a rule
about **thin evidence in general**, whose historical bite is mostly the
cold-start clubs' matchweek-5-to-11 tail (raw count ≥ 5 switches the few-games
arm off while `e` is still single-digit) plus three genuinely thin returning
club-seasons.

This document therefore preregisters the **general rule** — thin evidence ⇒
widen, of which Hull is the extreme member — tests it at match level where it
has support, and tests the extreme member itself only where the archive holds
its one analogue: the table-retro's 2025/26 Sunderland cells (§3.3). Stated
bluntly so the run cannot discover it: **the match-level result, whatever it
is, is evidence about the rule family, not about Hull specifically.**

### 1.5 Why this is not the dead break-widening experiment

The design record's graves clause warns that "the ask must not re-run a dead
experiment under new vocabulary," and the nearest grave is I2 season-break
widening — closed at `reports/epl_v3_result.md` (peak −0.000058 mean RPS, 1.5×
the 0.000038 optimiser noise, 0.8% of headroom; "the question is now closed").
Three structural differences, stated for the reader who should ask:

* **Different trigger.** I2's trigger was a clock — matches since a squad
  break — that fires for *every* club *every* August and decays over weeks.
  This trigger is a fixed property of a club's whole archive history that fires
  for almost nobody: 51 club-cutoff cells across six seasons (§2.2),
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

What is honestly shared with I2 is the noise floor, and §4 inherits its lesson:
the effect is measured against pre-stated noise scales, and a result inside them
is a miss however suggestive the sign.

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

**ADD, not REPLACE — ruled, with the measurement that rules it.** A replacement
rule (`provisional = thin-evidence only`) would *remove* widening from the
volatility arm's clubs — Aston Villa (`e` 31.3–33.5), Leicester (48.4–49.6),
Brighton (51.0–57.5), all data-rich — stripping 22 fixtures of widening at
`e* = 3` (34 at `e* = 1`) and making the model **more** confident on the
historical corpus, the opposite of the motivating direction, while silently
retiring an arm that is live on 13 team-cutoff flags (§0.2). The few-games arm
is likewise kept: at raw counts 1–4 it fires before the evidence rule adds
anything, and removing it would change cold-start semantics this experiment has
no business touching. The evidence rule adds; it removes nothing.

**Binary, not continuous — ruled.** A continuous `α(e)` touches every fixture
and would need a per-fixture strength. The machinery exists
(`epl/improve.py:473-494` proves the exact `(1−s1)(1−s2)` composition;
`:688-710` is the sanctioned per-fixture override), but the shape is refused
here because it breaks three published identities for one experiment's
convenience: the envelope's scalar
`widening_mode = "per_fixture_bernoulli@alpha={g}"` (`epl/leaguesim.py:774-775`),
compared field-by-field by `simcli`'s provider-identity check and `simbundle`'s
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
the last 10 rating deltas; the anchoring preregistration §2.1 fixed its market
window at M = 10 by the same citation). The reading: **a club is evidence-thin
when the likelihood's entire decayed knowledge of it weighs less than ten fresh
matches.** What the constant separates, on the pinned archive: it catches every
Hull-analogue with a 58× margin or more (0.06–0.17 against 10) and misses every
continuously-present club by 5× (median cell 51.97). Its nearest decisions:
**caught** — Sheffield United 2023/24 (9.84: two archive seasons, the fresher
ending 27 months before its opener); **missed** — West Brom 2020/21 (11.09),
Leeds 2025/26 (11.17), Ipswich 2026/27 (12.52). That the config-derived
constant lands inside the archive's own gap between those two groups
(9.84 … 11.09) is a fact about the archive noticed **after** the constant was
chosen from the config, and it is disclosed as such; the grid's neighbours 8 and
12 straddle the gap and are reported (§3.1).

**No parameter is selected anywhere in this experiment.** The grid
`e* ∈ {1, 3, 5, 8, 12}` exists to be *reported*, never selected from: every
grid point's estimand analogue is published as a secondary with zero decision
weight (§3.1). This is not offered as stricter than any precedent — the nearest
thing this repository has to a prequential selector is the anchoring
experiment's **failed** leave-one-season-out attempt, whose own result document
rules the label false, because the information travelled through shared
training ancestry rather than through the fold split; it is a precedent for
nothing. The correct statement here is simpler and stronger: **this experiment
performs no outcome-based selection at all.** `e*` is fixed at 10.0 from the
config, the grid is reported and never selected from, and `epl.evwiden.adoption`
takes no grid argument.

The cost is equally frozen: **if `e* = 10` misses and a neighbour's secondary
looks better, that neighbour is selection-on-outcome, may not be adopted, and a
future preregistration that chooses it must say its choice was informed by these
numbers and carries exploratory standing only.**

### 2.2 The frozen membership

At `e* = 10` on the pinned corpus: **51 newly-flagged club-cutoff cells** (a
cell is any of the 4,240 of §0.4 with `e < 10` and no incumbent flag in the
ledger; **47 of the 51 sit in blocks where the flagged club itself plays**, and
those 47 are the flags that reach a fixture). They concentrate on nine
club-seasons — three returning-thin (aston_villa 2019/20, `e` 4.74 at the
opener; norwich 2019/20, 3.15; sheffield_united 2023/24, 9.84) and six
cold-start tails (sheffield_united 2019/20, leeds 2020/21, brentford 2021/22,
nottm_forest 2022/23, luton 2023/24, ipswich 2024/25 — each in the weeks after
its fifth raw match, while `e` is still below 10). For 2026/27 the rule widens
Coventry (already widened) and **Hull**, and does not widen Ipswich.

The status is **as-of-cutoff, recomputed at every cutoff** — a club leaves the
set as its evidence accumulates (a cold-start club crosses `e = 10` around its
eleventh match; Hull, entering at 0.06, would cross at the same pace, around its
own eleventh 2026/27 match) — preserving `ASSUMPTIONS.md:356-360`'s refusal to
widen a club forever.

The freeze commit (§8.3) pins the enumerated cells and fixtures by digest: the
85 thin fixture keys, the 52 treated keys, the 51 newly-flagged cells, the 78
fit openings, and the 15 treated / 17 untouched table cells of the 32-cell
priceable census, each serialised canonically and hashed. `MembershipMismatch` fires when a recomputation differs
from any of them.

### 2.3 The arms and the estimand

**The arm's name is `dc_evwiden`.** Ruled here; grep confirms no existing use.
It names the mechanism (evidence-keyed widening), collides with no benchmark
column, and — unlike `dc_1x2_recal` — defines a full scoreline law, so it can
carry a table (§4.5).

**Both arms come from one posterior.** At each of the **78 block openings whose
block holds a thin fixture at any grid point — the union through `e* = 12`
(that is, `e* ≤ 12`); the primary's 62 are a subset** — one fit runs through the
identical pipeline: `freeze.frozen_wcmodel_config()`, seed 20260611,
`epl.fit.build_store`, `epl.anchor.Anchor` with `freeze.frozen_elo_config()`,
`epl.dcfit.fit_epl` with `feature_cache_dir=paths.FIT_CACHE_DIR`,
`fast_panel=True`. From that one fitted posterior:

* **Arm B — `dc_native`** — the block's fixtures predicted from the fitted
  posterior under **the fit's own recomputed incumbent provisional set**. This
  is predict pass 1. Nothing about it is read from the corpus.
* **Arm A — `dc_evwiden`** — the same block's fixtures predicted from **the same
  posterior object** under the §2.1 union. This is predict pass 2. No refit, no
  re-seed, no second sampler call: the two passes differ only in the set handed
  to `provisional_as`.
* **The delta** — `rps(Arm A) − rps(Arm B)` per fixture, `epl.score.rps` on the
  corpus's `y`, both arms from the same posterior, rounded by the same
  `round(v, 8)`.

**Why one posterior and not the corpus.** Mechanism (c) acts on the **full
scoreline grid** before the 1X2 projection. Two grids can agree at eight
decimals after projection and respond differently to `inflate_predictive`, so
pairing a new fit's Arm A against the corpus's old rounded 1X2 row would assert
"same draws, only membership differs" about an object the control never bound.
Both arms now come from the same grid, and the pairing is mechanical rather
than argued.

**The corpus is an external identity control.** The stored `dc_home` /
`dc_draw` / `dc_away` / `dc_rps` enter the estimand nowhere. They remain §3.2's
control at full strength: all **820** fixtures of the 78 openings must equal
Arm B at their eight decimals (`ControlMismatch`), and each stored `dc_rps`
must equal the RPS of its own stored probabilities to 1e-12 (`ScoreMismatch`).
The per-fixture evidence file carries `delta` (Arm A minus Arm B) and
`delta_vs_corpus` (Arm A minus the stored row) side by side, so a reader can
confirm the equality rather than take it. Because the control demands
eight-decimal equality and stops the run otherwise, the two can differ by at
most the eighth decimal per fixture.

**A fixture outside the treated set whose Arm-A prediction differs from its
Arm-B prediction at 8 decimals is `UntreatedMoved` and stops the run** — the
treatment must touch exactly the fixtures the rule names, and no others.

> **THE ESTIMAND: the mean paired RPS delta, `dc_evwiden` minus `dc_native`,
> over the 85 thin fixtures of the pinned corpus at `e* = 10`. Negative means
> the re-keyed widening helps.**

* **The population is fixed at 85 and no fixture may be dropped.** Thin =
  min-side `e < 10` at the block cutoff. By season: 26 / 11 / 12 / 12 / 12 / 12
  (2019/20 … 2024/25). **33 of the 85 are already widened by the incumbent
  predicate and carry a delta of exactly 0.0 by construction** — stated now so
  the dilution cannot be discovered later: the estimand's sign equals the
  treated-subset (n = 52) mean's sign by arithmetic, at 52/85 of its size. The
  treated-subset mean is a pre-stated secondary, not the estimand, because
  "thin" is the rule and the rule includes fixtures it happens not to change.
* **The statistic** — the pooled mean over the 85 deltas.
* **The primary interval** — `epl.score.block_bootstrap_ci` (`epl/score.py:193`)
  on the 85 deltas, blocks = the corpus's own `block` labels (the **62** blocks
  holding a thin fixture), B = 10,000, percentile, `alpha = 0.05`, resampling
  seed **20260814**.
* **The season interval** — same function, same B, same seed, blocks = the **6
  seasons**. Both are reported; §4.1 requires both. The season interval's job is
  to refuse a result carried by one season, and the risk is real and quantified
  now: 2019/20 holds 26 of the 85 thin fixtures and 21 of the 52 treated ones.
* **The full-population secondary** — the mean over all 2,280 fixtures. Under
  ADD this is the estimand × 85/2280 **as an arithmetic identity** (untreated
  deltas are exactly zero), printed as context, never a gate.

**`B = 10,000` is frozen and is not overridable.** No CLI flag, keyword or
environment variable may pass a different `B`, `alpha`, block definition or
resampling seed into any deciding computation — the two match intervals, the
MW6 table interval of §5, or the power simulation of §6. A harness that accepts
one is not the harness this document preregisters. The same closure applies to
`n_sims` (20,000), the simulation seed (20260611), the chunk size, `MC_BOOT`
(2,000), `SHARDS` (4), `K` (200, §5.4) and `e*` itself.

**§8.6's public-surface closure is where that sentence is made mechanical**, and
it is stated there once for the whole harness rather than repeated per constant:
a production path RESOLVES `n_sims`, the simulation seed and the chunk size from
the modules §0.1 pins them in and carries no parameter for them at all; the
constants that keep a keyword refuse a different value; and every remaining
seam — an injected implementation, a lifecycle attestation, a truncated
population — is refused whenever the target artifacts are pinned or the
directories are the preregistered ones.

**The structural-zero guard is two-sided at the merge.** Every merged row that
is **not** in the treated set must carry a delta of exactly 0.0 — this covers
both classes, and both are refusals:

* a fixture whose `e_min ≥ e*` (outside the thin population entirely) carrying a
  non-zero delta; and
* a **thin but already incumbent-widened** fixture — one of the 33 §2.3 states
  "carry a delta of exactly 0.0 by construction" — carrying a non-zero delta.

A guard that catches only the first class leaves the arithmetic §2.3 relies on
unenforced, because the 33 are exactly the rows whose zero-ness makes the
85-population's mean a known multiple of the treated mean. Both classes raise
`UntreatedMoved` at the merge, and §8.5's conformance report exercises both.

### 2.4 The compute budget, stated so it cannot later become a reason to redesign

| leg | fits | 20,000-season simulations |
|---|---:|---:|
| the post-freeze results canary (`point_in_time_canary`: clean and dirty at the cutoff, clean and dirty at the later date) | **4** | 0 |
| the single-opening exercise (§8.4 step 2) | **1** | 0 |
| the match-level openings (§2.3) | **78** | 0 |
| protected `ArchiveRunner`, `dc_native` at all 32 priceable cells (the parity oracle) | **32** | 32 |
| the new runner, control + treatment at all 32 priceable cells | **32** | 64 |
| **the post-freeze experiment** | **147** | **96** |
| v2 §8.2 pass 7, already run on 2026-08-28 (prior history, §8.1) | **35** | **35** |
| **the whole lifecycle, this lineage** | **182** | **131** |

**147 fits and 96 simulations of 20,000 seasons post-freeze; 182 and 131
across the whole lifecycle of this lineage.** The second figure is stated
because v2's was not: its §2.4 totalled only the post-freeze legs and called the
result "whole experiment", while v2 §8.2 pass 7 had by then spent 35 real fits and
35 real simulations on the protected control path. Pass 7 ran under v2's
authorisation and before v3 existed (§8.1); it is prior history for this
document and it is counted here rather than dropped, so that no later reader has
to reconstruct the arithmetic. The canary's four fits and
the single-opening exercise are counted because they are real fits on the real
archive: §8.4 makes them the first two steps of the frozen sequence, and a
budget that omits them would understate both the clock and the moment §8.7's
regime comes into force.

At the walk-forward's realised warm rate (≈ 8.8 s/fit) the 78 openings are
≈ 12 minutes; at the measured cold rate (57.24 s, `data/epl/fit/single_fit.json`)
≈ 75 minutes. The 70 table fits are ≈ 67 minutes cold; at the ≈ 1.24 minutes per
20,000-season simulation implied by the retro's own recorded scale, 105
simulations are ≈ 130 minutes. **The table leg is bounded by ~4 hours.**

The parity oracle needs its own fits and cannot ride the new runner's:
`ArchiveRunner` owns its fit (`epl/simretro.py:520-527,536`), exposes no
posterior and no `ParticleBook` for reuse, and returns `CutoffResult` /
`ArmResult`.

Shards run **sequentially** (the featpanel `.tmp` rename race in the locked path
crashes parallel shards; the fix is held for lock-v11), with
`OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1` pinned at the entry
point before numpy import, `python -u`, launched from a **nohup'd script file,
never a stdin heredoc** (macOS spawn re-imports `<stdin>` and kills the gate's
parallel leg), waited **per PID**. A failed fit poisons its shard and a failed
shard poisons the merge (§7.1).

**The run may not be thinned.** Dropping cutoffs, fixtures, cells or grid points
to fit a clock is an amendment, not an optimisation — and that expressly
includes sampling or truncating the parity oracle, which must complete at all 32
priceable cells (§3.3). The 32 are not a thinning: they are the whole of what the
protected runner can price, measured (§0.6), and the three it cannot are excluded
by name and by measurement rather than by choice.

---

## 3. Secondaries, controls, and the table-retro leg

Everything in §3.1 and §3.4 is published with the result and **decides
nothing**. No secondary may adopt, block, or qualify an adoption. A stratum or
grid point that clears §4's bar while the estimand misses it licenses nothing.

### 3.1 Reported, never deciding

* **The grid** `e* ∈ {1, 3, 5, 8, 12}`: each point's thin-population mean delta,
  treated count, and week-block CI, from the same 78 fits. At `e* ∈ {1, 3}` the
  delta is 0.000000 with a degenerate interval **by construction** (zero treated
  fixtures) — pre-stated here so an identically zero row cannot be presented as
  either a finding or a failure.
* **Strata of the 85**: by season (6); by club category of the thin side —
  *returning-thin* vs *cold-start tail* (2). Eight intervals; some will exclude
  zero by chance; none decides, and that is the correction.
* **The treated-subset mean** (n = 52), beside the estimand it determines.
* **Movement diagnostic**: mean and max |Δp| between arms over the 52 treated
  fixtures, printed beside the ADVI re-seed scale (per-match mean 0.0032, p99
  0.0139, max 0.0229) and the pooled re-seed shift (+0.000075) from
  `reports/epl_walkforward.md`, so "did the treatment move more than re-seeding
  does" is on the record whichever way the estimand lands. This is the one and
  only legitimate home of the `0.0032 / 0.0139 / 0.0229` triple: they are
  absolute probability shifts and are compared only with this experiment's own
  `|Δp|`, like for like. They justify nothing about the bar (§4.2).

### 3.2 The identity control — 820 fixtures, exact equality

Every fitted opening's incumbent-predicate predictions (Arm B) must reproduce
the corpus's own rows **exactly at their 8 decimals** — all **820** fixtures of
the 78 affected blocks, a strictly stronger control than the predecessors'
20-date samples because this experiment must refit these very cutoffs anyway.

The demand is exact for the reasons the predecessors proved: the seed does not
vary by cutoff, and a fit is a pure function of `(cutoff, store, frozen
config)`. The supporting citation is narrow and true:
`epl.walkforward.point_in_time_canary` (`epl/walkforward.py:450-460`) runs the
whole pipeline this experiment runs — anchor, fit, cold start, `predict_1x2` —
and compares **probabilities**, with a positive control proving the corruption
landed. `verify_fast_path_is_inert` is **not** cited: it builds the feature
panel twice and compares the two with `DataFrame.equals`
(`epl/walkforward.py:321-329`), which is a check on feature frames, not on
repeated fitted forecasts. Beyond that citation, **the 820-fixture control is
not supported by an assumption; it is the claim under test.** If repeated fits
do not reproduce the published probabilities at eight decimals, this experiment
stops, and that is the point of running the control first.

The fit's own recomputed provisional set must equal the ledger's recorded
`provisional_teams` at that cutoff (`PredicateMismatch` otherwise) — the control
that the incumbent arm being re-keyed is the incumbent arm that published. A
mismatch anywhere is most likely archive drift and is a STOP
(`ControlMismatch`) either way; **the control runs first, and not one treated
prediction is produced until it passes.** Max and mean |Δp| are reported even
when zero.

**These checks must be exercised directly, in the production code path.** The
in-tree audit of v1 established that loosening `Engine.fit`'s exact comparison
to a `1e-4` tolerance left the entire suite green, because the stub fitter in
the tests reimplements the control rather than exercising it — and §10 makes
widening that tolerance after a mismatch an invalidation, so the untested site
is exactly the site where it would be widened. Before the freeze commit,
`epl/tests/test_evwiden.py` must carry tests that execute the real
`Engine.fit` — not a stub — and go red when (a) the eight-decimal identity
comparison is loosened to any tolerance, (b) the `UntreatedMoved` loop is
disabled, and (c) the pass-2/pass-3 agreement check is disabled. §8.5's
conformance row L12 is that obligation.

### 3.3 The table-retro leg — the second gate's measurement

**Why it exists:** the queue binds it ("historical walk-forward + table retro
before adoption"), the product impact lives at table level, and the one
Hull-analogue (§0.5) is visible only here.

**Mechanics.** `epl/simretro.py` is protected, its `ARMS` tuple is closed, and
`ArchiveRunner._provider` raises on any other arm — so the table leg is a **new**
`epl/` module that reuses `epl.leaguesim` / `epl.particles` / `epl.season` /
`epl.table` / `epl.simmetrics` (all read-only imports) and reproduces
`simretro`'s schedule through `simretro`'s own public surface: `SEASONS` ×
`COMPARISON_CUTOFFS` minus the three cells §0.6's census measured as
unpriceable = **32 cells**, cutoffs from `cutoff_schedule`, realised
tables through `realised_positions` / `realised_hash`, 20,000 simulated seasons
per arm per cell, seed **20260611**. `data/epl/sim/retro_r1.jsonl` is read-only
and never appended; the leg writes its own ledger.

Per cell: **one fit** serves both arms (the posterior is arm-invariant, §0.2);
the control book carries the incumbent provisional set, the treatment book the
§2.1 union; identical particle draws and identical RNG streams, so the arms are
CRN-paired and the **only** divergence is the D12 per-fixture Bernoulli widening
branch on treated fixtures. D2 stays static-within-fit and D12 stays
per-fixture — the two standing open owner rulings this experiment explicitly
does not touch.

**Both arms are labelled `dc_native` to `leaguesim`.** That is the document's
rule and not a harness convenience: the provider *is* `DCNativeProvider` in both
arms — a `ParticleBook` may not wear another arm's name — and what differs
between them is the **book**, which is the treatment. The experiment's own arm
name `dc_evwiden` names the re-keyed book and is recorded on the row.

#### The treated cells, enumerated now

**The population first.** The cells are `SEASONS × COMPARISON_CUTOFFS` **minus
the three §0.6's census measured as unpriceable**, and those three are named by
key here so that the population is decidable from this document rather than from
a file:

```
EXCLUDED_CELLS = ("2019/20|MW0", "2020/21|MW0", "2023/24|MW3")
```

A thirty-third cell, or a thirty-second that is not one of these thirty-two, is
`MembershipMismatch`. The exclusion is by measurement (§0.6) and is not a
parameter: no caller may name, restore or extend it.

Treated cells computed from the pinned archive by the §0.3 recipe and
`count_volatility_arm` at each scheduled cutoff; predicate strict `<`, values at
2 dp. **15 of the 32 priceable cells change** — 2019/20 MW3 (aston_villa 7.47,
norwich 5.94), MW6 (9.997, 8.54, sheffield_united 5.68), MW10
(sheffield_united 9.16); 2020/21 MW6 (leeds 5.66); 2021/22 MW6 (brentford 6.52),
MW10 (9.92); 2022/23 MW6 (nottm_forest 5.72); 2023/24 MW0
(sheffield_united 9.84), MW6 (luton 5.73), MW10 (luton 9.23); 2024/25 MW6
(ipswich 6.52), MW10 (9.92); **2025/26 MW0 (sunderland 0.17), MW3 (3.05), MW6
(6.67)** — the Hull-analogue cells.

**The one treated cell v2 had and this document does not is 2019/20 MW0**
(aston_villa 4.74, norwich 3.15). It is lost to the census, not to a choice: it
is one of §0.6's three unpriceable cells, and the other two — 2020/21 MW0 and
2023/24 MW3 — were untouched cells whose loss costs the design denominator and
nothing else.

By label:

| cutoff label | cells | treated cells | excluded by §0.6 |
|---|---:|---:|---|
| MW0 | **5** | **2** | 2019/20, 2020/21 |
| MW3 | **6** | 2 | 2023/24 |
| MW6 | 7 | **7** | — |
| MW10 | 7 | 4 | — |
| MW19 | 7 | **0** | — |

**Both per-label censuses are binding pins, not tables in prose.**
`EXPECTED_TREATED_BY_LABEL = {MW0: 2, MW3: 2, MW6: 7, MW10: 4, MW19: 0}` must be
verified by `table_cells(check=True)` alongside the per-label CELL census
`EXPECTED_CELLS_BY_LABEL = {MW0: 5, MW3: 6, MW6: 7, MW10: 7, MW19: 7}`, which is
a pin v2 never needed because its labels held seven cells each and is required
here because they no longer do. The reason is not tidiness: **"MW6 is the only
label at which every cell is treated" is the entire stated ground for naming MW6
the deciding horizon** (§4.1), and after the census that sentence is a statement
about two censuses rather than one — a label could become all-treated by losing
its untouched cells, which is not the same fact and would not carry the same
ground. Pinning both is what makes the claim checkable. If either stops being
true, the ground for the deciding horizon has moved and the harness must refuse
rather than carry on. A departure from either pin is `MembershipMismatch`.

#### The two-sided cell identity

* An **untouched** cell (one of the 17) whose two arms' `sampler_digest`s differ
  is `TableIdentityBreak`.
* A **treated** cell (one of the 15) whose two arms' `sampler_digest`s are
  **equal** is `TableIdentityBreak`. A treatment that changes no sampler output
  where the rule says it must is not a null result; it is a treatment that never
  reached the sampler, and reporting its zero delta as evidence of no harm would
  be reporting the absence of the experiment.

#### The two digests, with disjoint jobs

> **`sampler_digest(run, tallies)` — sampler output only.** SHA-256 over the
> canonical JSON (`epl.leaguesim.canonical_json`) of, in this order:
>
> 1. the scored position matrix at full stored precision;
> 2. the per-particle fractional rank-mass tallies of §5.1;
> 3. the retained points, goal-difference and goals-for vectors;
> 4. the tie-block record — `block_start`, `block_span`, `resolution_code`.
>
> **Nothing else.** No club list, no plan, no seed, no posterior hash, **no
> provisional set**, no arm label, no clocks, no host, no shard id, no free
> text. It is comparable only **within one cell, between its two arms**, and
> that is its only use.

> **`substantive_digest(run, tallies, …)` — everything a rerun must reproduce.**
> SHA-256 over the canonical JSON of `sampler_digest`'s four items **plus**:
>
> 5. the club list;
> 6. the consequence weights and the boundary definition;
> 7. the realised-truth identity — `realised_hash`, the realised position vector
>    and the realised points vector;
> 8. `n_sims`, `n_particles`, `seed`;
> 9. **the full `SimPlan` state** — the complete field set of
>    `epl.leaguesim.SimPlan` (`epl/leaguesim.py:559-654`), serialised
>    canonically: `season`, `season_code`, `cutoff`, `observed_by`, `clubs`, the
>    fixture tuple (per fixture: `fixture_id`, `ordinal`, `home_key`,
>    `away_key`, and `result` as the played snapshot — `null` for unplayed),
>    `adjustments` (the int16 vector, by club), `boundaries`, `rule_id`,
>    `n_sims`, `n_particles`, `seed`, `chunk_size`, `n_unresolved`,
>    `results_lag`.
>
> **Excluded by name:** the arm label, the provisional set,
> `effective_posterior_hash`, wall clocks, host, shard id, and any free-text
> note.

**Why `effective_posterior_hash` is excluded from the payload.** It is supplied
as `ParticleBook.content_hash()`, and `content_hash` hashes
`sorted(self.provisional)` (`epl/particles.py:331-358`). Embedding it would
re-admit the provisional set into a digest the document says excludes it —
directly contradicting the definition, whatever the downstream consequence. The
posterior identity is not discarded: **`effective_posterior_hash` becomes a
separately-recorded and separately-compared provenance field** on every table
row (`effective_posterior_control`, `effective_posterior_treatment`), checked
directly the way the provisional sets are. Metadata is checked as metadata; the
sampler is checked by its output.

**That comparison may not fail open.** A hash absent on either side —
the new runner's or the protected oracle's — is `TableIdentityBreak`, not a
comparison skipped. A check that runs only when both sides happen to be present
is a check a missing field passes, and the whole reason excluding the hash from
the digest costs nothing is that it is compared somewhere else.

**`sampler_digest`'s signature is pinned.** A committed test asserts
`list(inspect.signature(sampler_digest).parameters) == ['run', 'tallies']`, and
a second committed test drives **the runner's own paired-arm sequence** — the
function `TableRunner` is built from — with two books differing only in
`provisional` over one run and one tally, and asserts that the two arms'
`provisional` fields differ while their **sampler digests are EQUAL**. Both are
required because the in-tree audit of v1 showed that a two-line change adding
`provisional` to the digest's payload left the whole suite green while turning
the treated-cell identity test into a test that cannot fail — the exact tautology
the digest split exists to end. A test that only checks which *existing* fields
move the digest cannot see a new input channel; these two can. The second is
stated at the level of the paired-arm sequence rather than at `TableRunner`
itself because `TableRunner.__call__` cannot be entered without a real fit, and
an obligation no test can execute is the shape §8.5 exists to refuse.

#### The provisional sets, checked as fields

Each table row records `provisional_control` and `provisional_treatment` as
sorted club lists. They are checked three ways: the parity oracle requires
`provisional_control` to equal protected `ArchiveRunner`'s own
`provenance["provisional_teams"]` at that cell; the treated-cell census requires
`provisional_treatment ⊋ provisional_control` at exactly the 15 named cells and
`provisional_treatment == provisional_control` at the other 17; and any
disagreement is `TableIdentityBreak`.

#### The parity oracle — all 32 priceable cells, completed before any treatment

The new runner must reproduce protected `epl.simretro.ArchiveRunner`'s
`dc_native` output at **all thirty-two priceable cells** — native parity, every
cell of the census, no
sampling — and the parity leg must **complete** before **one** treated
simulation is executed. `ArchiveRunner`'s `CutoffResult` retains the `SimRun` on
`ArmResult.run` (`epl/simretro.py:441-456`), so the comparator is the
**`substantive_digest`**, computed by the same harness function from the
protected runner's `SimRun` and from the new runner's control-arm `SimRun`. A
difference at any cell is `TableIdentityBreak` and stops the leg.
`data/epl/sim/retro_r1.jsonl` stays read-only and is not the comparison object:
the parity run is executed, not read off the archive ledger.

Three closures make "before" and "all 32" mechanical rather than aspirational:

1. **Completion, not interleaving — and, within a cell, control before
   treatment.** The parity oracle runs to completion over all 32 priceable cells
   and writes `data/epl/sim/evwiden/parity.jsonl` (32 rows) as its completion
   marker.
   `run_table` refuses to simulate any arm until that file exists and carries all
   32 cells, each with a digest to compare against. A design in which the new
   runner simulates control **and treatment** and only then compares the control
   against protected output has already executed the treatment before
   establishing parity, and does not satisfy this clause — **including inside a
   single cell**. The per-cell order is therefore fixed here and is a property of
   the code rather than of a comment: simulate the control arm, establish that
   cell's native parity against protected `ArchiveRunner`, and only then simulate
   the treatment arm. The sequence is one named function, and it takes the
   simulate and record steps as arguments so that the order can be **executed and
   observed** without a real fit: a spy records exactly how many arms were
   simulated before a refusal, which is the only way "before" is checkable at
   all. A cell handed no parity row at all is `TableIdentityBreak` for the same
   reason.
2. **No `--limit` on the oracle.** No CLI flag, keyword or subset argument may
   reduce the oracle's 32 cells. "All 32" is the whole content of the control,
   and §0.6's three excluded cells are excluded by the census and by nothing a
   caller can name.
3. **No `require_parity` parameter exists.** An exposed boolean that turns the
   oracle off is a bypass; the document does not permit one and the harness may
   not carry one. Parity is a property of the run, not an option of the caller.

Binding the *schedule* to protected code binds neither `ArchiveRunner`'s
semantics — verified adjustments, `config_read_once`, particle-book
construction, boundaries, chunking, refusal handling, ranker checks,
provenance — nor its call. The 19-untouched-cell control compares two arms
produced by the **same new code**, so any drift shared by both arms passes it
silently. Only the executed oracle catches that class.

### 3.4 Table-side secondaries — reported, never deciding

Per-cell paired ΔTRPS and ΔwTRPS for all 32 cells, published in full; per-club
points-interval coverage (cov50 / cov90, `epl.simmetrics.interval_coverage`) for
the treated clubs under both arms, read as §1.3 pre-states; and the
**Sunderland 2025/26 cells** (relegation probability, points mean and 5–95 band,
both arms) printed under the label *"the one Hull-analogue — illustrative, no
decision weight."*

**No cross-horizon average is published at all.** `epl/simretro.py:41` and
`epl/simmetrics.py:44` both freeze **"Never averaged across cutoffs"** — a
forecast at the opener and one at matchweek 19 answer different questions and
their average describes neither. The 32-cell pooled ΔTRPS and pooled ΔwTRPS are
**withdrawn from the published outputs entirely**, not demoted to secondaries:
publishing an aggregate that protected code forbids as a verdict invites it to
be quoted as one. What publishes in their place is every cell's ΔTRPS and ΔwTRPS
individually, and the four treated-cell label means of §4.1.

TRPS is proper **for the displayed marginals only** (`epl/simmetrics.py` says so
in its own docstring): two forecasts with the same position matrix and different
correlation structure score identically, widening changes the joint too, and no
table metric here can see that. Disclosed, not solved.

---

## 4. The adoption rule

### 4.1 The rule

> **ADOPT the evidence-mass re-key (as a shadow arm, §4.5) if and only if ALL
> FOUR:**
>
> **(i)** the point estimate of the estimand is `Δ ≤ −0.0010` RPS over the 85
> thin fixtures, **and**
>
> **(ii)** the 95% `(season, ISO week)` block bootstrap CI (62 blocks) excludes
> zero — its upper bound is strictly < 0, **and**
>
> **(iii)** the 95% season block bootstrap CI (6 blocks) also excludes zero,
> **and**
>
> **(iv)** the table gate holds, in three parts, all required:
>
> > **(iv-a) The named-horizon gate — MW6.** The statistic is the
> > **equal-weight mean over the seven MW6 cells of
> > ΔTRPS = TRPS(treatment) − TRPS(control)**. It must be **≤ +0.0002**.
> >
> > **(iv-b) The per-horizon point gates.** At each of MW0, MW3 and MW10, the
> > equal-weight mean of ΔTRPS **over that label's treated cells only** (2, 2
> > and 4 cells respectively — MW0's third treated cell was 2019/20 MW0, which
> > §0.6's census measured as unpriceable) must be **≤ +0.0002**. No interval is computed at
> > these labels and none is required; two cells do not carry one. MW19 holds
> > zero treated cells, is a structural zero by construction, is reported as
> > such, and decides nothing.
> >
> > **(iv-c) The significance clause, at MW6 only.** Gate (iv) **fails** if the
> > MW6 mean is `> 0` **and** the lower bound of its 95% season-block interval
> > (7 blocks, §5.3) is `> 0`.
>
> **Otherwise `dc_native` stands unchanged, Hull's forecast included.**

All four are required and none is sufficient. (i)–(iii) are the benefit gate;
(iv) is the do-no-harm gate the queue binds. Gate (iv) may additionally be
**UNRESOLVED** under §5.4's precision regime; UNRESOLVED blocks adoption and can
never grant one.

**Why MW6 is the named horizon, and why naming it now is not selection.** It is
named before any fit exists, on two grounds neither of which is an outcome.
*Support:* MW6 is the only one of the five labels at which **every** cell is
treated, so it is the only horizon at which the do-no-harm question is asked
with no structural zero in the denominator — which is why §3.3 makes both
per-label censuses binding pins rather than prose tables. **It is also the only
label §0.6's census left whole**: MW6 is 7 of 7 priceable, so its denominator is
the one v2 named and not a survivor of the measurement. That matters to the
"not selection" claim: MW0 lost two cells and MW3 one, and a horizon named after
a census could have been named *because* of one. MW6 was named in v2 before pass
7 ran, its ground was stated there in these words, and the census neither created
it nor moved it. *Product:* the
early-season table forecast is where a thin-evidence club's dispersion is widest
and where the issuance surface that motivated this work is published (§0.4). The
choice is frozen here; §10 makes replacing it after any table run an
invalidation.

### 4.2 The bar is an invented thin-population threshold, and says so

**`−0.0010` over the 85 thin fixtures is an invented thin-population
threshold.** It takes its numeral from `reports/epl_improved.md` §5.2's
model-change bar (45 challengers, all missed, best −0.000065); **the numeral is
borrowed, the authority is not.** The house bar was set over a full evaluation
window; this one is set over 85 fixtures chosen to be where the effect is
largest — a difference in system-level materiality of about 26.8× (2280/85).
Presenting it as "the house bar applied" would borrow authority from a different
estimand.

It is justified on four grounds, and the first two are weaker than the phrase
"the full bar applies" would suggest.

**Ground 1 — Noise, in RPS against RPS.** The demand the bar makes of the
treated population is a **mean of 52 paired RPS deltas**, so the like-for-like
comparison is with the standard error of that mean, under §6's three frozen
scenarios:

| scenario | paired SD (RPS) | SE of the 52-fixture mean | the bar `−0.0016346` in SEs |
|---|---:|---:|---:|
| A freshness-scale | 0.005262 | 0.000730 | **2.24** |
| B anchoring-scale | 0.014449 | 0.002004 | **0.82** |
| C mechanism-scale | 0.036 | 0.004992 | **0.33** |

The bar sits at about 2.2 standard errors of its own estimator under the
optimistic scenario and **inside one standard error** under both pessimistic
ones. It is **not** "well outside" the noise; under scenarios B and C it is
inside it. This is §6's power finding restated in the units the bar is written
in, and it points the same way.

There is **no committed per-fixture RPS-unit re-seed noise figure for this
corpus** — only the pooled corpus-level shift of `+0.000075`, which *is* an RPS
quantity and *is* comparable, and which ground 4 uses. The
`0.0032 / 0.0139 / 0.0229` ADVI re-seed triple is **not** used here: those are
absolute probability shifts `|Δp|`, a different quantity on a different scale,
and comparing a mean-RPS demand of 0.0016 against a probability scale beginning
at 0.0032 is not merely incomparable — read literally it is backwards. That
triple keeps its one legitimate home, §3.1's movement diagnostic.

**Ground 2 — Power.** §6's table is the evidence that a materially lower bar
would sit inside scenario B's noise and a materially higher one is unreachable
under every scenario. The bar is at the edge of what this population can
resolve, which is where a preregistered bar belongs.

**Ground 3 — Law, not cadence.** The rule changes the published probabilities
themselves on the fixtures it touches, i.e. the law, which is the thing the full
model-change scale protects. Freshness argued its bar down to −0.00030 because a
cadence change is operational; this is not operational, so **the freshness
discount does not apply**. That is a floor argument and nothing more. **The
product value of this rule is not quantified anywhere in this repository and
this experiment does not quantify it.** The one product-scale number in sight —
the 27.9%→15.9% relegation counterfactual — is ruled out of the evidence base
entirely by §1.2 and may not be borrowed here.

**Ground 4 — System-level materiality, and this is the concession.** A passing
result is `−0.0010 × 85/2280 = −0.000037` pooled over the corpus, **smaller in
magnitude than the +0.000075 re-seed shift**. **This experiment cannot
demonstrate a corpus-level improvement and does not claim one.**

**Required disclosure, in the result document, in these words:** *"the rule's
corpus-level effect is below this model's own re-seed noise, and its value is a
claim about the fixtures it touches, not about the model's aggregate
accuracy."*

**A corpus-level materiality *condition* is refused.** A pooled bar would be
unclearable by construction for any rule this targeted, and preregistering one
would be preregistering a guaranteed miss. The disclosure is required; the gate
is not added.

**What this experiment may claim on a pass at all four gates, exhaustively:**

1. that on **85 pre-specified thin-evidence fixtures** of the pinned corpus the
   re-keyed predicate changed the mean paired RPS by the reported amount, with
   the two reported intervals, at the power §6 states for the realised SD; and
2. that on the **15 pre-specified treated table cells** the paired ΔTRPS did not
   exceed `+0.0002` at MW6 or at any of MW0, MW3 and MW10, and that the MW6 mean
   was not resolvably positive.

**What it may never claim, on any result:** a corpus-level accuracy improvement
(ground 4); a quantified product value (ground 3); anything about Hull
specifically at match level (§11 — one analogue, and it is in the table leg);
anything about the joint law, which no table metric here sees (§3.4); or
anything about a threshold other than `e* = 10.0`.

### 4.3 The table gate's tolerance is invented, and says so

R1 has **no pass rule** — `reports/epl_sim_retro_v1_1.md` §10: *"Nothing, by
itself"* — so a table-level bar has no house precedent and one must be invented
for the queue's binding to be checkable. It is invented from R1's own recorded
scale, before any widened table exists: the retro's paired dc-family TRPS
differences that its report calls "two parts in a thousand" on a TRPS of order
0.08 are ~2e-4 **per cell**, and the gate caps degradation at that scale —
**+0.0002** — plus the significance clause, so a small-but-resolvable worsening
fails and an unresolvable wiggle does not.

The tolerance is applied to **treated-cell means directly**, at a single named
horizon. Applying the same per-cell scale to an average over 32 cells of which
17 are exact zeros would permit about **+0.00042667** of average degradation
across the 15 changed cells; the gates here permit at most **+0.0002** where the
treatment fires — **2.13× tighter**. The number is unchanged; the estimand it
governs is the one it was calibrated for.

A seven-block percentile bootstrap has poor coverage, is not claimed to have
good coverage, and has the narrow job both predecessors gave season blocks: to
refuse a verdict carried by one season. This paragraph is the disclosure that
(iv)'s numbers are choices, made blind, in a place where the house had none —
and §5 makes the simulation error of that horizon a published, deciding-capable
quantity rather than an unstated one.

### 4.4 What happens on a miss, and what publishes either way

`dc_native` stands unchanged. **The result publishes either way** —
`reports/epl_widening_result.md` and the §9 evidence files are written whatever
the signs, including the three embarrassing cases pre-named: the estimand
positive (widening thin clubs *hurts*); the estimand negative with the table
gate failing (better matches, worse tables — which the joint-vs-marginal
disclosure of §3.4 makes possible); and gate (iv) UNRESOLVED, which publishes as
UNRESOLVED with every number and names which precision condition fired. **There
is no file drawer.**

A miss is not re-litigated: not at a second seed, not at a neighbouring grid
point, not by REPLACE, not by a continuous α, not by dropping 2019/20, not by
the treated subset promoted to estimand, not by extending the corpus into
2025/26, not by a one-sided interval, not by a larger `n_sims`, and not by a bar
rewritten after the number. Each appears in §10.

### 4.5 What adoption would and would not change

Adoption is **shadow-first and this season ships nothing**, per the design
record's own ruling ("NOT shipped this season without it" — and passing the
gates is necessary, not sufficient). On ADOPT, `dc_evwiden` becomes a shadow arm
in the A8/A12 pattern — own ledger, own arm-tagged schema, own verify, scored
beside `dc_native` at `epl/livecycle.py`'s challenger step, no matchboard, no
gate, no pass rule — with the one difference A8's objection carves out:
`dc_evwiden` defines a full scoreline law, so it **can** carry a shadow table.
The published arm, `ISSUANCE_SCHEMA_VERSION`, the matchboard and every published
surface stay exactly as they are. Switching the published arm is a separate,
later owner ruling with its own amendment — the next free slot is **A13** — and
this document does not pre-authorise it.

**The invalidation cascade is named now.** A8's frozen recalibration constant
carries the clause "any change to decay, **widening**, inference or
scoreline-model semantics invalidates `a` until it is revalidated"
(`reports/epl_recal_grounding.md`). Research-phase runs here change no shipped
semantics, so `a` stands throughout this experiment. If the re-key is ever
adopted into the **published** arm, that adoption invalidates `a` until refit
under A8's own schedule, marks the A12 availability arm's downstream ledger rows
as pre-change history, and lands batched into the next lock version if any
production wiring touches `src/` — none is needed for the shadow shape, which
reaches the predicate the way `epl/dcfit.py` reaches the anchor: an explicit call
sequence, never a patched import. Under the adopted per-matchday live cadence,
the predicate recomputes at every fit's own cutoff, same rule, same constant.

**Who decides.** Adoption is an owner ruling, recorded as a dated entry in
[`reports/epl_sim_amendments.md`](epl_sim_amendments.md). No script, agent or
report may change any arm on the strength of these numbers.

---

## 5. The table leg's Monte-Carlo error, and the precision regime

Gate (iv)'s tolerance is the same order as the simulation's own error, so a gate
without a frozen error estimate is a gate that noise can decide. This section
freezes the estimator in full and makes simulation noise able only to **refuse**.

### 5.1 The per-particle fractional rank-mass tally

The object TRPS scores is **fractional rank mass**, not ordinal rank.
`epl/table.py` says of `.order` in its own docstring that *"inside a shared
block its sequence carries no meaning and is only the deterministic club-index
order"* (`epl/table.py:374-377`), while the scored matrix is built by
`epl.table.position_mass` / `position_mass_sums`, which spread `1/span` across
the `span` positions a tie block occupies (`epl/table.py:550-593`). A bootstrap
over `.order` would resample a different object from the one the point estimate
scores.

The tally is therefore built through the protected code that defines it. For
each deciding cell and each of its two arms, from the run's own `retained_rows`
and `plan`:

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
read** — `position_mass` reads `block_start` and `block_span` and nothing else,
and no other step of this estimator touches it. The harness may accumulate in
chunks the way `position_mass_sums` does provided the chunks are visited in
ascending season order, which makes the per-particle sums bit-identical to the
whole-array form; a committed test asserts that equality at 0.0.

**Two committed checks bind the tally to the point estimate it must describe.**

* **The matrix check, dimensionally exact:**
  `max |T.sum(axis=0) / n_sims − run.matrix| ≤ 1e-9`.
  `T[s]` accumulates **unnormalised** mass over the seasons particle `s`
  carries, so `T.sum(axis=0)` is on the scale of `n_sims` seasons, while
  `run.matrix` is `mass.matrix / n_sims` — the normalised matrix the run
  publishes. The division by `n_sims` is part of the equation, not an
  implementation detail; an invariant written without it is dimensionally wrong
  and cannot hold. The tolerance rather than bit equality is deliberate: the
  protected accumulator sums in **chunk** order and this one sums in **particle**
  order.
* **The equal-cluster check:** every particle's tally has **every row and every
  column** equal to `k = n_sims / P` to within 1e-9 — a league season is a
  bijection between clubs and ranks, and this is the same equal-cluster condition
  the protected `epl.simmetrics.trps_se_cluster` enforces on its own input
  (`epl/simmetrics.py:230-250`).

### 5.2 The estimator, frozen in full

**Deciding cells.** The estimator runs over the **15 treated cells** — the exact
cells §3.3 enumerates: MW6's seven, MW0's two, MW3's two, MW10's four. MW19
holds no treated cell, is a structural zero by construction, and enters nothing.
Fifteen cells × two arms = **30 tallies**.

**Preconditions, and the refusal that guards them.** All 30 tallies must report
the **same** `n_particles` `P`, and every particle must carry the same whole
number of simulated seasons. Under the pinned configuration `P = 1,000` at every
cell (`model.inference.draws = 1000`, bound by §0.1's `realised_config_sha256`)
and `n_sims / P = 20`. Any violation — unequal per-particle season counts, or
unequal `P` across cells or arms — raises **`TableMCImprecise`** and stops the
table leg. Joint resampling is undefined without a common index space, and this
document will not approximate one.

**One resample per replicate, applied to all thirty tallies.**

```
rng = numpy.random.default_rng(MC_SEED)          # MC_SEED = 20260827
for r in range(MC_BOOT):                          # MC_BOOT = 2,000
    picked = rng.integers(0, P, P)                # ONE draw, this replicate
    for cell c in the 15 deciding cells:
        for arm a in (control, treatment):
            M = T[c][a][picked].sum(axis=0)
            M = M / M.sum(axis=1, keepdims=True)  # row-normalise
            s[c][a] = epl.simmetrics.trps(M, positions_c, spans=spans_c)
        d_r[c] = s[c][treatment] − s[c][control]
    mw6_r  = mean(d_r[c] for the 7 MW6 cells)
    mw0_r  = mean(d_r[c] for the 2 treated MW0 cells)
    mw3_r  = mean(d_r[c] for the 2 treated MW3 cells)
    mw10_r = mean(d_r[c] for the 4 treated MW10 cells)
```

`positions_c` and `spans_c` are the cell's own realised position vector and
realised block widths from `epl.simretro.realised_positions` — the same two
arrays the cell's point estimate is scored with (`epl/simretro.py:1246,1261`).

**The standard errors, read off the replicate stream and nowhere else.**

```
mc_se_mw6  = std(mw6_r,  ddof=1)      mc_se_mw0  = std(mw0_r,  ddof=1)
mc_se_mw3  = std(mw3_r,  ddof=1)      mc_se_mw10 = std(mw10_r, ddof=1)
mc_se_cell[c] = std(d_r[c], ddof=1)                    # reported, decides nothing
```

**There is no quadrature step and no independence claim anywhere in this
estimator.** `epl.leaguesim.streams(seed, chunk, fixture_ordinal)` reads only
those three things (`epl/leaguesim.py:199-207`) — not the season, not the
cutoff, not the cell — and all 32 cells run at the same `seed = 20260611`.
Simulated season *n* of one cell and simulated season *n* of another therefore
consume the **same uniforms** and are priced by the **same particle index**
`n mod S`. The cells' Monte-Carlo errors are correlated by construction and the
size of that correlation is unknown; `sqrt(Σ se²)/7` would assume it away. Here
the label means are computed *inside* each replicate and their spread is read
directly, so whatever covariance the shared streams induce is reproduced within
every replicate rather than modelled. The per-cell SEs are published as
diagnostics and are never combined into a label SE.

**Why one index draw across cells is the right construction, and what it does
not claim.** It does **not** claim that particle *s* of one cell is the same
posterior draw as particle *s* of another — it plainly is not; the cells are
different seasons with different fits. What it uses is that the shared
randomness of two cells is indexed by `(particle index, chunk, fixture_ordinal)`
and the particle index is deterministic in the season index. Resampling the
particle **index** jointly therefore resamples the same simulation slots in
every cell at once, so two cells that share uniforms move together inside a
replicate exactly as they move together in the run. Within a cell, the same
`picked` applied to both arms is the CRN pairing: the arms share particles,
share streams, and differ only on the D12 branch at treated fixtures, so most of
the simulation noise cancels in the difference.

**Honest limits, stated now.** The particle is the cluster, as it is in every
Monte-Carlo error this repository publishes (plan v2 D15). Within-particle match
randomness at fixed particle is resampled only through the 20 seasons each
particle carries, and a 7-, 4- or 2-cell label mean is a small average
however it is estimated. This estimator bounds how much of the gate's margin is
simulation noise; it is not a model of the fit's own uncertainty, which no table
statistic in this experiment sees.

**`MC_BOOT = 2,000` and `MC_SEED = 20260827`**, pre-stated here before any table
run exists. Standing amendment A2-N4 leaves B and the resampling seed to "the
amendment that accompanies the first run to report the bootstrap SE, before that
run"; this is that document and this is that statement.

### 5.3 The MW6 season-block interval, frozen in full

| | |
|---|---|
| statistic | the equal-weight mean of the seven MW6 per-cell ΔTRPS |
| function | `epl.score.block_bootstrap_ci` (`epl/score.py:193`), the same function both match legs use |
| deltas | the 7 MW6 cell deltas, in season order |
| block labels | the seven season strings `2019/20 … 2025/26`, one cell per block, so `n_blocks = 7` |
| B | **10,000** (frozen, not overridable — §2.3) |
| alpha | **0.05** |
| resampling seed | **20260814** |
| quantile convention | `np.quantile(means, [alpha/2, 1 − alpha/2])` on the function's own pooled-mean resample, NumPy's default linear interpolation |

### 5.4 The precision and refusal rule, at every deciding boundary of gate (iv)

Gate (iv) is **UNRESOLVED**, and ADOPT is refused, if **any** of P1–P5 holds.
Every condition is one-directional: UNRESOLVED blocks adoption and can never
grant one.

* **(P1) Resolution.** Any deciding MC SE exceeds `0.25 × 0.0002 = 5e-5` — that
  is, any of `mc_se_mw6`, `mc_se_mw0`, `mc_se_mw3`, `mc_se_mw10`. A missing SE is
  treated as unresolved, never as small.
* **(P2) iv-a's tolerance boundary.** `|mean_MW6 − 0.0002| < 2 × mc_se_mw6`.
* **(P3) iv-b's tolerance boundaries.** At each of MW0, MW3 and MW10
  separately — published as `P3.MW0`, `P3.MW3`, `P3.MW10`:
  `|mean_L − 0.0002| < 2 × mc_se_L`.
* **(P4) iv-c's zero boundary on the mean.** `|mean_MW6 − 0| < 2 × mc_se_mw6`.
* **(P5) iv-c's zero boundary on the interval — the unanimity rule.** Defined
  immediately below.

**Why P4 and P5 exist at all.** Clause (iv-c) is a **failure** clause: gate (iv)
fails when the MW6 mean is `> 0` **and** its interval excludes zero. Simulation
noise that pushes the mean or the lower bound below zero converts a failure into
a passage. That is the one direction this document may not leave open, and
UNRESOLVED closes it without ever opening the other.

#### P5 — the unanimity rule, frozen

> **The whole of iv-c is recomputed on `K = 200` particle-resampled tally sets.**
> `rng = numpy.random.default_rng(20260828)`. For each `k` in `0 … 199`: draw
> **one** joint particle resample `picked_k = rng.integers(0, P, P)` and apply
> it to **all thirty tallies** exactly as §5.2 applies its own draw —
> row-normalising each resampled matrix and scoring it with
> `epl.simmetrics.trps(M, positions_c, spans=spans_c)`. From the resulting seven
> MW6 cell deltas compute the season-block interval of §5.3 — same function,
> same seven season blocks, `B = 10,000`, `alpha = 0.05`, seed **20260814** —
> and evaluate iv-c's verdict: **FAIL iff `mean_MW6 > 0` and `ci_lo_MW6 > 0`.**
>
> **P5 fires — and gate (iv) is UNRESOLVED — unless all 200 verdicts agree with
> each other and with the point-estimate verdict.** One dissenting `k` is
> enough.

**Why this bounds what the superseded proxy could not.** The natural-looking
guard is to compare `|ci_lo_MW6 − 0|` with `2 × mc_se_mw6`. That comparison is
invalid, and its invalidity is demonstrable rather than stylistic:
`mc_se_mw6` is the Monte-Carlo standard error of a **linear** statistic — the
equal-weight mean of seven cell deltas — while `ci_lo_MW6` is a **nonlinear
quantile of a season bootstrap over those same seven values**. The two need not
move together at all. Take cross-cell Monte-Carlo error proportional to
`(+h, −h, 0, 0, 0, 0, 0)`: the mean error is identically zero, so `mc_se_mw6` can
be arbitrarily small, while the season bootstrap's unequal resample
multiplicities give the `(+h, −h)` pair unequal weight in most replicates and can
move the lower quantile across zero. The proxy then fails to fire while iv-c
flips from FAIL to PASS — precisely the direction that must never be available.

The unanimity rule does not bound the endpoint by a scale that does not describe
it; it **propagates the Monte-Carlo uncertainty through the actual computation**,
re-deriving the interval endpoint 200 times from resampled tallies and requiring
the verdict itself to be stable. It shares the estimator's own construction —
one joint particle draw per replicate, applied to all 32 tallies — so it carries
the same cross-cell covariance for free. It can only ever refuse: unanimity is
required for the gate to resolve, and any disagreement yields UNRESOLVED.

Its cost is trivial beside the run it guards: 200 × (30 matrix resamples + one
10,000-replicate bootstrap over 7 scalars).

**The gate validates the unanimity run it is handed, and refuses one it cannot
check.** P5 fires unless the object carries `K = 200`, seed 20260828, **200
recorded verdicts**, a dissent count that equals the number of those verdicts
that actually disagree, a `fired` flag consistent with that count, and the same
point-estimate verdict the gate has itself just derived. This is not an extra
condition; it is what "the whole of iv-c is recomputed on `K = 200`
particle-resampled tally sets" means when the object reaches the gate from
somewhere else. It is one-directional like every other part of §5.4: an
unverifiable unanimity run is **unresolved**, exactly as an absent one is, and
neither can ever grant a passage.

#### The structural refusal, and how it is published

**`TableMCImprecise` is a refusal, not a published condition.** The structural
conditions of §5.2 — unequal per-particle season counts, or an `n_particles`
that differs across the 15 deciding cells or between a cell's two arms, or a
tally that fails either binding check of §5.1 — **raise** `TableMCImprecise` and
stop the table leg. They do not produce a verdict, because there is no verdict to
produce: the estimator's index space does not exist.

Consequently `reports/evidence/widening.json`'s `gate_iv.precision.conditions`
carries **seven entries and only seven** — `P1`, `P2`, `P3.MW0`, `P3.MW3`,
`P3.MW10`, `P4`, `P5` — each with its computed value, its rule string and a
boolean. There is no `P6` entry and there must not be one: a structural refusal
that stops the leg cannot also be a row in a file the stopped leg never writes.
This is stated explicitly because v1 froze a field list naming "P1–P6" while its
harness emitted exactly the seven above, and the frozen list must match what the
code emits.

The precision object also carries `mc_boot`, `mc_seed`, `unanimity_k`,
`unanimity_seed`, `unanimity_dissenting`, `n_particles`, `sims_per_particle`,
`mc_se_mw6`, `mc_se_mw0`, `mc_se_mw3`, `mc_se_mw10`, `mc_se_per_cell` (15
entries) and `resolved`.

**`n_sims` stays at 20,000** and the precision rule does **not** license a larger
run: enlarging a preregistered constant after a number exists is exactly what
§10 forbids. An UNRESOLVED verdict publishes as UNRESOLVED, with every number,
under §4.4's no-file-drawer rule, and the result document names which of P1–P5
fired.

---

## 6. The power analysis

§1.4 counted where the rule *bites*, which is support. This section is the power
analysis: it asks whether the three conjunctive match gates can jointly pass at
any plausible effect, and answers before any delta exists.

### 6.1 The scenarios, frozen blind

| scenario | paired SD | source |
|---|---:|---|
| **A — freshness-scale** | **0.005262** | `reports/epl_freshness_result.json`'s own `sd` over its 1,699 paired deltas — same corpus, same model, a predict-time change of comparable reach |
| **B — anchoring-scale** | **0.014449** | `reports/epl_anchoring_result.md`'s past-only estimand, paired sd over 2,280 fixtures — a larger predict-time change |
| **C — mechanism-scale** | **0.036** | a deliberately pessimistic extrapolation, named as invented, argued below |

Scenario C is grounded rather than guessed. The anchoring contrast's paired SD
scales with the size of its treatment, and the ladder is committed in
`reports/evidence/anchoring_per_fixture.csv`:

| market weight `w` | 0.15 | 0.30 | 0.50 | 0.75 | 1.00 |
|---|---:|---:|---:|---:|---:|
| paired SD | 0.003025 | 0.005832 | 0.009181 | 0.012690 | 0.015479 |

The relation is close to linear in the treatment's size, and mixing a fitted
scoreline grid halfway toward a max-entropy product grid is a larger
perturbation of the 1X2 law than any point on that ladder. Scenario C at 0.036
sits about 2.3× beyond the largest committed point. It is an extrapolation and it
is labelled one; a power analysis that tests only optimistic variances is not a
power analysis.

### 6.2 The construction, frozen and committed

The power simulation is **committed code**, not scratch: `epl.evwiden.power_simulation()`,
CLI `python -m epl.evwiden --power`, tested in `epl/tests/test_evwiden.py`. It
writes nothing; it prints the table and emits the `power` object that
`reports/evidence/widening.json` carries. Both files are already hashed by §8.3,
so freezing the power code costs no new hashed file and no lock-chain exposure.

* **Structure:** 85 fixtures, 52 treated, 62 week blocks, 6 seasons; by season
  26 / 11 / 12 / 12 / 12 / 12 with treated 21 / 4 / 7 / 6 / 7 / 7 — recomputed
  from the pinned artifacts by the harness itself, not typed in. Untreated deltas
  are **exactly 0.0**, never noisy, as the ADD design makes them.
* **Noise:** for a treated fixture *i* in week block *b*, the delta is
  `δ + s · ( sqrt(ρ)·u_b + sqrt(1−ρ)·z_i )` with `u_b` and `z_i` independent
  standard normals — an equicorrelated Gaussian whose correlation scope is **the
  week block and nothing else**. Season correlation is not modelled and is not
  claimed; ρ ∈ {0, 0.5} brackets it.
* **Consumption order, frozen:** per scenario,
  `u = rng.standard_normal((R, n_blocks))` **then**
  `z = rng.standard_normal((R, n_treated))`. This is frozen because it is the
  part v1 left unfrozen, and an unfrozen consumption order makes a stream
  unrecoverable (§6.4).
* **Replicates:** `R = 2,000`, simulation seed **20260827**, one
  `numpy.random.default_rng(20260827)` consumed in scenario order (A ρ=0,
  A ρ=0.5, B ρ=0, B ρ=0.5, C ρ=0, C ρ=0.5), and within a scenario one noise draw
  per replicate **reused across every grid point of δ** — common random numbers,
  so the power curve is monotone in δ up to Monte-Carlo error.
* **Gates:** all three deciding match gates exactly as §4.1 states them, using
  `epl.score.block_bootstrap_ci` at `B = 10,000`, `alpha = 0.05`, seed
  **20260814**, on the 62 week blocks and on the 6 seasons.
* **The bootstrap shortcut.** The committed implementation calls
  `epl.score.block_bootstrap_ci` directly. A vectorised inner loop is permitted
  **only** if a committed test asserts that its `(lo, hi, n_blocks)` equals the
  protected function's on the frozen structure, at three named noise draws, to
  `1e-15` — and reports `n_blocks` of 62 and 6. Absent that test, the shortcut is
  removed, not trusted.

**The MDE search grid and interpolation, frozen.**

* **Grid:** `δ ∈ {0, −0.0002, −0.0004, …, −0.0200}` — 101 points, step `2e-4`,
  δ the injected **treated-fixture** effect in RPS.
* **Power at a grid point:** the fraction of the R replicates at which **all
  three** deciding match gates pass.
* **MDE80:** scanning from `δ = 0` downward, the **first** adjacent pair of grid
  points that brackets power 0.80 is taken, and the MDE is the **linear
  interpolation in δ** between them. **Tie rule:** if a grid point's power is
  exactly 0.80, that grid point is the MDE and no interpolation is done.
  **Exhaustion rule:** if power does not reach 0.80 anywhere on the grid, the MDE
  is reported as `< −0.0200` with no interpolated value, and the table says so
  rather than extrapolating.
* **Reported scale:** the estimand's — the treated effect × 52/85.
* **Power at the bar** is evaluated at `δ = −0.0016346153846153847` exactly
  (`0.0010 × 85 / 52`), which is not on the grid and is not interpolated from it:
  it is its own evaluation at the same seed and replicates. **Power at 2× the
  bar** likewise, at `δ = −0.0032692307692307695`.

### 6.3 The frozen table

| scenario | ρ | power at the bar | joint MDE (estimand) | ratio to the −0.0010 bar | power at 2× the bar |
|---|---:|---:|---:|---:|---:|
| A freshness-scale | 0.0 | 0.451 | −0.001446 | 1.45× | 0.976 |
| A freshness-scale | 0.5 | 0.408 | −0.001571 | 1.57× | 0.950 |
| B anchoring-scale | 0.0 | 0.122 | −0.003741 | 3.74× | 0.321 |
| B anchoring-scale | 0.5 | 0.091 | −0.004180 | 4.18× | 0.267 |
| C mechanism-scale | 0.0 | 0.050 | −0.009309 | 9.31× | 0.087 |
| C mechanism-scale | 0.5 | 0.047 | −0.010522 | 10.52× | 0.080 |

These are the numbers the committed `power_simulation()` produces at the frozen
constants above, and they are the document's numbers. `power_reproduces()` must
compare the committed run against this table through the **real** comparison —
not a stubbed power object — and §8.5's conformance row L16 is that obligation.

**A structural fact, stated so no one reads the table as a defect in the
simulation.** Gate (i) is a threshold **at** the bar, not a test against zero, so
at a true effect exactly equal to the bar the probability of clearing it is about
one half whatever the variance is. **An 80%-power MDE equal to the bar is
unattainable by construction**, at any SD; the honest quantity is the ratio,
which is what the table reports. (This also disposes of the `MDE80 = 2.802·s/√52`
shortcut: that is the two-sided-test-against-zero MDE and does not describe gate
(i). The direction of its conclusion survives the correction.)

**The ruling. Nothing in §4 moves.** The bar stays −0.0010, the CIs stay, the
population stays 85, the constant stays 10.0. What changes is that the document
says, before any delta exists:

> **This design is underpowered against effects near its own bar unless the
> realised paired SD comes in at or below the freshness scale.** At the anchoring
> scale a true treated effect of −0.0016 would be missed about nine times in ten.
> A MISS IS THEREFORE SUBSTANTIALLY UNINFORMATIVE: "no adoption" here means "not
> detected at this power", not "no effect", and the result document must say so
> in those words.

§4.4's refusal to re-litigate a miss is unchanged, and this is not a licence to
re-run at a second seed, a larger corpus or a lower bar. It is the reader's
warning, frozen in advance, so that the size of the null cannot be argued about
after it arrives.

### 6.4 What the comparison with v1's scratch values actually supports

v1's six power rows were produced by uncommitted scratch code, and when the
committed implementation was written the two did not agree exactly. The reason is
now understood and is fixed at the source: v1 froze `R`, both seeds, the scenario
order and CRN-across-δ, **but not the consumption order of `u_b` and `z_i` inside
a replicate**, nor the fixture-to-block assignment beyond its counts. The scratch
stream was therefore unrecoverable and exact reproduction was never attainable.
§6.2 freezes the consumption order; the numbers in §6.3 are the committed
implementation's.

The comparison between the two sets of numbers is worth stating honestly,
because v1 stated it wrongly. v1's note claimed *"every difference is inside
Monte-Carlo error at R = 2,000 (SE ≈ 0.011 at p ≈ 0.45; ≈ 0.007 at p ≈ 0.10)"*.
Those are the standard errors of a **single** estimate. The two estimates come
from different, unrecoverable streams, so the correct comparator is the standard
error of their **difference**:

`SE_Δ = sqrt( p₁(1−p₁)/2000 + p₂(1−p₂)/2000 )`

| scenario, ρ | \|Δ power@bar\| | SE of difference | z | \|Δ power@2×\| | SE of difference | z | MDE relative change |
|---|---:|---:|---:|---:|---:|---:|---:|
| A, 0.0 | 0.010 | 0.015749 | 0.635 | 0.001 | 0.004790 | 0.209 | 0.4167% |
| A, 0.5 | 0.017 | 0.015587 | 1.091 | 0.006 | 0.007084 | 0.847 | 1.1590% |
| B, 0.0 | 0.019 | 0.009988 | 1.902 | 0.005 | 0.014793 | 0.338 | 0.0803% |
| B, 0.5 | 0.012 | 0.009357 | 1.282 | 0.007 | 0.014047 | 0.498 | 0.4808% |
| C, 0.0 | 0.008 | 0.007146 | 1.119 | 0.004 | 0.008819 | 0.454 | 1.1848% |
| C, 0.5 | 0.003 | 0.006590 | 0.455 | 0.001 | 0.008603 | 0.116 | 1.0625% |

**The defensible statement, and it is the one this document makes:** *none of
the twelve differences is significant at approximately 95% — the largest, B at
ρ = 0.0 at the bar, is 1.90 SE — but **four of the six `power@bar` differences
exceed one standard error of the difference** (A/0.5, B/0.0, B/0.5, C/0.0). All
six `power@2×` differences are within one SE of the difference.* The MDEs agree
to between **0.08% and 1.18%**.

Two claims are therefore withdrawn as unsupported: "every difference is inside
Monte-Carlo error" quoted beside one-estimate SEs, which is the wrong quantity
for comparing two streams; and the MDE agreement range "0.02–1.2%", whose lower
endpoint is not reproducible from the displayed values.

None of this conditions on an outcome. A power simulation reads only the frozen
SDs and the frozen 85/52/62/6 structure, which the committed implementation
recomputes from the pinned artifacts and matches exactly.

### 6.5 The realised-SD obligation, on the result document

After the run, the **realised paired SD of the treated deltas** is reported, and
**the joint-gate MDE is recomputed at that realised SD** — the fixed-scenario
simulation of §6.2 re-run with `s` set to the realised value, at the same
`R`, the same seeds, the same grid and the same interpolation rule, producing a
realised `power@bar`, realised `MDE80` and realised ratio in the same columns as
§6.3's table.

This is stated as an obligation on the **result document and on
`reports/evidence/widening.json`'s `power.realised` object**, not on the
pre-run harness, because the realised SD does not exist until the fits do. It is
a distinct quantity from the two-sided-test-against-zero MDE, which is not what
gate (i) is; a result document that reports the latter beside the realised SD
has not discharged this obligation.

**The realised numbers decide nothing and no threshold moves in response.** They
exist so the reader can size the null that §6.3's warning pre-announces.

---

## 7. Refusal semantics for the run

### 7.1 Typed refusals, by name

All derive from **`EvWidenError`**, caught by `main()`, printing `STOP: …` with
the type and offending key, exit **2** — the `RecalError` convention.

| type | fires when |
|---|---|
| `CorpusMissing` / `CorpusDigestMismatch` / `CorpusShapeMismatch` | the pinned parquet is absent / not `f31580073e…` / not 2,280 rows, 6 seasons, 212 blocks, `y` (993, 525, 762) |
| `ArchiveDigestMismatch` | `data/epl/matches.parquet` is not `323aa54af0…` or not 4,560 rows |
| `LedgerDigestMismatch` | `data/epl/fit/walkforward_ledger.jsonl` is not `869a558ce7…` or not 212 rows |
| `ConfigNotFrozen` | `epl/config_frozen.json` is not `9f2e086d…`, seed ≠ 20260611, widening ≠ `{mechanism: c, strength: 0.5}`, **or `realised_config_sha256` ≠ `78a51cd92c…`** |
| `MembershipMismatch` | a recomputed enumeration differs from §8.3's frozen digests (85 / 52 / 51 / 78, the 15 / 17 table cells, the byte-listed keys) **or from the per-label treated census `{MW0:2, MW3:2, MW6:7, MW10:4, MW19:0}` or the per-label cell census `{MW0:5, MW3:6, MW6:7, MW10:7, MW19:7}`** |
| `PredicateMismatch` | a fit's own provisional set ≠ the ledger's recorded `provisional_teams` at that cutoff |
| `EvidenceLeak` | a match dated ≥ its cutoff contributes to any `e(t, C)` |
| `CutoffLeak` | a training frame holds a match dated ≥ its cutoff, or a fixture appears in the fit that prices it |
| `CanaryFailed` / `EvidenceCanaryFailed` | `point_in_time_canary` fails, or the direction canary proved nothing (§7.3) / either leg of the evidence canary fails |
| `ControlMismatch` | any of the 820 identity-control probabilities differs from the corpus at 8 dp (§3.2) |
| `UntreatedMoved` | any non-treated row carries a non-zero delta — both an `e_min ≥ e*` stray and a thin-but-incumbent-widened row (§2.3) — or an Arm-A fixture outside the treated set differs from Arm B at 8 dp |
| `TableIdentityBreak` | an untouched cell's two arms' `sampler_digest`s differ; a treated cell's are equal; a parity comparison differs at any of the 32 cells; a cell simulated without a complete oracle; or a provisional-set field disagrees with the census (§3.3) |
| `TableMCImprecise` | §5.2's structural conditions — unequal per-particle season counts, unequal `n_particles` across the 15 deciding cells or between a cell's arms, a tally that fails either binding check of §5.1, or a tally file that is absent or fails its recorded digest |
| `FitFailed` / `UnpriceableFixture` / `ScoreMismatch` | as the predecessors define them, verbatim |
| `SchemaMismatch` / `RowConflict` | a ledger row lacks a required field / duplicate keys disagree on a non-volatile field |
| `ShardFailed` / `MergeIncomplete` | a shard exits non-zero or writes nothing / the merged key set is not exactly the pre-stated keys — not a superset, not a subset |
| **`StoreNotBuilt`** | a read-only pass required a point-in-time store and the store parquet is absent; the read-only accessor refuses and **never builds one** (§8.2) |
| **`SequenceViolation`** | a step of §8.4's frozen sequence ran without its predecessor's completion marker, or with a marker recorded under a different freeze commit |
| **`FreezeStateUnverified`** | the freeze/first-fit state could not be established from committed bytes and Git ancestry: the prereg blob is uncommitted, its commit is not an ancestor of HEAD, **or its current bytes differ from that blob**; a hashed file's bytes differ from the committed table; the recorded membership, schema or conformance digests do not match a fresh recomputation; the committed conformance table is not exactly §8.5's eighteen rows all green; a first-fit record names a different prereg blob; **or the record and its append-only witness disagree** (§8.6) |
| **`FeasibilityRecordMismatch`** | §0.6's census record is absent, fails the digest §8.3's freeze block binds, reports `completed: false`, or reports a priceable census that is not exactly this document's 32 cells. This document's table leg is SCOPED by that record, so a record that is not the record scopes nothing (§0.1, §8.3) |

**Twenty-seven named refusals; twenty-eight classes** counting the `EvWidenError`
base they all derive from. `epl/tests/test_evwiden.py`'s two inventory tests must
name 27 in both their tuple and their set, so that the "invents no refusal the
document never wrote" test closes the inventory exactly.

**UNRESOLVED is not a refusal and raises nothing.** Gate (iv) being left
UNRESOLVED by §5.4's precision rule is a **verdict**: it publishes, and it blocks
adoption. Conflating the two would make the harness raise on a result it is
required to publish.

A failed fit poisons its shard, a failed shard poisons the merge, shards are
waited on per PID, and a partial ledger is never scored. The merge refuses rows
stamped `harness_frozen: false`, by name — the predecessors' back-dating guard,
kept.

### 7.2 Provenance and resumability

Every row records `cutoff` · `e_star` · `seed` · `config_sha256` ·
`realised_config_sha256` · `archive_sha256` (the module-level digest over
`match_id, date, fthg, ftag`) · `ledger_sha256` · per-club `e` at 8 dp ·
incumbent and enlarged provisional sets · `match_ids` · `probs` (8 dp) ·
`health` · `harness_sha256` · `harness_frozen` · `blas_threads` · `shard_id` ·
clocks.

Every **table** row additionally records `provisional_control`,
`provisional_treatment`, `effective_posterior_control`,
`effective_posterior_treatment`, `sampler_digest_control`,
`sampler_digest_treatment`, `substantive_digest_control`,
`substantive_digest_treatment`, `parity_digest_simretro`, and — per §8.7 —
**the SHA-256 of its own tally file**.

Volatile fields (`wall_seconds`, `fit_seconds`, `seconds`, `shard_id`,
`started_at`, `host`) are excluded from the canonical form; `run_digest` is
SHA-256 over the canonical form; a resumed run's digest must equal an
uninterrupted run's byte for byte; the loader refuses disagreeing duplicates.
The runner is resumable per fit, keyed `cutoff|seed|config_sha256`.

`harness_frozen` records **what the guard established**, never what a caller
asserted — see §8.6.

### 7.3 The canaries

* **Results canary.** `epl.walkforward.point_in_time_canary`, run once as a
  precondition on the real archive **after** the freeze; `PASS: false` stops the
  run. It performs four real fits (`_forecasts` is called four times — clean and
  dirty at the cutoff, clean and dirty at the later date,
  `epl/walkforward.py:490-495`), which is why §8.4 makes it step 1 and why §2.4
  counts those four fits.

* **Evidence canary**, two-legged, because the existing canary rewrites results
  and cannot see the predicate input. The mutation is frozen exactly. Rows are
  selected by normalised date: `after` selects `date ≥ cutoff`, `before` selects
  `date < cutoff`. For the i-th selected row, 0-based in frame order:

  * `home_key := "__canary_corrupt__h{i}"`, `away_key := "__canary_corrupt__a{i}"`
  * `fthg := 9`, `ftag := 9`
  * **dates are not touched** — the cutoff partition must survive the mutation or
    the canary tests a different thing.

  Per-row unique sentinels are required, not decorative:
  `wcmodel.data.features`' duplicate-match dedup collapses content-identical
  rows, and a shared sentinel deleted the rows it meant to rewrite (fixed at
  06bd431). A canary that crashes is not a canary that fails.

  *Negative leg:* the evidence vector `e(t, C)` over the corpus's clubs, compared
  with `numpy.array_equal` on the float64 values **before rounding** — bit
  equality, not a tolerance — and both provisional sets (incumbent and enlarged)
  compared by set equality. Any difference is `EvidenceCanaryFailed`. *Positive
  control:* `max_t |e_corrupt − e_clean| > 1e-9`; the realised value is recorded
  on the canary record. *Both legs* record the number of rows the mask selected;
  an empty mask is a refusal, never a pass.

  The reference record from the authorised read-only pass: at cutoff 2022-08-13
  the negative leg moved `e` by 0.0 and the positive control by 52.53, with both
  provisional sets identical.

* **Identity canary.** An `e*` low enough to add nobody must yield
  `np.array_equal` with the corpus rows.

* **Direction canary.** The comparator is the **production path**:
  `finalize_grid(grid, posterior, provisional=True)` against the base
  `finalize_grid(grid, posterior, provisional=False)` computed from the same
  pre-widening `grid`. Comparing against `inflate_predictive` alone would compare
  against something the production map does not emit —
  `finalize_grid` (`src/wcmodel/model/draw_api.py:218-231`) applies
  `inflate_predictive` and then an **unconditional** renormalisation. Equality is
  **bit equality** (`numpy.array_equal`). Entropy must be strictly higher than
  the base **except** where `inflate_predictive`'s documented edge branch fires —
  a marginal mean at ~0 or at the largest representable score has no interior
  max-entropy solution and the grid is returned **unchanged**
  (`src/wcmodel/model/widening.py:225-233`) — in which case unchanged grid and
  equal entropy are the correct result. The canary records which branch every
  treated fixture took and **requires at least one treated fixture in the
  interior branch** with strictly higher entropy and a strictly positive
  `max |Δp|`. A direction canary in which every fixture took the edge branch is
  `CanaryFailed`: it proved nothing.

* **Seeded defects.** The adversarial audit seeds each defect class of §7.1 alone
  and demands red under the harness's own tests — **on synthetic corpora only**,
  as §7.4 defines synthetic.

### 7.4 "Synthetic" has an enforceable definition

A corpus, archive or ledger is **SYNTHETIC** iff every one of its values is
written literally in `epl/tests/test_evwiden.py`, or generated there by
arithmetic over literals written there. **No value may be read, copied, sampled,
transformed, or otherwise derived from** `data/epl/matches.parquet`,
`data/epl/fit/walkforward_predictions.parquet`,
`data/epl/fit/walkforward_ledger.jsonl`, `data/epl/sim/retro_r1.jsonl`, or any
artifact derived from them.

**The inventory of fact.** The synthetic generators in
`epl/tests/test_evwiden.py` are **three** — `_archive()`, `_corpus()` and
`_ledger()`, with `_world()` returning the three together. The invented club
names they use are **five** — `rich`, `mid`, `stale`, `cold` and `other`;
`other` appears in `_archive()` as the counterparty club and is not in the
module's `CLUBS` tuple, which is why an earlier inventory missed it. Every
statement in this document about the generators says "three generators" and
"five names", and there is no clause anywhere that says "both generators".

**The ancestry check is a mechanical obligation, not an assertion.** Before the
freeze commit, `epl/tests/test_evwiden.py` must carry a test that asserts,
mechanically, that none of the five invented club names appears in the pinned
archive's `home_key` or `away_key` columns or in the pinned corpus's club
columns, and that the three generators read nothing from the pinned artifacts.
Until that test exists and passes, the ancestry claim is an assertion about the
code and not a check on it, and the freeze block may not be rendered.

The `@pinned` tests are **not** synthetic and are not covered by this
definition. They read the pinned artifacts deliberately, to re-derive this
document's own census; they fit nothing and simulate nothing, and they are
authorised under §8.2.

---

## 8. The lifecycle

### 8.1 Why there is a v3, and this document's relationship to the fits that preceded it

**v1 is invalidated, by its own rule.** v1's R-B6 said that after any real fit
on the real archive exists — *"whether or not it produced a delta, whether or not
it was merged, whether or not anyone looked at it"* — any change to any hashed
file invalidates that preregistration, with no note, disclosure or ruling able to
restore it. Two real ADVI fits occurred: during v1's conformance-test
construction, before its `assert_may_fit` guard landed at `b112b51`, two evidence
tests invoked the real parity path and protected
`epl.simretro.ArchiveRunner` performed real ADVI fits on the pinned archive
before crashing on `epl.particles.ExcludedMassTooLarge` (man_city v
sheffield_united, 2019/20 MW0).

v1's own dated note recorded the event but drew the wrong conclusion from it —
that because the fits ran "through the protected retro machinery, not through
this experiment's treatment path", the no-fit attestation survived. It does not:
**the parity leg is a mandatory leg of this experiment**, and v1's R-B6 counts
any real fit without requiring a delta, a ledger row or an artifact. Under v1's
own remedy for that rule, v1 could not be repaired into legitimacy. That is why
v2 was written.

**v2 cannot be run as written, and that is a different fact.** v2 was never
invalidated by a violation of its own rules: it was executed against by the one
pass it authorised for exactly that purpose, and the measurement came back
against it. Its §3.3 required a **thirty-five-cell** parity oracle to complete
before any treated simulation; its §8.2 authorised pass 7, prospectively and by
name, to establish which of the thirty-five the protected runner can actually
price; the pass ran on 2026-08-28 and priced **thirty-two**. Three cells refuse
on `epl.particles.ExcludedMassTooLarge` against amendment A1's 0.02 ceiling
(§0.6). One unpriceable cell was pre-ruled to be enough, and v2's own text names
the remedy:

> *"a mandatory leg of this experiment cannot be executed on the shipped stack,
> **this preregistration cannot be run as written**, and the remedy is a NEW
> preregistration (v3) whose table leg is scoped to what the protected runner can
> actually do. Not a quiet narrowing of the 35 cells here."*

**This document is the remedy, and it is the whole of it.** v2 is closed with a
dated note recording that ruling; nothing else in v2 changed, and no number,
threshold, population, seed or gate of v2 was edited after its pass produced a
census. **The narrowing lives here, in a document written after the measurement
and honest about being written after it**, rather than in v2, where it would have
been a design edited by its own result.

**Neither event is hidden inside this document.** §2.4 counts pass 7's 35 fits
and 35 simulations in the lifecycle budget; §0.1 pins its record by digest; §0.6
publishes its census in full, including the exact cells, fixtures and masses that
refused; §8.2 carries all seven of v2's pre-freeze passes forward as **named
prior history** rather than re-authorising them; and §8.8's attestation states
the two v1 fits and the thirty-five pass-7 fits inside it rather than beside it.

**v3 inherits the invalidation regime v1's R-B6 fixed and v2 carried**
(§8.7): after the first
real fit **of this document**, any change to any hashed file invalidates this
preregistration, with no note able to restore it. **v3's no-fit clock starts at
v3's own freeze commit** (§8.3), and §8.4 step 1 is the first act that starts it.

**What that clock does and does not count, said before it starts.** The two v1
fits and pass 7's thirty-five are **prior history**: they preceded this document,
they were performed under other authorisations, and none of them produced a
delta, an estimand, a treatment arm, a §3.3 table cell or any number this
experiment publishes — pass 7's own outputs were protected `dc_native` control
rows, written outside the repository and deleted when the pass closed (§0.6).
They are named, counted and pinned rather than excused, and this document does
not repeat v1's mistake of arguing after the fact that a fit did not count. It
rules the scope in advance and then lives inside it: **from v3's freeze commit
onward, any fit or simulation that could produce an estimand, a treatment arm, a
delta, a table cell or a published number starts the regime, and nothing else is
authorised at all** — §8.2 authorises no pre-freeze pass that fits or simulates,
because the one question such a pass existed to answer has been answered.

**Two things v1 and v2 both got right and this document keeps.** No freeze block
was ever pasted into either, and no estimand of the experiment was ever fitted:
v1's two fits crashed inside the protected runner before producing a table, a
delta, a ledger row or any artifact, and pass 7 produced only the census.
`data/epl/fit/evwiden*` and `data/epl/sim/evwiden*` do not exist except for pass
7's single authorised record, and the shared point-in-time store's
`results.parquet` is byte-untouched throughout both events (184,115 bytes, mtime
2026-08-14 18:41). **Nothing in this document, and nothing in the harness it
binds, is informed by an outcome of the experiment**, because no outcome of the
experiment exists. It **is** informed by the census — that is what §0.6 says it
is for, and the census is a fact about the protected stack's capability, not a
result of the treatment.
### 8.2 The pre-freeze regime — read-only, enumerated, and mechanically read-only

> **Before the §8.3 freeze commit, no harness code fits and no harness code
> simulates, except where this section authorises a pass BY NAME, prospectively,
> before it runs. Reading the pinned artifacts is permitted, is read-only, and is
> enumerated by name in the freeze commit. Seeded-defect audits and the
> canaries' adversarial legs run on synthetic corpora only, as §7.4 defines
> "synthetic". No pre-freeze pass may enter any estimand, produce a treatment
> arm, produce a delta, or produce any published number.**

There is no synthetic-only clause anywhere else in this document to contradict
this one, and no clause keyed to an output directory. **The refusal is keyed to
the freeze state and to the artifact identity being read, never to the output
directory** — a `--dir` outside the default directories moves nothing, because
`data/` is gitignored and a directory-keyed guard would let a scratch run fit the
real archive and leave no Git trace at all.

#### The no-fit clock, defined once, and closed

v1 died because a real fit occurred that its own R-B6 counted, and v1's dated
note then argued that the fit did not count because it went through protected
machinery (§8.1). That argument was wrong, and this document is not going to
repeat it after the fact. It rules the scope **in advance** instead:

> **v3's no-fit clock — the regime §8.7 opens — is started by any fit or
> simulation that could produce an ESTIMAND, a TREATMENT arm, a delta, a table
> cell, or any number this experiment publishes.** §8.4 step 1 is the first such
> act and §8.7 says so. **It starts at v3's own freeze commit** (§8.3): nothing
> before that commit is authorised to fit or simulate at all.
>
> **This document authorises no pre-freeze pass that fits or simulates.** v2's
> §8.2 carried one — pass 7, the `dc_native` parity feasibility pass, authorised
> by name, prospectively, quarantined outside the repository, discarding its own
> outputs and leaving one record. That authorisation was v2's, the pass ran under
> it on 2026-08-28, and **the question it existed to answer has been answered**
> (§0.6). There is nothing left for such a pass to establish, so this document
> grants no equivalent and no successor. Its six pre-freeze passes are read-only
> and are the six v2 listed first.
>
> **"A table cell" in that list means §3.3's cell** — a control arm, a treatment
> arm and the delta between them. The protected oracle's own `dc_native` rows are
> that cell's PRECONDITION and not that cell: they carry a `substantive_digest`
> of the control side and no arm comparison, no delta and no estimand. That
> distinction is stated here because §0.6's census was produced from exactly
> those rows and this document is scoped by it, so a reader has to be able to see
> what the census was and was not made of.

**This reopens nothing and excuses nothing.** §8.1 stands on both counts: v1 was
invalidated under its own rule; v2 was defeated by its own executed pass and is
closed rather than repaired. The fits that preceded this document are named,
counted (§2.4) and pinned (§0.1), and the clock this section defines is v3's own,
prospective, and the only clock v3 is entitled to define.

#### The six authorised passes, authorised prospectively — and the seventh, which is history

These six are authorised **for this document, prospectively**: they are v3's own
pre-freeze passes, to be run under v3 before v3's freeze commit, and each must
appear in §8.3's enumeration. **All six are read-only**; none of them calls
`epl.dcfit.fit_epl` or `epl.leaguesim.simulate`; none writes inside the
repository. **There is no seventh**, and the reason is in the paragraph after the
list.

1. `python -m epl.evwiden --membership` and `--plan` — read the pinned corpus,
   archive and ledger; compute §2.2's cells, §2.3's population, §3.3's 32 table
   cells and the digests the freeze commit records.
2. `python -m epl.evwiden --canary --no-results-canary --dir <scratch>` — §7.3's
   evidence canary on the real archive, with any point-in-time store built in a
   `tempfile.TemporaryDirectory` and never under `paths.STORE_DIR`.
3. `pytest epl/tests/test_evwiden.py`, including the `@pinned` tests that
   re-derive the census, the grid table, the membership and the table cells, and
   including §8.5's conformance scenario run, whose JSON report is the artifact
   `--conformance` and `--freeze-block` consume.
4. `python -m epl.evwiden --partial-engine` — one partial engine pass at the
   first opening (2019-08-09): construction, `fit_points`, the enlarged set,
   `assert_cutoff_clean` and `assert_point_in_time` — the whole of the fit path
   **except** the call to `dcfit.fit_epl`. No sampler runs; the shared
   point-in-time store must be byte-identical afterwards, and the pass compares
   its bytes and mtime before and after to say so.

   **This pass is executable, and the reason the guard permits it is structural
   rather than attested.** The review's NEW-B5 found the opposite: `Engine`'s
   constructor called the guard, the guard refused the pinned archive while
   unfrozen, and the freeze block enumerated a pass no command could run. The
   Engine this pass builds is constructed in a mode that **cannot fit** —
   `Engine.fit` refuses on that flag **before it imports `dcfit`**, which is a
   claim about the order of two statements and is asserted by a committed test
   reading the function's own syntax tree, because a review found the sentence
   false while the pass was still callable.
5. `python -m epl.evwiden --freeze-block`, which reads the pinned artifacts to
   render §8.3's commit rather than have a human transcribe digests.
6. `python -m epl.evwiden --power`, which reads only the frozen SDs and the
   frozen structure recomputed from the pinned artifacts, and reproduces §6.3.

**The seventh pass is prior history and is enumerated as such.** v2's §8.2 pass
7 — the `dc_native` parity feasibility pass — ran on 2026-08-28 under **v2's**
authorisation, once, at HEAD `9adc3bc`, quarantined outside the repository, and
produced §0.6's census and nothing else. It is not authorised here, because it is
not repeatable here: its record exists, §0.1 pins it by digest, this document's
whole table leg is scoped by it, and a second execution would be a second answer
to a settled question. **The freeze block enumerates it in a HISTORY section,
distinct from the six above**, recording its date, its HEAD, its census and its
record digest, so that the enumeration stays complete without pretending the pass
was v3's to authorise. A pass 7 executed **under this document** — before or after
its freeze commit — is an invalidation (§10).

**The rule for any further pre-freeze pass.** It must be read-only; it may not
call `dcfit.fit_epl` or `leaguesim.simulate`, and may not build a store under
`paths.STORE_DIR`; it may write nothing under `data/`, `reports/` or anywhere in
the repository; and it must be **added to the freeze block's enumeration before
the freeze commit is made**. The freeze block's list stays binding and must be
complete — an unenumerated pre-freeze pass is a protocol deviation whether or not
it touched anything.

**The one write a pre-freeze command may make, and it is not inside the
repository.** The enumeration's completeness is only worth something if the
harness cannot write outside it, and a review found that it could: `--script`
refused the default production target while unfrozen but accepted **any other
directory**, including one inside the repository that happened to sit outside the
narrow set of paths the tests exercised. The enumeration was therefore false as a
statement about writes. Two clauses close it, and they are the whole rule:

> **`--script` writes the launcher only AFTER the freeze commit.** It is a
> post-freeze operational artifact — §8.4 step 1 is the first thing the launcher
> runs — so a pre-freeze `--script` is refused at **every** target, not only the
> default one. The refusal is on the freeze state and not on the path.
>
> **After the freeze, `--script` writes to the preregistered run directory and
> nowhere else.** It takes no target that resolves inside the repository other
> than `data/epl/fit/evwiden/launch.sh`, and it takes no interpreter, no command
> prefix and no forwarded keyword arguments: the launcher's contents are a
> function of this document's frozen constants and of the harness bytes §8.3
> hashes, and a caller who could name the Python that runs it could substitute an
> alternative implementation into every post-freeze step at once (§8.6's closure,
> the injection clause).

A pre-freeze command that writes anything else, anywhere, is a protocol deviation
whether or not the file mattered.
#### The read-only store accessor — the mechanism, not the promise

"Read-only" is a property of code, not of intent, and v1's harness violated its
own clause without anyone noticing: `--membership`, `--plan` and `--freeze-block`
all reached `table_cells`, which called `epl.fit.build_store(played)` at the
**default** root, and `build_store` can unlink and rewrite the shared
`results.parquet` (`epl/fit.py:177-203`). A pre-freeze command that can delete
and rebuild the project's point-in-time store is not read-only in any sense the
word carries.

**The binding mechanism:**

> A single **read-only store accessor** is the only route by which any pre-freeze
> path may obtain a point-in-time store. It opens the existing store parquet and
> returns it. **If the store parquet is absent it raises `StoreNotBuilt` and
> stops. It never builds, never writes, never unlinks, and takes no "build if
> missing" argument and no alternate root.**
>
> **It also may not create the store's directory as a side effect of checking
> it.** The accessor's own check-then-construct shape was a time-of-check /
> time-of-use hole, and not a theoretical one: `BitemporalStore.__init__`
> **creates its root directory** (`src/wcmodel/data/store.py:20-23`), so an
> accessor that verified `results.parquet` existed and then constructed the store
> would create the very directory tree it had just found missing whenever the two
> disagreed — a pre-freeze command writing into `paths.STORE_DIR` while the
> document claims nothing has been touched. The accessor therefore **records the
> root's existence, the parquet's existence, its byte size and its mtime before
> constructing anything, constructs only if all four say the store is already
> there, and re-verifies the same four afterwards** — raising `StoreNotBuilt` if
> the store was absent and `StoreNotBuilt` again if construction created or moved
> anything. A committed test drives it against a root that vanishes between the
> two moments and requires the refusal **and** that no directory was left behind.
>
> `epl.fit.build_store` is **not reachable** from `--membership`, `--plan` or
> `--freeze-block`, by any call path, at any depth. A committed test asserts the
> unreachability behaviourally — it executes all three commands against a store
> root whose parquet has been removed, requires `StoreNotBuilt` from each, and
> requires that nothing was created — and a second asserts that the shared
> store's bytes and mtime are unchanged by all three.

Post-freeze paths that legitimately need a store built (the canary, the fits, the
table leg) obtain it the way they always did; the closure is on the **pre-freeze**
commands, which are exactly the commands that run while the document still claims
nothing has been touched.

### 8.3 The freeze commit

This document is committed **before** the conformance work it binds. Then, in
order:

1. **The harness is revised and audited** — `epl/evwiden.py` and
   `epl/tests/test_evwiden.py` are brought to implement **this document**, with
   seeded defects and canaries on synthetic corpora only. §8.5's conformance
   report must be green on behavioural predicates **and must be backed by the
   independent pytest artifact §8.5 requires**, and an independent dual audit —
   one cross-model review and one in-tree adversarial seed audit — must report no
   blocking finding.

2. **A follow-up commit appends the freeze block to this document**, rendered by
   `--freeze-block`, carrying:

   * the **harness hash table** — file, line count and SHA-256 for each of
     `epl/evwiden.py` and `epl/tests/test_evwiden.py`, and the schema identifier
     `epl-evwiden-3`;
   * the **membership digests** — the 85 thin fixture keys, the 52 treated keys,
     the 51 newly-flagged club-cutoff cells, the 78 fit openings, the 15 treated
     and 17 untouched table cells, the three excluded cell keys of §0.6, and
     **both** per-label censuses of §3.3, each serialised canonically and hashed,
     recomputed by the harness's own code from the pinned artifacts;
   * the four pinned artifact digests of §0.1 and `realised_config_sha256`;
   * **the SHA-256 and byte size of §0.6's feasibility census record** — this
     document's table leg is scoped by that file, `data/` is gitignored, and a
     scope that rests on an unhashed local file rests on nothing. Binding it into
     the block is what makes the census checkable by a reader of the repository
     rather than only by a reader of this machine;
   * the **enumeration of every pre-freeze pass actually run**, complete, in two
     parts — the six of §8.2 authorised under this document, and the HISTORY
     entry for v2's pass 7 with its date, HEAD, census and record digest;
   * the conformance report of §8.5, all eighteen rows green, **together with the
     identity of the pytest artifact it was read from** — its path, its digest,
     its test-id list and its pass count.

   *If any hash differs at the time the run is executed, it is not the run this
   document preregisters.*

   **`--freeze-block` refuses to render** while any of the following holds, and
   the refusals are unconditional — there is no bypass parameter and no
   caller-supplied substitute for any of these inputs:

   * the conformance report is **not exactly §8.5's eighteen rows L1–L18**, or
     any row is red or absent. **A nonempty all-green SUBSET is a refusal**, not
     a pass: a renderer that accepted any green subset would render over a report
     that had simply dropped the rows it could not satisfy, and a review found
     that exact acceptance in v2's harness;
   * the conformance report was not **produced by and cross-checked against**
     §8.5's committed pytest artifact — same eighteen test ids, all passing,
     count eighteen;
   * §7.4's ancestry test is absent, or §6.3's power table is unreproduced;
   * **§0.6's feasibility census record is absent, fails its pinned digest, says
     it did not complete, or reports a priceable census that is not exactly this
     document's thirty-two cells.** v2's block refused over an *infeasible*
     census, which was the right refusal for a document claiming thirty-five.
     This document claims thirty-two **because** three cells are unpriceable, so
     the condition inverts: the block refuses unless the record says exactly
     that, cell for cell. A census that suddenly prices all thirty-five is as
     much a refusal as one that prices thirty-one — either way the document is
     scoped against a measurement that is no longer the measurement.

   A hash table committed over code that does not implement the document freezes
   the wrong thing, which is the one thing a hash table must never do — and a
   hash table committed over a census the document is not scoped to freezes a
   design against a question that was answered differently.

3. **Only then does the first real fit of this document run**, and it runs as
   step 1 of §8.4's sequence and in no other way.

**The write set is closed.** All code lands in `epl/evwiden.py` and
`epl/tests/test_evwiden.py`; the run writes only `data/epl/fit/evwiden*`,
`data/epl/sim/evwiden*` — which is also where v2's pass-7 record already sits, at
`data/epl/sim/evwiden_parity_feasibility.json`, **read-only to this document and
never rewritten by it** — `reports/epl_widening_result.md` and the §9 evidence
files. `src/`, `scripts/`, `site/`, `tools/`, `config/`, `.github/`,
`epl/simretro.py`, `epl/simmetrics.py`, the season ledgers,
`epl/season/points_adjustments.jsonl`, `data/epl/sim/retro_r1.jsonl` and the
pinned corpus are not written. `PYTHONPATH=src scripts/oa_lock.py` must print
`LOCK VALID` after every commit this work produces — checked, not assumed.

**This document's commit adds this document and the closing note on v2. Nothing
else.** No amendment-ledger cross-reference is appended: that file is append-only
under standing protection, its numbered entries mark changes to what a published
surface or frozen rule means, and a research preregistration that touches nothing
shipped binds by its own commit. If this experiment adopts, the adoption ruling
is the numbered entry.

### 8.4 The frozen post-freeze sequence, with completion markers

Five steps, in this order, and **nothing else may run on the real archive between
them**. Each step **refuses unless its predecessor's completion marker exists**;
the refusal is `SequenceViolation`.

Markers live at one fixed location, `data/epl/fit/evwiden/sequence/`, one JSON
file per step. Each marker records the step name, whether the step **completed**,
the UTC time, the freeze commit under which it was written, the harness file
digests at that moment, and a digest of what the step produced. A marker written
under a different freeze commit is not a marker for this run.

**Markers are written once.** They are MANIFEST members (§9.3), and §9.3's
manifest is computed at publication, so a marker rewritten after it has been
hashed leaves the manifest describing a file that no longer exists in that form.
A second write under the same freeze commit therefore **re-verifies**: it
compares what the step produced against what the marker records, returns the
marker unchanged if they agree, and refuses if they do not. A step that ran twice
under one freeze and produced two different things has not been resumed; it has
been re-run, and the second run is not the step the first marker unlocked.

**A marker may record a FAILURE, and a failure marker unlocks nothing.** A step
that ran and failed writes its marker with `complete: false`, and the step it
would have unlocked refuses exactly as it refuses on an absent one. The point is
not bookkeeping: it makes a failed step DURABLE, which is what closes the
retry channel §4.4's no-file-drawer rule exists to close.

**A file that records none of that is not a marker.** The next step checks the
one it is handed: the schema identifier is `epl-evwiden-3`, the recorded step is
the step whose path it sits at, the freeze commit is present, the harness digests
are the current bytes, and a product digest exists. Nothing here proves the step
*happened* — a marker is a file, and §8.6 is plain about what a file can
establish — but a marker that does not even claim to describe this step of this
document under this freeze cannot unlock the next one, and an empty JSON object
is not a completed step.

**Step 2's opening is the document's, not the shard's.** `--run --limit 1`
refuses unless the point it would fit is 2019-08-09 — the opening §8.4 names,
first by date and by nothing else. A different shard's first point is a different
opening, and choosing one at the command line would make step 2 the selection
step §8.4 says it is not.

> **Step 1 — the post-freeze results canary. This is the first post-freeze act
> and it performs the first real fits of this document.**
> `python -m epl.evwiden --canary --dir <the preregistered run directory>`, run
> once, after the freeze commit. It executes
> `epl.walkforward.point_in_time_canary` (four fits) and the evidence, identity
> and direction canaries. `PASS: false` on any leg stops the experiment and the
> failure publishes. Record: `data/epl/fit/evwiden/canary.json`.
> Marker: `sequence/step1_results_canary.json`.
>
> **The failure publishes BEFORE the refusal is raised, and step 1 runs once.**
> The canary record is written and a `complete: false` marker is left, and only
> then does the process stop. A failed canary that left neither would be a run
> that could simply be attempted again, and a retry conditioned on the first
> attempt's outcome is the file-drawer channel wearing a different name. Step 1
> therefore refuses outright while a step-1 marker of either kind exists: a
> continuation after a failed canary needs a **new dated pre-freeze note written
> before the retry**, saying so, not after it.
>
> **Step 2 — the single-opening exercise.**
> `python -m epl.evwiden --run --limit 1 --dir <scratch>` — one fit at the
> **first opening by date, 2019-08-09** (10 fixtures; ledger incumbent set
> `{sheffield_united}`; the §2.1 union adds exactly `{aston_villa, norwich}`),
> written to a scratch directory outside the preregistered run directory. Its
> purpose is to exercise, once and end to end, the one path no test can execute
> without a real fit: the identity control at that opening, the cutoff and
> point-in-time assertions, the three predict passes, the direction canary and
> the row schema. **Its numbers enter no estimand**; its rows are never merged;
> the opening is named here, before the fit, and it is first by date and not by
> anything else, **so it is not a selection step**. Because the results canary is
> a same-directory precondition of `--run`, the scratch directory carries its own
> copy of the step-1 canary record; that copy is a precondition artifact and
> enters nothing. Refuses without step 1's marker.
> Marker: `sequence/step2_single_opening.json`, written to the **preregistered
> run directory** (not the scratch directory), recording the opening, the row
> count, the row digest and the scratch path.
>
> **Step 2 is a COMMAND, and the launcher runs it.** A review found this step
> non-executable as v2's harness wrote it: the generated launcher carried only
> comments where step 2's command should be, and the sequence guard —
> which keys a step's location to the preregistered run directory — refused the
> scratch `--dir` the step is *required* to use. Two clauses close that, and both
> are properties of the code rather than of a comment:
>
> * **The step's own scratch target is part of the step.** `--run --limit 1`
>   requires a `--dir` that is **not** the preregistered run directory, refuses
>   one that is, and writes its marker to the preregistered directory regardless
>   of where its rows went. A step whose only legal target the guard refuses is
>   not a step; it is a sentence.
> * **The launcher emits it as a real command line**, between a
>   `need_marker step1_results_canary` command and step 3's, with the scratch
>   directory named — the launcher creates it — and §8.4's committed launcher test
>   reads **command lines only** and requires step 2's among them.
>
> **Step 3 — the four shards, sequentially.**
> The 78 openings are partitioned strided across **`SHARDS = 4`**, run
> sequentially by `data/epl/fit/evwiden/launch.sh`. Refuses without step 2's
> marker. Marker: `sequence/step3_shards.json`, recording all four shard ledger
> digests and their key counts; it is written only when all four shards have
> exited zero and written their expected key sets.
>
> **Step 4 — the merge.**
> Refuses without step 3's marker. The merged key set must be exactly the
> pre-stated keys — not a superset, not a subset (`MergeIncomplete`) — and the
> structural-zero guard of §2.3 runs here, in both directions.
> Marker: `sequence/step4_merge.json`. Product: `data/epl/fit/evwiden.json`.
>
> **Step 5 — the parity oracle, then the table's 32 cells.**
> Refuses without step 4's marker. The parity oracle runs protected
> `ArchiveRunner` at all 32 priceable cells to **completion**, writing
> `data/epl/sim/evwiden/parity.jsonl` (32 rows), and only then may any arm of any
> cell be simulated (§3.3). Marker: `sequence/step5_parity.json`, written when
> `parity.jsonl` holds all 32 cells with matching digests.

**`launch.sh` must emit exactly this order.** v1's launcher ran
canary → shards → table → merge, with no step-2 marker, and would have re-run the
once-only canary after a manual step 2. A committed test asserts that the
generated script's step order equals the five above, that each step's precondition
check appears before its command, and that removing any marker makes the
corresponding step refuse.

**The precondition check is a COMMAND, and the test reads it as one.** The
in-tree audit found the obligation unenforced in exactly the way an obligation
about text gets unenforced: every `need_marker` line could be deleted from the
generated script and the committed test stayed green, because the marker's NAME
also appears in the `#   marker: sequence/stepN_*.json` comment inside the
preceding block, so `text.index(step) < text.index(command)` held vacuously. The
test reads the script's **command lines only**, ignoring comments, and requires
one `need_marker <predecessor>` command before each step's own command. (The
harness refuses independently — `--run`, `--table` and `--merge` each pass their
step to the sequence check — so what the launcher's line buys is the early
refusal, not the guarantee. That is a reason to test it correctly, not a reason
not to.)

**`SHARDS = 4` is enforced, not defaulted.** `--shards` may not be passed a
different value: the CLI refuses it, the launcher generates four, and the
MANIFEST's shard filenames are the four of §9.3. A run at any other shard count
is not the run this document preregisters.

**Each step runs ONCE, at ONE target, and a second run of a step is not a
resume.** The write-once markers above close that for the steps whose product is
a file the marker digests. Step 5 needed one more clause, because its product is
expensive and its target was a parameter:

> **The table ledger is fixed, and `--table-ledger` names nothing.** A review
> found that the CLI accepted an arbitrary table-ledger path, and that the table
> branch checked only that step 4 preceded step 5 — performing the whole
> expensive run, and *only then* attempting the write-once step-5 marker. A
> caller who had seen the first table's outcome could therefore point at a second
> ledger, run the leg again, and have the second outcome exist before the marker
> conflict was raised. **That is an outcome-conditioned second run of the
> deciding leg**, which is the file-drawer channel §4.4 exists to close, wearing
> the clothes of a path argument.
>
> The ledger is therefore resolved from the frozen law and is not a parameter of
> any deciding path: `data/epl/sim/evwiden/table_cells.jsonl` and nothing else.
> **And step 5 claims its marker BEFORE it simulates**, not after: the write-once
> marker is opened at the start of the step and completed at its end, so a second
> attempt is refused before a single fit is spent rather than after a second
> outcome exists. A step-5 marker whose run did not complete records
> `complete: false` and unlocks nothing (§8.4's failure rule), which is the same
> durability the canary has and for the same reason.

**§8.7's regime comes into force at the completion of step 1**, not step 2. From the
moment the results canary's first fit completes, a real fit on the real archive
exists, and §8.7 applies.

### 8.5 The conformance report — behavioural predicates, not names

`--freeze-block` requires a green conformance report, and a conformance report is
worthless if its rows check that names exist. v1's fourteen rows checked field
names, constants, callables, a subclass count and a substring — they could all be
green while the obligations they were named for failed, and they were. **Every row
of v2's report executes a scenario that fails under its own defect class.** A row
that cannot go red is not a row.

**The rows execute against a synthetic 32-cell table leg.** Half the obligations
below are about the table — the scorer, the estimator, the unanimity rule, the
parity ordering — and a row cannot execute one of those against a hand-built dict
without becoming the shape this section condemns. The report therefore builds a
complete synthetic leg (every value written literally in `epl/evwiden.py`, §7.4-
synthetic for the same reason the test module's world is) and runs the production
`run_table`, `score_table`, `table_gate`, `paired_mc_bootstrap` and `unanimity`
over it.

| row | obligation | the scenario it executes |
|---|---|---|
| **L1** | both arms from one posterior (§2.3) | build a row whose **corpus probabilities differ from Arm B**, then require `delta` to equal `rps_A − rps_B` exactly, `delta_vs_corpus` to equal `rps_A − rps_native` exactly, and the two to be different numbers — so rewiring the delta to read the corpus, the defect this row names, moves it. (The superseded row's fixture set Arm B equal to the corpus, so its `or` disjunct greened from an equality its own fixture forced, and the in-tree audit proved the row stayed green under exactly the defect it names.) |
| **L2** | per-horizon gate, no cross-horizon average (§4.1) | score a real 32-cell leg through `score_table` whose 32-cell pooled mean passes while MW6's treated mean exceeds +0.0002; `table_gate` must return **FAIL**, resolved, with iv-a failed, and no pooled figure may appear anywhere outside the `withdrawn` note |
| **L3** | the MC estimator is tie-aware and jointly resampled (§5.1–5.2) | run the estimator over the whole **30-tally object of the 15 deciding cells**: a per-cell (quadrature) combination shrinks the MW6 label SE and the joint one does not; and tally a tie block of span 2, which must carry 1/2 on each position rather than an ordinal 1 and 0 |
| **L4** | the unanimity rule (§5.4) | run the **real rule** over the real 30-tally object: 200 recomputed iv-c verdicts at the frozen `K` and seed; inverting the point verdict must make every one dissent and gate (iv) come back UNRESOLVED with `P5` fired; a fabricated `K = 1` object must **not** resolve it; one dissenting `k` out of 200 must fire the counting rule; and the joint per-replicate draw must **disagree** with the same rule de-paired per cell |
| **L5** | parity complete before treatment (§3.3) | run the leg with an oracle of 31 cells and with none — each must raise `TableIdentityBreak` before **any** arm is simulated; run it with a control arm that drifted from protected output — the refusal must arrive after exactly **one** simulate call, the control's; and assert no `require_parity` parameter and no oracle `--limit` exist |
| **L6** | pre-freeze read-only (§8.2) | point the store root at an empty directory and call both the read-only accessor and `table_cells` — the function `--membership`, `--plan` and `--freeze-block` all reach: `StoreNotBuilt` from each, nothing created, no build parameter, `table_cells` never naming `build_store` on its own syntax tree, and the shared store's bytes and mtime unchanged across the row |
| **L7** | no freeze-state boolean on any fit surface (§8.6) | assert no fit or simulation surface accepts a freeze-state or implementation-check argument, and that `merge`'s two lifecycle keywords are refused at a preregistered target; then call `assert_may_fit`, `Engine`, `TableRunner`, `ParityRunner`, `run_fits`, `run_table`, `simulate_arm` and `run_canary` on the pinned artifacts while unfrozen and require refusal from **each**; and assert that **no feasibility surface unlocks anything under this document** — §8.2 authorises no pass that fits or simulates, the permission set and pass state are not rebindable module globals, and the parity oracle refuses on the pinned artifacts while unfrozen like every other surface |
| **L8** | first-fit state is global, validated, and ratcheted (§8.6) | assert the record's and the witness's functions take no directory argument; plant a record naming a different prereg blob and require `FreezeStateUnverified`; strip its identity fields and require it again, because a record that omits a field cannot be checked against it; **delete the record while its witness stands and require the post-first-fit state to hold** — the ratchet must not reset; plant a record with no witness line and require refusal; and break the witness's chain digest and require refusal |
| **L9** | the frozen sequence (§8.4) | remove each marker in turn and require the corresponding step to raise `SequenceViolation`; record a **failed** step and require it to unlock nothing; require a second, different marker write under one freeze commit to refuse; read the generated `launch.sh` as **commands** — every precondition must be a `need_marker` command line before its step's command, not a comment naming the marker, and **step 2's own command must be among them and must be executable**: its scratch `--dir` is permitted and the preregistered directory refused; require `merge`, `run_table` and `run_parity_oracle` to raise `SequenceViolation` when called **directly**, without the CLI; require a marker whose `complete` key is absent to unlock nothing; and require step 5 to claim its write-once marker **before** it simulates |
| **L10** | tallies are bound and rebound (§8.7, §9.3) | replace a tally NPZ with a structurally valid different one after the run: the read must refuse on the recorded digest, and refuse **again** on §5.1's binding checks when the row's digest is forged to match; then swap one deciding cell's tally under a scored leg and require `score_table` to refuse rather than re-derive a gate; and assert `score_table` carries **no `tallies=` and no `mc=` parameter at all**, so deciding evidence cannot be supplied at any target |
| **L11** | `sampler_digest` purity (§3.3) | assert `list(signature(sampler_digest).parameters) == ['run','tallies']`; and drive the runner's own paired-arm sequence with two books differing only in `provisional` over one run and one tally — the two arms' `provisional` fields must differ and their sampler digests must be **equal** |
| **L12** | the identity control is exercised, not stubbed (§3.2) | execute all three checks `Engine.fit` makes — the exact eight-decimal comparison against a 1e-9 drift, the `UntreatedMoved` loop against a fixture that moved, and the pass-2/pass-3 agreement — and require `Engine.fit` to **call all three**, read off its own syntax tree |
| **L13** | the structural-zero guard is two-sided (§2.3) | merge a row with `e_min ≥ e*` and a non-zero delta, and a thin-but-incumbent-widened row with a non-zero delta; each must raise `UntreatedMoved` |
| **L14** | both per-label censuses and the feasibility scope are pinned (§0.6, §3.3) | perturb one cell's treated set between labels, keeping the 32/15 totals intact; the census must raise `MembershipMismatch` on the per-label TREATED pin, not only on the totals; move a cell between labels keeping 32 intact and require the per-label CELL pin to fire; require the three excluded keys of §0.6 to be absent from `table_cells` and un-nameable by any caller; and drive `--freeze-block` against a census record that is absent, digest-mismatched, incomplete, and priceable-at-35 — each must refuse with `FeasibilityRecordMismatch` |
| **L15** | the evidence contract is closed (§9) | drop one of the 49 MANIFEST paths; corrupt a byte size; check `scored.per_cell` survives the projection; pass `--shards 2`; require all five sequence markers to be manifest members; and require the 32 tally names to be exactly the schedule minus §0.6's three excluded keys — each must refuse |
| **L16** | the power table reproduces (§6.3) | run the committed `power_simulation()` at the frozen constants through the **real** comparison, not a stubbed power object, and require all six rows, **every published column including `ratio`**, and a 101-point curve behind each |
| **L17** | the always-PASS controls are measured (§9.1) | measure a run containing one `UntreatedMoved`-class row and one `PredicateMismatch`-class row, then project it through `evidence_object`: the published `controls.untreated_moved.n` and `controls.predicate_mismatch.n` must be non-zero and their `PASS` false, and `merge` must call the measurement |
| **L18** | frozen constants are not overridable (§2.3) | attempt a different `B`, bootstrap seed, `MC_BOOT`, `MC_SEED`, `K`, `e*`, replicate count or shard count through every public surface and CLI flag; require `n_sims`, the simulation seed and the chunk size to be **absent** from every table surface and resolved from the frozen law; require `--limit` to name nothing but §8.4 step 2; require `--table-ledger` to name nothing at all and the ledger to be resolved from the frozen law; and require `--script` to be refused pre-freeze at **every** target and to accept no interpreter, command prefix or forwarded keyword post-freeze |

The report is emitted by `--conformance`, embedded in the freeze block, and
`--freeze-block` refuses while any row is red or absent. **There is no bypass
parameter**: the precondition is unconditional, so the renderer consumes the
report through the assertion and through nothing else — a bypass-rendered block
would become the committed evidence for its own freeze state, and §8.6's
condition (5) reads the block's conformance table back for the same reason.

#### The report may not be its own witness

**This is the clause that closes the defect four review rounds could not close in
the harness**, and it is written as law here because it is a statement about
where evidence comes from rather than about any one row's predicate.

v2's arrangement was circular in a way that no amount of strengthening the rows
could fix. `implementation_report()` executed the scenarios **and** reported on
itself; the principal test asserted the report's own `ok` fields; `freeze_block`
consumed the same object; and the committed-block guard accepted **any nonempty
all-green subset** of the rows rather than the exact set. Each of the four
artifacts believed the one before it, and the chain terminated in a function
grading its own homework. A row that silently stopped executing its scenario, or
a report that simply omitted a row it could not satisfy, was green everywhere.

> **The conformance report is produced FROM an artifact the harness does not
> write.** §8.5's eighteen scenarios are **committed pytest tests**, one per row,
> with stable test ids. They are executed by a pytest invocation that emits a
> **machine-readable JSON report of that run** — test id, outcome and duration
> per test, plus the totals. `--conformance` and `--freeze-block` **read that
> artifact** and cross-check it three ways:
>
> 1. **the test ids are exactly the eighteen**, one per row L1–L18 — no more, no
>    fewer, none renamed;
> 2. **every one of the eighteen outcomes is `passed`** — a skip, an error, an
>    xfail and an absence are all red, because each is a scenario that did not
>    run;
> 3. **the reported count is eighteen.**
>
> A row is green **iff** its own test id is present and passed in that artifact.
> The harness may not mark a row green from anything it computed itself, and it
> may not mark a row green because the artifact says something *like* what it
> wanted.
>
> **`--freeze-block` requires the EXACT eighteen-row set, and the committed-block
> guard requires it again.** A nonempty all-green subset is refused at both ends
> (§8.3, §8.6 condition (5)). The two checks are deliberately redundant: one
> guards what is rendered, the other guards what a later fit reads back out of
> the commit, and a review found v2 accepting a subset at the second.
>
> **The artifact is bound, not trusted.** Its path, its SHA-256, its test-id list
> and its pass count go into the freeze block (§8.3), so the committed block
> records *which run* certified the freeze. A replaced artifact fails the digest;
> an artifact from a different harness fails §8.6's harness-hash condition
> alongside it.

The consequence is that the chain now terminates outside the reporting code: the
report is a **reading** of a pytest run, the pytest run is committed code that
either executed the scenario or did not, and the freeze block records which run
it read. A report that lies about itself has nothing left to lie with.

**The rows keep their independent seeding obligation too.** Beyond the artifact,
`epl/tests/test_evwiden.py` must independently execute the seeded scenarios of
L5, L6, L7, L9, L11, L12 and L13 — the rows whose obligations are about
production wiring rather than about a computed value — so that a scenario which
went green by drifting away from the production path is caught by a second test
that did not.

### 8.6 The freeze guard, the public-surface closure, and the first-fit record

#### The public-surface closure — one guard, one refusal, no exceptions

> **No public surface of the harness accepts any parameter that can alter a
> frozen constant (`B`, `n_sims`, `seed`, `chunk_size`, `MC_BOOT`, `SHARDS`,
> `K`, `alpha`, the grid, `e*`), inject an alternative implementation (fitter,
> engine, runner, parity, `mc`), attest a lifecycle state (`harness_frozen`,
> `require_canaries`, `check_implementation`, `require_parity`), or truncate a
> deciding population (`--limit` on any deciding path), when the target
> artifacts are pinned or the directories are the preregistered ones. Test seams
> live behind ONE module-level guard that inspects the target and REFUSES
> pinned/preregistered targets; production paths resolve every constant from the
> frozen law and take no overrides.**

This is stated as one law rather than as a list of repairs because the defect it
closes is a **class**, and the class is what kept reopening. v1 and v2's first
harness each closed the leaks one at a time — a `harness_frozen` Boolean here, an
injected runner there, an `n_sims` keyword somewhere else, a `--limit` on a third
path — and each time a review found another surface of the same shape. The
enumeration above is therefore illustrative and the sentence is the rule: **any**
parameter with one of those four effects is closed on those terms, named here or
not.

Four consequences, all mechanical:

1. **Constants are resolved, never accepted.** `n_sims` (20,000), the simulation
   seed (20260611) and the chunk size are not parameters of `TableRunner`,
   `ParityRunner`, `run_table` or the single `leaguesim.simulate` call at all:
   the harness reads them from `epl.simretro` and `epl.leaguesim`, which is where
   §0.1 pins them. `B`, `alpha`, `MC_BOOT`, `MC_SEED`, `K`, `SHARDS` and `e*`
   keep their keywords — a keyword that names a constant is how a caller says
   *which* computation it means — but a **different value** is refused.
2. **Seams are guarded, not removed.** §7.3's seeded-defect audit needs to
   inject; §8.2 authorises it "on SYNTHETIC corpora only", in a directory of its
   own. The single guard is exactly that condition made mechanical: a seam is
   refused when the played frame is the pinned archive, when it is **derived**
   from the pinned archive, when the corpus is the pinned corpus, or when the
   target directory is (or sits inside) one of the preregistered ones. A caller
   that names no directory is refused too, because the default is the
   preregistered run directory.
3. **The ambiguous middle is refused, not allowed.** §7.4 defines SYNTHETIC as
   *literal*: every value written in `epl/tests/test_evwiden.py`. A frame that is
   neither byte-identical to the pinned archive nor literal — one derived from it
   and altered — is neither, and a guard that resolves its own doubt in favour of
   fitting is not a guard. The mechanical test is ancestry: a frame naming any of
   the pinned archive's own club keys was derived from it.
4. **`--limit` names one thing.** §8.4 step 2 is `--run --limit 1` and that is
   the only population the flag may name; every other value is refused on every
   path, including the parity oracle's 32 cells (§3.3's closure 2).
5. **The guard's scope is this experiment's artifacts, not every artifact.** A
   review found the guard refusing unrelated scratch work anywhere beneath the
   **shared** `paths.FIT_DIR`, which is where every experiment in this repository
   writes. That is over-refusal, and over-refusal is not conservatism: it blocks
   the audit passes §8.2 authorises, and a guard that stops legitimate work gets
   worked around. The preregistered set is the four directories this document
   names — `data/epl/fit/evwiden/`, `data/epl/sim/evwiden/`, the sequence
   directory and `reports/evidence/` — **plus the two files it names by path**,
   `data/epl/fit/evwiden.json` and §0.6's feasibility record. `paths.FIT_DIR`
   itself is not a preregistered directory and a target merely *inside* it is not
   refused for that reason alone. What replaces the breadth is exactness: the
   guard's list is a closed enumeration a committed test reads back, so a new
   evwiden artifact that is not in it is caught at the test rather than covered
   by a wildcard.
6. **Deciding evidence is derived, never supplied — including through a scratch
   target.** Two surfaces escaped the closure by taking their deciding inputs as
   arguments rather than as constants: `score_table(tallies=…, mc=…)` accepted
   caller-supplied tallies and a caller-supplied Monte-Carlo object, and the
   guard that should have refused them was keyed to the **ledger path**, so a
   caller who pointed at a scratch ledger while supplying real deciding evidence
   was permitted. And `merge` and `run_table` were callable directly, without the
   CLI sequence that enforces §8.4's markers.
   * **`score_table` derives its tallies and its Monte-Carlo object from the
     rebound tally files and from nothing else.** There is no `tallies=` and no
     `mc=` on any deciding path, at any target. §5's estimator and §5.4's
     unanimity rule are computed, not accepted.
   * **`merge`, `run_table` and `run_parity_oracle` require the sequence
     themselves.** Each calls §8.4's marker check for its own step on every
     invocation — not only when reached through `main` — so a direct API call is
     exactly as ordered as a command line. A step called out of order raises
     `SequenceViolation` from the function, not from the CLI wrapper.
   * **A sequence marker is validated, not read.** It must carry `complete: true`
     — a missing `complete` is FALSE, never true-by-absence — and the product
     digest it names is **recomputed** and compared, so a marker describing a
     product that no longer exists in that form unlocks nothing.

One mode is **not** a seam and is named here so the distinction is not argued
later: a construction-only `Engine` (§8.2's pass 4). It can only ever make the
object *less* capable — `Engine.fit` refuses on it structurally, before the
sampler is reached and **before it imports `dcfit`** — and it obtains its store
from §8.2's read-only accessor. A parameter that cannot enable anything is not a
parameter that needs guarding.

**The feasibility surface is closed and is not a module-level variable.** §0.6's
census was produced by v2's pass 7 under an authorisation this document does not
renew (§8.2), and the surface that granted it must not survive as something a
caller can re-enable. Its permission set and its active-pass state are **not
mutable module globals**: they are constants the harness reads and cannot be
rebound from outside, the feasibility record is **read-only to this document**,
and its digest is bound into the freeze block (§8.3) rather than recomputed from
whatever file happens to sit at the path. A forged, deleted or rewritten record
is caught by the block, not by the file.

#### The guard establishes state; it never accepts it

**No public fit surface accepts a freeze-state boolean.** `Engine`,
`TableRunner`, `ParityRunner`, `run_fits` and `run_table` carry no
`harness_frozen` parameter, and no other entry point may introduce one. A guard
that trusts a caller-supplied `True` performs no verification at exactly the
moment verification matters, and a direct harness call could then fit the pinned
artifacts while unfrozen — which is the whole of what "anywhere" forbids. The
same objection reaches `merge`, which fits and simulates nothing but would
otherwise score a ledger past the freeze check on a caller's word: its two
lifecycle keywords survive only as seams, under the closure above, and neither is
reachable from the CLI.

**The guard establishes the state itself, every time it is asked**, from
committed bytes and Git ancestry:

1. `reports/epl_widening_prereg_v3.md` — **this file and no other** — is
   **committed**, and the commit that last touched it is an **ancestor of
   HEAD**. No second source is accepted: §8.3 forbids an amendment-ledger
   cross-reference for this document, so a guard that would read one is a guard
   checking condition (1) against a file this law does not name. **And the file's
   CURRENT bytes must equal that committed blob's**, which is the condition v2's
   guard was missing: it bound the preregistration to its committed blob and then
   checked *current* bytes only for the two harness files, so an **uncommitted**
   post-fit edit to the preregistration itself went undetected — the one edit
   §8.7 most needs to see, because §8.7's whole regime is "the document cannot
   change after the first fit". Committed-blob equality plus current-byte
   equality is what makes that sentence true of a working tree as well as of a
   commit;
2. the freeze block in that **committed blob** carries a harness hash table whose
   two SHA-256 values equal the current bytes of `epl/evwiden.py` and
   `epl/tests/test_evwiden.py`;
3. the **schema identifier** in that block is `epl-evwiden-3`, and the
   **membership digests** it records **equal** a fresh recomputation from the
   pinned artifacts — equality in both directions, over the block's own
   membership table: a recorded digest no recomputation produces is as much a
   failure as a recomputed one the block does not record. **The block's recorded
   feasibility digest must likewise equal §0.6's record as it stands**, and a
   census whose priceable set is not exactly this document's thirty-two cells is
   a failure of this condition, not a warning;
4. the first-fit record, if present, is consistent with (1)–(3) **and carries
   every field §8.6 fixes**. A record that omits one cannot be validated against
   it, and a guard that reads each field "if present" passes a record with the
   fields stripped out. **Its append-only witness (below) is consistent with it**,
   and a witness that records a fit the record does not is a failure of this
   condition;
5. the **conformance report inside that committed block** carries **exactly**
   §8.5's eighteen rows L1–L18 and every one of them is green. §8.5 makes a green
   report the precondition of *rendering* the block; without this condition the
   guard would establish the freeze state from a block that had been rendered
   past it, and the block would then be the committed evidence for its own
   legitimacy. **A nonempty all-green SUBSET fails this condition** — v2's guard
   accepted one, which meant a block that had simply dropped a row it could not
   satisfy read back as green — and so does a block whose recorded pytest
   artifact identity (§8.5) is absent or does not match.

All five, or `FreezeStateUnverified`. Parsing two hash lines out of current prose
is not a freeze: an uncommitted paste satisfies it, and this document does not
accept it as one.

#### The first-fit record — one path, validated, and honest about what it proves

The record lives at **one fixed repo-root-keyed path**,
`data/epl/fit/evwiden_first_real_fit.json`, derived from `paths.REPO_ROOT` and
from nothing else. **No function that reads or writes it takes a directory
argument.** v1's record was written below the caller's chosen directory, so a
fresh or deleted `--dir` reset the entire §8.7 regime.

It records: the schema identifier; **the UTC instant of the first real fit** —
written by the call that performs the fit, immediately before it enters the
sampler, and never by any permission check that precedes it, because a timestamp
taken while deciding whether a fit may happen is not the instant one did; the
entry point that performed it; the Git HEAD commit at that moment; **the Git blob
id of `reports/epl_widening_prereg_v3.md` at that commit**; and the SHA-256 of
both hashed harness files. **All of them are required**, and a record missing one
is `FreezeStateUnverified` rather than a record with a gap. On every later fit
the guard re-reads it and raises `FreezeStateUnverified` if the recorded prereg
blob is not the blob of the freeze commit, or if a hashed file's current bytes
differ from the recorded ones.

**"The instant of the first real fit" means every recording site, not one.** A
review found the phrase true of `Engine.fit` and false everywhere else: the
canary recorded before its runner ran, `TableRunner` before the protected fit and
simulation, and `ParityRunner` before it called its runner — all of them **attempt**
timestamps dressed as occurrence timestamps. The rule is uniform and applies to
every site that may record: **the record is written after the call that performs
the fit has been entered and immediately before the sampler is invoked**, so that
a process which dies deciding whether to fit leaves no record claiming it did.
The distinction matters in one direction only and that is the direction the rule
protects: a missing record understates the ratchet and is caught by the witness
below; a record of a fit that never happened would start §8.7's regime over
nothing.

#### The append-only witness — because a deletable file is not a ratchet

**The record's job is to be a ONE-WAY ratchet, and an ordinary gitignored file
cannot be one.** Two reviews found the same hole and neither the document nor the
harness closed it: absence returns `None` and restores the pre-fit state, so
**deleting the record resets the entire §8.7 regime**. Nothing in v2 made the
transition durable.

> **Every write of the first-fit record is accompanied by an append to a separate
> WITNESS**, `data/epl/fit/evwiden_first_fit_witness.jsonl`, at the same fixed
> repo-root-keyed path discipline and with no directory argument anywhere. The
> witness is **append-only in the harness's own hands**: the harness opens it for
> append and never for truncation, never rewrites a line, and never deletes it.
> Each appended line carries the same identity fields as the record — instant,
> entry point, HEAD, prereg blob, harness digests — plus a **chain digest**: the
> SHA-256 of the previous line's chain digest concatenated with this line's
> canonical form, so a line removed from the middle breaks every digest after it.
>
> **The guard reads BOTH, and disagreement is `FreezeStateUnverified`:**
>
> * a witness with lines and **no record** is a **deleted record** — the ratchet
>   holds, the state is post-first-fit, and the harness refuses rather than
>   quietly reverting to pre-fit;
> * a record with **no witness line** naming it is a forged or hand-written
>   record and is refused;
> * a broken chain digest is refused;
> * both absent is pre-first-fit, which is the only state in which a fit may
>   begin.
>
> **What this does and does not buy.** It makes deletion *visible* rather than
> impossible: someone who deletes the record must also delete the witness, and
> someone who deletes both has deleted an append-only file whose absence the
> author's attestation (§8.8) speaks to and whose presence in any other checkout
> contradicts them. That is strictly more than v2 had, which was a single file
> whose removal silently reopened the design. **It is not a global proof**, and
> the paragraph below says so in the same words it always has.

**What the record proves, and what it does not.** Its **presence** proves a real
fit happened in this checkout and binds what may change afterwards. Its
**absence, together with the witness's absence, proves only that no fit has been
recorded here.** It is not proof that no fit has happened: `data/` is gitignored,
both files can be deleted together, and a fit can have occurred in another
checkout or on another machine. The pair is a **local enforcement mechanism**,
not a global fact.

The global claim — that no fit of this document has run — is therefore what it
has always been: **an attestation by the author, which a reader is entitled to
weigh as one.** This document states the attestation in §8.8 and states the two
v1 fits and pass 7's thirty-five inside it rather than beside it. The MANIFEST,
the sequence markers and the committed freeze block are what make the *run*
checkable once it starts; nothing makes the *absence* of a run checkable, and no
sentence in this document will claim otherwise.

### 8.7 After the first real fit: the hashed files cannot change at all

> **Before the first real fit of this document.** A hashed file may change. The
> freeze block is regenerated by `--freeze-block` and re-committed, and the run
> that follows is the run this document preregisters. No note is required,
> because nothing has been observed.
>
> **After any real fit on the real archive exists** — whether or not it produced
> a delta, whether or not it was merged, whether or not anyone looked at it —
> **any change to any hashed file invalidates this preregistration.** No note, no
> dated appendix, no disclosure and no owner ruling restores it. The invalidated
> run **publishes**, with its numbers and with the reason it was invalidated, and
> a new preregistration begins in a new document with its own freeze.
>
> **No note may be appended to this document after the first real fit, prose or
> otherwise.**

That last line replaces a prose-only allowance, and it is a ruling rather than a
tightening for its own sake. The first-fit record binds this document's **Git
blob at the freeze commit** (§8.6), and a prose note changes that blob: the guard
would raise `FreezeStateUnverified` on the next fit whatever the note said. The
allowance and the mechanism were incompatible, and there were only two coherent
resolutions — bind section hashes instead of the whole blob, so a prose-only
region could move; or drop the allowance. **This document drops the allowance.**
Binding sections would ask the guard to distinguish a typo from a threshold, a
judgement no digest can make and one this document has no interest in delegating.
Corrections after results exist belong in `reports/epl_widening_result.md`, which
is written after the numbers and is not hashed by anything.

**And the rule now sees an uncommitted edit.** v2 dropped the allowance and then
left the mechanism half-built: `assert_no_hashed_file_moved` bound the
preregistration to its **committed HEAD blob** while current-byte checks covered
only the two harness files, so a post-fit edit to the document that was never
committed changed nothing the guard looked at. §8.6 condition (1) closes it —
**the file's current bytes must equal its committed blob's**, checked on every
fit, exactly as the harness files are. A working tree in which the
preregistration has been edited is a working tree in which no further fit of this
document may run, whether or not the edit was committed.

The first real fit of this document is **step 1 of §8.4**, the post-freeze
results canary. That is when this regime begins.

**The deciding tallies are bound to the ledger and cannot be swapped.** The 32
per-cell tally files are written beside the table ledger as
`data/epl/sim/evwiden/tallies/<season>|<label>.npz` (`/` → `-`), each carrying
both arms' `[P, C, C]` arrays. Each is a live deciding input: §5's estimator and
§5.4's unanimity rule read them, and a structurally valid replacement could alter
the MC standard errors — and turn UNRESOLVED into PASS — without changing any
other digest.

Therefore:

* **every table ledger row records the SHA-256 of its own tally file**, written
  at the same moment as the row — a cell that produced no tally does not get a
  row with a null digest in it, it stops the leg;
* **every read rebinds**: `load_tallies` recomputes the file's digest and refuses
  (`TableMCImprecise`) on any disagreement **and on an absent recorded digest**,
  and re-runs §5.1's two binding checks before the arrays are used to decide
  anything. A read that treats a missing digest as nothing to check is a read
  that binds nothing;
* the tally files and `parity.jsonl` are **MANIFEST members** (§9.3);
* **`--verify` recomputes the table gate from the rebound tallies** — the whole
  of §5, including the unanimity rule — and refuses if the recomputed verdict,
  the recomputed standard errors or the recomputed precision conditions differ
  from the published ones. A verification that re-reads a JSON file it does not
  re-derive verifies nothing.

### 8.8 The attestation

**No fit of the experiment this document preregisters has been run.** No delta,
no treatment arm, no §3.3 table cell, no evidence file and no verdict of this
experiment exists anywhere, and no `data/epl/fit/evwiden*` or
`data/epl/sim/evwiden*` file exists other than the one this section excepts by
name.

**Three qualifications on that sentence, all of them mechanical.**

*The one file that exists, and it is not a fit of this experiment.*
`data/epl/sim/evwiden_parity_feasibility.json` (18,128 B, SHA-256
`07ee00d798cb0f01f29bc5bb5ba885c41e26d5494e9755c73a038a2777bad329`) is v2 §8.2
pass 7's record, written on 2026-08-28 under **v2's** authorisation and before
this document existed. It is the only `data/epl/sim/evwiden*` file there is; it
is **read-only to this document**, pinned by §0.1 and bound into §8.3's freeze
block; and it carries the census and no delta, no table cell, no arm comparison
and no estimand. The pass's own outputs — the protected oracle's `dc_native`
parity rows — were written outside the repository and deleted when the pass
closed, and the shared point-in-time store was byte-unchanged across it (184,115
B, SHA-256 `c297b8b04e50d3b5451cb9aed29fcbbfdd13abc290597316f13b176c69e8ded0`,
mtime 2026-08-14 18:41). **Thirty-five real ADVI fits and thirty-five real
simulations were spent producing it**, on the protected control path; §2.4 counts
them and §0.6 publishes what they measured.

*One file was there and is not.* `data/epl/fit/evwiden/first_real_fit.json` (739
bytes, 2026-08-28 15:34) existed in the working tree while v2 was being written.
It was **not** a fit: it was manufactured by a test-isolation defect at
`6bbacd0`, where the first-fit record's writer still took a directory argument
that defaulted to the preregistered run directory, and a working-tree version of
that commit's own test exercised the record path against the real directory
instead of a `tmp_path`. No fit occurred — at `6bbacd0` the only call site was
inside `assert_may_fit`'s frozen branch, no freeze block had ever been committed,
so `_frozen_now()` was `False` and that branch could not run — and the shared
point-in-time store was byte-untouched throughout. The file was inert (§8.6's
record lives at a different path) and it has been **deleted**. The isolation hole
is closed as far as a fixture can close it: `epl/tests/test_evwiden.py` carries
an autouse fixture that snapshots the preregistered paths before and after
**every test in that module** and fails the test that moved one, so this class of
artifact is found at the test that creates it rather than by a later audit. It is
function-scoped, and the review is right that a function-scoped fixture cannot
speak for import-time, collection-time, session-fixture, subprocess or crash-time
writes; **what it establishes is that no test body in the module writes there**,
and this document claims that and nothing wider.

*Neither the first-fit record nor its witness exists.*
`data/epl/fit/evwiden_first_real_fit.json` and
`data/epl/fit/evwiden_first_fit_witness.jsonl` are both absent, which under §8.6
is the pre-first-fit state and the only state in which a fit of this document may
begin.

**This attestation is made WITH every real fit of this lineage on the record and
named inside it**, not beside it:

* **two** real ADVI fits through protected `epl.simretro.ArchiveRunner` on the
  parity path during v1's conformance-test construction, crashing on
  `epl.particles.ExcludedMassTooLarge` at 2019/20 MW0, producing no delta, no
  ledger row and no artifact. They ended v1 (§8.1);
* **thirty-five** real ADVI fits and thirty-five real 20,000-season simulations
  through the same protected runner during v2's authorised pass 7 on 2026-08-28,
  producing the census of §0.6 and nothing else. They ended v2's *runnability*
  and are the reason this document exists.

All thirty-seven preceded this document, all were on the protected `dc_native`
control path, and none produced an estimand, a treatment arm or a published
number of this experiment. They are not excluded from the attestation; they are
its first sentences.

**This is an attestation, not a fact the repository can prove** (§8.6). `data/`
is gitignored, so the committed tree can establish only that nothing was
committed, and a reader is entitled to weigh the attestation as one. What the
repository *can* prove is narrower and is bound in the freeze block: the census
record's digest, the harness bytes, the conformance artifact's identity and this
document's own committed blob.

### 8.9 Dated pre-freeze notes

This document is pre-freeze and this section is where its pre-freeze events are
recorded. §8.7 closes it at the first real fit, after which nothing is appended
here or anywhere else in this document.

**2026-08-28 — this document exists because v2's own executed pass defeated it.**
v2 §8.2 authorised one pre-freeze pass that could fit and simulate — the
`dc_native` parity feasibility pass, pass 7 — prospectively, by name, quarantined
outside the repository, once. It was executed the same day it was authorised,
opened 14:50:24Z and closed 14:54:37Z at HEAD `9adc3bc`, arm `dc_native`, all
thirty-five of v2 §3.3's cells attempted under `run_retro`'s own typed per-cell
contract: `cells_expected: 35`, `cells_attempted: 35`, `completed: true`,
`error: null`, `feasible: false`. **Thirty-two cells price; three do not**, all
three `excluded_mass_ceiling` against amendment A1's 0.02 ceiling, all three a
Manchester City fixture against a promoted side — 2019/20 MW0 (man_city v
sheffield_united, 0.0234), 2020/21 MW0 (man_city v leeds, 0.0216), 2023/24 MW3
(man_city v luton, 0.0328). They are exactly the three cells v2 §8.2 named as
candidates, at exactly the masses it quoted; no fourth appeared, none was
cleared, and no cell failed as `runner_error`. The record is
`data/epl/sim/evwiden_parity_feasibility.json`, 18,128 B, SHA-256
`07ee00d798cb0f01f29bc5bb5ba885c41e26d5494e9755c73a038a2777bad329`. The
quarantine was deleted on close and the shared point-in-time store was
byte-unchanged across the pass.

v2 had pre-stated, before the pass ran, that **one unpriceable cell is enough**:
a mandatory leg could not be executed, v2 could not be run as written, and the
remedy was a new preregistration scoped to what the protected runner can price —
*"not a quiet narrowing of the 35 cells here."* v2 was accordingly **closed with
a dated note and nothing else in it changed**, and this document was written
against the census. §0.6 publishes the census in full and states what it moved.

**2026-08-28 — what this document changed from v2, in one list, so the diff is
not something a reader has to reconstruct.** Every clause of v2's law is carried
here unchanged except the following, and each is either forced by the census or
is a residual finding v2's harness had left open and this document now rules:

*Forced by the census (§0.6):* 35 → 32 table cells with the three excluded keys
named; 16 → 15 treated and 19 → 17 untouched; the new per-label CELL census
`{MW0: 5, MW3: 6, MW6: 7, MW10: 7, MW19: 7}` pinned beside the treated census
`{MW0: 2, MW3: 2, MW6: 7, MW10: 4, MW19: 0}`; gate (iv-b)'s MW0 mean over **2**
treated cells; §5's deciding tallies 32 → 30; §2.4's post-freeze budget 153/105 →
147/96 with the whole-lifecycle figure (182/131) stated for the first time;
§4.3's tolerance-comparison arithmetic recomputed (+0.00042667, 2.13× tighter);
§9.2's table CSV 35 → 32 rows; §9.3's MANIFEST 52 → 49 paths.

*Ruled as law, where v2 left the obligation to the harness:* §8.5's conformance
report must be read from an **independent committed pytest artifact** and the
freeze block must require the **exact** eighteen rows, not a green subset (§8.3,
§8.5, §8.6 condition (5)); the first-fit record gains an **append-only witness**
so deletion cannot reset the regime, and its instant is the instant of the fit at
**every** recording site (§8.6); §8.6 condition (1) binds this document's
**current bytes** as well as its committed blob, so an uncommitted post-fit edit
is detected (§8.7); `--script` is refused pre-freeze at every target and takes no
interpreter post-freeze (§8.2); the table ledger is resolved rather than named
and step 5 claims its marker before it simulates, closing the
outcome-conditioned second run (§8.4); `score_table` derives its tallies and
Monte-Carlo object rather than accepting them, and `merge`, `run_table` and
`run_parity_oracle` enforce the sequence themselves (§8.6); the guard's scope is
this experiment's enumerated artifacts rather than all of `paths.FIT_DIR`
(§8.6); the feasibility surface is closed and its record bound by digest rather
than trusted as a file (§8.3, §8.6); and the read-only store accessor closes its
check-then-construct window (§8.2).

*Not changed, and named so that the absence is deliberate:* the rule, `e* = 10.0`,
`α = 0.5`, ADD-not-REPLACE, binary-not-continuous, the 85-fixture estimand and its
52 treated, the 62 week blocks and 6 seasons, both bootstrap seeds, `B = 10,000`,
the −0.0010 bar, the +0.0002 table tolerance, MW6 as the deciding horizon and the
ground on which it was named, `MC_BOOT`, `MC_SEED`, `K = 200`, the unanimity rule,
`n_sims = 20,000`, `SHARDS = 4`, §6's frozen scenarios and its six-row power
table, §7's refusal inventory, §7.4's synthetic definition, and §8.4's five-step
sequence. **No threshold, seed, population or gate moved**, and none could have:
the only measurement that exists is a census of the protected stack's capability,
which touches the table leg's denominator and nothing else.

---

## 9. The evidence contract

**The result publishes either way** (§4.4), and the verdict's machine-readable
basis is committed, not gitignored.

### 9.1 `reports/evidence/widening.json`

Carries, at minimum, and by these names:

* `schema` (`epl-evwiden-3`), `generated_at`, `prereg_commit`, `prereg_blob`;
* `pins` — corpus / archive / ledger / frozen-config digests, the realised config
  digest, **§0.6's feasibility census digest and its 32-cell priceable set**, and
  the row and season counts;
* `estimand` — `{n: 85, mean, sd, se_iid}`;
* `ci_week` and `ci_season` — each `{function, n_blocks, B, alpha, seed, lo,
  hi}`; `ci_table_mw6` likewise, with `n_blocks: 7`;
* `gate_i`, `gate_ii`, `gate_iii` — each `{value, bar, PASS}`;
* `gate_iv` — `{mw6: {n: 7, mean, ci, per_cell: [...]},
  per_label: {MW0, MW3, MW10: {n_treated, mean, PASS}},
  mw19: {structural_zero: true, decides: "nothing"},
  precision: {…, conditions: [P1, P2, P3.MW0, P3.MW3, P3.MW10, P4, P5],
  resolved: bool}, PASS_or_UNRESOLVED}` — **seven conditions, no `P6`**, per
  §5.4;
* `controls` — `{identity: {n: 820, max_abs_diff, mean_abs_diff, PASS},
  untreated_moved, predicate_mismatch, table_parity: {n_cells: 32, PASS,
  per_cell_digests}}`;
* `canaries` — results, evidence (both legs, both row counts, the positive
  control's realised magnitude), identity, direction (with the branch each
  fixture took);
* `sequence` — the five markers of §8.4, each with its recorded freeze commit and
  completion time;
* `conformance` — §8.5's pytest artifact identity: path, SHA-256, the eighteen
  test ids and the pass count, as the freeze block records them;
* `grid` — five points, each `{n_thin, n_treated, mean, ci, degenerate,
  decides: "nothing"}`;
* `strata` — six seasons and two club categories, each `decides: "nothing"`;
* `movement` — mean and max `|Δp|` over the treated fixtures, beside the re-seed
  reference scale;
* `coverage` — per treated club, per arm, cov50 and cov90;
* `sunderland` — the three 2025/26 cells, both arms: relegation probability,
  points mean, 5–95 band, under the label §3.4 fixes;
* `power` — §6's object: the frozen scenarios, structure, MDE definition, R, both
  seeds, the six rows of §6.3, and `power.realised` per §6.5;
* `materiality` — the pooled corpus figure and §4.2's required sentence;
* `verdict` — `ADOPT` / `NO ADOPT` / `UNRESOLVED`, and which gate decided.

**The two controls that v1 hard-coded are measured.** `controls.untreated_moved`
and `controls.predicate_mismatch` must be **read off the merged rows** — the
count of merged rows whose recomputed provisional set disagreed with the
ledger's, and the count of non-treated merged rows carrying a non-zero delta —
not written as `{n: 0, PASS: true}` constants. Their values are true by
construction only because a refusal stops the run first; a verdict file that
always prints PASS for a control nobody measured is exactly the shape this
document's own "a test that cannot fail is not a test" objects to.

**`scored.per_cell` is not stripped.** The top-level per-cell structure must
survive into the JSON projection: it is what fills the required table-parity and
coverage diagnostics, and removing it before projection empties fields this
contract promises.

### 9.2 The three CSVs

**`widening_per_fixture.csv`** — 85 rows: `key, match_id, season, block, cutoff,
date, home_key, away_key, e_home, e_away, e_min, thin_at, treated,
incumbent_widened, p_home_B, p_draw_B, p_away_B, p_home_A, p_draw_A, p_away_A,
p_home_corpus, p_draw_corpus, p_away_corpus, y, rps_B, rps_A, delta,
delta_vs_corpus, max_abs_dp_vs_corpus`.

**`widening_table_cells.csv`** — 32 rows: `season, cutoff_label, cutoff,
treated_clubs, n_treated_clubs, trps_control, trps_treatment, delta_trps,
wtrps_control, wtrps_treatment, delta_wtrps, mc_se_paired, identical,
sampler_digest_control, sampler_digest_treatment, substantive_digest_control,
substantive_digest_treatment, parity_digest_simretro, provisional_control,
provisional_treatment, effective_posterior_control,
effective_posterior_treatment, tally_sha256, cov50_control, cov90_control,
cov50_treatment, cov90_treatment, cov50_treated_control, cov90_treated_control,
cov50_treated_treatment, cov90_treated_treatment, realised_hash`.
`mc_se_paired` is §5.2's per-cell `mc_se_cell`.

**`widening_grid_means.csv`** — `e_star, n_thin, n_treated, mean_delta, ci_lo,
ci_hi, n_blocks, degenerate, decides`.

### 9.3 `reports/evidence/MANIFEST.sha256` — an exact list of 49 paths

Each entry carries a SHA-256 **and a byte size**, and both are **validated** on
`--verify`, not merely recorded.

| # | path |
|---:|---|
| 1 | `reports/evidence/widening.json` |
| 2 | `reports/evidence/widening_per_fixture.csv` |
| 3 | `reports/evidence/widening_table_cells.csv` |
| 4 | `reports/evidence/widening_grid_means.csv` |
| 5–8 | `data/epl/fit/evwiden/shard_0{0,1,2,3}_of_04.jsonl` |
| 9 | `data/epl/fit/evwiden.json` |
| 10 | `data/epl/sim/evwiden/table_cells.jsonl` |
| 11 | `data/epl/fit/evwiden/canary.json` |
| 12 | `data/epl/sim/evwiden/parity.jsonl` |
| 13–44 | `data/epl/sim/evwiden/tallies/<S>\|<L>.npz` — **exactly 32**, one per priceable table cell: `<S>` over the seven seasons `2019-20, 2020-21, 2021-22, 2022-23, 2023-24, 2024-25, 2025-26` (the season string with `/` replaced by `-`), `<L>` over the five labels `MW0, MW3, MW6, MW10, MW19`, **minus the three cells §0.6's census measured as unpriceable** — `2019-20\|MW0`, `2020-21\|MW0` and `2023-24\|MW3` |
| 45–49 | `data/epl/fit/evwiden/sequence/step{1_results_canary, 2_single_opening, 3_shards, 4_merge, 5_parity}.json` |

The list is decidable from this document: the count is 49, the shard count is
fixed at 4, the tally naming function is literal and its 32 members are the
product of two enumerated sets minus three cells this document names by key, and
the five markers are named individually.
"Bulky local artifacts" is not a category here; it is a list.

**Publication leaves this MANIFEST valid.** The five sequence markers are
members of it, so every marker lands **before** the manifest is computed and
nothing manifested is written afterwards. The publication pass — `--merge
--evidence`, run after step 5 — re-verifies step 4's marker rather than rewriting
it (§8.4), and writes no other manifest member. A run that hashed a file and then
changed it published a manifest that was invalid the moment it was written, which
is the one thing a manifest cannot survive; the "publication-only, not a sixth
experiment step" reading of §8.4 does not repair that, and this clause is what
does.

**`--verify` refuses** if any of the 49 is missing from the MANIFEST; if any
digest disagrees; if any byte size disagrees; if the MANIFEST carries an entry
inside this experiment's namespace (`widening`, `evwiden`) outside the 52; or if
a promised file is not on disk. It may not skip a file it cannot find: a missing
artifact is a refusal, never a silent omission.

**`--verify` also re-derives the verdict**, per §8.7: it rebinds every tally to
its recorded digest, re-runs §5's estimator and §5.4's unanimity rule, recomputes
the table gate and the adoption decision, and refuses on any disagreement with
the published values. **A published value it cannot find is a disagreement**, not
a comparison skipped: a missing `gate_iv` block beside a table ledger, a standard
error present on one side and absent on the other, and a moved unanimity dissent
count each refuse. The adoption verdict is recomputed from the re-derived gate
and the ledger's own estimand rather than echoed out of the JSON. Files 5–49 are
not committed; what is committed is their digest and byte size, which is the
point of the MANIFEST.

### 9.4 The result document

`reports/epl_widening_result.md` publishes whatever the signs, and must carry:

* the verdict and which gate decided;
* §4.2's required materiality sentence, verbatim;
* §6.3's power warning in its own words if the estimand misses;
* §6.5's realised paired SD and the joint-gate MDE recomputed at it;
* §1.3's coverage reading, in the direction §1.3 fixes;
* the console output and row count of §8.4 step 2, and the digest of step 1's
  canary record;
* if gate (iv) is UNRESOLVED: which of P1–P5 fired, with its computed value.

---

## 10. What would invalidate this preregistration

* Any pinned digest of §0.1 differs at run time without a prior dated note.
* A real-archive fit or simulation runs before the §8.3 freeze commit, anywhere,
  under any output directory.
* **Any change to a hashed file after the first real fit of this document, with
  or without a note** (§8.7).
* A hashed file differs at run time from the committed freeze block.
* `e*` moves off 10.0, any grid point is promoted to the estimand, or a REPLACE
  or continuous-α variant is reported as this experiment.
* A fixture is dropped from the 85, a cell from the 32, or a season from either
  leg after the run starts; or a cell §0.6's census measured as unpriceable is
  added back to the oracle.
* The treated-subset mean, a stratum, a grid point, or any secondary decides
  anything.
* A second seed, bootstrap seed, `B`, `n_sims`, `MC_BOOT`, `K`, shard count or
  block definition is reported as this experiment.
* Any threshold or CI condition in §4 moves after any delta exists.
* The identity control's tolerance is widened after a mismatch, anywhere.
* The 27.9→15.9 counterfactual, or any live-2026/27 quantity, enters any gate.
* The result is not published, or publishes without the §9 evidence files.
* Gate (iv) evaluated on any cross-horizon average.
* The MW6 horizon replaced after any table run.
* The 32-cell parity oracle skipped, sampled, truncated, or established after any
  treated simulation.
* The estimand's delta computed against the corpus rather than against the
  same-posterior incumbent pass.
* Gate (iv) evaluated with an MC estimator that is not §5's jointly-resampled,
  tie-aware estimator — including any estimator that combines per-cell standard
  errors in quadrature, any estimator built on `.order`, and any run whose 15
  deciding cells do not share a common `n_particles`.
* §5.4's unanimity rule omitted, run at a different `K` or seed, or replaced by a
  scale comparison against `mc_se_mw6`.
* The steps of §8.4 run out of order, or a step run without its predecessor's
  marker.
* A deciding tally read without rebinding it to its recorded digest.
* Any deciding number produced through a seam §8.6's public-surface closure
  refuses — an injected fitter, engine, runner, oracle or Monte-Carlo object; a
  caller-attested lifecycle state; a truncated deciding population; or a frozen
  constant supplied rather than resolved.
* A treated arm simulated at any cell before that cell's native parity against
  protected `ArchiveRunner` has been established (§3.3's closure 1).
* Step 1 retried after a failed results canary without a dated pre-freeze note
  written **before** the retry (§8.4).
* A note of any kind appended to this document after the first real fit (§8.7),
  **committed or not** — §8.6 condition (1) binds this file's current bytes.
* A parity feasibility pass run under THIS document, before or after its freeze
  commit. v2's pass 7 answered the question once (§0.6); a second execution is a
  second answer to a settled question and this document authorises none.
* §0.6's census record replaced, rewritten, deleted, or found to disagree with
  the digest §8.3's freeze block binds; or the table leg run against a census
  whose priceable set is not exactly this document's 32 cells.
* A conformance report accepted from anything but §8.5's committed pytest
  artifact, or a freeze block rendered or read back over fewer than all eighteen
  rows L1–L18.
* The first-fit record deleted, or written without its append-only witness line,
  or recorded at a moment that is not the instant of the fit it attests (§8.6).
* The table ledger named by a caller, or step 5 run a second time against a
  different ledger after its first outcome exists (§8.4).
* `--script` run before the freeze commit, at any target; or a post-freeze
  launcher generated with a caller-supplied interpreter or command (§8.2).

---

## 11. Standing disclaimers

* **Small population, pre-picked.** 85 fixtures — 52 carrying the treatment — in
  62 blocks, selected by a rule that targets exactly where the effect should be
  largest. The estimand answers only the question asked: the value of the re-key
  over **all 85 thin fixtures**, 33 of which the incumbent predicate already
  widens and which therefore carry a delta of exactly zero by construction. Only
  52 fixtures are touched.
* The intervals are percentile block bootstraps over correlated fixtures — not
  moving-block, not exact tests; the 6- and 7-block season resamples have poor
  coverage and serve only to refuse single-season verdicts. One ADVI seed;
  mean-field under-dispersion is a known, separately scheduled limitation.
* **This design is underpowered against effects near its own bar** unless the
  realised paired SD comes in at or below the freshness scale (§6.3). A miss is
  substantially uninformative.
* **Sampler noise is not model error**, and on 85 fixtures the noise floor is
  proportionally higher than the corpus-level +0.000075 — both are reported;
  neither shrinks with a better argument.
* TRPS is proper for the displayed marginals only; the widening also changes the
  joint law, and no metric in this experiment sees that.
* §5's Monte-Carlo estimator bounds how much of gate (iv)'s margin is simulation
  noise. It is not a model of the fit's own uncertainty, which no table statistic
  here sees.
* The match-level result is evidence about the rule family, not about Hull: the
  Hull configuration itself has zero support in the scoring window and one
  analogue in the table leg, and nothing here may be quoted as "the Hull fix was
  validated" — or refuted — at match level.
* Six-to-seven seasons, one league, one model, one configuration, one frozen
  constant. Nothing generalises beyond them and nothing may be quoted as if it
  does.

---

## 12. What this does not decide

Not decided here, by anything this experiment can produce: no change to α (0.5),
decay (365), `k_att`/`k_def`, D2 (static-within-fit), D12 (per-fixture
Bernoulli), the volatility or few-games arms, the published arm,
`ISSUANCE_SCHEMA_VERSION`, the matchboard, A8's constant or ledger, A12's arm or
capture bounds, the freshness or anchoring verdicts, or the market-prior
question. No REPLACE variant and no continuous α is licensed. The lock chain is
untouched by design.

---

*Preregistered 2026-08-28. This is v3: a complete, self-contained statement of
the law of this experiment, written after `reports/epl_widening_prereg_v2.md`
was defeated by the one pass it authorised for exactly that purpose — v2 §8.2
pass 7, executed 2026-08-28, which measured three of v2's thirty-five mandatory
parity cells as unpriceable on the shipped stack (§0.6). **v2 was never quietly
narrowed**: it was closed with a dated note, nothing else in it changed, and this
document was written against the measured census instead, which is the remedy v2
itself pre-stated before its pass ran. It carries the whole of v2's law — which
was the whole of v1's law as two repair rounds left it — with the table leg's
census replaced by the measured one, with the residual findings four review
rounds and two in-tree adversarial audits left open against v2's harness ruled
as law here (§8.2, §8.3, §8.4, §8.5, §8.6), and with every real fit of the
lineage named inside its attestation rather than beside it: two under v1,
thirty-five under v2's pass 7, none under this document. `epl/evwiden.py` and
`epl/tests/test_evwiden.py` exist and implement this document; §8.3 forbids
rendering a freeze block until §8.5's report is green on behavioural predicates
produced by an independent pytest artifact, until the census record matches the
digest the block binds, and until a dual audit reports no blocking finding, and
no real fit of this document runs before that commit.*



