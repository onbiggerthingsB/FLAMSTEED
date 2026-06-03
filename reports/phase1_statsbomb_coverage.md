# Phase 1 — StatsBomb xG coverage report

StatsBomb Open Data xG is **point-in-time** (static + versioned; `valid_as_of == observed_at == match_date`) and **coverage-gated**: rich for big nations, sparse/absent for minnows. Uncovered teams are **absent / NULL**, never imputed.

- Pinned release marker: `statsbombpy-1.18.0@2026-06-03`
- Teams checked: **123**
- Covered: **123**
- Uncovered (gap set): **0**

## StatsBomb international competition inventory (live pull)

Selected via `competition_international == True` (the correct filter — **not** `country_name == "International"`, which silently drops the continental national-team cups that StatsBomb files under their confederation, e.g. UEFA Euro under `Europe`). Pulled **17** international national-team competition-seasons; **12** are men's-senior, covering **78** distinct men's-senior national teams. Women's and youth competitions are listed below the table but excluded from the men's-senior universe.

| competition | season | confederation | gender | teams |
|---|---|---|---|---:|
| African Cup of Nations | 2023 | Africa | men | 24 |
| Copa America | 2024 | South America | men | 16 |
| FIFA World Cup | 1958 | International | men | 3 |
| FIFA World Cup | 1962 | International | men | 2 |
| FIFA World Cup | 1970 | International | men | 7 |
| FIFA World Cup | 1974 | International | men | 6 |
| FIFA World Cup | 1986 | International | men | 4 |
| FIFA World Cup | 1990 | International | men | 2 |
| FIFA World Cup | 2018 | International | men | 32 |
| FIFA World Cup | 2022 | International | men | 32 |
| UEFA Euro | 2020 | Europe | men | 24 |
| UEFA Euro | 2024 | Europe | men | 24 |
| FIFA U20 World Cup | 1979 | International | men U20 | 2 |
| UEFA Women's Euro | 2022 | Europe | women | 16 |
| UEFA Women's Euro | 2025 | Europe | women | 16 |
| Women's World Cup | 2019 | International | women | 24 |
| Women's World Cup | 2023 | International | women | 32 |

### Reading this report — coverage is presence in the metadata above

`covered = True` means the team appears in StatsBomb's international competition/match metadata (the inventory above). Because the team list checked below IS that available universe, every listed team is covered by construction — the operative gap is the teams that **do not appear at all** (filled in once the 48-team draw lands).

**Men's-senior coverage shape (the real footprint).** StatsBomb's *free* international men's-senior xG is **NOT** World-Cup-only: it is the **8 FIFA World Cup finals editions** (1958, 1962, 1970, 1974, 1986, 1990, 2018, 2022) **plus** the recent continental cups — **UEFA Euro 2020 & 2024**, **Copa America 2024**, and the **African Cup of Nations 2023** — i.e. **12 men's-senior competition-seasons / ~78 national teams**. There are **NO qualifiers, NO friendlies, and no Nations League** in the free Open Data. So the qualifier/friendly tail is absent (NULL, never imputed), **but** the continental-cup participants — a meaningful slice of mid- and lower-tier sides (e.g. the full AFCON-2023 and Copa-2024 fields) — **ARE** covered. Practically this means xG is still **NULL for the entire (qualifier / friendly / Nations-League-heavy) backtest window**, but **available for finals + continental-cup matches**. This compounds the Phase-0 finding that free international xG collapsed after the 2026-01-20 FBref/Opta cutoff (see `SOURCES.md`).

**Men's-senior national teams present (78):**

- Albania
- Algeria
- Angola
- Argentina
- Australia
- Austria
- Belgium
- Bolivia
- Brazil
- Burkina Faso
- Cameroon
- Canada
- Cape Verde Islands
- Chile
- Colombia
- Congo DR
- Costa Rica
- Croatia
- Czech Republic
- Czechoslovakia
- Côte d'Ivoire
- Denmark
- Ecuador
- Egypt
- England
- Equatorial Guinea
- Finland
- France
- Gambia
- Georgia
- German DR
- Germany
- Ghana
- Guinea
- Guinea-Bissau
- Hungary
- Iceland
- Iran
- Italy
- Jamaica
- Japan
- Mali
- Mauritania
- Mexico
- Morocco
- Mozambique
- Namibia
- Netherlands
- Nigeria
- North Macedonia
- Panama
- Paraguay
- Peru
- Poland
- Portugal
- Qatar
- Romania
- Russia
- Saudi Arabia
- Scotland
- Senegal
- Serbia
- Slovakia
- Slovenia
- South Africa
- South Korea
- Spain
- Sweden
- Switzerland
- Tanzania
- Tunisia
- Turkey
- Ukraine
- United States
- Uruguay
- Venezuela
- Wales
- Zambia

**Women's competitions (listed separately, not in the men's-senior universe):** UEFA Women's Euro 2022, UEFA Women's Euro 2025, Women's World Cup 2019, Women's World Cup 2023.

**Youth competitions (separate):** FIFA U20 World Cup 1979.


## Covered

- Albania
- Algeria
- Angola
- Argentina
- Argentina U20
- Argentina Women's
- Australia
- Australia Women's
- Austria
- Austria Women's
- Belgium
- Belgium Women's
- Bolivia
- Brazil
- Brazil Women's
- Burkina Faso
- Cameroon
- Cameroon W
- Canada
- Canada Women's
- Cape Verde Islands
- Chile
- Chile Women's
- China PR Women's
- Colombia
- Colombia Women's
- Congo DR
- Costa Rica
- Costa Rica Women's
- Croatia
- Czech Republic
- Czechoslovakia
- Côte d'Ivoire
- Denmark
- Denmark Women's
- Ecuador
- Egypt
- England
- England Women's
- Equatorial Guinea
- Finland
- France
- France Women's
- Gambia
- Georgia
- German DR
- Germany
- Germany Women's
- Ghana
- Guinea
- Guinea-Bissau
- Haiti Women's
- Hungary
- Iceland
- Iceland Women's
- Iran
- Italy
- Italy Women's
- Jamaica
- Jamaica Women's
- Japan
- Japan Women's
- Korea Republic Women's
- Mali
- Mauritania
- Mexico
- Morocco
- Morocco Women's
- Mozambique
- Namibia
- Netherlands
- Netherlands Women's
- New Zealand Women's
- Nigeria
- Nigeria Women's
- North Macedonia
- Northern Ireland W
- Norway Women's
- Panama
- Panama Women's
- Paraguay
- Peru
- Philippines Women's
- Poland
- Poland Women's
- Portugal
- Portugal Women's
- Qatar
- Republic of Ireland Women's
- Romania
- Russia
- Saudi Arabia
- Scotland
- Scotland W
- Senegal
- Serbia
- Slovakia
- Slovenia
- South Africa
- South Africa Women's
- South Korea
- Soviet Union U20
- Spain
- Spain Women's
- Sweden
- Sweden Women's
- Switzerland
- Switzerland Women's
- Tanzania
- Thailand W
- Tunisia
- Turkey
- Ukraine
- United States
- United States Women's
- Uruguay
- Venezuela
- Vietnam Women's
- WNT Finland
- Wales
- Wales W
- Zambia
- Zambia W

## Uncovered — gap set (xG absent / NULL, never imputed)

_(none)_

## 48-team WC-2026 intersection — GATED

The 48-team WC-2026 coverage intersection is **gated** on the user-provided `config/tournament_2026.yaml` draw file (Task 13). This report covers the team list it was handed; the final 48-team gap analysis is produced once the draw file lands.
