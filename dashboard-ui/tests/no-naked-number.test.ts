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
import type { KoRow } from '../src/lib/types';

// Hard isolation: unmount + remove every rendered node between tests so one surface's
// DOM (e.g. MatchDetail's edge %) can never bleed into another's container.
afterEach(() => cleanup());
import Schedule from '../src/surfaces/Schedule.svelte';
import Tournament from '../src/surfaces/Tournament.svelte';
import Track from '../src/surfaces/Track.svelte';
import MatchDetail from '../src/surfaces/MatchDetail.svelte';
import WinBar from '../src/components/WinBar.svelte';
import HonestyBar from '../src/components/HonestyBar.svelte';
import BracketTree from '../src/components/BracketTree.svelte';
import App from '../src/App.svelte';

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
//
// MARKER-DISCIPLINE NOTE on [data-derived] (FIX 3 — read before adding any new use):
//   [data-derived] is a CONSCIOUSLY-REVIEWED exemption for NON-FORECAST numbers ONLY —
//   namely DERIVED signals (the EdgeChip's edge %, the ¼-Kelly stake signal, entry odds)
//   and BACKWARD-LOOKING performance stats (the Track record: beat-close rate, CLV, RPS,
//   reliability bins). These are not posteriors, so they carry no ± companion by design.
//   It must NEVER wrap a FORWARD-LOOKING FORECAST probability — a forecast must keep its
//   uncertainty companion (± / "distribution" region / coverage-gap). The guard cannot
//   infer semantics from markup, so it CANNOT tell a derived % from a smuggled forecast %;
//   every new [data-derived] use is therefore a manual review checkpoint, not a free pass.
const EXEMPT = '[data-uncertainty], [data-coverage-gap], [data-derived], [data-estimate]';

/**
 * The load-bearing guard. Factored out so the REAL surfaces (which must pass) and a
 * deliberately-naked snippet (which must be caught) exercise IDENTICAL logic.
 *
 * Three invariants:
 *  (1) Every [data-estimate] either contains a [data-uncertainty] companion, OR its
 *      text is exactly "—" (a null — not a naked number), OR it sits inside a gap.
 *      A bare "29%" with no ± companion is a naked estimate and fails.
 *  (2) Every element whose OWN text node shows a % is covered by an ancestor (or self)
 *      in the conscious exemption set. No probability % floats free.
 *  (3) [FIX 6] Every element whose `title` or `aria-label` ATTRIBUTE shows a % must
 *      ALSO be inside the exemption set. A `<span title="45%">` with no marker is a
 *      naked attribute % — the same loophole as visible text, just hidden in metadata
 *      (hover tooltips, SR labels) — and is caught. Today's attribute %s (WinBar /
 *      ScorelineGrid titles) all live inside data-uncertainty="distribution", so they
 *      pass; this closes the door on FUTURE forecasts leaking a % via an attribute.
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

  // (3) [FIX 6] every element with a %-shaped token in title / aria-label is exempt too.
  // A % smuggled into an attribute (hover tooltip, SR label) is just as naked as visible
  // text — close that loophole so a future forecast can't leak a probability via metadata.
  container.querySelectorAll('[title], [aria-label]').forEach((el) => {
    for (const attr of ['title', 'aria-label'] as const) {
      const val = el.getAttribute(attr);
      if (!val || !PCT.test(val)) continue;
      const ok = el.closest(EXEMPT) !== null || el.matches('[data-estimate]');
      expect(ok, `naked % in @${attr} (outside ${EXEMPT}): "${val.trim()}"`).toBeTruthy();
    }
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

  test('Tournament (progression table + bracket tree) has no naked numbers', () => {
    // Feed the KO rows so the BRACKET TREE (below the progression table) is exercised too —
    // its occupant %s must all sit inside Estimate/CoverageGap, same as the table cells.
    const { container } = render(Tournament, {
      data: J('tournament.json').data,
      markets: J('meta.json').data.markets,
      knockout: J('schedule.json').data.knockout,
    });
    // Sanity: the progression table renders estimates (else the guard is vacuous here).
    expect(container.querySelector('[data-estimate]')).not.toBeNull();
    // Sanity: the bracket tree actually rendered its slots (else its coverage is vacuous).
    expect(container.querySelector('[data-bracket-match]')).not.toBeNull();
    assertNoNakedNumbers(container);
  });

  test('BracketTree (occupants + a deeper-feeder coverage gap) has no naked numbers', () => {
    // Render the bracket tree DIRECTLY over a multi-round chain that exercises BOTH the
    // occupant-Estimate path AND the {coverage_gap} path (a W-feeder that resolves deeper).
    // Every occupant % must sit inside Estimate (data-uncertainty); the gapped slot renders
    // a CoverageGap — no naked % anywhere.
    const occ = (team: string, prob: number) => ({ team, prob, se: 0.003 });
    const knockout: KoRow[] = [
      { match: 73, stage: 'R32', status: 'upcoming', home_ref: '1A', away_ref: '3rd-BCDEF',
        home_occupants: [occ('Argentina', 0.51), occ('Mexico', 0.3), occ('Malta', 0.19)],
        away_occupants: [occ('Brazil', 0.4), occ('Croatia', 0.35)] },
      { match: 89, stage: 'R16', status: 'upcoming', home_ref: 'W73', away_ref: 'W74',
        home_occupants: [occ('Argentina', 0.44), occ('Brazil', 0.41)],
        away_occupants: { coverage_gap: true, reason: 'feeder W74 resolves from a later match' } },
      { match: 104, stage: 'Final', status: 'upcoming', home_ref: 'W101', away_ref: 'W102',
        home_occupants: { coverage_gap: true, reason: 'feeder W101 resolves from a later match' },
        away_occupants: { coverage_gap: true, reason: 'feeder W102 resolves from a later match' } },
    ];
    const { container } = render(BracketTree, { knockout });
    // Sanity: both an Estimate occupant % AND a coverage gap actually rendered (non-vacuous).
    expect(container.querySelector('[data-estimate]')).not.toBeNull();
    expect(container.querySelector('[data-coverage-gap]')).not.toBeNull();
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

  // ── FIX 2: the previously-UNEXERCISED %-bearing / marker states ────────────────
  // Each runs through the SAME assertNoNakedNumbers so it is real coverage, not a
  // bespoke assertion. A naked-number regression in any of these states would fail.

  test('Tournament with a NULL progression cell renders "—" (not a naked number)', () => {
    // Clone the real tournament data, then NULL OUT one market cell so Estimate must
    // render the em-dash null path ("—", no % and no ±). The guard must still pass AND
    // the "—" must not be (mis)read as a naked number.
    const data = J('tournament.json').data;
    data.Brazil.champion = { value: null, se: null }; // a null progression cell
    const { container } = render(Tournament, { data, markets: J('meta.json').data.markets });
    // Sanity: a "—" null estimate actually rendered (else this state is vacuous).
    const dashed = Array.from(container.querySelectorAll('[data-estimate]')).some(
      (e) => (e.textContent ?? '').trim() === '—',
    );
    expect(dashed, 'expected at least one "—" null estimate cell').toBe(true);
    assertNoNakedNumbers(container);
  });

  test('Schedule GROUP row with a gapped forecast_summary renders CoverageGap (no naked %)', () => {
    // Clone the real schedule and force a row's forecast_summary to a coverage gap so the
    // CoverageGap branch (not the ScorePill/WinBar branch) renders — a previously-unexercised
    // %-free state. The guard must pass and no naked % may appear.
    const sched = J('schedule.json').data;
    sched.group = sched.group.map((r: Record<string, unknown>, i: number) =>
      i === 1
        ? { ...r, forecast_summary: { coverage_gap: true, reason: 'forecast gap (test state)' } }
        : r,
    );
    const { container } = render(Schedule, { data: sched });
    // Sanity: the coverage-gap branch actually rendered.
    expect(container.querySelector('[data-coverage-gap]')).not.toBeNull();
    assertNoNakedNumbers(container);
  });

  test('Schedule KNOCKOUT row with a gapped home_occupants list renders CoverageGap (no naked %)', async () => {
    // Force a KO row's home_occupants to a coverage gap so the occupant-gap branch renders
    // (the leaner {coverage_gap, reason} shape) — exercises the gap path inside knockout.
    const sched = J('schedule.json').data;
    sched.knockout = sched.knockout.map((k: Record<string, unknown>) => ({
      ...k,
      home_occupants: { coverage_gap: true, reason: 'occupants gap (test state)' },
    }));
    const { container, getByRole } = render(Schedule, { data: sched });
    await fireEvent.click(getByRole('button', { name: 'knockout' }));
    // Sanity: a coverage gap rendered in the KO view, AND the away occupants still show %s.
    await waitFor(() => expect(container.querySelector('[data-coverage-gap]')).not.toBeNull());
    expect(container.querySelector('[data-estimate]')).not.toBeNull(); // away side still has estimates
    assertNoNakedNumbers(container);
  });

  test('WinBar WITH a de-vigged line: the line-legend %s live inside the distribution region', () => {
    // Pass a `line` so the ghosted-sharp-line legend ("line: H .. · D .. · A ..") renders.
    // Those line %s are emitted INSIDE data-uncertainty="distribution" (same region as the
    // model legend + bar-segment title %s), so the guard must pass — proving the line path,
    // which the bundle surfaces never feed today, is itself naked-number-safe.
    const model = { home: 0.3485557140956659, draw: 0.25864067803992613, away: 0.3928036078644081 };
    const line = { home: 0.34, draw: 0.27, away: 0.39 };
    const { container } = render(WinBar, { model, line });
    // Sanity: the line legend actually rendered a % (else this state is vacuous).
    const legend = container.querySelector('.ln');
    expect(legend, 'expected the de-vigged line legend to render').not.toBeNull();
    expect(PCT.test(legend?.textContent ?? '')).toBe(true);
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

  // ── FIX D: run the App SHELL + HonestyBar through the SAME guard ────────────────
  // The guard previously rendered only the four surfaces + WinBar in isolation — never
  // the composed shell or the honesty bar, so a future % in the bar / banner was an
  // unguarded blind spot. These close that: the SAME assertNoNakedNumbers scans the
  // shell + bar (incl. title/aria-label attributes), so a % smuggled into the honesty
  // bar/banner WOULD be caught.

  test('HonestyBar (synthetic provenance incl. banner) has no naked numbers', () => {
    // The synthetic banner text + as-of + "20,000 sims" version readout: today none carry
    // a %, so the guard passes. A future % in the bar/banner (visible OR in the title attr)
    // would be caught by invariants (2)/(3) — proving the bar is no longer a blind spot.
    const { container } = render(HonestyBar, {
      provenance: {
        as_of: '2026-06-06T19:31:22Z',
        posterior_key: '123a88ae08fd5ae5',
        git: 'eb4b7b1',
        is_synthetic: true,
        n_sims: 20000,
        banner: 'DRY-RUN · SYNTHETIC ODDS · NOT REAL — no real odds were sourced, no bet placed.',
      },
    });
    // Sanity: the DRY-RUN chip (with its banner title attribute) actually rendered.
    expect(container.querySelector('.dryrun')).not.toBeNull();
    assertNoNakedNumbers(container);
  });

  test('the composed App shell (over the fixture bundle) has no naked numbers', async () => {
    // Mock fetch over the committed fixture (as app.test.ts does), render the WHOLE App, and
    // run the composed shell — HonestyBar + nav + the landing Value Bets surface — through the
    // SAME guard. This covers the shell that the isolated surface tests never exercised.
    location.hash = '';
    const { container } = render(App);
    // Let onMount's loads resolve so the bar + nav + landing (Value Bets) surface are mounted.
    await waitFor(() => expect(container.querySelector('header.bar')).not.toBeNull());
    await waitFor(() => expect(container.querySelector('nav')).not.toBeNull());
    // PRIMARY landing is Value Bets: its bettable table (a derived %/odds surface) renders.
    await waitFor(() => expect(container.querySelector('[data-table="bettable"]')).not.toBeNull());
    assertNoNakedNumbers(container);
  });

  test('NON-VACUITY (shell): a hypothetical % smuggled into the honesty bar IS caught', () => {
    // Prove the shell coverage is non-vacuous: inject a naked % into a bar-shaped node with
    // NO marker (mirroring a future regression where a % leaks into the honesty bar text or
    // a title attr) and confirm the SAME guard throws. This is what gives FIX D teeth.
    const host = document.createElement('div');
    host.innerHTML = '<header class="bar"><span class="ver muted">model x · 45% sims</span></header>';
    expect(() => assertNoNakedNumbers(host)).toThrow(/naked % text/);
    host.innerHTML = '<header class="bar"><span class="dryrun" title="hit-rate 45%">DRY-RUN</span></header>';
    expect(() => assertNoNakedNumbers(host)).toThrow(/naked % in @title/);
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

  // [FIX 6] ATTRIBUTE non-vacuity: a % smuggled into title / aria-label with NO marker
  // must be caught exactly like visible text — this is what gives invariant (3) teeth.
  test('a <span title="45%"> with NO marker is flagged (attribute loophole closed)', () => {
    host.innerHTML = '<span title="45%">x</span>';
    expect(() => assertNoNakedNumbers(host)).toThrow(/naked % in @title/);
  });

  test('a naked aria-label="home 45%" with NO marker is flagged', () => {
    host.innerHTML = '<div aria-label="home 45%">x</div>';
    expect(() => assertNoNakedNumbers(host)).toThrow(/naked % in @aria-label/);
  });

  test('the SAME attribute % IS accepted once inside a marked region (control)', () => {
    // Mirrors the real WinBar/ScorelineGrid case: a title % is fine inside the distribution region.
    host.innerHTML = '<div data-uncertainty="distribution"><span title="home 45%">x</span></div>';
    expect(() => assertNoNakedNumbers(host)).not.toThrow();
  });
});
