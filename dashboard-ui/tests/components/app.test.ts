import { render, screen, waitFor } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import App from '../../src/App.svelte';

const dir = resolve(__dirname, '../fixtures/bundle');
function mockFetch() {
  globalThis.fetch = (async (url: string) => {
    const rel = String(url).replace(/^.*\/bundle\//, '');
    const body = readFileSync(resolve(dir, rel), 'utf8');
    return { ok: true, json: async () => JSON.parse(body) } as Response;
  }) as typeof fetch;
}

beforeEach(() => { location.hash = ''; mockFetch(); });

test('App loads the bundles and lands on the Value Bets primary surface + honesty bar', async () => {
  render(App);
  // The model honesty bar still renders (loaded for the secondary surfaces).
  await waitFor(() => expect(screen.getByText(/DRY-RUN/)).toBeInTheDocument());
  expect(screen.getByRole('navigation')).toBeInTheDocument();   // surface nav
  // PRIMARY landing = Value Bets: the SIGNAL-ONLY banner renders.
  await waitFor(() => expect(screen.getByText(/SIGNAL-ONLY/)).toBeInTheDocument());
  // Value Bets is the active (current) nav link on the empty hash.
  expect(screen.getByRole('link', { name: 'Value Bets' }).getAttribute('aria-current')).toBe('page');
});

test('App labels the Forecast group as a non-market-edge secondary surface', async () => {
  render(App);
  await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument());
  // The Forecast nav carries a visible "does NOT beat the market" label.
  expect(screen.getByText(/does NOT beat the market/i)).toBeInTheDocument();
});

// FIX G (a11y): the active surface link carries aria-current="page".
test('App nav marks the active surface link with aria-current="page"', async () => {
  location.hash = '#/tournament';
  render(App);
  await waitFor(() => expect(screen.getByText(/DRY-RUN/)).toBeInTheDocument());
  // A forecast hash (tournament) lights the Forecast group nav as active.
  const active = screen.getByRole('link', { name: 'Forecast' });
  expect(active.getAttribute('aria-current')).toBe('page');
  // Non-active links carry no aria-current.
  expect(screen.getByRole('link', { name: 'Value Bets' }).getAttribute('aria-current')).toBeNull();
  expect(screen.getByRole('link', { name: 'Track Record' }).getAttribute('aria-current')).toBeNull();
});
