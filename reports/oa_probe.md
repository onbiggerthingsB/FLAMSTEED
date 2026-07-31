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

## Requested instants (discovered kickoff -> the two snapshot requests)

Sign convention in the results table: drift = requested - snapshot ts, staleness = requested - Pinnacle's strictest last_update (both in minutes; NEGATIVE means the stamp postdates the requested instant). The strict pre-kickoff rule (OA F2, admissible_quote): a snapshot ts or last_update at/after the discovered kickoff is an IN-PLAY price and is flagged in the notes column — never a clean pre-kickoff quote.

| fixture | discovered kickoff | requested T-24h | requested T-1h |
|---|---|---|---|
| Qatar v Ecuador (2022-11-20) | 2022-11-20T18:00:00Z | 2022-11-19T18:00:00Z | 2022-11-20T17:00:00Z |
| Argentina v Mexico (2022-11-26) | 2022-11-26T18:00:00Z | 2022-11-25T18:00:00Z | 2022-11-26T17:00:00Z |
| South Korea v Portugal (2022-12-02) | 2022-12-02T18:00:00Z | 2022-12-01T18:00:00Z | 2022-12-02T17:00:00Z |
| Netherlands v United States (2022-12-03) | 2022-12-03T18:00:00Z | 2022-12-02T18:00:00Z | 2022-12-03T17:00:00Z |
| Argentina v France (2022-12-18) | 2022-12-18T18:00:00Z | 2022-12-17T18:00:00Z | 2022-12-18T17:00:00Z |
| Germany v Scotland (2024-06-14) | 2024-06-14T18:00:00Z | 2024-06-13T18:00:00Z | 2024-06-14T17:00:00Z |
| Germany v Hungary (2024-06-19) | 2024-06-19T18:00:00Z | 2024-06-18T18:00:00Z | 2024-06-19T17:00:00Z |
| Georgia v Portugal (2024-06-26) | 2024-06-26T18:00:00Z | 2024-06-25T18:00:00Z | 2024-06-26T17:00:00Z |
| Spain v Georgia (2024-06-30) | 2024-06-30T18:00:00Z | 2024-06-29T18:00:00Z | 2024-06-30T17:00:00Z |
| Spain v England (2024-07-14) | 2024-07-14T18:00:00Z | 2024-07-13T18:00:00Z | 2024-07-14T17:00:00Z |
| Mexico v South Africa (2026-06-11) | 2026-06-11T18:00:00Z | 2026-06-10T18:00:00Z | 2026-06-11T17:00:00Z |
| Canada v Qatar (2026-06-18) | 2026-06-18T18:00:00Z | 2026-06-17T18:00:00Z | 2026-06-18T17:00:00Z |
| Colombia v Portugal (2026-06-27) | 2026-06-27T18:00:00Z | 2026-06-26T18:00:00Z | 2026-06-27T17:00:00Z |
| Brazil v Japan (2026-06-29) | 2026-06-29T18:00:00Z | 2026-06-28T18:00:00Z | 2026-06-29T17:00:00Z |
| Spain v Argentina (2026-07-19) | 2026-07-19T18:00:00Z | 2026-07-18T18:00:00Z | 2026-07-19T17:00:00Z |

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

Provenance (full sha256 of the archived raw response; dry-run hashes are of MOCK bytes and are not persisted):

- Qatar v Ecuador (2022-11-20): discovery 43c9d370af91265bd41852f4a8fe3ea0659a099c59662cad1580048718a32448, T-24h aef4a5ed70ea40c7f60dd0d4556b4089d1da53779651157e06fd13dbdb8ba198, T-1h 3342c266a86865ae32bf03bc97071e9c6ead257ecd1129de1c615a2d69d85f4e
- Argentina v Mexico (2022-11-26): discovery 51a401f122f720cd17ec8bfa84320c664acb6f3e867a8763828bd95229d35f21, T-24h a15d892d329020eeeba7b66271d97428cd051c12db8577d2779d4a03063b751d, T-1h 7bd4680d5031373399dbf1c17e5410064f00da295b70384a5faca993e17a652c
- South Korea v Portugal (2022-12-02): discovery 25718d8420868ec1eea0475ba61f4830bc4740f7c914e8f73f9727587300d3b5, T-24h d0fdefe81d2b3b0cb87ab2c8edf290ef9a2aafe51e6a5ef47e55f0f90bb4a23e, T-1h f2d78cefeec339521f3b67b644327ed586259103abf685ae066f6f4aca4f3ef4
- Netherlands v United States (2022-12-03): discovery 0dcc405fdc4d8ec51a1a4bb9101c9711f1713bd65802644c9745b113321f61e6, T-24h b71eda71345474a3fc5b3734b9288e6b105e174a2a5be8739f13dc933795e788, T-1h 82abacec7b85d62eec45278e87a83be5e04571abbb3a5b96b9792463aa91e2ab
- Argentina v France (2022-12-18): discovery 7b440cce816d3cb59c7668f2ca4d8cb194b6a9fcc52b4ff9190979875778b851, T-24h 1984d1c74af9b45f4d9930cfb2d563a3603ffdab41d137c5ebd1c729c690af9e, T-1h 84f46f0122ac3e2e35364f2569f73072fbfda0b5cd50962aa4509fdf94d6192d
- Germany v Scotland (2024-06-14): discovery d3ac46bc662d4c0a39b8fb711377a9dd5019e292025accd0ec9b9d99a2d85141, T-24h 5dc179b594d1a0fb20edddaa36d4f82af4eb28129b8111aa23e56a902071aa55, T-1h acc138476e751f47d27393e09bca0d2cfe6985a03da3e5a18ef4130e5f04ffe9
- Germany v Hungary (2024-06-19): discovery 0d36fbbaeae4505be6fddcaecf1b83b42a4d6b6dcec8e28747285ff9eafa096f, T-24h e1bbfed211f3c60e2e37f42f51b48a20dbbf315ef4d02578eaace847ad673dc1, T-1h efbf29c91d10b8540af5b07c852c87553fbdc6aadc3196fb7a32875cd2aacbd1
- Georgia v Portugal (2024-06-26): discovery 528397ed7d5237a79ea129ffd68cea6fdd84042678941b41f099918b7ff6a598, T-24h 805f0508fe790ebd0bff7504346afffb35f8c0c1a51f86b9b5d67c92162590e5, T-1h 74c825d9447549a3567de259e0267c87ae8c782582ce77c8cd77fc01a4139fc3
- Spain v Georgia (2024-06-30): discovery e80e0d3887d1ff1194cbb457b2e415cb80afcd2f77a294e3b1aa1ee16f6088a1, T-24h 97864a2e7fdc5c4f716aca429f890480e860e666e86c6cced6419a18b556ceb5, T-1h 6a5dcb3dff683506c69acaf08db38fd72bc523250c1d3817e02f6be55ceb21db
- Spain v England (2024-07-14): discovery ae6d9e4e832535949545b4b7481f66314d333f74fdeceb6fd17e1145b7f4e392, T-24h 3c423d4d347079d08a40cc6c5edd509d304bda890e58cf50b83cf2e9f1b228b9, T-1h 65330f1ac6c7f6c75f8c94cb316f783842eb49017cd7195b97a24feeac5a6d4f
- Mexico v South Africa (2026-06-11): discovery 62e5cabf1c2c6e7b73968f42c85b71f64d448d9375834617db6e9d07ee10028b, T-24h 97aeb1ecb7f81483f326137fdb6f77fa860b59be36c9d2340917129eff85a836, T-1h 2426a919647cd51e925c31e7928812d093179a3f9cc387c6cfeb1372af342249
- Canada v Qatar (2026-06-18): discovery 9dbfeb8c34ea50bc48251a7efae06a19ed6d34a2742e6ad31a9b5c4cab6bebdf, T-24h 57a1611f5d5b07bffc671fc30d77742fd2259de5e438530e1464ec5587a36edc, T-1h d7ee31b602bd891a3a28a1671986a5fb68ada3cebbaa649f10f14e5bb82a2b7f
- Colombia v Portugal (2026-06-27): discovery 8ccfedc83866f2af2ff1fa94f1f35c4d360e74a259ca09506ab04a488e698745, T-24h 64d7f62e4f42a733006738339c027149889413ac12efabdef2e888706fa1f8ce, T-1h 0e071864a80590f26e21a2bd5dbe738583059de63be5caddb058b37e960ad909
- Brazil v Japan (2026-06-29): discovery 317da03951eb5b3341643760ed9e0a43a684d26855544381ea67a11668740590, T-24h d4662171890159bcdd84c6a52cdf2ff28f091add245bfcb9dda136bcb782b541, T-1h 95e3664b3616a60dc4770ea81e6313a127e445116a6b2a341fd270379e888fd5
- Spain v Argentina (2026-07-19): discovery 7fbe48e4421f271a7360088e41e0c5d9dd905b7fa78d9fb9b5d26bb4545ba753, T-24h 45809bdb28ab8f81330bfcff8f12cc94e1977cb9df6318a7a3c2bf130ce51d27, T-1h e4efddb9e291d19d78e9b8358e3b1c19399ec4620adeddca03169184f23ec53f

## Actual usage (`x-requests-last` / `x-requests-used` / `x-requests-remaining` headers)

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
