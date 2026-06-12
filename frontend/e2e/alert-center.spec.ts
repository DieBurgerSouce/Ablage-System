/**
 * E2E: Alert Center
 *
 * Prueft:
 * - /alerts rendert das Alert Center (h1 "Alert Center") mit den
 *   Statistik-Karten "Aktive Alerts", "Kritisch", "Letzte 24h", "Gelöst"
 *   (verifizierte CardTitles aus AlertCenter.tsx)
 * - GET /api/v1/alerts liefert 200 (kein 500)
 *
 * Idempotent: rein lesend, keine Alerts werden quittiert/geloescht.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Alert Center - UI', () => {
  test('Seite rendert mit Statistik-Karten', async ({ authenticatedPage: page }) => {
    await page.goto('/alerts');
    await page.waitForLoadState('networkidle');

    await expect(
      page.getByRole('heading', { name: 'Alert Center' })
    ).toBeVisible({ timeout: 15000 });

    for (const cardTitle of ['Aktive Alerts', 'Kritisch', 'Letzte 24h', 'Gelöst']) {
      await expect(page.getByText(cardTitle).first()).toBeVisible();
    }
  });
});

apiTest.describe('Alert Center - API', () => {
  apiTest('GET /alerts liefert 200 (kein 500)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/alerts`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
  });
});
