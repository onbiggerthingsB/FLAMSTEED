# worldcup — a forecast-first model of the 2026 FIFA World Cup

A quantitative forecasting system for the 2026 World Cup: a Bayesian scoreline
model fit on 49k+ international results, a 20,000-draw Monte-Carlo tournament
simulator over the real 48-team bracket, and a dashboard that refuses to show a
number without its uncertainty and provenance.

**The honest headline first:** this system is built to *forecast well*, not to
beat the market. Its own audited diagnostic (`reports/headroom_2026-06-10.md`)
found a statistical tie against sharp closing odds — so every edge-looking
number it produces ships behind a NOT-REAL banner, and the mission brief
(`docs/missions/2026-06-accuracy-upgrade.md`) explicitly forbids confusing
"interesting disagreement with a market" with "validated edge".

## How it works

```
martj42 results (pinned commit)        config/tournament_2026.yaml (verified draw)
        │                                              │
  BitemporalStore  ──read(cutoff)──►  features.build(cutoff)   [strict date < cutoff_day]
        │                                              │
  manual-results CSV fallback            PyMC scoreline model (Dixon-Coles family,
  (matchday ingest, PIT-safe)            ADVI, Elo-anchored priors, host_k=1.4)
                                                       │
                                         content-addressed posterior cache
                                                       │
                                    20k-sim tournament MC (groups → third-place
                                    ranking → R32 → final, FIFA tiebreakers)
                                                       │
                                      dashboard bundle (JSON, provenance-enveloped,
                                      gated: no naked numbers, leakage canaries)
                                                       │
                                          dashboard-ui (Svelte + Vite)
```

Everything downstream of a cutoff is a point-in-time read: a result is visible
only if it was *knowable* at that instant (`observed_at <= cutoff` and
`valid_as_of <= cutoff`), and every phase ships with leakage canaries that
include positive controls — a canary that cannot fail is treated as a bug.

## Operating it

```bash
# install (editable; never `uv run` scripts — it breaks the editable install)
uv pip install -e .

# the daily loop: ingest → leakage gate → fit (cached) → 20k sims → stage → provenance
PYTHONPATH=src .venv/bin/python scripts/daily_update.py --latest

# matchday fallback: hand-enter finished fixtures when upstream lags (median ~31h)
PYTHONPATH=src .venv/bin/python scripts/daily_update.py --latest --manual-results day1.csv

# the dashboard
cd dashboard-ui && npm install && npm run dev

# tests
PYTHONPATH=src .venv/bin/python -m pytest
```

The operator guide to every UI element is `docs/dashboard-guide.md` (including
the 60-second daily freshness check and known limitations).

The Odds-API key (value scanner only — never the model) goes in a local `.env`;
see `.env.example`. The forecast pipeline spends zero API credits.

## Discipline

- **Pre-registration.** Sweeps and adoption gates are committed as protocol
  documents *before any number exists* (`docs/superpowers/specs/`). Thresholds
  never get tuned against the metric they gate.
- **"Tested, no lift" is a recorded outcome.** Most things tried did not help,
  and the reports say so.
- **Too good = suspected bug.** Surprising wins are audited before they are
  believed; several were bugs.
- **Config-gated changes, byte-identical off.** Every model addition proves the
  off-state is bit-identical to the prior behavior before it ships.
- **No naked numbers.** Every probability renders with its Monte-Carlo SE, a
  derivation marker, or an explicit coverage gap — enforced by a render-guard
  test suite.

## Decision log (empirical record)

| Item | Verdict | Evidence |
|---|---|---|
| Elo-anchored strength prior (k=0.6) | **ADOPTED** | held-out RPS, n=2,111 |
| Host advantage `host_k=1.4` | **ADOPTED** | MLE on n=873 finals-tier host games, 95% CI [1.18, 1.64] |
| Altitude covariate | NO-LIFT | `reports/altitude_2026-06-10.md` |
| Club-Elo squad anchor (`k_squad`) | NO-LIFT | pooled support 0.0% on 113 held-out tournament matches |
| Friendly tier down-weighting | NO-LIFT | flat RPS across the weight grid |
| Scoreline tails in mismatches | **OPEN FINDING** | model over-predicts blowout tails (top-decile ratios 0.73–0.87); correction spec'd, not shipped — `reports/tails_2026-06-10.md` |
| Model vs sharp market | TIE | `reports/headroom_2026-06-10.md` |

## Layout

```
src/wcmodel/        the library: data/ (bitemporal store, sources, features),
                    model/ (scoreline model, inference, posterior cache),
                    sim/ (tournament MC), dashboard/ (bundle builder + gates),
                    backtest/, live/, value/ (scanner — separate, never feeds the model)
scripts/            operational entry points (daily_update, sweeps, diagnostics)
config/             config.yaml, the verified 2026 draw, squad/club-Elo snapshots
dashboard-ui/       Svelte viewer (serves the staged bundle from public/bundle)
docs/               mission brief, specs/pre-registrations, operator guides
reports/            every diagnostic and sweep, including the no-lifts
tests/              ~900 tests incl. leakage canaries with positive controls
```

`data/` and `logs/` are local artifacts (gitignored): the results cache, the
content-addressed posterior/sim caches, and the built dashboard bundles.
