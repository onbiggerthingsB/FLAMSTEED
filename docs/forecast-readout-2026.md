# What the model predicts for WC-2026

*A plain-language readout of the real model forecast. As-of 2026-06-07.*

---

## 0. Read this first — the honesty frame

This brief summarizes what **our forecasting model** thinks will happen at the
2026 World Cup. Before any number, four things you must hold in mind:

- **It is a market-prior-free Elo + recent-form Dixon-Coles model.** Team strength
  comes from a computed Elo history (recent results, form-weighted) feeding a
  Dixon-Coles low-score goal model. Crucially, **the betting market is never an
  input** — no bookmaker odds anchor the prior or the ratings (see
  `ASSUMPTIONS.md`, "Independent prior — Elo is NOT a prior or covariate").
  So this is *not* the book's number re-dressed; it is an independent estimate.
- **All matches are treated as neutral-venue.** Home-field advantage is switched
  off (`ha = 0 if neutral`, `ASSUMPTIONS.md`). In the fixture files "home" and
  "away" are just the scheduled name order, **not** a venue edge. A real
  tournament has hosts and travel; this model deliberately does not model that yet.
- **Every number carries its uncertainty.** Progression figures come from a
  20,000-run Monte-Carlo simulation (`meta.json` → `n_sims: 20000`), so each
  one ships with a **standard error (SE)** — the `± value` you see throughout.
  Scoreline forecasts carry their full probability distribution. A figure without
  its uncertainty is half a figure.
- **This is a NON-REAL, synthetic-odds dry-run.** Per `meta.json`:
  `is_synthetic: true`, and the provenance banner reads —
  > *"DRY-RUN · SYNTHETIC ODDS · NOT REAL — no real odds were sourced, no bet
  > was placed, and no number here is a real CLV/ROI claim."*

  **This is not betting advice.** No edge, no expected value, no return number in
  this document is real. What *is* real is the model's view of the football:
  who advances, who wins groups, and the most likely scorelines. Those need no
  odds — they are model + simulation only.

Provenance for everything below (all files under
`data/dashboard/2026-06-07T000000Z/`): `meta.json` carries `as_of:
2026-06-07T00:00:00Z`, `git: f018e66`, `posterior_key: bf33cfd568f3c67f`.

---

## 1. The title race — and why it looks "flat"

Top of the field by **champion probability** (from `tournament.json`, each
team's `champion.{value, se}`):

| #  | Team        | Champion %        | Reach-final %     |
|----|-------------|-------------------|-------------------|
| 1  | Norway      | **4.06 ± 0.14**   | 6.77 ± 0.18       |
| 2  | Argentina   | 3.79 ± 0.13       | 6.96 ± 0.18       |
| 3  | Portugal    | 3.75 ± 0.13       | 7.06 ± 0.18       |
| 4  | Japan       | 3.75 ± 0.13       | 6.80 ± 0.18       |
| 5  | Algeria     | 3.31 ± 0.13       | 5.79 ± 0.17       |
| 6  | England     | 2.96 ± 0.12       | 5.71 ± 0.16       |
| 7  | Spain       | 2.95 ± 0.12       | 5.72 ± 0.16       |
| 8  | Australia   | 2.90 ± 0.12       | 5.28 ± 0.16       |
| 9  | Netherlands | 2.78 ± 0.12       | 5.46 ± 0.16       |
| 10 | Senegal     | 2.66 ± 0.11       | 5.62 ± 0.16       |
| 11 | Belgium     | 2.62 ± 0.11       | 5.16 ± 0.16       |
| 12 | Tunisia     | 2.61 ± 0.11       | 4.98 ± 0.15       |

**Read the SEs before you read the ranking.** The gap from Norway (4.06%) to
Japan (3.75%) is about 0.3 points; the SEs are ~0.13. So the top four are a
**statistical near-tie** — the ordering inside that cluster is barely resolved by
20,000 sims. Treat positions 1–4 as "the leading pack", not a strict 1-2-3-4.

### The distribution is FLAT — on purpose, not a bug

The model's favourite (Norway, 4.06%) is only about **8× more likely to win than
its longest shot** (Qatar, 0.52% ± 0.05 — the bottom of the 48-team field in
`tournament.json`). A betting market would typically price its favourite at
*tens of times* the longest shot. Why is ours so compressed?

Three honest reasons, all by design:

1. **No market anchor.** We never import the book's odds, so we never inherit the
   book's confidence. The model only knows what the results-driven Elo + form tells
   it, and on neutral ground that signal separates teams *modestly*.
2. **Neutral venues.** With home advantage off, nobody gets the boost a host or a
   well-travelled favourite would get — strengths sit closer together.
3. **The knockout gauntlet is a stack of coin-flips.** In the 48-team bracket a
   champion must win **five straight knockout rounds** (R32 → R16 → QF → SF →
   Final; `schedule.json` knockout stages: 16 R32, 8 R16, 4 QF, 2 SF, 1 Final)
   *after* surviving the group. When the per-match edges are small (see §4),
   even a strong side's probability of running that gauntlet collapses toward the
   pack. Compounding ~5–7 near-even matches flattens everyone.

This flatness is **the honest signal**, not a defect. It says: *on neutral
ground, with no market to lean on, this is genuinely an open tournament.*

### Dark horses — where the model disagrees with conventional seeding

The flat field reorders the usual hierarchy. The model rates several lower-profile
sides **above** traditional powers (all from `tournament.json` champion values):

- **Norway, #1 overall (4.06%)** — the headline. A team that has not historically
  been a World Cup contender sits top of the model's board, driven by recent-form
  Elo with no market to pull it back down.
- **Algeria #5 (3.31%), Australia #8 (2.90%), Senegal #10 (2.66%), Tunisia #12
  (2.61%), Haiti #13 (2.57%)** — all ahead of names a bookmaker would rank far
  higher.

By contrast, the model pushes conventional heavyweights **down**:

| Team    | Model rank (of 48) | Champion % |
|---------|--------------------|------------|
| Brazil  | #16                | 2.37%      |
| Germany | #23                | 1.97%      |
| France  | #26                | 1.91%      |

**Why?** Two mechanics, no mystery:

- **Recent-form Elo, not reputation.** The rating reflects how teams have actually
  played in their recent window, not their pedigree or squad value. Sides on a
  strong current run (Norway, Algeria, Senegal) get rewarded; sides coasting on
  reputation do not.
- **No market correction.** A bookmaker's price blends form *with* market money,
  history, and squad pricing, which props traditional powers back up. We strip all
  of that out. France at #26 is what "form-Elo, neutral pitch, no betting prior"
  produces — read it as the model's honest disagreement, not a claim that France
  is bad.

The right way to hold these: **directional reads, not point estimates.** A 2-point
champion-probability gap, against ~0.12-point SEs, is real but small.

---

## 2. Group by group

All 12 groups have four teams. Below are the **projected group winner**
(`win_group`) and each team's **chance to advance** (`advance_from_group`), with
SEs, from `tournament.json`. Teams ordered by win-group probability.

> Note on "advance": the field is 48 teams in 12 groups; the top two plus the best
> eight third-placed teams reach the knockouts, which is why even fourth-placed
> sides carry a healthy advance probability.

**Group A** — *the flattest group in the tournament*
| Team           | Win group %   | Advance %     |
|----------------|---------------|---------------|
| South Korea    | 27.9 ± 0.3    | 70.3 ± 0.3    |
| Mexico         | 25.7 ± 0.3    | 66.8 ± 0.3    |
| Czech Republic | 24.0 ± 0.3    | 63.3 ± 0.3    |
| South Africa   | 22.4 ± 0.3    | 65.4 ± 0.3    |

**Group B**
| Team                   | Win group %  | Advance %    |
|------------------------|--------------|--------------|
| Switzerland            | 33.4 ± 0.3   | 74.6 ± 0.3   |
| Canada                 | 27.6 ± 0.3   | 70.7 ± 0.3   |
| Bosnia and Herzegovina | 23.5 ± 0.3   | 65.3 ± 0.3   |
| Qatar                  | 15.6 ± 0.3   | 55.9 ± 0.4   |

**Group C** — *near dead-heat for the win; a traditional power not favoured*
| Team     | Win group %  | Advance %    |
|----------|--------------|--------------|
| Haiti    | 28.1 ± 0.3   | 71.1 ± 0.3   |
| Morocco  | 27.5 ± 0.3   | 71.7 ± 0.3   |
| Brazil   | 26.4 ± 0.3   | 68.2 ± 0.3   |
| Scotland | 17.9 ± 0.3   | 55.1 ± 0.4   |

**Group D**
| Team          | Win group %  | Advance %    |
|---------------|--------------|--------------|
| Australia     | 29.3 ± 0.3   | 71.8 ± 0.3   |
| Turkey        | 27.9 ± 0.3   | 69.9 ± 0.3   |
| United States | 22.5 ± 0.3   | 63.8 ± 0.3   |
| Paraguay      | 20.3 ± 0.3   | 61.3 ± 0.3   |

**Group E**
| Team        | Win group %  | Advance %    |
|-------------|--------------|--------------|
| Ivory Coast | 28.4 ± 0.3   | 70.9 ± 0.3   |
| Germany     | 26.5 ± 0.3   | 69.7 ± 0.3   |
| Ecuador     | 23.2 ± 0.3   | 67.4 ± 0.3   |
| Curaçao     | 21.8 ± 0.3   | 60.7 ± 0.3   |

**Group F**
| Team        | Win group %  | Advance %    |
|-------------|--------------|--------------|
| Japan       | 30.9 ± 0.3   | 74.9 ± 0.3   |
| Netherlands | 25.8 ± 0.3   | 67.8 ± 0.3   |
| Tunisia     | 24.1 ± 0.3   | 65.6 ± 0.3   |
| Sweden      | 19.1 ± 0.3   | 58.1 ± 0.3   |

**Group G**
| Team        | Win group %  | Advance %    |
|-------------|--------------|--------------|
| Belgium     | 29.7 ± 0.3   | 71.5 ± 0.3   |
| Iran        | 25.1 ± 0.3   | 68.5 ± 0.3   |
| Egypt       | 24.6 ± 0.3   | 68.0 ± 0.3   |
| New Zealand | 20.6 ± 0.3   | 59.3 ± 0.3   |

**Group H** — *the model's most lopsided group*
| Team         | Win group %  | Advance %    |
|--------------|--------------|--------------|
| Spain        | 36.0 ± 0.3   | 75.9 ± 0.3   |
| Cape Verde   | 25.3 ± 0.3   | 68.3 ± 0.3   |
| Uruguay      | 20.8 ± 0.3   | 63.4 ± 0.3   |
| Saudi Arabia | 17.9 ± 0.3   | 57.6 ± 0.3   |

**Group I** — *tightest fight for the top spot (Norway/Senegal split 0.6 pt)*
| Team    | Win group %  | Advance %    |
|---------|--------------|--------------|
| Norway  | 28.7 ± 0.3   | 67.9 ± 0.3   |
| Senegal | 28.1 ± 0.3   | 72.1 ± 0.3   |
| France  | 23.1 ± 0.3   | 67.3 ± 0.3   |
| Iraq    | 20.0 ± 0.3   | 59.7 ± 0.3   |

**Group J**
| Team      | Win group %  | Advance %    |
|-----------|--------------|--------------|
| Argentina | 31.6 ± 0.3   | 73.8 ± 0.3   |
| Algeria   | 26.6 ± 0.3   | 68.9 ± 0.3   |
| Austria   | 23.5 ± 0.3   | 66.4 ± 0.3   |
| Jordan    | 18.3 ± 0.3   | 58.1 ± 0.3   |

**Group K**
| Team       | Win group %  | Advance %    |
|------------|--------------|--------------|
| Portugal   | 31.0 ± 0.3   | 71.6 ± 0.3   |
| Colombia   | 26.4 ± 0.3   | 67.5 ± 0.3   |
| Uzbekistan | 21.7 ± 0.3   | 64.3 ± 0.3   |
| DR Congo   | 20.9 ± 0.3   | 63.0 ± 0.3   |

**Group L**
| Team    | Win group %  | Advance %    |
|---------|--------------|--------------|
| England | 30.3 ± 0.3   | 71.1 ± 0.3   |
| Croatia | 26.3 ± 0.3   | 70.2 ± 0.3   |
| Ghana   | 22.0 ± 0.3   | 63.6 ± 0.3   |
| Panama  | 21.4 ± 0.3   | 62.0 ± 0.3   |

### Closest and most-uncertain groups

- **Group A is the flattest of all.** Only **5.5 points** separate the favourite
  (South Korea 27.9%) from the fourth side (South Africa 22.4%). Four teams, four
  near-equal chances — a true toss-up group.
- **Groups I and C have the tightest race for first place** — the top two are
  split by just **0.6 of a point** (Norway 28.7 / Senegal 28.1; Haiti 28.1 /
  Morocco 27.5). Whoever tops these groups is essentially a coin-flip.
- **Group C is also notable for who is *not* favoured:** Brazil sits **third**
  (26.4%) behind Haiti and Morocco — a vivid example of the recent-form,
  no-market reordering from §1.
- **At the other extreme, Group H is the model's clearest:** Spain (36.0%) sits a
  full **10.7 points** clear of the next side (Cape Verde 25.3%) — and even that
  is far from a lock.

---

## 3. Marquee fixtures — the 1X2 split and the most likely scorelines

Five notable group games. Each shows the **1X2 split** (home win / draw / away
win), the **top-3 most likely exact scorelines** with their probabilities, and a
one-line read. All from the per-fixture files in `fixtures/`. Remember: "home/away"
is scheduling order only — these are neutral-venue games.

### Argentina v Algeria — 2026-06-16 (`fixtures/Argentina__Algeria__2026-06-16.json`)
- **1X2:** Argentina **36.7%** · Draw **32.4%** · Algeria **31.0%**
- **Top scorelines:** 0-0 (22.6%) · 1-0 (12.4%) · 0-1 (10.6%)
- *Read:* the model's #2 and #5 title contenders, and it has them all but level —
  Algeria's away win sits within 6 points of Argentina's. A genuine near-pick'em.

### Brazil v Morocco — 2026-06-13 (`fixtures/Brazil__Morocco__2026-06-13.json`)
- **1X2:** Brazil **31.5%** · Draw **32.5%** · Morocco **36.0%**
- **Top scorelines:** 0-0 (21.9%) · 0-1 (12.6%) · 1-0 (11.4%)
- *Read:* the model makes **Morocco the favourite over Brazil** — driven by
  Morocco's stronger defensive rating (latent defense +0.347 vs Brazil's +0.171,
  from `why.team_strength`). The clearest single illustration of form-Elo over
  reputation.

### Norway v Senegal — 2026-06-22 (`fixtures/Norway__Senegal__2026-06-22.json`)
- **1X2:** Norway **33.6%** · Draw **31.0%** · Senegal **35.4%**
- **Top scorelines:** 0-0 (21.1%) · 0-1 (12.3%) · 1-0 (11.3%)
- *Read:* two of the model's dark horses (overall #1 and #10) decide top spot in
  Group I, and it slightly favours **Senegal away** — the kind of near-even,
  high-quality match the flat field produces.

### France v Senegal — 2026-06-16 (`fixtures/France__Senegal__2026-06-16.json`)
- **1X2:** France **30.8%** · Draw **31.7%** · Senegal **37.5%**
- **Top scorelines:** 0-0 (21.0%) · 0-1 (12.2%) · 1-0 (11.2%)
- *Read:* the model makes **Senegal a clear favourite over France** (37.5% to
  30.8%) — Senegal's higher attack and defense ratings outrank France with no
  market to lift France's pedigree back up.

### Netherlands v Japan — 2026-06-14 (`fixtures/Netherlands__Japan__2026-06-14.json`)
- **1X2:** Netherlands **30.0%** · Draw **32.0%** · Japan **38.1%**
- **Top scorelines:** 0-0 (21.7%) · 0-1 (12.4%) · 1-0 (11.4%)
- *Read:* Japan (a top-4 title side) is favoured **away** against the Netherlands,
  carried by an exceptional defensive rating (latent defense +0.402, the strongest
  in this set).

### Why every modal scoreline is 0-0 (and that's correct)

Across **all 72 group fixtures**, the single most likely exact score is **0-0**,
and the top three are always some ordering of **0-0, 1-0, 0-1**. This is not a
glitch — it is the correct behaviour of a low-mean Dixon-Coles goal model:

- International matches are low-scoring. When each side's expected goals is around
  1, the most probable *single* exact score is genuinely 0-0, with 1-0 and 0-1
  just behind. The probability mass is spread thinly across many scorelines, so no
  single high-scoring line ever wins the "most likely" slot.
- A 0-0 being modal (~20–26% here) does **not** mean a draw is the most likely
  *outcome* — add up all the home-win scorelines and the home side can still be
  favoured. The modal *score* and the most likely *result* are different
  questions.
- This is the same shape a bookmaker's **correct-score market** shows: 0-0, 1-0
  and 0-1 routinely sit at the short end. The model reproducing it is a sign the
  goal distribution is right, not wrong.

---

## 4. What the model is honest about NOT knowing

A trustworthy forecast is explicit about its gaps. Two stand out, and the bundle
labels both:

- **No live edge / no CLV / no ROI — by funding, not by failure.** Every fixture
  in `schedule.json` and every fixture file carries an explicit
  `edge: { coverage_gap: true, reason: "no live edge for this fixture as-of
  cutoff" }`. This is deliberate: the entire odds/edge/CLV layer is a
  **NON-REAL synthetic-odds dry-run** (`meta.json` → `is_synthetic: true`). Real
  odds and a real edge sit behind a **separate, explicit funding approval** that
  has not been granted (`ASSUMPTIONS.md`, Phase 4 "build-and-gate odds posture").
  Until the feed is funded, there is **no real betting number anywhere in this
  bundle** — and this document makes no such claim.
- **Sparse xG coverage.** The model is **Elo-anchored with optional, sparse xG
  enrichment, not an xG-driven model** (`ASSUMPTIONS.md`). xG comes from a static,
  point-in-time StatsBomb Open Data snapshot and covers only a subset of matches;
  uncovered matches are flagged in a coverage gap set
  (`reports/phase1_statsbomb_coverage.md`). The forecast does not pretend to a
  richer xG signal than it has.

**The clean split to take away:**

| Layer | Needs odds? | Status in this bundle |
|-------|-------------|------------------------|
| Scorelines, 1X2, group/progression probabilities | No — model + 20k-sim only | **Real model output** (synthetic-odds *posture*, but the forecasts are genuine) |
| Edge / CLV / ROI / staking | Yes — real odds feed | **Coverage gap** — awaits separate funding approval |

So: trust the **football** here — who advances, who wins the group, the likely
scorelines, each carried with its uncertainty. Do **not** read any betting value
into it. There is none in this dry-run, and the bundle says so on every fixture.

---

*Sources, all under `data/dashboard/2026-06-07T000000Z/`: `meta.json`
(provenance, `n_sims`, synthetic banner), `tournament.json` (per-team
progression, `{value, se}`), `schedule.json` (group rows + knockout occupants),
`fixtures/<id>.json` (per-match 1X2, scoreline shortlist/grid, `why.team_strength`,
`edge`). Model framing: `ASSUMPTIONS.md`. Every figure is pulled from the bundle;
none is invented; each carries its Monte-Carlo SE or its full distribution.*
