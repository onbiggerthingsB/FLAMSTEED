# EPL shots/SOT challenger — preregistration Amendment 3

**Written and owner-approved:** 2026-09-01

**Applies to:** `reports/epl_shots_prereg.md` at commit
`20dbd59ef784a932473aa2768d8f34d418ea00cf`, as amended by
`reports/epl_shots_prereg_amendment_1.md` at commit
`bd7431295a1b366a86324ca00e85a8fe524e2876` and
`reports/epl_shots_prereg_amendment_2.md` at commit
`d4d2ce3d7b5fcb84545e83fed7cd4846129cad70`, against the frozen harness
`H' = 3bcc893e8cef73a2e43abd43d3c48f9091e911c5`
(manifest SHA-256
`0e907e61e2135e36195f902c65b220ae465bb186a06dc2b9dcdc62e195f60c16`)

**Lifecycle point:** prospective amendment after the blocked H'-era training
run. No native training block, coefficient fit, K manifest, decision
prediction, score, or result artifact exists. The blocked run read no
decision-period outcome, market value, or scoring row; it stopped inside its
own sandbox before any model output was produced. The owner's item-1
authorization (2026-09-01, preserved at the session scratchpad as
`training_authorization_2026-09-01.md`) authorized "the fixed
2015/16–2018/19 training partition, once; the single eight-coefficient tilt
fit; content-addressed training artifacts; the K freeze — against frozen H'"
and, per the controller's announcement the owner accepted, now re-points to
the replacement freeze `H''` that this amendment prepares. It still does not
authorize the decision run, decision-period outcome access, or any bet, and
per §C7.6 below a new, separate owner authorization must name the committed
`H''` before the first real H'' training invocation.

## C1. The blocked run, quoted

The harness was invoked twice with the byte-identical authorized command
(`train --h 3bcc893e8cef73a2e43abd43d3c48f9091e911c5`; BLAS pinned to one
thread; the harness's own native containment built and pinned the child
sandbox itself). Both attempts exited 75 (`INTERRUPTED`, a
`NonPublishingRunStop`, explicitly not one of the publishable training
refusals). Not one byte of the frozen harness changed, before or after.

Attempt 1 (pid 35057), stderr in full:

> INTERRUPTED NativeWorkerSandboxStop: native sandbox preflight resource
> monitor refused: native process-group ownership monitor output is malformed

Attempt 2 (pid 37266), stderr head and tail as preserved:

> INTERRUPTED NativeWorkerIOFailure: historical native worker exited 1:
> Traceback (most recent call last):
>   File ".../pytensor/link/c/lazylinker_c.py", line 66, in \<module\>
>     raise ImportError(
> ImportError: Version check of the existing lazylinker compiled file.
> Looking for version 0.32, but found None. Extra debug information:
> force_compile=False, _need_reload=True
> ...
>   File "/private/tmp/epl-shots-native-47gsin4r/parent/epl/walkforward.py", line 197, in _one_cutoff
>   File "/private/tmp/epl-shots-native-47gsin4r/parent/epl/dcfit.py", line 270, in fit_epl
>   File "/private/tmp/epl-shots-native-47gsin4r/parent/src/wcmodel/model/inference.py", line 69, in sample
>   ...
>   File ".../pytensor/link/c/cmodule.py", line 2382, in compile_args
>     if int(platform.mac_ver()[0].split(".")[0]) >= 15:
> ValueError: invalid literal for int() with base 10: ''
> The above exception was the direct cause of the following exception:
> Traceback (most recent call last):
>   File "\<string\>", line 450, in \<module\>
> NativeSemanticRefusal: native model fit refused with
> builtins.ValueError: invalid literal for int() with base 10: ''

Attempt 1 was a preflight monitor fault that could not be reproduced in 100
targeted probes; per prereg §8.5 the identical command was re-invoked once
and the fail-closed harness accepted the resume. Attempt 2 then hit the
deterministic wall: the deny-default worker sandbox exposes no macOS system
subtree, so `/System/Library/CoreServices/SystemVersion.plist` is unreadable,
`platform.mac_ver()` returns `('', ('','',''), '')` inside the worker, and
the pinned PyTensor's `compile_args()` performs an unguarded `int('')`. The
per-run fresh `base_compiledir` guarantees the cold C-linker path on every
run, so this fires on the first native training block of every future run.
No lawful remedy existed under the run authorization: every cure edits frozen
bytes, so the run was correctly returned BLOCKED for an owner ruling and this
amendment.

## C2. The ruling: the Codex matrix is adopted

The owner-commissioned Codex `gpt-5.6-sol` ULTRA review of the blocked run
(scratchpad `codex-rev/train_blocked_answer.md`, 2026-09-01) is adopted as
the ruling for this amendment. Its verdict, cited verbatim:

> The attempt-2 root cause is proven, but the proposed plist-only Amendment 3
> is incomplete. A one-cycle repair needs:
>
> 1. Exact `SystemVersion.plist` read access.
> 2. Exact execution of CLT `ld-classic`.
> 3. Exact execution of CLT `dsymutil`.
> 4. Execution of generated probes only under the fresh `runtime/tmp`.
> 5. Exact `/dev/null` write access.
> 6. An explicitly pinned PyTensor `compiledir`.
> 7. A cold, production-path synthetic smoke gate.
> 8. A rewrite of the process-group monitor.
> 9. An explicit disposition of the H′-bound interrupted-run state before
>    any H″ training.
>
> Do not grant `/System`, `/System/Library`, `/usr/lib`, dyld-cache paths,
> general CLT execution, shells, or host temp directories.

The matrix's corrections are accepted as findings of record: the operative
allowlist is the SBPL profile builder, not `_NATIVE_SEALED_READ_ROOTS`
(which stays `()` and stays validated empty); the lazylinker "found None"
ImportError is normal cold-cache control flow; the failure is per fresh
sandbox runtime, not literally per block; and the parent's
`NativeWorkerIOFailure` classification was appropriate.

## C3. The nine items in scope

Exactly the following changes to the three candidate files
(`epl/shots.py`, `epl/shots_harness.py`, `epl/tests/test_shots.py`) are
authorized before `H''`, each red-test-first where testable. Shots feature
math, parsing, refusal taxonomy, and every preregistered frozen constant of
the experiment (raw and corpus digests, schedule identities and counts,
half-life, kappa, features, seeds, `N_BOOT`, tolerances, optimizer, canary
plan, decision bars) are untouched.

1. **Exact `SystemVersion.plist` read.** A new exact-literal system-read
   contract field (`system_read_literals`) carrying exactly
   `/System/Library/CoreServices/SystemVersion.plist`. The runtime lock
   binds the file's regular-file, non-symlink identity, mode, size, and
   SHA-256; the SBPL profile grants `file-read-data` and metadata for the
   exact literal (ancestor metadata only via the existing literal-ancestor
   mechanism, never a `subpath` rule). `_NATIVE_SEALED_READ_ROOTS` is not
   altered. The smoke gate probes `platform.mac_ver()` against the lock and
   proves the sibling `/System/Library/CoreServices/iOSSystemVersion.plist`
   stays denied.
2. **Exact `ld-classic` execution.** The CLT
   `/Library/Developer/CommandLineTools/usr/bin/ld-classic` joins the
   selected-tool set: resolved inside the approved developer root,
   exact-literal `process-exec`, hash-bound in the runtime lock (observed
   now at `76e14451cc95c19caee443f21a242cf3d925bb3f7a9b2b8e8761833f55ff5575`;
   the freeze regenerates the binding). Confirmed by `clang++ -###` reading
   and by a real link inside the candidate sandbox (the smoke).
3. **Exact `dsymutil` execution.** Likewise
   `/Library/Developer/CommandLineTools/usr/bin/dsymutil` (observed now at
   `e8637402b52ed9be1cb173ace2be1988bfdb399871c67ffe0d6396bfedd6a6bb`). The
   smoke requires a `.so.dSYM` under the candidate runtime.
4. **Generated execution only below `<runtime>/tmp`.** `process-exec` on
   the subpath `<runtime>/tmp` and nothing else generated: sandbox-
   inherited, same process group, same quotas. The smoke proves generated
   execution outside `<runtime>/tmp` is denied.
5. **Exact `/dev/null` write.** `file-write-data` on the literal
   `/dev/null`, an inert exact-device grant.
6. **Pinned compiledir.** `PYTENSOR_FLAGS` pins both
   `base_compiledir=<runtime>/pytensor` and
   `compiledir=<runtime>/pytensor/compiled`; the worker asserts the
   compiledir begins empty. This kills the ambient platform-derived
   directory naming and the `uname`/`file` dependency; neither executable
   is granted.
7. **The smoke gate** (§C5): a cold, production-path synthetic fit through
   the real sandbox, wired as a freeze precondition inside the harness.
8. **The process-group monitor rewrite** (matrix §5): one process-group-
   scoped snapshot (`/bin/ps -o pid=,pgid=,stat=,rss= -g <leader>`, selector
   validated against the pinned Apple `ps` at every launch), used for both
   ownership and RSS; canonical positive unique PIDs, every returned row's
   PGID must equal the owned group, mandatory leader row; `H` is live, `Z`
   is exited/zombie; a `?` state or a live RSS of `0` gets exactly 3
   bounded retries 0.05 s apart and then fails closed; diagnostics are
   bounded to the owned-group rows and reason, never the host process list;
   tests cover `H`, `Z`, `?`, live-zero RSS, missing leader, wrong PGID,
   duplicate/malformed rows, churn, zombie closure, and nonzero `ps` exit.
9. **The interrupted-state disposition** (§C6) and the stage-aware
   conversion of
   `test_public_effect_calls_require_live_h_and_k_before_writers`: the test
   reads its stage from the committed bytes (the committed H manifest's
   presence, the same reading Amendment 2 Rider 1 froze for the scaffold
   test), asserts the refused public-effect calls change nothing in any
   stage, and asserts outright namespace absence only in the pre-H stage.

Schema identities move with the shapes they name: the runtime lock to
`epl-shots-native-runtime-lock-3`, the sandbox contract to
`epl-shots-native-sandbox-contract-4`, the sandbox run receipt to
`epl-shots-native-sandbox-run-4`, the harness manifest to
`epl-shots-harness-manifest-5`, the receipt subject to
`epl-shots-pre-h-subject-4`, and the new smoke receipt is
`epl-shots-h-candidate-smoke-receipt-1`.

## C4. Explicit non-grants

Adopted verbatim from the matrix and binding: no `/System`, no
`/System/Library`, no `/usr/lib` file grants, no dyld/cryptex cache trees,
no general CLT execution, no CLT external `as`, no `codesign`,
`codesign_allocate`, `libtool`, `nm`, `lipo`, `dwarfdump`, or
`install_name_tool`, no `/usr/bin/uname`, no `/usr/bin/file`, no
`/usr/bin/env`, no `/bin/sh`, no `/bin/zsh`, no `/private/var/folders`,
`/var/tmp`, `/tmp`, or broad `/private/tmp`, no locale or timezone trees, no
resolver files, certificates, keychain, or Mach services, no `/dev/random`
or `/dev/urandom` file grants, no new `xcrun` authority, no `subpath` rule
for the plist, no network, and no write outside the per-run runtime. The
plist, `ld-classic`, `dsymutil`, and `/dev/null` grants are inert with
respect to repository reads, outcome-data reads, and network authority; the
`<runtime>/tmp` execution grant is the only meaningful expansion and stays
inside the group/quota/closure regime above.

## C5. The smoke-gate law

**`H''` cannot freeze unless a cold synthetic production-path fit has
survived the real sandbox.** `make_harness_manifest` requires a smoke
receipt; a missing, stale (candidate digests differing from the files being
frozen), or failed receipt makes the freeze impossible, and
`harness_manifest_status` re-validates the embedded receipt thereafter.

The smoke runs in a fresh disposable workspace under the real
`sandbox-exec` profile built from the live candidate contract, with the
production parent archive materialized exactly as in a real run, and:

1. **Cold identity:** empty `base_compiledir` and empty explicit
   `compiledir`; `platform.mac_ver()` equal to the runtime lock's
   ProductVersion; the exact locked CXX and SDK; BLAS resolution asserted
   (`-framework Accelerate` present in `blas__ldflags`, no silent
   fallback).
2. **Cold module build:** compile, link, load, and execute a C-linked
   PyTensor function; the module `.so` and its `.so.dSYM` must exist under
   the runtime compiledir.
3. **Real model path, synthetic data only:** a deterministic synthetic
   panel — seed `20260901`, four teams (`smoke_alpha`, `smoke_beta`,
   `smoke_gamma`, `smoke_delta`), 36 internally consistent pre-cutoff
   matches labeled season `2015/16` and one scored synthetic block of two
   fixtures labeled `2016/17` — through the actual route
   `walkforward.matchweek_cutoffs → walkforward._one_cutoff →
   dcfit.fit_epl → inference.sample` with the production likelihood,
   backend (ADVI), seed (20260611), and transformations; only the
   smoke-specific counts are reduced and frozen here: `advi_iters=1500`,
   `draws=200`, `tune=200`. No real raw file, corpus row, or outcome may be
   readable or read during qualification.
4. **Write path:** the synthetic store, feature cache, compiler cache/temp
   tree, and a canonical worker result written under the runtime; at least
   one written result is reopened and hash-verified. `data/epl/fit/shots_sot`,
   the K namespace, optimizer artifacts, and every real raw or
   decision-period file stay untouched.
5. **Scientific assertions:** finite posterior health (`all_finite`,
   `sigma_positive`, `home_adv_sane`), valid team/fixture identities, finite
   strictly-positive probabilities with row sums within `1.5e-8`.
6. **Containment negatives, inside the same profile:** canonical checkout
   read denied; the `/System/Volumes/Data` alias of the checkout denied;
   the decision sentinel `data/epl/fit/walkforward_predictions.parquet`
   denied; a write outside the runtime denied; numeric IPv4 and IPv6
   connects denied; IPv4 and IPv6 binds denied; a Unix-socket connect
   denied; the plist sibling denied; generated execution outside
   `<runtime>/tmp` denied. Actual connect/bind denial is required.
7. **Closure:** process-group closure with no surviving descendant, the
   resource ceilings observed, no unexpected symlink in the final runtime
   snapshot, and a clean runtime tree snapshot.

The receipt (untracked working file at
`reports/evidence/epl_shots/h_candidate_smoke_receipt.json`, embedded into
the `H''` manifest at freeze, never separately committed) binds: the three
candidate source digests, this amendment's commit and SHA-256, the runtime
lock SHA-256, the contract SHA-256, the profile (policy) SHA-256 and
environment, the synthetic-fixture digest, the exact child executable set
and the generated-exec subtree role, the BLAS/compiler decisions, the
outputs and their digests, the observed resource maxima, every negative
control, the closure/cleanup findings, and `passed`.

Iterative synthetic candidate qualification before the single `H''` freeze
is expressly authorized: refine the unfrozen candidate until the complete
cold path is clean, then freeze once. All real training data is forbidden
during qualification. This amendment authorizes running the smoke gate
itself pre-freeze, by name, in the same session that implements it.

## C6. Disposition of the H'-era interrupted state

1. H''s real run is declared nonpublishing and blocked; no fit,
   coefficient, K, or scientific result exists or may be claimed from it.
2. `H'` is superseded for future execution. Cross-H resume is prohibited:
   no `H''` invocation may adopt, resume, or reproduce the H'-era
   transaction, intent claim, or run lock, and the harness refuses (typed,
   before any write) when the active namespace carries a transaction bound
   to a different H.
3. The four preserved H'-bound files are interrupted-run evidence:

   ```text
   2026e85677fe846215476fb8efbc1dce5106de75dff0e156223a920a52758fb0  272629  native-intent-2026e8....json
   7daaef0f0f88450a1145c4ceb8a2e408f6f9a6f2dafbfca6aed8bc982c72dadf     146  .experiment-transaction.lock
   2d6cf9fbc9ee23d95917a8d44d48f82ccc1a515b7f23f36ca942f9b28c0e0035      65  .native-intent.claim
   60fe34bbb204f0ca63c7890596d3bdb1450799e76de09390ae1d29e953297bc2      30  .native-run.lock
   ```

   They are moved, digest-verified before and after, out of the active
   namespace to
   `data/epl/fit/shots_sot_interrupted/h-3bcc893e8cef73a2e43abd43d3c48f9091e911c5/`
   under a `disposition_receipt.json`
   (schema `epl-shots-interrupted-run-disposition-1`) binding all four
   digests and byte counts, `H'`, its manifest SHA-256, and this
   amendment. The active namespace `data/epl/fit/shots_sot/` must be empty
   (absent) when the first `H''` training invocation begins. This
   amendment authorizes exactly this quarantine namespace as an additional
   write path; both paths remain uncommitted (`/data/` is gitignored).

## C7. The H''-parent contract

1. `H''` must be the **sole direct child of this amendment's governance
   commit**. This amendment is committed alone, before any candidate byte
   edit; the freeze-parent gates in the candidate bytes are re-bound from
   Amendment 2 to this amendment's exact commit and tree, in scope this
   time, and the identity snapshot, receipt subject, and every manifest
   machine that binds the amendment chain binds Amendments 1, 2, and 3
   together.
2. Unlike the Amendment-2 lineage (whose parent was artifact-free and whose
   `H'` added its four paths), this amendment's tree lawfully carries the
   four H'-era freeze paths, byte-identical to `H'` — the record of what
   `H'` was. The parent gate therefore requires: within the pre-H forbidden
   namespaces the parent tree contains exactly
   `reports/evidence/epl_shots/harness_manifest.json`, byte-identical to
   the `H'` manifest (SHA-256 `0e907e6…f60c16`), and nothing else; and the
   parent's three candidate source files are byte-identical to their `H'`
   blobs. `H''` **modifies** exactly the four freeze paths (changed set ==
   the three sources plus the manifest; added set empty). `H'` and its
   history are not rewritten.
3. K verification remains parametric in the live verified H:
   `verify_coefficient_freeze_live` requires K to be a single-parent direct
   child of the H named at invocation, which after this amendment's freeze
   is `H''`, never `H'`.
4. K staging law: `.gitignore`'s `/data/` rule silently drops the K
   artifacts from a plain `git add`. The K commit must stage them
   explicitly (`git add -f` on the manifest-listed paths, or plumbing-built
   index) and verify the staged set equals the manifest's artifact set plus
   the K manifest before committing.
5. The full release bar (the exact H test command and the full `epl` suite)
   must be green before and after constructing the `H''` manifest.
6. A new, separate owner authorization naming the committed `H''` is
   required before the first real H'' training invocation. This amendment
   authorizes candidate surgery, synthetic qualification, and the freeze —
   not the real run.

## C8. Write set and lifecycle effect

This amendment authorizes: this governance file
(`reports/epl_shots_prereg_amendment_3.md`, committed alone as parent-state
governance); working-tree edits to the three candidate files within §C3;
the regenerated `reports/evidence/epl_shots/harness_manifest.json` at the
`H''` freeze; the untracked smoke receipt at
`reports/evidence/epl_shots/h_candidate_smoke_receipt.json`; and the
uncommitted disposition namespace of §C6. Nothing else: no `src/`, no
`scripts/`, no production wiring, no existing report edit. The later K and
decision write sets and the requirement to publish regardless of sign are
unchanged. Approval of this amendment authorizes curing the blocked run's
nine items within this scope, qualifying the candidate synthetically, and
freezing `H''`. It does not authorize the real post-`H''` training run.
