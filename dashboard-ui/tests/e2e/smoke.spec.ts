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
  // No actionable control (button or link styled as an action) that PLACES/SIZES a bet.
  // NB: targets bet-PLACING ACTION verbs ("place bet", "stake now", "wager", "bet now",
  // "buy", "order ticket"). The bare tokens are ANCHORED (^\s*bet\s*$ / ^\s*stake\s*$) so a
  // standalone "Bet"/"Stake" action button IS caught, while the "Value Bets" navigation
  // label (a route control whose full name is "Value Bets", not "Bet") is NOT flagged.
  const ACTION = /place\s*bet|bet\s*now|stake\s*now|wager|buy|order\s*(ticket|bet)|checkout|^\s*bet\s*$|^\s*stake\s*$/i;
  const betButtons = page.getByRole('button', { name: ACTION });
  await expect(betButtons).toHaveCount(0);
  const betLinks = page.getByRole('link', { name: ACTION });
  await expect(betLinks).toHaveCount(0);

  // Defensive: no <form>, no submit/checkout inputs, no commerce-shaped controls at all.
  await expect(page.locator('form')).toHaveCount(0);
  await expect(page.locator('button[type="submit"], input[type="submit"]')).toHaveCount(0);
  await expect(
    page.locator('[role="button"]').filter({ hasText: ACTION }),
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

test('(a2) the PRIMARY Value Bets surface (SIGNAL-ONLY banner) is the landing', async ({ page }) => {
  await page.goto('/');
  await waitForApp(page);
  // The empty hash lands on Value Bets: its SIGNAL-ONLY / NOT-REAL banner renders.
  await expect(page.getByText(/SIGNAL-ONLY/)).toBeVisible();
  // The value banner's NOT-REAL text (scope to the value banner — the app-shell HonestyBar
  // also carries a "NOT REAL" string, so match the signal-only variant specifically).
  await expect(page.getByText(/NOT REAL — signal-only/)).toBeVisible();
  // The bettable table shows the engineered DR Congo / betmgm +EV spot.
  await expect(page.locator('[data-table="bettable"]')).toBeVisible();
  await expect(page.getByText(/Portugal v DR Congo/)).toBeVisible();
});

test('(b) there is NO bet/stake/buy/order action affordance on the homepage', async ({ page }) => {
  await page.goto('/');
  await waitForApp(page);
  await assertNoBetAffordance(page);
});

test('(c) drill into the REAL-EDGE match detail: edge + stake render, NO bet affordance, banner persists', async ({
  page,
}) => {
  // The match surfaces live under the SECONDARY "Forecast" nav now; start on the schedule.
  await page.goto('/#/schedule');
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

// (d) FIX E: the Tournament + Track routes were never visited — extend the honesty invariants
// to EVERY surface, not just the homepage + one match. On each route the persistent NON-REAL
// banner must remain AND there must be no bet/stake/buy/order affordance.
test('(d) Tournament route: NON-REAL banner persists AND no bet affordance', async ({ page }) => {
  await page.goto('/#/tournament');
  await waitForApp(page);
  // Sanity: the progression table actually rendered (the route really switched).
  await expect(page.locator('table.prog')).toBeVisible();
  await expect(page.getByText(BANNER)).toBeVisible();
  await assertNoBetAffordance(page);
});

test('(e) Track route: NON-REAL banner persists AND no bet affordance', async ({ page }) => {
  await page.goto('/#/track');
  await waitForApp(page);
  // Sanity: the Track surface actually rendered (heading present on either gap or stats path).
  await expect(page.getByRole('heading', { name: /Track record/ })).toBeVisible();
  await expect(page.getByText(BANNER)).toBeVisible();
  await assertNoBetAffordance(page);
});
