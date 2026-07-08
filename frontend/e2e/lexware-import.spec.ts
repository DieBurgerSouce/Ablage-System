/**
 * E2E Tests: Lexware Import
 *
 * MODUL EINGEFROREN (Odoo-Neuausrichtung 2026-07): Lexware-Import übernimmt
 * Odoo. Der Backend-Router /api/v1/lexware ist deregistriert (404),
 * /admin/lexware leitet auf /frozen um (frozen-modules.ts, Key 'lexware').
 * Die API-/Routen-Erwartungen sind daher INVERTIERT (Freeze-Beweis).
 * Reaktivierung: ACTIVE_OPTIONAL_MODULES=lexware + Erwartungen zurückdrehen.
 *
 * WEITER AKTIV: PII-Sicherheit (CRITICAL, Rule #8) auf der Kundenliste
 * (/kunden gehört zum aktiven Archiv-Kern; bereits importierte Lexware-Daten
 * bleiben sichtbar): keine unmaskierte IBAN im sichtbaren UI.
 */

import { test, expect } from '@playwright/test';
import { test as authTest, expect as authExpect } from './fixtures';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Lexware Import - API (eingefroren: Router liefert 404)', () => {
  // Erwartung invertiert (2026-07): vor dem Freeze wurde != 404 verlangt.
  test('GET /api/v1/lexware/linking-statistics ist eingefroren (404)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/lexware/linking-statistics`);
    expect(resp.status()).toBe(404);
  });

  test('POST-Endpoint /api/v1/lexware/import/customers ist eingefroren (404)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/lexware/import/customers`);
    // Vor dem Freeze: POST-only -> GET 405. Seit dem Freeze ist der ganze
    // Router deregistriert -> 404 (nicht 405).
    expect(resp.status()).toBe(404);
  });
});

authTest.describe('Lexware Import - PII-Sicherheit (CRITICAL)', () => {
  authTest('Keine unmaskierte IBAN im sichtbaren Text der Kundenliste', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const content = (await page.textContent('body')) || '';

    // Volle deutsche IBAN = DE + 20 Ziffern. Falls sichtbar, MUSS sie maskiert sein.
    const unmaskedIbanPattern = /DE\d{20}/;
    const matches = content.match(unmaskedIbanPattern);
    authExpect(
      matches,
      `Unmaskierte IBAN im UI gefunden (Rule #8 Verstoss): ${matches?.[0] ?? ''}`
    ).toBeNull();
  });
});

authTest.describe('Lexware Import - Admin-Seite (eingefroren)', () => {
  // Erwartung angepasst (2026-07): /admin/lexware leitet per beforeLoad-Guard
  // auf die statische /frozen-Seite um (frozenModuleGuard('lexware')).
  authTest('Lexware-Admin-Seite leitet auf /frozen um', async ({ authenticatedPage: page }) => {
    await page.goto('/admin/lexware');
    await page.waitForLoadState('domcontentloaded');

    await authExpect(page).toHaveURL(/\/frozen\?module=lexware/, { timeout: 15000 });
    await authExpect(page.getByText('Modul eingefroren')).toBeVisible({ timeout: 15000 });
  });
});
