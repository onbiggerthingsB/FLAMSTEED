// T10 NON-REAL e2e smoke — fast, deterministic, offline (synthetic fixture bundle).
//
// Three load-bearing honesty invariants for a signal-only / paper dashboard:
//   (a) the persistent DRY-RUN / NON-REAL banner is visible on load;
//   (b) there is NO bet / stake / buy / order BUTTON or form affordance anywhere —
//       the stake is a read-only SIGNAL, not a control (signal-only is absolute);
//   (c) drill-down works (Schedule → a match detail) AND the banner persists.

import { test, expect, type Page } from '@playwright/test';

const BANNER = /DRY-RUN · SYNTHETIC ODDS · NOT REAL/;

async function waitForApp(page: Page) {
  // The app loads the bundle async; the banner only renders once provenance is in.
  await expect(page.getByText(BANNER)).toBeVisible();
}

test('(a) the NON-REAL honesty banner is visible on load', async ({ page }) => {
  await page.goto('/');
  await waitForApp(page);
});

test('(b) there is NO bet/stake/buy/order action affordance anywhere', async ({ page }) => {
  await page.goto('/');
  await waitForApp(page);

  // No actionable control (button or link styled as an action) that places/sizes a bet.
  // The stake_signal renders as plain read-only text inside data-derived — never a control.
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
  // (It only renders on a real-edge fixture; if present it must NOT be a button.)
  const stakeText = page.getByText(/¼-Kelly stake signal/);
  if (await stakeText.count()) {
    await expect(stakeText.first()).toBeVisible();
    // Its nearest interactive ancestor (if any) must not be a button/role=button.
    const isControl = await stakeText.first().evaluate((el) => {
      const ctrl = el.closest('button,[role="button"],a[href],input,form');
      return ctrl !== null;
    });
    expect(isControl, 'stake signal must be a read-only readout, not a control').toBe(false);
  }
});

test('(c) drill from schedule into a match detail; banner persists', async ({ page }) => {
  await page.goto('/');
  await waitForApp(page);

  // Schedule renders "detail →" links per fixture row.
  await page.getByRole('link', { name: /detail/ }).first().click();

  // The match-detail surface is up …
  await expect(page.getByText(/Most likely score/)).toBeVisible();
  // … and the honesty banner persists across the drill-down (it's app-shell-level).
  await expect(page.getByText(BANNER)).toBeVisible();
});
