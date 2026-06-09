// Model "second opinion" column on the Value Bets surface (DISPLAY-ONLY context).
//
// The +EV board is market-vs-market; the scoreline model has NO betting edge, so it must
// NOT drive the edge or the bettable list. This column only SHOWS our independent
// forecast's take on each pick's outcome + whether it agrees/disagrees with the de-vigged
// sharp fair prob. These tests assert:
//   (a) a value bet whose fixture+outcome exists in the forecast shows the model prob and
//       the correct agree/disagree tag (both directions);
//   (b) a pick with no matching forecast fixture shows "—" (no model view);
//   (c) the model second-opinion is purely display: it does NOT change the bettable list,
//       its contents, or its ordering — same value bundle in, same bettable list out,
//       whether or not a forecast is supplied.
//
// We exercise the REAL value loader (fetch + snake→camel + banner assert) for the value
// bundle, and build a small schedule-shaped forecast bundle inline so the join is
// deterministic. The join helper is also unit-tested directly.

import { render, screen, cleanup } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, describe, afterEach } from 'vitest';
import { loadValueBundle } from '../../src/lib/bundle';
import type { ValueBundle, ScheduleData, ValueBet } from '../../src/lib/types';
import {
  buildForecastIndex,
  modelSecondOpinion,
  parseEvent,
} from '../../src/lib/modelSecondOpinion';
import ValueBets from '../../src/surfaces/ValueBets.svelte';

afterEach(() => cleanup());

async function loadValueFixture(): Promise<ValueBundle> {
  globalThis.fetch = (async (url: string) => {
    const rel = String(url).replace(/^.*\//, '');
    const body = readFileSync(resolve(__dirname, '../fixtures', rel), 'utf8');
    return { ok: true, json: async () => JSON.parse(body) } as Response;
  }) as typeof fetch;
  return loadValueBundle('/value.json');
}

// A minimal schedule-shaped forecast bundle. The value fixture's lone bettable spot is
// "Portugal v DR Congo", pick "DR Congo" (the AWAY side), sharpFairProb ≈ 0.1463. We give
// the model an away-win prob ABOVE that (0.20) so the pick should read "agrees". A second
// fixture lets us flip the direction in a unit test.
function makeForecast(awayProb: number): ScheduleData {
  const home = 1 - 0.30 - awayProb; // draw fixed at 0.30
  return {
    group: [
      {
        home: 'Portugal',
        away: 'DR Congo',
        date: '2026-06-26',
        group: 'A',
        stage: 'group',
        status: 'upcoming',
        match_id: 'Portugal__DR_Congo__2026-06-26',
        edge: { coverage_gap: true, reason: 'n/a' },
        forecast_summary: {
          most_likely: { home_goals: 1, away_goals: 0, prob: 0.1 },
          shortlist: [],
          one_x_two: { home, draw: 0.30, away: awayProb },
        },
      },
    ],
    knockout: [],
  };
}

// Helper to make a synthetic ValueBet for direct unit tests of the join.
function bet(over: Partial<ValueBet>): ValueBet {
  return {
    event: 'Portugal v DR Congo',
    commenceTime: '2026-06-26 00:00',
    market: 'h2h',
    line: null,
    side: 'DR Congo',
    sharpBook: 'pinnacle',
    sharpFairProb: 0.1463,
    softBook: 'betmgm',
    softOdds: 7.25,
    edge: 0.05,
    suggestedStake: 0.01,
    bookTier: 'soft',
    lastUpdate: null,
    flags: [],
    bettable: true,
    ...over,
  };
}

describe('modelSecondOpinion join helper (unit)', () => {
  test('parseEvent splits "Home v Away" and rejects malformed labels', () => {
    expect(parseEvent('Portugal v DR Congo')).toEqual({ home: 'Portugal', away: 'DR Congo' });
    expect(parseEvent('no separator here')).toBeNull();
    expect(parseEvent('A v B v C')).toBeNull();
  });

  test('h2h away pick: model away prob, agrees when model >= sharp fair prob', () => {
    const idx = buildForecastIndex(makeForecast(0.20));
    const r = modelSecondOpinion(bet({ side: 'DR Congo', sharpFairProb: 0.1463 }), idx);
    expect(r.prob).toBeCloseTo(0.20, 6);
    expect(r.agrees).toBe(true);
  });

  test('h2h away pick: disagrees when model < sharp fair prob', () => {
    const idx = buildForecastIndex(makeForecast(0.10));
    const r = modelSecondOpinion(bet({ side: 'DR Congo', sharpFairProb: 0.1463 }), idx);
    expect(r.prob).toBeCloseTo(0.10, 6);
    expect(r.agrees).toBe(false);
  });

  test('h2h home pick reads the model home prob; Draw reads the draw prob', () => {
    const idx = buildForecastIndex(makeForecast(0.20)); // home = 0.50, draw = 0.30
    const home = modelSecondOpinion(bet({ side: 'Portugal', sharpFairProb: 0.4 }), idx);
    expect(home.prob).toBeCloseTo(0.50, 6);
    expect(home.agrees).toBe(true);
    const draw = modelSecondOpinion(bet({ side: 'Draw', sharpFairProb: 0.4 }), idx);
    expect(draw.prob).toBeCloseTo(0.30, 6);
    expect(draw.agrees).toBe(false);
  });

  test('no matching fixture → null prob, null agrees (renders "—")', () => {
    const idx = buildForecastIndex(makeForecast(0.20));
    const r = modelSecondOpinion(bet({ event: 'Nowhere v Nobody', side: 'Nobody' }), idx);
    expect(r.prob).toBeNull();
    expect(r.agrees).toBeNull();
  });

  test('totals market is not joinable from the viewer → null (—)', () => {
    const idx = buildForecastIndex(makeForecast(0.20));
    const r = modelSecondOpinion(bet({ market: 'totals', line: 2.5, side: 'Over' }), idx);
    expect(r.prob).toBeNull();
    expect(r.agrees).toBeNull();
  });

  test('known odds-API ↔ model name divergences still join (aliases)', () => {
    // odds wire uses "Bosnia & Herzegovina" / "USA"; model uses "Bosnia and Herzegovina" /
    // "United States". The alias map reconciles them so these fixtures join too.
    const sched: ScheduleData = {
      group: [
        {
          home: 'Switzerland', away: 'Bosnia and Herzegovina', date: '2026-06-24', group: 'B',
          stage: 'group', status: 'upcoming', match_id: 'm', edge: { coverage_gap: true, reason: 'n/a' },
          forecast_summary: { most_likely: { home_goals: 1, away_goals: 0, prob: 0.1 }, shortlist: [], one_x_two: { home: 0.5, draw: 0.3, away: 0.2 } },
        },
      ],
      knockout: [],
    };
    const idx = buildForecastIndex(sched);
    const r = modelSecondOpinion(
      bet({ event: 'Switzerland v Bosnia & Herzegovina', side: 'Bosnia & Herzegovina', sharpFairProb: 0.1749 }),
      idx,
    );
    expect(r.prob).toBeCloseTo(0.20, 6);
    expect(r.agrees).toBe(true);
  });
});

describe('Model second-opinion column on ValueBets (render)', () => {
  test('(a) joinable pick shows the model prob + correct agree tag', async () => {
    const bundle = await loadValueFixture();
    const { container } = render(ValueBets, { bundle, forecast: makeForecast(0.20) });
    const cell = container.querySelector('[data-cell="model"] [data-derived="model"]');
    expect(cell).not.toBeNull();
    // Model away prob 0.20 > sharpFairProb 0.1463 → agrees, and 20.0% is rendered.
    expect(cell?.getAttribute('data-agree')).toBe('agree');
    expect(cell?.textContent).toMatch(/20\.0\s*%/);
    expect(cell?.textContent).toMatch(/agrees/);
  });

  test('(a2) flips to disagree when the model rates it below the market', async () => {
    const bundle = await loadValueFixture();
    const { container } = render(ValueBets, { bundle, forecast: makeForecast(0.10) });
    const cell = container.querySelector('[data-cell="model"] [data-derived="model"]');
    expect(cell?.getAttribute('data-agree')).toBe('disagree');
    expect(cell?.textContent).toMatch(/disagrees/);
  });

  test('(b) a pick with no matching forecast fixture shows "—"', async () => {
    const bundle = await loadValueFixture();
    // Empty forecast → no fixture matches → model cell shows the em dash + "no model view".
    const empty: ScheduleData = { group: [], knockout: [] };
    const { container } = render(ValueBets, { bundle, forecast: empty });
    const cell = container.querySelector('[data-cell="model"] [data-derived="model"]');
    expect(cell?.getAttribute('data-agree')).toBe('none');
    expect(cell?.textContent).toMatch(/—/);
    expect(cell?.textContent).toMatch(/no model view/);
  });

  test('(b2) a null forecast bundle degrades the whole column to "—"', async () => {
    const bundle = await loadValueFixture();
    const { container } = render(ValueBets, { bundle, forecast: null });
    const cell = container.querySelector('[data-cell="model"] [data-derived="model"]');
    expect(cell?.getAttribute('data-agree')).toBe('none');
    expect(cell?.textContent).toMatch(/—/);
  });

  test('(c) the model second-opinion does NOT change the bettable list / ordering', async () => {
    const bundle = await loadValueFixture();
    const order = (c: HTMLElement) =>
      Array.from(c.querySelectorAll('[data-table="bettable"] tr[data-bet] td.ev')).map(
        (td) => td.textContent,
      );

    // Render with NO forecast, with an agreeing forecast, and with a disagreeing one.
    const { container: c0 } = render(ValueBets, { bundle, forecast: null });
    const base = order(c0);
    cleanup();

    const { container: c1 } = render(ValueBets, { bundle, forecast: makeForecast(0.20) });
    expect(order(c1)).toEqual(base);
    cleanup();

    const { container: c2 } = render(ValueBets, { bundle, forecast: makeForecast(0.10) });
    expect(order(c2)).toEqual(base);

    // The bettable row count is fixed by the value bundle alone, never by the model view.
    expect(base.length).toBe(bundle.data.bettable.length);
  });

  test('the honest "context, NOT the edge" label is present on the column', async () => {
    const bundle = await loadValueFixture();
    render(ValueBets, { bundle, forecast: makeForecast(0.20) });
    expect(screen.getByText(/context, NOT the edge/i)).toBeInTheDocument();
  });
});
