# Phase 1 — StatsBomb xG coverage report

StatsBomb Open Data xG is **point-in-time** (static + versioned; `valid_as_of == observed_at == match_date`) and **coverage-gated**: rich for big nations, sparse/absent for minnows. Uncovered teams are **absent / NULL**, never imputed.

- Pinned release marker: `statsbombpy-1.18.0@2026-06-03`
- Teams checked: **82**
- Covered: **82**
- Uncovered (gap set): **0**

## StatsBomb international competition inventory (live pull)

Pulled 11 international competition-seasons covering **82** distinct international team-entities (men's-senior + women's + U20). Men's-senior World Cup teams: **44**.

| competition | season | teams |
|---|---|---:|
| FIFA U20 World Cup | 1979 | 2 |
| FIFA World Cup | 1958 | 3 |
| FIFA World Cup | 1962 | 2 |
| FIFA World Cup | 1970 | 7 |
| FIFA World Cup | 1974 | 6 |
| FIFA World Cup | 1986 | 4 |
| FIFA World Cup | 1990 | 2 |
| FIFA World Cup | 2018 | 32 |
| FIFA World Cup | 2022 | 32 |
| Women's World Cup | 2019 | 24 |
| Women's World Cup | 2023 | 32 |

### Reading this report — coverage is presence in the metadata above

`covered = True` means the team appears in StatsBomb's international competition/match metadata (the inventory above). Because the team list checked below IS that available universe, every listed team is covered by construction — the operative gap is the teams that **do not appear at all** (filled in once the 48-team draw lands).

**Men's-senior caveat (the real coverage shape).** StatsBomb's *free* international men's-senior xG footprint is essentially **8 FIFA World Cup editions** (1958, 1962, 1970, 1974, 1986, 1990, 2018, 2022) — finals tournaments only, no qualifiers, no friendlies, no continental cups. So coverage is concentrated on nations that reached those finals; the minnow / qualifier tail is largely **absent (NULL), never imputed**. This compounds the Phase-0 finding that free international xG collapsed after the 2026-01-20 FBref/Opta cutoff (see `SOURCES.md`).

**Men's-senior World Cup teams present:**

- Argentina
- Australia
- Belgium
- Brazil
- Cameroon
- Canada
- Colombia
- Costa Rica
- Croatia
- Czechoslovakia
- Denmark
- Ecuador
- Egypt
- England
- France
- German DR
- Germany
- Ghana
- Iceland
- Iran
- Italy
- Japan
- Mexico
- Morocco
- Netherlands
- Nigeria
- Panama
- Peru
- Poland
- Portugal
- Qatar
- Romania
- Russia
- Saudi Arabia
- Senegal
- Serbia
- South Korea
- Spain
- Sweden
- Switzerland
- Tunisia
- United States
- Uruguay
- Wales

## Covered

- Argentina
- Argentina U20
- Argentina Women's
- Australia
- Australia Women's
- Belgium
- Brazil
- Brazil Women's
- Cameroon
- Cameroon W
- Canada
- Canada Women's
- Chile Women's
- China PR Women's
- Colombia
- Colombia Women's
- Costa Rica
- Costa Rica Women's
- Croatia
- Czechoslovakia
- Denmark
- Denmark Women's
- Ecuador
- Egypt
- England
- England Women's
- France
- France Women's
- German DR
- Germany
- Germany Women's
- Ghana
- Haiti Women's
- Iceland
- Iran
- Italy
- Italy Women's
- Jamaica Women's
- Japan
- Japan Women's
- Korea Republic Women's
- Mexico
- Morocco
- Morocco Women's
- Netherlands
- Netherlands Women's
- New Zealand Women's
- Nigeria
- Nigeria Women's
- Norway Women's
- Panama
- Panama Women's
- Peru
- Philippines Women's
- Poland
- Portugal
- Portugal Women's
- Qatar
- Republic of Ireland Women's
- Romania
- Russia
- Saudi Arabia
- Scotland W
- Senegal
- Serbia
- South Africa Women's
- South Korea
- Soviet Union U20
- Spain
- Spain Women's
- Sweden
- Sweden Women's
- Switzerland
- Switzerland Women's
- Thailand W
- Tunisia
- United States
- United States Women's
- Uruguay
- Vietnam Women's
- Wales
- Zambia W

## Uncovered — gap set (xG absent / NULL, never imputed)

_(none)_

## 48-team WC-2026 intersection — GATED

The 48-team WC-2026 coverage intersection is **gated** on the user-provided `config/tournament_2026.yaml` draw file (Task 13). This report covers the team list it was handed; the final 48-team gap analysis is produced once the draw file lands.
