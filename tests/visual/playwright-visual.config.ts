/**
 * Playwright Visual Regression Testing Configuration
 *
 * Konfiguration fuer Screenshot-basierte visuelle Regression-Tests.
 *
 * Features:
 * - Automatische Baseline-Screenshots
 * - Pixel-by-Pixel Vergleich
 * - Threshold-basierte Toleranz
 * - CI/CD Integration
 * - Multiple Viewport-Groessen
 */

import { defineConfig, devices } from '@playwright/test';
import path from 'path';

// Visual test specific settings
const VISUAL_TEST_CONFIG = {
  // Screenshot comparison thresholds
  maxDiffPixelRatio: 0.05, // Max 5% difference allowed
  threshold: 0.2, // Pixel color threshold (0-1)

  // Snapshot directory structure
  snapshotsDir: './tests/visual/__snapshots__',
  actualDir: './tests/visual/__snapshots__/actual',
  expectedDir: './tests/visual/__snapshots__/expected',
  diffDir: './tests/visual/__snapshots__/diff',

  // Baseline update settings
  updateSnapshots: process.env.UPDATE_SNAPSHOTS === 'true' ? 'all' : 'missing',
};

// Viewport configurations for different screen sizes
const VIEWPORTS = {
  desktop: { width: 1920, height: 1080 },
  laptop: { width: 1366, height: 768 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 375, height: 667 },
};

export default defineConfig({
  testDir: './tests/visual',
  testMatch: '**/*.visual.spec.ts',

  // Parallel execution disabled for visual tests to ensure consistent screenshots
  fullyParallel: false,
  workers: 1,

  // Retries for flaky visual tests
  retries: process.env.CI ? 2 : 0,

  // Strict mode for CI
  forbidOnly: !!process.env.CI,

  // Reporter configuration
  reporter: [
    ['list'],
    ['html', {
      outputFolder: 'playwright-visual-report',
      open: 'never',
    }],
    // Custom visual diff reporter
    ['json', {
      outputFile: 'playwright-visual-report/visual-results.json',
    }],
  ],

  // Global settings
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:80',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off', // Disable video for visual tests

    // Visual comparison settings
    // These are applied globally but can be overridden per-test
  },

  // Snapshot settings
  snapshotPathTemplate: '{testDir}/__snapshots__/{testFilePath}/{arg}{ext}',

  // Update baseline snapshots
  updateSnapshots: VISUAL_TEST_CONFIG.updateSnapshots as 'all' | 'missing' | 'none',

  // Test timeout (visual tests may take longer)
  timeout: 60000,
  expect: {
    timeout: 30000,
    // Visual comparison settings
    toHaveScreenshot: {
      maxDiffPixelRatio: VISUAL_TEST_CONFIG.maxDiffPixelRatio,
      threshold: VISUAL_TEST_CONFIG.threshold,
      animations: 'disabled', // Disable animations for consistent screenshots
    },
    toMatchSnapshot: {
      maxDiffPixelRatio: VISUAL_TEST_CONFIG.maxDiffPixelRatio,
      threshold: VISUAL_TEST_CONFIG.threshold,
    },
  },

  // Browser projects for visual testing
  projects: [
    // Desktop Chrome - Primary visual testing browser
    {
      name: 'desktop-chrome',
      use: {
        ...devices['Desktop Chrome'],
        viewport: VIEWPORTS.desktop,
        deviceScaleFactor: 1,
      },
    },

    // Desktop Firefox - Secondary browser
    {
      name: 'desktop-firefox',
      use: {
        ...devices['Desktop Firefox'],
        viewport: VIEWPORTS.desktop,
        deviceScaleFactor: 1,
      },
    },

    // Laptop viewport
    {
      name: 'laptop-chrome',
      use: {
        ...devices['Desktop Chrome'],
        viewport: VIEWPORTS.laptop,
        deviceScaleFactor: 1,
      },
    },

    // Tablet viewport (iPad)
    {
      name: 'tablet-safari',
      use: {
        ...devices['iPad (gen 7)'],
      },
    },

    // Mobile viewport (iPhone)
    {
      name: 'mobile-safari',
      use: {
        ...devices['iPhone 12'],
      },
    },

    // Dark mode specific project
    {
      name: 'dark-mode',
      use: {
        ...devices['Desktop Chrome'],
        viewport: VIEWPORTS.desktop,
        colorScheme: 'dark',
      },
    },

    // Light mode specific project
    {
      name: 'light-mode',
      use: {
        ...devices['Desktop Chrome'],
        viewport: VIEWPORTS.desktop,
        colorScheme: 'light',
      },
    },

    // High contrast modes (for accessibility)
    {
      name: 'high-contrast',
      use: {
        ...devices['Desktop Chrome'],
        viewport: VIEWPORTS.desktop,
        // Will be set via page.emulateMedia in tests
      },
    },
  ],

  // Web server configuration (if needed)
  webServer: process.env.CI ? undefined : {
    command: 'echo "Using Docker frontend at port 80"',
    url: 'http://localhost:80',
    reuseExistingServer: true,
    timeout: 5000,
  },
});

// Export visual test helper settings
export const visualTestSettings = {
  thresholds: VISUAL_TEST_CONFIG,
  viewports: VIEWPORTS,

  // Pages to test for visual regression
  keyPages: [
    { name: 'dashboard', path: '/', waitFor: 'networkidle' },
    { name: 'document-list', path: '/', waitFor: 'networkidle' },
    { name: 'upload', path: '/upload', waitFor: 'domcontentloaded' },
    { name: 'customers', path: '/kunden', waitFor: 'networkidle' },
    { name: 'suppliers', path: '/lieferanten', waitFor: 'networkidle' },
    { name: 'banking-transactions', path: '/admin/banking/transactions', waitFor: 'networkidle' },
    { name: 'dunning', path: '/admin/mahnungen', waitFor: 'networkidle' },
    { name: 'automation', path: '/automation', waitFor: 'networkidle' },
  ],

  // Elements to mask during screenshot (dynamic content)
  maskElements: [
    '[data-testid="timestamp"]',
    '.date-time',
    '.relative-time',
    '[data-testid="user-avatar"]',
    '.random-id',
    '.session-id',
  ],

  // Elements to hide during screenshot
  hideElements: [
    '.tooltip',
    '.popover',
    '[role="tooltip"]',
    '.cursor',
    '.caret',
  ],
};
