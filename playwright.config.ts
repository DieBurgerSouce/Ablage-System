import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for Ablage-System E2E tests.
 *
 * Tests frontend functionality including:
 * - Display modes (dark, light, whitescreen, blackscreen)
 * - Authentication flows
 * - Document upload and processing
 * - Admin panel
 */
export default defineConfig({
  testDir: './tests/frontend/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'playwright-report/results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:80',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // Mobile viewport tests for responsive design
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],
  // Local development server configuration
  webServer: process.env.CI ? undefined : {
    command: 'docker-compose up -d frontend && sleep 5',
    url: 'http://localhost:80',
    reuseExistingServer: true,
    timeout: 120000,
  },
  // Global test timeout
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
});
