# In-tree adversarial seed audit of the v3 harness — 2026-08-29

*Committed verbatim under v3 §8.3's dual-audit requirement and named in the
adjudication of 2026-08-29 (v3 §8.9). This is the audit's own report; nothing
in it is edited, summarised or answered here — the adjudication answers it, item
by item, in the document it is committed beside.*

**Verdict:** `FAIL` · **seeds red:** 28 of 30 · **tree clean:** True

## Summary

FAIL — do not freeze. 28 of 30 seeds red; two green, one of them a seed the brief mandates.

SEED BOOK: I could reconstruct 23 code-patch seeds of the round-6 book from the in-tree drivers (a b b2 c d d2 d3 d4 e f g h i j n o p q q2 r w x y; round-6's 'z' was a fixture-level self-test, not a code patch) plus the 7 new ones (aa aa2 bb cc dd ee ff) = 30. I could not reconstruct 2 of the 26 the brief cites; the round-6 brief itself is not in the record dirs I was pointed at. Every one of the 30 anchors matched its file exactly once before patching.

GREEN SEEDS: (ff) hardwiring `prereg_bytes_match_blob = True` leaves 320 passed — the current-bytes half of §8.6 condition (1), which §8.9 lists as newly ruled law, is guarded only by a test that checks a dict key and two source substrings. (d) making the merge's Arm B RPS recomputation read back the stored value leaves 320 passed — §2.3's \"recomputes it at the merge\" clause has no independent test. Seed (d) was green in round 6 too and was dropped from the round-7 book rather than closed.

THE OTHER MANDATED SEEDS: (aa) census drift, (aa2) excluded-set drift, (bb) unbinding the feasibility digest, (cc) re-adding `--table-ledger`, (dd) disabling the witness ratchet, (ee) accepting a green subset — all six red. But (ee) has a second half the brief names, \"or its own self-report\", and that one cannot be seeded red: I verified in a fresh process that `write_conformance_artifact` — public, exported, arbitrary outcomes — plus `assert_conformance_artifact` accepts a wholly fabricated 18/18 artifact, stamping current harness hashes so the digest cross-check can never catch it. Two committed tests do exactly this. §8.5's \"an artifact the harness does not write\" is false. I also verified `_POWER_RUN` poisoning: `committed_power_run()` hands back a planted object without running `power_simulation()`, which is the whole obligation of L16, a mandatory freeze row.

CENSUS CHECK FAILS. v3's text and the code disagree on census numbers in both directions. In the law: §3.3:1030 \"19-untouched-cell\" (17), §5.4:1489 \"all 32 tallies\" (30), §9.3:3130 \"outside the 52\" (49) — each contradicted by v3 elsewhere. In the harness: `pooled_delta_trps_35_cells` is emitted into widening.json, L2's published claim says \"35-cell leg\" where the law says 32-cell, `TABLE_TOLERANCE`'s docstring says 16 cells / 2.19× where §4.3 says 15 / 2.13×, and `--verify`'s refusal text says 52 paths where the value is 49. Two structural contradictions sit beside them: §8.9's \"No threshold, seed, population or gate moved\" is refuted by its own preceding paragraph, and §8.2's blanket ban on pre-freeze repository writes forbids the pytest write that §8.5 makes a freeze prerequisite.

The active executable constants are correct — 32/15/17, both per-label censuses, the three excluded keys, the feasibility SHA and byte count, and the budget arithmetic (182/131, against which my brief's 188/140 is the stale v2 figure). The defects are in what is untested, what is forgeable, and what the prose still says.

CHECKS THAT HOLD: protected paths untouched since ed77df5 (diff is exactly epl/evwiden.py, epl/tests/test_evwiden.py, and the two reports); v2 changed only by a 67-line dated append and its closing note is present and accurate against the record; full suite 1410 passed / 1 skipped before and after the replay; LOCK VALID; freeze block renders 8,896 B with all 18 rows yes.

TREE: byte-identical to HEAD 11159b1 at the end and after every individual seed (the runner checked and would have aborted otherwise). `git status --porcelain`, `git diff`, `git diff HEAD` all empty; epl/evwiden.py, epl/tests/test_evwiden.py and reports/epl_widening_prereg_v3.md each hash-match their HEAD blobs. No commits made. The conformance artifact and freeze block were regenerated from a clean full-suite run so the gitignored state is left functional.

RECORDS: /private/tmp/claude-502/-Users-likerun-Desktop-worldcup/5eb714a7-aa7a-4e5e-a0c2-359239e63ef8/scratchpad/ — R7_seedsummary.txt (all 30), R7_seed_<label>.json (per-seed tails), R7_baseline_full.txt and R7_final_full.txt (the two suite runs), R7_block.md (rendered block), r7_seed.py (the 30-seed driver).

## Findings

### BLOCKING

SEED (ff) IS GREEN — the mandated seed turns no test red. Patching epl/evwiden.py:8861 `prereg_bytes_match_blob = working_tree_bytes(rel) == blob` to `= True` leaves the module at 320 passed. This is the exact mechanism §8.9 advertises as newly ruled law ("§8.6 condition (1) binds this document's current bytes as well as its committed blob, so an uncommitted post-fit edit is detected"). Its one test, epl/tests/test_evwiden.py:7008 `test_the_guard_binds_the_documents_current_bytes_not_only_its_blob`, asserts only that the key `prereg_bytes_match_blob` is present in the status dict and that the strings `git_committed_bytes` and `PREREG_PATH` occur somewhere in the function source — all three survive the defect. This is precisely the "names, not obligations" shape §8.5's opening paragraph condemns in v1's fourteen rows, reintroduced in the guard that §8.7's whole regime depends on.

### BLOCKING

SEED (ee) SELF-REPORT HALF IS OPEN — the conformance artifact is forgeable, so the freeze precondition can be manufactured. `write_conformance_artifact` (epl/evwiden.py:9412) is exported in `__all__` and takes an arbitrary `outcomes` dict. Verified empirically: in a fresh process that ran no L-row, `write_conformance_artifact({r: 'passed' for r in ew.CONFORMANCE_ROWS})` followed by `assert_conformance_artifact()` returns ok=True, count=18. The harness-digest cross-check cannot catch it, because the writer stamps the CURRENT file hashes at write time, so a fabrication always matches. Two committed tests do exactly this and render an accepted block (epl/tests/test_evwiden.py:7365-7387, and the L18-adjacent case at 7366-7371). v3 §8.5 therefore states a falsehood as law: "The conformance report is produced FROM an artifact the harness does not write", "The harness may not mark a row green from anything it computed itself", "A report that lies about itself has nothing left to lie with". Note also that most seeds in this replay surface through one choke point — `test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head` erroring on the conformance artifact — so the detection channel for 8 of the 28 red seeds is the same channel this defect bypasses.

### BLOCKING

`_POWER_RUN` IS AN UNBOUND AUTHORITY OVER L16, A MANDATORY FREEZE ROW. `committed_power_run()` (epl/evwiden.py:4948) returns `_POWER_RUN['value']` whenever the module-level dict is populated. Verified empirically: planting `ew._POWER_RUN['value'] = {...}` before any call makes `committed_power_run()` return the planted object without executing `power_simulation()`. L16 (epl/evwiden.py:10415) calls `power_reproduces()` with no argument and its stated obligation is "run the committed `power_simulation()` at the frozen constants through the REAL comparison — not a stubbed power object" — the one thing the row exists to catch is supplied by process state. The pass-7 fix agent flagged this in its own concern 5 ("a caller who reached into `_POWER_RUN` could poison it... a reviewer may want it removed") and no round has removed it.

### IMPORTANT

SEED (d) FROM THE ROUND-6 BOOK IS STILL GREEN — 320 passed. Replacing the merge's Arm B RPS recomputation at epl/evwiden.py:5180 (`recomputed = float(score_mod.rps(np.array([native]), np.array([int(row["y"])]))[0])`) with `recomputed = float(row["rps_native"])` makes the first term of the `worst_rps` comparison identically zero, so §2.3's clause "recomputes it at the merge and refuses past 1e-12" becomes vacuous and nothing detects it. It survives only because the surviving corpus comparison plus §3.2's exact-equality identity control make it redundant — but that means the law's recomputation clause has no independent test. Round 6 found this green; the round-7 book dropped seed d and substituted d2/d3/d4, which target the CHECKS rather than the RECOMPUTATION and are all red.

### IMPORTANT

THE SOLE LAW CARRIES THREE STALE v2 CENSUS NUMBERS, each contradicted by v3 elsewhere on its own pages, and §8.7 would make them permanent. (1) reports/epl_widening_prereg_v3.md:1030 "The 19-untouched-cell control" — the census has 17 untouched; §8.9:2972 itself records "19 → 17 untouched". (2) line 1489 "one joint particle draw per replicate, applied to all 32 tallies" — there are 30; §5.2:1340 says "Fifteen cells × two arms = 30 tallies", 1342 says "All 30 tallies", §8.5 rows L3/L4 say "30-tally object", §8.9 records "§5's deciding tallies 32 → 30". The error is easy to miss because 32 is also the cell count. (3) line 3130 "if the MANIFEST carries an entry inside this experiment's namespace (`widening`, `evwiden`) outside the 52" — an operative `--verify` refusal clause, in the same sentence that twice says 49, under a heading that reads "an exact list of 49 paths"; §8.9:2978 records "52 → 49 paths".

### IMPORTANT

THE HARNESS EMITS AND PUBLISHES THE ABOLISHED 35-CELL CENSUS. Most consequential: `score_table` emits the keys `pooled_delta_trps_35_cells` and `pooled_delta_wtrps_35_cells` (epl/evwiden.py:7555-7566) and `evidence_object` carries those names into reports/evidence/widening.json — a published field naming a population v3 abolished. Also: conformance row L2's own published claim string says "score a real 35-cell leg" and its detail key is `pooled_35` (epl/evwiden.py:9668-9673), where v3 §8.5's L2 row says "score a real 32-cell leg ... whose 32-cell pooled mean passes"; `TABLE_TOLERANCE`'s docstring (epl/evwiden.py:329-331) says "across the 16 changed cells ... 2.19x tighter" where v3 §4.3:1213-1218 says 15 and 2.13× (32/15 = 2.1333; 2.19 is 35/16); `manifest_entries`' docstring says "§9.3's fifty-two paths" (8197) and `--verify`'s refusal text says "the 52" three times (8285-8290, 8392, 8600) while the executable value and the law are 49; the section header at 6363 reads "§3.3 — the 35-cell native-parity oracle"; the synthetic leg is called "35-cell" at 9129/9557/9645 though its own arithmetic comment says 17 zeros + 15 treated. In the tests, seed (h)'s red test is literally named `test_the_manifest_is_the_fifty_two_paths_of_9_3` while its body asserts `len(ew.MANIFEST_PATHS) == 49`.

### IMPORTANT

§8.9's TRANSPLANT CERTIFICATION IS FALSE ON ITS OWN PAGE. reports/epl_widening_prereg_v3.md:3005 states "**No threshold, seed, population or gate moved**, and none could have". The paragraph seven lines earlier (2971-2978) lists the moves: "16 → 15 treated and 19 → 17 untouched", "gate (iv-b)'s MW0 mean over **2** treated cells", "§5's deciding tallies 32 → 30". Populations and gate populations did move. This is exactly the sentence a reviewer would rely on to certify that the census transplant was not outcome-conditioned; the defensible claim is that no outcome threshold, seed, estimand or decision rule was chosen from an effect-bearing result, which is a different and weaker sentence.

### IMPORTANT

§8.2's READ-ONLY RULE AND MANDATORY PASS 3 CANNOT BOTH BE SATISFIED. §8.2 (reports/epl_widening_prereg_v3.md:2036-2039) says of the six authorised pre-freeze passes "**All six are read-only**; ... none writes inside the repository", and 2085-2091 says any further pass "may write nothing under `data/`, `reports/` or anywhere in the repository"; 2096-2113 then presents `--script` as "The one write a pre-freeze command may make, and it is not inside the repository." But pass 3 IS `pytest epl/tests/test_evwiden.py`, and its session must write data/epl/fit/evwiden_conformance.json inside the repository (epl/tests/test_evwiden.py:7295-7298 teardown), which `--freeze-block` then requires. §8.8 acknowledges the write as an exception to the attestation, but §8.2 — the clause the freeze block enumerates and asserts — does not authorise it. There is no legal pre-freeze sequence, and under §8.7 it cannot be repaired after the first fit.

### IMPORTANT

§2.4's "the whole lifecycle, this lineage" OMITS v1's TWO DISCLOSED FITS. The table (reports/epl_widening_prereg_v3.md:687-710) totals 147/96 post-freeze plus pass 7's 35/35 = 182/131, and the arithmetic is correct. But §8.8:2910-2924 counts "All thirty-seven" real fits of this lineage — v1's two plus pass 7's thirty-five — and v2's closing note (reports/epl_widening_prereg_v2.md:2953-2954) promises v3 names "pass 7's thirty-five fits, and v1's two, inside its own attestation and its own budget". Only the attestation does; the literal full-lineage figure is 184/131. A row labelled "the whole lifecycle" that omits two fits the same document counts elsewhere is a wording/scope defect in the budget §10 makes an amendment to move.

### MINOR

CORRECTION TO MY OWN BRIEF, so the wrong constant is not written into v3: the brief's "Whole-lifecycle budget: 188 fits / 140 simulations" is the v2-shaped figure. It is v2's post-freeze plan (153 fits / 105 simulations, at 35 cells) plus pass 7's 35/35, and it traces to the pass-7 fix agent's concern-3 item P5-I1, which was computed before the census existed. Under the 32-cell census the parity oracle is 32/32 and the new runner 32/64, so post-freeze is 147/96 and the lineage figure is 182/131. v3 §2.4 and §8.9:2976-2977 are right; the brief is stale. (Separately, per the finding above, the literal all-lineage figure including v1 is 184/131.)

### MINOR

§8.9's ONE-LINE SUMMARY OF THE WITNESS OVERSTATES §8.6's OWN CONCESSION. §8.9:2984-2985 says the first-fit record "gains an **append-only witness** so deletion cannot reset the regime". Verified empirically against the real functions with the paths rebound to a temp dir: record present + witness present -> `post_first_fit`; record deleted, witness standing -> refuses with `FreezeStateUnverified` (the ratchet holds, as seed (dd) confirms); **both deleted -> `pre_first_fit`**. §8.6:2758-2772 is honest about this ("It makes deletion *visible* rather than impossible... **It is not a global proof**"), so the operative clause is sound and only the summary line overclaims. Note also that `first_fit_state` pairs record to witness on `at` and `where` only (epl/evwiden.py:2861-2869), not on `schema`, `commit`, `prereg`, `prereg_blob` or `harness`.

### MINOR

`assert_table_census`'s DOCSTRING QUOTES THE SUPERSEDED PIN WITHOUT MARKING IT. epl/evwiden.py:5612 carries `EXPECTED_TREATED_BY_LABEL = {MW0: 3, MW3: 2, MW6: 7, MW10: 4, MW19: 0}` and "which today verifies only the 35/16 totals" inside a blockquote, twelve lines below the live constant `{MW0: 2, ...}` at line 348 and in the same docstring whose body correctly says "The 32/15 totals". The blockquote is a quotation of the v2-era audit finding, but nothing marks it as historical, so the function's own documentation contradicts the constant it enforces.

### MINOR

P5-B8 SURVIVES THE CLI FLAG'S REMOVAL THAT SEED (cc) VERIFIES. Seed (cc) is red — re-adding `--table-ledger` to the argument parser turns the suite red, so v3 §8.5 L18's "require `--table-ledger` to name nothing at all" holds at the CLI. The underlying channel does not close with it: `run_table(cells, ledger_path=...)` and `score_table(rows, ledger_path=...)` still accept an arbitrary ledger (epl/evwiden.py:6818, 7367), `_guard_ledger_location` (3035) returns immediately once `harness_frozen` is true so it constrains pre-freeze writes only, and `run_table` calls `require_sequence(SEQUENCE_STEPS[4])`, which by its own docstring requires "its predecessor's completion marker" and never claims step 5 — only `main` claims it (11688-11700). Post-freeze, a second outcome-conditioned table run at a scratch ledger remains reachable from Python.

### MINOR

THE WORKING TREE ARRIVED DIRTY. At session start `git status` showed ` M epl/evwiden.py` carrying seed (aa)'s exact drift — `EXPECTED_CELLS_BY_LABEL` set to `{"MW0": 6, "MW3": 5, ...}` instead of the recorded `{"MW0": 5, "MW3": 6, ...}`. It is a leftover from an interrupted prior run of this same audit (its scratchpad artifact AUD_seed_aa.json is 0 bytes, written 11:09). I saved a copy and restored the file before any measurement; every number in this report was taken against clean HEAD. Flagging because a census drift left uncommitted in the tree is the precise failure mode seed (aa) exists to catch, and it sat there undetected between runs.

## The thirty seeds, as the replay recorded them

```
SEED a driver_rc=0 "red": true :: 1 failed, 21 passed in 1.19s
FAILED epl/tests/test_evwiden.py::test_thin_is_the_thinner_side_and_treated_removes_the_already_widened
SEED b driver_rc=0 "red": true :: 1 failed, 110 passed in 19.05s
FAILED epl/tests/test_evwiden.py::test_seeded_defect_an_arm_b_that_drifted_from_the_corpus_refuses
SEED b2 driver_rc=0 "red": true :: 1 failed, 55 passed in 2.46s
FAILED epl/tests/test_evwiden.py::test_the_real_engine_fit_refuses_a_difference_no_tolerance_would_see
SEED c driver_rc=0 "red": true :: 1 failed, 78 passed in 2.59s
FAILED epl/tests/test_evwiden.py::test_arm_b_is_the_same_posteriors_incumbent_pass_and_never_the_corpus
SEED d driver_rc=0 "red": false :: 320 passed in 274.22s (0:04:34)
SEED d2 driver_rc=0 "red": true :: 1 failed, 112 passed in 20.65s
FAILED epl/tests/test_evwiden.py::test_seeded_defect_arm_bs_rps_is_recomputed_at_the_merge
SEED d3 driver_rc=0 "red": true :: 1 failed, 46 passed in 2.06s
FAILED epl/tests/test_evwiden.py::test_seeded_defect_score_mismatch_in_the_corpus_stops_the_run
SEED d4 driver_rc=0 "red": true :: 1 failed, 46 passed in 1.84s
FAILED epl/tests/test_evwiden.py::test_seeded_defect_score_mismatch_in_the_corpus_stops_the_run
SEED e driver_rc=0 "red": true :: 1 failed, 17 passed in 1.12s
FAILED epl/tests/test_evwiden.py::test_evidence_is_strictly_before_the_cutoff
SEED f driver_rc=0 "red": true :: 1 failed, 141 passed in 30.21s
FAILED epl/tests/test_evwiden.py::test_gate_iv_a_is_the_mw6_mean_against_the_tolerance
SEED g driver_rc=0 "red": true :: 1 failed, 45 passed in 2.12s
FAILED epl/tests/test_evwiden.py::test_a_failed_fit_poisons_its_shard_and_the_shard_refuses_to_re_run
SEED h driver_rc=0 "red": true :: 1 failed, 164 passed in 65.09s (0:01:05)
FAILED epl/tests/test_evwiden.py::test_the_manifest_is_the_fifty_two_paths_of_9_3
SEED i driver_rc=0 "red": true :: 1 failed, 3 passed in 1.05s
FAILED epl/tests/test_evwiden.py::test_the_frozen_constants_are_the_documents
SEED j driver_rc=0 "red": true :: 1 failed, 129 passed in 20.04s
FAILED epl/tests/test_evwiden.py::test_parity_is_established_before_one_treated_simulation_runs
SEED n driver_rc=0 "red": true :: 1 failed, 138 passed in 28.10s
FAILED epl/tests/test_evwiden.py::test_the_paired_bootstrap_applies_one_index_to_every_tally
SEED o driver_rc=0 "red": true :: 1 failed, 122 passed in 19.27s
FAILED epl/tests/test_evwiden.py::test_the_sampler_digests_signature_is_pinned_to_run_and_tallies
SEED p driver_rc=0 "red": true :: 182 passed, 1 error in 102.47s (0:01:42)
ERROR epl/tests/test_evwiden.py::test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head
SEED q driver_rc=0 "red": true :: 182 passed, 1 error in 102.46s (0:01:42)
ERROR epl/tests/test_evwiden.py::test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head
SEED q2 driver_rc=0 "red": true :: 182 passed, 1 error in 112.95s (0:01:52)
ERROR epl/tests/test_evwiden.py::test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head
SEED r driver_rc=0 "red": true :: 1 failed, 132 passed in 20.19s
FAILED epl/tests/test_evwiden.py::test_a_swapped_tally_is_refused_on_the_digest_and_on_its_invariants
SEED w driver_rc=0 "red": true :: 182 passed, 1 error in 102.19s (0:01:42)
ERROR epl/tests/test_evwiden.py::test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head
SEED x driver_rc=0 "red": true :: 1 failed, 262 passed in 221.05s (0:03:41)
FAILED epl/tests/test_evwiden.py::test_a_failed_canary_publishes_its_record_before_the_refusal_is_raised
SEED y driver_rc=0 "red": true :: 182 passed, 1 error in 105.06s (0:01:45)
ERROR epl/tests/test_evwiden.py::test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head
SEED aa driver_rc=0 "red": true :: 1 failed, 177 passed in 69.48s (0:01:09)
FAILED epl/tests/test_evwiden.py::test_membership_and_plan_carry_the_table_cell_memberships
SEED aa2 driver_rc=0 "red": true :: 1 failed, 88 passed in 3.45s
FAILED epl/tests/test_evwiden.py::test_the_two_always_pass_controls_are_measured_off_the_merged_rows
SEED bb driver_rc=0 "red": true :: 1 failed, 252 passed in 227.91s (0:03:47)
FAILED epl/tests/test_evwiden.py::test_a_census_that_is_not_the_census_scopes_nothing
SEED cc driver_rc=0 "red": true :: 182 passed, 1 error in 108.50s (0:01:48)
ERROR epl/tests/test_evwiden.py::test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head
SEED dd driver_rc=0 "red": true :: 182 passed, 1 error in 103.69s (0:01:43)
ERROR epl/tests/test_evwiden.py::test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head
SEED ee driver_rc=0 "red": true :: 1 failed, 315 passed in 232.35s (0:03:52)
FAILED epl/tests/test_evwiden.py::test_the_freeze_reads_an_artifact_it_did_not_write
SEED ff driver_rc=0 "red": false :: 320 passed in 280.67s (0:04:40)
R7-ALL-SEEDS-DONE
```
