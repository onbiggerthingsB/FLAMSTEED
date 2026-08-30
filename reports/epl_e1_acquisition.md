# The E1 acquisition record — the Championship archive, built standalone

**Written:** 2026-08-30 · **HEAD at writing:** `d20a13a` · **Branch:** `main`
· **Design reference:** [`reports/epl_lowerdiv_prereg.md`](epl_lowerdiv_prereg.md) v2 at `d20a13a`

**What this document is.** The acquisition record for football-data.co.uk's E1
(EFL Championship) season files, `1415`–`2526`. It exists because the E1 prereg's
registry-order rule (§0.6, §8.2) forbids writing a club into `epl/teams.py`
before the club enumeration it is written against has been **published**. This is
that publication.

**What this document is NOT.** It is not the lower-division experiment, and
nothing in it is evidence for or against that experiment's hypothesis. Under the
owner's 2026-08-30 **E1 SPLIT** ruling the Championship archive is built now as
**standalone infrastructure**: the prereg is the design reference for the
acquisition — its §2/§0.6 ingest rulings and its §8.10 attestation record — and
the confirmatory experiment holds, unrun, with no fit, no store build and no
harness in this build. When the experiment is revived it pins the archive
**as-found**.

**No outcome statistic appears anywhere below.** Not a score, not a goal count,
not a goal rate, not a result distribution. The census here is **structural**:
rows, clubs, opponents, spellings and folds. That restriction is the prereg's
(§0.6, §8.10) and it is honoured here even though this document is not itself a
§8.10 note.

---

## 1. The state this record is written in — DECLARED, not measured

**There is no network in this phase, and this record says so rather than
implying a fetch happened.** The prereg's A0 pass — the one pass that touches the
network — has **not run**. No E1 CSV has been downloaded, no
`data/epl/raw/E1_*.csv` exists, no `data/epl/raw/provenance_e1.json` exists and
no `data/epl/matches_e1.parquet` exists. The ingest code lands tested against
**synthetic** CSVs; the real download is the next phase's once-only act.

So the enumeration in §3 is **declared from the design reference and from the
public composition of the competition**, not measured off the source bytes. That
is a weaker warrant than A0's, and the whole of §5 exists to say what carries the
safety in its absence. Two things follow and both are load-bearing:

1. **The registry-order rule is satisfied in form and in substance.** The
   enumeration is published here, at a commit that precedes the registry commit,
   so the registry is written *against a list a reader can check* rather than
   against whatever the author happened to remember while editing `teams.py`. A
   spelling that is not in §3 must not appear in the registry.
2. **A declared census that is wrong REFUSES; it never invents a club.** §5 names
   the four independent mechanisms that turn a wrong guess into a loud stop.
   None of them is "the fit looks fine".

**When A0 does run, its measured census supersedes §3 by appendix, not by edit.**
A spelling A0 finds that §3 does not carry is not a licence to slug a new club:
it is an `AcquisitionIncomplete`, and the remedy is a registry commit written
against the measured list, appended below with its own date.

---

## 2. What is acquired, and the shape it must have

**Source.** `https://www.football-data.co.uk/mmz4281/{season_code}/E1.csv` —
the same generator, the same directory and the same columns as the pinned E0
archive, established from the repository without the network (the prereg's §0.6
cites `epl/oddscapture.py`, `epl/livecycle.py` and two existing tests that
already synthesise `E1` rows against those readers).

**Window.** The twelve season codes `epl.fetch.SEASON_CODES` already holds:
`1415`–`2526`. Same window as E0, so every promoted club's second-tier history is
covered on the span the E0 archive covers.

**Cache.** `data/epl/raw/E1_{code}.csv`, cache-first and hash-pinned under the
same discipline as E0: once a file lands it is never re-downloaded, and a byte
change under a recorded digest raises rather than proceeding.

**Provenance.** A **separate sidecar**, `data/epl/raw/provenance_e1.json`, keyed
`{division}_{season_code}` (`E1_1415`, …). `data/epl/raw/provenance.json` — the
E0 sidecar, keyed by bare season code — is **not opened for writing** on any path
of this build. Two files and two key schemes: the collision the scout named is
closed twice over.

**Shape.** A completed Championship season is a 24-club double round-robin:

* **24** clubs, **552** matches, **23** home and **23** away fixtures per club.

against E0's 20 / 380 / 19. Expected total volume **12 × 552 = 6,624** matches.
The per-season declared membership:

| season | code | clubs | expected matches | expected opponents each | membership |
|---|---|---|---|---|---|
| 2014/15 | `1415` | 24 | 552 | 23 | Birmingham, Blackburn, Blackpool, Bolton, Bournemouth, Brentford, Brighton, Cardiff, Charlton, Derby, Fulham, Huddersfield, Ipswich, Leeds, Middlesbrough, Millwall, Norwich, Nott'm Forest, Reading, Rotherham, Sheffield Weds, Watford, Wigan, Wolves |
| 2015/16 | `1516` | 24 | 552 | 23 | Birmingham, Blackburn, Bolton, Brentford, Brighton, Bristol City, Burnley, Cardiff, Charlton, Derby, Fulham, Huddersfield, Hull, Ipswich, Leeds, Middlesbrough, Milton Keynes Dons, Nott'm Forest, Preston, QPR, Reading, Rotherham, Sheffield Weds, Wolves |
| 2016/17 | `1617` | 24 | 552 | 23 | Aston Villa, Barnsley, Birmingham, Blackburn, Brentford, Brighton, Bristol City, Burton, Cardiff, Derby, Fulham, Huddersfield, Ipswich, Leeds, Newcastle, Norwich, Nott'm Forest, Preston, QPR, Reading, Rotherham, Sheffield Weds, Wigan, Wolves |
| 2017/18 | `1718` | 24 | 552 | 23 | Aston Villa, Barnsley, Birmingham, Bolton, Brentford, Bristol City, Burton, Cardiff, Derby, Fulham, Hull, Ipswich, Leeds, Middlesbrough, Millwall, Norwich, Nott'm Forest, Preston, QPR, Reading, Sheffield United, Sheffield Weds, Sunderland, Wolves |
| 2018/19 | `1819` | 24 | 552 | 23 | Aston Villa, Birmingham, Blackburn, Bolton, Brentford, Bristol City, Derby, Hull, Ipswich, Leeds, Middlesbrough, Millwall, Norwich, Nott'm Forest, Preston, QPR, Reading, Rotherham, Sheffield United, Sheffield Weds, Stoke, Swansea, West Brom, Wigan |
| 2019/20 | `1920` | 24 | 552 | 23 | Barnsley, Birmingham, Blackburn, Brentford, Bristol City, Cardiff, Charlton, Derby, Fulham, Huddersfield, Hull, Leeds, Luton, Middlesbrough, Millwall, Nott'm Forest, Preston, QPR, Reading, Sheffield Weds, Stoke, Swansea, West Brom, Wigan |
| 2020/21 | `2021` | 24 | 552 | 23 | Barnsley, Birmingham, Blackburn, Bournemouth, Brentford, Bristol City, Cardiff, Coventry, Derby, Huddersfield, Luton, Middlesbrough, Millwall, Norwich, Nott'm Forest, Preston, QPR, Reading, Rotherham, Sheffield Weds, Stoke, Swansea, Watford, Wycombe |
| 2021/22 | `2122` | 24 | 552 | 23 | Barnsley, Birmingham, Blackburn, Blackpool, Bournemouth, Bristol City, Cardiff, Coventry, Derby, Fulham, Huddersfield, Hull, Luton, Middlesbrough, Millwall, Nott'm Forest, Peterboro, Preston, QPR, Reading, Sheffield United, Stoke, Swansea, West Brom |
| 2022/23 | `2223` | 24 | 552 | 23 | Birmingham, Blackburn, Blackpool, Bristol City, Burnley, Cardiff, Coventry, Huddersfield, Hull, Luton, Middlesbrough, Millwall, Norwich, Preston, QPR, Reading, Rotherham, Sheffield United, Stoke, Sunderland, Swansea, Watford, West Brom, Wigan |
| 2023/24 | `2324` | 24 | 552 | 23 | Birmingham, Blackburn, Bristol City, Cardiff, Coventry, Huddersfield, Hull, Ipswich, Leeds, Leicester, Middlesbrough, Millwall, Norwich, Plymouth, Preston, QPR, Rotherham, Sheffield Weds, Southampton, Stoke, Sunderland, Swansea, Watford, West Brom |
| 2024/25 | `2425` | 24 | 552 | 23 | Blackburn, Bristol City, Burnley, Cardiff, Coventry, Derby, Hull, Leeds, Luton, Middlesbrough, Millwall, Norwich, Oxford, Plymouth, Portsmouth, Preston, QPR, Sheffield United, Sheffield Weds, Stoke, Sunderland, Swansea, Watford, West Brom |
| 2025/26 | `2526` | 24 | 552 | 23 | Birmingham, Blackburn, Bristol City, Charlton, Coventry, Derby, Hull, Ipswich, Leicester, Middlesbrough, Millwall, Norwich, Oxford, Portsmouth, Preston, QPR, Sheffield United, Sheffield Weds, Southampton, Stoke, Swansea, Watford, West Brom, Wrexham |

Membership counts sum to **288 = 12 × 24**, which is the arithmetic check that
the table is a partition of twelve complete seasons rather than a list of clubs
somebody remembered.

---

## 3. THE ENUMERATION — every distinct spelling, its fold, its key, its seasons

**This is the list the registry commit is written against, and it is published
here first.** `index fold` is `epl.teams._index_key` — lowercase, non-alphanumerics
dropped — which is the only string the registry actually looks up on, and
therefore the only string a collision can happen in.

**49 distinct spellings. 27 already resolve through the E0 registry. 22 are new.**

| # | football-data spelling | index fold | stable key | registry status | n | seasons |
|---|---|---|---|---|---|---|
| 1 | `Aston Villa` | `astonvilla` | `aston_villa` | already registered (E0) | 3 | 1617 1718 1819 |
| 2 | `Barnsley` | `barnsley` | `barnsley` | **NEW** | 5 | 1617 1718 1920 2021 2122 |
| 3 | `Birmingham` | `birmingham` | `birmingham` | **NEW** | 11 | 1415 1516 1617 1718 1819 1920 2021 2122 2223 2324 2526 |
| 4 | `Blackburn` | `blackburn` | `blackburn` | **NEW** | 11 | 1415 1516 1617 1819 1920 2021 2122 2223 2324 2425 2526 |
| 5 | `Blackpool` | `blackpool` | `blackpool` | **NEW** | 3 | 1415 2122 2223 |
| 6 | `Bolton` | `bolton` | `bolton` | **NEW** | 4 | 1415 1516 1718 1819 |
| 7 | `Bournemouth` | `bournemouth` | `bournemouth` | already registered (E0) | 3 | 1415 2021 2122 |
| 8 | `Brentford` | `brentford` | `brentford` | already registered (E0) | 7 | 1415 1516 1617 1718 1819 1920 2021 |
| 9 | `Brighton` | `brighton` | `brighton` | already registered (E0) | 3 | 1415 1516 1617 |
| 10 | `Bristol City` | `bristolcity` | `bristol_city` | **NEW** | 11 | 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425 2526 |
| 11 | `Burnley` | `burnley` | `burnley` | already registered (E0) | 3 | 1516 2223 2425 |
| 12 | `Burton` | `burton` | `burton` | **NEW** | 2 | 1617 1718 |
| 13 | `Cardiff` | `cardiff` | `cardiff` | already registered (E0) | 10 | 1415 1516 1617 1718 1920 2021 2122 2223 2324 2425 |
| 14 | `Charlton` | `charlton` | `charlton` | **NEW** | 4 | 1415 1516 1920 2526 |
| 15 | `Coventry` | `coventry` | `coventry` | already registered (E0) | 6 | 2021 2122 2223 2324 2425 2526 |
| 16 | `Derby` | `derby` | `derby` | **NEW** | 10 | 1415 1516 1617 1718 1819 1920 2021 2122 2425 2526 |
| 17 | `Fulham` | `fulham` | `fulham` | already registered (E0) | 6 | 1415 1516 1617 1718 1920 2122 |
| 18 | `Huddersfield` | `huddersfield` | `huddersfield` | already registered (E0) | 8 | 1415 1516 1617 1920 2021 2122 2223 2324 |
| 19 | `Hull` | `hull` | `hull` | already registered (E0) | 9 | 1516 1718 1819 1920 2122 2223 2324 2425 2526 |
| 20 | `Ipswich` | `ipswich` | `ipswich` | already registered (E0) | 7 | 1415 1516 1617 1718 1819 2324 2526 |
| 21 | `Leeds` | `leeds` | `leeds` | already registered (E0) | 8 | 1415 1516 1617 1718 1819 1920 2324 2425 |
| 22 | `Leicester` | `leicester` | `leicester` | already registered (E0) | 2 | 2324 2526 |
| 23 | `Luton` | `luton` | `luton` | already registered (E0) | 5 | 1920 2021 2122 2223 2425 |
| 24 | `Middlesbrough` | `middlesbrough` | `middlesbrough` | already registered (E0) | 11 | 1415 1516 1718 1819 1920 2021 2122 2223 2324 2425 2526 |
| 25 | `Millwall` | `millwall` | `millwall` | **NEW** | 10 | 1415 1718 1819 1920 2021 2122 2223 2324 2425 2526 |
| 26 | `Milton Keynes Dons` | `miltonkeynesdons` | `mk_dons` | **NEW** | 1 | 1516 |
| 27 | `Newcastle` | `newcastle` | `newcastle` | already registered (E0) | 1 | 1617 |
| 28 | `Norwich` | `norwich` | `norwich` | already registered (E0) | 9 | 1415 1617 1718 1819 2021 2223 2324 2425 2526 |
| 29 | `Nott'm Forest` | `nottmforest` | `nottm_forest` | already registered (E0) | 8 | 1415 1516 1617 1718 1819 1920 2021 2122 |
| 30 | `Oxford` | `oxford` | `oxford` | **NEW** | 2 | 2425 2526 |
| 31 | `Peterboro` | `peterboro` | `peterborough` | **NEW** | 1 | 2122 |
| 32 | `Plymouth` | `plymouth` | `plymouth` | **NEW** | 2 | 2324 2425 |
| 33 | `Portsmouth` | `portsmouth` | `portsmouth` | **NEW** | 2 | 2425 2526 |
| 34 | `Preston` | `preston` | `preston` | **NEW** | 11 | 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425 2526 |
| 35 | `QPR` | `qpr` | `qpr` | already registered (E0) | 11 | 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425 2526 |
| 36 | `Reading` | `reading` | `reading` | **NEW** | 9 | 1415 1516 1617 1718 1819 1920 2021 2122 2223 |
| 37 | `Rotherham` | `rotherham` | `rotherham` | **NEW** | 7 | 1415 1516 1617 1819 2021 2223 2324 |
| 38 | `Sheffield United` | `sheffieldunited` | `sheffield_united` | already registered (E0) | 6 | 1718 1819 2122 2223 2425 2526 |
| 39 | `Sheffield Weds` | `sheffieldweds` | `sheffield_wednesday` | **NEW** | 10 | 1415 1516 1617 1718 1819 1920 2021 2324 2425 2526 |
| 40 | `Southampton` | `southampton` | `southampton` | already registered (E0) | 2 | 2324 2526 |
| 41 | `Stoke` | `stoke` | `stoke` | already registered (E0) | 8 | 1819 1920 2021 2122 2223 2324 2425 2526 |
| 42 | `Sunderland` | `sunderland` | `sunderland` | already registered (E0) | 4 | 1718 2223 2324 2425 |
| 43 | `Swansea` | `swansea` | `swansea` | already registered (E0) | 8 | 1819 1920 2021 2122 2223 2324 2425 2526 |
| 44 | `Watford` | `watford` | `watford` | already registered (E0) | 6 | 1415 2021 2223 2324 2425 2526 |
| 45 | `West Brom` | `westbrom` | `west_brom` | already registered (E0) | 7 | 1819 1920 2122 2223 2324 2425 2526 |
| 46 | `Wigan` | `wigan` | `wigan` | **NEW** | 5 | 1415 1617 1819 1920 2223 |
| 47 | `Wolves` | `wolves` | `wolves` | already registered (E0) | 4 | 1415 1516 1617 1718 |
| 48 | `Wrexham` | `wrexham` | `wrexham` | **NEW** | 1 | 2526 |
| 49 | `Wycombe` | `wycombe` | `wycombe` | **NEW** | 1 | 2021 |

### 3.1 The 22 new registry entries

`Barnsley`, `Birmingham`, `Blackburn`, `Blackpool`, `Bolton`, `Bristol City`,
`Burton`, `Charlton`, `Derby`, `Millwall`, `Milton Keynes Dons`, `Oxford`,
`Peterboro`, `Plymouth`, `Portsmouth`, `Preston`, `Reading`, `Rotherham`,
`Sheffield Weds`, `Wigan`, `Wrexham`, `Wycombe`.

The registry goes from **36** clubs to **58**. Every one of the 22 is a club that
appears in the declared membership of at least one of the twelve seasons; none is
speculative and none is a club of a division this build does not acquire.

Four of the 22 carry a canonical display name that is **not** football-data's
spelling, because football-data's spelling is an abbreviation and the canonical
name is what a reader of a table should see:

| football-data spelling | canonical name | key |
|---|---|---|
| `Sheffield Weds` | Sheffield Wednesday | `sheffield_wednesday` |
| `Peterboro` | Peterborough | `peterborough` |
| `Milton Keynes Dons` | Milton Keynes Dons | `mk_dons` |
| `Burton` | Burton Albion | `burton` |

In every such case **the football-data spelling is registered as an accepted
alias**, so the source's own string resolves without a rewrite anywhere in the
ingest.

### 3.2 The fold-collision check — RESULT: CLEAN

Every one of the 49 folds was computed and checked against the live
`epl.teams._INDEX` at `d20a13a` and against every other fold in the list. **No
collision.** The two folds worth naming because they are the near misses:

* `sheffieldweds` vs `sheffieldunited` / `sheffieldutd` / `sheffutd` /
  `sheffunited` — distinct, and Sheffield Wednesday's key is
  `sheffield_wednesday`, not a variant of `sheffield_united`.
* `burton` vs `burnley` — distinct strings, distinct clubs, distinct keys.

**A collision would have been resolved by REFUSING, never by renaming a club.**
`epl.teams._build_index` raises at import on a fold that maps to two different
`(canonical, key)` pairs, so a collision cannot be introduced quietly: it stops
every import of `epl.teams`, which is every path in the package.

---

## 4. What the acquisition writes, and what it must not touch

| artifact | path | written by |
|---|---|---|
| raw season CSVs | `data/epl/raw/E1_{code}.csv` | the fetch pass (next phase) |
| provenance sidecar | `data/epl/raw/provenance_e1.json` | the fetch pass (next phase) |
| tidy match table | `data/epl/matches_e1.parquet` | `python -m epl.build --division E1` |
| manifest | `data/epl/manifest_e1.json` | `python -m epl.build --division E1` |
| name mapping report | `data/epl/team_name_mapping_e1.json` | `python -m epl.build --division E1` |

**The E0 archive is not touched.** `data/epl/matches.parquet` stays
byte-identical at
`323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf`; the E0
fetch/parse/build path keeps its behaviour, its file names, its provenance keys
and its `match_id` recipe; and **the Elo anchor never sees an E1 row** — nothing
in this build adds E1 to any anchor, fit, store or forecast input, because this
build produces an archive and stops.

**The `match_id` recipes are disjoint by construction.** E0 keeps
`sha256("{season_code}|{date}|{home_key}|{away_key}")[:16]` unchanged — those ids
are pinned in artifacts all over the repository and may not move. E1 composes
`sha256("{division}|{season_code}|{date}|{home_key}|{away_key}")[:16]`. The two
id spaces cannot intersect except by a SHA-256 collision.

---

## 5. What carries the safety, given that §3 is declared and not measured

**Four mechanisms, each independent of the others, each of which converts a wrong
spelling into a stop rather than into a phantom club.**

1. **The fold-collision guard.** `epl.teams._build_index` refuses at import if a
   new spelling's fold collides with a registered one. A collision does not
   corrupt a fit; it prevents the package from importing at all.
2. **Strict resolution.** `epl.teams.resolve` raises `UnknownTeamError` on an
   unregistered spelling. There is no slugger and no fallback. A Championship
   club whose football-data spelling §3 got wrong does not become a new club —
   it fails to resolve.
3. **The null-key refusal.** For a non-E0 division a null `home_key` or
   `away_key` **raises `PhantomClub` at parse time**, naming the season, the date
   and the raw spelling. The row never reaches a frame, so the hazard in
   `epl.fit.to_store_frame` — `played["home_key"].astype(str)`, which turns a
   null key into the literal club `"None"` and silently merges every
   unregistered club into one mega-club with its own attack and defence — is
   **unreachable** on this build's call graph. `epl/fit.py` is protected and is
   not edited; the hazard is closed upstream by refusal, and a committed test
   asserts the hazard is still live in the protected module so nobody mistakes
   this for a repair.
4. **The structural validator.** The E1 validator runs the identical check list
   at (24, 552, 23): a season that is not a complete 24-club double round-robin
   fails, and `python -m epl.build --division E1` **refuses** on any issue rather
   than writing a partial archive.

**The failure mode this closes is the expensive one.** A wrong spelling in §3
costs a re-run of the parse pass after a one-line registry correction. A wrong
spelling that *resolved anyway* would cost a fit trained on a club that does not
exist, and would not look wrong from any downstream number.

---

## 6. Scope

This record covers the acquisition only. It authorises no fit, no store build, no
simulation and no estimand. The lower-division experiment's law is unchanged and
its freeze has not been taken. Nothing here may be cited as evidence about the
experiment's hypothesis, and the archive this record describes is the archive
that experiment will pin **as-found** if it is revived.

---

## 7. The ingest as built — 2026-08-30

**The code is complete and the network has still not run.** All six blockers are
carried, each behaviourally covered by a red-then-green test in
`epl/tests/test_e1ingest.py` (68 tests). `python -m epl.build --division E1`
exists and works; what it has never been given is a real E1 CSV. The archive
files in §4 do not exist yet, and building them is the next phase's once-only
deliberate act.

| blocker | where it is closed | the test that proves it |
|---|---|---|
| B1 fetch hardcodes E0 | `fetch.url_for` / `raw_path` / `url_pattern` take `division` | `test_the_e1_url_names_the_e1_file`, `test_the_cache_path_carries_the_division_and_e0_is_unchanged` |
| B2 provenance key collides | `{division}_{code}` **and** a separate sidecar | `test_an_e1_fetch_does_not_overwrite_the_e0_record_for_the_same_season` |
| B3 380/20/19 assumed | `schema.DivisionShape`, `validate_season(division=…)` | `test_a_championship_season_validates_at_552_24_23`, `test_the_same_championship_season_FAILS_the_e0_validator` |
| B4 spellings unregistered | 22 registry entries + the fold-collision guard | `test_every_declared_e1_spelling_resolves`, `test_the_collision_guard_refuses_a_fold_that_maps_two_clubs` |
| B5 null key becomes a club | `parse.PhantomClub`, raised before the frame exists | `test_an_unregistered_club_in_an_e1_file_refuses_at_parse_time`, `test_the_phantom_club_hazard_is_still_live_in_the_protected_module` |
| B6 `match_id` has no division | `E1\|` prefix; E0's payload verbatim | `test_every_id_in_the_pinned_e0_archive_still_reproduces`, `test_every_id_the_e1_build_writes_carries_the_division` |

**The strict gate is real.** `build(division="E1")` raises
`AcquisitionIncomplete` **before the first write** if any season carries a
blocking issue, so a refused build leaves a previously built archive untouched
rather than truncating it. The single non-blocking issue is the vendor's line of
bare commas, recognised by *deriving* the string from `parse.blank_rows_issue`
rather than by matching prose. E0 is deliberately **not** strict: it reports and
continues, because the daily live cycle meets an unregistered promoted club
before anyone has registered it and must still produce a table.

### 7.1 Two defects found while building, both fixed, both worth recording

1. **`build` wrote through module-level path constants, not the accessors.**
   `paths.MATCHES_PARQUET` is bound to the real `data/epl/` at *import*, so a
   test that repoints `paths.DATA_DIR` at a temporary directory does **not** move
   it. This was not theoretical: a red-phase test run called the then-unmodified
   `build()` and **overwrote the pinned 4,560-row archive with a 380-row
   synthetic season**. It was restored byte-identically to
   `323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf` by
   re-running `python -m epl.build` over the untouched, hash-pinned raw CSVs in
   `data/epl/raw/` — which is also a demonstration that the E0 archive is exactly
   reproducible from its cached source bytes. `build` now resolves **every**
   output through `paths.*(division)`, and two guards were added: a test that
   runs a full E0 build under a temporary root and asserts the pinned digest did
   not move, and a fixture-level fence that restores the archive and fails loudly
   if any test ever writes to it again.
2. **The build summary crashed on a season with no odds at all.**
   `overround_mean` is `None` when no row carries a usable price triple, and
   `format(None, '>6')` raises. Every E0 season carries prices, so this never
   fired — but the crash came *after* the parquet was written, so a run that had
   in fact succeeded would have reported failure. E1 odds coverage is not
   guaranteed the way E0's is, which is exactly when this would first have been
   met, on the one pass that touches the network.

Neither defect changes anything in §1–§6. Both are recorded because the second
would have been met for the first time during the real download, and the first
is the reason the accessor discipline in `epl/paths.py` is load-bearing rather
than stylistic.

---

*Written 2026-08-30 at `d20a13a`, under the owner's E1 SPLIT ruling of the same
date. The enumeration in §3 is published BEFORE the registry commit it is written
against, per the design reference's registry-order rule. It is DECLARED, not
measured: the network pass has not run, and §5 states what carries the safety in
its place.*
