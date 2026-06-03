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
_TBD — Task 2._

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
