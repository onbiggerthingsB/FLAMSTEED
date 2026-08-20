# EPL table simulator — the first `dc_native` 2026/27 issuance, cutoff 2026-08-21

**Season:** 2026/27 · **Cutoff:** 2026-08-21 (the season opener; zero fixtures played)
**Published arm:** `dc_native` · **Arms run:** `dc_native`, `dc_wdl_bridge`, `elo_wdl_bridge`
**Branch:** `epl-probe` · **Date:** 2026-08-19
**Acceptance gate: PASS — 0 failed, 0 skipped, 11 of 11 criteria ran and held.**

This is the first issuance in which the model arm actually ran. The previous
attempt ([`reports/epl_sim_first_issuance.md`](epl_sim_first_issuance.md)) failed
closed on the D11 truncation guard; the owner's ruling of 2026-08-19, recorded as
amendment **A1** in [`reports/epl_sim_amendments.md`](epl_sim_amendments.md)
*before* the guard was touched and *before* any `dc_native` number existed,
changed the 5e-3 threshold from a hard stop to a flag and pre-stated a 2e-2 hard
ceiling. This run is the first result produced under **D11 v1.0.1**.

Everything below is a **forecast**, conditional on current strengths staying fixed
for the rest of the season. Every percentage carries a Monte-Carlo standard error.
**Monte-Carlo error is not model error**: a tight SE on a badly specified model is
still a badly specified model. Positions are positions — "top 4", "top 5" and
"top 7" are table positions and are not claims about qualification for any
competition. There is no betting content anywhere in this report: no odds, no
market comparison, no stake.

---

## 1. Provenance

| | |
|---|---|
| Commit (envelope `git_commit`) | `1aa24772f1d60124378fbdf4856bcb452b4eb6e2`, `git_dirty = false` |
| Rule under which it ran | **D11 v1.0.1**, amendment **A1** (`reports/epl_sim_amendments.md`) |
| N (simulated seasons) | **20,000** |
| S (posterior draws) | **1,000**, each used exactly 20 times (min = max = 20) |
| Seed · chunk size | **20260611** · **2,000** (10 chunks) |
| `effective_posterior_hash` | `b87c4a17cd4ce867a6e92447d214ba3454dcc3376c2da85b85dbc09862cb1b61` |
| Bridge hash (the two bridge arms) | `cb1597eeb6d4f75a5113afd046223771434a62401f19783a63cb67f7a67fea0f` |
| Numbers digest, `dc_native` | `922040b234c3516bc5bd930dfd7c9077e93ae11a0275f0888d83ae2e7f8dfc9b` |
| Run digest, `dc_native` | `3a40110cd41286c42125322b9f90f36387d27e5d212992426eb78a2de0b3eb8a` |
| Tiebreak rule id | `PL-2026-27:C4-C7+C17;material={1|2,4|5,5|6,6|7,7|8,17|18};h2h_away=original_set;unresolved=fractional;v1` |
| Manifest / fixtures / frozen-config sha256 | `bfbf6050…`, `ec7f37c9…`, `9f2e086d…` |
| Elo anchor spec | `epl.elo/carryover=1/debut_offset=0/home_advantage=40/initial_rating=1500/k=20/mov=False/mov_autocorr=0.006/mov_base=7.5/mov_shape=0.8/promoted_offset=-75` |
| `max_goals` | **10** — unchanged, parity with the issued per-fixture forecasts (A1 (a)) |
| Widening mode | `per_fixture_bernoulli@alpha=0.5` |
| Environment | Python 3.12.13 · numpy 2.4.6 · scipy 1.17.1 · PyMC 6.0.1 · arviz 1.1.0 · macOS arm64 |
| RNG | `PCG64@numpy-2.4.6`, streams keyed `SeedSequence(seed, spawn_key=(chunk_index, fixture_ordinal))/v1` |

**The fit.** 35 fitted teams, 4,560 training matches, ADVI average loss 1,534.1,
fit 7.59 s. Cold start: **`coventry`** only (no match anywhere in the
2014/15–2025/26 archive), seeded at promoted rating **1519.61**, cold-start
z = 0.0429. `n_live_rows_visible = 0` — the season's results ledger is empty at
the opener, so the fit store is archive-only and the point-in-time path is
degenerate by construction here, not by shortcut.

**State of the season.** 0 played, 380 simulated, 0 unresolved, `results_lag = false`,
no points adjustments. Whole issuance 45.05 s wall (`dc_native` arm 1.44 s).

**Written to** `data/epl/sim/issuances/2026_27/2026-08-21/` (gitignored, as all of
`data/` is). The earlier `elo_wdl_bridge`-only demonstration remains untouched
under `data/epl/sim/issuances_partial/` as the historical record of the failed
attempt.

**Independently re-checked.** `simcli check` re-ran the published arm from the
issuance's own bundle and reproduced the number digest exactly:

```
recorded    922040b234c3516bc5bd930dfd7c9077e93ae11a0275f0888d83ae2e7f8dfc9b
recomputed  922040b234c3516bc5bd930dfd7c9077e93ae11a0275f0888d83ae2e7f8dfc9b
book hash   b87c4a17… == b87c4a17…      coherence PASS      parity PASS
```

---

## 2. The acceptance gate — eleven criteria

Run on the published arm, `dc_native`, through that arm's own provider. Full
record: `data/epl/sim/issuances/2026_27/2026-08-21/acceptance.json`.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `clubs_and_fixtures` | **PASS** | 20 clubs, 380 fixtures, complete double round-robin, played ∪ unplayed covers the fixture set |
| 2 | `promoted_complete` | **PASS** | Coventry / Hull / Ipswich each 38 fixtures, matrix rows sum to 1.0; expected relegations among the promoted **1.9672** (§5) |
| 3 | `marginal_parity` | **PASS** | 380 fixtures, 14,225 cells compared at ≥25 expected count; worst deviation **3.865σ** against the 4σ criterion; 0 failures |
| 4 | `tiebreak_oracle` | **PASS** | `pytest epl/tests/test_table.py -q` as a subprocess: 24 passed, returncode 0 |
| 5 | `cutoff_table` | **PASS** | Opener is degenerate (0 played), so a witness was run: 2025/26 at 2026-01-01, **186 played**, 516 points, zero mismatches; `non_degenerate_anywhere = true` |
| 6 | `matrix_and_markets` | **PASS** | Row/col max error 2.2e-16 / 4.4e-16; every consequence market equals its column sum to **0.0** (champion 1, top4 4, top5 5, top7 7, relegated 3); all per-sim identities hold |
| 7 | `serial_equals_chunked` | **PASS** | Deterministic ✓, 10-chunk concatenation ✓, 2-process parallel ✓, seed control moved the digest ✓ |
| 8 | `mc_uncertainty` | **PASS** | Every club × market carries finite `p`/`se`/`outer`/`inner`; worst market SE **0.01167**; outer/inner identity error 2.7e-20 |
| 9 | `limitations` | **PASS** | All six sections present including the new "Truncation-flagged fixtures"; the run's own numbers and rule id found in the text |
| 10 | `src_scripts_untouched` | **PASS** | `git diff --stat main -- src scripts` empty |
| 11 | `lock_valid` | **PASS** | `scripts/oa_lock.py` first line `LOCK VALID` |

**Verdict: PASS.** Criterion 3, `marginal_parity`, is the one the blocked run
could never supply — it is only defined for the DC-native arm, and it is the check
that the simulated per-fixture scoreline marginals *are* the published per-fixture
forecast rather than merely resembling it. It now has an answer, and the answer is
yes at the preregistered 4σ. Its headroom is thin: the worst of 14,225 cells sits
at 3.865σ, on `2627:man_united:liverpool`. That is close to what noise alone
would produce: the expected largest |Z| among 14,225 independent standard normals
is **4.1014** (quadrature on `1 − (2Φ(x) − 1)^m`, absolute error 3.2e-08; median
of the maximum 4.0617), so a worst cell at 3.87 is unremarkable rather than a
near-miss. It is nevertheless the first number to watch on the next issuance,
because a criterion this close to its own noise floor has little room to absorb a
real defect.

**[SE-1] — 2026-08-20 correction note (Codex review of ce82484 #2).** The two
`±` figures marked above — the 90.03% ± 0.37 title-race concentration and the
11.34% ± 0.25 / 4.42% ± 0.15 boundary shares — were ADDED to this report after
it was issued, in the commit that corrected the arithmetic elsewhere on this
page, and were not marked as post-issuance edits at the time. The arithmetic
corrections on this page carry dated notes and these insertions did not, which
weakens the audit trail this file exists to provide. Recorded here rather than
silently: nothing that was published was changed by them — each is a
Monte-Carlo standard error attached to a probability that was already in the
report, computed from the same 20,000 retained rows and 1,000 particles as
every other figure, and no probability, verdict or gate outcome moved. The rule
this note restores is that every edit to an ISSUED report is dated in the report
itself.

**2026-08-19 correction.** This paragraph previously gave that quantity as
**about 3.98** and drew from it the further conclusion that 3.98 is "the honest
reading of why the criterion is set at 4σ". Both are wrong. 3.9753 is
`Φ⁻¹(1 − 1/(2m))` — the point at which the EXPECTED NUMBER of exceedances is one
— which is neither the mean nor the median of the maximum. The error was small in
size and unhelpful in direction: it understated the noise floor being invoked and
so made the 4σ rule look better calibrated than it is. The 4σ rule is not well
calibrated at this m. At m = 14,225 the two-sided normal tail at 4σ is 6.334e-05,
which is 0.9010 expected exceedances and

```
P(at least one cell beyond 4σ) = 1 − (1 − 6.334e-05)^14225 = 0.5939   [IID REFERENCE]
```

**2026-08-20 relabelling (Codex review of ce82484 #1).** 0.5939 is the IID
REFERENCE for m = 14,225 cells, and is **not** the established failure
probability of a correct sampler under this gate. The product form assumes the
cells are independent, and `epl/simcanary.py` documents that they are not:
within a fixture the scoreline cells are multinomial, the home/draw/away triple
is a linear combination of cells already counted, and every `Z` divides by an
ESTIMATED, floored `max(cluster, binomial)` standard error rather than by a
known one — so the marginal normality the tail assumes is itself an
approximation. Under dependence the true exceedance probability can sit either
side of 0.5939, and it has not been computed. The sentence below is therefore a
statement about the iid arithmetic, not a measurement of the sampler; the same
relabelling is recorded as the ledger entry **A3-N1**, which also demotes A3's
leg 2 to an uncalibrated diagnostic. The 0.9010 expected-exceedance figure above
is exact under marginal normality (an expectation is linear and needs no
independence) and is not relabelled.

— under that iid reference, **a correct sampler would fail criterion 3 about
three runs in five.** That is the
subject of amendment **A3** (`reports/epl_sim_amendments.md`), which replaces the
fixed per-cell 4σ with a family-wise `z* = Φ⁻¹(1 − α/(2m))` at α = 0.01 (`z* =
4.9605` at this m) plus a global χ² leg, and which was recorded before the code
that implements it. **This issuance is not re-gated**: it passed under the rule
preregistered for it, and its worst cell clears A3's leg 1 by 1.096σ as well.
Every figure above is arithmetic on the normal distribution and carries no
Monte-Carlo error of its own; 3.865σ is quoted from this run's own acceptance
record.

---

## 3. Truncation-flagged fixtures (D11 v1.0.1)

Under amendment A1 the 5e-3 excluded-mass number is a **flag**, not a stop, and
the per-fixture excluded mass is recorded for **all** 380 simulated fixtures — not
only the flagged ones — in the envelope and in the sidecar
`excluded_mass_dc_native.json`.

**Whole-run record (`dc_native` and `dc_wdl_bridge`, identical because both reduce
the same grids):**

| | |
|---|---|
| Fixtures measured | **380** |
| Max particle-mean excluded mass | **0.005365** |
| Mean over all 380 | **0.0001547** |
| 90th percentile | **0.0003456** |
| Flagged (> 5e-3) | **1** |
| Hard ceiling (2e-2, pre-stated in A1) | **not approached** — the worst fixture is at 27% of it |

**Flagged fixtures — one, as expected:**

| Fixture | Particle-mean | Median particle | Worst particle | Particles > 1% (of 1,000) |
|---|---:|---:|---:|---:|
| `2627:man_city:coventry` | **0.005365** | 0.0001925 | 0.4484 | **88** |

Next worst, none of them flagged: `2627:arsenal:coventry` 0.003934,
`2627:liverpool:coventry` 0.003426, `2627:man_city:hull` 0.003284,
`2627:arsenal:hull` 0.002419, `2627:man_city:ipswich` 0.002137. Every fixture near
the top of the list pairs a strong home side with a promoted club.

**Production truncates at the same 10 goals and discards the same tail silently.**
The per-fixture forecast this project already publishes renormalises over exactly
the same grid, so this issuance is not discarding anything production keeps — it
is reporting what production does not report. The four numbers are given together
deliberately: the mean is 0.0054 while the median particle is 0.00019, **28 times
smaller — 1.45 orders of magnitude**, not four — so the tail is concentrated in a
handful of cold-start draws and not a uniform property of the fixture.

**2026-08-19 correction.** This sentence previously read "four orders of magnitude
smaller". `0.005365 / 0.0001925 = 27.87`, which is `log10(27.87) = 1.445` orders.
The point it was making survives the correction — the failing fixture's typical
particle is nowhere near the gate and a handful of extreme particles carry the
mean, which the worst-10 line below quantifies directly — but it was overstated by
two and a half orders of magnitude. The same error, in the same words, is
corrected for the first-issuance report in
[`epl_sim_first_issuance.md`](epl_sim_first_issuance.md) and in amendment A1-C1.
No excluded-mass number changes. Its cause is that Coventry has zero
archive rows, so its attack and defence are prior draws; a few draws put Coventry's
defence near −1.1, which against Man City's attack gives a home rate above 10 and
loses 25–45% of *that particle's* mass past the truncation. This is expected to
collapse once Coventry has fitted rows.

`elo_wdl_bridge` reports `measured = false`, `n_fixtures = 0` — it never touches
the particle grids, so it has no truncation tail to report, and it says so rather
than reporting a zero that would read as "measured, and it was zero".

---

## 4. The forecast — `dc_native`, all 20 clubs

N = 20,000 seasons over S = 1,000 posterior draws. `±` is one cluster-by-particle
Monte-Carlo standard error, in percentage points for probabilities and in points
for E[points]. Ordered by E[points].

| Club | P(champion) | P(top 4) | P(top 5) | P(relegated) | E[points] | sd | 5% | 50% | 95% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| arsenal | **49.46% ± 0.79** | 96.72% ± 0.21 | 98.46% ± 0.14 | 0.00% ± 0.00 | **81.75 ± 0.16** | 8.58 | 67 | 82 | 95 |
| man_city | **40.57% ± 0.77** | 94.87% ± 0.31 | 97.21% ± 0.21 | 0.00% ± 0.00 | **80.12 ± 0.17** | 8.78 | 65 | 80 | 94 |
| liverpool | **6.23% ± 0.30** | 63.63% ± 0.76 | 74.10% ± 0.69 | 0.08% ± 0.02 | **68.13 ± 0.19** | 9.49 | 52 | 68 | 84 |
| man_united | 0.97% ± 0.09 | 26.67% ± 0.70 | 38.27% ± 0.79 | 0.92% ± 0.12 | 59.24 ± 0.20 | 9.69 | 43 | 59 | 75 |
| aston_villa | 0.67% ± 0.07 | 21.73% ± 0.61 | 32.15% ± 0.72 | 1.24% ± 0.11 | 57.88 ± 0.19 | 9.58 | 42 | 58 | 74 |
| chelsea | 0.43% ± 0.06 | 16.80% ± 0.55 | 26.02% ± 0.68 | 1.92% ± 0.15 | 56.22 ± 0.19 | 9.61 | 40 | 56 | 72 |
| newcastle | 0.41% ± 0.06 | 16.30% ± 0.53 | 25.44% ± 0.66 | 2.05% ± 0.17 | 55.97 ± 0.19 | 9.53 | 40 | 56 | 72 |
| bournemouth | 0.33% ± 0.05 | 13.01% ± 0.50 | 20.95% ± 0.64 | 3.05% ± 0.20 | 54.44 ± 0.20 | 9.68 | 38 | 54 | 70 |
| brighton | 0.22% ± 0.04 | 11.58% ± 0.46 | 19.10% ± 0.61 | 3.50% ± 0.24 | 53.79 ± 0.20 | 9.73 | 38 | 54 | 70 |
| brentford | 0.29% ± 0.05 | 10.84% ± 0.45 | 18.01% ± 0.59 | 4.23% ± 0.27 | 53.29 ± 0.20 | 9.82 | 37 | 53 | 69 |
| nottm_forest | 0.08% ± 0.02 | 6.09% ± 0.34 | 10.17% ± 0.46 | 7.14% ± 0.35 | 49.95 ± 0.20 | 9.63 | 34 | 50 | 66 |
| fulham | 0.07% ± 0.02 | 4.22% ± 0.24 | 7.86% ± 0.36 | 9.34% ± 0.41 | 48.60 ± 0.19 | 9.56 | 33 | 48 | 65 |
| sunderland | 0.10% ± 0.04 | 4.69% ± 0.32 | 7.94% ± 0.44 | 12.85% ± 0.54 | 47.60 ± 0.23 | 10.19 | 31 | 47 | 65 |
| everton | 0.02% ± 0.01 | 2.96% ± 0.19 | 5.80% ± 0.28 | 11.28% ± 0.45 | 47.26 ± 0.18 | 9.31 | 32 | 47 | 63 |
| crystal_palace | 0.02% ± 0.01 | 2.36% ± 0.16 | 4.70% ± 0.26 | 13.11% ± 0.51 | 46.29 ± 0.18 | 9.27 | 31 | 46 | 62 |
| leeds | 0.02% ± 0.01 | 3.16% ± 0.24 | 5.96% ± 0.36 | 16.42% ± 0.62 | 45.90 ± 0.22 | 10.19 | 30 | 46 | 63 |
| tottenham | 0.02% ± 0.01 | 1.98% ± 0.15 | 4.00% ± 0.24 | 16.17% ± 0.55 | 45.38 ± 0.18 | 9.32 | 30 | 45 | 61 |
| coventry | 0.00% ± 0.00 | 0.19% ± 0.04 | 0.49% ± 0.07 | **55.77% ± 0.87** | 35.42 ± 0.20 | 9.52 | 21 | 35 | 52 |
| hull | 0.11% ± 0.04 | 2.15% ± 0.29 | 3.30% ± 0.37 | **58.71% ± 1.17** | 33.79 ± 0.39 | 14.11 | 12 | 33 | 58 |
| ipswich | 0.00% ± 0.00 | 0.04% ± 0.02 | 0.11% ± 0.03 | **82.24% ± 0.74** | 27.48 ± 0.23 | 9.55 | 13 | 27 | 44 |

Coventry's and Ipswich's `0.00% ± 0.00` for champion are hard zeros: neither won
the title in any of the 20,000 simulated seasons. That is a statement about 20,000
seasons, not a claim that the probability is zero.

**Column sums, exactly as the coherence check found them:** champion 1.000000,
top 4 4.000000, top 5 5.000000, top 7 7.000000, relegated 3.000000 — each equal to
its column sum to 0.0.

**Two things worth looking at rather than taking on trust.**

*Hull.* Its E[points] standard deviation across simulated seasons is **14.11**,
against 8.6–10.2 for every other club, and its 5–95% points band is 12–58, **46 points wide**, where
the next widest is sunderland's 31–65 at 34 and the median club sits at 32. It also carries a **higher** title probability
(0.11% ± 0.04) than seven established clubs including Tottenham (0.02% ± 0.01).
This is posterior *width*, not posterior *mean*: Hull is a fitted club, but its
Premier League rows in the 2014/15–2025/26 archive are old and few, so its
attack/defence posterior is far more diffuse than a continuously present club's.
The DC arm draws one joint parameter set per simulated season (D1), so a wide
posterior produces both an unusually long tail up and an unusually long tail down.
It is the model doing what it is specified to do; whether the width is *right* is
a question the retrospective has not yet been asked.

*Concentration.* Arsenal 49.46% ± 0.79 and Man City 40.57% ± 0.77 is a two-club
title race carrying **90.03% ± 0.37** of the mass (percentage points, one
cluster-by-particle Monte-Carlo standard error).<sup>[SE-1]</sup> The sum's error is SMALLER than
either club's, not the quadrature sum of the two: the pair are strongly negatively
correlated by construction, since a season in which one of them is champion is a
season in which the other is not. The DC arm is visibly **less** concentrated
than the Elo comparator at the very top (58.34% ± 0.35 vs 49.46% ± 0.79 for
Arsenal) — which is the
direction the parameter-uncertainty argument predicts — and its relegation
probabilities for the promoted clubs are visibly **more** extreme. Both are in §6.

---

## 5. Cut lines

Points totals at each material boundary, read off the simulated seasons
(`dc_native`).

| Line | 5% | 10% | 25% | 50% | 75% | 90% | 95% |
|---|---:|---:|---:|---:|---:|---:|---:|
| champion | 76 | 78 | 82 | **86** | 91 | 95 | 97 |
| 4th place | 61 | 62 | 64 | **67** | 70 | 72 | 74 |
| 5th place | 58 | 60 | 61 | **64** | 66 | 68 | 69 |
| 17th place | 32 | 34 | 36 | **38** | 40 | 42 | 43 |
| 18th place | 27 | 29 | 32 | **34** | 37 | 39 | 40 |

**Promoted clubs and the sanity band.** Expected relegations among the three
promoted clubs (Coventry, Hull, Ipswich), recomputed from the retained per-season
rows and agreeing with the recorded per-club probabilities to five decimal places:

| Arm | Expected relegations among the promoted | In the 0.9–2.0 band? |
|---|---:|---|
| `dc_native` (published) | **1.9672 ± 0.0133** | yes — but 2.5 MC SE below the ceiling |
| `dc_wdl_bridge` | 1.9489 ± 0.0132 | yes |
| `elo_wdl_bridge` | 1.4014 ± 0.0051 | yes, comfortably |

The published arm sits close to the top of the preregistered band. The band is a
sanity check on the cold-start path, not a calibration target, and the criterion
passes — but "1.97 of 3 promoted clubs go straight back down" is the sharpest
structural claim in this issuance and it is worth naming as such. The Elo
comparator, which carries no parameter uncertainty and no cold-start posterior,
puts it at 1.40.

---

## 6. The three arms side by side

All three arms ran on the same fixtures, the same cutoff, the same seed and the
same engine. They differ only in the law that gives a fixture its scoreline
distribution.

**`elo_wdl_bridge` carries no parameter uncertainty by construction**: it is static
frozen-Elo ratings at the cutoff plus an ordered-logit head fitted on pre-cutoff
history plus the empirical P(scoreline | outcome) bridge, with no posterior to draw
from. Its outer (posterior-sampling) Monte-Carlo variance is
**1.792e-05 for `dc_native` against 2.161e-09 for `elo_wdl_bridge`** — nearly four
orders of magnitude — which is exactly the leg that a no-parameter-uncertainty arm
does not have. Its tails are therefore narrower than the model's, and its standard
errors are correspondingly smaller for reasons that are **not** evidence it is
better determined.

### P(champion)

| Club | `dc_native` (published) | `dc_wdl_bridge` | `elo_wdl_bridge` |
|---|---:|---:|---:|
| arsenal | **49.46% ± 0.79** | 49.78% ± 0.79 | 58.34% ± 0.35 |
| man_city | **40.57% ± 0.77** | 40.25% ± 0.77 | 36.10% ± 0.34 |
| liverpool | **6.23% ± 0.30** | 6.08% ± 0.30 | 2.03% ± 0.10 |
| man_united | 0.97% ± 0.09 | 1.08% ± 0.10 | 1.90% ± 0.09 |
| aston_villa | 0.67% ± 0.07 | 0.72% ± 0.09 | 0.96% ± 0.07 |
| chelsea | 0.43% ± 0.06 | 0.39% ± 0.06 | 0.07% ± 0.02 |
| newcastle | 0.41% ± 0.06 | 0.38% ± 0.06 | 0.01% ± 0.01 |
| bournemouth | 0.33% ± 0.05 | 0.34% ± 0.05 | 0.42% ± 0.05 |
| brentford | 0.29% ± 0.05 | 0.22% ± 0.03 | 0.06% ± 0.02 |
| brighton | 0.22% ± 0.04 | 0.22% ± 0.04 | 0.08% ± 0.02 |
| hull | 0.11% ± 0.04 | 0.14% ± 0.04 | 0.00% ± 0.00 |
| sunderland | 0.10% ± 0.04 | 0.16% ± 0.04 | 0.02% ± 0.01 |
| nottm_forest | 0.08% ± 0.02 | 0.08% ± 0.02 | 0.01% ± 0.00 |
| fulham | 0.07% ± 0.02 | 0.06% ± 0.02 | 0.01% ± 0.01 |
| everton | 0.02% ± 0.01 | 0.02% ± 0.01 | 0.01% ± 0.01 |
| leeds | 0.02% ± 0.01 | 0.07% ± 0.02 | 0.01% ± 0.00 |
| tottenham | 0.02% ± 0.01 | 0.02% ± 0.01 | 0.00% ± 0.00 |
| crystal_palace | 0.02% ± 0.01 | 0.03% ± 0.01 | 0.00% ± 0.00 |
| coventry | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.01% ± 0.00 |
| ipswich | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 |

### P(relegated)

| Club | `dc_native` (published) | `dc_wdl_bridge` | `elo_wdl_bridge` |
|---|---:|---:|---:|
| ipswich | **82.24% ± 0.74** | 81.51% ± 0.75 | 46.13% ± 0.36 |
| hull | **58.71% ± 1.17** | 58.42% ± 1.17 | 46.62% ± 0.36 |
| coventry | **55.77% ± 0.87** | 54.97% ± 0.86 | 47.39% ± 0.36 |
| leeds | 16.42% ± 0.62 | 16.46% ± 0.62 | 15.75% ± 0.26 |
| tottenham | 16.17% ± 0.55 | 15.96% ± 0.55 | **53.83% ± 0.37** |
| crystal_palace | 13.11% ± 0.51 | 13.66% ± 0.51 | 17.55% ± 0.28 |
| sunderland | 12.85% ± 0.54 | 12.81% ± 0.52 | 12.22% ± 0.24 |
| everton | 11.28% ± 0.45 | 11.24% ± 0.43 | 15.39% ± 0.25 |
| fulham | 9.34% ± 0.41 | 9.88% ± 0.43 | 11.02% ± 0.22 |
| nottm_forest | 7.14% ± 0.35 | 7.54% ± 0.37 | 12.84% ± 0.23 |
| brentford | 4.23% ± 0.27 | 4.09% ± 0.25 | 5.12% ± 0.16 |
| brighton | 3.50% ± 0.24 | 3.60% ± 0.23 | 3.63% ± 0.13 |
| bournemouth | 3.05% ± 0.20 | 3.11% ± 0.21 | 0.70% ± 0.06 |
| newcastle | 2.05% ± 0.17 | 2.28% ± 0.18 | 7.25% ± 0.18 |
| chelsea | 1.92% ± 0.15 | 1.99% ± 0.15 | 4.22% ± 0.14 |
| aston_villa | 1.24% ± 0.11 | 1.41% ± 0.12 | 0.22% ± 0.03 |
| man_united | 0.92% ± 0.12 | 1.03% ± 0.11 | 0.06% ± 0.02 |
| liverpool | 0.08% ± 0.02 | 0.07% ± 0.02 | 0.08% ± 0.02 |
| arsenal | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 |
| man_city | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 |

**What the comparison shows.** `dc_native` and `dc_wdl_bridge` agree closely
everywhere — they share the same per-fixture outcome marginal by construction
(D18), so this is a consistency check on the bridge rather than an independent
opinion, and it is the check passing. The genuinely different arm is
`elo_wdl_bridge`, and the two headline disagreements are:

- **Tottenham.** The Elo comparator has Tottenham at 53.83% ± 0.37 to be relegated
  — above all three promoted clubs — while the model has it at 16.17% ± 0.55, 5th
  most likely. That is the frozen Elo table talking, through a head with no
  parameter uncertainty, and it disagrees with the model by more than 37
  percentage points. Whichever is right, they cannot both be.
- **The promoted clubs.** The model separates them (82 / 59 / 56) and the Elo arm
  does not (46 / 47 / 47). The model's separation comes from the Dixon-Coles fit
  and, for Coventry, from the cold-start prior; the Elo arm's flatness comes from
  all three sharing the same `promoted_offset = -75` seed.

Neither disagreement has been adjudicated. Nothing in this issuance says which arm
is more accurate — that is what the retrospective is for, and it has not run.

---

## 7. Ties the rulebook does not decide

`dc_native`, per club per simulated season:

| | |
|---|---|
| `unresolved_playoff_mass` (two clubs level on a material boundary, no play-off model) | **0.00003 per club** (0.0006 total across 20 clubs; 10 clubs carry any at all, max 0.0001) |
| `unresolved_multiway_mass` (three or more clubs level; the Handbook has no rule) | **0.00000** — exactly zero |
| Shared-position rate | 0.000375 |
| Mean shared positions per simulated season | 0.007 |

How positions were actually settled, over all 20 rungs: 73.34% unique on points
alone, 25.35% on goal difference, 1.25% on goals scored, 0.0125% on head-to-head
points, 0.0345% shared on a non-material rung, 0.004% on head-to-head away goals,
0.003% left to the play-off convention, 0.0% three-or-more-way. These eight shares
sum to 1.000000.

At the two boundaries that matter most. These are shares of the same 20,000
simulated seasons, recorded by the run itself; as a check on their scale, the
title boundary's non-points share reproduces independently from the retained
per-season rows as **4.42% ± 0.15** against the 4.425% recorded below. The
relegation boundary's decomposition was not independently reconstructed, so no
standard error is quoted for it.

| Boundary | UNIQUE | GD | GF | H2H pts | H2H away | play-off | 3+-way |
|---|---:|---:|---:|---:|---:|---:|---:|
| 17\|18 (relegation) | 88.66% | 10.95% | 0.385% | 0.015% | 0.0% | 0.0% | 0.0% |
| 1\|2 (title) | 95.58% | 4.25% | 0.175% | 0.0% | 0.0% | 0.0% | 0.0% |

Scorelines matter, and they matter at the relegation boundary about two and a half
times as often as at the title: **11.34% ± 0.25** of relegation boundaries and
**4.42% ± 0.15** of title boundaries are decided by something a points-only model
cannot see (percentage points, one cluster-by-particle Monte-Carlo standard error,
computed over the same 20,000 retained rows and 1,000 particles as every other
figure in this report).<sup>[SE-1]</sup> That is
the direct answer to "does simulating scorelines rather than results earn its
cost" for this season. The mass the rulebook genuinely does not decide is 3e-5 per
club — four orders of magnitude below a headline probability of 0.5, and it is
carried explicitly rather than rounded away.

---

## 8. What this is, and what has **not** been verified

**What it is.** A forecast of final table positions for 2026/27, computed at the
season opener with zero matches played, **conditional on current strengths
remaining fixed for the whole season**. There is no within-season drift, no
injuries, no manager change, no January transfer window. The correlated
within-season error that leaves out is named and unmodelled, not estimated.

**Monte-Carlo error is not model error.** Every `±` in this report is a
cluster-by-particle Monte-Carlo standard error over 20,000 seasons and 1,000
posterior draws. It describes how much the *number* would move if the same model
were simulated again with a different seed. It says nothing about whether the model
is right.

**Explicitly not verified:**

1. **No retrospective score.** The preregistered retrospective — ranked probability
   score on final tables across held-out seasons, and the arm-vs-arm comparison
   that would decide which arm should be published — has **not** been run. Only the
   smoke harness exists (T8). The full seven-season retrospective is **v1.1 R1**.
   Until it runs, `dc_native` is the published arm because the design says the
   model is the default, **not** because it has been shown to beat either
   comparator. Nothing here is an accuracy claim.
2. **The posterior is approximate and probably too narrow.** Parameter uncertainty
   is 1,000 mean-field ADVI draws. Mean-field ADVI is very likely under-dispersed,
   so the tails in this report are conditional on the approximate posterior and are
   not honest tails until the richer-inference sensitivity (D19) has been run. It
   has not.
3. **Cold start is unrefitted.** Coventry's parameters are prior draws at the
   frozen hyperparameters (D17). Refitted cold-start hyperpriors are **v1.1 R10**.
   The truncation flag in §3 is a visible symptom of exactly this.
4. **Hull's dispersion is unexplained, not excused.** §4 gives the mechanism
   (a diffuse posterior for a club with old and sparse archive rows); nothing has
   tested whether that width is correct.
5. **`check` for bridge arms.** `simcli check` rebuilds `dc_native` from the
   particle book alone; the bridge arms need the archive and the fitted bridge as
   well, and `check` does not reconstruct them. Recorded, not fixed.
6. **One cutoff.** This is a single issuance at a degenerate cutoff — zero matches
   played, so the point-in-time conditioning path is exercised only by the witness
   state in criterion 5. The interesting mid-season behaviour is untested on this
   season.

**Limitations note.** The full auto-generated note written from this run's own
numbers is `data/epl/sim/issuances/2026_27/2026-08-21/limitations.md`. It is
written from the cutoff and the issuance's own numbers and from no wall clock, so
two issuances of one specification produce it byte for byte. Its six sections are:
what the forecast is conditional on, what the rulebook does not decide, the state
of the season, truncation-flagged fixtures, Monte-Carlo error, and what these
numbers are not.

---

## 9. Reproducing this issuance

```
PYTHONPATH=src:. .venv/bin/python -m epl.simcli forecast \
    --season "2026/27" --cutoff 2026-08-21 --all-arms \
    --n-sims 20000 --seed 20260611 --chunk-size 2000 \
    --witness-season "2025/26" --witness-cutoff 2026-01-01

PYTHONPATH=src:. .venv/bin/python -m epl.simcli check \
    --directory data/epl/sim/issuances/2026_27/2026-08-21
```

Nothing in this issuance has been published anywhere, and nothing was pushed.
`docs/obligations.md` is not touched by this work. Verified after the commit:
`LOCK VALID`, `git diff --stat main -- src scripts` empty, `pytest epl/tests -q`
**331 passed**.

---

## Appendix — the limitations note, verbatim

Reproduced in full because it lives under `data/`, which is gitignored, and a
reader of this repository cannot otherwise open it. This is the exact content of
`data/epl/sim/issuances/2026_27/2026-08-21/limitations.md`, generated from the run
itself.

> # Limitations — dc_native, 2026/27 at 2026-08-21 00:00:00
>
> Written automatically from the run itself — from the cutoff and the issuance's
> own numbers, and from no wall clock, so two issuances of the same specification
> produce this file byte for byte. Every number this issuance publishes is subject
> to all of the following.
>
> ## What the forecast is conditional on
>
> * **Strengths are frozen at the cutoff.** No within-season drift, no injuries,
>   no manager change, no January transfer window. The forecast is conditional on
>   current strengths remaining fixed for the rest of the season (plan v2 D2). The
>   correlated within-season error this leaves out is named and unmodelled, not
>   estimated.
> * **An approximate posterior.** Parameter uncertainty comes from 1000
>   mean-field ADVI draws, one joint draw per simulated season. Mean-field ADVI is
>   very likely under-dispersed, so the tails here are **conditional on the
>   approximate posterior** and are not called honest tails until a
>   richer-inference sensitivity has been run (plan v2 D19).
> * **Match randomness** is the Dixon-Coles scoreline law, truncated at
>   10 goals per side — the same truncation the published
>   per-fixture forecast uses.
>
> ## What the rulebook does not decide
>
> * Clubs level after goals scored share their positions fractionally. Mean shared
>   positions per simulated season: **0.007**.
> * Mass resting on the play-off convention (two clubs level on a material
>   boundary, no model for the play-off): **0.00003** per club.
> * Mass resting on the three-or-more-way convention, for which the Handbook has
>   no rule at all: **0.00000** per club.
> * Tiebreak rule id: `PL-2026-27:C4-C7+C17;material={1|2,4|5,5|6,6|7,7|8,17|18};h2h_away=original_set;unresolved=fractional;v1`.
>
> ## The state of the season
>
> * Fixtures played and conditioned on: **0**; simulated: **380**.
> * Fixtures whose scheduled date has passed with no result recorded
>   (simulated either way): **0**.
> * Results lag flag: **False**.
> * Points adjustments applied: **none**.
>
> ## Truncation-flagged fixtures
>
> Every fixture is priced on a grid truncated at 10 goals per side, and the mass
> that truncation discards is measured per particle for all **380** simulated
> fixtures: max **0.00536**, mean **0.000155**, 90th percentile **0.000346**.
> **Production truncates at the same 10 goals and discards the same tail
> silently** — the per-fixture forecast this project publishes renormalises over
> exactly the same grid. Fixtures whose particle-mean excluded mass exceeds the
> 0.005 flag threshold are listed here by id (D11 v1.0.1).
>
> * `2627:man_city:coventry` — particle-mean **0.00536**, median particle 0.000193, worst particle 0.448, particles over 1%: 88
>
> ## Monte-Carlo error
>
> * 20000 simulated seasons, 1000 posterior draws, each used
>   20-20 times.
>   Largest cluster-by-particle standard error on any published market:
>   **0.0117**.
> * Standard errors are Monte-Carlo only. They do not describe model error, and a
>   tight standard error on a badly specified model is still a badly specified
>   model.
>
> ## What these numbers are not
>
> * "Top 4", "top 5" and "top 7" are **table positions**. They are not claims
>   about qualification for any competition.
> * There is no betting content here: no odds, no market comparison, no stake.
> * The forecast has not been scored against a preregistered retrospective at the
>   time of writing; until it has, treat it as a demonstration of the pipeline
>   rather than as an accuracy claim.
