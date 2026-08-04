# OA verdict — the pre-registered decision (V10)

## ADOPT

Gate: `mean(ΔRPS) <= -0.002` AND `support >= 0.8` — both halves required.

- n (primary, covered-only): **217**
- mean ΔRPS: **-0.01018**  (floor -0.002: MET)
- support: **0.995**  (req 0.8: MET)
- one-sided p (descriptive, never overrides the gate): 0.00560
- sign-flip veto: not fired
- jackknife (leave-one-team-out) mean range: [-0.01247, -0.00843]
- within-block correlation r: -0.1065

## Per-pool

| pool | n | blocks | mean ΔRPS | opp. support |
|---|---|---|---|---|
| euro2024 | 50 | 21 | -0.00742 | 0.130 |
| wc2022 | 63 | 22 | -0.01318 | 0.056 |
| wc2026 | 104 | 34 | -0.00968 | 0.057 |

## Secondary family (Holm, α=0.05, one-sided)

| member | n | mean ΔRPS | raw p | adj p | rejected |
|---|---|---|---|---|---|
| Eprime_other_devig | 217 | -0.01013 | 0.00650 | 0.02600 | yes |
| stacking | 217 | -0.00584 | 0.09779 | 0.29337 | no |
| elo_ordlogit | 217 | -0.00021 | 0.48155 | 0.58934 | no |
| elo_dc_5050 | 217 | -0.00061 | 0.29467 | 0.58934 | no |

## ITT sensitivity (primary contrast only)

VACUOUS on this inventory: all 217 locked fixtures are odds-covered, so there are no uncovered rows to dilute with and the ITT population IS the primary population — the figures above are the same computation, not an independent sensitivity. Reported for completeness because the spec requires the contrast; it carries no corroborating weight here.

Lock v5, commit 15a7a7e0e42a.
