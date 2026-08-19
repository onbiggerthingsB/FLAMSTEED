# EPL table simulator — amendments to the preregistered design

Every change to a preregistered decision of the EPL table simulator is recorded
here, **before** the code that implements it is written, with the observation
that prompted it, the ruling in full, the rationale, and any number the ruling
pre-states. An amendment recorded after a result exists is not an amendment; it
is a rationalisation, and this file exists so the distinction is checkable from
the git history rather than taken on trust.

Format per entry: **observation → ruling → rationale → what is pre-stated**.

---

## A1 — D11 v1.0.1 (2026-08-19)

**Decision amended:** D11, the per-fixture truncation guard.
**Status of the amendment when written:** the guard is unchanged in code; no
`dc_native` issuance of any kind exists.

### The observation

At the first attempted 2026/27 issuance — cutoff 2026-08-21, the season opener,
zero results, 20 clubs from the transition — the `dc_native` arm failed closed on
D11's excluded-mass guard. Recorded in full in
[`reports/epl_sim_first_issuance.md`](epl_sim_first_issuance.md) §2; the numbers
that matter here:

| | |
|---|---|
| Fixtures over the 5e-3 gate | **1 of 380** — `2627:man_city:coventry`, particle-mean **0.005365** against the 0.005 limit (7.3% over) |
| Next worst three | `arsenal:coventry` 0.003934, `liverpool:coventry` 0.003426, `man_city:hull` 0.003284 |
| Mean over all 380 fixtures | 1.55e-4 · 90th percentile 3.46e-4 |
| Median **particle** for the failing fixture | 1.9e-4 — four orders of magnitude under the gate |
| Concentration | the worst 10 particles of 1,000 contribute 42.6% of the mean; 88 particles exceed 1%, 22 exceed 5% |
| Worst particle (s=953) | λ_home = 10.25, λ_away = 0.90 → P(home > 10 goals) = 0.448 |

The failure is deterministic: the same stop on every attempt, at the same fit and
the same seeded cold-start draws.

Its cause is a cold start, not a mis-scale. Coventry has no match anywhere in the
2014/15–2025/26 archive, so its attack and defence come from prior draws at the
fitted hyperparameters (D17), sd ≈ 0.30/0.34, range −1.16 to +1.24. A handful of
draws put Coventry's defence near −1.1; against Man City's attack (mean +0.77)
that gives λ_home > 10, and those individual particles lose 25–45% of their mass
past the truncation. Every fixture near the top of the list involves a promoted
club.

Sensitivity, diagnostic only and with nothing changed: at `max_goals` 11 the
worst fixture is 0.002814 and no fixture is over the gate; at 12, 0.001480; at
14, 0.000404; at 16, 0.000103.

### The ruling (owner, 2026-08-19)

D11 v1.0.1 — *report-and-record with a pre-stated hard ceiling*:

**(a)** `PRODUCTION_MAX_GOALS` stays **10**, for parity with the issued
per-fixture forecasts. Cold start stays exactly as D17 froze it. The 5e-3 number
is **kept**, but its meaning changes from hard-stop to **flag**: every fixture
whose particle-mean excluded mass exceeds 5e-3 is recorded in the envelope
(fixture id, particle-mean, median particle, worst particle, count of particles
over 1%) and listed by id in `limitations.md` under a section **"Truncation-flagged
fixtures"**, together with the sentence that production truncates at the same 10
goals and discards the same tail silently.

**(b)** The per-fixture excluded mass for **all** fixtures is recorded in the
envelope — max, mean, 90th percentile, and the full per-fixture vector in the
retained npz or a sidecar — not only for the flagged ones.

**(c)** A **hard stop remains**: a particle-mean excluded mass above **2e-2** on
any fixture fails the run closed with `ExcludedMassTooLarge`, exactly as before.

**(d)** Nothing else in D11 changes: the grid is still built through the `_post()`
accessor, the likelihood is still Dixon-Coles only, covariates stay off, and the
`effective_posterior_hash` is unchanged in meaning and construction.

### The rationale

Production already discards this tail, silently, for this same fixture: the
per-fixture forecast this project publishes truncates and renormalises at exactly
the same 10 goals. D11's gate is what surfaced it. The guard was the first thing
to look at, and what it found is a real property of the published law rather than
a defect introduced by the simulator.

The amendment makes the simulator **more** visible about that tail than
production is, not less: production reports nothing, and after this amendment the
simulator reports the excluded mass for every fixture and names the ones over the
old threshold in the issuance's own limitations note.

The tail is a cold-start artefact of one club with zero archive rows. It is
expected to collapse once Coventry has fitted rows — a forecast, and recorded
here as one so it can be checked later rather than assumed now.

### What is pre-stated

**2e-2 is pre-stated here, in this entry, before any run under the amended rule
and before any `dc_native` number exists.** It is 4× the worst fixture observed
at the opener (0.005365). It still catches the failure mode the original guard
was built for: a mis-scaled rate — λ around 20 — excludes roughly half the mass
and would trip it by more than an order of magnitude.

The flag threshold stays at its preregistered value of 5e-3. Neither number was
chosen after seeing a result under the amended rule, because no such result
exists.

### Recording note

This entry is recorded **before the guard was changed and before any `dc_native`
issuance existed; the commit that changes the guard follows this one.**

---

## A2 — Harness v2 for future retrospective runs (2026-08-19)

**Decision amended:** the retrospective harness frozen by
[`reports/epl_sim_prereg_retro.md`](epl_sim_prereg_retro.md) §1 —
`epl/simretro.py` at `2b25ab35…` and `epl/simmetrics.py` at `e73f2f70…`.
**Status of the amendment when written:** not a line of either file has changed;
both still hash to the values above. R1 is the only retrospective run that
exists and it is already written up in
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md).

*Arithmetic note for this entry and the two below: every number computed here is
exact — closed form or deterministic quadrature — and carries no Monte-Carlo
error of its own. The handful of numbers quoted from runs that already happened
(`0.005365`, `1.9e-4`, `3.865σ`, `4.441e-16`) are quoted from their source
reports and carry whatever error those reports record beside them. No new
estimate is produced anywhere in A2, A3 or A1-C1.*

### The observation

A read-only Codex review of the R1 harness found four defects. Not one of them
changes an arithmetic result. Each of them weakens a guarantee that the R1
report makes on the harness's behalf, which is a different and quieter kind of
problem: the numbers are right and the reasons for trusting them are thinner
than they read.

**(a) The resume key omits producer identity.** `run_key`
(`epl/simretro.py:456`) is
`f"{season}|{cutoff_label}|{day}|{arm}|n{n_sims}|s{seed}"` — the question, and
nothing else. `run_retro` loads the ledger into `have = {row["run_key"]: row …}`
(`:583`) and skips any requested key already present (`:604`, `:629`), never
reading the `envelope_hash` that travels beside it. The docstring at `:558`
states the reasoning as *"every forecast is a pure function of (season, cutoff,
arm, n_sims, seed) **and the frozen configuration**"* — and the key covers the
five, not the configuration, not the harness source, not the fitted book. So a
ledger written by one producer and resumed by another passes its own resume
test: the rows it keeps are stale, the rows it appends are fresh, the file marks
neither, and nothing stops or warns. The `envelope_hash` needed to detect it is
already on every row and is simply never consulted at resume time.

**(b) The "beats flat at every (season, cutoff)" hard check passes on any
non-empty subset.** The flag is
`"dc_native_beats_flat_everywhere": bool(checked and not violations)` (`:783`),
where `checked` counts only the occasions at which *both* `dc_native` and `flat`
are present (`:765-771`). A missing cell — refused, un-run, or lost — is not a
violation; it is not counted at all. One surviving cell out of a preregistered
twenty-eight would report `True`. The check is guarded against emptiness and
against nothing else. In R1 it did not fire: `checked` was 28, and 28 is exactly
the admissible grid (six seasons × five comparison cutoffs, less the two openers
D11 refused). The count was right. Nothing in the harness established that it
was right, and a reader of "0 violations" cannot tell the two apart.

**(c) The `MC SE` column is mislabelled, twice.** Its value is
`float(stats_market["se"].mean())` (`epl/leaguesim.py:989`) — the **mean**
cluster-by-particle standard error over the club × consequence cells. The retro
report prints it under the heading `MC SE` (`epl/simretro.py:803`, `:843`), at
the right-hand end of a row whose leading number is TRPS, and its legend
(`epl_sim_retro_v1_1.md:95`) describes it as *"cluster-by-particle Monte-Carlo
error on the position matrix"*. It is neither of those things: it is not an
error on TRPS, and it is not the position matrix's error either — that quantity
exists, separately, as `matrix_cluster_se_max` in the same `mc` block. A reader
applying this project's own rule, an MC SE beside every headline number, will
read the column as belonging to the headline it sits in a row with. **TRPS in v1
carries no Monte-Carlo error at all**, and the column is what disguises that.

**(d) Ledger scoring checks row sums and not column sums.** `_as_matrix`
(`epl/simmetrics.py:92-108`) validates shape, finiteness, non-negativity and
row sums — *"every club must finish somewhere"* — and stops there.
`epl/table.py:check_doubly_stochastic` checks both margins and is called on a
freshly simulated result (`epl/simretro.py:392`, `:402`, `_check_clubs` at
`:643-651`), but never on a matrix read back **out of** the ledger:
`score_retro` → `_score_one` (`:658`) goes straight to `simmetrics.trps`. A
stored matrix whose columns have drifted — rows still summing to 1, position
mass no longer conserved — scores silently, and the scoring path is the one that
turns a stored row into a published number.

### The ruling (owner, 2026-08-19)

**Harness v2.** All four are fixed in `epl/simretro.py` / `epl/simmetrics.py`,
by the Fix commit that follows this one, under TDD with a positive control per
fix — each guard must be shown rejecting the thing it exists to reject, not
merely accepting a good run.

**(a) Producer identity, both in the key and as a refusal.** `run_key` gains a
producer segment: a digest over the harness schema version, the SHA-256 of
`epl/simretro.py` and `epl/simmetrics.py` as they stand at run time, and the
frozen configuration identity the runner already holds. A row from a different
producer can then never satisfy a request, by construction. In addition,
`run_retro` **refuses** — a named error, before any fit — when the ledger holds
any row whose producer identity differs from the current one, listing the
offending keys. The refusal may be overridden only by an explicit argument, and
the override is recorded in the run's own envelope and printed in the report, so
a mixed ledger is possible only on purpose and never quietly.

**(b) Completeness, not just non-emptiness.** The sanity block records
`n_expected` (the requested (season, cutoff) cells), `n_checked`, and
`n_missing` with each missing cell's reason taken from the ledger — a
`not_applicable` row and its stated reason, or absence. The flag is `True` only
if `n_checked > 0`, there are no violations, **and**
`n_checked + n_documented_refusals == n_expected`. An undocumented hole fails the
check instead of vanishing from it.

**(c) The column is renamed and the legend is rewritten.** The heading becomes
`cons-cell MC SE (mean)`, a second column `cons-cell MC SE (max)` is printed
from the `cluster_se_max` the `mc` block already carries, and the legend states
in the report itself that both are cluster-by-particle Monte-Carlo error over
the club × consequence cells, that neither is an error on TRPS, and that **TRPS
carries no Monte-Carlo error in this harness**. No new arithmetic: both numbers
are already recorded. Supplying a genuine MC SE for TRPS is a change to the
metric set, not a relabelling, and it is **out of scope for v2**; it is recorded
here as an open item so that the relabel is not mistaken for having answered it.

**(d) The scoring path checks both margins.** `score_retro` calls
`epl.table.check_doubly_stochastic` on every ledger matrix before scoring it, at
that function's existing `1e-8` tolerance, and the scored output records how
many matrices were checked and the worst row and column deviations seen. A
column-corrupt stored matrix raises instead of scoring.

**The R1 record STANDS.** [`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md)
in full, including its 2026-08-19 correction note, stands as issued under harness
**v1** at hashes `2b25ab35…` / `e73f2f70…`. No number in it changes, nothing in
it is withdrawn, and the hashes it verified at run time remain both the hashes it
ran under and the correct record of that run.

**The R1 ledger is NOT re-scored under v2.** The reason is specific rather than
convenient: **v2 changes no scoring arithmetic.** Every one of the four is a
key, a guard, or a label.

- **(a)** decides which rows a *future* run reuses. It cannot change what any
  stored row scores to.
- **(b)** adds an accounting record beside the same violation list computed the
  same way. R1's own `checked = 28` is already the whole admissible grid, so the
  completeness identity's answer for R1 is known and is `True`.
- **(c)** renames a column and prints a second number already in the ledger.
- **(d)** is a guard that can only refuse, never alter — and R1 already read
  every stored matrix back out of the ledger and checked both margins
  independently: 166 matrices, 0 failures, worst column-sum deviation
  `4.441e-16` (retro §6, Check 2). v2's answer for that ledger is therefore
  already on the record, obtained by exactly the check v2 installs.

Re-scoring would push the same rows through the same formulas and reproduce the
same numbers. Publishing that as a fresh result under a new harness version
would be the rationalisation this file exists to prevent — a second, newer-looking
citation for one run.

**Every future retrospective run records v2 hashes.** The Fix commit states the
new SHA-256 of both files, and **those hashes are appended to this entry as a
dated note when it does**. A run whose harness hashes match neither the v1 pair
above nor a v2 pair recorded here refuses, exactly as prereg §12 already
requires.

**Nothing else in the retrospective changes.** Not the question, the grid, the
seasons, the cutoffs, the arms, the nulls, the pairings, the metrics or the pass
rules. TRPS stays primary and unweighted; wTRPS stays secondary on the published
consequence boundaries; the paired differences stay a diagnostic with no pass
rule; scores are still never averaged across cutoffs.

### The rationale

Three of the four are guarantees that were *stated* but not *enforced*, and the
gap between those two is the whole subject of this file. The R1 report tells a
reader that the run beat the flat null everywhere, that its matrices are
coherent, and that a column of Monte-Carlo error sits beside every score. Two of
those three sentences were true of R1 as a matter of fact and not as a matter of
the harness having checked; the third was not true in the sense a reader would
take it. Fixing the harness is cheaper than asking every future reader to know
which is which.

The resume key is the one with teeth. R1 ran to completion and its hashes were
verified at run time against the preregistration, so there is no evidence the
defect fired — but the v1 key gives no *per-row* proof of that, and saying so
plainly is more useful than an assurance the key cannot support. That is
precisely why v2 puts the proof on each row instead of in a sentence.

Not re-scoring R1 is the conservative choice in the direction that costs
something. The tempting move is to re-run under v2 and cite the newer hashes;
the honest one is to leave the record where it was made, because a rerun would
produce no new information and every appearance of it.

### What is pre-stated

Fixed here, before the code exists and before any v2 run exists:

- The v2 resume key includes producer identity, and a foreign-producer row
  **refuses the run** rather than being silently reused; the override leaves a
  recorded trace in the envelope and in the report.
- The completeness identity is
  `n_checked + n_documented_refusals == n_expected`, with `n_checked > 0` and
  zero violations, all three required for the flag.
- The column names are `cons-cell MC SE (mean)` and `cons-cell MC SE (max)`, and
  the legend states that TRPS carries no MC SE in this harness.
- The margin guard runs at `check_doubly_stochastic`'s existing `1e-8`
  tolerance — not a new, looser number chosen to let something through.
- A TRPS Monte-Carlo error is **not** part of v2.

No threshold above was chosen after seeing a result under it, because no result
under harness v2 exists. The v2 hashes are the one thing this entry cannot
state in advance; they are appended as a dated note by the commit that creates
them.

### Recording note

Written **before any line of `epl/simretro.py` or `epl/simmetrics.py` changed**;
both files were re-hashed at the moment of writing and still match the v1 values
in the heading. The commit that changes them follows this one.

---

## A3 — `marginal_parity` multiplicity (2026-08-19)

**Decision amended:** acceptance criterion 3, `marginal_parity` — *fixture-level
simulated marginals match production within MC error* — implemented at
`epl/simcanary.py:marginal_parity`, whose preregistered per-cell threshold is
`DEFAULT_N_SIGMA = 4.0` (`epl/simcanary.py:83`).
**Status of the amendment when written:** the criterion is unchanged in code.
One issuance has passed under it — 2026-08-21, worst cell **3.865σ** of 14,225
compared cells, 0 failures.

### The observation

Two things: the rule is miscalibrated for its own size, and the sentence written
to defend it was also wrong.

**The rule is miscalibrated for its own size.** "Every cell within 4 cluster-SE"
is a per-cell threshold applied to roughly fourteen thousand cells at once. The
two-sided normal tail at 4σ is `6.334e-05`. At m = 14,225 that is **0.9010
expected exceedances** under a *correct* sampler, and

```
P(at least one cell beyond 4σ) = 1 − (1 − 6.334e-05)^14225 = 0.5939
```

**A correct sampler fails criterion 3 about three runs in five.** A gate that a
correct sampler fails more often than it passes is not a gate; it is noise wearing a threshold. All of this is exact arithmetic on the normal tail
— no simulation, no Monte-Carlo error.

**The defence of it was also wrong.** The issuance report
([`epl_sim_issuance_2026-08-21.md`](epl_sim_issuance_2026-08-21.md) §2) says
*"the expected largest |Z| among 14,225 independent standard normals is about
3.98"*. That is not the expected largest |Z|:

| quantity, m = 14,225 iid standard normals | value |
|---|---:|
| **E[max \|Z\|]** — quadrature on `1 − (2Φ(x) − 1)^m` (abs. err `3.2e-08`) | **4.1014** |
| median of max \|Z\| | 4.0617 |
| `Φ⁻¹(1 − 1/(2m))` — the point where *expected exceedances* = 1 | 3.9753 |
| E[max Z] (signed, not \|Z\|) | 3.9374 |

The report's 3.98 is the third row: the one-expected-exceedance point, which is
neither the mean nor the median of the maximum. The error is small in size and
unhelpful in direction — it understated the noise floor being invoked, which
made the 4σ rule look better calibrated than it is, and made 3.865σ look like
comfortable headroom rather than what it is, a value about one expected
exceedance out from the middle of the null.

**Two features of the standardisation cut the other way, and neither rescues the
rule.** The per-cell SE is `max(cluster SE, binomial SE)` (`simcanary.py:532`),
so |Z| is *deflated* wherever the cluster SE exceeds the binomial floor; and
three of every fixture's compared cells (the home/draw/away triple) are exact
linear combinations of that fixture's scoreline cells, so the m cells are not
independent. Both push the true null distribution of max|Z| below the iid
figures in the table. Neither makes a per-cell 4σ threshold defensible at
m = 14,225.

### The ruling (owner, 2026-08-19) — pre-stated before the code, and before any run under it

Criterion 3 becomes a **two-legged test, and both legs must hold**.

**Leg 1 — per-cell, family-wise.**

```
z* = Φ⁻¹(1 − α / (2m)),   α = 0.01,   m = cells actually compared in that run
```

A cell fails if `|Z| > z*`. At m = 14,225 this gives **z\* = 4.9605** (per-cell
two-sided p at z\*: `7.0299e-07`). `DEFAULT_N_SIGMA = 4.0` is retired as the
per-cell threshold; α = 0.01 is the constant that replaces it, and m is read
from the run rather than assumed.

**Leg 2 — global.** A Pearson-type omnibus over exactly the compared cells:

```
χ² = Σ Z²  over the m compared cells,  referred to χ² with df = m
```

The run passes leg 2 if **p > 1e-3**. The Z here is the same per-cell
standardised deviation leg 1 uses — same numerator, same
`max(cluster, binomial)` denominator — so the two legs can never disagree about
what a cell's deviation was.

**Both must hold.** Leg 1 alone cannot see a hundred cells each at 3σ in the
same direction; leg 2 alone cannot see one cell at 8σ among fourteen thousand.

**The report and the acceptance record print `m`, `z*`, `max|Z|`, `χ²`, `df`
and `p`** — all six, on every run, pass or fail. A criterion whose threshold
moves with the run has to show its threshold.

**Approximations in leg 2, recorded rather than hidden.** Σ Z² is not exactly
χ²_m: within a fixture the scoreline cells are multinomial and lose one degree
of freedom (at most 380 of 14,225, 2.7%), the ≥25-expected-count floor drops
cells and with them part of that constraint, the home/draw/away triple is a
linear combination of cells already in the sum, and the `max(cluster, binomial)` SE
deflates the terms. The net of these slacks makes leg 2 marginally **easier** to
pass. That is exactly why leg 2 is set at the very loose `p > 1e-3`: it exists
to catch a global mis-scaling that no single cell reveals, not to adjudicate a
borderline run. Leg 1 does the per-cell work, and leg 1's arithmetic is exact.

**The 2026-08-21 issuance is not re-gated, and does not need to be.** Its worst
cell, **3.865σ** over 14,225 compared cells, is below `z* = 4.9605` by
**1.096σ** — so on the leg that can be evaluated from its own record it passes
under A3 as well, with more margin than it had under the rule it was actually
gated by. Leg 2 did not exist when that run executed, is not computed
retroactively, and no claim is made here about what it would have said. The
issuance stands under the rule preregistered for it, exactly as R1 stands under
harness v1.

**Open item, named so it is not lost:** the sentence quoted above still stands
uncorrected in `epl_sim_issuance_2026-08-21.md` §2. It is corrected *here*; the
in-place dated correction to that report is a separate docs commit and has not
been made.

### The rationale

The criterion is the sharpest one the acceptance gate has — it is what
distinguishes *the simulated per-fixture marginals **are** the published
forecast* from *they resemble it* — and it was the one criterion the blocked
first issuance could never supply. Making it fail three runs in five under a
correct sampler would have destroyed it in the most damaging possible way: not
by letting a defect through, but by producing failures often enough that a
future operator learns to explain them away. The first time criterion 3 fails
should be a reason to stop, and it can only be that if a correct sampler
almost never causes it.

The two legs answer the two failure modes a single number cannot answer at once.
Bonferroni on the per-cell leg is deliberately blunt — it is conservative under
the dependence documented above, and conservative here means *harder to fail
spuriously*, which is the property the criterion needs most. The χ² leg is the
cheap insurance against the opposite error: a uniform, small mis-scaling that
never produces a single dramatic cell.

Recording the issuance report's arithmetic error in the same breath as the
ruling matters, because the wrong number is what made the old rule look sound.
An amendment that changed the rule without saying why the previous defence of it
did not hold would leave the reasoning worse than the code.

### What is pre-stated

- **α = 0.01**, the **`p > 1e-3`** χ² threshold, and the `z*(m)` formula are all
  fixed here, before the code that computes them and before any run under them.
  At m = 14,225, `z* = 4.9605`; at any other m the formula produces the number
  and the report prints it.
- **`min_expected_count` stays 25.0.** m is determined by the same eligibility
  rule as before and cannot be moved. This is load-bearing: a larger m *raises*
  z\* and makes leg 1 easier, so the rule that sets m must be frozen alongside
  the rule that reads it.
- Both legs are required, and both are printed whether they pass or fail.
- Nothing above was chosen after seeing a result under the amended rule, because
  no such result exists. The single number quoted from an existing run
  (3.865σ) is quoted as a check that the new rule does not retroactively fail a
  run that passed under the old one — it does not — and not as the reason for
  any threshold. Setting α to make 3.865 pass would have been the rationalisation
  this file exists to catch; α = 0.01 puts z\* at 4.9605, which 3.865 clears by a
  margin nobody had to choose.

### Recording note

Recorded **before the code that implements it** and before any acceptance run is
executed under the amended criterion. The next `dc_native` issuance is the first
run gated by it.

---

## A1-C1 — arithmetic correction to A1 (2026-08-19)

**A1's original text above is deliberately unedited.** This ledger is
append-only for the same reason it exists at all: an entry that can be quietly
rewritten after the fact is not a record of what was decided in advance. Three
arithmetic statements in A1 are wrong. Each is corrected here. **A1's ruling —
D11 v1.0.1, the 2e-2 hard ceiling, the 5e-3 flag — is unchanged by all three,
and the pre-stated ceiling is still 2e-2.**

**1. "It is 4× the worst fixture observed at the opener (0.005365)."** It is
**3.7279×** — `0.02 / 0.005365`. The ratio was rounded up rather than computed.
(`0.005365` is a particle-mean over 1,000 particles; A1 did not record a
Monte-Carlo error for it and none is invented here. The correction is to the
division, not to the estimate.)

**2. "a mis-scaled rate — λ around 20 — excludes roughly half the mass and would
trip it by more than an order of magnitude."** A Poisson mean of 20 puts
**98.92%** of its mass past 10 goals — `P(X ≥ 11 | λ = 20) = 0.989188`, exact,
not simulated — not roughly half. **The correction runs in the ceiling's
favour.** Such a fixture's excluded mass is at least `0.9892`, which is
**49.5×** the 2e-2 ceiling, or **1.69 orders of magnitude** over it. The guard
catches a mis-scaled rate **more** surely than A1 claimed, not less: A1
understated its own guard.

**3. "Median particle for the failing fixture | 1.9e-4 — four orders of
magnitude under the gate."** `5e-3 / 1.9e-4 = 26.3158`, which is **1.42 orders
of magnitude**. That table row should read *"about 26×, 1.4 orders under the
gate"*. It is still a large gap and still makes A1's point — the failing
fixture's typical particle is nowhere near the gate and a handful of extreme
particles carry the mean — but the point was overstated by two and a half orders
of magnitude.

**What does not change.** Not the ruling, not either threshold, not the
diagnosis (a cold-start artefact of a club with zero archive rows), not the
sensitivity table, and not the forecast A1 recorded — which R1 has since tested
out of sample and which held (retro §2, hole 2). Correction 2 strengthens A1's
justification for the ceiling; corrections 1 and 3 weaken two rhetorical
flourishes and leave the substance intact.

**Why a note and not an edit.** A1 was written to be checkable against the git
history as a decision made before the code and before any `dc_native` number
existed. Editing its numbers now — even to make them correct — would destroy the
property that makes it worth anything. The wrong figures stay where they were
written, with this note attached to them, and a reader can see both what was
claimed and what was true.

*A2, A3 and A1-C1 recorded 2026-08-19, all three before the code that implements
or corrects anything they describe.*

---

## A2-N1 — harness v2 hashes, and one deviation from A2 (2026-08-19)

**A2's original text above is deliberately unedited**, for the reason A1-C1
gives: an entry that can be rewritten after the fact is not a record of what was
decided in advance. This note records the one thing A2 said it could not state
in advance, and one thing A2 said would not happen and did.

### The v2 hashes

The Fix commit that implements A2 changes `epl/simretro.py` and
`epl/simmetrics.py`. Their SHA-256 as committed:

| file | harness v1 (frozen by the prereg) | harness v2 |
|---|---|---|
| `epl/simretro.py` | `2b25ab35…` | `f1744c25172f84875522f134ac73284ddc1ba965f50edc402f4b0677a5763f9f` |
| `epl/simmetrics.py` | `e73f2f70…` | `6756d86143425a2b55785c0c0be49839bf981b10e54857abda9272831217a7a4` |

A run whose harness hashes match neither the v1 pair nor this v2 pair refuses,
exactly as prereg §12 already requires. **R1 stands under v1** and is not
re-scored; A2 gives the reasons in full and none of them has changed.

Note that the v2 harness carries its own identity into every ledger row and into
the resume key (`producer_identity`), so a ledger written under v1 and one
written under v2 can no longer be mixed by accident — which is the point of A2
(a), and which also means the hashes above are enforced per row rather than only
verified once at the top of a run.

### The deviation: TRPS now carries a Monte-Carlo error

A2 pre-stated, under *What is pre-stated*: **"A TRPS Monte-Carlo error is not
part of v2."** It said supplying one is a change to the metric set rather than a
relabelling, put it out of scope, and recorded it as an open item so that the
relabel would not be mistaken for having answered it.

**The Fix commit supplies one anyway.** That is a deviation from a pre-statement
and it is recorded here rather than made quietly.

*What was added.* A `TRPS SE` column, and a `trps_se` field on every scored row.
The method is the delta method on the run's own per-cell cluster-by-particle
standard error: with `X` the cumulative forecast, `O` the cumulative outcome and
`g = dTRPS/dm` evaluated at the reported matrix,

```
g[c, k] = 2 / (C (R−1)) · Σ_{r ≥ k} (X[c, r] − O[c, r])
Var(TRPS) ≈ Σ_{c, k} g[c, k]² · se[c, k]²
```

*What the number is not.* The cells of one club are treated as independent. They
are not — a club's row sums to 1, so its cells are predominantly **negatively**
correlated — and ignoring those covariances **overstates** the variance. The
reported SE is therefore conservative rather than exact. It is Monte-Carlo error
only: it says nothing about model error, and nothing about TRPS being proper for
the displayed marginals rather than for the joint law. It is `n/a` for the
nulls, which record no per-cell error.

*Why it is a deviation and not a new amendment.* Nothing about the metric SET
changes: TRPS is still the primary score, computed by the same formula on the
same matrices, and no pass rule reads the new number. What changes is that a
headline number now has an error beside it, which is this project's standing
rule everywhere else. A2's own reason for deferring it — that it is a change of
substance rather than of labelling — is correct, and this note is the substance
being declared instead of assumed.

*What is NOT claimed.* No score in
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) gains an SE
retroactively. R1 ran under harness v1, which computed none, and the column is
`n/a` for that run by construction. The first retrospective run that reports a
TRPS SE will be the first run under v2, and there is not one yet.

### Column names

A2 pre-stated the headings `cons-cell MC SE (mean)` and `cons-cell MC SE (max)`.
They are `mean cell SE` and `max cell SE`. The rename is cosmetic and the legend
carries the full sentence A2 required — that both are cluster-by-particle error
over the club × consequence cells, that neither is an error on TRPS, and that
neither is the position matrix's own error — but the exact strings differ from
the pre-statement and that is said here rather than left to a reader to notice.

*Recorded 2026-08-19, immediately after the commit that produced the hashes.*
