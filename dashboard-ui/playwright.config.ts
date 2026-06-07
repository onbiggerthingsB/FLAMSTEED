import { defineConfig, devices } from '@playwright/test';

// T10 e2e: a FAST, DETERMINISTIC, OFFLINE smoke. The webServer runs `npm run build`
// (whose copy-bundle.mjs populates public/bundle/ from the committed NON-REAL fixture
// when there is no live data/dashboard/) then serves dist/ via `vite preview` — so the
// app always loads the synthetic DRY-RUN bundle, no network/real feed involved.
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run build && npm run preview',
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
