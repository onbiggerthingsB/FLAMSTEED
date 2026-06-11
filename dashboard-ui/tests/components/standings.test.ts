import { render, fireEvent, within, cleanup } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, expect, test } from 'vitest';
import Standings from '../../src/surfaces/Standings.svelte';
import Schedule from '../../src/surfaces/Schedule.svelte';
import type { Envelope, StandingsData, ScheduleData } from '../../src/lib/types';

afterEach(() => cleanup());

const dir = resolve(__dirname, '../fixtures/bundle');
const standings: Envelope<StandingsData> = JSON.parse(
  readFileSync(resolve(dir, 'standings.json'), 'utf8'),
);
const sch: Envelope<ScheduleData> = JSON.parse(readFileSync(resolve(dir, 'schedule.json'), 'utf8'));

// ── The surface itself ───────────────────────────────────────────────────────────────────
test('Standings renders one row per team per group, every probability + E[Pts]/E[GD] carrying its SE', () => {
  const { container } = render(Standings, { data: standings.data });
  const groups = Object.keys(standings.data);
  // One section per group.
  groups.forEach((g) => expect(container.querySelector(`[data-group="${g}"]`)).toBeTruthy());
  // One row per team.
  const rows = container.querySelectorAll('[data-team]');
  const totalTeams = groups.reduce((n, g) => n + standings.data[g].length, 0);
  expect(rows.length).toBe(totalTeams);
  // EVERY estimate cell (E[Pts], E[GD], P(top2), P(3rd qual.), P(elim.)) carries its
  // uncertainty companion OR shows "—" (a null) — never a naked number.
  const cells = container.querySelectorAll('[data-estimate]');
  expect(cells.length).toBeGreaterThan(0);
  cells.forEach((c) => {
    const hasCompanion = c.querySelector('[data-uncertainty]') !== null;
    const isDash = (c.textContent ?? '').trim() === '—';
    expect(hasCompanion || isDash).toBe(true);
  });
  // The three fate probabilities AND E[Pts]/E[GD] are all present in a row (5 estimate cells).
  const first = rows[0] as HTMLElement;
  expect(within(first).getAllByText(/±/).length).toBeGreaterThanOrEqual(5);
});

test('Standings rows are sorted by P(advance) descending (the builder pre-sorts; surface preserves)', () => {
  const { container } = render(Standings, { data: standings.data });
  // Read teams in DOM order for group A and confirm they match the fixture's (sorted) order.
  const domOrder = Array.from(container.querySelectorAll('[data-group="A"] [data-team]')).map(
    (r) => r.getAttribute('data-team'),
  );
  const expected = standings.data.A.map((r) => r.team); // fixture is pre-sorted by p_advance desc
  expect(domOrder).toEqual(expected);
  // And the p_advance values are genuinely non-increasing.
  const advs = standings.data.A.map((r) => r.p_advance.value!);
  for (let i = 1; i < advs.length; i++) expect(advs[i]).toBeLessThanOrEqual(advs[i - 1]);
});

test('Standings colours each row by its most-likely fate (a summary; numbers stay visible)', () => {
  const { container } = render(Standings, { data: standings.data });
  standings.data.A.forEach((r) => {
    const row = container.querySelector(`[data-team="${r.team}"]`) as HTMLElement;
    // The row carries its fate as a data attribute (the colour hook) AND a readable tag.
    expect(row.getAttribute('data-fate')).toBe(r.fate);
    if (r.fate) {
      expect(row.querySelector(`[data-fate-tag="${r.fate}"]`)).toBeTruthy();
    }
    // CRITICAL: the probabilities are STILL rendered (colour is a summary, numbers are the claim).
    expect(row.querySelectorAll('[data-estimate]').length).toBe(5);
  });
});

// ── The chip integration (third chip alongside group/knockout) ───────────────────────────
test('Schedule exposes a third "standings" chip alongside group/knockout', () => {
  const { getByRole } = render(Schedule, { data: sch.data, standings: standings.data });
  expect(getByRole('button', { name: 'group' })).toBeTruthy();
  expect(getByRole('button', { name: 'knockout' })).toBeTruthy();
  expect(getByRole('button', { name: 'standings' })).toBeTruthy();
});

test('Schedule standings chip renders the standings table, with aria-pressed reflecting the active chip', async () => {
  const { container, getByRole } = render(Schedule, { data: sch.data, standings: standings.data });
  const standingsBtn = getByRole('button', { name: 'standings' });
  // Default chip is group; standings is not yet rendered.
  expect(standingsBtn.getAttribute('aria-pressed')).toBe('false');
  expect(container.querySelector('[data-row="standings"]')).toBeNull();
  await fireEvent.click(standingsBtn);
  expect(standingsBtn.getAttribute('aria-pressed')).toBe('true');
  // The standings table now renders (group sections + team rows).
  const panel = container.querySelector('[data-row="standings"]');
  expect(panel).toBeTruthy();
  expect(panel!.querySelectorAll('[data-team]').length).toBeGreaterThan(0);
});

// ── Graceful degradation on a PRE-FEATURE bundle (no standings.json) ──────────────────────
test('Schedule standings chip degrades to a CoverageGap when standings is null (pre-feature bundle)', async () => {
  const { container, getByRole } = render(Schedule, { data: sch.data, standings: null });
  await fireEvent.click(getByRole('button', { name: 'standings' }));
  const panel = container.querySelector('[data-row="standings"]') as HTMLElement;
  expect(panel).toBeTruthy();
  // No team rows; an honest coverage gap instead — never a crash, never a naked surface.
  expect(panel.querySelector('[data-team]')).toBeNull();
  expect(panel.querySelector('[data-coverage-gap]')).toBeTruthy();
});

test('Schedule standings chip degrades to a CoverageGap when standings is an empty object', async () => {
  const { container, getByRole } = render(Schedule, { data: sch.data, standings: {} });
  await fireEvent.click(getByRole('button', { name: 'standings' }));
  const panel = container.querySelector('[data-row="standings"]') as HTMLElement;
  expect(panel.querySelector('[data-coverage-gap]')).toBeTruthy();
});
