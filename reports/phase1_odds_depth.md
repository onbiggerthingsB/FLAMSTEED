# UNVERIFIED until Odds API key provided (Phase-0 decision 1)

> **GATED STUB — NO PAID CALL HAS BEEN MADE.** This document records the *exact
> procedure* to verify The Odds API's actual international historical depth once
> a key exists. It has **NOT** been executed: The Odds API historical endpoint is
> **paid** (Phase 0 §3b, §3e item 1), and **no paid call is made here or by
> anything in Phase 1.** Everything below is a runbook for a human (or a future,
> explicitly-authorized task) to follow *after* a key + paid plan are in hand.

## Why this is gated, and what it gates

The backtest window (`backtest_window(matches, odds_start)` in
`src/wcmodel/data/windows.py`) is bounded **only** by `odds_start` — the date odds
coverage actually begins. That single date sets how far back the closing-line
backtest can run, so its value is load-bearing.

Phase 0 left `odds_start` **UNVERIFIED**:

- The Odds API's **headline** historical snapshot coverage starts **2020-06-06**
  (10-min snapshots; 5-min from 2022-09-01) — Phase 0 §3b.
- **BUT** that headline start does **not** necessarily apply to the bookmakers we
  actually benchmark on. The Odds API docs warn that *"bookmakers and sports will
  only be available in the historical odds API after the time that they were
  added to the regular odds API"* — so the usable closing-line history for the
  `pinnacle` / `betfair_ex_*` keys specifically **may begin materially later than
  2020-06-06** (Phase 0 §3e item 6, confirmed/sharpened in Phase 0 §4 Track D and
  §5a; source: the archived The Odds API v4 historical guide,
  `https://web.archive.org/web/20250101000000/https://the-odds-api.com/liveapi/guides/v4/`,
  accessed 2026-06-03).

Therefore: **`odds_start` MUST be set from the verified per-bookmaker depth
measured by the procedure below — it must NOT be assumed to equal the headline
2020-06-06, and it must NOT be hard-coded from any other guess.**

## Verification procedure (DO NOT EXECUTE WITHOUT A KEY + PAID PLAN)

> **DO NOT call the paid API** as part of building, testing, or reviewing Phase 1.
> Run the steps below only as a deliberate, separately-authorized verification
> task once a key + paid plan are confirmed (Phase 0 final-rec decision 1).

### Inputs required first

1. A funded The Odds API key on a plan that includes the **historical** endpoint
   (the historical endpoint is paid-only — Phase 0 §3b, §3e item 1).
2. The target competition sport keys (confirmed present in Phase 0 §3b), e.g.
   `soccer_fifa_world_cup` (match odds / `h2h`) and
   `soccer_fifa_world_cup_winner` (outrights). The same depth probe should be
   repeated **per sport key** of interest — depth can differ per competition.
3. The benchmark bookmaker keys to confirm: **`pinnacle`** and the Betfair
   Exchange keys (`betfair_ex_eu`, and `betfair_ex_uk` / `betfair_ex_au` if used;
   a single `regions=eu` query returns both Pinnacle and `betfair_ex_eu` per
   Phase 0 §3b).

### Endpoint

Use the historical odds snapshot endpoint:

```
GET /v4/historical/sports/{sport}/odds
    ?apiKey={key}
    &regions=eu
    &markets=h2h
    &date={ISO8601_timestamp}
```

(For per-event outright/depth checks, the sibling endpoint is
`GET /v4/historical/sports/{sport}/events/{eventId}/odds`.)

Each response is a **snapshot** wrapping the odds at `date`, plus
`previous_timestamp` / `next_timestamp` fields for walk-forward / walk-back
traversal of the snapshot series (Phase 0 §3b).

### Step-by-step

1. **Establish the headline floor.** Query with `date=2020-06-06T12:00:00Z`
   (the documented coverage start). Confirm a snapshot is returned at all for the
   sport key. This is the *earliest possible* start, not the per-bookmaker start.
2. **Find the earliest snapshot that actually contains each benchmark bookmaker.**
   This is the **per-bookmaker-add-date caveat (Phase 0 §3e item 6)** in action,
   and is the crux of the whole verification: a snapshot existing on a date does
   **not** mean `pinnacle` / `betfair_ex_*` are *in* that snapshot. Walk the
   snapshot series **forward from 2020-06-06** (following `next_timestamp`), and
   for each snapshot inspect `data[].bookmakers[].key`. Record, **per bookmaker
   key**, the **date of the earliest snapshot in which that key first appears**.
   That first-appearance date is that bookmaker's true historical start — it may
   be materially later than 2020-06-06.
   - Practically: a coarse outward scan (e.g. monthly probes) to bracket the
     first appearance, then a finer scan to pin the boundary, minimizes paid
     requests. Mind the plan's request-quota cap (Phase 0 §3e item 1) — each
     historical snapshot call consumes quota.
3. **Repeat per sport key** (e.g. `soccer_fifa_world_cup`,
   `soccer_fifa_world_cup_winner`). The verified depth is **per (sport key,
   bookmaker key)**; coverage need not begin on the same date for each.
4. **Note interval changes within the covered range.** Snapshot cadence is
   10-min from 2020-06-06 and 5-min from 2022-09-01 (Phase 0 §3b) — relevant to
   how precisely a closing line can be sampled, though not to the start date
   itself.

### Recording the result and wiring `odds_start`

- Record, in this file (replacing the UNVERIFIED banner once done), the measured
  **per-(sport key, bookmaker key) first-appearance dates**, with the snapshot
  timestamps as evidence.
- Set the backtest `odds_start` passed to
  `backtest_window(...)` from the **verified** depth — concretely, the **latest**
  of the first-appearance dates among the bookmaker keys the backtest actually
  relies on for that competition (so every relied-upon benchmark has coverage for
  the whole evaluated range). **Do not assume `2020-06-06`; do not hard-code a
  guess.**
- Consequence to keep in view (Phase 0 §5a): usable sharp-benchmark history is
  **≤ ~6 years and plausibly shorter** for `pinnacle` / `betfair_ex_*`
  specifically, and the minnow/qualifier tail within that window is shallower
  still. `backtest_window` deliberately keeps **all** odds-covered history
  (it is NOT cropped to `windows.feature_years`); this verification is what makes
  its lower bound honest.

## Until then

`odds_start` remains **UNVERIFIED**. `backtest_window` takes `odds_start` as an
explicit argument precisely so nothing in the codebase silently assumes a depth.
No Phase-1 code path calls the paid API.
