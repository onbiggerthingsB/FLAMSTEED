# OA MDE analysis (2026-07-28, seed 0)

n=185; noise model: empirical k0.5-k0.6 paired diffs (sd=0.01334); gate: mean<=-0.002 AND support>=0.80 (block bootstrap, pool x matchday).

| true delta | power |
|---|---|
| 0.000 | 0.03 |
| 0.001 | 0.15 |
| 0.002 | 0.51 |
| 0.003 | 0.83 |
| 0.004 | 0.98 |
| 0.006 | 1.00 |
| 0.010 | 1.00 |

Reading: the smallest delta with power >= 0.8 is the MDE. If the literature-plausible 0.002-0.004 band sits below it, the development verdict is DIRECTIONAL-ONLY and the prereg must say so (spec: 'inconclusive' is a permitted outcome).
