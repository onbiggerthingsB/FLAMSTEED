# PREREG — OA development verdict: odds-anchored arms vs incumbent (spec OA-5)

**STATUS: LOCKED. Sealed at lock-v1 (2026-08-02); the lock-time blanks below
were filled at lock-v6 from values already bound BEFORE the scored-pool run
(citations per item). Every post-lock change is a dated amendment entry and a
new chained lock — v1..v5 remain readable and still carry the DRAFT text, so
this completion cannot be mistaken for what was preregistered all along.**

Drafted 2026-07-31 (OA Foundations Plan 1, Task 7), BEFORE any scored-pool run.
Relocated 2026-08-01 from the gitignored
`docs/superpowers/specs/2026-07-28-oa-prereg-DRAFT.md` to this TRACKED path
(Codex Plan-2 batch-3 finding B3-1, BLOCKER, controller-ruled): the V8 lock
hashes this document, and a hash of untracked bytes is unattributable — the
prereg is methodology and belongs in the published tree, while strategy
content stays in the gitignored program-design spec. See the amendment log.
Template: the 2026-07-02 B/K prereg (archived at
`.superpowers/docs-archive/superpowers/specs/2026-07-02-bk-levers-prereg.md`),
extended per spec OA-5. Governing spec:
`docs/superpowers/specs/2026-07-28-odds-anchored-accuracy-program-design.md`
(v2 — all 16 Codex findings accepted; internal working doc, not tracked).
Lock procedure: Plan 2 fills the lock-time blanks below from the OA-0a
live-probe report, dates a LOCKED header, and commits — only then may the
first scored-pool run start.

## Frame (spec findings 1/9/15 — binding on every claim below)

This is an **exploratory transfer test**, not a confirmed-gain program. Every
existing pool is development data: the 185-pool selected k=0.6, and the
WC-2026 group-72 + knockout-32 were scored in the July capstone and market the
product. Nothing we currently hold can confirm anything. The **development
verdict** on the reused pools decides ONLY what enters the confirmatory test.
The **confirmatory lockbox is the AFC Asian Cup 2027 group stage, run LIVE**
(genuinely future, odds-covered, single pass, pre-registered before kickoff).
Production adoption of any odds arm waits for that confirmation; until then
odds arms are development-only, and no "market-grade accuracy" marketing claim
is made before confirmation (finding 15). A null is a real, publishable answer.

## Arms

- **E′ (PRIMARY, spec OA-1):** frozen-incumbent prediction-time blend. The
  incumbent posterior is fit UNTOUCHED (bitwise identical to production,
  k=0.6). At prediction time, for a fixture with admissible odds, the model's
  scoreline-implied rates are blended with bookmaker-implied rates; `w` is a
  single scalar learned by rolling CV on the development table, conditional on
  production k=0.6 (finding 12: no joint retune). Coherence invariant
  (finding 10): at w=1 the blended forecast must reproduce the de-vigged 1X2
  vector through the ACTUAL production scoring map (including the Dixon-Coles
  rho correction), enforced by test; rate-recovery solver failure ⇒ odds marked
  unavailable for that fixture (no symmetric-split fallback ever). Odds-absent
  fixtures: untouched incumbent output, exactly, by construction.
- **Incumbent benchmark:** the production model REGENERATED per-fixture at the
  `T_issue` information set below, via the existing walk-forward engine — the
  frozen pre-tournament fits from the B/K run are not information-set-comparable
  and are not reused (finding 2).
- **Secondary arms (the Holm-corrected family — EXACTLY four members;
  amendment 2026-08-01):** E′ under the de-vig method NOT selected (the de-vig
  choice itself made on the development table, inner validation, never on
  scored pools), S = stacking (1X2 only — diagnostic ceiling-check for E′,
  ineligible for scoreline/tournament surfaces; finding 6), the Elo
  ordered-logit head (odds-free; `wcmodel/eval/elo_ordlogit.py`), and the
  50/50 Elo-ordered-logit + DC average. Membership, the one-sided
  block-bootstrap p-values, Holm at α=0.05 and the fixed cardinality are
  enumerated in `reports/oa_analysis_spec.md` (hash-bound at the lock).
- **E-full (spec OA-2)** is research-only, pursued only after E′ has a verdict,
  and is NOT part of this prereg's test family.

## Information set (finding 2)

One pre-registered issuance timestamp **`T_issue` per fixture: 09:00 UTC on
the matchday** (matching the daily production cadence), where **matchday =
the venue-LOCAL calendar date of kickoff** (the scheduled `date` field in
`config/tournament_2026.yaml`) — NOT the UTC calendar date of the kickoff
instant. The two readings are not equivalent: 36 of the 104 WC-2026 fixtures
(evening Americas kickoffs) roll past midnight UTC, and under the UTC-date
reading their `t_issue` lands 5–9 h AFTER kickoff with an odds cut that is
post-kickoff too — in-play prices would sail through `admissible_quote`.
Concrete case: South Korea v Czech Republic, local 2026-06-11 20:00 UTC−6 =
kickoff 2026-06-12T02:00Z; the UTC-date `t_issue` would be 2026-06-12T09:00Z
(7 h post-kickoff; odds cut 08:30Z, also post-kickoff). The Odds API reports
`commence_time` as UTC ISO8601, so the UTC date is the natural-LOOKING join
key: **Plan 2 must map `commence_time` to the venue-local matchday when
joining odds to fixtures, never truncate it to the UTC date.** euro2024 and
wc2022 (UTC+2/+3, afternoon–evening kickoffs) have no rollover, so a misjoin
would not be caught by accident on those pools. Every arm — including the
incumbent benchmark — is issued from the same `T_issue`:

- **Pre-kickoff invariant (binding): `T_issue` < kickoff, strictly** — hence
  the odds cut `T_issue` − 30 min sits ≥ 30 min pre-kickoff. Enforced
  structurally, not by convention: every ledger row carries tz-aware
  `kickoff_utc`, and a row with `t_issue >= kickoff_utc` is rejected at
  write AND on load, so the UTC-date misjoin above cannot produce a
  scoreable row whatever produced it (pinned with the concrete case by
  `tests/eval/test_ledger.py::test_wc2026_rollover_fixture_pins_local_matchday_not_utc_date`).
  A fixture whose kickoff is not strictly after 09:00 UTC on its venue-local
  matchday cannot be issued at the default `T_issue` and is EXCLUDED from
  odds-scored evaluation rather than re-timed (none exist in the current
  development pools — the WC-2026 minimum kickoff−`T_issue` margin is 7 h;
  any alternative `T_issue` would be a dated amendment).
- Odds quotes require snapshot ts AND bookmaker `last_update` earlier than
  **`T_issue` − 30 min** (safety buffer, strict). Shipped contract:
  `admissible_quote` in `src/wcmodel/data/sources/odds.py` — STRICT `<` on
  BOTH legs (the stricter reading of the spec's `≤`); a missing bookmaker
  stamp is resolved by the caller to the strictest evidence present
  (`strictest_last_update`: the LATEST of the stamps present, the snapshot ts
  only when there is none) — never an unconditional snapshot-ts fallback.
- Model fits use training cutoff ≤ `T_issue`.
- Every issued forecast is a row in the common ledger
  (`src/wcmodel/eval/ledger.py`): `fixture_id, pool, date, home, away,
  kickoff_utc, t_issue, training_cutoff, arm, p_home, p_draw, p_away,
  issued_git, odds_snapshot_hash`. Enforced at write time and re-checked on
  load: `t_issue` exactly 09:00 UTC on the fixture's venue-local matchday
  (`date`), `t_issue` strictly before `kickoff_utc`, `training_cutoff >
  t_issue` rejected, duplicate `(arm, fixture_id)` rejected, probabilities
  sum to 1 ± 1e-9.

## Settlement contract (finding 3)

Bookmaker 1X2 settles at **90 minutes**. The curated regulation-time table
(`config/regulation_time_results.yaml`, loader
`src/wcmodel/eval/regulation.py`) holds verified 90' scores for all 63
knockout fixtures in the development pools (wc2022 16, euro2024 15, wc2026 32;
ET-count pin 19 = {wc2026: 9, wc2022: 5, euro2024: 5}). ET-inclusive finals
are never used to infer 90' outcomes. **Any KO fixture without a verified 90'
score is EXCLUDED from odds-scored evaluation — never inferred.** (Current
table: complete, 63/63, store-joined; the exclusion rule stands for any future
row that fails verification.)

## Scoring (finding 16)

Per-match 3-way 1X2 RPS, ONE canonical implementation:
`wcmodel.model.calibration.rps` — the ÷2-normalized convention, range [0,1]
(golden-tested in `tests/eval/test_rps_canonical.py`; `devig_select._rps`,
`baselines.rps` and `report._rps` all delegate). **Every threshold in this
prereg (the −0.002 floor, the MDE table) is on this canonical scale**, and so
is the noise model: the July B/K per-match JSONs it is built from are
canonical-scale (per-match max 0.905 < 1, mean ≈ 0.19 — the production
scorecard scale).

## Primary contrast + secondaries (spec OA-5)

**One primary contrast: E′ vs incumbent, pooled development RPS.** Everything
else (E′ under the other de-vig, S, the Elo ordered-logit head, the 50/50
Elo+DC average) is **secondary, Holm-corrected** — one family of exactly four,
corrected together, reported together. The full statistics — populations,
p-value definition, sign-flip veto, jackknife, MDE re-statement rule — are
enumerated in `reports/oa_analysis_spec.md`, hash-bound at the lock.

## Adoption gate — entry into the AC2027 confirmatory test (spec OA-5)

**ΔRPS ≤ −0.002 (practical floor; canonical scale; negative = arm beats
incumbent) AND ≥80% support under stratified block bootstrap (blocks =
pool × matchday)**, blocks resampled with replacement WITHIN pool strata;
support = fraction of bootstrap means < 0. Implementation:
`wcmodel.eval.power.block_bootstrap_support` (finding 8). **Team-overlap
sensitivity reported; per-pool effects reported separately — no cross-pool
sign-flip.** Point estimates never adopt.

## Measured MDE (Task 1: `reports/oa_mde.md`, seed 0) + pre-committed verdict language

Noise model: EMPIRICAL per-match paired RPS differences between two real arms
(k=0.5 vs k=0.6) on the same 185-fixture panel (sd = 0.01334) — preserves the
heavy tails. Gate power by true per-match effect δ (n_sims 400, n_boot 1000):

| true δ | power |
|---|---|
| 0.000 | 0.03 |
| 0.001 | 0.15 |
| 0.002 | 0.51 |
| 0.003 | 0.83 |
| 0.004 | 0.98 |
| 0.006 | 1.00 |
| 0.010 | 1.00 |

**MDE (smallest δ with power ≥ 0.80): 0.003** — INSIDE the
literature-plausible 0.002–0.004 band, not below it: the pool resolves the top
of the band but not the bottom (power at δ=0.002 is 0.51 — a coin flip).

**Conditioning (binding on every use of these numbers):** the table is a joint
property of n=185 AND sd(noise)=0.01334 — a CHOSEN arm contrast, not a
measured constant of the pool. By dispersion the headline ranks 2 of 6 among
the contrasts measured on this same pool (1 = tightest; `reports/oa_mde.md`
"Noise-model sensitivity"), and the full spread runs BOTH ways: k0.7 vs k0.6
is TIGHTER than the headline (sd=0.01014, MDE still 0.003) — a real arm
contrast as tight as the headline does exist — while under k0.8, k0.4 and
nuts_k0.6 the MDE moves to 0.004, and under k0.0 (sd=0.08044) NO δ in the
grid reaches power 0.80 — that contrast cannot resolve the band at all. The
lower-bound reading rests on the sampler-jitter benchmark, not on the
headline being the tightest possible: nuts_k0.6 vs k0.6 differs only in
inference backend — pure sampler jitter, zero arm change — and is already
2.4× more dispersed than the headline noise model. The only contrasts at or
inside the headline's dispersion (k0.7, k0.5) are 0.1 k-nudges between
otherwise-identical fits; E′ perturbs forecasts at prediction time by a
market blend, far more than a 0.1 k-nudge, so its realized dispersion is
EXPECTED to exceed the headline's, and **the headline MDE 0.003 is read as a
LOWER BOUND on the detectable effect, not an estimate of it** — a
pre-committed expectation, not a theorem: the k0.7 row is the standing
counterexample that a real arm contrast CAN be tighter, and the lock-time
blank below re-states the MDE from the realized contrast if it materially
differs.

**Binding constraint (conditioned form):** at n=185 AND sd(noise)=0.01334 the
mean ≤ −0.002 floor is the binding half of the gate, and the ≥80% support
requirement is a sign/robustness check rather than a second binding hurdle
(0 of 1804 floor-passing simulated panels were support-rejected; min support
among floor-passers 0.962). This is conditional on the noise model, NOT an
unconditional property of n: on the k0.4 contrast (sd=0.02972) support DOES
reject floor-passers (4; min support 0.774) — under a more dispersed realized
contrast the support half can bind.

**Panel-generation limitation (controller/Fable review, 2026-07-31):**
`simulate_power` draws each simulated panel iid from the centered empirical
diffs; only the SUPPORT stage models block dependence. If paired diffs
correlate positively within matchdays, iid generation understates the variance
of the panel MEAN, making the floor's power — and therefore the MDE —
optimistic at any given sd. This compounds the noise-model conditioning above
in the same direction: real detectability is no better than stated, possibly
worse. At lock, estimate the within-matchday correlation of the realized
paired diffs; if materially positive, re-run the grid with block-resampled
panel generation before re-stating the MDE.

**Machinery evidence:** the power curve's monotone shape is BY CONSTRUCTION
(common random numbers across the δ grid — nested simulations) and is NOT
evidence the gate machinery works. That evidence is `tests/eval/test_power.py`
(null-support, large-effect, and monotonicity tests on the actual
bootstrap-and-gate pipeline).

**Pre-committed verdict language** (conditional on n=185 and the headline
noise model): a gate FAIL is evidence against true effects ≥ ~0.004 but NOT
against a true 0.002 effect. A FAIL is therefore recorded as
**DIRECTIONAL-ONLY / inconclusive**, never as "no effect" — "inconclusive" is
a permitted outcome (spec OA-5), and the real test is AC2027 either way. If
the locked scored set or the realized arm contrast is materially more
dispersed than the headline noise model, the inconclusive band WIDENS and the
verdict must say so explicitly.

## Diagnostic 2×2 (finding 12)

**Elo-anchor on/off × odds on/off, reported regardless of verdict — the
double-anchor interaction is the scientific question here.** Diagnostic only:
never an arm-selection channel; `w` stays conditional on production k=0.6 (no
joint retune).

## Confirmatory rule (spec OA-5)

**The AC2027 group stage is scored ONCE, live, against the pre-registered arm;
pass ⇒ production adoption + only then any public accuracy-framing change.**
Single pass means: no second look, no post-hoc arm swap — the arm that enters
is the one this prereg's development gate selected, frozen before AC2027
kickoff. Until that pass, red lines stand: no odds in any public output
(denylist + scans), and the September AFCON releases are odds-absent incumbent
either way.

## Lock-time blanks — FILLED at lock-v6 (2026-08-02)

Every value below was bound BEFORE the scored-pool run and is already
recorded in an earlier lock or in the selection trace; the citation on each
line says where. This section is transcription, not choice. It was left
unfilled through v1..v5 by oversight, and the earlier versions still carry
the empty boxes, so the omission is visible rather than papered over.

- [x] **Scored set: 217 of 217 admissible.** No pool dropped: WC-2022
      coverage did NOT predate provider completeness, contrary to the risk
      flagged at draft time. Per-pool: wc2026 104, wc2022 63, euro2024 50.
      *Bound in* `lock-v1.scored_inventory` (2026-08-02, before issuance);
      re-attested identically at v2..v5.
- [x] **Sport keys VERIFIED live.** Five keys 404'd on first use; the free
      `/v4/sports?all=true` listing corrected three keys and two dates.
      Config-only, no code change, exactly as the draft required.
      *Bound in* `config/config.yaml` `oa_dev_slate.acquisition.sport_keys`
      and the G-A/G-B acquisition journal.
- [x] **Pre-kickoff invariant verified, all 217.** Every scored fixture's
      kickoff is strictly after its 09:00 UTC `t_issue` on the venue-local
      matchday; 36 UTC rollovers confirmed. Enforced twice — at manifest
      build (hard refusal) and again per row by `LedgerWriter._validate`,
      which rejects `t_issue >= kickoff_utc`.
      *Bound in* `config/oa_eval_manifest.yaml` (hashed by every lock).
- [x] **N_dev = 259.** Sized at 300, amended to 260 on the supply limit,
      then to 259 when market coherence (overround ≥ 1) was ruled part of
      ADMISSIBILITY after the walk caught a corrupt archived Pinnacle draw
      price (309.0, overround 0.797) on Argentina v Ecuador. All three
      rulings are dated and outcome-blind.
      *Bound in* `config/oa_dev_manifest.yaml` + the amendment log below.
- [x] **De-vig: multiplicative.** Chosen on the development slate under
      inner validation only, never on the scored pool. (The draft framed
      this as "Shin vs basic"; 'basic' resolves to multiplicative as the
      reporting label — see `wcmodel.eval.arms`.)
      *Bound in* `reports/oa_selection_trace.json` (pre-issuance).
- [x] **MDE re-stated: 0.008 at 80% power.** The locked set (217) and the
      realized noise model both differ from the draft's n=185 / sd=0.01334,
      so this is restated as the conditioning section requires: r_dev
      −0.1168, iid generation, noise sd 0.06324. The observed development
      effect (0.00504) is SMALLER than the MDE, so power at that effect is
      roughly 0.6 — a non-adoption on this design would have been weak
      evidence of no effect, and that limitation is recorded rather than
      argued afterwards.
      *Bound in* `lock-v2.power` (before issuance), unchanged since.

## Execution discipline (B/K template, carried over)

- This document is DRAFTED before any scored-pool run; the LOCK commit lands
  before the first scored run and pins HEAD (ledger rows carry `issued_git`;
  odds rows carry the raw-response sha256 archived at ingest).
- Ledger rows are the raw evidence; one report carries the primary verdict
  line, the Holm-corrected secondary table, per-pool effects, team-overlap
  sensitivity, and the 2×2 — regardless of verdict.
- Kaggle/public odds dumps (finding 14): admissible only with named+hashed
  dataset, license, upstream collector, bookmaker identity, market contract,
  per-fixture timestamps with timezone, and a blinded stratified validation
  against an independent source; no per-fixture timestamps ⇒ dev-only at most,
  flagged, excluded from confirmatory use.

## Amendment log

**2026-08-01 — per-tier `w` REMOVED from the secondary Holm family
(pre-lock).** The family listed in "Arms" and in "Primary contrast +
secondaries" named a fifth member, per-tier `w`, that has no implementation
and no fold protocol: the V6 selection spec fits ONE scalar `w` by monthly
chronological CV on the dev ledger, and nothing in the program produces or
validates a per-tier variant. A family member that cannot be computed either
inflates the Holm correction for nothing (every other member's threshold
divided by 5 instead of 4) or gets dropped after the fact, which is exactly
the researcher degree of freedom the pre-registration exists to remove
(Codex Plan-2 finding 6, BLOCKER). The family is therefore fixed at EXACTLY
four: E′ under the non-selected de-vig, S (stacking), the Elo ordered-logit
head, and the 50/50 Elo-ordered-logit + DC average. Enumerated with their
nulls, the one-sided block-bootstrap p-value and Holm at α=0.05 in
`reports/oa_analysis_spec.md`, which the V8 lock hash-binds. This amendment
lands BEFORE the lock and before any scored-pool issuance, so no issued
forecast or scored result is affected; it is logged here because the family
is a pre-registered object either way.

**2026-08-01 — prereg relocated to the tracked `reports/oa_prereg.md`
(pre-lock; Codex Plan-2 batch-3 finding B3-1, BLOCKER, controller-ruled).**
This document lived at the gitignored
`docs/superpowers/specs/2026-07-28-oa-prereg-DRAFT.md`, so the V8 lock's
`prereg_sha256` would have hashed bytes that exist in no commit — an
unattributable hash is no pre-registration at all. The prereg is methodology
(arms, information set, gate, verdict language) and is appropriate to
publish; strategy content stays in the gitignored program-design spec. A
one-line pointer remains at the old path (gitignored, uncommitted). This
relocation changes no substantive content and lands before the lock and
before any scored-pool issuance.

**2026-08-01 — lock-time panel-generation correlation is `r_dev`, measured
on the V5 dev-slate paired diffs (pre-lock; Codex Plan-2 batch-3 finding
B3-2, BLOCKER).** The "Panel-generation limitation" section above says the
lock estimates "the within-matchday correlation of the realized paired
diffs" — unimplementable at lock time: the scored pools' realized diffs
need outcomes, which the lock (correctly) freezes without. Adopted rule,
matching the ratified `reports/oa_analysis_spec.md` §6: the lock-time
estimate is **`r_dev`** — `power.within_block_correlation` on the V5
dev-slate paired diffs of the same contrast (E′(selected) − incumbent,
blocks = competition × venue-local matchday), the only realized
E′-vs-incumbent contrast that exists pre-lock, and dev data by
construction. The pre-committed threshold is unchanged: `r_dev > 0.05`
(strict) selects block panel generation for the MDE re-statement,
`power.generation_for_correlation`. The realized scored-pool `r` is
reported by V10 as an explicitly **post-hoc sensitivity only** — it never
changes the gate, the verdict, or the locked pre-committed reading.

**2026-08-02 — the confirmatory venue is a RANKED RULE, not a single named
tournament (USER RULING at the pre-lock gate).** Sections above name the
**AFC Asian Cup 2027** as THE confirmatory lockbox. The V0 dev-slate probe
then established that `soccer_afc_asian_cup` is not in The Odds API's
vocabulary at all (HTTP 404, not an empty listing), so the historical
route has never carried that competition and there is no evidence it will
be quotable live. Naming an unverifiable venue in a frozen prereg risks a
programme whose confirmatory test simply cannot be run — and any venue
chosen *after* that failure would be a post-hoc substitution.

Adopted, before the V8 lock and before any scored-pool issuance, the
confirmatory venue is decided by this RULE rather than by a later choice:

1. **Ranked candidate list, in order:** (a) AFC Asian Cup 2027 (first
   matchday 2027-01-07, `config/tournament_ac2027.yaml`); (b) Africa Cup of
   Nations 2027; (c) the 2027 FIFA World Cup qualification windows.
2. **Coverage probe, at T−30 days** before each candidate's first
   matchday, taken in rank order: buy the discovery listing for that
   competition's first TWO matchdays and one T_issue-cut snapshot per
   listed fixture, through the journaled acquisition runner under a
   user-approved cap, exactly as G-A/G-B were.
3. **Pre-committed pass bar:** a candidate is CONFIRMED as the venue iff
   (i) at least 4 fixtures are listed across those two matchdays, AND
   (ii) at least **60%** of listed fixtures carry an admissible sharp
   quote at the cut instant under the unchanged `admissible_quote` rule
   and the market-coherence rule (overround ≥ 1).
4. **First pass wins.** The first candidate that clears the bar IS the
   lockbox; later candidates are never probed, so the choice cannot drift
   toward whichever venue looks better after the fact.
5. **If no candidate clears the bar,** the confirmatory test is reported
   as **UNRUNNABLE — no covered venue**, and the programme's development
   result stands as exploratory only. No substitute venue is invented at
   that point.

The 60% bar is calibrated on evidence the G-B walk already produced, and
was chosen to separate the competitions the archive genuinely carries from
the ones it does not: AFCON 82% (115/140), Copa América 97% (31/32) versus
UEFA Nations League 25% (88/350) and WCQ-CONMEBOL 23% (25/110). It is
fixed here, before any 2027 probe is bought.

This rule is OUTCOME-BLIND in the same sense as the earlier pre-lock
rulings: it asks only whether a sharp book posted a price before kickoff,
which is knowable — and knowable to be knowable — without reference to any
result. It changes no arm, no information set, no gate, and no verdict
language.

---

## Amendment — 2026-08-02 (lock-v6): lock-time blanks filled, STATUS sealed

The six "Lock-time blanks" above were left unchecked through lock-v1..v5,
including at the moment the V10 verdict was taken. That is an omission worth
naming: a preregistration whose blanks are never filled has not, in the end,
registered those choices.

They are now filled, and every value is transcribed from a record that
predates the scored-pool run (per-line citations above). Nothing was chosen
here. The distinction is checkable rather than asserted: locks v1..v5 remain
readable and still contain the empty boxes and the DRAFT status line, so
anyone can diff this version against them and see exactly what changed and
when.

Also recorded at v6, closing the last open Codex finding against the lock
machinery: the posterior cache (`data/cache/oa_dev`, the fitted model states
every forecast is priced from) is now attested by a single digest over its
sorted contents. It is gitignored and covered by no document hash, so before
this the lock spoke for the code and the inputs but not for the model states
that produced the numbers. `verify_chain` does NOT re-check it — the cache
legitimately grows as later work adds fits — so this is attestation, not
enforcement: a posterior swapped after the fact is provable by re-hashing
against the lock that preceded it.

Neither change touches the analysis spec, the gate, the Holm family, or the
verdict. `reports/oa_verdict.md` stands as issued under lock-v5.

---

## Amendment — 2026-08-09 (lock-v7): additive product code in the attested tree

`src/wcmodel/model/markets.py` was added to the codebase. It projects the
scoreline grid the model already produces into the ordinary football markets
— over/under, both-teams-to-score, double chance, clean sheet, correct score
— for the product surface. It fits nothing, learns nothing, and reads no
outcome; every function is a sum over cells of a grid that already exists.

The programme's code tree is `src` and `scripts`, so this file falls inside
what the lock attests to, and `require_lock` correctly refused to run the
verdict under lock-v6 once it was committed. That refusal is the machinery
working: the alternative — filing production code somewhere outside
`CODE_PATHS` to avoid advancing the chain — would make the attested tree mean
"the code that computes forecasts, except the parts we chose not to re-lock",
and the lock would stop meaning anything.

**This amendment changes nothing about the analysis.** Not the gate, not the
sample, not the Holm family, not the statistical plan, not the verdict.
`reports/oa_verdict.md` stands as issued under lock-v5.

The claim of additivity is checkable rather than asserted. The V10 verdict was
re-run against the tree containing this module and returned mean ΔRPS
−0.01018 with bootstrap support 0.995 — identical to the numbers issued under
lock-v5, to every published digit, with only the lock-version footer differing.
An amendment that altered a forecast could not produce that output.

The 1X2 projection in the new module delegates to the production
`grid_one_x_two` rather than re-deriving it, so no second home/away convention
enters the codebase; its output on a shipped fixture bundle is byte-identical
to the 1X2 numbers already published for that fixture.

One constraint is recorded here because it governs how these outputs may be
described in public: **broader market coverage is not higher accuracy.** An
"over 1.5 goals" forecast is correct more often than a 1X2 forecast because
the event is more likely, not because the model improved. Each market carries
its own record and none may be pooled into a single headline hit rate.

---

## Amendment — 2026-08-09 (lock-v8): the delivery half of the same change

`src/wcmodel/dashboard/fixtures.py` and `.../schema.py` now emit and gate the
market projections described at v7. Same feature, same reasoning, same
non-effect on the analysis; only the delivery side.

It is a separate lock version for a process reason worth naming rather than
hiding: v7 was taken as soon as the module existed, before the code that
consumes it was written. Batching every `src`/`scripts` change of one feature
and taking a single version would have left a shorter chain saying the same
thing. The lesson is about sequencing, not about the gate — and the record is
more useful with the misstep in it than with two versions silently merged
into one.

Nothing here reaches the OA forecast path. The verdict stands as issued under
lock-v5; the gate, sample, Holm family and statistical plan are untouched, and
every document digest except this file's is unchanged from v7.

---

## Amendment — 2026-08-11 (lock-v9): the product got a name and a domain

Three commits between lock-v8 and this one changed `src/wcmodel/releases/`:
the model's public name became **Flamsteed** (7d8d383, replacing Antecast),
and the repository moved to `onbiggerthingsB/FLAMSTEED` (60ff444, e1b7489).
This amendment adds one more: `METHODOLOGY_URL` now points at
`https://flamsteed.io/methodology.html` rather than a GitHub README anchor,
because the site went live on 2026-08-11 and is verified serving.

`ARCHIVE_URL` deliberately does **not** move. `reports/` is not published to
the site, and the canonical citable copy of the forecast archive is already
the Zenodo DOI recorded alongside it. A citation URL that points at a page
which does not exist is worse than one that points at GitHub.

**Recorded because it is the more useful part of this entry:** the chain has
been in a refusing state since 7d8d383, and nobody noticed until a verdict
was next attempted, today. Nothing was issued in the interim, so nothing is
retrospectively in doubt — but the gap between "the lock started refusing"
and "we found out" was two days and three commits, and that is a property of
this process worth writing down rather than quietly closing. The refusal
worked exactly as designed; the monitoring around it did not exist. A lock
that is only consulted when someone happens to run the verdict is a lock that
tells you late.

**This amendment changes nothing about the analysis.** Not the gate, not the
sample, not the Holm family, not the sign-flip veto, not the statistical plan,
not the verdict. Every changed line is a string constant consumed by the
publisher; none is read by any code on the forecast path.

As at v7, the claim is checkable rather than asserted. The V10 verdict was
re-run against this tree and returned mean ΔRPS −0.01018 with bootstrap
support 0.995 on the same 217 covered fixtures — identical to the numbers
issued under lock-v5 and re-confirmed under v7 and v8, to every published
digit. `reports/oa_verdict.md` stands as issued under lock-v5.

Unchanged and restated because it governs how the domain may be used: the
site carries no prices, no betting advice, and no market-grade accuracy
claim. A domain is a nicer place to publish a forecast record. It is not
evidence about the forecast.
