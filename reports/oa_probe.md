# OA-0a probe — Odds API coverage + cost (spec finding 13)

**MODE: DRY-RUN.** Every response below came from recorded-shape MOCK payloads served by an in-process transport: ZERO network calls, ZERO credits spent, and the env `ODDS_API_KEY` was never read. Coverage/freshness values prove the pipeline and are NOT measurements — the user-gated live probe overwrites this report with real ones.

## Sport keys under test (config `odds.sport_keys`)

- wc2022: `soccer_fifa_world_cup` — the probe VERIFIES this exact string; a wrong key is corrected in config, no code change
- euro2024: `soccer_uefa_european_championship` — the probe VERIFIES this exact string; a wrong key is corrected in config, no code change
- wc2026: `soccer_fifa_world_cup` — the probe VERIFIES this exact string; a wrong key is corrected in config, no code change

## Call plan + projected credit cost

15 fixtures x (1 discovery @ 1 credit + 2 snapshots [T-24h, T-1h; h2h x eu = 1 region-market] @ 10 credits): 15 discovery + 30 snapshot calls = **315 credits** projected; modeled spend this run: 315 (dry-run: 0 actually billed).

| # | fixture | pool | stratum | call | endpoint | at | credits |
|---|---|---|---|---|---|---|---|
| 1 | Qatar v Ecuador (2022-11-20) | wc2022 | opening_day | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2022-11-20T00:00:00Z | 1 |
| 2 | Qatar v Ecuador (2022-11-20) | wc2022 | opening_day | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 3 | Qatar v Ecuador (2022-11-20) | wc2022 | opening_day | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 4 | Argentina v Mexico (2022-11-26) | wc2022 | mid_group | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2022-11-26T00:00:00Z | 1 |
| 5 | Argentina v Mexico (2022-11-26) | wc2022 | mid_group | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 6 | Argentina v Mexico (2022-11-26) | wc2022 | mid_group | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 7 | South Korea v Portugal (2022-12-02) | wc2022 | last_group_day | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2022-12-02T00:00:00Z | 1 |
| 8 | South Korea v Portugal (2022-12-02) | wc2022 | last_group_day | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 9 | South Korea v Portugal (2022-12-02) | wc2022 | last_group_day | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 10 | Netherlands v United States (2022-12-03) | wc2022 | knockout | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2022-12-03T00:00:00Z | 1 |
| 11 | Netherlands v United States (2022-12-03) | wc2022 | knockout | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 12 | Netherlands v United States (2022-12-03) | wc2022 | knockout | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 13 | Argentina v France (2022-12-18) | wc2022 | final | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2022-12-18T00:00:00Z | 1 |
| 14 | Argentina v France (2022-12-18) | wc2022 | final | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 15 | Argentina v France (2022-12-18) | wc2022 | final | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 16 | Germany v Scotland (2024-06-14) | euro2024 | opening_day | discovery | `/v4/historical/sports/soccer_uefa_european_championship/events` | 2024-06-14T00:00:00Z | 1 |
| 17 | Germany v Scotland (2024-06-14) | euro2024 | opening_day | snapshot T-24h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 18 | Germany v Scotland (2024-06-14) | euro2024 | opening_day | snapshot T-1h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 19 | Germany v Hungary (2024-06-19) | euro2024 | mid_group | discovery | `/v4/historical/sports/soccer_uefa_european_championship/events` | 2024-06-19T00:00:00Z | 1 |
| 20 | Germany v Hungary (2024-06-19) | euro2024 | mid_group | snapshot T-24h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 21 | Germany v Hungary (2024-06-19) | euro2024 | mid_group | snapshot T-1h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 22 | Georgia v Portugal (2024-06-26) | euro2024 | last_group_day | discovery | `/v4/historical/sports/soccer_uefa_european_championship/events` | 2024-06-26T00:00:00Z | 1 |
| 23 | Georgia v Portugal (2024-06-26) | euro2024 | last_group_day | snapshot T-24h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 24 | Georgia v Portugal (2024-06-26) | euro2024 | last_group_day | snapshot T-1h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 25 | Spain v Georgia (2024-06-30) | euro2024 | knockout | discovery | `/v4/historical/sports/soccer_uefa_european_championship/events` | 2024-06-30T00:00:00Z | 1 |
| 26 | Spain v Georgia (2024-06-30) | euro2024 | knockout | snapshot T-24h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 27 | Spain v Georgia (2024-06-30) | euro2024 | knockout | snapshot T-1h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 28 | Spain v England (2024-07-14) | euro2024 | final | discovery | `/v4/historical/sports/soccer_uefa_european_championship/events` | 2024-07-14T00:00:00Z | 1 |
| 29 | Spain v England (2024-07-14) | euro2024 | final | snapshot T-24h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 30 | Spain v England (2024-07-14) | euro2024 | final | snapshot T-1h | `/v4/historical/sports/soccer_uefa_european_championship/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 31 | Mexico v South Africa (2026-06-11) | wc2026 | opening_day | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2026-06-11T00:00:00Z | 1 |
| 32 | Mexico v South Africa (2026-06-11) | wc2026 | opening_day | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 33 | Mexico v South Africa (2026-06-11) | wc2026 | opening_day | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 34 | Canada v Qatar (2026-06-18) | wc2026 | mid_group | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2026-06-18T00:00:00Z | 1 |
| 35 | Canada v Qatar (2026-06-18) | wc2026 | mid_group | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 36 | Canada v Qatar (2026-06-18) | wc2026 | mid_group | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 37 | Colombia v Portugal (2026-06-27) | wc2026 | last_group_day | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2026-06-27T00:00:00Z | 1 |
| 38 | Colombia v Portugal (2026-06-27) | wc2026 | last_group_day | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 39 | Colombia v Portugal (2026-06-27) | wc2026 | last_group_day | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 40 | Brazil v Japan (2026-06-29) | wc2026 | knockout | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2026-06-29T00:00:00Z | 1 |
| 41 | Brazil v Japan (2026-06-29) | wc2026 | knockout | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 42 | Brazil v Japan (2026-06-29) | wc2026 | knockout | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |
| 43 | Spain v Argentina (2026-07-19) | wc2026 | final | discovery | `/v4/historical/sports/soccer_fifa_world_cup/events` | 2026-07-19T00:00:00Z | 1 |
| 44 | Spain v Argentina (2026-07-19) | wc2026 | final | snapshot T-24h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-24h | 10 |
| 45 | Spain v Argentina (2026-07-19) | wc2026 | final | snapshot T-1h | `/v4/historical/sports/soccer_fifa_world_cup/events/{event_id}/odds` | discovered kickoff T-1h | 10 |

## Per-fixture results

| pool | stratum | fixture | event found | Pinnacle T-24h | Pinnacle T-1h | snapshot drift T-24h (min) | drift T-1h (min) | Pinnacle last_update staleness at T-1h (min) | notes |
|---|---|---|---|---|---|---|---|---|---|
| wc2022 | opening_day | Qatar v Ecuador (2022-11-20) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2022 | mid_group | Argentina v Mexico (2022-11-26) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2022 | last_group_day | South Korea v Portugal (2022-12-02) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2022 | knockout | Netherlands v United States (2022-12-03) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2022 | final | Argentina v France (2022-12-18) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| euro2024 | opening_day | Germany v Scotland (2024-06-14) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| euro2024 | mid_group | Germany v Hungary (2024-06-19) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| euro2024 | last_group_day | Georgia v Portugal (2024-06-26) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| euro2024 | knockout | Spain v Georgia (2024-06-30) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| euro2024 | final | Spain v England (2024-07-14) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2026 | opening_day | Mexico v South Africa (2026-06-11) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2026 | mid_group | Canada v Qatar (2026-06-18) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2026 | last_group_day | Colombia v Portugal (2026-06-27) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2026 | knockout | Brazil v Japan (2026-06-29) | y | y | y | 3.0 | 3.0 | 8.0 | - |
| wc2026 | final | Spain v Argentina (2026-07-19) | y | y | y | 3.0 | 3.0 | 8.0 | - |

Provenance (sha256 of the archived raw response; dry-run hashes are of MOCK bytes and are not persisted):

- Qatar v Ecuador (2022-11-20): discovery 43c9d370af91, T-24h aef4a5ed70ea, T-1h 3342c266a868
- Argentina v Mexico (2022-11-26): discovery 51a401f122f7, T-24h a15d892d3290, T-1h 7bd4680d5031
- South Korea v Portugal (2022-12-02): discovery 25718d842086, T-24h d0fdefe81d2b, T-1h f2d78cefeec3
- Netherlands v United States (2022-12-03): discovery 0dcc405fdc4d, T-24h b71eda713454, T-1h 82abacec7b85
- Argentina v France (2022-12-18): discovery 7b440cce816d, T-24h 1984d1c74af9, T-1h 84f46f0122ac
- Germany v Scotland (2024-06-14): discovery d3ac46bc662d, T-24h 5dc179b594d1, T-1h acc138476e75
- Germany v Hungary (2024-06-19): discovery 0d36fbbaeae4, T-24h e1bbfed211f3, T-1h efbf29c91d10
- Georgia v Portugal (2024-06-26): discovery 528397ed7d52, T-24h 805f0508fe79, T-1h 74c825d94475
- Spain v Georgia (2024-06-30): discovery e80e0d3887d1, T-24h 97864a2e7fdc, T-1h 6a5dcb3dff68
- Spain v England (2024-07-14): discovery ae6d9e4e8325, T-24h 3c423d4d3470, T-1h 65330f1ac6c7
- Mexico v South Africa (2026-06-11): discovery 62e5cabf1c2c, T-24h 97aeb1ecb7f8, T-1h 2426a919647c
- Canada v Qatar (2026-06-18): discovery 9dbfeb8c34ea, T-24h 57a1611f5d5b, T-1h d7ee31b602bd
- Colombia v Portugal (2026-06-27): discovery 8ccfedc83866, T-24h 64d7f62e4f42, T-1h 0e071864a805
- Brazil v Japan (2026-06-29): discovery 317da03951eb, T-24h d46621718901, T-1h 95e3664b3616
- Spain v Argentina (2026-07-19): discovery 7fbe48e4421f, T-24h 45809bdb28ab, T-1h e4efddb9e291

## Actual usage (`x-requests-used` / `x-requests-remaining` headers)

Not available: dry-run serves no live responses, so no usage headers exist (and none are fabricated).

## Extrapolated full-program budget

(217 eval + N_dev) fixtures x 2 snapshots x 10 credits = **4340 + 20 x N_dev credits**

- 217 = the 185-pool (wc2022 + euro2024 + wc2026 group) + the 32 WC-2026 knockout fixtures.
- N_dev = the development-slate size — an OA-0b sizing decision and an explicit formula input, never assumed here.
- Per-event discovery, if needed, adds ~1 credit per fixture-day on top of the formula.

| N_dev (illustrative) | credits |
|---|---|
| 0 | 4340 |
| 100 | 6340 |
| 200 | 8340 |
| 400 | 12340 |
