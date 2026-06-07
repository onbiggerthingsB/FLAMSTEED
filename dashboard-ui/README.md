# WC Dashboard UI

A **read-only, signal-only** static viewer over the Plan-1 forecast/edge JSON bundles. It
renders pre-computed snapshots and **recomputes nothing** — no model runs in the browser, so
it is leakage-safe by construction. Every probability renders WITH its uncertainty (the "no
naked numbers" rule, structurally enforced by `tests/no-naked-number.test.ts`). Nothing here is
a control: the ¼-Kelly stake is a read-only SIGNAL, never a bet affordance (enforced by
`tests/e2e/smoke.spec.ts`).

**Posture: NON-REAL / dry-run.** v1 ships synthetic odds only. A persistent honesty bar at the
top of every surface shows the snapshot's as-of timestamp, the model/posterior version, and —
while the bundle is synthetic — an unmissable `DRY-RUN · SYNTHETIC ODDS · NOT REAL` chip. No
real odds are sourced, no bet is placed, and no number is a real CLV/ROI claim.

**Fail-safe honesty (the viewer does not trust the producer).** The NON-REAL chip is gated on
the authoritative `provenance.is_synthetic` flag, **not** on banner-presence — a synthetic
bundle with a missing/empty `banner` still shows the chip (with a hardcoded fallback string),
so it can never silently read as REAL. The on-screen claim is sourced from the producer's
banner when present, with a safe default otherwise. In the same spirit, the value components
degrade rather than crash on bad input: `CredibleInterval` renders `—` for a null/non-finite
value or a missing/degenerate CI (it never crashes the whole match-detail surface), and
`ScorelineGrid` degrades to a coverage gap for an empty / non-rectangular / all-zero grid
(never `NaN%` / divide-by-zero). `WinBar` clamps each visual segment to `max(0, v)` so a
non-normalized `one_x_two` can't paint a negative/oversized bar — a **visual-only** clamp that
never recomputes the probabilities (the data layer already gates sum≈1 + [0,1]).

## Stack

Dependency-light **Svelte 5 + Vite + TypeScript**. No UI kit, no CSS framework, no state
library — plain components, a hash router, and a small set of CSS tokens (`src/app.css`).

## Prerequisites

- **Node ≥ 20.11** (the bundle copier `scripts/copy-bundle.mjs` uses `import.meta.dirname`,
  Node 20.11+; pinned in `package.json` `engines`).
- `npm install` in this directory.

## Scripts

- `npm run dev` — copy the latest bundle into `public/bundle/`, then start Vite (HMR).
- `npm run build` — copy the bundle, then produce a static production build in `dist/`.
- `npm run preview` — serve the production build on port 4173.
- `npm run check` — `svelte-check` (TypeScript + Svelte type checking; the project keeps this
  at 0 errors / 0 warnings).
- `npm test` — Vitest: unit + component tests + the load-bearing no-naked-number guard.
- `npm run e2e` — Playwright NON-REAL smoke (offline, against the synthetic fixture bundle).

## How it gets data (`copy-bundle.mjs` → `public/bundle/`)

`dev`/`build`/`e2e` all run `scripts/copy-bundle.mjs` first, which populates `public/bundle/`:

1. If `../data/dashboard/<cutoff>/` dirs exist, it copies the **newest** one (selected by
   directory `mtime`, robust even if a future dir name is non-ISO).
2. Otherwise it falls back to the **committed synthetic fixture** at
   `tests/fixtures/bundle/`, so the app, tests, and e2e always have data offline.

To produce a fresh live bundle (from the repo root — note the console-script packaging gap,
so invoke the module directly):

```bash
PYTHONPATH=src uv run python -m wcmodel.dashboard.cli --dry-run
```

This writes a NON-REAL synthetic bundle under `data/dashboard/<cutoff>/`. `--no-dry-run`
**refuses** — the real feed is gated behind the funded pre-flip checklist and is not available
in v1.

## The bundle contract (the 5 artifacts + the envelope)

Each bundle dir is **stamped JSON only** (top-level `*.json` + a `fixtures/` dir). Every file
is an **envelope** `{ provenance, data }`, where `provenance` carries `as_of`, the
posterior/git version, `n_sims`, and — when synthetic — a `banner` (drives the DRY-RUN chip).
The TypeScript mirror of this contract lives in `src/lib/types.ts`.

| Artifact | Shape | Surface |
| --- | --- | --- |
| `schedule.json` | `{ group, knockout }` rows (group: forecast summary + edge node; KO: derived slot occupants `{team, prob, se}`) | Schedule (landing) |
| `tournament.json` | `team_progression` — `{value, se}` per market | Tournament progression |
| `track.json` | `track_record` (CLV / RPS / reliability) or an honest `coverage_gap` | Track record |
| `meta.json` | markets + provenance note | (header + column order) |
| `fixtures/<match_id>.json` | the full gated `fixture_forecast` + match-detail "why" + edge node | Match detail (fetched on drill-down) |

## The no-naked-number grammar

Every probability-shaped token (`45%`, `6.9%`) must sit inside one of three conscious markers,
or the guard fails:

- **`data-uncertainty`** — the estimate carries its `±` companion (`Estimate` /
  `CredibleInterval`), OR the distribution IS the uncertainty (`WinBar` / `ScorelineGrid` /
  `ScorePill`, `data-uncertainty="distribution"`).
- **`data-coverage-gap`** — an honest gap ("insufficient coverage"), never a number.
- **`data-derived`** — the **reviewed exemption** for NON-FORECAST numbers only: derived
  signals (the EdgeChip's edge %, the ¼-Kelly stake signal, entry odds) and backward-looking
  performance (the Track record). These are not posteriors, so they carry no `±` by design.
  A forward-looking forecast may **never** use `data-derived` — every new use is a manual
  review checkpoint, not a free pass.

The guard (`tests/no-naked-number.test.ts`) also catches `%`s smuggled into `title` /
`aria-label` attributes, and its non-vacuity block proves it has teeth (it must catch a
deliberately-naked `<span>45%</span>`). Coverage now includes the **composed `App` shell** (over
the fixture bundle) and the **`HonestyBar`** — so the honesty bar / banner is no longer an
unguarded blind spot; a future `%` leaked into the bar (visible OR in a `title` attr) is caught.
The NON-REAL e2e (`tests/e2e/smoke.spec.ts`) visits **every route** — Schedule, the match
detail, **Tournament, and Track** — asserting the NON-REAL banner persists and there is no
bet/stake/buy/order affordance on any of them.

## Known gaps / progressive

- **Ghosted sharp line in the WinBar** — spec §4 wants the de-vigged sharp 1X2 line
  "ghosted into the win-bar". `WinBar` already accepts an optional `line` prop and renders
  it naked-number-safely, but Plan-1's edge node emits only the scalar `edge` + `entry_odds`
  for the staked side (no de-vigged market 1X2), so `line` is currently UNFEEDABLE from the
  bundle and all surfaces pass model-only. v1 conveys the model-vs-market signal via the
  EdgeChip instead. Closing this needs a Plan-1 follow-up to emit the de-vigged market 1X2
  in the forecast/edge artifact — a data-layer change, intentionally out of scope here.
- **Progressive (spec §7), out of scope for v1:** the bracket-tree visualization, the rich
  team-strength posterior drill-down, deeper calibration views, provenance/version detail
  panels, and the real-feed flip (gated on the funding-flip checklist). The viewer is
  feed-agnostic: flipping to a real feed is a data-layer change, not a UI change.
