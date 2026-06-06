import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { isGap } from '../../src/lib/guards';
import { unwrap, provenanceOf } from '../../src/lib/bundle';
import type { Envelope, ScheduleData } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const sch: Envelope<ScheduleData> = JSON.parse(readFileSync(resolve(dir, 'schedule.json'), 'utf8'));

test('isGap detects coverage_gap nodes only', () => {
  expect(isGap({ coverage_gap: true, reason: 'x', value: null })).toBe(true);
  expect(isGap({ coverage_gap: true, reason: 'lean-edge-gap' })).toBe(true);   // no value key
  expect(isGap({ value: 0.1, se: 0.01 })).toBe(false);
  expect(isGap(null)).toBe(true);            // missing -> treat as gap (fail-safe to "no data")
  expect(isGap(undefined)).toBe(true);
});

test('unwrap + provenanceOf read the envelope', () => {
  expect(unwrap(sch).group.length).toBeGreaterThan(0);
  expect(provenanceOf(sch).is_synthetic).toBe(true);
});
