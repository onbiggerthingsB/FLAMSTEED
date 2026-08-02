# H2 — are the model's disagreements signal or noise?

## DIRECTION REPLICATED, CLEARS THE BAR — BUT NOT CERTIFIED

> **Why this is not a certification, despite clearing the bar.**
> The first run of this test used an internally inconsistent rule: it reported a 5% tail beside a 97.5th-percentile gate. Under it H2 narrowly MISSED. The rule was then corrected to a single one-sided α — which is the defensible construction, and would have been the right choice from the start — but it was chosen AFTER the near-miss was visible. Adopting a rule that turns a miss into a pass, once the data are seen, is precisely the move that invalidates a test.
>
> So the numbers below are a repaired ESTIMATE, not a passed test. The interval also only barely excludes zero. H2 stays UNCERTIFIED until an independent sample decides it under a rule fixed in advance.

H2 predicts a NEGATIVE gap: the deficit widens with disagreement. delta = RPS(book) − RPS(model); negative means the market won.

### Population

- dev-slate fixtures **259**, knockout excluded **40**, admitted **219**

### Result

- gap (|disagreement| ≥ 10% minus < 4%): **-0.02533**
- 90% block-bootstrap CI (dual to the one-sided α=0.05 test): [-0.04523, -0.00430]
- one-sided null-centred p: **0.0244**
- blocks: 67 pool × matchday, of which 21 contain BOTH groups and are drawn whole

The interval is two-sided at 1−2α, which is the interval DUAL to a one-sided α test, so significance and interval-exclusion cannot disagree. The previous version paired a 5% tail with a 97.5th-percentile gate and reported an exclusion that a higher-precision run put on the other side of zero.

| disagreement band | n | mean delta | CI | model wins |
|---|---|---|---|---|
| model much lower | 23 | -0.01787 | [-0.05515, +0.02095] | 43% |
| model lower | 38 | +0.00355 | [-0.01020, +0.01652] | 45% |
| agree (±4%) | 71 | +0.00205 | [-0.00146, +0.00566] | 51% |
| model higher | 61 | -0.00455 | [-0.01237, +0.00298] | 54% |
| model much higher | 26 | -0.02805 | [-0.06721, +0.00991] | 50% |

### Noise or bias?

- model much LOWER than market (n=23): -0.01787
- model much HIGHER than market (n=26): -0.02805
- difference between tails: -0.01018 [-0.08918, +0.07504], p 0.8137 (two-sided)

**No asymmetry detected.** This is NOT evidence of symmetry: the interval is far too wide to exclude a meaningful bias, and bias and variance can coexist. It means the data cannot separate them.

### What would it take to see this? (sensitivity grid)

Detection rate at the CURRENT sample and block structure for each effect size. This grid is POST-HOC — chosen while writing the repair, with the estimate already known — so read it as design guidance, not as evidence about which effect is real. It is still preferable to the withdrawn ~811-fixture figure, which plugged the observed noisy estimate into an iid power formula and then treated the answer as evidence the effect was real.

| effect | detected |
|---|---|
| -0.010 | 8% |
| -0.020 | 23% |
| -0.030 | 55% |
| -0.050 | 95% |
