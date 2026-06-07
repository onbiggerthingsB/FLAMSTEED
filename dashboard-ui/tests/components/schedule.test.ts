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

// ── GHOST LINE (spec §4) ──────────────────────────────────────────────────────────
// A group row whose forecast_summary carries the de-vigged ENTRY market_1x2 ghosts the
// sharp line into its WinBar: the `.ghost` markers + the "line: H .. · D .. · A .." legend
// render INSIDE the marked distribution region. The committed Brazil-Mexico row carries a
// market_1x2 (mirrors its edge's de-vig); a gapped-edge row carries none -> no line.
test('Schedule ghosts the de-vigged market line into the WinBar for a row that carries market_1x2', () => {
  const { container } = render(Schedule, { data: sch.data });
  // The Brazil-Mexico row (real edge -> market_1x2) is the one with a line.
  const row = container.querySelector('[data-match-id="Brazil__Mexico__2024-05-02"]') as HTMLElement;
  expect(row).toBeTruthy();
  // The ghosted sharp-line markers + the "line:" legend live inside the distribution region.
  expect(row.querySelector('.ghost')).toBeTruthy(); // the ghost markers painted
  expect(row.textContent).toMatch(/line:\s*H/); // the line legend readout rendered
  // The line legend % sits INSIDE the marked distribution region (no naked number).
  const legend = row.querySelector('.ln') as HTMLElement;
  expect(legend).toBeTruthy();
  expect(legend.closest('[data-uncertainty="distribution"]')).toBeTruthy();
});

test('Schedule renders NO ghost line for a row whose forecast_summary has no market_1x2', () => {
  const { container } = render(Schedule, { data: sch.data });
  // Brazil-Argentina is a coverage-gap edge -> no market_1x2 -> no ghosted line.
  const row = container.querySelector('[data-match-id="Brazil__Argentina__2024-05-01"]') as HTMLElement;
  expect(row).toBeTruthy();
  expect(row.querySelector('.ghost')).toBeNull();
  expect(row.querySelector('.ln')).toBeNull();
  expect(row.textContent).not.toMatch(/line:\s*H/);
});

test('Schedule renders KO rows as probable occupants with SE, or a gap', async () => {
  const { container, getByRole } = render(Schedule, { data: sch.data });
  // The stage navigator gates KO rows; switch to the knockout stage to reveal them.
  await fireEvent.click(getByRole('button', { name: 'knockout' }));
  const ko = container.querySelectorAll('[data-row="ko"]');
  expect(ko.length).toBe(sch.data.knockout.length);
});

// FIX G (a11y): the stage toggle buttons expose their pressed state to assistive tech.
test('Schedule stage toggle buttons carry aria-pressed reflecting the active stage', async () => {
  const { getByRole } = render(Schedule, { data: sch.data });
  const group = getByRole('button', { name: 'group' });
  const knockout = getByRole('button', { name: 'knockout' });
  // Default stage is group.
  expect(group.getAttribute('aria-pressed')).toBe('true');
  expect(knockout.getAttribute('aria-pressed')).toBe('false');
  await fireEvent.click(knockout);
  expect(group.getAttribute('aria-pressed')).toBe('false');
  expect(knockout.getAttribute('aria-pressed')).toBe('true');
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
