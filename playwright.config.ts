import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * Playwright configuration for Ablage-System E2E tests.
 *
 * Tests frontend functionality including:
 * - Display modes (dark, light, whitescreen, blackscreen)
 * - Authentication flows
 * - Document upload and processing
 * - Admin panel
 *
 * Authentication:
 * - Uses auth.setup.ts to authenticate before tests
 * - Auth state is stored in tests/frontend/e2e/.auth/user.json
 * - Set TEST_USER_EMAIL and TEST_USER_PASSWORD env vars to use custom credentials
 */

// Path to the authentication state file
const AUTH_STATE_PATH = path.join(__dirname, 'tests/frontend/e2e/.auth/user.json');

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
    // Authentication setup project - runs first
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    // Main tests - depend on setup and use authenticated state
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: AUTH_STATE_PATH,
      },
      dependencies: ['setup'],
    },
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        storageState: AUTH_STATE_PATH,
      },
      dependencies: ['setup'],
    },
    {
      name: 'webkit',
      use: {
        ...devices['Desktop Safari'],
        storageState: AUTH_STATE_PATH,
      },
      dependencies: ['setup'],
    },
    // Mobile viewport tests for responsive design
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
        storageState: AUTH_STATE_PATH,
      },
      dependencies: ['setup'],
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
