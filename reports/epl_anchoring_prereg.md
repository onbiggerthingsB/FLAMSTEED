# Market anchoring — preregistration of the input-level market-prior experiment

**Written:** 2026-08-26 · **Branch:** `main` · **Corpus:** frozen, pinned below
**Authorised by:** [`reports/epl_sim_amendments.md`](epl_sim_amendments.md) **A9**
(a) — market data may enter this product line's models as an input, under a
preregistered design, through the same gates as everything else.
**Status when written:** **no harness exists.** There is no `epl/mktprior.py`,
no runner, no shard, no ledger, no result file, and not one market-anchored fit
has been run. No paired delta for any fixture in this experiment exists anywhere
in this repository, and none can, because the code that would compute one has
not been written.

This document fixes the mechanism, the parameter and how it is selected, the
estimand, the resampling, the secondaries, the adoption rule, the refusal
semantics and the scope **before** the harness that answers it. It follows
[`reports/epl_freshness_prereg.md`](epl_freshness_prereg.md) (5ba83e7), which in
turn follows [`reports/epl_sim_prereg_retro.md`](epl_sim_prereg_retro.md)
(07b5871). Like the freshness document and unlike 07b5871, it precedes its code,
so **the harness hashes are frozen by a follow-up commit, after the harness is
written and audited and before any fit is run** — §6 says exactly what that
commit must contain.

Every number below was computed on 2026-08-26 from the pinned artifacts by the
recipes given beside them, **before this document was committed and before any
harness code was written**. Where a figure from the design work could not be
reproduced, it is quoted and the failure to reproduce it is recorded rather than
smoothed over (§1.4). Where a figure reproduced but a *different, less
flattering* quantity is also true, both are printed (§1.4 again — this is the
one the reader should not skip).

**A9 (d) governs the vocabulary of everything below.** This experiment opens an
input and a labelled diagnostic. It creates no betting product: no surface of
this product line gives betting advice, prices, or recommendations, and none is
proposed here.

---

## 0. What is pinned

### 0.1 The corpus and the configuration

| | |
|---|---|
| Corpus | `data/epl/fit/walkforward_predictions.parquet` |
| SHA-256 | `f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a` |
| Rows | **2,280** — 6 seasons × 380 |
| Seasons | 2019/20, 2020/21, 2021/22, 2022/23, 2023/24, 2024/25 |
| Outcome counts (`y` = 0 home / 1 draw / 2 away) | 993 / 525 / 762 |
| Blocks — `(season, ISO week)` | **212** |
| Block openings (the cutoffs this experiment fits at) | **212**, 2019-08-09 … 2025-05-19 |
| Fixtures per block | min 1, median 10, max 20 |
| Frozen config | `epl/config_frozen.json`, SHA-256 `9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc` |
| Realised config | `epl.freeze.frozen_wcmodel_config()` — `seed` **20260611**, `model.strength_prior` `{enabled: true, source: elo, k_att: 0.6, k_def: 0.6}`, `model.widening` `{mechanism: c, strength: 0.5}`, `model.inference` `{backend: advi, draws: 1000, tune: 1000, advi_iters: 30000}`, `model.covariates.enabled` `[]` |

The corpus digest, row count, season tuple and outcome counts are **already
pinned in code** at `epl/recalfit.py:91-98` (A8). This experiment adopts those
constants rather than restating them. It is the same corpus, at the same digest,
that A8 and the freshness preregistration pin.

Verify with:

```
shasum -a 256 data/epl/fit/walkforward_predictions.parquet epl/config_frozen.json
```

**Precision.** Every probability in the corpus was written by
`epl/walkforward.py::_one_cutoff` as `round(v, 8)`. Recomputing RPS from the
stored `dc_home`/`dc_draw`/`dc_away` with `epl.score.rps` reproduces the stored
`dc_rps` for all 2,280 rows with **max |Δ| = 0.0**. Comparisons against the
corpus in §3.2 are comparisons at eight decimals, which is all the corpus holds.

**The corpus is read-only to this experiment.** `walkforward_predictions.parquet`
is never regenerated, never rewritten, never appended to. Two standing
preregistrations check its digest in code; a rewrite breaks both. This
experiment writes its own file (§2.6).

### 0.2 The reference scores on this corpus, recomputed

| forecaster | mean RPS |
|---|---:|
| `base` (season-frequency) | 0.234598 |
| `elo` | 0.203114 |
| **`dc` (the model — Arm B)** | **0.201942** |
| market, Pinnacle **closing**, proportional de-vig (`market_rps`) | 0.195418 |
| market, Pinnacle closing, Shin (`market_shin_rps`) | 0.195406 |
| market, **Avg opening**, proportional de-vig (recomputed, §0.3) | 0.196854 |

Two gaps matter and are stated once here so nothing later has to re-derive them:

* **The model-to-market gap is +0.006524 against the close and +0.005088 against
  the open.** These reproduce the design's "+0.0063 with closing odds, +0.0050
  with OPENING odds".
* **The closing-versus-opening leak is +0.001445** on Pinnacle
  (0.196863 → 0.195418) and **+0.001385** on Avg (0.196854 → 0.195469). This
  reproduces the design's measured +0.001445 exactly on the Pinnacle pair. It is
  why every odds figure in this experiment is an **opening** price and why
  closing prices are structurally excluded from the anchor (§2.1, §5.1
  `ClosingOddsRead`).

### 0.3 The odds panel — which column, and why

**The anchor's odds column is the market average at the open: `AvgH` / `AvgD` /
`AvgA`.** Not Pinnacle. Recomputed availability across the archive's twelve
season files:

| season file | `AvgH` | `PSH` | rows |
|---|:--:|:--:|---:|
| `E0_1415` … `E0_1819` | **absent** | present | 380 each |
| `E0_1920` … `E0_2425` | present | present | 380 each |
| `E0_2526` | present | present (**210 of 380**) | 380 |
| 2026/27 fixtures file (`data/epl/odds_snapshots/fixtures_2026-08-26T053948Z.csv`) | present | **absent — no `PS*` column at all** | 5 |

**Pinnacle is dying in the archive and dead in the live feed.** It is complete
through 2024/25, complete for 210 of 380 rows in 2025/26, and absent as a column
from the 2026/27 fixtures file, whose ten filled books are B365, Betfred,
BetVictor, Bet&Win, Paddy Power, SKB, Max, Avg, and Betfair Exchange. A model
whose input column disappears mid-season is not a model. **Avg is the only
opening column that is present in every season this experiment reads and in the
live feed it would run on.**

`epl/parse.py` extracts **Pinnacle only** (`_CLOSING_ODDS = (PSCH, PSCD, PSCA)`,
`_OPENING_ODDS = (PSH, PSD, PSA)`) and, where both exist, **prefers the close**.
It therefore cannot feed this anchor, on two counts, and the harness carries its
own `epl/`-side extraction (§2.6). `epl/parse.py` is **not modified**: the
existing benchmark columns keep their existing meaning, unchanged, so that
`dc_native`-versus-market stays exactly the comparison it already is (§3.4).

**The pre-2019/20 backfill, ruled.** `AvgH` does not exist before 2019/20, and
the market window at a 2019/20 cutoff reaches back into seasons that have only
Pinnacle. The panel therefore takes **`Avg` opening where present and `PS`
opening where `Avg` is absent**, with the source recorded per row. The
justification is measured, not assumed — on the 2,490 archive matches where both
opening triples are complete:

| Avg-open vs PS-open, proportional de-vig | value |
|---|---:|
| pooled mean RPS on the corpus's 2,280 fixtures, Avg-open | 0.19685444 |
| pooled mean RPS on the same 2,280, PS-open | 0.19686299 |
| **difference** | **0.00000855** |
| per-match \|Δp\| across the three outcomes: mean / p99 / max | 0.003385 / 0.012553 / 0.022380 |
| per-match Δ in `m = log(p_H/p_A)`: signed mean / sd | −0.005088 / 0.034603 |

The design work reports the two sources agreeing "to ±0.00008". **This document
could not reproduce that number and reproduces a smaller one at the same
scale**: the pooled-RPS difference is **8.55e-6**, an order of magnitude tighter
than quoted. The discrepancy is recorded and resolves nothing, because no
comparison of the two sources is the estimand, a secondary, or an input to the
adoption rule.

What is worth naming is the *per-match* row, because it is not small: the two
sources disagree on individual prices by **mean 0.0034, max 0.0224** in
probability — which is **the same scale as this model's own ADVI re-seed noise**
(mean 0.0032, p99 0.0139, max 0.0229, `reports/epl_walkforward.md`, quoted in
freshness §1.3). The backfill substitutes a source whose per-match disagreement
with the primary is the size of the sampler's own jitter. That is the honest
statement of what the backfill costs, and it is why the backfill is confined to
history (§3.3 reports the estimand restricted to Avg-only windows as a
secondary).

**The backfill never touches the live arm.** It applies to matches played before
2019/20 and to nothing else. A live 2026/27 anchor reads `Avg` and only `Avg`,
because `PS` is not there to read.

**The panel, pinned.** Built from the ten files `E0_1415` … `E0_2425` — the only
files any cutoff in this experiment can reach (`E0_2526`'s earliest match is
2025-08-15, after the last cutoff 2025-05-19) — one row per archive match with a
complete opening triple, home/away resolved through `epl.teams`, de-vigged by
`epl.devig.proportional`:

| | |
|---|---|
| rows readable by this experiment (`date < 2025-05-19`) | **4,167** |
| by source | `Avg` **2,267** · `PS` **1,900** |
| date range | 2014-08-16 … 2025-05-18 |
| canonical SHA-256 | `84ea5621e1aaa45bd43c3063897d79525103ae74dd51eb071b777bae9618235c` |

The canonical form is `json.dumps` over records
`{date, home, away, src, h, d, a}` sorted by `(date, home, away)`, prices rounded
to 4 dp, `sort_keys=True, separators=(",",":")`. **Every one of the 4,560 archive
matches has a complete opening triple**, so no match is silently absent from the
panel and there is no imputation anywhere in this design.

Source-file digests, pinned so a re-download cannot change a number silently:

```
76b7858051ff6b17f46f49f26fdc70c1f29537270492606f5cc63d67fad5d149  E0_1415.csv
bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085  E0_1516.csv
9625a7652b5f98fbd3e2e4d378c851fc246693f3343e34a72428d5b6e864d3e0  E0_1617.csv
4f3389365ef3f7ac966764ed8ba67cf3b79f5aebed18dd224099c4b2c98bc67b  E0_1718.csv
7c096b3c2ecd54c6993d22eeea73450c2bde11e3457238b226b8f43c62dfc35e  E0_1819.csv
100037618b94f94057400bb02bf6bac4ef74ddaa58cde4b38370839c39caee61  E0_1920.csv
5afe63f69401457b8354eaacee24f9a3e520b3c3af6329564a9783e20d789c62  E0_2021.csv
335afcbabeb2939fa10ab39ba3e8215072d0b577cb8d0705c1e44c56e934e703  E0_2122.csv
8442792d3b614c94ea3cf381bd2736805889cc1713169035368fff19c3d02380  E0_2223.csv
b2e057b0ed959f198b0f63d2391c01239f3608e6de5db68edab3f88e04d07ff3  E0_2324.csv
d0c8ce4a96d886cf60cf101f570f4a3893844226f91c7bd769eb568c49edbfa4  E0_2425.csv
```

**A named archive limitation, stated before the run.** The committed season files
are the source's *final* versions. An "opening" price in a final file is the
price the aggregator recorded when the market opened, but nothing in the file
proves it was never revised afterwards. A backtest reading the final file may
therefore see a value a live system could not have had. This is unfixable from
the archive and it is **not** guarded by a tolerance; it is disclosed. The A9
capture programme is the mitigation: the live arm reads only the dated snapshots
(§3.5), never the final season file, so the live arm is strictly harder than
this backtest, and once a season of snapshots exists a dated note may compare
snapshot openings to the final file's openings.

### 0.4 The existing anchor, read from the code

`src/wcmodel/model/scoreline.py:191-218` (`_priors`), verbatim in effect:

```
if strength and strength.get("enabled"):
    ez = np.asarray(d.elo_z if d.elo_z is not None else np.zeros(d.n_teams), dtype=float)
    mean_att = float(strength["k_att"]) * ez
    mean_def = float(strength["k_def"]) * ez
else:
    mean_att = 0.0
    mean_def = 0.0
att_raw = pm.Normal("att_raw", mean_att, sigma_att, shape=d.n_teams)
def_raw = pm.Normal("def_raw", mean_def, sigma_def, shape=d.n_teams)
att = pm.Deterministic("att", att_raw - pt.mean(att_raw))
defe = pm.Deterministic("def", def_raw - pt.mean(def_raw))
```

`d.elo_z` is a **single per-team vector**. On the EPL path it is supplied by
`epl/dcfit.py:264` — `state = anchor_state_at(anchor, cutoff, teams, observed_by)`
then `elo_z = state.elo_z(teams)` — and handed to `build_design(mp, cov=…,
cov_mask=…, elo_z=elo_z)`. `epl.anchor.AnchorState.elo_z` mirrors
`wcmodel.model.strength.team_elo_z` exactly: population (ddof=0) z-score, and
**all zeros when the dispersion is zero**.

**The doubled anchor, named.** `k_att = k_def = 0.6`, so a club's Elo enters
`att` and `def` at 0.6 each. Because
`log λ_home = μ + h + att[home] − def[away]` and
`log λ_away = μ + att[away] − def[home]`, a strength difference of `Δz` moves
`log(λ_home/λ_away)` by **2 × 0.6 × Δz = 1.2 Δz**. This is the doubling the
World Cup accuracy review found, present identically in the EPL fit. **This
document does not fix it and does not widen it** — §2.2 rules the market term
into the *same* vector at the *same* scale, so the multiplier after adoption is
exactly the multiplier before it. Whether 1.2 is the right total anchor strength
is a separate question, left open in §6.

### 0.5 The size of the treatment

`z_mkt` and `elo_z` are both unit-sd z-scores over the fitted teams, so the
prior mean moves by `k_att × w × sd(z_mkt − elo_z)` when the blend weight is
`w` (§2.2). Recomputed across all 212 cutoffs:

| quantity | mean | median | min | max |
|---|---:|---:|---:|---:|
| `sd(z_mkt − elo_z)` (z units) | 0.2942 | 0.2920 | 0.1455 | 0.4268 |
| prior-mean shift at `w = 1`, i.e. `0.6 × sd` (log-rate units) | **0.1765** | — | 0.0873 | 0.2561 |
| as a fraction of the attack prior scale `sigma_att = 0.5` | **0.353** | — | 0.175 | 0.512 |

**The largest treatment this experiment can apply is about a third of a prior
standard deviation on a club's mean**, against a likelihood carrying 2,000–3,900
decay-weighted matches. That is stated here, before the run, so that a small
effect is not later reported as a disappointment and a large one is not reported
without someone asking how a third of a prior sd moved a posterior that much.

---

## 1. The question, and the honest motivation

### 1.1 What A9 opened, and what it did not

A9 (a) permits market data as a **model input** under a preregistered design. A9
(b) permits market **benchmark columns** on prospective surfaces. A9 (c) leaves
the lock-v10 closure of the World Cup odds-anchoring program standing as history
and requires new market-anchored work to be **new work under new
preregistration**. This is that new work. Nothing here re-runs, re-opens or
retracts the OA program; what it reuses from it is machinery and argument, named
where used.

### 1.2 Why the target is the PRIOR and not the output

The obvious design is an output blend: mix the model's 1X2 vector with the
de-vigged market's. It was measured, and it is dead twice over.

**It saturates.** A leave-one-season-out output blend of `dc` with the de-vigged
market beats `dc` by **+0.0063 RPS with closing odds and +0.0050 with opening
odds**, with season-block CIs excluding zero — and the selected weight goes to
**`w = 1.0`, pure market**; the DC residual adds **+0.0002, not significant**.
A blend whose optimum is "use the market and discard the model" is not a model
improvement. It is a measurement that the market is better, which §0.2 already
prints in one line.

**And it cannot reach the product.** A8's kill argument applies verbatim: **a
1X2 law defines no scoreline law.** The league-table simulator consumes
scorelines. An output blend produces three numbers per fixture and cannot feed
the table engine, so even a blend that helped could not be adopted into the
thing this repository builds.

**So the target is the input.** A market-implied strength term in the DC fit's
**prior**, beside the Elo anchor that is already there. The fit still produces a
scoreline law; the table engine still runs; the market's information enters where
information belongs, and the likelihood is free to overrule it.

### 1.3 The motivation correction, recorded before the run

The story that motivated this work was **roster blindness**: the model cannot see
a summer transfer window until results accumulate under a 365-day decay
half-life, so a market anchor should help most **early in a season** and most on
**promoted clubs**.

**That story failed measurement.** The early-season × promoted-club interaction
in the measured gain is **~0.000**: the gain does not concentrate early and does
not concentrate on promoted clubs. It is broad.

**The honest motivation is therefore broad information, not roster blindness.**
The market prices every club every week using information the model does not
have — injuries, form, tactical change, money — and it prices them better than
the model does at every point in the season, not only in August. This document
states that as the motivation and states the failed story as a failed story.
Nothing below is designed around, weighted toward, or reported in terms of
promoted clubs or early matchweeks, and §3.1's strata exist to *report* those
cuts, not to rescue them.

There is a structural echo of the correction in the design itself, and it is
worth naming: under §2.3's leakage rule the market term is **silent about
promoted clubs** — a club with no prior-season EPL match has no window, so its
`z_mkt` is zero and the market prior does nothing for it. If the roster-blindness
story had been true, this design would have been the wrong one. The measurement
says it was not true, so the silence costs the estimand nothing it was measured
to have.

### 1.4 The room, recomputed — including the part that is not flattering

The design work reports the room as: **only 6% of the market-minus-DC strength
disagreement is already in Elo; residual sd 0.44 log-odds; correlation +0.17 with
DC's own errors.** Recomputing from the pinned corpus and the pinned odds panel,
per fixture, with `m = log(p_home/p_away)`:

| quantity (2,280 corpus fixtures, Avg-opening de-vigged) | value |
|---|---:|
| `δ = m_market − m_dc`: mean / sd | +0.0391 / 0.4104 |
| `corr(δ, elo_diff_pre)` | −0.2855 |
| **share of `δ` explained by Elo (`R²`)** | **8.2%** |
| residual sd of `δ` after removing Elo | 0.3932 log-odds |
| **`corr(δ, DC's signed error)`** | **+0.1712** |
| `corr(Elo-residualised δ, DC's signed error)` | +0.1679 |

**The design's three figures reproduce**: 8.2% against 6%, 0.393 against 0.44,
and **+0.1712 against +0.17 exactly**. The market's disagreement with the model
is almost entirely *not* something Elo already knows, and it points, weakly but
measurably, at where the model is wrong.

**And now the number the design work does not report.** At the level the anchor
actually operates — a **per-club strength vector**, not a per-fixture edge — the
market is nearly collinear with the Elo anchor already in the prior. Recomputed
at all 212 cutoffs, over each cutoff's fitted teams:

| quantity | mean | median | min | max |
|---|---:|---:|---:|---:|
| `corr(z_mkt, elo_z)` | **+0.9549** | +0.9574 | +0.9089 | +0.9894 |
| `R²` — share of `z_mkt` explained by `elo_z` | **0.9121** | 0.9166 | — | — |
| residual sd of `z_mkt` after removing `elo_z` (z units) | 0.2906 | 0.2889 | — | — |

**Roughly 91% of what the market knows about a club's strength is already in the
prior, put there by the Elo anchor.** The room this experiment can occupy is the
remaining ~9%, scaled by `k_att = 0.6` — which is exactly the 0.35-prior-sd
treatment of §0.5.

The two facts are not in conflict and both are true. `z_mkt ≈ 0.955 · elo_z + ε`
and DC's own fitted strength is *itself* anchored on `elo_z` at k = 0.6, so the
`elo_z` component very largely cancels out of the *difference* `m_market − m_dc`,
leaving a residual that is only 8% Elo. A per-club anchor is mostly redundant;
the per-fixture disagreement it leaves behind is mostly not. **This document
prints the pessimistic framing beside the optimistic one and lets the experiment
decide**, and neither number is the estimand, a secondary, or an input to the
adoption rule.

**The 6% figure could not be reproduced exactly, and the reason is structural:**
recomputing it as the design work defines it needs DC's *fitted* per-club
strengths at each cutoff, which requires the very fits this document
preregisters. The 8.2% above is the closest quantity computable from artifacts
that exist today — the same functional, evaluated on the corpus's published DC
forecasts instead of on its unpublished posteriors. If the design work's recipe
is later supplied and reproduces 6%, that is a dated note and changes nothing
below.

### 1.5 What the leakage rule costs, measured before it is adopted

§2.3 rules that only the odds of **matches already played** may enter `z_mkt`.
That rule throws information away, and this document measures how much rather
than asserting it is negligible. Rebuilding the market edge under the
conservative rule — `m_cons = η + s[home] − s[away]` from the past-only window,
at each fixture's own block cutoff — over the 2,261 fixtures that have one:

| quantity | same-fixture odds (**illegal**) | past-odds-only (**the design**) |
|---|---:|---:|
| `corr(δ, DC's signed error)` | +0.1712 | **+0.0982** |
| `corr(Elo-residualised δ, DC's signed error)` | +0.1679 | +0.0916 |
| `corr(δ, elo_diff_pre)` | −0.2855 | −0.4907 |
| `sd(δ)` | 0.4104 | 0.3784 |

**The conservative rule retains about 57% of the correlation with the model's own
errors** (0.0982 / 0.1712). Just over two fifths of the measurable signal is
given up to make the design defensible. That is the price, it is stated before
the run, and §2.3 argues why it is the right price.

### 1.6 What the pairing does and does not remove

The design is paired at the fixture: the same fixture, the same clubs, the same
date, the same realised outcome, the same metric, priced by two fits that differ
in **one thing only — the blend weight `w` in the prior mean**. Composition
cannot enter the mean of a within-fixture difference.

**(a) ADVI sampling noise between two fits.** Both arms use seed 20260611 —
`epl/walkforward.py` does not vary the seed by cutoff and there is no per-cutoff
derivation anywhere in the walk — but they optimise against different priors, so
their trajectories differ and the residual noise is effectively independent. Its
measured scale on this exact corpus and model: the whole 212-fit walk re-run at
seed 987654 moved pooled DC mean RPS by **+0.000075**; per-match probability
distance mean **0.0032**, p99 **0.0139**, max **0.0229**
(`reports/epl_walkforward.md`). Pairing cannot subtract this. **Blocking absorbs
it**, and the blocking is chosen so that it can: every fit involved in pricing a
fixture sits at that fixture's own block opening, so fit-level noise is nested
strictly inside a bootstrap block in both arms. An iid bootstrap would count one
fit's noise realisation, shared by up to 20 fixtures, as 20 independent pieces of
evidence.

**(b) The asymmetry that has a direction.** Arm A's prior sees information Arm
B's does not. That is the treatment. But it means **any leak biases the result
toward adoption**, which is the direction the model change would be made on.
Four guards, pre-stated: the `date < cutoff` bound on the training frame,
unchanged and already canaried (§5.3); the market window's own bound, canaried
separately because the existing canary rewrites results and cannot see odds
(§5.4); the `w = 0` re-fit control, which must return the corpus's own rows
(§3.2); and the in-fold selection of `w`, which never touches the scored season
(§2.4).

**(c) The treatment is not decomposed.** Moving `w` moves the prior mean of every
club's `att` and `def` at once. The estimand is the value of **a fit taken under
a market-informed strength prior**, which is the operational object. Nothing here
attributes the effect to a club, a stratum, or a component of the market's
information, and no such attribution may be read out of the result afterwards.

**(d) Direction of bias, on balance.** Setting aside a leak, the residual is
sampler noise, close to mean-zero, entering both arms through the same optimiser,
the same `advi_iters` and the same draw count, so the approximation penalty is
first-order equal and cancels in the difference. **The design has no argued
direction of bias and a variance floor of order 1e-4 that §4's threshold sits on
top of.**

---

## 2. The mechanism and the estimand

### 2.1 `z_mkt` — market-implied club strength, exactly

For a cutoff `C` (a block opening at midnight):

**Step 1 — the window.** Take every panel row (§0.2) whose match date is
**strictly before `C`** and **within 365 days of `C`**; then keep a row if it is
among the **10 most recent** such matches of *either* club. Two constants, both
fixed here: `M = 10` matches per club, `L = 365` days. `L` is the model's own
`decay_half_life_days`, not a new number. `M = 10` is one club-quarter of a
38-match season and is the same window the fit already uses to decide that a
club is low-information — `config/config.yaml:11`, `elo.volatility_window: 10`,
read on this very path by `count_volatility_arm` in `epl/dcfit.py`. **Neither is tuned; the
only parameter this experiment selects is `w` (§2.4).** Recomputed across the 212
cutoffs, the window holds **min 201, median 233, max 262 matches**.

**Step 2 — de-vig.** `epl.devig.proportional` — the naive proportional
normalisation, which is `wcmodel.data.devig.multiplicative` (the OA's own
`OA_DEVIG_LABELS` records that "basic" *is* multiplicative), and which the
package's tests assert agrees with `wcmodel`'s implementation to **1e-12** on
the real prices. **Multiplicative, per the OA precedent, and it is not a choice
made here**: preferring whichever de-vig scores better would be choosing the
input to suit the answer, exactly as `epl/devig.py`'s own docstring refuses to do
for the benchmark. Shin is not used, is not swept, and is not reported as an
alternative anchor.

**Step 3 — the inversion, by weighted ridge least squares.** For each window
match `i` with de-vigged `(p_H, p_D, p_A)`, define the market's draw-excluded
home-minus-away log-odds

```
m_i = log(p_H,i / p_A,i)
```

and fit

```
m_i  =  eta  +  s[home_i]  −  s[away_i]  +  residual
```

by weighted least squares with weights `w_i = 0.5 ** (age_days_i / 365)` — the
pipeline's own decay weight (`src/wcmodel/data/features.py:297`), so the market
anchor's memory is the likelihood's memory and not a second free knob — and a
ridge penalty `λ = 1.0` on the club coefficients `s` only, never on `eta`. In
matrix form, with `X` the (n × (K+1)) home/away incidence matrix whose last
column is all ones:

```
s, eta  =  solve( Xᵀ W X + diag(λ,…,λ, 0),  Xᵀ W m )
```

`λ = 1.0` is fixed here, is **not** selected, and exists to shrink a club with
few window matches toward the league mean rather than to fit anything. Sanity of
the solve, recomputed at all 212 cutoffs: `eta` — the market's implied home
advantage in log-odds — runs **0.2519 to 0.4429, median 0.3740**, and the
cross-club sd of `s` runs **0.6693 to 0.8181, median 0.7514**. The system is
well-conditioned at every cutoff and never degenerate.

**Step 4 — the z-score.** `z_mkt` is `s` z-scored over the **fitted teams** (the
design's team index), population sd (ddof = 0), with **all zeros when the sd is
zero** — mirroring `wcmodel.model.strength.team_elo_z` and
`epl.anchor.AnchorState.elo_z` contract for contract, so the two vectors live on
the same scale and can be mixed.

**A fitted club with no window match gets `z_mkt = 0`** — the no-information
shrink to the mean, which is what `team_elo_z` already does for an absent club.
This is not a dropped fixture and never becomes one. Recomputed: it happens at
**7 of 212 cutoffs**, and affects exactly **19 of 2,280 fixtures**, every one of
them a promoted club's opening weekend:

```
2019-08-09  liverpool–norwich · bournemouth–sheffield_united · tottenham–aston_villa
2020-09-12  fulham–arsenal · liverpool–leeds · west_brom–leicester
2021-08-13  brentford–arsenal · watford–aston_villa · norwich–liverpool
2022-08-05  fulham–liverpool · bournemouth–aston_villa · newcastle–nottm_forest
2023-08-11  burnley–man_city · brighton–luton · sheffield_united–crystal_palace
2024-08-16  ipswich–liverpool · newcastle–southampton
2024-08-19  leicester–tottenham · fulham–leicester
```

These 19 fixtures stay in the estimand's denominator with the market term inert.
§1.3 explains why that costs nothing the measurement says was there.

### 2.2 How it enters the prior — the ruling

**The market term does not add a second anchor. It rotates the one that exists.**

```
z_blend(w)  =  zscore_over_fitted_teams( (1 − w) · elo_z  +  w · z_mkt )      for w > 0
z_blend(0)  :=  elo_z                                                          exactly
mean_att    =  k_att · z_blend(w)     with k_att = 0.6, FROZEN
mean_def    =  k_def · z_blend(w)     with k_def = 0.6, FROZEN
```

Four things this ruling settles, each of which the alternative would have left
open:

**(i) The att/def entry: symmetric, at the same scale, into both.** Not att-only.
The algebra is why. With `att[t] = a_t + m_t` and `def[t] = d_t + m_t` for a
common shift `m_t = k · z_blend[t]`,

```
log λ_home  =  μ + h + (a_h + m_h) − (d_a + m_a)   gains  (m_h − m_a)
log λ_away  =  μ     + (a_a + m_a) − (d_h + m_h)   gains  (m_a − m_h)
```

so the **sum of the two log-rates is exactly invariant** and the anchor moves the
*margin* only. An att-only entry would raise a strong club's attack without its
defence and therefore push expected **total goals**, injecting a 1X2 signal —
which carries information about the margin and none about the total — into a
channel it says nothing about. Symmetric entry is the only entry consistent with
what a 1X2 price actually is.

**(ii) The doubled anchor is neither fixed nor widened.** Because the market term
travels inside the *same* vector at the *same* `k`, the net multiplier on the
strength difference stays exactly `2 × 0.6 = 1.2` at every `w`, identical to
today's. **No `w` in this experiment changes how hard the prior pulls; `w`
changes only which direction it pulls in.** The doubling is disclosed in §0.4 and
left where it is: fixing it is a change to `k_att`/`k_def`, which is a different
experiment with a different estimand.

**(iii) The anchor's strength is not silently re-swept.** The additive
alternative — `mean = 0.6 · elo_z + k_mkt · z_mkt` — would confound "the market's
information helps" with "a tighter anchor helps", because `z_mkt` is 91%
collinear with `elo_z` (§1.4): at `k_mkt = 0.6` the Elo-direction pull would
nearly double to ~1.17 without one word of the design saying so.
`scripts/sweep_strength_k.py` settled `k = 0.6` on held-out RPS; **this
experiment does not re-open that decision by accident.**

**(iv) `w = 1` is the exact input-level analogue of the output blend's
saturation endpoint** — a *pure market direction* for the prior — which is what
makes §2.5's pre-ruling meaningful rather than decorative.

**`w = 0` is the baseline, exactly.** `z_blend(0)` is defined as `elo_z`
literally, not as `zscore(elo_z)`, so the identity is exact by construction
rather than to float round-off, and a `w = 0` fit is the corpus's own
specification. §3.2 makes that a checkable control instead of a claim.

### 2.3 The leakage rule — which odds are legal at cutoff `C`

> **Only the odds of matches whose kickoff is strictly before `C` may enter
> `z_mkt(·, C)`. A fixture kicking off at or after `C` contributes nothing to the
> prior of the fit that prices it, and neither does any other fixture of its
> matchday.**

This is the subtlest clause in the design and it is ruled the conservative way,
with the argument, because the permissive alternative is tempting and wrong here.

**The permissive alternative, stated fairly.** A live system at `C` genuinely
*does* have opening prices for the coming weekend — they are typically posted
days ahead. Reading them would make the anchor fresher and, per §1.5, roughly
twice as informative. Three reasons it is refused:

1. **It is unverifiable from the artifact.** The archive carries no publication
   timestamp for an opening price. "Published before `C`" is a claim about the
   world that the file cannot support, and a preregistration may not rest a
   leakage guarantee on an unrecorded fact. Re-scheduled and midweek fixtures
   make it false often enough to matter.
2. **It puts a fixture's own market price into the prior that prices it.** Even
   where temporally legal, the scored forecast would then contain the market's
   opinion of that exact match. The comparison policy (§3.4) already bans
   claiming credit against a same-timing market for precisely this reason; it
   would be incoherent to ban it at the output and permit it at the input.
3. **The conservative rule inherits a bound that is already proven.** A match's
   odds are published before the match. So "the match is legal at `C`" implies
   "its odds are legal at `C`", and match legality is `features.build`'s existing
   `date < cutoff.normalize()` bound — the same bound the likelihood uses, the
   same bound `epl.walkforward.point_in_time_canary` returned **max |Δp| = 0.0**
   on against a positive control of 0.812. **The legality of an odds row is
   inherited from the legality of its match**, and needs no new argument, no new
   timestamp, and no new trust.

**What adoption would therefore commit to.** If this experiment adopts, the live
arm runs under **the same rule**: at issuance, `z_mkt` reads only matches already
played. A live implementation that reads the coming weekend's prices is **a
different model** and needs its own preregistration and its own run. This
sentence exists so that nobody adopts on the conservative backtest and ships the
permissive version; §7 lists doing so as an invalidation.

**And the backtested number is a lower bound.** §1.5 measures the cost at ~43% of
the correlation with DC's errors. Whatever this experiment reports, a permissive
design could report more — and would have to earn it under its own document.

### 2.4 The parameter `w`, and how it is selected

**The grid, fixed here:**

```
w ∈ { 0.00, 0.15, 0.30, 0.50, 0.75, 1.00 }
```

Six points. `w = 0.00` is on the grid deliberately — **the selection must be
allowed to say "no market term"** — and it costs no fits, because a `w = 0` fit
is the corpus's own row (§2.2). Five points require fits. The grid is kept to six
because every point costs 212 fits (§2.7) and because `w` is a mixing weight on
[0, 1] with no structure finer than this to resolve: `sd(z_mkt − elo_z)` is 0.29
z-units, so adjacent grid steps move a club's prior mean by 0.026–0.044 log-rate
units, already below the model's own per-match forecast jitter.

**Selection is leave-one-season-out and in-fold, never on the scored season.**
For each of the six seasons `s`:

1. Score every grid `w` on the **other five seasons'** fixtures by mean RPS.
2. Take the argmin. **Ties break toward the smaller `w`** — less market
   dependence — which is `src/wcmodel/eval/blend.py`'s own frozen tie order
   (`(mean RPS, w, method)`), adopted here rather than invented.
3. Season `s`'s fixtures are priced at **that** `w`, chosen without any fixture
   of season `s` in the selection.

The six selected weights are published with the result. `LOSO` is used rather
than `blend.py`'s monthly walk-forward because the estimand pools whole seasons
and the bootstrap blocks are seasons and ISO weeks; a monthly fold would leak
across a season boundary in both directions.

**No other parameter is selected anywhere in this experiment.** `M`, `L`, `λ`,
the de-vig, `k_att`, `k_def`, the seed, `advi_iters`, the decay half-life and the
widening are all fixed above or frozen in the config.

### 2.5 The `w → 1` analogue, pre-ruled

The output blend saturated at pure market. The input-level analogue must be ruled
before it can happen, so here it is:

> **If LOSO selects the grid maximum `w = 1.00` in any fold, the result publishes
> with that fact stated in its headline, the count of folds doing so is printed,
> and the "model contributes nothing" diagnostic runs.**

**And the honest distinction, stated in advance: `w = 1` is NOT the market's
forecast.** At `w = 1` the prior's *direction* is the market's, and the
likelihood, the decay, the widening, the correlation term and the scoreline
structure are all still the model's. Unlike the output blend, whose `w = 1`
endpoint *is* the de-vigged market vector by construction, this experiment's
`w = 1` arm is DC fitted under a market-directed prior and can be better or worse
than the market. The two saturations are not the same event and may not be
described as if they were.

**The diagnostic that runs at the boundary**, labelled exactly as §3.4 requires:
the `w = 1` arm's mean RPS beside the **same-timing (opening) market**
benchmark, printed as a *model-contribution diagnostic* and nothing else, plus
the correlation between the arm's forecasts and the de-vigged opening market's,
plus §3.3's movement diagnostic. If that comparison shows the arm has collapsed
onto the market, the finding is that the prior has stopped being a prior — which
is a reason to report, not a reason to hide.

**The threshold in §4 does not move in either direction on account of the
selected `w`.** A grid-maximum selection is a fact printed beside the number, not
an adjustment to the bar.

**The symmetric case needs no special rule.** If LOSO selects `w = 0.00` in every
fold, the estimand is exactly 0.000000 by construction, the CI is degenerate, and
the finding is that in-fold selection preferred no market term at all. That
publishes too (§4.4).

### 2.6 The arms, the estimand, and where the numbers go

**The arm's name is `dc_market_prior`.** Ruled here. It does not collide with
"anchor", which in this repository already means the Elo prior
(`epl.anchor.Anchor`, `anchor_spec`) and the G3 digest regime; it does not
collide with `market_*`, which means the de-vigged benchmark; and it names the
**mechanism** — a prior — so it can never be read as a market-derived forecast.
Grep confirms no existing use of `dc_market_prior` or `dc_mkt` anywhere in the
repository.

* **Arm B — `dc_native`.** For each of the **2,280** corpus fixtures, the
  probabilities and RPS **already in the corpus** (`dc_home`, `dc_draw`,
  `dc_away`, `dc_rps`), at the eight decimals they were written with. **Arm B is
  not recomputed.** It is the published walk-forward's own output.
* **Arm A — `dc_market_prior`.** For each of the **212 block openings**, one fit
  at that cutoff at the season's LOSO-selected `w`, through the identical
  pipeline: `freeze.frozen_wcmodel_config()`, seed **20260611**,
  `epl.fit.build_store` over the played frame, `epl.anchor.Anchor` with
  `freeze.frozen_elo_config()`, `epl.dcfit`'s orchestration with
  `feature_cache_dir=paths.FIT_CACHE_DIR` and `fast_panel=True`, with
  `z_blend(w)` in the `elo_z` slot of `build_design`; then
  `post.predict_1x2(home, away, neutral=False)` for that block's fixtures,
  rounded to 8 decimals by the same `round(v, 8)` the ledger uses.
* **The delta** — `rps(A) − rps(B)` per fixture, RPS by `epl.score.rps`
  (`epl/score.py:91`) on the same `y` encoding. The harness recomputes Arm B's
  RPS from the stored probabilities and refuses if it differs from the stored
  `dc_rps` by more than **1e-12** (`ScoreMismatch`); checked on 2026-08-26 across
  all 2,280 rows, the maximum difference is **0.0**.

> **THE ESTIMAND: the mean paired RPS delta, `dc_market_prior` minus
> `dc_native`, over all 2,280 fixtures of the pinned corpus. Negative means the
> market prior helps.**

* **The statistic** — the mean over all 2,280 deltas, pooled over matches, not a
  mean of block means.
* **The primary interval** — `epl.score.block_bootstrap_ci` (`epl/score.py:193`),
  blocks = the corpus's own `block` column, `(season, ISO week)`, giving **212**
  blocks; **B = 10,000**; percentile; `alpha = 0.05`; resampling seed
  **20260814**, the function's default and the project's standard.
* **The season interval** — the same function, the same B, the same seed, blocks
  = the corpus's **6 seasons**. Both are reported; §4.1 rules that **both must
  exclude zero**.

**The denominator is fixed at 2,280 and no fixture may be dropped.** A fixture
Arm A cannot price is a refusal (§5.1), never a deletion. Arm A's fits see the
same matches as Arm B's, so an unpriceable fixture in Arm A is a defect by
construction.

**The output file is new.** Per-fixture Arm A rows go to
`data/epl/fit/dc_market_prior_predictions.parquet`, a file that does not exist
today. The pinned corpus `f31580073e…` is **never regenerated**; two standing
preregistrations check its digest in code, and this experiment reads it and does
not write it.

**No power claim is made in advance.** The paired SD is unknown until the fits
exist. The realised paired SD, SE and the MDE at 80% power are reported **with**
the result. **No threshold in §4 moves in response to them.**

### 2.7 Where the code lives — the config hook, verified

The design brief reported that `config/config.yaml` ~line 60 reserves a
market-anchor `strength_prior` source, and asked for it to be verified rather
than trusted. **It is FALSE as an operative hook.** The key exists:

```
58:  strength_prior:
59:    enabled: true            # CALIBRATED ON: anchoring beats the old model AND plain Elo on held-out 1X2 RPS
60:    source: elo              # elo only in v1 (market anchor out of scope)
61:    k_att: 0.6               # knee of the held-out-RPS curve: …
68:    k_def: 0.6
```

…and **nothing reads it.** `_priors` (`src/wcmodel/model/scoreline.py:191-218`)
reads `enabled`, `k_att`, `k_def` and `d.elo_z`, and never `source`; a repository
grep for a read of `strength_prior["source"]` or `.get("source")` returns
**nothing** in `src/`, `epl/` or `scripts/` — the only textual hits are a
docstring in `scripts/sweep_strength_k.py` that *writes* the key and a comment in
`src/wcmodel/model/strength.py` about data sources. `epl/config_frozen.json`'s
realised config carries `{"enabled": true, "source": "elo", "k_att": 0.6,
"k_def": 0.6}`. **Setting `source: market` would change no computed value.** The
key is documentation with the shape of a hook.

**The harness nevertheless needs no `src/` edit, and no experiment branch.** The
reachable seam is one layer down and already `epl/`-side: `epl/dcfit.py:264`
builds `elo_z` itself and hands it to `build_design(mp, cov=…, cov_mask=…,
elo_z=elo_z)`, and `build_design` accepts any correctly-shaped vector
(`src/wcmodel/model/panel.py:95-118`). Supplying `z_blend(w)` in that slot
delivers `mean_att = 0.6 · z_blend` and `mean_def = 0.6 · z_blend` through
`wcmodel`'s own unmodified prior code. So:

* **`src/`, `scripts/`, `site/`, `tools/`, `.github/` are not touched.** The lock
  chain is not broken and needs no new version for this work.
* **`config/config.yaml` is not edited either.** `source: elo` stays as it is,
  and this document records that it is inert so a future reader does not mistake
  it for a switch. (Turning it into a real switch would be an `src/` change and a
  different piece of work; it is not needed and is not proposed.)
* **All harness code lands under `epl/`** — `epl/mktprior.py` and
  `epl/tests/test_mktprior.py` — and the run writes only to `data/epl/fit/`
  (its ledger, its shards, `dc_market_prior_predictions.parquet`,
  `anchoring.json`, and the existing feature cache under `paths.FIT_CACHE_DIR`)
  and to `reports/epl_anchoring_result.md`.
* **`epl/parse.py` is not modified.** The `Avg`-opening extraction is a new
  `epl/`-side reader in `epl/mktprior.py`; the existing Pinnacle benchmark
  columns keep their existing meaning.

Because the config hook is inert, **the experiment runs on `main` with an
`epl/`-only harness**, not on a pinned experiment branch. Only an ADOPT would
put market-prior wiring on the model's production path, and that lands batched
into the next lock version under the house merge-batching rule (§6).

**One caching fact, checked because it would have been a silent disaster.**
`epl.dcfit.fit_epl` calls `wcmodel.model.inference.sample` **directly**, which
does no caching; `wcmodel`'s content-addressed `cached_fit` — whose key hashes
the config and the match panel **but not the ratings** (`epl/dcfit.py` module
docstring) — is used by the dashboard and backtest paths and **not** by this one.
Two fits at different `w` therefore cannot collide in a posterior cache. The
*feature* panel cache (`wc_features.build_cached`) is keyed on cutoff, store and
config and is independent of `w`, so sharing it across the five weights is
correct and is what makes the budget below achievable. §5.1's `PanelOutOfDate`
guards the one way that could go wrong.

### 2.8 The compute budget, stated so it cannot later become a reason to redesign

| | fits |
|---|---:|
| 212 cutoffs × 5 grid weights requiring a fit (`w = 0` is the corpus) | **1,060** |
| §3.2 control: `w = 0` re-fits at 20 pre-stated block openings | **20** |
| **total** | **1,080** |

At the preregistered walk's realised warm rate (212 fits in 31 minutes,
≈ **8.8 s/fit** with the fast panel and a warm feature cache) that is
**≈ 2.6 hours**. At the measured cold single-fit cost of **57.24 s**
(`data/epl/fit/single_fit.json`) it is **≈ 17.2 hours**. **The grid is the
multiplier and it is stated honestly: a sixth grid point would cost another 212
fits, which is why there are six and not twenty.**

The run may be sharded by `(cutoff, w)` under §5.1's merge rule, with BLAS
threads pinned to 1 per worker and per-PID waits. **It may not be thinned.**
Dropping weights, cutoffs, seasons or strata to fit a clock is an amendment, not
an optimisation.

---

## 3. Secondaries — reported, never deciding

Everything in this section is published with the result and **decides nothing**.
No secondary may adopt, block, or qualify an adoption. A stratum that clears
§4's threshold while the estimand misses it **does not license a
stratum-conditional market prior**: that is a different rule, needing its own
preregistration and its own run.

### 3.1 Strata

**By season** — six strata, each reporting n, mean delta, paired SD, the selected
`w`, and a `(season, ISO week)` block bootstrap CI at the same B and seed.

**By matchweek position** — three strata, fixed here: **matchweeks 1–6**,
**7–19**, **20–38**, by the fixture's position in its season. These exist because
§1.3's failed story predicted an early-season concentration and the record should
show what actually happened, not because anything conditions on them.

**By promoted-club involvement** — two strata: fixtures with at least one
promoted club (`home_promoted | away_promoted`) and the rest. Same reason.

**Eleven intervals across three families. Some will exclude zero by chance.** No
multiplicity correction is applied, because none of them decides anything — and
that is the correction.

### 3.2 The `w = 0` re-fit identity control

**What it is.** Twenty block openings are re-fitted at `w = 0.00` and their
blocks' fixtures re-priced. Because `z_blend(0)` is defined as `elo_z` exactly
(§2.2), those fits are re-runs of a specification the corpus already contains, so
**they must return the corpus's own rows.**

**The twenty dates** are **freshness §3.2's twenty**, reused verbatim rather than
re-drawn, so the choice cannot have been made to suit this experiment. They are
the ascending block-opening dates at indices
`numpy.random.default_rng(20260826).choice(212, size=20, replace=False)`, sorted
— reproduced independently on 2026-08-26:

```
2019-10-21  2019-12-03  2020-02-14  2020-03-07  2020-06-22
2020-07-20  2020-09-14  2021-10-16  2021-12-06  2022-01-11
2022-08-05  2022-10-01  2022-10-18  2023-04-01  2023-04-03
2023-09-01  2024-02-12  2024-02-26  2024-09-21  2024-10-21
```

Those 20 blocks carry **227 fixtures — 681 probabilities** — and cover all six
seasons. (Freshness's control checked the 56 own-day fixtures at those dates;
this one checks the whole block, because a block fit prices its whole block.)

**The tolerance ruled: exact equality at the corpus's own precision.** Every one
of the 681 recomputed probabilities must equal the stored `dc_home`/`dc_draw`/
`dc_away` **exactly** as the 8-decimal values the corpus holds, and the RPS
recomputed from them must equal the stored `dc_rps` to **1e-12**. Not a numeric
tolerance: the seed does not vary by cutoff, a fit is a pure function of
`(cutoff, store, frozen config, z)`, and the project already demands and gets bit
equality from two separate `fit_epl` calls (`point_in_time_canary` with
`np.array_equal`, `verify_fast_path_is_inert` with `DataFrame.equals`). Asking
for less here would be asking for less than the project already proves.

**The condition that makes the demand fair**, pre-stated: the control runs in the
same interpreter and virtual environment as the main run, with
`OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1` per worker and
`fast_panel=True`. The thread pinning is recorded in every row's provenance
(§5.2).

**What it actually tests.** The archive has grown since the walk-forward run —
2025/26 and 2026/27 results have been ingested. Arm A builds its store and anchor
from the archive **as it stands at run time** and relies on the point-in-time
property to make later data irrelevant. This control is where that reliance
becomes a check. **A mismatch is most likely archive drift, not sampler noise**,
and it is a STOP either way.

**On failure the run stops.** `ControlMismatch` (§5.1). The control runs
**first**; not one market-prior fit is run until it passes. A tolerance is never
widened after seeing a difference — a difference is an amendment, written before
anything continues.

**Reported regardless:** the maximum and mean absolute probability difference
across the 681 comparisons, so the number is on the record even when it is zero.

### 3.3 Movement diagnostic

Mean and max absolute probability difference between Arm A and Arm B across all
2,280 fixtures, per selected `w` and pooled, printed beside the seed-replica
scale (mean 0.0032, p99 0.0139, max 0.0229). It answers "did the treatment move
the forecast at all, or less than re-seeding does" — worth knowing whichever way
the estimand lands. It decides nothing.

Reported with it: the realised distribution of `z_blend(w) − elo_z` against
§0.5's pre-run prediction of 0.29 z-units, and the realised per-cutoff `eta`
against §2.1's pre-run band of 0.25–0.44.

### 3.4 The comparison policy — pre-ruled by the decider, recorded here

| comparison | status |
|---|---|
| `dc_market_prior` vs **`dc_native`** | **THE ESTIMAND.** The only comparison that decides anything. |
| `dc_market_prior` vs `elo` | Context. Reported, decides nothing. |
| `dc_native` vs market (Pinnacle **closing**, `market_rps`) | The **unchanged public benchmark**. Not recomputed, not redefined, not moved by this experiment. |
| `dc_market_prior` vs **same-timing (opening) market** | Permitted **only** as an explicitly labelled **model-contribution diagnostic** (§2.5). Never a headline, never an adoption input. |
| `dc_market_prior` vs **closing** market | **BANNED by construction.** The arm reads opening prices; scoring it against the close would credit it with the +0.001385 timing gap of §0.2. |
| any "beats the market" claim, for any arm | **BANNED.** Not in the result document, not in a commit subject, not on a published surface. |

A9 (b) permits a de-vigged market column beside the model's on prospective
surfaces. That permission is about **context**, and this table is what context
may not become.

### 3.5 The live capture cadence, ruled

The A9 capture programme's file (`data/epl/odds_snapshots/`) is
football-data's EPL **fixtures** file, which the source overwrites in place, so
every uncaptured window is unrecoverable.

> **Capture runs TUESDAY AND FRIDAY.** Not Friday only.

The source collects both midweek and weekend rounds into the same overwritten
file; a Friday-only cadence silently misses every midweek round, which in a
congested season is a material share of the fixtures the live anchor would price.
Files stay local per the standing football-data ruling, mirrored to the private
vault, never redistributed. Each snapshot is named with its UTC capture instant
(`fixtures_YYYY-MM-DDTHHMMSSZ.csv`), which is the publication timestamp the final
season file does not carry — the one artifact that could later support a
permissive leakage rule under its own preregistration (§2.3).

**The live arm reads snapshots and never the final season file.** Stated in §0.3
and repeated here because it is the whole point of the cadence.

---

## 4. The adoption rule

### 4.1 The rule

> **ADOPT `dc_market_prior` as a model change if and only if ALL THREE:**
>
> **(i) the point estimate of the estimand is `Δ ≤ −0.0010` RPS, and**
> **(ii) the 95% `(season, ISO week)` block bootstrap CI (212 blocks) excludes
> zero — its upper bound is strictly < 0, and**
> **(iii) the 95% season block bootstrap CI (6 blocks) also excludes zero.**
>
> **Otherwise `dc_native` stands unchanged.**

All three are required and none is sufficient.

### 4.2 Why `−0.0010`, and why it is not scaled to the prize

**`−0.0010` is the house bar for a model change**
([`reports/epl_improved.md`](epl_improved.md) §5.2), against which 45 challengers
were measured and all 45 missed; the best was −0.000065. It is not lowered here
and it is not raised.

It is emphatically **not** scaled to the +0.0050 output-blend prize. That number
is what the *market* is worth against this model, not what a market-informed
*prior* is worth — §1.4 measures the prior-level room at ~9% of the market's
club-strength information, and §0.5 measures the largest available treatment at a
third of a prior sd. Setting the bar at some fraction of +0.0050 would be
choosing a threshold from a quantity this design cannot deliver.

**The freshness experiment's `−0.00030` is not precedent here, and the difference
is principled.** That bar was argued down from `−0.0010` because a cadence change
is *operational*: zero new parameters, one pre-stated candidate, no grid. **This
is the opposite case on both counts.** A market prior is a **model change** — a
new input, a new data dependency, a new failure mode in the live pipeline — and
it comes with a **six-point grid and an in-fold selection**. The two things the
house bar buys that freshness did not need to buy, cover against selection over a
grid and cover against a new degree of freedom that fits noise, are exactly what
this experiment needs. The full bar applies.

**Why (iii) as well as (ii).** The brief specifies "the 95% season-block CI", and
this repository uses that phrase for **both** intervals — `epl_improved.md` §5.1
prints "95% CI, week blocks (212)" and "95% CI, season blocks (6)" side by side
in the same table. Rather than pick the reading that adopts on weaker evidence,
this document requires both. There is also a design reason: **`w` is selected per
season-fold**, so an entire season's deltas share a selected weight — a
dependence the ISO-week blocking does not carry and the season blocking does. A
6-block percentile bootstrap has poor coverage and is not claimed to have good
coverage; its job is narrower and stated plainly: **to refuse a result carried by
one season.**

### 4.3 Why all three, and not any

A point estimate past the threshold with an interval straddling zero is exactly
the pattern the improvement programme rejected four times over. An interval
excluding zero at |Δ| < 0.0010 is a real effect too small to buy a new upstream
data dependency, a twice-weekly capture obligation, and a live failure mode when
a book stops publishing — measurable and material are different findings, and
this rule reports the difference instead of collapsing it. And a week-block
interval excluding zero while the season-block interval does not is a result
carried by fewer than six independent seasons, which is not enough to change the
model.

### 4.4 What happens on a miss, and what publishes either way

**`dc_native` stands**, unchanged, with `strength_prior.source` still inert and
`config/config.yaml` still untouched.

**The result publishes either way.** `reports/epl_anchoring_result.md` and
`data/epl/fit/anchoring.json` are written whatever the sign, whatever the width —
including the case where the estimand is **positive** (the market prior *hurts*,
which a 0.35-prior-sd rotation plus sampler noise can certainly produce), and
including the degenerate case where LOSO selects `w = 0.00` in every fold and the
estimand is exactly zero. **There is no file drawer**, and no outcome of this
experiment is a reason not to publish it. A9 (a) subjects market inputs to the
same gates as everything else, and publishing a miss is one of those gates.

A miss is not re-litigated: not by re-running at a second seed, not by extending
the grid, not by moving to a monthly fold, not by dropping 2020/21, not by
restricting to matchweeks 1–6, not by switching to Shin, not by moving to a
one-sided interval, and not by a bar chosen after the number exists. Each is
listed in §7 as an invalidation.

### 4.5 What adoption would and would not change

**Adoption changes what the prior mean points at.** It changes nothing about the
likelihood, the decay, the widening, `k_att`, `k_def`, the inference backend, the
seed, the scoreline structure, or the metric.

**Adoption is shadow-first.** `dc_market_prior` is a **new arm, run in shadow**,
and **there is no arm switch this season.** The published arm stays the published
arm; the matchboard's forecast stays `dc_native`'s;
`ISSUANCE_SCHEMA_VERSION` stays `epl-issuance-5`. A shadow arm accumulating a
live record is a separate, later, owner decision with its own bar, and this
document does not pre-authorise it.

**Scope boundary.** This experiment scores **match-level 1X2 forecasts by RPS**.
It says nothing about the league-table simulator's TRPS, about table forecasts,
or about the table simulator's record. If a market-anchored fit ever feeds the
table engine, the value of that is a different quantity measured a different way,
and **this document does not license it** — it merely notes, against the output
blend, that an input-level anchor *could* feed it, which is a statement about
feasibility and not about value.

**A named limitation.** The corpus is 2019/20–2024/25 and the decision applies to
2026/27 and after. The mechanism generalises — a live issuance reads played
matches' opening prices, which is what §2 measures — but the magnitude is
measured on six past seasons, with different clubs, and with `Avg` present
throughout while Pinnacle was still alive. That is an argument, not evidence, and
it is written here rather than left implicit.

**Who decides.** Adoption is an owner ruling, recorded as a dated entry in
[`reports/epl_sim_amendments.md`](epl_sim_amendments.md). No script, no agent and
no report may change the model on the strength of these numbers; the rule above
is what the ruling is checked against, not a switch that throws itself.

---

## 5. Refusal semantics for the run

### 5.1 Typed refusals, by name

All derive from **`MarketPriorError`**, caught by `main()`, which prints
`STOP: …` naming the type and the offending key, and exits **2** — the
convention A8's `RecalError` set and freshness's `FreshnessError` follows.

| type | fires when |
|---|---|
| `CorpusMissing` | the pinned parquet is absent |
| `CorpusDigestMismatch` | its SHA-256 is not `f31580073e…` |
| `CorpusShapeMismatch` | rows ≠ 2,280, seasons ≠ the pinned six, `y` counts ≠ (993, 525, 762), or blocks ≠ 212 |
| `ConfigNotFrozen` | `epl/config_frozen.json` is not `9f2e086d…`, the realised seed is not 20260611, or `strength_prior` is not `{enabled: true, k_att: 0.6, k_def: 0.6}` |
| `OddsSourceDigestMismatch` | any of the ten pinned `E0_*.csv` digests differs |
| `OddsPanelMismatch` | the built panel is not 4,167 readable rows / `Avg` 2,267 / `PS` 1,900, or its canonical digest is not `84ea5621…` |
| `OddsTripleIncomplete` | a panel row has a missing or ≤ 1.0 price — the panel imputes nothing and half-uses nothing |
| `ClosingOddsRead` | any closing column (`*C*`) is read anywhere in the anchor path |
| `OddsLeak` | a window row's match date is ≥ its cutoff, or a scored fixture's own odds appear in its own cutoff's window |
| `CutoffLeak` | a fit's training frame holds a match dated ≥ its own cutoff, or a fixture appears in the fit that prices it |
| `PanelOutOfDate` | a cached feature panel's maximum match date is ≥ its cutoff |
| `RecoveryUnstable` | the ridge normal equations are singular, the solve's condition number exceeds 1e10, or the recovered `eta` falls outside **[0.10, 0.70]** |
| `DegenerateStrength` | the cross-club sd of the recovered `s` is ≤ 0 at any cutoff, which would silently zero the whole anchor |
| `CanaryFailed` | `epl.walkforward.point_in_time_canary` returns `PASS: false` (§5.3) |
| `MarketCanaryFailed` | the odds canary fails, in either direction (§5.4) |
| `ControlMismatch` | any of the 681 control probabilities differs from the corpus (§3.2) |
| `GridEscape` | a selected `w` is not on `{0.00, 0.15, 0.30, 0.50, 0.75, 1.00}` |
| `FoldLeak` | a scored season's fixtures appear in that season's own selection fold |
| `FitFailed` | `fit_epl` raises, or health reports a non-finite draw, a non-positive scale parameter, or an implausible `home_adv` |
| `UnpriceableFixture` | a club is absent from the posterior index at its block's cutoff |
| `ScoreMismatch` | Arm B's RPS recomputed from stored probabilities differs from stored `dc_rps` by > 1e-12 |
| `SchemaMismatch` | a ledger row lacks a required field (§5.2) |
| `RowConflict` | two rows share a key and disagree on any non-volatile field |
| `ShardFailed` | a shard process exits non-zero, or writes no rows |
| `MergeIncomplete` | the merged ledger's key set is not exactly the 1,060 pre-stated `(cutoff, w)` fit keys |

**A failed fit poisons its shard, and a failed shard poisons the merge.** A shard
that raises does not write a partial ledger and does not exit 0. The merge takes
the union of shard ledgers **only if every shard exited 0** and the union's key
set equals the expected keys exactly — not a superset, not a subset. **Partial
results never silently merge, and a partial ledger is never scored.** Shards are
waited on **per PID**, never by a bare `wait`, so a failed shard cannot be lost
behind a successful one.

### 5.2 What every fit row records

`cutoff` · `w` · `seed` (20260611) · `config_sha256` · `realised_config_sha256` ·
`odds_panel_sha256` · `n_window_matches` · `eta` · `z_mkt` (per club, 8 dp) ·
`z_blend` (per club, 8 dp) · `n_zero_zmkt_clubs` · `avg_share_of_window` ·
`n_training_matches` · `n_teams` · `wall_seconds` · `match_ids` · `probs` (8 dp)
· `cold_start_teams` · `provisional_teams` · `anchor_spec` · `warnings` ·
`unpriceable` · `health` · `harness_sha256` · `archive_rows` and
`archive_sha256` · `blas_threads` · `shard_id`.

`shard_id` and the clock fields are **recorded but excluded from the canonical
digest** (§5.5): the environment a row was produced in belongs on the record, and
it must not be able to change a number.

### 5.3 The results canary

`epl.walkforward.point_in_time_canary` is run once as a precondition, at its
default cutoff, and its full dict is written into the run artifact. `PASS: false`
is `CanaryFailed` and the run does not start. On the preregistered walk it
returned **max |Δp| = 0.0** with a positive control of **0.811805376021185**.

### 5.4 The odds canary — new, because the existing one cannot see odds

`point_in_time_canary` rewrites **results** from a cutoff onward and demands
identical forecasts. It is blind to the odds panel, so it cannot detect a market
leak. This experiment therefore adds its analogue, and it is a precondition, not
a result:

* **Negative leg.** Replace every panel row whose match date is ≥ the cutoff with
  a corrupted triple (each price multiplied by a fixed perturbation that changes
  the de-vigged vector materially), recompute `z_mkt` and `z_blend`, and demand
  `np.array_equal` against the uncorrupted vectors. Under §2.3 this must hold by
  construction; the canary proves the code implements the rule rather than
  describing it.
* **Positive control.** Corrupt panel rows **before** the cutoff the same way and
  demand `z_blend` **moves** by more than 1e-9. A canary that cannot fail is not
  a canary, and this leg is what makes the negative leg mean something.

Either leg failing is `MarketCanaryFailed` and the run does not start.

### 5.5 Resumability, and what "byte-identical" means here

The runner is **resumable per fit**, keyed by
`cutoff|w|seed|config_sha256|odds_panel_sha256`. A key already in the ledger is
skipped — not re-run, not re-scored, not appended twice.

**A resumed run must produce the same result as an uninterrupted one, and the
demand is made on the canonical form rather than on the raw file**, because a row
records its own wall clock and two runs will never agree on that. Pre-stated now,
before any row exists:

* **Volatile fields**, excluded from the canonical form and from every digest:
  `wall_seconds`, `fit_seconds`, `seconds`, `shard_id`, `started_at`, `host`.
  This is `epl/simretro.py`'s `_VOLATILE` pattern, and the list is fixed here.
* **Canonical form**: rows sorted by `cutoff` then `w` then key, volatile fields
  removed, serialised with `sort_keys=True` and no whitespace variation.
* **`run_digest`**: SHA-256 over the canonical form. **A resumed run's
  `run_digest` must equal an uninterrupted run's, byte for byte**, and the scored
  result written from it must be identical.
* The scoring loader refuses duplicate keys that disagree (`RowConflict`), so
  append order cannot change a number.

---

## 6. What this does not decide, and the hash commit that must follow

**Not decided here, by anything this experiment can produce:**

* **No published-arm change.** `dc_market_prior` is shadow-first, there is no arm
  switch this season, `ISSUANCE_SCHEMA_VERSION` stays `epl-issuance-5`, the
  matchboard schema is untouched, and the published forecast stays `dc_native`'s.
* **No anchor-strength change.** `k_att` and `k_def` stay 0.6, and the 1.2×
  doubling of §0.4 stays exactly as it is. **The question the OA program left
  open — whether the right total anchor strength differs once the anchor's
  direction is market-informed — is a genuine open question, is named here, and
  is NOT answered by this experiment.** Answering it means sweeping `k` jointly
  with `w`, which is a two-dimensional selection surface, a different bar and a
  different document.
* **No decay change.** `decay_half_life_days` stays 365. A market-prior result is
  not evidence about decay in either direction and may not be cited as any.
* **No de-vig selection.** Multiplicative, fixed. Shin is not an alternative
  anchor here and is not swept.
* **Nothing about the shadow challenger.** `dc_1x2_recal` (A8) is untouched: no
  constant is refitted and no row is written to
  `reports/epl_recal_shadow.jsonl`. Both arms here are **raw** `dc`-family
  probabilities. A8's corpus digest is *read*, never rewritten.
* **Nothing about the league-table simulator.** Not the published arm, not D2,
  not D11's thresholds, not D12, not the harness-v5 hash pair, not TRPS, not the
  nulls, not `check`.
* **Nothing about the freshness experiment.** That experiment fits at the **507
  additional match dates**; this one fits at the **212 block openings**. They
  share the corpus and nothing else: this harness does not read, write or depend
  on `data/epl/fit/freshness*`, and freshness's Arm B and this experiment's Arm B
  are the same untouched stored rows. **If freshness adopts a matchday cadence,
  this result still concerns block-opening fits** and would need its own re-run to
  speak to a matchday cadence; the two adoptions are independent rulings.
* **No betting product.** A9 (d), restated: no surface gives betting advice,
  prices, or recommendations, and none is proposed.
* **Where the code and its output may live.** All harness code is under `epl/`.
  The run writes only to `data/epl/fit/` and `reports/epl_anchoring_result.md`.
  It does **not** write `src/`, `scripts/`, `site/`, `tools/`, `.github/`,
  `config/`, the season ledger, `epl/season/points_adjustments.jsonl`,
  `data/epl/sim/retro_r1.jsonl`, `reports/matchboard_scorecard.jsonl`,
  `reports/epl_recal_shadow.jsonl`, `epl/simretro.py`, `epl/simmetrics.py`, or
  the pinned corpus.

**The harness hash commit.** This commit adds this document and a dated
cross-reference at the end of the amendment ledger. **Nothing else. The harness
does not exist.** Following 07b5871's pattern as freshness §6 adapts it:

1. The harness is written and audited.
2. **A follow-up commit adds a hash table to this document** — file, line count
   and SHA-256 for every harness file — and a schema identifier, carrying
   07b5871's own sentence with "either" widened to "any": *if any hash differs at
   the time the run is executed, it is not the run this document preregisters.*
   The same commit freezes the **enumerated fit-point list** — the 1,060
   `(cutoff, w)` pairs and the 2,280 fixtures they price — by digest, recomputed
   from the pinned corpus, so that a run fitting any other set of points is
   identifiably not this experiment. It also freezes the **odds panel digest**
   `84ea5621…` as recomputed by the harness's own reader, so that the panel this
   document measured and the panel the harness builds are provably the same
   object.
3. **Only then does the first fit run.** Not one fit before that commit exists.
4. Any change to a hashed file after that commit requires an amendment in
   `reports/epl_sim_amendments.md` **before** the change, in that file's format
   (observation → ruling → rationale → what is pre-stated), with the hashes
   reissued alongside it.

**On merging, if this ever adopts.** Production wiring for a market prior would
touch `src/` and therefore break the lock chain, which nothing polls and which
refuses silently. Per the house merge-batching rule it lands **batched into the
next lock version**, tested against the lock's code paths before the merge, with
the lock re-verified after. Nothing in this experiment's own harness touches
`src/` or `scripts/` (§2.7), so **the lock is untouched by the run itself** — a
claim to re-check, not to assume, after every commit this work produces.

---

## 7. What would invalidate this preregistration

* **The corpus digest differs** at run time, or its row count, season set,
  outcome counts or block count differ.
* **Any pinned `E0_*.csv` digest differs**, or the odds panel's canonical digest
  is not `84ea5621…`.
* **`epl/config_frozen.json` differs**, or the realised seed is not 20260611, or
  `k_att`/`k_def` are not 0.6.
* **A fit runs before the harness-hash commit of §6 exists**, or a hashed file
  differs at run time without a prior amendment.
* **A closing-odds column is read** anywhere in the anchor path.
* **Odds of a match not yet played enter `z_mkt`** — including a live
  implementation adopted on this backtest that reads the coming round's prices
  (§2.3).
* **`w` is selected on the scored season**, on the pooled corpus, or off the
  pre-stated grid.
* **`M`, `L`, `λ`, the de-vig, `k_att` or `k_def` is tuned** anywhere in this
  experiment.
* **A fixture is dropped** from the 2,280 for any reason. Refusals are reported;
  deletions are amendments.
* **A stratum or a season is excluded** after the run starts.
* **A second seed, a second bootstrap seed, a second B, an extended grid, or a
  second definition of the blocks** is run and reported as if it were this
  experiment.
* **Any threshold or CI condition in §4 moves** after any delta exists.
* **A secondary decides anything** — including a stratum-conditional market
  prior assembled from §3.1.
* **The control's tolerance is widened** after a control row fails.
* **The arm is compared to a closing market**, or any "beats the market" claim is
  made for any arm (§3.4).
* **The result is not published** after a run completes.
* **The pinned corpus is regenerated** by anything in this work.

---

## 8. Standing disclaimers

* **Sampler noise is not model error.** Both are reported; only one of them
  shrinks with more fits, and neither shrinks with a better argument.
* **A prior is not a forecast.** At every `w`, including 1.00, the arm's output
  is a Dixon-Coles fit under a rotated prior, not a market price. §2.5 rules how
  that must be described.
* **The market prior is 91% redundant with the anchor already in the model**
  (§1.4). Whatever this experiment reports, it reports about the remaining
  fraction.
* The posterior is mean-field ADVI at 1,000 draws. Its under-dispersion is a
  known, separately scheduled limitation and no "honest tails" language attaches
  to any number this experiment produces.
* **The estimand is a mean over 2,280 correlated fixtures in 212 blocks and 6
  seasons.** The intervals are percentile block bootstraps, not exact tests, and
  they inherit every assumption that resampling whole ISO weeks — or whole
  seasons, six of them — makes.
* **Six seasons, one league, one model, one configuration, one odds aggregate.**
  Nothing here generalises to another league, another model, another decay
  setting, or another book, and nothing may be quoted as if it does.
* Every RPS in this experiment scores a **1X2 match forecast**. No table
  position, no threshold, and no consequence-ranked quantity appears anywhere in
  it.
* **A9 (d):** this is an input and a diagnostic. It is not a betting product, and
  no language in the result may make it read as one.

---

*Preregistered 2026-08-26, before any line of the market-prior harness existed.
The corpus digest, the odds panel digest, the window statistics, the room
recomputations of §1.4 and §1.5, the nineteen zero-window fixtures, the twenty
control dates and every figure in §0 were computed from the pinned artifacts on
that date and are reproducible from the recipes given beside them. The harness
hashes, the fit-point digest and the panel digest that make "the design was fixed
first" checkable for the run itself arrive in the follow-up commit named in §6,
and no fit runs before it.*

---

## §6 step 2 — the harness-hash freeze (2026-08-26)

The harness named in §6 now exists and has passed the adversarial audit §6
step 1 requires before this note may be written. What the audit found is in
2160766; what it verified is on the record:

* **twelve seeded defects**, each seeded alone into `epl/mktprior.py` and
  demanded red under the file's own tests: the blend losing its z-score (the
  doubled-anchor widening §2.2 (ii) forbids), `z_blend(0)` losing the exact
  identity, the window's cutoff bound made inclusive (§2.3's leak — own-matchday
  odds in), the `OddsLeak` assert silenced, a fold containing its own scored
  season (the partition invariant refuses it), the season-label cross-check
  removed, poison believed on load, a corrupt mid-ledger line believed, the
  shard partition off by one, a merge accepting a **subset** of the pre-stated
  key set, the resume key dropping `w`, and the merge scoring rows stamped
  `harness_frozen: false`. Eleven went red at first pass. The subset-tolerant
  merge stayed green because its test ran the short merge from behind the
  freeze guard and never reached the refusal it names — the guard itself fires
  when reached (`MergeIncomplete: … 1 missing … Not a superset, not a
  subset.`), the **test** was the defect, and 2160766 rewrote it to reach the
  key-set check on the frozen path: red under the same seed, green clean.
* **the leakage clause attacked with constructions** through the public API,
  each refused or excluded per §2.3's exact ruling: a postponed match dated
  after the cutoff and the scored fixture's own cutoff-day row contribute
  nothing (`z_mkt` bit-identical with and without them, max |Δz| = 0.0; the
  earlier meeting of the same clubs legitimately remains); a leaked frame
  forced past the window is `OddsLeak` by name; a source file whose bytes move
  after the pin is `OddsSourceDigestMismatch`; a panel with one price moved is
  `OddsPanelMismatch`; a file offering only closing columns is refused, and a
  closing NAME anywhere in the anchor path is refused by shape.
* **the §5.4 odds canary, re-run on the real panel** at cutoff 2022-10-18:
  negative leg exactly **0.0** across **1,030** corrupted on-or-after rows,
  positive control **4.98**, all five `z_blend` legs identical after the
  cutoff and moving before it, panel digest `84ea5621…`.
* **§3.2's identity control re-run at one date** (2022-10-18, the block of
  18): all **54** recomputed probabilities equal the corpus's stored values
  **exactly** at their 8 decimals, max |ΔRPS| = **0.0**, `read_odds: false`,
  parity lines byte-identical with the implementer's smoke — the `w = 0`
  identity theorem holds and the archive has not drifted. And **one
  `w = 1.00` fit** through the same Engine: `n_window` **129** (the ruled
  window's own median — A10), `eta` **0.3558** inside the pre-stated band,
  `z_blend` unit-sd, movement mean |Δp| **0.0120** against the 0.0032
  seed-replica scale — a real treatment, and no third fit, the freshness
  sweep's compute holding the machine.
* **the gates:** the full `epl/tests` suite green, both lock checks
  `LOCK VALID` (v10) after every commit, `git diff 5ba83e7..HEAD -- src
  scripts site .github tools` empty, `config/config.yaml` untouched with
  `strength_prior.source` re-verified inert, every protected file untouched,
  the coupled ledger tests green after each ledger append, and a secret scan
  over every commit since 5ba83e7 clean against a working positive control.

These are the bytes:

| File | Lines | SHA-256 |
|---|---:|---|
| `epl/mktprior.py` | 3230 | `8f214d16bd41c7b6e38a62fa3ddb3941ee219dd67f6357e2b8474d3053b1aba3` |
| `epl/tests/test_mktprior.py` | 1313 | `923d5fb390b8eecd59233052143e98de4c93fa52c11570a5e22183fd13c18746` |

Schema identifier: `epl-market-prior-1`. (`epl/oddscapture.py` is deliberately
not a §6 harness file: it is not wired into `epl.mktprior` and changes no
backtest number — ced09da.)

**The enumerated fit-point list is frozen with the harness.** The 1,060
`(cutoff, w)` pairs, recomputed from the pinned corpus by `grid_points` under
§0.1's binding counts and serialised in `(cutoff, w)` order as `;`-joined
`{cutoff}|{w:.2f}` (`fit_point_digest`), hash to:

    0f28ab2d64db241b8f16f79e9149ea2b79882e3984a2052ac02cc4d8b788e5e2

The 2,280 fixtures each weight prices are the corpus's own block rows, frozen
transitively by the corpus digest `f31580073e…` and enforced at 212 blocks /
2,280 fixtures by `CorpusShapeMismatch`. A run that fits any other set of
points is not this experiment.

**The odds panel digest is frozen as recomputed by the harness's own reader.**
`build_panel()` over the eleven pinned `E0_*.csv` reproduces 4,167 rows /
`Avg` 2,267 / `PS` 1,900 and the canonical digest §0.3 measured —
`84ea5621e1aaa45bd43c3063897d79525103ae74dd51eb071b777bae9618235c` — so the
panel this document measured and the panel the harness builds are provably the
same object.

**Two deviations, recorded rather than smoothed over.**

1. §2.1's published sanity trios were measured under a per-venue window the
   section does not rule. **A10** corrects the record before this freeze: the
   venue-blind definition binds, the harness computes it, and both trios are
   pinned in code as `MEASURED_*` / `DOCUMENTED_*` with a test asserting each.
2. §5.5 states the resume key as `cutoff|w|seed|config_sha256|odds_panel_sha256`;
   the implemented key is `cutoff|w|seed|config_sha256`. The fifth component is
   enforced as a precondition instead of in the key: `OddsPanelMismatch`
   refuses any panel that is not the pinned one before a fit runs, and
   `panel_sha256` sits on every row outside the volatile set, so `RowConflict`
   refuses a disagreement. Within any run this document permits, the omitted
   component is a constant; a run under a different panel is refused before it
   fits, not resumed past.

Verify with:

    shasum -a 256 epl/mktprior.py epl/tests/test_mktprior.py

**If any hash differs at the time the run is executed, it is not the run this
document preregisters.** Any change to a hashed file after this commit requires
an amendment in `reports/epl_sim_amendments.md` **before** the change, in that
file's format, with the hashes reissued alongside it (§6 step 4). §6 step 3 now
applies: only after this commit does the first fit run — and the run itself
queues behind the freshness sweep's compute, per the standing machine
constraint.

---

## §6 step 4 — dated re-freeze: two code defects, one latent (2026-08-26)

**Appended, not edited.** Everything above stands as written and as committed;
this note corrects it by addition.

### (a) The archive digest bound nothing

`Engine._archive_digest` asked for `("match_id", "date", "home_score",
"away_score")` and kept only the columns it found. This schema names the scores
**`fthg`/`ftag`** (`epl/schema.py`), so both were dropped silently and the
digest covered **`match_id` and `date` alone**. `archive_sha256` is on all
11,400 ledger rows to witness *"was the results archive the same object when
this fit ran?"*, and about the scores it witnessed nothing. Demonstrated on a
three-row frame whose first match moves from 2-1 to 3-1:

    columns actually digested: ['match_id', 'date']
    before = 1df0eaf34c449165…   after = 1df0eaf34c449165…   UNCHANGED = True

This does **not** reopen the estimand: `archive_rows` (4,560) rode every row,
§3.2's `w = 0` control held exact 8-decimal equality against the pinned corpus,
and the corpus digest `f31580073e…` binds the fixtures. What was absent was the
independent per-row witness the field advertised. Fixed as a module-level
`archive_digest(played)` over `ARCHIVE_DIGEST_COLUMNS = ("match_id", "date",
"fthg", "ftag")`, with a missing column now raising `SchemaMismatch` rather
than narrowing the digest in silence. Rows already written carry the old
`ce7e4255…`; they are historical and are not rewritten.

### (b) `w = 0` was a disappearance, not a selection — latent, and it never fired

§2.4 puts `w = 0.00` on the grid and spends **no fits** on it, because
`z_blend(0)` IS `elo_z` and the corpus already holds that row. So the ledger
contains **no `w = 0.00` rows at all** — 11,400 = 2,280 × the five *fitted*
weights. `estimand()` knew this and synthesised the pair (Arm A is Arm B, delta
exactly `0.0`). The **predictions writer's call site did not**: it filtered
`float(r["w"]) == selected[season]` against that same ledger, so a season the
selection priced at zero contributed **nothing** to
`dc_market_prior_predictions.parquet` — no row, no warning, no refusal.

Proven on a synthetic six-season corpus with one season selected at `w = 0`:

    corpus fixtures                : 24
    LEGACY predictions rows written: 20
    fixtures of the w=0 season     : 4
    of those, present in LEGACY    : 0
    RED PROOF: predictions silently short by 4 rows

**It never fired in the run this document preregisters.** `anchoring.json`
records `n_folds_at_zero: 0` and `folds_at_zero: []` — no fold chose zero, so
all 2,280 fixtures are present in the committed parquet (`da685cf4…`, 2,280
rows). The defect was latent. It is reported because a latent defect in the
file §2.6 names is still a defect in the file §2.6 names, and the next run's
selection is not this run's.

**The fix removes the duplication that caused it.** The selected set is now
built in exactly one place — `pick_at_selected_weights(rows, selection)` —
which both `estimand()` and the predictions writer call, so the estimand's
population and the predictions file's population are the same object by
construction rather than by coincidence. Tests, RED before the change:
`test_a_season_selected_at_w_zero_still_emits_its_predictions_rows` and
`test_the_estimand_and_the_predictions_file_price_the_same_rows`.

### The bytes are reissued (§6 step 4)

The run this document preregisters is complete; the freeze is re-cut for
whatever runs next, not retroactively loosened for what already ran.

| File | Lines | SHA-256 |
|---|---:|---|
| `epl/mktprior.py` | 3276 | `edfcd9842bbd7b877e973f9ba0b0d666e6ea0e70d231afde2ab20ca9cedbeda4` |
| `epl/tests/test_mktprior.py` | 1416 | `2b1dd4d4db1c02c0a1395181076331693eecf466005b9502bdb96bc5c70e8646` |

Superseded: `8f214d16bd…` / `923d5fb390…`. Verify with

    shasum -a 256 epl/mktprior.py epl/tests/test_mktprior.py

Any further change to a hashed file requires a further note here before it.
