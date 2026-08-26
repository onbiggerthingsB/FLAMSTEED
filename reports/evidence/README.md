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
