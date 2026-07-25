# Live-2026 calibration scorecard (FULL TOURNAMENT, as of 2026-07-20)

**HONESTY RULE:** n=104 -> wide CIs. This scorecard INFORMS the
adoption meeting; it never auto-triggers a model change (the
2026-06-25 lesson: 72-game live variance is not a bias signal).

KO outcome semantics: scores are ET-inclusive (an ET win scores as
a win; a shootout game scores as a draw).

- matches scored: 104 (72 group + 32 knockout); fresh fits this run: 14
- model mean RPS: 0.15609 | naive-Elo baseline: 0.15565 (lower better; n_elo=104)
- draw rate: predicted 0.234 vs realized 0.231

## Favorite-band reliability (live)
| band | n | pred fav-win | real fav-win | ±SE | pred draw | real draw | RPS |
|---|---|---|---|---|---|---|---|
| 0.55-0.65 | 22 | 0.600 | 0.818 | 0.082 | 0.239 | 0.045 | 0.1555 |
| 0.65-0.75 | 18 | 0.696 | 0.778 | 0.098 | 0.203 | 0.222 | 0.0916 |
| 0.75-0.85 | 10 | 0.799 | 0.800 | 0.126 | 0.141 | 0.200 | 0.0785 |
| 0.85+ | 6 | 0.887 | 0.500 | 0.204 | 0.086 | 0.500 | 0.1969 |
| all | 56 | 0.697 | 0.768 | 0.056 | 0.193 | 0.179 | 0.1257 |

## Blowout tails (the P4 question, on live data)
| tail | predicted | realized |
|---|---|---|
| margin>=2 | 0.428 | 0.433 |
| margin>=3 | 0.215 | 0.212 |
| margin>=4 | 0.102 | 0.087 |

## By stage (modal-outcome hits are vs the 1X2 modal pick)
| stage | n | mean RPS | modal hits |
|---|---|---|---|
| group | 72 | 0.15746 | 46/72 |
| R32 | 16 | 0.11632 | 12/16 |
| R16 | 8 | 0.18793 | 6/8 |
| QF | 4 | 0.13399 | 4/4 |
| SF | 2 | 0.19600 | 2/2 |
| third | 1 | 0.33295 | 0/1 |
| final | 1 | 0.27073 | 1/1 |
| all knockout | 32 | 0.15301 | 25/32 |
