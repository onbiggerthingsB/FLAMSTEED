# EPL league-table retrospective — v1.1 R1

**Run:** 2026-08-19 · **Branch:** `epl-probe` · **Season opens:** 2026-08-21
**Preregistered at:** commit `07b5871` — [`reports/epl_sim_prereg_retro.md`](epl_sim_prereg_retro.md), written before the run and before any retrospective number existed beyond the T8 smoke.

This is the execution of the preregistration. It reports what the harness produced, including what it refused to produce. Nothing here decides anything: **there is no pass rule**, and whether `dc_native` remains the published arm is an owner ruling made after these tables exist (§10).

**Standing disclaimers.** Monte-Carlo standard error is reported beside every simulated row and **is not model error** — a tight SE on a badly specified model is still a badly specified model. Scores are per (season, cutoff) and are **never averaged across cutoffs**: the opener and matchweek 19 are different questions. Table positions are table positions; ranks 1, 4, 5, 7 and 17 are not claims about qualification for, or exclusion from, any competition. Every forecast scored here was made at a past cutoff conditional on the strengths at that cutoff staying fixed for the remainder of the season — a named, unmodelled limitation. There is no betting content anywhere in this run: no odds, no market comparison, no stake.

---

## 1. Provenance

**Harness hashes, checked at run time against the preregistration (§1 of the prereg). Both match; R1 is the run that document preregisters.**

| File | SHA-256 at run time | Prereg §1 | Match |
|---|---|---|---|
| `epl/simretro.py` | `2b25ab351710ed140047e56c2463d2cf9cda8996b8bf684732de04143b6cb805` | `2b25ab351710ed140047e56c2463d2cf9cda8996b8bf684732de04143b6cb805` | **yes** |
| `epl/simmetrics.py` | `e73f2f70bdb5dfc42572aa7a5c19af4c5843e376a240e4d335c6edd5d451fb9a` | `e73f2f70bdb5dfc42572aa7a5c19af4c5843e376a240e4d335c6edd5d451fb9a` | **yes** |

| | |
|---|---|
| Commit at run | `07b5871b033bc0e027cc0364d37587f231d8cf5f` |
| Harness schema | `epl-simretro-1` |
| Metrics schema | `epl-simmetrics-1` |
| N (simulated seasons per arm per cutoff) | **20,000** |
| S (posterior draws / particles) | **1,000** |
| Seed | **20260611** — one seed only |
| Bootstrap | **10,000** resamples, percentile CI, resampling seed **20260814**, blocks = seasons |
| Ledger | `data/epl/sim/retro_r1.jsonl` — **fresh path**, 170 rows (166 forecasts + 4 `not_applicable` markers) |
| Wall time, whole run | **307 s** (5.1 min) over 34 completed (season, cutoff) cells |
| Median cell wall time | 8.3 s |
| Verified adjustments required | yes (`require_verified_adjustments=True`) |
| Threads | `OMP/OPENBLAS/MKL/VECLIB/NUMEXPR_NUM_THREADS=1`, serial, one process |

**2026-08-19 correction.** *Commit at run* previously read `e814c0261de068a0d8955e2ebb207406586ee380`, which no branch reaches and whose own commit timestamp (17:59:53) falls after R1 finished: it did not exist while the run executed. R1 ran at `07b5871`, the preregistration commit, and the field now says so. No harness hash and no number in this report changes.

**Fresh ledger, not a resume.** Prereg §10 required R1 to either write to a fresh ledger path or knowingly resume the T8 smoke's ten colliding rows. R1 wrote to a fresh path, so the smoke's ten `run_key`s were recomputed from scratch rather than reused — which is what makes the reproduction check in §9 a check rather than a tautology.

**Where the ledger lives.** `data/` is gitignored in this repository, so `data/epl/sim/retro_r1.jsonl` (4.0 MB, 170 rows) and `data/epl/sim/retro_r1_scores.json` sit on disk beside this report but are **not in the commit**. The report and the preregistration are the committed artifacts. The ledger is reproducible from the harness at the hashes above — same seasons, same cutoffs, same N, same seed — and §9 demonstrates that reproduction on the ten rows where an independent earlier ledger exists to check it against.

**How it was driven.** `epl/simretro.py`'s own CLI refuses anything but `--smoke` by design, so R1 called `simretro.run_retro` directly, once per (season, cutoff), from a throwaway driver that is not part of the harness and is not committed. Calling per cell rather than once for the whole grid is the only orchestration choice made, and it was made for one reason: a refusal the code raises for one cell must not take the other 41 with it (§2). Every parameter passed is a value already fixed in `epl/simretro.py`; one `ArchiveRunner` was built and reused across all cells, which is exactly what a single whole-grid call does. **No harness file was edited** — the hashes above are the proof.

## 2. Coverage, and the holes

The preregistered grid is 7 seasons × 5 comparison cutoffs × (3 arms + 2 nulls) = 175 keys, plus MW28 sanity at 7 × 5 = 35. **R1 did not fill all of it.** Two distinct refusals fired, both of them refusals the code raises on purpose and both anticipated by prereg §12 as documented refusals rather than deletions. They are reported here first, before any score, because a reader who takes the tables below for a complete seven-season result would be reading something that does not exist.

### Hole 1 — 2023/24 refuses entirely: unverified points adjustments

**All 6 cutoffs of 2023/24 refused**, with `UnverifiedAdjustment`, before any fit ran. The three effective points-adjustment rows for that season (`adj-2324-everton-02` −6, `adj-2324-everton-03` −2, `adj-2324-nottm-forest-01` −4) are seeded `verified: false` in `epl/season/points_adjustments.jsonl`.

This is the gate working exactly as designed. Prereg §5: *an unverified adjustment row refuses the season rather than scoring it* — the retrospective must not credit or debit a season against a deduction nobody has checked against the league's published record. Plan D16 and adjudication item 3 both assign that check to **the operator**, against premierleague.com. **R1 did not flip the flag**, and no agent should: setting `verified: true` is an attestation that a human compared the row to the published record, and doing it to unblock a run would convert the guard into decoration.

**Consequence:** the retrospective is **six seasons, not seven** (2019/20, 2020/21, 2021/22, 2022/23, 2024/25, 2025/26). Every bootstrap below has **6 blocks, not 7**, and every 'how many seasons' count below is out of 6.

**Remedy, and its cost:** an operator verifies those three rows against the league's published record, sets `verified: true`, and reruns R1. The ledger is resumable and keyed on the question, so the rerun costs the six cutoffs of 2023/24 and nothing else — roughly a minute of compute.

### Hole 2 — 2 openers refuse: the D11 truncation ceiling

**2 (season, cutoff) cells refused** with `ExcludedMassTooLarge` — the hard 2e-2 ceiling pre-stated in [amendment A1](epl_sim_amendments.md) (D11 v1.0.1 (c)), before any `dc_native` number existed.

| season | cutoff | fixture | particle-mean excluded mass | ceiling |
|---|---|---|---|---|
| 2019/20 | MW0 | man_city v sheffield_united | **0.0234** | 0.02 |
| 2020/21 | MW0 | man_city v leeds | **0.0216** | 0.02 |

Every one is at **MW0** — the opener — and every one is a fixture pairing a strong attack against a **promoted club with no rows in the archive**. This is the same mechanism amendment A1 diagnosed at the 2026/27 opener and named in advance: a cold-start club draws its attack and defence from prior draws, a handful of those draws put the opposing λ above 10, and those particles lose a quarter to a half of their mass past the 10-goal truncation. A1 recorded the forecast that *the tail collapses once the club has fitted rows*. **R1 is the first out-of-sample test of that forecast, and it holds:** the identical (season, club) pairs pass at MW3 and at every later cutoff, three matchweeks later, with no change to anything.

**Consequence:** MW0 is scored on **4 seasons** (2021/22, 2022/23, 2024/25, 2025/26) rather than seven, while MW3 through MW19 have 6. The MW0 column is therefore a **narrower** column than the ones below it, and its block bootstrap has correspondingly fewer blocks. It is labelled with its season count everywhere it appears.

Note what did **not** refuse: other seasons in this window also promoted a club with no archive rows and their openers went through, so the ceiling is not tripped by cold start as such — it is tripped when a cold-start defence draw meets a top attack in the same fixture. And the refusals are confined to the opener: in both affected seasons the very next scored cutoff, MW3, passes, three matchweeks and a handful of results later, with nothing changed. That is A1's forecast holding out of sample.

This is not evidence about which arm is better at the opener. It is evidence that **the published `dc_native` arm cannot always produce an opener forecast for a season containing a club with no archive history** — a capability gap in the shipped model, separate from every arm comparison below, and arguably worth more than the cells it cost.

### The grid, cell by cell

`ok` = five series written · `REFUSED` = the reason named above.

| season | MW0 | MW3 | MW6 | MW10 | MW19 | MW28 (sanity) |
|---|---|---|---|---|---|---|
| 2019/20 | **REFUSED** (ExcludedMassTooLarge) | ok | ok | ok | ok | ok |
| 2020/21 | **REFUSED** (ExcludedMassTooLarge) | ok | ok | ok | ok | ok |
| 2021/22 | ok | ok | ok | ok | ok | ok |
| 2022/23 | ok | ok | ok | ok | ok | ok |
| 2023/24 | **REFUSED** (UnverifiedAdjustment) | **REFUSED** (UnverifiedAdjustment) | **REFUSED** (UnverifiedAdjustment) | **REFUSED** (UnverifiedAdjustment) | **REFUSED** (UnverifiedAdjustment) | **REFUSED** (UnverifiedAdjustment) |
| 2024/25 | ok | ok | ok | ok | ok | ok |
| 2025/26 | ok | ok | ok | ok | ok | ok |

**Filled:** 136 scored comparison rows + 30 MW28 sanity rows + 4 `not_applicable` markers = 170 ledger rows. **Refused:** 8 of 42 cells.

The `not_applicable` markers are `ppg_pointmass` at MW0, undefined before three complete rounds and pre-stated as such in prereg §4. They claim the key so a resumed run does not re-fit to rediscover it; `score_retro` skips them.

## 3. Every metric, per (cutoff, season, arm) — comparison cutoffs

MW28 is **not** in this table; it is in §7. TRPS is primary and unweighted; wTRPS on the published boundaries is secondary; everything else is a diagnostic. `champ -ln p` is floored at 0.5/N and is local — read the zero-hit count in §6 before reading it. `MC SE` is cluster-by-particle Monte-Carlo error on the position matrix and is **not** model error.

| cutoff | season | arm | TRPS | flat TRPS | wTRPS | Brier champ | Brier top4 | Brier top5 | Brier top7 | Brier releg | champ -ln p | pts CRPS | pts MAE | cov50 | cov90 | MC SE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MW0 | 2021/22 | `dc_native` | 0.0882 | 0.1750 | 0.0552 | 0.0995 | 0.0648 | 0.0750 | 0.0617 | 0.0695 | 0.311 | 5.21 | 7.75 | 0.50 | 0.95 | 0.00289 |
| MW0 | 2021/22 | `dc_wdl_bridge` | 0.0885 | 0.1750 | 0.0555 | 0.1100 | 0.0652 | 0.0753 | 0.0624 | 0.0690 | 0.330 | 5.22 | 7.77 | 0.50 | 0.95 | 0.00288 |
| MW0 | 2021/22 | `elo_wdl_bridge` | 0.0941 | 0.1750 | 0.0637 | 0.1762 | 0.0832 | 0.0895 | 0.0503 | 0.0868 | 0.406 | 5.97 | 8.57 | 0.35 | 0.75 | 0.00133 |
| MW0 | 2021/22 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW0 | 2022/23 | `dc_native` | 0.1604 | 0.1750 | 0.1461 | 0.2069 | 0.1971 | 0.1491 | 0.2305 | 0.1436 | 0.414 | 9.52 | 13.09 | 0.30 | 0.70 | 0.00280 |
| MW0 | 2022/23 | `dc_wdl_bridge` | 0.1598 | 0.1750 | 0.1451 | 0.2044 | 0.1956 | 0.1482 | 0.2287 | 0.1426 | 0.413 | 9.50 | 13.06 | 0.30 | 0.70 | 0.00281 |
| MW0 | 2022/23 | `elo_wdl_bridge` | 0.1483 | 0.1750 | 0.1334 | 0.3634 | 0.1831 | 0.1312 | 0.2102 | 0.1245 | 0.564 | 8.99 | 11.69 | 0.30 | 0.45 | 0.00127 |
| MW0 | 2022/23 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW0 | 2024/25 | `dc_native` | 0.1161 | 0.1750 | 0.0684 | 1.3140 | 0.0369 | 0.0508 | 0.1104 | 0.0781 | 2.237 | 8.15 | 11.60 | 0.30 | 0.75 | 0.00302 |
| MW0 | 2024/25 | `dc_wdl_bridge` | 0.1163 | 0.1750 | 0.0688 | 1.3039 | 0.0379 | 0.0516 | 0.1105 | 0.0790 | 2.215 | 8.17 | 11.59 | 0.30 | 0.75 | 0.00302 |
| MW0 | 2024/25 | `elo_wdl_bridge` | 0.1292 | 0.1750 | 0.0755 | 1.4355 | 0.0398 | 0.0641 | 0.1135 | 0.0885 | 2.578 | 9.24 | 12.33 | 0.25 | 0.50 | 0.00123 |
| MW0 | 2024/25 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW0 | 2025/26 | `dc_native` | 0.1356 | 0.1750 | 0.1135 | 0.7169 | 0.1358 | 0.0981 | 0.1959 | 0.1015 | 1.226 | 6.69 | 9.39 | 0.50 | 0.85 | 0.00337 |
| MW0 | 2025/26 | `dc_wdl_bridge` | 0.1349 | 0.1750 | 0.1126 | 0.7051 | 0.1345 | 0.0972 | 0.1949 | 0.1010 | 1.202 | 6.67 | 9.36 | 0.50 | 0.85 | 0.00336 |
| MW0 | 2025/26 | `elo_wdl_bridge` | 0.1327 | 0.1750 | 0.1112 | 0.7906 | 0.1277 | 0.0868 | 0.2117 | 0.0904 | 1.333 | 6.67 | 8.92 | 0.45 | 0.75 | 0.00135 |
| MW0 | 2025/26 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2019/20 | `dc_native` | 0.0899 | 0.1750 | 0.0869 | 0.9418 | 0.0743 | 0.1150 | 0.1003 | 0.0978 | 1.194 | 5.31 | 7.70 | 0.30 | 1.00 | 0.00271 |
| MW3 | 2019/20 | `dc_wdl_bridge` | 0.0897 | 0.1750 | 0.0865 | 0.9272 | 0.0736 | 0.1142 | 0.0997 | 0.0984 | 1.182 | 5.30 | 7.69 | 0.35 | 1.00 | 0.00272 |
| MW3 | 2019/20 | `elo_wdl_bridge` | 0.0973 | 0.1750 | 0.0813 | 0.7510 | 0.0517 | 0.1052 | 0.1135 | 0.0986 | 0.951 | 5.67 | 7.91 | 0.30 | 0.80 | 0.00109 |
| MW3 | 2019/20 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2019/20 | `ppg_pointmass` | 0.1803 | 0.1750 | 0.1400 | 0.0000 | 0.2000 | 0.1000 | 0.2000 | 0.2000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2020/21 | `dc_native` | 0.0740 | 0.1750 | 0.0656 | 0.3599 | 0.0715 | 0.0935 | 0.1030 | 0.0420 | 0.603 | 4.49 | 5.97 | 0.60 | 0.85 | 0.00264 |
| MW3 | 2020/21 | `dc_wdl_bridge` | 0.0741 | 0.1750 | 0.0658 | 0.3637 | 0.0709 | 0.0942 | 0.1037 | 0.0419 | 0.611 | 4.49 | 5.97 | 0.60 | 0.85 | 0.00266 |
| MW3 | 2020/21 | `elo_wdl_bridge` | 0.0865 | 0.1750 | 0.0766 | 1.4511 | 0.0565 | 0.0891 | 0.1286 | 0.0365 | 1.931 | 5.36 | 7.15 | 0.55 | 0.80 | 0.00120 |
| MW3 | 2020/21 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2020/21 | `ppg_pointmass` | 0.2053 | 0.1750 | 0.2400 | 2.0000 | 0.4000 | 0.3000 | 0.3000 | 0.1000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2021/22 | `dc_native` | 0.0884 | 0.1750 | 0.0499 | 0.1194 | 0.0451 | 0.0851 | 0.0599 | 0.0537 | 0.352 | 5.31 | 7.39 | 0.45 | 0.90 | 0.00252 |
| MW3 | 2021/22 | `dc_wdl_bridge` | 0.0884 | 0.1750 | 0.0500 | 0.1237 | 0.0456 | 0.0846 | 0.0597 | 0.0541 | 0.360 | 5.32 | 7.40 | 0.50 | 0.90 | 0.00253 |
| MW3 | 2021/22 | `elo_wdl_bridge` | 0.0964 | 0.1750 | 0.0604 | 0.2881 | 0.0556 | 0.0986 | 0.0643 | 0.0691 | 0.585 | 6.21 | 8.61 | 0.35 | 0.70 | 0.00116 |
| MW3 | 2021/22 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2021/22 | `ppg_pointmass` | 0.2197 | 0.1750 | 0.1550 | 2.0000 | 0.1750 | 0.2000 | 0.1000 | 0.2000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2022/23 | `dc_native` | 0.1406 | 0.1750 | 0.1376 | 0.0610 | 0.1814 | 0.1420 | 0.2041 | 0.1572 | 0.224 | 8.22 | 11.35 | 0.25 | 0.60 | 0.00247 |
| MW3 | 2022/23 | `dc_wdl_bridge` | 0.1399 | 0.1750 | 0.1370 | 0.0642 | 0.1801 | 0.1415 | 0.2035 | 0.1567 | 0.230 | 8.20 | 11.34 | 0.25 | 0.65 | 0.00249 |
| MW3 | 2022/23 | `elo_wdl_bridge` | 0.1299 | 0.1750 | 0.1257 | 0.0487 | 0.1714 | 0.1372 | 0.1775 | 0.1401 | 0.191 | 7.63 | 9.90 | 0.35 | 0.55 | 0.00110 |
| MW3 | 2022/23 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2022/23 | `ppg_pointmass` | 0.1947 | 0.1750 | 0.2200 | 2.0000 | 0.2000 | 0.3000 | 0.3000 | 0.2000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2024/25 | `dc_native` | 0.1023 | 0.1750 | 0.0652 | 1.2350 | 0.0412 | 0.0485 | 0.1043 | 0.0704 | 1.903 | 7.55 | 10.62 | 0.35 | 0.75 | 0.00261 |
| MW3 | 2024/25 | `dc_wdl_bridge` | 0.1022 | 0.1750 | 0.0653 | 1.2234 | 0.0418 | 0.0491 | 0.1032 | 0.0710 | 1.880 | 7.55 | 10.63 | 0.35 | 0.75 | 0.00260 |
| MW3 | 2024/25 | `elo_wdl_bridge` | 0.1046 | 0.1750 | 0.0663 | 1.4137 | 0.0460 | 0.0576 | 0.0962 | 0.0613 | 2.215 | 8.13 | 10.97 | 0.25 | 0.70 | 0.00112 |
| MW3 | 2024/25 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2024/25 | `ppg_pointmass` | 0.1421 | 0.1750 | 0.1400 | 2.0000 | 0.1000 | 0.1000 | 0.2000 | 0.2000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2025/26 | `dc_native` | 0.1346 | 0.1750 | 0.1154 | 0.7763 | 0.1563 | 0.1167 | 0.2023 | 0.0628 | 1.195 | 6.50 | 9.10 | 0.45 | 0.85 | 0.00317 |
| MW3 | 2025/26 | `dc_wdl_bridge` | 0.1341 | 0.1750 | 0.1149 | 0.7564 | 0.1559 | 0.1165 | 0.2017 | 0.0626 | 1.167 | 6.49 | 9.06 | 0.45 | 0.85 | 0.00316 |
| MW3 | 2025/26 | `elo_wdl_bridge` | 0.1352 | 0.1750 | 0.1223 | 1.1247 | 0.1639 | 0.1229 | 0.2206 | 0.0481 | 1.556 | 6.75 | 9.31 | 0.30 | 0.70 | 0.00132 |
| MW3 | 2025/26 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW3 | 2025/26 | `ppg_pointmass` | 0.2934 | 0.1750 | 0.2350 | 2.0000 | 0.3000 | 0.2750 | 0.3000 | 0.2000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2019/20 | `dc_native` | 0.0926 | 0.1750 | 0.0857 | 0.5014 | 0.0788 | 0.1101 | 0.1019 | 0.1126 | 0.703 | 5.30 | 7.80 | 0.40 | 0.95 | 0.00270 |
| MW6 | 2019/20 | `dc_wdl_bridge` | 0.0925 | 0.1750 | 0.0851 | 0.5018 | 0.0784 | 0.1087 | 0.1014 | 0.1120 | 0.706 | 5.29 | 7.78 | 0.40 | 0.95 | 0.00271 |
| MW6 | 2019/20 | `elo_wdl_bridge` | 0.1044 | 0.1750 | 0.0809 | 0.1861 | 0.0593 | 0.1007 | 0.1147 | 0.1203 | 0.364 | 5.66 | 7.82 | 0.35 | 0.75 | 0.00110 |
| MW6 | 2019/20 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2019/20 | `ppg_pointmass` | 0.1895 | 0.1750 | 0.1800 | 0.0000 | 0.2000 | 0.2000 | 0.3000 | 0.2000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2020/21 | `dc_native` | 0.0762 | 0.1750 | 0.0677 | 0.3011 | 0.0745 | 0.0996 | 0.1053 | 0.0442 | 0.534 | 4.75 | 6.72 | 0.55 | 0.85 | 0.00264 |
| MW6 | 2020/21 | `dc_wdl_bridge` | 0.0759 | 0.1750 | 0.0676 | 0.3042 | 0.0737 | 0.0996 | 0.1058 | 0.0437 | 0.542 | 4.74 | 6.72 | 0.55 | 0.95 | 0.00265 |
| MW6 | 2020/21 | `elo_wdl_bridge` | 0.0904 | 0.1750 | 0.0773 | 1.3525 | 0.0616 | 0.0954 | 0.1241 | 0.0376 | 1.746 | 5.70 | 7.65 | 0.45 | 0.70 | 0.00117 |
| MW6 | 2020/21 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2020/21 | `ppg_pointmass` | 0.2053 | 0.1750 | 0.2400 | 2.0000 | 0.3000 | 0.3000 | 0.4000 | 0.1000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2021/22 | `dc_native` | 0.0841 | 0.1750 | 0.0490 | 0.1320 | 0.0548 | 0.0830 | 0.0596 | 0.0408 | 0.359 | 4.97 | 7.23 | 0.50 | 0.90 | 0.00242 |
| MW6 | 2021/22 | `dc_wdl_bridge` | 0.0845 | 0.1750 | 0.0496 | 0.1389 | 0.0552 | 0.0838 | 0.0607 | 0.0411 | 0.373 | 4.98 | 7.24 | 0.50 | 0.90 | 0.00243 |
| MW6 | 2021/22 | `elo_wdl_bridge` | 0.0854 | 0.1750 | 0.0549 | 0.2249 | 0.0689 | 0.0921 | 0.0528 | 0.0497 | 0.484 | 5.26 | 7.21 | 0.40 | 0.75 | 0.00107 |
| MW6 | 2021/22 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2021/22 | `ppg_pointmass` | 0.1737 | 0.1750 | 0.1600 | 2.0000 | 0.1000 | 0.2000 | 0.3000 | 0.1000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2022/23 | `dc_native` | 0.1295 | 0.1750 | 0.1310 | 0.0533 | 0.1657 | 0.1231 | 0.1962 | 0.1672 | 0.207 | 7.73 | 10.83 | 0.25 | 0.70 | 0.00240 |
| MW6 | 2022/23 | `dc_wdl_bridge` | 0.1289 | 0.1750 | 0.1306 | 0.0526 | 0.1655 | 0.1230 | 0.1950 | 0.1667 | 0.205 | 7.70 | 10.81 | 0.25 | 0.70 | 0.00241 |
| MW6 | 2022/23 | `elo_wdl_bridge` | 0.1143 | 0.1750 | 0.1140 | 0.0574 | 0.1543 | 0.1124 | 0.1787 | 0.1219 | 0.210 | 6.96 | 9.25 | 0.35 | 0.60 | 0.00109 |
| MW6 | 2022/23 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2022/23 | `ppg_pointmass` | 0.1895 | 0.1750 | 0.1800 | 2.0000 | 0.2000 | 0.2000 | 0.2000 | 0.2000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2024/25 | `dc_native` | 0.0987 | 0.1750 | 0.0591 | 1.1771 | 0.0288 | 0.0433 | 0.0975 | 0.0671 | 1.974 | 7.33 | 10.31 | 0.35 | 0.75 | 0.00237 |
| MW6 | 2024/25 | `dc_wdl_bridge` | 0.0986 | 0.1750 | 0.0589 | 1.1694 | 0.0291 | 0.0435 | 0.0960 | 0.0672 | 1.961 | 7.34 | 10.32 | 0.35 | 0.75 | 0.00236 |
| MW6 | 2024/25 | `elo_wdl_bridge` | 0.1024 | 0.1750 | 0.0607 | 1.3424 | 0.0286 | 0.0483 | 0.0847 | 0.0750 | 2.451 | 8.25 | 11.01 | 0.30 | 0.50 | 0.00102 |
| MW6 | 2024/25 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2024/25 | `ppg_pointmass` | 0.1263 | 0.1750 | 0.0800 | 0.0000 | 0.0000 | 0.1000 | 0.1000 | 0.2000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2025/26 | `dc_native` | 0.1203 | 0.1750 | 0.0996 | 0.4333 | 0.1467 | 0.1078 | 0.1841 | 0.0378 | 0.780 | 5.79 | 7.97 | 0.45 | 0.85 | 0.00280 |
| MW6 | 2025/26 | `dc_wdl_bridge` | 0.1198 | 0.1750 | 0.0990 | 0.4144 | 0.1456 | 0.1074 | 0.1838 | 0.0375 | 0.754 | 5.79 | 7.96 | 0.45 | 0.85 | 0.00278 |
| MW6 | 2025/26 | `elo_wdl_bridge` | 0.1197 | 0.1750 | 0.0976 | 0.4906 | 0.1462 | 0.1045 | 0.1891 | 0.0236 | 0.817 | 5.86 | 8.15 | 0.35 | 0.80 | 0.00123 |
| MW6 | 2025/26 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW6 | 2025/26 | `ppg_pointmass` | 0.2000 | 0.1750 | 0.1600 | 0.0000 | 0.3000 | 0.2000 | 0.3000 | 0.0000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2019/20 | `dc_native` | 0.0721 | 0.1750 | 0.0539 | 0.2725 | 0.0560 | 0.0589 | 0.0733 | 0.0678 | 0.465 | 4.19 | 6.43 | 0.45 | 0.95 | 0.00239 |
| MW10 | 2019/20 | `dc_wdl_bridge` | 0.0724 | 0.1750 | 0.0540 | 0.2659 | 0.0566 | 0.0575 | 0.0736 | 0.0687 | 0.458 | 4.18 | 6.42 | 0.45 | 0.95 | 0.00237 |
| MW10 | 2019/20 | `elo_wdl_bridge` | 0.0827 | 0.1750 | 0.0510 | 0.0641 | 0.0400 | 0.0497 | 0.0871 | 0.0751 | 0.198 | 4.70 | 6.76 | 0.40 | 0.85 | 0.00103 |
| MW10 | 2019/20 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2019/20 | `ppg_pointmass` | 0.1737 | 0.1750 | 0.1000 | 0.0000 | 0.1000 | 0.1000 | 0.2000 | 0.1000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2020/21 | `dc_native` | 0.0664 | 0.1750 | 0.0462 | 0.6027 | 0.0609 | 0.0742 | 0.0534 | 0.0122 | 0.933 | 4.38 | 6.22 | 0.55 | 0.90 | 0.00202 |
| MW10 | 2020/21 | `dc_wdl_bridge` | 0.0660 | 0.1750 | 0.0461 | 0.6081 | 0.0602 | 0.0741 | 0.0534 | 0.0123 | 0.945 | 4.37 | 6.21 | 0.60 | 0.90 | 0.00201 |
| MW10 | 2020/21 | `elo_wdl_bridge` | 0.0779 | 0.1750 | 0.0552 | 1.4870 | 0.0489 | 0.0774 | 0.0662 | 0.0090 | 2.128 | 5.22 | 7.15 | 0.45 | 0.70 | 0.00091 |
| MW10 | 2020/21 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2020/21 | `ppg_pointmass` | 0.1316 | 0.1750 | 0.1200 | 2.0000 | 0.2000 | 0.1000 | 0.1000 | 0.1000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2021/22 | `dc_native` | 0.0654 | 0.1750 | 0.0442 | 0.1414 | 0.0563 | 0.0812 | 0.0210 | 0.0554 | 0.371 | 4.37 | 6.42 | 0.55 | 0.90 | 0.00197 |
| MW10 | 2021/22 | `dc_wdl_bridge` | 0.0653 | 0.1750 | 0.0443 | 0.1425 | 0.0567 | 0.0815 | 0.0212 | 0.0550 | 0.373 | 4.36 | 6.39 | 0.55 | 0.90 | 0.00198 |
| MW10 | 2021/22 | `elo_wdl_bridge` | 0.0702 | 0.1750 | 0.0504 | 0.1870 | 0.0645 | 0.0959 | 0.0206 | 0.0616 | 0.439 | 4.98 | 7.08 | 0.35 | 0.80 | 0.00100 |
| MW10 | 2021/22 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2021/22 | `ppg_pointmass` | 0.1211 | 0.1750 | 0.1000 | 2.0000 | 0.1000 | 0.1000 | 0.1000 | 0.1000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2022/23 | `dc_native` | 0.1212 | 0.1750 | 0.1140 | 0.0090 | 0.1309 | 0.1070 | 0.1891 | 0.1428 | 0.086 | 6.94 | 9.79 | 0.25 | 0.70 | 0.00187 |
| MW10 | 2022/23 | `dc_wdl_bridge` | 0.1206 | 0.1750 | 0.1137 | 0.0090 | 0.1299 | 0.1067 | 0.1889 | 0.1426 | 0.086 | 6.93 | 9.77 | 0.25 | 0.70 | 0.00189 |
| MW10 | 2022/23 | `elo_wdl_bridge` | 0.1062 | 0.1750 | 0.0968 | 0.0240 | 0.1083 | 0.0820 | 0.1822 | 0.1105 | 0.132 | 6.05 | 8.28 | 0.25 | 0.80 | 0.00093 |
| MW10 | 2022/23 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2022/23 | `ppg_pointmass` | 0.1684 | 0.1750 | 0.2000 | 2.0000 | 0.2000 | 0.2000 | 0.3000 | 0.2000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2024/25 | `dc_native` | 0.0820 | 0.1750 | 0.0458 | 0.4951 | 0.0238 | 0.0339 | 0.0945 | 0.0522 | 0.786 | 5.99 | 8.34 | 0.35 | 0.70 | 0.00222 |
| MW10 | 2024/25 | `dc_wdl_bridge` | 0.0821 | 0.1750 | 0.0458 | 0.4798 | 0.0247 | 0.0342 | 0.0935 | 0.0526 | 0.769 | 5.99 | 8.34 | 0.40 | 0.70 | 0.00221 |
| MW10 | 2024/25 | `elo_wdl_bridge` | 0.0835 | 0.1750 | 0.0442 | 0.4366 | 0.0202 | 0.0354 | 0.0850 | 0.0588 | 0.688 | 6.48 | 8.74 | 0.35 | 0.60 | 0.00104 |
| MW10 | 2024/25 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2024/25 | `ppg_pointmass` | 0.1263 | 0.1750 | 0.1000 | 0.0000 | 0.0000 | 0.1000 | 0.2000 | 0.2000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2025/26 | `dc_native` | 0.0941 | 0.1750 | 0.0806 | 0.2825 | 0.1194 | 0.0811 | 0.1324 | 0.0561 | 0.535 | 4.84 | 6.69 | 0.60 | 0.85 | 0.00253 |
| MW10 | 2025/26 | `dc_wdl_bridge` | 0.0937 | 0.1750 | 0.0800 | 0.2703 | 0.1187 | 0.0801 | 0.1316 | 0.0560 | 0.521 | 4.83 | 6.68 | 0.60 | 0.85 | 0.00251 |
| MW10 | 2025/26 | `elo_wdl_bridge` | 0.0891 | 0.1750 | 0.0774 | 0.1795 | 0.1144 | 0.0738 | 0.1461 | 0.0438 | 0.403 | 4.55 | 6.01 | 0.60 | 0.70 | 0.00116 |
| MW10 | 2025/26 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW10 | 2025/26 | `ppg_pointmass` | 0.1526 | 0.1750 | 0.1600 | 0.0000 | 0.2000 | 0.3000 | 0.2000 | 0.1000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2019/20 | `dc_native` | 0.0497 | 0.1750 | 0.0409 | 0.0003 | 0.0863 | 0.0357 | 0.0199 | 0.0627 | 0.013 | 2.83 | 3.61 | 0.60 | 0.85 | 0.00151 |
| MW19 | 2019/20 | `dc_wdl_bridge` | 0.0497 | 0.1750 | 0.0407 | 0.0004 | 0.0857 | 0.0346 | 0.0203 | 0.0629 | 0.014 | 2.81 | 3.60 | 0.65 | 0.90 | 0.00151 |
| MW19 | 2019/20 | `elo_wdl_bridge` | 0.0483 | 0.1750 | 0.0339 | 0.0000 | 0.0801 | 0.0199 | 0.0117 | 0.0578 | 0.001 | 2.92 | 3.87 | 0.55 | 0.85 | 0.00078 |
| MW19 | 2019/20 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2019/20 | `ppg_pointmass` | 0.0842 | 0.1750 | 0.0400 | 0.0000 | 0.1000 | 0.0000 | 0.0000 | 0.1000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2020/21 | `dc_native` | 0.0508 | 0.1750 | 0.0326 | 0.0411 | 0.0545 | 0.0544 | 0.0501 | 0.0018 | 0.170 | 2.46 | 3.25 | 0.70 | 1.00 | 0.00156 |
| MW19 | 2020/21 | `dc_wdl_bridge` | 0.0505 | 0.1750 | 0.0325 | 0.0430 | 0.0542 | 0.0533 | 0.0510 | 0.0020 | 0.176 | 2.46 | 3.25 | 0.70 | 1.00 | 0.00156 |
| MW19 | 2020/21 | `elo_wdl_bridge` | 0.0531 | 0.1750 | 0.0313 | 0.1259 | 0.0512 | 0.0494 | 0.0466 | 0.0028 | 0.310 | 2.65 | 3.42 | 0.65 | 0.90 | 0.00091 |
| MW19 | 2020/21 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2020/21 | `ppg_pointmass` | 0.1000 | 0.1750 | 0.0800 | 0.0000 | 0.1000 | 0.1000 | 0.2000 | 0.0000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2021/22 | `dc_native` | 0.0494 | 0.1750 | 0.0284 | 0.0035 | 0.0369 | 0.0443 | 0.0110 | 0.0498 | 0.045 | 3.47 | 4.85 | 0.70 | 0.90 | 0.00130 |
| MW19 | 2021/22 | `dc_wdl_bridge` | 0.0495 | 0.1750 | 0.0283 | 0.0032 | 0.0363 | 0.0443 | 0.0112 | 0.0498 | 0.043 | 3.47 | 4.86 | 0.70 | 0.90 | 0.00130 |
| MW19 | 2021/22 | `elo_wdl_bridge` | 0.0486 | 0.1750 | 0.0294 | 0.0021 | 0.0428 | 0.0527 | 0.0066 | 0.0447 | 0.034 | 3.54 | 4.87 | 0.60 | 0.85 | 0.00073 |
| MW19 | 2021/22 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2021/22 | `ppg_pointmass` | 0.0579 | 0.1750 | 0.0200 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.1000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2022/23 | `dc_native` | 0.0675 | 0.1750 | 0.0695 | 0.3526 | 0.0492 | 0.0327 | 0.1083 | 0.1396 | 0.548 | 3.46 | 4.84 | 0.45 | 0.90 | 0.00167 |
| MW19 | 2022/23 | `dc_wdl_bridge` | 0.0673 | 0.1750 | 0.0689 | 0.3548 | 0.0487 | 0.0319 | 0.1080 | 0.1384 | 0.550 | 3.45 | 4.83 | 0.45 | 0.90 | 0.00166 |
| MW19 | 2022/23 | `elo_wdl_bridge` | 0.0611 | 0.1750 | 0.0612 | 0.8318 | 0.0224 | 0.0149 | 0.1018 | 0.1254 | 1.039 | 3.14 | 4.52 | 0.50 | 0.90 | 0.00086 |
| MW19 | 2022/23 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2022/23 | `ppg_pointmass` | 0.1105 | 0.1750 | 0.1200 | 2.0000 | 0.0000 | 0.1000 | 0.2000 | 0.2000 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2024/25 | `dc_native` | 0.0511 | 0.1750 | 0.0203 | 0.0573 | 0.0278 | 0.0152 | 0.0340 | 0.0217 | 0.198 | 3.90 | 5.51 | 0.40 | 0.85 | 0.00156 |
| MW19 | 2024/25 | `dc_wdl_bridge` | 0.0510 | 0.1750 | 0.0205 | 0.0625 | 0.0283 | 0.0159 | 0.0341 | 0.0214 | 0.207 | 3.88 | 5.49 | 0.40 | 0.85 | 0.00156 |
| MW19 | 2024/25 | `elo_wdl_bridge` | 0.0484 | 0.1750 | 0.0189 | 0.0302 | 0.0261 | 0.0200 | 0.0247 | 0.0222 | 0.136 | 3.86 | 5.47 | 0.40 | 0.80 | 0.00085 |
| MW19 | 2024/25 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2024/25 | `ppg_pointmass` | 0.0842 | 0.1750 | 0.0600 | 0.0000 | 0.1000 | 0.1000 | 0.1000 | 0.0000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2025/26 | `dc_native` | 0.0799 | 0.1750 | 0.0559 | 0.1096 | 0.0721 | 0.0558 | 0.1407 | 0.0052 | 0.278 | 3.91 | 5.44 | 0.45 | 0.90 | 0.00162 |
| MW19 | 2025/26 | `dc_wdl_bridge` | 0.0797 | 0.1750 | 0.0555 | 0.1078 | 0.0721 | 0.0553 | 0.1392 | 0.0053 | 0.276 | 3.91 | 5.44 | 0.45 | 0.85 | 0.00163 |
| MW19 | 2025/26 | `elo_wdl_bridge` | 0.0798 | 0.1750 | 0.0577 | 0.0399 | 0.0770 | 0.0549 | 0.1512 | 0.0036 | 0.171 | 4.09 | 5.57 | 0.40 | 0.85 | 0.00085 |
| MW19 | 2025/26 | `flat` | 0.1750 | 0.1750 | 0.1500 | 0.9500 | 0.1600 | 0.1875 | 0.2275 | 0.1275 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| MW19 | 2025/26 | `ppg_pointmass` | 0.0947 | 0.1750 | 0.0800 | 0.0000 | 0.1000 | 0.1000 | 0.2000 | 0.0000 | 0.000 | n/a | n/a | n/a | n/a | n/a |

### Mean TRPS per (cutoff, arm)

Means are taken **within** a cutoff and never across cutoffs. The season count is on every row because it is not the same at every cutoff (§2).

| cutoff | seasons | `dc_native` | `dc_wdl_bridge` | `elo_wdl_bridge` | `flat` | `ppg_pointmass` |
|---|---|---|---|---|---|---|
| MW0 | 4 | 0.1251 | 0.1249 | 0.1261 | 0.1750 | n/a |
| MW3 | 6 | 0.1049 | 0.1047 | 0.1083 | 0.1750 | 0.2059 |
| MW6 | 6 | 0.1002 | 0.1000 | 0.1028 | 0.1750 | 0.1807 |
| MW10 | 6 | 0.0835 | 0.0833 | 0.0849 | 0.1750 | 0.1456 |
| MW19 | 6 | 0.0581 | 0.0580 | 0.0565 | 0.1750 | 0.0886 |

## 4. Paired differences (TRPS), per cutoff — the preregistered pairings

Paired within an occasion (same season, same cutoff, same fit, same fixtures, same random slots), season-block bootstrap, 10,000 resamples, percentile CI. TRPS is a **loss**, so a **positive** mean means `dc_native` scored **worse**.

> **There is no pass rule.** Shipping does not depend on these intervals. No interval here, at any cutoff, in either direction, is by itself a decision. This was pre-stated (prereg §7) precisely so a wide interval cannot now be read as 'inconclusive, therefore keep what we have' and a narrow one cannot be read as 'significant, therefore switch'.

| cutoff | pair | n | blocks | mean | sd | CI95 low | CI95 high |
|---|---|---|---|---|---|---|---|
| MW0 | `dc_native-dc_wdl_bridge` | 4 | 4 | **0.00021** | 0.00051 | -0.00023 | 0.00065 |
| MW0 | `dc_native-elo_wdl_bridge` | 4 | 4 | **-0.00101** | 0.01091 | -0.00950 | 0.00761 |
| MW3 | `dc_native-dc_wdl_bridge` | 6 | 6 | **0.00023** | 0.00032 | 0.00001 | 0.00047 |
| MW3 | `dc_native-elo_wdl_bridge` | 6 | 6 | **-0.00337** | 0.00811 | -0.00860 | 0.00293 |
| MW6 | `dc_native-dc_wdl_bridge` | 6 | 6 | **0.00019** | 0.00038 | -0.00010 | 0.00044 |
| MW6 | `dc_native-elo_wdl_bridge` | 6 | 6 | **-0.00255** | 0.01050 | -0.00953 | 0.00551 |
| MW10 | `dc_native-dc_wdl_bridge` | 6 | 6 | **0.00020** | 0.00032 | -0.00004 | 0.00041 |
| MW10 | `dc_native-elo_wdl_bridge` | 6 | 6 | **-0.00140** | 0.01008 | -0.00829 | 0.00633 |
| MW19 | `dc_native-dc_wdl_bridge` | 6 | 6 | **0.00011** | 0.00010 | 0.00003 | 0.00018 |
| MW19 | `dc_native-elo_wdl_bridge` | 6 | 6 | **0.00151** | 0.00294 | -0.00047 | 0.00382 |

Block counts per cutoff: **MW0** 4, **MW3** 6, **MW6** 6, **MW10** 6, **MW19** 6. A bootstrap over this few blocks gives a wide, coarse interval: a season-block bootstrap over 4-6 blocks resamples the same handful of seasons repeatedly, so the interval describes how much these particular seasons disagree with each other, not how much an unseen season might have disagreed with all of them.

- **`dc_native-dc_wdl_bridge`: the interval excludes zero at MW3, MW19** and spans it at the other 3.
- **`dc_native-elo_wdl_bridge`: every interval spans zero**, at all 5 cutoffs.

**An interval that excludes zero is not a pass.** There is no pass rule (prereg §7), and prereg §11 pre-stated that 'the interval excluded zero' is not on its own a sufficient rationale for changing anything. Read the magnitudes beside the signs: where `dc_native − dc_wdl_bridge` separates from zero it does so at about 2e-4 on a TRPS of order 0.06-0.10 — two parts in a thousand, and a comparison of the model against **its own** 1X2 pushed through the empirical bridge, not against a rival. The pairing that actually bears on the published-arm question, `dc_native − elo_wdl_bridge`, spans zero at every cutoff.

## 5. An additional pairing: `elo_wdl_bridge` − `flat`

**Not preregistered.** `DEFAULT_COMPARISONS` (`epl/simretro.py:97-98`) holds two pairings and this is not one of them; it was added by the R1 run instruction as a further diagnostic and is reported in its own section so it cannot be mistaken for a preregistered result. It has no pass rule either. It answers one narrow question: does the Elo arm clear the uniform matrix, and by how much. The `flat` null is the closed-form 0.175 at every season, so this difference is just the Elo arm's TRPS minus a constant, and its spread across seasons is the Elo arm's own spread.

| cutoff | pair | n | blocks | mean | sd | CI95 low | CI95 high |
|---|---|---|---|---|---|---|---|
| MW0 | `elo_wdl_bridge-flat` | 4 | 4 | **-0.04891** | 0.02287 | -0.07122 | -0.03146 |
| MW3 | `elo_wdl_bridge-flat` | 6 | 6 | **-0.06669** | 0.01970 | -0.08023 | -0.05211 |
| MW6 | `elo_wdl_bridge-flat` | 6 | 6 | **-0.07222** | 0.01326 | -0.08197 | -0.06251 |
| MW10 | `elo_wdl_bridge-flat` | 6 | 6 | **-0.09007** | 0.01218 | -0.09817 | -0.08044 |
| MW19 | `elo_wdl_bridge-flat` | 6 | 6 | **-0.11845** | 0.01239 | -0.12580 | -0.10857 |

## 6. The two hard checks

### Check 1 — `dc_native` beats the flat null at every (season, cutoff)

**Comparison cutoffs: True** — 28 cells checked, 0 violations.

**MW28 sanity cutoff, reported separately: True** — 6 cells checked, 0 violations.

### Check 2 — coherence

The runner enforces the doubly-stochastic conditions twice during the run (`epl/simretro.py:392`, `:402`, and again in `_check_clubs` at `:643-651`), and a failure raises before anything reaches the ledger. R1 re-checked it a third time, independently, by reading every stored matrix back out of the ledger:

- matrices re-checked: **166** (every forecast row, arms and nulls, comparison and sanity cutoffs)
- failures: **0**
- worst row-sum deviation from 1: `2.220e-16`
- worst column-sum deviation from 1: `4.441e-16`
- positive control: rejected a +0.25 perturbation, as it must

### Other guards, reported because they were asked to be read

- champion log-loss **zero hits** — the forecast never once simulated the realised champion, so the true score is unbounded and the 0.5/N floor stands in: **12** across the comparison cutoffs, floor applied **12** times. By series: `ppg_pointmass` 12.
  Every one belongs to `ppg_pointmass`, the null that puts all its mass on a single projected ordering and so gives probability exactly zero to every champion but one — the failure mode the floor exists for. **The three arms contributed none.** A `champ -ln p` of 10.597 in the tables above is that floor, not a score.
- shared realised finishing positions across the scored seasons: **0**.
- `never_averaged_across_cutoffs` flag carried by the scores object: **True**.

## 7. MW28 — sanity only, in no comparison

Kept structurally apart: scored by a separate `score_retro` call with **no pairings at all**, so MW28 cannot enter a comparison even by accident (prereg §12 names 'MW28 enters a comparison' as an invalidation). By late March the table has converged and TRPS is on its way to zero for every arm — a difference here measures the calendar, not the forecast. These rows exist to show the harness degenerates the way a correct harness should, and for no other purpose.

| season | arm | TRPS | flat TRPS | wTRPS | champ -ln p | pts CRPS | pts MAE | cov50 | cov90 | MC SE |
|---|---|---|---|---|---|---|---|---|---|---|
| 2019/20 | `dc_native` | 0.0390 | 0.1750 | 0.0376 | 0.000 | 2.20 | 3.10 | 0.55 | 0.90 | 0.00118 |
| 2019/20 | `dc_wdl_bridge` | 0.0391 | 0.1750 | 0.0378 | 0.000 | 2.20 | 3.09 | 0.55 | 0.90 | 0.00118 |
| 2019/20 | `elo_wdl_bridge` | 0.0378 | 0.1750 | 0.0340 | 0.000 | 2.30 | 3.27 | 0.50 | 0.85 | 0.00076 |
| 2019/20 | `flat` | 0.1750 | 0.1750 | 0.1500 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| 2019/20 | `ppg_pointmass` | 0.0526 | 0.1750 | 0.0600 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| 2020/21 | `dc_native` | 0.0458 | 0.1750 | 0.0285 | 0.000 | 2.33 | 3.17 | 0.55 | 0.85 | 0.00101 |
| 2020/21 | `dc_wdl_bridge` | 0.0458 | 0.1750 | 0.0288 | 0.001 | 2.34 | 3.17 | 0.55 | 0.85 | 0.00103 |
| 2020/21 | `elo_wdl_bridge` | 0.0493 | 0.1750 | 0.0308 | 0.001 | 2.52 | 3.43 | 0.55 | 0.85 | 0.00069 |
| 2020/21 | `flat` | 0.1750 | 0.1750 | 0.1500 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| 2020/21 | `ppg_pointmass` | 0.0737 | 0.1750 | 0.0600 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| 2021/22 | `dc_native` | 0.0453 | 0.1750 | 0.0269 | 0.166 | 3.12 | 4.49 | 0.30 | 0.75 | 0.00085 |
| 2021/22 | `dc_wdl_bridge` | 0.0453 | 0.1750 | 0.0271 | 0.172 | 3.13 | 4.49 | 0.30 | 0.75 | 0.00085 |
| 2021/22 | `elo_wdl_bridge` | 0.0470 | 0.1750 | 0.0315 | 0.178 | 3.29 | 4.68 | 0.35 | 0.70 | 0.00057 |
| 2021/22 | `flat` | 0.1750 | 0.1750 | 0.1500 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| 2021/22 | `ppg_pointmass` | 0.0737 | 0.1750 | 0.0400 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| 2022/23 | `dc_native` | 0.0384 | 0.1750 | 0.0475 | 0.514 | 2.24 | 3.07 | 0.50 | 0.90 | 0.00097 |
| 2022/23 | `dc_wdl_bridge` | 0.0383 | 0.1750 | 0.0471 | 0.511 | 2.23 | 3.06 | 0.55 | 0.90 | 0.00098 |
| 2022/23 | `elo_wdl_bridge` | 0.0339 | 0.1750 | 0.0428 | 0.677 | 2.08 | 2.90 | 0.55 | 0.95 | 0.00063 |
| 2022/23 | `flat` | 0.1750 | 0.1750 | 0.1500 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| 2022/23 | `ppg_pointmass` | 0.0526 | 0.1750 | 0.0800 | 10.597 | n/a | n/a | n/a | n/a | n/a |
| 2024/25 | `dc_native` | 0.0395 | 0.1750 | 0.0278 | 0.015 | 2.59 | 3.72 | 0.50 | 0.90 | 0.00096 |
| 2024/25 | `dc_wdl_bridge` | 0.0393 | 0.1750 | 0.0277 | 0.012 | 2.59 | 3.72 | 0.55 | 0.90 | 0.00095 |
| 2024/25 | `elo_wdl_bridge` | 0.0385 | 0.1750 | 0.0302 | 0.005 | 2.64 | 3.79 | 0.40 | 0.85 | 0.00065 |
| 2024/25 | `flat` | 0.1750 | 0.1750 | 0.1500 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| 2024/25 | `ppg_pointmass` | 0.0737 | 0.1750 | 0.0600 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| 2025/26 | `dc_native` | 0.0543 | 0.1750 | 0.0426 | 0.319 | 2.38 | 3.54 | 0.55 | 0.95 | 0.00104 |
| 2025/26 | `dc_wdl_bridge` | 0.0542 | 0.1750 | 0.0422 | 0.322 | 2.37 | 3.55 | 0.55 | 0.95 | 0.00103 |
| 2025/26 | `elo_wdl_bridge` | 0.0520 | 0.1750 | 0.0392 | 0.301 | 2.38 | 3.56 | 0.45 | 0.95 | 0.00067 |
| 2025/26 | `flat` | 0.1750 | 0.1750 | 0.1500 | 2.996 | n/a | n/a | n/a | n/a | n/a |
| 2025/26 | `ppg_pointmass` | 0.0789 | 0.1750 | 0.0400 | 0.000 | n/a | n/a | n/a | n/a | n/a |

| cutoff | seasons | `dc_native` | `dc_wdl_bridge` | `elo_wdl_bridge` | `flat` | `ppg_pointmass` |
|---|---|---|---|---|---|---|
| MW28 | 6 | 0.0437 | 0.0437 | 0.0431 | 0.1750 | 0.0675 |

## 8. In plain language, per cutoff

Which arm scored the better (lower) TRPS, and in how many of the scored seasons. **These are counts, not tests.** No pass rule attaches to them, a count says nothing about the size of a difference, and six seasons of one league is six observations however lopsided the tally.

| cutoff | seasons | `dc_native` better than `elo_wdl_bridge` | `dc_native` better than `dc_wdl_bridge` | mean TRPS `dc_native` | mean TRPS `elo_wdl_bridge` | mean TRPS `dc_wdl_bridge` |
|---|---|---|---|---|---|---|
| MW0 | 4 | **2 of 4** | **2 of 4** | 0.1251 | 0.1261 | 0.1249 |
| MW3 | 6 | **5 of 6** | **2 of 6** | 0.1049 | 0.1083 | 0.1047 |
| MW6 | 6 | **4 of 6** | **1 of 6** | 0.1002 | 0.1028 | 0.1000 |
| MW10 | 6 | **4 of 6** | **2 of 6** | 0.0835 | 0.0849 | 0.0833 |
| MW19 | 6 | **1 of 6** | **1 of 6** | 0.0581 | 0.0565 | 0.0580 |

- **MW0.** `elo_wdl_bridge` scored the better TRPS in **2 of 4** seasons, `dc_native` in **2 of 4**. Paired mean `dc_native − elo_wdl_bridge` = **-0.00101** (95% CI -0.00950 to 0.00761, 4 blocks); positive means `dc_native` worse. Against its own 1X2 through the bridge, `dc_native` was better in **2 of 4**.
- **MW3.** `elo_wdl_bridge` scored the better TRPS in **1 of 6** seasons, `dc_native` in **5 of 6**. Paired mean `dc_native − elo_wdl_bridge` = **-0.00337** (95% CI -0.00860 to 0.00293, 6 blocks); positive means `dc_native` worse. Against its own 1X2 through the bridge, `dc_native` was better in **2 of 6**.
- **MW6.** `elo_wdl_bridge` scored the better TRPS in **2 of 6** seasons, `dc_native` in **4 of 6**. Paired mean `dc_native − elo_wdl_bridge` = **-0.00255** (95% CI -0.00953 to 0.00551, 6 blocks); positive means `dc_native` worse. Against its own 1X2 through the bridge, `dc_native` was better in **1 of 6**.
- **MW10.** `elo_wdl_bridge` scored the better TRPS in **2 of 6** seasons, `dc_native` in **4 of 6**. Paired mean `dc_native − elo_wdl_bridge` = **-0.00140** (95% CI -0.00829 to 0.00633, 6 blocks); positive means `dc_native` worse. Against its own 1X2 through the bridge, `dc_native` was better in **2 of 6**.
- **MW19.** `elo_wdl_bridge` scored the better TRPS in **5 of 6** seasons, `dc_native` in **1 of 6**. Paired mean `dc_native − elo_wdl_bridge` = **0.00151** (95% CI -0.00047 to 0.00382, 6 blocks); positive means `dc_native` worse. Against its own 1X2 through the bridge, `dc_native` was better in **1 of 6**.

## 9. Reconciliation with the T8 smoke

The smoke (`data/epl/sim/retro_smoke.jsonl`, 2025/26 at MW0 and MW10, same N and same seed) shares ten `run_key`s with R1. R1 wrote a fresh ledger, so those ten forecasts were **recomputed from scratch**. If the harness is the pure function of (season, cutoff, arm, N, seed) it claims to be, the recomputation must agree exactly.

| run_key | envelope hash equal | digest equal | max abs matrix diff | TRPS R1 | TRPS smoke |
|---|---|---|---|---|---|
| `2025/26|MW0|2025-08-15|dc_native|n20000|s20260611` | False | False | 0.000e+00 | 0.1356 | 0.1356 |
| `2025/26|MW0|2025-08-15|dc_wdl_bridge|n20000|s20260611` | False | False | 0.000e+00 | 0.1349 | 0.1349 |
| `2025/26|MW0|2025-08-15|elo_wdl_bridge|n20000|s20260611` | False | False | 0.000e+00 | 0.1327 | 0.1327 |
| `2025/26|MW0|2025-08-15|flat|n20000|s20260611` | True | True | 0.000e+00 | 0.1750 | 0.1750 |
| `2025/26|MW0|2025-08-15|ppg_pointmass|n20000|s20260611` | True | n/a | n/a | n/a | n/a |
| `2025/26|MW10|2025-11-22|dc_native|n20000|s20260611` | False | False | 0.000e+00 | 0.0941 | 0.0941 |
| `2025/26|MW10|2025-11-22|dc_wdl_bridge|n20000|s20260611` | False | False | 0.000e+00 | 0.0937 | 0.0937 |
| `2025/26|MW10|2025-11-22|elo_wdl_bridge|n20000|s20260611` | False | False | 0.000e+00 | 0.0891 | 0.0891 |
| `2025/26|MW10|2025-11-22|flat|n20000|s20260611` | True | True | 0.000e+00 | 0.1750 | 0.1750 |
| `2025/26|MW10|2025-11-22|ppg_pointmass|n20000|s20260611` | True | True | 0.000e+00 | 0.1526 | 0.1526 |

**The forecasts reproduced exactly.** 9 of 9 recomputed matrices are bit-identical to the smoke's (max absolute difference 0), and 9 of 9 agree on **all 10** forecast-bearing fields compared element by element — `clubs`, `matrix`, `matrix_se`, `consequences`, `points_hist`, `tie_diagnostics`, `mc`, `realised`, `n_sims`, `n_particles`. Same seed, same rows.

**The provenance hashes do not agree, and should not.** Only 4 of 10 `envelope_hash` values match, and the `digest` differs on every simulated arm. This is not a reproducibility failure; it is the envelope doing its job. `leaguesim.envelope` records the code state that produced a number — `git_commit`, `git_dirty` and `epl_tree_sha256` are envelope fields (`epl/leaguesim.py:157-169`) — and `SimRun.digest` drops only `wall_seconds` (`NON_REPRODUCIBLE_FIELDS`, `epl/leaguesim.py:173`). The smoke was written at 13:10 today; three commits landed between then and R1's 17:36 start, so `git_commit` necessarily differs and the hash over it necessarily differs too.

The rows themselves supply the control. A null's envelope is `{"null": true, "note": name}` and carries no git state (`ArmResult.from_null`, `epl/simretro.py:303-310`), and **the two null series are exactly the rows whose `envelope_hash` does match** — while the three simulated arms, whose envelopes carry the commit, are exactly the rows that differ. Provenance changed; the forecast did not.

Worth stating plainly because prereg §9 claims `envelope_hash` makes 'two identical runs on different days agree': that claim holds for two runs at the **same commit**, not across commits. `_VOLATILE` (`epl/simretro.py:111`) strips the three clock fields, and R1 confirms it does — `fit_seconds` and `wall_seconds` were the only differing provenance fields and they did not affect the hash — but nothing strips the commit, by design. The reproducibility guarantee that matters is the one tested above: identical inputs, identical forecast.

The prereg quoted the smoke's direction in advance (§10 of the prereg) so it could not be presented later as a surprise: at MW0 and MW10 of 2025/26, `elo_wdl_bridge` scored the better TRPS. R1 reproduces those two cells exactly, and §8 shows what the other five seasons do at the cutoffs where they were scorable.

## 10. What this decides

**Nothing, by itself.** Prereg §11: R1 informs three decisions and all three are **owner rulings made after these tables exist**, recorded as written amendments in `reports/epl_sim_amendments.md`:

1. whether `dc_native` remains the published arm;
2. **D2** — whether horizon widening is introduced;
3. **D12** — whether the widening mixture branch moves from a per-fixture Bernoulli draw to the per-season variant.

**The default, absent a ruling, is unchanged in every case:** `dc_native` stays the published arm as issued on 2026-08-21, D2 stays static-within-fit, D12 stays per-fixture. No agent, no script and no report may switch the published arm on the strength of these numbers, and the harness has no code path that would.

A ruling has to contend with what is actually here: **6 seasons, not seven**; **MW0 on 4 of them**; no pass rule; a `dc_native − elo_wdl_bridge` interval that **spans zero at every cutoff**; and the smoke's direction known in advance and **not** reproduced. 'The interval excluded zero' is not, on its own, a sufficient rationale (prereg §11, written before these numbers existed) — and on the pairing that bears on the published-arm question, no interval excludes zero anyway, which is equally not a rationale for anything.

**The one thing R1 establishes without needing a ruling is a defect**, and it is not about arms at all: the published `dc_native` arm failed closed at two of the six openers it was asked for, because a cold-start club's defence draw against a top attack pushes more than 2% of the scoreline mass past the 10-goal truncation (§2, hole 2). That is a capability gap on exactly the date the product publishes a season's first table. It is separate from every comparison above, it does not shrink if the comparison is called inconclusive, and it is the item this run most clearly hands to the owner.

A second finding, quieter but squarely on the preregistered question: **the T8 smoke did not generalise.** The prereg quoted in advance that `elo_wdl_bridge` beat `dc_native` at both smoke cutoffs of 2025/26. Across the seasons R1 could score, `dc_native` has the lower mean TRPS at MW0, MW3, MW6 and MW10 and the higher one at MW19. The 2025/26 cells reproduce bit-for-bit (§9), so the reversal is other seasons disagreeing with that one — not a change in the harness. One season pointed one way; the rest mostly point the other; and every `dc_native − elo_wdl_bridge` interval spans zero, so the reversal is a change of sign in a mean, not a demonstration that the order is settled either way. That is what a one-season result was worth, which is why its direction was put on the record in advance rather than discovered now.

---

TRPS is primary and unweighted; wTRPS on the published consequence boundaries is secondary; the champion log loss is a floored diagnostic. Paired differences are a diagnostic with no pass rule (plan v2 §5). Nothing here is a betting signal, and a position is not a claim about qualification for any competition.

*R1 run and scored 2026-08-19 from ledger `data/epl/sim/retro_r1.jsonl`. Harness `epl-simretro-1` / metrics `epl-simmetrics-1`, hashes verified against the preregistration at the top of §1.*
