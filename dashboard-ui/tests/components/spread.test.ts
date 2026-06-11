import { render, fireEvent } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import SpreadLine from '../../src/components/SpreadLine.svelte';
import Schedule from '../../src/surfaces/Schedule.svelte';
import MatchDetail from '../../src/surfaces/MatchDetail.svelte';
import type { Envelope, ScheduleData, CoverPair } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const sch: Envelope<ScheduleData> = JSON.parse(readFileSync(resolve(dir, 'schedule.json'), 'utf8'));

// ── SpreadLine component (unit) ──────────────────────────────────────────────────
// One line: "{home} −1.5 · {p}%   ·   {away} +1.5 · {q}%". A DERIVED readout of the
// scoreline distribution → it lives inside data-uncertainty="distribution" (the distribution
// IS the uncertainty, same as WinBar / ScorePill), never a naked number.

test('SpreadLine renders both cover sides with the ±1.5 line and the model %s', () => {
  const cover: CoverPair = { home: 0.246, away: 0.754 };
  const { container, getByText } = render(SpreadLine, { cover, home: 'Brazil', away: 'Mexico' });
  // Both teams + their signed line render.
  expect(getByText(/Brazil/)).toBeTruthy();
  expect(getByText(/Mexico/)).toBeTruthy();
  // The U+2212 minus (not a hyphen) on the home line, and a "+" on the away line.
  expect(container.textContent).toContain('Brazil −1.5');
  expect(container.textContent).toContain('Mexico +1.5');
  // Same rounding style as the scoreline percentages (pct(), 0 dp): 25% / 75%.
  expect(container.textContent).toContain('25%');
  expect(container.textContent).toContain('75%');
  // Labeled as a MODEL probability.
  expect(container.textContent?.toLowerCase()).toContain('model');
});

test('SpreadLine: every visible % sits inside a data-uncertainty region (no naked number)', () => {
  const { container } = render(SpreadLine, { cover: { home: 0.31, away: 0.69 }, home: 'A', away: 'B' });
  const region = container.querySelector('[data-uncertainty="distribution"]');
  expect(region).not.toBeNull();
  // Both % readouts are inside the distribution region.
  const pctNodes = [...container.querySelectorAll('span')].filter((n) => /\d%/.test(n.textContent ?? ''));
  expect(pctNodes.length).toBeGreaterThan(0);
  for (const n of pctNodes) expect(n.closest('[data-uncertainty]')).not.toBeNull();
  // No "±?" unknown-SE token leaks into a KNOWN distribution readout.
  expect(container.textContent).not.toContain('±?');
});

// ── Schedule GROUP card: the cover line renders UNDER the win-bar when present ─────
// The committed fixture predates the feature (no cover key), so inject the pair into the
// first group row — the same clone-and-mutate pattern the existing schedule tests use. The
// SpreadLine renders only when forecast_summary.cover is present.

function withCover(data: ScheduleData, p: CoverPair): ScheduleData {
  return {
    ...data,
    group: data.group.map((r, i) =>
      i === 0 && !('coverage_gap' in r.forecast_summary)
        ? { ...r, forecast_summary: { ...r.forecast_summary, cover: p } }
        : r,
    ),
  };
}

test('Schedule group card shows the ±1.5 cover line UNDER the win-bar when cover is present', () => {
  const data = withCover(sch.data, { home: 0.22, away: 0.78 });
  const { container } = render(Schedule, { data });
  const first = container.querySelector('[data-row="group"]') as HTMLElement;
  // The cover line rendered inside the SAME .dist column as (i.e. UNDER) the WinBar.
  const dist = first.querySelector('.dist') as HTMLElement;
  const winbar = dist.querySelector('.winbar-wrap');
  const spread = dist.querySelector('[data-spread]');
  expect(winbar).toBeTruthy();
  expect(spread).toBeTruthy();
  // It carries the home/away teams and the ±1.5 line.
  expect(spread?.textContent).toContain(`${data.group[0].home} −1.5`);
  expect(spread?.textContent).toContain(`${data.group[0].away} +1.5`);
  // The cover %s sit inside the distribution region (no naked number).
  expect(spread?.closest('[data-uncertainty="distribution"]') ?? spread?.querySelector('[data-uncertainty="distribution"]')).toBeTruthy();
  // Scope the % readouts to the SpreadLine element (the WinBar legend shares the .dist column).
  expect(spread?.textContent).toContain('22%');
  expect(spread?.textContent).toContain('78%');
});

test('Schedule group card renders NO cover line when forecast_summary has no cover', () => {
  // The committed fixture has no cover key → the line is omitted (never fabricated).
  const { container } = render(Schedule, { data: sch.data });
  expect(container.querySelector('[data-spread]')).toBeNull();
});

test('Schedule KNOCKOUT view has no cover line (no concrete matchup → no grid → no cover)', async () => {
  const data = withCover(sch.data, { home: 0.22, away: 0.78 });
  const { container, getByRole } = render(Schedule, { data });
  await fireEvent.click(getByRole('button', { name: 'knockout' }));
  // KO rows are unresolved occupant lists, never a concrete home/away grid — so no cover line.
  expect(container.querySelector('[data-row="ko"]')).toBeTruthy();
  expect(container.querySelector('[data-spread]')).toBeNull();
});

// ── MatchDetail: the cover line renders under the win-bar when the forecast carries cover ──

test('MatchDetail shows the cover line under the win-bar when forecast.cover is present', async () => {
  const files = ['Brazil__Argentina__2024-05-01'];
  const matchId = files[0];
  globalThis.fetch = (async (url: string) => {
    const rel = String(url).replace(/^.*\/bundle\//, '');
    const env = JSON.parse(readFileSync(resolve(dir, rel), 'utf8'));
    // Inject a cover pair into the fixture detail (the committed fixture predates the feature).
    if (env?.data?.forecast) env.data.forecast.cover = { home: 0.27, away: 0.73 };
    return { ok: true, json: async () => env } as Response;
  }) as typeof fetch;

  const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId });
  // The cover line appears once the fixture resolves.
  const spread = await new Promise<HTMLElement>((res) => {
    const tick = () => {
      const el = container.querySelector('[data-spread]') as HTMLElement | null;
      if (el) res(el);
      else setTimeout(tick, 5);
    };
    tick();
  });
  expect(spread.closest('[data-uncertainty="distribution"]') ?? spread.querySelector('[data-uncertainty="distribution"]')).toBeTruthy();
  // Scope the % assertions to the SpreadLine element — the WinBar legend may coincidentally
  // share a % with the cover, so assert on the cover line specifically (no cross-element match).
  expect(spread.textContent).toContain('Brazil −1.5');
  expect(spread.textContent).toContain('27%');
  expect(spread.textContent).toContain('Argentina +1.5');
  expect(spread.textContent).toContain('73%');
});

test('MatchDetail renders NO cover line when the forecast carries no cover (back-compat)', async () => {
  const matchId = 'Brazil__Argentina__2024-05-01';
  globalThis.fetch = (async (url: string) => {
    const rel = String(url).replace(/^.*\/bundle\//, '');
    return { ok: true, json: async () => JSON.parse(readFileSync(resolve(dir, rel), 'utf8')) } as Response;
  }) as typeof fetch;
  const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId });
  // Wait for the win-bar (the section rendered), then assert no cover line.
  await new Promise<void>((res) => {
    const tick = () => (container.querySelector('.winbar-wrap') ? res() : setTimeout(tick, 5));
    tick();
  });
  expect(container.querySelector('[data-spread]')).toBeNull();
});
