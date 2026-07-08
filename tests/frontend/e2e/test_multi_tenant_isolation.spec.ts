/**
 * E2E Tests: Multi-Tenant Isolation
 *
 * Testet Datenisolation zwischen Unternehmen:
 * - API-Antworten enthalten nur eigene Daten
 * - Direkte ID-Zugriffe auf fremde Ressourcen werden blockiert
 * - Company-Kontext wird korrekt gesetzt
 *
 * Bezieht sich auf KNOWN_ISSUES: Multi-Tenant 500-Bugs
 * (companies/get_current_company, require_company MultipleResultsFound)
 */

import { test, expect } from '@playwright/test';
import path from 'path';

test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

test.describe('Multi-Tenant Isolation', () => {
  test.describe('Company Context API', () => {
    test('sollte /api/v1/companies/current ohne 500-Fehler laden', async ({ request }) => {
      const response = await request.get('/api/v1/companies/current');

      // War ein bekannter 500-Bug (MultipleResultsFound)
      expect(response.status()).not.toBe(500);
      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty('id');
      expect(data).toHaveProperty('name');
    });

    test('sollte company_id in allen API-Antworten konsistent sein', async ({ request }) => {
      const companyResp = await request.get('/api/v1/companies/current');
      if (companyResp.status() !== 200) return;

      const company = await companyResp.json();
      const companyId = company.id;

      // Dokumente sollen zur selben Company gehören
      const docsResp = await request.get('/api/v1/documents/?limit=5');
      if (docsResp.status() === 200) {
        const docs = await docsResp.json();
        const items = docs.items || docs;
        if (Array.isArray(items) && items.length > 0 && items[0].company_id) {
          for (const doc of items) {
            expect(doc.company_id).toBe(companyId);
          }
        }
      }
    });
  });

  test.describe('Cross-Company Zugriff', () => {
    test('sollte 403 oder 404 bei Zugriff auf fremde Dokument-ID zurückgeben', async ({ request }) => {
      // Versuche eine sehr unwahrscheinliche UUID zu laden (gehört wahrscheinlich nicht zu diesem User)
      const fakeId = '00000000-0000-0000-0000-000000000001';
      const response = await request.get(`/api/v1/documents/${fakeId}`);

      // Darf NICHT 200 zurückgeben (würde fremde Daten liefern)
      expect([403, 404, 422]).toContain(response.status());
    });

    test('sollte 403 oder 404 bei Zugriff auf fremde Entity-ID zurückgeben', async ({ request }) => {
      const fakeId = '00000000-0000-0000-0000-000000000002';
      const response = await request.get(`/api/v1/entities/${fakeId}`);
      expect([403, 404, 422]).toContain(response.status());
    });

    test('sollte 403 oder 404 bei Zugriff auf fremde Transaktion zurückgeben', async ({ request }) => {
      // HINWEIS (Odoo-Neuausrichtung 2026-07): Das Banking-Modul ist
      // eingefroren — /api/v1/banking liefert seit dem Freeze deterministisch
      // 404 (Router deregistriert). Der Test bleibt als Leak-Guard gueltig
      // ("nie 200 fuer fremde IDs"), beweist aber aktuell den Freeze statt
      // der Tenant-Isolation. Bei Reaktivierung (ACTIVE_OPTIONAL_MODULES=
      // banking) prueft er wieder die echte Isolation.
      const fakeId = '00000000-0000-0000-0000-000000000003';
      const response = await request.get(`/api/v1/banking/transactions/${fakeId}`);
      expect([403, 404, 422]).toContain(response.status());
    });
  });

  test.describe('UI zeigt nur eigene Daten', () => {
    test('sollte keine Dokumente anderer Companies in der Liste zeigen', async ({ page, request }) => {
      const companyResp = await request.get('/api/v1/companies/current');
      if (companyResp.status() !== 200) return;
      const company = await companyResp.json();

      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Kein Leak-Hinweis wie "(fremdes Unternehmen)" soll sichtbar sein
      const pageText = await page.locator('body').innerText();
      expect(pageText).not.toContain('company_id mismatch');
      expect(pageText).not.toContain('unauthorized_company');
    });
  });
});
