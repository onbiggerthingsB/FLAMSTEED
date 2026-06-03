# SOURCES

Per-source provenance, license, refresh cadence, access (free/key/scrape), the
`revision_contaminated` policy, and a `source_version` where pinned. Rows are
**appended per adapter task** (Tasks 4, 8, 9, 10, 13); Task 1 seeds the header,
the FBref/Opta note, and the first (results) row.

| Source | Feature | License | Access | Policy | source_version | Notes |
|---|---|---|---|---|---|---|
| `martj42/international_results` | match results | CC0 | free (git) | point_in_time | _pinned in Task 4_ | immutable results; `valid_as_of == observed_at == match date` |

## FBref / Opta advanced data — termination note

FBref advanced data (xG) terminated 2026-01-20 — ToS/contract dispute per Stats
Perform's statement to The Athletic (FBref disputes it); NOT the WC exclusivity
deal. We use StatsBomb Open Data for xG.
