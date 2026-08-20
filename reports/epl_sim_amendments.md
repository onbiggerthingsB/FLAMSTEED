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
