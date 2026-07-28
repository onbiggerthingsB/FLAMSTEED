# OA MDE analysis (2026-07-28, seed 0)

n=185; noise model: empirical k0.5-k0.6 paired diffs (sd=0.01334); gate: mean<=-0.002 AND support>=0.80 (block bootstrap, pool x matchday) — at this n the floor is the binding half, so the table below is the power of the floor alone (see 'Binding constraint').

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

Binding constraint: the mean<=-0.002 floor, NOT the support requirement. Across every delta above, 1804 simulated panels cleared the floor and 0 of them were then rejected by support>=0.80; the smallest support among floor-passers was 0.962, so support_req would have to exceed 0.962 before it rejected a single one. support>=0.80 only asks that the panel mean sit ~0.84 bootstrap standard errors below zero, which at n=185 the floor already implies with room to spare. Every power number in the table is therefore the power of the floor alone, and Task 7's prereg must state that at this n the support requirement is a sign/robustness check, not a second binding hurdle.

Reading: the smallest delta with power >= 0.80 is the MDE. Here the MDE (0.003) sits INSIDE the literature-plausible 0.002-0.004 band, not below it, so the pool resolves the top of the band but not the bottom: power is 0.98 at delta=0.004, 0.83 at 0.003, and 0.51 at 0.002 — a coin flip. Pre-committed consequence: a gate FAIL is evidence against effects >= ~0.004 but NOT against a true 0.002 effect, so a FAIL is DIRECTIONAL-ONLY / inconclusive rather than 'no effect' (spec: 'inconclusive' is a permitted outcome).
