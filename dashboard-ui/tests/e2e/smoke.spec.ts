// T10 NON-REAL e2e smoke — fast, deterministic, offline (synthetic fixture bundle).
//
// Load-bearing honesty invariants for a signal-only / paper dashboard:
//   (a) the persistent DRY-RUN / NON-REAL banner is visible on load;
//   (b) there is NO bet / stake / buy / order BUTTON or form affordance anywhere —
//       the stake is a read-only SIGNAL, not a control (signal-only is absolute);
//   (c) drill-down into the REAL-EDGE match detail works AND the same no-affordance
//       invariant holds on that edge-bearing detail page (where the edge + ¼-Kelly
//       stake actually render — the most likely place a bet control would creep in)
//       AND the NON-REAL banner persists.

import { test, expect, type Page } from '@playwright/test';

const BANNER = /DRY-RUN · SYNTHETIC ODDS · NOT REAL/;
// The fixture row that carries a REAL edge / stake / entry-odds (see tests/fixtures/bundle/schedule.json).
// The FIRST group row (Brazil v Argentina) is an edge-coverage-GAP fixture, so drilling
// the first link would never cover the MatchDetail that renders the edge + ¼-Kelly stake.
const REAL_EDGE_ID = 'Brazil__Mexico__2024-05-02';

async function waitForApp(page: Page) {
  // The app loads the bundle async; the banner only renders once provenance is in.
  await expect(page.getByText(BANNER)).toBeVisible();
}

// The signal-only invariant, factored out so it is enforced IDENTICALLY on the homepage
// AND on the edge-bearing detail page: no interactive affordance that places/sizes/stages
// a bet, and the stake signal (if present) is a read-only readout with no interactive ancestor.
async function assertNoBetAffordance(page: Page) {
  // No actionable control (button or link styled as an action) that places/sizes a bet.
  const betButtons = page.getByRole('button', { name: /bet|buy|order|stake|place|wager/i });
  await expect(betButtons).toHaveCount(0);
  const betLinks = page.getByRole('link', { name: /bet|buy|order|stake now|place|wager/i });
  await expect(betLinks).toHaveCount(0);

  // Defensive: no <form>, no submit/checkout inputs, no commerce-shaped controls at all.
  await expect(page.locator('form')).toHaveCount(0);
  await expect(page.locator('button[type="submit"], input[type="submit"]')).toHaveCount(0);
  await expect(
    page.locator('[role="button"]').filter({ hasText: /bet|buy|order|stake|place|wager/i }),
  ).toHaveCount(0);

  // The stake signal, if present, is plain text (read-only), not an interactive control.
  const stakeText = page.getByText(/¼-Kelly stake signal/);
  if (await stakeText.count()) {
    await expect(stakeText.first()).toBeVisible();
    // Its nearest interactive ancestor (if any) must not be a control — a read-only SIGNAL.
    const isControl = await stakeText.first().evaluate((el) => {
      const ctrl = el.closest('button,[role="button"],a[href],input,form');
      return ctrl !== null;
    });
    expect(isControl, 'stake signal must be a read-only readout, not a control').toBe(false);
  }
}

test('(a) the NON-REAL honesty banner is visible on load', async ({ page }) => {
  await page.goto('/');
  await waitForApp(page);
});

test('(b) there is NO bet/stake/buy/order action affordance on the homepage', async ({ page }) => {
  await page.goto('/');
  await waitForApp(page);
  await assertNoBetAffordance(page);
});

test('(c) drill into the REAL-EDGE match detail: edge + stake render, NO bet affordance, banner persists', async ({
  page,
}) => {
  await page.goto('/');
  await waitForApp(page);

  // Drill into the REAL-EDGE row specifically (Brazil v Mexico) — NOT the first row, which is
  // an edge-coverage-gap fixture. Click that row's detail link by its #/match/<id> href.
  await page.locator(`a[href="#/match/${REAL_EDGE_ID}"]`).click();

  // The match-detail surface is up …
  await expect(page.getByText(/Most likely score/)).toBeVisible();

  // … and the edge / ¼-Kelly stake actually render here (this is the page that surfaces them).
  // Pin the EDGE chip explicitly (data-derived="edge"), not just the stake text — otherwise
  // removing <EdgeChip> while keeping the stake readout would slip past this smoke (Codex 5).
  await expect(page.locator('[data-derived="edge"]')).toBeVisible();
  await expect(page.getByText(/¼-Kelly stake signal/)).toBeVisible();

  // … yet there is STILL no bet/stake/order control: the stake is a read-only SIGNAL even on
  // the edge-bearing detail page (the most likely place a bet affordance would be added) …
  await assertNoBetAffordance(page);

  // … and the honesty banner persists across the drill-down (it's app-shell-level).
  await expect(page.getByText(BANNER)).toBeVisible();
});
