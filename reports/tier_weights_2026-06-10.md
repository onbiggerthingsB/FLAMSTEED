# Phase 2c — Per-Tier Likelihood Weight — Held-out RPS Sweep

_Generated 2026-06-10. Cutoff 2024-06-01T00:00:00Z. OFFLINE (no Odds-API credits). Lockbox untouched._

**Knob:** `model.likelihood_tier_weights` multiplies each match's time-decay likelihood weight by a per-tier importance weight `w = decay × tier_w[tier]`. The sweep tunes `tier_w[friendly]` (every other tier fixed at 1.0); the friendly-intercept δ_f is DEFERRED (out of scope for this staging).

**Gate:** the objective is TOURNAMENT prediction, so the PRIMARY metric is held-out 1X2 RPS on NON-FRIENDLY matches only. All-matches RPS is a SECONDARY diagnostic. Comparisons are PAIRED on the identical non-friendly set vs the w=1.0 baseline.

- Held-out set: valid-played internationals with date > 2024-06-01 (non-friendly n=1670; all-matches n=2188).

## Paired held-out 1X2 RPS (lower = better; PAIRED on the non-friendly set)

| tier_w[friendly] | non-friendly RPS | paired Δ vs 1.0 | 95% CI | all-matches RPS |
|---|---|---|---|---|
| 1.0 | 0.33284 | — (ref) | — | 0.33492 |
| 0.8 | 0.33278 | -0.00006 | [-0.00036, +0.00024] | 0.33501 |
| 0.6 | 0.33278 | -0.00006 | [-0.00068, +0.00058] | 0.33520 |
| 0.4 | 0.33287 | +0.00003 | [-0.00096, +0.00105] | 0.33551 |

(Δ < 0 = the arm BEATS w=1.0 on the non-friendly slice. ADOPT requires the best arm's Δ < 0 AND the 95% upper bound < 0 — a strict paired-bootstrap win.)

## Verdict

**P2C VERDICT: NO-LIFT (no friendly weight strictly beats 1.0 beyond the paired CI)**

best candidate tier_w[friendly]=0.8 gave non-friendly Δ=-0.00006 95%CI[-0.00036,+0.00024] vs 1.0 — the interval includes (or sits above) zero. Consistent with the brief's warning that time-decay already downweights old friendlies, so the marginal value of re-weighting them is small. Leave `likelihood_tier_weights` off (a valid recorded outcome).
