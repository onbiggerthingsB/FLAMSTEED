# EPL shots/SOT challenger — prospective preregistration

**Written:** 2026-08-31  
**Status:** preregistered design only; no challenger code, fit, prediction, or result exists  
**Challenger name:** `dc_1x2_shots`  
**Decision corpus:** 2,280 EPL fixtures, 2019/20 through 2024/25

This document freezes one experiment before its implementation. The challenger
uses only the source columns `HS`, `AS`, `HST`, and `AST`: home and away total
shots and home and away shots on target. They are post-match event counts, not
shot-quality values. No shot locations, event-level records, odds, lineups, or
availability information enter the challenger.

The question is narrow: does a point-in-time shot-volume and shot-on-target
overlay improve the native Dixon–Coles 1X2 forecast enough to close a material
part of its gap to the market on exactly the existing scoring fixtures? This is
a shadow experiment. It cannot alter a published forecast or production model.

## 1. Frozen data and partitions

### 1.1 Decision corpus and comparators

| Item | Frozen value |
|---|---|
| Scoring corpus | `data/epl/fit/walkforward_predictions.parquet` |
| Corpus SHA-256 | `f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a` |
| Rows | 2,280; exactly 380 in each of 2019/20–2024/25 |
| Native comparator | stored `dc_home`, `dc_draw`, `dc_away` (`dc_native`) |
| Market comparator | stored `market_home`, `market_draw`, `market_away`; proportional de-vig of the corpus's closing-price benchmark |
| Outcome | stored `y`, ordered home/draw/away |
| Primary dependence block | the corpus's `(season, ISO week)` block; 212 blocks |
| Tidy match archive | `data/epl/matches.parquet`, SHA-256 `323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf` |

The decision population is the corpus's exact ordered `match_id` sequence. A
shot-data problem may remove a historical row from the feature state, but may
never delete, substitute, or reorder a scoring fixture. The run refuses unless
all 2,280 candidate, native, market, and outcome rows join one-to-one.

### 1.2 Raw shot inputs

The raw sidecar reader allowlists exactly `Date`, `HomeTeam`, `AwayTeam`, `HS`,
`AS`, `HST`, and `AST`. The first three are ordering/grouping/join keys, not
numeric predictors. The only raw measures are the four columns below, with
their source meanings preserved exactly. Outcomes come from the frozen
training/decision match records, not from additional raw columns.

| Column | Meaning | Permitted transformation |
|---|---|---|
| `HS` | home total shots | history weighting, averaging, and attack/defence ratios in §3 |
| `AS` | away total shots | same |
| `HST` | home shots on target | same |
| `AST` | away shots on target | same |

The input panel is the 4,180 nonblank match rows in `E0_1415.csv` through
`E0_2425.csv`. `E0_1415.csv` is burn-in; 2015/16–2018/19 is the coefficient
training partition; 2019/20–2024/25 is the untouched decision partition.
`E0_2526.csv` and every later file are excluded from design, fitting, scoring,
diagnostics, and second looks.

Pinned source digests:

```text
76b7858051ff6b17f46f49f26fdc70c1f29537270492606f5cc63d67fad5d149  data/epl/raw/E0_1415.csv
bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085  data/epl/raw/E0_1516.csv
9625a7652b5f98fbd3e2e4d378c851fc246693f3343e34a72428d5b6e864d3e0  data/epl/raw/E0_1617.csv
4f3389365ef3f7ac966764ed8ba67cf3b79f5aebed18dd224099c4b2c98bc67b  data/epl/raw/E0_1718.csv
7c096b3c2ecd54c6993d22eeea73450c2bde11e3457238b226b8f43c62dfc35e  data/epl/raw/E0_1819.csv
100037618b94f94057400bb02bf6bac4ef74ddaa58cde4b38370839c39caee61  data/epl/raw/E0_1920.csv
5afe63f69401457b8354eaacee24f9a3e520b3c3af6329564a9783e20d789c62  data/epl/raw/E0_2021.csv
335afcbabeb2939fa10ab39ba3e8215072d0b577cb8d0705c1e44c56e934e703  data/epl/raw/E0_2122.csv
8442792d3b614c94ea3cf381bd2736805889cc1713169035368fff19c3d02380  data/epl/raw/E0_2223.csv
b2e057b0ed959f198b0f63d2391c01239f3608e6de5db68edab3f88e04d07ff3  data/epl/raw/E0_2324.csv
d0c8ce4a96d886cf60cf101f570f4a3893844226f91c7bd769eb568c49edbfa4  data/epl/raw/E0_2425.csv
```

These are final archive files. A provider may have corrected a historical
count after the match; the archive cannot prove the correction time. The
experiment therefore establishes date ordering of matches, not a stronger
claim about the provider's revision history.

## 2. Validation, quarantine, and refusal

Validation runs before any coefficient fit. A row is blank only when `Date`,
`HomeTeam`, and `AwayTeam` are all blank; such trailing rows are ignored. Dates
are parsed by trying exactly `%d/%m/%y` and then `%d/%m/%Y`, never by inference.
Every other row must have a parseable date and canonical teams and must join
exactly once to the tidy archive by date/home/away. Each shot field must be
present, numeric, finite, integer-valued, and nonnegative. The containment
checks are `HST <= HS` and `AST <= AS`. Goals exceeding shots on target is not a
validation failure: own goals and provider definitions make that an unsafe
invariant.

The preregistration-time profile found no missing or nonnumeric shot fields and
one containment failure:

```text
2021-08-15  Newcastle v West Ham  HS=17  AS=8  HST=3  AST=9
```

That entire row is quarantined from all four historical feature accumulators.
It is not clamped, corrected, winsorized, or imputed. Newcastle–West Ham remains
in the scoring population and receives a prediction because its own post-match
counts cannot enter its prediction anyway. The row cannot affect later
predictions. The build must reproduce exactly this one quarantine key and these
four values. Zero or two such rows, a different key/value, or any additional
invalid row is `ShotPanelMismatch` and stops the run; it does not silently
expand the quarantine.

Other typed stops are:

| Refusal | Condition |
|---|---|
| `SourceDigestMismatch` | any pinned raw or corpus digest differs |
| `ShotSchemaMismatch` | any required field is absent, duplicated, or renamed |
| `ShotValueInvalid` | null, nonfinite, negative, or noninteger shot value outside the one pinned quarantine |
| `ShotPanelMismatch` | row count, quarantine identity, or one-to-one archive join differs |
| `FixtureSetMismatch` | candidate/native/market/outcome keys are not the identical 2,280 ordered keys |
| `TimeBoundaryViolation` | an observation with `date >= cutoff` reaches a feature accumulator |
| `ProbabilityInvalid` | any native/market probability is nonfinite or not strictly positive, any candidate probability is nonfinite/outside [0,1], or a row sum differs from 1 by more than `1e-12` |
| `FitFailure` | the one fixed optimizer does not converge or returns nonfinite coefficients |
| `CanaryFailed` | any negative or positive-control canary in §7 fails |
| `LockMismatch` | the harness or coefficient manifest differs from the applicable run manifest |

No refusal may be converted into row dropping or an alternate specification.

## 3. The one fixed challenger

### 3.1 Point-in-time shot strengths

For a prediction block with cutoff `C`, the eligible history is exactly valid
EPL rows with `date < C`. The cutoff is the native walk-forward block cutoff,
not the target fixture's kickoff. Consequently, matches on `date == C` and
earlier matches within the same prediction block are excluded. Every match in a
block sees the same history.

For every eligible historical row `i`, freeze

```text
w_i(C) = 2 ** (-(C - date_i).days / 365)
```

so the half-life is exactly 365 days. There is no half-life sweep. At each
cutoff compute four weighted league means: home and away total shots and home
and away shots on target. For a channel `m` (total shots or shots on target), a
team's attack observations are its own home value divided by the home league
mean when it played home, and its own away value divided by the away league
mean when it played away. Its defence observations are the opponent's value,
divided by the opponent-role league mean. Weighted attack and defence ratios
are shrunk toward 1 with a fixed pseudo-exposure of `kappa = 10`:

```text
ratio = (10 + sum_i(w_i * normalized_count_i)) / (10 + sum_i(w_i))
```

For fixture home team `h` and away team `a`, the four pre-match predictions are

```text
HS_hat  = mean_HS(C)  * attack_shots(h,C) * defence_shots(a,C)
AS_hat  = mean_AS(C)  * attack_shots(a,C) * defence_shots(h,C)
HST_hat = mean_HST(C) * attack_sot(h,C)   * defence_sot(a,C)
AST_hat = mean_AST(C) * attack_sot(a,C)   * defence_sot(h,C)
```

The pseudo-exposure supplies a neutral team ratio for promoted/cold-start
clubs; it does not invent a shot count. A missing league mean is a typed stop.

Exactly four features are then formed:

```text
x1 = HST_hat - AST_hat
x2 = (HS_hat - HST_hat) - (AS_hat - AST_hat)
x3 = HST_hat + AST_hat
x4 = (HS_hat - HST_hat) + (AS_hat - AST_hat)
```

Their means and population standard deviations are computed on the 1,520
training fixtures only and frozen. `z_j = (x_j - mean_j) / sd_j`; a zero or
nonfinite standard deviation is `FitFailure`. There are no caps, interactions,
splines, team indicators, season indicators, or alternate feature sets.

### 3.2 Fixed residual probability tilt

The coefficient-training partition is exactly 2015/16–2018/19. `E0_1415` is
history only. The schedule has exactly **142** blocks: 35, 36, 36, and 35 in
season order. A block is the exact tuple `(season, ISO year, ISO week)` obtained
from the normalized match date. Blocks are ordered by their earliest match
date; `C` is that minimum calendar date at `00:00:00`, and every fixture in the
block uses that same `C`. There is no kickoff-time, daily, matchday, rolling
seven-day, or fortnightly alternative.

Each training fixture receives a native 1X2 probability generated by the
parent-commit implementation of `epl.walkforward._one_cutoff`, with cutoffs
constructed exactly as above and `cadence=1`. Both the native fit and shot state
use only rows with `date < C`. The identity is:

| Native training component | Frozen identity |
|---|---|
| Source parent commit | `6450fb51aef22021a00b3eed72395f1c4141cae3` |
| `epl/walkforward.py` blob at that commit | SHA-256 `c68f316f4f3d74881de1312aafd42ae08b5963bfc43ec5065baab4250c5c8710` |
| `epl/fit.py` blob at that commit | SHA-256 `ab471e96b8321359a0998d6ca7a03496b91b484582ef081f0d43462db6ed1ce6` |
| Locked native Python family | 157 parent-commit `.py` files under `epl/` (excluding tests) and `src/wcmodel/`, canonical SHA-256 `d388375d3158c122c2fd92c05a670329da7f96957c3814f02937f1c85f6433b0` |
| EPL frozen config | `epl/config_frozen.json`, SHA-256 `9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc` |
| Runtime config | `config/config.yaml`, SHA-256 `ffc577bdb690e699fbf9febceddebf41739fbf52d9910cc529b8462f7a7fee65` |
| Native inference | seed `20260611`, no override; ADVI, 1,000 draws, 1,000 tune, 30,000 ADVI iterations |
| Dependency intent | `pyproject.toml` SHA-256 `97c2299706e305f0583c59aeb155028aa84e5ec18ddaba3c3addfbefe7882d9b`; `uv.lock` SHA-256 `aa57fed33191e34bbed23940f174e411beab0bfe395d8898146f13adea4f2df7` |

The native-family digest uses the repository's `_code_sha256` framing: sorted
relative path and blob bytes, each preceded by its eight-byte big-endian
length. The later harness records resolved imported package versions as well as
the two dependency-file digests. Any mismatch is `LockMismatch`; current dirty
working-tree bytes are not a substitute for the named parent blobs.

The training inputs, generator, and dependencies must be hash-verified before
the training-only run that creates predictions and fits the tilt. That run
writes a second, immutable coefficient manifest containing the
training-prediction digest, feature moments, eight coefficients, optimizer
receipt, and objective value. The coefficient manifest is hash-frozen before a
decision prediction exists. Training native probabilities pass through the
same eight-decimal rounding as the stored decision native probabilities;
decision rows use the stored values without regeneration.

Let `pH`, `pD`, and `pA` be the native probabilities. With away as reference,
the challenger is

```text
eta_H = log(pH / pA) + beta_H dot z
eta_D = log(pD / pA) + beta_D dot z
eta_A = 0
q = softmax(eta_H, eta_D, eta_A)
```

There is no intercept. The eight coefficients (`beta_H` and `beta_D`, four
each) are fitted once by minimizing, over the training partition,

```text
sum_i(-log(q_i[y_i])) + 0.5 * sum(beta ** 2)
```

from an all-zero start with deterministic L-BFGS-B, `maxiter=10000`,
`ftol=1e-12`, and `gtol=1e-10`, using float64 values and the analytic gradient.
The build freezes the exact numerical-library version. Failure to converge is a
refusal, not permission to change the optimizer or penalty. After this one
training fit, coefficients and scaling moments are immutable and applied
unchanged to all 2,280 scoring rows.

This is the only arm. The half-life, pseudo-exposure, four features, penalty,
optimizer, training seasons, and combination rule are not selected or tuned on
the scoring corpus. No candidate sweep, ablation winner, best season, or
alternative random seed may replace it after the decision outcomes are read.

## 4. Paired estimands and uncertainty

For ordered outcomes home/draw/away, the per-match ranked probability score is

```text
RPS(p,y) = 0.5 * ((pH - I[y=H])**2
                + (pH + pD - I[y in {H,D}])**2)
```

The two paired deltas, both on the exact same 2,280 fixtures, are

```text
d_native_i = RPS(dc_1x2_shots_i, y_i) - RPS(dc_native_i, y_i)
d_market_i = RPS(dc_1x2_shots_i, y_i) - RPS(market_i, y_i)
```

Negative is improvement. The primary point estimates are the arithmetic means
of these per-match deltas; they are not differences between separately rounded
season means. Stored native and market RPS values are independently recomputed
from their probabilities and must agree with the corpus within `1e-12` per row.

The primary interval is a paired nonparametric block bootstrap over the 212
`(season, ISO week)` blocks: sample 212 blocks with replacement, retain every
fixture in a sampled block, compute the fixture-weighted mean paired delta, and
repeat `B=10,000` times with NumPy `Generator(PCG64(20260831))`. Report the
2.5th and 97.5th percentiles for both estimands.

Season sensitivity is mandatory and decision-relevant but not a substitute for
the primary: report each of the six season means and a paired whole-season
bootstrap that samples six seasons with replacement, `B=10,000`,
`Generator(PCG64(20260832))`, again using fixture-weighted means and percentile
endpoints. Also report mean multiclass log loss and its paired deltas as a
non-deciding diagnostic; it cannot rescue a failed RPS gate.

No fixture, season, or block may be omitted after scores are visible. No
unpaired test, iid match bootstrap, one-sided interval, multiple-testing
adjustment, or alternative market de-vig is substituted.

## 5. Expected effect and frozen decision bars

The planning expectation against `dc_native` is a mean paired RPS change of
**-0.0025 to -0.0005**, with a central expectation near **-0.0013**. This is a
prospective engineering prior, not evidence. Because the frozen native-to-
market gap is about +0.0065 RPS, the expected challenger remains roughly
**+0.0040 to +0.0060 worse than market**. A market win is therefore possible in
principle but not the modal expectation; this experiment must be allowed to
say that the feature is useful yet insufficient.

The result receives exactly one of these dispositions:

1. **Eligible for a separately preregistered production build** only if all are
   true: mean `d_native <= -0.0010`; the upper endpoint of the primary weekly
   95% interval for `d_native` is `< 0`; at least four of six season means are
   negative; no season mean `d_native` exceeds `+0.0020`; and mean log loss is
   no worse than native by more than `+0.0010`.
2. Add the label **market-competitive** only if mean `d_market <= 0` and the
   upper endpoint of its primary weekly 95% interval is `< 0`. This label is
   required for any claim that the challenger beats market prices.
3. **Research signal only; do not adopt** if the native effect is favorable but
   any eligibility/no-harm bar fails, or if the native mean lies in
   `(-0.0010, 0)`.
4. **Reject** if mean `d_native >= 0` or a safety/refusal condition is triggered.

Passing these bars does not itself change production. The challenger produces
only 1X2 probabilities and cannot silently replace a scoreline model or table
simulator. “Eligible” means the owner may authorize a new, prospective,
scoreline-compatible design; it is not permission to retrofit this result.

## 6. Scope and lock

The write set for the present preregistration step is exactly this new file:
`reports/epl_shots_prereg.md`. No fit is authorized by writing it. No current
`src/`, `scripts/`, model, parser, schema, walk-forward, simulator, config, raw
data, or existing report file is in scope.

The later allowed write set is exactly new files at `epl/shots.py`,
`epl/shots_harness.py`, `epl/tests/test_shots.py`,
`data/epl/fit/shots_sot/`, `reports/evidence/epl_shots/`, and the eventual
`reports/epl_shots_result.md`. The build must read shots through a sidecar.
Every existing file, all of `src/`, all of `scripts/`, `epl/parse.py`,
`epl/schema.py`, the frozen native corpus, and production wiring are locked.
A need to write any other path stops the lifecycle for an owner ruling and
amended preregistration. Generated evidence must never overwrite an artifact.

The first, harness manifest is deliberately non-self-referential. It records
`freeze_parent_commit` and that commit's tree (the committed preregistration
state immediately before the freeze bundle), plus SHA-256 of every audited new
source/test/runner file, all pinned data/config/dependency identities, resolved
package versions, output schemas and row/key invariants, synthetic canary
receipts, and audit receipt. It does **not** claim to contain its own future git
commit or hash. The harness-freeze commit, `H`, adds only the allowed audited
bundle and this manifest. Later verification recomputes every listed file hash;
it does not require `HEAD == H`, because coefficient and result commits are
expected descendants.

The training feature moments and fitted coefficients do not exist at this
first freeze. The training-only subphase creates artifacts plus a second,
non-self-referential coefficient manifest. That manifest records `H`, the
SHA-256 of the frozen harness manifest, and SHA-256 of every training
prediction/moment/coefficient/optimizer artifact; it neither records its own
future commit nor hashes itself. A coefficient-freeze commit, `K`, adds only
those content-addressed training artifacts and the coefficient manifest. The
decision invocation names `K` and verifies ancestry plus all listed bytes,
rather than requiring the then-current `HEAD` to equal `K`. A harness mismatch
refuses before training; a coefficient mismatch refuses before reading
decision outcomes.

## 7. Leakage canaries and adversarial checks

All canaries have negative and positive controls; bit-identical negative output
without a moving positive control is not a pass. Before the first hash freeze,
the auditor runs synthetic versions of every canary and inspects the real-panel
validation receipts that require no fit. Real-panel legs requiring fitted
coefficients or decision rows run as automated, non-reporting gates inside the
two phase-5 subphases; their logic is already frozen and their receipts are
published. They cannot be used to revise the specification.

1. **Cutoff boundary.** For a chosen block, replace every shot field on rows
   with `date >= C` by large, different but internally valid values. Its
   histories, four features, and predictions must be bit-identical. Changing a
   valid row at `date < C` must move at least one applicable feature by more
   than `1e-9`. A dedicated boundary fixture proves `date == C` is excluded and
   `date == C-1 day` is included.
2. **Target and same-block isolation.** Corrupt a target fixture's own shot
   values and all same-block shot values; every prediction already issued for
   that block must be bit-identical. A prior-block positive control must move.
3. **Outcome isolation.** Corrupt all scoring outcomes and results while
   holding the frozen training fit fixed; all 2,280 challenger probabilities
   must be bit-identical. In a pre-freeze synthetic positive control, changing
   an eligible synthetic training outcome must move at least one coefficient.
   No real-data fit is permitted for this canary before the harness freeze.
4. **Odds isolation.** Corrupt all market probabilities; challenger
   probabilities must be bit-identical, while the market paired-score
   diagnostic must move. Market prices are comparator data, never features.
5. **Zero-tilt identity.** With all eight coefficients set to exactly zero in a
   unit fixture, the transformation must reproduce native probabilities within
   `1e-12`. As its positive control, set `z1=1` and only the home `z1`
   coefficient to `+0.1`; at least the home probability must move by more than
   `1e-9`. This is a formula test, not an alternate experiment arm.
6. **Quarantine poison tests.** Inject, one at a time, a null, negative,
   noninteger, `HST>HS`, `AST>AS`, duplicate key, missing join, and second bad
   row. Each must reach its named refusal. The pinned Newcastle row alone must
   quarantine and allow all 2,280 score keys.
7. **Fixture integrity.** The canonical ordered 2,280-key panel is the negative
   control and must pass unchanged. Drop, duplicate, or reorder one key as
   separate positive controls and require `FixtureSetMismatch` every time; the
   scorer may not repair the panel.
8. **Look-ahead trap.** Make future shot rows perfectly encode their future
   outcomes; pre-cutoff features and predictions must remain bit-identical. As
   the positive control, place the same encoded signal in an otherwise eligible
   `date < C` row and require an applicable feature to move by more than `1e-9`.

An independent adversarial audit must inspect date comparisons, accumulator
membership, raw-column allowlisting, quarantine semantics, train/score
separation, comparator isolation, resampling code, and every decision
inequality. The auditor should attempt deliberate failures; a green ordinary
test suite alone is not an audit receipt.

## 8. Locked lifecycle

The phases are sequential and may not be collapsed:

1. **Preregister.** Commit this document while no challenger implementation,
   fit, prediction, or result exists.
2. **Build.** Implement only the fixed specification and typed refusals. Use
   synthetic fixtures for fit-path development. Source validation may verify
   the pinned raw shapes/digests, but no real-data native prediction or
   coefficient fit and no scoring-corpus paired delta may be computed, even
   informally.
3. **Adversarial audit.** A reviewer runs §7, inspects the complete diff and
   write set, and records defects. Repairs require the canaries and audit to be
   rerun.
4. **Hash freeze.** Commit the audited code/tests, synthetic canary receipts,
   dependency versions, data digests, and pre-run manifest. The executable must
   require `harness_frozen: true`. No native training prediction, coefficient
   fit, decision-corpus prediction, or score may precede this commit `H`.
5. **Run, in two gated subphases.** First, after verifying the harness manifest,
   run the real 2015/16–2018/19 training partition exactly once: create its
   point-in-time native/shot features and predictions, fit the one tilt, and
   write the training-prediction digest, feature moments, eight coefficients,
   optimizer receipt, and objective into a content-addressed coefficient
   manifest. Do not open decision outcomes or create a decision prediction.
   Commit/hash-freeze that manifest as `K` without changing code, data,
   dependencies, or rules. Second, verify both manifests and run the 2,280-row
   decision stage exactly once, producing predictions, paired scores,
   intervals, season sensitivity, and disposition. A process crash may resume only from
   content-addressed shards with matching hashes; changing code, data, seed,
   coefficients, moments, or specification is a new experiment, not a rerun.
6. **Publish regardless of sign.** Commit a new result report and immutable
   evidence manifest containing all estimates, intervals, per-season results,
   exclusions (expected to be zero scoring fixtures), canary/audit receipts,
   and the applicable frozen disposition. If a typed refusal occurs before an
   estimate can validly exist, publish the refusal name, stage, message, both
   manifest identities, and every receipt/count completed before the stop; mark
   headline RPS, intervals, season results, and log loss explicitly
   `N/A — not computed after <RefusalName>`. Do not fabricate zeroes or elevate
   partial diagnostics into estimates. Null, harmful, and refused results are
   published with the same provenance standard as favorable ones.

There is no post-result repair, hyperparameter sweep, best-seed selection,
season deletion, 2025/26 peek, or quiet replacement of the market benchmark.
Any follow-up must start with a new named preregistration that cites this result.
