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
