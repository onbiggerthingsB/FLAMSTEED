# Are the model's disagreements with the market signal or noise?

## INCONCLUSIVE

H2 (pre-committed, formed on the 217-fixture eval pool): the model's deviations from the market are NOISE, so its deficit widens with disagreement. H2 predicts a NEGATIVE gap.

- fixtures scored: **244**  (excluded as decided past 90': 15)
- gap (|disagreement| ≥ 10% minus < 4%): **-0.02365**  95% CI [-0.05766, +0.01032]
- one-sided p against the pre-committed direction: 0.0824

delta = RPS(book) − RPS(model); negative means the market won.

| disagreement band | n | mean delta | 95% CI | model wins |
|---|---|---|---|---|
| model much lower | 28 | -0.01677 | [-0.06295, +0.03059] | 39% |
| model lower | 44 | +0.00157 | [-0.01502, +0.01842] | 43% |
| agree (±4%) | 82 | +0.00248 | [-0.00154, +0.00668] | 54% |
| model higher | 63 | -0.00531 | [-0.01416, +0.00344] | 54% |
| model much higher | 27 | -0.02574 | [-0.07488, +0.01799] | 52% |

### Noise or bias?

Both tails losing means the deviations are VARIANCE (shrink the model). One tail losing means a BIAS, which is correctable and a different fix entirely.

- model much LOWER than market  (n=28): -0.01677
- model much HIGHER than market (n=27): -0.02574

- difference between tails: -0.00897 95% CI [-0.07627, +0.05560] → **no detectable asymmetry (consistent with variance)**

Eval-pool figures this was formed on, for comparison: much lower −0.0205, agree −0.0036, much higher −0.0297. The direction and rough magnitude replicate; the certification does not.

### Why INCONCLUSIVE — power, not absence of signal

- per-fixture SD: **0.1272** in the extreme bands vs **0.0192** when the two agree — roughly 7× the variance.
  That spread IS the finding's own subject matter: when the model departs from the market the result is wildly variable, big wins and big losses, which is what makes the mean so hard to pin down.
- at the observed effect (-0.02365) and that spread, 80% power needs ~**183 fixtures per group**; the extreme bands are only 23% of fixtures, so ~**811 total**.
- we have 244. This is an underpowered test of a real-looking effect, not evidence the effect is absent.
