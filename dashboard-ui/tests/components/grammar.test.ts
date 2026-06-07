import { render, screen } from '@testing-library/svelte';
import Estimate from '../../src/components/Estimate.svelte';
import CoverageGap from '../../src/components/CoverageGap.svelte';
import CredibleInterval from '../../src/components/CredibleInterval.svelte';
import EdgeChip from '../../src/components/EdgeChip.svelte';
import HonestyBar from '../../src/components/HonestyBar.svelte';
import WinBar from '../../src/components/WinBar.svelte';
import ScorePill from '../../src/components/ScorePill.svelte';
import ScorelineGrid from '../../src/components/ScorelineGrid.svelte';

test('ScorePill marks the most-likely score+prob as a distribution readout, never "±?"', () => {
  // The scoreline distribution IS the uncertainty (spec §4: "1–0 · 12%"). The prob must
  // sit inside data-uncertainty="distribution" and must NOT render the unknown-SE token "±?"
  // (which would misread known uncertainty as unknown).
  const { container } = render(ScorePill, { ml: { home_goals: 1, away_goals: 0, prob: 0.15 } });
  const region = container.querySelector('[data-uncertainty="distribution"]')!;
  expect(region).toBeInTheDocument();
  expect(region.textContent).toContain('1–0');
  expect(region.textContent).toContain('15%');
  expect(container.textContent).not.toContain('±?');     // distribution carries it, not a missing SE
});

test('WinBar: every visible probability sits inside a data-uncertainty region (no naked legend)', () => {
  // RED before the fix: the legend readout (H 45% ...) lived OUTSIDE the data-uncertainty
  // container, so a visible probability escaped the no-naked-number contract.
  const { container } = render(WinBar, { model: { home: 0.45, draw: 0.27, away: 0.28 } });
  const pctNodes = [...container.querySelectorAll('span')].filter((n) => /\d%/.test(n.textContent ?? ''));
  expect(pctNodes.length).toBeGreaterThan(0);                 // the legend readouts exist
  for (const n of pctNodes) {
    expect(n.closest('[data-uncertainty]')).not.toBeNull();   // ...and each is inside the marker
  }
});

// FIX F: a non-normalized / negative-segment one_x_two must never paint a negative flex.
// The clamp is VISUAL only — the probabilities are NOT recomputed (the title shows raw pct).
test('WinBar clamps each segment flex to max(0, v) (no negative/oversized bar from a bad bundle)', () => {
  const { container } = render(WinBar, { model: { home: -0.2, draw: 0.5, away: 0.9 } });
  const segs = [...container.querySelectorAll('.s')] as HTMLElement[];
  expect(segs.length).toBe(3);
  for (const s of segs) {
    const flex = parseFloat(s.style.flex);
    expect(flex).toBeGreaterThanOrEqual(0); // never a negative flex weight
  }
  // The negative home segment clamps to a zero-weight flex (not a negative one).
  expect(parseFloat(segs[0].style.flex)).toBe(0);
});

test('Estimate renders value with its SE companion and the no-naked markers', () => {
  const { container } = render(Estimate, { value: 0.288, se: 0.0032, label: 'champion' });
  const est = container.querySelector('[data-estimate]')!;
  expect(est).toBeInTheDocument();
  expect(est.querySelector('[data-uncertainty]')).toBeInTheDocument();   // the ± is INSIDE the estimate
  expect(est.textContent).toContain('29%');
  expect(est.textContent).toContain('±');
});

test('Estimate with a null value renders a dash, no naked number', () => {
  const { container } = render(Estimate, { value: null, se: null, label: 'x' });
  expect(container.querySelector('[data-estimate]')!.textContent).toContain('—');
});

test('CoverageGap marks itself as a gap (never a number)', () => {
  const { container } = render(CoverageGap, { reason: 'xg not covered' });
  expect(container.querySelector('[data-coverage-gap]')).toBeInTheDocument();
  expect(screen.getByText(/insufficient coverage/i)).toBeInTheDocument();
});

test('CredibleInterval shows the 94% HDI', () => {
  const { container } = render(CredibleInterval, { value: 0.085, ci: [-0.698, 1.151], label: 'attack' });
  const est = container.querySelector('[data-estimate]')!;
  expect(est.querySelector('[data-uncertainty]')).toBeInTheDocument();
  expect(est.textContent).toContain('HDI');
});

// ── FIX B: CredibleInterval null/non-finite guard (crash-safety, mirrors Estimate) ──
// A null/NaN strength value used to crash the whole MatchDetail surface (value.toFixed on
// null). It must degrade to "—" inside data-estimate (no naked number, no throw).
test('CredibleInterval with a null value renders "—" and does not crash', () => {
  let container: HTMLElement;
  expect(() => {
    ({ container } = render(CredibleInterval, { value: null as unknown as number, ci: [-0.7, 1.15], label: 'x' }));
  }).not.toThrow();
  const est = container!.querySelector('[data-estimate]')!;
  expect(est).toBeInTheDocument();
  expect((est.textContent ?? '').trim()).toBe('—');
});

test('CredibleInterval with a non-finite value renders "—" (no malformed token)', () => {
  const { container } = render(CredibleInterval, { value: Infinity, ci: [-0.7, 1.15], label: 'x' });
  expect((container.querySelector('[data-estimate]')!.textContent ?? '').trim()).toBe('—');
});

test('CredibleInterval with a missing/degenerate ci renders "—" (degrades, no crash)', () => {
  const { container } = render(CredibleInterval, { value: 0.5, ci: undefined as unknown as [number, number], label: 'x' });
  expect((container.querySelector('[data-estimate]')!.textContent ?? '').trim()).toBe('—');
});

// ── FIX C: ScorelineGrid degenerate/empty-grid guard (crash-safety) ──
// An empty / all-zero / non-rectangular grid used to yield -Infinity/0 → NaN% / ÷0 cell
// backgrounds. It must degrade to a CoverageGap, never NaN%/÷0, never throw.
test('ScorelineGrid renders a normal heatmap with the distribution marker', () => {
  const grid = [
    [0.1, 0.2, 0.05],
    [0.15, 0.25, 0.05],
    [0.05, 0.05, 0.05],
  ];
  const { container } = render(ScorelineGrid, { grid, home: 'Brazil', away: 'Mexico' });
  expect(container.querySelector('[data-uncertainty="distribution"]')).not.toBeNull();
  expect(container.querySelector('table')).not.toBeNull();
  // No malformed NaN% leaked into a cell title.
  expect(container.innerHTML).not.toContain('NaN');
});

// FIX G (a11y): a screen-reader summary names the distribution + the most-likely cell.
// The % lives in the aria-label inside data-uncertainty="distribution", so it is exempt.
test('ScorelineGrid exposes a screen-reader summary naming the distribution + most-likely cell', () => {
  const grid = [
    [0.1, 0.2, 0.05],
    [0.15, 0.40, 0.05], // peak at home=1, away=1
  ];
  const { container } = render(ScorelineGrid, { grid, home: 'Brazil', away: 'Mexico' });
  const region = container.querySelector('[data-uncertainty="distribution"]')!;
  const label = region.getAttribute('aria-label') ?? '';
  expect(label).toContain('distribution');
  expect(label).toContain('Brazil 1–1 Mexico'); // the argmax cell
  expect(label).toContain('%');                  // carries its probability
  expect(region.getAttribute('role')).toBe('img');
});

test('ScorelineGrid with an empty grid [[]] degrades to a coverage gap (no NaN, no throw)', () => {
  let container: HTMLElement;
  expect(() => {
    ({ container } = render(ScorelineGrid, { grid: [[]], home: 'Brazil', away: 'Mexico' }));
  }).not.toThrow();
  expect(container!.querySelector('[data-coverage-gap]')).not.toBeNull();
  expect(container!.querySelector('table')).toBeNull();
  expect(container!.innerHTML).not.toContain('NaN');
});

test('ScorelineGrid with an empty outer array [] degrades to a coverage gap', () => {
  const { container } = render(ScorelineGrid, { grid: [], home: 'Brazil', away: 'Mexico' });
  expect(container.querySelector('[data-coverage-gap]')).not.toBeNull();
  expect(container.querySelector('table')).toBeNull();
});

test('ScorelineGrid with an all-zero grid degrades to a coverage gap (no ÷0)', () => {
  const { container } = render(ScorelineGrid, { grid: [[0, 0], [0, 0]], home: 'Brazil', away: 'Mexico' });
  expect(container.querySelector('[data-coverage-gap]')).not.toBeNull();
  expect(container.innerHTML).not.toContain('NaN');
});

test('EdgeChip is a derived comparison, NOT a data-estimate', () => {
  const { container } = render(EdgeChip, { edge: 0.0686, isSynthetic: true });
  expect(container.querySelector('[data-estimate]')).toBeNull();         // edges carry no companion by design
  expect(container.textContent).toContain('6.9%');
});

test('HonestyBar surfaces the NON-REAL banner from provenance', () => {
  render(HonestyBar, { provenance: { as_of: '2026-06-06T19:31:22Z', posterior_key: 'abc', git: 'eb4b7b1', is_synthetic: true, n_sims: 20000, banner: 'DRY-RUN · SYNTHETIC ODDS · NOT REAL — x' } });
  expect(screen.getByText(/DRY-RUN/)).toBeInTheDocument();
  expect(screen.getByText(/2026-06-06/)).toBeInTheDocument();
});
