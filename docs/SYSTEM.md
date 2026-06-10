# WC-2026 Quant System — Complete System Document

> **Purpose of this file:** a single, self-contained briefing on everything in this repository —
> the data pipeline, the Bayesian model, the tournament simulator, the backtest/validation harness,
> the live odds layer, the +EV value-betting scanner, and the Svelte dashboard UI — including the
> honest empirical findings, the binding engineering rules, and how to run it all. It is written so
> that an AI assistant (e.g. Claude on claude.ai) with **no repository access** can fully understand
> the system, reason about it, and help extend it. Last updated: **2026-06-10** (main @ `fa78838`).

---

## 1. What this is (TL;DR)

A **quantitative forecasting and betting-analysis system for the 2026 FIFA World Cup** (48 teams,
104 matches, USA/Mexico/Canada hosts, kicks off June 11 2026), built in Python 3.12 with a Svelte
web dashboard. It has two distinct products that share one pipeline:

1. **A Value Bets scanner (the money tool).** Pure *market-vs-market*: it de-vigs the sharp
   bookmaker (Pinnacle) to get "fair" probabilities, then flags any soft bookmaker offering a
   better price than fair (`edge = fair_prob × soft_odds − 1`). This is the only legitimate
   retail +EV mechanism. **No model is in this edge path.** Signal-only — it never places bets.
2. **A statistical forecast (the prediction tool).** A Bayesian Dixon-Coles scoreline model whose
   team strengths are anchored to point-in-time Elo ratings, feeding a 20,000-iteration Monte-Carlo
   tournament simulator → per-match win/draw/loss, scoreline grids, and champion/advance
   probabilities. Clearly labeled in the UI as *"independent forecast — does NOT beat the market."*

The separation is deliberate and is the system's most important design decision (see §2).

**Stack:** Python 3.12 + `uv`, PyMC (ADVI variational inference), pandas/numpy, DuckDB/Parquet
bitemporal store, The Odds API (live + historical odds), Svelte 4 + Vite + TypeScript dashboard,
pytest (~630 tests) + vitest (107) + Playwright e2e. Local-only (no deploy); odds API key lives in
a gitignored `.env` as `THE_ODDS_API_KEY` (never committed, never printed; ~19,000 paid credits
remaining on the plan).

---

## 2. The honest headline conclusions (read this first)

These were established empirically during development, with leakage-guarded tests. They are the
context for every design decision:

1. **The model does NOT beat the betting market.** On 1X2 (win/draw/win), the model *ties* the
   sharp closing line (Pinnacle) but does not beat it (CLV validation on real historical odds).
   On totals (over/under goals), the model's apparent "edges" (up to +38%!) were proven to be the
   **model's own miscalibration**, confirmed by direct comparison against Pinnacle itself: the
   model disagreed with the sharp line exactly as much as with soft books (mean |gap| 0.077 vs
   sharp ≈ 0.075 vs consensus; model-vs-market correlation only 0.52). The model is the outlier,
   not the market. **Conclusion: the efficient-market null holds — a public-data model has no
   betting edge. Never bet model-vs-market disagreements; they are −EV.**
2. **The only real retail +EV is market-vs-market** ("value betting"): a slow soft book lagging
   the sharp consensus. A live proof-of-concept found real but *small* edges (2–9%), concentrated
   in not-yet-sharp early lines and small low-limit books. Every >10% "edge" found in real data
   was an artifact (stale/suspended/mismatched line) — the too-good guard caught all of them.
3. **Realized CLV (closing-line value) is the success metric**, not single-bet profit. If the
   closing line moves toward your bet, the edge was real. The system paper-tracks this.
4. **Honest expectations:** the WC is the most efficiently priced market on earth, so the value
   surface is thin; soft books limit/ban winners; edges decay in minutes. This is a grind tool,
   not a money printer. The user places all bets manually — the system is signal-only by hard,
   test-enforced invariant.
5. **The model's role after the no-edge finding:** a credible *forecast* (the Forecast tab) and a
   *display-only second opinion* next to each value bet (a ⚠ when the model rates a pick below
   the market is the useful caution signal; "agrees" is weak evidence because the model
   historically over-rated underdogs).

---

## 3. Repository layout

```
worldcup/
├── config/
│   ├── config.yaml              # ALL knobs (see §13). Single source of truth.
│   ├── tournament_2026.yaml     # verified 104-match bracket: 12 groups, 16 venues, KO tree
│   └── lockbox.json             # single-use lockbox registry (backtest discipline)
├── src/wcmodel/                 # the Python package (editable install)
│   ├── config.py                # load_config()
│   ├── data/                    # PHASE 1 — data spine
│   │   ├── store.py             # BitemporalStore (valid_as_of / observed_at, read(cutoff))
│   │   ├── elo.py               # compute_elo_history (point-in-time rating_pre)
│   │   ├── features.py          # features.build(cutoff) — the leakage-safe panel + build_cached
│   │   ├── devig.py             # shin / power / proportional de-vig
│   │   ├── tiers.py             # match-type taxonomy (wc_finals … friendly)
│   │   ├── tournament.py        # bracket loader + validate_tournament + host_home_factor
│   │   ├── cache.py             # content-addressed cache primitives (content_key, _git_commit)
│   │   └── sources/             # adapters: results (martj42), odds (The Odds API parse),
│   │                            #   statsbomb (xG, coverage-gated), climate
│   ├── model/                   # PHASE 2 — the scoreline model
│   │   ├── panel.py             # to_match_panel + build_design → DesignData (incl. elo_z)
│   │   ├── strength.py          # team_elo_z(feats, teams) — the Elo strength anchor input
│   │   ├── scoreline.py         # PyMC models (DC + bivariate Poisson), _priors, _rates, fit()
│   │   ├── posterior.py         # Posterior: predict_scoreline / predict_1x2, widening, fail-safes
│   │   ├── widening.py          # mechanism-(c) mean-preserving predictive-variance inflation
│   │   ├── covariates.py        # CovariateTransform (standardize, persist, leakage-safe)
│   │   ├── volatility_diagnostic.py  # count_volatility_arm (provisional-team detection)
│   │   └── cache.py             # cached_fit: content-addressed posterior cache (netCDF + meta)
│   ├── sim/                     # PHASE 3 — tournament Monte-Carlo
│   │   ├── scoreline.py         # RateBook (per-draw rates; mirrors predict_scoreline exactly)
│   │   ├── groups.py / thirds.py / knockout.py / bracket.py / tournament.py / run.py
│   │   │                        # FIFA tiebreakers, third-place best-8 → R32, KO resolution
│   │   │                        #   (ET ~1/3 rate, pens 50/50), bracket tree, 20k-sim loop
│   │   └── cache.py             # content-addressed sim cache
│   ├── backtest/                # PHASE 4 — validation harness
│   │   ├── walkforward.py       # walk-forward engine, per-matchday refits
│   │   ├── clv.py               # clv_pct, beat_close, clv_summary
│   │   ├── baselines.py         # elo_baseline_1x2, model_fair_1x2, market_fair_1x2, rps
│   │   ├── staking.py           # ¼-Kelly × uncertainty shrink, commissions, settle_bet
│   │   ├── devig_select.py      # empirical de-vig selection (Shin won)
│   │   ├── validation.py        # assert_leakage_invariant + foresight-RED hard-STOP
│   │   └── lockbox.py           # single-use lockbox (final 18% of history, frozen)
│   ├── live/                    # PHASE 5 — live odds layer
│   │   ├── odds_live.py         # fetch_live_odds (audited route), CallBudget (hard caps)
│   │   ├── decide.py / scan.py  # live decision + ranked scan at cutoff=now
│   │   ├── ingest_live.py       # POINT_IN_TIME result ingest
│   │   ├── clv_tracker.py       # PaperClvTracker — append-only realized-CLV paper ledger
│   │   └── cli.py / tournament.py / validation.py   # thin CLI + live tournament + guards
│   ├── value/                   # THE +EV VALUE SCANNER (the money tool; NO model imports)
│   │   ├── types.py             # ValueBet + ValueConfig dataclasses
│   │   ├── scanner.py           # de-vig sharp → fair; edge; SIX guards; scan()
│   │   └── bundle.py            # build_value_bundle + gate_value (SIGNAL-ONLY/NON-REAL stamp)
│   ├── markets/                 # totals engine (kept; superseded as edge source — see §10.4)
│   │   ├── derived.py           # totals_probs(grid) — O/U from the scoreline grid
│   │   └── totals_edge.py       # totals_edges (model-vs-book; PROVEN -EV, not used for picks)
│   └── dashboard/               # dashboard DATA layer (Python → JSON bundles)
│       ├── provenance.py        # Provenance envelope {as_of, posterior_key, git, is_synthetic…}
│       ├── schema.py            # gates: no naked numbers, coverage_gap, no_impute, coherence
│       ├── build.py             # build_snapshot(cutoff) → gated, stamped JSON bundle
│       ├── fixtures.py / tournament_view.py / track.py / why.py / edges.py
│       └── cli.py
├── dashboard-ui/                # THE FRONTEND (Svelte 4 + Vite + TS) — see §11
│   ├── src/App.svelte           # shell + nav (Value Bets | Track Record | Forecast)
│   ├── src/lib/                 # router, types, bundle loaders, format (uncertainty grammar),
│   │   └── modelSecondOpinion.ts  # joins value bets ↔ model 1X2 (display-only)
│   ├── src/surfaces/            # ValueBets, Schedule, MatchDetail, Tournament, Track
│   ├── src/components/          # HonestyBar, WinBar, EdgeChip, Estimate, CoverageGap, ModelCell…
│   ├── scripts/copy-bundle.mjs  # stages newest data bundles → public/bundle/
│   └── tests/                   # vitest (107) + Playwright e2e (no-bet-affordance guard)
├── scripts/                     # operational entrypoints (see §14)
├── tests/                       # pytest: ~630 tests incl. 44 leakage canaries, 24 value tests
├── docs/                        # this file, value-scanner.md, architecture/retrospective docs
│   └── superpowers/{specs,plans}/   # every feature's design spec + TDD implementation plan
│                                # (ASSUMPTIONS.md / SOURCES.md live at the repo root)
├── data/                        # GITIGNORED: raw pulls, caches, dashboard bundles
└── reports/                     # committed reports; PAPER LEDGERS gitignored
```

---

## 4. The data spine (Phase 1)

**Bitemporal store** (`data/store.py`): every row carries `valid_as_of` (when the fact became
true) and `observed_at` (when we learned it). `store.read(table, cutoff)` returns only rows
knowable at the cutoff. This is the leakage firewall: *every* fit, feature, and snapshot reads
through it. Deterministic tie-breaks make reads reproducible.

**Results:** the martj42 international-results dataset — **49,296 played internationals** (full
history through 2026-06-02 at the production cutoff), normalized, with penalty-shootout winners
joined on. Score sanity gates (finite, non-negative, integral) before anything consumes them.

**Computed Elo** (`data/elo.py`): our own Elo over the full history (initial 1500, K=40 scaled by
match importance — WC finals 1.0 down to friendlies 0.4 — goal-difference multiplier, +100 home
advantage, neutral-venue aware). The leakage-safe feature is `rating_pre` (the rating *before*
each match). Deterministic ordering by `(date, match_id)`. Also defines **provisional** teams:
fewer than 5 matches OR recent rating volatility above an empirically derived threshold (16.5
rating points = the p95 of windowed rating-delta std across all teams/history).

**Features** (`features.build(cutoff)`): the per-team-per-match panel strictly before the cutoff
day — `elo_pre`, opponent, venue/neutral flags, provisional flags, time-decay weights
(365-day half-life over a 4-year window), match-type tiers, optional covariates (rest days,
travel km, altitude; currently disabled — see §5.6), xG where StatsBomb covers it (coverage-gated,
NULL-safe, **never imputed**). `build_cached` content-addresses the panel (cutoff + config +
git in the key — a key omission here once caused a real stale-serve bug, since fixed and canaried).

**WC-2026 bracket** (`config/tournament_2026.yaml`): programmatically built from openfootball,
validated — 12 groups × 4, 104 matches, 16 venues with countries, the full knockout tree
including the two-path R32 bracket and third-place best-8 qualification. Host home games
(USA/Mexico/Canada in-country) get `host_k = 1.4` × home advantage — empirically calibrated
(P2b 2026-06-10: k_elo=1.422, 95% CI [1.18, 1.64] over 873 finals-tier host games; the old 0.5
assumption was outside the CI); everything else is neutral.

---

## 5. The scoreline model (Phase 2)

### 5.1 Core math (Dixon-Coles)

For match *i* between home team *h* and away team *a*:

```
log λ_home = μ + home_term + att[h] − def[a] + covariate_offsets
log λ_away = μ + away_term + att[a] − def[h] + covariate_offsets
goals ~ DixonColes(λ_home, λ_away, ρ)        # ρ = low-score dependence, |ρ| ≤ 0.15
```

- `home_term/away_term`: ordinary home game → `(home_adv, 0)`; **neutral → (k_n·home_adv,
  k_n·home_adv)** with `k_n = 0.5` (see §5.4); host home game → `(host_k·home_adv, 0)`.
- Likelihood weighted by time-decay; fit by **ADVI, 30,000 iterations** (production), seeded.
- Soft sum-to-zero centering on att/def. A bivariate-Poisson alternative exists behind the same
  interface (config `model.likelihood`).

### 5.2 The Elo strength anchor (the big model upgrade — shipped 2026-06-09)

**The diagnosed problem:** with vanilla hierarchical priors (`att, def ~ Normal(0, σ)`),
international data is too sparse (~10 games/team/year) and the posterior shrinks *every* team
toward the global mean. Measured: att spread sd ≈ 0.13 across 336 teams; Germany's net strength
≈ Curaçao's; **Germany was given only 39% to beat Curaçao** (truth ≈ 85%+) and the model leaned
*Morocco over Brazil*. Champion odds were near-uniform (Norway #1 at 4.3%, France #27). Widening
was ruled out as the cause (identical predictions with it on/off); the *fit itself* was compressed.

**The fix:** anchor each team's prior **mean** to its point-in-time Elo:

```
elo_z[team] = z-scored latest rating_pre strictly BEFORE the cutoff   (debutants → 0)
att[team] ~ Normal(k_att · elo_z[team], σ_att)      # k_att = 0.6
def[team] ~ Normal(k_def · elo_z[team], σ_def)      # k_def = 0.6  (strong team: high att AND def)
```

- Leakage-safe (Elo is computed from *results* only, strictly `< cutoff` — preserves the
  project's "market-prior-free" principle: betting odds NEVER feed the model).
- Config-gated (`model.strength_prior`, byte-identical to the old model when off).
- **k calibrated by held-out 1X2 RPS** (cutoff 2024-06-01, scored on 2,111 internationals played
  after it; lower = better):

  | k | model RPS | Elo-baseline RPS |
  |---|---|---|
  | 0.0 (old model) | 0.35922 | 0.34045 |
  | 0.4 | 0.33653 | 0.34045 |
  | **0.6 (shipped)** | **0.33277** | 0.34045 |
  | 0.8 | 0.33290 | 0.34045 |
  | 1.0 | 0.33267 | 0.34045 |

  Note the old model was *worse than plain Elo*; the anchored model beats both. k=0.6 is the knee
  of the plateau (full gain, least anchoring). Reproduce with `scripts/sweep_strength_k.py`.
- **Validated production effect** (cutoff 2026-06-07): Germany v Curaçao 39% → **88.4%**; Spain v
  Cape Verde 91.4%; Brazil 48% > Morocco 23% (correct order, appropriately cautious); Argentina v
  Curaçao 94.7%. None faked (gate was 75–92%; >95% would have been flagged as over-anchoring).

### 5.3 Predict-time machinery (`posterior.py`)

`predict_scoreline(home, away, neutral, host_factor, covariates) → grid[h,a]` (a normalized
scoreline probability grid, posterior draws integrated). `predict_1x2` folds the grid's
triangles. Fail-safes reject degenerate/NaN grids (a diverged coarse fit once produced these).
**Mechanism-(c) widening:** for *provisional* teams only, predictive variance is inflated
(exactly mean-preserving, max-entropy construction) — uncertainty honesty for low-information
teams. The simulator's `RateBook.rates` applies the *identical* rate logic (canonical invariant:
**sim must mirror predict** — tested).

### 5.4 The neutral-venue calibration fix (shipped 2026-06-08)

Diagnosed on 1,922 held-out internationals: non-neutral games were calibrated (+0.03 goals) but
**neutral games under-predicted total goals by −0.34/game** — because `neutral=True` zeroed
home advantage on both sides, scoring the game at the *away* rate. Every WC group game is
neutral, so the whole forecast under-scored (this manufactured a wall of fake "UNDER" totals
edges). Fix: a neutral game uses the *average environment* — both sides get `+0.5·home_adv`
(`model.neutral_home_adv_fraction`, empirical best-fit 0.53 ≈ principled 0.5). Result: neutral
gap −0.341 → **+0.019**; non-neutral path bit-identical; 1X2 unchanged (symmetric boost).

### 5.5 Posterior cache

`cached_fit` content-addresses each fit: key = cutoff + full `model` config block + `elo` +
`windows` blocks + feature hash + git commit → `posterior-<key>.nc` + meta JSON. Any config or
data change is a cache miss, never a stale serve.

### 5.6 Covariates: tested, no lift

A full covariate pipeline exists (standardized, persisted transforms, missing-indicators,
leakage-canaried). The `rest_days` ablation showed **no held-out improvement** → `covariates.
enabled: []`. "Tested, no lift" is a recorded, valid outcome in this project.

---

## 6. The tournament simulator (Phase 3)

20,000 seeded Monte-Carlo tournament replays: per-draw scoreline sampling from the posterior →
group standings with **full FIFA tiebreakers** → third-place ranking and the best-8 → R32
assignment (the genuinely tricky 48-team-format logic) → knockout resolution (extra time at
~1/3 goal rate, penalties 50/50) → aggregated markets per team: `win_group, advance_from_group,
reach_r16/qf/sf/final, champion, first/second/third, out` — each with a Monte-Carlo standard
error. Conditioning: already-played results (read at the cutoff) are fixed, the rest simulated.
Content-addressed sim cache (posterior values + bracket + played-results + seed in the key).

---

## 7. The backtest & validation harness (Phase 4)

- **Walk-forward engine:** sweeps decision cutoffs forward; refits per matchday; the posterior
  cache key is `< cutoff`-only, and leakage tests force *fresh* fits so a cached posterior can
  never mask a fit-level leak (this exact masking was found by adversarial review and fixed).
- **CLV (the north star):** `clv_pct = entry_odds/close_odds − 1`, beat-close rate, vs the
  Pinnacle close. **De-vig method: Shin** (chosen empirically by RPS over power/proportional).
- **Staking:** ¼-Kelly × posterior-uncertainty shrink; venue commissions; drawdown; bootstrap CIs.
- **Foresight-RED tripwires (enforced as tests):** simulated ROI > +10%, beat-close > 58%, or
  avg CLV > +2% ⇒ **SUSPECTED LEAK — hard STOP**, never a celebration.
- **Lockbox:** final 18% of odds-covered history frozen, single-use, judged against 9
  pre-registered DOF. **Permutation null:** label-shuffles must place the real score ~99th pct.
- **44 leakage canaries** across every phase, each with a *positive control* (an injected leak
  that MUST trip the canary — proving non-vacuity). Example: a post-cutoff result must change
  nothing; the same result ingested pre-cutoff must change the fit (and does).

**Key result from this harness:** the model **ties but does not beat** the sharp 1X2 close, and
sharpening levers (σ priors, widening strength) were *inert* — the under-confidence was
structural (fixed later by the strength anchor, which improves the *forecast* but, as expected,
still does not beat the market).

---

## 8. The live odds layer (Phase 5)

The Odds API integration (`live/odds_live.py`): audited `GET /v4/sports/{sport}/odds` route,
`regions=us,uk,eu` (~20 books per pull incl. Pinnacle, BetMGM, DraftKings, FanDuel, William Hill,
Unibet variants, Betsson, LeoVegas, Coolbet, Grosvenor, GTBets…). Hard **CallBudget** caps with
exponential backoff; credit headers surfaced after every call; the API key is read from `.env`,
handed only to the request, deleted promptly, **never printed or logged**.

Safety gates (config `live:`): `dry_run: true` (no network/spend without the explicit flip) and
`signal_only: true` (**no bet/broker/order path exists anywhere in the codebase — enforced by a
test that greps the source**). Paper ledgers are append-only JSONL, gitignored, and a re-log of
the same signal raises. `PaperClvTracker` settles entry-vs-close into realized CLV with
NOT-REAL banners until a real feed is funded.

---

## 9. The Value Bets scanner — the money tool (`src/wcmodel/value/`)

**Mechanism (no model anywhere in this path):**
1. One capped live pull per market (`h2h` + `totals`, WC-2026, us/uk/eu ≈ 6 credits/scan).
2. Per event+market: de-vig **Pinnacle** with Shin → `fair_prob` per outcome. No Pinnacle line ⇒
   **coverage gap** (never fabricate a fair price from soft books).
3. Per soft book per outcome: `edge = fair_prob × soft_decimal_odds − 1`. Positive ⇒ the soft
   book pays more than the sharp's truth ⇒ +EV at that moment (positive expected CLV).
4. Suggested stake: ¼-Kelly on the edge (display-only suggestion).

**The six guards** (every one fired on real data; a spot is *bettable* only if ALL pass):

| Guard | Rule | Catches |
|---|---|---|
| Sharp-absent | no Pinnacle ⇒ coverage gap | fabricated edges |
| Too-good | edge > 10% ⇒ SUSPECTED ARTIFACT, excluded | stale/suspended/mismatched lines (a +128% MLB "edge" was a dead line) |
| Both-sides | one book +EV on **every** outcome of a full market ⇒ stale | dead lines (impossible on a live market). Requires full-market coverage — an adversarial review caught that the naive version killed real edges on partially-quoted 3-way markets |
| Book-tier | only configured *soft* books are bettable; sharps/exchanges tagged `non_soft` | "edges" at venues you can't/shouldn't bet |
| Freshness | quote older than 900s flagged stale (fail-open if the API omits `last_update`, documented) | evaporated edges |
| Longshot | odds > 8.0 tagged fragile | tiny prob error × big odds = spurious edge |

**Output:** a JSON bundle `{provenance, data:{bettable, filtered(+reasons), coverage_gaps}}`,
stamped `signal_only: true`, `is_synthetic: true` (NON-REAL banner — nothing here is a real
CLV/ROI claim until a funded feed flips it), gated before write (`gate_value` raises on a missing
stamp or malformed ValueBet — a violating bundle is never written). Bettable spots append to the
paper ledger `reports/value_paper_ledger.jsonl` (gitignored); `settle_one` → realized CLV later.

**First live scan (2026-06-09, 6 credits): 71 bettable / 401 filtered / 83 coverage gaps.** Max
surviving edge +9.3% (Scotland @ 6.64 gtbets; Bosnia @ 6.25 unibet). ~20 distinct picks across
books. Honest read: real but early-line value (lines loosen weeks out, tighten toward kickoff);
multi-book picks (the same pick +EV at 6–8 books) are more trustworthy than a single small-book
outlier (GTBets drove a cluster — loose lines, lowest limits).

---

## 10. What the model is NOT used for (and why) — the decision log

1. **1X2 model-vs-market betting: rejected.** Tied the sharp close; no CLV edge (Phase-4 result).
2. **Sharpening the old model via σ/widening: rejected.** Levers inert; under-confidence
   structural (data-dominated compressed posterior).
3. **Totals (O/U) model-vs-soft-book betting: built, then rejected with proof.** A full totals
   engine exists (`markets/`). The forward scan showed huge edges → treated as a suspected bug →
   diagnosis found the neutral-venue under-prediction (§5.4) → fixed → re-scan still showed a
   wall of bidirectional edges → final diagnosis: per-fixture goal-expectation miscalibration,
   confirmed against Pinnacle directly (model |gap| vs sharp == vs soft consensus; corr 0.52,
   slope 0.58). **All 55 "edges" were model error; none were bet.** The totals code remains as
   diagnostics; it is not a pick source.
4. **The strength-anchored model (current): used for the FORECAST + second opinion only.** It is
   a genuinely better forecaster (beats plain Elo held-out), but a better public-data forecast
   still ≈ agrees with the market ⇒ still no betting edge. This is stated in the UI.

Supporting diagnostic scripts kept in the repo: `diagnose_totals_calibration.py` (neutral split),
`sharp_totals_check.py` (model vs Pinnacle vs consensus), `ev_scan_poc.py` (multi-sport soft-vs-
sharp proof of concept), `sweep_strength_k.py` (anchor calibration), `clv_validation.py`
(accuracy/RPS vs market harness).

---

## 11. The dashboard UI (frontend) — `dashboard-ui/`

**Stack:** Svelte 4 + Vite + TypeScript, hash router, no backend — it reads static JSON bundles
from `public/bundle/` (staged by `scripts/copy-bundle.mjs` from `data/dashboard/`, which prefers
the newest live artifacts and falls back to committed fixtures). 107 vitest tests + Playwright
e2e. `npm run dev` → typically http://localhost:5173/.

### 11.1 The three surfaces

1. **Value Bets (primary; the default route).** The ranked +EV board:
   `event · market · pick · edge% · book · odds · sharp-fair% · model 2nd-opinion · ¼-Kelly stake
   · freshness · kickoff`. A prominent honesty header: *"Signals, not guarantees. The real test is
   CLV, not any single result. Soft books limit winners."* A collapsed **"Filtered (and why)"**
   section lists every rejected spot with its guard flags (transparency builds trust in what
   survives), plus coverage gaps. Last-scanned timestamp + credits used are shown.
2. **Track Record.** Realized-CLV scoreboard from the paper ledger (beat-close rate, avg CLV%,
   stratified, with NOT-REAL banner until funded). Fills in as logged bets settle.
3. **Forecast (secondary, deliberately demoted).** The original model dashboard — schedule with
   per-fixture win/draw/win bars, match detail (scoreline grid heat, most-likely scores, the
   "why" panel), and the tournament/bracket view (champion & advance probabilities, KO-slot
   occupants) — under a visible label: **"independent forecast — does NOT beat the market."**

### 11.2 The model second-opinion column (display-only)

`lib/modelSecondOpinion.ts` joins each value bet to the forecast bundle's 1X2 by exact
(home, away) — with a tiny explicit alias map for known odds-API↔model name divergences
("Bosnia & Herzegovina"↔"Bosnia and Herzegovina", "USA"↔"United States"); never fuzzy matching.
Display emphasis is deliberately asymmetric: **disagreement** (model rates the pick *below* the
sharp fair prob) renders as a prominent amber **⚠ "caution: below the market"**; agreement
renders muted ("model 30.0% · in line") because the old model agreed with almost every underdog
pick (weak evidence). A test proves the column never changes the bettable list/order (the model
cannot touch the edge path). Totals picks show "—" (no model view wired for totals lines).

### 11.3 The "no naked numbers" grammar (load-bearing UI principle)

Every probability rendered must carry uncertainty context (an `Estimate` with se / a distribution
bar / an explicit coverage-gap) — enforced by a vitest render-guard suite (21 tests) that fails
if any surface emits a bare point estimate. Missing data renders as an explicit `CoverageGap`
("why there's no number here"), never an imputed value, never silence.

### 11.4 Safety in the UI

No bet-placing affordance exists — no button/link/form that places, sizes, or submits a bet
(Playwright `assertNoBetAffordance` checks action-verb patterns AND anchored bare "Bet"/"Stake"
tokens; the ValueBets component test asserts zero buttons). The NON-REAL/DRY-RUN banner is
app-shell-level and persists across all routes; the bundle loaders *fail loud* if the banner/
provenance stamp is missing from a bundle.

### 11.5 Data contract (what the UI consumes)

`public/bundle/` after staging:
- `meta.json / schedule.json / tournament.json / track.json / fixtures/*.json` — the forecast
  bundle: every file wrapped in `{provenance:{as_of, posterior_key, git, is_synthetic, n_sims,
  banner}, data:…}`; every number `{value, se}` or a coverage_gap node. Current production
  bundle: as_of `2026-06-07T00:00:00Z`, posterior `b7b2cdb86a628635`, git `fa78838`, 20k sims.
- `value.json` — the value bundle: `{provenance:{scan_ts, sharp:"pinnacle", regions, credits…,
  signal_only:true, is_synthetic:true, banner}, data:{bettable[], filtered[], coverage_gaps[]}}`.

---

## 12. Validated results (the numbers, all leakage-guarded)

**Forecast quality (after the strength anchor, k=0.6):**
- Held-out 1X2 RPS 0.33277 (old model 0.35922; plain-Elo baseline 0.34045; n=2,111).
- Production-cutoff discrimination: Germany 88.4% v Curaçao (was 39%); Spain 91.4% v Cape Verde;
  Brazil 48% > Morocco 23% (was *leaning Morocco*); France 76.4% v New Zealand; Argentina 94.7%.
- Champion board (20k sims): **Spain 12.8%, Argentina 12.8%**, Brazil 6.8%, France 5.2%,
  England 4.9%, Portugal 4.5%, Netherlands 3.5%, Norway 2.6%, Germany 2.6%. (Old broken board:
  Norway #1 at 4.3%, France #27 at 1.8%.) Argentina advance-from-group 94.8% (was 74%).
- Neutral totals calibration: gap −0.341 → +0.019 goals; P(over 2.5) miscal −0.090 → −0.014.

**Market-efficiency findings:**
- 1X2: model ties the sharp close (no CLV edge).
- Totals: model-vs-sharp mean |gap| 0.077 ≈ model-vs-consensus 0.075; corr 0.52 → model is the
  outlier; all apparent totals edges were model error.
- Value scan: 71 bettable (2–9.3% edges) / 401 filtered / 83 gaps on one 6-credit scan; every
  >10% "edge" in the multi-sport PoC was an artifact (e.g. +128% on a dead MLB line, both-sides
  +EV on an offseason NHL line) and was auto-rejected.

**Engineering state:** full suite 627 passed / 0 failed; 44 leakage canaries (all with positive
controls); 24 value-scanner tests incl. the no-bet-path grep test; 107 vitest + svelte-check
clean + production build green. Main @ `fa78838`. Adversarial multi-agent reviews ran on every
load-bearing diff (the scanner core, the neutral fix, the strength anchor) and their real
findings (a both-sides guard that killed genuine edges; a panel-cache key that omitted the
cutoff; the gitignore for the paper ledger) were fixed with RED→GREEN tests.

---

## 13. Configuration reference (`config/config.yaml`, the important blocks)

```yaml
seed: 20260611                      # global; everything seeded/reproducible
elo:        {initial_rating: 1500, k_base: 40, k_by_match_type: {wc_finals: 1.0 … friendly: 0.4},
             home_advantage: 100, provisional_games: 5, provisional_volatility_threshold: 16.5}
windows:    {feature_years: 4, decay_half_life_days: 365}
model:
  likelihood: dixon_coles           # | bivariate_poisson
  neutral_home_adv_fraction: 0.5    # the neutral-venue fix (§5.4)
  strength_prior: {enabled: true, source: elo, k_att: 0.6, k_def: 0.6}   # the anchor (§5.2)
  covariates: {enabled: [], host_k: 1.4, hosts: [United States, Mexico, Canada]}   # empirical (P2b): k_elo=1.422 [1.18,1.64], n=873
  prior:      {sigma_att: 0.5, sigma_def: 0.5, home_loc: 0.25, rho_scale: 0.1}
  widening:   {mechanism: c, strength: 0.5}     # provisional-team predictive inflation
  inference:  {backend: advi, advi_iters: 30000, draws: 1000}
sim:        {n_sims: 20000, max_goals: 12, extra_time_scale: 0.3333, penalty_home_prob: 0.5}
backtest:   {primary_bookmaker: pinnacle, devig_method: shin, kelly_fraction: 0.25,
             foresight_red: {roi: 0.10, beat_close_rate: 0.58, avg_clv: 0.02},
             lockbox_fraction: 0.18, permutation_shuffles: 200}
live:       {dry_run: true, signal_only: true, sport_key: soccer_fifa_world_cup,
             regions: us,uk,eu, call_budget: {max_calls_per_day: 480}}
value:      {sports: [soccer_fifa_world_cup], markets: [h2h, totals], sharp_book: pinnacle,
             edge_min: 0.02, too_good: 0.10, longshot_odds: 8.0, stale_seconds: 900,
             kelly_fraction: 0.25, soft_books: [betmgm, draftkings, fanduel, betrivers,
             williamhill, bovada, betonlineag, unibet_*, betsson, leovegas, coolbet, grosvenor,
             gtbets, …], max_calls_per_scan: 2,
             ledger_path: reports/value_paper_ledger.jsonl}
markets.totals: {lines: [0.5…5.5], edge_threshold: 0.03, sharp_book: pinnacle}  # diagnostics only
dashboard:  {output_dir: data/dashboard, n_sims: 20000}
```

Secrets: `.env` (gitignored) holds `THE_ODDS_API_KEY` (value never committed/printed/logged) and
an empty `API_FOOTBALL_KEY` slot (injuries integration deferred).

---

## 14. How to run everything

```bash
# ── THE DAILY LOOP ──────────────────────────────────────────────────────────
# 1. Refresh the value board right before betting (~6 API credits):
cd ~/worldcup
PYTHONPATH=src .venv/bin/python scripts/scan_value.py

# 2. View the dashboard (auto-stages the newest bundles on startup):
cd dashboard-ui && npm run dev          # → http://localhost:5173/
#    (re-stage while it runs: node scripts/copy-bundle.mjs, then refresh)

# ── FORECAST / MODEL ────────────────────────────────────────────────────────
# Regenerate the forecast bundle (fit at the cutoff + 20k sim; minutes):
PYTHONPATH=src .venv/bin/python scripts/build_real_snapshot.py
# Recalibrate the strength anchor (offline, no credits; ~minutes per k):
PYTHONPATH=src .venv/bin/python scripts/sweep_strength_k.py --ks 0.0,0.4,0.6
# Diagnostics: diagnose_totals_calibration.py, sharp_totals_check.py (1 credit),
#              ev_scan_poc.py (multi-sport PoC, ~18 credits), clv_validation.py

# ── TESTS ───────────────────────────────────────────────────────────────────
uv run --extra dev pytest -m "not slow" -q       # full Python suite (~630, ~3 min)
uv run --extra dev pytest -k leakage -q          # the 44 leakage canaries
uv run --extra dev pytest tests/value -q         # the scanner (24)
cd dashboard-ui && npm test                      # vitest (107); npm run e2e for Playwright
```

**Operational gotchas (hard-won):**
- Run *scripts* with `PYTHONPATH=src .venv/bin/python …`, **not** `uv run` — `uv run` re-syncs
  the venv and has repeatedly broken the editable `wcmodel` install (recover with
  `uv pip install -e .`).
- Long jobs (the 20k-sim regen, k-sweeps) are best launched detached (`nohup … &`) — they take
  10–40 minutes.
- The posterior/panel/sim caches are content-addressed under `data/cache/`; any config/git/data
  change is a clean miss. Changing the `model:` block (even a predict-time knob) re-fits once.
- Test fixtures that fit on tiny synthetic stores pin `strength_prior.enabled=false` — on
  degenerate coarse fits the anchor can push `home_adv` negative and flip direction assertions
  (documented in the tests; not a production issue).

---

## 15. Binding invariants (the project's law)

1. **No data leakage / look-ahead, anywhere.** Everything reads through `read(cutoff)`; fits use
   strictly-pre-cutoff data; canaries with positive controls enforce it per phase.
2. **Too-good = suspected bug.** Any result past the foresight-RED ceilings, any >10% market
   edge, any 99% favorite ⇒ stop and root-cause; never celebrate first. (This rule caught every
   real bug in the project: fake totals edges, the cache-key leak, the neutral-venue bug.)
3. **Signal-only.** No bet/broker/order/execution path exists; a test greps for one. The user
   places every bet manually. Real money flow would be a separate, explicitly gated decision.
4. **Market-prior-free model.** Betting odds never feed the model (Elo is results-derived).
   Odds enter only at comparison layers (edge calc, CLV, baselines).
5. **NON-REAL provenance taint** until a real feed is funded: every bundle carries
   `is_synthetic`/banner; the gate refuses to write without it; the UI refuses to load without it.
6. **No naked numbers in the UI** — every probability has uncertainty or an explicit gap.
7. **Tested, not vibes.** TDD (RED→GREEN) per change; "tested, no lift" is a valid recorded
   outcome (rest_days); load-bearing diffs get adversarial multi-agent review before merge.
8. **The user controls all merges.**

---

## 16. Current state & possible next steps

**Live now (main @ `fa78838`):** the value scanner + dashboard (Value Bets primary, Track Record,
Forecast demoted), the strength-anchored model (k=0.6), the neutral-venue fix, the regenerated
20k-sim forecast bundle, all tests green. ~19k API credits remain.

**Deferred / open ends:**
- **Bet logging UX:** a one-click "I took this bet" action feeding the CLV Track Record (the
  ledger + settle machinery exist; the UI affordance doesn't yet).
- **Close-line settle automation** for the value ledger (pull the closing Pinnacle line near
  kickoff per logged bet; `settle_one` exists, scheduling doesn't).
- **Sharp-consensus fallback** when Pinnacle is absent (currently an honest coverage gap).
- **Multi-sport scanning** (config is a one-line list; the WC alone is thin by design).
- **API-Football injuries** (key slot exists, unfunded), **public deploy** (it's static
  files + JSON — trivial on Netlify/Vercel if ever wanted), **knockout-stage second opinions /
  totals model view** in the UI.
- The **fit-cache** re-fits on predict-time-only knob changes (wasteful, not wrong — accepted).

**The one-paragraph honest summary:** this project set out to beat the betting market with a
model and proved—rigorously, three different ways—that it can't. It then pivoted to the two
things that *are* real: a market-vs-market value scanner with disciplined artifact rejection and
CLV tracking (the only honest retail edge), and a genuinely credible, leakage-clean World Cup
forecast (now beating its own Elo baseline) presented without a single dishonest number. The
discipline (bitemporal reads, canaries with teeth, too-good-is-a-bug, adversarial review,
signal-only) is the product as much as the code is.

---

## 17. Glossary

- **1X2** — home win / draw / away win market. **Totals** — over/under total goals.
- **Sharp / soft books** — Pinnacle (low margin, fast, accurate = "truth") vs recreational books
  (slower, bettable, limit winners).
- **De-vig** — removing the bookmaker margin from odds to get fair probabilities (we use Shin).
- **Edge** — `fair_prob × offered_odds − 1`; expected profit per unit staked.
- **CLV** — closing-line value; entry odds vs closing odds. Positive average CLV ⇒ real edge.
- **RPS** — ranked probability score for 1X2 forecasts (lower = better).
- **Elo `rating_pre`** — a team's rating *before* a match (the leakage-safe feature).
- **`elo_z`** — z-scored latest pre-cutoff Elo per team; the strength-prior anchor.
- **Provisional team** — low-information team (few games / volatile rating) → widened predictions.
- **Bitemporal store** — data keyed by valid-time and observed-time; `read(cutoff)` = time machine.
- **Coverage gap** — an explicit "no number here, and why" instead of imputation or silence.
- **Foresight-RED** — implausibly-good backtest ceilings that hard-stop the run as a suspected leak.
- **Lockbox** — frozen final slice of history, evaluated once against pre-registered choices.
- **NON-REAL / DRY-RUN banner** — the taint stamped on all outputs until a real odds feed is funded.
