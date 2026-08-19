# EPL table simulator — preregistration of the v1.1 R1 retrospective

**Written:** 2026-08-19 · **Branch:** `epl-probe` · **Season opens:** 2026-08-21
**Status when written:** the R1 retrospective **has not been run**. No score for any
season other than 2025/26, and no score at any cutoff other than MW0 and MW10, exists
anywhere in this repository.

**2026-08-19 editorial:** four sentences reworded to remove wording reproduced from an
internal planning document; no design element, hash or number changed.

This document restates, from the harness source and before the run, exactly what R1
will do: which seasons, which cutoffs, which arms, which metrics, how they are
compared, what counts as a stop, and what the numbers are and are not allowed to
decide. It is written now because a validation design written after the first table
exists is a design written *by* that table.

Everything here is restated **from the code**, with file, function and line range, so
that a reader can check the claim against the harness rather than take this document's
word for it. The two harness files are hashed below; the hashes are what make "the
design was fixed first" checkable instead of asserted.

There is no betting content in this document or in anything R1 produces: no odds, no
market comparison, no stake. Monte-Carlo standard error is reported beside every
headline and **is not model error** — a tight SE on a badly specified model is still a
badly specified model. Table positions are table positions; "top 4", "top 5" and
"top 7" are not claims about qualification for any competition.

---

## 1. The harness, frozen

R1 runs `epl/simretro.py` (the schedule, the arms, the ledger, the scoring, the
report) over `epl/simmetrics.py` (the metrics). Both are at their state in this
commit, and neither is touched by this commit — this commit adds only this document.

| File | Lines | SHA-256 |
|---|---|---|
| `epl/simretro.py` | 911 | `2b25ab351710ed140047e56c2463d2cf9cda8996b8bf684732de04143b6cb805` |
| `epl/simmetrics.py` | 473 | `e73f2f70bdb5dfc42572aa7a5c19af4c5843e376a240e4d335c6edd5d451fb9a` |

Verify with:

```
shasum -a 256 epl/simretro.py epl/simmetrics.py
```

Schema identifiers carried into every ledger row and every score:
`epl-simretro-1` (`epl/simretro.py:83`) and `epl-simmetrics-1`
(`epl/simmetrics.py:68`).

**If either hash differs at the time R1 is run, R1 is not the run this document
preregisters.** A change to either file between this commit and the run must be
recorded as an amendment in `reports/epl_sim_amendments.md` *before* the change, in
the format that file already uses (observation → ruling → rationale → what is
pre-stated), and this document's hashes reissued alongside it.

---

## 2. Seasons

**2019/20, 2020/21, 2021/22, 2022/23, 2023/24, 2024/25, 2025/26** — seven, fixed at
`epl/simretro.py:87-88` (`SEASONS`).

2025/26 sits in `epl.windows`' excluded set. It is admitted here, and the reason is
narrow enough to state exactly: that exclusion exists because of **odds-coverage
bias**, and no odds column enters a league-table score. Nothing in R1 reads a market.
The bypass is therefore explicit rather than defaulted — `allow_excluded=True` is
passed at the single call site that builds the weekly grid,
`weekly_cutoffs` (`epl/simretro.py:122-133`), and the reason is written into that
function's docstring and the module docstring so it travels with the code.

Admitting 2025/26 is a decision with a cost, stated here rather than discovered later:
it is the season the T8 smoke was run on (§10), so it is the one season for which a
result is already known. It is one of seven blocks in the bootstrap and cannot be
quietly dropped afterwards; if it were dropped, this document would have to be amended
first.

---

## 3. The cutoff rule

Fixed at `epl/simretro.py:90-92` and implemented in `cutoff_schedule`
(`epl/simretro.py:136-165`). The rule is executed against the archive, not read from a
remembered list of dates — a hard-coded date list is a place for a convenient date to
hide.

- **MW0** — a season's opening weekly walk-forward cutoff: nothing has been played yet.
- **MWk**, k ∈ {3, 6, 10, 19} — the first weekly cutoff with `10k` or more of that
  season's fixtures dated behind it; those four thresholds are 30, 60, 100 and 190
  fixtures.
- **MW28** — computed by the same rule, **sanity check only, excluded from every
  comparison** (`SANITY_CUTOFFS`, `epl/simretro.py:92`). By late March the table has
  converged, TRPS is on its way to zero for every arm, and a difference there measures
  the calendar rather than the forecast. `run_retro` does not run it by default:
  the default cutoff set is `COMPARISON_CUTOFFS` (`epl/simretro.py:91`, applied at
  `epl/simretro.py:574`), so MW28 has to be asked for on purpose.

The weekly grid comes from `epl.walkforward.matchweek_cutoffs` at cadence 1, so the
feature-panel cache hits wherever it already exists.

**The point-in-time boundary.** The `10k` count is over fixture **dates**, and it
decides one thing only: *where to stand*. It is never how the simulator decides a
fixture is played. What is played at a cutoff comes from the results ledger, through
`epl.season`, exactly as it does in a live issuance. This is stated in both the module
docstring and `cutoff_schedule`'s own docstring because it is the single place where
this design could quietly become date-driven.

If a season never reaches a required count before any weekly cutoff, `cutoff_schedule`
raises `RetroError` and names the label. It does not silently fall back to the last
available cutoff.

---

## 4. Arms and nulls

Three arms (`ARMS`, `epl/simretro.py:94`), two nulls (`NULLS`,
`epl/simretro.py:95`), all constructed by `ArchiveRunner` (`epl/simretro.py:326-441`).

| Name | What it is | Built at |
|---|---|---|
| `dc_native` | The model. The per-particle Dixon-Coles scoreline grid, sampled directly. | `_provider`, `epl/simretro.py:422-433` |
| `dc_wdl_bridge` | The model's own 1X2 (including the mixture branch) → outcome → scoreline drawn from the empirical bridge. | same |
| `elo_wdl_bridge` | Frozen Elo ratings at the cutoff → an ordered-logit head fitted on pre-cutoff history → outcome → the same bridge. | same |
| `flat` (null) | The uniform 20×20 matrix. Available at every cutoff. | `_null`, `epl/simretro.py:436-441` |
| `ppg_pointmass` (null) | Points-per-game extrapolation as a single point mass on one projected ordering. | same |

**One engine, one ranker.** All three arms go through `leaguesim.simulate` and
`epl.table`'s ranker with common random numbers, so the *only* thing that differs
between them is how a fixture becomes a scoreline. A difference between arms is
therefore attributable to the scoreline law and to nothing else in the stack.

**One fit per (season, cutoff)**, shared by all three arms
(`ArchiveRunner._fit`, `epl/simretro.py:356-363`), run under
`epl.fit.config_read_once` exactly as `epl.walkforward` runs it. The empirical bridge
is fitted once per cutoff from all valid played matches dated before it, and its hash
is recorded in the row's provenance. The `date < cutoff` filter is applied **inside**
`EmpiricalBridge.fit` (`epl/bridge.py:211-230`) rather than trusted from the caller,
and the cutoff is part of the bridge's content hash, so two cutoffs can never be
mistaken for one bridge in an envelope.

**`ppg_pointmass` is undefined early and says so.** It requires every club to have
played at least `PPG_MIN_ROUNDS = 3` (`epl/bridge.py:92`, checked at
`epl/bridge.py:629-630`) — at the opener there is no rate to extrapolate, and after
one round the rate is estimated from one match. When it declines, `run_retro` writes a
`not_applicable` marker row (`_not_applicable_row`, `epl/simretro.py:473-492`) so the
key is claimed and a resumed run does not pay for the whole cutoff's fit again to
rediscover the same thing. `score_retro` skips those rows
(`epl/simretro.py:719`). This is pre-stated because the per-club minimum, not the
season-wide fixture count, is what governs: **it is possible for `ppg_pointmass` to
decline at MW3 in a season with an uneven early schedule**, and if that happens it is
expected behaviour, not a failure and not a result.

**Expected row count.** 7 seasons × 5 comparison cutoffs = 35 cells × 5 series = **175
keys**, of which the 7 `ppg_pointmass` rows at MW0 are `not_applicable` by
construction → **168 scored rows**, minus any further `ppg_pointmass` declines at MW3
as described above. MW28, if run as a sanity check, adds 35 keys that enter no
comparison.

---

## 5. The realised outcome

`realised_positions` (`epl/simretro.py:197-255`).

Final positions and points come from the archive season's 380 results plus the
adjustments ledger's **final** state — a season is scored against the table it actually
finished with, not against a point-in-time snapshot — placed through the simulator's
own ranker, so the forecast and the outcome are ranked by identical rules.

- `require_verified=True` is the default and R1 runs with it: **an unverified
  adjustment row refuses the season rather than scoring it.** The retrospective must
  not credit or debit a season against a deduction nobody has checked against the
  league's published record.
- A duplicate fixture in the archive raises rather than collapsing silently
  (`epl/simretro.py:222-225`).
- A **shared** finishing position is reported (`n_shared`) rather than silently
  ordered; both clubs take the shared rank. The count is printed in the report's sanity
  block.
- The `adjustments` override argument exists for tests and for a "what would it be
  without" control. It is **never** used for a published number.

---

## 6. The metrics

All in `epl/simmetrics.py`, which knows nothing about arms, seasons or cutoffs: it
takes a forecast and an outcome and returns a score. Every entry point refuses a matrix
that is not admissible — rows that do not sum to 1 make TRPS meaningless rather than
merely bad.

| Role | Metric | Function | Lines |
|---|---|---|---|
| **Primary** | TRPS, unweighted | `trps` | `149-162` |
| Secondary | wTRPS on published boundaries | `wtrps` + `consequence_weights` | `191-212`, `165-188` |
| Null reference | Flat-matrix TRPS, closed form | `flat_trps` | `215-237` |
| Diagnostic | Consequence Briers | `consequence_briers` | `244-266` |
| Diagnostic | Champion log loss, floored | `champion_logloss_floored` | `269-305` |
| Diagnostic | Points CRPS (exact) | `points_crps` | `323-338` |
| Diagnostic | Points MAE of E[pts] | `points_mae` | `341-349` |
| Diagnostic | Central 50 % / 90 % coverage | `interval_coverage` | `352-371` |
| Diagnostic | Boundary decider rates | `boundary_decider_rates` | `423-473` |

**The primary is TRPS, unweighted.** The tournament rank probability score of Ekstrøm,
Van Eetvelde, Ley and Brefeld (arXiv:1912.07364, eq. 2), reference string pinned at
`epl/simmetrics.py:71-73`. For a 20-club league with a full ranking this is the flat
`1/(20·19)` form: 20 clubs × 19 cumulative boundaries, every boundary counted once,
380 comparisons per forecast.

It is unweighted **on purpose**. A score concentrated on the four or five boundaries
the product publishes has far more variance across seven seasons than one aggregating
all 380, and it needs a band map that is ours rather than the paper's. The boundary-
weighted form is reported second, because it scores what the product shows.

**What TRPS is proper for, stated up front:** the *displayed marginals*, not the joint
law over the 20! orderings. Two forecasts with the same position matrix and different
correlation structure score identically. This document says so rather than implying
more.

**wTRPS weights** are equal on ranks r ∈ {1, 4, 5, 7, 17} (`CONSEQUENCE_RANKS`,
`epl/simmetrics.py:79`) and zero elsewhere, each 19/5 = 3.8 so the weights sum to
R−1 = 19 and the weighted score stays on the unweighted one's scale (enforced at
`epl/simmetrics.py:207-210`). The band map is **ours**: the paper's 2019 example
predates both a possible fifth Champions League place and this league's three-club
relegation. The 6|7 boundary does appear among the positions the ranker treats as
material when it resolves ties, but it is **not** a published position threshold, so
nothing here is weighted on it. (These five are the **consequence thresholds**: the
positional outputs the product displays — champion, top 4, top 5, top 7, relegation.
None of them is a price, a stake or an odds line, and nothing in this project reads one.
**Dated note, 2026-08-20:** this sentence previously used an older word for the same five
outputs; the wording is corrected in place under the project's vocabulary rule, and the
correction is recorded in [`reports/epl_sim_amendments.md`](epl_sim_amendments.md). The
rule renames the prose, not any identifier in the code, and it changes nothing about what
the five outputs are, how they are computed, or how they are scored.)

**The flat null is computed, not simulated** (`flat_trps`), in closed form
`(T+1)/(6T)` — **0.175** for 20 clubs, independent of the realised order. The null
therefore carries no Monte-Carlo error of its own, and every "beats flat" comparison is
against an exact number.

**Champion log loss is a diagnostic, not a headline.** It is local — it reads one cell
of the matrix and ignores everything the forecast said about the other nineteen clubs —
and it is infinite when a Monte-Carlo forecast never simulated the realised champion.
It is floored at `0.5/N` = **2.5e-5** at N = 20,000 (an unfloorable maximum of
−ln(2.5e-5) ≈ 10.597), and the honest report is the floored value **beside** the count
of how often the floor was needed. Both are returned; the report prints the total
zero-hit count in its sanity block. **Read `zero_hits` before reading `value`.**

**Points metrics are computed from an exact integer histogram** of the simulated
points, not from a summary: `points_histogram` (`epl/simmetrics.py:374-396`) preserves
the empirical distribution exactly, so CRPS, coverage and quantiles from the ledger
equal what the retained multi-gigabyte rows would give. CRPS uses the exact empirical
form `E|X − y| − ½E|X − X'|` in O(N log N). Interval bounds are empirical quantiles
taken with `method="lower"` on both sides, so an interval is a set of attainable
integer totals rather than an interpolation between them, and the test is inclusive of
the endpoints.

**The mean points residual is deliberately not reported.** The simulated and realised
tables hold nearly the same total number of points, so a mean residual cancels to near
zero however wrong the forecast is. MAE of E[pts] is reported instead.

**Monte-Carlo error** is carried on every simulated arm (`ArmResult.mc`,
`epl/simretro.py:263-310`; printed as the `MC SE` column, `epl/simretro.py:801-803`)
and is cluster-by-particle. It is not model error, and the report says so in its own
header text.

---

## 7. The comparison

`score_retro` (`epl/simretro.py:708-794`).

- **Pairings:** `dc_native − dc_wdl_bridge` and `dc_native − elo_wdl_bridge`
  (`DEFAULT_COMPARISONS`, `epl/simretro.py:97-98`).
- **Paired within an occasion**, keyed by (season, cutoff label, cutoff date, seed,
  n_sims) — the same fit, the same fixtures, the same random slots
  (`epl/simretro.py:739-745`).
- **Metric compared:** TRPS.
- **Resampling:** season-block bootstrap, blocks are seasons, **10,000** resamples
  (`N_BOOT`, `epl/simretro.py:102`), **percentile** CI, via
  `epl.score.block_bootstrap_ci` (`epl/score.py:193`), whose own resampling seed is
  fixed at **20260814**. Blocks are resampled with replacement and the statistic is the
  pooled mean, so unequal block sizes are weighted the way the estimator is.
- **Per cutoff index.** A comparison exists at MW0, at MW3, at MW6, at MW10 and at
  MW19, separately. There is no pooled interval.

### There is no pass rule

**Seven blocks. The intervals will be wide, and this is a diagnostic with no pass
rule.** Shipping does not depend on it. No interval in this run, at any cutoff, in any
direction, is by itself a decision — see §11 for who decides and how.

This is pre-stated so that a wide interval cannot later be read as "inconclusive,
therefore keep what we have" *and* a narrow one cannot be read as "significant,
therefore switch". Both readings would be inventing a rule after the fact.

---

## 8. The two hard checks, and the one thing never averaged

### Check 1 — `dc_native` beats the flat null at every (season, cutoff)

Computed at `epl/simretro.py:765-770` and surfaced as
`sanity.dc_native_beats_flat_everywhere`, `sanity.violations`, and
`sanity.STOP_AND_INSPECT`. The report prints it and, on violation, prints the offending
cells.

**A violation is STOP-and-inspect, not a finding.** The model failing to beat a uniform
matrix at some cutoff of some season is far more likely to be a defect in the harness,
the fit, the archive or the ranker than a fact about football. The response is to stop
and find the defect. It is specifically **not** licence to swap the published arm, and
it is not a result to report as one.

### Check 2 — coherence

Every arm's matrix and every null's matrix must satisfy the coherence conditions
(doubly stochastic to tolerance: each club's row of position probabilities sums to 1
and each position's column sums to 1). Enforced twice, on purpose:

- inside the runner, immediately after each simulation and each null
  (`epl/simretro.py:392`, `epl/simretro.py:402`), and
- again in `_check_clubs` (`epl/simretro.py:643-651`), which also verifies the matrix
  is exactly (n_clubs × n_clubs) for the clubs of that season.

A failure raises before anything is written to the ledger.

### Never averaged across cutoffs

A forecast at the opener and a forecast at matchweek 19 answer different questions, and
a pooled TRPS would describe neither. This is enforced structurally, not by convention:

- `epl/simmetrics.py` scores one forecast at a time and has no aggregation at all;
- `score_retro` aggregates strictly **within** a cutoff label
  (`epl/simretro.py:724-737`);
- `report` (`epl/simretro.py:812-874`) prints one line per (cutoff, season, arm) and
  has no headline row;
- the scores dict carries `never_averaged_across_cutoffs: True`.

**There will be no single headline TRPS for R1.** If a summary of R1 ever quotes one
number as "the model's TRPS", that number was constructed outside this harness and is
not a result of this preregistered run.

---

## 9. Run parameters, identity, and the ledger

| | |
|---|---|
| **N** — simulated seasons per arm per cutoff | **20,000** (`DEFAULT_N_SIMS`, `epl/simretro.py:100`) |
| **S** — posterior draws (particles) | **1,000** |
| **Seed** | **20260611** (`SEED`, `epl/simretro.py:101`), **one seed only** |
| Bootstrap resamples · seed | 10,000 · 20260814 |
| Ledger | JSONL, append-only, resumable |
| Verified adjustments required | yes (`require_verified_adjustments=True`) |

**One seed.** R1 is not a seed sweep, and a second seed is not a second result. Monte-
Carlo error is reported per row from within the run; running a different seed to see
whether the sign flips would be a different experiment and would need its own
preregistration.

**Identity and resumability.** Each row's `run_key` is
`season|cutoff_label|date|arm|n{N}|s{seed}` (`run_key`, `epl/simretro.py:456-465`) —
the *question*, not the answer. The answer's fingerprint travels beside it as
`envelope_hash`, over the run envelope and provenance with clock-measuring fields
(`wall_seconds`, `fit_seconds`, `seconds`) removed (`_VOLATILE`,
`epl/simretro.py:111`), so two identical runs on different days agree. Every forecast
is a pure function of (season, cutoff, arm, N, seed) and the frozen configuration, so a
resumed run is the same run: `run_retro` (`epl/simretro.py:543-640`) skips keys the
ledger already holds, and a crash costs the forecast in flight and nothing else.

**Each row keeps** the position matrix and its SE, the consequence-threshold
probabilities, the tie diagnostics, the exact points histogram, the realised outcome,
and the provenance of the fit that produced it — including
`effective_posterior_hash`, `bridge_hash`, cold-start and provisional club lists,
played/unresolved counts and the known adjustments (`_row`,
`epl/simretro.py:495-534`). Every metric in §6 is computable from the ledger alone,
without a rerun.

---

## 10. What is already known — the T8 smoke, quoted here so it cannot surprise anyone later

The harness has been run once on real data, as the T8 smoke: **2025/26 only, at MW0
and MW10**, all three arms plus both nulls, at the full N = 20,000. It is recorded at
`data/epl/sim/retro_smoke.md` and `data/epl/sim/retro_smoke.jsonl`.

**In that smoke, the Elo arm scored a slightly better TRPS than `dc_native` at both
cutoffs.** Quoted exactly, so that it is on the record before R1 rather than
rediscovered after it:

| cutoff | season | arm | TRPS | flat TRPS |
|---|---|---|---|---|
| MW0 | 2025/26 | `dc_native` | **0.1356** | 0.1750 |
| MW0 | 2025/26 | `dc_wdl_bridge` | 0.1349 | 0.1750 |
| MW0 | 2025/26 | `elo_wdl_bridge` | **0.1327** | 0.1750 |
| MW10 | 2025/26 | `dc_native` | **0.0941** | 0.1750 |
| MW10 | 2025/26 | `dc_wdl_bridge` | 0.0937 | 0.1750 |
| MW10 | 2025/26 | `elo_wdl_bridge` | **0.0891** | 0.1750 |

Paired differences from that run: `dc_native − elo_wdl_bridge` = +0.00283 at MW0 and
+0.00500 at MW10 (positive = `dc_native` worse, TRPS being a loss). `dc_native −
dc_wdl_bridge` = +0.00069 and +0.00045.

**What that is and is not.** It is **one season**, at two cutoffs, with **one block** —
so the "CI" printed in the smoke is a degenerate interval on a single number and
carries no information about sampling variability. It is not evidence that the Elo arm
is better; it is not evidence that it is not. Both §8 hard checks held in the smoke:
`dc_native` beat the flat null at both cutoffs (2 of 2 checked) and every matrix passed
coherence. The smoke also reported zero champion log-loss floor hits and zero shared
realised positions.

It is quoted here for one reason: **this direction is already known before R1 runs.**
If R1 reproduces it across seven seasons, that is a finding to be adjudicated on the
record — not a surprise, and not something this project can present as one. If R1
reverses it, that too has to be read against the fact that the smoke pointed the other
way. Either way, nobody gets to claim the sign was unanticipated.

The smoke ran at **N = 20,000, seed 20260611** — the R1 parameters — and the cutoff
rule of §3 placed 2025/26's MW0 at **2025-08-15** and MW10 at **2025-11-22**. Its ten
ledger rows therefore carry `run_key`s that **collide exactly** with ten of R1's, for
example `2025/26|MW0|2025-08-15|dc_native|n20000|s20260611`. R1 must therefore either
write to a **fresh ledger path** or knowingly resume those rows. Which of the two is
used will be recorded in the R1 report; either is reproducible, and neither changes a
number, because the key is the question and the forecast is a pure function of it.

The smoke's `ppg_pointmass` row at MW0 is the `not_applicable` marker described in §4
— the mechanism is not hypothetical, it has already fired once.

---

## 11. What this decides — and who decides it

R1 informs three decisions, all of which are **owner rulings, made after the tables
exist**, recorded as written amendments in `reports/epl_sim_amendments.md`:

1. **Whether `dc_native` remains the published arm.**
2. **D2** — whether horizon widening is introduced. A fit today pins every club's
   strength at its cutoff value for the rest of the season, and the reports label the
   forecast as such wherever they show one. The retrospective reports per cutoff
   precisely so the horizon cost is *visible*; that visibility is the only thing that
   may motivate widening.
3. **D12** — whether the widening mixture branch moves from a per-fixture Bernoulli
   draw to the per-season variant.

**The default, absent a ruling, is unchanged in every case:** `dc_native` stays the
published arm (as issued on 2026-08-21), D2 stays static-within-fit, D12 stays
per-fixture. R1 producing numbers does not by itself change anything. No agent, no
script and no report may switch the published arm on the strength of these numbers; the
harness has no code path that would do so, and this document is the reason there
shouldn't be one.

**Timing.** R1 executes no later than the seventh day after the opener, and **no
public accuracy claim** is made for this simulator until it has.

**What a ruling has to survive.** Any ruling that changes 1, 2 or 3 has to contend with
the fact that the comparison has no pass rule (§7), that seven blocks give wide
intervals, and that the smoke's direction was known in advance (§10). "The interval
excluded zero" is not, on its own, a sufficient rationale, and this document exists so
that saying so later is not a moving of goalposts.

---

## 12. What would invalidate this preregistration

Recorded so the failure modes are named rather than negotiated:

- **Either harness hash in §1 differs at run time** without a prior amendment. The run
  is then not this run.
- **A season, cutoff, arm or null is dropped** from §2–§4 after the run starts, for any
  reason other than a documented refusal the code itself raises (an unverified
  adjustment row, a season that cannot reach a cutoff's fixture count, `ppg_pointmass`
  declining on the per-club minimum). Refusals are reported; deletions are amendments.
- **A metric is promoted or demoted** after the tables exist. TRPS unweighted is the
  primary. wTRPS is secondary. Everything else in §6 is a diagnostic. Nothing in this
  list moves after the fact.
- **Any number is averaged across cutoffs** (§8).
- **A second seed, a second N, or a second bootstrap seed** is run and reported as if it
  were R1.
- **MW28 enters a comparison.** It is a sanity check on a degenerate regime and nothing
  else.
- **A pass rule is invented** for the paired differences, in either direction, after
  they are seen.

---

## 13. Standing disclaimers

- Everything R1 scores is a **forecast made at a past cutoff**, conditional on the
  strengths at that cutoff staying fixed for the remainder of that season. That
  conditioning is a named, unmodelled limitation, not an oversight.
- **Monte-Carlo standard error is not model error.** Both are reported; only one of
  them shrinks with N.
- The approximate posterior is mean-field with S = 1,000 draws. Its under-dispersion is
  a known and separately scheduled sensitivity; no "honest tails" language attaches to
  any R1 number.
- **Positions are positions.** Thresholds at ranks 1, 4, 5, 7 and 17 are table
  positions, not claims about qualification for, or exclusion from, any competition.
- **No betting content.** No odds, no market comparison, no stake — here, in the
  harness, or in anything R1 emits.

---

*Preregistered 2026-08-19, before the R1 retrospective was run. Harness hashes in §1
are what make that claim checkable.*
