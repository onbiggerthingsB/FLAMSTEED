# OA dev-slate mini-probe — which development competitions does the archive carry? (OA Plan 2 v2, V0)

**MODE: LIVE.** Real paid responses from The Odds API.

Every `sport_key` below is a **CANDIDATE**: a hypothesis this probe exists to verify, exactly as `odds.sport_keys` were for the OA-0a eval panel. A wrong key costs one discovery credit and shows up here as a finding — correcting it is a one-line edit to `SLATE_PROBES`, not a logic change. Competitions are named in the martj42 store's vocabulary (`tournament`), because that is what `oa_dev_slate.competitions` is keyed by.

This probe chooses the COMPETITIONS. Fixture SELECTION within them is the frozen rule in `src/wcmodel/eval/dev_slate.py` and is not affected by anything measured here.

## Call plan + projected credit cost

13 competitions x (1 discovery @ 1 credit + 1 snapshot [T-1h; h2h x eu] @ 10 credits) = **143 credits** projected, against the plan's 150-credit mini-probe budget; modeled spend this run: 68.

The snapshot leg is a CEILING: a competition whose listing comes back empty never has its snapshot precalled, so an uncovered probe costs 1 credit, not 11.

| # | competition | store tournament | candidate sport_key | call | endpoint | at | credits |
|---|---|---|---|---|---|---|---|
| 1 | UEFA Nations League (2022 group stage) | UEFA Nations League | `soccer_uefa_nations_league` | discovery | `/v4/historical/sports/soccer_uefa_nations_league/events` | 2022-06-14T00:00:00Z | 1 |
| 2 | UEFA Nations League (2022 group stage) | UEFA Nations League | `soccer_uefa_nations_league` | snapshot T-1h | `/v4/historical/sports/soccer_uefa_nations_league/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 3 | UEFA Nations League (2025 quarter-finals) | UEFA Nations League | `soccer_uefa_nations_league` | discovery | `/v4/historical/sports/soccer_uefa_nations_league/events` | 2025-03-20T00:00:00Z | 1 |
| 4 | UEFA Nations League (2025 quarter-finals) | UEFA Nations League | `soccer_uefa_nations_league` | snapshot T-1h | `/v4/historical/sports/soccer_uefa_nations_league/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 5 | CONCACAF Nations League (2023) | CONCACAF Nations League | `soccer_concacaf_nations_league` | discovery | `/v4/historical/sports/soccer_concacaf_nations_league/events` | 2023-11-21T00:00:00Z | 1 |
| 6 | CONCACAF Nations League (2023) | CONCACAF Nations League | `soccer_concacaf_nations_league` | snapshot T-1h | `/v4/historical/sports/soccer_concacaf_nations_league/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 7 | Copa América (2024) | Copa América | `soccer_conmebol_copa_america` | discovery | `/v4/historical/sports/soccer_conmebol_copa_america/events` | 2024-06-22T00:00:00Z | 1 |
| 8 | Copa América (2024) | Copa América | `soccer_conmebol_copa_america` | snapshot T-1h | `/v4/historical/sports/soccer_conmebol_copa_america/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 9 | Africa Cup of Nations qualification (2024) | African Cup of Nations qualification | `soccer_africa_cup_of_nations_qualification` | discovery | `/v4/historical/sports/soccer_africa_cup_of_nations_qualification/events` | 2024-10-11T00:00:00Z | 1 |
| 10 | Africa Cup of Nations qualification (2024) | African Cup of Nations qualification | `soccer_africa_cup_of_nations_qualification` | snapshot T-1h | `/v4/historical/sports/soccer_africa_cup_of_nations_qualification/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 11 | AFC Asian Cup (2023/24 finals) | AFC Asian Cup | `soccer_afc_asian_cup` | discovery | `/v4/historical/sports/soccer_afc_asian_cup/events` | 2024-01-23T00:00:00Z | 1 |
| 12 | AFC Asian Cup (2023/24 finals) | AFC Asian Cup | `soccer_afc_asian_cup` | snapshot T-1h | `/v4/historical/sports/soccer_afc_asian_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 13 | Africa Cup of Nations (2023/24 finals) | African Cup of Nations | `soccer_africa_cup_of_nations` | discovery | `/v4/historical/sports/soccer_africa_cup_of_nations/events` | 2024-01-22T00:00:00Z | 1 |
| 14 | Africa Cup of Nations (2023/24 finals) | African Cup of Nations | `soccer_africa_cup_of_nations` | snapshot T-1h | `/v4/historical/sports/soccer_africa_cup_of_nations/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 15 | CONCACAF Gold Cup (2023) | Gold Cup | `soccer_concacaf_gold_cup` | discovery | `/v4/historical/sports/soccer_concacaf_gold_cup/events` | 2023-07-16T00:00:00Z | 1 |
| 16 | CONCACAF Gold Cup (2023) | Gold Cup | `soccer_concacaf_gold_cup` | snapshot T-1h | `/v4/historical/sports/soccer_concacaf_gold_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 17 | UEFA Euro 2024 qualification | UEFA Euro qualification | `soccer_uefa_euro_qualification` | discovery | `/v4/historical/sports/soccer_uefa_euro_qualification/events` | 2023-06-16T00:00:00Z | 1 |
| 18 | UEFA Euro 2024 qualification | UEFA Euro qualification | `soccer_uefa_euro_qualification` | snapshot T-1h | `/v4/historical/sports/soccer_uefa_euro_qualification/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 19 | FIFA WC qualification — UEFA (2025) | FIFA World Cup qualification | `soccer_fifa_world_cup_qualifiers_europe` | discovery | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_europe/events` | 2025-03-21T00:00:00Z | 1 |
| 20 | FIFA WC qualification — UEFA (2025) | FIFA World Cup qualification | `soccer_fifa_world_cup_qualifiers_europe` | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_europe/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 21 | FIFA WC qualification — CONMEBOL (2025) | FIFA World Cup qualification | `soccer_fifa_world_cup_qualifiers_south_america` | discovery | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_south_america/events` | 2025-03-25T00:00:00Z | 1 |
| 22 | FIFA WC qualification — CONMEBOL (2025) | FIFA World Cup qualification | `soccer_fifa_world_cup_qualifiers_south_america` | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_south_america/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 23 | FIFA WC qualification — AFC (2024) | FIFA World Cup qualification | `soccer_fifa_world_cup_qualifiers_asia` | discovery | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_asia/events` | 2024-06-06T00:00:00Z | 1 |
| 24 | FIFA WC qualification — AFC (2024) | FIFA World Cup qualification | `soccer_fifa_world_cup_qualifiers_asia` | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_asia/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 25 | International friendlies (2024 March window) | Friendly | `soccer_international_friendlies` | discovery | `/v4/historical/sports/soccer_international_friendlies/events` | 2024-03-26T00:00:00Z | 1 |
| 26 | International friendlies (2024 March window) | Friendly | `soccer_international_friendlies` | snapshot T-1h | `/v4/historical/sports/soccer_international_friendlies/events/{event_id}/odds` | discovered kickoff T-1h | 10 |

## Per-competition coverage

| competition | candidate sport_key | probed date | events listed | Pinnacle T-1h | drift (min) | staleness (min) | notes |
|---|---|---|---|---|---|---|---|
| UEFA Nations League (2022 group stage) | `soccer_uefa_nations_league` | 2022-06-14 | 12 | n | 5.0 | - | sample fixture: Armenia v Scotland |
| UEFA Nations League (2025 quarter-finals) | `soccer_uefa_nations_league` | 2025-03-20 | 12 | n | 4.4 | - | sample fixture: Armenia v Georgia |
| CONCACAF Nations League (2023) | `soccer_concacaf_nations_league` | 2023-11-21 | - | - | - | - | a paid slate discovery for this key failed (HTTPStatusError: Client error '404 Not Found' for url 'https://api.the-odds-api.com/v4/historical/sports/soccer_concacaf_nations_league/events' For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404; paid evidence archived as raw_sha256=c48d635091eba3216cc30c9b1b8fc355a6a954ef10d6cefde85b262e5c186159) — never re-bought |
| Copa América (2024) | `soccer_conmebol_copa_america` | 2024-06-22 | 23 | y | 4.4 | 4.6 | sample fixture: Peru v Chile |
| Africa Cup of Nations qualification (2024) | `soccer_africa_cup_of_nations_qualification` | 2024-10-11 | - | - | - | - | a paid slate discovery for this key failed (HTTPStatusError: Client error '404 Not Found' for url 'https://api.the-odds-api.com/v4/historical/sports/soccer_africa_cup_of_nations_qualification/events' For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404; paid evidence archived as raw_sha256=c48d635091eba3216cc30c9b1b8fc355a6a954ef10d6cefde85b262e5c186159) — never re-bought |
| AFC Asian Cup (2023/24 finals) | `soccer_afc_asian_cup` | 2024-01-23 | - | - | - | - | a paid slate discovery for this key failed (HTTPStatusError: Client error '404 Not Found' for url 'https://api.the-odds-api.com/v4/historical/sports/soccer_afc_asian_cup/events' For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404; paid evidence archived as raw_sha256=c48d635091eba3216cc30c9b1b8fc355a6a954ef10d6cefde85b262e5c186159) — never re-bought |
| Africa Cup of Nations (2023/24 finals) | `soccer_africa_cup_of_nations` | 2024-01-22 | 12 | y | 4.4 | 4.9 | sample fixture: Guinea-Bissau v Nigeria |
| CONCACAF Gold Cup (2023) | `soccer_concacaf_gold_cup` | 2023-07-16 | 0 | - | - | - | no usable event in the 0 listed for `soccer_concacaf_gold_cup` on 2023-07-16 — either the archive does not carry this competition or the CANDIDATE sport key is wrong; both read the same here, so rule the key out before concluding the competition is absent |
| UEFA Euro 2024 qualification | `soccer_uefa_euro_qualification` | 2023-06-16 | 0 | - | - | - | no usable event in the 0 listed for `soccer_uefa_euro_qualification` on 2023-06-16 — either the archive does not carry this competition or the CANDIDATE sport key is wrong; both read the same here, so rule the key out before concluding the competition is absent |
| FIFA WC qualification — UEFA (2025) | `soccer_fifa_world_cup_qualifiers_europe` | 2025-03-21 | 0 | - | - | - | no usable event in the 0 listed for `soccer_fifa_world_cup_qualifiers_europe` on 2025-03-21 — either the archive does not carry this competition or the CANDIDATE sport key is wrong; both read the same here, so rule the key out before concluding the competition is absent |
| FIFA WC qualification — CONMEBOL (2025) | `soccer_fifa_world_cup_qualifiers_south_america` | 2025-03-25 | 5 | y | 4.3 | 4.7 | sample fixture: Bolivia v Uruguay |
| FIFA WC qualification — AFC (2024) | `soccer_fifa_world_cup_qualifiers_asia` | 2024-06-06 | - | - | - | - | a paid slate discovery for this key failed (HTTPStatusError: Client error '404 Not Found' for url 'https://api.the-odds-api.com/v4/historical/sports/soccer_fifa_world_cup_qualifiers_asia/events' For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404; paid evidence archived as raw_sha256=c48d635091eba3216cc30c9b1b8fc355a6a954ef10d6cefde85b262e5c186159) — never re-bought |
| International friendlies (2024 March window) | `soccer_international_friendlies` | 2024-03-26 | - | - | - | - | a paid slate discovery for this key failed (HTTPStatusError: Client error '404 Not Found' for url 'https://api.the-odds-api.com/v4/historical/sports/soccer_international_friendlies/events' For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404; paid evidence archived as raw_sha256=c48d635091eba3216cc30c9b1b8fc355a6a954ef10d6cefde85b262e5c186159) — never re-bought |

Provenance (full sha256 of the archived raw response; dry-run hashes are of MOCK bytes and are not persisted):

- UEFA Nations League (2022 group stage): discovery 8f825cb478b2049452398a44bdb6025b498222531197ab6f49fe0820f7de43e0
- UEFA Nations League (2025 quarter-finals): discovery 3381748578007ccc8cf9ad8d5019ad326224afef86da4005454d65612a03a92b
- CONCACAF Nations League (2023): -
- Copa América (2024): discovery d50f297ca91aff5664b05f4c412b0d76225752d769f6fa5beb705527da1be1d2, T-1h 4b7a7cd6e9487cf4d87617f07a772a540d1984f50fc06fcf20efb3dce5e2b323
- Africa Cup of Nations qualification (2024): -
- AFC Asian Cup (2023/24 finals): -
- Africa Cup of Nations (2023/24 finals): discovery a8a3e07d8e846e1c1fab8eca9b3820dcee944c7ca70a29ba7ba14f0a1ac052fb
- CONCACAF Gold Cup (2023): discovery 71fbd6700048e4d3d992e787748ebdd9a0307fb0a4ec110eadd334ebdbbb9244
- UEFA Euro 2024 qualification: discovery 3b261141332a3e8ec2f4365dd485301be612e2f36cb39f90241707090a36c28a
- FIFA WC qualification — UEFA (2025): discovery 68af976fe753fcf78a0d0ca0ae01df7257afa0fd3dc9ccca0c4ce72e875283d1
- FIFA WC qualification — CONMEBOL (2025): discovery 4601621ff449f3f1d1ef73e71594c595a7ccc2d556df8cfc36ca9e0374625baf, T-1h 628f0cba6686fb0f395e9e4ac7c4615c46a0ceca2676444a7e056803905068d9
- FIFA WC qualification — AFC (2024): -
- International friendlies (2024 March window): -

## Actual usage (`x-requests-last` / `x-requests-used` / `x-requests-remaining` headers)

| call | path | x-requests-last | x-requests-used | x-requests-remaining |
|---|---|---|---|---|
| 1 | `/v4/historical/sports/soccer_conmebol_copa_america/events` | 1 | 34 | 19966 |
| 2 | `/v4/historical/sports/soccer_conmebol_copa_america/events/c9746650027f5f6e28985b40c243db1a/odds` | 10 | 44 | 19956 |
| 3 | `/v4/historical/sports/soccer_concacaf_gold_cup/events` | 0 | 44 | 19956 |
| 4 | `/v4/historical/sports/soccer_uefa_euro_qualification/events` | 0 | 44 | 19956 |
| 5 | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_europe/events` | 0 | 44 | 19956 |
| 6 | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_south_america/events` | 1 | 45 | 19955 |
| 7 | `/v4/historical/sports/soccer_fifa_world_cup_qualifiers_south_america/events/5a9968330ea59400dd8151dc4d182a4a/odds` | 10 | 55 | 19945 |

Actual billed this run: **22 credits** — vs `--max-credits` 4800; modeled spend 68 credits.

## What this decides

- `oa_dev_slate.competitions` (config): the competitions above with a listing AND a sharp quote. A competition the archive does not carry cannot contribute dev fixtures at any price.
- `oa_dev_slate.n_dev`: sized from those competitions' fixture counts against the G-B cap, then frozen — the manifest is hash-bound into the V8 lock, so N_dev is pre-registered, never a yield.
- Neither is decided here by an agent: both land in config as the user's call at the spend gate.
