# WHAT I CHECKED

I inspected Git objects at commit `4c011837f1083864e524f48861ac620bcf3f89fd` only. I did not read repository working-tree files, import working-tree code, execute the harness, or run tests. There was no pin deviation.

I read the complete eight-item case record, beginning with the fourth-pass deciding review, then inspected the pinned v2 document, harness, tests, supporting protected modules, all four closure commits, and relevant historical diffs.

The closure changed exactly:

- `reports/epl_widening_prereg_v2.md`
- `epl/evwiden.py`
- `epl/tests/test_evwiden.py`

The protected `dcfit`, `simretro`, `leaguesim`, `particles`, adjustment, and store implementations were unchanged in `1afd54d..4c01183`.

I could independently check static control flow, signatures, formulas, committed text, commit ancestry, and which Git-tracked modules changed. I could not independently verify the reported test outcomes, `LOCK VALID`, 18/18 rendered rows, current ignored-artifact absence, shared-store bytes/mtime, or that pass 7 has not run.

Because `data/` is ignored (`.gitignore:14-16`), I had to accept from the document, tests, investigator, or author:

- Corpus/archive/ledger census values: 85 thin, 52 treated, 51 new cells, 47 playing, 78 openings, 820 controls, and the 35/16/19 table census.
- The protected retro ledger’s 200 rows/40 completed cells and its omissions.
- Excluded masses `0.0234`, `0.0216`, and `0.0328`.
- The store’s reported 184,115 bytes, mtime, and unchanged state.
- Deletion or nonexistence of `first_real_fit.json`, experiment artifacts, and the feasibility record.
- Owner-reported `1,355 passed / 1 skipped`, 265 widening tests, and current rendered-block output.

The exact, deduplicated Git-command log is below. Repeated `nl`, `sed`, and `rg` display filters are omitted because their underlying Git invocation was identical.

```text
git rev-parse '4c01183^{commit}'
git rev-parse '4c011837f1083864e524f48861ac620bcf3f89fd^{commit}'
git rev-parse --verify '4c011837f1083864e524f48861ac620bcf3f89fd^{commit}'
git cat-file -t 4c011837f1083864e524f48861ac620bcf3f89fd
git cat-file -p 4c011837f1083864e524f48861ac620bcf3f89fd
git show --no-patch --format=fuller 4c011837f1083864e524f48861ac620bcf3f89fd
git ls-tree -r --name-only 4c01183
git ls-tree -l 4c01183 -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git log --oneline --decorate --no-abbrev-commit 1afd54d..4c01183
git log --format='%H %s' 1afd54d..4c01183
git diff-tree --no-commit-id --name-status -r 1afd54d 4c01183
git diff-tree --no-commit-id --stat -r 1afd54d 4c01183
git diff-tree --no-commit-id --name-status -r 1afd54d 4c01183 -- epl/dcfit.py epl/simretro.py epl/leaguesim.py epl/particles.py epl/season/points_adjustments.jsonl src/wcmodel/data/store.py
git diff --stat 1afd54d 4c01183 -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git diff --unified=40 1afd54d 4c01183 -- reports/epl_widening_prereg_v2.md
git diff --unified=40 1afd54d 4c01183 -- epl/evwiden.py
git diff --unified=40 1afd54d 4c01183 -- epl/tests/test_evwiden.py
git show 4c01183:reports/epl_widening_prereg_v2.md
git show 4c01183:reports/epl_widening_prereg.md
git show 4c01183:reports/epl_sim_retro_v1_1.md
git show 4c01183:epl/evwiden.py
git show 4c01183:epl/tests/test_evwiden.py
git show 4c01183:epl/simretro.py
git show 4c01183:epl/particles.py
git show 4c01183:epl/leaguesim.py
git show 4c01183:epl/dcfit.py
git show 4c01183:epl/season/points_adjustments.jsonl
git show 4c01183:src/wcmodel/data/store.py
git show 4c01183:.gitignore
git grep -n assert_seam_allowed 4c01183 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v2.md
git grep -n -E '^(def|class) ' 4c01183 -- epl/evwiden.py
```

# FINDING-BY-FINDING

## M1 — RESOLVED

The document now consistently defines the 78-opening union through `e*=12`, meaning `e_min < 12`, not `≤12` (`reports/epl_widening_prereg_v2.md:484-487`). `fit_openings` computes the maximum grid value and uses the matching strict predicate (`epl/evwiden.py:1292-1310`). Both legs agree.

## M5 — RESOLVED

The supporting prose now distinguishes feature-frame parity from the actual 820-fixture fitted-forecast control and states that reproducibility is the claim under test (`reports/epl_widening_prereg_v2.md:651-670`). `Engine.fit` executes the incumbent prediction first and compares all stored rows before treatment prediction (`epl/evwiden.py:2078-2097`).

## B3 — STILL-OPEN

The text freezes decision constants and forbids public overrides (`reports/epl_widening_prereg_v2.md:551-566`, `2200-2218`). The harness still exports lower-level deciding surfaces with caller-selected constants: `estimand(grid=..., n_boot=..., seed=...)` (`epl/evwiden.py:4031-4105`) and `iv_c_verdict(n_boot=..., seed=...)` (`epl/evwiden.py:6674-6689`). The code leg remains broader than the law.

## B4 — RESOLVED

The law requires the entire 35-cell oracle before treatment and control→parity→treatment within each cell (`reports/epl_widening_prereg_v2.md:840-876`). The default production path completes and validates the oracle before constructing the new runner (`epl/evwiden.py:6338-6363`), while `run_cell_arms` places parity between the two calls (`epl/evwiden.py:5563-5610`). The exported callback seam is a new closure defect below, but the default path fixes this prior ordering defect.

## B6 — STILL-OPEN

The document treats the first-fit file as a one-way ratchet (`reports/epl_widening_prereg_v2.md:2304-2346`). Absence still returns `None` and restores the pre-fit state (`epl/evwiden.py:2680-2699`); enforcement has no independent append-only witness (`epl/evwiden.py:2741-2756`). Deletion therefore still resets the lifecycle.

## I6 — STILL-OPEN

The document says every missing published value is disagreement (`reports/epl_widening_prereg_v2.md:2592-2601`). `verify` is strict for several table fields, but still conditionally compares precision/unanimity members only when represented on one or both sides and permits published adoption structures with missing subfields (`epl/evwiden.py:7950-7998`). The implementation does not implement the universal statement.

## N-FREEZE-COMMIT — STILL-OPEN

The text demands committed v2-only evidence, exact schema, exact membership, first-fit binding, and conformance (`reports/epl_widening_prereg_v2.md:2266-2293`). The guard accepts arbitrary `sources` and `rev`, finds hashes anywhere in supplied blobs, and identifies the schema by substring (`epl/evwiden.py:8182-8241`, `8263-8268`). Its conformance check accepts any nonempty all-green subset (`epl/evwiden.py:8302-8319`). The code leg remains attested rather than exact.

## N-RH-FIRST-ACT — STILL-OPEN

The prescribed first post-freeze lifecycle includes a manual scratch single-opening exercise (`reports/epl_widening_prereg_v2.md:2116-2134`). The generated launcher contains only comments for that step, then proceeds to later commands (`epl/evwiden.py:9782-9809`). Worse, step 2 requires the fixed step-1 marker but writes into scratch while the canary/guard path expects the preregistered sequence (`epl/evwiden.py:3779-3813`, `10238-10265`). The sequence remains non-executable as written.

## NB4 — RESOLVED

This was the same treatment-before-parity defect as B4. The default production path now verifies all 35 oracle rows before the first treatment (`epl/evwiden.py:6136-6185`, `6338-6363`).

## NB5 — STILL-OPEN

Like B6, the supposedly one-way first-fit state is still an ordinary deletable ignored file (`epl/evwiden.py:2274-2279`, `2680-2756`). Neither document prose nor the harness creates an external or append-only ratchet.

## NB6 — STILL-OPEN

Normal step-4 publication now precedes evidence, but direct APIs remain forgeable. `run_table` itself has no sequence requirement (`epl/evwiden.py:6314-6363); `merge` is callable without the CLI sequence (`epl/evwiden.py:4833-4905`); and marker validation does not require `complete` or recompute the digest named in `produced` (`epl/evwiden.py:3594-3641`). Missing `complete` is treated as true on read (`epl/evwiden.py:10180-10186`).

## NB7 — STILL-OPEN

The ordinary tally-loading path rebinds files. But `score_table(tallies=..., mc=...)` still accepts caller-supplied deciding evidence (`epl/evwiden.py:6833-6872`). The guard is keyed to `ledger_path`, so supplying tallies while pointing at a scratch path avoids the production refusal (`epl/evwiden.py:6864-6981`). The alternative evidence path remains.

## NB8 — STILL-OPEN

`freeze_block` consumes `implementation_report` and believes each row’s own `ok` field (`epl/evwiden.py:9517-9545`, `9548-9588`). Several rows remain partial or false, and the committed-block reader accepts a green subset (`epl/evwiden.py:8165-8179`, `8302-8319`). The report is still capable of certifying itself.

## A1 — STILL-OPEN

The law demands that the two digests expose every treatment input channel (`reports/epl_widening_prereg_v2.md:815-828`). The production digest split is substantially improved, but the conformance route does not drive the actual `TableRunner.__call__`; it calls `arm_record`/synthetic helpers directly (`epl/tests/test_evwiden.py:2727-2771`). A later input channel inserted between helper and runner can remain green.

## A2 — RESOLVED

I withdraw the fourth-pass overstatement that the identity canary had no operative refusal. The canary itself is derivative, but the production path first executes `assert_identity_control` and `assert_untreated_unmoved`, then evaluates the no-added-club branch (`epl/evwiden.py:2078-2126`). The tests exercise those substantive refusals. That is sufficient for the underlying obligation.

## NEW-B1 — STILL-OPEN

Removing `n_sims`, simulation seed, and simulation chunk-size parameters from runner constructors is real (`epl/evwiden.py:5245-5301`, `5893-5921`). The class-wide law is not: public grid, `e*`, bootstrap, cell-list, `n_particles`, and population parameters remain (`epl/evwiden.py:4031-4105`, `5067-5082`, `5131-5185`, `5261-5301`, `5967-6016`, `6314-6321`, `6674-6689`). The module constants read by `frozen_table_constants` are also mutable and are not value-validated (`epl/evwiden.py:5245-5258`).

## NEW-B2 — STILL-OPEN

The new ancestry classifier decides derivation using overlap with pinned club keys (`epl/evwiden.py:2311-2362`). A frame copied from pinned dates, scores, or row structure but with renamed club keys is classified synthetic; empty frames are synthetic; missing key columns become unknown, which the guard permits (`epl/evwiden.py:2535-2594`). `TableRunner`, `ParityRunner`, and `Engine` also retain injectable dependencies or subclass surfaces (`epl/evwiden.py:1893-1965`, `5613-5666`, `5893-5921`).

## NEW-B3 — STILL-OPEN

`unanimity_is_valid` checks internal shape and self-consistency, not provenance from the 35 rebound tallies or a genuine `K=200` resampling computation (`epl/evwiden.py:6701-6755`). A fabricated object containing 200 identical verdicts, matching dissent count, and the point verdict satisfies it. `table_gate` trusts that object (`epl/evwiden.py:7062-7188`). `score_table` also permits supplied `mc` and optional expected census (`epl/evwiden.py:6833-6981`).

## NEW-B4 — STILL-OPEN

`check_implementation=False` was removed, but equivalent caller-attested paths survive. `freeze_block` accepts supplied `power`, `pre_freeze_runs`, corpus, archive, ledger, and table (`epl/evwiden.py:9548-9596`). `merge` still accepts lifecycle-affecting arguments and can guard one scratch target before writing its fixed production output (`epl/evwiden.py:4833-4911`, `5027-5030`). The closure is not end-to-end.

## NEW-B5 — STILL-OPEN

Pass 4 is now callable, but it does not do exactly what the text claims. The record says it stops before importing `dcfit` (`epl/evwiden.py:2252-2258`); `Engine.fit` imports `dcfit` first and only then checks `can_fit` (`epl/evwiden.py:2009-2027`). Text and code therefore disagree on the structural stopping point.

## NEW-B6 — STILL-OPEN

The protected parity path remains uncaught and is statically expected to fail at its first cell (`epl/evwiden.py:5923-5964`, `5967-6016`). Pass 7 has not been validly run, and its implementation does not establish feasibility. Detailed ruling is below.

## NEW-B7 — RESOLVED

The normal publication sequence now writes the step-4 marker before evidence and includes stable sequence markers in the manifest (`reports/epl_widening_prereg_v2.md:2030-2037`, `2576-2581`; `epl/evwiden.py:7293-7306`, `10375-10396`). Marker writes are write-once/reverify-on-repeat (`epl/evwiden.py:3644-3702`). On the prescribed path, evidence publication no longer invalidates its just-written MANIFEST.

## NEW-B8 — STILL-OPEN

A caught `CanaryFailed` now writes `PASS:false` and a `complete:false` marker before re-raising (`epl/evwiden.py:10194-10216`). Other failures—unexpected runtime errors, process death, serialization failure, or interruption before the catch/write—leave no marker and remain retryable. The fix closes one exception class, not the file-drawer channel.

## IMP-EFFECTIVE-POSTERIOR-BOTH-NULL — RESOLVED

The document now makes either missing hash a refusal (`reports/epl_widening_prereg_v2.md:798-813`), and `assert_native_parity` refuses missing values before comparing them (`epl/evwiden.py:6051-6074`).

## IMP-FIRST-FIT-TIMESTAMP — STILL-OPEN

The old permission-check timestamp was moved in `Engine.fit` (`epl/evwiden.py:2031-2053`). But other paths record before the operation whose occurrence they attest: canary before its runner (`epl/evwiden.py:3540-3548`), `TableRunner` before protected fit/simulation (`epl/evwiden.py:5680-5691`), and `ParityRunner` before `_runner(...)` (`epl/evwiden.py:5923-5933`). The document says “instant of the first real fit”; these remain attempt timestamps.

## IMP-POST-FIT-PROSE — STILL-OPEN

The prose-note allowance was correctly removed (`reports/epl_widening_prereg_v2.md:2331-2358`). But `assert_no_hashed_file_moved` binds the preregistration to its committed HEAD blob while current-byte checks cover only the two harness files (`epl/evwiden.py:2789-2805`). An uncommitted post-fit edit to v2 is therefore not detected.

## IMP-PREFREEZE-SCRIPT — STILL-OPEN

The text says the pre-freeze write enumeration is complete (`reports/epl_widening_prereg_v2.md:1862-1872`). `write_launch_script` refuses the default production target pre-freeze but permits a scratch directory and writes inside the repository if that scratch path is outside the narrowly tested evwiden directories (`epl/evwiden.py:9843-9863`). The enumeration remains false.

## IMP-L16-RATIO — RESOLVED

The document’s ratio column and six frozen values are present (`reports/epl_widening_prereg_v2.md:1467-1481`), and `power_reproduces` compares the ratio field (`epl/evwiden.py:4615-4670`). The separate supplied-power bypass remains under NEW-B4/L16.

## MIN-POWER-DATED-NOTE — RESOLVED

`power_reproduces` no longer advertises v1’s retired dated-note remedy (`epl/evwiden.py:4671-4676`).

## MIN-CONTINUITY-AND-STALE-PROSE — STILL-OPEN

Examples remain:

- Module preamble says six passes/no fits although v2 now enumerates seven and authorizes pass 7 (`epl/evwiden.py:95-102`).
- Test preamble still describes v1/two-gate structure (`epl/tests/test_evwiden.py:5-9`, `28-44`).
- `harness_freeze_status` says “Four conditions” while implementing a fifth (`epl/evwiden.py:8192-8204`, `8302-8307`).
- `write_evidence` still comments “exactly the eleven” for a 52-member manifest (`epl/evwiden.py:7831-7843`).
- The freeze block says every enumerated pass is unable to fit, despite pass 7’s protected fits (`epl/evwiden.py:9648-9653`).

The new no-post-fit-edit rule would make these permanent.

## MIN-READ-ONLY-STORE-TOCTOU — STILL-OPEN

`read_only_store` checks that `results.parquet` exists and then constructs `BitemporalStore` (`epl/evwiden.py:5117-5128`). The constructor creates its root directory (`src/wcmodel/data/store.py:20-23`), and existence can change between check and construction. The caveat remains.

# CONFORMANCE ROWS L1-L18

| Row | Re-grade | What it actually executes | Can it remain green while the named obligation fails? |
|---|---|---|---|
| L1 | Partial behavioural | Uses a corpus genuinely different from Arm B and removes the old always-true disjunct (`epl/evwiden.py:8725-8778`). | Yes. It detects the named corpus-difference mutation, but does not prove every arm uses one posterior. |
| L2 | Substantively behavioural, scope-partial | Runs a synthetic 35-cell table through `run_table`, scoring, gate, and failure conditions (`epl/evwiden.py:8780-8809`). | Yes. It covers this path, not all population/decision entry points. |
| L3 | Partial | Exercises the tie rule and checks a joint SE relationship (`epl/evwiden.py:8811-8858`). | Yes. Per-cell resampling can still satisfy that relationship. |
| L4 | Behavioural for the escaped mutation; partial overall | On jittered tallies, requires the joint draw to differ from a de-paired implementation (`epl/evwiden.py:8464-8481`, `8860-8902`). | Yes for fabricated unanimity/provenance, but no for the specific per-cell P5 mutation. |
| L5 | Partial | Drives an injected conformance runner, not `TableRunner.__call__` (`epl/evwiden.py:8915-8962`). | Yes. The production runner can be reordered while this helper stays green. |
| L6 | Partial | Checks empty root, read-only access, table cells, and snapshots (`epl/evwiden.py:8964-9002`). | Yes. It misses constructor TOCTOU and other write-capable modules. |
| L7 | False class-wide | Exercises the default guarded target (`epl/evwiden.py:9004-9053`). | Yes. Scratch-target merge/publication bypasses remain. |
| L8 | Partial | Checks wrong/missing first-fit identity (`epl/evwiden.py:9055-9083`). | Yes. It does not cover timing, deletion, or every recording site. |
| L9 | Substantively behavioural, wiring-partial | Parses non-comment launcher commands and exercises marker ordering/write-once behavior (`epl/evwiden.py:9085-9164`). | Yes. It misses the impossible/manual step 2 and direct APIs. |
| L10 | Substantively behavioural, wiring-partial | Mutates tally contents/digests and tests refusal (`epl/evwiden.py:9166-9212`). | Yes. Production wiring is partly AST-checked, and supplied tallies bypass loading. |
| L11 | Partial | Calls `run_cell_arms` with a custom record function (`epl/evwiden.py:9214-9295`). | Yes. It does not execute `TableRunner.__call__` or exclude hidden callback work. |
| L12 | Partial/source check | Helper refusals are behavioural, but production linkage is established by source inspection (`epl/evwiden.py:9297-9332`). | Yes. Source presence is not execution. |
| L13 | Partial, not the named merge scenario | Calls `assert_structural_zeros` directly (`epl/evwiden.py:9334-9352`). | Yes. Removing its call from `merge` can leave L13 green. |
| L14 | Partial | Perturbs the census, then checks table integration largely through source (`epl/evwiden.py:9354-9374`). | Yes. A wiring removal can survive. |
| L15 | Substantively behavioural, partial | Exercises missing/member/digest/size/marker manifest failures (`epl/evwiden.py:9376-9413`). | Yes. It does not cover every publication route. |
| L16 | False | Accepts caller-supplied power and compares that object (`epl/evwiden.py:9415-9431`; `9517-9588`). | Yes. A fabricated six-row object can match the frozen table without running `power_simulation`. |
| L17 | Partial/false for both controls | Measures `untreated_moved`; `predicate_mismatch` wiring is source-checked (`epl/evwiden.py:9433-9465`). | Yes. Removing one production measurement can remain green. |
| L18 | False class-wide | Checks selected signatures and CLI refusals (`epl/evwiden.py:9467-9504`). | Yes. It misses the estimand grid and mutable module constants; its chunk assertion is effectively tautological. |

The escaped L1 Boolean was repaired. L4 now genuinely requires disagreement between joint and de-paired jittered tallies. The jitter is structurally material—one-hot particle perturbations, not a near-zero float—and the inequality is deterministic at the frozen seed. I could not execute it, so its current green value is accepted from the owner, but the predicate would go red under the specific per-cell mutation.

Independence still fails:

- The principal test calls `implementation_report()` and asserts its `ok` fields (`epl/tests/test_evwiden.py:5380-5401`).
- Companion tests cover selected helpers and source shapes, not all named production obligations (`epl/tests/test_evwiden.py:5404-5493`).
- `freeze_block` consumes the same report (`epl/evwiden.py:9517-9588`).
- The committed-block guard accepts any nonempty all-green subset rather than exactly L1–L18 (`epl/evwiden.py:8165-8179`, `8302-8319`).

Therefore the test is not forbidden to believe the report, and no durable independent artifact outside that report establishes all 18 obligations.

# IN-TREE AUDIT FINDINGS

## 1 — RESOLVED

The exact L1 tautology is gone. The new fixture makes the corpus differ from Arm B and requires the substantive comparison, with no old `or` escape (`epl/evwiden.py:8725-8778`). This resolves the audit’s escaped seed narrowly.

## 2 — RESOLVED

L4 now constructs nonzero-jitter tallies and requires the joint and deliberately de-paired resamplers to disagree (`epl/evwiden.py:8464-8481`, `8860-8902`). The Boolean has no fallback disjunct. At the frozen fixture/seed it is a deterministic mutation test, not a probabilistic “usually differs” assertion.

## 3 — RESOLVED

Launcher evaluation now strips comments and checks actual `need_marker`/`run_step` commands (`epl/evwiden.py:9123-9156`). The old comment-satisfaction escape is closed.

## 4 — RESOLVED

The “at least one added club” requirement is now explicit in document and code (`reports/epl_widening_prereg_v2.md:680-690`; `epl/evwiden.py:1812-1842`, `2078-2084`). A direct test exercises the refusal.

## 5 — RESOLVED

`n_sims`, simulation seed, and simulation chunk size were removed from table runner constructors and resolved centrally (`epl/evwiden.py:5245-5301`, `5634-5664`, `5893-5921`, `6314-6321`). Other frozen-constant surfaces remain separate NEW-B1 failures.

## 6 — STILL-OPEN

All three legs fail:

1. The autouse isolation fixture is function-scoped and wraps test calls; it does not prevent module-import, collection, session fixture, subprocess, or crash-time writes (`epl/tests/test_evwiden.py:81-134`).
2. Because `data/` is ignored, I cannot independently verify deletion or present absence of the stale artifact.
3. §8.9 states an inferred test origin and “whole suite” isolation as facts (`reports/epl_widening_prereg_v2.md:2396-2412`, `2440-2463`). The audit established the likely call site, not an exhaustive provenance proof.

Consequently §8.8’s no-artifact attestation cannot be certified as true from the pinned tree.

## 7 — STILL-OPEN

Pass 4 is callable, but the “before importing `dcfit`” claim remains false: import occurs at `Engine.fit` entry, then `can_fit` is tested (`epl/evwiden.py:2009-2027`, `2252-2258`). Text and implementation do not match.

## 8 — RESOLVED

`table_gate` documentation now describes the implemented unresolved/pass/fail result rather than the stale earlier contract (`epl/evwiden.py:7062-7099`).

## 9 — RESOLVED

The audit’s cited protected-source locations were corrected to the current pinned objects, including the relevant evidence, fit-opening, and bootstrap call sites (`epl/evwiden.py:253`, `372`, `1298`, `6679`, `6769`).

## 10 — STILL-OPEN

The freeze guard still accepts arbitrary `sources` and `rev` (`epl/evwiden.py:8182-8241`). That contradicts the v2-only source claim and permits a caller-selected attestation object.

## 11 — STILL-OPEN

L11 still substitutes custom callbacks for the production runner; L12 still relies partly on source inspection (`epl/evwiden.py:9214-9332`). The named obligations are not durably exercised at the production level.

## 12 — STILL-OPEN

A scratch target can satisfy the seam guard while `merge` proceeds to fixed production publication (`epl/evwiden.py:4833-4911`, `5027-5030`). The lifecycle Boolean/target bypass was narrowed, not eliminated.

# THE CLOSURE PRINCIPLE

## 1. The guard and what it actually inspects

`assert_seam_allowed` is at `epl/evwiden.py:2535-2594`. It inspects only:

- `played`, classified as pinned/derived/synthetic/absent/unknown.
- `corpus`, using frozen row count, seasons, and outcome counts.
- `target`, tested against `EVWIDEN_DIR`, `TABLE_DIR`, `SEQUENCE_DIR`, `EVIDENCE_DIR`, and all of `paths.FIT_DIR`.
- A descriptive seam name/detail that has no enforcement semantics.

It refuses when:

- `archive_provenance(played) == "pinned"`;
- provenance is `"derived"`;
- `is_pinned_corpus(corpus)` is true;
- `target` is `None`, invalid, or within any preregistered directory.

It permits when none of those conditions holds, including `"unknown"`, `"absent"`, and `"synthetic"` archive provenance with a scratch target.

The ancestry test is club-key overlap (`epl/evwiden.py:2311-2362`):

- Exact archive digest → pinned.
- Any pinned club key → derived.
- No pinned club keys → synthetic.
- Missing columns/digest errors → unknown.

Consequences:

- Empty frame: synthetic.
- Renamed club keys: synthetic.
- Pinned dates/scores/fixtures with invented club keys: synthetic.
- A transformed frame with missing keys: unknown.
- A fabricated corpus with the pinned row/season/outcome marginals: pinned corpus.

The “ambiguous middle is refused” claim is false. It was narrowed to club-key ancestry; unknown and non-club-derived frames are allowed.

## 2. Every public surface against the four effects

Legend: A = alter a frozen constant; I = inject implementation; L = attest lifecycle/publication; T = truncate a deciding population.

The exported surface is listed at `epl/evwiden.py:165-198`; additional non-underscore module surfaces appear throughout the file.

| Public surface group | Names | Effect/result |
|---|---|---|
| Error types | `EvWidenError`, `CorpusMissing`, `CorpusDigestMismatch`, `CorpusShapeMismatch`, `ArchiveDigestMismatch`, `LedgerDigestMismatch`, `ConfigNotFrozen`, `MembershipMismatch`, `PredicateMismatch`, `EvidenceLeak`, `CutoffLeak`, `CanaryFailed`, `EvidenceCanaryFailed`, `ControlMismatch`, `UntreatedMoved`, `TableIdentityBreak`, `FitFailed`, `UnpriceableFixture`, `ScoreMismatch`, `SchemaMismatch`, `RowConflict`, `ShardFailed`, `MergeIncomplete`, `TableMCImprecise`, `StoreNotBuilt`, `SequenceViolation`, `FreezeStateUnverified` | No direct A/I/L/T effect. |
| Module constants | `SEED`, `BOOTSTRAP_SEED`, `E_STAR`, `E_GRID`, `ADOPT_DELTA`, `TABLE_TOLERANCE`, `RUN_ORDER`, `MC_BOOT`, `MC_SEED`, `SHARDS`, `POINT_GATE_LABELS`, `MANIFEST_PATHS`, feasibility globals | Mutable Python attributes; production reads several live without value validation. A/L bypass. |
| Loaders/hashes | `sha256_file`, `config_sha256`, `realised_config_sha256`, `assert_config_frozen`, `load_corpus`, `load_archive`, `load_walk_ledger`, `archive_digest`, `read_jsonl`, `load_ledger`, `canonical`, `run_digest`, `sampler_digest`, `substantive_digest`, `plan_state` | Mostly diagnostic, but alternate path/digest-check parameters can create inputs later misclassified by the guard. |
| Membership/population | `effective_evidence`, `evidence_table`, `Membership`, `membership`, `membership_digests`, `fit_openings`, `FitPoint`, `fit_key`, `fit_points`, `shard_points`, `thin_at`, `table_cutoffs`, `table_cells`, `assert_table_census` | A/T through `half_life`, `e_star`, grid, openings, seasons, labels, `check`, and supplied frames/store/config. Mostly unguarded. |
| Walk-forward fit | `Engine`, `Engine.enlarged`, `Engine.fit`, `run_fits`, `partial_engine_pass` | A/I/T through injectable frames/ledger, public point lists, `grid_treated`, `e_star`, subclassing and mutable attributes. Guards cover ordinary real calls, not the whole parameter class. |
| Canaries | `evidence_canary`, `identity_canary`, `direction_canary`, `run_canary`, `write_canaries` | I/L via injected fitter/runner/provisional function and caller-provided record/path. Only `run_canary`’s runner seam is guarded. |
| Lifecycle | `first_fit_record`, `record_first_real_fit`, `write_sequence_marker`, `require_sequence`, `require_run_preconditions`, `sequence_report`, `merge` | L/T through supplied marker contents, `complete`, `enforce`, requirement Booleans, table object, directory, and shard count. Not comprehensively guarded. |
| Scientific decision | `estimand`, `adoption`, `power_structure`, `power_simulation`, `realised_power`, `power_reproduces`, `evidence_object` | A/L/T through grid, seeds, replicate structure, supplied power, supplied conditions, and result objects. |
| Table simulation | `frozen_table_constants`, `simulate_arm`, `particle_tallies`, `assert_tally_binds_the_matrix`, `run_cell_arms`, `TableRunner`, `ParityRunner`, `run_parity_oracle`, `run_table` | A/I/T through `n_particles`, callbacks, books, store/anchor/config, cells, runner/parity, resume, and class mutation. Six selected paths call the guard; many lower surfaces do not. |
| Table decision | `load_table_ledger`, `paired_mc_bootstrap`, `iv_c_verdict`, `unanimity`, `unanimity_is_valid`, `score_table`, `table_gate` | A/I/T through optional expected census, cells, bootstrap constants, supplied tallies/MC/unanimity, and arbitrary scored objects. |
| Publication | `manifest_entries`, `update_manifest`, `read_manifest`, `assert_manifest_complete`, `write_evidence`, `verify` | L through alternate entries/path, `manifest=False`, `require_manifest_complete=False`, optional manifest checking, evidence path, and table ledger. No central seam guard. |
| Freeze/conformance | `git_head`, `git_blob_id`, `git_committed_bytes`, `git_commit_touching`, `git_is_ancestor`, `implementation_report`, `assert_implements_document`, `harness_freeze_status`, `require_harness_freeze`, `freeze_block` | L/A through arbitrary rev/sources, supplied power, supplied pre-freeze runs and supplied membership inputs. |
| Launch/CLI | `launch_script`, `write_launch_script`, `main` | I/L/T through `python`, forwarded `**kwargs`, `--dir`, `--table-ledger`, `--no-results-canary`, and mode combinations. `--shards`, generic `--limit`, and `--n-boot` are substantially closed. |

Only six call sites use `assert_seam_allowed`: `run_fits`, `run_canary`, `merge`, `run_parity_oracle`, `run_table`, and `score_table` (`epl/evwiden.py:3051`, `3535`, `4865`, `5980`, `6343`, `6864`). The code implements a short call-site list, not the stated class.

## 3. Remaining bypass surface

- Keyword defaults remain deciding inputs on `estimand`, `verify`, `iv_c_verdict`, table builders, and evidence publication.
- Callable seams accept `functools.partial` even though the module does not name it.
- `Engine`, `TableRunner`, and `ParityRunner` are subclassable; the `Engine` production check uses ordinary mutable attributes and nominal class behavior.
- `score_table(mc=..., tallies=...)` bypasses evidence derivation.
- `runner`, `parity`, `fitter`, `engine`, and record/simulate callbacks survive on public paths.
- `merge` retains lifecycle/decision inputs.
- `--limit` is correctly restricted at the CLI, but public `fit_points`, `shard_points`, `run_fits`, `run_parity_oracle`, and `run_table` accept arbitrary populations.
- `construction_only` makes an ordinary object less capable initially, but `can_fit` is mutable and the structural “before import” claim is false (`epl/evwiden.py:1917-1965`, `2009-2027`).
- `read_only_store` has the stated TOCTOU and accepts an alternate root.
- Direct `simulate_arm` is nominally gated; `run_cell_arms` is not.
- The module pins BLAS environment values at import/launcher, but direct API callers do not uniformly recheck them.
- `write_launch_script(..., **kwargs)` forwards arbitrary `python` into the post-freeze production launcher (`epl/evwiden.py:9694-9705`, `9843-9862`).
- The guard over-refuses unrelated scratch work anywhere under the shared `paths.FIT_DIR`, broader than the document’s named evwiden artifacts (`epl/evwiden.py:2281-2285`, `2512-2532`).
- The prescribed step-2 scratch run cannot satisfy the existing sequence/location combination (`epl/evwiden.py:3779-3813`, `10238-10265`).

## 4. The stated and implemented closures are not the same

The text states a semantic class: any parameter with one of four effects (`reports/epl_widening_prereg_v2.md:551-566`, `2200-2228`). The code implements a guard called at six manually selected sites.

Forbidden by the sentence but permitted by code include:

- Injected `simulate`/`record` callbacks in `run_cell_arms`.
- Alternate Python implementation in the generated launcher.
- `manifest=False` and `require_manifest_complete=False` on preregistered evidence publication.
- Caller-selected freeze sources/revision.
- Supplied MC/tallies/unanimity.
- Arbitrary deciding population lists.
- Mutable frozen-module constants and class attributes.

Refused by code but not justified by the sentence:

- Unrelated scratch work anywhere under the entire shared `paths.FIT_DIR`.
- Unknown target/`None` even for harmless diagnostics, while semantically near-real renamed-key frames are permitted.

The closure round’s central claim is false.

# FEASIBILITY AND PASS 7

## 1. Investigator ruling

The investigator’s correction is sound: the operative conclusion is “the protected invocation will crash,” but this is not a regression from r1. It is a longstanding protected-runner capability limit.

Static checks support it:

- Cell ordering is season-major then cutoff-label-major (`epl/evwiden.py:5067-5082`), and protected constants begin at 2019/20 and MW0 (`epl/simretro.py:92-99`). Thus 2019/20 MW0 is first.
- `ParityRunner` and `run_parity_oracle` have no per-cell catch (`epl/evwiden.py:5923-5964`, `5967-6016`).
- `run_retro` catches refusals, records them, and continues (`epl/simretro.py:1122-1138`, `1204-1210`).
- The protected excluded-mass hard stop remains `0.02` and propagates from fixture construction (`epl/particles.py:588-620`, `643-667`; `epl/leaguesim.py:744-749`).
- The A5 argument is coherent: all 2023/24 adjustment rows are now verified (`epl/season/points_adjustments.jsonl:1-4`), making the reported MW3 failure reachable.
- No protected module changed in `1afd54d..4c01183`.

I had to accept the ledger row counts, omitted-cell identities, store identity, and measured excluded masses on the investigator/report’s word because their underlying `data/` artifacts are not Git objects.

## 2. The no-fit clock

Prospective authorization is a legitimate governance distinction in principle. A named, quarantined, control-only feasibility pass defined before execution need not reopen v1: v1’s two fits were unauthorized under v1’s own broader rule, and §8.1 still states that honestly (`reports/epl_widening_prereg_v2.md:1742-1760`).

But v2’s factual characterization is wrong. It exempts a pass said to be unable to produce a table cell or published number (`reports/epl_widening_prereg_v2.md:1781-1789`). `ParityRunner` returns a cell-shaped record containing key, digest, provisional state, constants, and timing (`epl/evwiden.py:5947-5964`), and `run_parity_oracle` writes those rows (`epl/evwiden.py:5995-6006`).

So the distinction can be legitimate only after the law honestly calls this a quarantined control-cell feasibility run. As written, it rescues the clock through a false premise.

## 3. Mechanical restriction

Nominally, `_feasibility_permits` recognizes only `"epl.evwiden.ParityRunner"` and an outside-repository quarantine (`epl/evwiden.py:2416-2426`). It does not directly unlock `Engine`, `TableRunner`, `run_fits`, `simulate_arm`, or the direct `leaguesim.simulate` call.

Mechanically, however, pass 7 is not restricted to the stated experiment:

- The context manager yields arbitrary caller code and sets `completed:true` whenever the body returns, even if it did nothing (`epl/evwiden.py:2430-2509`).
- It does not itself instantiate `ParityRunner`, derive the 35 cells, run `run_parity_oracle`, validate 35 unique keys, or discard outputs.
- `run_parity_oracle` accepts arbitrary cells, injected runner, resume state, and output path (`epl/evwiden.py:5967-6016`).
- `ParityRunner` accepts alternate matches/store/anchor/config and `require_verified_adjustments=False` (`epl/evwiden.py:5893-5921`).
- Permission is cached in `self.may_fit`; `ParityRunner.__call__` does not recheck the active context (`epl/evwiden.py:5905-5910`, `5923-5933`). A runner constructed inside the pass can be reused after it closes.
- `FEASIBILITY_SURFACES` and `_FEASIBILITY` are mutable module globals (`epl/evwiden.py:2408-2413`).
- “Once” depends only on ordinary file existence; deleting the record permits another run (`epl/evwiden.py:2471-2477`).
- The record is non-atomic, forgeable, not bound to the archive/store/config/harness digest or 35 output rows, and records no completed-cell census (`epl/evwiden.py:2494-2509`).
- The quarantine output is not deleted.
- There is no CLI action that executes pass 7 (`epl/evwiden.py:10008-10079`).

The mechanical restriction is not real.

## 4. Recommendation on when to freeze

Do not freeze with pass 7 unrun.

`freeze_block` merely prints the supplied/default enumeration and does not require a successful feasibility record (`epl/evwiden.py:9548-9653`). Once the freeze exists, the context manager refuses to open (`epl/evwiden.py:2454-2460`). Freezing first therefore makes the still-unanswered feasibility pass impossible while committing a design statically expected not to complete.

The correct ordering is:

1. Repair pass 7 so one atomic command itself executes the protected, default-configured `dc_native` path over exactly the frozen 35 cells and produces an input/commit-bound record.
2. Run it pre-freeze.
3. If it completes, record the exact outcome in §8.9, then render and paste the freeze block.
4. If it crashes, do not amend this design quietly; create a new preregistration.

That is option (a), but only after repairing the pass implementation.

## 5. The third option

Re-scoping to the 32 priceable cells is scientifically cleaner than pretending the protected runner covers 35, but it is a different preregistration.

Certain consequences:

- `EXPECTED_TABLE_CELLS` becomes 32.
- The protected/new-runner budget becomes 64 fits and 96 simulations, making the complete post-freeze budget 147 fits and 96 simulations.
- Exact treated/untouched and per-label treated counts must be recomputed from ignored pinned inputs; I cannot derive them independently from Git.
- MW0 and MW3 lose cells.
- MW6 retains seven cells and remains the only label currently stated to be treated everywhere, so the support half of §4.1 may survive, while the exact comparative census argument must be rewritten and re-audited (`reports/epl_widening_prereg_v2.md:928-959`).

The chosen feasibility option is reasonable only if implemented as a real one-shot falsification pass. The current implementation is worse than re-scoping because it can report success without answering the question.

# NEW DEFECTS

## P5-B1 — BLOCKING: pass 7 can succeed without running pass 7

An empty body under `parity_feasibility_pass` exits normally and receives `completed:true` (`epl/evwiden.py:2485-2501`). No 35-cell census, protected runner call, or output validation is required. This alone makes its result unusable as feasibility evidence.

## P5-B2 — BLOCKING: pass 7 does not confine its authority or evidence

The context permits arbitrary body code; an injected/subset/resumed oracle can be used; a constructed `ParityRunner` retains cached authority after closure; the ordinary record can be deleted or forged; and quarantine outputs are not discarded (`epl/evwiden.py:2416-2509`, `5893-5933`, `5967-6016`). The stated one-shot, protected, exact-35 capability is not implemented.

## P5-B3 — BLOCKING: the no-fit exemption rests on a false output claim

The document says the authorized pass cannot produce a table cell or published number (`reports/epl_widening_prereg_v2.md:1781-1789`). The implementation returns and writes per-cell parity records (`epl/evwiden.py:5947-5964`, `5995-6006`). This is a law/implementation mismatch in the very exception used to keep v2 valid.

## P5-B4 — BLOCKING: freeze does not depend on feasibility and then disables it

`freeze_block` accepts/prints an enumeration without checking `FEASIBILITY_RECORD` or its outcome (`epl/evwiden.py:9548-9653`). The feasibility context refuses after freeze (`epl/evwiden.py:2454-2460`). Current ordering can immortalize an unrun, possibly unrunnable design.

## P5-B5 — BLOCKING: `run_cell_arms` is an unguarded implementation-injection surface

The exported helper accepts arbitrary `simulate`, `record`, and books with no target or artifact inspection (`epl/evwiden.py:5563-5610`). A callback labeled “control” can perform treatment work before returning, so the helper’s visible call order does not mechanically establish the named scientific order. The default `TableRunner` path is correct; the new class-wide closure is not.

## P5-B6 — BLOCKING: the frozen launcher accepts an alternative implementation

`launch_script(..., python=...)` accepts an arbitrary interpreter/command, and `write_launch_script(..., **kwargs)` forwards it into the post-freeze production launcher (`epl/evwiden.py:9694-9705`, `9843-9862`). No `assert_seam_allowed` call inspects it. This is exactly a public parameter injecting an alternative implementation.

## P5-B7 — BLOCKING: official evidence publication can skip its manifest contract

`write_evidence` accepts `manifest=False` and `require_manifest_complete=False` even when `directory` is the preregistered evidence directory (`epl/evwiden.py:7790-7845`). It has no closure guard. A public production surface can therefore publish `widening.json` without the supposedly mandatory 52-member manifest.

## P5-B8 — BLOCKING: `--table-ledger` permits an outcome-conditioned second table run

The CLI accepts an arbitrary table ledger (`epl/evwiden.py:10066-10075`, `10117-10120`). The table branch checks only that step 4 precedes step 5, then performs the expensive run before attempting the write-once step-5 marker (`epl/evwiden.py:10317-10345`). After seeing the first table outcome, a caller can point to a new ledger and execute another table leg; the later marker conflict occurs after the new outcome exists.

## P5-I1 — IMPORTANT: the stated “whole experiment” budget omits pass 7

The document totals 153 fits/105 simulations (`reports/epl_widening_prereg_v2.md:582-603`). A completed feasibility pass adds another 35 fits and 35 simulations, giving 188/140 across the actual lifecycle. `_plan` likewise reports only the post-freeze 153/105 plan. The post-freeze arithmetic is internally correct; the “whole experiment” label is not.

## P5-I2 — IMPORTANT: the guard overreaches into unrelated work

`PREREGISTERED_DIRS` includes all `paths.FIT_DIR` (`epl/evwiden.py:2281-2285`). Any unrelated scratch audit below that shared directory is refused, even though the document closes the evwiden artifacts, not every fit artifact in the repository. This can block legitimate §8.2 audit work.

## P5-I3 — IMPORTANT: the first-fit isolation note overstates what the fixture proves

A function-scoped test fixture cannot establish whole-suite isolation against import-time, collection-time, session fixture, subprocess, or abrupt-process writes (`epl/tests/test_evwiden.py:81-134`). §8.9’s unconditional account is stronger than its evidence (`reports/epl_widening_prereg_v2.md:2396-2463`).

## P5-I4 — IMPORTANT: v2 is not clean enough for its no-post-fit-edit rule

Dropping the prose-amendment allowance is the correct narrowing: post-outcome corrections would create discretionary amendment channels. But v2 still contains false/stale claims about pass count, pass 4’s stopping point, whole-suite isolation, whole-experiment budget, and manifest count. Under §8.7 these become uncorrectable after the first real fit (`reports/epl_widening_prereg_v2.md:2331-2358`).

## P5-M1 — MINOR: stale “exactly eleven” manifest comment

The manifest is correctly enumerated as 52 paths in code, but `write_evidence` still says “exactly the eleven” (`epl/evwiden.py:7831-7843`).

## P5-M2 — MINOR: freeze-status condition count is stale

The docstring says four conditions while code adds condition five (`epl/evwiden.py:8192-8204`, `8302-8307`).

The post-freeze census and budget otherwise reconcile:

- 4 canary fits + 1 single-opening + 78 match-level + 35 protected + 35 new-runner = 153 fits.
- 35 protected simulations + 70 new-runner simulations = 105.
- `EXPECTED_TABLE_CELLS=35`, treated 16, untouched 19, and the stated per-label counts sum to 16 (`epl/evwiden.py:383-387`; `reports/epl_widening_prereg_v2.md:928-937`).
- `substantive_digest` carries `n_sims`, `n_particles`, seed, and full plan state including chunk size (`epl/evwiden.py:5458-5507`).

Those agreements do not cure the pass-7 omission or public bypasses.

# VERDICT

DO-NOT-FREEZE — 27 of the 43 identifier/numbered prior findings in Parts 1–2 remain STILL-OPEN. The L1–L18 obligations are regraded separately above. I found 8 new BLOCKING defects in Part 5.

Before a freeze is legitimate:

1. Make pass 7 an atomic, exact-35, protected-default, non-forgeable feasibility command; run it before freeze; record the outcome. A crash requires a new preregistration or fully re-derived 32-cell design.
2. Implement the closure semantically across every effect-bearing public surface, including callback, launcher, evidence-publication, table-ledger, mutable-constant, supplied-MC/tally, and lifecycle paths.
3. Make §8.4 step 2 executable and make all sequence/publication markers recomputed, complete, and non-forgeable.
4. Replace self-certified conformance/freeze evidence with exact L1–L18 independent checks and correct the remaining text before the no-post-fit-edit regime starts.

Do not render or paste the freeze block, and do not begin the first real fit.

