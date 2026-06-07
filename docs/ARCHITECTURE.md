# Architecture & Retrospective — WC-2026 Quantitative Forecasting & Paper-Betting System

**Status:** consolidated reference, written off `main` at HEAD `88e25e8` (branch `arch-retro`).
**Scope:** the whole system — the Python modeling pipeline (`src/wcmodel/`), the dashboard data
layer (`wcmodel.dashboard`), and the Svelte viewer (`dashboard-ui/`). Read-only synthesis; no
code or model behavior is changed by this document.

This is a map and a retrospective, not a tutorial. It grounds every claim in the specs
(`docs/superpowers/specs/`), the plans (`docs/superpowers/plans/`), `ASSUMPTIONS.md`,
`SOURCES.md`, `config/config.yaml`, and the module docstrings themselves. Where a claim is
gated, pending, or on a separate branch, it says so.

---

## 1. What the system is

A **quantitative 2026 FIFA World Cup forecasting and paper-betting system** whose single
objective is **positive closing-line value (CLV)** — and, downstream, positive *simulated/paper*
ROI — measured against the **sharpest available line** (Pinnacle close, or Betfair Exchange when
funded). It is **not** optimizing raw accuracy and **not** optimizing calibration; the binding
framing, preserved verbatim through every phase, is:

> CLV is the leading indicator and primary number, ROI is the goal, calibration is purely
> diagnostic and never the target.

Two design commitments distinguish it from a generic prediction model:

- **Market-prior-free by design.** The scoreline model learns attack/defense from match
  *results* through a hierarchical shrinkage prior. **Elo is not a prior or a covariate** in the
  model (it is double-derived from the same results); it survives only as an *independent* Phase-4
  baseline. The market line is never an input — it is only ever the thing we try to beat. This is
  what lets a positive number be evidence of edge rather than of fitting to the bookmaker.
- **Edge concentration on the thin tail.** Liquid 1X2 match markets are assumed effectively
  unbeatable; the thesis targets **tournament-progression markets** (outright winner, win-group,
  to-advance, stage-of-elimination) and **thin lines on low-information teams** — exactly the
  markets the backtest covers worst, which is why the *live forward-test*, not the backtest, is
  the authoritative number for the thesis.

The whole instrument is built **NON-REAL / dry-run by default**: no odds are purchased, no bet is
ever placed (there is no order/broker/exchange path in the codebase), and every surfaced number
off the synthetic harness is unmistakably labelled non-real. Flipping to a real feed is a single,
explicitly-gated funding switch (see §6).

---

## 2. The pipeline, phase by phase

The architecture is **phase-isolated modules over an as-of-dated artifact cache** (chosen over a
notebook monolith for its structural leakage guarantee, and over a full orchestration/feature-store
stack as overkill for a single-user laptop project). Each phase reads prior cached artifacts and
writes its own through a clean contract, matching the "STOP after each phase for review" cadence.

```
sources → ① as-of features → ② posterior → ③ sim probabilities → ④ backtest CLV/ROI
                                                  ⑤ live odds + latest posterior/sim → ranked signals + realized-CLV tracker
                                                  ⑥ build_snapshot → gated JSON bundles → ⑦ Svelte viewer
```

### P1 — Bitemporal data layer (`src/wcmodel/data/`)

The leakage spine the entire project rests on. Every fact carries **two** timestamps:
`valid_as_of` (when it pertains in the world) and `observed_at` (when *this version* was
recorded). The store is **append-only and bitemporal**, and the single load-bearing invariant is:

- **`read(cutoff)`** returns, per logical fact, the version with the greatest `observed_at ≤ cutoff`
  (and `valid_as_of ≤ cutoff`) — the value *as it stood at the cutoff, pre-revision*. The
  walk-forward simply sweeps the cutoff forward, so look-ahead is impossible **by construction,
  not by vigilance**.

Sources (`data/sources/`): **martj42 international results** (CC0, immutable, pinned git commit —
the model anchor); **computed Elo in-house** (`data/elo.py`, point-in-time, the *one* source of
truth used both as a feature and as the Phase-4 naive baseline — no second divergent Elo);
**StatsBomb Open Data xG** (static/versioned ⇒ reclassified as *point-in-time, not
revision-contaminated*, but **coverage-gated and never imputed** — present only on finals +
continental-cup matches, NULL across the entire qualifier/friendly backtest window); **Open-Meteo
climate** (ERA5 reanalysis, fixed for past dates); **derived features** (rest/travel/altitude,
point-in-time by construction); **The Odds API** (Pinnacle close; adapter built + mocked, the live
paid pull gated); and **market values / rosters** (interface-only, deferred — the only sources
that would be `current_only`/revision-contaminated). `features.build(cutoff) → DataFrame`
assembles one leakage-safe panel; `windows.py` keeps the **feature window** (~4yr, time-decayed)
strictly distinct from the **backtest window** (max odds-covered history, uncropped); `tiers.py`
stamps confederation × strength-band × match-type × COVID tags so every later metric stratifies.
**Per-phase leakage canary:** the `read(cutoff)` invariant test — a point-in-time source never
returns `observed_at > cutoff`.

### P2 — Bayesian scoreline model (`src/wcmodel/model/`)

`inference.fit(features, cutoff) → Posterior`: a hierarchical Bayesian scoreline model fit **per
cutoff** that outputs a **posterior over scoreline distributions** (not point estimates), so
parameter uncertainty flows into the sim and into stake sizing. Goals are twin Poissons with
`log λ = μ + home_adv·(1−neutral) + α_attack − β_defense`; **both likelihoods ship behind one
`ScorelineModel` interface** — Dixon-Coles (low-score `τ` correction) and bivariate-Poisson
(shared covariance) — and the Phase-4 lockbox picks the winner by out-of-sample RPS. Priors are
**independent** (no Elo): `α, β ~ Normal(0, σ)` with soft sum-to-zero centering and `HalfNormal`
hyperpriors ⇒ partial pooling shrinks low-data teams to the mean with wide posteriors.
**Provisional-widening** (binding from P1: a flagged team must carry more predictive uncertainty,
else the flag is decorative) ships as two mechanisms behind one switch — (a) likelihood
down-weight and (c) predictive-variance inflation — lockbox-decided, design-lean (c). Inference is
flexible behind the interface: **ADVI/Pathfinder** for the repeated walk-forward refits, **NUTS**
for final/periodic fits, with a periodic **ADVI-falsely-tight check** (`inference.advi_variance_check`)
because we depend on posterior *width*. **Per-phase canary:** fitting at an early cutoff is
invariant to appending future matches (the P1 canary lifted to the model layer).

### P3 — Monte-Carlo tournament simulation (`src/wcmodel/sim/`)

`simulate(cutoff, posterior, store, config) → SimResult`: a seeded, per-cutoff, **full-posterior**
Monte Carlo (default `n_sims = 20,000`) that propagates the posterior through the 104-fixture
bracket. The structure is **one posterior draw per simulation** (`θ_s` fixed for the whole sim) so
a team's strength is correlated across all its fixtures — drawing θ per-fixture would wrongly
decorrelate and distort deep-progression probabilities. Uncertainty enters the sim **exactly
once** (posterior draw + scoreline sampling); mechanism-(c) widening is deliberately *not* applied
in-sim (it would double-count). Groups resolve by **source-verified FIFA-2026 tiebreakers in
order** (`groups.py`: points → head-to-head a/b/c recursive → all-group GD/GF → fair-play/ranking
stand-in as a seeded random tail) — head-to-head correctly **precedes** all-group GD/GF, a
betting-material ordering fixed via a cross-model + `/browse` source check. The **third-place →
R32 assignment** (`thirds.py`) — rank 12 thirds, take best 8, map each to its FIFA-predetermined
slot — was the focal adversarial-review target of the phase. Knockouts (`knockout.py`) resolve via
ET at scaled rates (≈30/90) → a true 50/50 shootout coin-flip (no uncalibrated tilt). Output: a
progression matrix per team × stage **with a Monte-Carlo standard error on every emitted market**
(the tail markets like champion/reach-SF carry the largest relative MC error and are exactly the
ones we price). **Per-phase canary:** simulating at cutoff C is invariant to mutating a post-C result.

### P4 — Backtest (`src/wcmodel/backtest/`)

`walkforward(store, odds_samples, config) → Metrics`: one honest, leakage-safe walk-forward that
answers the project's whole question — **does the model earn positive CLV (and simulated ROI)
against the sharp close, beating BOTH the market-only and naive-Elo baselines** — every metric
stratified by tier. At each cutoff: `features.build → cached_fit → (simulate) → de-vigged market
price → edge → non-bet filters → ¼-Kelly × uncertainty stake → settle on the actual result`. The
disciplines:

- **CLV first** (`clv.py`): beat-the-close rate + avg CLV% = `entry/close − 1`, on transacted prices.
- **Empirical de-vig** (`devig_select.py`): Shin is the prior; multiplicative/power are sensitivity
  checks; **Buchdahl/odds-proportional is sensitivity-only and is not even a choosable method** (it
  manufactures phantom favourite-longshot value); the best-calibrated de-vig of the close is chosen
  by RPS. Sign-flip / wide-spread / stale snapshot → non-bet (logged, counted, never dropped).
- **Two baselines** (`baselines.py`): market-only + naive-Elo, both through the identical
  settle/score path; "beat both or say so" is an asserted report line, not a vibe.
- **¼-Kelly × posterior-uncertainty shrink** (`staking.py`), bet only when `edge > 2pp` (the
  trigger, not a DOF); ROI/drawdown/bankroll with seeded bootstrap CIs.
- **The anti-overfit gates** (`validation.py`, `lockbox.py`, `report.py`): a **single-use lockbox**
  (final 18% of odds history by date) enforced as a real *mechanism* — `config/lockbox.json` pins
  the boundary + the **pre-registered count of 9 tuning DOF** before any tuning, and
  `LockboxRegistry` flips `used → true` **on disk** and physically refuses a second evaluation even
  from a fresh process; a **permutation null** (200 shuffles, RPS vs market+base-rate, judged at
  ~99th percentile); and **foresight-RED ceilings** (ROI > +10%, beat-close > 58%, avg CLV > +2%)
  enforced as a hard-STOP test — any metric past RED ⇒ suspected leak ⇒ STOP, never celebrate.

Load-bearing reality: **no real odds exist yet**, so this phase delivers *validated machinery + a
gated one-switch pull*, never a real CLV/ROI number. It is explicitly a **big-match,
revision-contaminated UPPER BOUND**; the minnow/progression tail is a coverage gap here. **Focal
canary:** a post-cutoff odds-or-result mutation must not move any as-of-cutoff price/edge/stake/P&L
(seeded ⇒ bit-identical, with non-vacuity teeth).

### P5 — Live forward-test (`src/wcmodel/live/`)

`scan(cutoff=now) → Ranked`: the **per-cutoff backtest body called at `cutoff = now`** — it
*reuses* `model_fair_1x2`/`edge_vector`/`choose_devig`/`stake_fraction`/`clv`/`non_bet_snapshot`/
`check_foresight_red`, never reimplements the decision. Because `read(now)` only ever sees ≤now
data, the live number is **point-in-time-correct by construction** and is therefore the
**authoritative, trustworthy forward number** the revision-contaminated backtest cannot be —
exactly for the minnow/progression edge the thesis targets. Pieces: `odds_live.py` (the new live
fetch route, gated behind a key + dry-run), `ingest_live.py` (write the actual finished result
point-in-time), `decide.py` (the one-cutoff decision), `scan.py` (rank by edge × liquidity),
`clv_tracker.py` (the append-only paper ledger — the authoritative number). The **new risk class
is operational, not look-ahead**: the entry price is logged **at decision time** and never
retroactively re-priced from the close, the ledger is **append-only/immutable**, and the **live
mis-log canary** (`validation.py`) proves that logging the close as the entry would be caught.
**SIGNAL-ONLY / PAPER** is an absolute, asserted invariant — the system emits signals + a paper
ledger; any real bet is the operator's manual action. The D3 penalty-KO fix (shootout-winner
ingest) landed before R32 so the live path can condition on knockouts.

### Dashboard data layer — Plan 1 (`src/wcmodel/dashboard/`)

`build_snapshot(cutoff)` writes **provenance-stamped, gated, leakage-safe JSON bundles** over the
existing P1–P5 outputs. It only assembles, gates, stamps, and writes — it **recomputes nothing**
(a snapshot *is* a `read(cutoff)`, so it is leakage-safe by construction). One bundle per cutoff
dir: `schedule.json` (group forecast rows + KO occupant rows), `tournament.json`
(`team_progression` with MC SE), per-fixture `fixtures/<id>.json` (scoreline shortlist + grid +
1X2 + "why" + edge), `track.json` (CLV/RPS/reliability or an honest coverage gap), `meta.json`.
Every artifact passes a **per-surface no-naked-number / coherence / coverage-gap / no-impute gate**
(`schema.py`) before disk — a violating artifact is never written; `json.dumps(allow_nan=False)`
fails loud on a residual NaN. Each file is an **envelope** `{provenance, data}` carrying as-of,
posterior/git version, n_sims, and the synthetic banner. The gated CLI (`wc-dashboard-build`)
defaults to dry-run; `--no-dry-run` **refuses** (the real feed is gated).

### Viewer — Plan 2 (`dashboard-ui/`)

A dependency-light **Svelte 5 + Vite + TypeScript** static viewer that **renders the Plan-1
bundles and recomputes nothing** — no model in the browser ⇒ **leakage-safe by construction**. Its
load-bearing rule is the **no-naked-number grammar**: every probability-shaped token must sit
inside one of three conscious markers — `data-uncertainty` (estimate + its `±`, or "the
distribution IS the uncertainty" for win-bars/grids/score-pills), `data-coverage-gap` (an honest
absence), or the **reviewed `data-derived` exemption** for non-forecast numbers only (edge %,
¼-Kelly stake signal, backward-looking track metrics) — enforced by `tests/no-naked-number.test.ts`
(with non-vacuity teeth) across every surface including the composed `App` shell and the honesty
bar. A persistent honesty bar shows the as-of/version and the `DRY-RUN · SYNTHETIC ODDS · NOT REAL`
chip, **gated on `provenance.is_synthetic`, not banner-presence** (fail-safe NON-REAL). The
Playwright NON-REAL e2e visits every route asserting the banner persists and there is **no
bet/stake/buy/order affordance** anywhere (the stake is a read-only signal).

---

## 3. Cross-cutting disciplines

These run through every phase and are the project's actual product.

- **NO leakage / bitemporal `read(cutoff)`.** The single invariant of §P1, enforced not by review
  but by construction, plus a **per-layer leakage canary** that lifts the same test to each phase:
  P1 `read(cutoff)` invariant → P2 fit-at-cutoff invariant → P3 sim-at-cutoff invariant → P4
  post-cutoff odds/result mutation invariant → P5 live mis-log canary → dashboard observed-after
  invariant. Each canary has **non-vacuity teeth** (a positive control proves a real leak *would*
  move it) — a canary that can't fail is the failure mode the project explicitly guards against.
- **No naked numbers.** Every probability wears its uncertainty as one inseparable unit (MC SE on
  progression, 94% HDI on team strength, the distribution-as-uncertainty for scorelines), and the
  market it disagrees with is always in view. Structurally enforced on *both* sides: the serializer
  gate (`dashboard/schema.py`) refuses to write a naked artifact, and the render guard
  (`tests/no-naked-number.test.ts`) refuses to render one. A coverage gap renders as a gap, never
  as an invented number.
- **NON-REAL / dry-run gating.** `live.dry_run` and `dashboard.dry_run` default **true**; the
  paid feed (`fetch_historical`/`fetch_live_odds`) raises without a key; `signal_only` is a
  standing invariant with no false setting wired. The synthetic taint is **fail-safe**: a bundle
  reads REAL only when dry-run is off AND *every* item is explicitly `is_synthetic=False` —
  anything missing/ambiguous/mixed → NON-REAL. So unverified data can never silently paint a
  real-looking banner.
- **Content-addressed caches / reproducibility.** One global `SEED` (`20260611`) spawns every RNG
  via NumPy `SeedSequence` (reproducible *and* parallel-safe). Every artifact is keyed by
  `hash(inputs, config, cutoff, seed, git-commit)` with `uv.lock` committed to pin the compute
  environment — any input/spec change invalidates the cache, so there are no stale-artifact bugs.
  Data + sim layers are bit-reproducible; inference is reproducible-on-fixed-hardware.
- **Cross-model Codex + multi-agent convergence review (the core safety mechanism).** Every
  load-bearing change is adversarially reviewed by an *independent* model (Codex) plus a
  multi-agent convergence pass, and **nothing merges until that review is satisfied and the focal
  canary is green**. This is not a nicety bolted on at the end — the git history shows it is how
  almost every fix in the project was found (the commit log is dense with "Codex finding",
  "FOCAL Codex", "convergence", "fail-safe", "non-vacuous"). It is the project's primary defense
  precisely because the failure modes here (a vacuous canary, a leaked feature, a taint that
  fails open) are the kind an author's own APPROVED review systematically misses.

---

## 4. Retrospective — what the cross-model loop caught that in-house APPROVED reviews missed

The pattern across the project is consistent: an in-house pass marks a phase APPROVED and
*correct-looking*, and the independent cross-model review then finds the place where the safety
property was **present in name but vacuous in fact**, or where a guard **failed open instead of
safe**. A few concrete, load-bearing examples:

1. **Leakage canaries made non-vacuous.** Several canaries initially *passed* without actually
   testing anything — the mutated post-cutoff fact didn't influence the path under test, so the
   assertion was trivially true. The convergence review forced each canary to carry a **positive
   control** proving a real leak would move it (e.g. the dashboard canary isolating the
   `observed_at` gate with a played-before/observed-after bracket fixture; the P4 canary's
   non-vacuity teeth). Lesson: *a green canary is worthless until you've proven it can go red.*

2. **The volatility threshold that flagged nobody.** The provisional-volatility threshold sat at a
   value (`40`) that flagged **0.00%** of team-match states — decorative, the exact failure mode
   the flag exists to prevent. The fix re-derived it empirically (`scripts/derive_volatility_threshold.py`)
   from the full martj42 history (p95 ≈ `16.5`, now flagging the most-volatile ~4.9% tail). Lesson:
   *a guard parameterized by intuition can silently guard nothing.*

3. **Fail-safe taint vs fail-open taint.** The synthetic-taint logic originally only flagged
   *positively-synthetic* items, so an **unmarked** item slipped through as REAL and could drop the
   NON-REAL banner. The fix inverted the default: a bundle is NON-REAL unless *every* item proves
   itself explicitly real (Plan-1 FIX A), mirrored at the render layer (the banner gated on
   `is_synthetic`, not banner-presence). Lesson: *safety defaults must fail closed; "real unless
   proven synthetic" is backwards.*

4. **The UTC-date edge key that silently dropped 28 fixtures.** The dashboard keyed edges on the
   fixture's **local** date while the scanner keyed on the **UTC commence date**; a negative-offset
   evening kickoff's local date is one day earlier, so **28 of 72 group fixtures** silently missed
   their edge into a coverage gap. Caught as a FOCAL Codex finding. Lesson: *two correct-looking
   keys that disagree by a timezone produce a silent, plausible-looking wrong answer.*

5. **The model-vs-market ordering that was betting-material.** An early draft of the FIFA group
   tiebreakers put **all-group GD/GF before head-to-head**; the source-verified 2026 order is the
   reverse, and the difference changes which team advances in real scenarios. Corrected via a
   cross-model + `/browse` source check. Lesson: *"looks plausible" is not "source-verified," and
   the gap can be directly value-moving.*

6. **Guards/gates that didn't cover every surface.** The no-naked-number gate initially covered
   only the scoreline grid and the progression table; the homepage, the track record, the
   fixture headline, and the shortlist **escaped the STOP**. The render guard initially skipped the
   composed `App` shell and the honesty bar. Both were closed only after the convergence pass
   enumerated the uncovered surfaces. Lesson: *a guard that covers "the obvious surface" leaves the
   rest unguarded by default.*

7. **A cache key recording a value the computation never used.** The posterior cache keyed on the
   *global* `load_config()["elo"]` rather than the threaded `cfg["elo"]`, so a lockbox K/T sweep
   could serve a stale fit keyed to an Elo it never actually ran with (the "P2-T8 stale-serve"
   lesson) — threading the config end-to-end was a must-do plumbing item the review insisted on
   before the lockbox could be trusted.

The through-line: **in-house APPROVED reviews validated that the code did what the author
intended; the cross-model loop validated that the safety property was actually true** — and those
are different questions. The vacuous canary, the decorative threshold, the fail-open taint, and the
ablation/cache that "measured nothing until the thing was actually threaded through" are all the
same shape: a guarantee that reads as satisfied while being empty.

---

## 5. The map — file/module table

### `src/wcmodel/` (Python pipeline — 61 modules across 6 subpackages)

| Path | Responsibility |
|---|---|
| `config.py` | Load/validate `config.yaml`; central seed management. |
| **data/** (Phase 1 — bitemporal layer) | |
| `data/store.py` | The append-only bitemporal store; the `read(cutoff)` invariant. |
| `data/elo.py` | In-house computed point-in-time Elo + the 1X2 naive baseline (one source of truth). |
| `data/features.py` | `build(cutoff) → DataFrame`: the per-cutoff leakage-safe feature panel. |
| `data/windows.py` | Feature window (~4yr, decayed) vs backtest window (uncropped) — kept distinct. |
| `data/tiers.py` | Confederation / strength-band / match-type / COVID stratification tags. |
| `data/coverage.py` | StatsBomb coverage enumeration (xG coverage-gated, never imputed). |
| `data/devig.py` | De-vig functions (multiplicative / power / Shin), pure math. |
| `data/tournament.py` | WC-2026 structure loader + validator (gated on `tournament_2026.yaml`). |
| `data/cache.py` | Content-addressed data-layer cache. |
| `data/sources/results.py` | martj42 international results adapter (immutable, pinned commit). |
| `data/sources/statsbomb.py` | StatsBomb xG adapter (point-in-time, coverage-gated, null-safe). |
| `data/sources/odds.py` | The Odds API adapter (Pinnacle close; live pull gated). |
| `data/sources/climate.py` | Open-Meteo ERA5 reanalysis climate adapter. |
| `data/sources/derived.py` | Rest days / travel / altitude (point-in-time by construction). |
| `data/sources/market_values.py` | Squad market values — interface only, deferred (would be contaminated). |
| **model/** (Phase 2 — Bayesian scoreline) | |
| `model/scoreline.py` | `ScorelineModel` interface + the two PyMC likelihoods (DC + bivariate-Poisson). |
| `model/likelihoods.py` | Scoreline log-likelihoods (NumPy reference + PyTensor versions). |
| `model/inference.py` | Backend dispatch (ADVI/Pathfinder/NUTS) + the ADVI-falsely-tight check. |
| `model/posterior.py` | The `Posterior` product: `predict_scoreline` / `predict_1x2` per fixture. |
| `model/widening.py` | Provisional-widening mechanisms (a) and (c) behind one config switch. |
| `model/calibration.py` | In-sample RPS-vs-Elo + posterior-predictive-check harness. |
| `model/rest.py` | Predict-time leakage-safe `rest_days`. |
| `model/panel.py` | Design-matrix / panel assembly for the fit. |
| `model/cache.py` | Content-addressed posterior cache (folds `cfg["elo"]`). |
| `model/volatility_diagnostic.py` | Volatility-arm sizing diagnostic (how many field teams trip the threshold). |
| **sim/** (Phase 3 — Monte Carlo) | |
| `sim/run.py` | `simulate(cutoff, posterior, store, config)` — the tournament-layer leakage gate. |
| `sim/tournament.py` | The full-posterior MC loop + progression aggregation (one draw per sim). |
| `sim/groups.py` | Group standings + source-verified FIFA-2026 tiebreakers. |
| `sim/thirds.py` | Third-place ranking + R32 slot assignment (the focal-review target). |
| `sim/knockout.py` | One KO tie: regulation → ET (scaled) → 50/50 shootout. |
| `sim/bracket.py` | Parse the verified tournament dict into a sim-ready bracket / feeder graph. |
| `sim/scoreline.py` | Per-draw scoreline sampling (raw DC/BP pmf). |
| `sim/cache.py` | Content-addressed sim cache. |
| **backtest/** (Phase 4 — backtest/CLV/ROI) | |
| `backtest/walkforward.py` | `walkforward(...) → Metrics` — the walk-forward integration heart + Elo memo. |
| `backtest/clv.py` | CLV (beat-close rate + avg CLV%) — the primary number. |
| `backtest/baselines.py` | Model fair price, market-only + Elo baselines, edge, RPS diagnostic. |
| `backtest/staking.py` | ¼-Kelly × uncertainty shrink, commission, bankroll, bootstrap CIs. |
| `backtest/validation.py` | The backtest leakage canary + the foresight-RED hard-STOP. |
| `backtest/lockbox.py` | The single-use lockbox as an on-disk mechanism (refuses a 2nd evaluation). |
| `backtest/devig_select.py` | Empirical de-vig selection (Shin prior, best-of-close by RPS). |
| `backtest/odds_ingest.py` | Real pure-parse path + the labelled NON-REAL synthetic-odds harness. |
| `backtest/report.py` | Stratified reporting + permutation null + coverage-gap rendering. |
| `backtest/cache.py` | Content-addressed `cached_walkforward`. |
| **live/** (Phase 5 — live forward-test) | |
| `live/scan.py` | `scan(cutoff=now) → Ranked` — rank by edge × liquidity. |
| `live/decide.py` | The one-cutoff live decision (reuses the Phase-4 functions). |
| `live/odds_live.py` | The new live fetch route + dry-run harness + call-budget guard (gated). |
| `live/ingest_live.py` | Write a finished fixture's actual result point-in-time. |
| `live/clv_tracker.py` | The append-only realized-CLV paper ledger (the authoritative number). |
| `live/validation.py` | The live mis-log canary + append-only immutability gates. |
| `live/tournament.py` | Live tournament-conditioning helpers (KO winner override, post-D3). |
| `live/cli.py` | The thin live runner (dry-run gated). |
| **dashboard/** (Plan 1 — snapshot data layer) | |
| `dashboard/build.py` | The snapshot orchestrator: assemble → gate → stamp → write (recomputes nothing). |
| `dashboard/schema.py` | Serializer-side guards (no-naked-numbers / coherence / coverage-gap / no-impute). |
| `dashboard/provenance.py` | The provenance envelope (as-of + cache key + git + NON-REAL taint). |
| `dashboard/fixtures.py` | Per-fixture forecast artifacts (shortlist + grid + 1X2) + schedule assembly. |
| `dashboard/tournament_view.py` | Per-team progression (+ MC SE) + derived future-KO occupants. |
| `dashboard/why.py` | Match-detail "why": team-strength posterior (94% HDI), rest days, coverage-gated xG. |
| `dashboard/track.py` | Track-record artifact (CLV/ROI/RPS-vs-baselines + derived reliability bins). |
| `dashboard/edges.py` | Per-fixture edge overlay re-keyed to the scanner's opportunities (UTC commence key). |
| `dashboard/cli.py` | The gated operator CLI (`wc-dashboard-build`; `--no-dry-run` refuses). |

### `dashboard-ui/src/` (Plan 2 — Svelte viewer — 13 components/surfaces + 5 TS libs)

| Path | Responsibility |
|---|---|
| `main.ts` / `App.svelte` / `app.css` | Entry point; app shell (bundle load, honesty bar, surface switch); CSS tokens. |
| `lib/types.ts` | Typed mirror of the Plan-1 bundle envelope contract. |
| `lib/bundle.ts` | Bundle loader (envelope unwrap, provenance). |
| `lib/guards.ts` | Coverage-gap / degenerate-input guards. |
| `lib/router.ts` | Hash router (with a malformed-percent-escape decode guard). |
| `lib/format.ts` | The uncertainty-grammar formatting helpers (load-bearing). |
| `components/Estimate.svelte` | A point estimate bound to its `±` companion. |
| `components/CredibleInterval.svelte` | 94% HDI display; degrades to `—` on bad/degenerate input. |
| `components/WinBar.svelte` | 1X2 distribution-as-uncertainty bar (clamps each segment, never recomputes). |
| `components/ScorelineGrid.svelte` | Joint scoreline grid; degrades to a coverage gap on a ragged/empty/all-zero grid. |
| `components/ScorePill.svelte` | Most-likely score + prob as one distribution readout ("1–0 · 12%"). |
| `components/EdgeChip.svelte` | The derived model-vs-line edge chip (`data-derived`). |
| `components/CoverageGap.svelte` | The honest "insufficient coverage" marker. |
| `components/HonestyBar.svelte` | Persistent as-of/version bar + the NON-REAL chip (gated on `is_synthetic`). |
| `surfaces/Schedule.svelte` | Landing: 104 fixtures as forecast rows + KO occupant rows + next-up anchor. |
| `surfaces/MatchDetail.svelte` | Drill-down: grid + 1X2-vs-line + the "why" + edge/stake. |
| `surfaces/Tournament.svelte` | Team-centric progression table (the coherence ladder). |
| `surfaces/Track.svelte` | Track record (CLV / RPS / reliability, or an honest coverage gap). |

---

## 6. Gated / post-funding follow-ups

Each is documented in `ASSUMPTIONS.md` / the specs and is intentionally *not* in v1; each entry
states what it needs.

- **The real-odds-feed flip (`decision_ts` vs `cutoff`).** Flipping `live.dry_run=false` /
  `--no-dry-run` is the single gated funding switch. The funding-flip runbook requires: verify
  pricing-fits-budget + the Phase-0 four-point checklist; **re-pick the sharp benchmark** (Pinnacle
  closed its public API in July 2025 — verify The Odds API still carries its close, else use Betfair
  Exchange; the fetch is already feed-agnostic); confirm the call budget ≤ plan quota; supply the
  key. **Pre-flip code follow-up:** separate an explicit `decision_ts` (bet-commit instant) from the
  `cutoff` evaluation horizon and require `decision_ts < close_ts`, so genuine-live prices the
  latest *transactable* snapshot at decision time rather than treating the latest-so-far as the
  close. This bites only once the real feed is funded; the dry-run machinery is honest as-is. Real
  odds samples must also be stamped `is_synthetic=False` or the fail-safe taint keeps the bundle
  NON-REAL.

- **Market-value / injury features.** Deferred / interface-only, flagged the *first* optional
  feature to revisit (the highest-value supplementary signal for minnows where Elo is noisy). Needs:
  a verified license and — critically — **point-in-time snapshots**, not current scraped state
  (scraping today's value under an old `valid_as_of` would leak the revision past the read
  invariant). Until then they would surface as `current_only` / `revision_contaminated` exposure.

- **The market-prior refinement (the held spec).** The project is deliberately market-prior-free.
  A future refinement that blends the sharp line into the prior is a held idea, not a committed
  design — it would need its own spec and would have to demonstrate, against a lockbox/CLV ablation,
  that it adds CLV rather than just regressing the model toward the line it is trying to beat.

- **The ghosted-sharp-line in the WinBar.** Spec §4 wants the de-vigged sharp 1X2 line ghosted into
  the win-bar. `WinBar` already accepts an optional `line` prop and renders it naked-number-safely,
  but Plan-1's edge node emits only the scalar `edge` + `entry_odds` for the staked side (no
  de-vigged market 1X2), so `line` is currently **unfeedable** from the bundle. Closing it needs a
  **Plan-1 data-layer follow-up** to emit the de-vigged market 1X2 in the forecast/edge artifact —
  a data change, not a UI change. v1 conveys model-vs-market via the EdgeChip instead.

- **The bracket-tree visualization.** Progressive / out of scope for v1 (spec §7). Along with the
  rich team-strength posterior drill-down, deeper calibration views, and provenance/version detail
  panels, it is a viewer-side addition over already-emitted outputs — no model or data-layer change
  required, just UI work.

### The covariates work — on branch, pending

A separate branch (not in this worktree at HEAD `88e25e8`) adds **model context covariates**
(`rest_days` / host) per the spec `docs/superpowers/specs/2026-06-07-model-context-covariates-design.md`
(not present here). It adds **leakage-safe** covariates — computed only from matches that exist at
the cutoff, NULL for an unplayed predecessor — **gated by an RPS/CLV ablation** so a covariate ships
only if it demonstrably improves the number rather than merely adding a knob (and thereby lockbox
overfit risk). Status: **on branch, pending** — described here from the spec contract, not validated
in this worktree.

---

*Grounding note:* the root `README.md` lives on `main` and is not present in this `arch-retro`
worktree (HEAD `88e25e8`); this document is grounded in the specs, plans, `ASSUMPTIONS.md`,
`SOURCES.md`, `config/config.yaml`, the `dashboard-ui/README.md`, and the module docstrings, all
read directly from this worktree.
