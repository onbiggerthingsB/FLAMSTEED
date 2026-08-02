# Where the model loses to the market — exploratory diagnostic

**Not preregistered.** Post-hoc strata chosen after outcomes were known, no gate, no multiplicity control. Anything striking here is a hypothesis for a future prereg'd test, not a finding. Cell counts are shown because with 217 fixtures cut this many ways, some cell will look dramatic by chance.

Comparator is the TRUE de-vigged book (`multiplicative`) from the archived cut snapshots, not the E' arm. Lower RPS is better, so a NEGATIVE `book − model` means the market won that stratum.

Overall: model 0.1868, book 0.1764, difference -0.01035, model wins 42% of fixtures.

That win rate is the first thing worth noticing: the model is not uniformly worse. It takes nearly half the individual fixtures and loses the aggregate through a fat tail of catastrophic misses — so the question is which fixtures blow up, not whether the model is broadly miscalibrated.

### by confederation (rating-history depth)

| stratum | n | RPS model | RPS book | book − model | model wins |
|---|---|---|---|---|---|
| at least one outside | 125 | 0.1940 | 0.1758 | -0.01820 | 38% |
| both UEFA/CONMEBOL | 92 | 0.1769 | 0.1772 | +0.00031 | 47% |

### by market favourite strength

| stratum | n | RPS model | RPS book | book − model | model wins |
|---|---|---|---|---|---|
| <40% | 24 | 0.2394 | 0.2254 | -0.01407 | 38% |
| 40-50% | 44 | 0.1941 | 0.1814 | -0.01274 | 41% |
| 50-60% | 55 | 0.2047 | 0.1879 | -0.01680 | 38% |
| 60-75% | 64 | 0.1720 | 0.1752 | +0.00321 | 56% |
| >75% | 30 | 0.1323 | 0.1113 | -0.02101 | 23% |

### by realised outcome

| stratum | n | RPS model | RPS book | book − model | model wins |
|---|---|---|---|---|---|
| away | 65 | 0.2060 | 0.2005 | -0.00549 | 40% |
| draw | 63 | 0.1819 | 0.1798 | -0.00207 | 48% |
| home | 89 | 0.1762 | 0.1564 | -0.01977 | 39% |

### by stage

| stratum | n | RPS model | RPS book | book − model | model wins |
|---|---|---|---|---|---|
| group | 154 | 0.1936 | 0.1806 | -0.01298 | 42% |
| knockout | 63 | 0.1701 | 0.1662 | -0.00393 | 41% |

### by pool

| stratum | n | RPS model | RPS book | book − model | model wins |
|---|---|---|---|---|---|
| euro2024 | 50 | 0.1972 | 0.1895 | -0.00772 | 48% |
| wc2022 | 63 | 0.2218 | 0.2083 | -0.01351 | 46% |
| wc2026 | 104 | 0.1605 | 0.1508 | -0.00971 | 37% |

### by model-vs-market disagreement on the market's favourite

| stratum | n | RPS model | RPS book | book − model | model wins |
|---|---|---|---|---|---|
| model much lower | 51 | 0.1822 | 0.1616 | -0.02053 | 29% |
| model lower | 47 | 0.1874 | 0.1848 | -0.00261 | 45% |
| agree (±4pp) | 59 | 0.1665 | 0.1629 | -0.00364 | 39% |
| model higher | 35 | 0.1992 | 0.1958 | -0.00342 | 54% |
| model much higher | 25 | 0.2253 | 0.1956 | -0.02970 | 52% |

### Calibration (all three outcomes pooled)

| predicted band | n | model: stated → actual | book: stated → actual |
|---|---|---|---|
| [0.0, 0.1) | 50 | 0.066 → 0.120 | 0.067 → 0.041 |
| [0.1, 0.2) | 112 | 0.157 → 0.170 | 0.152 → 0.172 |
| [0.2, 0.3) | 213 | 0.254 → 0.239 | 0.250 → 0.240 |
| [0.3, 0.4) | 92 | 0.341 → 0.380 | 0.339 → 0.351 |
| [0.4, 0.5) | 53 | 0.457 → 0.509 | 0.449 → 0.523 |
| [0.5, 0.65) | 66 | 0.571 → 0.515 | 0.576 → 0.602 |
| [0.65, 1.01) | 65 | 0.749 → 0.692 | 0.752 → 0.667 |

### Does the confederation split survive scrutiny?

| group | n | mean | 95% CI (fixture bootstrap) |
|---|---|---|---|
| both UEFA/CONMEBOL | 92 | +0.00031 | [-0.01022, +0.01126] |
| at least one outside | 125 | -0.01820 | [-0.03256, -0.00400] |

Same split held at fixed favourite strength — if the effect were real and not a proxy for lopsidedness, the core column should beat the non-core column in EVERY band:

| favourite band | non-core mean (n) | core mean (n) |
|---|---|---|
| <40% | -0.04981 (9) | +0.00738 (15) |
| 40-50% | -0.01265 (25) | -0.01287 (19) |
| 50-60% | -0.02856 (28) | -0.00461 (27) |
| 60-75% | -0.00439 (38) | +0.01433 (26) |
| >75% | -0.02179 (25) | -0.01712 (5) |

### The 10 fixtures the model lost worst

| fixture | pool | outcome | model | book | book − model |
|---|---|---|---|---|---|
| Cameroon v Brazil | wc2022 | home | 0.9126 | 0.6074 | -0.30518 |
| Ghana v Panama | wc2026 | home | 0.4417 | 0.2199 | -0.22179 |
| South Korea v Ghana | wc2022 | away | 0.5038 | 0.3002 | -0.20361 |
| Ivory Coast v Ecuador | wc2026 | home | 0.5206 | 0.3206 | -0.20001 |
| Qatar v Senegal | wc2022 | away | 0.3003 | 0.1052 | -0.19510 |
| United States v Australia | wc2026 | home | 0.2868 | 0.0978 | -0.18905 |
| South Korea v Portugal | wc2022 | home | 0.5979 | 0.4097 | -0.18818 |
| Ecuador v Senegal | wc2022 | away | 0.4952 | 0.3237 | -0.17153 |
| DR Congo v Uzbekistan | wc2026 | home | 0.2483 | 0.0956 | -0.15269 |
| Georgia v Portugal | euro2024 | home | 0.7829 | 0.6327 | -0.15028 |
