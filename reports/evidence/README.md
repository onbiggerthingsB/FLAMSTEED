# Committed evidence — the anchoring and freshness experiments (2026-08-26)

Both experiments shipped their verdicts as prose while every machine artifact
behind them sat in `data/`, which this repository gitignores in full (`git
ls-files data/` returns **zero** files). A reader could not check a single
number. This directory is the fix: the canonical, committed copies of what the
two runs actually produced, small enough to live in git, complete enough to
recompute both headline results.

Nothing here is a new measurement. Every file is a copy or a lossless
projection of an artifact the runs already wrote.

## What is here

| File | Rows | What it is |
|---|---:|---|
| `anchoring.json` | — | `data/epl/fit/anchoring.json`, **verbatim**. The machine-readable market-prior verdict: estimand, both bootstrap CIs, the LOSO selection, the six folds, strata, saturation diagnostic, movement, power. |
| `anchoring_per_fixture.csv` | 11,400 | The per-fixture ledger of the anchoring experiment, projected from the four shard ledgers: `key, match_id, season, block, cutoff, w, home_key, away_key, y, rps_arm, rps_native, delta`. 2,280 fixtures × the five **fitted** weights. |
| `anchoring_fold_grids.csv` | 66 | Every fold's mean RPS at every grid weight, with the selected `w` marked — for **both** selectors: `loso` (the published one) and `past_only` (the U2 correction; see the result document's dated note). |
| `freshness.json` | — | `data/epl/fit/freshness.json`, **verbatim**. |
| `freshness_per_fixture.csv` | 1,699 | The per-fixture paired deltas of the freshness sweep with their block labels: `key, match_id, season, block, date, cutoff, block_cutoff, staleness_days, home_key, away_key, y, rps_fresh, rps_block, delta`. |
| `MANIFEST.sha256` | 22 | SHA-256 **and byte size** of every local artifact behind both runs — the ones too bulky to commit. Format: `<sha256>  <repo-relative path>  <bytes>`. |

### Why `w = 0.00` has no rows

§2.4 of the anchoring preregistration puts `w = 0.00` on the grid and spends
**no fits** on it: `z_blend(0)` *is* `elo_z`, so Arm A is Arm B and the pinned
corpus already holds that row. Hence 11,400 = 2,280 × 5, not × 6. A season the
selection prices at `w = 0` contributes a delta of exactly `0.0`.

## Recomputing the headline numbers

`anchoring_per_fixture.csv` + `anchoring_fold_grids.csv` reproduce the
anchoring estimand and both dated corrections with arithmetic alone — no fits,
no model, no `data/`:

* **the published estimand**: price each fixture at its season's `loso`
  selected `w`, average `delta` over the 2,280 → **−0.000193**.
* **the past-only selector (U2)**: price each fixture at its season's
  `past_only` selected `w` → **−0.000295**.
* **the fold grids**: the `fold_mean_rps` column is what the selection
  minimised, one row per (selector, season, w).

`freshness_per_fixture.csv` reproduces the freshness estimand the same way:
average `delta` over the 1,699 → **−0.000216**, and the staleness strata are
`groupby(staleness_days)`.

The bootstrap CIs need the block labels, which is why `block` is a column in
both files: the primary blocks are `(season, ISO week)` — the `block` column
literally — and the secondary blocks are `season`.

## The manifest, and what it is for

`MANIFEST.sha256` names the artifacts that stayed local because they are too
large for git (~71 MB, dominated by the four 17 MB anchoring shard ledgers).
It lets anyone holding those files prove they hold *these* files. Two entries
are load-bearing and appear in the published prose:

    da685cf4c8ae8a87da087ba8e5ef649e42181d1e3576c56ae5dc641a5ac0630e  dc_market_prior_predictions.parquet
    f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a  walkforward_predictions.parquet

The second is the **pinned corpus** — the same digest two standing
preregistrations check in code.

## Off-machine mirror — PREPARED, NOT PUSHED

The bulky originals were prepared for the private vault
(`onbiggerthingsB/flamsteed-vault`, the destination the owner named on
2026-08-13, per `docs/obligations.md`) under
`data/epl/fit-evidence-2026-08-26/`, following the established drill:

* **22 files, 71 MB** staged: both sets of shard ledgers, both sets of run
  logs, all preconditions (canary, odds-canary, control, and the freshness
  **pre-freeze audit** control), both verdict JSONs, the predictions parquet
  and the pinned corpus.
* **`MANIFEST.sha256` extended** in the vault's own established format
  (`<sha256>  ./<path>`), 2,574 → 2,596 lines, and **verified 2,596 / 2,596**
  before any push was attempted.
* **Secret-scanned with a working positive control.** The control earned its
  keep: the first scanner pattern carried a typo (`{16]`), which made `grep`
  error out and report **zero hits on the payload** — a clean-looking result
  from a scanner that had not run. The control caught it. Re-run corrected:
  control fires (2 hits, 1 file), payload **0 hits, 0 files**, and no `.env`,
  key, or credential file present.

**The push did not happen.** It was refused by this environment's permission
system, and that refusal was not worked around. The vault therefore still
stands at commit `426eed7` — the same commit
`reports/epl_sim_amendments.md` already records — and carries **none** of the
2026-08-26 fit evidence.

**This is an open obligation.** The bulky originals exist on one machine only,
exactly the single-point-of-failure the backup obligation exists to close. To
finish it, an operator with push rights runs the staged commit; the payload,
the extended manifest and the clean scan are all reproducible from this
repository plus `data/`. When it lands, the vault commit hash belongs in a
dated note appended below this line.

## Provenance

Built by pure projection from the run artifacts on 2026-08-26. The two CSVs
carry full float `repr` — no rounding — so a recomputation matches the
published numbers to the last bit rather than to a printed precision.


## Vault push — completed (2026-08-27)

The obligation recorded above is closed: the 22-file / 71 MB originals are on
github.com/onbiggerthingsB/flamsteed-vault at commit **482c1fa**
(426eed7 → 482c1fa, ls-remote verified), under
`data/epl/fit-evidence-2026-08-26/`, with MANIFEST.sha256 extended
2,574 → 2,596 and re-verified 2,596/2,596 before the push.


## The evidence-mass widening experiment — its census and its adversarial record (2026-08-29)

Seven files here belong to a **third** experiment,
[`reports/epl_widening_prereg_v3.md`](../epl_widening_prereg_v3.md), and they
arrived before its run rather than after it. Nothing among them is a new
measurement.

| File | Bytes | What it is |
|---|---:|---|
| `widening_parity_feasibility.json` | 18,128 | `data/epl/sim/evwiden_parity_feasibility.json`, **verbatim**. The census v2 §8.2's pass 7 measured on 2026-08-28: which of the protected retro stack's 35 cells it can price. v3's whole table leg is scoped by it (v3 §0.6), and `data/` is gitignored, so the bytes are committed here — a scope resting on a file one machine holds rests on that machine. SHA-256 `07ee00d7…`, pinned by v3 §0.1 and bound in its freeze block. |
| `widening_review_round6_codex.md` | 34,866 | Cross-model deciding review of the v1→v2 harness (Codex `gpt-5.6-sol`, ultra). |
| `widening_review_v2_codex.md` | 43,593 | Cross-model deciding review of v2. |
| `widening_review_v2closure_codex.md` | 46,307 | Cross-model review of v2's closure round. |
| `widening_review_round7_codex.md` | 58,297 | Cross-model deciding review of **v3**, pinned to Git objects at HEAD `11159b1`. Verdict: **DO-NOT-FREEZE**. |
| `widening_audit_v2_intree.md` | 15,944 | In-tree adversarial seed audit of the v2 harness. |
| `widening_audit_v3_seeds.md` | 21,691 | In-tree adversarial seed audit of the **v3** harness, 30 seeded defects replayed. Verdict: **FAIL**, 28 of 30 red. |

The last two are the dissent. Both halves of v3 §8.3's required dual audit
reported blocking findings; the owner ruled **ADJUDICATED FREEZE** on
2026-08-29 and v3 §8.9 rules each finding one by one — twenty-three fixed
before the freeze block could render, eight recorded as known limitations under
a stated threat model. The reports are committed **in full and unedited**, with
byte sizes and SHA-256s in v3 §8.9, precisely so that a reader can weigh the
adjudication against what it overruled. They are **not** members of v3 §9.3's
MANIFEST, which is an exact list of the 49 artifacts that run will produce;
these are lineage records of the review that preceded it.


## The E1 (Championship) acquisition — its attestation (2026-08-30)

| File | Bytes | What it is |
|---|---:|---|
| `e1_acquisition.json` | 61,497 | Schema `epl-e1-acquisition-1`. The committed attestation of the once-only E1 acquisition: the twelve fetch digests and byte sizes, the per-season structural validation at (24, 552, 23), the complete 49-spelling club census with every index fold and stable key, the unmapped-name count (**0**), the archive's SHA-256 and 6,624-row count, the E0 archive's **unchanged** digest, and the acquisition timestamps. |

**This is infrastructure, not an experiment.** It was built standalone under the
owner's 2026-08-30 **E1 SPLIT** ruling; `reports/epl_lowerdiv_prereg.md` v2 is
its *design reference* only, that confirmatory experiment **holds** unrun, and
nothing in the file is evidence for or against its hypothesis. No fit, no store
build, no harness.

**Why the file exists at all** is the reason this directory exists: `data/` is
gitignored in full, so `data/epl/matches_e1.parquet` is not committed and a
reader could otherwise check nothing. The twelve source digests plus
`python -m epl.build --division E1` rebuild the archive, and this file is what
they must reproduce.

**It carries no outcome statistic, deliberately, and says so under
`outcome_summary_WITHHELD`.** The commissioning task asked for the E1 goal rate
against E0's — v1 language that v2 deleted as blocking review finding B4 and
that v2 §10 makes an invalidation to publish before the freeze, *"in a §8.10
note or anywhere else"*. The rate was never computed. The field records the
conflict and its resolution rather than hiding either; it `decides: "nothing"`.
