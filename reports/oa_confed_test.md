# H1 — confederation hypothesis, out-of-sample on the dev slate

## NOT SUPPORTED (direction reversed)

H1 predicts a NEGATIVE gap (non-core loses more). Direction was pre-committed; a positive gap refutes it and is not re-narrated.

> **On the reversal.** The gap points the opposite way to H1, and the tail in THAT direction is 0.0426. That is not a finding: the direction was not predicted in advance, so reading significance off it is the same post-hoc move H1 was supposed to test. What is supported is the narrow claim that H1 does not replicate — nothing about a reverse effect.

### Population

- dev-slate fixtures: **259**
- excluded as knockout (extra time possible, no verified 90' table for these competitions): **54**
- admitted (group/league only, so full time IS 90'): **205**

Exclusion is BY STAGE, decidable before kickoff. The earlier version excluded on `winner_override`, which is selection on the result and dropped exactly the fixtures whose 90' outcome was certain.

### Result

- gap (non-core − core): **+0.01357**
- 95% block-bootstrap CI: [-0.00178, +0.02884]
- one-sided null-centred p (α=0.05): **0.0426**
- blocks: 40 non-core, 40 core (pool × matchday)

| group | n | RPS model | RPS book | book − model | CI |
|---|---|---|---|---|---|
| non-core | 100 | 0.1909 | 0.1924 | +0.00153 | [-0.01018, +0.01313] |
| core | 105 | 0.1924 | 0.1803 | -0.01204 | [-0.02218, -0.00206] |

### By competition

| tournament | n | book − model |
|---|---|---|
| African Cup of Nations | 84 | -0.00204 |
| Copa América | 24 | +0.02103 |
| FIFA World Cup qualification | 25 | -0.03795 |
| UEFA Nations League | 72 | -0.00688 |

### Held at fixed favourite strength

| favourite band | non-core mean (n) | core mean (n) |
|---|---|---|
| <40% | -0.00456 (10) | -0.00927 (23) |
| 40-50% | -0.00533 (23) | -0.01810 (20) |
| 50-60% | +0.01006 (25) | -0.02202 (18) |
| 60-75% | +0.00451 (32) | -0.01400 (29) |
| >75% | -0.00746 (10) | +0.00759 (15) |
