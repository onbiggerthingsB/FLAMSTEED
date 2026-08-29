# WHAT I CHECKED

I inspected repository Git objects at commit `f4540416f22ab6a1d486371c83c61cdd8bd577f6` only. I did not read repository working-tree paths, import repository code, execute tests, run the harness, or fit/simulate anything. There was no repository-pin deviation.

I read the two permitted prior verdict files, then inspected the pinned preregistration, harness, tests, and relevant protected implementation files. The review covered the complete prior inventory, the fourteen-row conformance report, power-note arithmetic, bootstrap implementation, digest split, freeze/first-fit guards, execution order, MANIFEST/evidence closure, and supersession index.

The ignored `data/` inputs are absent from the Git tree. Consequently I could not independently verify:

- the 85/52/62/6 and 16/19 membership counts from source data;
- the reported `52.53` canary magnitude;
- the synthetic-name disjointness test’s result;
- the two accidental-fit count, absence of local artifacts, or store mtime;
- the six power rows by executing `power_simulation`;
- the owner’s reported “14/14 green”, power reproduction, or test-suite pass.

Those facts are accepted only as statements in the pinned document/tests. Static inspection does show that “14/14 green” is not a substantive conformance result.

The two prior verdicts read were:

```text
/private/tmp/claude-502/-Users-likerun-Desktop-worldcup/d76b36e4-d8cb-4127-b2b4-671db457c2b0/scratchpad/codex-rev/widening-out.md
/private/tmp/claude-502/-Users-likerun-Desktop-worldcup/d76b36e4-d8cb-4127-b2b4-671db457c2b0/scratchpad/codex-rev/widen-rereview-out.md
```

Deduplicated exact Git-command log for the evidentiary reads:

```text
git cat-file -t f454041
git cat-file -p f454041
git cat-file -p f454041 | sed -n '1,8p'
git diff-tree --no-commit-id --stat -r 1b79cc5 f454041
git diff-tree --no-commit-id --name-status -r 1b79cc5 f454041
git diff-tree --no-commit-id -r --name-status 1b79cc5 f454041
git ls-tree -r --name-only f454041
git ls-tree -r --name-only f454041 data reports/evidence
git ls-tree -r --name-only f454041 -- reports/epl_widening_prereg.md epl/evwiden.py epl/tests/test_evwiden.py reports/evidence data/epl
git ls-tree -r --name-only f454041 -- reports/epl_widening_prereg.md epl/evwiden.py epl/tests/test_evwiden.py epl/simretro.py epl/leaguesim.py epl/table.py epl/simmetrics.py epl/score.py epl/walkforward.py
git ls-tree -r --name-only f454041 -- data/epl/fit/walkforward_predictions.parquet data/epl/fit/walkforward_ledger.jsonl data/epl/matches.parquet data/epl/sim/retro_r1.jsonl data/epl/fit/evwiden data/epl/sim/evwiden
git cat-file -e f454041:data/epl/matches.parquet
git cat-file -e f454041:data/epl/fit/walkforward_predictions.parquet
git show f454041:.gitignore
git show f454041:reports/epl_widening_prereg.md | wc -l
git show f454041:epl/evwiden.py | wc -l
git show f454041:epl/tests/test_evwiden.py | wc -l
git grep -n -E '^## |^### |^\*\*Supersed|R2-|R-B4|R-B5|R-H|R-I5|R-I6|R-X|Supersession index|Dated note' f454041 -- reports/epl_widening_prereg.md
git grep -n -i 'supersed' f454041 -- reports/epl_widening_prereg.md
git grep -n -E 'implementation_report|assert_implements_document|R2-B3|R2-B4|R2-B5|R2-H|R2-X|R2-Z|Supersession index|Dated note|freeze_block|assert_may_fit|TableMCImprecise|sampler.output|sampler_output|power' f454041 -- reports/epl_widening_prereg.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'Git identity|uncommitted two-line|freeze guard|first-real-fit|first real fit|committed bytes|harness_freeze_status|assert_may_fit' f454041 -- reports/epl_widening_prereg.md
git grep -n -E 'before one treated|before any treated|before treatment|parity oracle' f454041 -- reports/epl_widening_prereg.md epl/evwiden.py
git grep -n -E 'particle_rank|rank_mass|mc_boot|mc_seed|TableMCImprecise|sampler_digest|substantive_digest|plan_digest|table_parity|ArchiveRunner|assert_may_fit|budget|provisional_control|provisional_treatment|implementation_report|R2-B3|R2-B4|zero|0\.0002|P1|P2|P3|P4|P5|P6' f454041 -- epl/evwiden.py epl/tests/test_evwiden.py epl/table.py epl/leaguesim.py epl/simretro.py epl/simmetrics.py
git grep -n -E 'assert_may_fit\(' f454041 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'table_fits|table_simulations|total_fits|~4 hours|ParityRunner|run_parity|RUN_ORDER|PRE_FREEZE_RUNS|first post-freeze|results canary|single-opening' f454041 -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'tallies|tally_path|npz|tally_check|sampler_digest' f454041 -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg.md
git grep -n -E '^def (run_fits|run_table)|harness_frozen: bool = True|harness_frozen=True' f454041 -- epl/evwiden.py
git grep -n -A 55 -B 10 'def content_hash' f454041 -- epl/particles.py
git grep -n -E 'provisional|content_hash' f454041 -- epl/particles.py
git grep -n -A 170 -B 20 '^def verify' f454041 -- epl/evwiden.py
git grep -n -A 110 -B 20 '^def write_manifest' f454041 -- epl/evwiden.py
git grep -n -A 100 -B 20 '^def verify_manifest' f454041 -- epl/evwiden.py
git grep -n -A 55 -B 10 '^def canonical_json' f454041 -- epl/leaguesim.py
git grep -n -A 80 -B 20 '^def _jsonable' f454041 -- epl/leaguesim.py
git grep -n -E '^def build_store|STORE_DIR|results\.parquet|unlink\(' f454041 -- epl/fit.py epl/paths.py
git grep -n -E 'parity\.jsonl|tallies|first_real_fit\.json|widening(_per_fixture|_table_cells|_grid_means)?\.(json|csv)' f454041 -- epl/evwiden.py reports/epl_widening_prereg.md
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '1,900p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '1035,1190p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '1175,1275p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '1270,1525p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '1515,1740p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '1740,2013p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '2010,2245p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '2245,2463p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '2460,2699p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '2567,2643p'
git show f454041:reports/epl_widening_prereg.md | nl -ba | sed -n '2646,2699p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '400,455p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '590,625p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '630,715p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '1200,1815p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '1860,2120p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '2280,2470p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '2440,2825p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '2800,2870p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '3035,3105p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '3125,3565p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '3885,3970p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '3990,4225p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '4225,4850p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '4925,5420p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '5400,5735p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '5735,6030p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '6027,6380p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '6375,6570p'
git show f454041:epl/evwiden.py | nl -ba | sed -n '6645,6857p'
git show f454041:epl/particles.py | nl -ba | sed -n '315,365p'
git show f454041:epl/fit.py | nl -ba | sed -n '160,215p'
git show f454041:epl/leaguesim.py | nl -ba | sed -n '175,270p'
git show f454041:epl/leaguesim.py | nl -ba | sed -n '540,675p'
git show f454041:epl/leaguesim.py | nl -ba | sed -n '780,1030p'
git show f454041:epl/leaguesim.py | nl -ba | sed -n '1030,1255p'
git show f454041:epl/table.py | nl -ba | sed -n '350,390p'
git show f454041:epl/table.py | nl -ba | sed -n '535,605p'
git show f454041:epl/simmetrics.py | nl -ba | sed -n '180,270p'
git show f454041:epl/walkforward.py | nl -ba | sed -n '315,360p'
git show f454041:epl/walkforward.py | nl -ba | sed -n '445,510p'
git show f454041:src/wcmodel/model/draw_api.py | nl -ba | sed -n '210,240p'
git show f454041:src/wcmodel/model/widening.py | nl -ba | sed -n '215,240p'
git show f454041:epl/tests/test_evwiden.py | nl -ba | sed -n '80,270p'
git show f454041:epl/tests/test_evwiden.py | nl -ba | sed -n '1120,1425p'
git show f454041:epl/tests/test_evwiden.py | nl -ba | sed -n '1930,2638p'
git show f454041:epl/tests/test_evwiden.py | nl -ba | sed -n '2940,3275p'
git show f454041:epl/tests/test_evwiden.py | nl -ba | sed -n '3510,3675p'
git show f454041:epl/tests/test_evwiden.py | nl -ba | sed -n '3740,3952p'
```

# POWER-NOTE VERIFICATION

The note’s table is at `reports/epl_widening_prereg.md:2674-2681`; its claim is at `:2667-2669`.

Because the scratch and committed estimates use different, unrecoverable streams, the appropriate independent-run standard error for their difference is

\[
SE_\Delta=\sqrt{\frac{p_1(1-p_1)}{2000}+\frac{p_2(1-p_2)}{2000}}.
\]

The quoted `≈0.011` at `p≈0.45` and `≈0.007` at `p≈0.10` are single-estimate SEs, not SEs of a difference. The corresponding difference SEs are approximately `0.0157` and `0.0095`.

| Scenario, ρ | \|Δ power@bar\| | SE difference | z | \|Δ power@2×\| | SE difference | z | MDE relative change |
|---|---:|---:|---:|---:|---:|---:|---:|
| A, 0.0 | 0.010 | 0.015749 | 0.635 | 0.001 | 0.004790 | 0.209 | 0.4167% |
| A, 0.5 | 0.017 | 0.015587 | 1.091 | 0.006 | 0.007084 | 0.847 | 1.1590% |
| B, 0.0 | 0.019 | 0.009988 | 1.902 | 0.005 | 0.014793 | 0.338 | 0.0803% |
| B, 0.5 | 0.012 | 0.009357 | 1.282 | 0.007 | 0.014047 | 0.498 | 0.4808% |
| C, 0.0 | 0.008 | 0.007146 | 1.119 | 0.004 | 0.008819 | 0.454 | 1.1848% |
| C, 0.5 | 0.003 | 0.006590 | 0.455 | 0.001 | 0.008603 | 0.116 | 1.0625% |

Arithmetic rulings:

- Under a one-SE comparator, four of six `power@bar` differences exceed the correct difference SE: A/0.5, B/0.0, B/0.5, and C/0.0. All six `power@2×` differences are within one difference SE.
- All twelve are within `1.96 × SE_difference`; B/0.0 at the bar is closest, at `1.902 SE`. Thus a defensible statement would be “none differs significantly at approximately 95%,” not “every difference is inside Monte-Carlo error” followed by one-SE figures.
- The note’s quoted SEs are the wrong quantity for comparing two streams. Its claim does not survive the comparator it quotes.
- The MDE range recomputed from the displayed values is **0.0803%–1.1848%**. The upper endpoint rounds to `1.2%`; the claimed lower endpoint `0.02%` is not reproducible.

This is an IMPORTANT false supporting claim, not by itself a blocker. The corrected numbers were supplied pre-freeze and do not condition on an experiment outcome. The table can be corrected honestly before a new freeze.

The attestation disclosure at `reports/epl_widening_prereg.md:2688-2699` is candid enough to establish the fatal event, but not independently complete: it provides no exact test names, logs, timestamps, or durable evidence, and the ignored data state prevents checking the claimed lack of artifacts or store mtime.

More importantly, its conclusion is wrong. Protected `ArchiveRunner` parity is a mandatory 35-fit experiment leg (`reports/epl_widening_prereg.md:2104-2123,2133-2139`; `epl/evwiden.py:4485-4543`). R-B6 applies after **any** real fit whether or not it produced a delta or artifact (`reports/epl_widening_prereg.md:1252-1258`). Therefore those two ADVI fits were fits of this experiment. “Not through the treatment path” does not preserve the no-fit attestation.

# FINDING-BY-FINDING

## B1 — REPAIRED

The text requires both arms from one posterior and demotes the corpus to an external control (`reports/epl_widening_prereg.md:930-959`). One fit feeds incumbent and enlarged predict passes, while the deciding delta is Arm A minus recomputed Arm B and `delta_vs_corpus` remains separate (`epl/evwiden.py:1760-1812,2171-2233`).

## B2 — REPAIRED

The document replaces the pooled table gate with MW6 plus separate MW0/MW3/MW10 treated-cell means (`reports/epl_widening_prereg.md:963-1036`). The code computes those horizons, marks MW19 structural, removes pooled output, and decides only on iv-a/b/c (`epl/evwiden.py:5134-5177,5242-5256,5276-5404`).

## B3 — STILL-OPEN

The text now specifies a tie-aware joint estimator (`reports/epl_widening_prereg.md:1812-2009`), and most of it is implemented (`epl/evwiden.py:4032-4113,4936-5062`). The code leg still fails because:

- frozen table-CI `B=10,000` is overridable through `--n-boot` and passed into scoring without refusal (`epl/evwiden.py:6665-6676,6814-6818`);
- P5 uses the equal-weight mean’s MC SE as a purported bound on a nonlinear season-bootstrap quantile (`epl/evwiden.py:5032-5055,5140-5152,5366-5370`), which is not conservative;
- deciding tally sidecars are later trusted without rebinding (`epl/evwiden.py:4724-4736,5180-5201`).

## B4 — STILL-OPEN

The document requires all-35 protected/new-control parity before one treated simulation (`reports/epl_widening_prereg.md:1133-1139,2133-2139`). The harness first generates protected rows, but `TableRunner` then simulates control and treatment before `run_table` compares the control with protected output (`epl/evwiden.py:4327-4362,4766-4770,4794-4823`). `--table --limit` can also reduce “all 35” to a caller-supplied subset (`epl/evwiden.py:4604-4625,6799-6803`).

## B5 — STILL-OPEN

Prospective text and an artifact-aware guard now exist (`reports/epl_widening_prereg.md:1182-1229,2213-2241`; `epl/evwiden.py:1980-2034`). Both legs nevertheless fail:

- the note admits pre-freeze real parity fits (`reports/epl_widening_prereg.md:2688-2699`);
- required “read-only” pre-freeze routes call `table_cells`, which calls `build_store` at the shared default store (`epl/evwiden.py:3930-3953,6317-6324,6506-6525,6725-6740`); `build_store` can unlink and rewrite `results.parquet` (`epl/fit.py:177-203`).

## B6 — STILL-OPEN

The normative text correctly forbids all post-fit hashed-file changes (`reports/epl_widening_prereg.md:1233-1269,2196-2200`). Enforcement is directory-local: `first_real_fit.json` is read and written below the caller’s chosen directory, and absence simply returns (`epl/evwiden.py:2030-2104`). A fresh/deleted directory loses history, while `harness_freeze_status` merely reports the default record and does not condition `frozen` on it (`epl/evwiden.py:6162-6167`). The admitted fits also appear to have already triggered this regime.

## I1 — REPAIRED

The complete realised-configuration digest is pinned in the text (`reports/epl_widening_prereg.md:1274-1303`). Code hashes the full realised configuration and checks the file, seed, widening mode, and realised digest on production paths (`epl/evwiden.py:637-705,1690-1692,4263-4264`).

## I2 — STILL-OPEN

The fixed-scenario joint power simulation, grid, interpolation, and corrected rows now exist (`reports/epl_widening_prereg.md:1307-1397,2464-2557`; `epl/evwiden.py:3132-3503`). But the document also requires the realised treated SD and the **joint-gate MDE recomputed at that realised SD** (`reports/epl_widening_prereg.md:1392-1397`). Code reports the SD beside a different two-sided-zero-test MDE and explicitly says the joint MDE remains the fixed-scenario simulation’s (`epl/evwiden.py:3071-3091`); `power_simulation` loops only A/B/C (`epl/evwiden.py:3397-3449`).

## I3 — REPAIRED

Round two correctly labels the bar invented, fixes the unit comparisons, and limits the claim to touched fixtures (`reports/epl_widening_prereg.md:2382-2460`). The code applies the stated threshold and publishes the required limited-materiality sentence (`epl/evwiden.py:3583-3589,5721-5738`).

## I4 — REPAIRED

The mutation, masks, exact comparator, row counts, and positive control are frozen (`reports/epl_widening_prereg.md:1447-1482`). Code implements unique sentinels, `array_equal`, both mask counts, the set comparisons, and positive-control magnitude (`epl/evwiden.py:2471-2586,6601-6613`).

## I5 — REPAIRED

R2-I5 corrects the inventory to three generators and five names and makes ancestry checking an obligation (`reports/epl_widening_prereg.md:2280-2314`). Tests enumerate them, check pinned-artifact disjointness, and block generator I/O (`epl/tests/test_evwiden.py:200-255`). The result of the pinned disjointness check could not be independently verified because its inputs are absent from Git.

## I6 — STILL-OPEN

The text freezes fields and eleven paths (`reports/epl_widening_prereg.md:1515-1576,2323-2378`), but the implementation is not closed:

- deciding `parity.jsonl` and tally NPZ files are omitted from `MANIFEST_PATHS` (`epl/evwiden.py:4708-4736,4766-4770,5455-5469`);
- manifest byte sizes are parsed but never compared (`epl/evwiden.py:5806-5852`);
- `--verify` does not reproduce the table/MC/adoption decision (`epl/evwiden.py:5923-6019`);
- main removes top-level `scored.per_cell` before evidence projection, making required table-parity and coverage fields empty (`epl/evwiden.py:5686-5696,5708-5711,6827-6843`).

## M1 — REPAIRED

The text corrects the union to `e* ≤ 12` (`reports/epl_widening_prereg.md:1580-1586`); the grid includes 12 and the implemented membership/opening construction reaches that endpoint (`epl/evwiden.py:245,1136-1153`).

## M2 — REPAIRED

The text now binds the canary to `finalize_grid` and handles the documented edge no-op (`reports/epl_widening_prereg.md:1590-1612`). Code exercises the production path, records branch choice, and requires a moving interior case (`epl/evwiden.py:2641-2765`).

## M3 — REPAIRED

The LOSO precedent is withdrawn and no grid selection is claimed (`reports/epl_widening_prereg.md:1616-1635`). `E_STAR` is fixed, the grid is reporting-only, and `adoption` has no grid argument (`epl/evwiden.py:236-245,3560-3562`).

## M4 — REPAIRED

The disclaimer now distinguishes 85 thin fixtures from 52 touched fixtures (`reports/epl_widening_prereg.md:1639-1646`). Code separately forms thin and treated populations and enforces exact zero for untreated rows (`epl/evwiden.py:2982-3015`).

## M5 — REPAIRED

The support citation is narrowed to the actual forecast canary and the 820-fixture control is correctly framed as a test (`reports/epl_widening_prereg.md:1650-1667`). Protected code confirms the fast-path check is only a feature-frame check, while the point-in-time canary fits and compares forecasts (`epl/walkforward.py:321-354,450-506`; `epl/evwiden.py:1788-1807`).

## N-B3-TIE — REPAIRED

This is the re-review’s “wrong tie statistic” blocker. The text uses fractional rank mass rather than ordinal `.order` (`reports/epl_widening_prereg.md:1833-1841,1864-1897`); code constructs `Ranking` and calls protected `position_mass` (`epl/evwiden.py:4032-4113`; `epl/table.py:550-593`).

## N-B3-COV — REPAIRED

This is the false cross-cell-independence blocker. Text requires one joint particle-index resample across all 32 tallies (`reports/epl_widening_prereg.md:1908-1958`). Code draws one `picked` vector per replicate, applies it to every arm/cell, and computes label means inside that replicate (`epl/evwiden.py:5026-5059`).

## N-B3-ZERO — STILL-OPEN

P4 correctly protects the MW6 mean-zero boundary. P5 does not protect the CI endpoint: it compares the season-bootstrap lower quantile with the MC SE of the equal-weight mean (`reports/epl_widening_prereg.md:1980-1991`; `epl/evwiden.py:5032-5055,5140-5152,5366-5370`).

A counterexample is cross-cell MC error proportional to `(+h,−h,0,…,0)`: mean error and therefore `mc_se_mw6` can be zero while unequal season-bootstrap multiplicities move the lower quantile across zero. P5 can then fail to fire while iv-c changes from FAIL to PASS.

## N-B4-TAUTOLOGY — REPAIRED

`sampler_digest` now excludes the provisional set and other metadata (`reports/epl_widening_prereg.md:2034-2047`; `epl/evwiden.py:4120-4150`). The treated/untreated identity rule reads that digest and compares provisional membership separately (`epl/evwiden.py:4409-4478`).

## N-B4-BUDGET — REPAIRED

The specific oracle-versus-table-budget contradiction is repaired. Text and `_plan` agree on 70 table fits and 105 simulations with an approximately four-hour bound (`reports/epl_widening_prereg.md:2104-2131`; `epl/evwiden.py:6537-6553`). The erroneous whole-experiment total is a separate new defect.

## N-FREEZE-COMMIT — STILL-OPEN

Committed Git-byte and ancestry checks now exist, but the full obligation includes schema, membership, and first-fit state (`reports/epl_widening_prereg.md:1769-1779`). The guard parses only the two harness hashes; schema/ membership are not validated and first-fit is merely returned (`epl/evwiden.py:6118-6167`). A test accepts a mocked committed source containing only two hash lines as frozen (`epl/tests/test_evwiden.py:3137-3167`).

## N-RH-FIRST-ACT — STILL-OPEN

The text now names results canary, manual single opening, then shards→merge→table (`reports/epl_widening_prereg.md:2164-2207`). The launcher performs canary→shards→table→merge, has no Step-2 completion marker, and would rerun the once-only canary after manual Steps 1–2 (`epl/evwiden.py:6457-6487`). Tests enforce the contradictory sequence (`epl/tests/test_evwiden.py:3262-3268`).

## N-RX-REFUSAL — REPAIRED

The text distinguishes 23 named refusal subclasses from 24 classes including the base and makes P1–P5 an `UNRESOLVED` result rather than an exception (`reports/epl_widening_prereg.md:2245-2276`). `TableMCImprecise` now has structural-only scope (`epl/evwiden.py:605-617`).

## N-SUP-PREFREEZE — REPAIRED

R2-B5 expressly supersedes the introduction’s synthetic-only clause and enumerates six permitted passes (`reports/epl_widening_prereg.md:2213-2241,2612-2613`). Code carries the six-entry enumeration (`epl/evwiden.py:419-446`). The implementation’s store-writing side effect is a new defect, not an unnamed supersession.

## N-DIGEST-STATE — REPAIRED

The complete `SimPlan` field set is specified (`reports/epl_widening_prereg.md:2049-2060,2088-2102`) and serialized into `substantive_digest` (`epl/evwiden.py:4153-4219`). An indirect provisional-set inclusion remains a separate new inconsistency.

## N-LIFECYCLE-CHECKABILITY — STILL-OPEN

Round two initially repairs the overstatement by calling no-fit history an attestation rather than a mechanically provable fact (`reports/epl_widening_prereg.md:1756-1767`). The dated note then makes that attestation false while repeating it: it admits real fits through the required parity leg and nevertheless says “no fit of this experiment anywhere” (`reports/epl_widening_prereg.md:2688-2699`; `epl/evwiden.py:4485-4543`).

## N-I5-ANCESTRY — REPAIRED

The text converts the nonexistent check into a precise obligation (`reports/epl_widening_prereg.md:2302-2314`), and tests now cover the five names, disjointness, and generator I/O (`epl/tests/test_evwiden.py:200-255`).

## N-I6-LIST — REPAIRED

The particular category-versus-list defect is repaired: the document names four shards and eleven literal paths (`reports/epl_widening_prereg.md:2338-2370`), and code carries the same path tuple and exact-membership validator (`epl/evwiden.py:5455-5469,5821-5862`). The list is substantively incomplete and the four-shard constant is not enforced, but those are new defects.

## SH-B5-INTRO — REPAIRED

The synthetic-only introduction is explicitly superseded by R2-B5 and indexed (`reports/epl_widening_prereg.md:2213-2241,2612-2613`); the harness contains the six-pass enumeration (`epl/evwiden.py:419-446`).

## SH-B4-BUDGET — REPAIRED

The old 35-fit/70-simulation budget is quoted and superseded with 70/105 (`reports/epl_widening_prereg.md:2016-2023,2104-2131,2611`); `_plan` carries that table subtotal (`epl/evwiden.py:6537-6553`).

## SH-H-FIRST-ACT — REPAIRED

The contradictory first-act clauses are expressly superseded and the canary is now named first (`reports/epl_widening_prereg.md:2143-2209,2633-2634`). The launcher also begins with the canary (`epl/evwiden.py:6457-6463`). Its remaining Step-2/table-order failure is separately ruled above.

## SH-B4-H-DIGEST — REPAIRED

The provisional-set-in-digest contradiction is repaired for the identity test: R2-B4 creates `sampler_digest`, excludes provisional metadata, and reissues R-H on it (`reports/epl_widening_prereg.md:2025-2086,2609-2610`; `epl/evwiden.py:4120-4150,4409-4448`).

Prior-finding total: **10 STILL-OPEN**.

# NEW DEFECTS

The following are new defects at `f454041`. Defects already counted as prior-open—particularly invalid P5, overridable `B`, and incomplete freeze parsing—are not counted again here.

## NB1 — BLOCKING — the current preregistration is already invalidated

The note admits two pre-freeze real ADVI fits through the mandatory parity path (`reports/epl_widening_prereg.md:2688-2699`). Parity is expressly part of the experiment (`reports/epl_widening_prereg.md:2104-2123,2133-2139`), and R-B6 says any real fit counts without requiring a delta, ledger row, or artifact (`reports/epl_widening_prereg.md:1252-1258`).

The fits occurred before the guard landed, hence before subsequent changes to hashed harness files. Under R-B6’s own remedy, this document cannot be repaired into legitimacy; a new preregistration is required.

## NB2 — BLOCKING — required pre-freeze “read-only” commands can mutate the store

R-B5 forbids building under `paths.STORE_DIR` or writing inside the repository (`reports/epl_widening_prereg.md:1221-1226`). Yet `--membership`, `--plan`, and `--freeze-block` all reach `table_cells`, which invokes `build_store(played)` with the default root (`epl/evwiden.py:3930-3953,6317-6324,6506-6525,6725-6740`). `build_store` can unlink and rewrite the shared parquet (`epl/fit.py:177-203`).

## NB3 — BLOCKING — `assert_may_fit` trusts the Boolean it must establish

The CLI obtains live freeze state, but public fit surfaces accept caller-supplied `harness_frozen=True`: `Engine`, `TableRunner`, `ParityRunner`, `run_fits`, and `run_table` (`epl/evwiden.py:1671-1688,2299-2306,4243-4262,4507-4522,4739-4748`). `assert_may_fit` trusts the value and performs no Git verification when true (`epl/evwiden.py:1980-2034`). A direct harness call can therefore fit pinned artifacts while unfrozen, contradicting “anywhere” (`reports/epl_widening_prereg.md:1769-1773`).

## NB4 — BLOCKING — parity is neither all-35 nor established before treatment

`run_parity_oracle` produces protected rows first, but new-control parity is checked only after `TableRunner` has already simulated treatment (`epl/evwiden.py:4327-4362,4794-4823`). `--table --limit` reduces completeness to the truncated input, and `require_parity=False` is an exposed API bypass (`epl/evwiden.py:4579-4625,4739-4748,4824-4827,6799-6803`).

## NB5 — BLOCKING — first-fit state is deletable and directory-scoped

The global R-B6 regime is stored as `<directory>/first_real_fit.json`; an absent record is interpreted as no prior fit (`epl/evwiden.py:1924-1930,2037-2104`). It is not committed or manifested, and the record’s own commit/prereg blob are not later validated. Changing/deleting the directory resets the protection.

## NB6 — BLOCKING — no executable path implements R2-H’s frozen sequence

R2-H requires results canary→single-opening exercise→four shards→merge→parity/table, with nothing else on the archive between (`reports/epl_widening_prereg.md:2164-2194`). The launcher omits any Step-2 marker, immediately starts shards, and puts table before merge (`epl/evwiden.py:6457-6487`). `require_run_preconditions` checks only the canary (`epl/evwiden.py:2816-2862`).

## NB7 — BLOCKING — deciding tally sidecars are mutable and unverifiable

The 32 deciding arrays are removed from ledger rows and written as NPZ sidecars (`epl/evwiden.py:4401-4405,4708-4736,4810-4834`). Reloading checks neither their digest against the ledger nor their matrix/tally invariant before using them to decide P1–P5 (`epl/evwiden.py:4724-4736,5180-5201`). They are absent from the eleven-path MANIFEST, and `verify` never rederives the table gate (`epl/evwiden.py:5455-5469,5923-6019`).

A structurally valid replacement can alter MC SEs—and potentially change UNRESOLVED to PASS—without changing any manifested digest.

## NB8 — BLOCKING — the fourteen-row conformance gate grades names, not obligations

`freeze_block` treats `assert_implements_document` as permission to freeze (`epl/evwiden.py:6260-6283,6307-6316`), but the predicates at `epl/evwiden.py:6199-6256` are:

| Row | What it actually checks |
|---|---|
| R-B1 | three field names exist |
| R-B2 | keys/constants on a hand-built ideal gate |
| R2-B3 | constants, refusal-class name, P1–P5 labels |
| R2-B4 | protected signature and three callables |
| R2-B5 | one callable and six strings |
| R-B6 | three callables |
| R-I1 | 64-character constant and source substring |
| R2-I2 | two callables |
| R-I4 | source substring and callable |
| R2-I5 | a test-function name occurs in working-tree text |
| R2-I6 | list length, `SHARDS` constant, two column names |
| R-M2 | source substring and callable |
| R2-X | subclass count |
| R2-I2 numbers | compares a supplied/generated power object after rounding; does not cover realised-MDE publication |

R2-H has no row at all. The test merely asserts that every self-reported row is green (`epl/tests/test_evwiden.py:3885-3893`). The report can therefore be 14/14 while current B3/B4/B5/B6/R2-H obligations fail.

## NI1 — IMPORTANT — the power-note supporting claim is false

The correct power-difference SE and MDE range are given above. The displayed table supports a 95%-interval statement, not the quoted one-SE statement, and supports `0.08%–1.18%`, not `0.02%–1.2%` (`reports/epl_widening_prereg.md:2667-2681`).

## NI2 — IMPORTANT — `substantive_digest` indirectly includes the excluded provisional set

The text explicitly excludes provisional membership (`reports/epl_widening_prereg.md:2049-2060`). Code includes `effective_posterior_hash`, supplied as `book.content_hash()` (`epl/evwiden.py:4202-4217,4344-4351`), and `ParticleBook.content_hash()` hashes `sorted(self.provisional)` (`epl/particles.py:331-358`). This does not revive the sampler-identity tautology, but it directly contradicts the digest definition.

## NI3 — IMPORTANT — the whole-experiment budget is five fits short

The document and `_plan` report 148 fits: 78 match openings plus 70 table fits (`reports/epl_widening_prereg.md:2122-2127`; `epl/evwiden.py:6540-6546`). They omit four mandatory results-canary fits and the single-opening exercise (`reports/epl_widening_prereg.md:2155-2189`). The prescribed total is 153.

## NI4 — IMPORTANT — MANIFEST/schema enforcement remains incomplete

- Byte sizes are recorded but not validated (`reports/epl_widening_prereg.md:2347-2349`; `epl/evwiden.py:5806-5852`).
- `SHARDS=4` is not enforced: CLI and launcher accept other values (`reports/epl_widening_prereg.md:2338-2341`; `epl/evwiden.py:6397-6423,6665-6670,6765-6787,6806-6825`).
- R2-B3 promises P1–P6 values/booleans, while evidence carries P1–P5 and explains P6 away (`reports/epl_widening_prereg.md:2005-2009`; `epl/evwiden.py:5388-5401`).
- Top-level `scored.per_cell` is stripped before JSON evidence projection, emptying required parity and coverage diagnostics (`epl/evwiden.py:5686-5696,5708-5711,6827-6843`).

## NI5 — IMPORTANT — the supersession index’s “complete” claim is false

R2-B3 explicitly supersedes R-I6’s `mc_se_mean` field (`reports/epl_widening_prereg.md:2005-2010`) but the index omits it (`:2604-2606,2626-2627`). R2-X also changes `TableMCImprecise` from covering UNRESOLVED to structural-only (`:2266-2269`), while its supersession quote/index row names only the class count (`:2247-2248,2635`).

## NI6 — IMPORTANT — the frozen tally invariant is dimensionally wrong in text

The text defines `T[s]` as unnormalised accumulated mass and then requires `T.sum(axis=0) == run.matrix` (`reports/epl_widening_prereg.md:1876-1878,1888-1897`). The correct implementation divides by `n_sims` (`epl/evwiden.py:4080-4099`). The code is mathematically right, but it does not implement the literal frozen equation.

## NM1 — MINOR — generator wording regressed

R2-I5 correctly establishes three generators, then says “both generators” (`reports/epl_widening_prereg.md:2289-2319`).

New blocking-defect total: **8**.

# SUPERSESSION HYGIENE

The four previously named hygiene failures are narrowly repaired:

- introduction versus R-B5: repaired by R2-B5 and index row 19;
- oracle versus old budget: repaired by R2-B4 and index row 17;
- impossible first act: repaired textually by R2-H and index rows 39–40;
- provisional-set digest versus treated inequality: repaired by the `sampler_digest` split and index rows 15–16.

However, the current index is still **not clean**:

- it omits R2-B3’s supersession of R-I6’s `mc_se_mean`;
- it omits R2-X’s semantic change to `TableMCImprecise`;
- R2-I5 retains “both generators” after correcting the inventory to three;
- the substantive digest’s indirect provisional inclusion contradicts R2-B4’s exclusion claim.

The direct later prose usually makes the intended rule recoverable, so these new index defects are IMPORTANT/MINOR rather than additional blockers. They nevertheless defeat the heading’s assertion that the index is complete.

# VERDICT

DO-NOT-FREEZE — **10 prior findings remain STILL-OPEN; 8 NEW blocking defects exist.**

The current §6 freeze block must not be pasted, and the first intended fit must not begin.

Before a legitimate freeze:

1. Treat this preregistration as invalidated by the disclosed pre-freeze parity fits; create a new preregistration/freeze rather than repairing this document in place.
2. Make all pre-freeze routes genuinely read-only and make freeze/first-fit state unforgeable, global, schema-and-membership-bound, and independent of caller-supplied Booleans/directories.
3. Enforce the exact post-freeze order and establish all-35 protected/new-control parity before any treatment simulation, with no `--limit` or API bypass.
4. Replace P5 with actual propagated uncertainty for the season-CI endpoint, bind/manifest every deciding tally/parity artifact, and make verification recompute the table gate and evidence contract.
5. Replace the existence-based conformance report with behavioral predicates that would fail on the defects above, and correct the power-note, budget, digest, MANIFEST, and supersession statements before the new freeze.

