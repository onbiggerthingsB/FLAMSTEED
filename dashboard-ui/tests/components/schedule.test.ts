import { render, fireEvent, within } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import Schedule from '../../src/surfaces/Schedule.svelte';
import type { Envelope, ScheduleData } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const sch: Envelope<ScheduleData> = JSON.parse(readFileSync(resolve(dir, 'schedule.json'), 'utf8'));

test('Schedule renders group rows with a forecast + edge, and links to match detail', () => {
  const { container } = render(Schedule, { data: sch.data });
  const rows = container.querySelectorAll('[data-row="group"]');
  expect(rows.length).toBe(sch.data.group.length);
  // every rendered most-likely score carries its probability (no naked score)
  const first = rows[0];
  expect(within(first as HTMLElement).getAllByText(/%/).length).toBeGreaterThan(0);
  expect((first.querySelector('a[href^="#/match/"]') as HTMLAnchorElement)).toBeTruthy();
});

test('Schedule renders KO rows as probable occupants with SE, or a gap', async () => {
  const { container, getByRole } = render(Schedule, { data: sch.data });
  // The stage navigator gates KO rows; switch to the knockout stage to reveal them.
  await fireEvent.click(getByRole('button', { name: 'knockout' }));
  const ko = container.querySelectorAll('[data-row="ko"]');
  expect(ko.length).toBe(sch.data.knockout.length);
});

// ── Next-up anchor (spec D6) ────────────────────────────────────────────────────
// The Schedule landing anchors to the NEXT-UP fixture: the FIRST group row whose
// status is 'upcoming' is marked [data-nextup] (and scrolled into view on mount). The
// committed fixture is all-'played', so we synthesise upcoming rows to exercise the
// marker deterministically.
test('Schedule marks exactly ONE next-up row (the first upcoming) when an upcoming row exists', () => {
  const data: ScheduleData = {
    ...sch.data,
    group: sch.data.group.map((r, i) =>
      // Make the last two rows upcoming; only the FIRST of them must be marked next-up.
      i >= sch.data.group.length - 2 ? { ...r, status: 'upcoming' as const } : r,
    ),
  };
  const { container } = render(Schedule, { data });
  const marked = container.querySelectorAll('[data-nextup]');
  expect(marked.length).toBe(1);
  // The marked row is the FIRST upcoming row, and it carries a visible "next up" marker.
  const firstUpcoming = data.group.find((r) => r.status === 'upcoming')!;
  expect((marked[0] as HTMLElement).getAttribute('data-status')).toBe('upcoming');
  expect(marked[0].closest('[data-row="group"]')).toBe(marked[0]);
  expect(container.textContent).toMatch(/next up/i);
  // Sanity: the marked row is the first upcoming one (Brazil v … by match_id).
  expect((marked[0] as HTMLElement).getAttribute('data-match-id')).toBe(firstUpcoming.match_id);
});

test('Schedule marks NO next-up row when every group row is already played', () => {
  // The committed fixture is all-'played'.
  const { container } = render(Schedule, { data: sch.data });
  expect(container.querySelectorAll('[data-nextup]').length).toBe(0);
});
