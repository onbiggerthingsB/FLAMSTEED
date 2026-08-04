# H1 — confederation hypothesis, out-of-sample on the dev slate

## FAILS TO REPLICATE (direction reversed)

H1 predicts a NEGATIVE gap (non-core loses more). Direction was pre-committed; a positive gap means it fails to replicate in that direction, which is NOT the same as refuting it.

> **On the reversal.** The gap points the opposite way to H1, and the one-sided tail in THAT direction is 0.9698. That is not a finding: the direction was not predicted in advance, so reading significance off it is the same post-hoc move H1 was supposed to test. What is supported is the narrow claim that H1 does not replicate — nothing about a reverse effect.

### Population

- dev-slate fixtures: **259**
- excluded as knockout (extra time possible, no verified 90' table for these competitions): **40**
- admitted (group/league only, so full time IS 90'): **219**

Exclusion is BY STAGE, decidable before kickoff. The earlier version excluded on `winner_override`, which is selection on the result and dropped exactly the fixtures whose 90' outcome was certain.

### Result

- gap (non-core − core): **+0.01307**
- 90% block-bootstrap CI (dual to the one-sided α=0.05 test): [+0.00149, +0.02463]
- one-sided null-centred p: **0.9698**
- blocks: 83 pool × matchday, of which 8 contain BOTH groups and are drawn whole

**Identification limit.** Confederation is nearly collinear with competition here: all 84 AFCON rows are non-core, all Nations League and World Cup qualification rows are core, and only Copa América contains both. The aggregate gap therefore cannot cleanly separate a confederation effect from a competition effect — no amount of resampling fixes that, and it is a limit of the sample, not of the estimator.

| group | n | RPS model | RPS book | book − model | CI |
|---|---|---|---|---|---|
| non-core | 106 | 0.1864 | 0.1879 | +0.00155 | [-0.00775, +0.01067] |
| core | 113 | 0.1981 | 0.1866 | -0.01152 | [-0.01830, -0.00488] |

### By competition

| tournament | n | book − model |
|---|---|---|
| African Cup of Nations | 86 | -0.00179 |
| Copa América | 30 | +0.01795 |
| FIFA World Cup qualification | 25 | -0.03795 |
| UEFA Nations League | 78 | -0.00734 |

### Held at fixed favourite strength

| favourite band | non-core mean (n) | core mean (n) |
|---|---|---|
| <40% | -0.00555 (11) | -0.00699 (27) |
| 40-50% | -0.00421 (25) | -0.01769 (24) |
| 50-60% | +0.01006 (25) | -0.02202 (18) |
| 60-75% | +0.00440 (35) | -0.01400 (29) |
| >75% | -0.00746 (10) | +0.00759 (15) |
