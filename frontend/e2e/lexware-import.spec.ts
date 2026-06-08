/**
 * E2E Tests: Lexware Import
 *
 * - Import-Endpoints existieren (kein 404) und sind gegated
 * - PII-Sicherheit (CRITICAL, Rule #8): keine unmaskierte IBAN im sichtbaren UI
 * - Lexware-Admin-Seite rendert ohne Crash
 *
 * CRITICAL RULE: NEVER log/expose customer numbers, IBANs, VAT-IDs from Lexware
 * imports. Siehe .claude/Docs/Integrations/Lexware.md.
 *
 * Verifiziert gegen die laufende API: der Lexware-Router haengt unter
 * /api/v1/lexware (app/api/v1/lexware.py). GET /linking-statistics existiert;
 * /import/customers ist POST-only (GET -> 405). Beide sind != 404.
 */

import { test, expect } from '@playwright/test';
import { test as authTest, expect as authExpect } from './fixtures';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Lexware Import - API', () => {
  test('GET /api/v1/lexware/linking-statistics existiert (kein 404)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/lexware/linking-statistics`);
    // Existiert -> gegated (401/403); existiert NICHT -> 404. Wir verlangen != 404.
    expect(resp.status()).not.toBe(404);
    expect([200, 401, 403]).toContain(resp.status());
  });

  test('POST-Endpoint /api/v1/lexware/import/customers existiert (GET -> 405)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/lexware/import/customers`);
    // POST-only Route: GET liefert 405 (Method Not Allowed), nicht 404.
    expect(resp.status()).not.toBe(404);
    expect([405, 401, 403]).toContain(resp.status());
  });
});

authTest.describe('Lexware Import - PII-Sicherheit (CRITICAL)', () => {
  authTest('Keine unmaskierte IBAN im sichtbaren Text der Kundenliste', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle');

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

authTest.describe('Lexware Import - Admin-Seite', () => {
  authTest('Lexware-Import-Seite rendert ohne Crash', async ({ authenticatedPage: page }) => {
    await page.goto('/admin/lexware');
    await page.waitForLoadState('networkidle');

    const content = (await page.textContent('body')) || '';
    authExpect(content).not.toMatch(/Internal Server Error|Traceback/);
    // Admin-Seite muss erreichbar sein (Admin ist Superuser) und nicht zur Login-Seite umleiten.
    authExpect(page.url()).not.toMatch(/\/login/);
  });
});
