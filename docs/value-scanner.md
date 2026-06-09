# +EV Value Scanner (World Cup 2026)

An **on-demand, signal-only** scanner that finds where a **soft book** is offering a
better price than the **sharp (Pinnacle) consensus** on World Cup 2026 matches — so you
can place genuine positive-CLV ("+EV value") bets **manually**. It is the dashboard's
primary surface. The model forecast is kept only as a clearly-labeled secondary tab.

> **NOT REAL / SIGNAL-ONLY.** This system emits *signals* and a *paper* ledger. It never
> places, sizes, or stages a bet — there is no bet / broker / order path anywhere. You
> execute every bet yourself. The suggested ¼-Kelly stake is a *suggestion*, never an
> instruction, and is never auto-acted.

## What it is

A **pure, market-vs-market** scanner — **no model is in the edge path**. Per event ×
market (`h2h`, `totals`) × outcome:

1. **Sharp fair price.** De-vig Pinnacle's full market with **Shin** (`data.devig.shin`)
   → `fair_prob` for each outcome. Pinnacle is the truth reference.
2. **Edge per soft book.** `edge = fair_prob × soft_decimal_odds − 1`. Positive ⇒ +EV at
   that moment.
3. **Suggested stake.** ¼-Kelly on the edge (config `kelly_fraction`), surfaced as a
   *suggestion* with a hard caveat.

Six **guards** reject fake edges (every one fired on real WC data in the PoC):

| Guard | Rule |
|---|---|
| **Sharp-absent** | No Pinnacle line for the event/market → **coverage gap**, never an edge. |
| **Too-good** | `edge > too_good` (0.10) → SUSPECTED ARTIFACT, excluded from bettable. |
| **Both-sides** | One book +EV on *every* side of a market → stale de-vig, excluded. |
| **Book-tier** | Only **soft (bettable)** books are actionable; other-sharp/exchange prices are tagged, not bettable. |
| **Freshness** | Quotes older than `stale_seconds` (900s) are flagged stale, excluded. |
| **Longshot** | Edges on odds `> longshot_odds` (8.0) tagged fragile, excluded. |

A spot is **bettable** only if it passes *all* guards. Every other spot is still
serialized but tagged (`too_good` / `fragile` / `non_soft` / `both_sides` / `stale` /
`below_min`) so the viewer can show **"what we filtered and why"**. Events with no sharp
line become **coverage gaps** — never fabricated into an edge.

## Honest caveats (read these — see spec §1, §12)

The project's market-prior-free scoreline model has **no betting edge** — it ties but
does not beat the sharp 1X2 line. The only real retail +EV mechanism is market-vs-market.
This scanner productizes *that* mechanism, with its limits stated up front:

- **Thin by design.** The World Cup is the most efficiently-priced market on earth, so the
  value surface is **sparse** — softest *now* (weeks pre-kickoff, loose early lines) and
  tightening toward each game. Expect *few* bettable spots, fewer as kickoff nears.
- **Small, fragile edges.** Real edges are **2–5%**, move in **minutes**, and concentrate
  at **small, low-limit soft books** that limit/ban winners fast.
- **Soft-book identity drift.** Odds-API book keys vary by region; the `soft_books` set
  must be maintained. An unknown book is treated as `non_soft` (shown, not bettable) —
  never silently bet.
- **Execution is yours.** The tool only signals; capturing the edge needs your accounts +
  fast manual action, and winners get limited. No code change fixes that.
- **Pinnacle availability.** If The Odds API drops Pinnacle for the WC, the sharp reference
  degrades; `sharp_book` is configurable and the scanner *gaps* (never fabricates) when the
  sharp is absent.

### CLV is the metric — not single-bet profit

**Realized closing-line value (CLV) is the success metric**, not single-bet profit (too
noisy). Positive average CLV ⇒ the edges are real; flat/negative ⇒ they weren't, and you
lost nothing finding out (it is **paper-tracked**). The viewer's **Track Record** surface
is the honest scoreboard: beat-close-rate + avg CLV% over your logged bets.

## How to run a scan

A scan makes **one live Odds-API call per market** (`h2h`, then `totals`) × the configured
regions ≈ ~6 credits, **hard-capped** by `value.max_calls_per_scan`. The API key is read
from `.env` and **never printed**.

```bash
# From the repo root. Use the venv python directly with PYTHONPATH=src —
# NOT `uv run` (it re-syncs and breaks the editable wcmodel install).
PYTHONPATH=src .venv/bin/python scripts/scan_value.py
```

This fetches the live board, runs the pure scan → bundle pipeline, and writes:

- a provenance-stamped, **SIGNAL-ONLY / NON-REAL** value bundle JSON to
  `data/dashboard/value/<scan_ts>.json` (the viewer reads the newest one);
- the bettable spots appended to the **paper ledger** `reports/value_paper_ledger.jsonl`
  (gitignored, append-only).

Point the viewer at the result: `dashboard-ui`'s `copy-bundle.mjs` picks up the newest
`data/dashboard/value/*.json` (else the committed fixture) into `public/bundle/value.json`,
which the **Value Bets** surface renders.

### Settle (realized CLV)

Near kickoff, a settle pass pulls the closing (Pinnacle) line and records realized CLV
via `wcmodel.live.clv_tracker.PaperClvTracker` (`settle_one`). Track Record accumulates it.

## The signal-only invariant

Signal-only is a **hard, asserted invariant**: there is **no bet / broker / order path
anywhere** in `src/wcmodel/value/`. The scanner emits signals + a paper ledger only; you
place every bet manually. This is enforced by a test —
`tests/value/test_bundle.py::test_no_bet_or_broker_path_exists` — which greps the `value`
package source for any execution token (`place_bet`, `broker`, `order`, `stake_real`,
`execute_bet`) and fails if one appears. Every value bundle is stamped `signal_only: true`
/ `is_synthetic: true` with a NOT-REAL banner; the viewer asserts the banner on load and
renders no bet/stake/order control.
