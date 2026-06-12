/**
 * E2E: Import-Verwaltung mit Import-Runs-Panel (W3-F2)
 *
 * Prueft:
 * - /admin/imports rendert die Import-Verwaltung (h1 "Import-Verwaltung")
 * - Das Panel "Letzte Import-Läufe" (ImportRunsPanel, W3-F2) ist sichtbar
 * - GET /api/v1/imports/runs liefert 200 und eine Listen-Struktur (kein 500)
 * - E-Mail-/Ordner-Import-Konfigurationslisten antworten ohne 500
 *
 * Idempotent: rein lesend.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Import-Verwaltung - UI', () => {
  test('Seite rendert mit Import-Runs-Panel (W3-F2)', async ({ authenticatedPage: page }) => {
    await page.goto('/admin/imports');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    await expect(
      page.getByRole('heading', { name: 'Import-Verwaltung' })
    ).toBeVisible({ timeout: 15000 });

    // W3-F2: Panel "Letzte Import-Läufe"
    await expect(page.getByText('Letzte Import-Läufe')).toBeVisible({ timeout: 15000 });
  });
});

apiTest.describe('Import-Verwaltung - API', () => {
  const headers = () => ({ Authorization: `Bearer ${adminToken()}` });

  apiTest('GET /imports/runs liefert 200 mit Listen-Struktur', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/imports/runs`, { headers: headers() });
    apiExpect(resp.status()).toBe(200);
    const body = await resp.json();
    const runs = Array.isArray(body) ? body : body.runs || body.items;
    apiExpect(Array.isArray(runs)).toBeTruthy();
  });

  apiTest('E-Mail- und Ordner-Import-Configs antworten ohne 500', async ({ request }) => {
    for (const ep of ['/api/v1/imports/email/configs', '/api/v1/imports/folder/configs']) {
      const resp = await request.get(`${API_BASE}${ep}`, { headers: headers() });
      apiExpect(resp.status(), `${ep} darf nicht crashen`).not.toBe(500);
      apiExpect(resp.status()).toBe(200);
    }
  });

  apiTest('Import-Logs antworten ohne 500', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/imports/logs`, { headers: headers() });
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
  });
});
