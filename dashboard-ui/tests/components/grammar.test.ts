import { render, screen } from '@testing-library/svelte';
import Estimate from '../../src/components/Estimate.svelte';
import CoverageGap from '../../src/components/CoverageGap.svelte';
import CredibleInterval from '../../src/components/CredibleInterval.svelte';
import EdgeChip from '../../src/components/EdgeChip.svelte';
import HonestyBar from '../../src/components/HonestyBar.svelte';
import WinBar from '../../src/components/WinBar.svelte';
import ScorePill from '../../src/components/ScorePill.svelte';

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
