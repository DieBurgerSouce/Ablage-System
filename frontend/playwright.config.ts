import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
    testDir: './e2e',
    globalSetup: './e2e/global-setup.ts',
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    // Lokal hart auf 4 Worker begrenzen: Mit `undefined` startet Playwright auf
    // dieser Maschine 16 Worker und ueberlastet das Single-Uvicorn-Backend
    // (socket hang up / ECONNRESET / 502 / 503, x-response-time >3s fuer triviale
    // Requests — siehe QA-Lauf 2026-06-12).
    workers: process.env.CI ? 1 : 4,
    reporter: 'html',
    use: {
        baseURL: process.env.BASE_URL || 'http://localhost:80',
        trace: 'on-first-retry',
    },
    projects: [
        // Tests use authenticatedPage fixture for auth (no setup project needed)
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
            testIgnore: /auth\.setup\.ts|global-setup\.ts/,
        },
        {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] },
            testIgnore: /auth\.setup\.ts|global-setup\.ts/,
        },
        {
            name: 'webkit',
            use: { ...devices['Desktop Safari'] },
            testIgnore: /auth\.setup\.ts|global-setup\.ts/,
        },
        {
            name: 'a11y',
            use: { ...devices['Desktop Chrome'] },
            testDir: './e2e/a11y',
            testMatch: /\.a11y\.spec\.ts$/,
        },
    ],
    // Use Docker container when available, otherwise Vite dev server
    webServer: process.env.CI ? undefined : {
        command: 'echo "Using Docker frontend at port 80"',
        url: 'http://localhost:80',
        reuseExistingServer: true,
        timeout: 5000,
    },
});
