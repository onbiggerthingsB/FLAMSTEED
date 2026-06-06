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
