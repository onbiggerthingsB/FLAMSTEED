import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte({ hot: false })],
  // Svelte 5's package exports resolve to the server build by `default`; under
  // Vitest/jsdom we must opt into the `browser` condition so `mount()` (used by
  // @testing-library/svelte) resolves to the client build instead of the
  // server stub that throws `lifecycle_function_unavailable`.
  resolve: { conditions: ['browser'] },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.ts'],
    exclude: ['tests/e2e/**'],
  },
});
