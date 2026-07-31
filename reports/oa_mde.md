# OA MDE analysis (2026-07-28, seed 0)

n=185; noise model: empirical k0.5-k0.6 paired diffs (sd=0.01334); gate: mean<=-0.002 AND support>=0.80 (block bootstrap, pool x matchday).

SCOPE: every number below is a joint property of n=185 AND sd(noise)=0.01334, NOT of n alone. MDE = floor + z*sd(noise)/sqrt(n), and sd(noise) here is a CHOSEN arm contrast rather than a measured constant of the pool, so the MDE, the false-positive rate, and which half of the gate binds all move when the contrast changes — 'Noise-model sensitivity' below re-runs the whole grid under the other arms on this pool and shows them moving. Under the shipped contrast the floor is the binding half, so the table below is the power of the floor alone (see 'Binding constraint').

| true delta | power |
|---|---|
| 0.000 | 0.03 |
| 0.001 | 0.15 |
| 0.002 | 0.51 |
| 0.003 | 0.83 |
| 0.004 | 0.98 |
| 0.006 | 1.00 |
| 0.010 | 1.00 |

MDE (smallest delta with power >= 0.80): 0.003.

Common random numbers: every row above is simulated from the same seed, and each simulation draws its panel BEFORE the floor is tested, so simulation s at one delta is simulation s at any other delta shifted by the delta difference — same resampled noise, same bootstrap block draws. Floor-passing and support are therefore both nested across the grid, and the curve is monotone BY CONSTRUCTION. That is deliberate variance reduction (delta-to-delta comparisons carry no Monte-Carlo noise), but it makes the monotonicity arithmetic rather than a check: it would come out just as smooth if the machinery were wrong. Task 7's prereg must not cite the shape of this curve as evidence the machinery works — that evidence is tests/eval/test_power.py.

Binding constraint: the mean<=-0.002 floor, NOT the support requirement. Across every delta above, 1804 simulated panels cleared the floor and 0 of them were then rejected by support>=0.80; the smallest support among floor-passers was 0.962, so support_req would have to exceed 0.962 before it rejected a single one. support>=0.80 only asks that the panel mean sit ~0.84 bootstrap standard errors below zero, which at this n and this dispersion the floor already implies with room to spare. Every power number in the table is therefore the power of the floor alone. That is conditional on the noise model, not on n: on the more dispersed k0.4-vs-k0.6 contrast (sd=0.02972, only 2.2x the headline) measured on this SAME 185 pool, support>=0.80 DOES reject 4 floor-passers (min support 0.774) — and it is the tightest of 3 alternative contrasts that bind. Task 7's prereg must state the conditioned form — at n=185 AND sd(noise)=0.01334 the support requirement is a sign/robustness check rather than a second binding hurdle — not the unconditional claim.

Reading: the smallest delta with power >= 0.80 is the MDE. Here the MDE (0.003) sits INSIDE the literature-plausible 0.002-0.004 band, not below it, so the pool resolves the top of the band but not the bottom: power is 0.98 at delta=0.004, 0.83 at 0.003, and 0.51 at 0.002 — a coin flip. Pre-committed consequence, CONDITIONAL on n=185 AND sd(noise)=0.01334 (the k0.5-vs-k0.6 contrast): a gate FAIL is evidence against effects >= ~0.004 but NOT against a true 0.002 effect, so a FAIL is DIRECTIONAL-ONLY / inconclusive rather than 'no effect' (spec: 'inconclusive' is a permitted outcome). Every number in this paragraph moves with sd(noise), so Task 7's prereg must carry the conditioning and not just the numbers — see 'Noise-model sensitivity' for what they become under the other arms measured on this same pool.

## Noise-model sensitivity

Each row re-runs the WHOLE grid above with only the contrast swapped: identical 185 matches, identical block structure, same floor/support_req/seed 0/n_sims 400/n_boot 1000. Every arm was scored in the July B/K sweep (reports/bk_levers_2026-07-02.md) — no new scoring was run here.

| contrast (vs k0.6) | sd(noise) | MDE | power(0.000) | floor_pass | support_reject | min_support |
|---|---|---|---|---|---|---|
| k0.7 | 0.01014 | 0.003 | 0.00 | 1799 | 0 | 0.978 |
| k0.5 (headline) | 0.01334 | 0.003 | 0.03 | 1804 | 0 | 0.962 |
| k0.8 | 0.01774 | 0.004 | 0.05 | 1784 | 0 | 0.877 |
| k0.4 | 0.02972 | 0.004 | 0.16 | 1783 | 4 | 0.774 |
| nuts_k0.6 | 0.03252 | 0.004 | 0.21 | 1813 | 20 | 0.753 |
| k0.0 | 0.08044 | none in this grid | 0.20 | 1664 | 493 | 0.579 |

The shipped choice is not neutral: by dispersion it ranks 2 of 6 (1 = tightest), and the widest contrast (k0.0) is 6.0x more dispersed. Under k0.0 (sd=0.08044, peak power 0.7975) no delta in the grid reaches power 0.80 at all: that contrast cannot resolve the band, flipping the Reading above from a straddle to no resolution. Decisively, nuts_k0.6 vs k0.6 is the SAME configuration with k fixed at 0.6, differing only in inference backend (reports/bk_levers/bk_sweep.py) — pure sampler jitter — and it is already 2.4x more dispersed than the headline noise model. No real arm change (least of all a prediction-time market blend, which moves forecasts far more than a 0.1 k-nudge) can plausibly be as tight, so read the headline MDE as a LOWER BOUND on the detectable effect rather than an estimate of it.
