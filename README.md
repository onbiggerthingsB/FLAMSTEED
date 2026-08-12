# Flamsteed — point-in-time football forecasting

*Formerly `worldcup`, renamed 2026-08-10. Named for John Flamsteed, first
Astronomer Royal, who refused to publish figures he had not finished checking.
The first archive is the 2026 FIFA World Cup; old links redirect.*

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21641225.svg)](https://doi.org/10.5281/zenodo.21641225)
Forecast archive (24 point-in-time snapshots, CC BY 4.0): [doi:10.5281/zenodo.21641225](https://doi.org/10.5281/zenodo.21641225)

A quantitative forecasting system for the 2026 World Cup: a Bayesian scoreline
model fit on 49k+ international results, a 20,000-draw Monte-Carlo tournament
simulator over the real 48-team bracket, and a dashboard that refuses to show a
number without its uncertainty and provenance.

**The honest headline first:** this system is built to *forecast well*, not to
beat the market — and it does not beat the market. An early audited diagnostic
(`reports/headroom_2026-06-10.md`) found a statistical tie against sharp closing
odds; the later preregistered test put the market **ahead** of the model by
~0.010 mean RPS on 217 fixtures (`reports/oa_conclusion.md`). So every
edge-looking number it produces ships behind a NOT-REAL banner, and the mission brief
(`docs/missions/2026-06-accuracy-upgrade.md`) explicitly forbids confusing
"interesting disagreement with a market" with "validated edge".

## How it did — World Cup 2026 final record

The system ran live wire-to-wire: all 104 matches ingested point-in-time,
~40 daily production refits, zero leakage violations. Every number below is
reproducible from the committed per-match records (`reports/`).

**Tournament calls**
- **Champion correct: Spain** — the model's co-favorite throughout, and its
  50.7%/49.3% pick in the final itself. The final's regulation score (0-0) was
  the model's single most likely scoreline (13.9%); Spain won in extra time.
- **Both finalists correctly identified** — Spain and Argentina were its top
  two in title odds from the group stage onward.
- **All four semifinalists** were in its projected quarterfinal eight published
  before the Round of 32 had finished.

**Match outcomes**
- Knockout ties: the model's favorite won **26 of 32 (81%)**; QF+SF+Final
  combined **7 of 7**. (Counted by tie-winner — which team advanced. The full
  scorecard's stricter 1X2-modal scoring, where a shootout game counts as a
  draw, gives 25/32; both definitions stated to avoid metric ambiguity.) Of the six misses, four were penalty shootouts, one was
  the third-place exhibition, and exactly one was a true 90-minute upset
  (Norway over Brazil). Regulation-decided, full-stakes knockouts: **24/25**.
- Group stage: correct 1X2 outcome in **46 of 72 (63.9%)** against a
  three-way market (final-store point-in-time replay; 45/72 on the
  in-tournament store).

**Calibration (proper scoring, point-in-time, verified — full 104-game
scorecard: `reports/live_scorecard_final.md`)**
- Vs its naive-Elo baseline: ahead over the group stage as played live
  (RPS 0.157 vs 0.163 on the in-tournament store); over the full 104-game
  replay on the final consolidated store the two are **statistically tied**
  (0.1561 vs 0.1557). Reported both ways, because honest scoring is the
  point of the system.
- Favorites: predicted 69.7% win rate, realized 76.8% (56 favorite-band
  games) — calibrated, with the error on the humble side.
- Goal-margin tails within ~1.5pp of reality at every threshold
  (≥2: 42.8% pred / 43.3% real; ≥3: 21.5/21.2; ≥4: 10.2/8.7); draw rate
  predicted 23.4% vs realized 23.1%.
- Its upsets clustered in its least-confident calls: the model was rarely
  wrong where it claimed to be sure, and the games it called coin flips
  (the final: 50.7/49.3) genuinely were.

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
| Club-Elo squad anchor (`k_squad`) | NO-LIFT | pooled support 0.0% on 113 held-out tournament matches (`reports/p3sweep/sweep_20260611T012358Z.log`); re-evaluated post-group-stage on 185 and closed (`reports/p3sweep/addendum3_20260701T222121Z.md`) |
| Friendly tier down-weighting | NO-LIFT | flat RPS across the weight grid — `reports/tier_weights_2026-06-10.md` |
| Scoreline tails in mismatches | **OPEN FINDING** | model over-predicts blowout tails (top-decile ratios 0.73–0.87). No correction has been specified in the thinning direction; the one perturbation trialled was mis-signed and its verdict is withdrawn in the report's own controller's note — `reports/tails_2026-06-10.md` |
| Model vs sharp market | TIE | `reports/headroom_2026-06-10.md` |
| Odds-anchored blend (E′, w=0.95) | **NEGATIVE — market beats model, nothing adopted** | preregistered gate passed (mean ΔRPS −0.010, n=217), but the winning arm is 95% bookmaker and indistinguishable from pure market — so the finding is the market outforecasting the model, not the model improving. Retrospective, hence a development diagnostic; the confirmatory programme was **closed 2026-08-12 without a run** — the sealed venue offered 0.284 power against this effect and a defensible design needs ~400 fixtures across years (`reports/oa_confirmatory_design.md`; ruling sealed in the lock-v10 amendment). Hash-chained prereg `lock-v1..v6` (v7–v10 record product-code changes and the closure; none alters a result here); plain-language account with full correction history in `reports/oa_conclusion.md` |
| Model deficit concentrated where it disagrees with the market | **OPEN FINDING** | direction replicated out of sample (gap −0.025, p 0.024) but deliberately uncertified — the decision rule was corrected after a near-miss was visible; needs an independent sample under a rule fixed in advance — `reports/oa_disagreement_test.md` |

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
