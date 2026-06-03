# Phase 0 — Data-Acquisition Spike: Findings

**Status:** IN PROGRESS — research only, no spending, no accounts. Ends in a hard stop for approval.
**Date:** 2026-06-03
**Spec:** `docs/superpowers/specs/2026-06-03-worldcup-betting-model-design.md` (§6)

> ⛔ **Constraints honored in producing this report:** public documentation only; no accounts, keys, ToS click-through, payment, or volume scraping; no code or installs.

**Citation key:** every fact is tagged `(source: URL; accessed YYYY-MM-DD; confidence: High|Med|Low)`. Facts that could not be confirmed from public docs are marked `UNVERIFIED — <what would confirm>` and are NOT asserted.

## 1. Executive summary
_TBD — written in Task 5._

## 2. Track A — Modeling libraries

### 2a. Comparison table

| Library | License | Last commit / latest release | Open issues | Stars | Dep weight | Fit | Primary sources |
|---|---|---|---|---|---|---|---|
| `penaltyblog` | MIT | Latest release: v1.11.0 (2026-06-02 per PyPI) | 0 | 169 | Light (pure-Python + Cython, custom MCMC; no heavy probabilistic-programming dep since v1.8.0) | **ADOPT** — Dixon-Coles, Bivariate-Poisson, and Hierarchical Bayesian goal models built-in; Bayesian layer runs its own Cythonized MCMC sampler | (source: https://pypi.org/project/penaltyblog/; accessed 2026-06-03; confidence: High) · (source: https://github.com/martineastwood/penaltyblog; accessed 2026-06-03; confidence: High) |
| `soccerdata` | Apache-2.0 | Latest release: v1.9.0 (2026-04-12 per PyPI) | 30 | 1.7 k | Medium (Selenium/Playwright for some backends) | **ADOPT with caution** — 8 backends documented (ClubElo, ESPN, FBref, Football-Data.co.uk, Sofascore, SoFIFA, Understat, WhoScored); scraping-ToS risk flagged by maintainers | (source: https://pypi.org/project/soccerdata/; accessed 2026-06-03; confidence: High) · (source: https://github.com/probberechts/soccerdata; accessed 2026-06-03; confidence: High) |
| `socceraction` / SPADL | MIT | Latest release: v1.5.3 (2024-08-15 per PyPI); last GitHub release same date | 21 | 778 | Medium (pandas, numpy, optional xgboost/kloppy) | **DEFER** — xT/VAEP are event-level player-valuation metrics; not needed for a scoreline/odds model unless set-piece or shot features are required | (source: https://pypi.org/project/socceraction/; accessed 2026-06-03; confidence: High) · (source: https://github.com/ML-KULeuven/socceraction; accessed 2026-06-03; confidence: High) |
| `kloppy` | BSD-3-Clause | Latest release: v3.18.0 (2025-10-23 per PyPI); releases every ~2-3 months | 54 | 522 | Medium (16+ provider serializers) | **DEFER** — event/tracking-data IO standardization layer; relevant only if raw StatsBomb or proprietary event feeds are used in Phase 2+ | (source: https://pypi.org/project/kloppy/; accessed 2026-06-03; confidence: High) · (source: https://github.com/PySport/kloppy; accessed 2026-06-03; confidence: High) |
| `mplsoccer` | MIT | Latest release: v1.6.1 (UNVERIFIED — PyPI version page failed to load; last-commit date not accessible from public docs; GitHub has no releases) | 15 | 517 | Light (matplotlib + seaborn) | **ADOPT** — pitch/radar visualizations; reporting and diagnostics only; no inference role | (source: https://pypi.org/project/mplsoccer/1.6.1 — partial load; accessed 2026-06-03; confidence: Med) · (source: https://mplsoccer.readthedocs.io/en/latest/; accessed 2026-06-03; confidence: High) |
| `PyMC` (+ `pymc-extras`) | Apache-2.0 | PyMC v6.0.1 (2026-05-20); pymc-extras v0.11.0 (2026-05-14) | PyMC: 307 open; pymc-extras: 104 open | PyMC: 9.6 k | Heavy (PyTensor, Aesara/JAX backend, optional nutpie/blackjax/numpyro) | **ADOPT (primary inference)** — NUTS confirmed; ADVI confirmed in stable API; Pathfinder confirmed in `pymc-extras` v0.11.0 | (source: https://pypi.org/project/pymc/; accessed 2026-06-03; confidence: High) · (source: https://pypi.org/project/pymc-extras/; accessed 2026-06-03; confidence: High) · (source: https://www.pymc.io/projects/docs/en/stable/api/vi.html; accessed 2026-06-03; confidence: High) · (source: https://www.pymc.io/projects/extras/en/stable/generated/pymc_extras.inference.fit_pathfinder.html; accessed 2026-06-03; confidence: High) |
| `cmdstanpy` / Stan | BSD-3-Clause | cmdstanpy v1.3.0 (2024-10-20 per PyPI) | 26 | 198 | Heavy (requires separate CmdStan binary install; ~2 GB) | **FALLBACK/ALTERNATIVE** — NUTS (`sample()`), ADVI (`variational()`), and Pathfinder (`pathfinder()`) all confirmed in API; Python interop cost is higher (file-based I/O, subprocess) | (source: https://pypi.org/project/cmdstanpy/; accessed 2026-06-03; confidence: High) · (source: https://mc-stan.org/cmdstanpy/api.html; accessed 2026-06-03; confidence: High) · (source: https://mc-stan.org/cmdstanpy/users-guide/examples/Pathfinder.html; accessed 2026-06-03; confidence: High) |

### 2b. Per-library notes

**1. `penaltyblog` (MIT, v1.11.0, 2026-06-02)**
Provides Poisson, Dixon-Coles, Bivariate-Poisson, and Hierarchical Bayesian goal models out of the box, optimized with Cython for performance (source: https://github.com/martineastwood/penaltyblog; accessed 2026-06-03; confidence: High). Bayesian models migrated away from PyMC in v1.0.0 (2024-12-12) and were rewritten in Stan at that point; v1.1.0 (2025-03-15) then explicitly removed Stan-based models ("Temporarily removed Stan-based models due to dependency management challenges"), and v1.8.0 (2026-01-08) introduced a replacement Bayesian layer using a custom Cythonized MCMC sampler — meaning it is **not PyMC/Stan and does not expose ADVI or Pathfinder** (source: https://penaltyblog.readthedocs.io/en/latest/changelog/index.html; accessed 2026-06-03; confidence: High). Suitable as the primary Dixon-Coles / Bivariate-Poisson starting point for MLE and custom-MCMC fits; complement with PyMC for full Bayesian walk-forward backtesting requiring ADVI/Pathfinder.

**2. `soccerdata` (Apache-2.0, v1.9.0, 2026-04-12)**
Unified Pandas scraper for 8 sources: ClubElo, ESPN, FBref, Football-Data.co.uk (MatchHistory), Sofascore, SoFIFA, Understat, WhoScored (source: https://github.com/probberechts/soccerdata; accessed 2026-06-03; confidence: High). The FAQ states: "Even though web scraping is ubiquitous, its legal status remains unclear" (source: https://soccerdata.readthedocs.io/en/latest/faq.html; accessed 2026-06-03; confidence: High). Fragility risk (scraper breakage when upstream sites change) is an inherent property of the scraping architecture, not a separately quoted warning on the FAQ page. FiveThirtyEight and FotMob scrapers were removed in v1.9.0. Use FBref and Football-Data.co.uk backends only; do not rely on WhoScored or Sofascore without legal review.

**3. `socceraction` / SPADL (MIT, v1.5.3, 2024-08-15)**
Converts event-stream data (StatsBomb, Opta, Wyscout, Stats Perform, WhoScored) to the SPADL format and values actions via xT and VAEP frameworks (source: https://pypi.org/project/socceraction/; accessed 2026-06-03; confidence: High). Last release over 9 months ago (as of 2026-06-03). Relevant only if event-level features (e.g., set-piece xT, shot placement) are needed; not required for a pure scoreline model.

**4. `kloppy` (BSD-3-Clause, v3.18.0, 2025-10-23)**
Vendor-independent data model standardizing 16+ event and tracking-data providers (source: https://pypi.org/project/kloppy/; accessed 2026-06-03; confidence: High). Strong maintenance cadence (~every 2-3 months). Not needed for Phase 1 (scoreline model from aggregated match data); revisit in Phase 2+ if raw event feeds are incorporated.

**5. `mplsoccer` (MIT, v1.6.1, last-commit date UNVERIFIED)**
Pitch, radar, and heatmap visualizations for Matplotlib; lightweight dependency on matplotlib and seaborn (source: https://mplsoccer.readthedocs.io; accessed 2026-06-03; confidence: High). Has no GitHub releases published (only PyPI/conda-forge), so the "last commit" date for the repo is UNVERIFIED — would require inspecting the GitHub commit list directly. Fit is purely for reporting and diagnostic plots.

**6. `PyMC` v6.0.1 + `pymc-extras` v0.11.0 (both Apache-2.0)**
PyMC v6.0.1 released 2026-05-20 confirms NUTS, ADVI (pymc.ADVI, pymc.FullRankADVI, functional `pm.fit()`), and mini-batch ADVI in its stable API (source: https://www.pymc.io/projects/docs/en/stable/api/vi.html; accessed 2026-06-03; confidence: High). Pathfinder is delivered via `pymc-extras` (v0.11.0, 2026-05-14) as `pymc_extras.inference.fit_pathfinder()`; the v0.10.0 release notes include "Refactor Pathfinder for larger models" and v0.11.0 confirms PyMC v6 compatibility (source: https://pypi.org/project/pymc-extras/; accessed 2026-06-03; confidence: High) (source: https://www.pymc.io/projects/extras/en/stable/generated/pymc_extras.inference.fit_pathfinder.html; accessed 2026-06-03; confidence: High). NUTS backend is selectable: `pymc`, `nutpie`, `blackjax`, `numpyro`. Nine-thousand-plus stars and 300+ open issues reflect a large, active community. Dep weight is heavy but manageable with a pinned conda/mamba environment.

**7. `cmdstanpy` v1.3.0 + CmdStan (BSD-3-Clause)**
Python wrapper around the CmdStan binary; exposes `CmdStanModel.sample()` (NUTS-HMC), `CmdStanModel.variational()` (ADVI), and `CmdStanModel.pathfinder()` (Pathfinder VI) in a unified API (source: https://mc-stan.org/cmdstanpy/api.html; accessed 2026-06-03; confidence: High). All three inference algorithms confirmed (source: https://mc-stan.org/cmdstanpy/users-guide/examples/Pathfinder.html; accessed 2026-06-03; confidence: High). Stan 2.37 released Sep 2025 with further Pathfinder memory improvements (source: https://blog.mc-stan.org/2025/09/02/release-of-cmdstan-2-37/; accessed 2026-06-03; confidence: High). The Python interop cost is non-trivial: models must be written in the Stan DSL (.stan files), data is passed via JSON/rdump file I/O, and CmdStan (~2 GB binary) must be installed separately.

### 2c. Recommended stack

**Phase 1–2 recommended stack:**

| Role | Package |
|---|---|
| Scoreline model likelihoods (DC, Bivariate-Poisson, MLE baseline) | `penaltyblog` |
| Match result and odds data ingestion | `soccerdata` (FBref + Football-Data.co.uk backends only) |
| Bayesian inference — fast approximate (ADVI, Pathfinder) + full NUTS | `PyMC` v6 + `pymc-extras` |
| Visualization / diagnostics | `mplsoccer` + `arviz` (bundled with PyMC) |

**Defer to Phase 2+:** `socceraction`, `kloppy` (only if event feeds are added).

**Do not adopt:** `cmdstanpy`/Stan as primary inference layer (see §2d).

### 2d. PyMC vs Stan — explicit call with evidence

**Decision: PyMC is the primary inference library.**

Evidence:

1. **ADVI availability.** PyMC v6.0.1 stable docs confirm `pymc.ADVI`, `pymc.FullRankADVI`, and functional `pm.fit()` in the stable API (source: https://www.pymc.io/projects/docs/en/stable/api/vi.html; accessed 2026-06-03; confidence: High). CmdStanPy also provides ADVI via `model.variational()` (source: https://mc-stan.org/cmdstanpy/api.html; accessed 2026-06-03; confidence: High). Both libraries confirm ADVI — no difference on this criterion.

2. **Pathfinder availability.** PyMC's Pathfinder is implemented in `pymc-extras` (`fit_pathfinder()`), released v0.11.0 on 2026-05-14 with stated PyMC v6 compatibility (source: https://pypi.org/project/pymc-extras/; accessed 2026-06-03; confidence: High) (source: https://www.pymc.io/projects/extras/en/stable/generated/pymc_extras.inference.fit_pathfinder.html; accessed 2026-06-03; confidence: High). CmdStanPy also provides Pathfinder via `model.pathfinder()`, fully documented for CmdStanPy v1.3.0 (source: https://mc-stan.org/cmdstanpy/users-guide/examples/Pathfinder.html; accessed 2026-06-03; confidence: High). Again, both libraries satisfy the Pathfinder requirement — no difference on this criterion alone.

3. **Python integration cost.** PyMC models are written entirely in Python (using the PyMC/PyTensor DSL inline), results are returned as `InferenceData` objects compatible with `arviz`, and the pipeline stays in one language. Stan requires model code in a separate `.stan` DSL file, data passed via file I/O or CmdStanPy dict wrappers, and a separate CmdStan binary (~2 GB) installed and managed. For a Python walk-forward backtesting loop this subprocess boundary adds friction and latency.

4. **Ecosystem coherence.** PyMC v6 + pymc-extras + arviz are an integrated family with shared release cadences and shared PyTensor compute graph. Multiple NUTS backends (nutpie, blackjax, numpyro) are selectable without model rewrites. penaltyblog's custom Cythonized MCMC is a complementary MLE/fast-MCMC layer; when we need full Bayesian inference we call PyMC directly.

5. **Note on expectation vs. evidence.** The expectation that "PyMC is primary for Python integration" is confirmed, not contradicted, by the evidence. Both PyMC and Stan now support ADVI and Pathfinder; PyMC's advantage is purely the zero-friction Python integration and the arviz diagnostics pipeline, not algorithm availability. If Stan DSL were already required for other reasons (e.g., existing .stan models), the calculus would change.

**Conclusion:** Adopt PyMC v6 + pymc-extras as the sole Bayesian inference layer. Stan/CmdStanPy is a viable fallback if PyMC ADVI/Pathfinder performance proves inadequate on large walk-forward backtests, but it is not adopted in Phases 1–2.

## 3. Track B — Odds APIs

### 3a. Rubric reminder

**GATING (disqualifying if either fails):**
- **(a)** Pinnacle and/or Betfair Exchange present
- **(b)** Timestamped **closing** snapshots near kickoff (not arbitrary pre-match odds)

**WEIGHTED:** (c) international / World Cup coverage; (d) markets — match (1X2, ideally Asian handicap) and outright/progression

**TIE-BREAKERS:** cost; snapshot granularity; Betfair depth (traded volume + back/lay)

---

### 3b. Scorecard table

| Feed | (a) Pinnacle/Betfair | (b) Closing snapshots | (c) Int'l/WC | (d) Markets | bet\_time + close? | Betfair depth | Cost | Gating result |
|---|---|---|---|---|---|---|---|---|
| **The Odds API** | **YES** — Pinnacle in EU region (`pinnacle`); Betfair Exchange in EU (`betfair_ex_eu`), UK (`betfair_ex_uk`) and AU (`betfair_ex_au`) regions, so a single `regions=eu` query returns both Pinnacle and Betfair Exchange | **YES** — `GET /v4/historical/sports/{sport}/odds` and `GET /v4/historical/sports/{sport}/events/{eventId}/odds`; snapshots from 2020-06-06 at 10-min intervals; 5-min intervals from 2022-09-01; walk-forward via `previous_timestamp` / `next_timestamp` fields | **YES** — `soccer_fifa_world_cup`, `soccer_fifa_world_cup_womens`, `soccer_fifa_world_cup_winner`, `soccer_conmebol_copa_america`, `soccer_uefa_european_championship`, `soccer_africa_cup_of_nations` confirmed in sports list | h2h (1X2) via `soccer_fifa_world_cup`; outrights/futures via the separate `soccer_fifa_world_cup_winner` key — both confirmed in the sports catalogue; spreads (handicap) "mainly available for US sports and bookmakers at this time" (Asian handicap not confirmed for soccer); lay odds auto-included via `h2h_lay` for Betfair Exchange | **YES** — querying `date=T_bet` and `date=T_close` for any event gives both snapshots; `previous_timestamp`/`next_timestamp` navigation enables time series | Betfair Exchange back and lay included via `h2h_lay` market key; `includeBetLimits` param exposes bet limits; traded volume NOT provided (Exchange order book back/lay only, not traded volume series) | Tiered paid plans required for historical endpoint; exact pricing is UNVERIFIED — the pricing page is JavaScript-rendered and did not load in any Wayback Machine snapshot examined; public docs confirm "This endpoint is only available on paid usage plans" | **PASSES** both gates |
| **SportsDataIO** | UNVERIFIED — "Betting Odds API" exists with "Historical Odds & Betting Lines" in Vault product; no public list of bookmakers found; Pinnacle and Betfair Exchange not confirmed or denied from public docs | UNVERIFIED — "all betting odds older than 30 days are stored in our Historical API data warehouse" per public docs, but snapshot granularity, timestamp format, and closing-line capture not documented publicly | UNVERIFIED — product pages reference "Available Sports & Leagues" and "Coverage Overview" but only UEFA Champions League access confirmed on free tier; WC/international coverage not confirmed | UNVERIFIED — "Betting Odds API" product exists but specific markets not listed in public docs | UNVERIFIED | UNVERIFIED | Enterprise / contact sales ("reach out to our sales team" per public docs) | **AT RISK** — gate (a) and gate (b) both UNVERIFIED; classified AT RISK |
| **OpticOdds** | Pinnacle **YES** — explicit "Pinnacle API" listed as a sportsbook API product; "200+ operators including onshore sportsbooks, DFS, sharp offshore sportsbooks"; Betfair Exchange UNVERIFIED (not explicitly named in public docs inspected) | Partially confirmed — Odds Screen product includes "Opening and closing line comparison" and "Price and bet point history"; API documentation is a JavaScript SPA that could not be fully rendered; closing snapshot availability via the API (not just the Odds Screen) is UNVERIFIED | UNVERIFIED — "Real-time odds…standardized across soccer, football, basketball, tennis, cricket" stated, but World Cup / international tournament coverage not specifically confirmed in public docs | "Full bet coverage: main lines, alternates, props, outrights"; soccer confirmed; Asian handicap not specifically mentioned | UNVERIFIED for API time-series; Odds Screen shows "historical CLV for up to two weeks" | UNVERIFIED — not confirmed whether traded volume is in the feed; back/lay format not mentioned | Enterprise / quote-based (multi-step form to get pricing, no public price) | **AT RISK** — gate (a) partial (Pinnacle confirmed, Betfair unverified); gate (b) unverified for API closing snapshots; classified AT RISK |
| **OddsJam** | UNVERIFIED — 100+ sportsbooks listed but bookmaker list not publicly enumerated; Pinnacle not confirmed; US-market focus (DraftKings, FanDuel, etc.) prominent in all marketing | UNVERIFIED — no historical odds API endpoint confirmed from public documentation; API described as "real-time betting odds…player props, alternate markets, injury data, schedules, ranking, scores" with no mention of historical/closing snapshots | UNVERIFIED — soccer listed as a supported sport; World Cup / international coverage not confirmed | Real-time main lines, alternate markets, props, futures; no Asian handicap specifically confirmed | UNVERIFIED | UNVERIFIED | Enterprise / contact sales; FAQ says "contact us to get started" for API pricing | **DISQUALIFIED (gating)** — gate (a) UNVERIFIED: no public confirmation of Pinnacle or Betfair; gate (b) UNVERIFIED: no historical/closing endpoint found in public docs |
| **Betfair Exchange Historical Data** | Betfair Exchange **YES** — this IS the Betfair Exchange data source; Pinnacle not applicable (Betfair Exchange is itself the sharp benchmark) | **YES** — compressed time-stamped `.bz2` price files capturing full order book at each market tick; pre-event data available; data used in production by multiple open-source football modelling projects | **YES** — Betfair Exchange covers all sports listed on the Exchange; FIFA World Cup 2018 modelling tutorial published by Betfair datascientists confirms WC football markets exist in historical archive | Match odds (1X2 Back/Lay), outrights/futures on Exchange; Asian handicap UNVERIFIED (Exchange runs Asian handicap markets but historical data coverage for soccer AH not confirmed in public docs) | **YES** — `.bz2` files contain full time series of order book states from market creation to settlement, enabling both bet-time and closing snapshots | **STRONGEST** — `batb` (Best Available To Back) and `batl` (Best Available To Lay) full price ladder; `trd` (traded volume per price point); `tv` (total volume traded); `ltp` (last traded price); `atb`/`atl` (full available back/lay depth) — all confirmed in Betfair ESA Swagger schema; "Available volume back, Available volume lay, Back-lay spread, Total volume traded" explicitly listed as extractable features by open-source implementations | UNVERIFIED — "purchase & download" model confirmed; exact pricing not found in public docs (historicdata.betfair.com is JavaScript-rendered; no public price list found in Wayback Machine snapshots); live Exchange API has £299 activation fee but the historical data service pricing is separate | **PASSES** both gates |
| **Football-Data.co.uk** | **YES (partial)** — Pinnacle closing odds present since 2012/13 (`PSCH`/`PSCD`/`PSCA` columns); closing odds for other bookmakers since 2019/20 (column names prefixed 'C'); Betfair Exchange not covered | **YES (partial, domestic leagues only)** — closing odds columns (`C` prefix) available since 2019/20 for all covered leagues; Pinnacle-specific closing odds back to 2012/13 | **NO** — covers 22 European domestic club league divisions plus 16 "extra leagues" (Argentina, Austria, Brazil, China, Denmark, Finland, Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden, Switzerland, USA); explicitly described as "premier divisions" and domestic club leagues; **no World Cup, no international tournaments** | Match odds 1X2; Asian handicap aggregate since 2005/06 (from Betbrain/OddsPortal average, not individual book); no outrights | YES (closing columns present), but only a single closing-line snapshot per match, not a time series | None — no exchange data | FREE (all data free since July 2007) | **DISQUALIFIED (gating)** — gate (c) fails: international/World Cup coverage confirmed absent; not a gating criterion itself, but as the task spec notes: Track D selection-bias feeds on this gap; for a World Cup betting model this is a terminal coverage gap |

**Sources for table:**
- The Odds API bookmakers: (source: https://web.archive.org/web/20241001000000/https://the-odds-api.com/sports-odds-data/bookmaker-apis.html; accessed 2026-06-03; confidence: High)
- The Odds API historical endpoint: (source: https://web.archive.org/web/20250101000000/https://the-odds-api.com/liveapi/guides/v4/; accessed 2026-06-03; confidence: High) — quotes: "Returns a snapshot of games with bookmaker odds for a given sport, region and market, at a given historical timestamp. Historical odds data is available from June 6th 2020, with snapshots taken at 10 minute intervals. From September 2022, historical odds snapshots are available at 5 minute intervals."
- The Odds API sports list (soccer_fifa_world_cup): (source: https://web.archive.org/web/20241001000000/https://the-odds-api.com/sports-odds-data/sports-apis.html; accessed 2026-06-03; confidence: High)
- The Odds API markets (spreads note): (source: https://web.archive.org/web/20250101000000/https://the-odds-api.com/liveapi/guides/v4/; accessed 2026-06-03; confidence: High) — quote: "spreads and totals markets are mainly available for US sports and bookmakers at this time"
- The Odds API Betfair lay odds: (source: https://web.archive.org/web/20250101000000/https://the-odds-api.com/liveapi/guides/v4/; accessed 2026-06-03; confidence: High) — quote: "Lay odds are automatically included with h2h results for relevant betting exchanges (Betfair, Matchbook etc). These have a h2h_lay market key."
- SportsDataIO soccer docs: (source: https://web.archive.org/web/20250101000000/https://sportsdata.io/developers/api-documentation/soccer; accessed 2026-06-03; confidence: Med) — "The SportsDataIO API Free Trial only provides access to the UEFA Champions League…all betting odds older than 30 days are stored in our Historical API data warehouse"
- OpticOdds homepage: (source: https://web.archive.org/web/20251001000000/https://opticodds.com/; accessed 2026-06-03; confidence: High) — "Pinnacle API" listed; "Real-time odds from 200+ sportsbooks"; "Opening and closing line comparison"
- OddsJam API page: (source: https://web.archive.org/web/20250101000000/https://oddsjam.com/odds-api; accessed 2026-06-03; confidence: High) — "real-time betting odds from 100+ sportsbooks"
- Betfair Exchange Historical Data service: (source: https://web.archive.org/web/20241001000000/https://developer.betfair.com/; accessed 2026-06-03; confidence: High) — quote: "The Betfair Historical Data service provides time-stamped Betfair Exchange data for purchase & download. This data should be used for analysis & test..."
- Betfair ESA Swagger schema (back/lay/volume fields): (source: https://raw.githubusercontent.com/betfair/stream-api-sample-code/master/ESASwaggerSchema.json; accessed 2026-06-03; confidence: High) — `RunnerChange.batb`: "Best Available To Back — LevelPriceVol triple delta"; `RunnerChange.batl`: "Best Available To Lay"; `RunnerChange.trd`: "Traded — PriceVol tuple delta"
- Betfair historical data extractable features (open-source confirmation): (source: https://github.com/williamdevena/Betfair_historical_data_exploration_and_analysis; accessed 2026-06-03; confidence: High) — "Available volume back, Available volume lay, Last traded price, Back-lay spread, Total volume traded"
- Betfair World Cup coverage: (source: https://raw.githubusercontent.com/betfair-datascientists/predictive-models/master/README.md; accessed 2026-06-03; confidence: High) — "FIFA World Cup 2018 Modelling Tutorial"
- Football-Data.co.uk data page: (source: https://web.archive.org/web/20250101000000/https://www.football-data.co.uk/data.php; accessed 2026-06-03; confidence: High) — quotes: "closing odds ('C' included the data column headings). Closing home-draw-away odds are also available for Pinnacle bookmaker only back to 2012/13"; "16 other worldwide premier divisions, with fulltime results and closing match odds (best and average market price, and Pinnacle odds) dating back to 2012/13"

---

### 3c. Disqualifications

**OddsJam — DISQUALIFIED (gating):** Fails gate (a): no public documentation confirms Pinnacle or Betfair Exchange coverage; API marketing focuses on US retail books (DraftKings, FanDuel). Fails gate (b): no historical/closing odds API endpoint is documented in any publicly accessible resource. Even if these features existed behind a paywall, they cannot be confirmed without an account, which is outside the constraints of this spike.

**Football-Data.co.uk — DISQUALIFIED (coverage):** Pinnacle closing odds are confirmed (gate a passes) and closing snapshots are confirmed (gate b passes), but coverage is restricted to domestic club leagues only. No World Cup, no international tournament matches are present in any confirmed data file. This is a terminal coverage gap for a World Cup model. The data remains valuable as a domestic backtest benchmark (noted in Track D).

**Note on SportsDataIO and OpticOdds (AT RISK):** Both are AT RISK rather than disqualified outright, because the gating properties could not be positively confirmed OR denied. SportsDataIO's bookmaker list is not publicly documented. OpticOdds' API closing-snapshot capability is only partially confirmed (Odds Screen feature only). Both would require account-level access to verify, which is outside this spike's constraints.

---

### 3d. Recommendation

**Recommended feed: The Odds API**

The Odds API is the only candidate that publicly and verifiably passes both gating criteria with citable evidence: Pinnacle is explicitly listed in the EU bookmakers region and Betfair Exchange is listed in the UK and AU regions; the historical endpoint `GET /v4/historical/sports/{sport}/odds` is documented to return timestamped snapshots at 5-minute intervals (from September 2022), with `previous_timestamp` and `next_timestamp` fields enabling full time-series traversal from any hypothetical bet-placement time to the closing snapshot just before kickoff. The `soccer_fifa_world_cup` sport key is explicitly listed in the sports catalogue, directly addressing the World Cup universe requirement. For the CLV benchmark, Pinnacle's `eu`-region closing line is the industry-standard sharp reference. Betfair Exchange lay odds are included automatically via the `h2h_lay` market key. The closing-vs-pre-match distinction is handled natively: querying the same event at `date=T_bet` returns the opening/pre-match snapshot, and querying at `date=T_close` (kickoff minus 1 minute) returns the closing line — both using the same endpoint with a single `date` parameter change. Both bet-time and close are directly available. The gap is that traded volume (for VWAP near close) is not provided by The Odds API; Betfair Exchange traded volume requires the Betfair Historical Data service as a supplement.

**Runner-up: Betfair Exchange Historical Data service**

Betfair Historical Data passes both gating criteria and is the strongest candidate for VWAP-near-close computation and full bid-ask spread analysis: it provides `batb`/`batl` (full price ladder), `trd` (traded volume per price level), and `tv` (total volume) in its `.bz2` time-stamped files. World Cup coverage is confirmed. It is the ideal data source for the Betfair "fair price" component of the CLV benchmark. It loses to The Odds API as primary feed because: (i) pricing is unverified (purchase model, no public price list found); (ii) data is in a compressed proprietary JSON-L format requiring a dedicated parsing pipeline; (iii) Pinnacle odds are not in this source — a Pinnacle closing line requires a separate feed; (iv) accessing the live Exchange API also requires a funded account with a £299 one-time activation fee, creating an onboarding dependency. The practical recommendation is to use The Odds API as the primary feed (Pinnacle closing line + Betfair back/lay) and pair it with the Betfair Historical Data service for the traded-volume VWAP component when budget permits. This pairing is a user decision flagged in §8.

---

### 3e. Open items and decisions needed

1. **The Odds API pricing** — UNVERIFIED from public docs. The pricing page is JavaScript-rendered and did not load in any archived snapshot. Plan tiers, historical data cost, and request quota caps must be confirmed before purchasing. UNVERIFIED — would confirm by loading https://the-odds-api.com/pricing.html in a logged-in browser after account creation.
2. **Betfair Historical Data pricing** — UNVERIFIED. "Purchase & download" model confirmed; exact per-market or per-sport cost not found in any public document. UNVERIFIED — would confirm at https://historicdata.betfair.com/ after creating a Betfair account.
3. **Asian handicap on soccer via The Odds API** — The docs say "spreads…mainly available for US sports and bookmakers at this time." Asian handicap for soccer specifically is UNVERIFIED. A fallback is the aggregate Asian handicap data from Football-Data.co.uk (but only for domestic leagues).
4. **Betfair Exchange Account dependency** — Both the live Exchange API (real-time betting) and the Historical Data service require a Betfair account. For backtest purposes, only the Historical Data service is needed and may not require a funded account (account creation is free). The £299 fee applies to live-API app keys. This needs user confirmation before any account creation.
5. **SportsDataIO and OpticOdds** — AT RISK. If The Odds API pricing is unacceptable, one of these may be viable. Recommend revisiting with account-level access in Phase 1 if needed.
6. **Per-bookmaker historical start date** — UNVERIFIED, and load-bearing for backtest depth. The Odds API docs warn that "bookmakers and sports will only be available in the historical odds API after the time that they were added to the regular odds API." The headline coverage start (2020-06-06) therefore need not apply to Pinnacle or Betfair Exchange specifically: their historical closing lines may begin later, which bounds the usable Pinnacle-CLV backtest window. UNVERIFIED — would confirm the dates `pinnacle` and `betfair_ex_*` were added to the regular API (vendor support or account-level historical probes in Phase 1).

## 4. Track C — Feature sources + bitemporal feasibility
_TBD — Task 3._

## 5. Track D — Historical-odds coverage & match universe
_TBD — Task 4._

## 6. Consolidated recommendation
_TBD — Task 5._

## 7. Costs & accounts appendix
_TBD — Task 5._

## 8. Decisions needed before Phase 1
_TBD — Task 5._

## 9. HARD STOP
_TBD — Task 5._

## 10. Sources log
_TBD — Task 6._
