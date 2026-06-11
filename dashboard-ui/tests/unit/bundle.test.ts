import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, expect, test, vi } from 'vitest';
import { isGap } from '../../src/lib/guards';
import { unwrap, provenanceOf, loadBundle } from '../../src/lib/bundle';
import type { Envelope, ScheduleData } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const sch: Envelope<ScheduleData> = JSON.parse(readFileSync(resolve(dir, 'schedule.json'), 'utf8'));

afterEach(() => vi.restoreAllMocks());

function mockFetch({ standings = true }: { standings?: boolean } = {}) {
  globalThis.fetch = (async (url: string) => {
    const rel = String(url).replace(/^.*\/bundle\//, '');
    // Item A: simulate a PRE-FEATURE bundle by 404-ing standings.json.
    if (rel === 'standings.json' && !standings) return { ok: false, status: 404 } as Response;
    const body = readFileSync(resolve(dir, rel), 'utf8');
    return { ok: true, json: async () => JSON.parse(body) } as Response;
  }) as typeof fetch;
}

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

test('loadBundle loads standings.json when present (Item A)', async () => {
  mockFetch({ standings: true });
  const b = await loadBundle('/bundle');
  expect(b.standings).not.toBeNull();
  expect(Object.keys(b.standings!.data).length).toBeGreaterThan(0);
});

test('loadBundle degrades standings to null on a PRE-FEATURE bundle (404), without failing the bundle', async () => {
  mockFetch({ standings: false });
  const b = await loadBundle('/bundle');
  // The standings artifact is OPTIONAL: a 404 yields null, and the rest of the bundle still loads.
  expect(b.standings).toBeNull();
  expect(b.schedule.data.group.length).toBeGreaterThan(0); // the bundle itself is intact
  expect(b.tournament).toBeTruthy();
});
