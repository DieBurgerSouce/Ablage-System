/**
 * Perception-Audit-Konfiguration (Erste-10-Minuten-Walks).
 *
 * Bewusst getrennt von playwright.config.ts:
 * - KEIN globalSetup / KEIN Auth-Cache: die Walks loggen sich echt per UI ein
 *   (Onboarding + Login-Erlebnis SIND Teil des Audits).
 * - workers: 1, fullyParallel: false — ehrliche Timings gegen den einzelnen
 *   uvicorn-Worker und Schutz vor dem Login-Rate-Limit (5/min/IP).
 * - Keine Traces/Videos: Stoppuhr-Messungen nicht verfaelschen; Beweis-
 *   Screenshots macht der Walk selbst gezielt (helpers.shoot()).
 *
 * Aufruf:  PERCEPTION_ITER=01 npx playwright test --config playwright.perception.config.ts
 */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/perception',
  testMatch: '**/*.walk.ts',
  timeout: 600_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:80',
    screenshot: 'off',
    trace: 'off',
    video: 'off',
    viewport: { width: 1440, height: 900 },
    locale: 'de-DE',
    timezoneId: 'Europe/Berlin',
  },
});
