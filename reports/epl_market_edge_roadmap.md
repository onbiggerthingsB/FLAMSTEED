# EPL market-edge build roadmap

**Status date:** 2026-08-31  
**Decision:** research and paper evaluation only; no live-money use is authorised
by this roadmap.  
**Starting point:** the six-season `dc_native` walk-forward loses to de-vigged
Pinnacle close by `+0.0065246909` RPS. The first objective is therefore to make
the evidence path trustworthy, not to increase the number of model variants.

This document is a delivery roadmap. It is not an experiment preregistration.
Each experiment named below requires its own estimand and adoption rule to be
written before its harness exists.

## 1. Non-negotiable lifecycle

For every accuracy or betting experiment:

1. preregister the population, estimand, decision rule, uncertainty method,
   exclusions, failure treatment, and adoption bar;
2. build without running a fit on the real scoring corpus;
3. adversarially audit with synthetic fixtures and deliberately corrupt data;
4. hash-freeze the harness, configuration, input manifests, and code identity;
5. run once on the real corpus or fixed prospective horizon;
6. publish pass, fail, refusal, and missingness either way.

No row may disappear because a forecast or quote failed. A refusal is an
outcome in the ledger, not permission to score an easier subset.

## 2. Delivery order

| Order | Work package | Why now | Direct expected RPS | Lock effect | Completion gate |
|---:|---|---|---:|---|---|
| 0 | Preserve the current audit baseline | Prevent accidental rewriting of the valid 2,280-fixture result | `0` | none | Existing reports/data remain byte-untouched; working-tree provenance reported |
| 1 | Repair EPL odds capture and provenance | There is currently no usable EPL executable-price history | `0` | outside `src/` and `scripts/` | Correct path; zero-EPL refusal; every observation ledgered; append-safe unique files; file/ledger hashes reconcile; cadence status is honest |
| 2 | Repair point-in-time EPL result and identity gates | Backdated results and unresolved teams invalidate replay claims | `0` | outside lock | Supplied observation times survive projection; historical fallback is explicit; null keys refuse; invalid books cannot masquerade as closing prices |
| 3 | Harden EPL walk-forward run identity | A future result must not mix runs or score a subset | `0` | outside lock | Immutable run envelope; resume mismatch/duplicates refuse; stops or missing rows block a verdict; eligible schedule equality required |
| 4 | Forward betting-evaluation plane | Determines whether any forecast can beat a price after margin | `0` | EPL implementation outside lock | Preregistration precedes code; named executable entry; strict sharp close; economic CLV and flat ROI; all non-bets/failures retained; adversarial tests green; harness frozen before collection |
| 5 | Shots/SOT challenger | Largest credible on-disk accuracy improvement | modal `-0.0013`, range `[-0.0025,+0.0002]` | EPL prototype outside lock; canonical adoption may touch lock | Separate preregistration precedes code; raw contradictions quarantined; strict lag; one fixed arm; paired week-block decision and no-harm gates |
| 6 | Dynamic state-space challenger | Largest credible goals-model architecture improvement | modal `-0.0008`, range `[-0.0013,+0.0002]` | canonical implementation touches locked `src/` | One literature-led specification, no scoring-corpus sweep, identical-fixture comparison |
| 7 | Lower-division promotion bridge | Targets the subgroup where DC's Elo advantage concentrates | whole-corpus modal `-0.00012`; potentially larger promoted effect | EPL prototype outside lock | Replace the known-underpowered 85-row decision with an earlier-cohort bridge and a promoted-population estimand; whole-corpus no-harm gate |
| 8 | Point-in-time squad-value prior | Addresses summer/promoted cold starts before EPL goals exist | modal `-0.0004`, range `[-0.0009,+0.0002]` | canonical source touches lock | Licensed bitemporal snapshots, first-seen values, revision audit, coverage gate |
| 9 | Actual lineup/player model | Potentially useful only if information and quote clocks prove a lag | modal `-0.0002`, range `[-0.0010,+0.0002]` | full model likely touches lock | Fixed issuance horizon; point-in-time player evidence; market-only control; prospective economic-CLV gate |

Packages 6-9 do not begin merely because packages 1-5 compile. They begin only
after the preceding experiment's published result changes the expected value of
the next decision, or the owner explicitly funds an independent research arm.

## 3. Locked correction tranche

The following defects are corrections, not model experiments, but the files are
inside the v10 `src/`/`scripts/` lock:

- make entry and close distinct snapshots of the same event and reject a quote
  whose provider update time is not strictly pre-kickoff;
- reject NaN, infinity, invalid decimal odds, and underround books in shared
  non-bet/de-vig code;
- define one coherent scoreline law for training and prediction, expose excluded
  mass, and make the configured goal ceiling real rather than decorative;
- require every lock sidecar, re-hash every claimed input, validate hash syntax
  and timing/book coherence, and make lock JSON plus sidecar atomic;
- retain timestamps, provider identity, last-update time, and supplying book in
  totals and sharp-close caches; forbid composite fallback in a named-book test.

These changes must not rewrite v10. The sequence is: document exact corrections
and compatibility impact; write adversarial tests; implement; audit the diff;
create a new chained lock version; verify both the old chain and new head; then
allow a new evaluation to cite the new lock.

## 4. Deliberately closed or demoted work

Do not rerun these merely because implementation is cheap:

- 270/180/120-day shorter decay: observed effects were `+0.000022`,
  `+0.000565`, and `+0.001774` respectively;
- simple congestion/rest: observed `+0.000102`;
- isolated fast home-advantage drift: neutral to worse in the prior arm;
- the same 85-fixture widening decision: unresolved and underpowered under its
  preregistered primary block structure;
- market-prior/output blending as an independent edge claim;
- tau/bivariate-Poisson shopping: expected 1X2 effect is approximately zero;
- truncation as an accuracy feature: repair it for correctness, especially for
  totals and exact score, but expected pooled 1X2 gain is below `0.00005`.

The only decay follow-up with a coherent prior is a single longer-memory arm
(540/730/no-decay), and even its modal gain is only about `0.00010`. It remains
below the five packages above unless later evidence changes that ordering.

## 5. Evidence-plane decision rule

The forward betting plane's primary phase-one endpoint is economic closing-line
value for the selected outcome:

`C = executable_entry_odds * devigged_sharp_close_probability - 1`.

The initial continuation bar is at least 500 selected bets, mean `C >= +1%`,
and a two-sided 95% calendar-week-block lower confidence bound above zero. A
pass authorises continued paper or explicitly capped tiny-stake validation; it
does not establish profitable live betting. Flat-stake realised ROI is always
published but cannot decide the phase-one gate because it is severely
underpowered at plausible edges.

## 6. Current definition of done

This build tranche is done only when:

- packages 1-3 have focused adversarial tests and no current artifact was
  silently rebuilt;
- the betting and shots preregistrations are committed before their harnesses;
- package 4 is built and audited but has not manufactured historical timing;
- package 5 is built and audited without running a real-corpus fit before its
  freeze;
- locked corrections have an approved, file-specific migration plan rather
  than an unreviewed diff;
- the final report separates planned, built, tested, frozen, run, and adopted
  states.
