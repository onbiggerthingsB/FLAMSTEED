# Dated note — the shots/SOT REFUSED result, 2026-09-02

This note accompanies [`reports/epl_shots_result.md`](epl_shots_result.md), the
REFUSED result published at commit `428c4cc` under the frozen preregistration
[`reports/epl_shots_prereg.md`](epl_shots_prereg.md) and its three amendments.

**It changes nothing that was published.** No estimate, disposition, refusal
name, stage, message, threshold, coefficient, or count moves. The result
document and its evidence manifest keep the exact bytes `428c4cc` wrote. This
note adds two things `428c4cc` left out: the *bytes* of the evidence it names,
and three values from the optimizer receipt that the rendered result document
has no field for.

---

## 1. Why the note exists rather than an edit

`reports/epl_shots_result.md` and
`reports/evidence/epl_shots/result_evidence_manifest.json` are not editable
documents. The harness re-derives both from durable state on every idempotent
republish — the report from `_render_decision_report`
(`epl/shots_harness.py:13956`), the manifest from the live inventory
(`epl/shots_harness.py:14701-14720`) — and then binds each on disk to those
exact bytes:

* `_write_fixed_bytes_once` / `_write_fixed_canonical_once` fall through to a
  byte-equality bind when the file already exists
  (`epl/shots_harness.py:13912-13933`, `:14725-14727`, `:14760-14762`);
* `_require_fixed_publication_bytes` re-binds both a second and a third time
  (`epl/shots_harness.py:14036-14057`, `:14731-14734`, `:14766-14776`);
* the bind itself, `_durably_bind_decision_entry_at`
  (`epl/shots_harness.py:2079`), refuses on a size mismatch
  (`:2104-2108`, `ManualReconciliationRequired`), on a byte mismatch
  (`:2120-2128`), and — through `_decision_entry_identity`
  (`epl/shots_harness.py:1985-2001`) — on any file that is not one regular
  entry with `st_nlink == 1` and mode exactly `0444`.

Appending a line to either file, or relaxing either file's mode, would
therefore take `epl.shots_harness train --h 0f9ff9b…` off its resume path and
into manual reconciliation. The result document is frozen the way the harness
is frozen. A dated sibling is the only lawful place to put a correction.

## 2. The evidence, now recoverable from a clean clone

`result_evidence_manifest.json` (SHA-256
`746d6d9471bfed4d03f527699800494d8326af6517c741b7779a57b45c5ad871`, 45,033 B)
names six artifacts by content address. All six were written under
`data/epl/fit/shots_sot/`, and this repository gitignores `/data/` in full —
so every digest in the published manifest verified on one machine and on no
other. A byte-for-byte copy of each now lives under
[`reports/evidence/epl_shots_result_receipts/`](evidence/epl_shots_result_receipts/),
which is exactly what `reports/evidence/` exists for: *"Nothing here is a new
measurement. Every file is a copy or a lossless projection of an artifact the
runs already wrote"* — [`reports/evidence/README.md`](evidence/README.md).

| Schema | SHA-256 | Bytes | Original (gitignored) path |
|---|---|---:|---|
| `epl-shots-native-training-intent-1` | `d760b30ed9062fc780a6e5ce3d59b3bc339b21040e384642895906f2ed31b706` | 272,629 | `data/epl/fit/shots_sot/native-intent-d760b30e….json` |
| `epl-shots-native-job-completion-3` | `5f57c56383f1f6a8e539fa68e84e7e7f327a716475eba92e28cb2773a937ed13` | 902,431 | `data/epl/fit/shots_sot/native-completion-5f57c563….json` |
| `epl-shots-feature-moments-2` | `f9ae0c0500b88ff0bf0879db8f1b9d58117038250d94cd6994619d7932a7fc5c` | 531 | `data/epl/fit/shots_sot/feature-moments-f9ae0c05….json` |
| `epl-shots-optimizer-intent-1` | `c6b29706587d96f23a404c9b76dd206ba29d1f48e50e2071ef31432a57e156db` | 909 | `data/epl/fit/shots_sot/optimizer-intent-c6b29706….json` |
| `epl-shots-optimizer-receipt-3` | `7207f9799afe6816ecf142acdc726ce8e0b95c8e78466d26f0bcfc66bf15221e` | 1,631 | `data/epl/fit/shots_sot/optimizer-receipt-7207f979….json` |
| `epl-shots-decision-result-2` | `001e165bd0e8c0b42abbece0aaa344b4f73dd5cdc17e9351529ad4f32ee8e6e5` | 2,106 | `data/epl/fit/shots_sot/decision-result-001e165b….json` |

1,180,237 bytes in total. The copies keep their full content-addressed
filenames, unabbreviated, because the harness parses the digest out of the
filename (`_optimizer_records_at`, `epl/shots_harness.py:9802-9831`) and then
requires `sha256(bytes) == digest` (`_load_optimizer_artifact_at`,
`epl/shots_harness.py:9580-9601`). Renaming a copy would make it
unrestorable.

The 142 `native-block-…` shards are **not** copied. They are counted in the
decision-result terminal (`counts.native_blocks: 142`) but no published
manifest names them individually, and they are not part of the evidence
`428c4cc` promised.

### Restoring the run state on a fresh machine

```
mkdir -p data/epl/fit/shots_sot
cp reports/evidence/epl_shots_result_receipts/*.json data/epl/fit/shots_sot/
chmod 0444 data/epl/fit/shots_sot/*.json
```

`chmod 0444` is not cosmetic: `_decision_entry_identity`
(`epl/shots_harness.py:1985-2001`) refuses any artifact whose mode is not
exactly `0444`, and git records only the executable bit, so a clean checkout
materialises these at `0644`. Restoring the shards is a separate matter — the
142 `native-block-…` files are absent from a clean clone, so a restored tree
can be verified against the published manifest but cannot resume a training
run.

## 3. Three values the rendered result document has no field for

`_render_decision_report` (`epl/shots_harness.py:13956-13996`) emits a fixed
refusal block: name, stage, message, and four `N/A — not computed after
FitFailure` lines. It has no slot for the certificate's arithmetic. These
three values are transcribed verbatim from
`optimizer-receipt-7207f9799afe6816ecf142acdc726ce8e0b95c8e78466d26f0bcfc66bf15221e.json`,
whose digest `428c4cc` already committed inside
`result_evidence_manifest.json`; nothing here is new information, only
information that was previously unreadable without the file.

| Field | Value |
|---|---|
| `gradient_max_abs` | `0.00012105580182988906` |
| `gradient_acceptance_threshold` | `1e-05` |
| `message` (SciPy termination) | `CONVERGENCE: RELATIVE REDUCTION OF F <= FACTR*EPSMCH` |

The surrounding receipt fields, for context and all equally verbatim:

| Field | Value |
|---|---|
| `method` | `L-BFGS-B` |
| `success` / `status` | `true` / `0` |
| `iterations` | `18` |
| `function_evaluations` / `gradient_evaluations` | `21` / `21` |
| `options` | `{"ftol": 1e-12, "gtol": 1e-10, "maxiter": 10000}` |
| `objective_value` / `independent_objective_value` | `1454.4584744361389` / `1454.4584744361389` |
| `gradient_certified` | `false` |
| `gradient_consistent` / `objective_consistent` | `true` / `true` |
| `beta_distance_actual_bound_l2` | `0.00021910411928069718` |
| `beta_distance_acceptance_ceiling_l2` | `2.8284271247461906e-05` |

So: the optimizer converged and the Amendment 1 certificate refused it. The
gradient exceeded its acceptance threshold by a factor of about 12.1, and the
coefficient-distance bound exceeded its ceiling by about 7.7. `FitFailure` was
durably receipted, `K` was never created, and the eight coefficients in the
receipt carry no standing.

## 4. What this note does not decide

The `1e-5` threshold and its `sqrt(8)·1e-5` distance ceiling were written into
Amendment 1 before any optimizer had run. Whether that certificate was
correctly specified, and whether anything should be retested, is not settled
here and is not settleable by a note. The preregistration's closing law
reserves it:

> Any follow-up must start with a new named preregistration that cites this
> result. — `reports/epl_shots_prereg.md`

This note cites the result. It proposes nothing.

## 5. Integrity of the published bytes

For a reader checking that this commit changed nothing published:

| Path | SHA-256 | Bytes |
|---|---|---:|
| `reports/epl_shots_result.md` | `b9e8ee513e886f7b0a0c63980318954e8111d7004c79ec416776251ccd49a07d` | 787 |
| `reports/evidence/epl_shots/result_evidence_manifest.json` | `746d6d9471bfed4d03f527699800494d8326af6517c741b7779a57b45c5ad871` | 45,033 |

Both are unchanged from `428c4cc`. Both must stay unchanged.
