# Lower-division evidence — preregistration of the second-tier archive experiment

**Written:** 2026-08-30 · **Branch:** `main` · **Schema:** `epl-lowerdiv-1`
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
population, the estimand, the resampling, the secondaries, the five-part
adoption rule, the Monte-Carlo estimator and its precision regime, the refusal
semantics, the lifecycle, the evidence contract and the scope. There are no
repair sections and no supersession index inside it, because there is nothing
inside it to supersede. Every clause below is operative. **Where this document
is silent, nothing is implied.**

**Status.** No harness exists. `epl/lowerdiv.py` and `epl/tests/test_lowerdiv.py`
are not written; no `data/epl/matches_e1.parquet` exists; no E1 CSV has been
fetched; no fit, no simulation, no delta, no evidence file and no verdict of this
document exists. This commit is the **first** step of the house lifecycle —
preregistration BEFORE harness code, then cross-model design review, then harness
TDD, then dual audit, then freeze, then run, then publish either way — and §8
says exactly what each step must contain and in what order.

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
| Widening per-fixture evidence (the pinned population's source of truth) | `reports/evidence/widening_per_fixture.csv` — **committed**, 85 rows, the exact fixture keys, blocks and seasons this document's population is pinned to (§0.5) |
| Table-retro anchor | `data/epl/sim/retro_r1.jsonl` (**protected, read-only**) and `epl.simretro`'s public constants: `SEASONS` (7, 2019/20 … 2025/26), `COMPARISON_CUTOFFS` (MW0/MW3/MW6/MW10/MW19), `DEFAULT_N_SIMS` **20,000**, `SEED` **20260611** |
| Feasibility census | `reports/evidence/widening_parity_feasibility.json` (committed, byte-identical to the gitignored `data/epl/sim/evwiden_parity_feasibility.json`), SHA-256 **`07ee00d798cb0f01f29bc5bb5ba885c41e26d5494e9755c73a038a2777bad329`**, 18,128 bytes. **This document's table leg is scoped by it exactly as widening v3's was** — 32 priceable cells, 3 unpriceable — so it is a pin, not a citation |

Verify with:

```
shasum -a 256 data/epl/fit/walkforward_predictions.parquet \
              data/epl/fit/walkforward_ledger.jsonl \
              data/epl/matches.parquet epl/config_frozen.json \
              reports/evidence/widening_parity_feasibility.json \
              reports/evidence/widening_per_fixture.csv
```

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
| E1-informed feature cache | `data/epl/fit/cache_e1/` | the run |
| match-leg run directory | `data/epl/fit/lowerdiv/` | the run |
| table-leg run directory | `data/epl/sim/lowerdiv/` | the run |

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
  `epl/fit.py:88-91` records that the promoted seed was worth **0.0030 RPS — the
  largest single configuration effect ever measured on this data.**
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

**THE PIN.** The population is **not derived by this experiment**. It is the
widening run's population, taken as data:

* the **85 thin fixtures** are exactly the 85 rows of the committed
  `reports/evidence/widening_per_fixture.csv`, identified by their `key` column;
* "thin" means `e_min < 10.0` computed on the **E0-only** archive at
  `323aa54af0…` — the same `e*`, the same recipe, the same archive, the same
  fixtures;
* the **62 week blocks** and the **6 seasons** are that file's own `block` and
  `season` columns; the season split is **26 / 11 / 12 / 12 / 12 / 12**
  (2019/20 … 2024/25) and the block-size distribution is 46 blocks of 1, 10 of 2,
  5 of 3, 1 of 4 — all re-derived from the committed CSV by the harness, never
  typed in;
* the freeze block pins the 85 keys, the 62 block labels and the 6-season split
  by canonical digest, **and additionally pins the 85 keys equal to widening v3's
  own frozen membership digest
  `38d18d4d96b4eed0391d167d1bf7be6b95de83db6f8fda2846ad97c3fb368d5a`** — computed
  through `epl.evwiden`'s own canonical serialiser, imported read-only, so the
  comparison is against that document's serialisation and not against a
  re-invented one. A reader can then check that this experiment's population is
  that experiment's population and not a look-alike. If the two digests cannot be
  made to agree, the discrepancy is published before the freeze and this
  document does not run.

`PopulationRederived` (§7.1) fires if any code path computes `e` on a frame that
is not the pinned E0 archive, or derives the thin set from anything but the
committed CSV. **The enforcement is architectural first and procedural second:**
E1 lives in a separate parquet and a separate store root, so
`effective_evidence(cutoff, e0_played)` is unchanged **by construction**.

**The new `e` is a headline secondary and decides nothing.** For every one of the
85 fixtures and every club-cutoff cell of §3.1, the E1-informed `e` is computed
and published beside the E0-only `e`. "The rule dissolved the thin population" is
the most interesting number this experiment can produce, and it must not look
like a discovery made after the fact. It is preregistered as a report, here,
before any fit.

### 0.6 The E1 acquisition — a named, authorised, read-only-to-the-model pass

The second-tier archive does not exist. It is acquired **before the freeze**, by
a pass authorised here by name (§8.2 pass A), and the acquisition is
**read-only to the model**: it fetches, parses, validates and registers, and
**no fit, no store build, no simulation and no estimand touches it until after
the freeze commit.**

**What it acquires.** football-data.co.uk's E1 (EFL Championship) season files
for `1415`–`2526` — the same twelve season codes `epl.fetch.SEASON_CODES`
already holds, so every promoted club's second-tier history is covered on the
same window as the pinned E0 archive. Expected volume 12 × 552 = **6,624**
matches against E0's 4,560: the training set grows **≈ 2.45×** and the team
index from **29** at the 2019/20 opener and **35** at the 2026/27 opener —
both measured read-only from the pinned E0 archive as the distinct
`home_key ∪ away_key` of played matches dated before the cutoff — to roughly two
and a half times those. **The exact E1 club count is NOT estimated here**: the
acquisition pass measures it and publishes the census (§8.2 pass A), and every
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

**Six blockers stop E1 flowing through the E0 chain unchanged. Each gets a ruled
remedy here, and none of them edits a protected module.**

| # | blocker, with its citation | THE RULING |
|---|---|---|
| **B1** | `epl/fetch.py:31` `BASE_URL` and `:82` `raw_path` hardcode `E0` | `epl.lowerdiv.fetch_e1` composes its own URL and its own `raw_path` → `data/epl/raw/E1_{code}.csv`. `epl/fetch.py` is not edited; its cache-first, hash-pinned discipline is reimplemented in the new module with the same semantics (once cached, never re-downloaded; a byte change raises) and a committed test asserts the two paths never collide |
| **B2** | `raw/provenance.json` is keyed by `season_code` alone (`epl/fetch.py:174`), so an E1 record would **overwrite** the E0 record for the same season | E1 provenance goes to a **separate sidecar**, `data/epl/raw/provenance_e1.json`, keyed **`{division}_{season_code}`** (`E1_1415`, …). `raw/provenance.json` is not opened for writing on any path of this experiment. A committed test asserts the two files' key sets are disjoint and that the E0 sidecar's bytes are unchanged across the acquisition |
| **B3** | `epl/schema.py:52-53` `TEAMS_PER_SEASON = 20` / `MATCHES_PER_SEASON = 380`; `epl/validate.py:85-109` asserts 380 matches, 20 clubs, 19 opponents each. E1 is 24 / 552 / 23 | The E1 validator is a **division-parameterised copy** in `epl/lowerdiv.py` at (24, 552, 23), applying the identical check list. `epl/schema.py` and `epl/validate.py` keep their E0 constants and their E0 callers unchanged. A season that fails any check **refuses**; it is not dropped and it is not repaired |
| **B4** | `epl/teams.py` holds **36** registered clubs and **97** indexed spellings (measured); every Championship-only club resolves to `None` | The registry gains an entry per E1 club **before any fit**, as data, in `epl/teams.py` — the one file outside the write set this document touches, and it is touched because a second registry would be a second source of truth for club identity, which is precisely the defect §8.9 exists to design out. `_build_index` (`epl/teams.py:109-121`) already refuses a fold collision at import, so a Championship spelling whose fold collides with a registered one **blocks everything at import time**, loudly. The acquisition pass therefore **enumerates every E1 spelling and its fold BEFORE the registry is written**, and publishes the enumeration (§8.2). A committed test re-resolves the pinned E0 archive's `home_team_raw` / `away_team_raw` through the enlarged registry and asserts **every E0 key is unchanged** |
| **B5** | **THE PHANTOM-CLUB HARD FAILURE.** `epl/fit.py:157-158` does `played["home_key"].astype(str)`, so a null key becomes the literal string `"None"` and **every unregistered Championship club silently merges into one mega-club with its own attack and defence, and the fit looks healthy.** Unreachable today (all 35 observed E0 spellings resolve); live the instant E1 lands | `epl/fit.py` is PROTECTED and is **not edited**. Instead: **a null key must REFUSE, never stringify.** `epl.lowerdiv.to_store_frame` raises **`PhantomClub`** on any null `home_key` or `away_key` — naming the season, the date and the raw spelling — and only then delegates to `epl.fit.to_store_frame` for the projection, so there is exactly one projection and the refusal strictly precedes it. `epl.lowerdiv.build_store_e1` refuses on the combined frame before calling `epl.fit.build_store(frame, root=…)`. **Two committed tests, both mandatory:** one asserts `PhantomClub` fires on a synthetic frame with one null key; the other asserts that `epl.fit.to_store_frame` fed the same frame *still* produces the string `"None"` — the hazard is documented as live in the protected module and closed by refusal upstream, not by a fix we may not make. In addition the E1 build is **gated** on `manifest_e1["issues"] == []` and on an empty unresolved-spelling list in `team_name_mapping_e1.json` |
| **B6** | `epl/parse.py:145` `_match_id = sha256("{season_code}\|{date}\|{home_key}\|{away_key}")[:16]` carries no division, and the two archives merge into one store keyed on `match_id` | E1 ids are composed by a **new recipe used only for E1 rows**: `sha256("{division}\|{season_code}\|{date}\|{home_key}\|{away_key}")[:16]`. E0 ids are untouched and byte-identical. A committed test asserts the E0 and E1 id sets are **disjoint** on the built archives, and `E1Leak` fires if an E1 id is ever found in an E0 artifact |

**What the acquisition publishes, in this document, BEFORE the freeze block is
rendered** (§8.2, appended as a dated §8.10 note, and refused as a freeze
precondition if absent): the twelve fetch records with URL, byte size, SHA-256
and fetch time; the per-season validation report (row count, club count,
opponent counts, unplayed count) with every failure named; the **complete
distinct-club census and spelling set** with each spelling's index fold and the
collision check's result; the count and identity of any unmapped name; the E1
goal rate against E0's, measured; and the E1 archive's SHA-256, row count and
byte size, which the freeze block then pins.

**If the acquisition fails any of its own checks, this preregistration is not
run.** A season that will not validate is not silently excluded: §10 makes
dropping one an invalidation, and the remedy is a new document scoped to what the
source actually publishes — the same remedy widening v2 pre-stated and then had
to take.

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
   estimate of its E1 attack, and the fixed offset δ (§2.2) prices the *centre*
   of the league gap but not its *dispersion*. If the treatment worsens the 85
   thin fixtures, that is the hypothesis this bullet names, and the result
   document must say so in these words rather than attribute the sign to noise.
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
  estimand's shape, the resampling, three of the five gates and the table
  census — because direct comparability with `−0.00413` is the point. §6.4 is
  the honest account of what that comparability costs in power.

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
selects nine columns and drops everything else.

**The write set is closed** (§8.3): all code lands in `epl/lowerdiv.py` and
`epl/tests/test_lowerdiv.py`, plus registry data in `epl/teams.py` under B4's
ruling. `src/`, `scripts/`, `site/`, `tools/`, `config/`, `.github/`,
`epl/simretro.py`, `epl/simmetrics.py`, `epl/leaguesim.py`, `epl/table.py`,
`epl/particles.py`, `epl/fit.py`, `epl/walkforward.py`, `epl/evwiden.py`, the
season ledgers and the pinned corpus are **not written**.
`PYTHONPATH=src scripts/oa_lock.py` must print `LOCK VALID` after every commit
this work produces — checked, not assumed.

### 2.2 THE CALIBRATION RULING

`epl/anchor.py:114-122 AnchorState.z` **raises `KeyError` for any club with no
rating**, and `epl/dcfit.py:261-266` calls `state.elo_z(teams)` on the whole
panel team set. Adding the Championship clubs to that set — however many the
acquisition pass finds — therefore raises on the first fit unless every
second-tier club has a rating on the E0 z-scale. The
calibration is not decoration; it is the thing that makes the fit run.

#### PRIMARY — (a) a fixed league-strength offset, δ = −75.0, frozen by citation

> **The two divisions' centres are exactly `δ = −75.0` rating points apart, and
> every crossing in either direction is priced by that one constant.**

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
   r_E0(t, C)  =  ( r_E1(t, C) − mean_E1(C) )  +  ( mean_E0(C) + δ )
   ```

   where `mean_E1(C)` and `mean_E0(C)` are the two divisions' means over the
   clubs that completed the most recent season of each division before `C` —
   **exactly the `division_mean` `epl/elo.py:361` already computes**, on each
   archive separately. A club's position *within* its own division is preserved
   exactly; the division's centre sits δ below the top flight's.
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

   | arrival at an E1 season boundary | classification | seed |
   |---|---|---|
   | in the previous E0 season, not the previous E1 season | **relegated from E0** | `mean_E1(C) − δ` = `mean_E1 + 75` |
   | in neither previous season | **arrived from below (League One)** | `mean_E1(C) + δ` = `mean_E1 − 75` — `epl.elo`'s own rule, unchanged |
   | in the previous E1 season | **continuing** | `mean_E1 + carryover · (r − mean_E1)`, `carryover = 1.0` — `epl.elo`'s own rule, unchanged |

   And on the E0 side, which this experiment does **not** touch, a club promoted
   from E1 keeps entering at `mean_E0 + δ`: `epl.elo`'s existing promoted seed,
   unchanged, no new rule. **One constant, δ = −75.0, both directions, no second
   parameter** — the relegation seed is the same number with its sign read the
   other way, which is the arithmetic identity of "the centres are 75 points
   apart."

   **A committed test asserts the classification against the two archives**: for
   every E1 season boundary after the first, the *relegated* set equals
   `E0(prev season) − E0(this season)` computed from the pinned E0 archive's own
   memberships, and the *arrived-from-below* set is disjoint from it. The first
   E1 season (2014/15) has no boundary and every club starts at
   `initial_rating`, exactly as `epl.elo`'s first-season branch already does.
   A club the two archives place in both divisions in one season, or an arrival
   the rule cannot classify, raises **`LadderBoundaryMismatch`** and stops the
   ladder; it is not repaired silently and it is not defaulted to either seed.
4. **δ is NOT re-estimated, and the refusal is in the law because the code cannot
   catch it.** Estimating δ from the ~66 promotion/relegation crossings in the
   twelve-season window would read outcomes inside the scoring window and make δ
   a fitted parameter wearing a hyperparameter's name. `epl/windows.py:74-87
   assert_tuning_only` exists to catch exactly that — **and it keys on season
   strings, so E1 rows carrying the label `"2019/20"` pass through it
   undetected.** The guard cannot see this leak. The refusal is therefore
   preregistered: **δ = −75.0, from `epl/config_frozen.json`'s `chosen`
   block, is not swept, not tuned, not re-derived, and not sensitivity-tested as
   a deciding quantity.** A future document that fits δ must say its choice was
   informed by these numbers and carries exploratory standing only.

**Where δ comes from and what that is worth.** It is the repository's existing,
data-chosen estimate of the league gap in Elo points: tuned on 2014/15–2018/19
only, then frozen, and worth 0.0030 RPS — the largest single configuration effect
ever measured on this data (`epl/fit.py:88-91`). Its live arithmetic is on the
record at `epl/liveanchor.py:11-16`: Hull's stale rating 1398.9, Ipswich's
1411.1, division mean 1594.6, promoted seed 1594.6 − 75 = 1519.6.

**What δ does and does not do.** It is a *rating* offset feeding a *prior mean*
at `k_att = k_def = 0.6`. It shifts the prior, not the likelihood. If the E1 rows
in the likelihood disagree with δ, the posterior overrides it — which is the
honest reading of "give the club real evidence," and is stated here so it cannot
be presented later as either a bug or a subtlety discovered after the fact.

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

**The acquisition pass measures the E1 goal rate against E0's and publishes it
(§0.6).** If it differs materially, that is a finding for a later
preregistration, and this document does not pre-authorise one.

### 2.3 The arms and the estimand

**Both arms are two real fits at the same opening.** At each of the **212 block
openings of the pinned corpus** — every one, not a subset; §4.4 and §3.2 are why
— two fits run through the identical pipeline
(`freeze.frozen_wcmodel_config()`, seed 20260611, `epl.dcfit.fit_epl` with
`fast_panel=True`), differing in exactly two inputs:

* **Arm B — `dc_native`** — fit against the **E0-only** store root
  `data/epl/fit/store/` with the incumbent `epl.anchor.Anchor` and the E0 feature
  cache. This is the published object, refit.
* **Arm A — `dc_e1`** — fit against the **E1-informed** store root
  `data/epl/fit/store_e1/` (E0 ∪ E1) with §2.2's cross-league anchor and the E1
  feature cache `data/epl/fit/cache_e1/`. Only the block's E0 fixtures are
  predicted.
* **The delta** — `rps(Arm A) − rps(Arm B)` per fixture, `epl.score.rps` on the
  corpus's `y`, rounded by the same `round(v, 8)`.

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

> **THE ESTIMAND: the mean paired RPS delta, `dc_e1` minus `dc_native`, over the
> 85 pinned thin fixtures of §0.5. Negative means the second-tier evidence
> helps.**

* **The population is fixed at 85 and no fixture may be dropped.** It is
  §0.5's pin and it is not re-derived. **All 85 move** — there are no structural
  zeros (§1.4), so the estimand's sign is not a known multiple of any subset's.
* **The statistic** — the pooled mean over the 85 deltas.
* **The primary interval** — `epl.score.block_bootstrap_ci`
  (`epl/score.py:193`) on the 85 deltas, blocks = the pinned **62** `(season,
  ISO week)` labels, `B = 10,000`, percentile, `alpha = 0.05`, resampling seed
  **20260814**.
* **The season interval** — same function, same `B`, same seed, blocks = the
  **6 seasons**. Its job is to refuse a result carried by one season, and the
  risk is quantified now: 2019/20 holds 26 of the 85.
* **The collateral estimand** — the mean over all **2,280** fixtures, with its
  own 212-block week interval and its own 6-season interval. Unlike under
  widening this is **not** the estimand × 85/2280; every fixture moves, so it is
  a genuine second number, and §4.4 makes it a gate rather than a note.

**Every deciding constant is frozen and is not overridable.** No CLI flag,
keyword or environment variable may pass a different `B`, `alpha`, block
definition, resampling seed, `n_sims` (20,000), simulation seed (20260611),
chunk size, `MC_BOOT` (2,000), `MC_SEED` (20260831), `K` (200, §5.4), `SHARDS`
(4), `δ` (−75.0), `γ` (0.5) or population into any deciding computation. §8.6's
public-surface closure is where that sentence is made mechanical: a production
path **RESOLVES** these from the modules §0.1 pins them in and carries no
parameter for them at all.

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
| **the post-freeze experiment** | **592** | **96** |

**Wall clock, computed from measured rates and stated before the freeze.** The
E0 cold rate is **57.24 s/fit** (`data/epl/fit/single_fit.json`, cutoff
2025-01-25, 4,019 training matches, 35 teams). The E1-informed fits train on
≈ 2.45× the rows with ≈ 2.5× the team parameters; the budget assumes **150 s/fit**
(2.6× the measured cold rate) and the acquisition pass's single-opening exercise
(§8.4 step 2) measures the realised rate and publishes it. At ≈ 1.24 minutes per
20,000-season simulation implied by the retro's recorded scale:

| leg | seconds | hours |
|---|---:|---:|
| 212 E0 fits at 57.24 s | 12,135 | 3.4 |
| 212 E1 fits at 150 s | 31,800 | 8.8 |
| 62 γ fits at 150 s | 9,300 | 2.6 |
| canary (8) + single-opening (2) | 1,036 | 0.3 |
| parity oracle: 32 fits + 32 simulations at ≈ 74 s | 4,213 | 1.2 |
| table: 64 fits + 64 simulations | 11,393 | 3.2 |
| **total** | **≈ 69,900** | **≈ 19.4** |

**Budget ≈ 20 hours, bounded by 30.** Every E1 featpanel key is a cold miss on
the first run (the key hashes the `< cutoff` result set,
`src/wcmodel/data/features.py:315-412`), so the warm-rate arithmetic that made
the predecessor's 78 openings cost twelve minutes does not apply here.

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

* **THE DISSOLVED POPULATION (§0.5's headline secondary).** For each of the 85
  fixtures: `e_min` on the E0 archive (the pinned value), `e_min` on the
  E1-informed archive, and the ratio. Plus the club-cutoff census: how many of
  the 4,240 cells of widening v3 §0.4 have `e < 10` under each archive. Plus the
  Hull / Coventry / Ipswich panel at the 2026/27 opener under both archives.
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

**The control runs first, and not one Arm-A prediction is produced until it
passes.** A mismatch is most likely archive drift and is a STOP
(`ControlMismatch`) either way. Max and mean `|Δp|` are reported even when zero.

The demand is exact for the reason the predecessors proved: the seed does not
vary by cutoff, and a fit is a pure function of `(cutoff, store, frozen config)`.
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
store, the treatment fit against the E1-informed store; **identical particle
draws and identical RNG streams**, so the arms are CRN-paired at the sampler and
the only divergences are the posterior and the provisional set. D2 stays
static-within-fit and D12 stays per-fixture — the two standing open owner rulings
this experiment does not touch.

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
3. **"E1-informed clubs" is a REPORTED field, not a gate population.** For each
   cell, the clubs whose E1-informed evidence at that cutoff is non-empty while
   their E0-only `e` is below 10.0 — computed from the **pinned E0 archive** by
   the §0.3 recipe and from the E1 archive's date index, at the scheduled cutoff,
   predicate strict `<`, values at 2 dp. It is published per cell and per label
   so a reader can see where the treatment had the most to work with. **It
   decides nothing and no gate is taken over it.**

**The exact schedule is a pin, tuple by tuple**: `FROZEN_TABLE_SCHEDULE`,
thirty-two `(season, cutoff_label, cutoff date, E1-informed clubs)` tuples,
recomputed by §8.2's read-only pass from the pinned artifacts and the acquired E1
archive, and frozen in the harness the freeze commit hashes, **together with the
per-label CELL census `{MW0: 5, MW3: 6, MW6: 7, MW10: 7, MW19: 7}`**. An
aggregate census alone permits a bogus same-label season or a cutoff moved by a
week; the schedule does not. A departure from either is `MembershipMismatch`, and
it is asked on every deciding path — `table_cells`, `run_parity_oracle`,
`run_table`, `score_table` and `table_gate` each call it.

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
   gate; §10 makes adding one an invalidation.
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

### 4.1 The rule

> **ADOPT the E1-informed arm (as a shadow arm, §4.6) if and only if ALL FIVE:**
>
> **(i)** the point estimate of the estimand is `Δ ≤ −0.0010` RPS over the 85
> pinned thin fixtures, **and**
>
> **(ii)** the 95% `(season, ISO week)` block bootstrap CI (62 blocks) excludes
> zero — its upper bound is strictly `< 0`, **and**
>
> **(iii)** the 95% season block bootstrap CI (6 blocks) also excludes zero,
> **and**
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
> > MW6 mean is `> 0` **and** the lower bound of its 95% season-block interval
> > (7 blocks, §5.3) is `> 0`.
>
> **and (v)** the **collateral gate** holds, in two parts, both required:
>
> > **(v-a)** the mean paired RPS delta over **all 2,280 corpus fixtures** is
> > **≤ +0.000075**, **and**
> >
> > **(v-b)** gate (v) **fails** if that mean is `> 0` **and** the lower bound of
> > its 95% 212-block week interval is `> 0`.
>
> **Otherwise `dc_native` stands unchanged, Hull's forecast included.**

All five are required and none is sufficient. (i)–(iii) are the benefit gate;
(iv) and (v) are the do-no-harm gates. Gate (iv) may additionally be
**UNRESOLVED** under §5.4's precision regime; UNRESOLVED blocks adoption and can
never grant one.

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

**What this experiment may claim on a pass at all five gates, exhaustively:**

1. that on **85 pre-specified thin-evidence fixtures** of the pinned corpus,
   training on the second-tier archive changed the mean paired RPS by the
   reported amount, with the two reported intervals, at the power §6 states for
   the realised SD; and
2. that on the **2,280 fixtures of the whole corpus** the mean paired RPS delta
   did not exceed `+0.000075` and was not resolvably positive; and
3. that on **all 32 pre-specified table cells** the paired ΔTRPS did not exceed
   `+0.0002` at MW6 or at any of MW0, MW3, MW10 and MW19, and that the MW6 mean
   was not resolvably positive.

**What it may never claim, on any result:** a corpus-level accuracy improvement;
a quantified product value; that the improvement is attributable to better
parameter estimates rather than to the cold-start path dissolving (§1.2 bullet 2);
anything about Hull specifically at match level (§11 — one analogue, and it is in
the table leg); anything about the joint law, which no table metric here sees;
anything about δ other than the frozen −75.0; or anything about a second-tier
archive other than the twelve E1 seasons §0.6 acquires.

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

**The point gate (v-a) does the work; the significance clause (v-b) can only
refuse.** (v-a) fires on the point estimate alone and needs no power. (v-b) is a
second, stricter condition, and §6.3 measures exactly what it can resolve — a
harm of `+0.00135` to `+0.00627` depending on scenario and block correlation.
**Unresolvable harm therefore passes (v-b)**, which is the honest shape for a
do-no-harm gate and is stated before the run so that a pass on (v) cannot later
be read as a demonstration of no harm.

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
primary, not at a different δ, not by dropping 2019/20, not by re-deriving the
population under the E1 archive, not by extending the corpus into 2025/26, not by
a one-sided interval, not by a larger `n_sims`, not by adding a third division,
and not by a bar rewritten after the number. Each appears in §10.

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
* **P5 — the unanimity rule, frozen.** Draw `K = 200` independent resample
  streams (`numpy.random.default_rng(MC_SEED + 1 + j)` for `j` in `0…K-1`, each
  running §5.2's whole `MC_BOOT` loop's *point* evaluation only: one `picked`
  per stream, the gate recomputed on it). Gate (iv)'s PASS/FAIL verdict must be
  **unanimous across all K streams**. A single dissent makes gate (iv)
  UNRESOLVED. `K`, the seed offset and the derivation are frozen and are not
  overridable; a scale comparison against `mc_se_mw6` is **not** a substitute and
  §10 makes replacing P5 with one an invalidation.

**Eight conditions, no ninth.** The evidence file carries all eight by name with
their computed values and a `resolved: bool`. The count is eight and not the
predecessor's seven because §3.3 makes MW19 a deciding label, and a precision
regime whose condition list did not grow with its gate list would be a regime
with a hole in it.

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

---

## 6. The power analysis

§0.5 counted where the treatment *bites*, which is support. This section asks
whether the three conjunctive benefit gates can jointly pass at the effect this
experiment exists to test, and answers before any delta exists.

### 6.1 The scenarios, frozen blind

| scenario | paired SD | source |
|---|---:|---|
| **A — widening-realised, thin** | **0.022751278102833457** | the widening run's realised paired SD over **these same 85 fixtures** (`reports/evidence/widening.json` → `estimand.sd`). The optimistic floor — and it is optimistic for a named reason: 33 of its 85 rows were exact zeros with zero variance |
| **B — widening-realised, treated** | **0.028887934876731913** | the same run's realised SD over the 52 fixtures that actually moved (`power.realised.sd_paired_treated`). The like-for-like scale for a population in which every fixture moves |
| **C — doubled-fit scale** | **0.040854278…** = B × √2 | **an extrapolation, labelled one.** Under widening both arms came from ONE posterior, so the sampler's own noise cancelled exactly in the pair; here the arms are two independent fits and the sampler noise enters twice, independently. √2 is the independent-addition scale. It is not measured and it is not claimed to be |

A power analysis that tests only optimistic variances is not a power analysis.

### 6.2 The construction, frozen

* **Structure:** the 85 pinned fixtures in their 62 pinned week blocks and 6
  seasons, **recomputed by the harness from the committed
  `reports/evidence/widening_per_fixture.csv`, never typed in**. Row order:
  ascending `key`, stable mergesort. Block order: first appearance in that
  sequence. **All 85 are treated** — there are no structural zeros (§1.4).
* **Noise:** for fixture *i* in week block *b*, the delta is
  `δ + s · ( sqrt(ρ)·u_b + sqrt(1−ρ)·z_i )` with `u_b` and `z_i` independent
  standard normals — an equicorrelated Gaussian whose correlation scope is **the
  week block and nothing else**. Season correlation is not modelled and is not
  claimed; ρ ∈ {0, 0.5} brackets it.
* **Consumption order, frozen:** per (scenario-independent) stream,
  `u = rng.standard_normal((R, n_blocks))` **then**
  `z = rng.standard_normal((R, n_fixtures))`. This is frozen because it is the
  part the predecessor's v1 left unfrozen, which made its stream unrecoverable
  and its numbers unreproducible (widening v3 §6.4).
* **Replicates:** `R = 2,000`. A **fresh** `numpy.random.default_rng(20260830)`
  is constructed for each ρ, so both ρ values consume the same underlying
  stream in the same order; ρ is applied to the draws, not to the seed. The
  order is ρ = 0.0 then ρ = 0.5, and it is frozen because the construction is
  otherwise identical and an unfrozen order would leave the two rows
  interchangeable in name only.
* **The collateral leg's structure** (gate (v), §6.3's third table) is the same
  construction over the corpus: the 2,280 rows of the pinned corpus parquet in
  ascending `match_id`, stable mergesort, its 212 `block` labels in first-
  appearance order, and its 6 seasons — recomputed by the harness, never typed
  in.
* **Gates:** the three deciding benefit gates exactly as §4.1 states them, using
  `epl.score.block_bootstrap_ci` at `B = 10,000`, `alpha = 0.05`, seed
  **20260814**, on the 62 week blocks and on the 6 seasons.

**THE EQUIVARIANCE IDENTITY, and why this power simulation is exact rather than
approximate.** `epl.score.block_bootstrap_ci`'s resample indices depend only on
`(seed, n_boot, n_blocks)` and not on the data
(`epl/score.py:222-223`: `rng = default_rng(seed); draw = rng.integers(0,
n_blocks, size=(n_boot, n_blocks))`), and its statistic is
`sums[draw].sum(axis=1) / sizes[draw].sum(axis=1)` — **affine in the data**.
Therefore, for `s > 0`,

```
block_bootstrap_ci(δ + s·ε, …)  =  δ + s · block_bootstrap_ci(ε, …)
```

exactly, in both endpoints. Verified read-only at three `(δ, s)` points to
`≤ 1.8e-18` absolute. Consequently all three gates are **exactly linear in δ**:

```
gate (i)   passes iff  δ  ≤  −0.0010 − s·mean(ε_r)
gate (ii)  passes iff  δ  <  −s·hi_week(ε_r)
gate (iii) passes iff  δ  <  −s·hi_season(ε_r)
```

so the whole power curve, at every δ and every scenario, is computed in closed
form from **R triples** `(mean, week-CI upper, season-CI upper)` of the
**standardised** draw. Common random numbers are exact across δ *and* across
scenarios, and **the power curve is exactly monotone in δ rather than monotone up
to Monte-Carlo error.** A committed test must assert the identity against direct
evaluation at three named `(δ, s, ρ)` points to `1e-15`; absent that test the
closed form is removed, not trusted.

**The MDE search grid and interpolation, frozen.**

* **Grid:** `δ ∈ {0, −0.0002, −0.0004, …, −0.0200}` — 101 points, step `2e-4`.
* **Power at a grid point:** the fraction of the R replicates at which **all
  three** benefit gates pass.
* **MDE80:** scanning from `δ = 0` downward, the **first** adjacent pair
  bracketing power 0.80, linearly interpolated in δ. **Tie rule:** a grid point
  whose power is exactly 0.80 **is** the MDE, no interpolation. **Exhaustion
  rule:** if 0.80 is never reached, the MDE is reported as `< −0.0200` with no
  interpolated value and the table says so rather than extrapolating.
* **Named evaluation points**, each its own evaluation at the same stream, never
  interpolated from the grid: the bar `δ = −0.0010`; **the predecessor's measured
  effect `δ = −0.00412976353895183`**; and twice the bar `δ = −0.0020`.

### 6.3 The sizing table

**Provenance of these numbers, stated exactly.** They are the output of a
**read-only sizing pass** run on 2026-08-30 at the constants above, which fitted
nothing, simulated no season and wrote nothing. **They are not yet the committed
implementation's numbers, because no harness exists.** §8.3 makes reproducing
them a freeze precondition: `python -m epl.lowerdiv --power` must produce this
table exactly, and `--freeze-block` refuses to render otherwise. Because §6.2
freezes the consumption order, the block order, the row order and every seed, the
stream is fully determined by this document and reproduction is attainable — that
is the direct lesson of widening v3 §6.4, where an unfrozen consumption order
made the predecessor's v1 numbers unrecoverable.

| scenario | ρ | paired SD | power at the bar | **power at −0.00413** | power at 2× bar | joint MDE (estimand) | ratio to the bar | **ratio to −0.00413** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A widening-realised, thin | 0.0 | 0.022751 | 0.065 | **0.366** | 0.119 | −0.007196 | 7.20× | **1.74×** |
| B widening-realised, treated | 0.0 | 0.028888 | 0.054 | **0.258** | 0.092 | −0.009126 | 9.13× | **2.21×** |
| C doubled-fit | 0.0 | 0.040854 | 0.047 | **0.146** | 0.070 | −0.012923 | 12.92× | **3.13×** |
| A widening-realised, thin | 0.5 | 0.022751 | 0.053 | **0.301** | 0.102 | −0.008376 | 8.38× | **2.03×** |
| B widening-realised, treated | 0.5 | 0.028888 | 0.044 | **0.207** | 0.079 | −0.010620 | 10.62× | **2.57×** |
| C doubled-fit | 0.5 | 0.040854 | 0.040 | **0.124** | 0.059 | −0.015027 | 15.03× | **3.64×** |

**Per-gate pass rate at δ = −0.00412976, which identifies the binding gate:**

| scenario | ρ | gate (i) | **gate (ii) — week** | gate (iii) — season | joint |
|---|---:|---:|---:|---:|---:|
| A | 0.0 | 0.899 | **0.415** | 0.518 | 0.366 |
| B | 0.0 | 0.847 | **0.293** | 0.400 | 0.258 |
| C | 0.0 | 0.765 | **0.170** | 0.274 | 0.146 |
| A | 0.5 | 0.861 | **0.339** | 0.442 | 0.301 |
| B | 0.5 | 0.802 | **0.234** | 0.345 | 0.207 |
| C | 0.5 | 0.724 | **0.144** | 0.241 | 0.123 |

**The collateral gate's SIGNIFICANCE CLAUSE (v-b), sized on the 2,280 fixtures /
212 blocks / 6 seasons of the pinned corpus, same construction.** Gate (v-a) is a
**point** gate — it fires on the point estimate alone and needs no power; at a
true corpus effect exactly equal to its `+0.000075` bar it refuses about half the
time, by the same structural fact §6.3 states for gate (i). The table below sizes
only (v-b), which is the clause that can refuse a *resolvable* harm:

| scenario | ρ | P((v-b) fires) at a true effect of +0.000075 | (v-b)'s harm MDE80 | benefit-resolution MDE80 (for the record) |
|---|---:|---:|---:|---:|
| A | 0.0 | 0.030 | +0.001349 | −0.001382 |
| B | 0.0 | 0.028 | +0.001712 | −0.001757 |
| C | 0.0 | 0.028 | +0.002418 | −0.002481 |
| A | 0.5 | 0.029 | +0.003491 | −0.003598 |
| B | 0.5 | 0.029 | +0.004431 | −0.004568 |
| C | 0.5 | 0.028 | +0.006267 | −0.006464 |

**A structural fact, so no one reads the tables as a defect in the simulation.**
Gate (i) is a threshold **at** the bar, not a test against zero, so at a true
effect exactly equal to the bar the probability of clearing it is about one half
whatever the variance is. **An 80%-power MDE equal to the bar is unattainable by
construction**, at any SD; the honest quantity is the ratio, which is what the
tables report.

### 6.4 THE RULING — what `n` buys, and what it cannot

**Nothing in §4 moves.** The bar stays −0.0010, the CIs stay, the population
stays the pinned 85, δ stays −75.0, γ stays 0.5, `n_sims` stays 20,000. What
changes is that this document says, before any delta exists:

> **THIS DESIGN IS UNDERPOWERED AGAINST THE VERY EFFECT ITS PREDECESSOR
> MEASURED.** At `δ = −0.00413` — the widening run's own point estimate on this
> same population — the three benefit gates jointly pass with probability
> **0.12 to 0.37**. The joint MDE is **1.74× to 3.64× that effect.** A miss is
> therefore substantially uninformative: **"no adoption" here means "not detected
> at this power", not "no effect", and the result document must say so in those
> words.**

**Gate (ii), the 62-block week interval, is the binding gate — the same gate that
decided the predecessor UNRESOLVED.** At `δ = −0.00413` gate (i) passes 0.72–0.90
and gate (iii) 0.24–0.52, while gate (ii) passes **0.14–0.42**. This is not a
coincidence and it is not fixable by this design: the week interval resamples 62
blocks, of which 46 hold exactly one fixture, so its effective sample size is the
block count and the block count is a property of *where thin fixtures occur*, not
of how many fits are run.

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
26.8× the fixtures and 3.4× the blocks. §6.3's third table sizes it: the
collateral leg resolves an effect of **±0.00135 to ±0.00248** at ρ = 0 and
**±0.0035 to ±0.0063** at ρ = 0.5. That is enough to refuse a *resolvable*
corpus-level harm and is **not** enough to demonstrate a corpus-level benefit at
the scale a thin-fixture effect of −0.00413 implies
(`−0.00413 × 85/2280 = −0.000154`, nine to forty times below what the leg can
resolve). **That asymmetry is why gate (v) is written as a do-no-harm gate and
not as a benefit gate**, and why the 212 openings are fitted at a cost of nine
extra hours: they buy the ability to refuse, the maximal identity control of
§3.2, and nothing else. The one thing they conspicuously do **not** buy is the
answer to the primary question.

**This is not a licence to re-run.** §4.5's refusal to re-litigate a miss is
unchanged. §6 is the reader's warning, frozen in advance, so the size of the null
cannot be argued about after it arrives.

### 6.5 The realised-SD obligation, on the result document

After the run, the **realised paired SD of the 85 deltas and of the 2,280
deltas** is reported, and **the joint-gate MDE is recomputed at the realised
thin-population SD** — the §6.2 construction re-run with `s` set to the realised
value, at the same `R`, the same seeds, the same grid and the same interpolation
rule, producing realised `power@bar`, realised `power@−0.00413`, realised
`MDE80` and realised ratios in the same columns as §6.3.

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
| **`PopulationRederived`** | the thin set is derived from anything but `reports/evidence/widening_per_fixture.csv`, or `e` is computed on a frame that is not the pinned E0 archive, or a recomputed population digest differs from widening v3's frozen `38d18d4d96…` |
| **`PhantomClub`** | any row reaching the store builder carries a null `home_key` or `away_key` — the refusal names the season, date and raw spelling and **precedes** the projection (§0.6 B5) |
| **`RegistryCollision`** | an E1 spelling's index fold collides with a registered one (raised by `epl/teams.py:109-121` at import), or re-resolving the pinned E0 archive through the enlarged registry changes any E0 key |
| **`LadderBoundaryMismatch`** | an E1 season-boundary arrival cannot be classified as relegated-from-E0, arrived-from-below or continuing by §2.2's rule; or a club appears in both divisions in one season; or the recomputed relegated set differs from `E0(prev) − E0(this)` on the pinned E0 archive |
| **`AcquisitionIncomplete`** | a season's E1 CSV is absent, fails its recorded digest, fails the (24, 552, 23) validation, or leaves an unmapped spelling |
| `MembershipMismatch` | a recomputed enumeration differs from §8.3's frozen digests — the 85 keys, the 62 blocks, the 6-season split, the 212 openings, `FROZEN_TABLE_SCHEDULE` tuple-by-tuple, or the per-label CELL census `{MW0:5, MW3:6, MW6:7, MW10:7, MW19:7}` |
| `PredicateMismatch` | an Arm-B fit's own provisional set ≠ the ledger's recorded `provisional_teams` at that cutoff |
| `EvidenceLeak` | a match dated ≥ its cutoff contributes to any `e(t, C)` |
| `CutoffLeak` | a training frame holds a match dated ≥ its cutoff, or a fixture appears in the fit that prices it — checked on **both** store roots |
| `CanaryFailed` / `EvidenceCanaryFailed` | `point_in_time_canary` fails on either store, or the direction canary proved nothing (§7.3) / either leg of the evidence canary fails |
| `ControlMismatch` | any of the 2,280 identity-control probabilities differs from the corpus at 8 dp (§3.2) |
| `TableIdentityBreak` | **any** cell's two arms' `sampler_digest`s are EQUAL (§3.3: every cell must change under this design); a parity comparison differs at any of the 32 cells; a cell simulated without a complete oracle; or a schedule field disagrees with `FROZEN_TABLE_SCHEDULE` |
| `TableMCImprecise` | §5.2's structural conditions — unequal per-particle season counts, unequal `n_particles` across deciding cells or between a cell's arms, a tally that fails either binding check of §5.1, or a tally file absent or failing its recorded digest |
| `FitFailed` / `UnpriceableFixture` / `ScoreMismatch` | as the predecessors define them, verbatim |
| `SchemaMismatch` / `RowConflict` | a ledger row lacks a required field / duplicate keys disagree on a non-volatile field |
| `ShardFailed` / `MergeIncomplete` | a shard exits non-zero or writes nothing / the merged key set is not exactly the pre-stated keys — not a superset, not a subset |
| `StoreNotBuilt` | a read-only pass required a point-in-time store and the store parquet is absent; the read-only accessor refuses and **never builds one** (§8.2) |
| `SequenceViolation` | a step of §8.4's frozen sequence ran without its predecessor's completion marker, or with a marker recorded under a different freeze commit |
| `FreezeStateUnverified` | the freeze/first-fit state could not be established from committed bytes and Git ancestry: the prereg blob is uncommitted, its commit is not an ancestor of HEAD, or its current bytes differ from that blob; a hashed file's bytes differ from the committed table; the recorded membership, schema or conformance digests do not match a fresh recomputation; the committed conformance table is not exactly §8.5's rows all green; a first-fit record names a different prereg blob; or the record and its append-only witness disagree |
| `FeasibilityRecordMismatch` | the committed census record is absent, fails its pinned digest, reports `completed: false`, or reports a priceable census that is not exactly these 32 cells |
| **`PathNotFrozen`** | any writer or reader resolves an artifact path that is not the one §8.9's single layout function returns (§8.9) |

**Thirty-four named refusals; thirty-five classes** counting the `LowerDivError`
base they all derive from. (`RecalError` above is a citation to the exit-code
convention, not a class of this harness.) `epl/tests/test_lowerdiv.py`'s two
inventory tests must name **thirty-four** in both their tuple and their set, so
that the "invents no refusal the document never wrote" test closes the inventory
exactly and a thirty-fifth named type is as much a failure as a missing one.

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
`ledger_sha256` · `delta_offset` (−75.0) · `gamma` · per-club `e` on the E0
archive at 8 dp · per-club `e` on the E1-informed archive at 8 dp · incumbent and
recomputed provisional sets · cold-start set · team-index size · `match_ids` ·
`probs` (8 dp) · `health` · `harness_sha256` · `harness_frozen` · `blas_threads` ·
`shard_id` · clocks.

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
runner is resumable per fit, keyed `cutoff|arm|seed|config_sha256`.

`harness_frozen` records **what the guard established**, never what a caller
asserted (§8.6).

### 7.3 The canaries

* **Results canary, TWICE.** `epl.walkforward.point_in_time_canary`, run once on
  the **E0** store and once on the **E1-informed** store, as a precondition
  **after** the freeze. `PASS: false` on either stops the run. Each performs four
  real fits (`epl/walkforward.py:490-495`), which is why §8.4 makes it step 1 and
  why §2.4 counts eight fits.
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
`reports/evidence/widening_per_fixture.csv`, or any artifact derived from them.

**The ancestry check is a mechanical obligation, not an assertion.** Before the
freeze commit, `epl/tests/test_lowerdiv.py` must carry a test that asserts,
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

**The no-fit clock.** Between this commit and the freeze commit, **no fit and no
season simulation of this document may run, anywhere, under any output
directory.** §10 makes one an invalidation. The one exception is stated by name
and it is not an exception to that rule: pass A acquires data and fits nothing.

**The authorised passes, authorised prospectively and by name. There are six.**

> **Pass A — THE E1 ACQUISITION.** The only pass that touches the network and the
> only pass that writes a new artifact before the freeze.
> `python -m epl.lowerdiv --acquire`. It fetches the twelve E1 season CSVs
> (cache-first, hash-pinned, refusing a byte change on a cached file), parses
> them under §0.6's B1/B2/B6 rulings, resolves club names under B4, validates
> under B3, refuses under B5, and writes exactly:
> `data/epl/raw/E1_{code}.csv` (12), `data/epl/raw/provenance_e1.json`,
> `data/epl/matches_e1.parquet`, `data/epl/manifest_e1.json`,
> `data/epl/team_name_mapping_e1.json`.
>
> **It is READ-ONLY TO THE MODEL.** It builds no store, constructs no Engine,
> imports no sampler, and calls nothing in `src/wcmodel/model/`. A committed test
> asserts that the acquisition path's import closure excludes
> `wcmodel.model.scoreline`, and the pass compares the E0 archive's bytes and
> mtime before and after and refuses if either moved.
>
> **It runs ONCE**, with a completion marker, and it publishes its record as a
> dated §8.10 note appended to this document **before** the freeze block: the
> twelve fetch records, the per-season validation table, the complete E1 club
> census and spelling set with each spelling's fold, the collision-check result,
> any unmapped name, the E1 goal rate against E0's, and the E1 archive's SHA-256,
> row count and byte size. **A freeze block may not render while that note is
> absent** (§8.3).
>
> **Registry order is binding.** The spelling enumeration is produced and
> published **before** the `epl/teams.py` entries are written, so that the
> registry is written against a measured list rather than a guessed one, and so
> that a fold collision is discovered on a list rather than at import time in the
> middle of a run.

* `python -m epl.lowerdiv --membership` and `--plan` — read the pinned corpus,
  the pinned E0 archive, the ledger, the committed widening per-fixture CSV and
  the acquired E1 archive; compute the 85 keys, the 62 blocks, the 6-season
  split, the 212 openings, `FROZEN_TABLE_SCHEDULE` and the per-label CELL census,
  and the digests §8.3 pins. **Neither reaches a store build:** the read-only
  store accessor opens an existing store parquet and raises `StoreNotBuilt` if it
  is absent — it never builds one.
* `python -m epl.lowerdiv --canary --no-results-canary --dir <scratch>` — §7.3's
  evidence and E1-isolation canaries, with any point-in-time store built in a
  `tempfile.TemporaryDirectory` and never under `paths.STORE_DIR` or the E1 store
  root.
* `pytest epl/tests/test_lowerdiv.py` — the synthetic corpora, the `@pinned`
  tests that re-derive this document's census, the power table, the membership
  and the table schedule, and §8.5's conformance scenario run.
* `python -m epl.lowerdiv --power` — reads only the frozen SDs and the frozen
  structure recomputed from the committed CSV, and must reproduce §6.3 exactly.
* `python -m epl.lowerdiv --freeze-block` — reads the pinned artifacts to render
  §8.3's commit rather than have a human transcribe digests.

**`--script` may not be run before the freeze commit, at any target**, and a
post-freeze launcher may not be generated with a caller-supplied interpreter or
command.

### 8.3 The freeze commit

This document is committed **before** the harness it binds. Then, in order:

1. **Pass A runs and publishes its note** (§8.2). No E1 archive, no freeze.
2. **The harness is written and audited** — `epl/lowerdiv.py` and
   `epl/tests/test_lowerdiv.py` are brought to implement **this document**, with
   seeded defects and canaries on synthetic corpora only. §8.5's conformance
   report must be green on behavioural predicates **and must be backed by an
   independent pytest artifact**, and an independent dual audit — one cross-model
   review and one in-tree adversarial seed audit — must report no blocking
   finding, **or the owner must adjudicate what it reported**, with the complete
   dissent published beside the law.
3. **A follow-up commit appends the freeze block to this document**, rendered by
   `--freeze-block`, carrying:

   * the **harness hash table** — file, line count and SHA-256 for each of
     `epl/lowerdiv.py` and `epl/tests/test_lowerdiv.py`, the SHA-256 of
     `epl/teams.py` after B4's registry addition, and the schema identifier
     `epl-lowerdiv-1`;
   * the **membership digests** — the 85 thin fixture keys, the 62 block labels,
     the 6-season split, the 212 fit openings, `FROZEN_TABLE_SCHEDULE` tuple by
     tuple, the per-label CELL census, and the three excluded cell keys — each
     serialised canonically and hashed, recomputed by the harness's own code from
     the pinned artifacts — **together with widening v3's own frozen thin-fixture
     digest `38d18d4d96…`, which the recomputed 85 must equal**;
   * the four pinned artifact digests of §0.1, `realised_config_sha256`, and
     **the E1 archive's SHA-256, row count, byte size and per-season club
     census**;
   * the SHA-256 and byte size of the feasibility census record, and **both
     paths that hold those bytes**;
   * the **enumeration of every pre-freeze pass actually run**, complete,
     including pass A with its date, its record and its digests;
   * the conformance report of §8.5, every row green, **together with the
     identity of the pytest artifact it was read from** — path, digest, test-id
     list and pass count;
   * §6.3's power table as the committed `--power` reproduced it.

   *If any hash differs at the time the run is executed, it is not the run this
   document preregisters.*

   **`--freeze-block` refuses to render** while any of the following holds, and
   the refusals are unconditional — there is no bypass parameter and no
   caller-supplied substitute for any of these inputs:

   * pass A's dated note is absent from this document, or the E1 archive is
     absent or fails the digest the note recorded;
   * the conformance report is **not exactly §8.5's rows**, or any row is red or
     absent. **A nonempty all-green SUBSET is a refusal**, not a pass: a renderer
     that accepted any green subset would render over a report that had dropped
     the rows it could not satisfy, and a review found that exact acceptance in
     the predecessor's harness;
   * the report was not **produced by and cross-checked against** §8.5's
     committed pytest artifact — same test ids, all passing, same count;
   * §7.4's ancestry test is absent, or §6.3's power table is unreproduced;
   * the feasibility census record is absent, fails its pinned digest, says it
     did not complete, or reports a priceable census that is not exactly these
     32 cells;
   * the recomputed 85-fixture digest is not equal to widening v3's
     `38d18d4d96…`.

4. **Only then does the first real fit of this document run**, and it runs as
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
UTC time, the freeze commit under which it was written, the harness file digests
at that moment, and — per the predecessor's adjudicated fix — **`products`, a map
from repo-relative path to the SHA-256 of what that file held when the step
finished.** `assert_sequence_marker_wellformed` **re-hashes every product against
the bytes on disk on every read**: a marker is a claim that a step produced
something, and a claim about a file that is gone, or is no longer that file,
unlocks nothing. A marker written under a different freeze commit is not a marker
for this run.

**Markers are written once.** They are MANIFEST members (§9.3), so a second write
under the same freeze commit **re-verifies**: it compares what the step produced
against what the marker records, returns the marker unchanged if they agree, and
refuses if they do not.

> **A MARKER IS CHECKED AGAINST THE FREEZE COMMIT, NOT AGAINST HEAD — the fourth
> harness defect the predecessor's run disclosed, and it disclosed it by going
> red.** `epl/evwiden.py:4328-4335` compares a marker's `freeze_commit` against
> `git_head()` and refuses unless they are **equal**. HEAD necessarily advances
> after the run: §8.4's own step 6 commits the result document and the evidence
> files, and the predecessor did exactly that at `f3bc756`. **From that commit
> onward every sequence-guarded path in that harness raises
> `SequenceViolation`, and `pytest epl/tests` carries 59 failures on `main` that
> no one introduced** — the ratchet firing on the publication it was built to
> permit. Measured on this repository at HEAD `40eed13`: *"step5_parity refuses:
> step4_merge's marker was written under a different freeze commit
> (38be3e2d4c65… against 40eed1398637…)."*
>
> **The rule here is different and it is birth-law.** A marker's `freeze_commit`
> must equal **the freeze commit recorded in this document's committed freeze
> block** — one fixed value, established once by §8.6's guard from committed
> bytes and Git ancestry — **and that commit must be an ANCESTOR of HEAD, never
> equal to it.** Every property the equality check was reaching for survives: a
> marker from a different freeze does not unlock anything, a marker written
> before the freeze does not unlock anything, and no caller may supply the value.
> What does not survive is a harness that goes red the moment it publishes, which
> is not integrity — it is a guard that cannot tell publication from tampering.

**`epl/evwiden.py` is protected and frozen and is NOT repaired by this
document.** The predecessor's redness is disclosed here, at its measured HEAD,
because §8.9's discipline is to name a defect where it lives and design it out
here rather than to inherit its shape silently.

**A marker may record a FAILURE, and a failure marker unlocks nothing.** A step
that ran and failed writes `complete: false`, and the step it would have unlocked
refuses exactly as it refuses on an absent one. This makes a failed step
DURABLE, which is what closes the retry channel §4.5's no-file-drawer rule
exists to close.

**THE RECLAIM RULE — a crashed step may resume, and every resumption is on the
record**, carried forward from the predecessor's adjudication as birth-law rather
than discovered here:

> * a **COMPLETED** step produced an outcome, and the sequence stays ONCE-ONLY
>   for it: re-running it after seeing what it produced is the
>   outcome-conditioned second run §4.5 closes, and no reclaim reopens it;
> * a **FAILED** step has published its failure, and a continuation after it
>   still needs a new dated pre-freeze note written BEFORE the retry;
> * an **OPEN CLAIM** — a step that started and did not finish — produced no
>   complete product, so there is no outcome to condition a retry on and nothing
>   to put in a file drawer. It may be re-claimed **once per dated reclaim record
>   appended to the claim file** — appended, never overwritten — and the
>   completion marker carries the whole reclaim list forward, so a resumed step's
>   history survives the step and a reader can count the resumptions.

**Resumption is a first-class path with its own marker**, not an ad-hoc script.
The predecessor's run needed a hand-written `resume_from_step3.sh` because its
once-only guard refused a lawfully-completed step 1; here `--resume-from <step>`
is a preregistered entry point that validates every prior marker, refuses on the
first that is absent or fails its product re-hash, and writes its own reclaim
record. §10 makes running the sequence by any other means an invalidation.

> **Step 1 — the post-freeze results canaries, both stores. This is the first
> post-freeze act and it performs the first real fits of this document.**
> `python -m epl.lowerdiv --canary --dir <the preregistered run directory>`, run
> once. It executes `point_in_time_canary` on the E0 store (four fits) and on the
> E1-informed store (four fits), plus the evidence, E1-isolation and identity
> canaries. `PASS: false` on any leg stops the experiment **and the failure
> publishes before the refusal is raised** — the canary record is written and a
> `complete: false` marker is left, and only then does the process stop. Step 1
> refuses outright while a step-1 marker of either kind exists.
> Product: `data/epl/fit/lowerdiv/canary.json`.
>
> **Step 2 — the single-opening exercise.** `--run --limit 1`, which **refuses
> unless the point it would fit is 2019-08-09** — the first opening of the
> corpus, named here by date and by nothing else. A different shard's first point
> is a different opening, and choosing one at the command line would make step 2
> the selection step it is not. It fits both arms at that opening, runs the
> identity control on that opening's fixtures, and **publishes the realised E1
> fit seconds**, which §2.4's budget is checked against. Its console output and
> row count are required in the result document.
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
| L3 | §0.5 | `PopulationRederived` fires when `e` is computed on any frame but the pinned E0 archive, and the recomputed 85 equals widening v3's frozen digest |
| L4 | §0.6 B5 | `PhantomClub` refuses before the projection; and `epl.fit.to_store_frame` fed the same frame still produces `"None"` — the hazard is documented, not silently fixed |
| L5 | §0.6 B4, §2.2 | **registry:** re-resolving the pinned E0 archive through the enlarged registry changes no E0 key, and a synthetic fold collision raises at import. **Ladder:** every E1 season-boundary arrival classifies as relegated-from-E0 / arrived-from-below / continuing against the two archives' own memberships, a relegated club is seeded ABOVE the E1 mean and an arrival from below BELOW it, and a misclassification raises `LadderBoundaryMismatch` |
| L6 | §3.2 | the identity control is exercised in the **production** fit path, not reimplemented by a stub, and goes red when its tolerance is loosened to any value |
| L7 | §3.3 | parity is complete at all 32 cells before one treated simulation, and established per cell before its treatment arm |
| L8 | §4.1 | the per-horizon gate; **no cross-horizon average on any deciding path**; gate (v) is evaluated on all 2,280 rows |
| L9 | §5.1–5.2 | the MC estimator is tie-aware and jointly resampled; both binding tally checks hold |
| L10 | §5.4 | P5, the unanimity rule at `K = 200`, and the seven conditions with no eighth |
| L11 | §6.2 | the equivariance identity holds to `1e-15` at three named points, and `--power` reproduces §6.3 |
| L12 | §8.2 | the pre-freeze commands are mechanically read-only; pass A's import closure excludes the sampler; the read-only store accessor never builds a store |
| L13 | §8.4 | the frozen six-step sequence, its markers, its product re-hashing, and the reclaim rule — **including that a marker is checked against the freeze block's recorded commit and its ANCESTRY to HEAD, never against HEAD's equality: the test advances HEAD past the freeze with a synthetic commit and asserts the sequence still passes, and asserts it refuses a marker from a different freeze** |
| L14 | §8.6 | the guard establishes the freeze state and never accepts it, on every surface |
| L15 | §8.6 | the first-fit state is one fixed path, validated, and RATCHETED by an append-only witness |
| L16 | §8.7, §9.3 | every deciding tally is bound to its row and rebound on every read |
| L17 | **§8.9** | **one layout: every writer's path and every manifest entry come from the same function; a test walks every writer against every reader and every manifest member** |
| L18 | §9 | the evidence contract is closed; the two always-PASS controls are measured off the merged rows |
| L19 | §2.3 | the frozen constants are not overridable from any public surface |
| L20 | §3.3 | `sampler_digest` is a pure function of `(run, tallies)` and reads no fit-identifying field |

**Twenty rows.** A freeze block rendered or read back over fewer than all twenty
is `FreezeStateUnverified`.

### 8.6 The freeze guard, the public-surface closure, and the first-fit record

**The public-surface closure — one guard, one refusal, no exceptions.** A
production path **RESOLVES** `n_sims`, the simulation seed, the chunk size, `B`,
`alpha`, the bootstrap seed, `MC_BOOT`, `MC_SEED`, `K`, `SHARDS`, `δ`, `γ` and
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
a conformance table that is not exactly §8.5's twenty green rows, is
`FreezeStateUnverified`. `harness_frozen` on every ledger row records what the
guard established, never what a caller asserted.

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
this document reuses exactly two of their products: the committed per-fixture CSV
that pins the population (§0.5) and the committed feasibility census that scopes
the table leg (§3.3). Both are read-only here and both are pinned by digest.

### 8.9 ONE DIRECTORY LAYOUT — the path split, designed out

**The defect this section exists to prevent, named with its root cause.** The
widening run's disclosed deviation 2: the table leg wrote its artifacts under the
run directory while the manifest named them under `data/epl/sim/evwiden/`; the
first `--evidence` pass refused with `MergeIncomplete` on 34 paths, and
byte-identical artifacts had to be placed at both paths by hand. **The root cause
was two sources of truth for one location:** `MANIFEST_PATHS`
(`epl/evwiden.py:8176`) is a tuple of hardcoded relative strings, while
`manifest_targets(..., table_ledger=...)` (`:8551-8563`) re-parents them onto a
**caller-supplied** ledger path, and `tallies_dir` (`:7033-7046`) derives the
tally directory from `ledger_path.parent`. Writer location was a runtime
parameter; manifest location was a constant; nothing bound them.

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
   member.** §8.5 row L17: enumerate every path-producing call site in
   `epl/lowerdiv.py`, assert each resolves through `layout()`, assert the set of
   paths written by a full synthetic run equals `layout().manifest_members()`
   exactly — not a superset, not a subset — and assert that a seeded second
   source of truth (a hardcoded relative string) makes the test red.

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

**This is the one place this document may grow before the freeze commit, and it
closes at that commit.** A dated note is appended here, and nowhere else, for
each of:

* **pass A's acquisition record** (§0.6, §8.2) — the twelve fetch records, the
  per-season validation table, the complete E1 club census and spelling set with
  each spelling's index fold, the collision-check result, any unmapped name, the
  E1 goal rate against E0's, and the E1 archive's SHA-256, row count and byte
  size. **A freeze block may not render while this note is absent**, and the
  freeze block pins the archive digest this note records;
* **any pre-freeze pass that produced a number this document is scoped by**, with
  its date, the HEAD it ran at, what it measured, and where its record lives;
* **any dated note required BEFORE a retry** by §8.4's reclaim rule.

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

* `schema` (`epl-lowerdiv-1`), `generated_at`, `prereg_commit`, `prereg_blob`;
* `pins` — corpus / E0 archive / **E1 archive** / ledger / frozen-config digests,
  the realised config digest, the feasibility census digest and its 32-cell
  priceable set, the widening per-fixture CSV's digest, and the row and season
  counts;
* `calibration` — `{delta: -75.0, delta_source: "epl/config_frozen.json chosen.promoted_offset",
  gamma_primary: 1.0, gamma_secondary: 0.5, swept: false}`;
* `acquisition` — pass A's record: the twelve fetch digests, the validation
  table, the club census and spelling folds, the unmapped-name list, the E1 goal
  rate against E0's;
* `estimand` — `{n: 85, mean, sd, se_iid}`;
* `ci_week` and `ci_season` — each `{function, n_blocks, B, alpha, seed, lo,
  hi}`; `ci_corpus_week` (`n_blocks: 212`), `ci_corpus_season` and
  `ci_table_mw6` (`n_blocks: 7`) likewise;
* `gate_i`, `gate_ii`, `gate_iii` — each `{value, bar, PASS}`;
* `gate_iv` — `{mw6: {n: 7, mean, ci, per_cell: [...]},
  per_label: {MW0: {n: 5}, MW3: {n: 6}, MW10: {n: 7}, MW19: {n: 7}, each with
  mean, mc_se and PASS},
  precision: {conditions: [P1, P2, P3.MW0, P3.MW3, P3.MW10, P3.MW19, P4, P5],
  resolved}, PASS_or_UNRESOLVED}` — **eight conditions, no ninth**;
* `gate_v` — `{n: 2280, mean, bar: 7.5e-05, ci_week, PASS}`;
* `controls` — `{identity: {n: 2280, max_abs_diff, mean_abs_diff, PASS},
  e1_leak, population_rederived, phantom_club, predicate_mismatch,
  point_in_time_e1, table_parity: {n_cells: 32, PASS, per_cell_digests}}`;
* `canaries` — results (both stores), evidence (both legs, both row counts, the
  positive control's realised magnitude), **E1-isolation (all four legs, with the
  positive control's realised `max |Δp|`)**, identity;
* `sequence` — the six markers of §8.4, each with its recorded freeze commit,
  completion time, product paths and product digests;
* `conformance` — §8.5's pytest artifact identity: path, SHA-256, the twenty test
  ids and the pass count, as the freeze block records them;
* `dissolved_population` — per fixture and per club-cutoff cell, `e` under each
  archive, each `decides: "nothing"`;
* `cold_start_census`, `gamma_arm`, `strata`, `movement`, `coverage`,
  `sunderland`, `unpriceable_cells_retry` — each `decides: "nothing"`;
* `power` — §6's object: the frozen scenarios, structure, the equivariance
  identity's verification, the MDE definition, `R`, both seeds, the three tables
  of §6.3, and `power.realised` per §6.5;
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
whole corpus moves): `key, match_id, season, block, cutoff, date, home_key,
away_key, e_home_e0, e_away_e0, e_min_e0, e_home_e1, e_away_e1, e_min_e1, thin,
p_home_B, p_draw_B, p_away_B, p_home_A, p_draw_A, p_away_A, p_home_corpus,
p_draw_corpus, p_away_corpus, y, rps_B, rps_A, delta, delta_vs_corpus,
max_abs_dp_vs_corpus, cold_start_B, cold_start_A, provisional_B, provisional_A`.
The 85 pinned fixtures are flagged by `thin`, and a reader can recompute the
estimand from this file alone.

**`lowerdiv_table_cells.csv`** — 32 rows: `season, cutoff_label, cutoff,
e1_informed_clubs, n_e1_informed_clubs, trps_control, trps_treatment, delta_trps,
wtrps_control, wtrps_treatment, delta_wtrps, mc_se_paired, identical,
sampler_digest_control, sampler_digest_treatment, substantive_digest_control,
substantive_digest_treatment, parity_digest_simretro, provisional_control,
provisional_treatment, effective_posterior_control, effective_posterior_treatment,
tally_sha256, cov50_control, cov90_control, cov50_treatment, cov90_treatment,
cov50_e1informed_control, cov90_e1informed_control, cov50_e1informed_treatment,
cov90_e1informed_treatment, realised_hash`.

**`lowerdiv_gamma_arm.csv`** — 85 rows, the γ = 0.5 secondary: `key, delta_gamma,
delta_primary, difference`.

**`lowerdiv_e1_census.csv`** — one row per E1 club: `key, canonical, spellings,
index_folds, seasons_present, matches, first_date, last_date`.

### 9.3 `reports/evidence/MANIFEST.sha256`

Each entry carries a SHA-256 **and a byte size**, and both are **validated** on
`--verify`, not merely recorded. **The list is `sorted(layout().manifest_members())`
and is not written down anywhere else** (§8.9). Its members are, exactly:

| group | paths |
|---|---|
| evidence | `reports/evidence/lowerdiv.json`, `lowerdiv_per_fixture.csv`, `lowerdiv_table_cells.csv`, `lowerdiv_gamma_arm.csv`, `lowerdiv_e1_census.csv` |
| match leg | `data/epl/fit/lowerdiv/shard_0{0,1,2,3}_of_04.jsonl` (4), `data/epl/fit/lowerdiv.json`, `data/epl/fit/lowerdiv/canary.json` |
| E1 archive | `data/epl/matches_e1.parquet`, `data/epl/manifest_e1.json`, `data/epl/team_name_mapping_e1.json`, `data/epl/raw/provenance_e1.json` |
| table leg | `data/epl/sim/lowerdiv/table_cells.jsonl`, `data/epl/sim/lowerdiv/parity.jsonl`, `data/epl/sim/lowerdiv/tallies/<S>\|<L>.npz` — **exactly 32 files** (each holding BOTH arms' tallies, so 64 tallies in 32 paths), `<S>` over the seven seasons with `/` replaced by `-`, `<L>` over the five labels, minus the three excluded cells |
| sequence | `data/epl/fit/lowerdiv/sequence/step{1..6}.json` (6) |
| conformance | `data/epl/fit/lowerdiv_conformance.json` |

The count is decidable from this document: 5 + 6 + 4 + 34 + 6 + 1 = **56 paths**.
"Bulky local artifacts" is not a category here; it is a list, and §8.9 makes it a
list that one function produces.

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

* the verdict and which gate decided;
* §4.2's required materiality sentence, verbatim;
* **§6.4's power ruling in its own words if the estimand misses**, including the
  sentence *"not detected at this power, not no effect"* and the measured joint
  power at −0.00413;
* §6.5's realised paired SDs and the joint-gate MDE recomputed at the realised
  thin-population SD;
* §0.5's dissolved-population numbers — the E1-informed `e` for all 85 fixtures
  and the club-cutoff census — reported as the pre-stated secondary they are;
* §1.2 bullet 2's attribution: how much of any improvement is the cold-start path
  dissolving, stated as unseparable by this design;
* §3.4's coverage reading, in the direction §3.4 fixes;
* pass A's acquisition record by reference to the §8.10 note, and the E1 archive's
  digest;
* the console output, row count and **realised E1 fit seconds** of §8.4 step 2,
  and the digest of step 1's canary record;
* if gate (iv) is UNRESOLVED: which of P1–P5 fired, with its computed value, and
  §5.5's pre-statement that this was the modal outcome.

---

## 10. What would invalidate this preregistration

* Any pinned digest of §0.1 differs at run time without a prior dated note.
* **`data/epl/matches.parquet` is written, or its bytes move, for any reason.**
* **An E1 row reaches the E0 archive, the E0 store root, `epl.elo`, or
  `effective_evidence`.**
* **The thin population is re-derived rather than taken from the pinned
  `reports/evidence/widening_per_fixture.csv`**, or the recomputed 85-key digest
  is not widening v3's `38d18d4d96…`, or a fixture is dropped from the 85.
* **A null club key is stringified rather than refused, anywhere on any path**, or
  the `PhantomClub` refusal is moved after the projection.
* A real-archive fit or season simulation runs before the §8.3 freeze commit,
  anywhere, under any output directory. Pass A is data acquisition and fits
  nothing; a pass A that builds a store or imports the sampler is such a fit.
* Pass A is run more than once, or its dated note is absent when the freeze block
  renders, or the E1 archive's bytes differ from that note.
* An E1 season that fails validation is dropped, repaired by hand, or excluded
  rather than refused.
* Registry entries are written before the spelling enumeration is published, or a
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
* **δ moves off −75.0, is swept, is estimated from crossings, or is presented as
  fitted; or γ moves off 0.5 in the secondary, or off 1.0 in the primary; or the
  γ arm is promoted to the estimand.**
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
  block's recorded commit and its ancestry to HEAD** (§8.4) — the shape that made
  the predecessor's harness go red on its own publication.
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
* Step 1 retried after a failed canary without a dated pre-freeze note written
  **before** the retry.
* A conformance report accepted from anything but §8.5's committed pytest
  artifact, or a freeze block rendered or read back over fewer than all twenty
  rows L1–L20.
* The first-fit record deleted, or written without its append-only witness line,
  or recorded at a moment that is not the instant of the fit it attests.
* `--script` run before the freeze commit, at any target; or a post-freeze
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
* **This design is underpowered against the effect it exists to test.** Joint
  power 0.12–0.37 at −0.00413; joint MDE 1.74×–3.64× that effect; gate (ii) is
  the binding gate. **A miss is substantially uninformative.**
* **Gate (iv) UNRESOLVED is the modal outcome of the table leg** (§5.5), because
  two fits per cell carry more paired MC error than one posterior did, at the
  same 20,000 seasons.
* The intervals are percentile block bootstraps over correlated fixtures — not
  moving-block, not exact tests; the 6- and 7-block season resamples have poor
  coverage and serve only to refuse single-season verdicts. One ADVI seed;
  mean-field under-dispersion is a known, separately scheduled limitation.
* **Sampler noise is not model error**, and with two independent fits per pair it
  enters this design's deltas twice rather than cancelling. Both are reported;
  neither shrinks with a better argument.
* **The improvement, if any, cannot be attributed to better parameter estimates
  rather than to the cold-start path dissolving** (§1.2, §2.3). No design here
  separates them.
* **δ prices the centre of the league gap and not its dispersion.** A club whose
  attack is estimated largely from Championship matches carries a Championship
  attack shifted by a constant. That is the modelling assumption and it is not
  tested here.
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

*Preregistered 2026-08-30. This is the lower-division-evidence experiment
[`reports/epl_widening_result.md`](epl_widening_result.md) named as its own
successor. It is written on the structure of
[`reports/epl_widening_prereg_v3.md`](epl_widening_prereg_v3.md) — that
document's §5 statistics, §8 lifecycle, §9 evidence contract and §10
invalidations — with every ruling its four review rounds, two in-tree adversarial
audits and one owner adjudication reached carried here as birth-law rather than
as a later repair, and with the four harness defects that run disclosed designed
out before a line of harness code exists (§8.4's reclaim rule and first-class
resumption; §8.4's step-indexed canary record; §8.4's freeze-commit-and-ancestry
marker rule, learned from that harness going red on its own publication;
§8.9's single layout function).
It differs from its predecessor in the three ways that matter and each is stated
as a loss or a cost rather than discovered by the run: the structural-zero control
cannot exist because the arms are two fits (§1.4); the population must be pinned
rather than derived because one Championship season is three times the threshold
that defines it (§0.5); and the design is underpowered against the very effect it
exists to test, with gate (ii) binding, and no amount of additional data can buy
power on a population that is pinned (§6.4). No harness exists, no E1 archive
exists, and no fit of this document has ever run.*
