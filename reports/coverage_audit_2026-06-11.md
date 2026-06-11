# Coverage Audit — "insufficient coverage" badges (WC-2026 dashboard)

**Date:** 2026-06-11
**Branch / worktree:** `chore/coverage-audit` @ `e60ebce` (worktree `~/Desktop/wc-coverage`, pinned at `main e60ebce`)
**Cutoff:** `2026-06-10T00:00:00Z` (matches the staged bundle's `provenance.as_of`)
**Mode:** READ-ONLY. Only write is this report. Zero ingestion, zero data-layer writes, zero installs, zero paid API calls.

---

## 0. TL;DR

- The dashboard's operator-visible **"insufficient coverage"** badge is a single dumb component
  (`CoverageGap.svelte`) that renders the literal string for **any** `coverage_gap` node, keyed
  only on its `reason` prop. There is no per-team count or window in the badge itself.
- The data layer emits **several distinct `coverage_gap` reasons**. Exactly **one** is
  per-team / windowed: `_recent_form` (last-`n=5` played matches as-of cutoff). Its only trigger
  is **zero** valid-played matches as-of cutoff.
- **Empirically, that recent-form condition fires for 0 / 48 WC-2026 teams.** Every team has
  hundreds of valid-played internationals as-of `2026-06-10T00:00:00Z` (min **235** = Cape Verde,
  max **1101** = Sweden). The staged bundle confirms it: 144 / 144 fixture-sides carry an OK
  `recent_form` (5 matches each); **0 gapped**.
- The badges the operator actually sees are **structural per-fixture gaps**, not a history
  shortage: xG-not-covered, rest-days-unknown-for-unplayed-fixture, no-live-edge, no-sharp-line.
  These are intrinsic to forecasting *future* fixtures, not curable by adding historical results.
- **Therefore: neither candidate dataset clears any badge. (a) clears 0/48, (b) clears 0/48.**

---

## 1. The badge trigger — quoted from source

### 1.1 UI: one component, one literal, fed by `reason`

`dashboard-ui/src/components/CoverageGap.svelte:4`:

```svelte
<span class="gap" data-coverage-gap title={reason}>insufficient coverage</span>
```

The component (`dashboard-ui/src/components/CoverageGap.svelte:1-7`) takes a single `reason`
prop and **always** prints `insufficient coverage`; the `reason` is only the hover `title`.
Every surface that renders a gap passes a `reason` straight through:

- `surfaces/MatchDetail.svelte:65-86` — xG (home/away), rest (home/away), recent-form entries, edge.
- `surfaces/Schedule.svelte:54,86,105` — forecast_summary, edge, KO occupants.
- `surfaces/ValueBets.svelte:139` — value coverage gaps (no sharp line).
- `surfaces/Track.svelte:22` — whole track surface when no backtest records.
- `components/BracketTree.svelte:73-75`, `components/ScorelineGrid.svelte:58`.

The canonical data-layer constructor is `dashboard/schema.py:116-118`:

```python
def coverage_gap(reason: str) -> dict:
    """An explicit coverage gap (thin/absent data) — NEVER a fabricated number."""
    return {"coverage_gap": True, "reason": reason, "value": None}
```

### 1.2 ALL `coverage_gap` reasons emitted by the data layer (enumerated)

| # | reason string | source (file:line) | per-team? | windowed? | exact condition | UI element |
|---|---|---|---|---|---|---|
| R1 | `no played history as-of cutoff` | `dashboard/build.py:290,295,305` (in `_recent_form`, def at `:269`) | **YES** | **YES** (last `n=5` played, `date<=cutoff`) | team has **0** valid-played matches as-of cutoff | MatchDetail recent-form |
| R2 | `xg not StatsBomb-covered for this fixture` | `dashboard/why.py:37` (via `_fixture_why._xg_node`, `build.py:331-344`) | per-fixture-side | no | this exact `(team,opp,date)` not in StatsBomb xG read | MatchDetail xG |
| R3 | `xg missing` | `dashboard/why.py:39` | per-fixture-side | no | covered but xG value null | MatchDetail xG |
| R4 | `rest_days unknown for an unplayed fixture` | `dashboard/build.py:352,359` (`_rest_days`) | per-fixture-side | no | this fixture identity has no PLAYED row in features frame | MatchDetail rest |
| R5 | `rest_days null as-of cutoff` | `dashboard/build.py:361` | per-fixture-side | no | played row exists but rest_days null | MatchDetail rest |
| R6 | `no live edge for this fixture as-of cutoff` | `dashboard/build.py:608` (also `:606` `no forecast for this fixture`) | per-fixture | no | no edge node for this event key | Schedule/MatchDetail edge |
| R7 | `feeder {ref} resolves from a later match` | `dashboard/build.py:415` | per-KO-slot | no | KO feeder ref (W74/L101…) not yet resolved | BracketTree / Schedule occupants |
| R8 | `no backtest records supplied` | `dashboard/build.py:638` | global | no | track-record build got no backtest rows | Track surface |
| R9 | `no sharp ({sharp_book}) line` | `value/scanner.py:103` | per-market | no | no Pinnacle line for that event/market/line | ValueBets coverage gaps |

`_recent_form`'s windowed query (`build.py:269,291-306`), quoted:

```python
def _recent_form(results, team: str, *, cutoff, n: int = 5) -> dict:
    ...
    played = valid_played_results(results)                       # :291
    mask = (played["home_team"] == team) | (played["away_team"] == team)  # :292
    mine = played.loc[mask].copy()
    if mine.empty:
        return coverage_gap("no played history as-of cutoff")    # :295
    ...
    mine = mine[pd.to_datetime(mine["date"]).dt.tz_localize(None).dt.normalize() <= cut]  # :303
    if mine.empty:
        return coverage_gap("no played history as-of cutoff")    # :305
    mine = mine.sort_values("date").tail(n)                      # :306  (n=5)
```

**KEY:** `_recent_form` has **no minimum-count threshold > 0**. It takes `tail(5)` but never gaps
for "fewer than 5". The *only* gap is **count == 0** (no played history as-of cutoff). So the
effective badge threshold for the one team-windowed condition is **count >= 1**.

### 1.3 Which reason drives the operator-visible badge?

All R1–R9 render the identical "insufficient coverage" string, so all are "the badge" textually.
But evidence from the **staged bundle** (`dashboard-ui/public/bundle`, `as_of=2026-06-10T00:00:00Z`)
shows which actually appear:

```
 144  no live edge for this fixture as-of cutoff          (R6)
 144  xg not StatsBomb-covered for this fixture           (R2)
 144  rest_days unknown for an unplayed fixture           (R4)
  34  feeder W*/L* resolves from a later match            (R7; 1 each, 32 KO slots)
   1  no backtest records supplied                        (R8)
  83  no sharp (pinnacle) line  (value.json)              (R9)
   0  no played history as-of cutoff                      (R1)  <-- recent_form NEVER fires
```

144 = 72 group fixtures × 2 sides. **R1 (recent_form) does not appear at all.** The visible
badges are R2/R4/R6/R9 — all structural to forecasting *future* fixtures (StatsBomb is historical
and per `(match_id,team)`, so a 2026 fixture is never xG-covered; `features.build(cutoff)` drops
unplayed rows, so rest_days always gaps; no live odds in dry-run ⇒ no edge / no sharp line).
**None of these is a "not enough match history" condition.**

---

## 2. Gap table — all 48 WC-2026 teams (badge-driving windowed condition R1)

Computed by assembling a TEMP `BitemporalStore` exactly as `daily_update.step_ingest`
(`scripts/daily_update.py:187-222`): fresh tempfile-dir store, `load_results(store,
cache_dir=~/worldcup/data/cache)` at the pinned martj42 commit
`6b6f8e9f321414957cc17861d8c2dbf25c4437b0` (cache hit, no network, no prod write). Then read
`results` `cutoff=2026-06-10T00:00:00Z` and mirror `_recent_form`'s own filters exactly:
`valid_played_results` → team home/away mask → `date<=cutoff`. **Count = valid-played matches
as-of cutoff. Threshold = 1 (gap iff count == 0). Badge = "YES" iff count < threshold.**

Raw results rows read as-of cutoff: **49,378**.

All 48 teams, in `config/tournament_2026.yaml` order:

| # | Team | count | thr | badge | # | Team | count | thr | badge |
|--:|---|--:|--:|:--:|--:|---|--:|--:|:--:|
| 1 | Mexico | 1003 | 1 | no | 25 | Belgium | 853 | 1 | no |
| 2 | South Africa | 480 | 1 | no | 26 | Egypt | 756 | 1 | no |
| 3 | South Korea | 1007 | 1 | no | 27 | Iran | 612 | 1 | no |
| 4 | Czech Republic | 360 | 1 | no | 28 | New Zealand | 416 | 1 | no |
| 5 | Canada | 469 | 1 | no | 29 | Spain | 783 | 1 | no |
| 6 | Bosnia and Herzegovina | 283 | 1 | no | 30 | Cape Verde | 235 | 1 | no |
| 7 | Qatar | 635 | 1 | no | 31 | Saudi Arabia | 740 | 1 | no |
| 8 | Switzerland | 884 | 1 | no | 32 | Uruguay | 970 | 1 | no |
| 9 | Brazil | 1059 | 1 | no | 33 | France | 935 | 1 | no |
| 10 | Morocco | 617 | 1 | no | 34 | Senegal | 637 | 1 | no |
| 11 | Haiti | 510 | 1 | no | 35 | Iraq | 654 | 1 | no |
| 12 | Scotland | 851 | 1 | no | 36 | Norway | 872 | 1 | no |
| 13 | United States | 790 | 1 | no | 37 | Argentina | 1068 | 1 | no |
| 14 | Paraguay | 783 | 1 | no | 38 | Algeria | 616 | 1 | no |
| 15 | Australia | 581 | 1 | no | 39 | Austria | 860 | 1 | no |
| 16 | Turkey | 642 | 1 | no | 40 | Jordan | 485 | 1 | no |
| 17 | Germany | 1031 | 1 | no | 41 | Portugal | 694 | 1 | no |
| 18 | Curaçao | 385 | 1 | no | 42 | DR Congo | 523 | 1 | no |
| 19 | Ivory Coast | 636 | 1 | no | 43 | Uzbekistan | 354 | 1 | no |
| 20 | Ecuador | 591 | 1 | no | 44 | Colombia | 638 | 1 | no |
| 21 | Netherlands | 879 | 1 | no | 45 | England | 1089 | 1 | no |
| 22 | Japan | 790 | 1 | no | 46 | Croatia | 396 | 1 | no |
| 23 | Sweden | 1101 | 1 | no | 47 | Ghana | 671 | 1 | no |
| 24 | Tunisia | 678 | 1 | no | 48 | Panama | 539 | 1 | no |

**Teams with badge (count == 0): 0 / 48.** min=235 (Cape Verde, #30), max=1101 (Sweden, #23).
Cross-check: staged bundle has 144/144 fixture-sides with OK `recent_form` (5 matches each),
**0 gapped** — consistent with the store query.

---

## 3. Candidate datasets — would either clear any badge?

### (a) Kaggle "World Cup Complete Dataset: 1930-2026" — WC matches ONLY

- **Download-verification: HELD — no auth.** `which kaggle` → not found; `~/.kaggle/kaggle.json`
  → missing. Per instructions, no account/credential creation; reasoning-based assessment follows.
- WC-finals matches are already inside martj42's coverage (martj42 = all internationals incl.
  World Cups). So (a) is a strict subset, by tournament, of what is already ingested.
- The badge-driving windowed condition (R1) is about **recent** play and already passes for all
  48 teams off martj42 alone. A WC-only **historical** dataset adds matches that are (i) already
  present and (ii) old — it cannot raise any team from count 0, because **no team is at 0**.
- The visible badges (R2 xG / R4 rest_days / R6 edge / R9 sharp line) are not about result
  history at all — a results dataset of any kind cannot supply StatsBomb xG, rest-day features
  for *unplayed* fixtures, live edges, or sharp odds.
- **Teams whose badge would clear if (a) ingested: 0 / 48.** (none)

### (b) Kaggle martj42 "International football results, 1872-present" — all internationals

- **Download-verification: HELD — no auth** (same kaggle/auth absence as above).
- **Identity established from repo source.** `src/wcmodel/data/sources/results.py:1` —
  *"martj42/international_results adapter."* — and `:36-37` fetch from
  `https://raw.githubusercontent.com/martj42/international_results/{commit}/...`, pinned at
  `MARTJ42_COMMIT = "6b6f8e9f321414957cc17861d8c2dbf25c4437b0"` (`:30`, bumped 2026-06-09, GitHub
  master sha, "to ingest results through today before WC-2026 kickoff"). The Kaggle martj42
  listing is a **mirror of this same upstream project**. This repo already ingests it from the
  GitHub source.
- Ingesting the Kaggle mirror adds **nothing beyond a possible recency delta** (the GitHub pin
  already carries rows through ~2026-06-08/09; a Kaggle snapshot could be staler or marginally
  fresher, with no as-of provenance). Even a few extra recent rows cannot clear R1 (every team is
  already at hundreds, not 0) and cannot touch R2/R4/R6/R9.
- **Teams whose badge would clear if (b) ingested: 0 / 48.** (none)

### Why neither helps (the load-bearing point)

The operator-visible badges are **forward-looking structural gaps** for fixtures that have not
been played: no StatsBomb xG for a 2026 match, no rest-day feature for an unplayed fixture, no
live edge / no sharp odds in the dry-run bundle. They are honest "we don't fabricate" markers,
**not** symptoms of thin historical coverage. The one genuinely history-driven, per-team,
windowed condition (`_recent_form`, R1) already passes for all 48 teams off the existing martj42
ingest. Adding more historical results — whether WC-only (a) or the martj42 mirror (b) — moves no
team off a badge.

---

## 4. Provenance / write-discipline confirmation

- Worktree verified: `git rev-parse HEAD` = `e60ebced7c5a91523139959a91a27a30410b68de` (e60ebce);
  `git branch --show-current` = `chore/coverage-audit`.
- All reads on the production tree (`~/worldcup/data/cache`,
  `dashboard-ui/public/bundle`) were read-only; the temp store was a `tempfile.mkdtemp` dir.
- `THE_ODDS_API_KEY` never read or printed; no Odds-API calls.

---

both candidates are snapshot datasets with no as-of provenance; ingestion design has bitemporal implications and is a prereg item requiring my authorization.
