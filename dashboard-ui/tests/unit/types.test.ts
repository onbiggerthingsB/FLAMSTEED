import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Envelope, ScheduleData, TournamentData, MetaData } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const load = <T>(f: string): Envelope<T> => JSON.parse(readFileSync(resolve(dir, f), 'utf8'));

test('fixture envelopes match the typed contract', () => {
  const meta = load<MetaData>('meta.json');
  expect(meta.provenance.is_synthetic).toBe(true);
  expect(meta.provenance.banner).toBeTruthy();           // banner present iff synthetic
  expect(meta.data.markets).toContain('champion');

  const sch = load<ScheduleData>('schedule.json');
  expect(Array.isArray(sch.data.group)).toBe(true);
  const row = sch.data.group[0];
  expect(typeof row.match_id).toBe('string');

  const tour = load<TournamentData>('tournament.json');
  const team = Object.keys(tour.data)[0];
  // The serializer emits a market node only `if m in prog.columns`, so a market key may be
  // absent — the inner map is Partial. Read it null-safely (mirrors the surfaces' `?.`).
  const champion = tour.data[team]?.champion;
  expect(champion).toBeDefined(); // the committed fixture DOES carry champion for every team
  expect(typeof champion?.value === 'number' || champion?.value === null).toBe(true);
});
