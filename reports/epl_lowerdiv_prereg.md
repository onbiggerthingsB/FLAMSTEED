# Lower-division evidence — preregistration of the second-tier archive experiment

**Version:** **v2**, 2026-08-30 · **Written:** 2026-08-30 · **Branch:** `main`
· **Schema:** `epl-lowerdiv-2`

**What v2 is.** v1 of this document was committed at `35e562f`, before any
harness existed, and went straight to cross-model design review. That review
ruled it **UNSOUND** on fifteen blocking, fourteen important and two minor
findings, and the owner then re-founded the gate family on this document's own
power analysis (§4.0). v2 lands both — the refounding and every review finding —
**as final law**, by direct edit. There are no repair sections, no supersession
index and no amendment machinery inside this document: v1's text is not
preserved anywhere in it, because a preregistration that carries its own
corrections as annotations is a document a reader has to reconstruct before they
can check it. Where a finding was **refuted** from the repository, the refutation
is recorded in the clause it concerns rather than deleted (§13 indexes them).
Every clause below is operative and every number in it was recomputed for v2.
**Template and precedent:** [`reports/epl_widening_prereg_v3.md`](epl_widening_prereg_v3.md)
— its §5 statistics, §8 lifecycle, §9 evidence contract and §10 invalidations are
the shape this document takes, and every ruling those four sections reached is
carried here as ordinary text rather than cited.
**Queued by:** [`reports/epl_widening_result.md`](epl_widening_result.md), which
closed the widening experiment UNRESOLVED and named its successor in the law:
*"the natural successor is the lower-division-evidence experiment already
queued, which attacks the same thin-evidence weakness with more data rather than
more blur, and would be expected to subsume this rule's effect if real."* Under
widening v3 §10, re-testing that rule is a NEW preregistration. This is it.
**Owner-pinned standing queue:** this is the "Hull widening" successor and sits
behind the anchoring verdict, the anchored arm, automation + the live-cycle
cadence switch, A11+FPL capture and the injury shadow arm. §8.1 positions it
explicitly rather than jumping it.

**What this document is.** One coherent statement of the complete law of this
experiment: the architecture, the one frozen calibration constant, the pinned
population, the estimand, the resampling, the secondaries, the four-part
adoption rule and its one reported diagnostic, the Monte-Carlo estimator and its
precision regime, the refusal semantics, the lifecycle, the evidence contract and
the scope. Every clause below is operative. **Where this document is silent,
nothing is implied.**

**Status.** No harness exists. `epl/lowerdiv.py` and `epl/tests/test_lowerdiv.py`
are not written; no `data/epl/matches_e1.parquet` exists; no E1 CSV has been
fetched; no fit, no simulation, no delta, no evidence file and no verdict of this
document exists. v1 of this document was step one of the house lifecycle —
preregistration BEFORE harness code, then cross-model design review, then harness
TDD, then dual audit, then freeze, then run, then publish either way. v2 is step
two's output landed as law: **the design review has happened, and this is the
document it produced.** §8 says exactly what each remaining step must contain and
in what order, and §8.3 forbids a freeze block until every one of them has.

Every number in §0–§3 and §6 was computed from committed or pinned artifacts by
the recipes given beside it, by read-only passes that fit nothing, simulate no
season and download nothing. Where a number is an extrapolation rather than a
measurement, it says so.

---

## 0. What is pinned

### 0.1 The corpus, the TWO archives, the two store roots, and the configuration

| | |
|---|---|
| Corpus | `data/epl/fit/walkforward_predictions.parquet` |
| SHA-256 | `f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a` |
| Rows | **2,280** — 6 seasons × 380; seasons 2019/20 … 2024/25; blocks `(season, ISO week)` **212** |
| Outcome counts (`y` = 0/1/2) | 993 / 525 / 762 — adopted from `epl/recalfit.py:91-98` (A8), as every predecessor adopts them |
| Walk-forward ledger | `data/epl/fit/walkforward_ledger.jsonl`, SHA-256 `869a558ce7f84ef0f4a4ebdd8f781a4a72213fd5946b4e7088d716d99e82ba9e` — 212 rows, one per block opening, each carrying `provisional_teams` and `cold_start_teams` as the published fits computed them |
| **E0 archive — READ-ONLY, BYTE-IDENTICAL** | `data/epl/matches.parquet`, SHA-256 `323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf` — **4,560** matches, 12 seasons 2014/15 … 2025/26, 380 per season, 35 clubs observed of 36 registered |
| **E1 archive — NEW, digest pinned in the freeze block** | `data/epl/matches_e1.parquet` — 12 seasons 2014/15 … 2025/26, expected 552 per season / 24 clubs per season (§0.6 measures it; the freeze block pins its digest, row count and club census) |
| Frozen config file | `epl/config_frozen.json`, SHA-256 `9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc` |
| **Realised config** | `realised_config_sha256` = SHA-256 of `json.dumps(freeze.frozen_wcmodel_config(), sort_keys=True, default=str)` = **`78a51cd92c48838a57e3d6832b7661aad7a5b231425572214a067c2a35edbdcd`** |
| Widening per-fixture evidence (the pinned population's source of truth) | `reports/evidence/widening_per_fixture.csv` — **committed**, 85 rows, the exact fixture `match_id`s, blocks and seasons this document's population is pinned to (§0.5) |
| Collateral structure (the 2,280/212/6 skeleton, committed) | `reports/evidence/anchoring_per_fixture.csv` — **committed**, 11,400 rows = 2,280 fixtures × 5 anchoring weights; **deduplicated to one row per `match_id`, keeping the first row in ascending-`match_id` order**, it yields exactly 2,280 fixtures, 212 `(season, ISO week)` blocks and 6 seasons. §6.2's collateral construction is built from **this committed file**, not from the gitignored corpus parquet, so the power table is reproducible from Git alone |
| Table-retro anchor | `data/epl/sim/retro_r1.jsonl` (**protected, read-only**) and `epl.simretro`'s public constants: `SEASONS` (7, 2019/20 … 2025/26), `COMPARISON_CUTOFFS` (MW0/MW3/MW6/MW10/MW19), `DEFAULT_N_SIMS` **20,000**, `SEED` **20260611** |
| Feasibility census | `reports/evidence/widening_parity_feasibility.json` (committed, byte-identical to the gitignored `data/epl/sim/evwiden_parity_feasibility.json`), SHA-256 **`07ee00d798cb0f01f29bc5bb5ba885c41e26d5494e9755c73a038a2777bad329`**, 18,128 bytes. **This document's table leg is scoped by it exactly as widening v3's was** — 32 priceable cells, 3 unpriceable — so it is a pin, not a citation |

Verify with:

```
shasum -a 256 data/epl/fit/walkforward_predictions.parquet \
              data/epl/fit/walkforward_ledger.jsonl \
              data/epl/matches.parquet epl/config_frozen.json \
              reports/evidence/widening_parity_feasibility.json \
              reports/evidence/widening_per_fixture.csv \
              reports/evidence/anchoring_per_fixture.csv
```

**Five of those inputs are gitignored, and that is a weakness this document
closes rather than discloses.** The corpus parquet, the ledger, the E0 archive,
`single_fit.json` and the future E1 archive live outside Git, so a clean clone
cannot regenerate the numbers this document's verdict rests on. §9.5 therefore
makes a **committed reproduction bundle** — the full 2,280-row scoring corpus,
the 212-row opening ledger, and canonical attestations for both archives and both
store roots — a freeze precondition and a manifest member. Until that bundle
exists, the gitignored digests above are accepted on this document's word, and
§8.3 refuses to render a freeze block on that basis.

**`ConfigNotFrozen` fires on four conditions**, unchanged from the predecessor:
the frozen file's digest, the realised seed (20260611), the realised widening
block (`{mechanism: c, strength: 0.5}`), and `realised_config_sha256`. Every
ledger row carries `config_sha256` and `realised_config_sha256`, so a reader can
tell which moved.

#### THE ARCHITECTURAL PIN — two archives, two store roots, one Elo anchor

> **E1 rows never enter `data/epl/matches.parquet`, never enter the store root
> `data/epl/fit/store/`, and never reach `epl.elo`.**

The layout is frozen here, once, and §8.9 makes it the only layout any writer or
reader of this experiment may name:

| what | path | who writes it |
|---|---|---|
| E0 archive | `data/epl/matches.parquet` | **nobody** — read-only to this document |
| E0 store root | `data/epl/fit/store/` | **nobody** — read-only to this document |
| E1 raw CSVs | `data/epl/raw/E1_{season_code}.csv` | the §8.2 acquisition pass |
| E1 provenance sidecar | `data/epl/raw/provenance_e1.json`, keyed `E1_{season_code}` | the acquisition pass |
| E1 archive | `data/epl/matches_e1.parquet` | the acquisition pass |
| E1 name-mapping report | `data/epl/team_name_mapping_e1.json` | the acquisition pass |
| E1 manifest | `data/epl/manifest_e1.json` | the acquisition pass |
| E1-informed store root (E0 ∪ E1) | `data/epl/fit/store_e1/` | the run |
| **Arm-B (E0-only) feature cache** | `data/epl/fit/lowerdiv/cache_b/` | the run |
| **Arm-A (E1-informed) feature cache** | `data/epl/fit/lowerdiv/cache_a/` | the run |
| match-leg run directory | `data/epl/fit/lowerdiv/` | the run |
| table-leg run directory | `data/epl/sim/lowerdiv/` | the run |

**Both feature caches are experiment-private, and neither is the incumbent's.**
`src/wcmodel/data/features.py:439-450`'s `build_cached` writes a `.tmp` parquet
and renames it on a miss, and its cache key hashes the current Git HEAD
(`:399-406`). Pointing Arm B at the shipped E0 cache would let this experiment
write into a directory the published arm reads, and would make a HEAD advance
during the run change the key of a cache the published arm shares. Two private
roots, resolved from §8.9's `layout()` and from nowhere else, remove both. Two
consequences are pre-stated rather than discovered: **every key is a cold miss on
the first run** (§2.4's budget already assumes that), and **a HEAD advance during
the run produces further cold misses but can never produce a wrong hit**, because
HEAD is inside the key. Shards run sequentially (§2.4), so the `.tmp` rename race
that crashes parallel shards in the locked path cannot occur; a `.tmp` file
surviving a run is `PathNotFrozen`, and neither cache root is a manifest member.

**Why this decision and not the merged one.** `epl/elo.py:265` builds a season's
`clubs` from every row carrying that season label, and `_open_season`
(`epl/elo.py:339-384`) computes `division_mean` over `prev_clubs` and defines
`promoted = clubs - prev_clubs`. Put both divisions under one season label and
`clubs` becomes ~44, the division mean becomes a two-division mean, `promoted`
becomes "new to either division", and **every rating on the E0 scale shifts with
no exception raised** — the seasons-interleave guard (`epl/elo.py:236-240`)
passes because both divisions run August–May, and the club-twice-in-a-block
guard (`:288-293`) passes because no club plays in both divisions on one day.
The frozen `epl_anchor_spec` string would still read `promoted_offset=-75` while
meaning something else entirely. The merged architecture also breaks four
standing preregistrations' archive pin at once, invalidates the walk-forward
corpus, and destroys the identity control that is this design's only remaining
harness-bug detector (§1.4). **The separation is what makes §0.5's population pin
architectural rather than procedural**, and that is the reason it is stated here
as a pin and not as a practice.

`ArchiveDigestMismatch` fires if `data/epl/matches.parquet` is not
`323aa54af0…` or not 4,560 rows, at every entry point, before anything else runs.
`E1Leak` (§7.1) fires if an E1 `match_id` appears in the E0 archive, in the E0
store root, in any frame passed to `epl.elo`, or in any frame passed to
`effective_evidence` (§0.3).

### 0.2 The incumbent, read from the code — and the hole this experiment aims at

The published arm is `dc_native`: `epl.dcfit.fit_epl` (`epl/dcfit.py:216`), the
Dixon-Coles scoreline model of `src/wcmodel/model/scoreline.py` anchored on
`epl.anchor.Anchor` with `strength_prior.enabled = true`, `k_att = k_def = 0.6`,
trained on the E0 archive alone.

Two layers price a club arriving from the second tier, and they are not
symmetric:

* **The Elo layer prices it with a number chosen on data.**
  `epl/config_frozen.json`'s `chosen.promoted_offset = -75.0`, with
  `carryover = 1.0` and `debut_offset = 0.0`. `epl/elo.py:30-52` states the
  rationale in full — a club arriving from the second tier is not an average
  Premier League club, and a returning club's old top-flight rating is **not**
  restored. `epl/elo.py:147-152` refuses a positive offset by construction.
  `epl/fit.py:88-91` records that the promoted seed was worth **0.0030 RPS** on
  an already-observed scoring window, and `epl/config_frozen.json`'s
  `delta_vs_chosen` records **0.001309 RPS** as its contrast on the tuning window
  it was chosen on. §2.2 keeps the two apart; v1 cited the first as if it were
  the second.
* **The Dixon-Coles layer prices it with nothing.** A promoted club with no
  pre-cutoff E0 match is handled by Fix 3's prior draws
  (`epl/dcfit.py:151-168 _prior_draws`), and that module's own docstring says
  what they are: *"a prior draw is not a posterior… on these fixtures the DC
  forecast is a smeared version of the Elo forecast and should not be expected to
  beat it."* A promoted club with a decade-stale E0 spell — Hull — is worse off
  still: it has archive rows, so it is not cold-start, and its rows carry
  essentially no decayed weight.

**The candidate fix this document tests: give the likelihood the club's actual
recent football.** Hull played 46 Championship matches last season. The model
has never seen one of them.

### 0.3 Effective evidence — the quantity, carried across verbatim, and the archive it is computed on

For a club `t` and cutoff `C` (midnight):

```
e(t, C)  =  Σ  0.5 ** (age_days / 365)     over matches of t with date < C,
                                            age_days = (C − date) in whole days
```

This is the fit's own likelihood weight, not a new number:
`src/wcmodel/data/features.py:297` computes
`decay_weight = 0.5 ** (age_days / half_life)` with `half_life = 365`, and
`src/wcmodel/model/panel.py:34-36` renames it to the panel's `weight`. The
implementation is `epl.evwiden.effective_evidence` (`epl/evwiden.py:1237`) and
its `prior_rows` (`:1225`), transplanted **verbatim** into `epl/lowerdiv.py`
including the `EvidenceLeak` guard placed on the **ages that weight the sum**
rather than on the filter that produced them, so it can actually go red.

> **`e` IS COMPUTED ON THE E0 ARCHIVE AND ON NOTHING ELSE, ALWAYS, EVERYWHERE IN
> THIS DOCUMENT.** Passing the E1 frame, or any frame containing an E1 row, to
> `effective_evidence` is `E1Leak` and stops the run. §0.5 is why.

### 0.4 What the E0 archive holds for the clubs this experiment is about

Measured read-only from the pinned archive at the 2026/27 opener (cutoff
2026-08-21), carried from widening v3 §0.4 and re-derivable by the §0.3 recipe:

| club | E0 rows | first / last E0 season | `e` at the 2026/27 opener |
|---|---:|---|---:|
| **hull** | **76** | 2014/15 – 2016/17 | **0.0607** |
| **coventry** | **0** | — | **0.0000** (cold start) |
| ipswich | 38 | 2024/25 – 2024/25 | 12.5208 |

Hull carries six hundredths of one match of decayed evidence. Its published
issuance surface shows the symptom: `reports/epl_sim_issuance_2026-08-21.md` §4
records Hull's E[points] sd at **14.11** against 8.6–10.2 for every other club,
and its limitation 4 states *"Hull's dispersion is unexplained, not excused."*

### 0.5 THE POPULATION TRAP — measured, and the pin that closes it

**This is the single most important clause in the document.**

`e` is a sum over an archive. Enlarge the archive and `e` changes. Measure how
much, with the E0 decay half-life of 365 days over a 46-match Championship
season spread 4 August to 5 May, evenly (read-only, arithmetic over dates, no
fit):

| cutoff | `e` added by ONE prior Championship season |
|---|---:|
| **an August opener** | **+29.25** |
| the following December | +23.47 |
| the following May | +17.79 |
| a second season further back, at the opener | +14.63 |
| *(for scale: one 38-match E0 season on the same window, at the opener)* | *+24.17* |

The widening experiment's threshold is `e* = 10.0`. **One prior Championship
season is roughly three times it.** Under an E1-informed archive Hull goes from
`e = 0.0607` to ≈ 30; Coventry from 0 to ≈ 30; and every one of the nine treated
club-seasons of widening v3 §2.2 — aston_villa 2019/20 (4.74), norwich 2019/20
(3.15), sheffield_united 2023/24 (9.84), and the six cold-start tails — was
promoted from the Championship the season before and clears 10 by a wide margin.

> **A re-derived thin population would be empty or near-empty and the estimand
> would be undefined. The experiment would look like it had cured the disease by
> redefining the symptom.**

**THE PIN, AND THE COLUMN IT IS ON.** The population is **not derived by this
experiment**. It is the widening run's population, taken as data:

* the **85 thin fixtures** are exactly the 85 rows of the committed
  `reports/evidence/widening_per_fixture.csv`, **identified by their `match_id`
  column and by nothing else**;
* "thin" means `e_min < 10.0` computed on the **E0-only** archive at
  `323aa54af0…` — the same `e*`, the same recipe, the same archive, the same
  fixtures;
* the **62 week blocks** and the **6 seasons** are that file's own `block` and
  `season` columns; the season split is **26 / 11 / 12 / 12 / 12 / 12**
  (2019/20 … 2024/25) and the block-size distribution is 46 blocks of 1, 10 of 2,
  5 of 3, 1 of 4 — all re-derived from the committed CSV by the harness, never
  typed in;
* the freeze block pins the 85 `match_id`s, the 62 block labels and the 6-season
  split by canonical digest, **and additionally pins the 85 `match_id`s equal to
  widening v3's own frozen membership digest
  `38d18d4d96b4eed0391d167d1bf7be6b95de83db6f8fda2846ad97c3fb368d5a`** — computed
  through `epl.evwiden`'s own canonical serialiser, imported read-only, so the
  comparison is against that document's serialisation and not against a
  re-invented one. A reader can then check that this experiment's population is
  that experiment's population and not a look-alike. If the two digests cannot be
  made to agree, the discrepancy is published before the freeze and this
  document does not run.

> **WHY `match_id` AND NOT `key`, MEASURED.** The CSV's `key` column is the
> widening run's **opening** key — `cutoff|seed|config_sha256` — and it is
> **not unique per fixture**. Measured read-only on the committed file:
> **85 distinct `match_id` values, 62 distinct `key` values** — one `key` per
> week-block opening, so the `key` column counts *openings* and the `match_id`
> column counts *fixtures*, which are the two different numbers this section
> reports. The canonical digests, all three stated here so a reader can check the
> pin without recomputing it:
>
> | serialisation | SHA-256 |
> |---|---|
> | the **85 sorted `match_id`s** | `38d18d4d96b4eed0391d167d1bf7be6b95de83db6f8fda2846ad97c3fb368d5a` |
> | the 85 sorted `key`s (with repeats) | `5a0d92c50fa31e6b2793d2caeda43769be47e2e3564225e77d45292acf1146d3` |
> | the 62 sorted distinct `key`s | `2a40d7f235a864a002a526d8598c85c37991d841063a4bf50a3abec0544abe6c` |
>
> **The pinned digest `38d18d4d96…` is the `match_id` digest.** A harness that
> took the document's word and joined on `key` would either fail the freeze or —
> worse — join whole openings rather than fixtures and silently score a
> different population. The membership join on the corpus is therefore
> **one-to-one on `match_id`**, and a join producing anything but 85 rows is
> `MembershipMismatch`. `epl/tests/test_lowerdiv.py` must carry a regression test
> that computes both digests from the committed CSV and asserts that **only** the
> `match_id` digest equals `38d18d4d96…`, so the two can never be swapped back.

`PopulationRederived` (§7.1) fires if any code path computes `e` on a frame that
is not the pinned E0 archive, or derives the thin set from anything but the
committed CSV, or joins the thin set on any column but `match_id`. **The
enforcement is architectural first and procedural second:** E1 lives in a
separate parquet and a separate store root, and **no surface of this experiment
ever passes an E1-bearing frame to `effective_evidence`** (see the ruling
immediately below), so `effective_evidence(cutoff, e0_played)` is unchanged **by
construction** rather than by discipline.

**THE E1-INFORMED `e` IS NOT COMPUTED, AND THAT IS A DELIBERATE LOSS.** v1 made
"the E1-informed `e` for all 85 fixtures" the headline secondary. It cannot be:
computing it means passing a frame containing E1 rows to the effective-evidence
function, which is exactly the condition `E1Leak` and `PopulationRederived` are
written to refuse. The available scoping — a second evidence API, a second
schema, a rename, and dataflow tests keeping the two apart — would buy a number
that decides nothing at the price of turning §0.5's architectural pin into a
procedural one with a documented exception, and this document's single most
important clause is not worth that. **So the secondary is dropped, and its job is
done by a quantity that is not `e`:**

> **THE E1 SUPPORT CENSUS (§3.1), the replacement, preregistered here.** For each
> of the 85 fixtures and each club-cutoff cell, the **count of E1 matches
> strictly before the cutoff** and the **date of the most recent one**, read off
> the E1 archive's date index by a function that computes no decay weight, takes
> no half-life, and never touches the E0 archive. It is a count, not an evidence
> mass; it is published beside the E0-only `e`; it answers "did the treatment
> have anything to work with, and how much" without asserting a number on `e`'s
> scale.

**What the loss costs, stated plainly.** "The rule dissolved the thin
population" can no longer be reported as an `e` under the E1 archive. It does not
need to be: §0.5's own read-only arithmetic already answers it — one prior
Championship season adds **+29.25** at an August opener against a threshold of
**10.0** — and that arithmetic is over dates, not over an archive, so it is not
a leak. A future document that wants the E1-informed `e` itself must build the
second evidence API, preregister it, and take the architectural cost knowingly.

### 0.6 The E1 acquisition — two named, authorised, read-only-to-the-model passes

The second-tier archive does not exist. It is acquired **before the freeze**, by
two passes authorised here by name (§8.2, A0 and A1), and the acquisition is
**read-only to the model**: it fetches, parses, validates and registers, and
**no fit, no store build, no simulation and no estimand touches it until after
the seal commit that carries the freeze block.**

**What it acquires.** football-data.co.uk's E1 (EFL Championship) season files
for `1415`–`2526` — the same twelve season codes `epl.fetch.SEASON_CODES`
already holds, so every promoted club's second-tier history is covered on the
same window as the pinned E0 archive. Expected volume 12 × 552 = **6,624**
matches against E0's 4,560: the training set grows **≈ 2.45×** and the team
index from **29** at the 2019/20 opener and **35** at the 2026/27 opener —
both measured read-only from the pinned E0 archive as the distinct
`home_key ∪ away_key` of played matches dated before the cutoff — to roughly two
and a half times those. **The exact E1 club count is NOT estimated here**: the
acquisition measures it and publishes the census (§8.2, A0 and A1), and every
number in this document that would depend on it is stated as a rate or a ratio
rather than as a count.

**That the format is identical is established from the repository, without the
network.** `epl/oddscapture.py:79-93` documents football-data's multi-division
file and reads `Div` with the EPL rows as `Div == "E0"`;
`epl/livecycle.py:252-260` reads season CSVs with
`_E0_REQUIRED = ("Div","Date","HomeTeam","AwayTeam","FTHG","FTAG")` and filters
`Div == "E0"`; `epl/tests/test_livecycle.py:290` and
`epl/tests/test_oddscapture.py:34` already synthesise `E1` rows against those
readers. E1 is the same generator, the same directory, the same columns.

**Seven blockers stop E1 flowing through the E0 chain unchanged. Each gets a
ruled remedy here, and none of them edits a protected module.**

| # | blocker, with its citation | THE RULING |
|---|---|---|
| **B1** | `epl/fetch.py:31` `BASE_URL` and `:82` `raw_path` hardcode `E0` | `epl.lowerdiv.fetch_e1` composes its own URL and its own `raw_path` → `data/epl/raw/E1_{code}.csv`. `epl/fetch.py` is not edited; its cache-first, hash-pinned discipline is reimplemented in the new module with the same semantics (once cached, never re-downloaded; a byte change raises) and a committed test asserts the two paths never collide |
| **B2** | `raw/provenance.json` is keyed by `season_code` alone (`epl/fetch.py:174`), so an E1 record would **overwrite** the E0 record for the same season | E1 provenance goes to a **separate sidecar**, `data/epl/raw/provenance_e1.json`, keyed **`{division}_{season_code}`** (`E1_1415`, …). `raw/provenance.json` is not opened for writing on any path of this experiment. A committed test asserts the two files' key sets are disjoint and that the E0 sidecar's bytes are unchanged across the acquisition |
| **B3** | `epl/schema.py:52-53` `TEAMS_PER_SEASON = 20` / `MATCHES_PER_SEASON = 380`; `epl/validate.py:85-109` asserts 380 matches, 20 clubs, 19 opponents each. E1 is 24 / 552 / 23 | The E1 validator is a **division-parameterised copy** in `epl/lowerdiv.py` at (24, 552, 23), applying the identical check list. `epl/schema.py` and `epl/validate.py` keep their E0 constants and their E0 callers unchanged. A season that fails any check **refuses**; it is not dropped and it is not repaired |
| **B4** | `epl/teams.py` holds **36** registered clubs and **97** indexed spellings (measured); every Championship-only club resolves to `None` | The registry gains an entry per E1 club **before any fit**, as data, in `epl/teams.py` — the one file outside the write set this document touches, and it is touched because a second registry would be a second source of truth for club identity, which is precisely the defect §8.9 exists to design out. `_build_index` (`epl/teams.py:109-121`) already refuses a fold collision at import, so a Championship spelling whose fold collides with a registered one **blocks everything at import time**, loudly. The acquisition pass therefore **enumerates every E1 spelling and its fold BEFORE the registry is written**, and publishes the enumeration (§8.2). A committed test re-resolves the pinned E0 archive's `home_team_raw` / `away_team_raw` through the enlarged registry and asserts **every E0 key is unchanged** |
| **B5** | **THE PHANTOM-CLUB HARD FAILURE.** `epl/fit.py:157-158` does `played["home_key"].astype(str)`, so a null key becomes the literal string `"None"` and **every unregistered Championship club silently merges into one mega-club with its own attack and defence, and the fit looks healthy.** Unreachable today (all 35 observed E0 spellings resolve); live the instant E1 lands | `epl/fit.py` is PROTECTED and is **not edited**. Instead: **a null key must REFUSE, never stringify.** `epl.lowerdiv.to_store_frame_e1` raises **`PhantomClub`** on any null `home_key` or `away_key` — naming the season, the date and the raw spelling — **before** it projects, so the refusal strictly precedes any stringification on this experiment's own call graph. **Two committed tests, both mandatory:** one asserts `PhantomClub` fires on a synthetic frame with one null key; the other asserts that `epl.fit.to_store_frame` fed the same frame *still* produces the string `"None"` — the hazard is documented as live in the protected module and closed by refusal upstream, not by a fix we may not make. In addition the E1 build is **gated** on `manifest_e1["issues"] == []` and on an empty unresolved-spelling list in `team_name_mapping_e1.json`. **The invariant is scoped, not global** (§5.6): the live hazard remains in `epl.fit.to_store_frame` and its existing callers — the incumbent store builder and `epl.walkforward.point_in_time_canary` reach it directly — and this document may not claim a repository-wide property it does not enforce |
| **B6** | `epl/parse.py:145` `_match_id = sha256("{season_code}\|{date}\|{home_key}\|{away_key}")[:16]` carries no division, and the two archives merge into one store keyed on `match_id` | E1 ids are composed by a **new recipe used only for E1 rows**: `sha256("{division}\|{season_code}\|{date}\|{home_key}\|{away_key}")[:16]`. E0 ids are untouched and byte-identical. A committed test asserts the E0 and E1 id sets are **disjoint** on the built archives, and `E1Leak` fires if an E1 id is ever found in an E0 artifact |
| **B7** | **THE PROJECTOR RELABELS EVERY ROW.** `epl/fit.py:72-80` sets `TOURNAMENT_LABEL = "Premier League"` and `:151-163` writes `"tournament": TOURNAMENT_LABEL` unconditionally; `build_store` (`:194-203`) records `source_version = paths.rel(paths.MATCHES_PARQUET)`. **Delegating the E1 projection to that path would label every Championship row "Premier League" and attest the E0 archive as its source** — the union store §2.1 specifies could not be produced | The E1 half is projected by a **lowerdiv-owned projector**, `epl.lowerdiv.to_store_frame_e1`, which produces the identical column set and identical dtypes but preserves `tournament = "EFL Championship"` and `city = home_key`, and is written by `epl.lowerdiv.build_store_e1` **directly** through `wcmodel.data.store.BitemporalStore.write` (a read-only import; `src/` is not edited) with `source = "epl.lowerdiv"` and `source_version` naming `data/epl/matches_e1.parquet` and its digest. **The E0 half is unchanged**: it is projected by protected `epl.fit.to_store_frame` exactly as the E0 store is, so the union store's E0 rows are value-identical to the E0 store's, which §3.2's parity check asserts column by column. A committed test reads back every row of a synthetic union store and asserts the division label and source provenance of each half through the real build path |

#### THE ACQUISITION IS TWO PASSES, NOT ONE, AND THE ORDER IS FORCED

v1 specified one acquisition pass that fetched, parsed, resolved, validated and
wrote the archive, and also required the club-spelling enumeration to be
published **before** `epl/teams.py` was written. **That is not executable, and
the repository says why.** An unregistered spelling resolves to `None`
(`epl/parse.py:185-201` retains the row and records an issue); a null club key
fails validation immediately (`epl/validate.py:92-96` adds a failed
`teams_resolved` check and returns); and under B3's ruling a season that fails
any check refuses. One pass cannot discover the names, wait for a registry
commit, and then resolve, validate and write. **So the acquisition is split, and
each half has its own marker, its own products and its own failure law:**

> **A0 — FETCH AND CENSUS. Network, no resolution, no archive.** Fetches the
> twelve E1 season CSVs under B1/B2's rulings (cache-first, hash-pinned, refusing
> a byte change on a cached file), writes `data/epl/raw/E1_{code}.csv` and
> `data/epl/raw/provenance_e1.json`, and publishes the **outcome-blind spelling
> census**: every distinct `HomeTeam`/`AwayTeam` string, its normalised form, its
> index fold, its per-season presence, and the fold-collision check's result
> against the current registry. **A0 reads no score column at all** — a committed
> test asserts the census function's input frame is projected to the date and
> team columns before it is touched, and that no goal column reaches it. A0
> writes no parquet, resolves no name and builds nothing.
>
> **THE REGISTRY COMMIT — between the passes, by hand, against the published
> list.** `epl/teams.py` gains one entry per E1 club, written against A0's
> measured census rather than a guessed one. A fold collision is resolved by
> **refusing**, never by renaming a club (§10).
>
> **A1 — PARSE, RESOLVE, VALIDATE, WRITE. No network.** Re-reads the cached
> CSVs, re-verifies each against A0's recorded digest, parses under B6's id
> recipe, resolves every name through the enlarged registry, validates under B3
> at (24, 552, 23), refuses under B5, and writes `data/epl/matches_e1.parquet`,
> `data/epl/manifest_e1.json` and `data/epl/team_name_mapping_e1.json`. An
> unresolved spelling at A1 is `AcquisitionIncomplete`: it means the registry
> commit was wrong, and the remedy is to fix the registry and re-run A1 — never
> to drop the season and never to null the club.
>
> **A1 is the only half that may be re-run**, because it is a pure function of
> the cached bytes and the registry, it fetches nothing, and re-running it after
> a registry correction conditions on nothing but a spelling. **A0 runs once**
> and its marker is terminal.

**What the acquisition publishes, in this document, BEFORE the freeze block is
rendered** (§8.2, appended as a dated §8.10 note, and refused as a freeze
precondition if absent) — **and the list is an allow-list, not a minimum**: the
twelve fetch records with URL, byte size, SHA-256 and fetch time; the per-season
**structural** validation report (row count, club count, opponent counts,
unplayed count) with every failure named; the **complete distinct-club census and
spelling set** with each spelling's index fold and the collision check's result;
the count and identity of any unmapped name; and the E1 archive's SHA-256, row
count, byte size and per-season club census, which the freeze block then pins.

> **NO OUTCOME SUMMARY OF THE TREATMENT DATA MAY BE PUBLISHED BEFORE THE FREEZE,
> AND THE GOAL RATE IS THE CASE THAT MATTERS.** v1 required the acquisition pass
> to measure "the E1 goal rate against E0's" and publish it in this document
> before the freeze block existed. That is a summary of the treatment's own
> outcomes, seen by the author while the operative law is still editable and
> while the guard that binds this file's bytes has no reference blob yet — and
> v1's own §2.2 then let it license a judgement ("if it differs *materially*",
> unthresholded, "that is a finding for a later preregistration"). **The goal
> rate moves after the freeze**: it is computed and published in
> `reports/epl_lowerdiv_result.md` (§9.4), not here. `--freeze-block` **refuses**
> if the §8.10 note carries any field outside the allow-list above, and the
> allow-list contains no scores, no goal counts, no goal rates, no result
> distribution and no derived outcome statistic of any kind. Structural counts —
> rows, clubs, opponents, unplayed fixtures — are not outcome summaries and are
> the only census this document is scoped by.

**If the acquisition fails any of its own checks, this preregistration is not
run.** A season that will not validate is not silently excluded: §10 makes
dropping one an invalidation, and the remedy is a new document scoped to what the
source actually publishes — the same remedy widening v2 pre-stated and then had
to take. **Abandonment publishes as an outcome**: if A0 or A1 refuses and the
experiment is not run, that fact and its cause are published as a dated §8.10
note and this document is closed, rather than quietly replaced by an
E1-informed successor.

---

## 1. The question, and the honest motivation

### 1.1 The finding, and what its predecessor left open

The widening experiment tested whether the predicate that decides predict-time
widening should be keyed on effective evidence mass rather than promotion
category. Its verdict, published in full at
[`reports/epl_widening_result.md`](epl_widening_result.md):

| gate | requirement | measured | ruling |
|---|---|---|---|
| (i) | thin-fixture mean ΔRPS ≤ −0.0010 | **−0.004130** (n = 85) | PASS |
| (ii) | 95% week-block CI upper < 0 | [−0.009620, **+0.000485**] (62 blocks) | **FAIL** |
| (iii) | 95% season-block CI upper < 0 | [−0.006613, −0.002196] (6 blocks) | PASS |
| (iv) | MW6 table gates above MC error | −0.0000258, inside the paired MC error | UNRESOLVED |

**The effect was the largest this program has ever measured — four times the
adoption bar — and it missed gate (ii) by +0.000485.** Its own §6.3 warning had
been frozen in advance and applied: *a miss at this power means "not detected at
this power," not "no effect."*

**The question this document asks is a different one.** Widening asked whether a
thin-evidence club should be made *less confident*. This asks whether it should
be made *better informed*: the model has never seen Hull's forty-six most recent
competitive matches, and this experiment gives them to it. The two are related —
if the second answer is right, the first is a workaround — which is exactly why
the result document named this the successor.

### 1.2 The counter-hypotheses, stated before the run

Three, each with a reading direction fixed now.

1. **Second-tier evidence may be worse than no evidence.** The Championship is a
   different competition: different opponent quality, different tempo, different
   goal rate. A club's attack parameter estimated largely from E1 matches is an
   estimate of its E1 attack, and the fixed bridge `delta_rating` (§2.2) prices
   an assumed *centre* for the league gap but not its *dispersion* — and the
   shared panel additionally pools the two divisions' scoring level and home
   advantage (§2.2). If the treatment worsens the 85 thin fixtures, that is the
   hypothesis this bullet names, and the result document must say so in these
   words rather than attribute the sign to noise.
2. **The improvement may be an artefact of the cold-start path dissolving.**
   §2.3 states the mechanism and §3.1 measures it. A promoted club with 46 prior
   E1 matches is no longer cold-start, so `epl/dcfit.py:171-191 cold_start_clubs`
   returns `[]` for it and Fix 3's prior-draw path is never entered. Some of any
   measured improvement is therefore "the model stopped drawing from the prior",
   not "the model learned about the club." The two cannot be separated by this
   design and the result document may not claim they can.
3. **The E1 arm's `dc_native` control is not the published `dc_native`, in one
   respect.** The control arm is refit against the **E0-only** store, so it *is*
   the published object — that is §3.2's identity control. But the treatment
   arm's provisional set differs from the published one for the reason in (2),
   and any claim that the three `ExcludedMassTooLarge` refusals dissolved (§3.4)
   must attribute it to the cold-start path disappearing, not to better parameter
   estimates.

### 1.3 Why this is not the widening rule under new vocabulary

* **Different object.** Widening changed a *predicate* at predict time and left
  the posterior bit-identical. This changes the *training data* and therefore the
  posterior. Nothing about the two treatments is shared.
* **Different mechanism.** Widening added a mix toward a max-entropy grid. This
  adds rows to a likelihood. No mix, no strength, no α.
* **Different failure mode.** Widening's risk was double-counting dispersion
  (v3 §1.3). This experiment's risk is the opposite: importing *confident* but
  *mis-levelled* evidence. §1.2's bullet 1 is that risk stated.
* **What is shared, and it is shared deliberately:** the population, the
  estimand's shape, the resampling, three of the four deciding gates and the
  table census — because direct comparability with `−0.00413` is the point.
  §6.4 is the honest account of what that comparability costs in power, and
  §4.0 is the account of the one gate the refounding stopped sharing.

### 1.4 What this design LOSES relative to its predecessor, stated as a loss

Widening's strongest control was `UntreatedMoved`
(`epl/evwiden.py:4509 assert_structural_zeros`): both arms came from **one
posterior**, so every untreated fixture carried a delta of exactly 0.0 at eight
decimals, and 33 of the 85 thin fixtures were structural zeros by construction.

**That control cannot exist here.** An E1-informed fit is a different fit —
different training rows, different team index, different posterior — so **every
fixture moves.** The two-sided structural-zero guard, the 33-of-85 zero-delta
arithmetic, and the "mechanically indistinguishable from an incumbent
provisional fixture" argument all evaporate. So does the arithmetic identity that
made the full-corpus mean equal the estimand × 85/2280.

**Three replacements, all mandatory and blocking:**

1. **The identity control at full corpus strength** (§3.2). The E0-only arm must
   reproduce the published corpus at eight decimals over **all 2,280 fixtures**
   of all 212 openings — not the 820 of widening's 78 openings. When the
   structural-zero guard is gone, the identity control is the only thing left
   that catches a harness bug, so it is made maximal rather than convenient.
2. **`assert_point_in_time`** (`epl/fit.py:206`) on the **E1-informed store**, at
   every opening, proving from the store itself that the latest training date is
   strictly before the cutoff.
3. **The collateral gate** (§4.4). Every one of the 2,280 published fixtures now
   moves, so the design creates a harm surface that did not exist under widening,
   and a gate family calibrated for a structural-zero design must gain a gate to
   cover it.

**The same loss arrives again at table level, and §3.3 rules it there.** The
predecessor's 32 table cells split 15 treated / 17 untouched for the same reason
its fixtures split 52 / 33: one posterior, so only a widened object could move.
Here every cell changes, the two-sided cell identity collapses to one side, MW19
stops being a structural zero, and the deciding population becomes all 32. A
reader who has followed §1.4 should expect §3.3 before reaching it.

---

## 2. The treatment and the estimand

### 2.1 The treatment, exactly

> **The E1-informed arm `dc_e1` is `dc_native` fit against a store containing
> the E0 archive AND the E1 archive, with every second-tier club given a rating
> on the E0 scale by §2.2's frozen offset, and with nothing else changed.**

Everything downstream is the incumbent machinery, untouched: the same frozen
config, the same seed 20260611, the same likelihood, the same ADVI settings, the
same `strength_prior` at `k_att = k_def = 0.6`, the same widening mechanism (c)
at strength 0.5, the same volatility and few-games arms, the same
`predict_1x2` projection. **Only E0 fixtures are predicted.** The E1 rows are
training evidence and nothing else; no E1 fixture appears in any estimand, any
gate, any ledger row's `probs`, or any table.

**The locked package takes the second league with a zero-byte diff, and that was
verified before this document was written.** `src/wcmodel/data/store.py`'s
`write` keys on `["match_id"]` and stores whatever columns the frame carries;
`read` is `SELECT * EXCLUDE (rn, _ingest_seq)`. `src/wcmodel/data/features.py`
`build()` filters `date < cutoff_day`, maps `tournament → tiers.match_type`, and
computes `decay_weight = 0.5**(age/365)`; nothing in it is league-aware, and
`tiers.match_type` maps any Championship label to `"other"` — **the same bucket
`"Premier League"` already falls into** (`epl/fit.py:73-80` names that
coincidence), so even the Elo K multiplier is unchanged.
`src/wcmodel/model/panel.py`'s `build_design` builds `teams` from the panel, and
`scoreline.py`'s `_priors` / `_rates` are indexed by `n_teams`. **No file under
`src/` or `scripts/` is edited, no lock version is required, and the lock chain
is untouched by design** (§12).

**`tournament` for E1 rows is `"EFL Championship"`, and the taxonomy is not
gamed.** `to_match_panel` carries `match_type`, and it would be mechanically
possible to tag E1 rows with a label mapping to a different `tiers` bucket so
that a league flag reached the panel with zero new code. **That is refused**: it
is a lie in the taxonomy and it moves the internal Elo K multiplier as a side
effect. Both labels map to `"other"`, deliberately, and the E1 mask of §2.2's
secondary is built by joining `mp["match_id"]` against the E1 parquet — never off
a panel column, because `to_match_panel` (`src/wcmodel/model/panel.py:33-36`)
selects nine columns and drops everything else. **The label survives only because
the E1 half is projected by this experiment's own projector** (§0.6 B7):
protected `epl.fit.to_store_frame` overwrites `tournament` with
`TOURNAMENT_LABEL = "Premier League"` on every row it touches, so delegating the
E1 projection to it would silently erase the division this clause names.

**The write set is closed** (§8.3): all code lands in `epl/lowerdiv.py` and
`epl/tests/test_lowerdiv.py`, plus registry data in `epl/teams.py` under B4's
ruling. `src/`, `scripts/`, `site/`, `tools/`, `config/`, `.github/`,
`epl/simretro.py`, `epl/simmetrics.py`, `epl/leaguesim.py`, `epl/table.py`,
`epl/particles.py`, `epl/fit.py`, `epl/walkforward.py`, `epl/evwiden.py`, the
season ledgers and the pinned corpus are **not written**.
`PYTHONPATH=src scripts/oa_lock.py` must print `LOCK VALID` after every commit
this work produces — checked, not assumed.

**`epl/lowerdiv.py` is built in two committed stages, and the order is the one
§0.6 forces.** Stage 1 is the **acquisition surface alone** — `fetch_e1`, the
census, the parameterised validator, the id recipe, the projector and the
registry tooling — written, tested and audited, and committed **before A0 runs**,
because A0's command cannot execute a module that does not exist. Stage 2 is
every experiment surface: the anchor, the store builder, the fit legs, the table
leg, the estimator, the gates and the lifecycle. The freeze block hashes the
finished file, not the stages; §8.3 states where each stage sits in the
lifecycle.

### 2.2 THE CALIBRATION RULING

`epl/anchor.py:114-122 AnchorState.z` **raises `KeyError` for any club with no
rating**, and `epl/dcfit.py:261-266` calls `state.elo_z(teams)` on the whole
panel team set. Adding the Championship clubs to that set — however many the
acquisition pass finds — therefore raises on the first fit unless every
second-tier club has a rating on the E0 z-scale. The
calibration is not decoration; it is the thing that makes the fit run.

#### PRIMARY — (a) a fixed league-strength BRIDGE, `delta_rating` = −75.0, frozen by citation

> **THE BRIDGE ASSUMPTION, named as an assumption.** This experiment prices every
> crossing in either direction by one constant, `delta_rating = −75.0` rating
> points, and **treats the two divisions' centres as if they were exactly that
> far apart.** That is a modelling assumption this document adopts and does not
> validate. It is not an arithmetic identity, it is not an estimate of the
> unconditional gap between the two ladders, and it is not what the number was
> chosen to mean.

**The symbol is `delta_rating` throughout — prose, schemas, code and tests — and
it is never written `δ`.** §6's power grid sweeps a *different* quantity, an RPS
effect size, and that one is `mu_rps`. v1 wrote both as `δ`; units disambiguated
them for a human and nothing disambiguated them for an implementation.

> **WHAT `−75.0` ACTUALLY IS IN THE REPOSITORY, AND WHY THAT MATTERS HERE.**
> `epl/elo.py:29-44` states its meaning in full: it is a **destination seed for a
> selected promotion cohort** — "PROMOTED CLUBS ARE SEEDED BELOW THE DIVISION
> MEAN … Seeding them AT the mean would assert that a club arriving from the
> second tier is an average Premier League club" — and, with the carryover rule,
> a **division-mean stabilisation device**: "re-seeding 3 clubs at `mean + offset`
> roughly cancels that upward drift". It was fitted to the clubs that go *up*,
> conditional on having earned promotion. **It was never an estimate of the
> difference between the two ladders' centres, and it was never used in the
> reverse direction.** This experiment uses it as both. That is a new assumption
> wearing an old number's authority, and the consequences run all the way into
> what the estimand may be read as saying (§2.3).

Every constant of the construction, frozen here:

1. **The second-tier ladder.** The E1 ladder is computed on the **E1 archive
   alone**, with the **identical frozen `EloConfig`** — the same `k`, the same
   `home_advantage`, `carryover = 1.0`, `debut_offset = 0.0`,
   `promoted_offset = −75.0`, `initial_rating` — read from
   `epl.freeze.frozen_elo_config()`, and with `epl.elo`'s own within-season
   update applied unchanged. **`epl/elo.py` is not edited and the E0 ladder is
   not recomputed.**
2. **The mapping onto the E0 scale.** At any cutoff `C`, for a club `t` rated
   `r_E1(t, C)` on the second-tier ladder:

   ```
   r_E0(t, C)  =  ( r_E1(t, C) − mean_E1(C) )  +  ( mean_E0(C) + delta_rating )
   ```

   where `mean_E1(C)` and `mean_E0(C)` are the two divisions' means over the
   clubs that completed the most recent season of each division before `C` —
   **exactly the `division_mean` `epl/elo.py:361` already computes**, on each
   archive separately. A club's position *within* its own division is preserved
   exactly; the division's centre is *assumed* to sit `delta_rating` below the
   top flight's.

2b. **THE SOURCE-LADDER RESOLVER — total, and stated because the fit demands
   totality.** `epl/dcfit.py:261-266` calls `state.elo_z(teams)` on the whole
   panel team set and `epl/anchor.py:114-122` raises for any club without a
   rating, so **every club in Arm A's team index must resolve to exactly one
   source ladder at every cutoff.** A club with history in both divisions is the
   ordinary case, not the exception, and v1 did not say which ladder wins. The
   rule, total over every membership and crossing history:

   | case, evaluated at cutoff `C` | source rating |
   |---|---|
   | the club's **most recent played match strictly before `C` was an E0 match** | its **E0 ladder** rating at `C`, unmapped — it is already on the E0 scale |
   | the club's **most recent played match strictly before `C` was an E1 match** | its **E1 ladder** rating at `C`, mapped by point 2 |
   | the club has **no played match in either archive before `C`** | it cannot be in the team index — the index is built from the panel and the panel is built from pre-cutoff played matches — so no rating is requested. If one is requested anyway, **`LadderBoundaryMismatch`**; it is not defaulted to either mean |

   **Repeated crossings need no extra rule**: "most recent division played" is
   evaluated at each cutoff independently, so a club that goes up, down and up
   again is priced from whichever ladder it was last on. A committed test asserts
   the resolver is total over the union team index at all 212 openings, that
   exactly one branch fires per club-cutoff, and that a club present in both
   archives in the same season raises rather than resolving.

2c. **THE Z-SCALE IS ARM B'S, AND THAT IS A CHOICE THIS DOCUMENT MAKES
   EXPLICITLY.** `epl/anchor.py:213-216` computes `mean` and `sd` **over the
   teams it is asked for** — `r = np.array([ratings[t] for t in teams]);
   mean = np.mean(r); sd = np.std(r)` — and `elo_z` divides by that `sd`. Arm A
   asks for a union team set roughly two and a half times the size of Arm B's, so
   a bare call **re-centres and rescales the whole z-prior**, and every E0 club's
   z-score moves because other clubs were added. Mapping raw E1 ratings onto an
   E0-centred raw scale does not survive that: the treatment would silently
   include a renormalisation of the incumbent's priors.

   **The ruling:** `epl.lowerdiv.CrossLeagueAnchor` constructs the `AnchorState`
   for Arm A **directly**, with `mean` and `sd` set to the values protected
   `epl.anchor.Anchor` returns for **Arm B's E0 team set at the same cutoff** —
   the reference scale, frozen per cutoff, identical in both arms. `epl/anchor.py`
   is not edited; `AnchorState` is constructed through its own public
   constructor. A committed test asserts that at every one of the 212 openings
   the two arms' `(mean, sd)` are bit-identical, and that every E0 club's `elo_z`
   under Arm A equals its `elo_z` under Arm B to `1e-12` — **so the only thing
   the treatment moves on the E0 clubs' priors is nothing at all**, and every
   z-score difference between the arms belongs to a club the E1 archive added.
3. **THE E1 SEASON BOUNDARY — written out here, because the code cannot get it
   right on its own.** The two ladders are independent and **no rating is carried
   across a division boundary in either direction.** `epl.elo._open_season`
   (`epl/elo.py:339-384`) defines `promoted = clubs − prev_clubs` and seeds every
   member at `division_mean + promoted_offset`. **On the E1 archive that rule is
   wrong for half the arrivals**: a club dropping into the Championship from the
   Premier League is in `clubs − prev_clubs` exactly like a club climbing from
   League One, and a bare run would seed it 75 points *below* the Championship
   mean when it should sit *above* it. **No exception would be raised.** The
   boundary rule is therefore stated here rather than left to the code, and
   `epl/lowerdiv.py` classifies every E1 arrival explicitly from the two
   archives' own season memberships:

   **The three classes are named for what the data proves, not for where a club
   came from.** v1 called the third class "arrived from below (League One)";
   absence from both observed divisions last season does not prove League One
   provenance — a club returning after a multi-season gap, or one previously in
   E0 and long gone, is merely outside the two divisions this experiment
   observes. The labels are corrected accordingly and are the schema's own
   strings:

   | arrival at an E1 season boundary | classification | seed |
   |---|---|---|
   | in the previous E0 season, not the previous E1 season | **`from_E0`** | `mean_E1(C) − delta_rating` = `mean_E1 + 75` |
   | in neither previous season | **`outside_observed_divisions`** | `mean_E1(C) + delta_rating` = `mean_E1 − 75` — `epl.elo`'s own rule, unchanged |
   | in the previous E1 season | **`continuing`** | `mean_E1 + carryover · (r − mean_E1)`, `carryover = 1.0` — `epl.elo`'s own rule, unchanged |

   And on the E0 side, which this experiment does **not** touch, a club promoted
   from E1 keeps entering at `mean_E0 + delta_rating`: `epl.elo`'s existing
   promoted seed, unchanged, no new rule. **One constant, both directions, no
   second parameter** — and the reverse seed is the same number with its sign
   read the other way **because the bridge is assumed symmetric**, not because
   any identity makes it so.

   **`from_E0` DISCARDS AVAILABLE FORM, and that is the choice being made.** A
   club relegated straight out of the top flight has a live E0 rating, earned in
   the season that just ended, and this rule throws it away and reseeds the club
   at `mean_E1 + 75`. The incumbent's stale-rating rationale does not cover it:
   `epl/elo.py:38-44` concerns a club **returning** to E0 after an unobserved
   Championship spell — "remembered from before the evidence we do not have" —
   and a direct relegation has no such gap. The reset is chosen anyway, for one
   stated reason: carrying an E0 rating across the boundary would mix the two
   ladders' scales inside the E1 ladder, which is the one thing point 3 exists to
   prevent. **It is a cost, it is not free, and §11 carries it as a limitation.**
   Multi-season absences and repeated crossings fall out of the same rule with no
   extra clause: classification is re-evaluated at every boundary from the two
   archives' own memberships.

   **A committed test asserts the classification against the two archives**: for
   every E1 season boundary after the first, the `from_E0` set equals
   `E0(prev season) − E0(this season)` computed from the pinned E0 archive's own
   memberships, and the `outside_observed_divisions` set is disjoint from it. The
   first E1 season (2014/15) has no boundary and every club starts at
   `initial_rating`, exactly as `epl.elo`'s first-season branch already does.
   A club the two archives place in both divisions in one season, or an arrival
   the rule cannot classify, raises **`LadderBoundaryMismatch`** and stops the
   ladder; it is not repaired silently and it is not defaulted to either seed.
4. **`delta_rating` is NOT re-estimated, and the refusal is in the law because no
   guard is looking for it.** Estimating the bridge from the ~66
   promotion/relegation crossings in the twelve-season window would read outcomes
   inside the scoring window and make it a fitted parameter wearing a
   hyperparameter's name. The refusal is therefore preregistered:
   **`delta_rating` = −75.0, from `epl/config_frozen.json`'s `chosen` block, is
   not swept, not tuned, not re-derived, and not sensitivity-tested as a deciding
   quantity.** A future document that fits it must say its choice was informed by
   these numbers and carries exploratory standing only.

   > **THE `assert_tuning_only` CLAIM v1 MADE IS BACKWARDS, and the correction
   > matters because v1 leaned on it.** v1 wrote that the guard "keys on season
   > strings, so E1 rows carrying the label `2019/20` pass through it
   > undetected." It does not. `epl/windows.py:71-86` intersects the seasons
   > **present in the frame** with `SCORE_SEASONS ∪ EXCLUDED_SEASONS` and raises
   > on any hit; `2019/20` is the first member of `SCORE_SEASONS`, so exactly that
   > row is what it catches. **The real limitations are two, and neither is the
   > one v1 named:** the guard cannot distinguish divisions, so it cannot tell an
   > E1 tuning frame from an E0 one; and it protects only the call paths that
   > invoke it, so a bridge estimated outside those paths is unseen. This
   > document's refusal is therefore a *law*, enforced by §10 and by the
   > public-surface closure of §8.6, and it is not delegated to a guard that
   > behaves differently from the way v1 described.

**Where `−75.0` comes from and what that is worth — the provenance, corrected.**
It is the repository's frozen, data-chosen promoted seed: tuned on 2014/15–
2018/19 only, then frozen. **Its tuning-window contrast against zero is
`0.001309` RPS** (`epl/config_frozen.json`, `delta_vs_chosen`), and that is the
number this document may cite as the offset's measured worth on the window it was
chosen on. **The `0.0030` figure is a different quantity and v1 cited it as this
one**: it is `reports/epl_baseline.md:147-150`'s sensitivity, 0.2011 → 0.2041,
measured on an **already-observed scoring window**. `epl/windows.py:31-39` says
the relevant thing out loud — the scoring window "is blind with respect to the
Bayesian model and NOT blind with respect to Elo" — so `0.0030` is a previously
observed E0 scoring-window sensitivity, not fresh authority for a new bridge
role. Both numbers are reported; neither licenses the bridge. Its live arithmetic
is on the record at `epl/liveanchor.py:11-16`: Hull's stale rating 1398.9,
Ipswich's 1411.1, division mean 1594.6, promoted seed 1594.6 − 75 = 1519.6.

**What `delta_rating` does and does not do.** It is a *rating* offset feeding a
*prior mean* at `k_att = k_def = 0.6`. It shifts the prior, not the likelihood.
If the E1 rows in the likelihood disagree with it, the posterior overrides it —
which is the honest reading of "give the club real evidence," and is stated here
so it cannot be presented later as either a bug or a subtlety discovered after
the fact.

**THE TREATMENT ALSO POOLS TWO NUISANCES ACROSS THE DIVISIONS, and refusing
option (b) is what makes that so.** `src/wcmodel/model/scoreline.py:178-180,
216-217` carries **one `mu` and one `home_adv` for the whole panel.** Adding E1
rows to that panel therefore estimates a single scoring level and a single home
advantage over both divisions, whatever the Championship's own levels are. The
treatment is not "E1 evidence with everything else held fixed": it is **E1
evidence, plus a symmetric ±75 bridge, plus pooled scoring level and pooled home
advantage** — one package, tested as one thing. §2.3's estimand reading direction
is written to say exactly that and nothing more.

**src diff: zero bytes.** The construction lives entirely in `epl/lowerdiv.py`.

#### PRE-STATED SECONDARY — (c) a fixed down-weight γ = 0.5, REPORTED, DECIDING NOTHING

A second arm, **`dc_e1_gamma`**, identical to `dc_e1` except that after
`w = likelihood_weight(d, …)` every E1 row's weight is multiplied by a frozen
**γ = 0.5**.

* **γ = 0.5 is cited, not tuned:** it is the configuration's own
  `k_by_match_type["other"] = 0.5` multiplier and the frozen
  `model.widening.strength = 0.5`. **A γ swept over a grid is
  selection-on-outcome and is refused** — widening v3 §2.1's language on `e*` is
  the precedent and it is adopted verbatim here.
* **`src` diff: zero bytes**, exactly as for the primary arm.
* **The primary arm is γ = 1.0**, which is the null and a hypothesis rather than
  a knob: E1 evidence enters at exactly the decayed weight the likelihood already
  gives every match, with no second discount, because a discount is a second free
  constant and this design carries one.
* **The mask** is built by joining `mp["match_id"]` against
  `data/epl/matches_e1.parquet` (§2.1), and its definition is frozen: an E1 row
  is a row whose `match_id` is in the E1 archive's id set. The arithmetic
  identity is stated so it cannot be confused with §0.5's pin: under γ, an
  E1-informed club's evidence is `e_E0 + γ · e_E1`, and **the pinned population
  is defined on `e_E0` alone** — that is a bookkeeping note, not a contamination.
* **`dc_e1_gamma` runs over the 62 openings holding a thin fixture only** — not
  all 212 — because it is a secondary, it decides nothing, and it needs only the
  primary estimand's population. It has its own estimand, its own two intervals
  and its own row in the evidence file, each stamped `decides: "nothing"`.

#### REFUSED — (b) a per-match league indicator with a fitted coefficient

Out of scope, and the reasons are three:

1. **It needs a `src/` edit.** `src/wcmodel/model/scoreline.py:124-127` raises
   unless a covariate name is in `_PER_TEAM_COVS | _PER_MATCH_COVS`
   (`:42-43`), so option (b) is one string in `_PER_MATCH_COVS` — two lines with
   `src/wcmodel/model/panel.py:24` kept in sync — and therefore a **lock-v11**
   item on a chain that nothing polls and that any `src/` commit breaks
   silently until the next lock version.
2. **It changes `realised_config_sha256`.** Enabling a covariate moves the digest
   that §0.1 pins and that four standing EPL preregistrations pin, and
   `epl/dcfit.py:239-250`'s `EPL_COVARIATES` allow-list — currently exactly
   `("rest_days",)` — would have to be extended or `fit_epl` raises
   `NotImplementedError`.
3. **It does not estimate what its name suggests.** `_cov_offset` adds a
   per-match term symmetrically to both `log λ_home` and `log λ_away`
   (`scoreline.py:153-176`), so β is a league **scoring-rate** offset — "are
   there more goals in the Championship?" — **not** a league strength offset.
   Strength is already carried by the Championship clubs' own attack and defence.
   Paying a lock version and a moved config digest for a goal-rate nuisance
   parameter is not this experiment's trade.

**The E1 goal rate against E0's is measured and published AFTER the freeze, in
the result document (§0.6, §9.4).** It is an outcome summary of the treatment
data and it may not be seen while this law is editable. Whatever it turns out to
be, it is a finding for a later preregistration, and this document does not
pre-authorise one — and because it is now read after the freeze, it cannot have
shaped a single clause above it.

### 2.3 The arms and the estimand

**Both arms are two real fits at the same opening.** At each of the **212 block
openings of the pinned corpus** — every one, not a subset; §4.4 and §3.2 are why
— two fits run through the identical pipeline (`freeze.frozen_wcmodel_config()`,
seed 20260611, `epl.dcfit.fit_epl`), differing in exactly two inputs:

* **Arm B — `dc_native`** — fit against the **E0-only** store root
  `data/epl/fit/store/` with the incumbent `epl.anchor.Anchor` and the Arm-B
  feature cache `layout().cache_b`. This is the published object, refit.
* **Arm A — `dc_e1`** — fit against the **E1-informed** store root
  `data/epl/fit/store_e1/` (E0 ∪ E1) with §2.2's cross-league anchor and the
  Arm-A feature cache `layout().cache_a`. Only the block's E0 fixtures are
  predicted.
* **The delta** — `rps(Arm A) − rps(Arm B)` per fixture, `epl.score.rps` on the
  corpus's `y`. **The order of operations is frozen** (§3.2): probabilities are
  rounded to 8 dp first, RPS is computed on the rounded probabilities, and the
  subtraction is then rounded by `round(v, 8)`. A delta computed on unrounded
  probabilities is a different statistic and is not this one.

> **THE FAST PATH IS A CONTEXT, NOT A KEYWORD.** v1 named
> "`epl.dcfit.fit_epl` with `fast_panel=True`". **`fit_epl` has no `fast_panel`
> parameter** (`epl/dcfit.py:216-220`); the read-once fast path is established by
> an outer `epl.fit.config_read_once(cfg)` context manager, which is how
> `epl.walkforward.point_in_time_canary` (`epl/walkforward.py:491`) does it.
> **Every fit of this experiment runs inside exactly one
> `with epl_fit.config_read_once(cfg):` block per shard**, entered before the
> first fit of the shard and exited after the last, and a committed test asserts
> that no deciding fit runs outside one. An interface used as lifecycle law must
> be callable as written.

**`cold_start_clubs` is called with the E0 `matches` frame in BOTH arms**, so the
season-membership question ("which clubs are in this season?") is answered by the
top flight in both. What differs is `d.teams`, which under Arm A contains the
Championship clubs — and therefore a promoted club is no longer in
`clubs - set(teams)`, so **`cold_start_clubs` returns `[]` for it and Fix 3's
prior-draw path is never entered.** Likewise
`src/wcmodel/model/volatility_diagnostic.py:104-113` counts `games` from the
store's Elo rows, so a promoted club with 46+ E1 rows stops firing
`few_games_flag`. **Both of these are silent semantic changes with zero lines
edited, and both are pre-stated here rather than discovered by the run:** Arm A's
provisional set is not Arm B's, the 46-of-2,280 incumbent widened fixtures will
not reproduce under Arm A, and that is expected rather than a refusal.

> **THE ESTIMAND: the mean MATCHED-FIXTURE RPS difference, `dc_e1` minus
> `dc_native`, over the 85 pinned thin fixtures of §0.5.**
>
> **What a negative sign means, exactly.** Negative means **the whole treatment
> package helped**: the E1 rows in the likelihood, *plus* the symmetric ±75
> bridge of §2.2, *plus* the pooled `mu` and pooled `home_adv` that adding a
> second division to one panel forces. **It does not identify "second-tier
> evidence helps"**, because no arm of this design varies the bridge or unpools
> the nuisances. The result document must state the sign in the package's terms
> and may not attribute it to any component.

* **"Matched-fixture", not "CRN-paired", and the distinction is load-bearing.**
  The pairing this design actually guarantees is at match level: both arms score
  the *same fixture* against the *same outcome*, so the difference is a paired
  statistic. It is **not** fit-level common random numbers. Adding teams changes
  the sorted team index (`epl/dcfit.py:261`) and therefore the dimension and
  index placement of `att_raw`/`def_raw` (`src/wcmodel/model/scoreline.py:
  209-210`), and ADVI consumes the same seed in a different-dimensional graph
  (`src/wcmodel/model/inference.py:66-72`) — which promises no covariance
  reduction and is not an independent draw either. §6's scenario C exists because
  of this and is a sensitivity case, not a measurement.
* **The population is fixed at 85 and no fixture may be dropped.** It is
  §0.5's pin, joined on `match_id`, and it is not re-derived. **All 85 move** —
  there are no structural zeros (§1.4), so the estimand's sign is not a known
  multiple of any subset's.
* **The statistic** — the pooled mean over the 85 differences.
* **The season interval — THE DECIDING INTERVAL (§4.0).** `epl.score.block_bootstrap_ci`
  (`epl/score.py:193`) on the 85 differences, blocks = the **6 seasons**,
  `B = 10,000`, percentile, `alpha = 0.05`, resampling seed **20260814**. Its job
  is to refuse a result carried by one season, and the risk is quantified now:
  2019/20 holds 26 of the 85.
* **The week interval — REPORTED, NEVER DECIDING (§4.0).** Same function, same
  `B`, same `alpha`, same seed, blocks = the pinned **62** `(season, ISO week)`
  labels. It is computed and published with every result and it decides nothing.
* **BLOCK LABELS ARE REMAPPED TO ZERO-PADDED FIRST-APPEARANCE ORDINALS BEFORE
  EVERY BOOTSTRAP CALL.** `epl.score.block_bootstrap_ci` does
  `np.unique(labels, return_inverse=True)` (`epl/score.py:217`), which **sorts**,
  and its fixed resample indices then attach to blocks in *sorted* label order.
  Every block ordering in this document — the power construction, the estimand,
  the collateral leg — is therefore expressed as an ordinal string
  (`"00"`, `"01"`, …) assigned in first-appearance order over the frozen row
  order, so **sorted order and first-appearance order are the same order by
  construction** and the question cannot arise. *Measured, and recorded because
  it narrows the defect:* for the 85 fixtures' 62 `(season, ISO week)` labels and
  6 season labels the two orders **already coincide** (`2019/20|2019W32` …
  `2024/25|2025W20` sorts chronologically), so the thin leg was never exposed;
  for the corpus's 212 labels under §6.2's ascending-`match_id` row order they
  **do not**, because first appearance is then a hash order. The remap closes
  both and is asserted by a committed test.
* **The collateral estimand** — the mean over all **2,280** fixtures, with its
  own 212-block week interval and its own 6-season interval. Unlike under
  widening this is **not** the estimand × 85/2280; every fixture moves, so it is
  a genuine second number, and §4.4 makes it a gate rather than a note.

**Every deciding constant is frozen and is not overridable.** No CLI flag,
keyword or environment variable may pass a different `B`, `alpha`, block
definition, resampling seed, `n_sims` (20,000), simulation seed (20260611),
chunk size, `MC_BOOT` (2,000), `MC_SEED` (20260831), `K` (200, §5.4), `SHARDS`
(4), `delta_rating` (−75.0), `γ` (0.5) or population into any deciding
computation. §8.6's public-surface closure is where that sentence is made
mechanical: a production path **RESOLVES** these from the modules §0.1 pins them
in and carries no parameter for them at all.

### 2.4 The compute budget, stated so it cannot later become a reason to redesign

The predecessor's arithmetic does not carry over: **the two arms are two FITS,
not two predict passes off one posterior.**

| leg | fits | 20,000-season simulations |
|---|---:|---:|
| the post-freeze results canary, both stores (4 fits each) | **8** | 0 |
| the single-opening exercise (§8.4 step 2), both arms | **2** | 0 |
| the match legs: 212 openings × 2 arms | **424** | 0 |
| the γ = 0.5 secondary arm: 62 openings × 1 arm | **62** | 0 |
| protected `ArchiveRunner`, `dc_native` at all 32 priceable cells (the parity oracle) | **32** | 32 |
| the new runner, control + treatment at all 32 priceable cells (two fits per cell) | **64** | 64 |
| **the three unpriceable cells re-attempted under Arm A** (§3.4 secondary 1) | **3** | **3** |
| **the post-freeze experiment** | **595** | **99** |

**The three retry fits are budget, not a footnote.** §3.4's first secondary
re-attempts 2019/20 MW0, 2020/21 MW0 and 2023/24 MW3 under the E1-informed fit.
Those cells carry no treatment fit — they are outside the 32 — so each needs a
real fit and a real simulation. v1's table omitted them and totalled 592/96; the
work was mandatory in §3.4 either way, so the totals are **595 fits and 99
simulations**.

**Wall clock, computed from measured rates and stated before the freeze.** The
E0 cold rate is **57.24 s/fit** (`data/epl/fit/single_fit.json`, cutoff
2025-01-25, 4,019 training matches, 35 teams). The E1-informed fits train on
≈ 2.45× the rows with ≈ 2.5× the team parameters; the budget assumes **150 s/fit**
(2.6× the measured cold rate) and **post-freeze Step 2's** single-opening
exercise (§8.4 step 2) measures the realised rate and publishes it. At ≈ 1.24
minutes per 20,000-season simulation implied by the retro's recorded scale:

| leg | seconds | hours |
|---|---:|---:|
| 212 E0 fits at 57.24 s | 12,135 | 3.4 |
| 212 E1 fits at 150 s | 31,800 | 8.8 |
| 62 γ fits at 150 s | 9,300 | 2.6 |
| canary (8) + single-opening (2) | 1,036 | 0.3 |
| parity oracle: 32 fits + 32 simulations at ≈ 74 s | 4,213 | 1.2 |
| table: 64 fits + 64 simulations | 11,393 | 3.2 |
| the three unpriceable-cell retries: 3 E1 fits + 3 simulations | 673 | 0.2 |
| **total** | **70,550** | **19.6** |

**Budget ≈ 19.6 hours, bounded by 30.** Every featpanel key is a cold miss on
the first run in both arms (the key hashes the `< cutoff` result set and the
current HEAD, `src/wcmodel/data/features.py:315-412`, and §0.1 gives this
experiment its own two cache roots), so the warm-rate arithmetic that made the
predecessor's 78 openings cost twelve minutes does not apply here.

> **THE OVERRUN RULING, prestated with its threshold, because "bounded by 30" is
> not an instruction.** Of the 595 fits, **314 are Arm-A (E1-informed) fits** —
> 212 match-leg + 62 γ + 4 canary + 1 single-opening + 32 table treatment + 3
> retries — and the remaining cost, at the measured E0 rate and the retro's
> simulation scale, is **23,450 s**. The 30-hour bound is 108,000 s, so the
> budget survives an Arm-A rate up to `(108,000 − 23,450) / 314` = **269 s/fit**.
>
> **Step 2 publishes the realised Arm-A rate, and Step 3 refuses to start if it
> exceeds 269 s/fit.** The refusal is a **budget refusal**: it publishes, with the
> measured rate and the projected total, as a `complete: false` marker and a
> dated result document, and the experiment stops. **The run is then not thinned
> and not restarted** — a re-scoped run is a new preregistration (§10). There is
> no third option, and improvising one after seeing the clock is exactly the
> move §2.4's next paragraph forbids.

Shards run **sequentially** — the featpanel `.tmp` rename race in the locked path
crashes parallel shards and the fix is held for lock-v11, which this document
does not open — with
`OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1` pinned at the entry
point **before numpy import**, `python -u`, launched from a **nohup'd script
file, never a stdin heredoc** (macOS spawn re-imports `<stdin>` and kills the
gate's parallel leg), and waited **per PID**. A failed fit poisons its shard and
a failed shard poisons the merge (§7.1).

> **THE RUN MAY NOT BE THINNED.** Dropping openings, fixtures, cells, seasons or
> the γ arm to fit a clock is an amendment, not an optimisation — and that
> expressly includes sampling or truncating the 32-cell parity oracle, and
> expressly includes reducing the 212 openings to the 62 the primary estimand
> needs. A twenty-hour budget is not a reason to redesign anything, and a
> shorter one could not license it either.

---

## 3. Secondaries, controls, and the table leg

Everything in §3.1 and §3.4 is published with the result and **decides nothing**.
No secondary may adopt, block or qualify an adoption. A stratum that clears §4's
bar while the estimand misses it licenses nothing.

### 3.1 Reported, never deciding

* **THE E1 SUPPORT CENSUS (§0.5's replacement headline secondary).** For each of
  the 85 fixtures: `e_min` on the E0 archive (the pinned value), and for each of
  its two clubs the **count of E1 matches strictly before the cutoff** and the
  **date of the most recent one**. Plus the club-cutoff census: how many of the
  4,240 cells of widening v3 §0.4 have `e < 10` on the E0 archive **and** at
  least one prior E1 match. Plus the Hull / Coventry / Ipswich panel at the
  2026/27 opener: E0 `e`, E1 match count, last E1 date. **No `e` is computed on
  any frame containing an E1 row, here or anywhere** (§0.5), so this census is a
  count and never an evidence mass, and the two are never printed in one column.
* **The cold-start census.** How many of the 15 cold-start club-seasons stop
  being cold-start under Arm A, and how many club-cutoff cells stop firing
  `few_games_flag` — the mechanism §1.2 bullet 2 and §2.3 name.
* **The γ = 0.5 secondary arm** (§2.2): its 85-fixture mean, both intervals,
  and its delta against `dc_e1` per fixture.
* **Strata of the 85**: by season (6); by club category of the thin side —
  *returning-thin* vs *cold-start tail* (2). Eight intervals; some will exclude
  zero by chance; none decides, and that is the correction.
* **Movement diagnostic**: mean and max `|Δp|` between arms over the 85, and over
  the 2,280, printed beside the ADVI re-seed scale (per-match mean 0.0032,
  p99 0.0139, max 0.0229) and the pooled re-seed shift (+0.000075) from
  `reports/epl_walkforward.md:420-431`, so "did the treatment move more than
  re-seeding does" is on the record whichever way the estimand lands. **This is
  the one and only legitimate home of the `0.0032 / 0.0139 / 0.0229` triple:**
  they are absolute probability shifts and are compared only with this
  experiment's own `|Δp|`, like for like. They justify nothing about any bar.
* **The team-index census**: teams in the design at each of the 212 openings,
  both arms.

### 3.2 The identity control — 2,280 fixtures, exact equality, and it runs first

Every fitted opening's Arm-B predictions must reproduce the corpus's own rows
**exactly at their eight decimals** — **all 2,280 fixtures of all 212
openings.** This is strictly stronger than the predecessor's 820, and it is made
maximal on purpose: with the structural-zero guard gone (§1.4) this is the only
control left that catches a harness bug.

Additionally, each stored `dc_rps` must equal the RPS of its own stored
probabilities to `1e-12` (`ScoreMismatch`), and each Arm-B fit's own recomputed
provisional set must equal the ledger's recorded `provisional_teams` at that
cutoff (`PredicateMismatch`).

**THE FROZEN ORDER OF OPERATIONS, because "exact at eight decimals" is three
different demands until it is written down.** Per fixture, in this order and no
other: (1) `predict_1x2` returns float64 probabilities; (2) each probability is
rounded by `round(p, 8)`; (3) the identity comparison against the corpus row is
**exact equality on those rounded values**, no tolerance; (4) `epl.score.rps` is
computed **on the rounded probabilities** and compared with the stored `dc_rps`
to `1e-12` (`ScoreMismatch`); (5) the arm difference is formed from the two
step-4 values and rounded by `round(v, 8)`. Steps 3 and 4 are different checks at
different tolerances on purpose — one asks whether the forecast reproduced, the
other whether the stored score matches the stored forecast — and v1 left the
order between them, and the rounding, unstated.

**The control runs first, and not one Arm-A prediction is produced until it
passes.** A mismatch is a STOP (`ControlMismatch`) whatever its cause. Max and
mean `|Δp|` are reported even when zero.

> **A STOP IS NOT A DIAGNOSIS, and v1 published only the label.** "Most likely
> archive drift" does not distinguish archive drift from a stale store, a stale
> feature cache, environment nondeterminism, or a harness defect — and the pinned
> path depends on far more than `(cutoff, store, config)`: on this repository's
> code, on the installed PyMC/PyTensor/NumPy versions, on BLAS behaviour and
> thread count, and on the feature cache's contents and ordering. **On a
> `ControlMismatch` the harness publishes, before it exits:** the raw and rounded
> differences per offending fixture; the digests of the E0 archive, both store
> roots, both feature-cache roots and the ledger; the **environment fingerprint**
> of §8.6 (interpreter, package versions, BLAS vendor, thread environment); the
> freeze-state and dependency-hash results; and a **cause-classification matrix**
> naming which of {archive drift, store drift, cache drift, environment drift,
> harness defect} each of those comparisons is consistent with. The stop stands
> either way; what changes is that the reader can adjudicate it.

The demand is exact for the reason the predecessors proved: the seed does not
vary by cutoff, and a fit is a deterministic function of `(cutoff, store, frozen
config)` **holding code and environment fixed** — which §8.6's dependency hash
table and environment fingerprint are what make checkable rather than assumed.
The supporting citation is narrow and true —
`epl.walkforward.point_in_time_canary` (`epl/walkforward.py:450-460`) runs the
whole pipeline this experiment runs and compares **probabilities**, with a
positive control proving the corruption landed. `verify_fast_path_is_inert` is
**not** cited: it compares two feature frames with `DataFrame.equals`
(`epl/walkforward.py:321-329`), which is a check on panels, not on repeated
fitted forecasts. Beyond that citation, **the 2,280-fixture control is not
supported by an assumption; it is the claim under test.**

**These checks must be exercised directly, in the production code path.** The
in-tree audit of the predecessor's v1 established that loosening the exact
comparison to a `1e-4` tolerance left the entire suite green, because the stub
fitter in the tests reimplemented the control rather than exercising it — and
§10 makes widening that tolerance after a mismatch an invalidation, so the
untested site is exactly the site where it would be widened.
`epl/tests/test_lowerdiv.py` must carry tests that execute the real fit path —
not a stub — and go red when (a) the eight-decimal identity comparison is
loosened to any tolerance, (b) the `E1Leak` loop is disabled, or (c) the
`PhantomClub` refusal is disabled.

**And the point-in-time control on the new store.** `assert_point_in_time`
(`epl/fit.py:206`) runs on the **E1-informed** store at every opening, proving
from the store itself that the latest training date is strictly before the
cutoff day. `CutoffLeak` otherwise.

**THE STORES ARE BOUND BY CONTENT, NOT BY ROW COUNT.** `epl.fit.build_store`
(`epl/fit.py:194-197`) returns an existing store unchanged when
`len(existing) == len(frame)` and the `match_id` sets match — so a store whose
**scores, dates, teams, division labels or provenance** have moved is silently
reused, and v1's resume key `cutoff|arm|seed|config_sha256` bound none of that
either. Three rulings, all mandatory:

1. **`epl.lowerdiv.build_store_e1` never takes that shortcut.** It rebuilds
   unconditionally, or it verifies the existing table **column by column** against
   the frame it would have written and refuses on any difference.
2. **A canonical store digest is computed for each store root** — SHA-256 over
   the canonical serialisation of every decision-relevant column
   (`match_id, date, valid_as_of, observed_at, home_team, away_team, home_score,
   away_score, tournament, neutral, city`) in ascending `match_id` order — and
   the same is computed for the anchor's rating history and for the team index.
3. **Those three digests are bound into the resume key** —
   `cutoff|arm|seed|config_sha256|store_sha256|anchor_sha256|team_index_sha256` —
   recorded on every ledger row, published in the evidence file, and re-verified
   by `--verify`. In addition, the E1-informed store's **E0 subset must be
   value-identical to the E0 store's rows** on all eleven columns; a difference is
   `E1Leak`. A resume that cannot reproduce all three digests is not a resume.

### 3.3 The table-retro leg — the same 32-cell census, the same tie-aware machinery

**Why it exists:** the queue binds it ("historical walk-forward + table retro
before adoption"), the product impact lives at table level, and the one
Hull-analogue — Sunderland 2025/26, `e` = 0.172 at its opener — is visible only
here.

**The census is the predecessor's, pinned by the same record.**
`epl.simretro` is protected, its `ARMS` tuple is closed
(`("dc_native", "dc_wdl_bridge", "elo_wdl_bridge")`) and `ArchiveRunner._provider`
raises on any other arm — so the table leg is a **new** runner in
`epl/lowerdiv.py` that reuses `epl.leaguesim` / `epl.particles` / `epl.season` /
`epl.table` / `epl.simmetrics` (all read-only imports) and reproduces
`simretro`'s schedule through `simretro`'s own public surface:
`SEASONS × COMPARISON_CUTOFFS` **minus the three cells the feasibility census
measured as unpriceable = 32 cells**, cutoffs from `cutoff_schedule`, realised
tables through `realised_positions` / `realised_hash`, 20,000 simulated seasons
per arm per cell, seed **20260611**. `data/epl/sim/retro_r1.jsonl` is read-only
and never appended.

```
EXCLUDED_CELLS = ("2019/20|MW0", "2020/21|MW0", "2023/24|MW3")
```

All three refuse with `epl.particles.ExcludedMassTooLarge` against the 0.02
ceiling pre-stated in amendment A1 (`epl/particles.py:124`
`HARD_STOP_EXCLUDED_MASS = 2e-2`); all three are Manchester City fixtures against
a promoted side (man_city v sheffield_united 0.0234; v leeds 0.0216;
v luton 0.0328). **The exclusion is by measurement and is not a parameter: no
caller may name, restore or extend it.** A thirty-third cell, or a thirty-second
that is not one of these thirty-two, is `MembershipMismatch`.
`FeasibilityRecordMismatch` fires if the committed census record is absent, fails
its pinned digest, reports `completed: false`, or reports a priceable set that is
not exactly these 32.

**Per cell: TWO fits, one per arm** — this is the change from the predecessor,
where one posterior served both arms. The control fit is against the E0-only
store, the treatment fit against the E1-informed store, and the simulation uses
**common simulation indices and common RNG streams applied to two different
particle books**: identical `streams(seed, chunk, fixture_ordinal)`, identical
fixture ordinals, identical `n_sims`, drawn from posteriors that are not the
same. **The particle VALUES are not identical and this document never says they
are** — §5.5 sizes what that costs. D2 stays static-within-fit and D12 stays
per-fixture — the two standing open owner rulings this experiment does not touch.

**Both arms are labelled `dc_native` to `leaguesim`.** The provider *is*
`DCNativeProvider` in both arms — a `ParticleBook` may not wear another arm's
name — and what differs between them is the posterior. The experiment's own arm
name `dc_e1` is recorded on the row.

#### THERE ARE NO UNTOUCHED CELLS, and that changes the leg's shape

The predecessor split its 32 cells into **15 treated** and **17 untouched**,
because one posterior served both arms and only a widened fixture could move.
**Here the treatment is a different fit, so every one of the 32 cells changes** —
the same loss §1.4 records at match level, arriving at table level. Three
consequences, all ruled here rather than discovered by the run:

1. **The deciding population is all 32 cells, not a treated subset.** §5.2's
   estimator runs over all 32, giving **64 tallies in 32 files**, and §4.1's per-horizon
   means are taken over **every cell of the label** — MW0's 5, MW3's 6, MW6's 7,
   MW10's 7 and MW19's 7. **MW19 stops being a structural zero** and becomes an
   ordinary deciding label.
2. **The two-sided cell identity collapses to one side.** Every cell's two arms'
   `sampler_digest`s must **DIFFER**; equality at any cell is
   `TableIdentityBreak`. A treatment that changes no sampler output where the
   design says every cell must change is not a null result; it is a treatment
   that never reached the sampler, and reporting its zero delta as evidence of no
   harm would be reporting the absence of the experiment. The predecessor's other
   side — an untouched cell that moved — has no referent here and is **not**
   carried forward as a check that could never fail.
3. **"E1-informed clubs" is a REPORTED annotation, and it is OUT of the frozen
   schedule.** For each cell, the clubs with at least one E1 match strictly
   before that cutoff whose E0-only `e` is below 10.0 — the E0 `e` computed from
   the **pinned E0 archive** by the §0.3 recipe, the E1 side a count off the E1
   archive's date index (§0.5: no `e` on an E1-bearing frame), predicate strict
   `<`, `e` values at 2 dp, clubs serialised as a **sorted list of canonical
   keys**. It is published per cell and per label so a reader can see where the
   treatment had the most to work with. **It decides nothing and no gate is taken
   over it.**

> **THE DECIDING SCHEDULE IS THREE FIELDS, NOT FOUR.** v1 made the E1-informed
> club list the fourth element of `FROZEN_TABLE_SCHEDULE` and then had every
> deciding path validate that tuple — which put a nondeciding annotation,
> derived from an archive that does not yet exist, inside a digest whose
> mismatch stops the table leg. **`FROZEN_TABLE_SCHEDULE` is thirty-two
> `(season, cutoff_label, cutoff_date)` triplets and nothing else**, recomputed
> from the pinned corpus, the feasibility census and `epl.simretro`'s public
> constants — **all committed, none of them E1** — so the deciding schedule is
> derivable before the E1 archive exists and is frozen at the same moment as the
> rest of the membership. The club annotation lives in a **separate secondary
> object**, `e1_informed_clubs`, keyed by the same triplets, stamped
> `decides: "nothing"`, excluded from every membership digest and from every
> gate, and validated only for well-formedness.

**The exact schedule is a pin, triplet by triplet**: `FROZEN_TABLE_SCHEDULE`,
thirty-two `(season, cutoff_label, cutoff date)` triplets, recomputed by §8.2's
read-only pass from the pinned artifacts, and frozen in the harness the freeze
block hashes, **together with the per-label CELL census
`{MW0: 5, MW3: 6, MW6: 7, MW10: 7, MW19: 7}`**. An aggregate census alone permits
a bogus same-label season or a cutoff moved by a week; the schedule does not. A
departure from either is `MembershipMismatch`, and it is asked on every deciding
path — `table_cells`, `run_parity_oracle`, `run_table`, `score_table` and
`table_gate` each call it.

**The deciding horizon is MW6**, named here before any fit, on three grounds and
with one of the predecessor's grounds explicitly retired:

* **Comparability, which is the primary ground.** MW6 was the predecessor's
  deciding horizon, named there before any fit of that document. Moving it here
  would make the table comparison rhetorical for the same reason §4.2 gives for
  carrying the bar.
* **Denominator.** MW6 is 7 of 7 priceable, so its denominator is not a survivor
  of the feasibility census (MW0 lost two cells, MW3 one).
* **Product.** MW6 is the earliest scheduled horizon at which every club has
  played and the table has begun to separate, and it is where a thin-evidence
  club's dispersion is widest and where the issuance surface that motivated this
  work is published.
* **RETIRED: "the only all-treated label."** That was the predecessor's stated
  comparative ground and **it does not hold here**, because every label is now
  all-changed and MW10 and MW19 are also 7 of 7 priceable. Carrying it forward
  unexamined would be quoting an argument whose premise this design removed. It
  is named and dropped rather than left to a reader to notice.

§10 makes replacing the horizon after any table run an invalidation.

**`sampler_digest(run, tallies)` — sampler output only.** SHA-256 over the
canonical JSON (`epl.leaguesim.canonical_json`) of, in order: the scored position
matrix at full stored precision; the per-particle fractional rank-mass tallies of
§5.1; and the retained points, goal-difference and goals-for vectors. A separate
`substantive_digest` carries the fit-identifying fields (posterior digest,
provisional set, team index) and is reported beside it. The two have disjoint
jobs and neither may be computed from the other.

**The parity oracle — all 32 cells, complete before one treated simulation.**
Protected `epl.simretro.ArchiveRunner` at `dc_native` is run at all 32 priceable
cells, and each cell's new-runner **control** arm must reproduce it. The oracle
takes **no cell list**: a caller cannot name, sample or truncate it. **A treated
arm may not be simulated at any cell before that cell's native parity has been
established**, and the whole oracle must be complete before the first treated
simulation of the leg. `TableIdentityBreak` on any disagreement.

### 3.4 Table-side secondaries — reported, never deciding

1. **The three unpriceable cells, re-attempted under Arm A.** Re-run
   `epl.simretro.ArchiveRunner`'s equivalent at 2019/20 MW0, 2020/21 MW0 and
   2023/24 MW3 under the E1-informed fit and report the particle-mean excluded
   mass against the 0.02 ceiling (current values 0.0234 / 0.0216 / 0.0328). A
   drop below 0.02 would restore a 35-cell oracle for a future document and is
   the single most valuable side-effect available. **The mechanism is pre-stated
   (§1.2 bullet 3, §2.3): it would work because promoted clubs stop being
   cold-start, not because the parameters got better** — and a result document
   that reports the dissolution without that attribution overstates the finding.
   These three cells are **not** added to this experiment's oracle or to any
   gate; §10 makes adding one an invalidation. **They cost three real fits and
   three real simulations, and §2.4's budget carries them**: they are outside the
   32, so no treatment fit exists at them, and v1's budget table omitted the work
   its own §3.4 made mandatory.
2. **The Sunderland 2025/26 illustrative panel** (MW0, MW3, MW6 — the
   Hull-analogue cells), both arms: relegation probability, points mean, 5–95
   band. Zero decision weight, exactly as the predecessor treated it.
3. **Per-club points-interval coverage** (`epl.simmetrics.interval_coverage`,
   cov50 / cov90) for the **E1-informed clubs** of §3.3, both arms, **with its
   reading direction fixed now**: if the control arm's coverage for those clubs
   already sits at or above nominal and the treatment pushes it further above, that is evidence
   that the second-tier evidence is over-tightening rather than informing, and
   the result document must say so in those words. No sign is assumed.

---

## 4. The adoption rule

### 4.0 THE OWNER RULING THAT RE-FOUNDED THIS GATE FAMILY

v1 of this document required five conjunctive gates, and its own §6 then measured
that one of them — the 62-block week interval — would refuse the very effect the
experiment exists to detect most of the time. The owner ruled on that, and the
ruling is law here, quoted in full:

> **Owner ruling, 2026-08-30, binding.** *"The gate family is RE-FOUNDED on the
> prereg's own frozen power analysis. Gates that DECIDE: (i) the magnitude bar on
> the pinned 85; (iii) the season-block CI upper < 0; (iv) the table-safety gate
> (the 32-cell census, tie-aware joint estimator, precision regime); (v) the
> corpus-harm gate. The week-block CI (old gate ii) is DEMOTED to a reported
> diagnostic — published with its CI, never deciding — with the disclosed reason:
> 62 blocks of heavy-tailed deltas make it the binding gate at 3.6x the measured
> effect scale, it decided the predecessor by +0.0005, and a gate that would
> refuse a true effect ~70% of the time measures the design, not the model. The
> power analysis is the on-record basis; the demotion happens BEFORE any harness,
> any ingest, any fit."*

**Three things about that ruling matter for how this document must be read.**

1. **The basis is on the record and is this document's own.** The demotion rests
   on §6's frozen power construction — the same construction, the same seeds, the
   same committed CSV — and on the predecessor's published verdict
   (`reports/epl_widening_result.md`: gate (ii) `[−0.009620, +0.000485]`, a miss
   by `+0.000485` on an effect four times the bar). It does not rest on any
   number this experiment has produced, because this experiment has produced
   none.
2. **The timing is the whole point.** The demotion happens **before any harness
   exists, before the E1 archive is fetched, and before a single fit** — so it
   cannot be, and cannot be read as, a bar moved after a number. §10 keeps that
   true in the other direction: any further change to §4 after a delta exists is
   an invalidation.
3. **Demoted is not deleted.** The week interval is computed at every result,
   published with both endpoints, and reported in the evidence file and the
   result document with the same prominence as the deciding intervals. What it
   may not do is decide. §6.3 re-measures it under the refounded construction and
   states what it would have cost.

**The measured basis, re-run for v2 (§6.3), stated here so §4 carries its own
justification.** At the predecessor's own measured effect `−0.00413` on this same
population, the week interval's upper bound clears zero with probability
**0.13 to 0.42** across scenarios A–C and the three correlation regimes — it
refuses a real effect between **58% and 87%** of the time, and 90% at the
illustrative D endpoint. At the mid scenario in the independent regime it refuses
**70.8%** of the time, which is the ruling's "~70%". Its own 80%-power MDE is
**1.65× to beyond 4.8×** the measured effect. The season interval, which now
decides in its place, passes **0.14 to 0.49** over the same scenarios. A gate
whose refusal rate is set by *where thin fixtures fall in the calendar* rather
than by the size of the effect is measuring the design.

**Where the ruling's "3.6x" came from, reconciled rather than left to look
inconsistent.** The ruling cites the scale v1 published: v1's §6.3 reported a
five-gate joint MDE of `−0.015027` at its most pessimistic row, which is 3.64×
`−0.00413`. v2's construction fixes the row order, the block ordinals, the
scenario-C constant and the season-correlation gap (§6.2), so the re-run figures
above are the ones this document is bound by. **They do not weaken the ruling's
basis; they widen it** — under season correlation the week interval's own MDE
reaches 4.48× and beyond.

### 4.1 The rule

> **ADOPT the E1-informed arm (as a shadow arm, §4.6) if and only if ALL FOUR:**
>
> **(i)** the point estimate of the estimand is `Δ ≤ −0.0010` RPS over the 85
> pinned thin fixtures, **and**
>
> **(iii)** the 95% season block bootstrap CI (6 blocks) excludes zero — its
> upper bound is strictly `< 0`, **and**
>
> **(iv)** the table gate holds, in three parts, all required:
>
> > **(iv-a) The named-horizon gate — MW6.** The equal-weight mean over the
> > seven MW6 cells of `ΔTRPS = TRPS(treatment) − TRPS(control)` must be
> > **≤ +0.0002**.
> >
> > **(iv-b) The per-horizon point gates.** At each of MW0, MW3, MW10 and MW19,
> > the equal-weight mean of ΔTRPS over **every cell of that label** — 5, 6, 7
> > and 7 cells respectively — must be **≤ +0.0002**. No interval is computed at
> > these labels and none is required. **There is no treated subset and no
> > structural zero**: every cell changes under this design (§3.3), so every cell
> > of every label enters its label's mean.
> >
> > **(iv-c) The significance clause, at MW6 only.** Gate (iv) **fails** if the
> > lower bound of the MW6 mean's 95% season-block interval (7 blocks, §5.3) is
> > `> 0` — **whatever the sign of the point estimate.**
>
> **and (v)** the **collateral gate** holds, in two parts, both required:
>
> > **(v-a)** the mean matched-fixture RPS difference over **all 2,280 corpus
> > fixtures** is **≤ +0.000075**, **and**
> >
> > **(v-b)** gate (v) **fails** if the lower bound of that mean's 95% 212-block
> > week interval is `> 0` — **whatever the sign of the point estimate.**
>
> **Otherwise `dc_native` stands unchanged, Hull's forecast included.**
>
> **REPORTED, NEVER DECIDING — the week interval (v1's gate (ii)).** The 95%
> `(season, ISO week)` block bootstrap CI over the 62 pinned blocks is computed
> at every result, published with both endpoints, and **takes no part in the
> adoption decision under any sign or magnitude.** §4.0 is why. A result document
> that presents it as a gate, or an implementation that lets it reach the verdict,
> is an invalidation (§10).

All four are required and none is sufficient. **(i) and (iii) are the benefit
gates; (iv) and (v) are the do-no-harm gates.** Gate (iv) may additionally be
**UNRESOLVED** under §5.4's precision regime; UNRESOLVED blocks adoption and can
never grant one.

**THE SIGNIFICANCE CLAUSES DROPPED THEIR POINT-SIGN CONJUNCT, and the reason is a
perverse pass v1 carried.** v1 wrote both (iv-c) and (v-b) as "fails if the mean
is `> 0` **and** the lower bound is `> 0`". A percentile interval's lower bound
can sit above zero while the observed mean does not — the bootstrap distribution
is not centred on the statistic — and in that configuration v1's clause **passed
a harm the interval had resolved**. The lower bound alone is the condition that
means what the clause is for. *Measured, for the record:* under §6.2's
construction the configuration did not arise in any of the 2,000 replicates at
any scenario or regime, so §6.3's collateral table is **numerically identical**
under the amended clause and the correction costs no power — it closes a hole
rather than moving a bar.

### 4.2 The bar is the predecessor's, carried for comparability, and says what that costs

**`−0.0010` over the 85 thin fixtures is the widening experiment's bar,
unchanged.** It is carried rather than re-argued for one reason, stated plainly:
**this experiment exists to test whether it subsumes the −0.00413 its
predecessor measured, and a different bar over the same population would make
that comparison rhetorical.** Widening v3 §4.2's four grounds for the numeral are
carried with it and are not restated as new argument — including its own
disclosure that the numeral is borrowed from
`reports/epl_improved.md` §5.2's model-change bar while the authority is not,
because the house bar was set over a full evaluation window and this one over 85
fixtures chosen to be where the effect is largest, a difference in system-level
materiality of about 26.8×.

**What is different, and it is not in the bar's favour.** Under widening only 52
of the 85 fixtures carried the treatment and 33 were exact zeros, so the bar of
−0.0010 over 85 was a demand of −0.0016346 on the 52 that moved. **Here all 85
move, so the bar is the demand.** That makes the bar *nominally* easier and
*actually* harder, because the paired SD rises: the predecessor's realised paired
SD was 0.022751 over the 85 with a third of them structurally zero, and every
one of this design's 85 carries the noise of **two independent fits** rather than
two predict passes off one posterior. §6 is that arithmetic.

**Ground 4 — system-level materiality, and it is the concession, restated for
this design.** A passing result at −0.0010 over 85 fixtures is
`−0.0010 × 85/2280 = −0.000037` if the effect were confined to the 85 —
**smaller in magnitude than the +0.000075 re-seed shift.** Unlike under widening,
the effect is *not* confined, which is why gate (v) exists; but gate (v) is a
do-no-harm gate and §6.4 shows it cannot demonstrate a corpus-level benefit
either.

**Required disclosure, in the result document, in these words:** *"the rule's
corpus-level effect is below this model's own re-seed noise, and its value is a
claim about the fixtures it touches, not about the model's aggregate accuracy."*

**A corpus-level materiality condition on the benefit side is refused.** A pooled
benefit bar would be unclearable by construction and preregistering one would be
preregistering a guaranteed miss. The disclosure is required; the benefit gate is
not added. **A corpus-level do-no-harm gate is a different object and IS added
(§4.4).**

**What this experiment may claim on a pass at all four deciding gates,
exhaustively:**

1. that on **85 pre-specified thin-evidence fixtures** of the pinned corpus, the
   treatment package of §2.2 — E1 rows in the likelihood, a symmetric ±75 bridge,
   pooled scoring level and pooled home advantage — changed the mean
   matched-fixture RPS by the reported amount, with the deciding season interval
   and the reported week interval, at the power §6 states for the realised SD;
   and
2. that on the **2,280 fixtures of the whole corpus** the mean paired RPS delta
   did not exceed `+0.000075` and was not resolvably positive; and
3. that on **all 32 pre-specified table cells** the paired ΔTRPS did not exceed
   `+0.0002` at MW6 or at any of MW0, MW3, MW10 and MW19, and that the MW6 mean
   was not resolvably positive.

**What it may never claim, on any result:** a corpus-level accuracy improvement;
a quantified product value; that the improvement is attributable to better
parameter estimates rather than to the cold-start path dissolving (§1.2 bullet 2);
**that "second-tier evidence helps", or that any component of §2.2's package is
what moved the number** (§2.3 — the package is tested as one thing); anything
about Hull specifically at match level (§11 — one analogue, and it is in the
table leg); anything about the joint law, which no table metric here sees;
anything about `delta_rating` other than the frozen −75.0; that the two divisions'
centres are 75 points apart; or anything about a second-tier archive other than
the twelve E1 seasons §0.6 acquires.

### 4.3 The table gate's tolerance is invented, and says so

R1 has **no pass rule** — `reports/epl_sim_retro_v1_1.md` §10: *"Nothing, by
itself"* — so a table-level bar has no house precedent and one must be invented
for the queue's binding to be checkable. It is the predecessor's, invented from
R1's own recorded scale before any widened table existed: R1's paired dc-family
TRPS differences of "two parts in a thousand" on a TRPS of order 0.08 are ~2e-4
per cell, and the gate caps degradation at that scale — **+0.0002** — plus the
significance clause, so a small-but-resolvable worsening fails and an
unresolvable wiggle does not. A seven-block percentile bootstrap has poor
coverage, is not claimed to have good coverage, and has the narrow job both
predecessors gave season blocks: to refuse a verdict carried by one season.

### 4.4 The collateral gate, and why the doubled-fit design forces it

Under widening, an untreated fixture's delta was exactly 0.0 by construction, so
the treatment **could not** harm the 2,195 fixtures it did not touch. **Under
this design every one of the 2,280 published fixtures is refit and moves.** A
design that changes 2,280 published probabilities and measures 85 of them is not
honest, and a gate family calibrated for a structural-zero treatment must gain a
gate when the structural zeros go. That is the whole argument; gate (v) is
forced by the architecture, not chosen for convenience.

**Its point bar is `+0.000075` and it is cited, not invented:** it is this
model's own committed ADVI re-seed shift over this very corpus
(`reports/epl_walkforward.md:420-431` — DC mean RPS 0.201942 → 0.202017). The
reading: **the enlarged archive may not degrade the whole corpus by more than
re-seeding the optimiser already does.** Using the model's own noise as a
do-no-harm tolerance is the same move gate (iv) makes with R1's recorded scale.

**(v-a) IS AN OBSERVED POINT-TOLERANCE SCREEN, NOT A DEMONSTRATION OF NON-HARM,
AND THIS DOCUMENT CALLS IT THAT.** v1 said "(v-a) does the work … needs no
power". It is a threshold on a noisy point estimate at a margin far below the
estimate's own scale, so its operating characteristics are those of a coin at the
margin, and §6.3 measures them: **at a true corpus effect of exactly zero it
passes 0.51–0.57 of the time**, and **at a true harm of `+0.001` — thirteen times
its own bar — it still passes 0.03 to 0.48** depending on scenario and
correlation regime. Meanwhile (v-b)'s 80%-power harm MDE is `+0.00138` to
`+0.01718`, i.e. **18× to 229× the point margin**. So:

* **(v-a) is a screen on the observed number**, and a pass means "the observed
  corpus mean did not exceed `+0.000075`" and nothing stronger. It is not
  evidence that the corpus was unharmed.
* **(v-b) can only refuse**, and only a *resolvable* harm. **Unresolvable harm
  passes (v).** That is the honest shape for a do-no-harm gate at this `n`, and
  it is stated before the run so a pass on (v) cannot later be read as a
  demonstration of no harm.
* **The required sentence in the result document, verbatim on any pass of (v):**
  *"gate (v) refuses resolvable corpus-level harm and does not demonstrate its
  absence; at this corpus size the smallest harm it could have resolved is"* —
  followed by the realised (v-b) MDE from §6.5.

### 4.5 What happens on a miss, and what publishes either way

`dc_native` stands unchanged. **The result publishes either way** —
`reports/epl_lowerdiv_result.md` and the §9 evidence files are written whatever
the signs, including the embarrassing cases pre-named: the estimand positive
(second-tier evidence *hurts* the clubs it is meant to help); the estimand
negative with gate (v) failing (better thin fixtures, worse corpus); the estimand
negative with gate (iv) failing (better matches, worse tables); and gate (iv)
UNRESOLVED, which publishes as UNRESOLVED with every number and names which
precision condition fired. **There is no file drawer.**

A miss is not re-litigated: not at a second seed, not at γ = 0.5 promoted to
primary, not at a different `delta_rating`, not by dropping 2019/20, not by
re-deriving the population under the E1 archive, not by extending the corpus into
2025/26, not by a one-sided interval, not by a larger `n_sims`, not by adding a
third division, **not by promoting or demoting a gate after the number**, and not
by a bar rewritten after the number. Each appears in §10. **The week interval's
demotion runs in both directions**: it may not be restored to deciding to rescue
a pass, and it may not be invoked to overturn one.

### 4.6 What adoption would and would not change

Adoption is **shadow-first and this season ships nothing.** On ADOPT, `dc_e1`
becomes a shadow arm in the A8/A12 pattern — own ledger, own arm-tagged schema,
own verify, scored beside `dc_native` at `epl/livecycle.py`'s challenger step, no
matchboard, no gate, no pass rule — with the difference A8's objection carves
out: `dc_e1` defines a full scoreline law, so it **can** carry a shadow table.
The published arm, `ISSUANCE_SCHEMA_VERSION`, the matchboard and every published
surface stay exactly as they are. Switching the published arm is a separate,
later owner ruling with its own amendment, and this document does not
pre-authorise it.

**The invalidation cascade is named now.** A8's frozen recalibration constant
carries the clause "any change to decay, widening, inference or scoreline-model
semantics invalidates `a` until it is revalidated"
(`reports/epl_recal_grounding.md`). Research-phase runs here change no shipped
semantics, so `a` stands throughout this experiment. If the E1 archive is ever
adopted into the **published** arm, that adoption invalidates `a` until refit
under A8's own schedule, marks the A12 availability arm's downstream ledger rows
as pre-change history, **and creates a standing operational obligation the shadow
shape does not have: the E1 archive must then be kept current on the same cadence
as the E0 one, or the published arm silently degrades as its second-tier evidence
decays.** That obligation is named here so that an adoption ruling cannot be made
without it.

**Who decides.** Adoption is an owner ruling, recorded as a dated entry in
[`reports/epl_sim_amendments.md`](epl_sim_amendments.md). No script, agent or
report may change any arm on the strength of these numbers.

---

## 5. The table leg's Monte-Carlo error, and the precision regime

Gate (iv)'s tolerance is the same order as the simulation's own error, so a gate
without a frozen error estimate is a gate that noise can decide. This section
freezes the estimator in full and makes simulation noise able only to **refuse**.
It is the predecessor's §5, carried with its constants and with the one change
the doubled-fit design forces (§5.5).

### 5.1 The per-particle fractional rank-mass tally

The object TRPS scores is **fractional rank mass**, not ordinal rank.
`epl/table.py:374-377` says of `.order` that *"inside a shared block its sequence
carries no meaning and is only the deterministic club-index order"*, while the
scored matrix is built by `epl.table.position_mass` / `position_mass_sums`, which
spread `1/span` across the `span` positions a tie block occupies
(`epl/table.py:550-593`). A bootstrap over `.order` would resample a different
object from the one the point estimate scores.

For each deciding cell and each arm, from the run's own `retained_rows` and
`plan`:

```
ranking = epl.table.Ranking(
    block_start     = run.retained_rows.block_start,
    block_span      = run.retained_rows.block_span,
    resolution_code = run.retained_rows.resolution_code,
    order           = run.retained_rows.order,
    boundaries      = run.plan.boundaries,
    rule_id         = run.plan.rule_id)
mass = epl.table.position_mass(ranking)                    # [N, C, C] float64
T[s] = mass[run.retained_rows.particle == s].sum(axis=0)   # [P, C, C] float64
```

`order` is passed because the dataclass requires the field; **it is never read**.
Chunked accumulation is permitted provided chunks are visited in ascending season
order, and a committed test asserts equality with the whole-array form at 0.0.

**Two committed checks bind the tally to the point estimate it must describe.**

* **The matrix check, dimensionally exact:**
  `max |T.sum(axis=0) / n_sims − run.matrix| ≤ 1e-9`. `T[s]` accumulates
  **unnormalised** mass, so `T.sum(axis=0)` is on the scale of `n_sims` seasons
  while `run.matrix` is `mass.matrix / n_sims`. The division is part of the
  equation, not an implementation detail. The tolerance rather than bit equality
  is deliberate: the protected accumulator sums in **chunk** order and this one in
  **particle** order.
* **The equal-cluster check:** every particle's tally has every row and every
  column equal to `k = n_sims / P` to within `1e-9` — a league season is a
  bijection between clubs and ranks, and this is the condition protected
  `epl.simmetrics.trps_se_cluster` enforces on its own input
  (`epl/simmetrics.py:230-250`).

### 5.2 The estimator, frozen in full

**Deciding cells:** **all 32** cells of §3.3's `FROZEN_TABLE_SCHEDULE`, and no
others — there is no treated subset (§3.3). Each contributes two tallies
(control, treatment): **64 tallies in 32 files**, one `.npz` per cell holding
both arms, which is why §9.3's manifest lists thirty-two tally paths and not
sixty-four.

**Preconditions, and the refusal that guards them.** All tallies must report the
**same** `n_particles` `P`, and every particle must carry the same whole number
of simulated seasons. Under the pinned configuration `P = 1,000`
(`model.inference.draws = 1000`, bound by §0.1's `realised_config_sha256`) and
`n_sims / P = 20`. Any violation — unequal per-particle season counts, or unequal
`P` across cells or arms — raises **`TableMCImprecise`** and stops the table leg.
Joint resampling is undefined without a common index space and this document will
not approximate one.

**One resample per replicate, applied to every tally:**

```
rng = numpy.random.default_rng(MC_SEED)           # MC_SEED = 20260831
for r in range(MC_BOOT):                           # MC_BOOT = 2,000
    picked = rng.integers(0, P, P)                 # ONE draw, this replicate
    for cell c in the deciding cells:
        for arm a in (control, treatment):
            M = T[c][a][picked].sum(axis=0)
            M = M / M.sum(axis=1, keepdims=True)   # row-normalise
            s[c][a] = epl.simmetrics.trps(M, positions_c, spans=spans_c)
        d_r[c] = s[c][treatment] − s[c][control]
    mw6_r  = mean(d_r[c] over the 7 MW6 cells)
    mw0_r  = mean(d_r[c] over the 5 MW0 cells)
    mw3_r  = mean(d_r[c] over the 6 MW3 cells)
    mw10_r = mean(d_r[c] over the 7 MW10 cells)
    mw19_r = mean(d_r[c] over the 7 MW19 cells)
```

`positions_c` and `spans_c` are the cell's own realised position vector and
realised block widths from `epl.simretro.realised_positions` — the same two
arrays the cell's point estimate is scored with (`epl/simretro.py:1246,1261`).

**The standard errors, read off the replicate stream and nowhere else:**

```
mc_se_mw6  = std(mw6_r,  ddof=1)      mc_se_mw0  = std(mw0_r,  ddof=1)
mc_se_mw3  = std(mw3_r,  ddof=1)      mc_se_mw10 = std(mw10_r, ddof=1)
mc_se_mw19 = std(mw19_r, ddof=1)
mc_se_cell[c] = std(d_r[c], ddof=1)                     # reported, decides nothing
```

**There is no quadrature step and no independence claim anywhere in this
estimator.** `epl.leaguesim.streams(seed, chunk, fixture_ordinal)` reads only
those three things (`epl/leaguesim.py:199-207`) — not the season, not the cutoff,
not the cell — and all 32 cells run at the same `seed = 20260611`, so the cells'
Monte-Carlo errors are correlated by construction and the size of that
correlation is unknown. `sqrt(Σ se²)/7` would assume it away and is refused.

### 5.3 The MW6 season-block interval

The 95% percentile interval of §4.1(iv-c) is a season-block bootstrap over the
seven MW6 cells' ΔTRPS values, `B = 10,000`, `alpha = 0.05`, seed **20260814**,
blocks = the 7 seasons. Seven blocks have poor coverage, are not claimed to have
good coverage, and serve only to refuse a verdict carried by one season.

### 5.4 The precision and refusal rule, at every deciding boundary of gate (iv)

Gate (iv) is **UNRESOLVED** — it publishes, it blocks adoption, it can never
grant one — if any of the following conditions fires. Each is computed and
published with its value whether it fires or not.

* **P1** — the MW6 mean lies within `1 × mc_se_mw6` of the `+0.0002` bar.
* **P2** — the MW6 mean lies within `1 × mc_se_mw6` of zero **and** (iv-c)'s
  interval lower bound has the opposite sign to the mean.
* **P3.MW0 / P3.MW3 / P3.MW10 / P3.MW19** — that label's mean over **all** its
  cells lies within `1 × mc_se_<label>` of the `+0.0002` bar. **Four sub-
  conditions, not three:** MW19 is an ordinary deciding label under this design
  (§3.3) and a precision rule that skipped it would leave one of gate (iv-b)'s
  four point gates unguarded.
* **P4** — any deciding cell's `mc_se_cell` exceeds `+0.0002`, i.e. the
  simulation's per-cell error is larger than the tolerance the gate applies.
* **P5 — the unanimity rule, frozen, and it must agree with the POINT verdict.**
  In full pseudocode, because v1's prose lost the half that does the work:

  ```
  point_verdict = gate_iv(T)                      # the unresampled tallies,
                                                  # recomputed separately, not
                                                  # read back from anywhere
  verdicts = []
  for j in range(K):                              # K = 200, frozen
      rng_j  = numpy.random.default_rng(MC_SEED + 1 + j)
      picked = rng_j.integers(0, P, P)            # ONE resample, this stream
      T_j    = {cell: {arm: T[cell][arm][picked].sum(axis=0)
                       for arm in (control, treatment)}
                for cell in the deciding cells}   # row-normalised as in §5.2
      verdicts.append(gate_iv(T_j))               # the WHOLE of (iv-a),
                                                  # (iv-b) and (iv-c)
  P5_fires = any(bool(v) != bool(point_verdict) for v in verdicts)
  ```

  **P5 fires — and gate (iv) is UNRESOLVED — unless all 200 verdicts agree with
  each other AND with the separately recomputed point verdict.** v1 required only
  that the 200 agree among themselves, under which all 200 could unanimously
  reverse the point result and P5 would stay silent; the predecessor's own
  implementation does not have that hole (`epl/evwiden.py:7572-7578`:
  `any(bool(v) != bool(point_verdict) for v in verdicts)`), and this document
  restores it. *One half of the review's finding is refuted and recorded as
  such:* v1 was **not** ambiguous about the draw — it already said "one `picked`
  per stream" — and the pseudocode above simply makes that unmistakable.
  **Published in the evidence file:** `point_verdict`, all 200 `verdicts`, the
  `dissent_count`, and `fired`. `K`, the seed offset and the derivation are
  frozen and are not overridable; a scale comparison against `mc_se_mw6` is
  **not** a substitute and §10 makes replacing P5 with one an invalidation.

**EIGHT CONDITIONS, NO NINTH, AND THEY ARE NAMED RATHER THAN COUNTED.** The
canonical condition IDs are exactly:

```
PRECISION_CONDITIONS = ("P1", "P2", "P3.MW0", "P3.MW3", "P3.MW10", "P3.MW19",
                        "P4", "P5")
```

The evidence file carries all eight **by those IDs**, each with its computed
value and a `resolved: bool`, and every conformance and freeze check compares the
**exact named set** rather than a count — because v1 stated the count three times
and got it wrong once (§8.5's L10 said "seven … with no eighth" while §5.4 and
§9.1 said eight), and a renderer required to make prose counts and schemas agree
cannot satisfy two inventories. The set is eight and not the predecessor's seven
because §3.3 makes MW19 a deciding label, and a precision regime whose condition
list did not grow with its gate list would be a regime with a hole in it.

**The structural refusal, and how it is published.** If gate (iv) is UNRESOLVED,
the result document states which condition fired, with its computed value, and
states that no table harm was demonstrated and no table safety was demonstrated
either. **UNRESOLVED is a verdict and raises nothing** — conflating it with a
refusal would make the harness raise on a result it is required to publish.

### 5.5 The one change the doubled-fit design forces

Under widening, one posterior served both arms of a cell, so the arms' particle
draws were identical objects and the only divergence was the D12 widening branch.
**Here the two arms are two fits**, so their `ParticleBook`s are drawn from
different posteriors. CRN pairing is preserved **at the sampler** — identical
`streams(seed, chunk, fixture_ordinal)`, identical fixture ordinals, identical
`n_sims` — but it is **not** preserved at the posterior, and the paired MC error
of a cell is therefore larger than the predecessor's at the same `n_sims`.

**Consequences, all pre-stated:**

* P4 is more likely to fire than it was, and if it fires the honest reading is
  "20,000 seasons cannot resolve +0.0002 for a treatment that refits" — not
  "the treatment is harmless."
* `n_sims` is **not** raised in response. It is frozen at 20,000 by §0.1's pin on
  `epl.simretro.DEFAULT_N_SIMS`, and §10 makes running at a different `n_sims`
  an invalidation. A precision regime that could be escaped by buying more
  simulations after seeing the number is not a precision regime.
* The predecessor's gate (iv) was UNRESOLVED at a *smaller* paired MC error than
  this design will have. **Gate (iv) being UNRESOLVED again is the modal
  outcome of the table leg, and it is predicted here, before the run.**

### 5.6 The scope of the phantom-club invariant, narrowed

§0.6's B5 refusal protects **this experiment's call graph and no more.** The
hazard itself — `played["home_key"].astype(str)` turning a null key into the
string `"None"` — is inside protected `epl.fit.to_store_frame`
(`epl/fit.py:157-158`), which this document may not edit, and existing callers
reach it directly: `epl.fit.build_store` and `epl.walkforward.point_in_time_canary`
(`epl/walkforward.py:470`) both project through it without passing any lowerdiv
surface. **So the claim is not "a null key refuses anywhere in this repository";
it is "a null key refuses on every path this experiment runs."**

The enforceable form, and what §8.5's L4 tests: `epl/tests/test_lowerdiv.py`
**enumerates every call site in `epl/lowerdiv.py` that reaches a store
projection**, asserts each one passes through `epl.lowerdiv.to_store_frame_e1`
first, and asserts that a seeded direct call to `epl.fit.to_store_frame` from
lowerdiv code makes the test red. The companion test that shows the protected
module *still* produces `"None"` stays: the hazard is documented as live where it
lives, closed where this document has authority, and not claimed to be closed
where it is not. §10 makes stringifying a null key on any lowerdiv path an
invalidation; it makes no claim about paths this document does not run.

---

## 6. The power analysis

§0.5 counted where the treatment *bites*, which is support. This section asks
whether the **two deciding benefit gates (i) and (iii)** can jointly pass at the
effect this experiment exists to test, and answers before any delta exists. It is
also the on-record basis for §4.0's refounding, so it is stated in the form that
makes the demotion checkable: the deciding pair is sized, the demoted week
interval is sized beside it, and both are read off one stream.

> **WHAT THIS SECTION SIZES, AND WHAT IT CANNOT.** Every power number below is
> **`benefit_gate_joint_power`** — the probability that gates **(i) and (iii)**
> both pass. **It excludes gates (iv) and (v).** Those depend on 20,000-season
> simulations of two posteriors whose paired Monte-Carlo error §5.5 says is
> larger than the predecessor's and is not known in advance, so no closed form
> exists for them and none is invented. **Actual four-gate adoption power is
> therefore LOWER than every figure in §6.3, and by an unquantified amount.**
> v1 printed these figures under the heading "Joint power" without that
> sentence; it is now part of the quantity's name.

### 6.1 The scenarios, frozen blind

| scenario | paired SD | standing | source |
|---|---:|---|---|
| **A — widening-realised, thin** | **0.022751278102833457** | measured | the widening run's realised paired SD over **these same 85 fixtures** (`reports/evidence/widening.json` → `estimand.sd`). The optimistic floor — and it is optimistic for a named reason: 33 of its 85 rows were exact zeros with zero variance |
| **B — widening-realised, treated** | **0.028887934876731913** | measured | the same run's realised SD over the 52 fixtures that actually moved (`power.realised.sd_paired_treated`). The like-for-like scale for a population in which every fixture moves |
| **C — doubled-fit scale** | **0.04085370929162502** | **ILLUSTRATIVE** | `B × √2`, **derived programmatically from B's full-precision value and never transcribed.** Under widening both arms came from ONE posterior, so the sampler's own noise cancelled exactly in the pair; here the arms are two fits and the sampler noise enters twice. √2 is the independent-addition scale **for two noise terms of equal size**, and scenario B's SD is a *total* paired SD rather than an optimizer-noise SD — so √2 applied to it is **neither a bound nor necessarily conservative.** It is a sensitivity case with a stated construction, not a measurement and not a ceiling |
| **D — envelope endpoint** | **0.05777586975346383** | **ILLUSTRATIVE** | `B × 2`, carried for one purpose: to show what the deciding pair does if the doubled-fit penalty is worse than √2. It is not a scenario anyone predicts |

> **v1 PRINTED C WRONG, AND `--freeze-block` COULD NOT HAVE CAUGHT IT.** v1's
> table read `0.040854278…`; `0.028887934876731913 × √2` is
> **`0.04085370929162502`**. A renderer required to reproduce §6.3 *exactly*
> would have refused forever against a transcribed constant. **C and D are
> computed from B inside the harness**, and every table in this section is
> rendered from **one canonical power object** carrying the replicate-level
> booleans. **No scenario SD, power value or MDE is computed twice**: §6.3's
> cells and the ranges §4.0, §6.4 and §11 quote are all reads of that one object.
> That is also why v1 could print the same cell as `0.124` in one table and
> `0.123` in another.

> **`OUT_OF_POWER_ENVELOPE` — preregistered here, and it is a disclosure, not a
> gate.** If §6.5's realised paired SD over the 85 exceeds scenario **D**, the
> result document states `OUT_OF_POWER_ENVELOPE` and reports that **every power
> figure in §6.3 was computed at a variance smaller than the one that obtained**,
> so the realised power is below the tabulated range and the pre-run warning
> understated the problem. **No threshold moves in response and no gate changes**
> (§6.5); the flag exists so that a reader is not left comparing a result against
> an envelope it fell outside.

A power analysis that tests only optimistic variances is not a power analysis.

### 6.2 The construction, frozen

* **Structure:** the 85 pinned fixtures in their 62 pinned week blocks and 6
  seasons, **recomputed by the harness from the committed
  `reports/evidence/widening_per_fixture.csv`, never typed in**. **Row order:
  ascending `match_id`, stable mergesort** — `match_id` is the population's
  identifier (§0.5) and it is unique, whereas `key` takes only 62 distinct
  values, so v1's ascending-`key` order left the within-key order to whatever the
  CSV happened to hold — which v1 never pinned. **All 85 are
  treated** — there are no structural zeros (§1.4).
* **Block order:** first appearance in that row order, **remapped to zero-padded
  ordinal strings** (`"00"`, `"01"`, …) before any bootstrap call, so that the
  sorted order `epl.score.block_bootstrap_ci` imposes internally
  (`epl/score.py:217`, `np.unique`) **is** the first-appearance order. §2.3
  records the measurement that motivated this: the thin leg's 62 labels already
  sorted into first-appearance order, the corpus leg's 212 do not.
* **Noise:** for fixture *i* in week block *b* of season *s*, the delta is

  ```
  mu_rps  +  scenario_sd · ( sqrt(rho_s)·v_s + sqrt(rho_w)·u_b
                             + sqrt(1 − rho_s − rho_w)·z_i )
  ```

  with `v_s`, `u_b` and `z_i` independent standard normals. **`mu_rps` is the
  effect size being swept, in RPS, and it is not `delta_rating`** (§2.2, M1):
  the two were both written `δ` in v1 and are unrelated quantities.
* **The three correlation regimes, frozen, in this order:**
  `(rho_s, rho_w) ∈ {(0.0, 0.0), (0.0, 0.5), (0.25, 0.5)}`. v1 modelled week-
  block correlation only and stated that season correlation "is not modelled and
  is not claimed". **Under the refounded deciding set that omission is no longer
  affordable**: gate (iii) resamples six season blocks and is now a deciding
  gate, so its power is exactly the thing season-level correlation destroys. The
  third regime carries it explicitly, and §6.3 shows it is the regime that hurts.
* **Consumption order, frozen:** per regime, one fresh
  `numpy.random.default_rng(20260830)`, then
  `v = rng.standard_normal((R, n_seasons))`, **then**
  `u = rng.standard_normal((R, n_blocks))`, **then**
  `z = rng.standard_normal((R, n_fixtures))`. This is frozen because it is the
  part the predecessor's v1 left unfrozen, which made its stream unrecoverable
  and its numbers unreproducible (widening v3 §6.4). **Each regime gets a FRESH
  generator at the same seed**, so all three regimes draw the identical
  `(v, u, z)` arrays and differ only in the weights applied to them — common
  random numbers across regimes as well as across scenarios and across `mu_rps`,
  which is what makes §6.4's regime-to-regime comparisons differences in the
  correlation rather than in the draw.
* **Replicates:** `R = 2,000`.
* **The collateral leg's structure** (gate (v), §6.3's Table 3) is the same
  construction over the corpus: **the 2,280 fixtures of the committed
  `reports/evidence/anchoring_per_fixture.csv`** — deduplicated to one row per
  `match_id`, ascending `match_id`, stable mergesort — its 212 `block` labels and
  its 6 `season` labels, both ordinal-remapped. **The committed CSV, not the
  gitignored corpus parquet, is the structure's source**, so §6.3's Table 3
  is reproducible from Git alone; v1 cited the parquet and was not.
* **Gates:** the deciding benefit gates exactly as §4.1 states them, using
  `epl.score.block_bootstrap_ci` at `B = 10,000`, `alpha = 0.05`, seed
  **20260814**, on the 6 seasons (deciding) and on the 62 week blocks (reported).

**THE EQUIVARIANCE IDENTITY, and what "exact" does and does not mean here.**
`epl.score.block_bootstrap_ci`'s resample indices depend only on
`(seed, n_boot, n_blocks)` and not on the data (`epl/score.py:222-223`:
`rng = default_rng(seed); draw = rng.integers(0, n_blocks, size=(n_boot,
n_blocks))`), and its statistic is `sums[draw].sum(axis=1) / sizes[draw].sum(axis=1)`
— **affine in the data**. Therefore, for `s > 0`,

```
block_bootstrap_ci(mu_rps + s·ε, …)  =  mu_rps + s · block_bootstrap_ci(ε, …)
```

exactly, in both endpoints. **Measured read-only at the three named points
`(mu_rps, s) ∈ {(−0.0010, A), (−0.00413, B), (−0.0200, C)}`: maximum absolute
error `3.469e-18` over both endpoints.** Consequently the gates are **exactly
linear in `mu_rps`**:

```
gate (i)    passes iff  mu_rps  ≤  −0.0010 − s·mean(ε_r)
gate (iii)  passes iff  mu_rps  <  −s·hi_season(ε_r)
[reported]  gate (ii)   passes iff  mu_rps  <  −s·hi_week(ε_r)
```

so the whole power curve, at every `mu_rps` and every scenario, is computed in
closed form from **R triples** `(mean, season-CI upper, week-CI upper)` of the
**standardised** draw. Common random numbers are exact across `mu_rps` *and*
across scenarios, and the power curve is exactly monotone in `mu_rps` rather than
monotone up to Monte-Carlo error. A committed test must assert the identity
against direct evaluation at those three named points to `1e-15`; absent that
test the closed form is removed, not trusted.

> **"EXACT" IS A STATEMENT ABOUT THE REUSE, NOT ABOUT THE ESTIMATE.** The affine
> reuse is exact per bootstrap replicate — including under unequal season-block
> sizes, which the pooled `sums/sizes` estimator handles correctly. **`R = 2,000`
> is still finite Monte Carlo**, so every power figure in §6.3 carries a binomial
> standard error of `sqrt(p(1−p)/2000)`: **≈ 0.005 near 5% power, ≈ 0.010 near
> 25%, ≈ 0.011 near 50%.** Those standard errors are printed in the table rather
> than left to the reader. The MDE column is additionally subject to **grid
> interpolation error** at the `2e-4` step. Neither is a defect; both were absent
> from v1's account of why the simulation is "exact rather than approximate", and
> that account is corrected here.

**The MDE search grid and interpolation, frozen.**

* **Grid:** `mu_rps ∈ {0, −0.0002, −0.0004, …, −0.0200}` — 101 points, step
  `2e-4`. The collateral leg's harm grid is its positive mirror.
* **Power at a grid point:** the fraction of the R replicates at which **both**
  deciding benefit gates pass.
* **MDE80:** scanning from `mu_rps = 0` downward, the **first** adjacent pair
  bracketing power 0.80, linearly interpolated in `mu_rps`. **Tie rule:** a grid
  point whose power is exactly 0.80 **is** the MDE, no interpolation.
  **Exhaustion rule:** if 0.80 is never reached, the MDE is reported as
  `beyond −0.0200` with no interpolated value and the table says so rather than
  extrapolating.
* **Named evaluation points**, each its own evaluation at the same stream, never
  interpolated from the grid: the bar `mu_rps = −0.0010`; **the predecessor's
  measured effect `mu_rps = −0.00412976353895183`**; and twice the bar
  `mu_rps = −0.0020`.

### 6.3 The sizing tables

**Provenance of these numbers, stated exactly.** They are the output of a
**read-only sizing pass** run on 2026-08-30 at the constants above, which fitted
nothing, simulated no season and wrote nothing. **They are not yet the committed
implementation's numbers, because no harness exists.** §8.3 makes reproducing
them a freeze precondition: `python -m epl.lowerdiv --power` must produce these
tables exactly, and `--freeze-block` refuses to render otherwise. Because §6.2
freezes the consumption order, the block order, the row order and every seed, the
stream is fully determined by this document and reproduction is attainable — that
is the direct lesson of widening v3 §6.4, where an unfrozen consumption order
made the predecessor's v1 numbers unrecoverable.

**Table 1 — `benefit_gate_joint_power`, the DECIDING pair {(i), (iii)}.**
MC standard errors in parentheses on the column that decides the ruling.

| scenario | ρ_season | ρ_week | paired SD | power at the bar | **power at −0.00413** | power at 2× bar | joint MDE80 | ratio to the bar | **ratio to −0.00413** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A widening-realised, thin | 0.00 | 0.0 | 0.022751 | 0.139 | **0.494** (0.011) | 0.235 | −0.006647 | 6.65× | **1.61×** |
| B widening-realised, treated | 0.00 | 0.0 | 0.028888 | 0.124 | **0.387** (0.011) | 0.196 | −0.008444 | 8.44× | **2.04×** |
| C doubled-fit *(illustrative)* | 0.00 | 0.0 | 0.040854 | 0.107 | **0.269** (0.010) | 0.149 | −0.011952 | 11.95× | **2.89×** |
| D envelope endpoint *(illustrative)* | 0.00 | 0.0 | 0.057776 | 0.098 | **0.203** (0.009) | 0.124 | −0.016892 | 16.89× | **4.09×** |
| A widening-realised, thin | 0.00 | 0.5 | 0.022751 | 0.127 | **0.436** (0.011) | 0.204 | −0.007452 | 7.45× | **1.80×** |
| B widening-realised, treated | 0.00 | 0.5 | 0.028888 | 0.111 | **0.335** (0.011) | 0.169 | −0.009467 | 9.47× | **2.29×** |
| C doubled-fit *(illustrative)* | 0.00 | 0.5 | 0.040854 | 0.092 | **0.237** (0.010) | 0.133 | −0.013389 | 13.39× | **3.24×** |
| D envelope endpoint *(illustrative)* | 0.00 | 0.5 | 0.057776 | 0.084 | **0.171** (0.008) | 0.111 | −0.018945 | 18.95× | **4.59×** |
| A widening-realised, thin | 0.25 | 0.5 | 0.022751 | 0.098 | **0.216** (0.009) | 0.130 | −0.014225 | 14.23× | **3.44×** |
| B widening-realised, treated | 0.25 | 0.5 | 0.028888 | 0.093 | **0.175** (0.008) | 0.116 | −0.018053 | 18.05× | **4.37×** |
| C doubled-fit *(illustrative)* | 0.25 | 0.5 | 0.040854 | 0.083 | **0.139** (0.008) | 0.102 | beyond −0.0200 | — | **> 4.84×** |
| D envelope endpoint *(illustrative)* | 0.25 | 0.5 | 0.057776 | 0.078 | **0.116** (0.007) | 0.093 | beyond −0.0200 | — | **> 4.84×** |

**Table 2 — per-gate pass rates at `mu_rps = −0.00412976353895183`, which
identifies the binding gate and prices the demotion.** Gate (ii) is shown
because it is reported, and because §4.0's basis has to be checkable.

| scenario | ρ_s | ρ_w | gate (i) | **gate (iii) — season, DECIDING** | *gate (ii) — week, reported* | **{i, iii} joint** | *{i, ii, iii} — what v1 required* |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 0.00 | 0.0 | 0.897 | **0.494** | *0.416* | **0.494** | *0.369* |
| B | 0.00 | 0.0 | 0.845 | **0.387** | *0.292* | **0.387** | *0.259* |
| C | 0.00 | 0.0 | 0.764 | **0.269** | *0.176* | **0.269** | *0.151* |
| D | 0.00 | 0.0 | 0.696 | **0.203** | *0.114* | **0.203** | *0.095* |
| A | 0.00 | 0.5 | 0.864 | **0.436** | *0.317* | **0.436** | *0.274* |
| B | 0.00 | 0.5 | 0.811 | **0.335** | *0.225* | **0.335** | *0.192* |
| C | 0.00 | 0.5 | 0.729 | **0.237** | *0.133* | **0.237** | *0.117* |
| D | 0.00 | 0.5 | 0.674 | **0.171** | *0.096* | **0.171** | *0.079* |
| A | 0.25 | 0.5 | 0.719 | **0.216** | *0.388* | **0.216** | *0.207* |
| B | 0.25 | 0.5 | 0.680 | **0.175** | *0.334* | **0.175** | *0.167* |
| C | 0.25 | 0.5 | 0.625 | **0.139** | *0.277* | **0.139** | *0.133* |
| D | 0.25 | 0.5 | 0.596 | **0.116** | *0.239* | **0.116** | *0.110* |

**Table 3 — the collateral gate (v), sized on the 2,280 fixtures / 212 blocks /
6 seasons of the committed collateral structure, same construction.** (v-a) is a
**point screen** (§4.4): it fires on the observed estimate alone and needs no
power, and its operating characteristics are in the last two columns. (v-b) is
the clause that can refuse a *resolvable* harm, evaluated under §4.1's amended
lower-bound-only form.

| scenario | ρ_s | ρ_w | P((v-b) fires) at a true effect of +0.000075 | (v-b)'s harm MDE80 | benefit-resolution MDE80 (for the record) | *(v-a) passes at true 0* | *(v-a) passes at true +0.001* |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 0.00 | 0.0 | 0.034 (0.004) | +0.001378 | −0.001342 | *0.569* | *0.030* |
| B | 0.00 | 0.0 | 0.031 (0.004) | +0.001756 | −0.001705 | *0.559* | *0.074* |
| C | 0.00 | 0.0 | 0.029 (0.004) | +0.002489 | −0.002404 | *0.544* | *0.158* |
| D | 0.00 | 0.0 | 0.028 (0.004) | +0.003505 | −0.003398 | *0.533* | *0.252* |
| A | 0.00 | 0.5 | 0.024 (0.003) | +0.003475 | −0.003396 | *0.530* | *0.237* |
| B | 0.00 | 0.5 | 0.022 (0.003) | +0.004415 | −0.004306 | *0.524* | *0.285* |
| C | 0.00 | 0.5 | 0.022 (0.003) | +0.006247 | −0.006104 | *0.517* | *0.346* |
| D | 0.00 | 0.5 | 0.021 (0.003) | +0.008829 | −0.008624 | *0.514* | *0.390* |
| A | 0.25 | 0.5 | 0.303 (0.010) | +0.006736 | −0.007017 | *0.514* | *0.443* |
| B | 0.25 | 0.5 | 0.302 (0.010) | +0.008589 | −0.008895 | *0.512* | *0.458* |
| C | 0.25 | 0.5 | 0.301 (0.010) | +0.012120 | −0.012611 | *0.509* | *0.469* |
| D | 0.25 | 0.5 | 0.300 (0.010) | +0.017180 | −0.017818 | *0.509* | *0.481* |

**A structural fact, so no one reads the tables as a defect in the simulation.**
Gate (i) is a threshold **at** the bar, not a test against zero, so at a true
effect exactly equal to the bar the probability of clearing it is about one half
whatever the variance is — measured, 0.504–0.515 across the regimes. **An
80%-power MDE equal to the bar is unattainable by construction**, at any SD; the
honest quantity is the ratio, which is what the tables report. The same structural
fact governs (v-a) at its own margin, which is why §4.4 calls it a screen.

**A second structural fact, and it is the one that changed under the refounding.**
In **every** row of Table 2 the `{i, iii}` joint equals gate (iii)'s own pass rate
to three decimals. That is not a coincidence: gate (iii) demands
`mu_rps < −s·hi_season(ε)` while gate (i) demands `mu_rps ≤ −0.0010 − s·mean(ε)`,
and with six season blocks the gap `hi_season(ε) − mean(ε)` is an order of
magnitude larger than `0.0010/s` at every scenario SD — so **gate (iii) implies
gate (i), always, in this design.** §6.4 draws the consequence.

### 6.4 THE RULING — what `n` buys, what the refounding bought, and what neither can

**Nothing in §4 moves after this section.** The bar stays −0.0010, the deciding
set stays {(i), (iii), (iv), (v)}, the population stays the pinned 85,
`delta_rating` stays −75.0, γ stays 0.5, `n_sims` stays 20,000. What changes is
that this document says, before any delta exists:

> **THIS DESIGN REMAINS UNDERPOWERED AGAINST THE VERY EFFECT ITS PREDECESSOR
> MEASURED, EVEN AFTER THE REFOUNDING.** At `mu_rps = −0.00413` — the widening
> run's own point estimate on this same population — the two deciding benefit
> gates jointly pass with probability **0.14 to 0.49** across scenarios A–C and
> the three correlation regimes — **0.12 to 0.20** at the illustrative D
> endpoint. The joint MDE80 is **1.61× to beyond 4.84× that effect.** A miss is
> therefore substantially uninformative: **"no adoption" here means "not detected
> at this power", not "no effect", and the result document must say so in those
> words.** And because §6's figures exclude gates
> (iv) and (v), **actual four-gate adoption power is lower still.**

**WHAT THE REFOUNDING BOUGHT, MEASURED RATHER THAN ASSERTED.** Table 2's last two
columns are the price of v1's five-gate rule and the value of §4.0's four-gate
one, at `−0.00413`:

| regime | v1's {i, ii, iii} | v2's {i, iii} | gained |
|---|---:|---:|---:|
| ρ_s 0.00, ρ_w 0.0 | 0.095 – 0.369 | **0.203 – 0.494** | +0.108 – +0.128 |
| ρ_s 0.00, ρ_w 0.5 | 0.079 – 0.274 | **0.171 – 0.436** | +0.092 – +0.162 |
| ρ_s 0.25, ρ_w 0.5 | 0.110 – 0.207 | **0.116 – 0.216** | +0.006 – +0.009 |

**The demotion is worth roughly nine to sixteen points of power where season
correlation is absent, and almost nothing where it is strong** — because in that
regime gate (iii), the gate that now decides, becomes the binding constraint by
itself. The refounding removed a gate that was measuring the calendar; it did not
turn an underpowered design into a powered one, and this document does not claim
it did.

**GATE (iii), THE SEASON INTERVAL, IS NOW THE BINDING GATE — and §6.3's second
structural fact says it is the *only* binding gate.** Because gate (iii) implies
gate (i) at every scenario SD in this design, the deciding pair's joint power
**is** gate (iii)'s pass probability: **0.139 to 0.494 at `−0.00413`** and
**0.083 to 0.139 at the bar**, over scenarios A–C (0.116 and 0.078 respectively
at the D endpoint). Three consequences, all stated before the run:

1. **Six blocks is the whole constraint.** The season interval resamples six
   blocks, one of which (2019/20) holds 26 of the 85 fixtures. Its effective
   sample size is the block count, and the block count is a property of the
   corpus window, not of how many fits are run.
2. **Season-level correlation is what would break it**, and the third regime
   prices that: at `ρ_season = 0.25` the deciding pair's power at `−0.00413`
   falls to **0.116–0.216** whatever the scenario. v1 did not model season
   correlation at all; under a deciding season interval that omission would have
   been the largest unstated risk in the document.
3. **The demoted week interval is not uniformly weaker.** At `ρ_season = 0.25` it
   passes *more* often than the season interval does (0.239–0.388 against
   0.116–0.216), because 62 blocks absorb a season-level shock that 6 blocks
   cannot. That is disclosed rather than buried: the refounding is a ruling about
   which gate measures the model rather than the design, and it is **not** a
   claim that the season interval dominates the week interval everywhere.

**This design is WORSE powered on the primary than its predecessor was**, and the
reason must be stated rather than discovered. The predecessor's 85 rows included
33 exact structural zeros with zero variance; here **every row carries the noise
of two independent fits.** More data in the training set does not become more
data in the estimand. §1.4 named the loss; this is its price in power.

**What more `n` CANNOT buy.** Nothing on the primary. The population is pinned by
§0.5 and cannot be enlarged: enlarging it under the E1 archive empties it, and
enlarging it under any other rule abandons the comparability with −0.00413 that
is this experiment's entire reason to exist. **A design that bought power by
moving its population would be answering a different question and calling it this
one.**

**What more `n` CAN buy, and it is exactly one thing.** All 2,280 corpus fixtures
now move, so there is a genuine second population with 212 blocks instead of 62 —
26.8× the fixtures and 3.4× the blocks. §6.3's Table 3 sizes it: the
collateral leg resolves a harm of **+0.00138 to +0.00351** at `ρ_s = 0, ρ_w = 0`,
**+0.00348 to +0.00883** at `ρ_s = 0, ρ_w = 0.5`, and **+0.00674 to +0.01718**
under season correlation. That is enough to refuse a *resolvable* corpus-level
harm and is **not** enough to demonstrate a corpus-level benefit at the scale a
thin-fixture effect of −0.00413 implies (`−0.00413 × 85/2280 = −0.000154`, nine
to over a hundred times below what the leg can resolve). **That asymmetry is why
gate (v) is written as a do-no-harm gate and not as a benefit gate**, and why the
212 openings are fitted at a cost of nine extra hours: they buy the ability to
refuse, the maximal identity control of §3.2, and nothing else. The one thing
they conspicuously do **not** buy is the answer to the primary question.

**This is not a licence to re-run.** §4.5's refusal to re-litigate a miss is
unchanged. §6 is the reader's warning, frozen in advance, so the size of the null
cannot be argued about after it arrives.

### 6.5 The realised-SD obligation, on the result document

After the run, the **realised paired SD of the 85 differences and of the 2,280
differences** is reported, and **the deciding-pair MDE is recomputed at the
realised thin-population SD** — the §6.2 construction re-run with `scenario_sd`
set to the realised value, at the same `R`, the same seeds, the same three
regimes, the same grid and the same interpolation rule, producing realised
`power@bar`, realised `power@−0.00413`, realised `MDE80` and realised ratios in
the same columns as §6.3's Table 1, plus the realised gate-(ii) diagnostic column
of Table 2 and the realised (v-b) harm MDE of Table 3 (which §4.4's required
sentence quotes).

**If the realised SD exceeds scenario D**, the result document states
`OUT_OF_POWER_ENVELOPE` per §6.1 and says that §6.3's tabulated range is an
upper bound on the power that actually obtained.

This is an obligation on the **result document** and on
`reports/evidence/lowerdiv.json`'s `power.realised` object, not on the pre-freeze
harness, because the realised SD does not exist until the fits do. It is a
distinct quantity from the two-sided-test-against-zero MDE, which is not what
gate (i) is; a result document that reports the latter beside the realised SD has
not discharged this obligation.

**The realised numbers decide nothing and no threshold moves in response.**

---

## 7. Refusal semantics for the run

### 7.1 Typed refusals, by name

All derive from **`LowerDivError`**, caught by `main()`, printing `STOP: …` with
the type and offending key, exit **2** — the `RecalError` convention.

| type | fires when |
|---|---|
| `CorpusMissing` / `CorpusDigestMismatch` / `CorpusShapeMismatch` | the pinned corpus parquet is absent / not `f31580073e…` / not 2,280 rows, 6 seasons, 212 blocks, `y` (993, 525, 762) |
| `ArchiveDigestMismatch` | `data/epl/matches.parquet` is not `323aa54af0…` or not 4,560 rows |
| `E1ArchiveDigestMismatch` | `data/epl/matches_e1.parquet` is absent, or its digest / row count / per-season club census differs from the freeze block's pins |
| `LedgerDigestMismatch` | `data/epl/fit/walkforward_ledger.jsonl` is not `869a558ce7…` or not 212 rows |
| `ConfigNotFrozen` | `epl/config_frozen.json` is not `9f2e086d…`, seed ≠ 20260611, widening ≠ `{mechanism: c, strength: 0.5}`, or `realised_config_sha256` ≠ `78a51cd92c…` |
| **`E1Leak`** | an E1 `match_id` appears in the E0 archive, the E0 store root, any frame passed to `epl.elo`, or any frame passed to `effective_evidence`; or the E0 archive's bytes moved; or an E1 fixture appears in any estimand, gate, `probs` field or table |
| **`PopulationRederived`** | the thin set is derived from anything but `reports/evidence/widening_per_fixture.csv`; or it is joined on any column but `match_id`, or the join does not produce exactly 85 rows one-to-one; or `e` is computed on a frame that is not the pinned E0 archive; or the recomputed 85-`match_id` digest differs from widening v3's frozen `38d18d4d96…` |
| **`PhantomClub`** | any row reaching the store builder carries a null `home_key` or `away_key` — the refusal names the season, date and raw spelling and **precedes** the projection (§0.6 B5) |
| **`RegistryCollision`** | an E1 spelling's index fold collides with a registered one (raised by `epl/teams.py:109-121` at import), or re-resolving the pinned E0 archive through the enlarged registry changes any E0 key |
| **`LadderBoundaryMismatch`** | an E1 season-boundary arrival cannot be classified `from_E0` / `outside_observed_divisions` / `continuing` by §2.2 point 3; or a club appears in both divisions in one season; or the recomputed `from_E0` set differs from `E0(prev) − E0(this)` on the pinned E0 archive; or §2.2 point 2b's source-ladder resolver is asked for a club with no played match in either archive before the cutoff, or resolves a club through more than one branch |
| **`AcquisitionIncomplete`** | a season's E1 CSV is absent, fails its recorded digest, fails the (24, 552, 23) validation, or leaves an unmapped spelling at A1; or A0's census is absent when A1 runs; or A0 is run a second time |
| **`BudgetExceeded`** | §2.4's overrun ruling fires — Step 2's realised Arm-A fit rate exceeds **269 s/fit**, so the projected total exceeds the 30-hour bound. The refusal publishes the measured rate, the projection and a `complete: false` marker **before** it stops, and the run is neither thinned nor restarted |
| `MembershipMismatch` | a recomputed enumeration differs from §8.3's frozen digests — the 85 `match_id`s, the 62 blocks, the 6-season split, the 212 openings, `FROZEN_TABLE_SCHEDULE` triplet-by-triplet, or the per-label CELL census; or the thin set's join on the corpus does not produce exactly 85 rows one-to-one `{MW0:5, MW3:6, MW6:7, MW10:7, MW19:7}` |
| `PredicateMismatch` | an Arm-B fit's own provisional set ≠ the ledger's recorded `provisional_teams` at that cutoff |
| `EvidenceLeak` | a match dated ≥ its cutoff contributes to any `e(t, C)` |
| `CutoffLeak` | a training frame holds a match dated ≥ its cutoff, or a fixture appears in the fit that prices it — checked on **both** store roots |
| `CanaryFailed` / `EvidenceCanaryFailed` | `epl.lowerdiv.point_in_time_canary_2` (§7.3) fails on either store, or the direction canary proved nothing (§7.3) / either leg of the evidence canary fails |
| `ControlMismatch` | any of the 2,280 identity-control probabilities differs from the corpus at 8 dp (§3.2) |
| `TableIdentityBreak` | **any** cell's two arms' `sampler_digest`s are EQUAL (§3.3: every cell must change under this design); a parity comparison differs at any of the 32 cells; a cell simulated without a complete oracle; or a schedule field disagrees with `FROZEN_TABLE_SCHEDULE` |
| `TableMCImprecise` | §5.2's structural conditions — unequal per-particle season counts, unequal `n_particles` across deciding cells or between a cell's arms, a tally that fails either binding check of §5.1, or a tally file absent or failing its recorded digest |
| `FitFailed` / `UnpriceableFixture` / `ScoreMismatch` | as the predecessors define them, verbatim |
| `SchemaMismatch` / `RowConflict` | a ledger row lacks a required field / duplicate keys disagree on a non-volatile field |
| `ShardFailed` / `MergeIncomplete` | a shard exits non-zero or writes nothing / the merged key set is not exactly the pre-stated keys — not a superset, not a subset |
| `StoreNotBuilt` | a read-only pass required a point-in-time store and the store parquet is absent; the read-only accessor refuses and **never builds one** (§8.2) |
| `SequenceViolation` | a step of §8.4's frozen sequence ran without its predecessor's completion marker, or with a marker recorded under a different freeze-parent commit |
| `FreezeStateUnverified` | the freeze/first-fit state could not be established from committed bytes and Git ancestry: the prereg blob is uncommitted, its commit is not an ancestor of HEAD, or its current bytes differ from that blob; a hashed file's bytes differ from the committed table; **any member of §8.6's DEPENDENCY HASH TABLE differs from its recorded SHA-256, or the table's path set differs from a fresh recomputation of the import closure**; **the environment fingerprint differs from the one the freeze block recorded**; the recorded membership, schema or conformance digests do not match a fresh recomputation; the committed conformance table is not exactly §8.5's rows all green; a first-fit record names a different prereg blob; or the record and its append-only witness disagree |
| `FeasibilityRecordMismatch` | the committed census record is absent, fails its pinned digest, reports `completed: false`, or reports a priceable census that is not exactly these 32 cells |
| **`PathNotFrozen`** | any writer or reader resolves an artifact path that is not the one §8.9's single layout function returns (§8.9) |

**Thirty-five named refusals; thirty-six classes** counting the `LowerDivError`
base they all derive from. (`RecalError` above is a citation to the exit-code
convention, not a class of this harness.) `epl/tests/test_lowerdiv.py`'s two
inventory tests must name **thirty-five** in both their tuple and their set, so
that the "invents no refusal the document never wrote" test closes the inventory
exactly and a thirty-sixth named type is as much a failure as a missing one.

**UNRESOLVED is not a refusal and raises nothing.** Gate (iv) being left
UNRESOLVED by §5.4's precision rule is a **verdict**: it publishes, and it blocks
adoption.

A failed fit poisons its shard, a failed shard poisons the merge, shards are
waited on per PID, and a partial ledger is never scored. The merge refuses rows
stamped `harness_frozen: false`, by name — the predecessors' back-dating guard,
kept.

### 7.2 Provenance and resumability

Every match-leg row records `cutoff` · `arm` · `seed` · `config_sha256` ·
`realised_config_sha256` · `archive_sha256` · `archive_e1_sha256` ·
`ledger_sha256` · **`store_sha256` · `anchor_sha256` · `team_index_sha256`**
(§3.2) · `delta_rating` (−75.0) · `gamma` · per-club `e` on the E0 archive at
8 dp · **per-club prior-E1 match count and last prior E1 date** (§3.1 — never an
`e`) · incumbent and recomputed provisional sets · cold-start set · team-index
size · `match_ids` · `probs` (8 dp) · `health` · `harness_sha256` ·
**`dependency_table_sha256`** · **`environment_fingerprint`** (§8.6) ·
`harness_frozen` · `blas_threads` · `shard_id` · clocks.

Every **table** row additionally records `provisional_control`,
`provisional_treatment`, `effective_posterior_control`,
`effective_posterior_treatment`, `sampler_digest_control`,
`sampler_digest_treatment`, `substantive_digest_control`,
`substantive_digest_treatment`, `parity_digest_simretro`, and **the SHA-256 of
its own tally file**.

Volatile fields (`wall_seconds`, `fit_seconds`, `seconds`, `shard_id`,
`started_at`, `host`) are excluded from the canonical form; `run_digest` is
SHA-256 over the canonical form; a resumed run's digest must equal an
uninterrupted run's byte for byte; the loader refuses disagreeing duplicates. The
runner is resumable per fit, keyed
**`cutoff|arm|seed|config_sha256|store_sha256|anchor_sha256|team_index_sha256`**
— §3.2's content binding, because a key that names only the config lets a moved
store resume into a completed run.

`harness_frozen` records **what the guard established**, never what a caller
asserted (§8.6).

### 7.3 The canaries

* **Results canary, TWICE — and it is THIS DOCUMENT'S canary, not the protected
  one.** v1 required "`point_in_time_canary` on the E0 store … and on the
  E1-informed store". **That function cannot do it.** Its signature is
  `point_in_time_canary(matches=None, cutoff="2022-01-01", later="2023-01-01",
  tmp_root=None)` (`epl/walkforward.py:450-451`): it accepts **neither a store
  nor an anchor**, it constructs the incumbent E0 `Anchor` from the `matches`
  frame it is handed (`:468`), and it projects its temporary stores through
  `epl.fit.to_store_frame` (`:470`), which labels every row Premier League.
  Handing it the union frame would leak E1 into the incumbent Elo ladder — the
  one thing §0.1's architectural pin exists to prevent — and handing it the E0
  frame cannot exercise the treatment store at all.

  **The ruling:** `epl.lowerdiv.point_in_time_canary_2(store_root, anchor,
  cutoff, later)` is a lowerdiv-owned canary taking the store root and the anchor
  **explicitly**, reproducing the protected function's structure step for step —
  rewrite every result from `cutoff` on, demand the forecast is unmoved, and
  prove at `later` that the corruption landed — with two substitutions and no
  others: the store it corrupts is the one it is given, and the anchor it fits
  against is the one it is given. `epl/walkforward.py` is **not edited**; the
  protected function is cited as the structure's source and is not called on any
  deciding path. It is run once with `(E0 store root, incumbent Anchor)` and once
  with `(E1-informed store root, §2.2's CrossLeagueAnchor)`. `PASS: false` on
  either stops the run. Each performs four real fits, which is why §8.4 makes it
  step 1 and why §2.4 counts eight fits. Its temporary stores live under
  `tempfile.TemporaryDirectory` and never under either preregistered store root.
* **Evidence canary**, two-legged, on the **E0** archive, because that is the
  archive `e` is computed on. The mutation is frozen exactly. Rows selected by
  normalised date: `after` selects `date ≥ cutoff`, `before` selects
  `date < cutoff`. For the i-th selected row, 0-based in frame order:
  `home_key := "__canary_corrupt__h{i}"`, `away_key := "__canary_corrupt__a{i}"`,
  `fthg := 9`, `ftag := 9`; **dates are not touched.** Per-row unique sentinels
  are required, not decorative: `wcmodel.data.features`' duplicate-match dedup
  collapses content-identical rows, and a shared sentinel deleted the rows it
  meant to rewrite. *Negative leg:* the `e` vector compared with
  `numpy.array_equal` on the float64 values **before rounding** — bit equality,
  not a tolerance. *Positive control:* `max_t |e_corrupt − e_clean| > 1e-9`, with
  the realised value recorded. *Both legs* record the row count the mask
  selected; an empty mask is a refusal, never a pass.
* **The E1-isolation canary — new, and it is the canary this design most needs.**
  Corrupt every row of the E1 archive by the same sentinel recipe, rebuild
  **only** the E1-informed store, and assert: (a) the E0-only Arm-B forecast at a
  named cutoff is **bit-identical** to its clean value; (b) the `e` vector on the
  E0 archive is bit-identical; (c) the Elo anchor's ratings and division mean at
  that cutoff are bit-identical; and (d) — the positive control — the **Arm-A**
  forecast at the same cutoff moves by `max |Δp| > 1e-9`. A canary in which (d)
  does not fire proved nothing and is `CanaryFailed`: it would mean the E1 rows
  never reached the likelihood at all.
* **Identity canary.** An E1-informed store built from an **empty** E1 frame must
  yield `np.array_equal` with the corpus rows at the same cutoff.
* **Seeded defects.** The adversarial audit seeds each defect class of §7.1
  alone and demands red under the harness's own tests — on synthetic corpora
  only, as §7.4 defines synthetic.

### 7.4 "Synthetic" has an enforceable definition

A corpus, archive or ledger is **SYNTHETIC** iff every one of its values is
written literally in `epl/tests/test_lowerdiv.py`, or generated there by
arithmetic over literals written there. **No value may be read, copied, sampled,
transformed, or otherwise derived from** `data/epl/matches.parquet`,
`data/epl/matches_e1.parquet`,
`data/epl/fit/walkforward_predictions.parquet`,
`data/epl/fit/walkforward_ledger.jsonl`, `data/epl/sim/retro_r1.jsonl`,
`reports/evidence/widening_per_fixture.csv`,
`reports/evidence/anchoring_per_fixture.csv`, `reports/evidence/lowerdiv_corpus.csv`,
`reports/evidence/lowerdiv_openings.jsonl`, or any artifact derived from them.

**The ancestry check is a mechanical obligation, not an assertion.** Before the
seal commit, `epl/tests/test_lowerdiv.py` must carry a test that asserts,
mechanically, that none of its invented club names appears in any pinned
artifact's club columns and that its generators read nothing from those
artifacts. Until that test exists and passes, the claim is an assertion about the
code and not a check on it, and the freeze block may not be rendered. The test
module's own inventory of generators and invented names is stated in the freeze
block by count and by name, so a later reader can check the claim against the
file.

The `@pinned` tests are **not** synthetic. They read the pinned artifacts
deliberately, to re-derive this document's census; they fit nothing and simulate
nothing, and they are authorised under §8.2.

---

## 8. The lifecycle

### 8.1 Where this sits, and what precedes it

**The house lifecycle, and this commit's place in it:** preregistration committed
**before** any harness code → cross-model design review → harness TDD → dual
audit (one cross-model review, one in-tree adversarial seed audit) → freeze →
run → publish either way. **This commit is step one.** No harness exists, and
§8.3 forbids a freeze block until every later step has happened.

**The queue.** The owner-pinned EPL standing queue puts the anchoring verdict,
the anchored arm, automation + the live-cycle cadence switch, A11+FPL capture
and the injury shadow arm **ahead** of the widening/decay work this document
belongs to. This document is the widening successor and is **queued behind them,
not ahead of them.** Preregistering it now costs no compute and no lock
exposure — this commit adds one file and touches nothing — and it exists now
because widening v3 §10
requires a new preregistration before any successor work, and because the
acquisition pass of §8.2 has a long lead time. **Executing it is a separate
owner decision and this document does not schedule itself.**

**The lock.** Options (a) and (c) need **zero bytes under `src/` or `scripts/`**,
so the lock chain is untouched and **no lock-v11 is required.** Every file this
experiment writes is under `epl/`, `data/` or `reports/`.
`PYTHONPATH=src scripts/oa_lock.py` must print `LOCK VALID` after every commit
this work produces, checked and not assumed — nothing polls the chain, and any
`src/` or `scripts/` commit breaks it silently until the next lock version.

**No fit of this document has ever run**, and no artifact of it exists. That
attestation is restated in §8.8 with the qualifications it carries.

### 8.2 The pre-freeze regime — read-only to the model, enumerated, and mechanically closed

**The no-fit clock.** Between this commit and the seal commit, **no fit and no
season simulation of this document may run, anywhere, under any output
directory.** §10 makes one an invalidation. The two named passes below are not
exceptions to that rule: A0 and A1 acquire data and fit nothing.

**The authorised passes, authorised prospectively and by name. There are seven.**

> **Pass A0 — FETCH AND CENSUS.** The only pass that touches the network.
> `python -m epl.lowerdiv --acquire-fetch`. It fetches the twelve E1 season CSVs
> (cache-first, hash-pinned, refusing a byte change on a cached file) and writes
> exactly `data/epl/raw/E1_{code}.csv` (12) and
> `data/epl/raw/provenance_e1.json`. It publishes the **outcome-blind spelling
> census** of §0.6 and **reads no score column**. It resolves no name, writes no
> parquet and builds nothing. **It runs ONCE**, with a terminal completion
> marker.
>
> **THE REGISTRY COMMIT — not a pass, a commit.** `epl/teams.py` gains one entry
> per E1 club, written against A0's published census. §10 makes writing a
> registry entry before that census is published an invalidation, and makes
> resolving a fold collision by renaming a club an invalidation.
>
> **Pass A1 — PARSE, RESOLVE, VALIDATE, WRITE.** No network.
> `python -m epl.lowerdiv --acquire-build`. It re-reads the cached CSVs,
> re-verifies each against A0's recorded digest, parses under §0.6's B6 recipe,
> resolves under B4, validates under B3, refuses under B5, and writes exactly
> `data/epl/matches_e1.parquet`, `data/epl/manifest_e1.json` and
> `data/epl/team_name_mapping_e1.json`. **It may be re-run** after a registry
> correction, because it fetches nothing and conditions on nothing but a spelling;
> every run appends to its claim record and the completion marker carries the list
> forward.
>
> **BOTH ARE READ-ONLY TO THE MODEL.** Neither builds a store, constructs an
> Engine, imports a sampler, or calls anything in `src/wcmodel/model/`. A
> committed test asserts that both acquisition paths' import closures exclude
> `wcmodel.model.scoreline`, and each pass compares the E0 archive's bytes and
> mtime before and after and refuses if either moved.
>
> **The acquisition record publishes as a dated §8.10 note appended to this
> document before the freeze block**, carrying exactly §0.6's allow-list and
> nothing else — **no goal rate and no outcome summary of any kind.** A freeze
> block may not render while that note is absent, and refuses if the note carries
> a field outside the allow-list (§8.3).

* `python -m epl.lowerdiv --membership` and `--plan` — read the pinned corpus,
  the pinned E0 archive, the ledger, the committed widening per-fixture CSV, the
  committed collateral structure CSV and the acquired E1 archive; compute the 85
  `match_id`s, the 62 blocks, the 6-season split, the 212 openings,
  `FROZEN_TABLE_SCHEDULE` and the per-label CELL census, and the digests §8.3
  pins. **Neither reaches a store build:** the read-only store accessor opens an
  existing store parquet and raises `StoreNotBuilt` if it is absent — it never
  builds one.
* `python -m epl.lowerdiv --canary --no-results-canary` — §7.3's evidence and
  E1-isolation canaries, with every point-in-time store built inside a
  `tempfile.TemporaryDirectory` the pass creates for itself and never under
  `paths.STORE_DIR` or the E1 store root. **It takes no directory argument**
  (§8.9 rule 3): a caller-supplied scratch path is the same seam as a
  caller-supplied ledger path, and this document refuses both.
* `pytest epl/tests/test_lowerdiv.py` — the synthetic corpora, the `@pinned`
  tests that re-derive this document's census, the power table, the membership
  and the table schedule, and §8.5's conformance scenario run.
* `python -m epl.lowerdiv --power` — derives scenarios C and D from B, recomputes
  the frozen structure from the two committed CSVs, and must reproduce §6.3's
  three tables exactly.
* `python -m epl.lowerdiv --freeze-block` — reads the pinned artifacts to render
  §8.3's block rather than have a human transcribe digests.

**`--script` may not be run before the seal commit, at any target**, and a
post-freeze launcher may not be generated with a caller-supplied interpreter or
command.

### 8.3 The freeze block, and the order that produces it

This document is committed **before** the harness it binds. Then, in order:

1. **The acquisition surface is written and audited** (§2.1): stage 1 of
   `epl/lowerdiv.py` and its tests, committed. **A0's command cannot run before
   the module that implements it exists**, and v1's order — "pass A runs … then
   the harness is written" — was not executable.
2. **A0 runs and publishes its outcome-blind census** (§8.2). No census, no
   registry commit before it.
3. **The registry commit** — `epl/teams.py`, written against A0's census.
4. **A1 runs and publishes the acquisition note** (§8.2, §8.10). No E1 archive,
   no freeze.
5. **The experiment surfaces are written and audited** — stage 2 of
   `epl/lowerdiv.py` and `epl/tests/test_lowerdiv.py` are brought to implement
   **this document**, with seeded defects and canaries on synthetic corpora only.
   §8.5's conformance report must be green on behavioural predicates **and must
   be backed by an independent pytest artifact**, and an independent dual audit —
   one cross-model review and one in-tree adversarial seed audit — must report no
   blocking finding, **or the owner must adjudicate what it reported**, with the
   complete dissent published beside the law.
6. **The reproduction bundle of §9.5 is generated and committed.**
7. **THE SEAL COMMIT appends the freeze block to this document**, rendered by
   `--freeze-block`, carrying:

   * the **FREEZE-PARENT COMMIT** — the SHA-1 of the commit at step 6, which
     holds the audited harness, the registry, the bundle and this document
     *without* the freeze block. **The block names its parent, never itself.**
     v1 required a marker to equal "the freeze commit recorded in this document's
     committed freeze block" while that block lived *in* the commit it named:
     a Git commit cannot contain its own SHA, because embedding it changes it,
     and no construction resolves the self-reference. The freeze-parent is
     immutable, already exists when the block renders, and gives every property
     the self-reference was reaching for (§8.4);
   * the **harness hash table** — file, line count and SHA-256 for each of
     `epl/lowerdiv.py` and `epl/tests/test_lowerdiv.py`, the SHA-256 of
     `epl/teams.py` after B4's registry addition, and the schema identifier
     `epl-lowerdiv-2`;
   * the **DEPENDENCY HASH TABLE and the ENVIRONMENT FINGERPRINT** of §8.6 —
     because ancestry alone does not bind the code that decides;
   * the **membership digests** — the 85 thin-fixture **`match_id`s**, the 62
     block labels, the 6-season split, the 212 fit openings,
     `FROZEN_TABLE_SCHEDULE` triplet by triplet, the per-label CELL census, and
     the three excluded cell keys — each serialised canonically and hashed,
     recomputed by the harness's own code from the pinned artifacts —
     **together with widening v3's own frozen thin-fixture digest
     `38d18d4d96…`, which the recomputed 85 `match_id`s must equal**, and
     **together with the 85-`key` digest `5a0d92c5…` recorded as the value the
     pin is NOT** (§0.5);
   * the pinned artifact digests of §0.1 including the committed collateral
     structure CSV, `realised_config_sha256`, and **the E1 archive's SHA-256, row
     count, byte size and per-season club census**;
   * the SHA-256 and byte size of the feasibility census record, and **both
     paths that hold those bytes**;
   * the SHA-256 and byte size of every member of §9.5's reproduction bundle;
   * the **enumeration of every pre-freeze pass actually run**, complete,
     including A0 and every A1 attempt with dates, records and digests;
   * the conformance report of §8.5, every row green, **together with the
     identity of the pytest artifact it was read from** — path, digest, test-id
     list and pass count;
   * §6.3's three tables as the committed `--power` reproduced them.

   *If any hash differs at the time the run is executed, it is not the run this
   document preregisters.*

   **`--freeze-block` refuses to render** while any of the following holds, and
   the refusals are unconditional — there is no bypass parameter and no
   caller-supplied substitute for any of these inputs:

   * A0's or A1's dated note is absent from this document, or the E1 archive is
     absent or fails the digest the note recorded;
   * **the §8.10 note carries any field outside §0.6's allow-list** — in
     particular any score, goal count, goal rate, result distribution or other
     outcome summary of the treatment data (§0.6);
   * the conformance report is **not exactly §8.5's rows**, or any row is red or
     absent. **A nonempty all-green SUBSET is a refusal**, not a pass: a renderer
     that accepted any green subset would render over a report that had dropped
     the rows it could not satisfy, and a review found that exact acceptance in
     the predecessor's harness;
   * the report was not **produced by and cross-checked against** §8.5's
     committed pytest artifact — same test ids, all passing, same count;
   * §7.4's ancestry test is absent, or §6.3's three tables are unreproduced;
   * the feasibility census record is absent, fails its pinned digest, says it
     did not complete, or reports a priceable census that is not exactly these
     32 cells;
   * **§9.5's reproduction bundle is absent or fails any of its digests**;
   * the recomputed 85-`match_id` digest is not equal to widening v3's
     `38d18d4d96…`, **or the harness's regression test showing that the 85-`key`
     digest is `5a0d92c5…` and is NOT the pin is absent** (§0.5);
   * the dependency hash table or the environment fingerprint is absent, or
     either fails a fresh recomputation.

8. **Only then does the first real fit of this document run**, and it runs as
   step 1 of §8.4's sequence and in no other way.

**This document's commit adds this document. Nothing else.** No amendment-ledger
cross-reference is appended: `reports/epl_sim_amendments.md` is append-only under
standing protection, its numbered entries mark changes to what a published
surface or frozen rule means, and a research preregistration that touches nothing
shipped binds by its own commit. If this experiment adopts, the adoption ruling
is the numbered entry.

### 8.4 The frozen post-freeze sequence, with completion markers

Six steps, in this order, and **nothing else may run on the real archives between
them.** Each step **refuses unless its predecessor's completion marker exists**;
the refusal is `SequenceViolation`.

Markers live at one fixed location, `data/epl/fit/lowerdiv/sequence/`, one JSON
file per step. Each records the step name, whether the step **completed**, the
UTC time, the **freeze-parent commit** under which it was written, the harness
file digests at that moment, and — per the predecessor's adjudicated fix —
**`products`, a map from repo-relative path to the SHA-256 of what that file held
when the step finished.** `assert_sequence_marker_wellformed` **re-hashes every product against
the bytes on disk on every read**: a marker is a claim that a step produced
something, and a claim about a file that is gone, or is no longer that file,
unlocks nothing. A marker written under a different freeze-parent commit is not a marker
for this run.

**Markers are written once.** They are MANIFEST members (§9.3), so a second write
under the same freeze-parent commit **re-verifies**: it compares what the step produced
against what the marker records, returns the marker unchanged if they agree, and
refuses if they do not.

> **A MARKER IS CHECKED AGAINST THE FREEZE COMMIT, NOT AGAINST HEAD — the fourth
> harness defect the predecessor's run disclosed, and it disclosed it by going
> red.** `epl/evwiden.py:4328-4335` compares a marker's `freeze_commit` against
> `git_head()` and refuses unless they are **equal**. HEAD necessarily advances
> after the run: §8.4's own step 6 commits the result document and the evidence
> files, and the predecessor did exactly that at `f3bc756`. **From that commit
> onward every sequence-guarded path in that harness raised
> `SequenceViolation`, and `pytest epl/tests` carried 59 failures and 9 errors
> across 66 distinct tests that no one introduced** — the ratchet firing on the
> publication it was built to permit. The refusal, measured at HEAD `40eed13`:
> *"step5_parity refuses: step4_merge's marker was written under a different
> freeze commit (38be3e2d4c65… against 40eed1398637…)."*
>
> **THE REDNESS IS GONE AND THE DEFECT IS NOT, and the distinction is the whole
> reason this clause exists.** At `6ed2ba5` the suite was returned to green by
> **retiring those 66 tests to `skipif` behind a `RUN_CONCLUDED` stage guard** —
> the concluded run's own markers asked read-only — so the baseline is now
> `1359 passed, 67 skipped, 0 failed`. **`epl/evwiden.py` was not touched**: it
> is byte-identical to what that document's freeze block hashes, the equality
> check at `:4328-4335` is still exactly the code quoted above, and it would
> refuse again on the next publication of any run it guarded. The cure was in the
> test file because the harness was frozen and concluded; **it was not a fix, and
> a design that inherited this shape would inherit the defect and not the cure.**
>
> **The rule here is different and it is birth-law.** A marker's `freeze_parent`
> must equal **the FREEZE-PARENT COMMIT recorded in this document's committed
> freeze block** (§8.3) — one fixed value, naming the commit that holds the
> audited harness *before* the block was appended, established once by §8.6's
> guard from committed bytes and Git ancestry — **and that commit must be an
> ANCESTOR of HEAD, never equal to it.** Every property the equality check was
> reaching for survives: a marker from a different freeze does not unlock
> anything, a marker written before the freeze does not unlock anything, and no
> caller may supply the value. What does not survive is a harness that goes red
> the moment it publishes, which is not integrity — it is a guard that cannot
> tell publication from tampering.
>
> **And the value is the PARENT'S, not the seal's, because a commit cannot name
> itself.** v1 wrote "the freeze commit recorded in this document's committed
> freeze block" — a SHA embedded in the very object it identifies, which changes
> the moment it is written. The freeze-parent already exists when the block
> renders, is immutable, and is an ancestor of the seal commit and therefore of
> HEAD. **The seal commit is identified only by what it contains**: §8.6's guard
> establishes it by finding this document's current bytes in a committed blob
> whose commit is an ancestor of HEAD, which needs no embedded identity at all.

**`epl/evwiden.py` is protected and frozen and is NOT repaired by this
document.** The predecessor's redness is disclosed here, with both its measured
HEAD and the commit that skipped it away, because §8.9's discipline is to name a
defect where it lives and design it out here rather than to inherit its shape
silently — and because a green suite is not evidence that the guard was fixed.

**A marker may record a FAILURE, and a failure marker unlocks nothing.** A step
that ran and failed writes `complete: false`, and the step it would have unlocked
refuses exactly as it refuses on an absent one. This makes a failed step
DURABLE, which is what closes the retry channel §4.5's no-file-drawer rule
exists to close.

**THE RECLAIM RULE — a crashed step may resume, a FAILED step may not, and every
resumption is on the record.** v1's version was not executable: it let a failed
step continue after "a new dated pre-freeze note written BEFORE the retry", while
§8.7 forbids any note after the first real fit and step 1 refuses outright while
either kind of step-1 marker exists — so a failed step 1 had no lawful retry path
at all. The rule is therefore three cases, and **failure is terminal**:

> * a **COMPLETED** step produced an outcome, and the sequence stays ONCE-ONLY
>   for it: re-running it after seeing what it produced is the
>   outcome-conditioned second run §4.5 closes, and no reclaim reopens it;
> * a **FAILED** step has published its failure, **and the experiment stops
>   there.** There is no retry, no note and no continuation: a step that ran to a
>   conclusion and failed is an outcome, the result document publishes it as one
>   (§4.5's no-file-drawer rule), and re-running the experiment is a new
>   preregistration. **No document edit is needed and none is permitted**, which
>   is what makes this rule consistent with §8.7 where v1's was not;
> * an **OPEN CLAIM** — a step that started and did not finish — produced no
>   complete product, so there is no outcome to condition a retry on and nothing
>   to put in a file drawer. It may be re-claimed **once per dated reclaim record
>   appended to the pre-frozen claim file** `data/epl/fit/lowerdiv/sequence/
>   claims.jsonl` — appended, never overwritten, a manifest member, and written
>   by the harness rather than by hand — and the completion marker carries the
>   whole reclaim list forward, so a resumed step's history survives the step and
>   a reader can count the resumptions. **Step 1's "refuses while a step-1 marker
>   of either kind exists" therefore has exactly one exception: an OPEN CLAIM
>   reclaimed through `--resume-from`**, which validates the claim file rather
>   than the marker.

**Resumption is a first-class path with its own marker**, not an ad-hoc script.
The predecessor's run needed a hand-written `resume_from_step3.sh` because its
once-only guard refused a lawfully-completed step 1; here `--resume-from <step>`
is a preregistered entry point that validates every prior marker, refuses on the
first that is absent or fails its product re-hash, and writes its own reclaim
record. §10 makes running the sequence by any other means an invalidation.

> **Step 1 — the post-freeze results canaries, both stores. This is the first
> post-freeze act and it performs the first real fits of this document.**
> `python -m epl.lowerdiv --canary`, run once, **with no directory argument of
> any kind** — every path comes from §8.9's `layout()`, and a `--dir` on a
> deciding path is `PathNotFrozen`. It executes §7.3's
> `point_in_time_canary_2` on the E0 store with the incumbent anchor (four fits)
> and on the E1-informed store with the cross-league anchor (four fits), plus the
> evidence, E1-isolation and identity canaries. `PASS: false` on any leg stops the
> experiment **and the failure publishes before the refusal is raised** — the
> canary record is written and a `complete: false` marker is left, and only then
> does the process stop. Step 1 refuses outright while a step-1 marker of either
> kind exists, except on an OPEN CLAIM reclaimed through `--resume-from`.
> Product: `data/epl/fit/lowerdiv/canary.json`.
>
> **Step 2 — the single-opening exercise, and the budget checkpoint.**
> `--run --limit 1`, which **refuses unless the point it would fit is
> 2019-08-09** — the first opening of the corpus, named here by date and by
> nothing else. A different shard's first point is a different opening, and
> choosing one at the command line would make step 2 the selection step it is not.
> It fits both arms at that opening, runs the identity control on that opening's
> fixtures, and **publishes the realised Arm-A fit seconds**. **§2.4's overrun
> ruling is evaluated here**: if the realised Arm-A rate exceeds **269 s/fit**,
> step 2 completes, publishes its measurement and the projected total, and step 3
> raises `BudgetExceeded` — the run is neither thinned nor restarted. Step 2's
> console output and row count are required in the result document.
>
> **Step 3 — the match legs.** Four shards, **sequential**, per-PID waits, BLAS
> pinned. Products: `data/epl/fit/lowerdiv/shard_0{0,1,2,3}_of_04.jsonl`.
>
> **Step 4 — the merge and the match-level scoring.** Products: the four shard
> ledgers it scored (not the merged verdict, whose bytes are not a constant of
> this step — §8.4's own order runs the merge twice, once here and once at
> publication with §3.3's gate in it).
>
> **Step 5 — the parity oracle and the table leg.** The oracle completes at all
> 32 cells **before one treated simulation**. Products: the table ledger **and**
> the parity ledger, both by path and digest.
>
> **Step 6 — publication.** `--merge --evidence`, which re-verifies step 4's and
> step 5's markers rather than rewriting them, computes §9.3's manifest, and
> writes `reports/epl_lowerdiv_result.md` and the §9 evidence files. It is
> publication only and is not a seventh experiment step; every manifest member
> lands before the manifest is computed and nothing manifested is written
> afterwards.
>
> **Step 6's own marker is NOT a manifest member, and that resolves an ordering
> that had no solution.** v1 put `step{1..6}.json` in the manifest, computed the
> manifest inside step 6, and required every member to land before the manifest
> is computed — so step 6's truthful completion marker had to exist before step 6
> completed. **`step6.json` is therefore a CLOSURE RECORD, not a product**: it is
> written after the manifest, it lives at
> `data/epl/fit/lowerdiv/sequence/step6.json` like its siblings, it is sealed by
> its own line in the append-only claim file, and `--verify` checks it against the
> manifest rather than inside it. Steps 1–5's markers stay manifest members,
> because each of them does land before step 6 runs.

**Step 2's scratch requirement is a function of the step, not of the run
directory.** The predecessor's step 2 required a hand copy of step 1's canary
record because the record's location was derived from the run directory rather
than from the step. Here `canary_record_path(step)` is one function, §8.9's
layout is its only source of paths, and a step that needs a prior step's product
resolves it by that function and never by a copy.

### 8.5 The conformance report — behavioural predicates, not names

Before the freeze block may render, `epl/tests/test_lowerdiv.py` must carry one
committed test per row below, each of which **fails under its own seeded defect
class and passes otherwise**, and the report must be **read from an independent
pytest artifact** (`data/epl/fit/lowerdiv_conformance.json`) rather than computed
by the renderer. **The report may not be its own witness.**

| row | § | obligation |
|---|---|---|
| L1 | §2.3 | both arms are real fits at the same opening against the two named store roots; neither reads the other's cache |
| L2 | §0.1, §7.1 | `E1Leak` fires on every one of its five conditions, each seeded alone |
| L3 | §0.5 | `PopulationRederived` fires when `e` is computed on any frame but the pinned E0 archive; **the thin set joins the corpus one-to-one on `match_id` and produces exactly 85 rows**; the recomputed 85-`match_id` digest equals widening v3's frozen `38d18d4d96…`; and **the 85-`key` digest is computed, asserted equal to `5a0d92c5…`, and asserted NOT equal to the pin** |
| L4 | §0.6 B5, **§5.6** | `PhantomClub` refuses before the projection **on every enumerated lowerdiv call site that reaches a store projection**, and a seeded direct call to `epl.fit.to_store_frame` from lowerdiv code makes the test red; and `epl.fit.to_store_frame` fed the same frame still produces `"None"` — the hazard is documented where it lives, not silently fixed and not claimed to be closed repository-wide |
| L5 | §0.6 B4, §2.2 | **registry:** re-resolving the pinned E0 archive through the enlarged registry changes no E0 key, and a synthetic fold collision raises at import. **Ladder:** every E1 season-boundary arrival classifies `from_E0` / `outside_observed_divisions` / `continuing` against the two archives' own memberships, a `from_E0` club is seeded ABOVE the E1 mean and an `outside_observed_divisions` arrival BELOW it, and a misclassification raises `LadderBoundaryMismatch`. **Resolver:** §2.2 point 2b is total over the union team index at all 212 openings, exactly one branch fires per club-cutoff, and a club with no prior match in either archive raises |
| L5b | §0.6 B7, §2.2 2c | **projection:** every E1 row of a synthetic union store reads back `tournament = "EFL Championship"` with the E1 source provenance, and every E0 row reads back Premier League with the E0 provenance, through the real build path. **Z-scale:** the two arms' `(mean, sd)` are bit-identical at every opening, and every E0 club's `elo_z` agrees across arms to `1e-12` |
| L6 | §3.2 | the identity control is exercised in the **production** fit path, not reimplemented by a stub; goes red when its tolerance is loosened to any value; **runs its five operations in §3.2's frozen order**; and **publishes the cause-classification matrix and the environment fingerprint on a seeded mismatch** |
| L6b | §3.2 | the store, anchor and team-index digests bind the resume key; a store whose row count and `match_id` set are unchanged but whose **scores** differ is refused rather than reused; and the union store's E0 subset is value-identical to the E0 store's on all eleven columns |
| L7 | §3.3 | parity is complete at all 32 cells before one treated simulation, and established per cell before its treatment arm |
| L8 | §4.0, §4.1 | the per-horizon gate; **no cross-horizon average on any deciding path**; gate (v) is evaluated on all 2,280 rows; **(iv-c) and (v-b) fire on the interval bound alone, independently of the point sign**; and **the week interval reaches no deciding surface — a seeded attempt to let it decide makes the test red** |
| L9 | §5.1–5.2 | the MC estimator is tie-aware and jointly resampled; both binding tally checks hold |
| L10 | §5.4 | P5 at `K = 200`, **including that it fires when all 200 verdicts agree with each other but disagree with the separately recomputed point verdict**; and the precision regime's condition set equals `PRECISION_CONDITIONS` **by name** — eight IDs, no ninth, compared as a set and never as a count |
| L11 | §6.2 | the equivariance identity holds to `1e-15` at the three named points; **scenarios C and D are derived from B's full-precision value inside the harness and are nowhere transcribed**; **block labels are ordinal-remapped before every bootstrap call**; and `--power` reproduces §6.3's three tables |
| L12 | §8.2 | the pre-freeze commands are mechanically read-only; **A0 reads no score column, and neither A0's nor A1's import closure includes the sampler**; **no pre-freeze or deciding command accepts a directory argument**; the read-only store accessor never builds a store |
| L13 | §8.4 | the frozen six-step sequence, its markers, its product re-hashing, and the reclaim rule — **including that a marker is checked against the freeze block's recorded FREEZE-PARENT commit and its ANCESTRY to HEAD, never against HEAD's equality: the test advances HEAD past the freeze with a synthetic commit and asserts the sequence still passes, and asserts it refuses a marker from a different freeze — and that a FAILED step is terminal while an OPEN CLAIM reclaims through `--resume-from` and the append-only claim file** |
| L14 | §8.6 | the guard establishes the freeze state and never accepts it, on every surface; **the dependency hash table and the environment fingerprint are recomputed at every guarded entry point, and a seeded edit to `epl/dcfit.py` — inside the repository lock's blind spot — makes the test red** |
| L15 | §8.6 | the first-fit state is one fixed path, validated, and RATCHETED by an append-only witness |
| L16 | §8.7, §9.3 | every deciding tally is bound to its row and rebound on every read |
| L17 | **§8.9** | **one layout: every writer's path and every manifest entry come from the same function; a test walks every PRODUCT writer against every reader against every manifest member, and separately enumerates the SOURCE writers — the twelve E1 raw CSVs — as a disjoint set the manifest covers transitively through `provenance_e1.json`; and `step6.json` is a closure record outside the manifest** |
| L18 | §9 | the evidence contract is closed; **the four always-PASS controls — `e1_leak`, `population_rederived`, `phantom_club`, `predicate_mismatch` — are measured off the merged rows as counts** |
| L19 | §2.3 | the frozen constants are not overridable from any public surface |
| L20 | §3.3 | `sampler_digest` is a pure function of `(run, tallies)` and reads no fit-identifying field; **`FROZEN_TABLE_SCHEDULE` is three fields, and the E1-informed club annotation reaches no membership digest and no gate** |

**Twenty-two rows** — `L1 … L20` plus `L5b` and `L6b`, the two that the review's
findings on the projector, the z-scale and store content-binding forced. A freeze
block rendered or read back over fewer than all twenty-two, **compared as the
exact named set and never as a count**, is `FreezeStateUnverified`.

### 8.6 The freeze guard, the public-surface closure, and the first-fit record

**The public-surface closure — one guard, one refusal, no exceptions.** A
production path **RESOLVES** `n_sims`, the simulation seed, the chunk size, `B`,
`alpha`, the bootstrap seed, `MC_BOOT`, `MC_SEED`, `K`, `SHARDS`, `delta_rating`, `γ` and
the deciding population from the modules §0.1 pins them in, and **carries no
parameter for them at all**. Constants that keep a keyword refuse a different
value. Every remaining seam — an injected fitter, engine, runner, oracle or
Monte-Carlo object; a caller-attested lifecycle state; a truncated deciding
population; **a caller-named ledger path (§8.9)** — is refused whenever the
target artifacts are pinned or the directories are the preregistered ones.

**The guard establishes state; it never accepts it.** The freeze/first-fit state
is established from **committed bytes and Git ancestry**: this document's blob
must be committed, its commit must be an ancestor of HEAD, and its current bytes
must equal that blob. A hashed file whose bytes differ from the committed table,
a membership or conformance digest that does not survive fresh recomputation, or
a conformance table that is not exactly §8.5's twenty-two green rows, is
`FreezeStateUnverified`. `harness_frozen` on every ledger row records what the
guard established, never what a caller asserted.

**THE DEPENDENCY HASH TABLE — because ancestry binds almost nothing.** The freeze
block hashes `epl/lowerdiv.py`, its test module and `epl/teams.py`, and the
repository lock covers only `CODE_PATHS = ("src", "scripts")`
(`src/wcmodel/eval/lock.py:74-77`). **Between them sits every `epl/` module this
experiment's forecast actually depends on** — `dcfit`, `anchor`, `elo`, `fit`,
`score`, `particles`, `leaguesim`, `season`, `table`, `simmetrics`, `simretro`,
`walkforward`, `freeze`, `windows`, `schema`, `validate`, `parse`, `fetch`,
`paths` — none of them hashed by the freeze block and none of them locked. A
descendant commit could rewrite `epl/dcfit.py` and still satisfy both ancestry
and `LOCK VALID`.

> **THE RULING.** `--freeze-block` computes and records a **DEPENDENCY HASH
> TABLE**: the sorted `(repo-relative path, SHA-256)` of **every repository file
> in the import closure of `epl.lowerdiv`** — resolved mechanically from
> `sys.modules` after a full import, restricted to paths inside this repository,
> and covering `epl/`, `src/wcmodel/` and `scripts/` alike — plus
> `epl/config_frozen.json`. **Every guarded entry point recomputes the closure
> and re-hashes every member**, and `FreezeStateUnverified` fires if any digest
> differs *or* if the closure's path set differs from the recorded one. The table
> is published in the evidence file and its own digest is carried on every ledger
> row.

**THE ENVIRONMENT FINGERPRINT — because a fit is only a pure function of its
inputs when the machine holds still.** §3.2 demands eight-decimal reproduction of
2,280 published forecasts, and that demand reaches past this repository into the
interpreter and the numerical stack. The freeze block records, and every ledger
row carries, a canonical fingerprint: Python version and implementation; the
installed versions of `numpy`, `pandas`, `pyarrow`, `pymc`, `pytensor`,
`arviz` and `scipy`; the BLAS/LAPACK vendor and version as NumPy reports them;
and the four thread environment variables §2.4 pins. A fingerprint that differs
from the recorded one is `FreezeStateUnverified` — and, on a `ControlMismatch`,
it is one row of §3.2's cause-classification matrix rather than an unexplained
"most likely archive drift".

**The first-fit record — one path, validated, and RATCHETED.** The instant of the
first real fit of this document is recorded at one fixed path with the prereg
blob it attests, and it is accompanied by an **append-only witness line**. A
record deleted, written without its witness, naming a different prereg blob, or
disagreeing with its witness is `FreezeStateUnverified`. A deletable file is not
a ratchet.

### 8.7 After the first real fit: the hashed files cannot change at all

Once the first real fit of this document has run, **any change to a hashed file —
`epl/lowerdiv.py`, `epl/tests/test_lowerdiv.py`, `epl/teams.py`, or this
document — is an invalidation, with or without a note, committed or not.** §8.6
condition (1) binds this file's *current bytes*, so appending a note to it after
the first fit invalidates the run.

Every deciding tally is bound to its ledger row by digest and **rebound on every
read**; `--verify` re-derives the verdict from the tallies rather than echoing it
out of the JSON.

### 8.8 The attestation

**As of this commit: no fit, no season simulation, no store, no E1 archive, no
delta, no evidence file and no verdict of this document exists.** No
`data/epl/fit/lowerdiv*`, no `data/epl/sim/lowerdiv*`, no
`data/epl/matches_e1.parquet`, no `data/epl/raw/E1_*.csv`. No harness file
exists. Every number in this document was computed by read-only passes over
committed or pinned artifacts, and the recipes are given beside them.

**Real fits and simulations DO exist in this lineage, and they are named rather
than elided.** The widening lineage spent two real fits under its v1, thirty-five
real fits and thirty-five real 20,000-season simulations under its v2 pass 7, and
its own frozen post-freeze budget of 147 fits and 96 simulations under v3. **None
of them belongs to this document**, none of them can enter any estimand here, and
this document reuses exactly three of their products: the committed per-fixture
CSV that pins the population (§0.5), the committed feasibility census that scopes
the table leg (§3.3), and the committed anchoring per-fixture CSV that supplies
the collateral leg's 2,280 / 212 / 6 structure (§0.1, §6.2). All three are
read-only here and all three are pinned by digest.

### 8.9 ONE DIRECTORY LAYOUT — the path split, designed out

**The defect this section exists to prevent, named with its root cause.** The
widening run's disclosed deviation 2: the table leg wrote its artifacts under the
run directory while the manifest named them under `data/epl/sim/evwiden/`; the
first `--evidence` pass refused with `MergeIncomplete` on 34 paths, and
byte-identical artifacts had to be placed at both paths by hand. **The root cause
was two sources of truth for one location:** `MANIFEST_PATHS`
(`epl/evwiden.py:8176`) is a tuple of hardcoded relative strings, while
**`manifest_entries(directory=…)`** (`epl/evwiden.py:8550-8563` — that is the
function's name; v1 called it `manifest_targets`, which does not exist)
re-parents them onto a **caller-supplied** directory, and `tallies_dir`
(`:7033-7046`) derives the tally directory from `ledger_path.parent`. Writer
location was a runtime parameter; manifest location was a constant; nothing bound
them.

**THE RULING, and it is birth-law here rather than a fix:**

1. **One function returns every path.** `epl.lowerdiv.layout()` is the single
   source of truth for every artifact location of this experiment — the run
   directories, the shard ledgers, the canary record, the sequence markers, the
   table ledger, the parity ledger, the tallies directory, every tally file, the
   evidence JSON, the CSVs and the MANIFEST. It takes **no arguments** on any
   deciding path.
2. **The manifest is derived from the same call the writers use.** §9.3's list is
   not a tuple of strings that a manifest builder re-parents; it is
   `sorted(layout().manifest_members())`, and every writer opens
   `layout().<name>`. There is exactly one place a path can be wrong, and if it
   is wrong it is wrong for the writer and the manifest together — which is a
   bug that fails immediately rather than a split that fails at publication.
3. **No deciding surface accepts a ledger path.** A caller-supplied ledger,
   tallies directory or run directory is `PathNotFrozen`, refused the same way a
   caller-supplied `n_sims` or seed is refused (§8.6). A scratch directory is
   permitted **only** on the pre-freeze passes §8.2 names, and only under
   `tempfile.TemporaryDirectory`.
4. **A test walks every writer against every reader against every manifest
   member — and PRODUCT writers are distinguished from SOURCE writers.** §8.5 row
   L17: enumerate every path-producing call site in `epl/lowerdiv.py`, assert each
   resolves through `layout()`, assert the set of **product** paths written by a
   full synthetic run equals `layout().manifest_members()` exactly — not a
   superset, not a subset — and assert that a seeded second source of truth (a
   hardcoded relative string) makes the test red. **`layout().source_members()`
   is the disjoint second set**: the twelve E1 raw CSVs, deliberately outside the
   manifest because they are source and are large, covered transitively through
   `provenance_e1.json` (§9.3). A path in neither set, or in both, is
   `PathNotFrozen`. Without that split the exact-set rule and §9.3's deliberate
   exclusion of the raw CSVs contradict each other, which is how v1 read.
5. **`step6.json` is a closure record, not a product** (§8.4). It is the one
   sequence marker outside `manifest_members()`, because a manifest computed
   inside step 6 cannot contain a truthful record of step 6's completion.

**The predecessor's three other disclosed defects are designed out in the same
spirit and in their own sections:** the once-only guard refusing a lawfully
completed step is fixed by §8.4's reclaim rule and its first-class `--resume-from`
path; the canary record's location depending on the run directory is fixed by
§8.4's `canary_record_path(step)` and by this section's rule 1; and the
marker-versus-HEAD equality check that turned that harness red on its own
publication is fixed by §8.4's freeze-commit-and-ancestry rule. **Three were
disclosed by the run's own deviation list; the fourth was disclosed by the suite
going red afterwards, which is the more expensive way to learn it.**

### 8.10 Dated pre-freeze notes

**This is the one place this document may grow before the seal commit, and it
closes at that commit.** A dated note is appended here, and nowhere else, for
each of:

* **A0's outcome-blind census** (§0.6, §8.2) — the twelve fetch records, the
  complete E1 spelling set with each spelling's index fold and per-season
  presence, and the collision-check result;
* **A1's acquisition record** (§0.6, §8.2) — the per-season **structural**
  validation table, the distinct-club census, any unmapped name, and the E1
  archive's SHA-256, row count, byte size and per-season club census. **A freeze
  block may not render while this note is absent**, and the freeze block pins the
  archive digest this note records;
* **any pre-freeze pass that produced a number this document is scoped by**, with
  its date, the HEAD it ran at, what it measured, and where its record lives;
* **an abandonment record**, if A0 or A1 refuses and the experiment is not run
  (§0.6).

**THE ALLOW-LIST IS THE NOTE'S SCHEMA, AND IT CARRIES NO OUTCOMES.** No note may
record a score, a goal count, a goal rate, a result distribution or any statistic
derived from a match result — of either archive. `--freeze-block` refuses on any
field outside the allow-list (§8.3), and §10 makes publishing one an
invalidation. Structural counts are not outcome summaries and are the whole
census this document is scoped by. **§8.4's reclaim rule requires no note at
all**: a FAILED step is terminal and an OPEN CLAIM is reclaimed through the
append-only claim file, so no §8.10 note is ever needed after the first fit —
which is what makes this section's closure consistent with §8.7 rather than in
conflict with it.

Each note carries a date, the HEAD it was written at, and what it records.
**After the first real fit of this document, §8.7 forbids any further note** —
committed or not, here or anywhere in this file — because §8.6 condition (1)
binds this file's current bytes. A note appended after the first fit is an
invalidation (§10), and this section is closed by the same clause that closes
every other.

---

## 9. The evidence contract

**The result publishes either way** (§4.5), and the verdict's machine-readable
basis is committed, not gitignored.

### 9.1 `reports/evidence/lowerdiv.json`

Carries, at minimum, and by these names:

* `schema` (`epl-lowerdiv-2`), `generated_at`, `prereg_commit`, `prereg_blob`,
  `freeze_parent_commit`;
* `pins` — corpus / E0 archive / **E1 archive** / ledger / frozen-config digests,
  the realised config digest, the feasibility census digest and its 32-cell
  priceable set, the widening per-fixture CSV's digest, **the collateral
  structure CSV's digest**, **`store_sha256` / `anchor_sha256` /
  `team_index_sha256` for both arms**, **`dependency_table` and its digest**,
  **`environment_fingerprint`**, and the row and season counts;
* `population` — `{n: 85, join_column: "match_id",
  digest_match_id: "38d18d4d96…", digest_key_not_the_pin: "5a0d92c5…",
  n_distinct_key: 62}` (§0.5);
* `calibration` — `{delta_rating: -75.0,
  delta_rating_source: "epl/config_frozen.json chosen.promoted_offset",
  tuning_contrast_rps: 0.001309,
  scoring_window_sensitivity_rps: 0.0030, gamma_primary: 1.0,
  gamma_secondary: 0.5, swept: false, bridge_validated: false}` (§2.2);
* `acquisition` — A0's and A1's records: the twelve fetch digests, the
  **structural** validation table, the club census and spelling folds, the
  unmapped-name list. **No outcome summary** (§0.6);
* `estimand` — `{n: 85, mean, sd, se_iid, statistic: "matched-fixture RPS
  difference"}`;
* `ci_season` — the **deciding** interval, `{function, n_blocks: 6, B, alpha,
  seed, lo, hi, decides: true}`; `ci_week` — the **reported diagnostic**,
  `{… n_blocks: 62 …, decides: false}`; `ci_corpus_week` (`n_blocks: 212`),
  `ci_corpus_season` and `ci_table_mw6` (`n_blocks: 7`) likewise;
* `gate_i`, `gate_iii` — each `{value, bar, PASS, decides: true}`;
* `diagnostic_week_ci` — `{lo, hi, would_have_passed: bool, decides: false}`,
  carrying §4.0's demotion explicitly so a reader can see what it would have done;
* `gate_iv` — `{mw6: {n: 7, mean, ci, per_cell: [...]},
  per_label: {MW0: {n: 5}, MW3: {n: 6}, MW10: {n: 7}, MW19: {n: 7}, each with
  mean, mc_se and PASS},
  precision: {conditions: PRECISION_CONDITIONS with each condition's computed
  value and resolved flag, unanimity: {K: 200, point_verdict, verdicts: [...200],
  dissent_count, fired}}, PASS_or_UNRESOLVED}` — **eight condition IDs, no
  ninth, compared as a named set** (§5.4);
* `gate_v` — `{n: 2280, mean, bar: 7.5e-05, ci_week, screen_note: "(v-a) is an
  observed point-tolerance screen, not a demonstration of non-harm", PASS}`;
* `controls` — `{identity: {n: 2280, max_abs_diff, mean_abs_diff, PASS},
  e1_leak, population_rederived, phantom_club, predicate_mismatch,
  point_in_time_e1, table_parity: {n_cells: 32, PASS, per_cell_digests}}`;
* `canaries` — results (both stores), evidence (both legs, both row counts, the
  positive control's realised magnitude), **E1-isolation (all four legs, with the
  positive control's realised `max |Δp|`)**, identity;
* `sequence` — the six markers of §8.4 (five manifested plus `step6.json`, the
  closure record), each with its recorded **freeze-parent
  commit**, completion time, product paths and product digests, plus the
  append-only claim file's reclaim list;
* `conformance` — §8.5's pytest artifact identity: path, SHA-256, the
  **twenty-two** test ids and the pass count, as the freeze block records them;
* `e1_support_census` — per fixture and per club-cutoff cell: E0 `e`, prior-E1
  match count, last prior E1 date, each `decides: "nothing"` (§3.1). **No E1
  `e`**, by §0.5;
* `e1_informed_clubs` — the per-cell sorted club lists of §3.3, keyed by
  `FROZEN_TABLE_SCHEDULE`'s triplets, `decides: "nothing"`, excluded from every
  membership digest;
* `cold_start_census`, `gamma_arm`, `strata`, `movement`, `coverage`,
  `sunderland`, `unpriceable_cells_retry` — each `decides: "nothing"`;
* `power` — §6's **one canonical object**, from which every table in §6.3 is
  rendered and into which no value is transcribed: the frozen scenarios
  (`sd_c` and `sd_d` derived from `sd_b`, not stored as literals), the three
  correlation regimes, the structure, the equivariance identity's measured error,
  the MDE definition, `R`, every seed, the replicate-level gate booleans, the
  Monte-Carlo standard errors, `deciding_set: ["i", "iii"]`,
  `benefit_gate_joint_power` (named so, and carrying
  `excludes_gates: ["iv", "v"]`), the gate-(ii) diagnostic column, and
  `power.realised` per §6.5 with its `OUT_OF_POWER_ENVELOPE` flag;
* `materiality` — the pooled corpus figure and §4.2's required sentence;
* `verdict` — `ADOPT` / `NO ADOPT` / `UNRESOLVED`, and which gate decided.

**The always-PASS controls are MEASURED, not asserted.** `controls.e1_leak`,
`controls.population_rederived`, `controls.phantom_club` and
`controls.predicate_mismatch` must be **read off the merged rows** — counts, not
`{n: 0, PASS: true}` constants. Their values are true by construction only
because a refusal stops the run first, and a verdict file that always prints PASS
for a control nobody measured is exactly the shape this document's own "a test
that cannot fail is not a test" objects to.

### 9.2 The CSVs

**`lowerdiv_per_fixture.csv`** — **2,280** rows (the whole corpus, because the
whole corpus moves): `match_id, key, season, block, block_ordinal, cutoff, date,
home_key, away_key, e_home_e0, e_away_e0, e_min_e0, n_e1_home, n_e1_away,
last_e1_home, last_e1_away, thin, p_home_B, p_draw_B, p_away_B, p_home_A,
p_draw_A, p_away_A, p_home_corpus, p_draw_corpus, p_away_corpus, y, rps_B, rps_A,
delta, delta_vs_corpus, max_abs_dp_vs_corpus, cold_start_B, cold_start_A,
provisional_B, provisional_A`. **`match_id` is the identifier and the join
column** (§0.5); `key` is carried for provenance and joins nothing. The 85 pinned
fixtures are flagged by `thin`, and a reader can recompute the estimand from this
file alone. **There is no `e_*_e1` column**, by §0.5.

**`lowerdiv_table_cells.csv`** — 32 rows: `season, cutoff_label, cutoff,
e1_informed_clubs, n_e1_informed_clubs, trps_control, trps_treatment, delta_trps,
wtrps_control, wtrps_treatment, delta_wtrps, mc_se_paired, identical,
sampler_digest_control, sampler_digest_treatment, substantive_digest_control,
substantive_digest_treatment, parity_digest_simretro, provisional_control,
provisional_treatment, effective_posterior_control, effective_posterior_treatment,
tally_sha256, cov50_control, cov90_control, cov50_treatment, cov90_treatment,
cov50_e1informed_control, cov90_e1informed_control, cov50_e1informed_treatment,
cov90_e1informed_treatment, realised_hash`.

**`lowerdiv_gamma_arm.csv`** — 85 rows, the γ = 0.5 secondary: `match_id,
delta_gamma, delta_primary, difference`.

**`lowerdiv_e1_census.csv`** — one row per E1 club: `key, canonical, spellings,
index_folds, seasons_present, matches, first_date, last_date`.

### 9.3 `reports/evidence/MANIFEST.sha256`

Each entry carries a SHA-256 **and a byte size**, and both are **validated** on
`--verify`, not merely recorded. **The list is `sorted(layout().manifest_members())`
and is not written down anywhere else** (§8.9). Its members are, exactly:

| group | paths |
|---|---|
| evidence | `reports/evidence/lowerdiv.json`, `lowerdiv_per_fixture.csv`, `lowerdiv_table_cells.csv`, `lowerdiv_gamma_arm.csv`, `lowerdiv_e1_census.csv` |
| **reproduction bundle (§9.5)** | `reports/evidence/lowerdiv_corpus.csv`, `reports/evidence/lowerdiv_openings.jsonl`, `reports/evidence/lowerdiv_attestations.json` |
| match leg | `data/epl/fit/lowerdiv/shard_0{0,1,2,3}_of_04.jsonl` (4), `data/epl/fit/lowerdiv.json`, `data/epl/fit/lowerdiv/canary.json` |
| E1 archive | `data/epl/matches_e1.parquet`, `data/epl/manifest_e1.json`, `data/epl/team_name_mapping_e1.json`, `data/epl/raw/provenance_e1.json` |
| table leg | `data/epl/sim/lowerdiv/table_cells.jsonl`, `data/epl/sim/lowerdiv/parity.jsonl`, `data/epl/sim/lowerdiv/tallies/<S>\|<L>.npz` — **exactly 32 files** (each holding BOTH arms' tallies, so 64 tallies in 32 paths), `<S>` over the seven seasons with `/` replaced by `-`, `<L>` over the five labels, minus the three excluded cells |
| sequence | `data/epl/fit/lowerdiv/sequence/step{1..5}.json` (5) and `data/epl/fit/lowerdiv/sequence/claims.jsonl` (1) |
| conformance | `data/epl/fit/lowerdiv_conformance.json` |

The count is decidable from this document: 5 + 3 + 6 + 4 + 34 + 6 + 1 = **59
paths**. "Bulky local artifacts" is not a category here; it is a list, and §8.9
makes it a list that one function produces.

**`step6.json` is deliberately NOT a member** (§8.4, §8.9 rule 5): the manifest
is computed inside step 6, so a manifest containing step 6's truthful completion
marker cannot be written. It is a closure record, sealed by its own line in
`claims.jsonl`, and `--verify` checks it against the manifest rather than inside
it. **The two feature-cache roots are not members either**: they are derived
caches whose keys hash HEAD, they are reproducible from the stores, and pinning
them would pin a HEAD (§0.1).

**The twelve E1 raw CSVs are covered transitively and deliberately.** They are
not manifest members — they are source, not product, and they are large — but
`data/epl/raw/provenance_e1.json` **is** a member and carries each one's URL,
byte size, SHA-256 and fetch time, so the manifest pins the raw bytes through one
file rather than twelve. `--verify` re-hashes every E1 CSV against that
sidecar and refuses on any disagreement or absence, which is the same guarantee
at one twelfth the manifest.

**Publication leaves this MANIFEST valid.** Every member lands **before** the
manifest is computed and nothing manifested is written afterwards. Step 6
re-verifies steps 4 and 5's markers rather than rewriting them.

**`--verify` refuses** if any member is missing from the MANIFEST; if any digest
disagrees; if any byte size disagrees; if the MANIFEST carries an entry inside
this experiment's namespace (`lowerdiv`) outside the list; or if a promised file
is not on disk. It may not skip a file it cannot find.

**`--verify` also re-derives the verdict**: it rebinds every tally to its
recorded digest, re-runs §5's estimator and §5.4's unanimity rule, recomputes
gates (iv) and (v) and the adoption decision, and refuses on any disagreement
with the published values. **A published value it cannot find is a disagreement**,
not a comparison skipped.

### 9.4 The result document

`reports/epl_lowerdiv_result.md` publishes whatever the signs, and must carry:

* the verdict and **which of the four deciding gates decided** — and, if the
  verdict is NO ADOPT, the reported week interval beside it with §4.0's ruling
  quoted, so a reader can see both what decided and what was demoted;
* §4.2's required materiality sentence, verbatim, and — on any pass of gate (v) —
  §4.4's required non-harm sentence, verbatim, with the realised (v-b) MDE;
* **§6.4's power ruling in its own words if the estimand misses**, including the
  sentence *"not detected at this power, not no effect"* and the measured
  `benefit_gate_joint_power` at −0.00413, **with the disclosure that it excludes
  gates (iv) and (v)**;
* §6.5's realised paired SDs, the deciding-pair MDE recomputed at the realised
  thin-population SD, and `OUT_OF_POWER_ENVELOPE` if it fired;
* §3.1's E1 support census — the prior-E1 match counts for all 85 fixtures and
  the club-cutoff census — reported as the pre-stated secondary it is, **and the
  statement that the E1-informed `e` was not computed and why** (§0.5);
* **the E1 goal rate against E0's** (§0.6, §2.2), measured after the freeze and
  published here rather than in the preregistration;
* §1.2 bullet 2's attribution: how much of any improvement is the cold-start path
  dissolving, stated as unseparable by this design; **and §2.2's package
  attribution — that no component of the treatment is identified** (§2.3);
* §3.4's coverage reading, in the direction §3.4 fixes;
* A0's and A1's acquisition records by reference to the §8.10 notes, and the E1
  archive's digest;
* the console output, row count and **realised Arm-A fit seconds** of §8.4 step 2
  against the 269 s/fit threshold, and the digest of step 1's canary record;
* if gate (iv) is UNRESOLVED: which of `PRECISION_CONDITIONS` fired, with its
  computed value, and §5.5's pre-statement that this was the modal outcome.

### 9.5 The reproduction bundle — committed, because the decisive inputs are not

**The problem, stated as the weakness it is.** The corpus parquet, the walk-
forward ledger, the E0 archive, `single_fit.json` and the future E1 archive are
all gitignored. §0.1 pins their digests, but **a clean clone cannot regenerate a
single one of them**, so every count, probability and outcome this document's
verdict rests on is, from Git's point of view, this document's word. v1 asserted
that "the verdict's machine-readable basis is committed, not gitignored"; for the
verdict's *outputs* that was true, and for its *inputs* it was not.

**The ruling: a content-addressed bundle is committed BEFORE the freeze, and its
absence is a freeze refusal** (§8.3 step 6). Three files, all manifest members,
all under `reports/evidence/`:

| file | contents |
|---|---|
| `lowerdiv_corpus.csv` | the **complete 2,280-row scoring corpus**: `match_id, season, block, cutoff, date, home_key, away_key, p_home, p_draw, p_away, y, dc_rps` — every probability and outcome the identity control of §3.2 compares against, so the control is checkable from Git alone |
| `lowerdiv_openings.jsonl` | the **212 opening records** from the walk-forward ledger: `cutoff, provisional_teams, cold_start_teams, config_sha256, realised_config_sha256` — the sets §3.2's `PredicateMismatch` is asserted against |
| `lowerdiv_attestations.json` | canonical attestations for everything that cannot be committed: for the E0 archive, the E1 archive, both store roots, the anchor history and the team index — path, SHA-256, row count, column list, and the per-column digests §3.2 defines. Plus the environment fingerprint and the dependency hash table of §8.6 |

**What this does and does not buy.** It makes the corpus, the openings and every
archive/store attestation **verifiable from a clean clone**, and it makes §6.2's
whole power construction reproducible from committed bytes (which is also why
§0.1 pins `reports/evidence/anchoring_per_fixture.csv` as the collateral leg's
structure rather than the parquet). It does **not** make the archives themselves
regenerable — football-data.co.uk's bytes are not this repository's to commit —
and this document does not pretend otherwise: the attestations are the contract,
and `--verify` refuses on any drift from them.

---

## 10. What would invalidate this preregistration

* Any pinned digest of §0.1 differs at run time without a prior dated note.
* **`data/epl/matches.parquet` is written, or its bytes move, for any reason.**
* **An E1 row reaches the E0 archive, the E0 store root, `epl.elo`, or
  `effective_evidence`.**
* **The thin population is re-derived rather than taken from the pinned
  `reports/evidence/widening_per_fixture.csv`**; or it is joined on any column
  but `match_id`; or the recomputed 85-`match_id` digest is not widening v3's
  `38d18d4d96…`; or a fixture is dropped from the 85.
* **An `e` is computed on any frame containing an E1 row**, or the E1-informed
  `e` secondary §0.5 drops is reinstated without its own preregistration.
* **A null club key is stringified rather than refused on any lowerdiv path**, or
  the `PhantomClub` refusal is moved after the projection (§5.6 scopes the claim
  and §10 does not extend it beyond that scope).
* **The E1 half of the union store is projected through
  `epl.fit.to_store_frame`**, so that its rows are labelled Premier League or
  attest the E0 archive as their source (§0.6 B7).
* **Arm A's z-scale is taken over its own union team set** rather than frozen to
  Arm B's E0 `(mean, sd)` at the same cutoff (§2.2 point 2c).
* A real-archive fit or season simulation runs before the §8.3 seal commit,
  anywhere, under any output directory. A0 and A1 are data acquisition and fit
  nothing; an acquisition pass that builds a store or imports the sampler is such
  a fit.
* A0 is run more than once; or A1 runs before A0's census is published; or either
  dated note is absent when the freeze block renders; or the E1 archive's bytes
  differ from A1's note.
* **Any outcome summary of the treatment data — a goal rate, a score
  distribution, any statistic derived from a match result — is published before
  the freeze**, in a §8.10 note or anywhere else (§0.6).
* An E1 season that fails validation is dropped, repaired by hand, or excluded
  rather than refused.
* Registry entries are written before A0's spelling census is published, or a
  fold collision is resolved by renaming a club rather than by refusing.
* **§2.2 point 3's E1 season-boundary rule is changed, or a bare
  `epl.elo._open_season` is used on the E1 archive** — which would seed clubs
  relegated from the Premier League 75 points *below* the Championship mean with
  no exception raised — or an unclassifiable arrival is defaulted to a seed
  rather than refused.
* **`epl/elo.py` is edited, or the E0 Elo ladder is recomputed by this
  experiment.**
* **Any change to a hashed file after the first real fit of this document, with
  or without a note, committed or not** (§8.7) — including a note appended to
  this document.
* A hashed file differs at run time from the committed freeze block.
* **`delta_rating` moves off −75.0, is swept, is estimated from crossings, or is
  presented as fitted; or γ moves off 0.5 in the secondary, or off 1.0 in the
  primary; or the γ arm is promoted to the estimand.**
* **A result is reported as identifying a component of §2.2's treatment
  package** — the E1 rows, the bridge, or the pooled nuisances — rather than the
  package (§2.3, §4.2).
* **The deciding set changes after any delta exists** — gate (ii) restored to
  deciding, or any of (i), (iii), (iv), (v) demoted — or the week interval
  reaches any deciding surface, or is omitted from the published result (§4.0).
* **(iv-c) or (v-b) is evaluated with the point-sign conjunct v1 carried**,
  i.e. requiring the mean to be `> 0` as well as the bound (§4.1).
* **§2.4's overrun ruling is bypassed**: the run is thinned, re-scoped or
  restarted after Step 2's realised rate exceeds 269 s/fit, instead of refusing.
* **A FAILED step of §8.4 is retried**, or a §8.10 note is written to enable one
  (§8.4's reclaim rule makes failure terminal).
* Option (b) — a fitted league covariate — is reported as this experiment, or
  `EPL_COVARIATES` is extended on any path this document runs.
* A division other than E1 is added, or E1 seasons outside `1415`–`2526` are
  ingested, and reported as this experiment.
* The 212 openings are reduced, the 2,280-fixture identity control is sampled or
  truncated, or gate (v) is evaluated on a subset.
* A cell is dropped from the 32, or a cell the feasibility census measured as
  unpriceable is added back to the oracle or to any gate.
* The treated-subset mean, a stratum, the γ arm, the dissolved-population
  secondary, or any secondary decides anything.
* A second seed, bootstrap seed, `B`, `n_sims`, `MC_BOOT`, `MC_SEED`, `K`, shard
  count or block definition is reported as this experiment.
* Any threshold or CI condition in §4 moves after any delta exists.
* The identity control's tolerance is widened after a mismatch, anywhere.
* The result is not published, or publishes without the §9 evidence files.
* Gate (iv) evaluated on any cross-horizon average, or the MW6 horizon replaced
  after any table run.
* The 32-cell parity oracle skipped, sampled, truncated, or established after any
  treated simulation.
* Gate (iv) evaluated with an MC estimator that is not §5's jointly-resampled,
  tie-aware estimator — including any estimator that combines per-cell standard
  errors in quadrature, any estimator built on `.order`, and any run whose
  deciding cells do not share a common `n_particles`.
* §5.4's unanimity rule omitted, run at a different `K` or seed, or replaced by a
  scale comparison against `mc_se_mw6`.
* The steps of §8.4 run out of order, or a step run without its predecessor's
  marker, or the sequence resumed by any means other than `--resume-from`.
* **A marker checked against HEAD's equality rather than against the freeze
  block's recorded FREEZE-PARENT commit and its ancestry to HEAD** (§8.4) — the
  shape that made the predecessor's harness go red on its own publication — or a
  freeze block that attempts to record the identity of the commit containing it.
* **A deciding path runs with a load-bearing dependency outside §8.6's dependency
  hash table**, or with an environment fingerprint differing from the freeze
  block's, or with either check disabled.
* **§9.5's reproduction bundle is absent, incomplete, or not committed before the
  freeze**, or a member of it fails its recorded digest at run time.
* A deciding tally read without rebinding it to its recorded digest.
* **Any artifact path resolved from anything but §8.9's single layout function**,
  or a manifest entry that does not come from `layout().manifest_members()`, or a
  deciding surface that accepts a ledger, tallies or run directory.
* Any deciding number produced through a seam §8.6's closure refuses — an
  injected fitter, engine, runner, oracle or Monte-Carlo object; a
  caller-attested lifecycle state; a truncated deciding population; or a frozen
  constant supplied rather than resolved.
* A treated arm simulated at any cell before that cell's native parity against
  protected `ArchiveRunner` has been established.
* Step 1 retried after a **failed** canary at all (§8.4: failure is terminal; an
  OPEN CLAIM is a different thing and reclaims through `--resume-from`).
* A conformance report accepted from anything but §8.5's committed pytest
  artifact, or a freeze block rendered or read back over fewer than all
  **twenty-two** rows `L1 … L20`, `L5b`, `L6b` — compared as a named set.
* The first-fit record deleted, or written without its append-only witness line,
  or recorded at a moment that is not the instant of the fit it attests.
* `--script` run before the seal commit, at any target; or a post-freeze
  launcher generated with a caller-supplied interpreter or command.
* Any commit of this work leaving `scripts/oa_lock.py` printing anything but
  `LOCK VALID`.

---

## 11. Standing disclaimers

* **Small population, pre-picked, and inherited rather than chosen.** 85
  fixtures in 62 blocks, selected by a *previous* experiment's rule that targeted
  exactly where *its* effect should be largest. That inheritance is what makes
  the comparison with −0.00413 possible and it is also a constraint this
  experiment cannot relax (§6.4).
* **This design is underpowered against the effect it exists to test, and the
  gate refounding did not fix that.** `benefit_gate_joint_power` 0.14–0.49 at
  −0.00413; joint MDE 1.61× to beyond 4.84× that effect; **gate (iii), the
  6-block season interval, is the binding gate** — and it binds alone, because it
  implies gate (i) at every scenario SD in this design (§6.3). Those figures
  **exclude gates (iv) and (v)**, so four-gate adoption power is lower still.
  **A miss is substantially uninformative.**
* **Season-level correlation is the risk the deciding interval is most exposed
  to**, and it is modelled rather than assumed away: at `ρ_season = 0.25` the
  deciding pair's power at −0.00413 falls to 0.116–0.216 (§6.3).
* **The bridge is an assumption, not a measurement.** `delta_rating = −75.0` was
  fitted as a destination seed for promoted clubs, not as the gap between two
  ladders' centres, and it is used here symmetrically in both directions with no
  validation. Nothing in this experiment tests it.
* **The treatment pools scoring level and home advantage across two divisions**,
  because the model carries one `mu` and one `home_adv` and option (b) is
  refused. Any effect is the package's, not the E1 rows'.
* **A club relegated straight out of the top flight has its live E0 form
  discarded** and is reseeded at `mean_E1 + 75` (§2.2 point 3). That is chosen to
  keep the two ladders' scales apart, and it is a real loss of information.
* **Gate (iv) UNRESOLVED is the modal outcome of the table leg** (§5.5), because
  two fits per cell carry more paired MC error than one posterior did, at the
  same 20,000 seasons.
* The intervals are percentile block bootstraps over correlated fixtures — not
  moving-block, not exact tests; the 6- and 7-block season resamples have poor
  coverage and serve only to refuse single-season verdicts. One ADVI seed;
  mean-field under-dispersion is a known, separately scheduled limitation.
* **Sampler noise is not model error**, and with two independent fits per pair it
  enters this design's differences twice rather than cancelling. **The pairing is
  at the fixture, not at the fit**: adding teams changes the design's dimension,
  so no common-random-numbers claim holds at posterior level, and scenario C's
  √2 is a stated construction rather than a bound. Both are reported; neither
  shrinks with a better argument.
* **The improvement, if any, cannot be attributed to better parameter estimates
  rather than to the cold-start path dissolving** (§1.2, §2.3). No design here
  separates them.
* **`delta_rating` prices an assumed centre of the league gap and not its
  dispersion.** A club whose attack is estimated largely from Championship
  matches carries a Championship attack shifted by a constant. That is the
  modelling assumption and it is not tested here.
* TRPS is proper for the displayed marginals only; the treatment also changes the
  joint law, and no metric in this experiment sees that.
* **The match-level result is evidence about second-tier evidence in general, not
  about Hull.** Hull's configuration has zero support in the scoring window and
  one analogue in the table leg, and nothing here may be quoted as "the Hull fix
  was validated" — or refuted — at match level.
* Twelve seasons, two divisions, one country, one model, one configuration, one
  frozen offset. Nothing generalises beyond them.

---

## 12. What this does not decide

Not decided here, by anything this experiment can produce: no change to α (0.5),
decay (365), `k_att`/`k_def`, `promoted_offset` as the E0 Elo uses it, D2
(static-within-fit), D12 (per-fixture Bernoulli), the volatility or few-games
arms, the published arm, `ISSUANCE_SCHEMA_VERSION`, the matchboard, A8's constant
or ledger, A12's arm or capture bounds, the freshness, anchoring or widening
verdicts, or the market-prior question. No fitted league covariate is licensed and
no third division is licensed. **The evidence-mass widening rule is not
re-litigated by this document**: widening v3's verdict stands as published, and
this experiment neither confirms nor overturns it — it asks a different question
on the same fixtures. **The lock chain is untouched by design and no lock-v11 is
opened.**

---

## 13. The design review, and its disposition

**This section is a provenance record. It decides nothing, and it holds no
correction that is not already law in the section it belongs to.** Every finding
below was fixed in place, by direct edit, in the clause it concerns; nothing in
this document is annotated, superseded or deferred. The index exists so a reader
can check the review against the document without holding both open, and because
three findings were **refuted from the repository** and a refutation that is not
recorded is indistinguishable from an omission.

**The review.** A cross-model design review of v1 at `35e562f`, run before any
harness existed, ruled the document **UNSOUND** on **15 blocking, 14 important
and 2 minor** findings. Its own verdict — *"after repair, the design is
defensible only as an explicitly exploratory estimation/engineering study with
adoption forbidden"* — is **not** adopted: §4.0's owner ruling re-founds the gate
family instead, and §6.4 states plainly what power the refounded set has and what
it does not. **A reader who wants the strongest available argument against
running this experiment at all should read §6.4 and §11 first.**

**Where each finding landed.** Blocking: B1 §0.5 (the pin is on `match_id`);
B2 §0.5 (the E1-informed `e` secondary is dropped, and §3.1's support census
replaces it); B3 §0.6, §2.1, §8.2, §8.3 (A0/A1 and the two-stage harness);
B4 §0.6, §8.3, §8.10 (the goal rate moves after the freeze, and the note has an
allow-list); B5 §0.6 B7, §2.1 (the lowerdiv projector); B6 §3.2 (store, anchor
and team-index digests in the resume key); B7 §2.2 points 2b and 2c (the source-
ladder resolver and Arm B's frozen z-scale); B8 §2.2, §2.3, §4.2, §11 (the bridge
is an assumption and the package is what is tested); B9 §7.3, §0.1 (the
two-store canary and the two private caches); B10 §5.4, §8.5 (named condition IDs
and named conformance rows); B11 §5.4 (P5 must agree with the point verdict);
B12 §8.3, §8.4 (the freeze-parent commit); B13 §8.4, §8.9, §9.3 (no `--dir`,
`step6.json` as a closure record, source vs product writers); B14 §8.6 (the
dependency hash table); B15 §6.1 (scenario C derived, not transcribed).
Important: I1 §2.3, §3.3, §11; I2 §3.2, §8.6; I3 §2.2; I4 §2.2 point 3;
I5 §2.2 point 4; I6 §6.1, §6.2, §6.3; I7 §4.1, §4.4; I8 §2.3, §6.2, §0.1;
I9 §2.4; I10 §8.4; I11 §5.6; I12 §9.5; I13 §3.3; I14 §2.3, §8.9. Minor:
M1 §2.2 (`delta_rating` / `mu_rps`); M2 §2.4.

**The three refutations, each recorded where it belongs.**

| # | the claim | what the repository says |
|---|---|---|
| **I5** | v1's own claim, which the review corrected: that `assert_tuning_only` lets an E1 row labelled `2019/20` pass undetected | **v1 was wrong and the review is right.** `epl/windows.py:71-86` intersects present seasons with `SCORE_SEASONS ∪ EXCLUDED_SEASONS` and raises; `2019/20` is in `SCORE_SEASONS`. §2.2 point 4 states the two real limitations instead — division-blindness and call-path coverage |
| **I8, the thin half** | that first-appearance block order and `np.unique`'s sorted order differ, so fixed bootstrap draws attach to different blocks | **Refuted for the 85-fixture leg, confirmed for the 2,280-fixture leg.** Measured read-only: the 62 `(season, ISO week)` labels and 6 season labels sort into first-appearance order already, so the thin leg was never exposed; under §6.2's ascending-`match_id` row order the corpus's 212 labels do not. §2.3's ordinal remap closes both regardless |
| **B11, the ambiguity half** | that v1 was "ambiguous about one particle draw versus a complete `MC_BOOT` loop" | **Refuted from v1's own text**, which already said "one `picked` per stream". **The other half of the finding stands and was the serious one**: v1 omitted the comparison against the point verdict that `epl/evwiden.py:7572-7578` performs, and §5.4 restores it in full pseudocode |

**One more claim the review made that this document does not adopt, and says
so.** The review proposed a materially different design — prospective
E0-only eligibility, fitting only openings containing eligible fixtures,
division-specific intercepts estimated on the tuning window, and standardized
within-division transfer. **That is a better experiment and it is not this one.**
Adopting it would abandon the comparability with `−0.00413` that is this
document's entire reason to exist (§6.4), and it belongs in its own
preregistration written against its own population. It is recorded here so that
the choice is on the record rather than unmade.

---

*Preregistered 2026-08-30 (v1), re-founded and repaired 2026-08-30 (v2). This is
the lower-division-evidence experiment
[`reports/epl_widening_result.md`](epl_widening_result.md) named as its own
successor. It is written on the structure of
[`reports/epl_widening_prereg_v3.md`](epl_widening_prereg_v3.md) — that
document's §5 statistics, §8 lifecycle, §9 evidence contract and §10
invalidations — with every ruling its four review rounds, two in-tree adversarial
audits and one owner adjudication reached carried here as birth-law rather than
as a later repair, and with the four harness defects that run disclosed designed
out before a line of harness code exists (§8.4's reclaim rule and first-class
resumption; §8.4's step-indexed canary record; §8.4's freeze-parent-and-ancestry
marker rule, learned from that harness going red on its own publication;
§8.9's single layout function).
It differs from its predecessor in the three ways that matter and each is stated
as a loss or a cost rather than discovered by the run: the structural-zero control
cannot exist because the arms are two fits (§1.4); the population must be pinned
rather than derived because one Championship season is three times the threshold
that defines it (§0.5); and the design is underpowered against the very effect it
exists to test, with gate (iii) binding after §4.0's refounding, and no amount of
additional data can buy power on a population that is pinned (§6.4). No harness
exists, no E1 archive exists, and no fit of this document has ever run.*
