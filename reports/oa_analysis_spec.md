# OA analysis spec — the scored-pool development verdict (Plan 2 v2, task V7)

**STATUS: pre-registration input. Written 2026-08-01, BEFORE any scored-pool
issuance or scoring.** This document is hash-bound into the V8 lock bundle
(`analysis_spec_sha256`); V10 implements it literally and may not depart from
it. A change after the lock is an amendment: a new `lock-v2.json` chaining
`lock-v1.json`, plus a dated entry in the prereg's amendment log. Forecasts
issued under a superseded lock are invalidated.

Governing documents: the prereg
(`reports/oa_prereg.md` — relocated 2026-08-01 from the gitignored
`docs/superpowers/specs/2026-07-28-oa-prereg-DRAFT.md` so the V8 lock hashes
tracked, attributable bytes (finding B3-1); LOCKED at V8), the
program design (`docs/superpowers/specs/2026-07-28-odds-anchored-accuracy-program-design.md`,
OA-5), and the plan (`docs/superpowers/plans/2026-08-01-oa-plan2-acquisition-blend-verdict.md`,
V7). It exists because Codex finding 6 (BLOCKER) and finding 12 (MAJOR) found
the Holm family, the nulls, α, the missingness rule and the conditional MDE
re-run undefined or unimplementable. Everything they named is fixed below.

Scope: this is the **development** verdict on reused pools. It decides ONLY
what enters the AC2027 confirmatory test. Nothing here can confirm anything,
and no public accuracy claim follows from it (prereg "Frame").

---

## 0. Objects this spec refers to

| Name | Definition | Where it lives |
|---|---|---|
| ΔRPS | per-match `rps(arm) − rps(incumbent)`, canonical ÷2-normalized 1X2 RPS, range [0,1]; negative = arm beats incumbent | `wcmodel.model.calibration.rps` |
| block | (pool, **venue-LOCAL matchday**) — the ledger's `date`, never the UTC date of kickoff (prereg information-set rule; 36 WC-2026 fixtures roll past midnight UTC) | `wcmodel.eval.ledger` |
| support | fraction of block-bootstrap means strictly `< 0` | `power.block_bootstrap_support` |
| gate constants | `GATE_FLOOR = -0.002`, `GATE_SUPPORT_REQ = 0.80`, both comparisons INCLUSIVE at the constant | `power.GATE_FLOOR`, `power.GATE_SUPPORT_REQ`, `power.gate_pass` |
| de-vig set | EXACTLY `{shin, multiplicative}`; `basic` is the reporting label for `multiplicative`; `power` can never enter (finding 13) | `implied.OA_DEVIG_METHODS` |
| locked inventory | the V8 lock's `scored_fixture_inventory`: fixture ids + chosen snapshot `raw_sha256` + eligibility flags, frozen WITHOUT outcomes | `reports/oa_lock/lock-v1.json` |
| selection trace | the frozen `(w, de-vig)` + stacking parameters + the full `(method, w)` CV grid | `blend.write_selection_trace` |

Bootstrap constants, pre-committed: **B = 10,000 resamples, seed 0**. The block
structure is identical across arms on a given population, so a fixed seed gives
every arm the SAME resample draws (common random numbers) — arm-to-arm
comparisons carry no Monte-Carlo noise of their own. Per-pool bootstraps
(§4) use `numpy.random.SeedSequence(0).spawn()` children consumed in sorted
pool-name order.

---

## 1. Primary contrast and the gate

**One primary contrast: E′(selected de-vig) vs the incumbent**, paired per
match on the primary population (§3), one-sided in the direction "E′ better".

* **E′(selected de-vig)** = the per-draw blend at the `(w, de-vig method)` the
  V6 selection froze, read from the locked selection trace. No re-selection,
  no re-tuning, no joint retune of k.
* **Incumbent** = the production model regenerated per fixture at the same
  `T_issue` information set (prereg "Incumbent benchmark"), bitwise identical
  to production at k=0.6.

**Decision rule (the gate):**

```
mean(ΔRPS) <= -0.002   AND   support >= 0.80
```

evaluated by `power.gate_pass(mean_diff, support)`. α does **not** apply here:
the gate IS the decision rule, not a hypothesis test. The one-sided p-value of
§2 is reported next to it **descriptively** and never overrides it. Point
estimates never adopt on their own; both halves are required.

Reported alongside, always: n, mean ΔRPS, support, p, the per-pool table (§4),
the jackknife range (§5), and the ITT sensitivity (§3).

---

## 2. Secondary family — exactly four members, Holm at α = 0.05

The secondary family is **exactly these four contrasts**, each against the
same incumbent, on the same primary population, paired per match, one-sided:

| # | Member | Definition (fully determined by the locked artifacts) |
|---|---|---|
| 1 | `Eprime_other_devig` | the per-draw blend under the de-vig method NOT selected at V6, at `w* = argmin` over the w grid of the selection trace's `grid_mean_rps` rows for that method (ties → smaller w, V6's own tie rule). Determined entirely by the locked trace; no scored-pool data enters. |
| 2 | `S` (stacking) | the V6 OOF-trained ordered-logit stack over [DC, de-vigged odds, elo_ordlogit] 1X2 vectors, at the locked deployment `params`. 1X2-only, structurally ineligible for scoreline/tournament surfaces. |
| 3 | `elo_ordlogit` | the odds-free Elo ordered-logit head (`wcmodel.eval.elo_ordlogit`), fitted only on information ≤ `T_issue` for the fixture's bucket — same information set as the incumbent. |
| 4 | `elo_dc_5050` | per match, `p = 0.5·p_elo_ordlogit + 0.5·p_incumbent`, renormalized by its own sum (the ledger's sum-to-1 tolerance is 1e-9). Odds-free. |

**Per-tier `w` is NOT a member.** It was removed from the family by the dated
prereg amendment of 2026-08-01 (finding 6: it was never implemented and never
had a fold protocol — a phantom member would have inflated the correction
while contributing no test). It is not implemented and may not be reported as
a contrast.

**Procedure.** Holm step-down at **α = 0.05, one-sided**, over the four
p-values of §2.1. Order p(1) ≤ … ≤ p(4) (raw-p ties broken by the fixed arm
order in the table above). Adjusted p-values are the monotone-enforced

```
p~(i) = max_{j <= i} min(1, (4 - j + 1) * p(j))
```

and member i is rejected (declared "better than incumbent, family-corrected")
when `p~(i) <= 0.05`. Holm is chosen precisely because it is valid under
ARBITRARY dependence between the four p-values, which is what common random
numbers and shared fixtures guarantee they have.

**Implementation** (added 2026-08-01, finding B3-5 — this rule is code, not
prose): `power.holm_adjust` over the fixed family keys `power.HOLM_FAMILY ==
("Eprime_other_devig", "stacking", "elo_ordlogit", "elo_dc_5050")`
(`stacking` is S), raw-p ties broken by that fixed order, monotone-enforced
adjusted p, rejection inclusive at α. A missing, extra, NaN or out-of-range
member raises — the fixed-cardinality stance below, enforced at the call.

**Family cardinality is fixed at four.** If any member cannot be computed —
missing rows, a failed fit, an arm not issued — the analysis **errors**. It is
never dropped, never re-weighted, never replaced.

Secondary results are reported regardless of the primary verdict and never
change it: a rejected secondary is not an adoption path, and E′ remains the
only arm the primary gate can advance to AC2027.

### 2.1 The block-bootstrap p-value

For a paired-difference vector with observed mean `m` and B block-bootstrap
means `m*_b` (blocks = pool × venue-local matchday, resampled with replacement
WITHIN pool strata — `power.block_bootstrap_support`'s scheme):

```
p_one_sided = (1 + #{ b : m*_b >= 0 }) / (B + 1)
```

i.e. the one-sided percentile-bootstrap p in the direction "arm better than
incumbent", with the standard +1 correction so p is never 0 and never below
`1/(B+1) = 9.999e-5`. It is the exact complement of the gate's support
statistic (`p = (1 + B(1 − support)) / (B + 1)`), which is why they are
reported together and cannot disagree in sign.

Known and accepted: this is a percentile p, not a studentized one; it is
chosen for coherence with the support statistic the gate already uses, and its
accuracy is bounded by the same block-bootstrap approximation. It is
descriptive for the primary and decision-bearing only through Holm for the
secondaries.

---

## 3. Population

Both populations are fixed by the V8 lock **entirely without outcome data**
— eligibility depends only on the odds snapshot and the solver, and on
NOTHING downstream of kickoff (amended 2026-08-01, finding B3-3: the
availability of a verified 90′ result is itself outcome information and
never enters eligibility — an earlier reading that excluded missing-90′
fixtures "at lock time" contradicted the outcome-free freeze and is
withdrawn).

* **`covered` flag** (frozen at V8, per fixture): an admissible cut quote at
  `T_issue − 30 min` (`odds.admissible_quote`, STRICT `<` on both legs) **AND**
  implied-rate solver success (`implied`: residual < 1e-6 with two-start
  agreement). Solver failure ⇒ not covered; there is no symmetric-split
  fallback, ever.
* **PRIMARY population** = the locked inventory restricted to `covered`. All
  five contrasts (primary + four secondaries) are computed on THIS population,
  including the two odds-free arms — otherwise the family would not be paired
  on a common set.
* **SENSITIVITY population (ITT-with-incumbent-fallback)** = the WHOLE locked
  inventory. Uncovered rows carry the incumbent forecast bitwise, with
  `odds_snapshot_hash = None`; their ΔRPS is therefore exactly 0.0 for every
  odds arm, which dilutes any effect toward the null by construction. Reported
  as a sensitivity only. **It can never produce an adoption the primary did
  not**, and if the two disagree the report must state the coverage rate and
  say plainly that the primary is the covered-only estimand.

**Exact-cardinality scorer (finding 10).** For each arm and each population,
the scorer asserts that the set of scored `fixture_id`s equals the locked set
EXACTLY:

* a fixture in the locked population with no ledger row for some arm ⇒ **ERROR**;
* a ledger row for a fixture outside the locked population ⇒ **ERROR**;
* a locked fixture that cannot be settled at scoring time — no verified 90′
  regulation outcome in `config/regulation_time_results.yaml` ⇒ **ERROR,
  and the run produces NO verdict** (amended 2026-08-01, finding B3-3).
  Eligibility was frozen without outcomes, so settlement availability can
  never re-shape the population: the fixture is never silently dropped and
  the population is never re-frozen. The remedy is outside the scorer —
  complete the curated 90′ table from verified sources, or formally amend
  the lock (`lock-v2.json` chaining `lock-v1.json`, dated prereg amendment)
  — and only then can a verdict exist;
* duplicate `(arm, fixture_id)` ⇒ already rejected by the ledger.

No inner join, no `dropna`, no "score what we have". A missing row changes the
paired set asymmetrically and is a bug, not a smaller sample.

**ITT scope (pre-committed; amended 2026-08-01, finding B3-4): the ITT
sensitivity is computed for the PRIMARY contrast only.** The four secondary
contrasts are covered-population only and are never re-run under ITT: the
incumbent-fallback construction is an odds-arm device (uncovered rows carry
the incumbent bitwise, ΔRPS exactly 0.0), so for the odds-free members an
ITT row is not even well-defined — their forecasts exist everywhere and
"fallback" has no meaning — and re-running any secondary on a different
population would break the family's common paired set (§2).

---

## 4. Per-pool effects and the sign-flip veto

Per pool (`wc2022`, `euro2024`, `wc2026`), on the primary population, report:
n, mean ΔRPS, own-pool support, own-pool p. The per-pool bootstrap resamples
that pool's own matchday blocks (B = 10,000, seed spawned per §0).

**Own-pool support in the opposite direction** = the fraction of that pool's
bootstrap means strictly `> 0`.

**Veto rule.** If the primary gate passes but **any** pool has

```
mean(ΔRPS | pool) > 0    AND    own-pool opposite-direction support >= 0.60
```

the verdict is **`inconclusive-heterogeneous`**, not PASS. Nothing advances to
AC2027 on a pooled average that one pool contradicts that strongly.

**Implementation** (added 2026-08-01, finding B3-5): `power.sign_flip_veto`
over per-pool `{n_blocks, mean_diff, opposite_support}` stats —
`mean_diff > 0` strict, `opposite_support >= power.VETO_OPPOSITE_SUPPORT_REQ
== 0.60` inclusive, zero-block pools skipped (they are not in the scan), an
entirely empty scan an error. PASS-only downgrade semantics live in its
docstring: a True return downgrades a primary PASS and can never rescue a
FAIL.

Deliberate properties of this rule, pre-committed rather than discovered
later:

* **No minimum pool size.** A pool holding a single block has degenerate
  support (0 or 1) and can therefore veto alone. Accepted, because the only
  consequence is inconclusiveness — the conservative direction. Pools
  contributing zero fixtures to the primary population are not in the scan at
  all.
* The veto only ever downgrades a PASS. It cannot rescue a FAIL, and per-pool
  effects are reported whatever the verdict.
* 0.60 is inclusive at the boundary (`>= 0.60`).

---

## 5. Team-overlap sensitivity — leave-one-team-out cluster jackknife

Matches sharing a team are not independent (a team's whole tournament moves
together), and every pool is a round-robin plus knockout over ~24–48 teams.

Procedure: for each team `t` appearing in the primary population, delete
**every** match in which `t` appears on either side, recompute the primary mean
ΔRPS on the remainder, and report

* the range `[min_t, max_t]` of the recomputed means, with the two extremal
  teams named and their deleted-match counts;
* the number of teams whose deletion pushes the mean above `GATE_FLOOR`.

This is a **sensitivity, not a gate** — it never changes the verdict. It is
also **not a variance estimate**: team clusters overlap (each match belongs to
exactly two of them), so the classic delete-one-cluster jackknife variance
formula does not apply and must not be quoted.

Pre-committed reporting rule: if any single team's deletion moves the mean
above the floor, the verdict line must carry "floor not robust to
leave-one-team-out" alongside the verdict, naming the team.

---

## 6. Panel-generation correlation and the MDE re-statement

`reports/oa_mde.md` (seed 0) generated every simulated panel i.i.d. from the
centered empirical diffs; only the SUPPORT stage modelled block dependence.
Where paired diffs correlate positively within a matchday, i.i.d. generation
understates the dispersion of the panel MEAN — the quantity the floor half of
the gate tests — so the stated MDE is optimistic (finding 12).

**Estimator (pre-committed).** `power.within_block_correlation(diffs, pool,
day)`: the mean PAIRWISE within-(pool, matchday) correlation of the paired
diffs — every ordered within-block pair weighted equally, centered on the
grand mean, scaled by the panel variance about it. A panel with no
within-block pair raises rather than returning nan (nan would compare False
against the threshold and silently select the optimistic branch).

**Threshold (pre-committed).** "Materially positive" is `r > 0.05`,
**strictly**; `r == 0.05` is not exceeded. Applied by
`power.generation_for_correlation(r)` → `"block"` or `"iid"`.

**Where it is measured at lock.** The scored pool's realized diffs do not
exist before the lock (they need outcomes), so the lock-time estimate is
`r_dev`, measured on the **V5 dev-slate** paired diffs of the same contrast
(E′(selected) − incumbent, blocks = competition × venue-local matchday). This
is the only realized E′-vs-incumbent contrast available pre-lock, and it is
dev data by construction.

**What the lock re-states.** The MDE grid is re-run with
`generation = generation_for_correlation(r_dev)`, noise = the dev-slate diffs,
labels = that dev panel's own blocks, at the shipped constants (deltas
0.000–0.010 per `scripts/oa_mde.py`, `n_sims=400`, `n_boot=1000`, seed 0). The
lock records `r_dev`, the chosen generation, and both `n_dev` and the locked
primary `n` side by side. The MDE is a joint property of (n, sd, generation) —
no rescaling formula is applied to move it between panel sizes, and the
re-statement says which n it belongs to.

**What V10 adds.** V10 reports the realized scored-pool `r` on the primary
diffs. If it exceeds the threshold, V10 re-runs the grid on the scored panel
itself under block generation and reports it as an explicitly **post-hoc**
sensitivity. Post-hoc MDE numbers never change the gate, the verdict, or the
locked pre-committed reading.

---

## 7. Verdict language

Exactly one of the following, from the locked prereg's permitted set:

| Verdict | Condition |
|---|---|
| **PASS** | `gate_pass(mean, support)` on the primary population AND no pool triggers the §4 veto |
| **inconclusive-heterogeneous** | gate passes but a pool vetoes (§4) |
| **FAIL — directional-only** | gate not met with `mean < 0` (E′ ahead of the incumbent but short of the floor and/or the support requirement) |
| **FAIL — no direction** | gate not met with `mean >= 0` |
| *(no verdict)* | the scorer errored (§3) — the run is invalid and produces no verdict |

Every non-PASS verdict carries the prereg's MDE conditioning sentence: at this
n and this realized dispersion a FAIL is evidence against effects of roughly
the MDE and above, **not** against a true 0.002 effect, and is never recorded
as "no effect". A PASS advances E′ to the AC2027 confirmatory test and nothing
else — it is not a production-adoption decision and licenses no public
accuracy claim.

## 8. Required outputs (V10)

`reports/oa_development_verdict.md` carrying, regardless of verdict: the
verdict line; n and coverage for both populations; primary mean/support/p; the
four-member Holm table with raw and adjusted p-values and the rejection
decisions; the per-pool table with the veto scan; the jackknife range and its
extremal teams; the realized `r` with the generation it implies; the ITT
sensitivity; and the diagnostic 2×2 (Elo-anchor on/off × odds on/off,
diagnostic only, never an arm-selection channel). Plus per-match JSONs holding
the paired ΔRPS rows the tables were computed from.
