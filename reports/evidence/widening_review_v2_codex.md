# WHAT I CHECKED

I inspected repository Git objects at commit `1afd54d8c5e9dde61dbbd046c95d07d4b96f0267` only. I did not read repository working-tree paths, import working-tree code, execute tests, or run the harness.

I read, in full:

- `reports/epl_widening_prereg_v2.md`
- the closing section of `reports/epl_widening_prereg.md`
- `epl/evwiden.py`
- `epl/tests/test_evwiden.py`
- relevant pinned supporting modules, including `epl/simretro.py`, `epl/particles.py`, `epl/walkforward.py`, and `src/wcmodel/data/store.py`
- all 22 commit messages in `f454041..1afd54d`
- all four permitted `/private/tmp/...` case-history files.

There was no pin deviation in repository evidence. A system-provided memory registry affected only presentation style, not factual or scientific conclusions.

Because `data/` is ignored and absent from the pinned Git tree (`.gitignore:14-16`), I could not independently verify:

- the corpus/archive/ledger digests or row counts;
- the 85/52 membership census, 35-cell 16/19 split, or per-label 3/2/7/4/0 counts;
- actual posterior particles, observed tallies, SEs, or unanimity outcomes;
- the shared-store 184,115-byte size and unchanged mtime;
- that exactly two prior ADVI fits occurred, both failed where stated, and produced no delta, estimand, ledger row, or artifact;
- the reported 241-file tests, 1,331 passes/1 skip, `LOCK VALID`, or absence of experiment artifacts.

Those numbers are accepted on the document’s or tests’ word. I did independently verify the declared algorithms, formulas, path inventories, budget arithmetic, control flow, and statically visible refusal/bypass paths.

<details>
<summary>Deduplicated exact Git command log</summary>

```text
git rev-parse '1afd54d^{commit}'
git rev-parse 1afd54d^{commit}
git cat-file -t 1afd54d
git cat-file -t 1afd54d8c5e9dde61dbbd046c95d07d4b96f0267
git cat-file -p 1afd54d
git cat-file -p 1afd54d8c5e9dde61dbbd046c95d07d4b96f0267
git diff-tree --no-commit-id --stat -r f454041 1afd54d
git diff-tree --no-commit-id --name-status -r f454041 1afd54d
git diff-tree --no-commit-id --name-only -r f454041..1afd54d
git log --oneline f454041..1afd54d
git log --format='%h %s%n%b' f454041..1afd54d
git log --format='%h %s%n%b' f454041..1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v2.md
git ls-tree -r --name-only 1afd54d -- reports/epl_widening_prereg.md reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git ls-tree -r --name-only 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py reports/evidence data/epl
git ls-tree -r --name-only 1afd54d -- data/epl/fit/walkforward_predictions.parquet data/epl/fit/walkforward_ledger.jsonl data/epl/matches.parquet data/epl/sim/retro_r1.jsonl data/epl/fit/evwiden data/epl/sim/evwiden reports/evidence/widening.json
git ls-tree -r --name-only 1afd54d8c5e9dde61dbbd046c95d07d4b96f0267 -- data
git cat-file -e 1afd54d:data/epl/matches.parquet
git cat-file -e 1afd54d:data/epl/fit/walkforward_predictions.parquet
git cat-file -e 1afd54d:data/epl/sim/retro_r1.jsonl
git show 1afd54d:.gitignore
git show 1afd54d:reports/epl_widening_prereg.md | wc -l
git show 1afd54d:reports/epl_widening_prereg_v2.md | wc -l
git show 1afd54d:epl/evwiden.py | wc -l
git show 1afd54d:epl/tests/test_evwiden.py | wc -l
git grep -n -E '^#|^##|^###' 1afd54d -- reports/epl_widening_prereg_v2.md
git grep -n -E 'R2-|R-B[1-6]|R-H|R-I[1-6]|R-M[1-5]|R-X|SH-|N-B|N-R|N-SUP|N-DIGEST|N-I|NB[1-8]|NI[1-6]|NM1|A[1-7]' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'mc_se_mean|P1–P6|P1-P6|P6|both generators|effective_posterior_hash' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'read.only|read_only|StoreNotBuilt|build_store|first.fit|first_fit|sequence|SequenceViolation|freeze.commit|freeze_commit|assert_may_fit|require_harness_freeze|Engine|TableRunner|ParityRunner|run_fits|publication|publish' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E '^def (read_only_store|assert_may_fit|run_fits|run_table|run_parity|write_sequence|require_sequence|freeze|launch|_plan|main)|^class (Engine|TableRunner|ParityRunner|StoreNotBuilt|SequenceViolation)' 1afd54d -- epl/evwiden.py
git grep -n -E 'assert_may_fit\(|Engine\(|TableRunner\(|ParityRunner\(|run_fits\(|run_table\(|read_only_store\(|build_store\(' 1afd54d -- epl/evwiden.py
git grep -n -E 'add_argument\(.*(frozen|freeze|fit|dir|root|store|limit|parity|shard)|--(membership|plan|freeze-block|power|canar|conformance|run|table|merge|evidence|verify|launch)' 1afd54d -- epl/evwiden.py
git grep -n -E 'ExcludedMassTooLarge|man_city|sheffield_united|two.*fit|v1 fit|b112b51' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py epl/simretro.py epl/particles.py
git grep -n -E 'implementation_report|L1|L2|L3|L4|L5|L6|L7|L8|L9|L10|L11|L12|L13|L14|L15|L16|L17|L18' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'unanim|tally_sha256|MANIFEST|52 paths|byte size|--verify|scored\.per_cell|substantive_digest|MC_BOOT|SHARDS|conditions|prereg' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'score_table\(|table_gate\(|unanimity\(|unanimity_fired\(' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n 'assert_not_overridable' 1afd54d -- epl/evwiden.py
git grep -n -E '^DEFAULT_N_SIMS|^SEED' 1afd54d -- epl/simretro.py
git grep -n -E 'draws:|volatility_window|seed:' 1afd54d -- config/config.yaml
git grep -n -E 'sampler_digest|TableRunner|signature|identity control|structural-zero|EXPECTED_TREATED_BY_LABEL|controls\.untreated|three generators' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'identity_canary|grid_treated|pass-2|pass 2' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v2.md
git grep -n -E '^def assert_structural_zeros|assert_structural_zeros\(|def estimand|def measured_controls|EXPECTED_TREATED_BY_LABEL|assert_table_census' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'POWER_|PUBLISHED_POWER|realised_power|power_simulation|_plan|total_fits|table_simulations|153|105' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v2.md
git grep -n -E 'joint_mde|sd_paired_treated|power\.realised|realised.*power' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v2.md
git grep -n -E 'sequence|SequenceViolation|marker|launcher|first_real_fit|publication|single.opening|results canary|scratch' 1afd54d -- reports/epl_widening_prereg_v2.md epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'require_sequence\(|write_sequence_marker\(|require_run_preconditions\(' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py
git grep -n -E 'step1_results_canary|step2_single_opening|step3_shards|step4_merge|step5_parity' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v2.md
git grep -n -E 'harness_freeze|harness_frozen|check_implementation|pre_freeze_runs' 1afd54d -- epl/evwiden.py epl/tests/test_evwiden.py reports/epl_widening_prereg_v2.md
git grep -n -E '^class BitemporalStore|def __init__|results.parquet' 1afd54d -- src/wcmodel/data/store.py
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '1,620p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '601,1200p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '1201,1800p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '1801,2329p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '473,610p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '678,850p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '1087,1335p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '1380,1565p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '1640,2105p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '2038,2230p'
git show 1afd54d:reports/epl_widening_prereg_v2.md | nl -ba | sed -n '2184,2329p'
git show 1afd54d:reports/epl_widening_prereg.md | nl -ba | tail -n 85
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '1,510p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '700,1515p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '1760,2325p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '2440,3215p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '3270,4055p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '4135,4555p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '4560,5335p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '5328,6335p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '6330,7130p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '6970,7425p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '7420,8095p'
git show 1afd54d:epl/evwiden.py | nl -ba | sed -n '8080,8678p'
git show 1afd54d:epl/tests/test_evwiden.py | nl -ba | sed -n '1080,1315p'
git show 1afd54d:epl/tests/test_evwiden.py | nl -ba | sed -n '1550,1855p'
git show 1afd54d:epl/tests/test_evwiden.py | nl -ba | sed -n '2600,3050p'
git show 1afd54d:epl/tests/test_evwiden.py | nl -ba | sed -n '3070,3730p'
git show 1afd54d:epl/tests/test_evwiden.py | nl -ba | sed -n '3830,4415p'
git show 1afd54d:epl/tests/test_evwiden.py | nl -ba | sed -n '4480,5015p'
git show 1afd54d:epl/tests/test_evwiden.py | nl -ba | sed -n '5040,5390p'
git show 1afd54d:epl/simretro.py | nl -ba | sed -n '470,585p'
git show 1afd54d:epl/simretro.py | nl -ba | sed -n '1175,1225p'
git show 1afd54d:epl/particles.py | nl -ba | sed -n '620,685p'
git show 1afd54d:epl/walkforward.py | nl -ba | sed -n '430,520p'
git show 1afd54d:src/wcmodel/data/store.py | nl -ba | sed -n '1,180p'
git show 1afd54d:reports/epl_widening_prereg.md | sed -n '2676,2681p' | awk -F'|' '{split($4,p,"→"); split($5,m,"→"); split($7,q,"→"); for(i=1;i<=2;i++){gsub(/[^0-9.]/,"",p[i]); gsub(/[^0-9.]/,"",m[i]); gsub(/[^0-9.]/,"",q[i])} sep=sqrt(p[1]*(1-p[1])/2000+p[2]*(1-p[2])/2000); seq=sqrt(q[1]*(1-q[1])/2000+q[2]*(1-q[2])/2000); printf "%s rho=%s dbar=%.3f SEdbar=%.6f zbar=%.3f d2x=%.3f SEd2x=%.6f z2x=%.3f MDErel=%.4f%%\n", $2,$3,(p[1]-p[2]<0?p[2]-p[1]:p[1]-p[2]),sep,(p[1]-p[2]<0?p[2]-p[1]:p[1]-p[2])/sep,(q[1]-q[2]<0?q[2]-q[1]:q[1]-q[2]),seq,(q[1]-q[2]<0?q[2]-q[1]:q[1]-q[2])/seq,100*(m[1]-m[2]<0?m[2]-m[1]:m[1]-m[2])/m[1]}'
git show 1afd54d:reports/epl_widening_prereg_v2.md | sed -n '572,577p' | awk -F'|' 'NR<=5 {fit=$3; sim=$4; gsub(/[^0-9]/,"",fit); gsub(/[^0-9]/,"",sim); fits+=fit+0; sims+=sim+0} END {printf "component sum: fits=%d simulations=%d\n",fits,sims}'
```

</details>

# CONTINUITY OF LAW

## Repaired-at-`f454041` inventory

| Finding | Ruling | v2 law | Pinned harness |
|---|---|---|---|
| `B1` | **HELD** | `reports/epl_widening_prereg_v2.md:480-516` | `epl/evwiden.py:1919-1961,2366-2427` |
| `B2` | **HELD** | `reports/epl_widening_prereg_v2.md:860-867,892-907` | `epl/evwiden.py:5950-5966,6132-6150,6170-6225` |
| `I1` | **HELD** | `reports/epl_widening_prereg_v2.md:67-94` | `epl/evwiden.py:776-833` |
| `I3` | **HELD** | `reports/epl_widening_prereg_v2.md:927-1010` | `epl/evwiden.py:274-290` |
| `I4` | **HELD** | `reports/epl_widening_prereg_v2.md:1607-1632` | `epl/evwiden.py:2651-2793` |
| `I5` | **HELD** | `reports/epl_widening_prereg_v2.md:1659-1689` | `epl/tests/test_evwiden.py:198-257` |
| `M1` | **REGRESSED** | Correct `e*≤12` law at `reports/epl_widening_prereg_v2.md:480-482` | Behavior is correct at `epl/evwiden.py:1279-1281`, but the old false wording “`e* < 12` union” returned at `epl/evwiden.py:361-364,1269-1271`. |
| `M2` | **HELD** | `reports/epl_widening_prereg_v2.md:1637-1653` | `epl/evwiden.py:2836-2977` |
| `M3` | **HELD** | `reports/epl_widening_prereg_v2.md:430-446` | `epl/evwiden.py:250-264,4020-4050` |
| `M4` | **HELD** | `reports/epl_widening_prereg_v2.md:522-533,2275-2280` | `epl/evwiden.py:3287-3332,3382-3547` |
| `M5` | **REGRESSED** | v2 correctly says the fast-path test is not forecast evidence at `reports/epl_widening_prereg_v2.md:644-656` | `Engine` again claims it proves forecast-level inertness at `epl/evwiden.py:1783-1796`, especially `:1789-1790`. |
| `N-B3-TIE` | **HELD** | `reports/epl_widening_prereg_v2.md:1093-1143` | `epl/evwiden.py:4591-4674` |
| `N-B3-COV` | **HELD** | `reports/epl_widening_prereg_v2.md:1161-1202` | `epl/evwiden.py:5704-5823` |
| `N-B4-TAUTOLOGY` | **HELD** | `reports/epl_widening_prereg_v2.md:738-804` | `epl/evwiden.py:4681-4711,5016-5055` |
| `N-B4-BUDGET` | **HELD** | `reports/epl_widening_prereg_v2.md:568-589` | `epl/evwiden.py:8276-8293` |
| `N-RX-REFUSAL` | **HELD** | `reports/epl_widening_prereg_v2.md:1306-1327,1531-1566` | `epl/evwiden.py:653-667,6238-6316` |
| `N-SUP-PREFREEZE` | **HELD** | `reports/epl_widening_prereg_v2.md:1736-1809` | `epl/evwiden.py:95-102,468-490,4407-4477` |
| `N-DIGEST-STATE` | **HELD** | `reports/epl_widening_prereg_v2.md:763-793` | `epl/evwiden.py:4714-4792` |
| `N-I5-ANCESTRY` | **HELD** | `reports/epl_widening_prereg_v2.md:1659-1689` | `epl/tests/test_evwiden.py:198-257` |
| `N-I6-LIST` | **HELD** | `reports/epl_widening_prereg_v2.md:2184-2206` | `epl/evwiden.py:6383-6400` |
| `SH-B5-INTRO` | **HELD** | `reports/epl_widening_prereg_v2.md:1736-1809` | `epl/evwiden.py:95-102,468-490,4407-4477` |
| `SH-B4-BUDGET` | **HELD** | `reports/epl_widening_prereg_v2.md:568-589` | `epl/evwiden.py:8276-8293` |
| `SH-H-FIRST-ACT` | **HELD**, narrowly | `reports/epl_widening_prereg_v2.md:1871-1940` | Results canary remains the stated first act and first launcher command at `epl/evwiden.py:405-413,8170-8177`; subsequent sequence enforcement is separately unsound. |
| `SH-B4-H-DIGEST` | **HELD** | `reports/epl_widening_prereg_v2.md:738-804` | `epl/evwiden.py:4681-4711,5016-5055` |

Result: **22 HELD, 2 REGRESSED**.

## Silent drops

I found no unstated loss of a v1 effective-law obligation. The apparent removals are explicitly replaced:

- invalid P5 proxy → `K=200` unanimity: `reports/epl_widening_prereg_v2.md:1266-1301`;
- ambiguous P6 → structural `TableMCImprecise` refusal outside the seven published conditions: `:1306-1327`;
- indirect provisional-set inclusion → separate provenance field: `:780-793`;
- corrected three-generator inventory: `:1669-1684`;
- old lifecycle → five-step marked sequence: `:1871-1940`;
- incomplete manifest categories → 52 exact paths: `:2184-2206`;
- `repairs_section` → v2-bound `prereg_blob`: `:2114`;
- false power comparison → SE-of-difference analysis: `:1463-1502`;
- v1 pre-freeze events are not inherited as v2 passes; the v2 list is expressly prospective: `:1752-1784`.

This is continuity of stated law, not a finding that every replacement works.

## Internal consistency, section references, and retired identifiers

I found no outcome-changing contradiction between two operative v2 clauses. The two fits are disclosed at `reports/epl_widening_prereg_v2.md:1697-1734`; the prospective v2 clock is scoped at `:1752-1758`; and the attestation is expressly non-mechanical at `:2085-2101`.

Two textual qualifications remain:

- “There is nothing to supersede” at `:18-20` is only coherent as “nothing inside v2 to supersede,” because metadata at `:4-6` says v2 supersedes v1.
- `reports/epl_widening_prereg_v2.md:2324-2325` says the harness does not exist, although it exists in the same commit.

Citation hygiene is not clean:

- retired `R-B6` remains operative shorthand at `reports/epl_widening_prereg_v2.md:582,1731,1942,2017`;
- typed refusals are cited as §5.1 instead of §7.1 at `epl/evwiden.py:531,778,865,1061,1707,4184`;
- provenance/resume rules are cited as §5.2 instead of §7.2 at `:638,996,1444,1535,1622,1646-1654`;
- the canary heading says §5.3 instead of §7.3 at `:2634`;
- freeze law is repeatedly called §6 rather than §8.3 at `:84-93,392,539-540,2324-2327,4203,7130,8071`;
- evidence law is called §6 rather than §9 at `:6333,6422-6425`;
- `iv_c_verdict`/`unanimity` call the §5.3 interval §7.3 at `:5853-5855,5885-5887`;
- dropped-cell invalidation is attributed to §7 instead of §10 at `:5983-5986`;
- nonexistent §3.3(a)/(b)/(c)/(4) labels occur at `:4684-4685,4715,5018-5025,5089,5193,8293-8299`;
- `table_gate`’s docstring still describes the retired conservative P5 proxy at `:6192-6198`, while its implementation uses unanimity at `:6260-6282`;
- tests still speak of internal supersession at `epl/tests/test_evwiden.py:1904-1909,2541-2544`;
- the retired-ID test scans code/tests, not v2 itself: `:4643-4680`.

These are mostly minor navigation defects, but they refute the claim that every harness citation now points cleanly to operative v2 law.

# FINDING-BY-FINDING

## B3 — STILL-OPEN

The text correctly freezes constants, replaces P5, and requires tally rebinding (`reports/epl_widening_prereg_v2.md:547-552,1243-1301,2063-2083`). Implementation closure fails: deciding runners accept arbitrary `n_sims`, seeds, and chunk sizes (`epl/evwiden.py:4869-4897,5113-5152,5506-5550`), and tally hashes/invariant metadata can be null or absent (`:5478-5503,5586-5611`).

## B4 — STILL-OPEN

v2 explicitly forbids simulating treatment before all 35 new-control cells have reproduced protected parity (`reports/epl_widening_prereg_v2.md:816-842`). `TableRunner.__call__` simulates control and treatment together (`epl/evwiden.py:4952-4976`); only after both return does `run_table` compare the new control to protected parity (`:5570-5596`). `assert_parity_complete` establishes merely that 35 protected rows exist (`:5338-5387`).

## B5 — RESOLVED

The recorded B5 defect is repaired: required pre-freeze inspection routes use `read_only_store`, which raises rather than calling `build_store` (`reports/epl_widening_prereg_v2.md:1736-1813`; `epl/evwiden.py:4407-4477,7975-7984,8245-8264`). The two v1 fits are now disclosed inside the v2 attestation (`reports/epl_widening_prereg_v2.md:1697-1734,2085-2101`).

This ruling does not clear newly introduced public fit/simulation bypasses; those are separately blocking below.

## B6 — STILL-OPEN

The record is now repo-root scoped, but the one-way property is not enforced. Deletion is interpreted as no record, incomplete records pass conditional identity checks, and the record is ordinary unmanifested JSON (`reports/epl_widening_prereg_v2.md:2011-2039`; `epl/evwiden.py:2184-2196,2258-2288,7318-7361`). `merge(harness_frozen=True)` can also score without live committed-state verification (`:4170-4221`).

## I2 — RESOLVED

v2 requires the realised-SD joint-gate MDE at the same `R`, seeds, grid, and interpolation, separately labeled from the two-sided quantity (`reports/epl_widening_prereg_v2.md:1508-1525`). `realised_power` performs that rerun (`epl/evwiden.py:3922-3947`), and the evidence object publishes both quantities distinctly (`:6532-6575`).

## I6 — STILL-OPEN

The 52 paths, byte sizes, and retained `scored.per_cell` are repaired (`reports/epl_widening_prereg_v2.md:2184-2218`; `epl/evwiden.py:6372-6400,6828-6881,6942-6957`). Verification is incomplete:

- missing table verdicts are accepted (`:7045-7052`);
- SEs compare only when both exist (`:7053-7057`);
- only fired-condition names are compared (`:7058-7062`);
- unanimity dissent is reported but not bound (`:7063-7074`);
- the adoption decision is echoed, not recomputed (`:7107-7115`).

## N-B3-ZERO — RESOLVED

The exact prior defect is repaired on the genuine computation. v2 protects both the point boundary and iv-c CI endpoint (`reports/epl_widening_prereg_v2.md:1266-1301`); `unanimity` reuses the resampled-cell machinery and reevaluates the interval for all 200 joint resamples (`epl/evwiden.py:5826-5947`). A new caller-supplied-`mc` bypass is classified separately below.

## N-FREEZE-COMMIT — STILL-OPEN

The guard now reads committed bytes and ancestry and correctly refuses when absent pinned inputs make membership unestablishable (`reports/epl_widening_prereg_v2.md:1983-2009`; `epl/evwiden.py:7301-7308,7353-7361`). It still:

- sources hashes from `AMENDMENTS_PATH` as well as v2 (`:7243-7264`);
- validates schema by substring containment (`:7289-7291`);
- scrapes hashes from Markdown table rows and checks only `fresh - recorded`, not exact equality or labels (`:7188-7202,7292-7316`);
- does not validate first-fit commit/schema or require all identity fields (`:2262-2288`).

## N-RH-FIRST-ACT — STILL-OPEN

The five-step text is coherent (`reports/epl_widening_prereg_v2.md:1871-1940`), but the launcher emits step 2 only as a “BY HAND” comment and reruns step 1 on restart (`epl/evwiden.py:8170-8197`). Marker enforcement is CLI-shallow; direct `run_table`/`merge` bypass it (`:4170-4221,5506-5535`). `--limit 2` truncates step 3, alternate shards can select the wrong step-2 cell, and mere file existence establishes step 3 (`:8419,8542-8589`).

## N-LIFECYCLE-CHECKABILITY — RESOLVED

v2 now states the two prior fits, their alleged stopping point, and the limitations of mechanical proof (`reports/epl_widening_prereg_v2.md:1697-1734,2085-2101`). The remaining absence claims are honestly attestations because ignored data cannot prove them.

## NB1 — RESOLVED

Replacement discharges NB1 on the disclosed facts.

v2 is a new document/schema, expressly invalidates v1, discloses the two parity-path fits, and starts a prospective v2 clock (`reports/epl_widening_prereg_v2.md:4-27,1693-1734,2085-2101`). v1 closes itself as lineage deciding nothing (`reports/epl_widening_prereg.md:2703-2730`). The harness binds v2 and rejects an explicit v1 prereg record (`epl/evwiden.py:390,492-497,2262-2281`).

That fresh clock is a normative attestation, not a mechanically proven fact; v2 says so. No v1 freeze, first-fit, or sequence state is intentionally inherited. The only disclosed contamination is operational knowledge that the protected parity path crashed at its first cell. I found no disclosed estimand, delta, tally, or scientific outcome. Because `data/` is absent, I had to accept that absence on the document’s word. If any posterior result, delta, estimand, or outcome was inspected, NB1 would immediately reopen and end this experiment.

## NB2 — RESOLVED

Required pre-freeze membership, plan, and freeze-block paths use the read-only accessor (`reports/epl_widening_prereg_v2.md:1796-1809`; `epl/evwiden.py:4407-4477,7975-7984,8245-8264`). Real `build_store` calls are behind guarded construction or temporary canary roots (`:1806-1828,4883-4892,8341-8355`).

`BitemporalStore.__init__` itself calls `mkdir` (`src/wcmodel/data/store.py:20-23`), but the accessor checks the parquet first. That leaves a TOCTOU caveat, not the prior ordinary-path mutation defect.

## NB3 — RESOLVED

The exact prior defect is fixed. `assert_may_fit` accepts no freeze Boolean and calls `_frozen_now()` itself (`reports/epl_widening_prereg_v2.md:1987-2009`; `epl/evwiden.py:2116-2181`). The five named fit surfaces expose no freeze-state parameter.

Other exported functions that bypass `assert_may_fit`, and merge’s caller Boolean, are new channels rather than the old trusted argument.

## NB4 — STILL-OPEN

Same controlling evidence as B4: v2 `reports/epl_widening_prereg_v2.md:816-842`; implementation order `epl/evwiden.py:4952-4976,5338-5387,5570-5596`.

## NB5 — STILL-OPEN

The path is fixed, but deletion and forgery remain. V2 admits deletion and cross-checkout limitations while calling presence a ratchet (`reports/epl_widening_prereg_v2.md:2026-2039`). Code treats absence as no prior fit and conditionally accepts missing prereg/blob fields (`epl/evwiden.py:2184-2196,2258-2288,7318-7361`).

## NB6 — STILL-OPEN

No faithful executable state machine exists. Marker files can be written directly without proving the act (`epl/evwiden.py:3013-3063`); `{}` is accepted because `require_sequence` permits missing/null `freeze_commit` and validates no step/schema/hashes/product (`:3088-3127`). The launcher omits executable step 2 and direct functions bypass marker enforcement (`:8170-8197,4170-4221,5506-5535`).

## NB7 — STILL-OPEN

v2 requires a digest on every tally row, rebinding on every read, and §5.1 rechecks (`reports/epl_widening_prereg_v2.md:2063-2083`). `load_tallies` checks only truthy hashes and rechecks only metadata fields that happen to exist (`epl/evwiden.py:5478-5503`); `run_table` can write `tally_sha256=None` (`:5586-5611`); caller-supplied `mc` bypasses tally reading entirely (`:5950-5956,6067-6095`).

## NB8 — STILL-OPEN

The conformance gate still grades names, source text, or weaker helpers:

- L4 fabricates Boolean verdicts instead of running unanimity (`epl/evwiden.py:7587-7607`);
- L5 greens while B4’s production ordering is still wrong (`:7609-7631`);
- L7 calls only `assert_may_fit`, not every surface (`:7648-7670`);
- L9 checks comments and marker removal, not the executable sequence (`:7695-7722`);
- L11 checks only a signature (`:7752-7758`);
- L12 searches source substrings (`:7760-7770`);
- L18 claims to vary `n_sims` but contains no such case (`:7879-7897`).

## NI1 — RESOLVED

The corrected table and conclusion are operative at `reports/epl_widening_prereg_v2.md:1463-1502`; the six frozen rows are at `epl/evwiden.py:3593-3605`.

My independent calculation, in table order, gives:

- bar-difference z-scores: `0.635, 1.091, 1.902, 1.282, 1.119, 0.455`;
- 2×-difference z-scores: `0.209, 0.847, 0.338, 0.498, 0.454, 0.116`;
- relative MDE differences: `0.4167%, 1.1590%, 0.0803%, 0.4808%, 1.1848%, 1.0625%`.

Thus four of six bar differences exceed one SE, none exceeds 1.96 SE, every 2× difference is below one SE, and the extrema correctly round to **0.08%–1.18%**.

## NI2 — RESOLVED

`effective_posterior_hash` is excluded from the substantive payload and retained separately (`reports/epl_widening_prereg_v2.md:763-793`; `epl/evwiden.py:4743-4792,4830-4844,6497-6504`).

## NI3 — RESOLVED

The corrected arithmetic is:

`4 + 1 + 78 + 35 + 35 = 153 fits`

and

`35 + 70 = 105 simulations`.

The document and `_plan` agree (`reports/epl_widening_prereg_v2.md:568-589`; `epl/evwiden.py:8276-8300`).

## NI4 — RESOLVED

Treating incomplete `--verify` as the separately surviving I6 finding, the named schema problems are repaired:

- exact 52 paths: `reports/epl_widening_prereg_v2.md:2184-2206`; `epl/evwiden.py:6372-6400`;
- byte-size validation: `epl/evwiden.py:6828-6881`;
- `SHARDS=4`: `:449-457,8441-8452`;
- seven conditions and no P6: `:6293-6317`;
- retained `scored.per_cell`: `:6942-6957`.

## NI5 — RESOLVED

The false-complete v1 supersession index is gone; v2 directly states operative law (`reports/epl_widening_prereg_v2.md:14-27`). The surviving retired citations are hygiene defects, not another false completeness index.

## NI6 — RESOLVED

The invariant is dimensionally correct at `reports/epl_widening_prereg_v2.md:1127-1143`; code divides by `n_sims` and checks row and column identities (`epl/evwiden.py:4637-4674`).

## NM1 — RESOLVED

v2 directly states three generators and rejects “both generators” (`reports/epl_widening_prereg_v2.md:1669-1676`); the ancestry inventory is bound by `epl/tests/test_evwiden.py:198-257`.

## Retired `mc_se_mean` hygiene — RESOLVED

v2 freezes the four named SEs and seven conditions (`reports/epl_widening_prereg_v2.md:1315-1327,2121-2126`); code emits them at `epl/evwiden.py:6293-6316`.

## `TableMCImprecise` scope hygiene — RESOLVED

It is now a structural refusal; ordinary precision failure publishes UNRESOLVED (`reports/epl_widening_prereg_v2.md:1306-1327`; `epl/evwiden.py:653-667,6238-6316`).

## Generator-count hygiene — RESOLVED

Same evidence as NM1: `reports/epl_widening_prereg_v2.md:1669-1676`; `epl/tests/test_evwiden.py:198-257`.

## Indirect provisional-digest hygiene — RESOLVED

Same evidence as NI2: `reports/epl_widening_prereg_v2.md:763-793`; `epl/evwiden.py:4743-4792,4830-4844`.

# AUDIT FINDINGS

## A1 — STILL-OPEN

The prescribed signature pin landed (`reports/epl_widening_prereg_v2.md:795-804`; `epl/evwiden.py:4681-4711`).

The prescribed `TableRunner`-level metamorphic test did not. The test calls `arm_record` directly (`epl/tests/test_evwiden.py:2635-2702`); L11 checks only the signature (`epl/evwiden.py:7752-7758`). A provisional-dependent channel introduced after `arm_record` returns remains invisible.

## A2 — STILL-OPEN

Real `Engine.fit` tests exercise exact identity comparison, the `UntreatedMoved` loop, and pass-2/pass-3 agreement (`reports/epl_widening_prereg_v2.md:666-676`; `epl/evwiden.py:1919-2013`; `epl/tests/test_evwiden.py:1216-1302`).

The production identity-canary branch is not directly asserted; explicit identity-canary tests still use `_stub_fitter` (`epl/tests/test_evwiden.py:1573-1592`). Replacing the production branch with a constant PASS can leave the suite green.

## A3 — RESOLVED

Both structural-zero classes are frozen (`reports/epl_widening_prereg_v2.md:554-566`), checked, and reached through `estimand` (`epl/evwiden.py:3287-3332,3427`). Tests exercise both classes (`epl/tests/test_evwiden.py:1785-1817`).

## A4 — RESOLVED

v2 freezes seven entries and no P6 (`reports/epl_widening_prereg_v2.md:1315-1322,2121-2126`). Code and tests bind the exact set (`epl/evwiden.py:6240-6316`; `epl/tests/test_evwiden.py:3531-3539`).

## A5 — RESOLVED

`EXPECTED_TREATED_BY_LABEL` is operative law (`reports/epl_widening_prereg_v2.md:719-736`) and is checked by `assert_table_census` through `table_cells` (`epl/evwiden.py:315,4500-4546`). The test perturbs labels while preserving totals (`epl/tests/test_evwiden.py:4574-4608`).

## A6 — RESOLVED

v2 is direct operative law rather than layered repair prose (`reports/epl_widening_prereg_v2.md:14-27`). The generator count and `TableMCImprecise` scope are stated at source (`:1306-1327,1669-1676`).

## A7 — RESOLVED

Both controls are measured (`reports/epl_widening_prereg_v2.md:2148-2155`). `measured_controls` derives counts from rows, `merge` installs them, and evidence publishes them (`epl/evwiden.py:3335-3379,4324-4328,6669-6681`). Tests cover clean, dirty, and published cases (`epl/tests/test_evwiden.py:1820-1855`).

# NEW DEFECTS

## Behavioural rows L1–L18

| Row | Assessment |
|---|---|
| `L1` | **Not behavioural.** Its corpus row is deliberately identical to the incumbent probabilities, and the Boolean expression can green from final equality alone. Rewiring the delta to the corpus can survive (`epl/evwiden.py:7473-7507`; v2 `:1957`). |
| `L2` | **Partial.** It tests `table_gate` on a hand-built object, bypassing `score_table`; a pooled-mean regression in the scorer can survive (`:7512-7534`; v2 `:1958`). |
| `L3` | **Partial.** It exercises only two cells, not the joint 32-tally object (`:7536-7585`; v2 `:1959`). |
| `L4` | **Not behavioural.** It fabricates verdict Booleans and an `mc` object; it never constructs tallies or calls `unanimity` (`:7587-7607`; v2 `:1960`). |
| `L5` | **False.** It checks existence/completeness of protected rows while the production treatment-before-parity defect remains (`:7609-7631`; v2 `:1961`). |
| `L6` | **Partial.** It calls the accessor and performs shallow AST inspection; it does not execute all named commands and compare store bytes/mtime (`:7633-7646`; v2 `:1962`). |
| `L7` | **Not the stated scenario.** It checks signatures and calls only `assert_may_fit`, not every public fit/simulation path (`:7648-7670`; v2 `:1963`). |
| `L8` | **Behavioural.** It plants a wrong-prereg record and requires refusal (`:7672-7693`; v2 `:1964`). |
| `L9` | **Partial.** It removes a marker and inspects launcher comments; it does not exercise the five-step lifecycle (`:7695-7722`; v2 `:1965`). |
| `L10` | **Partial.** Its missing-digest case is masked by an already inconsistent matrix; `verify` coverage is source inspection (`:7724-7750`; v2 `:1966`). |
| `L11` | **Not the prescribed test.** It checks only `sampler_digest`’s signature and silently downgrades TableRunner-level to arm-record-level (`:7752-7758`; v2 `:1967`). |
| `L12` | **Source-name check.** Dead or unreachable copies of four strings can keep it green (`:7760-7770`; v2 `:1968`). |
| `L13` | **Behavioural.** Both structural-zero classes execute (`:7772-7790`; v2 `:1969`). |
| `L14` | **Partial but current code works.** The helper is perturbed behaviorally; production wiring is checked only by source substring (`:7792-7810`; v2 `:1970`). |
| `L15` | **Substantively behavioural.** It checks missing paths, wrong sizes, retained `per_cell`, and wrong shard count (`:7812-7844`; v2 `:1971`). |
| `L16` | **Partial.** `power_reproduces(None)` runs the simulation, but its 101-point anti-stub check is vacuously `all([])` when `supplied={}` and it never compares the ratio column (`:3983-4007,7846-7858`; v2 `:1972`). |
| `L17` | **Partial.** It exercises `measured_controls` but not merge/evidence publication (`:7860-7877`; v2 `:1973`). |
| `L18` | **False.** It says it tries different `n_sims`, but contains no `n_sims` case (`:7879-7897`; v2 `:1974`). |

The report-reader test believes `row["ok"]`; its companion checks that selected functions are callable rather than rerunning the indexed scenarios (`epl/tests/test_evwiden.py:5242-5271`). Normal pytest discovery provides some independent coverage, but `freeze_block` consumes no durable pytest result. NB8 therefore remains open.

## NEW-B1 — BLOCKING: deciding constants are publicly overridable

v2 freezes `B`, `n_sims`, `MC_BOOT`, `SHARDS`, `K`, alpha, and seeds, and says alternatives invalidate the experiment (`reports/epl_widening_prereg_v2.md:547-552,684-697,2249-2250`).

Nevertheless:

- `TableRunner` and `ParityRunner` accept arbitrary `n_sims`, seeds, and chunk sizes and use them (`epl/evwiden.py:4869-4897,4952-4957,5113-5152`);
- `run_table` forwards arbitrary values (`:5506-5550`);
- `Engine.fit`/`run_fits` accept alternate grid inputs (`:1862-1863,2494-2500`);
- generic `--limit` can truncate the real step-3 population (`:8419,8542-8555`);
- L18 does not test `n_sims`.

Matching custom parity/treatment runs can therefore agree under the wrong frozen law.

## NEW-B2 — BLOCKING: test seams and near-real inputs can populate production ledgers

The text says every real fit/simulation must establish committed freeze state (`reports/epl_widening_prereg_v2.md:1659-1667,1983-2009`), but:

- exported `run_canary` invokes the four-fit protected canary without `assert_may_fit` (`epl/evwiden.py:2981-3001`; `epl/walkforward.py:450-496`);
- `simulate_arm` calls `leaguesim.simulate` directly (`epl/evwiden.py:4561-4587`);
- injected `run_fits(fitter=..., engine=...)` skips production Engine and writes stub provenance (`:2494-2541,2571-2613`);
- `run_parity_oracle` accepts an arbitrary runner (`:5185-5230`);
- `run_table` accepts arbitrary runner/parity implementations and can stamp their output frozen (`:5506-5605`);
- a real-derived archive differing by one value is neither byte-identical pinned input nor v2-literal synthetic input, yet `is_pinned_archive` can classify it as non-pinned and allow it before freeze (`:2068-2172`).

These are not mechanically confined to temporary roots.

## NEW-B3 — BLOCKING: truncated or fabricated unanimity evidence can PASS

The normal unanimity implementation is sound: one joint particle resample is used across all 32 tallies per `k`, the §5.3 interval machinery is reused, and both P4 and P5 boundaries are evaluated (`epl/evwiden.py:5704-5823,5826-5947`). Missing genuine unanimity fires P5.

But `score_table(..., mc=...)` skips tally loading, paired bootstrap, and unanimity (`:5950-5956,6067-6095`). `table_gate` trusts any truthy `mc.unanimity` with `fired=False` and validates neither `K=200`, seed, 200 verdicts, nor dissent consistency (`:6266-6282`). A fabricated `k=1` object can resolve PASS contrary to `reports/epl_widening_prereg_v2.md:1266-1301`.

## NEW-B4 — BLOCKING: freeze and decision gates retain caller-attested bypasses

`freeze_block(check_implementation=False)` renders despite a red conformance report (`epl/evwiden.py:7941-7976`), contradicting the unconditional precondition at `reports/epl_widening_prereg_v2.md:1846-1850`. The later freeze guard does not validate report greenness (`epl/evwiden.py:7205-7369`).

Separately, `merge(harness_frozen=True, require_canaries=False)` trusts caller lifecycle assertions and scores (`:4170-4221`). A bypass-rendered block can therefore become committed evidence for its own freeze state.

## NEW-B5 — BLOCKING: one mandatory pre-freeze pass is not executable

v2 requires a partial Engine pass through construction and PIT checks without fitting (`reports/epl_widening_prereg_v2.md:1768-1772`; enumeration at `epl/evwiden.py:480-484`).

`Engine.__init__` calls `assert_may_fit` before store/anchor construction and refuses pinned data before freeze (`epl/evwiden.py:1799-1828`). No command or test implements the promised stopping point. `freeze_block` merely prints the predeclared enumeration (`:8036-8041`). The required precondition cannot presently be truthfully established.

## NEW-B6 — BLOCKING: the protected parity path is already known to fail and is unchanged

v2 states that two executions of the protected parity path both crashed on `ExcludedMassTooLarge` at the first cell (`reports/epl_widening_prereg_v2.md:1697-1706,2091-2097`). `ParityRunner` still invokes the same protected `ArchiveRunner` over that cell with no remedy or catch (`epl/evwiden.py:5092-5182`; `epl/simretro.py:520-559`), and the same refusal remains at `epl/particles.py:643-667`.

`git diff-tree` shows neither protected module changed in `f454041..1afd54d`. This is a static inference rather than a new execution, but two identical prior failures plus an unchanged protected path mean mandatory step 5 is presently expected not to complete. Feasibility must be demonstrated without fitting the estimand before freeze.

## NEW-B7 — BLOCKING: publication invalidates its own MANIFEST

The post-step-5 launcher command is `--merge --evidence` (`epl/evwiden.py:8217-8226`). Main then writes evidence and MANIFEST and afterward rewrites `step4_merge.json` (`:8650-8665`).

That marker is one of the 52 manifest members (`:6372-6400`). A successful publication therefore immediately changes a manifested file after hashing it and places a step-4 marker write after step 5. The claimed “publication-only, not a sixth experiment step” exception does not make the resulting manifest valid (`reports/epl_widening_prereg_v2.md:1936-1940,2184-2218`).

## NEW-B8 — BLOCKING: a failed step-1 canary is unpublished and retryable

v2 requires the first post-freeze act to publish its result, including failure (`reports/epl_widening_prereg_v2.md:1883-1890`).

`run_canary` raises immediately on failure (`epl/evwiden.py:2981-3001`); `_run_all_canaries` does not catch it (`:8364-8372`); main writes the canary artifact only after successful return (`:8515-8534`). A failed first real-fit canary therefore leaves no durable result or marker and can be retried, creating an outcome-dependent retry/file-drawer channel.

## Prior blocking mechanisms confirmed, not counted again as new

- All-35 parity still occurs after treatment: B4/NB4.
- Markers accept `{}`, can be forged, and direct functions bypass them: N-RH-FIRST-ACT/NB6.
- Tally hashes and metadata can be null/optional: B3/NB7.
- `--verify` does not rederive adoption: I6.
- First-fit deletion/forgery remains possible: B6/NB5.
- The conformance report can green while obligations fail: NB8.

## Additional IMPORTANT defects

- **Effective-posterior parity fails open:** comparison occurs only when both hashes are non-null (`epl/evwiden.py:5265-5267`), contrary to binding provenance at `reports/epl_widening_prereg_v2.md:763-793`.
- **False first-fit timestamp:** the record is written during permission checking, before an actual fit begins (`epl/evwiden.py:2142-2181`), while v2 describes the instant of the first real fit/completion (`reports/epl_widening_prereg_v2.md:2019-2024`).
- **Allowed post-fit prose amendment is incompatible with the guard:** v2 permits prose-only notes (`reports/epl_widening_prereg_v2.md:2055-2058`), but record validation binds the entire prereg blob (`epl/evwiden.py:2272-2281`).
- **Unenumerated pre-freeze write:** `--script` writes a launcher under `data/` without freeze (`epl/evwiden.py:8231-8237,8466-8475`), contradicting the complete no-repository-write enumeration at `reports/epl_widening_prereg_v2.md:1754-1758,1778-1784`.
- **L16 omits a frozen power field:** `PUBLISHED_POWER` contains `ratio`, but `power_reproduces` never compares it (`reports/epl_widening_prereg_v2.md:1422-1436,1972`; `epl/evwiden.py:3593-3605,3983-4007,7846-7858`).

## Additional MINOR defects

- `power_reproduces` still advertises the retired v1 dated-note remedy (`epl/evwiden.py:3966-3975,4006-4013`) although v2 requires refusal (`reports/epl_widening_prereg_v2.md:1433-1436,1846-1850`).
- The citation and stale-prose defects listed under continuity remain.
- `read_only_store` has a small constructor TOCTOU caveat because `BitemporalStore.__init__` creates its directory (`src/wcmodel/data/store.py:20-23`).

## Checks that did pass

- The genuine `K=200` resampling is joint across all 32 tallies and reuses the interval machinery (`epl/evwiden.py:5704-5947`).
- Ordinary read-only membership/plan/freeze-block routes do not call `build_store` (`:4407-4477,7975-7984,8245-8264`).
- Missing pinned artifacts make the freeze guard refuse rather than pass (`:7301-7308,7353-7361`).
- The 52-path inventory and byte-size validation are implemented (`:6372-6400,6828-6881`).
- `SHARDS=4`, seven precision conditions, measured controls, `prereg`, sequence object, and retained `scored.per_cell` are emitted (`:449-457,6293-6317,6669-6681,6942-6957,8441-8452`).
- The §6.4 arithmetic and the realised-SD joint-gate rerun are correct (`reports/epl_widening_prereg_v2.md:1463-1525`; `epl/evwiden.py:3922-3947,6532-6575`).
- The stated budget is arithmetically correct and `_plan` agrees (`reports/epl_widening_prereg_v2.md:568-589`; `epl/evwiden.py:8276-8300`).

# VERDICT

DO-NOT-FREEZE — **15 prior findings** in Parts 1–3 are STILL-OPEN or REGRESSED, and **8 new blocking defects** were found in Part 4.

The 15 are:

`M1`, `M5`, `B3`, `B4`, `B6`, `I6`, `N-FREEZE-COMMIT`, `N-RH-FIRST-ACT`, `NB4`, `NB5`, `NB6`, `NB7`, `NB8`, `A1`, and `A2`.

Before freeze is legitimate, the shortest necessary list is:

1. Close every production fit, simulation, merge, freeze-block, injected-runner, and supplied-`mc` bypass; mechanically enforce all frozen constants.
2. Establish all-35 new-control parity before any treated simulation, and show that the unchanged protected path can actually complete.
3. Make first-fit, tally, freeze, and sequence evidence fail-closed, commit-bound, non-null, non-forgeable within the stated threat model, and fully reverified.
4. Provide a genuinely executable, once-only five-step launcher—including the exact isolated step 2, durable failed-canary publication, valid predecessor enforcement, and publication that leaves MANIFEST valid.
5. Replace the conformance rows with independent behavioural scenarios that fail under their named defect classes, then make `freeze_block` unable to bypass that result.

Do not render or paste the freeze block, and do not begin the first real fit.

