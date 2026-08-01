# OA blend selection — the frozen V6 procedure (OA Plan 2 v2)

**Deployment choice: w = 0.95, de-vig = multiplicative**

- dev fixtures scored: **259**
- excluded (no admissible odds): 0
- months: 16 (2022-01 .. 2025-12)
- scoreable folds (after the 2-month burn-in): **14**
- ledger: `data/oa_dev_ledger.parquet`
- trace (hash-bound at V8): `reports/oa_selection_trace.json`

## Walk-forward folds

Each fold's candidate is chosen on the months STRICTLY BEFORE it, then scored on it — so no fold's RPS informed its own choice.

| month | train fixtures | fold fixtures | w | de-vig | fold RPS |
|---|---|---|---|---|---|
| 2022-06 | 33 | 8 | 1.00 | multiplicative | 0.27800 |
| 2022-09 | 41 | 16 | 1.00 | multiplicative | 0.25444 |
| 2023-06 | 57 | 4 | 0.90 | multiplicative | 0.27380 |
| 2024-01 | 61 | 41 | 1.00 | multiplicative | 0.21829 |
| 2024-02 | 102 | 8 | 1.00 | multiplicative | 0.18027 |
| 2024-06 | 110 | 20 | 1.00 | multiplicative | 0.15624 |
| 2024-07 | 130 | 11 | 0.80 | multiplicative | 0.17307 |
| 2024-09 | 141 | 16 | 0.50 | multiplicative | 0.15172 |
| 2024-10 | 157 | 16 | 0.65 | multiplicative | 0.12080 |
| 2024-11 | 173 | 16 | 0.55 | multiplicative | 0.22677 |
| 2025-03 | 189 | 13 | 0.85 | multiplicative | 0.19227 |
| 2025-06 | 202 | 14 | 0.95 | multiplicative | 0.17277 |
| 2025-09 | 216 | 10 | 1.00 | multiplicative | 0.16591 |
| 2025-12 | 226 | 33 | 1.00 | multiplicative | 0.13370 |

## Grid (mean canonical RPS over all dev months)

Lower is better. w=0 IS the frozen incumbent, w=1 IS the de-vigged book, so this table brackets the whole question.

| rank | de-vig | w | mean RPS |
|---|---|---|---|
| 1 | multiplicative | 0.95 | 0.18868 |
| 2 | multiplicative | 0.90 | 0.18869 |
| 3 | multiplicative | 1.00 | 0.18870 |
| 4 | multiplicative | 0.85 | 0.18874 |
| 5 | multiplicative | 0.80 | 0.18882 |
| 6 | shin | 0.95 | 0.18886 |
| 7 | shin | 0.90 | 0.18887 |
| 8 | shin | 1.00 | 0.18888 |

## Reference points

- incumbent (w=0): **0.19372**
- de-vigged book (w=1, multiplicative): **0.18870**
- best grid point (multiplicative, w=0.95): **0.18868**
- best vs incumbent: **-0.00504** RPS

These are DEVELOPMENT numbers on the slate w was tuned on — they are not evidence of transfer and carry no verdict. The scored pools are untouched until the V8 lock closes and V9 issues.

## Stacking arm (same folds, same de-vig)

- de-vig: multiplicative
- fixtures: 259 (excluded, no odds: 0)
- folds: 14
- pooled OOF RPS: **0.19088**
- deployment weights: dc +0.864, odds +0.840, elo -0.818

The stacking arm is a SECONDARY in the Holm family, not the primary contrast — it is reported here because the V8 lock binds it to the same trace as (w, de-vig).
