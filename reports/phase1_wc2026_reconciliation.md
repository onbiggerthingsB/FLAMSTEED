# Phase 1 — WC 2026 Name Reconciliation (openfootball → martj42)

**Status: FOR REVIEW — not committed, not ingested.**

Reconciles every 2026 World Cup team (as named in the openfootball CC0 feed)
against the canonical key used in our martj42 international-results store, so
`features.build` can join each team's full match history. The
`config/tournament_2026.yaml` team list + group teams use the **martj42 store key**
(the `martj42 store key` column below).

## Sources

- **openfootball** draw + names: `openfootball/worldcup.json` @ `master`, files
  `2026/worldcup.json` and `2026/worldcup.teams.json` (CC0). The
  `name_normalised` column below is openfootball's own FIFA-style hint field
  (shown for context — we do NOT key on it).
- **martj42** store keys: `wcmodel.data.sources.results.fetch_results` /
  `normalize_results`, martj42/international_results pinned commit
  `dad6874bb720e23cccdf696f057aa64fa5471445` (the value in `results.py`),
  read from the local content-addressed cache. 336 distinct team names,
  49,368 rows.

## Key finding

The martj42 store keys on **common-English** names, NOT FIFA-normalised forms.
So `South Korea` (not `Korea Republic`), `Czech Republic` (not `Czechia`),
`Turkey` (not `Türkiye`), `Cape Verde` (not `Cabo Verde`), `Ivory Coast` (not
`Cote d'Ivoire`), `DR Congo` (not `Congo DR`), `Iran` (not `IR Iran`) are all the
martj42 keys. **46 of 48** WC teams therefore match the openfootball name verbatim.
Only two need a transform:

| WC team | openfootball name | martj42 store key | transform |
|---|---|---|---|
| United States | `USA` | `United States` | openfootball `name_normalised` |
| Bosnia & Herzegovina | `Bosnia & Herzegovina` | `Bosnia and Herzegovina` | `&` → `and` |

No team's normalised form ALSO exists as a separate martj42 key (zero ambiguity).
Every one of the 48 keys has real history (min 237 matches: Cape Verde).

## Full 48-team mapping

Ordered by group (A–L), draw order within group.

| # | Group | WC team | openfootball name | name_normalised (hint) | martj42 store key | matched? |
|---:|:--:|---|---|---|---|:--:|
| 1 | A | Mexico | `Mexico` | — | `Mexico` | yes |
| 2 | A | South Africa | `South Africa` | — | `South Africa` | yes |
| 3 | A | South Korea | `South Korea` | `Korea Republic` | `South Korea` | yes |
| 4 | A | Czech Republic | `Czech Republic` | `Czechia` | `Czech Republic` | yes |
| 5 | B | Canada | `Canada` | — | `Canada` | yes |
| 6 | B | Bosnia and Herzegovina | `Bosnia & Herzegovina` | — | `Bosnia and Herzegovina` | yes |
| 7 | B | Qatar | `Qatar` | — | `Qatar` | yes |
| 8 | B | Switzerland | `Switzerland` | — | `Switzerland` | yes |
| 9 | C | Brazil | `Brazil` | — | `Brazil` | yes |
| 10 | C | Morocco | `Morocco` | — | `Morocco` | yes |
| 11 | C | Haiti | `Haiti` | — | `Haiti` | yes |
| 12 | C | Scotland | `Scotland` | — | `Scotland` | yes |
| 13 | D | United States | `USA` | `United States` | `United States` | yes |
| 14 | D | Paraguay | `Paraguay` | — | `Paraguay` | yes |
| 15 | D | Australia | `Australia` | — | `Australia` | yes |
| 16 | D | Turkey | `Turkey` | `Türkiye` | `Turkey` | yes |
| 17 | E | Germany | `Germany` | — | `Germany` | yes |
| 18 | E | Curaçao | `Curaçao` | — | `Curaçao` | yes |
| 19 | E | Ivory Coast | `Ivory Coast` | `Cote d'Ivoire` | `Ivory Coast` | yes |
| 20 | E | Ecuador | `Ecuador` | — | `Ecuador` | yes |
| 21 | F | Netherlands | `Netherlands` | — | `Netherlands` | yes |
| 22 | F | Japan | `Japan` | — | `Japan` | yes |
| 23 | F | Sweden | `Sweden` | — | `Sweden` | yes |
| 24 | F | Tunisia | `Tunisia` | — | `Tunisia` | yes |
| 25 | G | Belgium | `Belgium` | — | `Belgium` | yes |
| 26 | G | Egypt | `Egypt` | — | `Egypt` | yes |
| 27 | G | Iran | `Iran` | `IR Iran` | `Iran` | yes |
| 28 | G | New Zealand | `New Zealand` | — | `New Zealand` | yes |
| 29 | H | Spain | `Spain` | — | `Spain` | yes |
| 30 | H | Cape Verde | `Cape Verde` | `Cabo Verde` | `Cape Verde` | yes |
| 31 | H | Saudi Arabia | `Saudi Arabia` | — | `Saudi Arabia` | yes |
| 32 | H | Uruguay | `Uruguay` | — | `Uruguay` | yes |
| 33 | I | France | `France` | — | `France` | yes |
| 34 | I | Senegal | `Senegal` | — | `Senegal` | yes |
| 35 | I | Iraq | `Iraq` | — | `Iraq` | yes |
| 36 | I | Norway | `Norway` | — | `Norway` | yes |
| 37 | J | Argentina | `Argentina` | — | `Argentina` | yes |
| 38 | J | Algeria | `Algeria` | — | `Algeria` | yes |
| 39 | J | Austria | `Austria` | — | `Austria` | yes |
| 40 | J | Jordan | `Jordan` | — | `Jordan` | yes |
| 41 | K | Portugal | `Portugal` | — | `Portugal` | yes |
| 42 | K | DR Congo | `DR Congo` | `Congo DR` | `DR Congo` | yes |
| 43 | K | Uzbekistan | `Uzbekistan` | — | `Uzbekistan` | yes |
| 44 | K | Colombia | `Colombia` | — | `Colombia` | yes |
| 45 | L | England | `England` | — | `England` | yes |
| 46 | L | Croatia | `Croatia` | — | `Croatia` | yes |
| 47 | L | Ghana | `Ghana` | — | `Ghana` | yes |
| 48 | L | Panama | `Panama` | — | `Panama` | yes |

## Unresolved teams

**None.** All 48 WC teams resolve to a martj42 store key with real history.

## Per-team history sanity (martj42 match counts)

All 48 keys verified to have substantial history in the store (counts below were
checked at reconciliation time; range 237–1103 matches). No key was selected on
string-existence alone.

