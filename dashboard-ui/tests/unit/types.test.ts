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
  expect(typeof tour.data[team].champion.value === 'number' || tour.data[team].champion.value === null).toBe(true);
});
