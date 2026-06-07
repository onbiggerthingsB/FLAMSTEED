import { render } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import Tournament from '../../src/surfaces/Tournament.svelte';
import type { Envelope, TournamentData, MetaData } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const tour: Envelope<TournamentData> = JSON.parse(readFileSync(resolve(dir, 'tournament.json'), 'utf8'));
const meta: Envelope<MetaData> = JSON.parse(readFileSync(resolve(dir, 'meta.json'), 'utf8'));

test('Tournament shows every team and every progression market carries an SE', () => {
  const { container } = render(Tournament, { data: tour.data, markets: meta.data.markets });
  const teamRows = container.querySelectorAll('[data-team]');
  expect(teamRows.length).toBe(Object.keys(tour.data).length);
  // every progression cell is an Estimate (value + uncertainty companion)
  const cells = container.querySelectorAll('[data-estimate]');
  expect(cells.length).toBeGreaterThan(0);
  // LOAD-BEARING: every cell carries its uncertainty companion OR shows "—" (a
  // null, never a naked number). Prefigures the T10 no-naked-number guard.
  cells.forEach((c) => {
    const hasCompanion = c.querySelector('[data-uncertainty]') !== null;
    const isDash = (c.textContent ?? '').trim() === '—';
    expect(hasCompanion || isDash).toBe(true);
  });
});

test('Tournament orders columns as the coherence ladder (shallow → deep)', () => {
  const { container } = render(Tournament, { data: tour.data, markets: meta.data.markets });
  const headers = Array.from(container.querySelectorAll('thead th')).map((h) => h.textContent?.trim());
  // first header is the team column; the rest are progression markets in ladder order.
  const cols = headers.slice(1);
  // Readable labels (the T11 header pass): market key → human label.
  const LABEL: Record<string, string> = {
    advance_from_group: 'Advance',
    reach_r16: 'R16',
    reach_qf: 'QF',
    reach_sf: 'SF',
    reach_final: 'Final',
    champion: 'Champion',
  };
  const idx = (market: string) => cols.indexOf(LABEL[market]);
  const chain = ['advance_from_group', 'reach_r16', 'reach_qf', 'reach_sf', 'reach_final', 'champion'];
  const positions = chain.map(idx).filter((p) => p >= 0);
  expect(positions.length).toBeGreaterThan(1);
  // shallow→deep reads left→right: each chain link sits to the left of the next.
  for (let i = 1; i < positions.length; i++) {
    expect(positions[i]).toBeGreaterThan(positions[i - 1]);
  }
});

test('Tournament sorts teams by champion probability descending', () => {
  const { container } = render(Tournament, { data: tour.data, markets: meta.data.markets });
  const order = Array.from(container.querySelectorAll('[data-team]')).map((r) => r.getAttribute('data-team')!);
  const expected = Object.keys(tour.data).sort(
    (a, b) => (tour.data[b].champion?.value ?? 0) - (tour.data[a].champion?.value ?? 0),
  );
  expect(order).toEqual(expected);
});
