# SOURCES

Per-source provenance, license, refresh cadence, access (free/key/scrape), the
`revision_contaminated` policy, and a `source_version` where pinned. Rows are
**appended per adapter task** (Tasks 4, 8, 9, 10, 13); Task 1 seeds the header,
the FBref/Opta note, and the first (results) row.

| Source | Feature | License | Access | Policy | source_version | Notes |
|---|---|---|---|---|---|---|
| `martj42/international_results` | match results | CC0 | free (git) | point_in_time | `dad6874bb720e23cccdf696f057aa64fa5471445` | immutable results; `valid_as_of == observed_at == match date`. `match_id = sha1(date\|home\|away\|city)`; one real same-day/same-venue double-header (Tahiti–New Caledonia, 1974-02-17) is disambiguated by a deterministic occurrence index so `match_id` is unique. |
| The Odds API (`the-odds-api.com`) | closing 1X2 odds (h2h) | proprietary ToS | **paid key** (live pull **gated** — see Phase-0 decision 1) | point_in_time | — (UNVERIFIED pricing) | CLV benchmarked vs **Pinnacle closing**; historical endpoint returns one timestamped snapshot per call, so we capture a bet-time + near-kickoff `close` series. `valid_as_of == observed_at == snapshot timestamp`. Adapter is **mocked** against `fixtures/oddsapi_historical_sample.json`; `fetch_historical` raises without `api_key` and is never called in tests. Betfair traded-volume/market depth is NOT in this feed (deferred, not fabricated). |

## FBref / Opta advanced data — termination note

FBref advanced data (xG) terminated 2026-01-20 — ToS/contract dispute per Stats
Perform's statement to The Athletic (FBref disputes it); NOT the WC exclusivity
deal. We use StatsBomb Open Data for xG.
