import { render, screen } from '@testing-library/svelte';
import Estimate from '../../src/components/Estimate.svelte';
import CoverageGap from '../../src/components/CoverageGap.svelte';
import CredibleInterval from '../../src/components/CredibleInterval.svelte';
import EdgeChip from '../../src/components/EdgeChip.svelte';
import HonestyBar from '../../src/components/HonestyBar.svelte';

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
