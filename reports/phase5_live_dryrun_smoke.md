# Phase 5 — Live Forward-Test Dry-Run Smoke (DRY-RUN — NOT AN EDGE CLAIM)

> **THIS IS PIPELINE SMOKE ON A CLEARLY-LABELLED-NON-REAL SYNTHETIC/FIXTURE HARNESS.**
> No real odds were sourced or paid for, and NO bet was placed (L1/L2). Every number
> below comes from the `backtest.odds_ingest.synthetic_odds_sample` harness
> (`is_synthetic=True`) and is **NOT a CLV or ROI claim**. The real CLV/ROI number is
> impossible until the feed is funded — a single gated switch (`live.dry_run=false` +
> an `--api-key`) behind a separate explicit funding approval. Mirrors the Phase-4
> synthetic snapshot's non-real labelling.

## What this demonstrates (machinery only)

The live loop runs end-to-end on a synthetic event at `cutoff = now`: fetch (dry-run,
no network) → ingest the actual played result POINT_IN_TIME → decide (the Phase-4
per-cutoff body at `cutoff = now`: `read(now)` → `cached_fit` → `model_fair_1x2` →
de-vig the ENTRY → `edge` → ¼-Kelly×uncertainty stake SIGNAL) → scan (edge×liquidity
→ `Ranked`) → log the entry IMMUTABLY at decision time → fold the close → realized CLV
(`entry/close − 1`) — all tainted `is_synthetic=True`, all SIGNAL-ONLY/PAPER.

## The focal operational-leakage gate (the live analog of the close-line leak)

The logged entry is the price available AT the decision cutoff (the EARLIEST snapshot
≤ kickoff), NEVER the close. The live mis-log canary
(`live.validation.assert_entry_logged_at_decision_time`) RAISES if the close were
logged as the entry. The bet log is append-only/immutable (a re-log raises). A too-good
live CLV trips foresight-RED → STOP, not celebrate.

## How to regenerate (synthetic; no spend, no bet)

```python
import pandas as pd
from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.live.decide import decide_live
from wcmodel.live.scan import scan, render_scan_report

s = synthetic_odds_sample(home="Brazil", away="Croatia",
                          commence="2024-06-30T19:00:00Z",
                          entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
                          bookmaker="pinnacle", seed=0)
d = decide_live(<small_store>, s["sample"], cutoff="2024-06-30T19:00:00Z",
                fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
assert d.is_synthetic is True and d.signal_only is True   # non-real, never a real bet
ranked = scan(<small_store>, [{"sample": s["sample"], "liquidity": 50.0}],
              cutoff="2024-06-30T19:00:00Z",
              fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
print(render_scan_report(ranked))                         # SMOKE ONLY — never an edge claim
```

## Gating posture (binding)

- Real feed: GATED (`fetch_live_odds` raises without a key; `live.dry_run=true`) —
  needs separate funding approval (L1). LIVE runs without `--api-key` are refused.
- SIGNAL-ONLY / PAPER: no order/broker/exchange path; no real bet (L2).
- This phase delivers VALIDATED LIVE MACHINERY + a gated one-switch feed, not a number.
- The live forward-test is the AUTHORITATIVE, point-in-time-correct number (L5) — the
  backtest stays the big-match revision-contaminated upper bound.
