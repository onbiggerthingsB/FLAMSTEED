// Task 8 render-guard: the PRIMARY "Value Bets" surface.
//
// Loads the value-bundle fixture (built by wcmodel.value off the golden odds snapshot),
// renders ValueBets, and asserts:
//   (1) the NOT-REAL / SIGNAL-ONLY banner renders (the honesty stamp is never dropped);
//   (2) the bettable table shows the engineered DR Congo / betmgm +EV spot;
//   (3) the "Filtered (and why)" section lists the rejected spot WITH its guard flags;
//   (4) NO naked number escapes — every %/edge/stake/fair-prob sits inside a conscious
//       data-derived / data-coverage-gap marker (the project's load-bearing grammar);
//   (5) there is NO bet/stake/order CONTROL — the stake is a read-only SUGGESTION signal.
//
// The same assertNoNakedNumbers() invariant from the load-bearing no-naked-number guard
// is reproduced here so this surface is held to the identical structural rule.

import { render, screen, cleanup } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, describe, afterEach } from 'vitest';
import { loadValueBundle } from '../../src/lib/bundle';
import type { ValueBundle } from '../../src/lib/types';
import ValueBets from '../../src/surfaces/ValueBets.svelte';

afterEach(() => cleanup());

// Load the value bundle through the REAL loader (fetch + snake→camel map + banner assert),
// exactly as the app does — so the test exercises the loader contract, not a hand-built object.
async function loadFixtureBundle(): Promise<ValueBundle> {
  globalThis.fetch = (async (url: string) => {
    const rel = String(url).replace(/^.*\//, '');
    const body = readFileSync(resolve(__dirname, '../fixtures', rel), 'utf8');
    return { ok: true, json: async () => JSON.parse(body) } as Response;
  }) as typeof fetch;
  return loadValueBundle('/value.json');
}

// A probability-shaped token: a digit (optionally with decimals), optional space, then %.
const PCT = /\d+(\.\d+)?\s*%/;
const EXEMPT = '[data-uncertainty], [data-coverage-gap], [data-derived], [data-estimate]';

// The SAME no-naked-number invariant the load-bearing guard enforces, applied to ValueBets.
function assertNoNakedNumbers(container: HTMLElement) {
  container.querySelectorAll('*').forEach((el) => {
    const ownText = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join('');
    if (!PCT.test(ownText)) return;
    const ok = el.closest(EXEMPT) !== null || el.matches('[data-estimate]');
    expect(ok, `naked % text (outside ${EXEMPT}): "${ownText.trim()}"`).toBeTruthy();
  });
  container.querySelectorAll('[title], [aria-label]').forEach((el) => {
    for (const attr of ['title', 'aria-label'] as const) {
      const val = el.getAttribute(attr);
      if (!val || !PCT.test(val)) continue;
      const ok = el.closest(EXEMPT) !== null || el.matches('[data-estimate]');
      expect(ok, `naked % in @${attr} (outside ${EXEMPT}): "${val.trim()}"`).toBeTruthy();
    }
  });
}

describe('ValueBets (PRIMARY surface) render guard', () => {
  test('renders the NOT-REAL / SIGNAL-ONLY banner from the value bundle', async () => {
    const bundle = await loadFixtureBundle();
    render(ValueBets, { bundle });
    expect(screen.getByText(/SIGNAL-ONLY/)).toBeInTheDocument();
    // The producer's NOT-REAL banner text is surfaced verbatim.
    expect(screen.getByText(/NOT REAL/)).toBeInTheDocument();
    // The honest "CLV is the test" lede is present.
    expect(screen.getByText(/The real test is CLV/i)).toBeInTheDocument();
  });

  test('the bettable table shows the engineered DR Congo / betmgm +EV spot', async () => {
    const bundle = await loadFixtureBundle();
    const { container } = render(ValueBets, { bundle });
    const table = container.querySelector('[data-table="bettable"]');
    expect(table).not.toBeNull();
    const text = table?.textContent ?? '';
    // The engineered spot: Portugal v DR Congo, pick DR Congo, soft book betmgm.
    expect(text).toMatch(/Portugal v DR Congo/);
    expect(text).toMatch(/DR Congo/);
    expect(text).toMatch(/betmgm/);
    // The de-vigged decimal odds the edge was priced against render as market data.
    expect(text).toMatch(/7\.25/);
    // The derived edge chip renders inside the data-derived exemption (never naked).
    expect(table?.querySelector('[data-derived="edge"]')).not.toBeNull();
    // The ¼-Kelly stake is a read-only SUGGESTION signal — present, derived, not a control.
    expect(table?.querySelector('[data-derived="stake"]')).not.toBeNull();
  });

  test('"Filtered (and why)" lists the rejected spot WITH its guard flags', async () => {
    const bundle = await loadFixtureBundle();
    const { container } = render(ValueBets, { bundle });
    const filtered = container.querySelector('[data-table="filtered"]');
    expect(filtered).not.toBeNull();
    const text = filtered?.textContent ?? '';
    // The too-good artifact (Brazil v Haiti) is shown, tagged with WHY it was filtered.
    expect(text).toMatch(/Brazil v Haiti/);
    expect(text).toMatch(/too_good/);
  });

  test('renders coverage gaps for events with no sharp (Pinnacle) line', async () => {
    const bundle = await loadFixtureBundle();
    const { container } = render(ValueBets, { bundle });
    // The pinnacle-less event is an honest coverage gap, never an edge.
    expect(container.querySelector('[data-coverage-gap]')).not.toBeNull();
    expect(container.textContent).toMatch(/X v Y/);
  });

  test('NO naked numbers escape the conscious markers', async () => {
    const bundle = await loadFixtureBundle();
    const { container } = render(ValueBets, { bundle });
    // Sanity (non-vacuity): the surface actually renders a % readout to police.
    expect(PCT.test(container.textContent ?? '')).toBe(true);
    assertNoNakedNumbers(container);
  });

  test('NO bet / stake / order CONTROL exists — the surface is signal-only', async () => {
    const bundle = await loadFixtureBundle();
    const { container } = render(ValueBets, { bundle });
    // No interactive bet/stake/order affordance: the stake is a read-only suggestion.
    expect(container.querySelector('button')).toBeNull();
    expect(container.querySelector('input')).toBeNull();
    expect(container.querySelector('form')).toBeNull();
    const html = container.innerHTML.toLowerCase();
    for (const forbidden of ['place bet', 'place a bet', 'submit bet', 'order ticket']) {
      expect(html.includes(forbidden), `forbidden control text: ${forbidden}`).toBe(false);
    }
  });
});
