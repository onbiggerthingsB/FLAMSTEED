# EPL shots/SOT challenger — preregistration Amendment 2

**Written and owner-approved:** 2026-09-01

**Applies to:** `reports/epl_shots_prereg.md` at commit
`20dbd59ef784a932473aa2768d8f34d418ea00cf`, as amended by
`reports/epl_shots_prereg_amendment_1.md` at commit
`bd7431295a1b366a86324ca00e85a8fe524e2876`
(tree `dee4fcf2c4cfc9301e87a1badd50198f9eef4854`)

**Lifecycle point:** prospective amendment before the replacement harness
freeze `H'`; no real native training prediction, coefficient fit, decision
prediction, scoring, or result artifact existed when this ruling was made, and
the superseded freeze computed none. No fit, prediction, or decision-period
outcome read has occurred at ruling time.

The owner approved this amendment with the following ruling:

> replacement H, disregard codex

Ruled 2026-09-01 as option (a) of the presented dispositions: the superseded
freeze is replaced by a new freeze `H'` rather than patched in place or left
standing, and the Codex review channel is disregarded for this decision by
explicit owner instruction. Except for the changes below, the original
preregistration and Amendment 1 remain binding. This amendment is committed as
parent-state governance before `H'`. The `H'` manifest and verifier must bind
both this amendment's exact commit and its SHA-256; a working-tree copy or an
uncommitted ruling is not sufficient.

## B1. The superseded freeze and its three disclosed defects

Freeze commit `c315ab1ee9317ce3a14db5055a8501291ee6d93e` (`epl(shots): H — the
harness, frozen`) is superseded. Its own post-freeze honest report disclosed
three defects, reproduced here exactly as reported:

1. **D1 — the scaffold test is not freeze-aware.**
   `epl/tests/test_shots.py::test_runner_state_and_public_effect_signatures_are_built_but_unfrozen`
   (~line 1964) asserts pre-H-only state (`not h_manifest_present`,
   `not h_frozen`, `issues == ()`), so the frozen suite read 393 passed /
   1 failed forever once the manifest existed.

2. **D2 — ten durable-state taxonomy conversions are unexecuted.** Only 4 of
   14 durable-state taxonomy conversions are executed by tests; uncovered
   lines in `epl/shots_harness.py`: 8835, 8866, 8966, 11211, 11269, 11298,
   12021, 12069, 12566, 12595 (all strictly stricter conversions; unproven).
   The first adversarial mutation (line 8835) left the suite green.

3. **D3 — the audit receipt cannot disclose, and `BUILD_STATE` is stale.**
   `shots._validate_audit_receipt` hard-requires `defects == []`, so a valid
   manifest structurally cannot carry a disclosed non-blocking defect; also
   `BUILD_STATE` reads `"BUILT_UNFROZEN_PRE_H"` inside frozen bytes (stale
   but gate-inert).

The defects are procedural and evidential; none is a change to the
preregistered model, data, bars, or refusal semantics, and none arose from or
enabled any real-data fit, prediction, or outcome read.

## B2. Supersession lineage

1. The superseded freeze commit `c315ab1ee9317ce3a14db5055a8501291ee6d93e` is
   preserved, unrewritten, under tag `shots-h-superseded`; nothing in its
   history is deleted.
2. `main` was reset to the Amendment 1 governance commit
   `bd7431295a1b366a86324ca00e85a8fe524e2876` (tree
   `dee4fcf2c4cfc9301e87a1badd50198f9eef4854`), which is artifact-free.
3. The three audited candidates were restored to the working tree, untracked
   and byte-identical to the superseded `H`:
   - `epl/shots.py`
     `084474212ca3d868a6cfee93c89c1b1d546598cc6bc35dcf921b96fe8ba589b7`
   - `epl/shots_harness.py`
     `3241dabb4a903257787b3e1874ab671cb1c9632149ca82d77763e81934136e10`
   - `epl/tests/test_shots.py`
     `4ce706465e6ca9789ac3cb2069688381ecaba664d1f031aed332e92481c9a270`
   The release-bar command reads 394 passed / 0 failed / 0 skipped at this
   state.
4. The replacement freeze `H'` will be the direct child of this amendment's
   commit, mirroring `H`-as-child-of-Amendment-1: governance first, alone;
   then the freeze from that exact artifact-free parent.

Disclosed for the freeze phase: the candidate bytes currently pin the freeze
parent and amendment binding to the Amendment 1 commit
(`AMENDMENT_1_COMMIT`/`AMENDMENT_1_TREE` and the parent gates in
`shots.make_harness_manifest` and `shots.harness_manifest_status`). Re-binding
those gates to this amendment's commit is freeze-phase work outside the three
riders below and requires the owner's freeze authorization naming this
amendment; this amendment discloses the fact and authorizes nothing beyond B3.

## B3. Scope of the permitted candidate changes

Exactly three riders are permitted against the restored candidates before
`H'`. Nothing else in the three files changes: shots feature math, parsing,
refusal semantics, and every preregistered frozen constant — raw and corpus
digests, schedule identities and row/block counts, half-life, kappa, feature
names, bootstrap seeds and `N_BOOT`, the probability and optimizer tolerances,
and the canary plan — are untouched.

1. **Rider 1 (cures D1).** The scaffold test becomes freeze-aware: it asserts
   the pre-`H'` readings when no committed manifest exists and the correct
   frozen-state readings (`h_manifest_present`, the `h_frozen` reading a bare
   inspection legitimately reports, and the issues the frozen state
   legitimately carries) when the committed manifest is present. The suite
   must be green on both sides of the freeze, proven by running it in both
   states.

2. **Rider 2 (cures D3).** `shots._validate_audit_receipt` accepts a typed
   defects list (each entry a severity plus text); disclosed non-blocking
   defects may ride in a valid manifest, while any blocking defect still
   refuses the freeze. The audit-receipt schema id is updated to name the new
   shape. The build-state reading becomes honest across the freeze boundary:
   derived from the live gates at inspection time rather than asserted by a
   constant, so no frozen byte claims the harness is unfrozen. Each change
   lands red-test-first.

3. **Rider 3 (cures D2).** Red tests are added exercising all ten uncovered
   durable-state taxonomy conversions (the `epl/shots_harness.py` lines listed
   in B1, located by their current text). Each test drives the actual
   production path into the conversion's crash/resume state and asserts
   `ManualReconciliationRequired`; each is verified red against a locally
   reverted conversion before being trusted. After this rider all 14
   conversions are executed by the suite.

## B4. Write set and lifecycle effect

This amendment authorizes one additional pre-`H'` governance path:
`reports/epl_shots_prereg_amendment_2.md`. Its governance commit must be the
direct child of the Amendment 1 commit and contain no harness, coefficient,
prediction, score, or result artifact. The subsequent `H'` commit still adds
exactly the three audited harness files and
`reports/evidence/epl_shots/harness_manifest.json` from that artifact-free
parent. The later K and decision write sets and the requirement to publish
regardless of sign are unchanged.

Approval of this amendment authorizes curing the three defects within the B3
scope and then completing and freezing the replacement harness. It does not
authorize the real post-`H'` training run. That run still requires a separate
owner authorization naming the committed `H'`.
