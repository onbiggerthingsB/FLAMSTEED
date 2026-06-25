# Favorite-band reliability — 2026-06-25

Read-only diagnostic of the FROZEN model. Predicted vs realized by favorite-probability band, on leakage-safe held-out data.

## historical_pool  (n_scored=1473)

| band | n | pred favwin | real favwin | pred draw | real draw | mean RPS | pred P(m>=3) | real P(m>=3) | flag |
|---|---|---|---|---|---|---|---|---|---|
| 0.55-0.65 | 250 | 0.601 | 0.592 | 0.241 | 0.260 | 0.183 | 0.195 | 0.196 |  |
| 0.65-0.75 | 196 | 0.702 | 0.740 | 0.197 | 0.179 | 0.133 | 0.271 | 0.270 |  |
| 0.75-0.85 | 185 | 0.799 | 0.838 | 0.144 | 0.119 | 0.089 | 0.381 | 0.324 |  |
| 0.85+ | 169 | 0.915 | 0.935 | 0.066 | 0.041 | 0.041 | 0.625 | 0.538 |  |
| all | 800 | 0.738 | 0.757 | 0.171 | 0.161 | 0.119 | 0.347 | 0.316 |  |

## Phase-2 gate verdict (historical pool, n=800 favorites / 1473 scored)

**VERDICT: SHIP NOTHING for favorite-band calibration. The historical pool REFUTES systematic favorite-overconfidence.**

- **No band is statistically miscalibrated** — predicted favorite-win is within the realized ±1.96·SE band in all four bands and the aggregate (zero `MISCALIBRATED` flags).
- **The frozen model is well-calibrated to slightly UNDER-confident on favorites.** Realized favorite-win EXCEEDS predicted in every band: 0.65-0.75 → 0.740 vs 0.702; 0.75-0.85 → 0.838 vs 0.799; 0.85+ → 0.935 vs 0.915; all → 0.757 vs 0.738. Favorites won *more* than the model said — the **opposite** of the live 2026 symptom.
- **Draws are well-calibrated to slightly OVER-predicted in mismatches** (0.75-0.85 → pred 0.144 vs real 0.119; 0.85+ → pred 0.066 vs real 0.041) — again opposite to "too few draws."
- **The one real (modest) signal: blowout-tail OVER-prediction in heavy mismatches** (0.75-0.85 → pred P(m≥3) 0.381 vs real 0.324; 0.85+ → 0.625 vs 0.538), ~6–9pp. Consistent with the known P4 tail finding; a *separate* concern from favorite-band calibration.

**Implication.** On 1473 leakage-safe held-out matches (WC-2022 + Euro-2024 + rolling pre-2026 internationals), the live 2026 group-stage favorite underperformance looks like **small-sample variance** (72 group matches), NOT a systematic model bias. Building the J calibration layer or G/K dispersion to "fix favorite overconfidence" would correct a bias that does not exist out-of-sample, and would likely DEGRADE the model (pushing an already slightly-under-confident favorite estimate further down). **Do NOT proceed to Phase 2 for favorite-overconfidence.** The diagnostic-first gate did its job.

**2026 population:** the per-matchday walk-forward (14 fits) was stopped for time. On ~54 matches it could not establish a 2026-specific systematic bias distinguishable from noise; the historical pool (n=1473) is the decisive evidence and it is clean. The only residual lever worth tracking is modest P4 blowout-tail over-prediction (existing P4a/4b tail diagnostic) — not a favorite-band calibrator.

_Branch `feat/accuracy-jgk-calibration`; FROZEN model unchanged; nothing merged._