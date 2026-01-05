import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
    testDir: './e2e',
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : undefined,
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
            testIgnore: /auth\.setup\.ts/,
        },
        {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] },
            testIgnore: /auth\.setup\.ts/,
        },
        {
            name: 'webkit',
            use: { ...devices['Desktop Safari'] },
            testIgnore: /auth\.setup\.ts/,
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
