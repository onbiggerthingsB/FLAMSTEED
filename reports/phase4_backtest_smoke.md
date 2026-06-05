# Phase 4 — Backtest Smoke Snapshot (SYNTHETIC — NOT AN EDGE CLAIM)

> **THIS IS PIPELINE SMOKE ON A CLEARLY-LABELLED-NON-REAL SYNTHETIC ODDS HARNESS.**
> No real odds were sourced or paid for (D1). Every number below comes from the
> `wcmodel.backtest.odds_ingest.synthetic_odds_sample` harness (`is_synthetic=True`)
> and is **NOT a CLV or ROI claim**. The real CLV/ROI number is impossible until
> real odds are sourced — a single gated switch (`fetch_historical`) behind a
> separate explicit funding approval. Mirrors the Phase-3 progression snapshot's
> non-real labelling.

## What this demonstrates (machinery only)

The walk-forward engine runs end-to-end on a synthetic event: refit the posterior
as-of the cutoff (memoised Elo), de-vig the close (Shin), compute
`edge = model_fair − devigged_market`, size a ¼-Kelly × uncertainty-shrunk stake
above the 2 pp trigger, settle against the actual result, and fold CLV + ROI +
RPS-vs-baselines — all tainted `is_synthetic=True`.

## Rendered run output (ALL SYNTHETIC — every number is non-real)

> One synthetic event (Brazil vs Croatia, made-up entry/close odds, settled to a
> made-up 2–0 Brazil result). Reproduced from the block below; `report.py` rendered
> the stratification, coverage-gap, and baseline verdict. **These are fabricated
> inputs — the values are pipeline-shape evidence, NOT a measurement of edge.**

- **`is_synthetic` (whole `Metrics`):** `True` — the entire result is non-real; no
  number here is ever an edge claim.
- **Bets placed:** `1` · **non-bets (filtered):** `{}` (the single event cleared the
  2 pp trigger on the synthetic prices).
- **CLV (SYNTHETIC):** `beat_close_rate = 0.0`, `avg_clv = −0.0286` — the bet was on
  `draw`, whose close (3.50) drifted LONGER than entry (3.40), so it lost CLV on the
  fabricated line. **A synthetic CLV, not a measured one.**
- **ROI / staking (SYNTHETIC):** `roi = −1.0`, `hit_rate = 0.0`, `turnover ≈ 0.0049`,
  `max_drawdown ≈ 0.0049`. `roi = −1.0` is the n=1 artifact of a single lost bet on a
  made-up result — **not** a performance figure.
- **RPS vs baselines (SYNTHETIC):** `mean_rps_model = 0.509`, `mean_rps_market =
  0.372`, `mean_rps_elo = 0.331`. On THIS fabricated single event the model RPS is
  worse than both baselines — the **baseline-beat verdict is `beats_both = false`**
  (honest: the machinery reports no edge rather than manufacturing one).
- **Stratified report (`report.render_stratum`, by `match_type`):** the single
  `wc_finals` stratum renders as an explicit **coverage GAP** —
  `"insufficient coverage (n=1)"` (n < `MIN_STRATUM_N` = 30). The thin stratum is
  NEVER averaged into a headline or reported as a number; that is the selection-bias
  discipline firing exactly as designed.
- **Per-bet ledger (SYNTHETIC):** `staked=draw`, `edge ≈ 0.031`, `stake ≈ 0.0049`,
  `pnl ≈ −0.0049`, `outcome=home`, `synthetic=True` on the record.
- **Foresight-RED:** NOT tripped (a `−1.0` ROI is nowhere near the `+10%` ceiling) —
  and a clean RED pass means nothing on its own anyway; the permutation null (Task 7)
  and the leakage canary (Task 6) are the real catches.

**No real-odds number exists in this document.** Every figure above is a fabricated
synthetic-harness artifact; the coverage-gap suppression and the `beats_both = false`
verdict are the machinery refusing to dress synthetic noise up as a result.

## How to regenerate (synthetic; no spend)

```python
import pandas as pd
from wcmodel.backtest.odds_ingest import synthetic_odds_sample
from wcmodel.backtest.walkforward import walkforward

s = synthetic_odds_sample(home="Brazil", away="Croatia",
                          commence="2024-06-30T19:00:00Z",
                          entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
                          bookmaker="pinnacle", seed=0)
rfs = pd.DataFrame([{ "home_team": "Brazil", "away_team": "Croatia",
                      "date": pd.Timestamp("2024-06-30"), "home_score": 2,
                      "away_score": 0, "tournament": "FIFA World Cup" }])
matches = pd.DataFrame({"date": pd.to_datetime(["2024-06-30"])})
m = walkforward(<small_store>, [s], results_for_settle=rfs, matches=matches,
                fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
assert m.is_synthetic is True       # the whole result is non-real
print(m.summary)                    # SMOKE ONLY — never an edge claim
```

(`<small_store>` is the leakage-safe test panel — `tests/data/conftest.py::small_store`;
the rendered numbers above came from this exact invocation. The synthetic inputs are
the same ones the walk-forward tests use, so this snapshot regenerates deterministically.)

## Gating posture (binding)

- Real pull: GATED (`fetch_historical` raises without a key) — needs separate
  funding approval (D1).
- This phase delivers VALIDATED MACHINERY + a gated one-switch pull, not a number.
- The backtest is a big-match, revision-contaminated UPPER BOUND; the Phase-5 live
  forward-test is the authoritative number for the minnow/progression edge.
