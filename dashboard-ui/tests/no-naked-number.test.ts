// T10 [LOAD-BEARING, FOCAL]: the no-naked-number render guard.
//
// The project's core rule — "no naked numbers" — made STRUCTURALLY enforced across
// the whole UI. Every probability-shaped token that renders MUST sit inside one of
// three conscious markers:
//   • data-uncertainty   — the estimate carries its ± companion (Estimate / CredibleInterval),
//                           OR the distribution IS the uncertainty (WinBar / ScorelineGrid /
//                           ScorePill, data-uncertainty="distribution").
//   • data-coverage-gap  — an honest gap ("insufficient coverage"), never a number.
//   • data-derived       — a conscious non-forecast numeric surface (the EdgeChip's edge %,
//                           the ¼-Kelly stake signal, the backward-looking Track performance
//                           stats). These are DERIVED signals / performance, not posteriors,
//                           so they are EXPLICITLY exempt — never exempt by accident.
//
// A % that escapes all three is a NAKED NUMBER and the guard fails.
//
// Non-vacuity (critical): a guard that cannot fail is worthless. The SAME
// assertNoNakedNumbers() is exercised against a deliberately-naked <span>45%</span>
// and MUST catch it (see the "NON-VACUITY" block at the bottom).

import { render, fireEvent, waitFor, cleanup } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, describe, beforeEach, afterEach } from 'vitest';

// Hard isolation: unmount + remove every rendered node between tests so one surface's
// DOM (e.g. MatchDetail's edge %) can never bleed into another's container.
afterEach(() => cleanup());
import Schedule from '../src/surfaces/Schedule.svelte';
import Tournament from '../src/surfaces/Tournament.svelte';
import Track from '../src/surfaces/Track.svelte';
import MatchDetail from '../src/surfaces/MatchDetail.svelte';

const dir = resolve(__dirname, 'fixtures/bundle');
const J = (f: string) => JSON.parse(readFileSync(resolve(dir, f), 'utf8'));

// A probability-shaped token: a digit (optionally with decimals), optional space, then %.
// Catches "45%", "6.9%", "29 %" — i.e. any visible percentage readout.
const PCT = /\d+(\.\d+)?\s*%/;

// The conscious exemption set: the markers under which a probability MAY render.
// [data-estimate] is included because an estimate's point value (its ".val" text,
// e.g. "29%") legitimately lives inside the estimate — and invariant (1) below
// SEPARATELY guarantees that estimate carries a [data-uncertainty] ± companion (or
// is a "—" null). So a % inside a [data-estimate] is never naked: its uncertainty is
// enforced by (1). A bare "45%" with no [data-estimate] ancestor still has no escape.
const EXEMPT = '[data-uncertainty], [data-coverage-gap], [data-derived], [data-estimate]';

/**
 * The load-bearing guard. Factored out so the REAL surfaces (which must pass) and a
 * deliberately-naked snippet (which must be caught) exercise IDENTICAL logic.
 *
 * Two invariants:
 *  (1) Every [data-estimate] either contains a [data-uncertainty] companion, OR its
 *      text is exactly "—" (a null — not a naked number), OR it sits inside a gap.
 *      A bare "29%" with no ± companion is a naked estimate and fails.
 *  (2) Every element whose OWN text node shows a % is covered by an ancestor (or self)
 *      in the conscious exemption set. No probability % floats free.
 */
function assertNoNakedNumbers(container: HTMLElement) {
  // (1) every estimate carries an uncertainty companion (or is a null em-dash, or inside a gap).
  container.querySelectorAll('[data-estimate]').forEach((est) => {
    const hasCompanion = est.querySelector('[data-uncertainty]') !== null;
    const isNullDash = (est.textContent ?? '').trim() === '—';
    const insideGap = est.closest('[data-coverage-gap]') !== null;
    expect(
      hasCompanion || isNullDash || insideGap,
      `naked estimate (no ± companion, not a — null): "${est.textContent?.trim()}"`,
    ).toBe(true);
  });

  // (2) every element whose OWN text shows a % is exempt by an ancestor or by being a marker.
  container.querySelectorAll('*').forEach((el) => {
    const ownText = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3) // text nodes only — don't double-count descendant text
      .map((n) => n.textContent)
      .join('');
    if (!PCT.test(ownText)) return;
    const ok = el.closest(EXEMPT) !== null || el.matches('[data-estimate]');
    expect(ok, `naked % text (outside ${EXEMPT}): "${ownText.trim()}"`).toBeTruthy();
  });
}

describe('no naked numbers — every surface honours the uncertainty/gap/derived markers', () => {
  test('Schedule (GROUP stage) has no naked numbers', () => {
    const { container } = render(Schedule, { data: J('schedule.json').data });
    assertNoNakedNumbers(container);
  });

  test('Schedule (KNOCKOUT stage, via nav click) has no naked numbers', async () => {
    const { container, getByRole } = render(Schedule, { data: J('schedule.json').data });
    // Drive the surface to its OTHER stage: the knockout occupants render data-estimate %s.
    await fireEvent.click(getByRole('button', { name: 'knockout' }));
    // Sanity: we actually switched stage and there ARE estimates to guard.
    await waitFor(() => expect(container.querySelector('[data-estimate]')).not.toBeNull());
    assertNoNakedNumbers(container);
  });

  test('Tournament has no naked numbers', () => {
    const { container } = render(Tournament, {
      data: J('tournament.json').data,
      markets: J('meta.json').data.markets,
    });
    // Sanity: the progression table renders estimates (else the guard is vacuous here).
    expect(container.querySelector('[data-estimate]')).not.toBeNull();
    assertNoNakedNumbers(container);
  });

  test('Track (coverage-gap path) has no naked numbers', () => {
    const { container } = render(Track, { data: J('track.json').data });
    assertNoNakedNumbers(container);
  });

  test('Track (REAL performance stats) has no naked numbers', () => {
    // The committed fixture's track is a gap; exercise the %-bearing REAL path too,
    // so the data-derived exemption on the performance region is actually tested.
    const real = {
      n_bets: 40,
      beat_close_rate: 0.58,
      avg_clv: 0.021,
      rps: { model: 0.18, market: 0.19, elo: 0.21 },
      reliability: [{ bin_lo: 0.6, bin_hi: 0.7, n: 12, forecast_mean: 0.64, empirical: 0.58 }],
      is_synthetic: true,
    };
    const { container } = render(Track, { data: real });
    // Sanity: real % readouts actually render here.
    expect(PCT.test(container.textContent ?? '')).toBe(true);
    assertNoNakedNumbers(container);
  });

  // MatchDetail loads its fixture via fetch in onMount. Use the REAL-edge fixture so the
  // EdgeChip's edge % AND the ¼-Kelly stake-signal % actually render (the [0]/gap fixture
  // would never exercise the derived % path the guard exists to police).
  const realEdgeId = 'Brazil__Mexico__2024-05-02';

  beforeEach(() => {
    globalThis.fetch = (async (url: string) => {
      const rel = String(url).replace(/^.*\/bundle\//, '');
      return { ok: true, json: async () => JSON.parse(readFileSync(resolve(dir, rel), 'utf8')) } as Response;
    }) as typeof fetch;
  });

  test('MatchDetail (real edge → derived stake % + edge %) has no naked numbers', async () => {
    const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId: realEdgeId });
    // Let onMount's fetch resolve and the edge section render.
    await waitFor(() => expect(container.querySelector('[data-section="edge"]')).not.toBeNull());
    await waitFor(() => expect(container.querySelector('[data-derived]')).not.toBeNull());
    // Sanity: a derived % (the edge chip and/or stake signal) actually rendered.
    expect(PCT.test(container.textContent ?? '')).toBe(true);
    assertNoNakedNumbers(container);
  });
});

// ── NON-VACUITY PROOF ───────────────────────────────────────────────────────────
// A guard that can't fail is worthless. These tests prove assertNoNakedNumbers has
// TEETH: the SAME function that passes on every real surface above MUST throw when a
// naked % is present, and MUST throw on a data-estimate with no ± companion.
describe('NON-VACUITY: the guard catches naked numbers (proves it has teeth)', () => {
  let host: HTMLElement;
  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });
  afterEach(() => host.remove());

  test('a bare <span>45%</span> with NO marker is flagged', () => {
    host.innerHTML = '<span>45%</span>';
    expect(() => assertNoNakedNumbers(host)).toThrow(/naked % text/);
  });

  test('a decimal "6.9%" with no marker is flagged', () => {
    host.innerHTML = '<div><p>edge: 6.9%</p></div>';
    expect(() => assertNoNakedNumbers(host)).toThrow(/naked % text/);
  });

  test('a [data-estimate] with NO [data-uncertainty] companion is flagged as a naked estimate', () => {
    host.innerHTML = '<span data-estimate><span class="val">29%</span></span>';
    expect(() => assertNoNakedNumbers(host)).toThrow(/naked estimate/);
  });

  test('the SAME naked span IS accepted once wrapped in a conscious marker (control)', () => {
    // Confirms the guard exempts ONLY the marked case — it is selective, not blanket-permissive.
    host.innerHTML = '<span data-derived="edge">▲ +6.9%</span>';
    expect(() => assertNoNakedNumbers(host)).not.toThrow();
  });
});
