/**
 * E2E: Modul-Freeze-Gates (Odoo-Neuausrichtung 2026-07)
 *
 * Beweist den Freeze-Zustand der ERP-/AI-Module (app/core/module_registry.py
 * + frontend/src/lib/frozen-modules.ts):
 * - Frontend: Navigation auf eine gefrorene Route landet per beforeLoad-Guard
 *   auf der statischen Seite /frozen?module=<key> mit deutschem Hinweistext
 *   (auch fuer Kindrouten wie /admin/datev/export — Guard sitzt am Parent).
 * - Backend: gefrorene Router sind deregistriert -> 404 auch AUTHENTIFIZIERT
 *   (kein 401/403-Artefakt), waehrend aktive Endpoints weiter 200 liefern
 *   (Kontrollprobe gegen ein global kaputtes Backend).
 *
 * Reaktivierung eines Moduls: ACTIVE_OPTIONAL_MODULES=<key> setzen, den
 * frozenModuleGuard der Route entfernen und die zugehoerigen Specs
 * (banking-reconciliation, datev-export, lexware-import, dashboard-invoices)
 * wieder scharf schalten.
 *
 * Idempotent: rein lesend.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Freeze-Gates - Frontend leitet auf /frozen um', () => {
  test('Gefrorene Route /banking landet auf /frozen mit deutschem Hinweis', async ({ authenticatedPage: page }) => {
    await page.goto('/banking');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/frozen\?module=banking/, { timeout: 15000 });
    await expect(page.getByText('Modul eingefroren')).toBeVisible({ timeout: 15000 });
    // Deutsches Modul-Label der Sektion (Badge auf der /frozen-Seite)
    await expect(page.getByText('Banking, Zahlungsverkehr & Mahnwesen')).toBeVisible();
    await expect(page.getByText(/stillgelegt/)).toBeVisible();
  });

  test('Kindroute /admin/datev/export wird vom Parent-Guard umgeleitet', async ({ authenticatedPage: page }) => {
    await page.goto('/admin/datev/export');
    await page.waitForLoadState('domcontentloaded');

    await expect(page).toHaveURL(/\/frozen\?module=datev/, { timeout: 15000 });
    await expect(page.getByText('Modul eingefroren')).toBeVisible({ timeout: 15000 });
  });
});

apiTest.describe('Freeze-Gates - Backend-Router liefern 404', () => {
  apiTest('Gefrorene Endpoints liefern authentifiziert 404, aktive weiter 200', async ({ request }) => {
    const headers = { Authorization: `Bearer ${adminToken()}` };

    // Repraesentative, vor dem Freeze verifizierte Endpoints je Modul-Key
    const frozenEndpoints = [
      '/api/v1/banking/accounts', // banking
      '/api/v1/invoices', // invoice_tracking
      '/api/v1/datev/config', // datev
      '/api/v1/lexware/linking-statistics', // lexware
    ];
    for (const ep of frozenEndpoints) {
      const resp = await request.get(`${API_BASE}${ep}`, { headers });
      apiExpect(resp.status(), `${ep} muss seit dem Freeze 404 liefern`).toBe(404);
    }

    // Kontrollprobe: aktiver Admin-Endpoint antwortet weiterhin 200 —
    // die 404s oben stammen also vom Freeze, nicht von einem toten Backend.
    const control = await request.get(`${API_BASE}/api/v1/admin/jobs`, { headers });
    apiExpect(control.status(), 'aktiver Kontroll-Endpoint /admin/jobs').toBe(200);
  });
});
