# OA-0a probe — Odds API coverage + cost (spec finding 13)

**MODE: LIVE.** Real paid responses from The Odds API.

## Sport keys under test (config `odds.sport_keys`)

- wc2022: `soccer_fifa_world_cup` — the probe VERIFIES this exact string; a wrong key is corrected in config, no code change
- euro2024: `soccer_uefa_european_championship` — the probe VERIFIES this exact string; a wrong key is corrected in config, no code change
- wc2026: `soccer_fifa_world_cup` — the probe VERIFIES this exact string; a wrong key is corrected in config, no code change

## Call plan + projected credit cost

15 fixtures x (1 discovery @ 1 credit + 2 snapshots [T-24h, T-1h; h2h x eu = 1 region-market] @ 10 credits): 15 discovery + 30 snapshot calls = **315 credits** projected; modeled spend this run: 295.

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
| Qatar v Ecuador (2022-11-20) | 2022-11-20T16:00:00Z | 2022-11-19T16:00:00Z | 2022-11-20T15:00:00Z |
| Argentina v Mexico (2022-11-26) | 2022-11-26T19:00:00Z | 2022-11-25T19:00:00Z | 2022-11-26T18:00:00Z |
| South Korea v Portugal (2022-12-02) | 2022-12-02T15:00:00Z | 2022-12-01T15:00:00Z | 2022-12-02T14:00:00Z |
| Netherlands v United States (2022-12-03) | - | - | - |
| Argentina v France (2022-12-18) | 2022-12-18T15:00:00Z | 2022-12-17T15:00:00Z | 2022-12-18T14:00:00Z |
| Germany v Scotland (2024-06-14) | 2024-06-14T19:00:00Z | 2024-06-13T19:00:00Z | 2024-06-14T18:00:00Z |
| Germany v Hungary (2024-06-19) | 2024-06-19T16:00:00Z | 2024-06-18T16:00:00Z | 2024-06-19T15:00:00Z |
| Georgia v Portugal (2024-06-26) | 2024-06-26T19:00:00Z | 2024-06-25T19:00:00Z | 2024-06-26T18:00:00Z |
| Spain v Georgia (2024-06-30) | 2024-06-30T19:00:00Z | 2024-06-29T19:00:00Z | 2024-06-30T18:00:00Z |
| Spain v England (2024-07-14) | 2024-07-14T19:00:00Z | 2024-07-13T19:00:00Z | 2024-07-14T18:00:00Z |
| Mexico v South Africa (2026-06-11) | 2026-06-11T19:00:00Z | 2026-06-10T19:00:00Z | 2026-06-11T18:00:00Z |
| Canada v Qatar (2026-06-18) | 2026-06-18T22:00:00Z | 2026-06-17T22:00:00Z | 2026-06-18T21:00:00Z |
| Colombia v Portugal (2026-06-27) | 2026-06-27T23:30:00Z | 2026-06-26T23:30:00Z | 2026-06-27T22:30:00Z |
| Brazil v Japan (2026-06-29) | 2026-06-29T17:00:00Z | 2026-06-28T17:00:00Z | 2026-06-29T16:00:00Z |
| Spain v Argentina (2026-07-19) | 2026-07-19T19:00:00Z | 2026-07-18T19:00:00Z | 2026-07-19T18:00:00Z |

## Per-fixture results

| pool | stratum | fixture | event found | Pinnacle T-24h | Pinnacle T-1h | snapshot drift T-24h (min) | drift T-1h (min) | Pinnacle last_update staleness at T-1h (min) | notes |
|---|---|---|---|---|---|---|---|---|---|
| wc2022 | opening_day | Qatar v Ecuador (2022-11-20) | y | y | y | 4.4 | 4.4 | 5.9 | - |
| wc2022 | mid_group | Argentina v Mexico (2022-11-26) | y | y | y | 4.4 | 4.3 | 4.8 | - |
| wc2022 | last_group_day | South Korea v Portugal (2022-12-02) | y | y | y | 4.4 | 4.4 | 4.8 | - |
| wc2022 | knockout | Netherlands v United States (2022-12-03) | n | - | - | - | - | - | not among 8 listed events (closest names first, up to 8; the API spells teams its own way — e.g. 'USA'/'Korea Republic' for the store's 'United States'/'South Korea' — so a spelling mismatch here reads exactly like absent coverage; rule that out against these names before concluding the event is missing): Netherlands v USA; England v Senegal; Portugal v Switzerland; France v Poland; Argentina v Australia; Brazil v South Korea; Japan v Croatia; Morocco v Spain |
| wc2022 | final | Argentina v France (2022-12-18) | y | y | y | 4.3 | 4.3 | 4.8 | - |
| euro2024 | opening_day | Germany v Scotland (2024-06-14) | y | y | y | 4.4 | 4.4 | 4.5 | - |
| euro2024 | mid_group | Germany v Hungary (2024-06-19) | y | y | y | 4.4 | 4.4 | 4.6 | - |
| euro2024 | last_group_day | Georgia v Portugal (2024-06-26) | y | y | y | 4.4 | 4.4 | 4.8 | - |
| euro2024 | knockout | Spain v Georgia (2024-06-30) | y | y | y | 4.4 | 4.4 | 4.4 | - |
| euro2024 | final | Spain v England (2024-07-14) | y | y | y | 4.4 | 4.4 | 5.1 | - |
| wc2026 | opening_day | Mexico v South Africa (2026-06-11) | y | y | y | 4.4 | 4.4 | 4.6 | - |
| wc2026 | mid_group | Canada v Qatar (2026-06-18) | y | y | y | 4.4 | 4.4 | 4.7 | - |
| wc2026 | last_group_day | Colombia v Portugal (2026-06-27) | y | y | y | 4.4 | 4.4 | 4.4 | - |
| wc2026 | knockout | Brazil v Japan (2026-06-29) | y | y | y | 4.4 | 4.4 | 4.8 | - |
| wc2026 | final | Spain v Argentina (2026-07-19) | y | y | y | 4.4 | 4.4 | 4.5 | - |

Provenance (full sha256 of the archived raw response; dry-run hashes are of MOCK bytes and are not persisted):

- Qatar v Ecuador (2022-11-20): discovery c021f9b0b33c1e491e09120d4b64cbd26b7569715e0f4209add7fe4dcec465b7, T-24h 5465f8d33bae3e6b93f5c9e7b8ffce6bbfffd855259040c39a9ba82765d8e362, T-1h c798a23b572650a22a0348fb26bd465e64aca2083f5a437acf87af1c98014c36
- Argentina v Mexico (2022-11-26): discovery e850739dbcfed16770df7caff5fed7eadfebf6526a83cb1bdd59ba33cdfaa3cf, T-24h 2466c96cc7eaa87c1c2358815d2fd40f86dcd16c8735459b155fd3bda8382a03, T-1h 78fde5301f26703595ab491f2bcdb198c2ab8cd6f5390d6a2dac8eb73589d241
- South Korea v Portugal (2022-12-02): discovery b2010466eb5734e9d5a945c2120babc014d1a5ad312ce4dd2d7451a27c67d25c, T-24h 681036270254f0bf3def5a9965e943284649076a9d7907142a9dd1599361683b, T-1h 4ea7c57f322ad517d86a2a6edaab36295a97d25e293a4a21a968717b78ffd0f9
- Netherlands v United States (2022-12-03): discovery 5f3181ad3544decedea6adbc30127a55a352aecde59b8a4b0be79f381d951cc2
- Argentina v France (2022-12-18): discovery 320bc0851899a87dede2ff08443fb00a5ef61b7beaa068eaa2e156a0d79ddc20, T-24h 777c3b27c7ab2aca9ce4aaa7bdb742278f7366256d6b033b2760fc9f7fad93c9, T-1h 5258334c76ae60e1f3b39f649928e8a71c433f5c88ab7b09d3c5b3430bdd635c
- Germany v Scotland (2024-06-14): discovery 3a43c4e815045ac57c889adcee0716911d0f2ad01c6b6b8de9dd35f13a00612f, T-24h fae684f2f189f290fb3c01b13c78fab91ece90af301534f3871d719fbcee5e0d, T-1h dd50c4e487cf7014237edbf50b5ce746cfc08ba96db49f5f83c19e289c0ec726
- Germany v Hungary (2024-06-19): discovery d878af464dfc46b5a99f8813fa4b91163bf58a9c00b2ce95177e79175aa225f4, T-24h bd3ade1b90498a50f9c6d7a6e311e13cf0c46b93ad6ddb90ab2bff55a3f9e6db, T-1h 783e9dc2136f7a2c334cb3e733b30c72c29e0c0fb210a50e230c6645c39987e0
- Georgia v Portugal (2024-06-26): discovery 67a1e1bd76e44330a6910d0af1b028418f8ecf754824e448d399cecb8bb49dd7, T-24h d7704613f225f1052fd43e72dacdd9c20dcb31e5ab07a33ad2fdbbccd9f01641, T-1h 7ec3f73c7f9a5e8c7591006456bdb086727fc3048e6e29a0fd5e2d4707d11276
- Spain v Georgia (2024-06-30): discovery 1b7f8d9a351ab797859b9b3f060ee920a7b58d7d8bd6ee79bf53c6f3d5c34334, T-24h 4644822495a1d509d48c779d76627ee4aa10e4a20a969286be87aa70b6ccdfd1, T-1h 5002ddaca848200253be06123b193980aaa4e129a7f7e1d39fa968c8cd83a3d8
- Spain v England (2024-07-14): discovery a080c518659202f40f47f6ae67db235ca01ac75373bcbb7e7625678d85f2a17b, T-24h 5bb01e194167c094fa16cd376c71bf231d8a3cb1889a6b71d99d33ec1d26b938, T-1h 7844e6742049efb61869893a537e05001291e339f11c2a140f27d3b5484b279a
- Mexico v South Africa (2026-06-11): discovery b909ec4f00fb22e8638d0c09d06ceacae70329373166ffd07fc7151412c5f940, T-24h c5a5664660201b31ee9bf3f966272423b9dea7ade2988962f9cbec9e4016f048, T-1h 43c24b5bc72d530ce069069cbc09649a56ce57f28aad08e5df5c73c05b55d59c
- Canada v Qatar (2026-06-18): discovery a391bcca5188e352b7ff9c94132442607fc03bdc7122ec37f3a5b5a007fe0d7d, T-24h 178e43f7da6ae3145a4cf13ec42c5e1761a34b9c1f0b956dbb09b76a71f5e03e, T-1h c28812929d2354489f146fdb6f70a960656c63be91736bc9ca82d8039dff0da0
- Colombia v Portugal (2026-06-27): discovery ef5ac24f7bed2c5bc6c01d2807c43646d7281c1710c35de1cba816363c67d623, T-24h c0f63075a45d1ee0c52ca40174f9dfc19d43a7cee70b0e2b764804f52627d34c, T-1h 05c57491eb52141b4050cbcff9138672a5cb478487120ac553a662d940adb0aa
- Brazil v Japan (2026-06-29): discovery 7e65088ca0a5d604a76c22bd474e5725a7475ff1f989872e2c09a60ff39ff39d, T-24h 55bd440c914d043705089d2afbc8de86fe2c2d9753c19655ae7742695f88ce57, T-1h 005f00c99ec480c382bb5478293fd9d5a48b6ce45d4cc8d982bc344e221f1036
- Spain v Argentina (2026-07-19): discovery 72aaf29c8930a7cbe49e3eaed7f17ee8fe42c732db32d4c77b9907a2346974a5, T-24h 8c7d4aa924c70bb4b79c0ff33c643682dab0eaef0b9dbf89626b2274ec135f7c, T-1h d3506bf14f3685c5433897e4eb3fa247ff32189a430107cf326b7a70ad0efd77

## Actual usage (`x-requests-last` / `x-requests-used` / `x-requests-remaining` headers)

| call | path | x-requests-last | x-requests-used | x-requests-remaining |
|---|---|---|---|---|
| 1 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 1 | 19999 |
| 2 | `/v4/historical/sports/soccer_fifa_world_cup/events/3fc968505e3de3acbb9baa2876925172/odds` | 10 | 11 | 19989 |
| 3 | `/v4/historical/sports/soccer_fifa_world_cup/events/3fc968505e3de3acbb9baa2876925172/odds` | 10 | 21 | 19979 |
| 4 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 22 | 19978 |
| 5 | `/v4/historical/sports/soccer_fifa_world_cup/events/9efa2a256d710b0b665146a2736ac2e7/odds` | 10 | 32 | 19968 |
| 6 | `/v4/historical/sports/soccer_fifa_world_cup/events/9efa2a256d710b0b665146a2736ac2e7/odds` | 10 | 42 | 19958 |
| 7 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 43 | 19957 |
| 8 | `/v4/historical/sports/soccer_fifa_world_cup/events/a93d6beff117e69247386c1ed8f7b29d/odds` | 10 | 53 | 19947 |
| 9 | `/v4/historical/sports/soccer_fifa_world_cup/events/a93d6beff117e69247386c1ed8f7b29d/odds` | 10 | 63 | 19937 |
| 10 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 64 | 19936 |
| 11 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 65 | 19935 |
| 12 | `/v4/historical/sports/soccer_fifa_world_cup/events/95ffdb09924c60f46b75ca6f106b676c/odds` | 10 | 75 | 19925 |
| 13 | `/v4/historical/sports/soccer_fifa_world_cup/events/95ffdb09924c60f46b75ca6f106b676c/odds` | 10 | 85 | 19915 |
| 14 | `/v4/historical/sports/soccer_uefa_european_championship/events` | 1 | 86 | 19914 |
| 15 | `/v4/historical/sports/soccer_uefa_european_championship/events/3e55e803b702a58c5ab64df5fc18ebad/odds` | 10 | 96 | 19904 |
| 16 | `/v4/historical/sports/soccer_uefa_european_championship/events/3e55e803b702a58c5ab64df5fc18ebad/odds` | 10 | 106 | 19894 |
| 17 | `/v4/historical/sports/soccer_uefa_european_championship/events` | 1 | 107 | 19893 |
| 18 | `/v4/historical/sports/soccer_uefa_european_championship/events/90c57e78c3442831cffa36c9e423e560/odds` | 10 | 117 | 19883 |
| 19 | `/v4/historical/sports/soccer_uefa_european_championship/events/90c57e78c3442831cffa36c9e423e560/odds` | 10 | 127 | 19873 |
| 20 | `/v4/historical/sports/soccer_uefa_european_championship/events` | 1 | 128 | 19872 |
| 21 | `/v4/historical/sports/soccer_uefa_european_championship/events/bda40e8c885c8037501f7d95ecdbd99d/odds` | 10 | 138 | 19862 |
| 22 | `/v4/historical/sports/soccer_uefa_european_championship/events/bda40e8c885c8037501f7d95ecdbd99d/odds` | 10 | 148 | 19852 |
| 23 | `/v4/historical/sports/soccer_uefa_european_championship/events` | 1 | 149 | 19851 |
| 24 | `/v4/historical/sports/soccer_uefa_european_championship/events/d6fc55a7ce9c0b895191bae5f91019a6/odds` | 10 | 159 | 19841 |
| 25 | `/v4/historical/sports/soccer_uefa_european_championship/events/d6fc55a7ce9c0b895191bae5f91019a6/odds` | 10 | 169 | 19831 |
| 26 | `/v4/historical/sports/soccer_uefa_european_championship/events` | 1 | 170 | 19830 |
| 27 | `/v4/historical/sports/soccer_uefa_european_championship/events/6815a8f217d293be0d4dd291d6567966/odds` | 10 | 180 | 19820 |
| 28 | `/v4/historical/sports/soccer_uefa_european_championship/events/6815a8f217d293be0d4dd291d6567966/odds` | 10 | 190 | 19810 |
| 29 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 191 | 19809 |
| 30 | `/v4/historical/sports/soccer_fifa_world_cup/events/80d82d1113934bfbea4ce8daf37a2433/odds` | 10 | 201 | 19799 |
| 31 | `/v4/historical/sports/soccer_fifa_world_cup/events/80d82d1113934bfbea4ce8daf37a2433/odds` | 10 | 211 | 19789 |
| 32 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 212 | 19788 |
| 33 | `/v4/historical/sports/soccer_fifa_world_cup/events/fa9502285b257b03e62968d50d9229fc/odds` | 10 | 222 | 19778 |
| 34 | `/v4/historical/sports/soccer_fifa_world_cup/events/fa9502285b257b03e62968d50d9229fc/odds` | 10 | 232 | 19768 |
| 35 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 233 | 19767 |
| 36 | `/v4/historical/sports/soccer_fifa_world_cup/events/67ae5751c401a98409b8566ae4897069/odds` | 10 | 243 | 19757 |
| 37 | `/v4/historical/sports/soccer_fifa_world_cup/events/67ae5751c401a98409b8566ae4897069/odds` | 10 | 253 | 19747 |
| 38 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 254 | 19746 |
| 39 | `/v4/historical/sports/soccer_fifa_world_cup/events/4f3d72fba877939d36a5315618184093/odds` | 10 | 264 | 19736 |
| 40 | `/v4/historical/sports/soccer_fifa_world_cup/events/4f3d72fba877939d36a5315618184093/odds` | 10 | 274 | 19726 |
| 41 | `/v4/historical/sports/soccer_fifa_world_cup/events` | 1 | 275 | 19725 |
| 42 | `/v4/historical/sports/soccer_fifa_world_cup/events/fb30113e43d113f1ace48b8563ba1ee9/odds` | 10 | 285 | 19715 |
| 43 | `/v4/historical/sports/soccer_fifa_world_cup/events/fb30113e43d113f1ace48b8563ba1ee9/odds` | 10 | 295 | 19705 |

Actual billed this run: **295 credits** — the LARGER of the summed per-call `x-requests-last` costs and the `x-requests-used` counter delta (the delta alone cannot see the first response's own cost, so where `x-requests-last` is absent the true spend can be up to one call price higher) — vs `--max-credits` 315; modeled spend 295 credits.

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
