# Phase-2 calibration — in-sample smoke snapshot

> **READ THIS FIRST.** This is an **IN-SAMPLE smoke snapshot on a tiny synthetic
> test fixture** (`tests/data/conftest.py::small_store`) — **NOT a result, edge,
> or calibration claim.** It is a **pipeline smoke test**: it proves the
> fit → predict → score path runs end-to-end and returns sane shapes. The fixture
> is dominated by 4-0 blowouts (a synthetic "ladder" of strong teams thrashing one
> punching-bag), so the model-vs-Elo comparison **is not meaningful**. The only
> honest verdict of edge is the **Phase-4 out-of-sample walk-forward (RPS / CLV)**,
> which does not exist yet. Per the project rule, a too-good in-sample result is a
> **suspected overfit / leakage bug**, never a win.

## Setup

- **Fixture:** `small_store` (synthetic; ~14 teams, a 9-team "ladder" beating
  "Malta" 4-0 plus a handful of core matches).
- **Cutoff:** `2024-06-01` (so the panel = matches strictly before it = the
  matches the model was fit on → **in-sample**).
- **Model:** Dixon-Coles likelihood, ADVI backend (`draws=300`, `advi_iters=4000`,
  `seed=0`), independent hierarchical prior (no Elo in the model), mechanism-(c)
  predictive widening for provisional teams.
- **Reproduce:** fit at the cutoff on `small_store`, then
  `vs_elo_baseline(post, store, "2024-06-01")`, `post.diagnostics()`, and
  `posterior_predictive_checks(post, to_match_panel(features.build("2024-06-01", store)))`.

## In-sample RPS vs the Elo baseline (`vs_elo_baseline`)

| metric | value |
|---|---|
| `model_rps` (in-sample) | **0.058** |
| `elo_rps` (in-sample) | **0.041** |
| `n_matches` | 53 |
| `in_sample` | `True` |

**Not too-good:** the model RPS (0.058) is **slightly WORSE** than the naive Elo
baseline (0.041) on these fitted matches — so there is **no** too-good /
suspected-leakage signal to surface here. This is expected and **not meaningful**:
the fixture is ~89% home-wins / ~7.5% draws (the blowout ladder), a distribution
the path-dependent Elo recompute fits almost trivially on its own training data,
while the independent-prior scoreline model is shrunk toward more realistic
football rates. **It is a smoke test of the scoring path, not a calibration
comparison.**

## Posterior diagnostics (`Posterior.diagnostics`)

| metric | value |
|---|---|
| `max_rhat` | `NaN` |
| `min_ess_bulk` | 268 |

`max_rhat` is **`NaN` BY DESIGN for the ADVI backend** — ADVI draws are i.i.d.
samples from the mean-field variational approximation, returned as a **single
chain**, so the between-chains R-hat is undefined (`az.summary` returns NaN). This
is **not** a convergence failure: it is the expected artifact of using the fast
walk-forward backend. The finite, healthy `min_ess_bulk = 268` confirms the draws
are usable. **R-hat is only meaningful for the multi-chain NUTS fit** — the
periodic NUTS run (the explicit ADVI-falsely-tight check) is where convergence
diagnostics live; this snapshot uses ADVI deliberately.

## Posterior-predictive checks (`posterior_predictive_checks`, obs vs pred)

| metric | observed | predicted |
|---|---:|---:|
| draw-rate | 0.075 | 0.189 |
| home-win-rate | 0.887 | 0.705 |
| mean total goals | 3.66 | 3.25 |
| `n_matches` | 53 | — |

The gaps (model predicts more draws / fewer home wins than the fixture shows) are
**the fixture being unrealistic**, not a misspecification finding: the synthetic
ladder is ~89% home-wins, far above any real football distribution, so the
hierarchical-prior model correctly pulls toward more typical rates and **cannot —
and should not — reproduce the synthetic blowout aggregates**. The mean-total-goals
match (3.66 obs vs 3.25 pred) is the closest, as expected. **No conclusion about
real calibration can be drawn from this fixture** — that is Phase 4's job on real,
out-of-sample data.

## Bottom line

The Phase-2 calibration harness (`vs_elo_baseline`, `posterior_predictive_checks`,
`Posterior.diagnostics`) **runs end-to-end and returns sane, well-typed outputs**.
Numbers here are a **synthetic-fixture pipeline smoke test only**. The real
out-of-sample evaluation — and the only honest verdict of edge — is **Phase 4**.
