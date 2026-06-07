// BracketTree (spec §3 "bracket tree" progressive item): an R32 → R16 → QF → SF → Final
// column layout where each match slot shows its probable occupants (top few, each
// `team prob±se` via Estimate) or a CoverageGap. Built from the knockout rows' feeders.
//
// TDD: this test asserts the rounds render as ordered columns, the slot occupants render
// with their Estimate (data-uncertainty) markers, and a feeder that resolves only deeper
// (a W/L ref → {coverage_gap}) renders a CoverageGap — never a fabricated number.
//
// The no-naked-number guard (tests/no-naked-number.test.ts) ALSO covers this component;
// here we additionally pin the structural contract (columns, ordering, occupant markers).

import { render } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import BracketTree from '../../src/components/BracketTree.svelte';
import type { Envelope, ScheduleData, KoRow } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const sch: Envelope<ScheduleData> = JSON.parse(readFileSync(resolve(dir, 'schedule.json'), 'utf8'));

// A multi-round synthetic knockout chain that exercises EVERY round column + the gap path.
// (The committed fixture is a single Final row; this gives the column ordering + the
// W-feeder coverage-gap branch real coverage, deterministically.)
const occ = (team: string, prob: number, se = 0.003) => ({ team, prob, se });
const multiRound: KoRow[] = [
  // Deliberately OUT OF round order in the source array, to prove the view re-orders columns.
  { match: 104, stage: 'Final', status: 'upcoming', home_ref: 'W101', away_ref: 'W102',
    home_occupants: { coverage_gap: true, reason: 'feeder W101 resolves from a later match' },
    away_occupants: { coverage_gap: true, reason: 'feeder W102 resolves from a later match' } },
  { match: 73, stage: 'R32', status: 'upcoming', home_ref: '1A', away_ref: '3rd-BCDEF',
    home_occupants: [occ('Argentina', 0.51), occ('Mexico', 0.30), occ('Malta', 0.19)],
    away_occupants: [occ('Brazil', 0.40), occ('Croatia', 0.35)] },
  { match: 89, stage: 'R16', status: 'upcoming', home_ref: 'W73', away_ref: 'W74',
    home_occupants: [occ('Argentina', 0.44), occ('Brazil', 0.41)],
    away_occupants: { coverage_gap: true, reason: 'feeder W74 resolves from a later match' } },
  { match: 101, stage: 'QF', status: 'upcoming', home_ref: 'W89', away_ref: 'W90',
    home_occupants: [occ('Argentina', 0.38)],
    away_occupants: [occ('Spain', 0.36)] },
  { match: 102, stage: 'SF', status: 'upcoming', home_ref: 'W97', away_ref: 'W98',
    home_occupants: [occ('France', 0.33)],
    away_occupants: [occ('Argentina', 0.31)] },
];

test('BracketTree renders the committed fixture knockout rows as match slots', () => {
  const { container } = render(BracketTree, { knockout: sch.data.knockout });
  const matches = container.querySelectorAll('[data-bracket-match]');
  expect(matches.length).toBe(sch.data.knockout.length);
  // The committed Final has occupants on both sides → estimates render with their ± companion.
  const ests = container.querySelectorAll('[data-estimate]');
  expect(ests.length).toBeGreaterThan(0);
  ests.forEach((e) => expect(e.querySelector('[data-uncertainty]')).not.toBeNull());
});

test('BracketTree lays out rounds as ordered columns R32 → R16 → QF → SF → Final', () => {
  const { container } = render(BracketTree, { knockout: multiRound });
  const cols = Array.from(container.querySelectorAll('[data-round]')).map(
    (c) => c.getAttribute('data-round'),
  );
  // Every present round shows up as exactly one column, ordered shallow → deep.
  expect(cols).toEqual(['R32', 'R16', 'QF', 'SF', 'Final']);
});

test('BracketTree shows each slot\'s probable occupants via Estimate (with the ± companion)', () => {
  const { container } = render(BracketTree, { knockout: multiRound });
  // The R32 home slot lists its placers, each carrying an Estimate + uncertainty companion.
  const r32 = container.querySelector('[data-round="R32"]')!;
  const estimates = r32.querySelectorAll('[data-estimate]');
  expect(estimates.length).toBeGreaterThan(0);
  estimates.forEach((e) => expect(e.querySelector('[data-uncertainty]')).not.toBeNull());
  // Argentina (a known occupant of the R32 home slot) is named alongside its estimate.
  expect(r32.textContent).toMatch(/Argentina/);
});

test('BracketTree renders a CoverageGap (never a number) for a feeder that resolves deeper', () => {
  const { container } = render(BracketTree, { knockout: multiRound });
  // The R16 away slot is a W74 feeder → a coverage gap, NOT a fabricated occupant %.
  const gaps = container.querySelectorAll('[data-coverage-gap]');
  expect(gaps.length).toBeGreaterThan(0);
  // The Final (both feeders deeper) is entirely gapped — no estimate leaks in.
  const finalCol = container.querySelector('[data-round="Final"]')!;
  expect(finalCol.querySelector('[data-coverage-gap]')).not.toBeNull();
});

test('BracketTree caps the occupant list (top few) per slot', () => {
  // A slot with many occupants must not render an unbounded list — top few only.
  const many: KoRow[] = [
    { match: 73, stage: 'R32', status: 'upcoming', home_ref: '1A', away_ref: '2A',
      home_occupants: Array.from({ length: 8 }, (_, i) => occ(`Team${i}`, 0.5 - i * 0.05)),
      away_occupants: { coverage_gap: true, reason: 'x' } },
  ];
  const { container } = render(BracketTree, { knockout: many });
  const homeSlot = container.querySelector('[data-bracket-slot="home"]')!;
  const ests = homeSlot.querySelectorAll('[data-estimate]');
  expect(ests.length).toBeGreaterThan(0);
  expect(ests.length).toBeLessThanOrEqual(4);
});
