# Live-2026 calibration scorecard (as of 2026-07-01)

**HONESTY RULE:** n=79 -> wide CIs. This scorecard INFORMS the
adoption meeting; it never auto-triggers a model change (the
2026-06-25 lesson: 72-game live variance is not a bias signal).

- matches scored: 79 (72 group + 7 R32); fresh fits this run: 20
- model mean RPS: 0.15655 | naive-Elo baseline: 0.16269 (lower better; n_elo=79)
- draw rate: predicted 0.230 vs realized 0.278

## Favorite-band reliability (live)
| band | n | pred fav-win | real fav-win | ±SE | pred draw | real draw | RPS |
|---|---|---|---|---|---|---|---|
| 0.55-0.65 | 16 | 0.593 | 0.812 | 0.098 | 0.242 | 0.062 | 0.1553 |
| 0.65-0.75 | 17 | 0.693 | 0.765 | 0.103 | 0.203 | 0.235 | 0.0948 |
| 0.75-0.85 | 7 | 0.795 | 0.714 | 0.171 | 0.145 | 0.286 | 0.1017 |
| 0.85+ | 6 | 0.879 | 0.500 | 0.204 | 0.091 | 0.500 | 0.1975 |
| all | 46 | 0.698 | 0.739 | 0.065 | 0.193 | 0.217 | 0.1303 |

## Blowout tails (the P4 question, on live data)
| tail | predicted | realized |
|---|---|---|
| margin>=2 | 0.435 | 0.456 |
| margin>=3 | 0.221 | 0.241 |
| margin>=4 | 0.106 | 0.114 |

## R32 subtable (n=7)
- mean RPS: 0.14930
