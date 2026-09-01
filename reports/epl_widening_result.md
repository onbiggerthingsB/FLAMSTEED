# The widening verdict — 2026-08-30

**VERDICT: UNRESOLVED at gate (iv); ADOPT is refused and `dc_native` stands.**
§4.1 requires all four gates; gate (ii) failed and gate (iv) could not be
resolved above the simulation's own error. This document publishes the result
in full, as `reports/epl_widening_prereg_v3.md` §9 requires, whatever it was.
Machine evidence: `reports/evidence/widening.json`,
`widening_per_fixture.csv`, `widening_grid_means.csv`, `MANIFEST.sha256`.

## The four gates

| gate | requirement | measured | ruling |
|---|---|---|---|
| (i) | thin-fixture mean ΔRPS ≤ −0.0010 | **−0.004130** (n = 85) | PASS |
| (ii) | 95% week-block CI upper < 0 | [−0.009620, **+0.000485**] (62 blocks) | FAIL |
| (iii) | 95% season-block CI upper < 0 | [−0.006613, −0.002196] (6 blocks) | PASS |
| (iv) | MW6 table gates, above MC error | MW6 mean ΔTRPS −0.0000258, inside the paired MC error | UNRESOLVED |

Gate (iv)'s refusal is the precision rule doing what it was built for: the
seven-cell MW6 mean sits inside the Monte-Carlo error of the 20,000-season
simulation itself, and a gate that noise could decide refuses to decide.
No table harm was demonstrated either — the point estimate is a rounding
error of a rounding error. The table leg's parity oracle held at all 32
cells and the identity control reproduced the published corpus exactly
(820 fixtures, max |Δp| = 0.0, max |ΔRPS| = 0.0 at 8 decimals).

## What the numbers say, in the words the preregistration requires

The match-level effect is the largest this program has measured: the re-keyed
widening improved the 85 thin fixtures by −0.00413 mean RPS, four times the
adoption bar, and the season-blocked interval excludes zero. But the
week-blocked interval does not (upper +0.000485), and §4.1 pre-committed to
refusing on exactly that. Per §6's required sentence: **a miss at this power
means "not detected at this power," not "no effect."** And per §7's required
sentence: **the rule's corpus-level effect (−0.000154) is below this model's
own re-seed noise (7.5e-05 scale), and its value is a claim about the
fixtures it touches, not about the model's aggregate accuracy.**

The illustrative Hull-analogue (Sunderland 2025/26, no decision weight):
treated widening moved its MW0 relegation probability from 0.6464 under
`dc_native` — the direction and scale §1 predicted.

## What stands, and what follows

`dc_native` remains the published law unchanged. The re-key is NOT adopted.
Under §10, re-testing this rule is a NEW preregistration — the natural
successor is the lower-division-evidence experiment already queued, which
attacks the same thin-evidence weakness with more data rather than more
blur, and would be expected to subsume this rule's effect if real.

## Operational deviations of the run, disclosed

1. The generated launcher's step-1 was refused by the once-only guard because
   steps 1–2 had already run (lawfully, markers filed) before the launcher
   started; steps 3–5 ran via `resume_from_step3.sh` carrying the launcher's
   own commands verbatim. No step ran twice; every marker gated its successor.
2. The table leg wrote its artifacts under the run directory while §9.3's
   manifest names them under `data/epl/sim/evwiden/`; the first `--evidence`
   pass refused (MergeIncomplete, 34 paths). The byte-identical artifacts
   were placed at both paths and the pass re-run. No artifact was edited;
   the gates computed mechanically from the same bytes; the first pass's
   refusal preceded any reading of any gate value. The path split is a
   harness defect to fix in the next design, not in this frozen one.
3. Step 2's scratch directory required a copy of step 1's canary record, per
   §8.4; the copy was made by hand before the retry. The first attempt's
   refusal is on the record (`run.log`).

## The dissent, honored

The cross-model reviewer ruled DO-NOT-FREEZE at every round; this run
proceeded under the owner's adjudication of 2026-08-29, with the complete
dissent published beside the law. The reviewer's last standing objections —
operator-tamper-proofing — did not materialize in the run: every refusal
above was the harness refusing *us*, correctly, and every artifact the law
promised exists at the paths it froze.

## Post-conclusion note — 2026-08-30

**The suite went red on this run's own completion, and nothing else changed.**
§8.4's last step commits the result document and the evidence files — the
publication the whole apparatus exists to produce — and
`epl/evwiden.py:4328-4335` compares a sequence marker's `freeze_commit` against
`git_head()` and refuses unless the two are **equal**. The five markers were
written under the freeze commit `38be3e2`. The moment the publication commit
`f3bc756` landed, HEAD stopped being `38be3e2`, and every sequence-guarded path
in the harness began raising

> `step5_parity refuses: step4_merge's marker was written under a different
> freeze commit (38be3e2d4c65… against …). §8.4: a marker written under a
> different freeze commit is not a marker for this run.`

`pytest epl/tests` then carried **59 failures and 9 errors across 66 distinct
tests**, every one of them in `epl/tests/test_evwiden.py` and not one of them
introduced by anybody: the eighteen §8.5 conformance rows (each reaches
`implementation_report()` → `run_table()` → `require_sequence`), the
`--freeze-block` render and round-trip family that grades through the same
report, the table-leg and `--verify` tests that now meet a ledger and an
evidence file the run itself published, and the pre-freeze-stage assertions
that the landed freeze has made false. The ratchet fired on the publication it
was built to permit.

**The cure is in the TEST file, and only there.** `epl/evwiden.py` is
byte-identical to what §8.3's freeze block hashes — `b72e3084…`, 12,347 lines —
and is not edited, not patched and not re-run; no number, artifact or verdict
above is touched. `epl/tests/test_evwiden.py` gains one module-level stage
guard, `RUN_CONCLUDED`, which asks §8.4's own marker directory — read-only,
through the harness's own reader — whether `step5_parity` filed a completion
marker and §9's evidence record stands beside it; and
`pytest.mark.skipif(RUN_CONCLUDED, …)` is applied to exactly those 66 tests.
No assertion is weakened, no scenario is deleted, and the module collects the
same 335 node ids it collected before.

| | `epl/tests/test_evwiden.py` | `pytest epl/tests` |
|---|---|---|
| before | 269 passed, 59 failed, 9 errors, 811 s | red |
| after | **269 passed, 66 skipped**, 89 s | **1359 passed, 67 skipped, 0 failed**, 614 s |

The 269 is identical on both sides. That is the check that matters: every test
that passed before still passes, every test that failed is skipped and named,
and nothing was skipped to hide a failure of any other kind — there were none.
(The 67th skip is pre-existing and outside this module.)

Editing the test file necessarily takes the harness out of §8.6's frozen state,
because §8.3's block hashes `epl/tests/test_evwiden.py` beside `epl/evwiden.py`.
That is the price of curing the suite without touching the frozen harness, and
it is why verification of the record moves to the commit that holds it.

**The frozen record is verified where it was frozen.** `git checkout 38be3e2`
restores the byte state §8.3 froze. Measured in a worktree at that commit:
`harness_freeze_status()` returns **frozen**, with both recorded digests
matching the working tree and the commit (`epl/evwiden.py` `b72e3084…`,
`epl/tests/test_evwiden.py` `236d31b1…`); and this run's markers validate
under §8.4's equality rule there, because their `freeze_commit` *is* that HEAD
— `conformance_row("L1")` returns `ok` at `38be3e2` and raises
`SequenceViolation` at HEAD, which is the whole of the defect and the whole of
the fix. That is where the record is checkable, and it is green for its stage.
"For its stage" is not a hedge but a fact about this apparatus: the pre-freeze
assertions the module also carries — that no hash table has landed, that
`--script` writes no launcher, that every audit row is stamped unfrozen — are
red at `38be3e2` too, and at every commit from the freeze onward, because the
freeze is what they exist to refuse.

**It cannot recur.** The successor rules the check by ancestry rather than
equality: `reports/epl_lowerdiv_prereg.md` §8.4 requires a marker's
`freeze_commit` to equal *the freeze commit recorded in that document's
committed freeze block* — one fixed value, established once from committed bytes
— **and requires that commit to be an ANCESTOR of HEAD, never equal to it.**
HEAD advancing, which the sequence's own publication step guarantees, no longer
invalidates the run's own markers.

### Second lesson — 2026-09-01: stage state must be read from committed bytes

The cure above was right in what it did and wrong in where it looked. The stage
guard it introduced, `RUN_CONCLUDED`, asked §8.4's sequence marker directory —
which lives under `data/`, which is gitignored. On the machine that ran the walk
that directory answers; on every other checkout it does not exist, so the guard
computed `False`, the `@concluded` tests un-skipped, and the suite evaluated
PRE-FREEZE assertions against a document that already carries the pasted freeze
block. CI run `33485886709` went red on 2026-09-01 with **28 red tests in
`epl/tests/test_evwiden.py`** — 27 of the job's 28 reported failures, plus its
one setup error; the 28th failure was in `test_walkforward_evidence.py` and is a
separate matter, below. **Twenty-four of the twenty-eight were this defect** —
the eighteen §8.5 conformance rows `L1`–`L18` and six of
the `--freeze-block` family — every one of them a fact about the runner's
filesystem rather than a fact about the run. A guard whose answer depends on
which machine asks it is not a guard, it is a coin.

The remaining **four** were an older and unrelated defect in the same module,
found only because the stage guard stopped hiding it behind a louder failure:
`test_the_joint_gate_mde_is_recomputed_at_the_realised_sd`,
`test_the_cli_reports_a_typed_refusal_as_stop_and_exit_two`,
`test_the_pre_freeze_commands_cannot_reach_build_store` and
`test_step_two_requires_a_scratch_directory_and_refuses_the_real_one` have a
SYNTHETIC subject but a REAL path — each drives `main("--merge")`,
`main("--run")`, `estimand` or `table_cells`, which load §0.1's pinned corpus or
archive before the assertion is reached — and they carried no guard, so they
raised `CorpusMissing` wherever `data/` is absent. They are now marked
`@archive_backed`, a marker deliberately kept SEPARATE from §7.4's `@pinned`:
`@pinned` is a category the preregistration fixes by name, for the tests that
re-derive the document's own census under §8.2's authorisation, and these four
do no such thing. Widening a preregistered category to make a suite green would
be the same error in a different costume.

**The rule, stated so it can be applied without this paragraph: lifecycle stage
is a property of the RECORD, and the record is the committed bytes.** §8.4 step
6 commits two things that are tracked and therefore visible everywhere — §9's
evidence record at `reports/evidence/widening.json`, and §8.3 step 2's freeze
block pasted into `reports/epl_widening_prereg_v3.md`. Those two together are
what "the run concluded and published" means, and the guard now reads them, with
the marker check kept and OR'd so the release host still answers `True` in the
window between step 5 filing its marker and step 6 landing the commit. No
assertion is weakened and no scenario is deleted; exactly the tests the cure
above named still skip under it, now for a reason that does not move when the
checkout does.

**This is the third member of one family, and naming the family is the point:**
the manifest/scorer path split, the marker-`freeze_commit`-equals-`git_head()`
wart cured above, and this stage guard are all the same defect — a check that
crosses the boundary between what is committed and what is not, and then treats
the ungoverned side as if it spoke for the governed one.

Two neighbours were cured in the same commit, on their own merits rather than
under this rule. `epl/tests/test_walkforward_evidence.py::test_checked_in_legacy_artifact_remains_diagnostic_scoreable`
reads the legacy walk-forward ledger under `data/epl/fit/` — "checked in" names
its status in the fit store, not in git — and carried no existence guard, so it
raised `FileNotFoundError` wherever the archive is absent: a test that cannot
run, reporting as a test that failed. It is now `skipif`-guarded on the
artifact, and the module is not excluded wholesale, because its other forty-odd
tests are the adversarial no-fit suite and must keep running everywhere.
`epl/tests/test_shots.py` is PLATFORM-bound, not archive-bound: its autouse
fixture calls `/usr/bin/xcrun`, because the H′ harness contains its workers with
`sandbox-exec` and pins its runtime closure to Homebrew paths, so all 409 of its
tests reported as setup errors on ubuntu. Those bytes are frozen and may not
gain a skip, so the exclusion is stated in `.github/workflows/ci.yml` with its
reason; that module's release bar runs at freeze time on the Darwin release host
and its receipt is committed at `reports/evidence/epl_shots/harness_manifest.json`
(schema `epl-shots-harness-manifest-4`, `canary_receipt.counts` 43 collected /
43 passed / 0 failed, `audit_receipt.pass` true), not inferred from this job.

**Measured, both roots, before the commit.** The dataless figure is the EPL job's
own pytest line — all nine `--ignore` flags — run against a fresh clone that has
no `data/` directory at all, which is the only honest way to predict a runner:
the audit of 2026-08-25 was fooled once by a sandbox whose package root still saw
the archive, and that lesson is kept.

| | before (`ce80325`) | after |
|---|---|---|
| CI, EPL job (run `33485886709`) | 1204 passed, **28 failed, 410 errors** | — |
| dataless simulation, EPL job's exact line | 1204 passed, 83 skipped, **28 failed, 1 error** | **1172 passed, 144 skipped, 0 failed** |
| local `pytest epl/tests` (full, `data/` present) | — | 2000 passed, 66 skipped, 1 failed |
| local `pytest` (root suite) | — | **1679 passed, 0 failed** |

The simulation is faithful, and the middle row is the evidence for that claim:
run against `ce80325` it reproduces the runner's EPL job exactly — the same 28
failures and the same single error, with the 409 `test_shots` setup errors
accounted for by the ninth `--ignore` the same line carries.

`1204 + 83 + 28 + 1` and `1172 + 144` are both **1316**, so nothing was dropped
from collection. The 61 new skips break down, from `-rs`, as **56** on the stage
guard, **4** `@archive_backed` and **1** in `test_walkforward_evidence.py`. Of
those 61, twenty-nine were the red ones. **The other thirty-two were passing, and
saying so plainly matters more than the green tick does:** they are `@concluded`
pre-freeze lifecycle tests that pass ONLY where `data/` is absent, and the
release host has skipped every one of them since the cure above. CI was running
thirty-two tests the record already calls history, and getting a pass out of
them because the runner could not see the run. Making the two machines agree is
the whole change; the thirty-two do not become weaker by being named, they stop
being counted twice under two different meanings.

The one local red is `test_shots.py::test_public_effect_calls_require_live_h_and_k_before_writers`,
and it is **not this work**: it asserts `data/epl/fit/shots_sot` does not exist,
and on this host a real shots run has created it. It fails identically at
`ce80325` with every change here stashed. It is a fact about this machine's
artifact directory, inside frozen bytes that may not be edited to accommodate it,
and it is recorded here rather than quietly carried.
