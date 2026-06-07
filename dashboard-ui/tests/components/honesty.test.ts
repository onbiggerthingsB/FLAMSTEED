// Convergence-hardening FIX A: the NON-REAL banner must be gated on `is_synthetic`,
// NOT on banner-presence. Fail-safe honesty: a synthetic bundle whose `banner` field is
// missing/empty must STILL render the DRY-RUN chip — the UI must not DEPEND on the
// producer always emitting a banner string. (Workflow #5: the on-screen honesty claim is
// sourced from the producer's authoritative banner when present, with a hardcoded fallback.)

import { render, screen } from '@testing-library/svelte';
import { test, expect, describe } from 'vitest';
import HonestyBar from '../../src/components/HonestyBar.svelte';
import type { Provenance } from '../../src/lib/types';

const base = (over: Partial<Provenance>): Provenance => ({
  as_of: '2026-06-06T19:31:22Z',
  posterior_key: '123a88ae08fd5ae5',
  git: 'eb4b7b1',
  is_synthetic: false,
  n_sims: 20000,
  ...over,
});

const DEFAULT_BANNER = /DRY-RUN · SYNTHETIC ODDS · NOT REAL/;

describe('HonestyBar: NON-REAL banner is gated on is_synthetic (fail-safe), not banner-presence', () => {
  test('(a) is_synthetic:true with NO banner STILL renders the DRY-RUN chip (fail-safe default)', () => {
    // The producer-omitted-banner case: a synthetic bundle MUST never silently read as REAL.
    render(HonestyBar, { provenance: base({ is_synthetic: true }) }); // banner undefined
    expect(screen.getByText(DEFAULT_BANNER)).toBeInTheDocument();
  });

  test('(b) is_synthetic:false with NO banner renders NO DRY-RUN chip (a real bundle is not mislabeled)', () => {
    const { container } = render(HonestyBar, { provenance: base({ is_synthetic: false }) });
    expect(container.querySelector('.dryrun')).toBeNull();
    expect(screen.queryByText(DEFAULT_BANNER)).toBeNull();
  });

  test("(c) is_synthetic:true WITH a banner shows the producer's banner text (authoritative claim)", () => {
    const producerBanner = 'DRY-RUN · SYNTHETIC ODDS · NOT REAL — no real odds, no bet placed.';
    render(HonestyBar, { provenance: base({ is_synthetic: true, banner: producerBanner }) });
    expect(screen.getByText(producerBanner)).toBeInTheDocument();
  });
});
