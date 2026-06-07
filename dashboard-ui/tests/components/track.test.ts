import { render, screen } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import Track from '../../src/surfaces/Track.svelte';
import type { Envelope, TrackData, TrackReal } from '../../src/lib/types';

const dir = resolve(__dirname, '../fixtures/bundle');
const tr: Envelope<TrackData> = JSON.parse(readFileSync(resolve(dir, 'track.json'), 'utf8'));

test('Track renders a coverage gap honestly when no records', () => {
  // The committed fixture's track.json data IS a coverage_gap (no backtest
  // records supplied to the demo build): the honest "insufficient coverage" path.
  const { container } = render(Track, { data: tr.data });
  expect(container.querySelector('[data-coverage-gap]')).toBeInTheDocument();
  // No performance metrics are fabricated when there are no records.
  expect(container.querySelector('table')).not.toBeInTheDocument();
  expect(screen.queryByText(/RPS/i)).not.toBeInTheDocument();
});

test('Track renders CLV/RPS + reliability for a real track', () => {
  const real: TrackReal = {
    n_bets: 40, beat_close_rate: 0.58, avg_clv: 0.021,
    rps: { model: 0.18, market: 0.19, elo: 0.21 },
    reliability: [{ bin_lo: 0.6, bin_hi: 0.7, n: 12, forecast_mean: 0.64, empirical: 0.58 }],
    is_synthetic: true,
  };
  const { container } = render(Track, { data: real });
  expect(screen.getByText(/beat[- ]close/i)).toBeInTheDocument();
  // 58% appears twice (beat-close rate AND the bin's empirical) — assert it renders.
  expect(screen.getAllByText(/58%/).length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText(/RPS/i)).toBeInTheDocument();
  // CLV is the primary number; the model RPS should be present too.
  expect(screen.getByText(/avg CLV/i)).toBeInTheDocument();
  expect(screen.getByText(/0\.18/)).toBeInTheDocument();
  // The reliability bin renders its range, n, forecast vs empirical.
  expect(screen.getByText(/64%/)).toBeInTheDocument();
  // No fabricated SE companion on these backward-looking performance stats.
  expect(container.querySelector('[data-uncertainty]')).not.toBeInTheDocument();
});

test('Track shows "—" for null metrics and never fabricates a point for an empty bin', () => {
  const real: TrackReal = {
    n_bets: 7,
    beat_close_rate: null,
    avg_clv: null,
    rps: { model: 0.2, market: null, elo: null },
    reliability: [
      // An empty bin: n=0 with null forecast/empirical — must render "—", never a point.
      { bin_lo: 0.5, bin_hi: 0.6, n: 0, forecast_mean: null, empirical: null },
    ],
    is_synthetic: true,
  };
  const { container } = render(Track, { data: real });
  // Null performance metrics render the em dash, not a fabricated number.
  const dashes = screen.getAllByText('—');
  expect(dashes.length).toBeGreaterThanOrEqual(2); // beat-close + avg CLV at least
  // The empty reliability bin shows n=0 and "—" for both forecast and empirical.
  const cells = Array.from(container.querySelectorAll('tbody td')).map((c) => c.textContent?.trim());
  expect(cells).toContain('0');
  expect(cells.filter((c) => c === '—').length).toBeGreaterThanOrEqual(2); // forecast + empirical of the empty bin
});
