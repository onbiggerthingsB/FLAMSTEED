# Locked correction tranche: staged implementation and lock migration plan

**Status:** plan only, written 2026-08-31. No source change, fit, forecast,
score, or betting action is authorised by this document.

**Current immutable baseline:** `reports/oa_lock/lock-v10.json` is schema
`oa-lock-v1`, names code commit
`6670bedc5908c453636d8237ecf3ed52c4fc6ada`, and its existing sidecar says
`40bbf4ab70c3782672aff0e03aed7b8caa7553687d1844b8615a42836786a30a`.
Those two v10 files, and lock v1-v9, must remain byte-for-byte unchanged.

These are correctness repairs with **zero claimed RPS gain**. They are needed
before an economic edge can be measured honestly. Every package below changes
at least one path in `src/` or `scripts/`, so the present v10 lock must go red
after the implementation commit and remain unusable for new issuance until a
new lock is chained to it.

## 1. Global rules for the tranche

1. Write a dated correction amendment before implementation. It must freeze the
   contracts and constants below, declare existing forecasts/caches legacy, and
   say that no correction may be selected by its realised score.
2. Build and audit only with hand-built and already-archived fixtures. Do not run
   a fit, regenerate a posterior, rescore the real corpus, or inspect an outcome
   to choose a correction.
3. A rejected quote, invalid draw, missing archive object, or incompatible old
   artifact is a typed, counted refusal. It may not disappear from a denominator
   or fall back to a uniform probability, raw implied probability, another
   bookmaker, another event, or a smaller scored subset.
4. Version the changed contracts explicitly: `market-quote-v2`,
   `scoreline-law-v2`, `totals-quote-v2`, and `oa-lock-v2`. A consumer must refuse
   an unknown version.
5. Preserve old artifacts under their old version. Never rewrite an old cache,
   ledger row, report, lock JSON, or sidecar to make it look compatible.
6. Keep model-price and market-price provenance separate. A posterior hash does
   not prove an odds quote, and a raw odds hash does not prove a model fit.

## 2. Delivery sequence and stop points

| Stage | Deliverable | Mandatory stop condition |
|---:|---|---|
| 0 | Freeze the amendment and red tests | No production code until the amendment fixes schemas, tolerances, exclusions, and migration treatment |
| 1 | Make the lock verifier schema-aware and self-verifying | No other locked correction may merge until legacy v1-v10 still verify and a missing sidecar fails |
| 2 | Introduce one strict event/quote selection boundary | No entry/close or live selector may retain its own snapshot-selection loop |
| 3 | Centralise finite-market and de-vig validation | No consumer may call the numerical de-vig functions on an unvalidated market |
| 4 | Replace clip-and-condition scoreline arithmetic with one coherent law | No old posterior may be issued through the new law; no real fit is run in this tranche |
| 5 | Migrate totals and sharp-reference provenance | No object lacking a raw hash, event identity, quote clock, named book, line and side may be called an entry or close |
| 6 | Integration/audit | Any unclassified exception, silent row loss, legacy fallback, or direct duplicate arithmetic blocks the lock |
| 7 | Commit code, then take the next chained lock | New issuance remains stopped until the new head verifies against the implementation commit |

Stages 2 and 3 may be developed together after Stage 1. Stage 5 depends on both
of them. Stage 4 may be developed in parallel, but its integration gate precedes
Stage 7.

## 3. Stage 0 — pre-code amendment and fixtures

Create `reports/oa_correction_amendment_v11.md` before any implementation. The
amendment must incorporate this plan by hash and freeze:

- the exact identity tuple and quote-clock ordering in §5;
- the admissible raw-market and de-vig contracts in §6;
- `scoreline-law-v2`, including `TAU_MIN = 1e-12`,
  `TAIL_MASS_TOL = 1e-8`, and `HARD_MAX_GOALS = 40`, in §7;
- the totals and sharp-reference definitions in §8;
- the fact that v11 is a **harness/correction lock on operational hold**, not an
  adoption verdict and not authority to reuse a v10 posterior;
- the rule that changing either numerical constant or any exclusion after the
  amendment requires another lock version.

Build a small committed, outcome-free poison corpus for tests: two different
events on the same day with the same team names; same event id with a changed
kickoff/team; equal-price entry and close; future `last_update`; a later envelope
containing an older quote; NaN/infinite/Boolean odds; an underround; a partial
totals line; mixed-book totals sides; invalid Dixon-Coles tau draws; and high-rate
draws whose 0-10 tail is material. The corpus contains no real results.

## 4. Stage 1 — lock sidecar and inventory verification

### Files that must change

- `src/wcmodel/eval/lock.py`
- `scripts/oa_lock.py`
- `scripts/oa_acquire.py` (journal receipt schema and shared archive checks)
- tests: `tests/eval/test_lock.py` and the archive/receipt cases in
  `tests/eval/test_acquire.py`

`scripts/oa_scored_inventory.py` and `scripts/oa_eval_manifest.py` need changes
only if their emitted schemas cannot supply the v2 verifier's exact fixture and
kickoff identity. They must not be rewritten merely to change formatting.

### Required implementation contract

1. Replace the single `LOCK_SCHEMA`/`LOCKED_DOCUMENTS` assumption with an
   immutable schema registry. `oa-lock-v1` retains exactly its current eight
   document keys and canonical digest algorithm. `oa-lock-v2` adds exactly
   `correction_plan` (`reports/epl_locked_corrections_plan.md`) and
   `correction_amendment` (`reports/oa_correction_amendment_v11.md`). A bundle is
   verified under its own schema; v1 digests must not be reserialised or
   reinterpreted as v2. Permit v1 -> v2, prohibit a later downgrade.
2. Require one and only one `lock-vN.sha256` for every `lock-vN.json`. The
   sidecar must be exactly 64 lower-case hexadecimal characters plus one final
   newline, and must equal the canonical JSON digest. Missing, malformed,
   duplicate-version, and orphan sidecars fail. This stronger structural check
   can apply to v1-v10 because all current versions already have sidecars.
3. Verify every v2 claim, not merely document hashes. Evidence entries become
   typed `{path, sha256, role}` records. A claimed file must exist and hash
   exactly. Do not carry forward the current whole-cache attestation with the
   note that it is not rechecked. For v11, record an empty compatible-posterior
   manifest plus `operational_hold: true`; later model artifacts must be an
   exact per-file manifest in a later lock.
4. Re-derive the head's `scored_inventory` from the locked eval manifest and
   locked acquisition-journal bytes, canonicalise row order, and compare the
   full rows and counts—not just `n_fixtures`/`n_eligible`. Group receipts by
   `call_id` and fixture. Identical replayed terminal receipts may collapse;
   conflicting terminal receipts, a success followed by an error, two digests,
   an unknown fixture, a duplicate manifest fixture, or last-write-wins logic
   fail.
5. For every eligible `cut_raw_sha256`, require 64 lower-case hex, require
   `data/odds_raw/<sha256>.json`, re-hash its bytes, parse it, and check the raw
   event against manifest home, away and exact UTC kickoff plus the receipt's
   requested sport/event identity. Re-run the strict timestamp, named-book,
   complete-outcome and coherent-book gates. An archived error body remains
   evidence but can never make a fixture eligible.
6. Store in v2 the journal hash, manifest hash, inventory-derivation version,
   archive-root policy, and the sorted eligible raw-object manifest. Verification
   re-derives all of them. Historical v1-v10 bundles remain valid historical
   attestations; the v2 verifier must not pretend their previously untyped cache
   strings have become re-verifiable evidence.
7. Write JSON and sidecar through same-directory temporary files, `fsync` both,
   then rename with the JSON as the final commit marker and `fsync` the lock
   directory. A crash may leave only named temporary files, never a valid-looking
   head. `--take` may resume only an incomplete byte-identical candidate; it must
   never overwrite a complete version.

### Adversarial tests

- Delete a sidecar; add an orphan sidecar; use upper-case, whitespace, two lines,
  63/65 characters, or the correct digest of non-canonical JSON: all fail.
- Tamper with a historical JSON or sidecar and ensure the chain fails before
  head-document checks.
- Verify the real v1-v10 fixture chain in a copied directory under the new code
  and assert every original JSON/sidecar hash is unchanged.
- Mutate an evidence file, journal line, manifest row or raw blob; delete the raw
  blob; point a receipt at an HTTP error body; inject a conflicting duplicate
  receipt; make inventory counts agree while rows differ: all fail.
- Crash after each temporary write, each `fsync`, and each rename. No state may
  verify as a complete new lock, and a retry must be deterministic.
- Give v11 a v1 document set, downgrade v12 to v1, change the declared code
  commit, or leave the code commit unresolved: all fail.

### Compatibility and migration risk

The main risk is retroactively applying v2 document or evidence requirements to
v1-v10 and thereby making an honest historical chain unverifiable. Schema-local
verification prevents that. The second risk is mutable gitignored evidence:
whole-directory cache hashes cannot be promises that verification declines to
check. v2 must enumerate immutable objects or make no claim. During the bridge
between the implementation commit and v11, `require_lock()` must fail by design;
all issuance/scoring entry points stay disabled.

## 5. Stage 2 — strict entry/close identity and `last_update`

### Files that must change

- `src/wcmodel/data/sources/odds.py`
- `src/wcmodel/backtest/odds_ingest.py`
- `src/wcmodel/backtest/walkforward.py`
- `src/wcmodel/live/decide.py`
- `src/wcmodel/live/validation.py`
- `src/wcmodel/live/odds_live.py`
- `scripts/clv_validation.py`
- `scripts/oa_acquire.py`
- focused tests in `tests/data/test_odds_historical.py`,
  `tests/backtest/test_odds_ingest.py`, `tests/backtest/test_walkforward.py`,
  `tests/live/test_decide.py`, and `tests/live/test_validation.py`

### Required implementation contract

Introduce one public immutable `market-quote-v2` object and one selector in
`data.sources.odds`. The source event identity is the exact tuple:

`(event_id, sport_key, home_team, away_team, commence_time_utc)`.

No canonical-name or date-only key is allowed inside quote selection. The legacy
`event_key(home, away, UTC date)` may remain solely as an explicitly named
results-join key; it is not quote provenance.

Each quote must carry: schema, source/provider, raw SHA-256, event identity,
bookmaker, market key, line (null for h2h), exact outcome set, prices,
`snapshot_ts`, `bookmaker_last_update`, `market_last_update`,
`strictest_last_update`, and `last_update_source`. All timestamps are parsed as
timezone-aware UTC instants.

Selection is always `select_quote_asof(sample, expected_identity, bookmaker,
market, cut)`. It must:

1. refuse a multi-event snapshot or any sample spanning identities;
2. require the exact market outcomes (`home/draw/away` after event-aware mapping
   for h2h; paired Over/Under for one totals line);
3. set `strictest_last_update` to the later of the book and market stamps, using
   the envelope timestamp only when both are absent and recording that fallback;
4. require `snapshot_ts < cut`, `strictest_last_update < cut`, and
   `strictest_last_update <= snapshot_ts`; equality at the decision/kickoff cut
   is inadmissible;
5. choose the greatest admissible `strictest_last_update`, then greatest
   `snapshot_ts`, then raw digest as a deterministic tie-break. A later envelope
   cannot displace a fresher earlier quote merely by carrying stale prices;
6. require an explicit `entry_cut` and `close_cut` (`close_cut` is kickoff). Do
   not infer a decision price as the earliest pre-kickoff snapshot;
7. require entry and close to share the full event, bookmaker, market, line and
   outcome identity, with `entry.strictest_last_update <=
   close.strictest_last_update`.

A bet may use a valid entry even when no independent close exists. If both cuts
select the same quote identity, record `clv_unavailable="same_quote"`; do not
manufacture zero CLV. A paired CLV observation requires distinct raw/snapshot
quote identities. Live code must call the same selector; remove its private
`_decision_time_entry`, `_event_meta`, `_snapshot_has_book`, and mirrored canary
selection arithmetic. The canary should independently validate the returned
quote envelope, not reimplement selection.

### Adversarial tests

- Two events with the same teams/date, two event ids, or a changed exact kickoff
  cannot pair; neither can swapped teams or sport keys.
- A snapshot containing two events and a sequence of one-event snapshots from
  different fixtures both fail.
- Book stamp clean/market stamp late, market clean/book late, missing one stamp,
  missing both, stamp equal to cut, stamp after envelope, naive timestamp, and
  later-envelope/older-update cases pin the clock law.
- A close missing the entry bookmaker, a same-snapshot pair, an entry after the
  decision cut, and a quote at kickoff are counted refusals with exact reasons.
- Equal prices at two timestamps remain distinct quotes; the canary catches a
  close timestamp logged as entry even though values match.
- List-shaped and bare-event payloads produce identical quote objects, including
  raw hash and all stamps.

### Compatibility and migration risk

The signature change is intentionally breaking: callers that lack an explicit
entry cut or expected event identity must stop. Existing ledgers containing only
`entry_ts`, `close_ts` and prices cannot be backfilled with event ids or provider
stamps; mark them `market-quote-v1/legacy_unverifiable`. Date-only result joins
may still map results to an already-verified quote, but cannot establish quote
identity. Coverage and CLV denominators will probably shrink; publish reason
counts rather than comparing new and old means as though only the model changed.

## 6. Stage 3 — finite raw-market and de-vig gates

### Files that must change

- `src/wcmodel/data/devig.py`
- `src/wcmodel/eval/implied.py`
- `src/wcmodel/eval/oof.py`
- `src/wcmodel/backtest/devig_select.py`
- `src/wcmodel/backtest/baselines.py`
- `src/wcmodel/backtest/odds_ingest.py`
- `src/wcmodel/value/scanner.py`
- `src/wcmodel/markets/totals_edge.py`
- `scripts/oa_acquire.py`, `scripts/oa_dev_oof.py`,
  `scripts/clv_validation.py`, `scripts/ev_scan_poc.py`, and the three totals
  scripts named in §8
- tests in `tests/data/test_devig.py`, `tests/backtest/test_baselines.py`,
  `tests/backtest/test_odds_ingest.py`, `tests/markets/test_totals_edge.py`, and
  OA implied/OOF tests

### Required implementation contract

Put one validation boundary in `data.devig`; numerical methods must call it
themselves, not trust callers. For a named-book market:

- the outcome set and length must be exact for its surface;
- each value must be a real numeric scalar but not `bool`, finite, and strictly
  greater than 1.0;
- inverse prices and their sum must be finite;
- a single-book benchmark must have overround at least `1 - 1e-6`;
- a cross-book best-price vector is an executable-price collection, not a book
  and not eligible for de-vigging.

Every method (`multiplicative`, `power`, `shin`) must return the exact expected
shape, finite probabilities in `(0,1)`, and sum to one within `1e-12`. Solver
non-convergence, a missing sign change where the method requires one, an invalid
root, or invalid output is a typed `DevigError`; there is no lower-bound pin,
best-effort normalisation, or raw-inverse fallback. A truly fair book may use the
method's explicitly tested zero-vig limit. An underround may be retained as a
separately labelled executable arbitrage observation, but not converted into a
fair benchmark distribution.

The quote gate and de-vig gate return stable reason codes such as
`nonfinite_price`, `invalid_decimal`, `incomplete_market`, `underround_book`, and
`devig_failure`. Walk-forward, OOF, live, totals and acquisition ledgers retain
one row per requested fixture and count these reasons.

### Adversarial tests

- `nan`, `+/-inf`, `True/False`, numeric strings, `None`, zero, negative, 1.0,
  subnormal and extremely large odds all have pinned outcomes.
- Missing, duplicate, extra and permuted outcome names cannot silently change
  the home/draw/away or Over/Under order.
- Underround at and beyond the `1e-6` tolerance, exact fair books, ordinary
  overrounds, and cross-book composites exercise separate policies.
- Monkeypatch each numerical method to produce NaN, negative mass, wrong shape,
  non-unit sum, solver failure and an invalid root; every consumer fails closed
  with the same reason.
- A malformed quote must never reach edge, stake, RPS, implied-rate inversion or
  eligibility code. A static/call-spy test pins this ordering.

### Compatibility and migration risk

`eval.implied.book_overround` and `is_coherent_book` currently duplicate only a
subset of the needed checks; consolidate rather than maintain two policies.
Generic de-vig currently accepts values that can yield NaN, and Shin currently
normalises some no-root cases. Tightening this changes coverage and can change
the previously selected de-vig method. Therefore v10 selection traces and fair
market probabilities remain historical and cannot be silently reselected under
v2. No RPS comparison is run in this correction tranche.

## 7. Stage 4 — coherent truncation and Dixon-Coles tau law

### Files that must change

- `src/wcmodel/model/likelihoods.py`
- `src/wcmodel/model/draw_api.py`
- `src/wcmodel/model/posterior.py`
- `src/wcmodel/eval/implied.py`
- `src/wcmodel/eval/blend.py`
- `src/wcmodel/markets/derived.py`
- `src/wcmodel/releases/pricing.py`
- `src/wcmodel/dashboard/fixtures.py`
- every direct caller found by the integration inventory, currently including
  `src/wcmodel/backtest/totals_backtest.py`,
  `scripts/diagnose_totals_calibration.py`, `scripts/run_totals_backtest.py`,
  `scripts/scan_totals_forward.py`, and `scripts/sharp_totals_check.py`
- tests in `tests/model/test_draw_api.py`, likelihood/posterior tests,
  `tests/eval/test_implied.py`, `tests/eval/test_blend.py`,
  `tests/markets/test_derived.py`, and release/dashboard parity tests

### Required implementation contract

The present path applies a soft floor to tau in the fitting likelihood, clips
negative tau cells at prediction, and renormalises each fixed 0-10 grid. Those
are three different laws. `scoreline-law-v2` must use one law in fit, prediction,
blending, implied inversion, totals and release pricing.

For each Dixon-Coles rate pair `(lambda_home, lambda_away)` require all four
factors to be at least the frozen `TAU_MIN = 1e-12`:

- `1 - lambda_home * lambda_away * rho > 0` for 0-0;
- `1 + lambda_home * rho > 0` for 0-1;
- `1 + lambda_away * rho > 0` for 1-0;
- `1 - rho > 0` for 1-1.

Writing `t = TAU_MIN`, rho must lie in the rate-dependent closed intersection
`max((t-1)/lambda_home, (t-1)/lambda_away) <= rho <=
min(1-t, (1-t)/(lambda_home*lambda_away))`. The fitting graph must make states
outside this support impossible for every training fixture; prediction must
reject an invalid posterior draw. Delete `_TAU_FLOOR` semantics and prediction
clipping.
Do not discard invalid draws or renormalise after clipping. The four canonical
corrections are mass-neutral on the infinite independent-Poisson law when they
are non-negative; documentation must stop calling that valid construction a
non-normalising quasi-pmf.

Replace `PRODUCTION_MAX_GOALS = 10` as a silent conditioning rule with an
immutable `ScorelineLaw` carrying `grid`, `support_max`, `retained_mass`,
`omitted_mass`, likelihood and law version. Select the smallest common square
support whose posterior-mixture omitted mass is at most `1e-8`, up to a hard
ceiling of 40 goals per side. For Dixon-Coles with support at least 1, use the
Poisson marginal CDFs to compute the exact retained mass (the four corrections
cancel); for bivariate Poisson use its proper joint law. Normalising the retained
grid is allowed only after the omitted mass is computed and below tolerance,
and that approximation/error must ride with the object. If the hard ceiling
cannot meet tolerance, raise a typed `ExcludedMassTooLarge`; never return a
conditional 0-40 forecast as though it were unconditional.

Add `Posterior.predictive_law(...)` as the production API. A temporary
`predict_scoreline(...)` ndarray adapter may remain for compatibility only after
the law has passed the tail gate; all issuance, market and evaluation consumers
must migrate to the law object before v11. `grid_one_x_two`, totals, correct
score, simulation, blending and implied-rate inversion must consume the same law
and may not normalise independently.

### Adversarial tests

- Check all four tau orientations against hand calculations and exact
  mass-neutral cancellation. A single non-positive tau in fit or prediction
  fails; no cell is clipped and no draw is dropped.
- Pin fit/predict tau parity: the same rate/rho tuple is accepted or rejected on
  both NumPy and PyTensor paths at the boundary and one ULP to either side.
- Low-rate fixtures stay on a small support; high-rate fixtures expand beyond
  10; a deliberately extreme fixture reaches 40 and refuses. The reported
  omitted mass agrees with an independent high-support calculation.
- Increasing support after the tolerance is met changes each 1X2/totals price by
  no more than the declared tail-error bound. Home/draw/away sum to one; Over and
  Under for every supported line sum to one; nested totals remain monotone.
- Production, posterior adapter, blend endpoints, implied inversion,
  dashboard/release prices and totals derive from the identical law. A
  call-site test rejects a second `grid / grid.sum()`, `np.clip` tau guard or
  hard-coded 10 in a production consumer.
- Include the known high-tail top-attack/cold-start shape as a synthetic canary:
  it must expand or give an explicit mass refusal, never silently disappear.

### Compatibility and migration risk

This is the highest-risk correction. It changes both fitted support and
prediction semantics. All v10 posterior caches, implied-rate caches, blend
weights, golden grids, calibration parameters and downstream forecast artifacts
are incompatible with `scoreline-law-v2`, even if a particular fixture happens
to produce close numbers. Key every cache by law version and refuse old keys.
No fit is run here. After v11 freezes the corrected harness, a separately
authorised, preregistered fit/evaluation is required; only a subsequent artifact
lock may authorise issuance from a new posterior.

## 8. Stage 5 — totals and sharp-close provenance

### Files that must change

- `src/wcmodel/data/sources/odds.py`
- `src/wcmodel/markets/totals_edge.py`
- `src/wcmodel/backtest/totals_backtest.py`
- `scripts/run_totals_backtest.py`
- `scripts/scan_totals_forward.py`
- `scripts/sharp_totals_check.py`
- `scripts/diagnose_totals_calibration.py`
- `src/wcmodel/dashboard/provenance.py` and release/dashboard serializers that
  publish totals or a market comparison
- tests in `tests/data/test_odds_totals.py`,
  `tests/markets/test_totals_edge.py`, `tests/backtest/test_totals_leakage.py`,
  and new script-level cache/provenance tests

### Required implementation contract

`parse_totals_snapshot` must accept the full archived envelope, not a detached
event, and emit `totals-quote-v2` objects. Every line/side retains raw SHA-256,
provider, event identity, request/response/snapshot clocks, book and market
`last_update`, strictest update, bookmaker, market key, numeric line, side and
price. Complete pairs are formed only from the same event, book, market, line,
snapshot and raw object.

The historical totals cache currently stores derived price maps without those
facts. Replace it with a versioned manifest referencing content-addressed raw
responses; derived records must be reproducible from the raw bytes. Old cache
rows become `totals-quote-v1/legacy_unverifiable`; do not infer hashes or clocks
from filenames or modification times.

Keep three concepts distinct:

1. **Executable entry:** the selected side's best admissible price may come from
   any configured soft book, but its actual book and quote identity ride with
   the bet.
2. **Same-venue close:** CLV by raw odds ratio uses the same bookmaker, event,
   market, line and side as entry. A close at a different book is missing
   same-venue CLV, not a substitute.
3. **Sharp close:** economic CLV is
   `entry_decimal_odds * devigged_named_sharp_close_probability(side) - 1`.
   Its Over and Under must be the paired named sharp book (currently Pinnacle)
   at the same event/line and one admissible, strictly pre-kickoff close quote.
   A consensus or cross-book best pair is never labelled sharp.

`sharp_totals_check.py` currently consumes one live pull. A current Pinnacle
quote may be labelled `sharp_current`; it cannot be labelled `sharp_close`
unless the archived pre-kickoff close contract is satisfied. If Pinnacle is
absent, report `sharp_close_missing`; do not promote all-book median consensus
to sharp. `run_totals_backtest.py` must not select entry from one soft book and
close from another while reporting one CLV. `scan_totals_forward.py` may select
best executable side prices across books, but may not de-vig the resulting
cross-book composite.

Every paper-ledger row must additionally carry quote-schema version, event id,
sport/provider, raw digest, snapshot and strictest-update clocks, market/line,
entry book, decision cut, scoreline-law version, posterior object manifest/hash,
and the later close status. Append-only identity is a hash of those fields, not
`fixture|date` alone.

### Adversarial tests

- Pair Over from one book with Under from another; pair two lines, two snapshots,
  two events or two raw hashes; all benchmark de-vigs fail.
- Entry at book A and close at book B yields `same_venue_clv_missing`; it cannot
  enter the same-venue CLV mean. A valid named-book sharp close remains a
  separate economic-CLV observation.
- A Pinnacle quote at/after kickoff by either snapshot or strictest update, a
  stale later envelope, missing raw bytes, raw-hash tampering, a one-sided line,
  and non-finite prices all fail with stable reason codes.
- A live/current quote is never serialised with `sharp_close=true`; a consensus
  row cannot acquire bookmaker `pinnacle` or role `sharp` through fallback.
- Integer lines preserve push/void rather than treating equality as a loss;
  half-lines have no push. Settlement and CLV denominators are pinned separately.
- Reparse every v2 cache row from its raw object and compare byte-stable canonical
  output. A derived-only v1 row is refused, not auto-upgraded.

### Compatibility and migration risk

Historical totals CLV and any “sharp” conclusion based on derived-only cache
rows lose verified status. Preserve and label them; do not delete them. The new
denominators will be smaller, and same-venue CLV, sharp economic CLV and realised
ROI will have different coverage. Publish all three counts. Changing the
scoreline law simultaneously means a before/after totals score is not an
isolated provenance comparison; only a new preregistered forward evaluation can
support an edge claim.

## 9. Stage 6 — integration and audit gate

Before a lock is taken:

1. Run the focused suites above, then the complete test suite, with network
   disabled and no fit backend invoked. Assert zero paid calls and zero writes to
   live journals, posterior caches or paper ledgers.
2. Inventory every call site of `parse_snapshot`, `parse_totals_snapshot`,
   `entry_close_prices`, `book_aware_close`, all de-vig methods,
   `predict_scoreline`, `mean_grid_over_draws`, and direct scoreline
   normalisation. Each must use the v2 boundary or be an explicitly quarantined
   legacy reader.
3. Mutation-test the critical comparisons: change each strict `<` to `<=`,
   remove one identity field, bypass finite validation, remove a sidecar check,
   clip one tau, or force support 10. At least one named adversarial test must
   fail for every mutation.
4. Produce a migration report containing counts only: legacy quote/cache rows,
   v2-parseable rows, each exclusion reason, compatible posterior count (expected
   zero for scoreline-law-v2), and old/new lock-file hashes. Do not calculate RPS,
   ROI, CLV or an adoption verdict.
5. Review the diff specifically for exception swallowing. Broad `except` blocks
   may translate a typed refusal into a ledger reason, but may not return a
   price, an empty success, or skip a fixture.

## 10. Stage 7 — issue the next lock without rewriting v10

Use this exact two-commit bridge:

1. Before implementation, record the hashes of every existing
   `reports/oa_lock/lock-v*.json` and `.sha256`. In particular pin the v10
   sidecar value printed at the top of this plan.
2. Commit the dated amendment, implementation, tests and migration report as one
   reviewed correction commit `C_fix`. Do not include a new lock file in this
   commit. The tracked tree must then be clean. From `C_fix` until step 5,
   `require_lock()` failing against v10 is the expected safety state; do not
   bypass it.
3. With the new verifier, verify copied v1-v10 bundles under `oa-lock-v1`, all
   mandatory sidecars, the chain links, and unchanged bytes. This is historical
   verification only; it does not authorise `C_fix` under v10.
4. Run `scripts/oa_lock.py --take --schema oa-lock-v2` from clean `C_fix`.
   The tool must compute `prior_lock_sha256` from the actual canonical v10 JSON
   (`40bbf4…a30a`), set `version: 11`, set `code_commit: C_fix`, bind the v2
   document/evidence/inventory manifests, and set
   `operational_hold: no_scoreline_law_v2_posterior`.
5. Commit only the newly created v11 JSON and sidecar as `C_lock`. Because this
   commit adds report artifacts rather than changing `src/`/`scripts/`, the code
   tree at `C_lock` must equal `C_fix`. Run both full-chain verification and
   `require_lock()`; both must pass for v11 while every recorded v1-v10 file hash
   remains unchanged.
6. Tag/report the state as **corrected harness frozen; fitting and issuance on
   hold**. Do not restate any v10 result as having been produced under v11.
7. A later, separately preregistered fit/evaluation runs under the frozen v11
   harness. If it produces an acceptable compatible posterior, enumerate and
   hash that artifact in a new v12 adoption/issuance lock chained to v11. If the
   evaluation fails or refuses, publish that outcome; v11 remains the historical
   correction lock. Any post-v11 code fix is likewise v12 or later—never an edit
   to v11.

## 11. Definition of done

This correction tranche is complete only when:

- all v1-v10 JSON and sidecar bytes are unchanged and the new verifier accepts
  their historical chain;
- v11 is a valid `oa-lock-v2` child of the actual v10 digest;
- every entry, close, totals pair and sharp reference is attributable to exact
  raw bytes, event, book, market, line and clocks;
- malformed markets cannot reach de-vig, scoring, edge or staking code;
- fit and prediction express the same non-negative Dixon-Coles law, and every
  published scoreline price carries an explicit bounded tail error;
- legacy artifacts are labelled and refused where semantics are missing rather
  than backfilled;
- no fit, RPS, ROI, CLV verdict, live order, or claimed accuracy improvement was
  produced during the correction tranche.
