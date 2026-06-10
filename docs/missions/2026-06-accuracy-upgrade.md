# Mission Brief — WC-2026 Forecast Accuracy Upgrade

**Repo:** `~/worldcup` (main @ `fa78838` or later)
**Today:** 2026-06-09 · **Kickoff:** 2026-06-11 · **Round of 32 begins:** ~2026-06-28

**Objective:** improve the *forecast* — held-out 1X2 RPS, calibration/reliability, and scoreline-distribution fidelity — so per-match win/draw/loss and most-likely-score outputs are as accurate as a public-data model can be. This is forecast work, not edge work: we have already proven (three ways) the model does not beat the market, and nothing here changes that claim or touches the value scanner.

**How to work this brief:** Phases 0 and 1 run first, strictly in order. Phase 1 ends in a decision gate (G1) where the user picks the order of Phases 2–5. Phase 3's data acquisition is the long pole and may start in parallel once G1 passes. Each phase: spec → plan → RED tests → implement → GREEN → report → **STOP at the checkpoint and wait for the user**. One branch per phase (`feat/p<N>-<slug>`); never merge to main yourself.

---

## 1. Required reading before any code

In order: `CLAUDE.md` (if present) → the complete system document in `docs/` (titled "WC-2026 Quant System — Complete System Document") → `ASSUMPTIONS.md` → `SOURCES.md` → `config/config.yaml` → skim `docs/superpowers/specs/` to match the existing spec format. Do not start a phase without having read these.

## 2. Binding rules (non-negotiable)

1. **No leakage.** Every new data source enters the bitemporal store with `valid_as_of` / `observed_at` and is read only through `read(cutoff)`. Every new source ships with leakage canaries **with positive controls** (an injected leak that MUST trip the canary, proving non-vacuity). Pattern: a fact observed after the cutoff changes nothing; the same fact observed before the cutoff must change the fit.
2. **Too-good = suspected bug.** Any surprising accuracy jump (including the model suddenly *beating* the market on held-out RPS) → hard stop, root-cause, write it up. Never celebrate first.
3. **Market-prior-free model.** Betting odds never feed the model. Phase 3 raises a spirit-of-the-rule question and has a mandatory user sign-off gate (G3) before any code.
4. **"Tested, no lift" is a valid, recorded outcome.** Do not force-adopt changes that fail their held-out gate. Write the report, set the config off, move on.
5. **TDD, RED→GREEN.** Never weaken, skip, or delete an existing test to make something pass. Full suite green at every checkpoint.
6. **Config-gated + byte-identical off.** Every model change sits behind a config flag and is byte-identical to the current model when off (existing pattern: `strength_prior.enabled`).
7. **The user controls all merges.** Pause when a load-bearing diff is ready and announce: *"ready for cross-model (Codex) review"* — then wait.
8. **No naked numbers** in anything user-facing; coverage gaps are explicit, never imputed.

## 3. Operational rules (hard-won — do not violate)

- Run scripts as `PYTHONPATH=src .venv/bin/python scripts/<x>.py`. **Never `uv run` a script** (it re-syncs the venv and breaks the editable install; recovery is `uv pip install -e .`). Tests via `uv run --extra dev pytest …` are fine.
- Any change to the `model:` config block invalidates the posterior cache → refits take 10–40 min. Launch long jobs detached (`nohup … > logs/<x>.log 2>&1 &`) and poll the log; never block a session on a fit.
- Test fixtures on tiny synthetic stores pin `strength_prior.enabled=false` (degenerate fits can flip signs). Apply the same pattern to any new anchor/covariate.
- **Spend zero Odds-API credits.** Everything in this brief is offline. Use only odds already in the store; if stored odds coverage is thin for some analysis window, report that as a limitation — do not pull history.
- Never print or log `THE_ODDS_API_KEY`.

## 4. Explicit non-goals (do not build, do not "improve")

The value scanner edge path (`src/wcmodel/value/`) and its guards; any bet-execution affordance; weather/heat covariates; FIFA-ranking ingestion; revisiting rest-days; penalty-shootout skill modeling; blending market odds into the model or forecast. The model's only consumers remain the Forecast tab and the display-only second-opinion column, and a test already proves the model cannot touch the bettable list — keep it that way.

## 5. Evaluation protocol (used by every phase)

- **Primary metric:** held-out 1X2 RPS (lower = better) using the established protocol — e.g. the 2024-06-01-cutoff / n≈2,111 set from the k-sweep — plus reliability curves for 1X2 and for P(draw) specifically.
- **Secondary:** neutral-venue total-goals calibration gap; tail fidelity at large Elo gaps; champion-board sanity (no >95% match favorites; orderings pass the smell test).
- **Never consume the lockbox.** It is single-use and frozen. All evaluation here uses standard held-out windows.
- **Comparisons are paired:** when comparing model vs market or variant A vs B, score the identical match set.
- **Expectation honesty in every report:** a *perfect* model's modal exact score is ~10–13%; the deliverable is sharper, better-calibrated distributions, not certainty, and not a betting edge.

---

## Phase 0 — Tournament-readiness ops (deadline: 2026-06-10 EOD, before kickoff)

**Goal:** the freshest possible production forecast, and a one-command daily loop, before real matches start arriving.

1. **Ingest results through today.** Pull the latest martj42 data (warm-up friendlies since the 2026-06-02 production cutoff) and ingest POINT_IN_TIME via the existing machinery. Verify row counts increase; verify a `read(cutoff=2026-06-02)` is unchanged (the existing canary pattern should cover this — confirm it runs).
2. **`scripts/daily_update.py`** — one idempotent command that runs: ingest new results → `features.build_cached` → `cached_fit(cutoff=today)` → 20k-sim → `build_snapshot` → stage bundles (`copy-bundle`). Flags: `--cutoff`, `--dry-run`. Writes a run log and prints a provenance summary (as_of, posterior key, git, n_sims). Designed for `nohup`. Re-running the same day must be safe (cache hits, no duplicate ingests). It must spend **zero** API credits — the value scan stays a separate, manual command. Document a launchd/cron recipe in `docs/` but do not install it; the user decides scheduling.
3. **Conditioning smoke test.** June 12 is the first production use of the played-results conditioning path with the real 2026 bracket. Verify an end-to-end test exists that ingests a fabricated played group match at a fake cutoff and confirms the sim fixes that result and downstream advance probabilities shift coherently. Add it if missing.
4. **Regenerate the production bundle** at the new cutoff (detached); verify the dashboard loads it, provenance updated.

**Checkpoint C0:** show the champion/advance board diff old-cutoff → new-cutoff. Sanity: small moves only (friendlies barely move Elo). A large move = too-good/too-weird → investigate before proceeding.

---

## Phase 1 — Headroom diagnostic (the roadmap generator)

**Goal:** quantify, on the *anchored* model (k=0.6), exactly where and how much the model trails the de-vigged sharp close — turning "make it more accurate" into a ranked slice list and a stopping rule. The prior CLV validation predates the strength anchor; rerun it.

1. Build on `clv_validation.py` (or a new `scripts/model_market_gap.py`): for every stored-odds-covered held-out match (standard windows only, lockbox untouched), Shin-devig the Pinnacle close → market 1X2 probabilities; compute paired `RPS_model` vs `RPS_market` on the identical set.
2. Stratify: |Elo gap| quartiles · confederation pairing (UEFA–UEFA, UEFA–CONMEBOL, other-cross-confed, intra-other) · match tier · neutral flag · provisional-team involvement.
3. Deliverable: `reports/headroom_<date>.md` — a ranked table of slices by `RPS_model − RPS_market` with per-slice n and bootstrap CIs, plus the aggregate gap, plus reliability curves (model and market) overlaid.
4. **Honesty tripwire:** if `RPS_model < RPS_market` in aggregate, treat it as too-good. Audit for leakage (odds-covered-subset selection bias, cutoff alignment between the fit and the close timestamp) before believing it.

**Gate G1 (user decision — STOP):** present the table. The user selects which of Phases 2–5 run and in what order. Default recommendation to offer: if the aggregate gap is < ~0.005 RPS, run only Phase 2a/2b + Phase 0 maintenance and skip the rest; if ≥ ~0.01, Phase 3 is the priority and its data work should start immediately in parallel with Phase 2.

---

## Phase 2 — Cheap wins from data already in the store

Each item independently: short spec → implementation behind a config flag → sweep → held-out RPS gate → adopt or record no-lift. Order: 2a, 2b, 2c; 2d is a stretch.

### 2a. Altitude covariate (the one disabled-but-untested covariate worth testing)

- The covariate pipeline (`CovariateTransform`) already exists; the recorded no-lift result was rest_days, not altitude. martj42 carries venue city — build a small **hand-curated** city→elevation table (sources recorded in `SOURCES.md`; deterministic, no geocoding API) covering CONMEBOL qualifier venues (La Paz ~3,640m, Quito ~2,850m, Bogotá ~2,640m, …), other high venues encountered in the panel, and the 2026 venues (Mexico City ~2,240m, Guadalajara ~1,570m; everything else effectively lowland).
- **Mechanism honesty:** the cleanly fittable effect is the *acclimatized-home* advantage — a high-altitude home side vs a lowland visitor (the CONMEBOL natural experiment). For two lowland teams meeting at altitude the effect is ambiguous; test a symmetric goal-rate term separately and expect possible no-lift there. Suggested form: covariate = f(venue_alt − visiting team's accustomed alt), accustomed alt from a tiny country→base-city table (Bolivia/Ecuador/Colombia/Mexico + lowland default).
- **Pitfall:** the Elo history already grants +100 home advantage on those non-neutral qualifier matches, and the DC model has its own `home_adv`. The altitude term must measure the *increment beyond* standard home advantage — be explicit in the spec about the baseline.
- Gate: held-out RPS on a CONMEBOL-qualifier slice AND no regression overall. 2026 application if adopted: mostly Mexico at Estadio Azteca/Akron (acclimatized host) — which interacts with 2b.

### 2b. Host-effect calibration (`host_k = 0.5` is an assumption, not an estimate)

- Sample: all historical matches in finals tiers (`wc_finals`, continental finals) where venue country == team country (martj42 `country` + `neutral` columns; pool WC + Euro + Copa + AFCON hosts for n).
- Estimate host overperformance as the residual vs Elo expectation, converted into home-advantage units → an empirical `host_k` ± CI. **Pitfall (same as 2a):** be explicit about whether the Elo expectation baseline already includes the +100 home term for these matches (source data marks host games non-neutral), and about how the model's `(host_k·home_adv, 0)` term compares to the neutral `(0.5·ha, 0.5·ha)` environment — measure the increment in the units the model actually uses.
- Literature and history suggest hosts overperform by roughly a full home advantage or more, so expect the estimate to *raise* `host_k`; that legitimately bumps USA/Mexico/Canada and the champion board. Report the sensitivity (champion/advance deltas at old vs new `host_k`). Small-n honesty: report the CI, and if it comfortably includes 0.5, record no-change.

### 2c. Tier weights in the likelihood (friendlies are noisy strength measurements)

- Currently the likelihood weight is time-decay only. Add a multiplicative per-tier importance weight: `w = decay × tier_w[tier]`, config block `model.likelihood_tier_weights`, all-1.0 = byte-identical off-state. Sweep `tier_w[friendly] ∈ {0.4, 0.6, 0.8, 1.0}` first (others fixed at 1.0); optionally test a friendly-specific intercept offset `δ_f` on μ (friendlies may have a different base goal rate).
- Gate: held-out RPS scored on **non-friendly** matches (tournament prediction is what we care about). Watch the interaction with decay — both downweight old friendlies; the marginal value is recent friendlies, so a null result is plausible. Record it honestly if so.

### 2d. (Stretch) Dead-rubber flag

- Matchday-3 group games where one/both teams' fates are settled behave differently and feed GD tiebreakers in the sim. Reconstructing this requires inferring historical group assignments (within a tournament edition, group-stage matches form near-cliques in the match graph — connected components on early-matchday subgraphs). Fiddly; only attempt if 2a–2c are done and time permits. Downweight flagged matches; same gate as 2c.

**Checkpoint C2:** one report per item with the sweep table and verdict; adopted items get the bundle regenerated and the system doc's decision log updated.

---

## Phase 3 — Squad-strength anchor (the big lever; ship before the Round of 32)

**Why this is the priority lever:** the residual model–market gap is mostly *information asymmetry* — the market knows the 26 names, the model knows team labels. A second anchor term is the one structural change that adds information rather than reshaping what's already there.

### Gate G3 — mandatory user sign-off BEFORE any code (STOP)

Present the invariant question: invariant #4 says betting odds never feed the model. Transfermarkt market values are crowd judgments, not betting odds — arguably compliant with the letter, but they import aggregated human opinion. Options to present: **(a)** Transfermarkt values (richest signal, most "opinion-like"), **(b)** club-Elo aggregates from clubelo.com (results-derived like our own Elo, philosophically cleanest, but Europe-only coverage hurts CONCACAF/AFC/CAF squads), **(c)** abstain. Do not proceed without an explicit choice.

### Spec (write it in `docs/superpowers/specs/`, match the house format)

1. **Data contract.** A bitemporal player table: `{player_id, name, national_team, club, value_eur | club_elo, valid_as_of (valuation date), observed_at (ingest time)}` in the store. Plus squad-list tables: historical tournament squads (WC 2014/2018/2022, Euros 2016/2020/2024 — multiple public datasets exist; record provenance in `SOURCES.md`) and the announced final 2026 squads for the 48 teams (a hand-curated CSV with sources is acceptable for production).
2. **Sources.** Option (a): the maintained Transfermarkt Kaggle mirror (e.g. `davidcariboo/player-scores`) carries valuations **with dates** — that's what makes the point-in-time story work; verify recency and license at ingest. Option (b): clubelo.com's free historical API (daily club ratings) joined through each squad player's club.
3. **Name joining:** squad-list names → player table via exact match plus a small **explicit alias map** (house precedent from the odds↔model team aliases). **Never fuzzy-match.** Unmatched players → logged coverage gap, never imputed.
4. **`squad_z` construction:** per team at cutoff, take the most recent squad knowable at that cutoff; per player take `log(value_eur)` (heavy right tail) or club Elo, valued as-of strictly before the cutoff; aggregate = mean of the top-18 players (or minutes-weighted if minutes are cleanly available); z-score across covered teams. Coverage handling: anchor mean becomes `k1·elo_z + k2·squad_z·has_squad[t]` — uncovered teams keep the pure-Elo anchor rather than receiving an implicit "average squad," since coverage correlates with strength. Document this choice in the spec.
5. **Model:** `att[t] ~ Normal(k1·elo_z + k2·squad_z·has_squad, σ_att)` and same for `def`. Config: extend `model.strength_prior` with `k_squad` (default 0.0 = byte-identical to today). Mirror exactly in the sim's `RateBook` (the sim-must-mirror-predict invariant; the existing test pattern should catch a divergence — verify it does).
6. **Leakage canaries with positive controls:** a valuation/squad change observed after the cutoff must be inert; the same change observed before the cutoff must move the fit.

### Calibration & validation

- Sweep `k_squad ∈ {0.0, 0.2, 0.4, 0.6}` at `k_elo = 0.6`, scored by held-out RPS **on tournament matches** at cutoffs set just before past tournaments (squads known, matches unseen) — extend `scripts/sweep_strength_k.py`. Then a coarse joint check on `(k_elo, k_squad)` around the winner. Adopt at the knee, exactly like the k=0.6 decision.
- **Anti-over-anchoring gate** (house precedent): production sanity favorites should land in sensible bands; any >95% match favorite or absurd ordering = stop and diagnose.
- **v0 fallback** if the full pipeline can't ship before the R32: a hand-built `squad_z` for the 48 qualified teams only (e.g. club-Elo mean of the announced squads), behind the same config knob, validated by the same sweep on whatever historical squads were easiest to assemble. Better a crude validated v0 in production for the knockouts than a perfect pipeline that misses the tournament.

**Checkpoint C3:** sweep table, before/after champion board, canary results → pause for cross-model review before merge.

---

## Phase 4 — Scoreline-distribution quality (the "what will the final score be" phase)

Strict order: diagnose → sensitivity → only then implement. This phase is allowed to terminate early with a no-lift record.

1. **4a Tail diagnostic** (`scripts/diagnose_tails.py`): using walk-forward predictions on historical matches, bucket by |Elo gap| and compare predicted vs realized tail masses — P(favorite scores ≥4), P(|GD| ≥ 3), P(≥5 total goals) — per bucket. The concern: Poisson tails are typically too thin for blowouts, and the 48-team field is the most mismatch-heavy WC ever.
2. **4b Sensitivity (the go/no-go):** perturb the current production grids with a mean-preserving tail-fattening transform sized by the 4a misfit; rerun the group/advance sim; compare advance, third-place-best-8, and champion deltas against Monte-Carlo SE (20k sims → SE ≈ 0.2–0.35pp on champion probs). If deltas < ~2×SE, **record no-lift and skip 4c** — thin tails would be cosmetic, since GD tiebreakers are the only place grid shape matters downstream.
3. **4c (conditional) Implementation options**, behind `model.likelihood` / `model.widening`, spec decides: (i) per-match gamma frailty multiplier on rates (overdispersion, easy in PyMC), (ii) extend mechanism-(c) widening keyed on Elo gap (mismatch-conditional inflation — smallest change), (iii) a negative-binomial likelihood variant (note the DC low-score correction is defined on Poisson; an NB hybrid is nonstandard — spec must address it). Gate: held-out tail calibration improves AND 1X2 RPS does not regress.
4. **4d Draw calibration:** reliability of P(draw) by |Elo gap| decile; summarize the ρ posterior. If draws are systematically mis-predicted, the knobs are `rho_scale` (cheap) or gap-dependent ρ (stretch); held-out gate as always.
5. **4e (Stretch, behind `model.xg_blend`) xG-informed likelihood** on StatsBomb-covered matches only — goals are a noisy label and coverage happens to be densest exactly on recent WCs/Euros. Spec decides the form (auxiliary observation `xG ~ Normal(λ, σ_xg)` on covered matches vs a blended target); coverage-gated, never imputed, off-state byte-identical.

---

## Phase 5 — Inference upgrade (zero new data; plausibly real calibration gains)

- Mean-field ADVI systematically underestimates posterior variance and can misplace correlated posteriors — with 336 teams plus anchor terms, that's not hypothetical. On the *same* model: try `fullrank_advi` (note O(d²) cost at ~700+ latent dims — may be slow; measure) and NUTS via nutpie or numpyro/JAX. Compare: held-out RPS, reliability curves, sampler diagnostics, wall-clock (the daily loop must stay runnable — a 6-hour fit fails ops even if it wins on RPS).
- **Re-ablate widening:** mechanism-(c) was tuned against the mean-field posterior; if the new posterior is wider, widening may double-count — rerun the widening on/off comparison under the new backend.
- Adopt only on lift; config `model.inference.backend` selects; document either way. Only if reliability curves *still* show systematic miscalibration afterward, consider a post-hoc temperature layer with properly nested validation (do not tune temperature on the evaluation set).

---

## Per-phase acceptance checklist (every phase, no exceptions)

- [ ] Spec + plan committed in `docs/superpowers/` before implementation
- [ ] RED→GREEN tests for every change; new data sources have leakage canaries **with positive controls**
- [ ] Full pytest suite green (~630, incl. all 44 existing canaries); vitest/e2e green if anything user-facing moved
- [ ] Config-gated; off-state byte-identical (asserted by test, house pattern)
- [ ] Report in `reports/` with the numbers and an explicit **ADOPTED / NO-LIFT** verdict
- [ ] On adoption: production bundle regenerated, system document + decision log (§10-style) updated, "Last updated" bumped
- [ ] Checkpoint summary posted; load-bearing diffs flagged **"ready for cross-model review"**; wait for the user

## Timeline at a glance

| Window | Work |
|---|---|
| Jun 9–10 | **Phase 0** — must finish before kickoff Jun 11 |
| Jun 10–12 | **Phase 1** + Gate G1 (user picks priorities) |
| Jun 12–18 | **Phase 2** (2a, 2b, 2c; 2d stretch) |
| Jun 12–26 | **Phase 3** — Gate G3 first; data work in parallel; **must ship (or v0-ship) before R32 ~Jun 28** |
| Jun 18–30 | **Phase 4** (diagnostic-first; may legitimately end at 4b) |
| Any time, offline | **Phase 5** |

Throughout the group stage, the daily loop from Phase 0 runs after every matchday — that incoming data is the highest-information signal the model will ever get, and keeping the bundle current is worth more than any single feature above.
