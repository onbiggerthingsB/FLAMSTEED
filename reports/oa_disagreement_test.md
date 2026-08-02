# H2 — are the model's disagreements signal or noise?

## DIRECTION REPLICATED, CLEARS THE BAR — BUT NOT CERTIFIED

> **Why this is not a certification, despite clearing the bar.**
> The first run of this test used an internally inconsistent rule: it reported a 5% tail beside a 97.5th-percentile gate. Under it H2 narrowly MISSED. The rule was then corrected to a single one-sided α — which is the defensible construction, and would have been the right choice from the start — but it was chosen AFTER the near-miss was visible. Adopting a rule that turns a miss into a pass, once the data are seen, is precisely the move that invalidates a test.
>
> So the numbers below are a repaired ESTIMATE, not a passed test. The interval also only barely excludes zero. H2 stays UNCERTIFIED until an independent sample decides it under a rule fixed in advance.

H2 predicts a NEGATIVE gap: the deficit widens with disagreement. delta = RPS(book) − RPS(model); negative means the market won.

### Population

- dev-slate fixtures **259**, knockout excluded **54**, admitted **205**

### Result

- gap (|disagreement| ≥ 10% minus < 4%): **-0.02556**
- 95% block-bootstrap CI: [-0.05185, -0.00032]
- one-sided null-centred p (α=0.05): **0.0286**
- blocks: 39 extreme, 45 agree

One α governs both the interval and the test. The earlier version reported a 5% tail beside a 97.5th-percentile gate — two different bars in one report.

| disagreement band | n | mean delta | CI | model wins |
|---|---|---|---|---|
| model much lower | 23 | -0.01787 | [-0.06594, +0.03012] | 43% |
| model lower | 36 | +0.00181 | [-0.01687, +0.02042] | 42% |
| agree (±4%) | 64 | +0.00229 | [-0.00233, +0.00705] | 52% |
| model higher | 56 | -0.00326 | [-0.01350, +0.00600] | 57% |
| model much higher | 26 | -0.02805 | [-0.07902, +0.01703] | 50% |

### Noise or bias?

- model much LOWER than market (n=23): -0.01787
- model much HIGHER than market (n=26): -0.02805
- difference between tails: -0.01018 [-0.07927, +0.05763], p 0.3835

**No asymmetry detected.** This is NOT evidence of symmetry: the interval is far too wide to exclude a meaningful bias, and bias and variance can coexist. It means the data cannot separate them.

### What would it take to see this? (design curve)

Detection probability at the CURRENT sample for effects declared in advance — not the observed estimate plugged into a power formula, which is what the withdrawn ~811-fixture figure did.

| true effect | detected |
|---|---|
| -0.010 | 0% |
| -0.020 | 0% |
| -0.030 | 25% |
| -0.050 | 98% |

Read it as design guidance, not as evidence about which effect is real.
