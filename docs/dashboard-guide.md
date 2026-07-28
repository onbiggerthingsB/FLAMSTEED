# Dashboard operator guide

A plain-language walkthrough of every element in the forecasting dashboard, written
for the system's owner. The numbers shown as examples are the **real values from the
current staged bundle** (`as_of 2026-06-10T00:00:00Z`, posterior `e45d051e8e68d492`,
model `76adff1`, 20,000 sims). Your screen should match these until the next nightly
update moves them.

This guide was written by reading the actual Svelte sources in `dashboard-ui/src/`,
not from memory. Where it names a rule, that rule lives in code.

---

## 1. The three tabs and their three separate clocks

The nav bar has three destinations (`src/App.svelte`):

- **Value Bets** — the primary tab. The +EV betting board.
- **Track Record** — backward-looking performance (CLV, calibration).
- **Forecast** — the model surfaces (schedule, tournament, match detail). Deliberately
  demoted in the nav with the inline note *"independent forecast — does NOT beat the
  market."* It is kept for interest, not as a betting edge.

**These three tabs run on three independent clocks. This is the single most important
thing to understand about freshness.**

| Tab | Its clock | Where it shows |
|---|---|---|
| Forecast | the **bundle `as_of`** | the honesty bar at the very top: *"as of 2026-06-10T00:00:00Z"* |
| Value Bets | the **scan `scan_ts`** | the scan-meta line: *"last scanned …"* |
| Track Record | **fills as logged bets settle** | the `n_bets` count and CLV stats |

The Forecast `as_of` and the Value `scan_ts` are produced by **different jobs at
different times** and loaded as **independent artifacts** (`App.svelte` loads the value
bundle and the model bundle in two separate, fire-and-forget async calls — one failing
cannot take down the other).

> **A days-old Value timestamp says NOTHING about Forecast freshness, and vice versa.**
> The current bundle illustrates exactly this: the Forecast bundle is `as_of`
> 2026-06-10, while the Value scan is `scan_ts` **2026-06-09T04:55:13Z** — about a day
> older. That is not a bug. The two clocks are simply independent. Read each tab's own
> timestamp; never infer one from the other.

---

## 2. Forecast tab

The Forecast group is secondary by design. Every Forecast screen opens under the
italic label *"Independent forecast — does NOT beat the market; kept for interest
only."*

### The win/draw/win bar (`WinBar.svelte`)

Each fixture leads with a horizontal three-segment bar — home (accent), draw (grey),
away (green) — with a legend reading e.g. `H 78% · D 16% · A 6%`. **The distribution
itself is the uncertainty.** The whole bar + legend sit inside one
`data-uncertainty="distribution"` region, so the percentages are an honest readout of a
distribution, not bare point estimates. (Tomorrow's first fixture, Mexico v South
Africa, reads exactly **H 78.2% / D 15.6% / A 6.1%**.)

If a fixture also carries a de-vigged sharp market line, a faint white **ghost marker**
is overlaid on the bar showing where the market splits — the model vs the line, side by
side. Most group fixtures have **no** ghost line (no live edge as-of cutoff); that is
normal.

### What "± se" means and the no-naked-numbers grammar

The project's core rule is **"no naked numbers."** It is enforced structurally — there
is a test (`tests/no-naked-number.test.ts`) that fails the build if any probability-
shaped token renders outside one of three conscious markers:

- **`data-uncertainty`** — an estimate carrying its **± companion** (the `Estimate`
  component renders `value ±se`, e.g. `96% ±0.1`), **or** a distribution that *is* the
  uncertainty (the WinBar, the scoreline grid, the score pills).
- **`data-coverage-gap`** — an honest gap that renders the italic text *"insufficient
  coverage,"* never a fabricated number.
- **`data-derived`** — a conscious non-forecast number: the edge %, the ¼-Kelly stake
  signal, the backward-looking Track stats. These are signals/performance, not model
  posteriors, so they are **explicitly** exempt — never by accident.

The `±se` you see (e.g. on champion or advance numbers) is the **Monte-Carlo standard
error** of that estimate, in percentage points. It tells you how much the number would
wobble if the 20,000-simulation run were repeated — it is sampling noise, not model
uncertainty about the world. A small `±se` (0.1–0.4) just means the simulation has
settled. The grammar module (`src/lib/format.ts`) guarantees a value never prints
alone: if the SE is genuinely missing it renders `±?` (explicit unknown), never a
silent bare number.

### The scoreline grid + most-likely score — and its honest ceiling

Each match-detail page (Forecast → a fixture → *detail →*) shows a **most-likely score**
plus a top-3 shortlist (the `ScorePill` unit: `2–0 · 15%`), and a full **scoreline
grid** heat-map (`ScorelineGrid.svelte`, away goals across, home goals down, cells
shaded by probability).

> **Read the most-likely % honestly.** Even a *perfect* model's single modal exact
> score lands only around **~10–13%**, because the probability is spread across dozens of
> plausible scorelines. Tomorrow's fixtures show this exactly: Mexico v South Africa's
> most-likely score is **2–0 at 15.0%**, and South Korea v Czech Republic's is **1–1 at
> 11.7%**. A "low" most-likely percentage is **expected, not a defect** — it is what a
> well-spread scoreline distribution looks like. The shortlist exists precisely so you
> never mistake one modal score for a confident prediction.

### The "why" panel

On a match-detail page, the **Why** card opens the model up (`MatchDetail.svelte`):

- **team strength** — attack and defense as a value with a 94%-HDI **credible
  interval** (`CredibleInterval`: `1.32 [1.10, 1.55] (94% HDI)`). This is genuine
  posterior uncertainty about a parameter, shown as an interval rather than a ±.
- **xG**, **rest days** — context inputs, shown as plain data or an honest gap.
- **recent results** — raw match history, explicitly labeled *"data, not a forecast."*

Any of these rows can render a **coverage gap** instead of a number if the input is
missing.

### CoverageGap nodes — anywhere they appear

A **CoverageGap** node (`CoverageGap.svelte`) renders the muted italic text
*"insufficient coverage"* with the underlying reason on hover. It appears wherever a
surface has **no honest number to show** — a fixture with no forecast, a missing xG, a
knockout slot with no probable occupants, an empty scoreline grid, or a value market
with no sharp line. **It is a feature, not an error:** the dashboard refuses to
fabricate a number when it lacks the data, and says so plainly. Seeing a coverage gap
means "we don't have this," never "something broke."

On the Forecast schedule, each upcoming fixture also carries an **edge chip**; before
kickoff most read a coverage gap (`"no live edge for this fixture as-of cutoff"`) —
expected, because the model is not the betting edge.

### The tournament / bracket view

Forecast → Tournament (`Tournament.svelte`) is a progression table: one row per team,
columns running shallow→deep — **Win group · Advance · R16 · QF · SF · Final ·
Champion** — each cell an `Estimate` (`value ±se`). The columns preserve the
**coherence chain**: advance ≥ reach-R16 ≥ … ≥ champion always holds, read left to
right. Teams are sorted by champion probability, so the favorites sit at the top
(currently Argentina, Spain, Brazil…). Below the table, a **Bracket tree** lays out
R32→Final with each slot's probable occupants drawn from the group-placing markets;
slots with no resolved feeder show a coverage gap.

---

## 3. What changes after a nightly update

When the overnight job runs and you reload:

- The honesty-bar **`as_of` advances** to the new timestamp. (Only this clock; the
  Value `scan_ts` and Track fills move on their own schedules.)
- Matches that have **been played render as fixed results** — the schedule row's
  `status` flips to `played` and the row dims to ~55% opacity (`Schedule.svelte`,
  `.row[data-status="played"]`). A played match is a settled fact, not a forecast.
- **Conditioned numbers move.** Once a group result is known, every downstream
  probability that was conditioned on it updates: the group table, advance-from-group,
  and the deeper bracket markets all shift. The "next up" anchor (the accent-tinted left
  edge and the *next up* tag) advances to the next still-upcoming fixture.

Group A is the baseline to watch tomorrow, since both 2026-06-11 fixtures are Group A
matches — those results will be the first to move the advance numbers in §"What you
should see."

---

## 4. Value Bets tab

The primary tab (`ValueBets.svelte`). It is **market-vs-market**: it flags where a
**soft book** offers a better price than the de-vigged **sharp** line (Pinnacle). It is
**signal-only** — there is no bet, stake, or order control anywhere (see §6).

The top shows the **NOT-REAL banner** (see §5) and a scan-meta line: *last scanned ·
sharp book · regions · credits used (remaining).* Current scan: **scan_ts
2026-06-09T04:55:13Z**, sharp = pinnacle, regions us,uk,eu.

### Every column in the bettable table

| Column | What it is |
|---|---|
| **event** | the fixture, "Home v Away." |
| **market** | the market (e.g. `h2h`), plus the line for totals. |
| **pick** | the side this spot is on (a team, or Draw). |
| **edge** | the **derived** edge signal (model-implied vs de-vigged line), an `EdgeChip` like `▲ +6.9%`. Derived, not a posterior — exempt from the ± rule, tagged NON-REAL when synthetic. |
| **book** | the **soft** book offering the price. |
| **odds** | the soft book's **decimal odds** (market data, 2dp — not a probability, so no ±). |
| **fair** | the de-vigged **sharp fair %** — the market's own no-vig probability, a derived datum. |
| **model** | the **model second opinion** (see below). |
| **¼-Kelly stake** | a read-only **suggestion** — what fraction of bankroll a quarter-Kelly stake would be. A signal, never an instruction (`stakeSignal`). |
| **freshness** | how stale the quote is, as a human age ("12m ago"), from the quote's `last_update` vs the scan time. Edges evaporate in minutes — **always re-check at bet time.** |
| **kickoff** | the fixture's commence date. |

### The model second-opinion column — read this carefully

This column (`ModelCell.svelte`, `modelSecondOpinion.ts`) shows what **our independent
forecast** thinks of the **same** outcome the pick names, then compares it to the sharp
fair %. It is **display-only context** — it is computed by a one-way read-side join into
the already-loaded forecast bundle and is **fed nowhere near the edge or the bettable
decision.** A missing forecast simply renders "—"; it can never change which spots are
bettable.

The emphasis is deliberately asymmetric:

- **Agreement is weak evidence.** Our model systematically over-rates underdogs, so it
  "agrees" with almost any underdog value pick. Agreement is rendered **quietly** —
  muted *"model X% · in line,"* no celebratory badge.
- **⚠ Disagreement is the meaningful signal.** When the model rates the pick **below**
  the market, that is a genuine caution flag and gets a prominent amber **⚠** badge
  (*"caution: below the market"*). **That warning is the column's whole point** — agreement
  is near-noise; disagreement is the thing to notice.

### Filtered (and why)

Below the bettable table, a collapsible **"Filtered (and why)"** section lists every
spot that was rejected, each tagged with the **guard flag(s)** that excluded it. Nothing
is hidden — you can see what was thrown out and the exact reason. (The board is honest
about its own rejections, not just its picks.)

### Coverage gaps (Value)

A separate section lists events/markets with **no sharp Pinnacle line.** No sharp truth
⇒ no claim — these are never fabricated into an edge, just shown as honest gaps.

### The six guards

A spot is **bettable only if NO guard fires** (`src/wcmodel/value/scanner.py`,
`classify_edge` — read-only; the scanner is not modified by this guide). The six guard
flags:

1. **`non_soft`** — the price is not from a configured soft book (we only beat soft books).
2. **`below_min`** — the edge is below the minimum edge threshold (`edge_min`).
3. **`too_good`** — the edge is implausibly large (`> too_good`); a "too good to be true"
   price is almost always a stale/wrong line, not free money.
4. **`fragile`** — the odds are a longshot (`> longshot_odds`); high-variance, fragile edge.
5. **`stale`** — the quote is older than `stale_seconds` (a missing timestamp **fails
   open** — surfaced, not swallowed, because you re-verify at bet time).
6. **`both_sides`** — the book is +EV on **every** leg of the full market, which signals a
   stale de-vig rather than a real edge.

---

## 5. The NOT-REAL / DRY-RUN banner

The current bundle is **synthetic** (`is_synthetic: true`). The honesty bar shows a
warning chip and the Value tab shows a prominent banner:

> *DRY-RUN · SYNTHETIC ODDS · NOT REAL — no real odds were sourced, no bet was placed,
> and no number here is a real CLV/ROI claim.*

The chip is gated on the authoritative `is_synthetic` flag, **not** on the banner text
(`HonestyBar.svelte`, "FIX A"): even if the producer emitted no banner string, a
synthetic bundle still shows a hardcoded NOT-REAL chip. It **can never silently read as
real.**

**What the banner taints:** the **betting-side** claims — the odds feed is unfunded /
synthetic, so every **edge, CLV, and ROI** number is not a real-money claim. Do not
treat any value-board edge or track CLV as a funded result while this banner is up.

**What the banner does NOT mean:** the **forecast percentages are real model output.**
The 20,000-sim posterior — win/draw/win, champion, advance, the scoreline grid — is the
genuine model. The banner is about the **odds/betting** side, not the model's forecast.

---

## 6. What the dashboard does NOT do

- **No live in-game updating.** The forecast moves only at the nightly update; nothing
  ticks during a match. A played match renders as a fixed result, not a live feed.
- **No bet placement.** The Value tab is signal-only: there is **no bet, stake, or order
  control of any kind.** The ¼-Kelly number is a read-only suggestion. This is enforced
  by test — `tests/components/valuebets.test.ts`, *"NO bet / stake / order CONTROL
  exists — the surface is signal-only"* — which asserts there is no `<button>`, no
  `<input>`, no `<form>`, and none of the strings "place bet" / "submit bet" / "order
  ticket" anywhere in the rendered surface.

---

## The operator's 60-second daily freshness check

1. **Top bar — Forecast clock.** Read *"as of …"*. After an overnight run it should be
   today's date (currently `2026-06-10T00:00:00Z`). If it did not advance, the nightly
   forecast job did not land — investigate the job, not the dashboard.
2. **Top bar — NOT-REAL chip.** If the DRY-RUN / SYNTHETIC chip is showing, you are on a
   synthetic bundle: forecasts are real, **betting numbers are not.** Treat edges/CLV as
   illustrative only.
3. **Forecast → Schedule.** Confirm yesterday's matches now read `status: played` (dimmed)
   and the *next up* anchor sits on the right upcoming fixture. Glance that the conditioned
   group/advance numbers moved as expected.
4. **Value Bets — its own clock.** Read *"last scanned …"* (currently
   `2026-06-09T04:55:13Z`). This is the **Value** clock and is **independent** of the
   Forecast clock — a stale scan here says nothing about forecast freshness. If you need
   fresh edges, the scan, not the forecast, is what must be re-run.
5. **Value Bets — the ⚠ column.** Scan the model column for amber **⚠** caution badges
   (model rates the pick below the market). Agreement is weak; a ⚠ is the real flag.
6. **Track Record — fills.** Check `n_bets` and beat-close rate. This clock advances only
   as logged bets settle — independent of both clocks above.

Three clocks, three jobs. Read each tab's own timestamp; never infer one from another.

> **RPS scale boundary — 2026-07-28 (OA finding 16).** The Track tab's *"RPS vs
> baselines"* numbers (`track.rps.{model,market,elo}`) are now the canonical
> ÷2-normalized RPS in `[0, 1]`. Bundles built before that date hold the old
> unnormalized `[0, 2]` values, so the **first rebuild after it halves all three
> displayed numbers** — a unit change, not an accuracy gain; the deltas and the
> model/market/elo ordering are unchanged. Do not compare a post-rebuild Track RPS
> against a screenshot or archived bundle from before the boundary. The schema guard
> bounds these at `[0, ∞)` and will not flag the shift. The public site's live
> scorecard figures are on the canonical scale already and are unaffected.
