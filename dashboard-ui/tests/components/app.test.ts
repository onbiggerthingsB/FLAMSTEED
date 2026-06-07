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

test('App loads the bundle and shows the honesty bar + schedule landing', async () => {
  render(App);
  await waitFor(() => expect(screen.getByText(/DRY-RUN/)).toBeInTheDocument());
  expect(screen.getByRole('navigation')).toBeInTheDocument();   // surface nav
});

// FIX G (a11y): the active surface link carries aria-current="page".
test('App nav marks the active surface link with aria-current="page"', async () => {
  location.hash = '#/tournament';
  render(App);
  await waitFor(() => expect(screen.getByText(/DRY-RUN/)).toBeInTheDocument());
  const active = screen.getByRole('link', { name: 'Tournament' });
  expect(active.getAttribute('aria-current')).toBe('page');
  // Non-active links carry no aria-current.
  expect(screen.getByRole('link', { name: 'Schedule' }).getAttribute('aria-current')).toBeNull();
  expect(screen.getByRole('link', { name: 'Track record' }).getAttribute('aria-current')).toBeNull();
});
