# WHAT I CHECKED

I inspected Git objects at commit `11159b1ef2688fa98685bc759aa8c8f5824bfe0d` only. I did not read repository working-tree paths, import repository code, execute tests, or execute the harness. The permitted `/private/tmp/...` case-history reports were read separately and are not repository state. There was no deviation from the pin.

The pinned blobs matched the supplied identities and sizes:

- `reports/epl_widening_prereg_v3.md`: `ebff2eff4195becb340ef519513c693b69bae352`, 207,116 bytes.
- `reports/epl_widening_prereg_v2.md`: `494a79c3efe7c4bc5c0309c28200d24254a7d19f`, 182,328 bytes.
- `epl/evwiden.py`: `83c7cba8bb84f6dfd84921f64148024d1162b665`, 621,469 bytes.
- `epl/tests/test_evwiden.py`: `970515a463d3f303d8d5ae74cb178f2c7359490d`, 356,564 bytes.

I read the sixth-pass closure review first and in full, then the other ten record items, v3, v2, the harness, the tests, relevant protected runners, all seven v3 commits collectively and individually, the v2-closing diff, and the historical blobs needed to establish when MW6 was selected.

Because `/data/` is ignored (`.gitignore:14-16`), I could not independently verify:

- that the pass-7 JSON exists with the reported 18,128 bytes and SHA-256;
- its 35 attempts, three unpriceable cells, masses, exception classes, timestamps, run commit, quarantine deletion, or store invariance;
- the claimed absence of other fit/simulation artifacts;
- the conformance artifact or its reported contents;
- 1,410 passed / 1 skipped, 320 tests in `test_evwiden.py`, `LOCK VALID`, the clean working tree, or the 8,896-byte rendered freeze block.

Those remain owner/test/agent assertions. Git does bind the expected census file to an exact SHA, size, and exact 32/3 key sets, but does not contain the evidence bytes or an archival locator (`reports/epl_widening_prereg_v3.md:67-95`; `epl/evwiden.py:2539-2570,10817-10870`).

The repeated macOS `/tmp/xcrun_db-*` warnings were caused by the read-only sandbox. They did not alter the returned Git objects.

<details>
<summary>Deduplicated exact Git-command log</summary>

Repeated `nl`/`sed` line slicing is deduplicated to the exact underlying Git invocation.

```text
git rev-parse '11159b1^{commit}'
git rev-parse '11159b1:epl/evwiden.py'
git rev-parse '11159b1:reports/epl_widening_prereg_v3.md'
git rev-parse '11159b1:epl/tests/test_evwiden.py'
git cat-file -t 11159b1
git cat-file -s '11159b1:epl/evwiden.py'
git cat-file -s '11159b1:reports/epl_widening_prereg_v3.md'
git cat-file -s '11159b1:epl/tests/test_evwiden.py'
git show --no-patch --format=fuller 11159b1
git ls-tree -l 11159b1 -- reports/epl_widening_prereg_v3.md reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git ls-tree -r --name-only 11159b1 -- data
git ls-tree -r --name-only 11159b1 -- reports/evidence
git ls-tree 11159b1 data/epl/fit/evwiden_first_real_fit.json data/epl/fit/evwiden_first_fit_witness.jsonl
git show 11159b1:reports/epl_widening_prereg_v3.md
git show 11159b1:reports/epl_widening_prereg_v2.md
git show 11159b1:epl/evwiden.py
git show 11159b1:epl/tests/test_evwiden.py
git show 11159b1:epl/walkforward.py
git show 11159b1:epl/simretro.py
git show 11159b1:src/wcmodel/data/store.py
git show 11159b1:.gitignore
git log --format='%H %s' ed77df5..11159b1
git log --oneline --no-decorate ed77df5..11159b1
git log --oneline --reverse ed77df5..11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md reports/epl_widening_prereg_v2.md
git log --format='%H %s' -- reports/epl_widening_prereg_v2.md
git log --oneline -S'FIRST_FIT_WITNESS' ed77df5..11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md
git diff-tree --no-commit-id --name-status -r ed77df5 11159b1
git diff-tree --no-commit-id --name-status -r b7ef416 226065c 187d6da 258e5b9 eec8bd4 21d496f 11159b1 -- reports/epl_widening_prereg_v3.md reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git diff-tree --no-commit-id -p --unified=3 78a2302 -- reports/epl_widening_prereg_v2.md
git diff-tree --no-commit-id -p --unified=3 b16875a -- reports/epl_widening_prereg_v2.md
git diff --stat ed77df5 11159b1 -- reports/epl_widening_prereg_v3.md reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git diff --unified=3 ed77df5 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md reports/epl_widening_prereg_v2.md
git diff --unified=80 ed77df5 11159b1 -- reports/epl_widening_prereg_v2.md
git diff --numstat ed77df5 11159b1 -- reports/epl_widening_prereg_v2.md
git diff --name-status ed77df5 11159b1 -- reports/epl_widening_prereg_v2.md
git diff --unified=20 226065c 187d6da -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md
git diff --unified=20 187d6da 258e5b9 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md
git diff 187d6da^ 187d6da -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md
git diff 187d6da 258e5b9 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md
git diff 187d6da 11159b1 -- epl/evwiden.py
git ls-tree -r --name-only 1b79cc5 -- reports
git grep -n -E 'deciding horizon|MW6' 1b79cc5 -- reports/epl_widening_prereg.md reports/epl_widening_prereg_v1.md reports/epl_widening_prereg_v2.md
git grep -n -E 'deciding horizon|MW6' f454041 -- reports
git grep -n -E 'deciding horizon|MW6' 1afd54d -- reports/epl_widening_prereg_v2.md
git grep -n -E 'EXPECTED_TABLE|EXPECTED_TREATED|EXPECTED_CELL|UNTOUCHED|EXCLUDED_CELL|EXCLUDED_CELLS|MANIFEST_PATHS|parity_oracle|TABLE_TOLERANCE|POINT_GATE_LABELS|MW6|182|131|147|96|188|140|priceable|unpriceable' 11159b1 -- epl/evwiden.py
git grep -n -E 'EXPECTED_TABLE|EXPECTED_TREATED|EXPECTED_CELL|UNTOUCHED|EXCLUDED_CELL|EXCLUDED_CELLS|MANIFEST_PATHS|parity_oracle|TABLE_TOLERANCE|POINT_GATE_LABELS|MW6|182|131|147|96|188|140|priceable|unpriceable' 11159b1 -- epl/tests/test_evwiden.py
git grep -n -E '182|131|147|96|188|140|32|35|15|17|MW0|MW3|MW6|MW10|MW19|0\.00042667|2\.13|priceable|unpriceable|§2\.4|§4\.1|§4\.3|§5\.3|§8\.1|§8\.9|excluded' 11159b1 -- reports/epl_widening_prereg_v3.md
git grep -n -i -E '35[- ]cell|thirty[- ]five|all 35|35 rows|19[- ]untouched|nineteen[- ]untouched|16 changed|sixteen changed|16 treated|sixteen treated|2\.19x|2\.19×|52[- ]member|52 paths|outside the 52|all thirty[- ]two tallies|all 32 tallies|32 tallies' 11159b1 -- reports/epl_widening_prereg_v3.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E '^(__all__|[A-Z][A-Z0-9_]*\s*=|def |class )|dcfit\.fit_epl|leaguesim\.simulate|assert_seam_allowed|require_sequence|claim_sequence_step|score_table|run_cell_arms|run_table|run_parity_oracle|working_tree_bytes|_cli_arguments|EXCLUDED_CELLS|FEASIBILITY|parity_feasibility' 11159b1 -- epl/evwiden.py
git grep -n -E 'closure|public parameter|alternative implementation|truncate|frozen constant|caller|EXCLUDED_CELLS|feasibility|pass 7|run_cell_arms|append-only|gitignored|census record|reader' 11159b1 -- reports/epl_widening_prereg_v3.md
git grep -n -E 'FIRST_FIT|first_fit|claim_sequence_step|require_sequence|run_table|run_parity_oracle|def merge|def score_table|working_tree_bytes|_cli_arguments|write_launch_script|read_only_store|PREREGISTERED|WRITES|FEASIBILITY|feasibility|table-ledger|script' 11159b1 -- epl/evwiden.py reports/epl_widening_prereg_v3.md epl/tests/test_evwiden.py
git grep -n -E 'parity_feasibility_pass|parity_feasibility_census|FEASIBILITY_SURFACES|_FEASIBILITY|parity-feasibility' 11159b1 -- epl/evwiden.py
git grep -n 'FEASIBILITY_RECORD' 11159b1 -- epl/evwiden.py
git grep -n 'record_first_real_fit' 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'CONFORMANCE_ARTIFACT|pytest_sessionfinish|pytest_runtest|conformance.json|write.*conformance' 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'n_particles|1,000 particles|1000 particles|particle count' 11159b1 -- reports/epl_widening_prereg_v3.md epl/evwiden.py
git grep -n -E '^_[A-Z][A-Z0-9_]*\s*=|_POWER_RUN|_IMPLEMENTATION_REPORT|CACHE|cached' 11159b1 -- epl/evwiden.py
git grep -n -E 'IMPLEMENTATION_REPORT|CONFORMANCE_CACHE|memo|cache' 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'sampler_digest.*provisional|run_cell_arms|paired.arm sequence|TableRunner.*level|later input channel|A1' 11159b1 -- epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md
git grep -n -E 'P5-B5|P5-B6|P5-B7|NEW-B1|NEW-B2|NEW-B3|NEW-B4|NEW-B5|NEW-B8|run_cell_arms|LAUNCH_PYTHON|single guard|closure principle|ambiguous middle|synthetic ancestry|public parameter' 11159b1 -- reports/epl_widening_prereg_v3.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E '^(def|class) ' 11159b1 -- epl/evwiden.py
git grep -n -E 'first post-freeze act|nothing else|between them|five-step|Only after|may run|run out of order|every fit|anywhere' 11159b1 -- reports/epl_widening_prereg_v3.md
git grep -n -E 'run_fits.*sequence|Engine\.fit.*sequence|TableRunner.*require_sequence|ParityRunner.*require_sequence|simulate_arm.*require_sequence|run_canary.*require_sequence|claim_sequence_step|second table|step 5.*claim' 11159b1 -- epl/tests/test_evwiden.py epl/evwiden.py
git grep -n -E '\b35\b|THIRTY-FIVE|thirty-five|\b16 treated\b|\b19 untouched\b|52-member|schema 2|epl-evwiden-2|v2 and only v2|2\.19' 11159b1 -- reports/epl_widening_prereg_v3.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'working_tree_bytes|_cli_arguments' 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'WRITES|PREREGISTERED_DIRS|preregistered_files|EVWIDEN_|TABLE_|EVIDENCE_|CONFORMANCE_ARTIFACT|FIRST_FIT' 11159b1 -- epl/tests/test_evwiden.py
git grep -n -E '\*\*kwargs|Callable|runner:|fitter:|engine:|store=|anchor=|config:|harness_frozen|require_canaries|check_implementation|require_parity|expected:' 11159b1 -- epl/evwiden.py
git grep -n -E 'table ledger|table_cells\.jsonl|ledger is therefore|resolved from|names nothing|not a parameter' 11159b1 -- reports/epl_widening_prereg_v3.md
git grep -n -E 'record_first_real_fit\(|first_fit_state\(|first_fit_record\(|witness_lines\(|assert_no_hashed_file_moved\(|harness_freeze_status\(|require_harness_freeze\(|assert_may_fit\(|dcfit\.fit_epl|leaguesim\.simulate' 11159b1 -- epl/evwiden.py
git grep -n -E '^def _frozen_now|^def git_committed_bytes|^def git_blob_id|^def git_head|^def sha256_file' 11159b1 -- epl/evwiden.py
git grep -n -E 'record\[.?commit|FIRST_FIT.*commit|first.fit.*commit|prereg_blob.*witness|witness.*harness|witness.*commit|same identity fields' 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md
git grep -n '^def freeze_block' 11159b1 -- epl/evwiden.py
git grep -n 'require_harness_freeze' 11159b1 -- epl/evwiden.py
git grep -n -E 'ParityRunner\(|runner\(cell|parity_runner' 11159b1 -- epl/evwiden.py
git grep -n -E '^def point_in_time_canary|def _forecasts' 11159b1 -- epl/walkforward.py
git grep -n -E '^class ArchiveRunner|def __call__' 11159b1 -- epl/simretro.py
git grep -n -E 'ParityRunner.*may_fit|ParityRunner.*freeze|re-?check.*Parity|cached.*freeze|working_tree_bytes.*Parity' 11159b1 -- epl/tests/test_evwiden.py reports/epl_widening_prereg_v3.md epl/evwiden.py
git grep -n -E '_run_all_canaries\(|run_canary\(' 11159b1 -- epl/evwiden.py
git grep -n 'run_canary' 11159b1 -- epl/tests/test_evwiden.py
git grep -n -E 'prereg_bytes_match_blob|uncommitted.*prereg|CURRENT bytes|dirty.*prereg' 11159b1 -- epl/tests/test_evwiden.py
git grep -n -E '^def membership_digests|assert_table_census\(' 11159b1 -- epl/evwiden.py
git grep -n -E '^def freeze_block|freeze_block\(' 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E '^def _plan|_plan\(|post.freeze|lifecycle|planned_fits|planned_sim|n_fits|n_sim' 11159b1 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'feasibility_status\(|assert_feasibility_permits_a_freeze\(|_frozen_table_cell_keys\(' 11159b1 -- epl/evwiden.py
git grep -n -i -E 'crash|resume|retry|restart|interruption|in.flight|cell in flight' 11159b1 -- reports/epl_widening_prereg_v3.md epl/evwiden.py
git grep -n -E 'load_tallies\(|paired_mc_bootstrap\(|unanimity\(' 11159b1 -- epl/evwiden.py
git grep -n '_guard_ledger_location' 11159b1 -- epl/evwiden.py
git grep -n -E 'closure principle|semantic class|runtime surface|TableRunner|table-ledger|fixed table_cells|not a parameter|five-step|first post-freeze|scratch directory|own copy|working_tree_bytes|current bytes|all decision-relevant|all calls|public' 11159b1 -- reports/epl_widening_prereg_v3.md
```

</details>

# FINDING-BY-FINDING

There are 41 unique prior identifiers across the two inventories. Repeated `NB6`–`NB8` entries are ruled again below for completeness but counted once. Twenty-three unique prior findings remain open.

## Part 1(a): residual list

### P5-B8 — STILL-OPEN

The CLI does claim step 5 before simulating (`epl/evwiden.py:11688-11700`), but the claimed closure is false.

`claim_sequence_step` performs an unlocked read/check followed by ordinary `write_text`; it is neither atomic nor exclusive, so concurrent callers can both pass (`epl/evwiden.py:3898-3934,3992-4012`). Exported `run_table` and `run_parity_oracle` only require the predecessor marker and never claim their current step (`epl/evwiden.py:6461-6478,6817-6856`). `run_table` still accepts `ledger_path`, and CLI `--dir` still selects a different ledger (`epl/evwiden.py:6817-6847,11437-11448`), contradicting the fixed-ledger law (`reports/epl_widening_prereg_v3.md:2391-2413`).

The claim also makes the promised crash recovery impossible: an open `complete:false` claim permanently refuses the official retry, while §7.2 promises resumability and `run_table` says a crash costs only the in-flight cell (`reports/epl_widening_prereg_v3.md:1775-1795`; `epl/evwiden.py:3914-3932,6836-6839`). The text and harness cannot simultaneously provide once-only execution and the promised resumption.

### B6 — STILL-OPEN

The new witness is an internally hash-chained JSONL file, but both it and the record are ordinary, deletable files under ignored `/data/` (`epl/evwiden.py:2381-2399,2781-2813`; `.gitignore:14-16`). Deleting both returns `pre_first_fit` (`epl/evwiden.py:2841-2844`). The document itself concedes that both can be deleted (`reports/epl_widening_prereg_v3.md:2758-2772`), contradicting the absolute ratchet claim at `2983-2985`.

The pairing is weaker than the text promises: code compares only `at` and `where`, not `schema`, `commit`, `prereg`, `prereg_blob`, or `harness` (`epl/evwiden.py:2861-2869`; document `2742-2754`). A rewritten record with old `at`/`where` can therefore launder changed code or preregistration bytes.

Witness-only state is merely unreadable/refused, not a genuine post-fit state. Worse, `harness_freeze_status` reads the witness only if the record exists; record-absent/witness-present yields `first_fit_ok=None`, which still satisfies the frozen predicate (`epl/evwiden.py:8969-8979,9019-9022`).

### NB5 — STILL-OPEN

NB5’s deletion-reset concern remains for the same reason. The chain has no non-deletable or externally anchored head. Full deletion or empty truncation resets `first_fit_state` to pre-fit (`epl/evwiden.py:2781-2813,2841-2844`), contrary to the claimed deletion ratchet (`reports/epl_widening_prereg_v3.md:2734-2772`).

### N-RH-FIRST-ACT — STILL-OPEN

The document says step 2’s scratch directory carries its own copy of step 1’s canary (`reports/epl_widening_prereg_v3.md:2311-2324`). The launcher only creates the scratch directory and invokes `--run --limit 1 --dir "$SCRATCH"`; it never copies the canary (`epl/evwiden.py:11065-11069`). Main calls `require_run_preconditions(directory=scratch)`, which looks for `scratch/canary.json` and refuses its absence (`epl/evwiden.py:4135-4141,11587-11589`).

The committed test merely source-checks the generated command and never executes the sequence or supplies the missing copy (`epl/tests/test_evwiden.py:7068-7112`). Step 2 is not executable in sequence.

### NB6 — STILL-OPEN

The direct APIs now call `require_sequence`, and a marker without `complete:true` does not unlock the successor (`epl/evwiden.py:3836-3843,4038-4104,5193-5259,6461-6478,6817-6855`).

The claimed product-digest revalidation is false. `_sequence_marker_state` recomputes a digest of the marker’s own embedded `produced` dictionary, not the current bytes of the named product (`epl/evwiden.py:3852-3866`). Product deletion or mutation therefore leaves the marker valid. Step 5’s marker does not even carry a ledger SHA, only path/count/check metadata (`epl/evwiden.py:11688-11704`).

### NB7 — RESOLVED

`score_table` no longer accepts `tallies=` or `mc=` and derives the tallies, bootstrap, and unanimity object internally (`epl/evwiden.py:7367-7371,7489-7514`). The named scratch-path injection is closed.

This does not resolve the separate wrong-population and fabricated-`scored` routes under `NEW-B3`.

### NB8 — STILL-OPEN

The renderer no longer computes an artifact for itself, but the new artifact is not independent evidence.

`write_conformance_artifact` is exported and accepts arbitrary outcomes, then stamps current harness hashes around them (`epl/evwiden.py:182-207,9412-9437`). The eighteen pytest wrappers merely call `conformance_row`, assert its returned `ok`, and later write their own passed IDs (`epl/tests/test_evwiden.py:7301-7325,7365-7371`). `conformance_row` memoizes one `implementation_report()` execution for all eighteen rows (`epl/evwiden.py:9381-9404`).

A committed test explicitly manufactures `{L1 … L18: "passed"}`, writes it through the public writer, and renders an accepted block (`epl/tests/test_evwiden.py:7365-7387`). That disproves the text’s claim that the harness cannot mark rows green from something it computed (`reports/epl_widening_prereg_v3.md:2480-2524`).

### A1 — STILL-OPEN

The prose moved A1 to the paired-arm sequence (`reports/epl_widening_prereg_v3.md:960-973`), but the conformance route still drives `_conf_runner` and `run_cell_arms`, not the actual `TableRunner.__call__` path (`epl/evwiden.py:6158-6246,9201-9291,9780-9817`). A later channel inserted between the helper and `TableRunner` can remain green.

Removing `run_cell_arms` from `__all__` changes wildcard import behavior only. It remains a callable module attribute accepting injected simulation/record/book functions (`epl/evwiden.py:6027-6098`).

### IMP-FIRST-FIT-TIMESTAMP — STILL-OPEN

The document says the timestamp is recorded immediately before sampler entry and that nothing which can raise intervenes (`reports/epl_widening_prereg_v3.md:2704-2727`). The code still records an attempt:

- `run_canary` records before a wrapper that imports, loads, constructs, and copies data before its first fit (`epl/evwiden.py:3764-3772`; `epl/walkforward.py:461-484`).
- `ParityRunner` records before `ArchiveRunner` derives season state (`epl/evwiden.py:6420-6427`; `epl/simretro.py:534-540`).
- `simulate_arm` records a “first real fit” before a simulation that performs no fit (`epl/evwiden.py:5754-5765`).

The AST test omits `run_canary` and treats `self._runner(` as the sampler (`epl/tests/test_evwiden.py:6992-7006`).

### IMP-POST-FIT-PROSE — STILL-OPEN

The default helper correctly reads current bytes and compares them with the committed preregistration blob (`epl/evwiden.py:8751-8795,8840-8862`). That improves the normal guard.

It is still not enforced on every later fit. `ParityRunner.__init__` caches `assert_may_fit` once, and one instance executes all 32 cells without rereading the current document, witness, or record (`epl/evwiden.py:6400-6404,6417-6427,6483-6503`). That contradicts the every-fit promise (`reports/epl_widening_prereg_v3.md:2711-2714,2811-2819`).

In addition, `working_tree_bytes` is a rebindable module global directly supplying the lifecycle verdict. Tests monkeypatch it (`epl/tests/test_evwiden.py:4278-4305,5768-5776`). Even if arbitrary Python rebinding were declared out of scope, the cached parity approval independently leaves this finding open.

### IMP-PREFREEZE-SCRIPT — RESOLVED

The document requires refusal before freeze and permits one fixed target afterward (`reports/epl_widening_prereg_v3.md:2101-2113`). `write_launch_script` checks the freeze state before any write, refuses every prefreeze target, and after freeze permits only `EVWIDEN_DIR` (`epl/evwiden.py:11141-11159`).

The separate mutable-interpreter issue remains under `P5-B6`.

### MIN-READ-ONLY-STORE-TOCTOU — STILL-OPEN

The law requires an absent store to remain absent (`reports/epl_widening_prereg_v3.md:2129-2148`). `read_only_store` snapshots the root, constructs `BitemporalStore`, and only afterward checks for mutation (`epl/evwiden.py:5529-5547`). The constructor can create the directory before the mismatch is raised (`src/wcmodel/data/store.py:20-23`). The test checks the exception but not removal (`epl/tests/test_evwiden.py:7238-7265`).

### P5-I2 — STILL-OPEN

The scope is narrower than all of `paths.FIT_DIR`, but still includes the entire shared `reports/evidence` directory (`epl/evwiden.py:2420-2421,2617-2635`). That tree contains unrelated anchoring/freshness/README material, so unrelated evidence work is over-refused.

The prose says “this experiment’s artifacts” and “four directories plus two individual files,” while code enumerates five individual files (`reports/epl_widening_prereg_v3.md:2583-2596`; `epl/evwiden.py:2428-2431`). Both scope accuracy and prose fail.

### P5-B2 — RESOLVED

The mutable feasibility permission/pass surface and executable feasibility runner are gone. The remaining reader pins exact SHA-256, size, completion, 35 attempts, and exact 32 priceable/3 unpriceable key sets; absence or mismatch refuses (`epl/evwiden.py:2553-2570,10817-10870`). Freeze renders the census identity and counts (`epl/evwiden.py:10651-10655,10752-10764`).

This resolves the named mutable-authority defect. It does not prove execution or provenance: the ignored bytes remain owner-supplied, and the repository cannot inspect or recover them. The prose overstates repository-only checkability at `reports/epl_widening_prereg_v3.md:2187-2191`.

## Part 1(b): remaining sixth-pass inventory

### B3 — RESOLVED

The estimand constants and interpretation are frozen in the document (`reports/epl_widening_prereg_v3.md:656-671`). `estimand` refuses overrides, and iv-c implements the stated strict rule (`epl/evwiden.py:4359-4383,7201-7223`). Broader mutable/public closure defects are separately ruled under `NEW-B1`.

### I6 — STILL-OPEN

The evidence contract says every missing or disagreeing published value refuses (`reports/epl_widening_prereg_v3.md:3134-3140`). `verify` checks only a selected subset of verdict, SE, fired-boundary, and dissent fields, often conditionally; population and several gate subfields can be omitted without refusal (`epl/evwiden.py:8518-8567`). The implementation remains weaker than the text.

### N-FREEZE-COMMIT — RESOLVED

The guard now requires the supplied revision to equal HEAD and the source set to contain v3 and the harness exactly (`epl/evwiden.py:8751-8781`; `reports/epl_widening_prereg_v3.md:2645-2664`). The prior arbitrary-revision/source-set hole is closed.

### NB6 — STILL-OPEN

As ruled above: predecessor checks improved, but the product digest hashes marker metadata instead of product bytes, and direct expensive paths never claim their current step (`epl/evwiden.py:3852-3866,6461-6478,6817-6855`).

### NB7 — RESOLVED

As ruled above: `score_table` has no `tallies=` or `mc=` seam and derives both (`epl/evwiden.py:7367-7371,7489-7514`).

### NB8 — STILL-OPEN

As ruled above: the artifact is forgeable through the exported writer, and all eighteen tests read one self-authored implementation report (`epl/evwiden.py:9381-9437`; `epl/tests/test_evwiden.py:7301-7387`).

### NEW-B1 — STILL-OPEN

The document states a semantic closure class (`reports/epl_widening_prereg_v3.md:2537-2555`); the code still implements a hand-picked call-site list.

Open decision/effect surfaces include:

- caller-controlled seasons, labels, cutoffs, checking, and store/config inputs in `table_cutoffs`/`table_cells` (`epl/evwiden.py:5434-5464,5551-5605`);
- arbitrary cell sequences in `run_parity_oracle`/`run_table` (`6461-6517,6817-6868`);
- arbitrary scored objects in `table_gate` and arbitrary PASS tables in `adoption` (`5043-5097,7589-7725`);
- `simulate_arm(n_particles=…)` (`5723-5765`);
- arbitrary points and subclassable engines in `run_fits` (`3227-3312`);
- injected runners/stores/anchors/configs in `Engine`, `TableRunner`, and `ParityRunner`;
- mutable `LAUNCH_PYTHON`, `working_tree_bytes`, `_POWER_RUN`, and other module globals.

The closure is still a list, not the sentence.

### NEW-B2 — STILL-OPEN

Provenance classification still admits an ambiguous middle: missing caches/bad columns become `unknown`, and renamed/copied real arrays can become “synthetic” (`epl/evwiden.py:2433-2508,2638-2764`).

There is also a concrete real-fit bypass. `run_canary` guards caller-supplied synthetic `played`/`corpus`, then the default runner ignores those values and calls `point_in_time_canary()` without arguments; that function loads real baseline data and performs four fits (`epl/evwiden.py:3759-3772`; `epl/walkforward.py:450-495`). Prefreeze synthetic metadata can therefore authorize real fitting; postfreeze `played=None` is classified non-real and can avoid the first-fit witness.

### NEW-B3 — STILL-OPEN

Although direct `tallies=`/`mc=` parameters are gone, the broader outcome-injection path remains:

- `unanimity_is_valid` checks self-consistency but not the frozen population; 200 copies of one verdict can pass (`epl/evwiden.py:7235-7289`).
- `table_gate` accepts any supplied `scored` object (`7589-7725`).
- `adoption` trusts a supplied PASS table (`5043-5097`).
- `merge(table=...)` omits `table` from its guarded seams and forwards it to the decision (`5193-5239,5357-5361`).

This contradicts the no-caller-supplied-decision-evidence clause (`reports/epl_widening_prereg_v3.md:2597-2608`).

### NEW-B4 — STILL-OPEN

Explicit freeze-state parameters were narrowed, but `merge(harness_frozen=True, require_canaries=False, directory=<scratch>)` can pass its guard before pinned data are loaded, then write the fixed production output (`epl/evwiden.py:5193-5259,5251-5284,5394-5397`).

`freeze_block` also still accepts caller `corpus`, `played`, `ledger`, and `table`, contrary to “no caller-supplied substitute” (`reports/epl_widening_prereg_v3.md:2202-2204`; `epl/evwiden.py:10603-10607`).

### NEW-B5 — RESOLVED

Construction-only `Engine` behavior is explicitly specified (`reports/epl_widening_prereg_v3.md:2042-2067`). The implementation refuses fitting before importing/calling `dcfit`, and construction alone is non-fitting (`epl/evwiden.py:2011-2059,2103-2121,2291-2361`).

### NEW-B6 — RESOLVED

Conditional on the owner-reported pass-7 facts, the protected path was actually enumerated, v2 was defeated, and v3’s freeze gate requires the exact resulting 32/3 census (`reports/epl_widening_prereg_v3.md:238-318`; `epl/evwiden.py:10817-10870`). The pass execution surface is absent from v3.

The ignored record’s provenance remains unverified, but that is not the original feasibility-regression finding.

### NEW-B8 — STILL-OPEN

Only `CanaryFailed` is durably recorded on the CLI canary path; sibling `EvidenceCanaryFailed`, unexpected exceptions, and process crashes can leave no failed marker (`epl/evwiden.py:11508-11550`). Direct `run_canary` is not current-step claimed and remains repeatable. The document’s durable no-file-drawer behavior is therefore incomplete (`reports/epl_widening_prereg_v3.md:2379-2417`).

### MIN-CONTINUITY-AND-STALE-PROSE — STILL-OPEN

Current-world v2 values remain in document, code, emitted field names, errors, docstrings, and committed fixtures. Examples include:

- document: 19 untouched (`reports/epl_widening_prereg_v3.md:1027-1032`), 32 instead of 30 tallies (`1489`), and 52 instead of 49 manifest paths (`3130`);
- code: 16/2.19× (`epl/evwiden.py:325-331`), 35/19 parity descriptions (`6362-6381,6641-6673`), 35-cell emitted keys (`7555-7566`), and 52-path descriptions (`7805-7815,8391-8394,8600-8601`);
- tests: old 19/35/52 fixtures or prose (`epl/tests/test_evwiden.py:2536-2538,2906-2911,3092-3098,6643`).

### P5-B1 — RESOLVED

Conditional on the owner’s word, pass 7 executed all 35 cells and completed its census. The empty-body context-manager surface is gone; v3 contains only the exact census reader (`epl/evwiden.py:10817-10870`).

### P5-B3 — RESOLVED

v3 accurately classifies pass 7 as protected-control capability history, not an arm comparison or estimand (`reports/epl_widening_prereg_v3.md:1897-1959`). The code consumes it only as an exact priceability census (`epl/evwiden.py:10817-10870`).

### P5-B4 — RESOLVED

The freeze now depends on the exact pinned census and no feasibility pass remains available (`epl/evwiden.py:10651-10655,10817-10916`). A missing, altered, incomplete, 35-priceable, or wrong-key record refuses.

### P5-B5 — STILL-OPEN

`run_cell_arms` remains a module-level callable accepting injected simulators, recorders, books, and parity objects (`epl/evwiden.py:6027-6098`). Its own docstring admits that a callback labelled “control” can do treatment work (`6052-6065`). Removal from `__all__` does not close explicit access, and its self-check cannot attest what injected callbacks did. The paired-arm law is at `reports/epl_widening_prereg_v3.md:960-973`.

### P5-B6 — STILL-OPEN

The user-facing interpreter parameter was removed, but `LAUNCH_PYTHON` is a mutable module global interpolated into the script (`epl/evwiden.py:10943-10949,11016`). `write_launch_script` never validates it (`11115-11164`). The fixed-interpreter promise remains bypassable without changing hashed source (`reports/epl_widening_prereg_v3.md:2101-2113`).

### P5-B7 — RESOLVED

`write_evidence` performs its official-target/frozen-manifest checks before writing and refuses the preregistered destination when requirements are disabled (`epl/evwiden.py:8338-8368,8391-8407`). The prior write-before-refusal route is closed.

### P5-I1 — RESOLVED

The original omission of pass 7 is fixed. `_plan` and §2.4 correctly give 147/96 postfreeze and 182/131 after adding pass 7 (`reports/epl_widening_prereg_v3.md:687-710`; `epl/evwiden.py:11185-11232`).

The phrase “whole lifecycle, this lineage” creates a new, narrower budget defect because it omits v1’s two real fits; that is separately graded below.

### P5-I3 — RESOLVED

The document now confines the fixture claim to the specific tested contracts and does not claim the reported entire-suite result as Git-verifiable evidence (`reports/epl_widening_prereg_v3.md:2885-2892`). The reported 1,410/1 and ignored-artifact absence remain owner assertions, but the previous prose overclaim is removed.

### P5-I4 — STILL-OPEN

The stale current-world clauses listed above would become immutable after the first fit under §8.7 (`reports/epl_widening_prereg_v3.md:2742-2830`). v3 is not clean enough for its own no-post-fit-edit rule.

### P5-M1 — STILL-OPEN

The old “eleven” count changed, but count drift remains: the active manifest has 49 paths, while document/code still say 52 (`reports/epl_widening_prereg_v3.md:3130`; `epl/evwiden.py:7805-7815,8391-8394,8600-8601`). The executable tuple is 12 fixed + 32 tallies + 5 markers = 49 (`epl/evwiden.py:7816-7837`).

### P5-M2 — RESOLVED

The freeze-status docstring now says five conditions (`epl/evwiden.py:8808-8823`). Remaining v2/schema-2 names at `8812-8819` are stale-prose defects, not the original count error.

### IN-TREE-6 — RESOLVED

v3 explicitly owns the conformance artifact and narrows the fixture claims (`reports/epl_widening_prereg_v3.md:2480-2524,2885-2902`). This resolves the original undocumented-evidence issue, although NB8 shows the new evidence design is unsound.

### IN-TREE-7 — RESOLVED

This is the construction-versus-fit issue ruled under `NEW-B5`; the refusal occurs before `dcfit.fit_epl` (`epl/evwiden.py:2011-2059,2103-2121`).

### IN-TREE-10 — RESOLVED

The freeze guard now fixes HEAD and the exact v3/harness source set (`epl/evwiden.py:8751-8781`).

### IN-TREE-11 — RESOLVED

Narrowly, the original purely existential L11/L12 rows were replaced with helper-level behavioral scenarios and AST linkage checks (`epl/evwiden.py:10191-10309`). A1 and the weak AST/linkage evidence remain separately open.

### IN-TREE-12 — STILL-OPEN

The scratch merge/fixed-output route remains. `merge` can be called with caller-attested freeze/canary booleans at a scratch target, passes before loading pinned data, and writes production `widening.json` (`epl/evwiden.py:5193-5259,5251-5284,5394-5397`). Its L7 probe instead uses `target=None`, which guarantees refusal and misses the actual scratch route (`epl/evwiden.py:9873-9890`).

# THE CENSUS TRANSPLANT

## 1. Every constant

The active central constants are correct:

| Quantity | Required | Document | Harness | Ruling |
|---|---:|---|---|---|
| cells | 32 | `reports/epl_widening_prereg_v3.md:306-318` | `epl/evwiden.py:435-441` | correct |
| treated | 15 | same | `epl/evwiden.py:439-441` | correct |
| untouched | 17 | same | derived as 32−15 at `439-441` | correct |
| cells by label | 5/6/7/7/7 | `306-318` | `350-356` | correct |
| treated by label | 2/2/7/4/0 | `306-318` | `346-348` | correct |
| exclusions | exact three | `268-277` | `358-377` | correct |
| deciding tallies | 30 | `1337-1351` | 15 cells × 2 arms at `7489-7514` | correct |
| parity completion | 32 | `306-318` | `6638-6687` | correct |
| manifest paths | 49 | evidence schedule | `7816-7837` | correct executable value |
| postfreeze budget | 147/96 | `687-710` | `_plan` at `11185-11232` | correct |
| lifecycle incl. pass 7 | 182/131 | `687-710` | `_plan` at `11185-11232` | correct for v3 + pass 7 |

Freeze rendering outputs 32/15/17, both per-label censuses, excluded-key identity, and census-record SHA/size/counts (`epl/evwiden.py:10687-10722,10752-10764`).

The transplant is not complete as one clean statement. Current document errors are:

- 19 untouched instead of 17 (`reports/epl_widening_prereg_v3.md:1027-1032`);
- 32 tallies instead of 30 (`1489`, contradicting `1461`);
- 52 manifest paths instead of 49 (`3130`);
- “No … population or gate moved” after explicitly listing population and gate-population changes (`2971-2977,2998-3007`).

The most consequential code residue is not merely commentary: `score_table` emits `pooled_delta_trps_35_cells` and `pooled_delta_wtrps_35_cells`, and `evidence_object` carries those false names into `widening.json` (`epl/evwiden.py:7551-7566,8091-8108`).

## 2. Gate populations and tolerance

The intended default-path populations are correct:

- iv-a/MW6: seven treated cells (`reports/epl_widening_prereg_v3.md:1075-1091`; `epl/evwiden.py:7444-7464`);
- iv-b: MW0=2, MW3=2, MW10=4 (`reports/epl_widening_prereg_v3.md:1337-1405`; `epl/evwiden.py:7466-7477`);
- MW19: seven cells, zero treated (`epl/evwiden.py:7479-7487`);
- iv-c: seven MW6 season blocks (`reports/epl_widening_prereg_v3.md:1420-1431`);
- point labels: MW0/MW3/MW10 (`epl/evwiden.py:342-348`);
- P1–P4 boundaries: implemented with the stated strict comparisons (`epl/evwiden.py:7661-7687`);
- P5: K=200 and the fixed seed are used in the normal computation (`epl/evwiden.py:7292-7358`).

The tolerance calculation is correct:

`0.0002 × 32 / 15 = 0.000426666…`, and `0.000426666… / 0.0002 = 2.13333…`.

Thus `+0.00042667` and `2.13×` are right (`reports/epl_widening_prereg_v3.md:1213-1218`). This is a mechanically recomputed explanatory equivalent of the already-fixed `+0.0002` treated-cell threshold, not a new post-census tolerance choice.

The populations are not enforced on all deciding surfaces:

- `score_table(expected_cells=None)` validates even total rows only when its caller opts in (`epl/evwiden.py:7367-7408`);
- `table_gate` accepts wrong-population scored objects (`7589-7725`);
- `paired_mc_bootstrap` does not require 15 cells (`7057-7166`);
- `unanimity_is_valid` does not bind MW6=7, 15 cells, 30 tallies, bootstrap count, or bootstrap seed (`7235-7289`);
- `TABLE_CI_BLOCKS=7` is unused by production code (`379-384`);
- committed tests pass a v2-shaped 35/16/three-per-label scored fixture to the gate and expect resolution (`epl/tests/test_evwiden.py:3234-3270`).

Therefore the written populations are correct, but the executable gates are not population-closed.

## 3. Budget ruling

The v3 author is right against the 188/140 brief:

- fits: `4 canary + 1 single-opening + 78 openings + 32 oracle + 32 runner = 147`;
- simulations: `32 oracle + 64 runner = 96`;
- adding pass 7: `147 + 35 = 182 fits`; `96 + 35 = 131 simulations`.

That agrees with §2.4 and `_plan` (`reports/epl_widening_prereg_v3.md:687-710`; `epl/evwiden.py:11185-11232`). The proposed 188/140 incorrectly adds pass 7 to v2’s obsolete 153/105 plan.

However, 182/131 is not literally the “whole lifecycle, this lineage.” v3 itself records v1’s two real ADVI fits (`reports/epl_widening_prereg_v3.md:41-48,1899-1946,2910-2924`). Literal full-lineage expenditure is 184 fits/131 simulations. This is an IMPORTANT scope/wording defect, not a rejection of the 147/96 or 182/131 arithmetic.

## 4. Dropping point

The normal constructor drops the three exclusions at `table_cutoffs` before appending cells, and `assert_table_census` checks excluded-key restoration before aggregate totals (`epl/evwiden.py:5434-5464,5625-5644`).

It is not the only schedule-building route, and substitution is not reliably caught:

- `table_cells` is exported and accepts `seasons=`, `labels=`, `e_star=`, and `check=False` (`epl/evwiden.py:182-199,5551-5605`);
- `assert_table_census` checks excluded-key intersection, totals, per-label counts, and the all-treated label, but not exact key set, uniqueness, cutoff, evidence value, or treated-club identity (`5608-5692`);
- replacing an untouched MW19 season with a bogus same-label season preserves every implemented check;
- `run_table` and `run_parity_oracle` accept caller cells without invoking the census assertion (`6461-6517,6817-6868`);
- `assert_parity_complete` binds only to those supplied keys plus length 32 (`6638-6687`);
- membership digests hash only `season|label`, not cutoff or treated-club identity (`1486-1521`);
- `freeze_block` accepts substituted corpus/played/ledger/table objects (`10603-10607`).

The claim that a substituted thirty-second cell is necessarily caught (`reports/epl_widening_prereg_v3.md:853-855,1019-1022`) is false.

## 5. Legitimacy of v3

Plain ruling: v3 is scientifically a legitimate feasibility-conditioned rebirth, not an outcome-conditioned redesign—conditional on the owner’s unverified statement that pass 7 produced only protected-control priceability information and no arm comparison, delta, or estimand.

v2 prospectively specified the full census and the “write a new preregistration” remedy before execution (`reports/epl_widening_prereg_v2.md:1883-1991`). Pass 7 could reveal:

- whether each protected-control cell priced;
- refusal class and excluded mass;
- runtime/provenance information.

It could not reveal treatment performance because it ran no treatment arm. The clauses influenced beyond the bare boolean census are record SHA/size, timestamps, run commit, exception classes, fixtures, and masses (`reports/epl_widening_prereg_v3.md:250-285,2859-2872,2940-2957`). None selects an estimand or effect threshold.

A different set of unpriceable cells would mechanically have changed exact membership, totals, both per-label censuses, iv-b denominators, tally count, budget, manifest membership, and the descriptive tolerance equivalent. If MW6 had lost a cell, this v3 would not have been writable because its preselected deciding-horizon ground would have failed. That is legitimate feasibility adaptation precisely because the adaptation rule preceded the measurement.

The false sentence is “No threshold, seed, population or gate moved” (`reports/epl_widening_prereg_v3.md:2998-3007`): populations and gate populations did move. The honest statement is that no outcome threshold, seed, estimand, or decision rule was chosen from an effect-bearing result.

## 6. v2 closure

The v2 closure is structurally correct. `git diff ed77df5 11159b1 -- reports/epl_widening_prereg_v2.md` shows one 67-line dated append and no edits to prior text. It states the census, invokes v2’s pre-rule, declares v2 infeasible, points to v3, retains v2 as lineage, and says the note decides nothing (`reports/epl_widening_prereg_v2.md:2898-2961`).

It does not retroactively repair v2. Its claim that v3 counts both prior events inside its budget inherits the 184/131 wording defect (`2953-2954`).

## 7. No-fit clock and inherited regime

Starting R-B6’s clock at v3’s own freeze commit is scientifically legitimate:

- v1’s two fits were unauthorized and disclosed;
- v2 prospectively authorized pass 7 as a control-only capability census and pre-ruled the successor-document remedy;
- v3 carries all of that as named history and authorizes no further prefreeze fitting/simulation pass (`reports/epl_widening_prereg_v3.md:1897-2031,2073-2083`).

This is not v1’s dead “fresh clock erases prior information” argument because v3 does not erase the prior fitting and, on the supplied account, no treatment result was learned.

The lifecycle law is nonetheless internally impossible at the pin. It says all six prefreeze passes are read-only and no further prefreeze pass may write anywhere in the repository (`reports/epl_widening_prereg_v3.md:2033-2039,2085-2116`). Mandatory pass 3 is pytest and must produce `data/epl/fit/evwiden_conformance.json` (`2048-2051,2894-2902`). The harness session writes exactly that file, and freeze requires it (`epl/evwiden.py:9368-9437`; `epl/tests/test_evwiden.py:7285-7298`; document `2164-2213`). A required freeze prerequisite is forbidden by the same operative law.

# THE DECIDING HORIZON

## 1. Does §4.1 follow from the 32-cell census?

Yes. The required comparative premise is not equal label denominators; it is that MW6 is the only label whose priceable population is entirely treated:

- MW0: 2/5;
- MW3: 2/6;
- MW6: 7/7;
- MW10: 4/7;
- MW19: 0/7.

That matches §1.4 and §4.1 (`reports/epl_widening_prereg_v3.md:873-895,1077-1091`) and the harness mappings (`epl/evwiden.py:346-356`). The argument works on the 32-cell census and does not need the former 35.

## 2. Did v3 retain equal-denominator assumptions?

The operative gate uses label-specific populations, so §4.1, §3.3, §4.2, and the secondaries do not require all labels to contain seven cells (`reports/epl_widening_prereg_v3.md:1077-1091,1335-1405`; `epl/evwiden.py:7444-7487`).

One comparative sentence is false: v3 says MW6 is “the only label whose census was left whole” (`reports/epl_widening_prereg_v3.md:1105-1107`). MW10 and MW19 also remain 7/7 priceable; MW6 is uniquely all-treated, not uniquely whole.

The old uniform world also survives in harness prose, emitted 35-cell keys, conformance scenario descriptions, and v2-shaped gate fixtures (`epl/evwiden.py:6362-6381,7372-7381,7555-7566,9557-9561,9645-9673`; `epl/tests/test_evwiden.py:3234-3270`). Those do not change the intended normal-path arithmetic, but they make v3 internally unclean.

## 3. Was MW6 chosen after the census?

No. Git history establishes that MW6 was selected before pass 7:

- at `1b79cc5`, repaired v1 already names MW6 as the seven-cell deciding horizon and gives the “only label every cell is treated” ground in `reports/epl_widening_prereg.md:985-1007`;
- v2 at `1afd54d` retains the same ground in `reports/epl_widening_prereg_v2.md:725-734,894-918`;
- it remained through `4c01183`, before the pass-7 census commits.

Therefore a different census could have made the existing MW6 ground fail, but could not legitimately have caused the owner to choose another label. The authorized response would have been no writable v3 of this form.

## 4. Harness consistency

The intended constants are consistent: `POINT_GATE_LABELS` is MW0/MW3/MW10, iv-b uses 2/2/4, and iv-a/iv-c/§5.3 use the seven MW6 cells (`epl/evwiden.py:342-356,7444-7477,7635-7687`).

The inconsistency is enforcement, not the chosen label: public scorer/gate/bootstrap/unanimity surfaces do not require those populations, and `TABLE_CI_BLOCKS=7` is not used by production code (`epl/evwiden.py:7057-7166,7235-7289,7367-7408,7589-7725`).

# CONFORMANCE ROWS L1-L18

| Row | Re-grade | What actually executes; can it stay green under its named defect? |
|---|---|---|
| L1 | PARTIAL BEHAVIORAL | It executes corpus-versus-Arm-B mutation and catches the old equality fixture, but direct literal arrays or a distinct posterior channel can still satisfy it. `epl/evwiden.py:9590-9643`. |
| L2 | PARTIAL BEHAVIORAL | It drives a pooled-pass/MW6-fail scenario, but checks a hand-picked output surface and even searches a stale `pooled_delta_trps_35_cells` name. Another pooled publication or wrong-population gate can survive. `epl/evwiden.py:9645-9674`. |
| L3 | PARTIAL BEHAVIORAL | It exercises ties and a joint-SE inequality, but does not execute a depaired reference estimator; another wrong estimator can preserve both observations. `epl/evwiden.py:9676-9723`. |
| L4 | PARTIAL BEHAVIORAL | It exercises K=1, one dissent, inversion, and one paired/depaired disagreement. `unanimity_is_valid` still accepts 200 repeats of one verdict and omits population bindings. `epl/evwiden.py:7235-7289,9731-9767`. |
| L5 | PARTIAL BEHAVIORAL | It tests ordering through `_conf_runner`/`run_cell_arms`, not actual `TableRunner.__call__`; A1 can remain green. `epl/evwiden.py:9201-9291,9780-9817`. |
| L6 | PARTIAL BEHAVIORAL | It exercises read-only refusal, but its “nothing created” assertion does not catch constructor creation followed by refusal; TOCTOU remains. `epl/evwiden.py:9829-9867`; `epl/tests/test_evwiden.py:7238-7265`. |
| L7 | PARTIAL / SOURCE-HEAVY | It checks selected signatures and selected unfrozen calls. It misses the scratch merge route and `run_canary`’s synthetic-metadata/real-fit shadowing. `epl/evwiden.py:9873-9931`. |
| L8 | PARTIAL BEHAVIORAL | It tests several malformed record/witness states, but not full deletion returning pre-fit, record/witness identity disagreement beyond `at`/`where`, or freeze-status skipping witness-only state. `epl/evwiden.py:9933-9985`. |
| L9 | FAILS ITS NAMED OBLIGATION | It tests marker primitives/source text, not the actual launcher sequence. Step 2 lacks its canary, direct APIs skip current claims, product hashes are not recomputed, and the official claim prevents resumption. It can be green while the frozen sequence fails. `epl/evwiden.py:9996-10124`; `epl/tests/test_evwiden.py:7068-7191`. |
| L10 | PARTIAL BEHAVIORAL | Tally-byte and binding mutations are real, but linkage/signature pieces are source checks and the broader fabricated-scored path remains. `epl/evwiden.py:10126-10189`. |
| L11 | PARTIAL BEHAVIORAL | It drives the helper’s provisional-purity scenario but not the actual `TableRunner`; the named production obligation can fail after the helper. `epl/evwiden.py:10191-10265`. |
| L12 | PARTIAL BEHAVIORAL / AST | It executes three helper checks, then uses AST presence to assert `Engine.fit` calls them. Dead or conditionally bypassed calls can keep it green; actual `Engine.fit` scenarios are separate tests not artifact-bound. `epl/evwiden.py:10274-10309`; `epl/tests/test_evwiden.py:1293-1364`. |
| L13 | NOT THE NAMED BEHAVIOR | It calls `assert_structural_zeros` directly rather than merging the malformed rows as the row promises. `merge` can fail to invoke it while L13 stays green. `epl/evwiden.py:10311-10329`. |
| L14 | PARTIAL / FALSE FEASIBILITY HALF | It catches label-count perturbations and one excluded key, but not same-label key substitution, duplicate seasons, altered cutoffs, or altered treated clubs. Its feasibility probe can self-raise rather than exercise all reader cases. `epl/evwiden.py:10331-10369`. |
| L15 | PARTIAL BEHAVIORAL | It mutates manifest helper inputs but does not execute the complete evidence writer/reader contract. Emission mismatches—including stale 35-cell keys—can remain green. `epl/evwiden.py:10371-10413`. |
| L16 | POISONABLE | It calls `committed_power_run`, but a pre-populated module `_POWER_RUN` supplies the answer without executing the committed simulation. `epl/evwiden.py:4945-4963,10415-10431`. |
| L17 | PARTIAL BEHAVIORAL | It proves the untreated-moved publication, but not the full predicate-mismatch obligation; merge linkage is source-based. `epl/evwiden.py:10433-10465`. |
| L18 | PARTIAL / SOURCE-HEAVY | It checks a hand-picked signature/CLI inventory. `_cli_arguments` source-scans `add_argument` lines and can miss multiline/alias surfaces; mutable globals and `--dir` ledger selection remain. `epl/evwiden.py:9076-9086,10467-10548`. |

## 1. Can the renderer still author its own evidence?

Yes.

The direct call chain is:

`freeze_block` → conformance-artifact reader → exact-ID/outcome checks → `conformance_row`/`implementation_report` re-execution for the displayed report (`epl/evwiden.py:9381-9437,10561-10600`).

More decisively, the same module exports `write_conformance_artifact(outcomes=...)`, which accepts arbitrary outcomes and attaches current hashes. Tests use it to create an all-passed artifact and render a block (`epl/tests/test_evwiden.py:7365-7387`). The reporting code can still author acceptable evidence; the author’s independence claim is false.

## 2. Forgery, staleness, partiality, and code binding

The reader correctly requires exactly eighteen stable IDs, all passed, count eighteen, and matching current document/harness hashes (`reports/epl_widening_prereg_v3.md:2480-2519`; `epl/evwiden.py:9412-9437`).

That blocks a green subset and an artifact naming different source hashes. It does not establish provenance:

- the public writer can forge all outcomes while using current hashes;
- there is no authenticated pytest-session identity;
- an old artifact from the same unchanged harness remains acceptable indefinitely;
- the ignored file is not recoverable from Git;
- the block prints the artifact SHA, but the later committed-block guard parses the eighteen yes/no rows rather than rereading and authenticating that artifact (`epl/evwiden.py:8932-8948`).

The binding is therefore a source-version label, not proof that those source bytes executed those tests.

## 3. What do eighteen passed IDs establish?

They establish only that a JSON object contains the expected IDs and the string `passed`. Even in a genuine pytest run, each wrapper proves that `conformance_row(row)["ok"]` returned true. It does not independently establish the full prose obligation when the row is partial, AST-based, helper-level, or itself wrong.

## 4. Memoisation

One `implementation_report()` shared by eighteen wrapper tests is an evidentiary defect, not merely a compute optimization. The tests are eighteen readers of one self-grading execution, contrary to the prose’s “each executes its own row’s scenario” claim (`reports/epl_widening_prereg_v3.md:2480-2499`; `epl/evwiden.py:9381-9404`).

A per-row independent executor would improve isolation and make dropped/dead rows easier to detect. It would not by itself cure the public artifact writer, incomplete row scenarios, or lack of authenticated session provenance.

## 5. `_POWER_RUN`

`_POWER_RUN` is poisonable. `committed_power_run()` returns the module cache when populated, so L16 can go green without executing `power_simulation()` (`epl/evwiden.py:4945-4963,10415-10431`). Because L16 is a mandatory freeze prerequisite and no fresh-process/empty-cache invariant is authenticated, this is blocking.

# NEW DEFECTS

I count three new blocking defect classes. Recurrences of prior findings—claim bypasses, witness deletion, scratch merge, `run_canary`, and conformance self-authorship—are counted under their prior identifiers, not again here.

## V3-B1 — BLOCKING: the exact 32-cell experiment is not bound end-to-end

The active aggregate constants are right, but no single production assertion establishes the frozen exact schedule, unique keys, cutoff dates, and treated-club membership. `assert_table_census` permits a bogus same-label season or altered cutoff/treated club; direct table/oracle paths bypass it; gate/bootstrap/unanimity accept wrong populations; membership digests omit cutoff and club identity (`epl/evwiden.py:1486-1521,5551-5692,6461-6517,6817-6868,7057-7166,7235-7289,7367-7408,7589-7725`).

This defeats the core v3 promise that the experiment is exactly the measured 32, not merely any 32 with the same aggregate census (`reports/epl_widening_prereg_v3.md:306-318,853-855,1019-1022`).

## V3-B2 — BLOCKING: the prefreeze conformance protocol is self-contradictory

v3 prohibits every prefreeze repository write while requiring pytest to write the conformance artifact under ignored repository `data/` before freeze (`reports/epl_widening_prereg_v3.md:2033-2051,2085-2116,2164-2213,2894-2902`; `epl/evwiden.py:9368-9437`; `epl/tests/test_evwiden.py:7285-7298`).

There is no legal sequence satisfying both clauses. One must be amended before freeze; it cannot be repaired afterward under the no-post-fit-edit rule.

## V3-B3 — BLOCKING: L16’s required power evidence can be replaced by process state

The module-level `_POWER_RUN` cache is an unbound authority over `committed_power_run()`. Pre-populating it skips the committed power simulation and supplies L16’s result (`epl/evwiden.py:4945-4963,10415-10431`). The conformance artifact records only the wrapper’s passed outcome, not whether the simulation executed.

## V3-I1 — IMPORTANT: “whole lineage” budget is false

182/131 is correct for pass 7 plus v3, but full lineage also includes two disclosed v1 fits, making literal expenditure 184/131 (`reports/epl_widening_prereg_v3.md:41-48,687-710,1899-1946,2910-2924`).

## V3-I2 — IMPORTANT: v3 contains current, output-bearing v2 residues

This includes 19 untouched, 32 tallies, 52 paths, false 35-cell output keys, old parity counts, and the false “no population or gate moved” statement (`reports/epl_widening_prereg_v3.md:1027-1032,1489,2998-3007,3130`; `epl/evwiden.py:325-331,6362-6381,6641-6673,7555-7566,7805-7815`). These are not harmless lineage quotations, and §8.7 would make them permanent.

## V3-I3 — IMPORTANT: the ignored census is integrity-bound but not repository-auditable

The SHA/size/exact-key reader is sound against accidental mutation or deletion (`epl/evwiden.py:2553-2570,10817-10870`). But a repository-only reader has neither the evidence bytes nor an archival locator. Git cannot independently inspect the masses, execution commit, completion, timings, or provenance, and cannot recover the file if deleted. The claim that the hash makes the census checkable by a repository reader is overstated (`reports/epl_widening_prereg_v3.md:2187-2191`).

## Closure-principle disposition

The closure remains a hand-picked list. In addition to the defects above:

- `--dir` still selects alternate canary, shard, ledger, and table locations after freeze (`epl/evwiden.py:11387-11448,11635-11704`);
- `run_fits`, `run_parity_oracle`, and `run_table` expose `resume=False` and do not enforce current-step claims (`3227-3312,6461-6517,6817-6899`);
- `run_cell_arms` remains directly callable with injected effects (`6027-6098`);
- `run_canary` validates inputs different from those its default runner uses (`3759-3772`);
- `merge` and `freeze_block` retain caller-supplied decision/evidence objects (`5193-5397,10603-10607`);
- `LAUNCH_PYTHON`, `working_tree_bytes`, `_POWER_RUN`, and cached implementation reports remain mutable runtime authorities.

The census reader’s inverted gate itself behaves correctly for absence, truncation, wrong SHA, incomplete census, extra/wrong key sets, or a 35-priceable record (`epl/evwiden.py:10817-10870`). What it cannot prove is that the pinned bytes were produced by the claimed harness run.

`EXCLUDED_CELLS` is now frozen historical scope, not a continuing claim that those fixtures can never become priceable. If the protected stack changes and one becomes priceable, v3 still excludes it by name; §10 must treat adding it back as a new design, not silently enlarge this one (`reports/epl_widening_prereg_v3.md:3210-3225`; `epl/evwiden.py:358-377`).

The v3 author’s global claim that every residual item closed is therefore false: eleven of the fourteen unique Part 1(a) identifiers remain open, including executable-step, lifecycle-ratchet, exact-sequence, conformance-independence, and actual-runner defects.

# VERDICT

DO-NOT-FREEZE — 23 prior findings remain STILL-OPEN, and 3 new blocking defect classes were found.

Before a freeze can be legitimate, the shortest necessary list is:

1. Bind the exact canonical 32 cells—including uniqueness, cutoff, treated-club identity, and every dependent gate population—on every executable decision path.
2. Make the five-step lifecycle executable and coherent: copy the step-2 canary, make claims atomic, define crash-safe retry semantics, bind markers to current product bytes, enforce current-step claims on direct APIs, and close alternate `--dir`/ledger/file-drawer routes.
3. Replace the deletable/partially checked first-fit pair with a consistent ratchet, validate full record/witness identity, and reread lifecycle/current bytes before every fit.
4. Make conformance lawful and independently evidenced: expressly authorize its one prefreeze write or redesign it, remove the arbitrary artifact writer and `_POWER_RUN` authority, and make each row genuinely behavioral against the production path.
5. Correct the current v2 residues and lifecycle-budget wording before the no-post-fit-edit rule activates.

Do not render or paste the freeze block, and do not begin the first real v3 fit.

