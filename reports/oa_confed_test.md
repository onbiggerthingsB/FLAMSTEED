# Confederation hypothesis — out-of-sample test on the dev slate

## INCONCLUSIVE

H1 (pre-committed, formed on the 217-fixture eval pool): the model's deficit against the market is concentrated in fixtures involving a team outside UEFA/CONMEBOL. H1 predicts a NEGATIVE gap (non-core loses more).

- fixtures scored: **244** (123 non-core, 121 core)
- excluded as decided past 90' (shootouts, no 90' label): 15
- gap (non-core − core): **+0.01190**  95% CI [-0.00473, +0.02895]
- one-sided p against the pre-committed direction: 0.9141

| group | n | RPS model | RPS book | book − model | 95% CI |
|---|---|---|---|---|---|
| non-core | 123 | 0.1939 | 0.1947 | +0.00088 | [-0.01051, +0.01289] |
| core | 121 | 0.2003 | 0.1893 | -0.01102 | [-0.02415, +0.00100] |

### By competition

| tournament | n | book − model |
|---|---|---|
| African Cup of Nations | 105 | -0.00239 |
| Copa América | 28 | +0.01998 |
| FIFA World Cup qualification | 25 | -0.03795 |
| UEFA Nations League | 86 | -0.00681 |

### Held at fixed favourite strength

Favourite strength partly confounded the eval-pool version, so the same control is applied here.

| favourite band | non-core mean (n) | core mean (n) |
|---|---|---|
| <40% | -0.00550 (16) | -0.00685 (26) |
| 40-50% | -0.00941 (30) | -0.01419 (28) |
| 50-60% | +0.01353 (29) | -0.01638 (21) |
| 60-75% | +0.00422 (38) | -0.01704 (31) |
| >75% | -0.00746 (10) | +0.00759 (15) |

Contamination note: no verified 90' table exists for AFCON or Copa América, so a knockout tie decided by an extra-time GOAL is scored on its ET-inclusive final. Shootouts are excluded (15 fixtures). The residual perturbs both arms on the same fixture, so it adds noise to the paired difference rather than a direction.
