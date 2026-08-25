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
**≈49.46×** the 2e-2 ceiling, or **1.69 orders of magnitude** over it. The
guard catches a mis-scaled rate **more** surely than A1 claimed, not less: A1
understated its own guard.

*In-place fix, 2026-08-20 — to A1-C1's own arithmetic.* As written on 2026-08-19
that ratio read **49.5×**. `0.989188 / 0.02 = 49.4594`, so the figure was rounded
**up** — the same fault correction 1 records against A1, a ratio quoted rather
than computed, repeated inside the note correcting it. It is fixed above in
place, to **≈49.46×**, rather than by a further note: A1-C1 *is* the correction
note, and a correction of a correction of a correction is a worse record than a
fixed number whose history is stated here. Nothing else moves.
`log10(49.4594) = 1.6942`, so **1.69 orders of magnitude** was and remains
right, and neither the ruling, the 2e-2 ceiling nor the 5e-3 flag depends on the
second decimal. Found by a read-only reviewer (Codex review of `a18c845` #5).

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

---

## A2-N2 — A2 (b) was not enforced on the path that runs it (2026-08-19)

**A2's and A2-N1's text above are deliberately unedited**, for the reason
A1-C1 gives. This note records a defect in the Fix commit that implemented A2 —
found by a read-only verifier reading that commit — the change that closes it,
and the harness hashes it produces.

*Arithmetic note: every number in this entry is an exact count of ledger rows or
of grid cells. Nothing here is estimated, so nothing here carries a Monte-Carlo
error. The R1 scores quoted elsewhere are unchanged and carry whatever error
their own report records beside them.*

### The observation

A2 (b) pre-states `n_expected` as **"the requested (season, cutoff) cells"** and
the flag as True only when `n_checked + n_documented_refusals == n_expected`,
with `n_checked > 0` and no violations. The Fix commit implements exactly that —
and only when the caller passes `expected_cells`. Two things then left the
identity unable to fail on the path that actually produces rows.

**The grid was derived from the answer.** With `expected_cells` at its default,
`score_retro` set `cells` from the rows it had just been handed
(`n_expected_source = "derived from the rows supplied"`). Every row present is
then a cell expected, so `n_checked == n_expected` holds **by construction** and
any subset closes its own accounting. `_cli` — the only in-repo caller — called
`score_retro(rows)` with neither argument, and the new test drove only the
explicit-`expected_cells` branch, so the suite was green across the gap.

**Documented refusals never left `run_retro`.** `run_retro` returned only rows
that are not `not_applicable`, so `n_documented_refusals` was **structurally
zero** on that path: a cell the runner declined *and wrote a reason for* was
indistinguishable from a cell that was lost, and the accounting could not close
on a correct run even with the grid stated.

Measured, before the change:

| what was scored | `n_expected` | `n_checked` | `n_missing` | doc. refusals | `complete` | beats flat everywhere | `STOP_AND_INSPECT` |
|---|---|---|---|---|---|---|---|
| the real 170-row R1 ledger, default path | 34 | 34 | 0 | 0 | **True** | **True** | **False** |
| one cell of a two-cell request | 1 | 1 | 0 | 0 | **True** | **True** | **False** |

The first row is a run **eight cells short of its preregistered 42**, reporting
that its accounting closes. That is A2 (b)'s own sentence — *"reported True on
ANY non-empty subset — one surviving cell of a preregistered twenty-eight"* —
reproduced under v2. A separate check confirmed the second half directly: a run
in which the runner declined one null wrote **1** `not_applicable` marker to the
ledger and returned **0** of them.

### The ruling (owner, 2026-08-19)

**Harness v2.1.** Both halves are fixed in `epl/simretro.py`, under TDD, each
with a positive control.

1. **The request is stated, never derived.** A new `requested_cells()` returns
   the (season, cutoff) grid a `run_retro` call with the same arguments would be
   asked to fill; `run_retro` and it share one normalisation (`_grid`) so the
   two sides of the identity cannot drift apart. `_cli` states its grid.
2. **An unstated grid certifies nothing.** With `expected_cells` absent,
   `n_expected` and `complete` are `None` — *not evaluated*, which is not the
   same as *complete* and not the same as *incomplete* —
   `dc_native_beats_flat_everywhere` is `False`, and `STOP_AND_INSPECT` is
   `True`. The report prints **NOT EVALUATED** and says why. Cells derived from
   the rows are still scanned for a missing ARM inside a cell that is present,
   which is a hole visible without knowing the grid.
3. **`run_retro` returns the `not_applicable` markers** beside the forecasts, so
   a documented refusal reaches the accounting that exists to count it.
   `score_retro` still skips them when scoring.

**A2's flag is unchanged and is now enforceable.**
`dc_native_beats_flat_everywhere` is still a strict boolean, still True only
under A2's three conditions. What changed is that the third condition can now
fail.

**The R1 record STANDS, and is not re-scored.** Every reason A2 gives holds:
v2.1 changes no scoring arithmetic. Held against the fixed harness, the R1
ledger reads:

| grid stated | `n_expected` | `n_checked` | `complete` | beats flat everywhere |
|---|---|---|---|---|
| none (the default path) | `None` | 34 | `None` — not evaluated | False |
| the preregistered grid | 42 | 34 | **False** | False |
| the admissible cells R1 scopes its numbers to | 34 | 34 | **True** | **True** |

Against the preregistered grid the harness now **names** the eight missing
cells, and they are exactly the two refusals
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) §2 reports before any
score: all six cutoffs of 2023/24 (`UnverifiedAdjustment`), and the 2019/20 and
2020/21 openers (D11's truncation ceiling, amendment A1). Against the 34
admissible cells the accounting closes and the hard check is True.

So **no R1 number and no R1 claim changes.** A2 justified not re-scoring R1
partly on the assertion that *"R1's own `checked` = 28 is already the whole
admissible grid, so the completeness identity's answer for R1 is known and is
`True`"* — an assertion that was correct and that no code could check when it
was written. It is now checkable, and it checks out. What changes is that the
scope has to be **stated** for the flag to be True at all; R1 stated its scope in
prose, on its first page, before any score, which is why the two readings agree.

### The v2.1 hashes

| file | v1 (frozen by the prereg) | v2 | v2.1 |
|---|---|---|---|
| `epl/simretro.py` | `2b25ab35…` | `f1744c25…` | `e449c78d96dffa663b9feccbcbb4f291f63d4452a34081bbdd68306afff91bff` |
| `epl/simmetrics.py` | `e73f2f70…` | `6756d861…` | `6756d86143425a2b55785c0c0be49839bf981b10e54857abda9272831217a7a4` (unchanged) |

`epl/simmetrics.py` is untouched by this change, so v2.1 is the **pair**
(`e449c78d…`, `6756d861…`). A run whose harness hashes match none of the pairs
recorded here refuses, exactly as prereg §12 requires. The producer identity
that v2 puts in every ledger row and in the resume key is a digest over these
files, so a v2 ledger and a v2.1 ledger cannot be mixed by accident either —
which is why the fix does not, and could not, alter a stored row.

### Recording note

Recorded immediately after the Fix commit that produced the hashes. The
behaviour is held by four tests in `epl/tests/test_simretro.py`:
`test_completeness_is_not_derived_from_the_rows_it_was_handed`,
`test_run_retro_returns_the_documented_refusals_it_wrote`,
`test_requested_cells_is_the_grid_run_retro_fills`, and — where the gitignored
ledger is present in the checkout —
`test_the_real_r1_ledger_does_not_certify_itself`, which asserts the three rows
of the R1 table above against the artifact itself.

---

## A2-N3 — R1's TRPS gains a Monte-Carlo error after the fact (2026-08-19)

**A2's, A2-N1's and A2-N2's text above are deliberately unedited**, for the
reason A1-C1 gives. This note records a **second** deviation from A2's TRPS-SE
pre-statement — and one that a reader of A2-N1 alone is told did not happen.
A2-N1 declared the first deviation and, in the same breath, promised that the
already-published R1 report would not acquire the number. It has. That is
recorded here, in the ledger, because a deviation declared only inside the
document that deviates is not on the record; this file **is** the record.

*Arithmetic note: every number in this entry is an exact count of cells in a
table that already exists. Nothing here is estimated, so nothing here carries a
Monte-Carlo error of its own. The TRPS values and errors it points at carry the
errors that addendum prints beside them.*

### The observation

A2-N1, under *What is NOT claimed*, says verbatim:

> No score in `reports/epl_sim_retro_v1_1.md` gains an SE retroactively. R1 ran
> under harness v1, which computed none, and the column is `n/a` for that run by
> construction. The first retrospective run that reports a TRPS SE will be the
> first run under v2, and there is not one yet.

At HEAD, [`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) carries an
**Addendum A — TRPS Monte-Carlo error per cell**, added the same day, which
supplies exactly that. The report declares the departure itself, in a paragraph
headed *Relation to amendment A2-N1* — prominently and honestly — but it
declared it only where the departure happened. The ledger, whose entire purpose
is to hold what was pre-stated against what departed from it, still told a
reader the opposite.

### What Addendum A supplies

An error beside every scored R1 cell — numeric where the run stored a per-cell
error, `n/a` where it did not:

| | count |
|---|---|
| (season, cutoff) cells scored by R1 | **34** |
| scored (cutoff, season, arm) cells in the addendum's tables | **166** (136 comparison + 30 MW28, the same accounting §2 gives) |
| …carrying a numeric `±` (`dc_native`, `dc_wdl_bridge`, `elo_wdl_bridge`) | **102** |
| …carrying `± n/a` (`flat` 34, `ppg_pointmass` 30) | **64** |
| absent, shown `—` (`ppg_pointmass` at MW0, the `not_applicable` markers) | **4** |
| per-cutoff mean rows, each with the MC error of the mean | **6** cutoffs, **29** arm-cells (18 numeric, 11 `n/a`) |

The method is the delta method A2-N1 already records, applied to `matrix_se` —
the cluster-by-particle per-cell error every R1 row already stored.

### Why this is a deviation, and from what

From **two** pre-statements, not one:

1. **A2**: *"A TRPS Monte-Carlo error is **not** part of v2."* A2-N1 already
   declared one deviation from this — v2's harness computes a TRPS SE. Addendum
   A is a second, distinct one: the number is now attached to a run that
   predates v2 entirely.
2. **A2-N1 itself**, quoted above. That sentence is now false of HEAD. It stays
   where it was written, unedited, and this note is attached to it — the same
   treatment A1-C1 gave A1's arithmetic, and for the same reason: an entry that
   can be quietly rewritten after the fact is not a record of what was decided
   in advance.

### What is preserved

Everything A2-N1's sentence was protecting, except the sentence:

- **R1's body is untouched.** Not one TRPS, wTRPS, Brier, CRPS, coverage, mean,
  bootstrap interval, count or hash in §1–§10 has moved. The commit that added
  the addendum removes **zero** lines from that file — it is a pure append, and
  that is checkable in the diff, not merely asserted.
- **Harness v1 still computed no TRPS SE.** The addendum changes nothing about
  what the R1 run did. The R1 ledger `data/epl/sim/retro_r1.jsonl` is unchanged
  and no stored row was rewritten; the errors were already in it.
- **Nothing is presented as something R1 reported.** These are figures computed
  after the fact, by a later formula, from stored per-cell errors — an addendum,
  not a revision, and labelled as one on its first line.
- **No pass rule reads them.** There is none to read (prereg §7). R1's §10
  ruling, the published-arm question and R1's own two hard checks (retro §6)
  are all unchanged by the addendum, and would be unchanged if it were deleted.

### Why a note and not an edit

Editing A2-N1 to say the opposite of what it said would remove the only thing
that makes this ledger worth reading: that a reader can see what was claimed and
what turned out to be true, in that order, against the git history. A2-N1's
sentence was written in good faith and was overtaken within the day. It stays
wrong, in place, with this attached.

### Recording note

Unlike A1-C1, A2 and A3 — written before the code they govern — this note is
written **after** the thing it records, and that lateness is the defect it
closes. The addendum was committed in `31dac41` with its deviation declared in
its own prose; a read-only verifier reading that commit found the ledger had not
been updated to match, which is how the gap surfaced. This entry decides
nothing: no threshold moves, no pre-statement is amended, no flag changes, and
R1's record stands exactly as A2-N2 leaves it.

The invariant is now held by a test rather than by diligence:
`test_the_amendment_ledger_records_the_addendum_s_deviation` in
`epl/tests/test_retro_addendum.py` reads both files and fails if the addendum is
present without this note, or if A2-N1's original sentence is edited away rather
than superseded; `test_the_check_fails_when_the_ledger_does_not_record_the_deviation`
is its positive control.

*Recorded 2026-08-19, in the commit that responds to that finding.*

---

## A3-N1 — leg 2 is demoted to a diagnostic (2026-08-20)

**A3's original text above is deliberately unedited**, for the reason A1-C1
gives. This note demotes one half of A3's ruling — before the code that
implements the demotion — and records that A3's own defence of both legs
asserted a direction it had not computed.

*Arithmetic note: every figure in this entry is exact arithmetic on the normal
or chi-square distribution — no simulation, so nothing here carries a
Monte-Carlo error of its own. The one figure quoted from a run (3.865σ) is a
standardised deviation the 2026-08-21 acceptance record reports; it carries
whatever error that record states beside it and is not re-estimated here.*

### The observation

Two findings from a read-only reviewer, one against each leg.

**Leg 2's reference distribution is not the one leg 2 refers to** (Codex review
of `a18c845` #3). A3 lists four reasons `Σ Z²` is not exactly `χ²_m` and then
asserts a direction — *"the net of these slacks makes leg 2 marginally **easier**
to pass"*. That direction was asserted, not computed, and two of its own inputs
make the assertion unsafe:

- **The compared cells are correlated, twice over.** *Within* a fixture the
  scoreline cells are multinomial: an excess in one cell forces a deficit in the
  others, and the home/draw/away triple is an exact linear combination of
  scoreline cells already in the sum. *Across* fixtures the same particle set
  and the same simulated seasons drive every cell, so the deviations do not
  decorrelate between fixtures either. `Σ Z²` is a quadratic form in a dependent
  vector; its null is `χ²_m` only if that vector is m independent standard
  normals, and it is not.
- **The per-cell denominator is estimated, and floored.** `Z` divides by
  `max(cluster SE, binomial SE)` (`epl/simcanary.py:532`) — a random quantity
  bounded below, not a known constant — so each term is a squared ratio of two
  estimates rather than a squared standard normal.

Dependence does not simply make a quadratic form easier to pass. Positive
dependence **inflates** the variance of `Σ Z²` and fattens its upper tail
relative to `χ²_m`; the within-fixture multinomial pulls the other way; nobody
has computed the net. `p > 1e-3` is therefore a threshold on a distribution that
has not been calibrated, and setting it loose does not repair a wrong reference —
it only makes the miscalibration harder to notice.

**Leg 1's headline arithmetic is an iid reference, not the gate's error rate**
(Codex review of `ce82484` #1). A3 quotes **0.9010** expected exceedances and

```
P(at least one cell beyond 4σ) = 1 − (1 − 6.334e-05)^14225 = 0.5939
```

as what a correct sampler does under the **old** 4σ rule. Both figures assume
the m cells are independent, and the dependence that breaks leg 2 is the same
dependence those two numbers were computed without. They are exactly right as
what they are — the **iid reference for m cells** — and they were more than
enough to establish A3's point, that a per-cell 4σ threshold at m = 14,225 is not
a gate. They are not the family-wise error rate of any rule this project runs.

### The ruling (owner, 2026-08-20)

**Leg 2 is DEMOTED from pass/fail to a reported diagnostic.** `Σ Z²`, `df = m`
and the nominal p are still computed on every run and still printed beside `m`,
`z*` and `max|Z|` — all six, whether leg 1 passes or fails, exactly as A3
requires. What changes is that **no run passes or fails on the last three**. The report
labels the trio *diagnostic — the reference distribution is not calibrated*, and
`marginal_parity`'s verdict is leg 1 alone. `DEFAULT_CHI2_MIN_P` stops being a
threshold and becomes the p below which the diagnostic is flagged for a human to
look at; it is not an acceptance criterion and the acceptance record says so.

**Leg 1 REMAINS the criterion, unchanged.** A cell fails if
`|Z| > z* = Φ⁻¹(1 − α/(2m))` with **α = 0.01** and m the cells actually compared
in that run; at m = 14,225, `z* = 4.9605`. `min_expected_count` stays **25.0**,
for the reason A3 gives: m must be frozen by the same rule that reads it.

**Leg 1's error under dependence, in both directions, because A3 stated only
one.**

- **Conservative direction.** `P(any |Z| > z*) ≤ α` is Boole's inequality and
  holds whatever the dependence — *provided each cell's Z is marginally standard
  normal*. Positive dependence, which is what sharing one particle set across
  fixtures produces, pushes the realised family-wise rate strictly below α, and
  the more so the stronger it is. A3's *"conservative under the dependence
  documented above"* is right about this half.
- **Anti-conservative direction — WITHDRAWN as stated, 2026-08-20 (Codex review
  of `7b9d7d1` #5).** This bullet read: *"Measured against the iid figure this
  ledger quotes, negative dependence runs the other way: for negatively
  associated cells `P(at least one exceedance)` can exceed the product form
  `1 − (1 − p)^m`. The within-fixture multinomial is exactly such negative
  association, so the rule is slightly anti-conservative relative to the iid
  reference."* The inference does not hold. Negative association bounds
  `P(∩ A_i) ≤ Π P(A_i)` for events that are **coordinatewise increasing** (or
  all decreasing) in the underlying counts, and the events here are
  `|Z_i| > z*` — TWO-SIDED exceedances, which are increasing in `|count −
  expected|` and neither increasing nor decreasing in the counts themselves. The
  multinomial's negative association therefore says nothing about them in this
  form, and the direction claimed **is not supported**. It is not replaced by
  the opposite claim: the direction of the departure from the iid reference is
  simply **not established** here. What does stand, and is unaffected, is the
  Bonferroni bound — the realised family-wise rate is at most α under ANY
  dependence — and that is the only guarantee leg 1 is asserted to have.
- **And marginal normality is itself an approximation.** The floor on the
  denominator deflates `|Z|` (conservative). A cell's count is discrete and
  right-skewed, and at `z ≈ 5` its true upper tail is not guaranteed to be
  bounded by the normal's (anti-conservative). The ≥25-expected-count rule
  limits this and does not remove it.
- **Neither direction has been computed.** Both are recorded because the
  honest statement of leg 1 is *a bound whose slack is unknown in sign*, not
  *a conservative rule*.

**Calibrating it properly is v1.2, and the path is pre-stated here.** A
**parametric-bootstrap null of the sampler**: B independent re-simulations of
the same fixture set, at the same fitted posterior and the same particle book,
differing only in seed, each pushed through the identical `marginal_parity`
path against the same production reference. The null distributions of `max|Z|`
and of `Σ Z²` are read off that ensemble, and the acceptance thresholds — a
`max|Z|` quantile, and a restored leg-2 threshold if the ensemble supports one —
are set from its quantiles instead of from a closed form that does not apply.
**B, the quantile and the acceptance rule are NOT chosen here**; they are
pre-stated in v1.2's own amendment, written before the bootstrap runs, in this
file. What is fixed here is only that the calibration is done this way and that
leg 2 cannot gate anything until it is.

**The 2026-08-21 issuance is unaffected, and still passes leg 1.** Its worst
cell, **3.865σ** over 14,225 compared cells, is below `z* = 4.9605` by
**1.096σ**. It was gated by neither leg — it ran under the 4σ rule
preregistered for it — and **no run has yet been gated by leg 2 at all**, so
this demotion withdraws no verdict, changes no published number and re-opens no
closed acceptance. The next `dc_native` issuance is the first run gated by
leg 1 as amended, and the first to print leg 2 as a diagnostic.

### The rationale

A3's whole case against the 4σ rule was that a gate whose null nobody had
calibrated is not a gate. Leg 2 was written in the same breath and has the same
defect: a statistic referred to a distribution it does not follow, with a loose
threshold standing in for a calibration. Keeping it as a pass/fail criterion
while its reference is known to be wrong would repeat the error the amendment
exists to correct, and would be worse than the 4σ rule was, because a loose
uncalibrated gate fails silently in the direction of passing.

Demoting rather than deleting keeps the number in front of the reader. The
failure mode leg 2 was built for — a uniform, small mis-scaling that never
produces a single dramatic cell — is real, and `Σ Z²` still points at it even
when its p-value cannot be trusted to three decimal places. A diagnostic that is
printed and read is worth more than a threshold that is passed without being
believed.

Recording both directions of leg 1's slack is the same discipline. A3 wrote
*"conservative under the dependence documented above"*, which is true of one of
the two dependences it had just documented and not of the other. The correct
sentence is longer and less comfortable, and it is the one that survives review.

### What is pre-stated

- **Leg 1 is the criterion; leg 2 is a diagnostic.** α = 0.01, the `z*(m)`
  formula, and `min_expected_count = 25.0` are unchanged from A3 and unchanged
  here. No threshold moves in this note.
- **All six numbers are still printed on every run** — `m`, `z*`, `max|Z|`,
  `χ²`, `df`, `p` — with the last three labelled as an uncalibrated diagnostic.
- **0.5939 and 0.9010 are the iid reference for m cells**, and are not claimed
  as the family-wise error rate of any rule.
- **The v1.2 calibration path is the parametric bootstrap described above**, and
  its constants are pre-stated in a later entry, before it runs.
- Nothing here was chosen after seeing a result under it: no run has been gated
  by either leg, and the one figure quoted from an existing run (3.865σ) is
  quoted, as A3 quoted it, to show that nothing retroactively fails.

### Recording note

A3's two-legged rule **is implemented at HEAD** (`epl/simcanary.py`, committed
in `eba5585`): at the moment this is written, leg 2 can still fail a run. This
note is recorded **before the commit that demotes it**, and before any run is
gated by either leg.

---

## A2-N4 — the TRPS SE is a diagonal approximation, and "conservative" is withdrawn (2026-08-20)

**A2's, A2-N1's, A2-N2's and A2-N3's text above are deliberately unedited**, for
the reason A1-C1 gives. This note withdraws a claim A2-N1 made about the number
it declared, and A2-N3 carried forward: that the delta-method TRPS standard
error is *conservative*. It is not known to be.

*Arithmetic note: this entry states a variance identity and the sign of its
omitted terms. It estimates nothing, so it carries no Monte-Carlo error of its
own. Every TRPS SE it relabels keeps the value it already has; the numbers do
not move, only the claim about which way they err.*

### The observation

Codex reviews of `97ab5d0` #3 and `e5ec1cc` #3, independently, against the same
sentence. A2-N1 records the estimator as

```
g[c, k] = 2 / (C (R−1)) · Σ_{r ≥ k} (X[c, r] − O[c, r])
Var(TRPS) ≈ Σ_{c, k} g[c, k]² · se[c, k]²
```

and then says: *"The cells of one club are treated as independent. They are not
— a club's row sums to 1, so its cells are predominantly **negatively**
correlated — and ignoring those covariances **overstates** the variance. The
reported SE is therefore conservative rather than exact."*

The premise is right and the conclusion does not follow. The exact delta-method
variance is the full quadratic form

```
Var(TRPS) ≈ Σ_{(c,k)} Σ_{(c',k')} g[c, k] · g[c', k'] · Cov(m[c, k], m[c', k'])
```

and the estimator keeps only the terms with `(c, k) = (c', k')`. What is dropped
is `g · g' · Cov`, not `Cov`. The gradient has **mixed signs**: with `O` the
cumulative outcome, `X[c, r] − O[c, r]` is non-negative for ranks below the
club's realised position and non-positive at and above it, so `g[c, k]` is
positive for some k and negative for others **within the same club's row**. A
negative covariance multiplied by two gradient components of opposite sign
contributes a **positive** term to the variance. The omitted total is therefore
of undetermined sign, and the diagonal sum can be an over- **or** an
under-estimate of the delta-method variance it approximates.

The error is one of vocabulary rather than of arithmetic — no computed number is
wrong — but "conservative" is exactly the word a reader uses to decide whether a
tight SE can be trusted, and it was not earned.

**Dated rigor note, 2026-08-20 (Codex review of `7b9d7d1` #4) — the ARGUMENT
above is withdrawn; the CONCLUSION stands.** The paragraph infers that `g[c, k]`
has mixed signs within a club's row from the signs of `X[c, r] − O[c, r]`. That
does not follow: `g[c, k]` is a REVERSE CUMULATIVE SUM, `Σ_{r ≥ k} (X[c, r] −
O[c, r])`, not the summand, and a sum of terms of mixed sign need not change sign
as `k` moves. Two rows of any R1 matrix are immediate counterexamples. For the
club that finished **first**, `O[c, r] = 1` for every `r ≥ 1`, so every summand is
`≤ 0` and every `g[c, k]` is `≤ 0` — no sign change anywhere in the row. For the
club that finished **last**, `O[c, r] = 0` for every `r < R`, so every summand up
to `R` is `≥ 0` and the gradient does not change sign there either. Rows in the
middle of the table CAN produce a sign change. So counterexamples exist in both
directions and **no sign claim is made** about the omitted covariance total.

The conclusion A2-N4 draws is unaffected and is reaffirmed here: the estimator
drops `g · g' · Cov` rather than `Cov`, the dropped total's sign is **not
determined** by anything computed, and the diagonal sum can be an over- or an
under-estimate of the delta-method variance. What is withdrawn is the *proof by
gradient sign*, which was not a proof. "Conservative" remains withdrawn — for the
stronger reason that nothing establishes the direction, rather than for the
weaker one that the gradient argument establishes the opposite.

### The ruling (owner, 2026-08-20)

**1. The quantity is relabelled.** It is the **diagonal approximation** to the
delta-method Monte-Carlo variance of TRPS, and it is reported as
`TRPS MC SE (diagonal approx.)`. The accompanying sentence, wherever this
project states it, becomes: *the cross-cell covariance is omitted, and because
the TRPS gradient changes sign within a club's row the omitted terms can raise
or lower the variance — the direction of the approximation is not known.*

**2. The word "conservative" is WITHDRAWN** wherever this project applies it to
this number: A2-N1's *"conservative rather than exact"*, the harness
legend that prints the same phrase, `epl/simmetrics.py`'s docstring, and
Addendum A's *"Conservative, not exact"* bullet in
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md). Those sentences stay
where they were written, unedited, for A1-C1's reason; this entry is what
withdraws them, and a dated note in the retrospective report points a reader of
Addendum A here.

**3. Future runs that retain per-season rows compute the TRPS MC SE by
cluster-by-particle bootstrap of TRPS itself.** Resample the particles — the
same cluster the stored per-cell `matrix_se` is already built on — with
replacement, recompute the position matrix and recompute TRPS on each resample,
and report the standard deviation of the resampled TRPS values. That estimator
needs no independence assumption, no gradient and no covariance matrix, and it
is an error on TRPS rather than an error propagated from the cells. It requires
the per-particle position tallies to be retained, which is why it is stated as a
requirement on the runs that retain them rather than as something the existing
ledger can be made to answer. **B and the resampling seed are not chosen here**;
they are pre-stated in the amendment that accompanies the first run to report
the bootstrap SE, before that run.

**4. Addendum A's numbers STAY, relabelled.** Not one of the 102 numeric `±`
figures in [`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) Addendum A
changes: the arithmetic that produced them is unchanged and remains correct as
the diagonal approximation it is. What is withdrawn is the bullet claiming they
overstate. A dated note in that report records the withdrawal in place, beside
the numbers it qualifies, so a reader of the addendum alone is not left with the
retracted sentence — the failure mode A2-N3 was written to close, applied in the
other direction.

**5. R1's record is untouched, again.** No score moves, no pass rule reads a
TRPS SE (prereg §7 leaves none to read), and every conclusion in
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) §1–§10 is unchanged by
this note and would be unchanged if the addendum were deleted.

**6. The code still carries the withdrawn word at the moment this is written**,
including the test that pins the phrase `conservative rather than exact`
(`epl/tests/test_simretro.py:818`). Changing the harness text, its docstring and
that test is the Fix commit that follows this entry, under TDD, and this entry
is recorded before it.

### The rationale

This project's standing rule is a Monte-Carlo error beside every headline. A
number reported under that rule is read as *how far this could move*, and the
adjective attached to it decides which way a reader leans when it looks small.
"Conservative" says *lean safe*. Nothing established that, and two reviewers
reading independently reached the same objection from the same three lines.

The diagonal approximation is worth keeping. It is cheap, it is computed from
errors the ledger already stores, and it is the right order of magnitude for
what it measures — the retrospective's own numbers put it one to two orders of
magnitude under the between-season spread, which is the comparison that actually
matters when reading a score. What it cannot support is a claim about its own
direction, and the fix is to stop making one rather than to withdraw the number.

The bootstrap is the estimator that answers the question the delta method was
approximating, and it is stated here as a requirement on future runs precisely
because it cannot be applied retroactively: R1's ledger stores per-cell errors,
not per-particle tallies. Saying so plainly is better than implying the existing
figures could be upgraded in place.

### What is pre-stated

- The label is **`TRPS MC SE (diagonal approx.)`**, and the sentence that
  accompanies it states that the omitted covariance **can raise or lower** the
  variance.
- **"Conservative" is withdrawn** of this quantity in the harness, in the
  metrics docstring, in Addendum A and in A2-N1 — by this note, not by editing
  any of them.
- Future runs retaining per-season rows report a **cluster-by-particle bootstrap
  of TRPS itself**; the resampling unit is the particle, and B is pre-stated in
  the amendment accompanying the first run that reports it.
- **No number changes.** Addendum A's figures, R1's body, and every score in
  this project stand exactly as issued.

### Recording note

Recorded **before the commit that changes the harness text, the metrics
docstring and the test that pins the withdrawn phrase**, and before any run
reports a bootstrap TRPS SE. The dated note in
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) is written in the same
commit as this entry, so the ledger and the report cannot disagree about the
withdrawal for even one commit — which is the specific defect A2-N3 records.

---

## A4 — harness v3: typed refusals, and completeness on every path (2026-08-20)

**Decision amended:** A2 (a) and A2 (b) as amended by A2-N2 — the producer
identity, the resume/provenance guard, and the completeness identity
`n_checked + n_documented_refusals == n_expected` — implemented in
`epl/simretro.py` at the harness **v2.1** pair
(`e449c78d…`, `6756d861…`).
**Status of the amendment when written:** not a line of `epl/simretro.py` or
`epl/simmetrics.py` has changed since A2-N2; both still hash to the v2.1 values
recorded there. R1 is still the only retrospective run that exists, and it ran
under **v1**.

*Arithmetic note: every number in this entry is an exact count of arms, cells or
ledger rows, or a SHA-256. Nothing here is estimated, so nothing here carries a
Monte-Carlo error. No score is quoted, computed or changed.*

### The observation

Six findings from read-only reviews of the commits that built, repaired and
recorded this accounting (`97ab5d0`, `ba8eca5`, `e5ec1cc`). Two are already closed; four are open at HEAD. All six are
listed, with their status, because the ruling below is one design and it has to
answer all of them.

| # | finding | source | status at HEAD |
|---|---|---|---|
| 1 | the default/CLI path derived the expected grid from the rows it was handed, so any subset closed its own accounting | `97ab5d0` #1 | **closed** by v2.1 (A2-N2): unstated ⇒ `n_expected = None`, `complete = None`, `STOP_AND_INSPECT = True`, and `_cli` states its grid |
| 2 | `run_retro` filtered `not_applicable` rows out of its return, so `n_documented_refusals` was structurally zero on the real path | `97ab5d0` #2 | **closed** by v2.1 (A2-N2): the markers are returned beside the forecasts |
| 3 | a missing **required** arm is counted as a "documented refusal" | `ba8eca5` #1 | **OPEN** |
| 4 | whole-cell refusals — season construction, runner exceptions — escape the accounting entirely | `ba8eca5` #2 | **OPEN** |
| 5 | rows with no producer identity are exempt from the provenance guard | `e5ec1cc` #2 | **OPEN** |
| 6 | an unrecorded harness hash is not refused | `e5ec1cc` #1 | **OPEN** |

**3 — the harness writes its own alibi.** When the runner returns a cell without
an arm, `run_retro` writes a `not_applicable` marker for it with the reason
`"{arm} is not defined at {label}"` — for **any** arm, including the required
`dc_native` and the always-defined `flat`. The runner is never asked whether it
refused; its silence is converted into a documented refusal by the caller. An
accidentally dropped `flat` therefore yields a marker, a "documented refusal",
and — if some other cell passes — `complete = True`,
`dc_native_beats_flat_everywhere = True` and `STOP_AND_INSPECT = False` on a run
that has silently lost the comparison the whole retrospective exists to make.
The test that covers this path omits `flat` on purpose and expects closure, so
an accidental omission is indistinguishable from the fixture.

**4 — the refusals that matter most cannot reach the accounting.** The two
refusals R1 actually hit are `UnverifiedAdjustment` (`epl/season.py:581`, all six
cutoffs of 2023/24) and `ExcludedMassTooLarge` (`epl/particles.py:629`, the
2019/20 and 2020/21 openers, amendment A1). Both are raised *inside* the cell,
before any row is written, and both propagate out of `run_retro`. Nothing writes
a marker; the cell is simply absent, and the accounting can only report it as an
undocumented hole. R1's eight missing cells are documented in **prose**, in the
report, by a human — which is exactly the class of guarantee this ledger exists
to convert into a check.

**5 — the guard's own escape hatch.** The provenance refusal skips rows whose
`producer` is absent (`row.get("producer") not in (None, me)`), and an absent
`producer` is precisely the v1 schema. A v1 ledger is therefore appended to
silently by a v2, v2.1 or later run, without the override that exists to make
mixing deliberate. The keys cannot collide — a v1 key has no producer segment,
so it can never satisfy a v3 request — but the file ends up holding two
producers' rows with nothing recording it.

**6 — the hash rule is stated, not enforced.** A2-N1 and A2-N2 both say *"a run
whose harness hashes match none of the pairs recorded here refuses, exactly as
prereg §12 requires."* `producer_identity()` hashes both files at run time and
folds the digest into the key and every row — which makes rows from different
harnesses non-interchangeable, and is genuinely worth having — but it never
compares those hashes to the recorded pairs. A fresh ledger under an arbitrarily
modified harness runs to completion and reports nothing unusual. The
preregistration's §12 invalidation condition has no code behind it.

### The ruling (owner, 2026-08-20) — pre-stated before the code

**Harness v3.** Four changes in `epl/simretro.py`, under TDD, each with a
positive control: every guard must be shown refusing the thing it exists to
refuse, not merely accepting a good run.

**(i) Typed refusals, written by the runner, counted by the scorer.**

The runner writes a **typed refusal marker row** for every refusal it raises or
catches. The row carries a `refusal_kind` from a closed set, and free-form
`reason` text beside it:

| `refusal_kind` | written when |
|---|---|
| `excluded_mass_ceiling` | `ExcludedMassTooLarge` — D11's 2e-2 hard ceiling (A1) |
| `unverified_adjustment` | `UnverifiedAdjustment` — a points adjustment the season ledger has not verified |
| `arm_not_defined` | an arm or null that does not exist at this cutoff by rule (`ppg_pointmass` at MW0) |
| `runner_error` | any other exception from season construction, the fit, the simulation or the runner |

`score_retro` counts **only typed markers** as documented refusals. A row with
`not_applicable` text and no `refusal_kind` is not a documented refusal; it is a
hole. **An absent required arm — `dc_native` or `flat` — with no typed marker
gives `complete = False` and `STOP_AND_INSPECT = True`**, whatever else passed.
The caller stops inventing reasons on the runner's behalf: `run_retro` no longer
manufactures a marker for a missing arm it was not told about.

Whole-cell failures are caught **at the cell boundary**, and a marker of the
matching kind is written for every requested arm of that cell before anything
propagates. `excluded_mass_ceiling`, `unverified_adjustment` and
`arm_not_defined` are expected refusals: the marker is written and the run
continues, as it does today. `runner_error` is not expected: the marker is
written **and the exception is re-raised**, so an unexplained failure still stops
the run — the marker exists so the hole is named in the ledger and can be seen
by the resumed run, not so that an unknown error can be swallowed.

**(ii) The expected grid is always the schedule, on every path.**

`n_expected` is the **request**, and the request is `seasons × cutoffs × arms` —
a (season, cutoff, **arm**) triple, not a (season, cutoff) pair. `requested_cells`
returns triples for the same arms and nulls the matching `run_retro` call was
given, and both the CLI and the default path pass it. The identity becomes

```
n_scored + n_typed_refusals == n_expected        (triples, not cells)
```

with `n_scored > 0` and zero violations, all three required for `complete`.
`dc_native_beats_flat_everywhere` stays a strict boolean over the cells where
both required arms scored, and is `False` unless `complete` is `True`.

When a caller supplies no grid, `score_retro` does **not** derive one from the
rows and does **not** return "not evaluated": it uses the **whole preregistered
schedule** — every season, every cutoff label, every arm and null. That is the
most demanding grid available, so an unstated request can only ever report more
missing, never fewer, and the v2.1 `None` / NOT EVALUATED branch is retired
because nothing can reach it. A smoke run scored without stating its grid will
therefore read incomplete against the full schedule, correctly; `_cli` states its
grid and reads exactly what it asked for.

**(iii) A row with no producer is refused.**

The provenance guard treats an absent `producer` as foreign. A ledger holding
legacy rows refuses the run — by name, listing the offending keys — unless
`--allow-legacy-rows` (`allow_legacy_rows=True`) is passed, which is recorded on
every row the run writes, recorded in the run's envelope and **printed in the
report**, exactly as the existing foreign-producer override is. The two overrides
are counted separately in the sanity block.

**(iv) `run_retro` refuses to start under an unrecorded harness.**

Before any fit, `run_retro` compares the SHA-256 of `epl/simretro.py` and
`epl/simmetrics.py` against the **recorded pairs**, and refuses — a named error —
unless the running pair is one of them. The recorded pairs are exactly the pairs
written in this ledger:

| version | `epl/simretro.py` | `epl/simmetrics.py` | recorded in |
|---|---|---|---|
| v1 | `2b25ab35…` | `e73f2f70…` | the preregistration §1 |
| v2 | `f1744c25…` | `6756d861…` | A2-N1 |
| v2.1 | `e449c78d…` | `6756d861…` | A2-N2 |
| v3 | *appended as a dated note after the Fix commit* | *idem* | this entry |

The list lives in a module constant that the Fix commit updates, and **the code's
list must equal this ledger's list** — a test reads this file and fails if they
diverge, the same shape of check that already holds A2-N3's note against
Addendum A. Development and the test suite necessarily run under unrecorded
hashes; they pass an explicit `allow_unrecorded_harness=True`, which is recorded
on every row written and printed in the report, and a run that used it is not a
citable run. There is no silent path.

**R1 and Addendum A stand under v1.** Nothing in
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) is re-scored, for every
reason A2 gives and A2-N2 re-checks: v3 changes no scoring arithmetic — it is
four guards and one accounting unit. **v2 and v2.1 were never used for a
published run**; no report in this repository cites a number produced under
either. v3 will be the first harness after v1 to produce a published
retrospective number, and the first retrospective run under it is the first run
that can report `complete = True` against a stated triple-level grid.

**Nothing else in the retrospective changes.** Not the question, the grid, the
seasons, the cutoffs, the arms, the nulls, the pairings, the metrics or the pass
rules. TRPS stays primary and unweighted; wTRPS stays secondary; the paired
differences stay a diagnostic with no pass rule; scores are still never averaged
across cutoffs.

### The rationale

Findings 3 and 4 are the same defect seen from both ends. The harness was asked
to distinguish *refused on purpose* from *lost by accident*, and it was given no
information with which to do it — so it guessed, and it guessed in the direction
of "documented". A refusal is a fact the runner knows and the scorer does not;
the only fix that can work is to make the runner say so, in a typed field, and
to make the scorer believe nothing else. Every other arrangement reduces to the
caller writing the alibi for the callee, which is what finding 3 is.

Moving the accounting unit from the cell to the (season, cutoff, arm) triple is
the smaller half of the same point. A cell is "present" as soon as one arm in it
scored; the thing that gets lost is an arm, and until the unit of the identity
is the arm, the identity cannot see the loss. A2 (b) chose the cell because the
refusals it had in mind were whole-cell refusals — which is exactly finding 4,
and both are answered by the same change.

Findings 5 and 6 are guarantees this ledger has now asserted three times in
prose. A2-N1 wrote that v1 and v2 rows "can no longer be mixed by accident";
A2-N2 repeated it for v2.1; both sentences were true of the key and false of the
guard, because the guard exempts the only rows a v1 ledger contains. The hash
rule has been stated since the preregistration and has never had code behind it.
The pattern is the one this file was created to catch — a guarantee stated in a
document, satisfied in fact, and unenforced in code — and the answer is the same
each time: put the check where the claim is.

Making the default grid the **whole** preregistered schedule, rather than
"not evaluated", is the conservative choice in the direction that costs
something. It means a casual `score_retro(rows)` on a partial ledger prints a
long list of missing triples and `complete = False`. That is noisier than a
`None`, and it is the right noise: an unstated request is not a licence to
certify, and the failure it produces is loud, specific and easy to correct by
stating the grid.

### What is pre-stated

Fixed here, before the code exists and before any v3 run exists:

- **The four refusal kinds are exactly** `excluded_mass_ceiling`,
  `unverified_adjustment`, `arm_not_defined`, `runner_error`. The set is closed;
  adding a fifth is an amendment.
- **Only typed markers count as documented refusals.** An absent `dc_native` or
  `flat` with no marker ⇒ `complete = False` **and** `STOP_AND_INSPECT = True`.
- **`n_expected` is `seasons × cutoffs × arms`**, stated by the caller on every
  path, defaulting to the whole preregistered schedule and never derived from
  the rows. The identity is `n_scored + n_typed_refusals == n_expected`, with
  `n_scored > 0` and no violations, all three required.
- **A producer-less row refuses the run** unless `allow_legacy_rows` is passed,
  and the override is recorded on every row, in the envelope and in the report.
- **An unrecorded harness pair refuses the run before any fit**, with no silent
  override; the recorded list in the code must equal the list in this entry, and
  a test enforces that equality.
- **`runner_error` re-raises after writing its marker.** The other three kinds
  let the run continue.
- The **v3 hashes** are the one thing this entry cannot state in advance; they
  are appended here as a dated note by the commit that creates them, exactly as
  A2-N1 and A2-N2 did for v2 and v2.1.

No threshold above was chosen after seeing a result under it, because no result
under harness v3 exists, and the only run this ledger describes — R1 — ran under
v1 and is not re-scored.

### Recording note

Written **before any line of `epl/simretro.py` changed under this ruling**; both
harness files were re-hashed at the moment of writing and still match the v2.1
values in A2-N2. The commit that changes them follows this one.

### The v3 hashes, and what landed (recorded 2026-08-20, immediately after the Fix commit)

**A4's text above is deliberately unedited**, for the reason A1-C1 gives: an
entry that can be rewritten after the fact is not a record of what was decided
in advance. This note records the one thing A4 said it could not state in
advance — the v3 hashes — and three places where the code that landed differs
from the wording of the ruling.

*Arithmetic note: every number in this note is an exact count of ledger rows or
grid triples, or a SHA-256. Nothing here is estimated, so nothing here carries a
Monte-Carlo error. No score is quoted, computed or changed.*

#### The v3 hashes

The Fix commit changes `epl/simretro.py`, `epl/simmetrics.py` and
`epl/retro_addendum.py`, and adds `epl/retro_harness_versions.json`. The harness
pair's SHA-256 as committed:

| version | `epl/simretro.py` | `epl/simmetrics.py` | recorded in |
|---|---|---|---|
| v3 | `6fc293dfc6abb463f3345bd0894ad0c02ba61e7613cb62b5bb5fba38abaa0576` | `6f5390092b2cef3a92d2dcedb6ec954545a2e9a891011414c79fc68d0bb0189b` | this note, and `epl/retro_harness_versions.json` |

A run whose harness hashes match none of the pairs recorded here refuses, as
prereg §12 requires — and, for the first time, refuses in code rather than in
prose. **R1 stands under v1** and is not re-scored; **v2 and v2.1 were never
used for a published run.**

#### Deviation 1 — the list is a data file, not a module constant

A4 (iv) says "the list lives in a module constant that the Fix commit updates".
It does not, and it cannot: appending a version to `epl/simretro.py` changes
that file's own SHA-256, so the entry being appended is invalidated by the act
of appending it. The recorded pairs live in `epl/retro_harness_versions.json`,
which `epl.simretro.recorded_harness_versions()` reads and which no hash covers.

The substance A4 asked for is unchanged and is enforced:
`test_the_recorded_harness_list_in_the_code_equals_the_one_in_the_ledger` parses
the tables in THIS entry — the ruling's table and the one above — and fails if
the versions or the hashes diverge from the JSON, which is the same docs/code
coupling that holds A2-N3's note against Addendum A.

#### Deviation 2 — two renames, stated rather than left to be noticed

A2-N1's *Column names* section exists because a pre-stated string differed from
the one that shipped. The same two things happened here.

* `score_retro`'s `expected_cells` keyword is **`expected_triples`**. A4 (ii)
  did not name the keyword; passing triples to something called `expected_cells`
  is precisely the drift this ledger exists to catch.
* The sanity block renames `n_checked` → **`n_scored`** and
  `n_documented_refusals` → **`n_typed_refusals`**, as A4 requires, and adds
  **`n_cells_compared`** beside them — the number of cells where BOTH required
  arms scored, which is what `dc_native_beats_flat_everywhere` ranges over and
  which the pre-statement did not name. It is a count, not a threshold, and no
  flag reads it that did not already read the same quantity under its old name.

One boundary is worth stating because it is not perfect. A marker's key is built
from the cutoff DATE, so a failure to resolve the SCHEDULE itself has no key to
be written under and propagates unmarked. Everything downstream of the schedule
— the realised table, the fit, the simulation, the runner — is marked. An
unmarked schedule failure still stops the run and still reads as an undocumented
hole in the accounting; what it does not get is a named row.

#### Deviation 3 — `trps_se_cluster` exists and nothing calls it

A2-N4 (3) requires future runs that retain per-season rows to report a
cluster-by-particle bootstrap of TRPS itself. `epl.simmetrics.trps_se_cluster`
is that estimator, landed here with tests: it resamples particles with
replacement, recomputes the position matrix and recomputes TRPS on each
resample. **`n_boot` and the seed are required arguments with no defaults**,
because A2-N4 pre-states that B and the resampling seed are chosen in the
amendment accompanying the first run that reports the number — a default here
would be that choice, made by this module, after the fact. No ledger row in this
repository stores per-particle tallies, so nothing in the harness calls it and
no number in this project comes from it.

#### R1 re-read under the triple unit — and it no longer closes

A2-N2 recorded a three-row sanity table for the R1 ledger under the CELL unit.
Held against v3 the same 170-row artifact reads:

| grid stated | `n_expected` | `n_scored` | `n_typed_refusals` | `complete` | beats flat everywhere |
|---|---|---|---|---|---|
| none (the default path) | 210 | 166 | 0 | **False** | False |
| the preregistered schedule, as triples | 210 | 166 | 0 | **False** | False |
| the admissible cells R1 scopes its numbers to, as triples | 170 | 166 | 0 | **False** | False |
| the 166 triples R1 actually scored | 166 | 166 | 0 | **True** | **True** |

Row three is the change, and it is the change A4 predicted in its own words:
*"the first retrospective run under v3 is the first run that can report
`complete = True` against a stated triple-level grid."* R1's four
`ppg_pointmass`-at-MW0 markers carry `not_applicable` TEXT and no
`refusal_kind`, because v1 wrote no typed field — so under A4 (i) they are holes
rather than documented refusals, and the admissible grid is four triples short.
The eight whole-cell holes the harness names are unchanged and are still exactly
the two refusals [`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) §2
reports before any score: all six cutoffs of 2023/24 (`UnverifiedAdjustment`)
and the 2019/20 and 2020/21 openers (D11's ceiling, amendment A1).

**No R1 number and no R1 claim changes.** R1 stands under v1, is not re-scored,
and every conclusion in §1–§10 of its report is untouched. What changes is that
a harness that can tell a refusal from a loss now says, of a v1 ledger, that it
cannot tell — which is the honest answer and the reason A4 exists.

#### Recording note

Recorded immediately after the Fix commit that produced the hashes. The
behaviour is held by seven tests in `epl/tests/test_simretro.py` —
`test_only_a_typed_marker_the_runner_wrote_is_a_documented_refusal`,
`test_a_whole_cell_refusal_is_typed_for_every_requested_arm`,
`test_an_unexpected_error_is_marked_and_then_re_raised`,
`test_the_expected_grid_is_the_schedule_on_every_path`,
`test_a_producer_less_row_refuses_the_run_unless_it_is_allowed`,
`test_run_retro_refuses_an_unrecorded_harness_before_any_fit` and
`test_the_recorded_harness_list_in_the_code_equals_the_one_in_the_ledger` —
each of which drives its guard RED on the thing the guard exists to refuse, and
by `test_the_real_r1_ledger_does_not_certify_itself`, which asserts the four
rows of the table above against the artifact itself where it is present.

### The v4 hashes — set-identity completeness, marker legality, sealed overrides (recorded 2026-08-20)

A round-2 Codex review of the v3 Fix commit (`b5aa609`) and of the commit that
recorded v3 (`cdd8879`) found four defects in what A4 ruled and one in how it
was recorded. All five are fixed in the commit this note accompanies, which
therefore produces a NEW harness pair. R1 stands under v1 and is not re-scored;
**v4 has not been used for a published run.**

*Arithmetic note: this note quotes two SHA-256 values and counts of rows. No
score is quoted, computed or changed by it.*

| version | `epl/simretro.py` | `epl/simmetrics.py` | recorded in |
|---|---|---|---|
| v4 | `7aabbd7822c29f4628c03012cf3fad1df4bcd9a2e37b5e770cdaff680880d321` | `53c11eb14ff93e156595bfd69991250d820731926d2073c7047a8e7d21cde58d` | this note, and `epl/retro_harness_versions.json` |

**What v4 changes, and why each was wrong under v3.**

1. **Completeness is a SET identity.** A4 (ii) states the identity as
   `n_scored + n_typed_refusals == n_expected`, and cardinality cancels: a
   triple carrying both a score and a typed refusal is counted on both sides,
   paying for exactly one undocumented hole somewhere else. Two scored rows plus
   one overlapping refusal against three expected triples closed the accounting
   over a grid with a cell missing — `identity_holds`, `complete`, and
   `dc_native_beats_flat_everywhere`, all true, all wrong. The union of the
   scored triples and the typed refusals must now BE the expected set, with an
   empty intersection; `n_overlapping` and the offending triples are reported
   and are STOP-worthy.

2. **A marker's KIND must be true of its ARM.** `arm_not_defined` means "no such
   arm here by rule", and this harness has exactly one such rule:
   `ppg_pointmass` needs three complete rounds (prereg §4). v3 validated the
   kind for membership in the closed set and never as a claim, so `flat` — a
   constant matrix, defined at every cutoff — could be labelled
   `arm_not_defined` at MW10 and the accounting would close over the missing
   comparison. `epl.simretro.CONDITIONAL_ARMS` names the arms that may carry
   that kind; the check runs when a marker is written AND when a ledger is
   scored, since a ledger can arrive from a run this process did not make. The
   other three kinds are unrestricted, and must be: `unverified_adjustment` and
   `runner_error` are facts about a season or a failure, and
   `excluded_mass_ceiling` is marked for every arm of a refused cell.

3. **The override flags are inside `envelope_hash`.** `allow_foreign_producer`,
   `allow_legacy_rows` and `allow_unrecorded_harness` were set after the row was
   hashed, so override provenance could be added to or removed from any row
   without invalidating a hash — and that provenance is the entire reason the
   overrides are permitted. The flags are folded into the row's envelope hash at
   append time; a row with no override is unchanged, so nothing already written
   moves.

4. **A persisted `runner_error` stays STOP-worthy.** The marker is written and
   the exception re-raised, so the run that wrote one did not finish — but
   `run_retro` skips occupied keys on resume, so the cell is never retried and
   the marker becomes an ordinary documented refusal that closes the accounting.
   `score_retro` now reports `n_runner_errors` and sets `STOP_AND_INSPECT`
   whenever one is present, whatever the completeness verdict says. (This is the
   contract A4 did not require and Codex `7b9d7d1` item 2 asked for.)

5. **A version key names ONE pair.** `cdd8879` claimed exact equality between
   this ledger's list and `epl/retro_harness_versions.json`, but both sides of
   the test collapsed into a version-keyed dictionary, and a dictionary keeps
   the last of a repeated key — so a rogue second `v3` entry, inserted before
   the legitimate one and matching a mutated harness, was overwritten out of the
   comparison while the runtime membership test accepted it.
   `recorded_harness_versions()` now refuses a repeated version outright, and
   the test counts both lists without collapsing them.

**Recording note.** Recorded in the same commit as the code that produced the
hashes, which is what makes the entry citable rather than a promise. The
behaviour is held by five new tests in `epl/tests/test_simretro.py` —
`test_completeness_is_a_set_identity_and_an_overlap_cannot_pay_for_a_hole`,
`test_an_arm_not_defined_marker_for_an_always_defined_arm_is_refused`,
`test_the_override_flags_are_covered_by_the_envelope_hash`,
`test_a_persisted_runner_error_marker_stays_stop_worthy_on_resume` and
`test_the_harness_version_list_refuses_a_duplicate_version_key` — plus
`test_the_bootstrap_refuses_a_tally_with_the_right_total_and_wrong_margins`,
which closes a fifth Codex finding in `epl/simmetrics.py`: the bootstrap checked
each particle's total tally mass and not its per-club and per-rank margins, so a
tally in which two clubs both finished first — and one rank was occupied by
nobody — carried the right total and resampled into a matrix whose columns do
not sum to one, which `trps` scores without complaint.

### The v5 hashes — a validated, identified, span-aware truth (recorded 2026-08-20)

Amendment **A6 (a)** — ruled and recorded at `38830a2` before the code existed —
changes what `run_retro` validates, what its key and seal cover, and what the
scorer compares a forecast to. The commit this note accompanies implements it and
therefore produces a NEW harness pair. The note lives **here**, inside A4,
because A4 (iv)'s version list lives here and
`test_the_recorded_harness_list_in_the_code_equals_the_one_in_the_ledger` reads
this entry and no other; A6 (a.5) states that rule and deliberately does not
restate the list, since a second copy is a list the test does not read.

**The record lands in the same commit as the code it identifies.** A6 (a.5) says
these hashes cannot be stated *in advance* — a file's own SHA-256 cannot be
written into that file — which is why the list is a data file the harness reads.
It does not say they may be stated in a *later* commit, and they may not: the
test above asserts that HEAD's own pair is one of the recorded ones, so a commit
that changes the harness without recording it is red at that assertion, and every
code commit in this project is green. Code and record therefore arrive together —
the shape `cdd8879` used when it introduced that assertion together with the v3
pair satisfying it.

**R1, Addendum A and Addendum B stand under v1 and v3 and are not re-scored.
v5 has not been used for a published run.**

*Arithmetic note: this note quotes two SHA-256 values and exact counts of ledger
rows, clubs and scored components. Nothing here is estimated, so nothing here
carries a Monte-Carlo error. No score is quoted, computed or changed by it.*

| version | `epl/simretro.py` | `epl/simmetrics.py` | recorded in |
|---|---|---|---|
| v5 | `d64bef11ea3cefa32f585eb2e6749465a9acbbb6de54981ddf96f52dcf7eea1d` | `b03d4fbcda4b4f6405ee165acc8a2786e79f0ef37111e6369f199d7dca32c5a4` | this note, and `epl/retro_harness_versions.json` |

**What v5 changes, and why each was wrong under v4.**

1. **The realised archive is validated before it is ranked** (A6 (a.1)). v1–v4
   checked non-empty and no duplicate ordered pair. A duplicate check cannot see
   a MISSING pair, so a 379-result archive produced a perfectly normal-looking
   20-club truth, ranked and scored, while the schedule still held 380 fixtures
   and the forecasts simulated the match the table never counted
   (`gate-retro.md` #2, `ranker.md` #1). `realised_positions` now requires
   exactly 20 clubs **as an equality** — an archive may not define its own league
   by leaving one out — exactly 380 played results, and the 380 ordered pairs to
   BE the complete double round-robin, which subsumes the duplicate check and
   adds the missing-pair case. Failure raises the typed
   `IncompleteRealisedArchive`; `_refusal_kind` classes it `runner_error`, so the
   markers naming the cells are written and the exception is re-raised and the
   run stops. This closes for the realised archive the hole `ranker.md` #3
   reports in `leaguesim.simulate`, and closes it **there only**: A6's table says
   so and this note repeats it rather than letting the fix look wider than it is.

2. **The truth is in the key and in the seal** (A6 (a.2)). `realised_hash` is the
   SHA-256 of the canonical JSON of the season, the sorted results, the sorted
   adjustments, the boundaries and the rule id — the adjustments because one
   moves the table without moving a result, the boundaries and the rule because
   they decide what a tie means. Its first twelve hex are a `|t…` segment of
   `run_key` and the hash joins the row's `envelope_hash` payload, so a row
   scored against one archive cannot satisfy a request under another and a
   resumed run that meets a changed archive re-runs instead of mixing. The
   segment sits **before** the producer segment and is **omitted** when there is
   no truth to name: every key ever written still ends `|p…`, and a refusal
   marker for a season whose truth could not be built is keyed exactly as it was.
   `score_retro` reports `realised_hash_by_season` and sets `STOP_AND_INSPECT`
   when one season carries two distinct values. A pre-A6 row carries no hash and
   reads as one unknown truth, which is why the published ledger raises no stop.

3. **Scoring is span-aware, and the rule is the ranker's own** (A6 (a.3)). The
   realised outcome is a matrix `O[c, j] = 1/k_c` across the club's realised
   block — `epl/table.py`'s stated *"a block of k clubs spanning k positions
   takes 1/k of each"*, which `leaguesim._mass_chunk` already applies to the
   forecast side. `_score_one` reads the `span` every ledger row has stored since
   v1 and that the scorer never read (`ranker.md` #2). A forecast reproducing the
   ranker's own 0.5/0.5 split across a realised 17–18 tie now scores **zero** on
   TRPS and on the relegation Brier, where v4 charged it `2 × 0.25 / (20 × 19)`
   for being right. `O` is held to the two margins the forecast matrix is held
   to; v4's point-mass outcome for a tie fails them — rank 18's column sums to 0
   and rank 17's to 2 — and the code now refuses to build it rather than scoring
   against it.

**Why no published number moves, measured rather than asserted.** `O` reduces to
v4's step function exactly when every span is 1. Read off
`data/epl/sim/retro_r1.jsonl` as committed, on 2026-08-20: **190** scored rows,
**3,800** club-spans (190 × 20) **all equal to 1**, `realised.n_shared == 0` on
**every** row, and **1,520** scored components (190 rows × 8 — TRPS, wTRPS, flat
TRPS, the TRPS MC SE, the Brier block, `beats_flat`, the champion log loss and
the points block) re-derived through `epl.simretro._score_one` under v5 and
compared to the same rows with the `span` field dropped, which is v4's input
because v4 never read it: **0 moved**.
`test_v5_reduces_to_v4_on_the_published_R1_ledger` performs that comparison and
carries a positive control — one real published row given a realised 17–18 tie it
did not have, whose TRPS then moves — so "unchanged" is a fact about this
ledger's spans and not a property of the comparison. The same figures are stated
as a dated note at the foot of
[`reports/epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md).

**What this note does not claim.** It records a harness pair and an arithmetic
result. It rules on nothing: A6 is the ruling, this is the recording A6 (a.5)
said could not be written in advance.

---

## A5 — the 2023/24 points adjustments are attested and verified (2026-08-20)

**Decision amended:** none. D16's scoring gate is unchanged in code and
unchanged in force; what changes is the state of four DATA rows it reads.
**Status of the amendment when written:** the flip is authorised and the four
rows are edited in the same commit as this note; no retrospective run under the
verified rows exists yet.

*Arithmetic note: this entry quotes four integers that are points deductions and
four dates. Nothing here is estimated and no score is computed, quoted or
changed by it.*

### The observation

R1 refused all six cutoffs of 2023/24 with `UnverifiedAdjustment`
([`epl_sim_retro_v1_1.md`](epl_sim_retro_v1_1.md) §2, Hole 1). The three
effective rows for that season were seeded `verified: false` by plan v2 D16,
and D16 and adjudication item 3 both assign the check to a human against
premierleague.com. R1 correctly declined to flip them, and said so in the
report: *setting `verified: true` is an attestation … doing it to unblock a run
would convert the guard into decoration.*

### What was done, and by whom — stated exactly

1. **The assistant did the verification work.** Each of the four rows in
   `epl/season/points_adjustments.jsonl` was checked against the Premier
   League's own published statement — the size of the deduction, the date it
   was known, whether it took effect immediately, and whether it replaced an
   earlier deduction or added to one. The assistant then presented the owner an
   evidence table mapping each row to its statement, recommended the flip, and
   asked for explicit words.
2. **The owner authorised the flip.** In the transcript of 2026-08-20 the owner
   replied, verbatim: **"Yes — mark the four 2023/24 deduction rows verified."**
   That sentence is the authorisation and nothing more is claimed for it: the
   owner did not personally compare the rows to the published record, and this
   note must not be read as saying so.

The four rows, with the statement each was checked against:

| id | delta | known_at | supersedes | published statement |
|---|---|---|---|---|
| `adj-2324-everton-01` | **−10** | 2023-11-17 | — | [premierleague.com/en/news/3788486](https://www.premierleague.com/en/news/3788486) — 17 Nov 2023, "immediate deduction of 10 points" |
| `adj-2324-everton-02` | **−6** | 2024-02-26 | `adj-2324-everton-01` | [premierleague.com/en/news/3912574](https://www.premierleague.com/en/news/3912574) — 26 Feb 2024, the Appeal Board "substituted the original points deduction of 10 for six", immediate effect |
| `adj-2324-nottm-forest-01` | **−4** | 2024-03-18 | — | [premierleague.com/en/news/3936397](https://www.premierleague.com/en/news/3936397) — 18 Mar 2024, four points, immediate |
| `adj-2324-everton-03` | **−2** | 2024-04-08 | — | [premierleague.com/en/news/3960088](https://www.premierleague.com/en/news/3960088) — 08 Apr 2024, two points, immediate, a separate breach |

Net at the end of the season: **Everton −8** (the −6 that replaced the −10, plus
the separate −2) and **Nottingham Forest −4**. Everton finish **15th**, Forest
**17th**.

### What changed in the repository

Only the four rows. `id`, `delta`, `known_at` and `supersedes` are byte-for-byte
what they were — the attestation records a CHECK, it does not restate the
ledger — and each row gains three fields that make the flag answerable rather
than decorative:

* `"verified": true`
* `"verified_at": "2026-08-19"` — the day the assistant did the checking
* `"verified_by"` — one sentence naming who checked, against what, and the
  owner's authorising words quoted in full
* `"source_url"` — the statement that row was checked against

`epl/season.py`, `epl/simretro.py` and every other module are untouched.

### The guard is still live, and is still driven RED

Flipping the only unverified rows in the repository would have left
`test_unverified_adjustment_rows_refused_for_scoring` with nothing to refuse —
a canary that cannot fail, which is the failure mode this project treats as a
bug rather than a pass. The refusal path is therefore driven on a **synthetic**
unverified row from here on, in a temporary ledger root, with the real ledger
appearing only as the control that says the guard is not simply always firing:

* `epl/tests/test_season.py::test_unverified_adjustment_rows_refused_for_scoring`
  — synthetic row RED, then three positive controls: the same row verified
  scores, the same row with the gate opted out scores, and the real 2023/24
  ledger scores.
* `epl/tests/test_simretro.py::test_2023_24_scores_under_the_verified_gate_after_the_attestation`
  — the realised 2023/24 table under the DEFAULT gate (Everton −8 and 15th,
  Forest −4 and 17th), then a synthetic unverified row refusing the same call.
* `epl/tests/test_season.py::test_the_2023_24_rows_carry_the_attestation_that_verified_them`
  — the three attestation fields are asserted on all four rows, because a flag
  with no record of what it was checked against is what D16 exists to refuse.
* The 2023/24 archive assertions in `epl/tests/test_season.py` and
  `epl/tests/test_table.py` that had to pass `require_verified=False` to run now
  run with the gate ON.

### What this does NOT decide

Nothing about any arm. The retrospective's conclusions are not touched by this
note: it makes a season SCOREABLE that was refused, and the run that scores it —
and the addendum that reports it — is the commit that follows. Whether
`dc_native` remains the published arm is an owner ruling, unchanged and still
open (R1 §10).

### Recording note

Written in the same commit that edits the four rows and the tests, and before
the 2023/24 run. The evidence table above is the one the owner was shown.

### A5-N1 — the attestation is no longer self-supporting (recorded 2026-08-20)

**Decision amended:** none. No row, flag, date, URL or score changes here.

*Arithmetic note: this entry quotes no number that was computed. It records a
check and who performed it.*

**The gap.** A5 records that *the assistant did the verification work* and that
the owner authorised the flip on that basis. Everything in it is stated plainly,
including that the owner did not personally compare the rows to the published
record — but the CHECK itself then rested on a single agent's reading of four
web pages, and the only evidence that the reading was right was the same agent's
table. An attestation whose sole support is the party being attested for is
self-supporting, and that is the one property this ledger exists to prevent.

**What closed it.** In the review round this note accompanies, a SEPARATE
verifier agent — not the one that produced A5's table, and working from the four
`source_url` values in `epl/season/points_adjustments.jsonl` rather than from
A5's summary — independently re-fetched the four premierleague.com statements on
**2026-08-20** and reported that all four confirm the rows as recorded: the −10
of 17 Nov 2023, the Appeal Board's substitution of six for ten on 26 Feb 2024,
Nottingham Forest's −4 of 18 Mar 2024, and Everton's separate −2 of 08 Apr 2024,
each immediate and each matching its row's `delta`, `known_at` and `supersedes`.

**What this note is, exactly.** It is the record of that second reading, filed by
a third party — the author of this entry, who consolidated the review round's
findings and did **not** re-fetch the four pages personally. So the chain is now:
one agent checked and tabulated (A5), a second agent independently re-fetched and
confirmed (this note), the owner authorised on the record (A5), and a third wrote
it down. That is two independent readings rather than one, which is what "no
longer self-supporting" means here and all it means. It is still not a human
reading the league's pages, and A5's sentence about D16 — *whether that satisfies
D16 is a question about D16* — is unchanged and still open.

**Recording note.** Filed in the documentation commit of the round, dated rather
than folded into A5's own text, so that A5 remains the record of what was done
when it was written and this remains the record of what was added afterwards.

---

## A6 — harness v5, `check` semantics, the `observed_by` clarification, and the CRN pairing note (2026-08-20)

**Decisions amended:** three, all named.
(i) the retrospective harness contract of
[`reports/epl_sim_prereg_retro.md`](epl_sim_prereg_retro.md) §1 as it stands after
A2 (a) and A4 (i)–(iv) and the v4 note — what a run must validate, and what its key
and seal must cover;
(ii) the realised-outcome rule of that document's §5 and §6 — a shared realised
rank is reported and then scored as a point mass, and after this it is scored over
its span;
(iii) the issuance `check` contract of plan v2 T9 as it stands at
`epl-issuance-3`.
**(c) and (d) amend nothing.** (c) restates an invariant the plan already has and
the code does not implement everywhere; (d) corrects a DESCRIPTION of what the
sampler does, and changes no sampler, no threshold, no number and no rule.
**Status of the amendment when written:** not a line of `epl/` has changed under
this ruling. `epl/simretro.py` and `epl/simmetrics.py` still hash to the **v4**
pair recorded in A4's dated note. The committed opener issuance at
`data/epl/sim/issuances/2026_27/2026-08-21/` is byte-for-byte as published, R1 and
Addenda A and B are as published, and this entry changes no number in any of them.

*Arithmetic note: every number in this entry is an exact count of ledger rows,
clubs, fixtures or ordered pairs, or a SHA-256 read off — or recomputed from — a
committed file. Nothing here is estimated, so nothing here carries a Monte-Carlo
error. Two figures are QUOTED from the reviews and were not recomputed here; both
are marked where they appear. No score is computed, quoted or changed.*

### The observation

Six final-state, read-only composition reviews were run against clean `a2b1ead`
and kept outside the repository at `~/Desktop/codex-reviews/final-state/`. Five
produced findings — `engine-pricing.md`, `gate-retro.md`, `ranker.md`,
`live-ingest.md`, `live-forecast.md`. The sixth, `live-path`, returned **zero
bytes on both its attempt and its retry** (`_status.txt`), and the ground it was
given was covered instead by the two later reviews `live-ingest.md` and
`live-forecast.md`; that is stated here rather than left as a silent gap in the
count. All five that ran end **DO-NOT-SHIP**, each on composition — the modules
hold, and the paths that join them do not.

Their findings, deduplicated across files, with what this entry does about each.
The four that A6 rules on are the four the owner asked for; the rest are recorded
because a round whose findings are half-transcribed is not a record, and **nothing
below accepts them — an unruled finding is not an accepted one.**

| # | finding | where it is reported | A6 |
|---|---|---|---|
| 1 | `observed_by` bounds the state and the training frame and is then dropped when the DC fit builds its Elo covariates (`epl/dcfit.py:261`, called from `epl/simcli.py:231`) and when the Elo arm is built (`epl/simcli.py:486`); the empirical bridge filters on the cutoff alone (`epl/bridge.py:553`) | `engine-pricing.md` #1, `gate-retro.md` #1, `live-forecast.md` #1, `live-ingest.md` #1 | **(c)** |
| 2 | the engine checks a provider's self-reported dates and accepts a provider with no usable `describe()` (`epl/leaguesim.py:978`, `:1000`) | `engine-pricing.md` #1, `gate-retro.md` #1 | **(c)** |
| 3 | the retrospective's realised truth is neither complete nor identity-bound: `run_retro` checks only non-empty and no duplicate ordered pair (`epl/simretro.py:264`), so a 379-result archive ranks and scores as a normal 20-club season, and the truth is in neither the run key (`:599`) nor the envelope seal (`:699`) | `gate-retro.md` #2, `ranker.md` #1 | **(a)** |
| 4 | scoring discards the stored `span` (`epl/simretro.py:1096`): a realised 17–18 tie is scored as if both clubs were definitely 17th | `ranker.md` #2 | **(a)** |
| 5 | `check` verifies only the numerical fields; the full digest the record already carries is never read (`epl/simcli.py:1089`), so an edited `observed_by` inside a published output left every check passing | `gate-retro.md` #3 | **(b)** |
| 6 | the retained rows and the full per-fixture truncation vector are written (`epl/leaguesim.py:1456`) and excluded from the digest and the check (`epl/simcli.py:1337`) | `engine-pricing.md` #4 | **(b)** |
| 7 | `check` ignores `gate_PASS` and `acceptance.json` (`epl/simcli.py:462`, `:1242`), so an issuance that exited 3 on a failed gate can `check` PASS | `live-forecast.md` #3 | **(b)** |
| 8 | check-time parity passes `post=None` (`epl/simcli.py:1364`), so the reference is the book's own mixture and the production adapter is never called | `gate-retro.md` #4 | **(b)** |
| 9 | the native arm inverse-CDFs a scoreline grid (`epl/leaguesim.py:648`) while the bridge arms inverse-CDF H/D/A (`epl/bridge.py:454`), so sharing `u[0]` does not pair their outcomes | `engine-pricing.md` #3 | **(d)** |
| 10 | non-integral goals are coerced silently, on ingest (`epl/simcli.py:1491`) and at validation (`epl/leaguesim.py:733`) | `engine-pricing.md` #2, `live-forecast.md` #2 | not ruled here |
| 11 | the advertised ingest cannot create a ledger revision, and detected kickoff moves are not ingested (`epl/season.py:1054`, `:325`, `epl/simcli.py:1450`, `:1462`) | `live-ingest.md` #2, #3 | not ruled here |
| 12 | direct `leaguesim.simulate` validates 38 appearances per club and not the round-robin, so duplicated ordered pairs with matching missing pairs pass (`epl/leaguesim.py:1034`, `epl/table.py:517`) | `ranker.md` #3 | not ruled here — **(a)** closes the same hole for the retrospective's realised archive only, and says so |
| 13 | the cut-line headlines carry no Monte-Carlo error (`epl/simcli.py:1597`) | `engine-pricing.md` #5 | not ruled here |
| 14 | issuance writes are in place and `issuance.json` precedes `summary.md`, so an interruption leaves a stale or missing summary that is still selected as the last issuance (`epl/simcli.py:465`, `:469`, `:1784`) | `live-forecast.md` #4 | not ruled here |
| 15 | prohibited vocabulary in tracked forecast output and in one gate-criterion key | `engine-pricing.md` #6, `gate-retro.md` #5, `ranker.md` #4, `live-ingest.md` #4, `live-forecast.md` #5 | not ruled here — a rename of a JSON key is a schema/version bump with a backward-compatible read and its own dated note, per the standing rule |

### The ruling (owner, 2026-08-20) — pre-stated before the code

#### (a) Harness v5 — the realised archive is validated, identified, and scored over its own spans

**(a.1) `run_retro` validates the realised archive BEFORE it scores anything, and
refuses otherwise.** The check runs inside `realised_positions`, so every caller
gets it, and `run_retro` runs it once per season before the first fit of that
season:

* the club set is the season manifest's, and has **exactly 20** members; the set
  of clubs appearing in the archive rows must **equal** it, not be contained in
  it — an archive may not define its own league;
* there are **exactly 380** played results;
* the 380 ordered pairs are **exactly** the complete double round-robin
  `{(h, a) : h ≠ a}` — every ordered pair present once and none extra. This
  subsumes the existing duplicate check and adds the missing-pair case the
  duplicate check cannot see.

A failure raises a typed `IncompleteRealisedArchive` (a `RetroError`) naming the
counts and listing the missing and extra ordered pairs. It is a refusal to score,
not a `refusal_kind` marker: A4's markers document a cell that could not be run,
and this is a season whose truth is not a season.

**(a.2) The realised truth enters the run key and the envelope seal.**
`realised_hash` is the SHA-256 of the canonical JSON of
`{"season", "results": sorted [(home, away, hg, ag)], "adjustments": sorted
mapping, "boundaries", "rule_id"}` — the results **and** the adjustments, because
an adjustment moves the table without moving a result, and the boundaries and
rule id, because they decide what a tie means. Its first twelve hex become a
`|t…` segment of `run_key`, and the hash itself joins the row's `envelope_hash`
payload. A row scored against one truth then cannot satisfy a request under
another, and a resumed run that meets a changed archive stops instead of mixing.
`score_retro` reports `realised_hash` per season in its sanity block and sets
`STOP_AND_INSPECT` if any season carries two distinct values.

**No row is re-keyed.** R1's ledger stands exactly as it is; its rows could not
satisfy a v5 request in any case, because the producer segment A2 (a) put in the
key already changes when `epl/simretro.py` does.

**(a.3) Scoring becomes span-aware, and the rule is exactly the ranker's own.**
The realised outcome stops being a vector of integers and becomes a matrix
`O[c, j]` of the same kind and orientation as the forecast matrix. For club `c`
with realised block start `p_c` and block span `k_c`:

```
O[c, j] = 1 / k_c   for  p_c <= j <= p_c + k_c - 1
O[c, j] = 0         otherwise
```

That is exactly the allocation the ranker already makes for a simulated tie —
`epl/table.py`'s stated convention, *"a block of k clubs spanning k positions
takes 1/k of each"* (plan v2 D8), implemented in `leaguesim._mass_chunk` as
`inside / span`. `cumulative_outcome` becomes `cumsum(O, axis=1)[:, :-1]`, which
is the identical transformation `cumulative_forecast` applies to the forecast, and
`consequence_briers` takes the realised value of a consequence to be the mass `O`
puts inside that consequence's position slice — `y_c = Σ_{j ∈ slice} O[c, j]` —
which is fractional exactly when the tie straddles the boundary.

**The consequence, stated as the rule rather than left to be derived: a forecast
that matches the ranker's own allocation scores zero.** TRPS is
`Σ (O_cum − X_cum)² / (C·(R−1))`; a club forecast at 0.5/0.5 across a realised
17–18 tie has `X_cum = O_cum` at every boundary and contributes nothing, and its
relegation Brier is `(0.5 − 0.5)² = 0`. Under v4 that same forecast is charged for
being right. Two invariants are asserted on `O` on the way in, the same two the
forecast matrix is held to: every row sums to 1, and every column sums to 1 —
`table.check_doubly_stochastic` is run on the realised outcome matrix, because a
fractional allocation that is not doubly stochastic is not a table.

**(a.4) v5 reduces to v4 exactly when no realised tie occurred, and R1 + Addenda A
and B stand as published.** When `k_c = 1` for every club, `O` is a permutation
matrix and its cumulative is `(ranks >= p_c)` — precisely what
`cumulative_outcome` returns today — so every score is unchanged bit-for-bit.
**No realised tie occurred anywhere in the seven seasons.** Read off
`data/epl/sim/retro_r1.jsonl` on 2026-08-20 at `a2b1ead`: **190** scored rows,
`realised.n_shared == 0` on **every one of them**, and all **3,800** club-spans
(190 rows × 20 clubs) equal **1**. Re-scoring R1, Addendum A and Addendum B under
v5 would return the same numbers, so they are not re-scored, for the reason A2 and
A4 both give: the run of record is the run that ran.

**(a.5) The v5 hashes are the one thing this entry cannot state in advance.** They
are appended as a dated note **inside the A4 entry**, where A4 (iv)'s harness-
version list lives and where
`test_the_recorded_harness_list_in_the_code_equals_the_one_in_the_ledger` reads
it. A6 states the rule and deliberately does **not** restate the list: a second
copy of it in a second entry is a list the test does not read, which is the exact
shape of failure the v4 note's item 5 was written about.

**Nothing else in the retrospective changes.** Not the question, the grid, the
seasons, the cutoffs, the arms, the nulls, the metrics or the pass rules. TRPS
stays primary and unweighted; the paired differences stay a diagnostic with no
pass rule; scores are still never averaged across cutoffs.

#### (b) `check` semantics — what a PASS is allowed to mean

**A fourth verdict.** Beside `PASS`, `FAIL` and `REFUSED`, a criterion may report
**`UNANCHORED`**: *the record predates the field this criterion is held against.*
An `UNANCHORED` criterion did not run, claims nothing, and neither passes nor
fails the record. It is listed by name in `check`'s output and printed in the
report line. **It is not a passing criterion**: `check` gains a separate boolean
`fully_anchored`, false whenever the list is non-empty, and its headline reads
`PASS (n criteria unanchored: pre-A6 record)` so the boolean cannot be read
without the qualification.

**The new record fields arrive as `epl-issuance-4`**, with the leniency
conditioned on the schema exactly as `epl-issuance-2` and `-3` already condition
theirs: mandatory from `-4` on, and a `-4` record missing one **FAILs** that arm
naming the field. Earlier records are read as they are today and report
`UNANCHORED` for the criteria the missing fields anchor. The added fields are
`record_digest`, `sidecar_digests` (per arm: the retained-rows `.npz` and the
truncation `.json`), `acceptance_digest`, and `training_frame_sha256`. Nothing is
renamed and nothing is removed.

**(b.1) The full-record digest becomes part of what `check` verifies.** For each
arm, `check` reads the published `output_<arm>.json` off disk, drops only
`NON_REPRODUCIBLE_FIELDS` from its envelope, hashes the whole payload — matrix,
consequences, cut lines, `mc`, **and the envelope, including `observed_by`,
`provider_hash`, `effective_posterior_hash`, `git_commit` and
`results_snapshot_sha256`** — and requires it to equal `record["digests"][arm]`.
That anchor already exists in every record ever written; it was simply never
read, which is why `gate-retro.md` #3 could change a published `observed_by` to
`2099-01-01` and watch the check pass.

The record's own fields that no output carries — `published_arm`, `arms`, `files`,
`gate_PASS` — are covered by `record_digest`: the SHA-256 of the canonical JSON of
the whole record with exactly one field removed, `record_digest` itself. It is
written into `issuance.json` **and printed in `summary.md`**, and `check` requires
both copies to agree with the recomputation, naming which copy disagrees. **A6
states its limit rather than overselling it:** a digest a file carries about
itself is a checksum against accident, not a seal against an editor, and an editor
who updates every copy in the directory is caught by the repository history and by
nothing in the bundle. That is what the history is for, and saying so is cheaper
than a fourth copy.

`check` additionally requires each arm's envelope to agree with the record on the
ten fields both carry — `season`, `arm`, `cutoff`, `observed_by`, `seed`,
`n_sims`, `n_particles`, `chunk_size`, `n_played`, `results_lag` — a disagreement
being a `FAIL` naming the field. This is evaluable on every schema, since it
compares two things a bundle already has.

**(b.2) The two sidecars are anchored.** `sidecar_digests` records the SHA-256 of
`rows_<arm>.npz` and of `excluded_mass_<arm>.json` as written, and `check`
recomputes both. Independently of that anchor, and on every schema:

* the **retained rows** are re-derived — `check` already re-runs the arm — and the
  npz's ten arrays are compared to the re-run's `retained_rows.arrays()`
  element-for-element. A disagreement is a `FAIL`.
* the **truncation sidecar** must be internally and externally consistent: its
  `summary` must equal the `excluded_mass` block in the arm's envelope (which
  `digests[arm]` anchors), and `max`, `mean`, `p90`, `n_fixtures`, `n_flagged` and
  the flagged set must **recompute exactly** from its own `per_fixture` vector.
  When the envelope says `measured: false` the vector must be empty, and a
  non-empty vector under `measured: false` is a `FAIL`.

The residual is stated: a doctored per-fixture vector that preserves every
statistic the envelope carries is invisible to the recomputation and is caught
only by `sidecar_digests`, which is why the field exists and why its absence is
reported rather than shrugged at.

**(b.3) `check` consults `acceptance.json`.** A bundle with no `acceptance.json`,
or a record whose `gate_PASS` is `null`, reports **`REFUSED`** for this criterion —
a bundle that cannot show it passed its gate has not shown it, and a refusal is
not a pass. A present gate report whose `PASS` is false, or whose `PASS`
disagrees with the record's `gate_PASS`, is a **`FAIL`**. This is what stops a
`forecast --skip-oracle` issuance — which exits 3 with a failed gate — from
`check`ing PASS afterwards. From `epl-issuance-4` the gate report's bytes are
anchored by `acceptance_digest`.

**(b.4) The check-time parity rerun uses the production grid, or refuses.** A
posterior is **RECONSTRUCTABLE** at check time when the record names the fit's
inputs — `cutoff`, `observed_by`, the frozen configuration identity, and (from
`-4`) `training_frame_sha256` — and re-deriving under exactly those inputs yields
a posterior for which
`ParticleBook.from_posterior(post).content_hash() == record["effective_posterior_hash"]`.
Nothing weaker counts: a posterior that does not reproduce the anchored book is
not the posterior this issuance published from, and using it as the reference
would measure a different law.

* Reconstructable ⇒ parity's reference is `draw_api.production_grid(post, …)` and
  the criterion reports `PASS`/`FAIL`. The production adapter is then actually
  called at check time, which is the whole point: today it never is, so adapter
  drift is invisible to every check in the repository.
* Not reconstructable, on a record that carries the fit anchor ⇒ **`REFUSED`**,
  which is not `PASS`, and the arm is not `PASS`.
* On a **pre-A6 record**, which pins no training frame and therefore cannot say
  which frame the fit that made it saw ⇒ **`UNANCHORED`**. The book-mixture
  comparison is still computed and reported, labelled as the diagnostic it is,
  and A3's leg 1 continues to pass or fail on it exactly as it does today.

**(b.5) What the committed opener issuance will report — pre-stated, by criterion.**
`data/epl/sim/issuances/2026_27/2026-08-21/` is an **`epl-issuance-1`** record. It
is not re-issued, not re-run and not edited by A6 or by the commit that implements
it. Of the criteria above, **exactly five report `UNANCHORED (pre-A6 record)` for
it — `record_digest`, `retained_rows_anchored`, `truncation_sidecar_anchored`,
`acceptance_digest`, `parity_reference_is_production_grid`**. The rest were
evaluated against the committed bundle **on 2026-08-20 at `a2b1ead`** by
recomputation from the files as committed: the four A6 can settle in advance each
report `PASS`, and the fifth is a re-derivation whose outcome A6 does not assert.

| criterion | verdict for the committed opener | evidence |
|---|---|---|
| `published_output_full_digest` | **PASS**, all three arms | recomputed from each `output_<arm>.json` with `wall_seconds` dropped: `3a40110cd412…`, `5d3dad2d540e…`, `04bda8e4e6d6…` — equal to the record's `digests` map |
| `envelope_agrees_with_record` | **PASS**, all three arms | the ten shared fields agree; `bridge_hash` is absent for `dc_native` and `effective_posterior_hash` differs for `elo_wdl_bridge`, both by construction, so neither is in the shared set |
| `acceptance_verdict` | **PASS** | `acceptance.json` carries `PASS: true`, `failed: []`, `skipped: []`; the record carries `gate_PASS: true` |
| `truncation_sidecar_consistent` | **PASS**, all three arms | each sidecar's `summary` equals its envelope's `excluded_mass`; `max`, `mean`, `p90` and `n_fixtures` recompute exactly from the 380-entry vectors for the two DC arms; `elo_wdl_bridge` carries `measured: false` with an empty vector |
| `retained_rows_reproduce` | **runs** — a re-derivation, available on every schema | A6 does **not** assert its outcome in advance; it is measured when the code lands and reported then |
| `record_digest` · `retained_rows_anchored` · `truncation_sidecar_anchored` · `acceptance_digest` | **UNANCHORED (pre-A6 record)** | the record carries no such field, and computing one now and calling it an anchor would be the record anchoring itself after the fact — the one thing this ledger exists to prevent |
| `parity_reference_is_production_grid` | **UNANCHORED (pre-A6 record)** | no `training_frame_sha256`; the posterior the fit saw cannot be identified from the record, so the production adapter cannot be shown to have been exercised for this issuance. The book-mixture leg is still computed and reported |

So the committed opener stays verifiable **for exactly what its record can
support**, its top-level verdict is unchanged, and it can never report
`fully_anchored`. That is the honest end state and it is recorded here rather than
engineered around: the first issuance written under `epl-issuance-4` is the first
that can be fully anchored, and no earlier one is retrofitted into looking like it.

#### (c) `observed_by` binds the WHOLE forecast — a clarification, not an amendment

`observed_by` is a bound on the **run's knowledge**, not on one of its inputs.
Everything a forecast reads that is derived from match results is bounded by it:

1. the season **state** — already;
2. the **training frame** — already;
3. the **anchor state supplying `elo_z`** to the DC fit (`epl/dcfit.py:261`);
4. the Elo arm's own **anchor state and history frame** (`epl/simcli.py:486-489`);
5. the empirical **bridge**'s fitting frame (`epl/bridge.py:553`), whose filter is
   `date < cutoff` with no knowledge bound at all.

A provider that cannot state the knowledge bound it was built under is **refused**
rather than trusted; `epl/leaguesim.py:978`/`:1000` currently checks self-reported
dates and accepts a provider with no usable `describe()`.

**This is a bug fix to an existing invariant and is recorded here for the
avoidance of doubt.** No preregistered decision changes: plan v2 D5/D18 and the
bitemporal rule already say what the five surfaces above must do. Three of the
five reviews name it as their P0, and it is written down so that the fix commit is
read as *implementing* the invariant rather than as *introducing* it — and so that
the gap between what the plan said and what the code did is dated, rather than
discovered later as an undocumented change of behaviour.

**Pre-stated positive control**, before the fix exists: at `cutoff = 2026-08-26`,
`observed_by = 2026-08-22`, with one result played 2026-08-24 and filed as
observed 2026-08-25, every arm's numbers must be identical to the same run against
a ledger from which that row is absent entirely. `gate-retro.md` #1 reports that at
HEAD the same probe moves Arsenal by **+2.99 Elo** while the state sees zero
results — *quoted from that review and not recomputed here*.

#### (d) Native and bridge arms do not share an OUTCOME draw — a note on what CRN buys

The `u`-slot convention (`epl/leaguesim.py:583`) is a fixed contract, and it is
worth having. What it does **not** do is pair outcomes across the native and
bridge arms, and the phrase "common random numbers" has been read as if it did:

* `DCNativeProvider.sample` inverts `u[0]` against the **flattened scoreline CDF**
  — `flat = (rows < u[0]).sum()`, then `(hg, ag) = (flat // side, flat % side)`,
  row-major over 121 cells (`epl/leaguesim.py:648`);
* `DCWDLProvider.sample` and `EloOutcomeProvider.sample` invert `u[0]` against a
  **three-cell H/D/A CDF** and then draw the scoreline from the bridge's
  conditional with `u[2]` (`epl/bridge.py:454`, `:607`).

The same uniform indexes two different partitions of `[0, 1)`, and the home-win
cells are scattered through the row-major flattening rather than contiguous, so
equal `u[0]` does not mean equal outcome. `engine-pricing.md` #3 reports a HEAD
probe in which, with identical 1X2 laws, the arms disagreed on **76.5%** of
fixture outcomes — *quoted from that review and not recomputed here*.

**What follows, and what does not.** Every draw is still an exact draw from its own
arm's law, so no marginal, no matrix and no point estimate is affected, and no
number in R1, Addendum A or Addendum B is wrong. What is affected is the **degree
of coupling** in the paired columns that compare `dc_native` against a bridge arm:
they are validly paired *within an occasion* — same season, same cutoff, same fit,
same fixtures, same random slots — and they are **not** variance-reduced to the
degree "common random numbers" suggests, because the coupling stops at the uniform
and does not reach the outcome. The two bridge arms **are** pathwise paired against
each other, on both slots. Nothing in this project turns on the difference: the
paired differences are a diagnostic with no pass rule (prereg §7 and §11, restated
at Addendum B.5), and this note does not create one.

**A6 (d) takes precedence** over the prereg's *"with common random numbers"*
sentence and over the `ScorelineProvider` docstring wherever either is read as
asserting outcome-level pairing between `dc_native` and a bridge arm. The pointer
sentences at those two places land with the code commit, in the pattern the v4
note used; the sentences themselves stay unedited, for the reason A1-C1 gives.

**An outcome-paired native sampler is v1.2, and is not retrofitted.** Making the
native arm draw the outcome first and the scoreline conditionally would change
every `dc_native` number this project has ever issued, the published opener
included. That is a new sampler, and a new sampler belongs to a version with its
own preregistration — not to a patch that silently re-bases the published record.

### The rationale

Findings 3, 4, 5, 6, 7 and 8 are one defect wearing six coats: **a check whose
inputs are chosen by the thing being checked.** The harness decides what the truth
is from the rows it was handed; the scorer takes the ranker's fractional answer and
rounds it; `check` hashes the fields it expects to move and skips the ones that
carry provenance; parity compares the sampler to a reference derived from the
sampler's own book. Each is defensible in isolation and each removes the same
thing — an independent statement the artefact has to agree with. A6 puts one back
in each place: the schedule for the archive, the ranker's own allocation for the
outcome, the record's full digest for the file, the production adapter for the
grid, and the gate report for the gate.

Span-aware scoring is the smaller half of the same point and the one with a sharp
edge. The simulator already treats a tie fractionally — every forecast matrix in
the repository allocates 1/k across a tied block — and the scorer then compared
that fractional forecast to an integer truth. A forecast that reproduces the
ranker's own answer was charged for it. Making `O` a row of the same kind as the
forecast's row is not a new convention; it is the convention already in the code,
applied on both sides of the subtraction.

The `UNANCHORED` verdict exists because the alternatives are both dishonest. Making
the new criteria pass vacuously on old records turns the leniency into the hole it
was written to avoid — the mistake `epl-issuance-2` already made once, and which
the schema-strict comment at `epl/simcli.py:1265` records. Failing old records for
lacking fields that did not exist when they were written would say the published
issuance is wrong, which it is not. The truthful third answer is *this criterion
had nothing to hold this record against*, said out loud, in a list, next to a
boolean that goes false. A pre-A6 record can then be verified for what it supports
and can never claim more.

(c) is written as an amendment entry although it amends nothing because the
alternative is worse: a fix commit that quietly changes what every future forecast
sees, with no dated statement of what the rule always was. The invariant is old;
the observation that the code does not implement it is new; the entry dates the
second without pretending to change the first.

(d) is the case this ledger handles least often and should: **the code is right and
the description is wrong.** No number moves, no rule changes, and the only thing at
stake is what a reader is entitled to conclude from the word "paired". Writing it
down costs one entry. Leaving it costs a future reader the belief that a narrow
paired interval reflects a coupling that was never there.

### What is pre-stated

Fixed here, before the code exists and before any run under any of it exists:

- **The realised-archive validation is exactly three conditions** — the manifest's
  20 clubs as an equality, 380 played results, and the complete double
  round-robin as a set equality over ordered pairs — refusing with
  `IncompleteRealisedArchive` and naming the missing and extra pairs. It is a
  refusal to score, never a `refusal_kind` marker.
- **`realised_hash` covers results, adjustments, boundaries and rule id**, enters
  `run_key` as a `|t…` segment and the row's `envelope_hash`, and two distinct
  values for one season is `STOP_AND_INSPECT`.
- **The span rule is `O[c, j] = 1/k_c` across the realised block and 0 elsewhere**,
  cumulated by the same function that cumulates the forecast, with
  `y_c = Σ_{j ∈ slice} O[c, j]` for the consequence Briers. A forecast matching the
  ranker's allocation scores **zero**. `O` is asserted doubly stochastic.
- **v5 reduces to v4 wherever every span is 1**, and R1 + Addenda A and B are not
  re-scored: 190 scored rows, `n_shared == 0` on every one, all 3,800 club-spans
  equal to 1.
- **`UNANCHORED` is a fourth verdict, is not a pass, and forces `fully_anchored`
  false**; the five criteria it applies to for the committed opener are named in
  (b.5), and none of the criteria A6 settles in advance FAILs it.
- **`epl-issuance-4` adds `record_digest`, `sidecar_digests`, `acceptance_digest`
  and `training_frame_sha256`**, mandatory from `-4` on, absent-and-`UNANCHORED`
  before it, with no key renamed or removed.
- **A missing or `null` gate report is `REFUSED`, a false or disagreeing one is
  `FAIL`.**
- **Parity uses `production_grid` only when the re-derived posterior reproduces the
  anchored `effective_posterior_hash`**, and otherwise `REFUSED` — or `UNANCHORED`
  on a record with no fit anchor.
- **`observed_by` binds the state, the training frame, the DC fit's Elo
  covariates, the Elo arm's anchor and history, and the bridge's fitting frame**;
  a provider that cannot state its bound is refused.
- **No outcome-paired native sampler is built in v1.1.** It is v1.2, with its own
  preregistration, and no published `dc_native` number is re-based to it.
- The **v5 hashes** are the one thing this entry cannot state in advance; they are
  appended as a dated note inside the A4 entry, where the list the test reads
  lives.

No threshold, count or rule above was chosen after seeing a result under it: no
run under harness v5 exists, no record under `epl-issuance-4` exists, and the four
verdicts pre-stated for the committed opener were recomputed from the bundle
exactly as it was published on 2026-08-19 and committed unchanged since.

### Recording note

Written **before any line of `epl/` changed under this ruling**. Both harness files
were re-hashed at the moment of writing and still match the **v4** values in A4's
dated note — `7aabbd78…` and `53c11eb1…`, unchanged; `git diff --stat main -- src
scripts` is empty; the committed opener bundle and `data/epl/sim/retro_r1.jsonl`
are untouched, and every count and digest quoted in (a.4) and (b.5) was recomputed
from those files exactly as they stand committed. The full suite — 508 tests — is
green at this commit, which changes no code. The commit that implements any of
this follows this one.

### What landed for findings 10 and 11 — the ingest (recorded 2026-08-20, with the G1 Fix commit)

A6's table records findings 10 (silent non-integral goals) and 11 (an ingest that
cannot revise, and a kickoff move nothing acts on) and rules on neither. They are
implemented here, and this note says what the code now does so the behaviour is
dated rather than discovered. **No preregistered decision changes**, and in
particular **D4 is kept exactly as written**.

1. **A goal count is never coerced.** `epl.season.goal_count` accepts an exact
   integer — `2`, `2.0`, `"2"` — and refuses `1.9`, `nan`, `inf`, `True`, a
   negative and a word, at the moment the value is offered. `int(1.9)` is `1`,
   and a ledger holding `1` for a source that said `1.9` presents read-time
   validation with a perfectly good integer. Both writers use it: the manual
   overlay and the openfootball adapter.

2. **The ingest can revise, behind an explicit flag.** `--allow-revisions` lets a
   source revise its OWN earlier statement — a changed scoreline appends a
   correction row, and a fixture the refreshed file carries unscored appends a
   `postponed` status row, so the fixture reads as unplayed from that observation
   on. Both are appends; the latest-observation resolution that already exists is
   what makes them win, and a snapshot bounded before them still reads what the
   ledger said then.

   **D4's case is untouched.** A source may not overrule another's row: openfootball
   meeting a hand-entered result it disagrees with still STOPs with
   `ResultConflict`, whatever the flag says, and the remedy is a deliberate manual
   correction — the human deciding, which is what D4 asks for. The same rule is
   what stops a source that has merely not caught up from "withdrawing" a round
   the operator entered by hand: an unscored line in a file that never filed the
   result is a source with nothing to say, not a retraction.

   Two write-time refusals guard the append-only file: a correction stamped no
   later than the row it corrects is refused rather than written (it could never
   win the resolution, so the line would change nothing while reading like a
   correction), and a fixture the ledger reads as `abandoned` is revived by a
   later score only under the flag, while one it reads as `postponed` is revived
   by any ingest — a postponement says "not played yet", an abandonment is a
   deliberate strike.

3. **The manual overlay writes statuses and marked corrections.** A row may carry
   `status: "postponed"|"abandoned"` and no goals, or a scoreline with
   `"correction": true`. An UNMARKED disagreement is still `ResultConflict`: the
   likelier explanation for one is a typo, and an append-only ledger has no undo.
   The marker is a directive to the reader and is not written to the ledger; the
   row's note records what it supersedes.

4. **`detect_kickoff_amendments` is wired to the ingest.** An openfootball ingest
   diffs the refreshed parse against the vendored bytes, keeps only the moves that
   actually change the kickoff the season already knows, and appends them to
   `kickoff_amendments.jsonl` with `known_at` = the ingest time. The function has
   existed since T2 with no caller, so a moved kickoff left the old date in place
   — and a fixture whose stale date has passed reads as `unresolved`, and past two
   days sets `results_lag`. The second filter is what keeps a re-fetch from
   re-appending the same move every week: the vendored bytes never change, so the
   raw diff alone repeats itself for the rest of the season.

Nothing above touches a number in any issued forecast, the retrospective, or the
committed opener bundle. `src/` and `scripts/` are unchanged.

### What landed for A6 (c) — the knowledge bound (recorded 2026-08-20, with the G2 Fix commit)

A6 (c) pre-stated that `observed_by` binds the whole forecast and named the five
surfaces. Four of them already respected it or now do; the fifth is stated as a
limit rather than claimed.

* the season **state** and the **training frame** — already, unchanged;
* the **DC fit's Elo covariates** — `fit_epl` takes `observed_by` and builds
  `elo_z` through `epl.anchor.anchor_state_at`, which passes the bound to an
  anchor that has a known-at dimension and refuses an object that can state no
  bound at all. An `epl.anchor.Anchor` is the archive's own snapshot table, a
  closed record with nothing a later observation could reveal, so it takes no
  such argument and needs none — and which of the two is in hand is read off the
  SIGNATURE rather than discovered by catching `TypeError`, because a
  `TypeError` raised inside a replay would otherwise be swallowed and silently
  downgraded into the unbounded call this exists to prevent;
* the **Elo arm's anchor state and history frame** — both now carry the bound,
  taken from the `SeasonState`, which is where this run's knowledge clock is
  decided. Taking it from anywhere else is how two clocks get into one run;
* the **bridge's fitting frame** — the live path already fits the bridge on
  `fit.training`, which `live_training_frame` bounds by both clocks (D18, and
  the test that pins it predates this round). `EmpiricalBridge.fit`'s own
  `date < cutoff` filter is the PLAY clock and is correct as it stands.

**What is NOT done, and why.** A6 (c) also says a provider that cannot state its
bound is refused. `epl/leaguesim.py`'s backstop still accepts a provider with no
usable `describe()`, and `ParticleBook` still carries no fit cutoff or
`observed_by`. Closing that would change `ParticleBook.content_hash()` — hence
`effective_posterior_hash` — or the provider `describe()` blocks that land in
each arm's envelope, and both are anchored in the COMMITTED opener issuance's
`digests` and `provider_hashes`. Making the engine refuse what it cannot verify
would therefore require re-issuing the published opener, which this round is
explicitly not doing. It is recorded here as an open item for the first issuance
written under `epl-issuance-4`, where the record can carry the provenance without
re-basing a published one.

The probe A6 (c) pre-states is now a test: at `cutoff = 2026-08-26`,
`observed_by = 2026-08-22`, with one result played 2026-08-24 and filed as
observed 2026-08-25, the anchor's ratings and `elo_z` and the Elo arm's content
hash are identical to the same run against a ledger without the row — and the
positive control drops the bound and watches Arsenal move, which is what HEAD
did. The committed opener's own ledger is empty, so no number in it moves:
`dc_native` still reproduces and still reports `digest_matches: true`, and the two
bridge arms are REFUSED there for the reason they always were, its bundle carrying
no sidecars.

### What landed for A6 (b) — `check` semantics (recorded 2026-08-20, with the G3 Fix commit)

`epl-issuance-4` is live and the fourth verdict exists. The committed opener was
re-checked under the new code on 2026-08-20. **This is what the documented
whole-bundle command emits** — the JSON report goes to stdout and is elided
here; these are the stderr lines and the exit code:

```
$ PYTHONPATH=src:. .venv/bin/python -m epl.simcli check \
      --directory data/epl/sim/issuances/2026_27/2026-08-21
[check] re-running dc_native at 2026-08-21 00:00:00 (N=20000, seed=20260611)
[check] dc_native: PASS
[check] dc_wdl_bridge: REFUSED — dc_wdl_bridge cannot be re-derived from this issuance: arms.json, bridge.json are missing. An issuance written before the arm sidecars existed carries no record of the fitted bridge or the Elo head, and a check that cannot rebuild the arm is not a passing check.
[check] elo_wdl_bridge: REFUSED — elo_wdl_bridge cannot be re-derived from this issuance: arms.json, bridge.json, elo_arm.json are missing. An issuance written before the arm sidecars existed carries no record of the fitted bridge or the Elo head, and a check that cannot rebuild the arm is not a passing check.
[check] record_digest: UNANCHORED — unanchored (pre-A6 record)
[check] acceptance_digest: UNANCHORED — unanchored (pre-A6 record)
[check] FAIL; unanchored: acceptance_digest, dc_native.parity_reference_is_production_grid, dc_native.retained_rows_anchored, dc_native.truncation_sidecar_anchored, dc_wdl_bridge.retained_rows_anchored, dc_wdl_bridge.truncation_sidecar_anchored, elo_wdl_bridge.retained_rows_anchored, elo_wdl_bridge.truncation_sidecar_anchored, record_digest
$ echo $?
4
```

*Arithmetic note: the two transcripts in this section quote verdicts, criterion
names and an exit code. Nothing in them is estimated, so nothing in them carries
a Monte-Carlo error.*

**The headline is `FAIL` and the exit code is 4 — and for the reason they always
were.** The two bridge arms are `REFUSED` because this bundle carries no arm
sidecars, and a `REFUSED` arm is not a passing arm. That is A6 (b.5)'s *"its
top-level verdict is unchanged"* holding rather than failing: `PASS` was already
false for this bundle at `a2b1ead`, before A6 existed, on exactly those two arms.

**Where the landed code DEVIATES from (b.5), recorded rather than smoothed over.**
(b.5) pre-stated that *"exactly five report `UNANCHORED (pre-A6 record)`"* and
named five criteria. The code reports those five **names** as nine per-arm
**entries**. `record_digest` and `acceptance_digest` are record-level and appear
once each. `retained_rows_anchored` and `truncation_sidecar_anchored` are per-arm
and are evaluated for all three arms, none of which carries sidecars — six.
`parity_reference_is_production_grid` appears for `dc_native` alone, because the
two bridge arms are refused before the rebuild that would evaluate it — one. Two
plus six plus one is nine, and every arm-level entry is namespaced
`<arm>.<criterion>`, which is what makes an entry distinguishable from a name.
(b.5) counted criteria and the tool counts and namespaces entries; the bundle's
standing is the same under either count — five names, nine entries, and no
anchor.

**Narrowed to the published arm** — `--arm dc_native`, which is the question the
per-criterion table in (b.5) is written about — the same bundle reports:

```
$ PYTHONPATH=src:. .venv/bin/python -m epl.simcli check \
      --directory data/epl/sim/issuances/2026_27/2026-08-21 --arm dc_native
[check] re-running dc_native at 2026-08-21 00:00:00 (N=20000, seed=20260611)
[check] dc_native: PASS
[check] record_digest: UNANCHORED — unanchored (pre-A6 record)
[check] acceptance_digest: UNANCHORED — unanchored (pre-A6 record)
[check] PASS (5 criteria unanchored: pre-A6 record); unanchored: acceptance_digest, dc_native.parity_reference_is_production_grid, dc_native.retained_rows_anchored, dc_native.truncation_sidecar_anchored, record_digest
$ echo $?
0
```

**That is a NARROWED run, and its headline is not the bundle's.** `--arm
dc_native` asks about one arm and is answered about one arm; the bundle's verdict
is the block above. Five entries here because one arm contributes two sidecar
anchors and one parity anchor — not because the bundle has five.

Per criterion for `dc_native`: `published_output_full_digest`,
`envelope_agrees_with_record`, `truncation_sidecar_consistent` and
`retained_rows_reproduce` all `PASS`, and the record-level `acceptance_verdict`
`PASS`es. `retained_rows_reproduce` is the criterion (b.5) declined to predict —
a re-derivation available on every schema. Measured now that the code exists: it
passes for the committed opener's `dc_native` arm, all ten arrays element for
element, and `dc_native` still reports `digest_matches: true`.

> **Correction, 2026-08-20 (r6 Fix commit).** As first written, this note carried
> one fenced block, headed `PASS (5 criteria unanchored: pre-A6 record)` with
> `fully_anchored: false` beside it, and presented that as what the documented
> whole-bundle command emits. It is not. That block is the `--arm dc_native`
> run — an option the note did not mention — its criterion names were shown
> stripped of the `<arm>.` namespace the code writes, and the whole-bundle
> headline is `FAIL` with exit code 4 and nine entries. The two blocks above are
> the two commands' actual output.
> `test_the_committed_opener_reports_exactly_the_pre_A6_criteria_unanchored`
> stayed green throughout because it, too, passed `arms=("dc_native",)`;
> `test_the_committed_opener_whole_bundle_check_is_FAIL_and_the_ledger_says_so`
> now measures both runs and holds every line of this note's two blocks against
> them, so the note and the tool cannot drift apart again.

Three points where the implementation had to decide something (b) does not
spell out, each decided the strict way and stated here:

1. **Absent versus present-and-null.** A `-4` record with one of the four new
   keys ABSENT FAILs the criterion it anchors, naming the field — that is
   (b)'s rule, and it is what stops the leniency becoming the hole
   `epl-issuance-2` already made once. A key PRESENT and `null` is different and
   is not tampering: it is the issuer saying there was nothing to pin. A run made
   from a book with no posterior pins no training frame, and a run issued with no
   gate has no gate bytes to hash. Both report UNANCHORED with a note that says
   which, so they are not passes either.

2. **`training_frame_sha256` is written only when there is a fit to identify** —
   `fit.post is not None`. Claiming an anchor for a run that had no posterior
   would be the record anchoring itself after the fact.

3. **Reconstruction is offered, not performed.** `check_issuance` takes a `post`
   argument and uses `draw_api.production_grid` when
   `ParticleBook.from_posterior(post).content_hash()` equals the record's
   `effective_posterior_hash`, exactly as (b.4) requires. It does not itself
   re-fit: a check has no store and a fit is minutes. A `-4` record checked
   without a reproducing posterior therefore reports REFUSED, which is not a
   pass and leaves the arm not a pass — the honest state, and the one (b.4)
   asks for.

Also landed here, from `live-forecast.md` #4 (recorded by A6 and not ruled on):
the issuance is written to a staging directory OUTSIDE the season's issuance
folder and moved into place in one step, with `summary.md` before
`issuance.json` and `issuance.json` last. `_last_issuance` additionally requires
a directory named for a cutoff DAY, so a half-written run is not a candidate on
either count. Tested by interrupting a re-issue and asserting the previous
issuance is still selected, byte for byte, with nothing else in the folder.

Every test issuance in the suite runs no gate or the fast gate, so none of them
can `check` PASS any more — which is finding 7 working. Those tests now assert
what is true: every arm reproduces, and the only thing standing between the
bundle and a pass is the gate it cannot show.

---

## A7 — the per-fixture matchboard: the published forecast the record already named (2026-08-25)

**Decisions amended:** two, both named.
(i) the published surface set of plan v2 — what an issuance bundle *contains*, and
what `check` holds it to — as that stands at `epl-issuance-4` after A6 (b);
(ii) the sentence acceptance criterion 3 prints on PASS (`epl/simcli.py:1358`),
which names a *published per-fixture forecast* this project does not publish.
**(f) amends nothing.** It draws a boundary around a field set rather than moving
one, and is written down for the reason A6 (c) gives: a rule stated nowhere is a
rule a later commit cannot be held to.
**Status of the amendment when written:** not a line of `epl/` has changed under
this ruling, and **no matchboard exists anywhere in this repository** — not in a
bundle, not in `reports/`, not in a branch. `epl/simretro.py` and
`epl/simmetrics.py` still hash to the **v5** pair (`d64bef11…`, `b03d4fbc…`), the
last pair `epl/retro_harness_versions.json` records and the pair the running files
produce. `ISSUANCE_SCHEMA_VERSION` is `epl-issuance-4`. The opener bundle at
`data/epl/sim/issuances/2026_27/2026-08-21/` is untouched: its three per-arm run
digests were recomputed from the files on disk on 2026-08-25 and equal the
record's `digests` map (`3a40110c…`, `5d3dad2d…`, `04bda8e4…`). The working tree
at `89d3d58` carried nothing but this entry when it was written.

*Arithmetic note: every probability in this entry is an exact ratio of counts over
one fixed sample of 20,000 retained simulated seasons — a count divided by 20,000,
not an estimate re-drawn here — and every standard error beside one is the
project's cluster-by-particle formula (plan v2 D15) evaluated on that same sample.
Those SEs are Monte-Carlo error and nothing else; they say nothing about model
error. The scores quoted in observation (c) are quoted from
[`reports/epl_walkforward.md`](epl_walkforward.md) and from `site/market-test.html`
and carry whatever error those documents record beside them; none is recomputed
here. Every hash, count and date is exact.*

### The observation

#### (a) The record's own sentence names a surface that does not exist

On PASS, `marginal_parity` prints (`epl/simcli.py:1358`):

> simulated per-fixture marginals ARE the published per-fixture forecast

and the shipped opener carries that sentence, verbatim, in its own `summary.md`
(line 53), beside **PASS** and **14,225** compared cells over **380** fixtures,
worst cell `3.865σ`. The criterion is sound and the sentence is the strongest
claim the acceptance gate makes — A3 says so in as many words: it is what
distinguishes *the marginals **are** the forecast* from *they resemble it*.

The trouble is the object at the end of it. **There is no published per-fixture
forecast.** What an issuance publishes is `output_<arm>.json` — a 20×20 position
matrix, the consequence state, the cut lines, the `mc` block — plus `envelope.json`,
`limitations.md`, `rows_<arm>.npz` and `excluded_mass_<arm>.json`. The per-fixture
law the criterion compares against is production's own grid, computed at check
time and never written down for a reader. So the sentence is true of an internal
comparison and false as a description of the bundle, and it has stood in the
shipped `summary.md` since that file was written on 2026-08-19.

The gap was found by the 2026-08-21 final-state reviews — the round A6 rules on —
and it was **left unruled**: A6's table records fifteen findings and rules on the
four the owner asked for, and this one is not among the fifteen. It has therefore
been sitting in the record for four days as a sentence nobody has either made true
or withdrawn.

#### (b) The bar moved, and the instruction is explicit

On **2026-08-22** the owner redefined what would satisfy this project: **accuracy
parity with the World Cup edition**, and explicitly **not** beating the internal
accuracy benchmark. In this session the owner instructed, verbatim: *"build the
per match surface for epl"*, in the World Cup style.

Those two sentences settle the shape of the answer and not merely that there
should be one. The World Cup edition already published a per-match surface —
`reports/live_scorecard_final.json`, 104 rows, one per match, rendered by
`tools/gen_plate1.py` as one mark per match — and "parity" is only checkable
against a surface built to the same specification.

#### (c) The measured record this surface would stand on

[`reports/epl_walkforward.md`](epl_walkforward.md), 2,280 matches over six
seasons, priced weekly at a frozen configuration chosen before any of them were
seen:

| | mean normalised RPS |
|---|---:|
| Dixon-Coles, this architecture | **0.201942** |
| walk-forward Elo + ordered logit | **0.203114** |
| the internal accuracy benchmark | **0.195418** |

The preregistered pass rule is **NOT MET** and the verdict is **INCONCLUSIVE
(precise null)**: Δ = −0.001172 against Elo, 95% block-bootstrap
[−0.002809, +0.000466], where PASS required Δ ≤ −0.0034 and hi < 0. The distance
behind the benchmark is **+0.006525** [+0.004099, +0.008982]. The benchmark column
is what that report defines as an internal accuracy benchmark and states is never
displayed publicly, never turned into a signal and never sized; §11 of it is the
citation for every figure in this table.

The World Cup edition's published distance is **about 0.010** — `site/market-test.html`
carries it as its headline figure, with `0.01018` in the body.

**So the EPL edition is at or inside the World Cup edition's published distance,
on 2,280 matches against the World Cup's 217.** That is the entire strength of the
case for building this surface, and it is a *retrospective* strength: it is a
walk-forward record over finished seasons, not a live scored one, and it licenses
publishing a forecast, not believing it. Which is what makes (a) urgent rather
than tidy — the sentence already claims a surface, the bar now asks for one, and
the honest order is the surface first and the claim afterwards, earned.

### The ruling (owner, 2026-08-25) — pre-stated before the code

#### (a) The matchboard sidecar

**Every issuance written from here on publishes `matchboard_dc_native.json`**, a
required sidecar, derived **deterministically from `rows_dc_native.npz` of the
same bundle** and from nothing else. It is **never re-priced**: not from the
particles, not from a fresh grid, not from `draw_api.production_grid`. The 38 of
380 opener fixtures that carried provisional widening (`n_provisional: 38` in the
opener's own acceptance record) are the standing proof of why — the widening is in
the retained rows and in no grid a later reader can rebuild, so a re-priced
matchboard would silently publish a different law from the one the run issued.

**`dc_native` only.** A6 (d) records that a bridge arm inverts `u[0]` against a
three-cell H/D/A CDF and then draws its **scoreline** from the bridge's
conditional (`epl/bridge.py:454`, `:607`). Its 1X2 is that fixture's own law; its
scorelines are a league-wide conditional wearing that fixture's name, and every
margin field below is computed from scorelines. A surface with three meaningful
columns and four decorative ones is worse than no surface, so the bridge arms get
no matchboard at all rather than a partial one. There is no `matchboard_<arm>.json`
for any arm but the published native arm, and `check` never namespaces a matchboard
criterion to a bridge arm.

**One row per unplayed fixture**, in `fixture_ordinal` order, each carrying:

| field | what it is |
|---|---|
| `fixture_id` | the stable date-free id (`epl/season.py:171`), e.g. `2627:arsenal:coventry` |
| `fixture_ordinal` | the rank of that id among the season's 380 **sorted** fixture ids — the npz column contract (`epl/leaguesim.py:37`) made readable |
| `date` | the kickoff DAY the season knew at `observed_by`, after `kickoff_amendments`; the same field name the World Cup row uses |
| `home`, `away` | the two club keys, in the fixture's own orientation |
| `probs` | `{"home", "draw", "away"}` — the WC row's own object, so a WC-shaped reader needs no translation |
| `probs_se` | `{"home", "draw", "away"}`, cluster-by-particle |
| `e_margin`, `e_margin_se` | see the semantics below |
| `p_marg_ge2`, `p_marg_ge3`, `p_marg_ge4` | see the semantics below |
| `p_marg_ge2_se`, `p_marg_ge3_se`, `p_marg_ge4_se` | cluster-by-particle |
| `n_sims`, `n_particles` | the counts **this row** was computed from — a per-row count is what makes a short or truncated row detectable |

**The World Cup semantics, stated here because the code that defined them is no
longer importable.** `scripts/live_scorecard_final.py` imports `score_fixtures`,
`grid_to_1x2`, `grid_margin_stats` and `favorite_band_reliability` from
`wcmodel.model.calibration`; **none of the four is in that module at HEAD**
(`from wcmodel.model.calibration import score_fixtures` raises `ImportError`,
checked 2026-08-25). An implementer told to "match the World Cup" therefore cannot
run the World Cup's code. The semantics are pinned instead from the generator as
git records it at **`f374841`** and from the published artifact
`reports/live_scorecard_final.json`, and they are:

* **`margin` is UNSIGNED: `|home_goals − away_goals|`.** A draw has margin 0. The
  quantity names no side and is not the winner's margin signed by who won.
  Verified against the published artifact: all 24 drawn matches of the 104 carry
  `realized_margin == 0` and no row is negative.
* **`e_margin = E|home − away|`.** In the World Cup it is `Σ_{i,j} |i−j| · p[i,j]`
  over the scoreline grid — an exact sum over a grid. **On the matchboard it is
  the mean of `|hg − ag|` over that fixture's retained simulated scorelines** —
  the same functional, estimated from the rows rather than integrated over a
  grid. That is why the matchboard's carries an MC SE and the World Cup's did not,
  and the difference is stated rather than papered over.
* **`p_marg_ge_k = P(|home − away| ≥ k)`** for k = 2, 3, 4 — in the World Cup the
  grid mass on cells with `|i−j| ≥ k`; on the matchboard the fraction of that
  fixture's retained scorelines with `|hg − ag| ≥ k`. The three events are
  **nested**, so the chain is monotone by construction on any one sample.
* **`realized_margin = |hg − ag|`** — the scorecard's realised column, not a
  matchboard field; it belongs to (e).

**Every SE is cluster-by-particle** (plan v2 D15):
`sqrt(Σ_s (m_s − p)² / (S(S−1)))` over the S per-particle means, where a particle's
`m_s` is the statistic over that particle's own simulated seasons. A binomial SE
computed as if 20,000 seasons were 20,000 independent draws is **not** this
project's SE and is a FAIL of the derivation, not a rounding difference: the
opener's rows are 1,000 particles used exactly 20 times each, and the clustering
is the whole reason the number is honest.

**A header block** on the same file, naming the run the rows came from: `season`,
`arm`, `cutoff`, `observed_by`, `seed`, `chunk_size`, `n_sims`, `n_particles`,
`n_fixtures`, the source npz filename, `effective_posterior_hash`, the record's
`digests["dc_native"]`, and the three provenance digests the envelope already
carries and which anchor the names and dates this surface prints —
`manifest_sha256`, `fixtures_base_sha256`, `kickoff_amendments_sha256`.
`n_fixtures` **must equal the record's `n_unplayed`**, and a disagreement is a
FAIL: a matchboard that prices a different number of fixtures than the run had is
not the run's matchboard. `schema_version` is `epl-matchboard-1`.

**A companion `matchboard.md`** renders it in the house voice and carries the
standing limitations language, in these terms and not softer ones: *these numbers
carry no accuracy claim; the claim is earned by the live scored record or not at
all.* It also states, on the same page, that the law is one arm's, that scorelines
are truncated at 10 goals under D11 v1.0.1 (A1) with the tail discarded, and how
many of the fixtures carried provisional widening.

#### (b) Anchoring — the matchboard joins the G3 regime

The matchboard is a sidecar and is held exactly as A6 (b.2) holds the other two.

1. **Its digest enters the record.** `sidecar_digests["dc_native"]` gains
   `"matchboard"` (the SHA-256 of `matchboard_dc_native.json` as written) and
   `"matchboard_md"` (the same for `matchboard.md`), beside the existing `rows`
   and `excluded_mass`. `files["dc_native"]` gains both filenames, so
   `record_digest` covers the fact that they were published at all.
2. **It is written through the staged path.** Both files are written into the
   staging directory outside the season's issuance folder and moved into place in
   the one step the A6 (b) landed note installs, before `summary.md` and well
   before `issuance.json`. A half-written matchboard is never a candidate for
   anything.
3. **`check` re-derives it from the rows.** Two criteria, and exactly two:
   * **`matchboard_anchored`** — recomputes both SHA-256s from the files on disk
     and requires them to equal `sidecar_digests["dc_native"]["matchboard"]` and
     `["matchboard_md"]`. This is the bit-level statement, and it is the only leg
     that can catch a doctored file which preserves every quantity a
     recomputation would check.
   * **`matchboard_reproduces`** — reads `rows_dc_native.npz`, re-derives every
     row and every field of the matchboard from it, and compares. Ids, ordinals,
     dates, club keys and counts must be **equal**; the eleven floating-point
     quantities per row must agree to **1e-12 absolute**. A tolerance rather than
     bit equality, and the reason is stated rather than left as slack: the
     re-derivation may sum in a different order under a different numpy build,
     and `matchboard_anchored` is where bit-level identity is asserted. This leg
     is the semantic one — it is what makes a matchboard *of these rows* rather
     than *shipped beside them*.

   A **tampered** matchboard fails `matchboard_anchored`, and fails
   `matchboard_reproduces` too whenever the tampering touched a number. A
   **deleted** matchboard on a record whose schema requires one is a **FAIL**
   naming the missing file — never a silent pass and never an `UNANCHORED`.
4. **Mandatory from `epl-issuance-5`.** The matchboard fields arrive with the
   schema bump, on A6 (b)'s own pattern: mandatory from `-5` on, and a `-5` record
   missing one **FAILs** the criterion it anchors, naming the field. Nothing is
   renamed and nothing is removed. A6's landed distinction between *absent* and
   *present-and-`null`* does **not** rescue anything here: `null` is the issuer
   saying there was nothing to pin, and for `dc_native` there is always something
   to pin — an issuance whose season has no unplayed fixtures left writes a
   matchboard with `n_fixtures: 0` and an empty row array, which is present. A
   `-5` record carrying `matchboard: null` is a **FAIL**.

#### (c) Pre-A7 records, and the one derivation that is allowed

**A pre-A7 record has no matchboard by construction**, and `check` says exactly
that: `matchboard_anchored` and `matchboard_reproduces` both report
**`UNANCHORED`** with a **new** note, `PRE_A7_NOTE = "unanchored (pre-A7 record)"`,
distinct from `PRE_A6_NOTE`. Never FAIL. This is A6 (b)'s fourth verdict used for
the thing it was built for — *the record predates the field this criterion is held
against* — and it carries A6's consequences unchanged: an `UNANCHORED` criterion
is not a passing criterion, and it forces `fully_anchored` false.

**The opener is never retrofitted.** `data/epl/sim/issuances/2026_27/2026-08-21/`
is not re-issued, not re-run, not edited, and no matchboard is written into it.
Computing one now and filing it inside the bundle would be the record anchoring
itself after the fact, which is the one thing this ledger exists to prevent.

**A derivation from a preserved pre-A7 bundle is permitted, as a labelled DERIVED
artifact and not as part of the record.** It is written **outside** every bundle
directory — `reports/epl_matchboard_<season>_<cutoff>_derived.json` and `.md` —
and it must carry `"derived": true`, the source bundle path, `"derived_at"`, and
the source bundle's **recorded** hashes copied from its record. Its `.md` states
on its first line that it is derived after the fact from a preserved bundle and is
not part of that bundle's record. **`check` FAILs any bundle directory that
contains a file matching the derived naming convention**, so a derived artifact
can never drift into a bundle and be mistaken for a sidecar.

#### (d) What the MW0 derivation actually inherits — provenance, stated exactly

A matchboard derived today from the opener bundle inherits **two different kinds
of provenance**, and A7 names both rather than collapsing them into one word.

**What is anchored pre-kickoff.** Four content hashes were recorded in a tracked
file before a ball was kicked: `effective_posterior_hash`
`b87c4a17cd4ce867a6e92447d214ba3454dcc3376c2da85b85dbc09862cb1b61`, the bridge
hash `cb1597ee…`, the `dc_native` numbers digest `922040b2…` and the `dc_native`
run digest `3a40110c…`. They stand in
[`reports/epl_sim_issuance_2026-08-21.md`](epl_sim_issuance_2026-08-21.md), first
committed at **`9478e71`** on **2026-08-19 16:15:58 +0800** — two days before the
2026-08-21 cutoff and before any 2026/27 result existed (`n_played: 0`). That
commit is the checkable pre-kickoff anchor, and it is checkable because the file
is in git. Re-verified 2026-08-25: all three per-arm run digests recompute from
the bundle on disk and equal the record's `digests` map.

**What is NOT anchored, and must not be described as if it were.**
`rows_dc_native.npz` — the file a matchboard is derived from — **is covered by no
hash recorded before kickoff.** `data/` is gitignored, so the bundle is not in
this repository's history at all; the record is `epl-issuance-1` and carries no
`sidecar_digests`; and A6 (b.5) pre-stated, and the G3 landed note then measured,
`dc_native.retained_rows_anchored → UNANCHORED (pre-A6 record)`. What the rows
have instead is **reproduction**: `retained_rows_reproduce` re-runs the arm and
compares all ten arrays element for element, and the A6 (b) landed note records it
passing for this bundle. So the derivation inherits **pre-kickoff provenance for
the law** (the posterior hash and run digest recorded at `9478e71`) and
**reproduction-based provenance for the rows**. A derived artifact's own text, and
any scorecard row that cites it, must say both — and must not call the rows
anchored.

**For the record and explicitly not as an anchor:** `sha256(rows_dc_native.npz)`
as the file stands on 2026-08-25 is
`c6906778cd8eacf564d35a1a00e59adec85881bb64f04eed7ee6cb9bb27c42f8`. It is written
here so a later reader can tell whether the file moved after this entry. It is
being recorded **after** kickoff and does not become a pre-kickoff anchor by
appearing in this ledger.

**One claim is refused entry.** It was put to this entry that the four hashes were
also vault-pushed at commit `426eed7`. **That object is not in this repository** —
`git log --all` finds no such commit and no vault checkout is present here — so it
is not entered into the record. `9478e71` is, because it can be checked from this
history by anyone who reads this line.

#### (e) Scoring — the matchboard scorecard ledger

**A matchboard scorecard ledger accumulates the live scored record**, appended
**per matchweek, after the results have entered the season ledger** and never
before. One row per scored fixture, carrying the forecast, the realised outcome,
and enough provenance to find the bundle that priced it: `fixture_id`, `date`,
`home`, `away`, the `probs` as issued, the issuance's `season`, `cutoff`,
`observed_by` and `digests["dc_native"]`, the realised `outcome` and
`realized_margin` (`|hg − ag|`, as in (a)), the matchweek, and the RPS columns
below. Joined with its matchboard row it is field-for-field a World Cup scorecard
row.

* **Per-fixture RPS** against the realised outcome, over the ordered outcomes
  `(home, draw, away)`, by this project's own literal:
  `RPS = (1/(r−1)) Σ_{i=1..r−1} (CP_i − CO_i)²` with `r = 3`.
* **A uniform-baseline column** beside it: the same RPS for `(1/3, 1/3, 1/3)`.
  Exactly, and pre-stated as arithmetic the implementation must reproduce:
  **5/18 = 0.277778** for a home or away result and **1/9 = 0.111111** for a draw.
* **No pass rule.** None. This ledger reports; it decides nothing, triggers
  nothing and gates nothing. A live record that is allowed to fire a rule is a
  rule that will be explained away the first time it fires.
* **No benchmark column on this surface**, per (f).
* **A row is admissible only if the forecast preceded the kickoff.** The
  issuance's `cutoff` and `observed_by` must both be at or before the fixture's
  kickoff as the season knew it, and the row records all three so a reader can
  check the ordering rather than trust it. This is the World Cup edition's own PIT
  discipline restated for a league season.
* **The margin fields are reported as reliability, not as a score**: predicted
  mean against realised frequency, in the shape the World Cup's own blowout-tails
  table used, and labelled as a comparison rather than a proper score — because
  that is what it is.
* The ledger is **append-only**, and each row records the matchweek and the ingest
  that supplied the result.

#### (f) The margin-quantity boundary

`e_margin`, `p_marg_ge2`, `p_marg_ge3` and `p_marg_ge4` are published on the
matchboard as **World-Cup-parity fields**, under the owner's 2026-08-22
instruction, and for no other reason. **They are a closed set of four.** Adding a
fifth quantity is a new amendment, not an implementation detail.

The product line's standing vocabulary rule otherwise stands, and this ruling
narrows rather than loosens it. Not permitted on the matchboard, its render, its
scorecard ledger, or any surface derived from them: prices or returns of any kind;
total-goals or threshold fields; both-teams-to-score; a correct-score list; and
**no benchmark comparison column** — the accuracy benchmark of observation (c)
belongs to the internal walk-forward record and stays there, exactly as
[`reports/epl_walkforward.md`](epl_walkforward.md) says it does.

### The rationale

**The sentence came first, and that is the defect.** `marginal_parity` has been
telling every reader of a published `summary.md` that the simulated per-fixture
marginals *are* the published per-fixture forecast, while the bundle published no
such thing. There were two honest repairs — publish the surface, or withdraw the
sentence — and one dishonest one, which is to leave it. The owner's instruction
picks the first, and picking it changes the sentence from a claim about a missing
object into a claim about a file `check` can re-derive.

**Deriving from the rows is not a convenience, it is the only correct source.**
The engine already retains every simulated scoreline; the 38 provisionally widened
opener fixtures exist only in those rows; and A1 records that production truncates
at 10 goals and discards the tail. Re-pricing from particles or from a fresh grid
would publish a law nobody issued, and it would do it invisibly, because the two
laws agree almost everywhere. The rows are the run. Anything else is a
reconstruction wearing the run's name — which is exactly the objection A6 (d)
raises against putting a bridge arm's scorelines on a per-fixture surface, and the
same objection is why (a) is `dc_native` only.

**The anchoring is A6's argument applied to one more file.** A6 found six coats on
one defect: *a check whose inputs are chosen by the thing being checked.* A
matchboard is precisely the kind of file that invites the seventh coat — a
derived, human-readable artifact that no digest covers and that a reader trusts
because it looks like output. Putting it under `sidecar_digests` and under a
re-derivation on the way in costs one schema bump and closes it before it opens.

**`UNANCHORED` for pre-A7 records, for A6's reasons verbatim.** Passing the new
criteria vacuously on old records turns the leniency into the hole it exists to
avoid; failing old records for lacking a file that did not exist when they were
written says the published issuance is wrong, and it is not. The third answer —
*this criterion had nothing to hold this record against* — is the true one, and
A6 already built the verdict that says it.

**Naming what the MW0 rows do and do not inherit is the whole point of (d).** It
would have been easy, and wrong, to write that a matchboard derived from the
opener "inherits pre-kickoff provenance through the hash chain". Part of it does:
the law is anchored, in git, two days early, and that is a real and unusual
guarantee. The rows are not, because `data/` is not in git and the record predates
`sidecar_digests` — they are *reproducible*, which is a different and weaker
statement that this project can make honestly and should make in those words. An
entry that blurred the two would have been the ledger manufacturing an anchor for
a file the record explicitly reports as unanchored.

**No pass rule on the live ledger, deliberately.** The satisfaction bar is
accuracy parity with the World Cup edition. A live per-fixture record is how that
is eventually answered, and the temptation, once a number exists, is to let it
decide something. The World Cup edition's own scorecard leads with the honesty
rule — n = 104 gives wide intervals, the scorecard informs a decision and never
triggers one — and a Premier League matchweek is ten matches. Parity of surface
here means parity of restraint too.

### What is pre-stated

Fixed here, before the code exists and before any matchboard exists anywhere.

**1. The MW0 control, as exact counts.** Recomputed a **third** time on
2026-08-25, independently, from `rows_dc_native.npz` of the opener bundle:
`fixture_ordinals` column **5**, which is the rank of `2627:arsenal:coventry`
among the season's 380 sorted fixture ids. Over **n = 20,000** retained simulated
seasons (**1,000** particles, each used exactly **20** times, min = max = 20):

| outcome | count | probability | exact | cluster-by-particle SE |
|---|---:|---:|---:|---:|
| home | **15,278** | **0.763900** | 7639/10000 | 0.003511 |
| draw | **3,235** | **0.161750** | 647/4000 | 0.002800 |
| away | **1,487** | **0.074350** | 1487/20000 | 0.002006 |

The three counts sum to 20,000 exactly.

**A rounding trap, recorded because it would otherwise be built into a test.**
This session's two earlier pre-kickoff computations are carried into this entry as
**H 0.7639 / D 0.1618 / A 0.0743**. The first two are those probabilities rounded
to four places; **the third is `0.074350` truncated, not rounded** — round-half-up
gives **0.0744**. And the draw cell sits *exactly* on the four-place boundary
(`0.161750`). The three computations do not disagree about any number; they
disagree about how one of them is printed. **So the control is asserted on the
counts, or on the probabilities to 1e-9 — never on a rendered four-decimal
string.** A test that string-matched `0.0743` would have failed correct code, and
a test that string-matched `0.0744` would have contradicted this ledger.

**Margin fields for the same fixture**, same sample, same SE formula:

| field | value | exact | SE |
|---|---:|---:|---:|
| `e_margin` | **2.642600** | — | 0.020452 |
| `p_marg_ge2` | **0.612750** | 2451/4000 | 0.004215 |
| `p_marg_ge3` | **0.430550** | 8611/20000 | 0.004351 |
| `p_marg_ge4` | **0.291900** | 2919/10000 | 0.004036 |

**2. Invariants every matchboard must satisfy, on every fixture.**

* `p_home + p_draw + p_away == 1` to within **1e-9**.
* `p_marg_ge2 >= p_marg_ge3 >= p_marg_ge4`. The events are nested on one sample,
  so this is monotone **by construction** — a violation is a defect in the
  derivation, never a sampling accident, and the test must say so.
* `0 <= e_margin`, and `e_margin >= p_marg_ge2 + p_marg_ge3 + p_marg_ge4` is
  **not** asserted; nothing here needs it and an invented inequality is a future
  false failure.
* Every row's `n_sims` equals the header's, and the header's equals the record's
  `n_sims`; `n_fixtures` equals the record's `n_unplayed`.
* **Every SE clusters by particle.** The positive control is the one the project
  already uses: recomputing an SE as a binomial over `n_sims` gives a materially
  different number, and the test must show the derivation rejecting it rather than
  merely producing something.

**3. What `check` does, in both directions.**

* On a post-A7 (`epl-issuance-5`) bundle with a **bit-flipped** matchboard:
  **FAIL**. On the same bundle untampered: PASS — the positive control, without
  which the first half proves nothing.
* On a post-A7 bundle with the matchboard **deleted**: **FAIL**, naming the file.
* On a **pre-A7** bundle with no matchboard: the **`UNANCHORED`** line with
  `PRE_A7_NOTE`, **not FAIL**, and `fully_anchored` false.

**4. What A7 does to the committed opener's `check` output — pre-stated, because
it is pinned by tests and by A6's own transcript.** Adding two criteria that
report `UNANCHORED` on a pre-A7 record changes the opener's unanchored list.
Pre-stated:

* the **whole-bundle** run goes from **9 entries to 11** — the two additions are
  `dc_native.matchboard_anchored` and `dc_native.matchboard_reproduces`, and
  nothing is namespaced to a bridge arm, which is (a)'s `dc_native`-only rule
  showing up in the output;
* the **`--arm dc_native`** run goes from **5 entries to 7**;
* **neither headline changes in kind**: the whole bundle is still **FAIL**, exit
  **4**, for the reason A6 (b)'s landed note gives — its two bridge arms are
  REFUSED for want of arm sidecars, and that was true before A7 existed. The
  narrowed run is still **PASS**, exit **0**.
* the headline's parenthetical stops naming one round. Its shape becomes
  `PASS (<n> criteria unanchored: <reasons>)`, where `<reasons>` is the sorted
  distinct set of the unanchored entries' own notes. For the opener under `--arm
  dc_native` that is **`PASS (7 criteria unanchored: pre-A6 record, pre-A7
  record)`**. If the landed string differs, that is a **deviation** and is
  recorded in a dated note under A7 — the A6 (b.5) pattern — never smoothed over.

**Three tests must move in the same commit, and how they move is ruled here, not
left to the implementer.** `epl/tests/test_simcli.py` pins the old list in
`COMMITTED_OPENER_UNANCHORED`, pins the narrowed headline string, and asserts that
**every** `UNANCHORED` row carries `PRE_A6_NOTE`
(`test_the_committed_opener_reports_exactly_the_pre_A6_criteria_unanchored`); and
`test_the_committed_opener_whole_bundle_check_is_FAIL_and_the_ledger_says_so`
holds **every line of A6 (b)'s two fenced transcripts against live output**.

* The note-equality assertion becomes: each `UNANCHORED` row carries `PRE_A6_NOTE`
  **or** `PRE_A7_NOTE`, and the two matchboard entries carry `PRE_A7_NOTE`
  specifically. A weaker assertion — "one of the notes" with no per-entry
  expectation — is not acceptable: it is the shape of check that stops being able
  to fail.
* **A6 (b)'s fenced blocks are NOT edited.** They are the record of what the
  command emitted on 2026-08-20 under the code as it then stood, and A1-C1's rule
  applies to them. The commit appends a **new dated transcript note under A7**
  carrying the current output, and the test's ledger source moves to that note.
  A6's blocks stay in place and a test continues to assert they are **present and
  unedited** — the A2-N3 pattern, where a superseded statement stays where it was
  written and is superseded rather than erased.

**5. What A7 does not decide.** Nothing about the harness, the retrospective, the
arms, the nulls, the gate criteria, D11's thresholds, or which arm is published.
No number in R1, in Addendum A or B, in the opener bundle or in any published
report moves. `epl/simretro.py` and `epl/simmetrics.py` are not touched, so there
is no harness v6 and no new hash pair to record. `src/`, `scripts/`, `site/`,
`tools/` and `.github/` are not touched.

No threshold, count, field name or verdict above was chosen after seeing a result
under it, because no matchboard exists to have produced one. The single control
that is quoted from existing work — the `arsenal:coventry` row — is quoted as
counts recomputed here for the third time, from a bundle whose law was hash-anchored
in git before kickoff, and it is a control the code must reproduce rather than a
threshold anything was tuned to.

### Recording note

Written **before any line of the matchboard exists**: no `matchboard_dc_native.json`,
no `matchboard.md`, no derived artifact, no criterion, no test. The opener bundle
was re-verified at the moment of writing — three per-arm run digests recomputed
from the files on disk and equal to the record's `digests` map — and the control
in *What is pre-stated* was computed from those same files, on 2026-08-25, before
this entry was committed and before any code was written. The working tree at
`89d3d58` carried no change but this entry, and
`git diff --stat 89d3d58 -- src scripts site tools .github epl` is empty. **The
commit that records this entry precedes every commit that implements any of it.**

### What landed for A7 — `check` under the matchboard (recorded 2026-08-25)

`epl-issuance-5` is live, `matchboard_dc_native.json` and `matchboard.md` are
required sidecars of every issuance written from here on, and the committed
opener is untouched: it was not re-issued, not re-run and not edited, and no
matchboard was written into it. What follows is what the two documented commands
emit against that bundle under the new code. The JSON report goes to stdout and
is elided; these are the stderr lines and the exit code.

```
$ PYTHONPATH=src:. .venv/bin/python -m epl.simcli check \
      --directory data/epl/sim/issuances/2026_27/2026-08-21
[check] re-running dc_native at 2026-08-21 00:00:00 (N=20000, seed=20260611)
[check] dc_native: PASS
[check] dc_wdl_bridge: REFUSED — dc_wdl_bridge cannot be re-derived from this issuance: arms.json, bridge.json are missing. An issuance written before the arm sidecars existed carries no record of the fitted bridge or the Elo head, and a check that cannot rebuild the arm is not a passing check.
[check] elo_wdl_bridge: REFUSED — elo_wdl_bridge cannot be re-derived from this issuance: arms.json, bridge.json, elo_arm.json are missing. An issuance written before the arm sidecars existed carries no record of the fitted bridge or the Elo head, and a check that cannot rebuild the arm is not a passing check.
[check] record_digest: UNANCHORED — unanchored (pre-A6 record)
[check] acceptance_digest: UNANCHORED — unanchored (pre-A6 record)
[check] FAIL; unanchored: acceptance_digest, dc_native.matchboard_anchored, dc_native.matchboard_reproduces, dc_native.parity_reference_is_production_grid, dc_native.retained_rows_anchored, dc_native.truncation_sidecar_anchored, dc_wdl_bridge.retained_rows_anchored, dc_wdl_bridge.truncation_sidecar_anchored, elo_wdl_bridge.retained_rows_anchored, elo_wdl_bridge.truncation_sidecar_anchored, record_digest
$ echo $?
4
```

**Narrowed to the published arm**, which is the question A7's pre-statement 4 is
written about:

```
$ PYTHONPATH=src:. .venv/bin/python -m epl.simcli check \
      --directory data/epl/sim/issuances/2026_27/2026-08-21 --arm dc_native
[check] re-running dc_native at 2026-08-21 00:00:00 (N=20000, seed=20260611)
[check] dc_native: PASS
[check] record_digest: UNANCHORED — unanchored (pre-A6 record)
[check] acceptance_digest: UNANCHORED — unanchored (pre-A6 record)
[check] PASS (7 criteria unanchored: pre-A6 record, pre-A7 record); unanchored: acceptance_digest, dc_native.matchboard_anchored, dc_native.matchboard_reproduces, dc_native.parity_reference_is_production_grid, dc_native.retained_rows_anchored, dc_native.truncation_sidecar_anchored, record_digest
$ echo $?
0
```

*Arithmetic note: the two transcripts above quote verdicts, criterion names and
exit codes. Nothing in them is estimated, so nothing in them carries a
Monte-Carlo error. The float tolerance and the field count named below are
exact.*

**Pre-statement 4 landed exactly.** The whole-bundle run went from nine entries
to **eleven**; the `--arm dc_native` run from five to **seven**; the two
additions are `dc_native.matchboard_anchored` and
`dc_native.matchboard_reproduces` and nothing is namespaced to a bridge arm;
neither headline changed in kind — the bundle is still FAIL with exit 4 for its
two REFUSED bridge arms, the narrowed run still PASS with exit 0; and the
narrowed parenthetical is `PASS (7 criteria unanchored: pre-A6 record, pre-A7
record)`, character for character what A7 pre-stated. There is no deviation to
record on any of those.

**A6 (b)'s two fenced blocks are NOT edited.** They record what the command
emitted on 2026-08-20 under the code as it then stood, and every string in them
— nine entries, five names, `PASS (5 criteria unanchored: pre-A6 record)` — is
now false of the running code. A1-C1 is why they stay: a superseded statement
stays where it was written and is superseded rather than erased.
`test_the_committed_opener_whole_bundle_check_is_FAIL_and_the_ledger_says_so`
now holds every line of the two blocks **above** against live output, and
`test_the_A6_b_transcripts_are_present_and_unedited` holds A6's blocks in place
and asserts they carry no mention of the matchboard — the A2-N3 pattern.

**Where the landed code DEVIATES from A7, recorded rather than smoothed over.**

1. **Eleven floats pre-stated, FOURTEEN implemented.** A7 (b.3) says
   `matchboard_reproduces` compares "the eleven floating-point quantities per
   row" to 1e-12. The field table in A7 (a) that it is written beside names
   **fourteen**: `probs` (3), `probs_se` (3), `e_margin`, `e_margin_se`,
   `p_marg_ge2/3/4` (3) and `p_marg_ge2_se/ge3_se/ge4_se` (3). Eleven is the
   table with the three margin standard errors left out of the count. The code
   implements the **table** and compares all fourteen, because comparing fewer
   would leave three published quantities outside the criterion that exists to
   catch a moved number, and dropping the three fields to make the count read
   eleven would delete columns the ruling names. `epl.matchboard.ROW_FLOAT_FIELDS`
   is the enumeration and a test asserts its length is 14.

2. **The schema-version comparison moved from equality to an ORDINAL.**
   `_unanchored` decided the A6 leniency with `schema == ISSUANCE_SCHEMA_VERSION`.
   Bumping that constant to `epl-issuance-5` would have silently returned every
   `-4` record to the leniency A6 wrote for records that predate its fields — the
   fail-closed anchor becoming downgradeable by a version bump, which is the
   exact defect the Codex review of `04b26a2` closed one round earlier. The
   comparison is now `schema_ordinal(schema) >= A6_SCHEMA_ORDINAL`, and an
   unparseable version string resolves to the newest schema there is rather than
   the oldest, so writing nonsense into `schema_version` is not a way out of a
   check. A7 rules nothing about this; it is recorded because a strictness that
   is preserved by an edit nobody wrote down is a strictness the next edit will
   drop.

3. **The derived-artifact refusal lives inside `matchboard_anchored`.** A7 (b.3)
   says *exactly two* criteria and A7 (c) says `check` FAILs any bundle
   containing a file named like a derived artifact. Both hold: the refusal is the
   first thing `matchboard_anchored` evaluates, on **every** schema, so a stray
   derived file FAILs a pre-A7 bundle too — and no third criterion was added, so
   the entry counts above are the pre-stated ones.

Three points the implementation had to decide and A7 does not spell out, each
decided the strict way:

1. **A failure to write the matchboard aborts the whole issuance.** It is
   required, it is derived after the record's own numbers exist so it can carry
   them, and it is written into the staging directory before `summary.md` and
   well before `issuance.json`. A bundle silently missing one sidecar is the
   shape of defect A6 spent six findings on, so there is no partial-write path:
   the staging directory is discarded and no issuance appears.

2. **`n_provisional` is read from the gate's own count, and is `None` when no
   gate ran.** The render then says the count was not measured rather than
   printing a zero nobody counted.

3. **The scorecard ledger REFUSES an inadmissible row rather than dropping it.**
   A7 (e) makes a row admissible only if `cutoff` and `observed_by` are both at
   or before the fixture's kickoff as the season knew it. `epl.matchboard.score`
   raises naming the fixture and the offending stamp. A ledger that silently
   omitted the row it could not justify would be a ledger nobody can audit, and
   the omission would be invisible in the append-only file.

**What did not move.** No number in R1, in Addendum A or B, in the opener bundle
or in any published report. `epl/simretro.py` and `epl/simmetrics.py` are
untouched and still hash to the **v5** pair, so there is no harness v6 and no new
hash pair to record. `src/`, `scripts/`, `site/`, `tools/` and `.github/` are
untouched.
