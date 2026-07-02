import { defineConfig, devices } from '@playwright/test';

// W2.3: Die pwa-offline-Specs UND der Perf-Benchmark ('Kundenliste laden',
// Budget 6000ms) laufen ISOLIERT und SERIELL im dedizierten 'pwa'-Projekt
// (workers=1 via A-Z-Loop). Aus den parallelen Cross-Browser-Projekten werden
// sie per grepInvert ausgeschlossen, damit sie NICHT doppelt und nicht unter
// 4-Worker-Last laufen (SW-Precache-Contention → newPage-Timeout, Benchmark-
// Flake; A-Z-Loop 7). Ein einzelner Regex als Single Source of Truth fuer
// Ein-/Ausschluss verhindert Drift zwischen den Projekten.
const PWA_SERIAL_GREP = /PWA Offline Features|Ablage - Performance Benchmark Report/;

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
        // a11y-Specs laufen NUR im dedizierten a11y-Projekt (unten):
        // Unter paralleler Last messen axe-Scans transiente Renderzustaende
        // (Einblende-Animationen, Avatar-Lade-Fallbacks) und werden flaky.
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
            testIgnore: /auth\.setup\.ts|global-setup\.ts|[\\/]a11y[\\/]/,
            grepInvert: PWA_SERIAL_GREP,
        },
        {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] },
            testIgnore: /auth\.setup\.ts|global-setup\.ts|[\\/]a11y[\\/]/,
            grepInvert: PWA_SERIAL_GREP,
        },
        {
            name: 'webkit',
            use: { ...devices['Desktop Safari'] },
            testIgnore: /auth\.setup\.ts|global-setup\.ts|[\\/]a11y[\\/]/,
            grepInvert: PWA_SERIAL_GREP,
        },
        {
            // W2.3: Isoliertes, serielles Projekt fuer pwa-offline + Perf-Benchmark.
            // fullyParallel=false serialisiert die Tests INNERHALB einer Datei;
            // die vollstaendige Serialisierung ueber beide Dateien hinweg stellt
            // der A-Z-Loop her, indem er dieses Projekt mit `--workers=1` faehrt
            // (scripts/sim_a_to_z.ps1). Chromium-Device, weil die File-Handling-/
            // launchQueue-Tests (open-file) Chromium voraussetzen.
            name: 'pwa',
            use: { ...devices['Desktop Chrome'] },
            fullyParallel: false,
            grep: PWA_SERIAL_GREP,
            testIgnore: /auth\.setup\.ts|global-setup\.ts|[\\/]a11y[\\/]/,
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
