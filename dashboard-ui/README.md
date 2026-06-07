# WC Dashboard UI

A read-only, signal-only viewer for the Plan-1 forecast/edge bundle. Every probability
renders WITH its uncertainty (the "no naked numbers" rule, structurally enforced by
`tests/no-naked-number.test.ts`). Nothing here is a control: the ¼-Kelly stake is a
read-only SIGNAL, never a bet affordance (enforced by `tests/e2e/smoke.spec.ts`).

## Scripts

- `npm run dev` — copy the bundle into `public/bundle/` and start Vite.
- `npm test` — vitest (unit + component + the no-naked-number guard).
- `npm run check` — svelte-check (types).
- `npm run e2e` — Playwright smoke (offline, against the synthetic fixture bundle).

## Known gaps / progressive

- **Ghosted sharp line in the WinBar** — spec §4 wants the de-vigged sharp 1X2 line
  "ghosted into the win-bar". `WinBar` already accepts an optional `line` prop and renders
  it naked-number-safely, but Plan-1's edge node emits only the scalar `edge` + `entry_odds`
  for the staked side (no de-vigged market 1X2), so `line` is currently UNFEEDABLE from the
  bundle and all surfaces pass model-only. v1 conveys the model-vs-market signal via the
  EdgeChip instead. Closing this needs a Plan-1 follow-up to emit the de-vigged market 1X2
  in the forecast/edge artifact — a data-layer change, intentionally out of scope here.
