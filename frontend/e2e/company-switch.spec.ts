/**
 * E2E: Firmenwechsel / Multi-Tenant (Journey J5)
 *
 * Prueft:
 * - CompanySwitcher ist sichtbar und zeigt die aktuelle Firma (Seed: "E2E Test GmbH")
 * - Firmenwechsel via API ist idempotent (Wechsel auf die eigene aktuelle Firma)
 * - Wechsel auf fremde/nicht existierende Firma wird abgelehnt (kein 200, KEIN 500)
 * - /companies/current liefert nie 500 (Regression: MultipleResultsFound, W1-049)
 *
 * Tokens kommen aus dem globalSetup-Cache (kein Login pro Test, Rate-Limit 5/15min).
 * Seed: scripts/seed_e2e.py (admin@localhost.com + viewer@localhost.com,
 * beide Mitglied in "E2E Test GmbH" mit is_current=true).
 * Idempotent: es wird nur auf die ohnehin aktuelle Firma "gewechselt".
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken, viewerToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

apiTest.describe('Firmenwechsel - API-Invarianten', () => {
  apiTest('Firmenliste laedt fuer Admin und enthaelt die Seed-Firma', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/companies`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).toBe(200);
    const body = await resp.json();
    const companies = Array.isArray(body) ? body : body.companies || body.items || [];
    apiExpect(companies.length).toBeGreaterThan(0);
    const names = companies.map((c: { name: string }) => c.name);
    apiExpect(names).toContain('E2E Test GmbH');
  });

  apiTest('/companies/current liefert die aktuelle Firma (kein 500)', async ({ request }) => {
    for (const token of [adminToken(), viewerToken()]) {
      const resp = await request.get(`${API_BASE}/api/v1/companies/current`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      apiExpect(resp.status()).not.toBe(500);
      apiExpect(resp.status()).toBe(200);
    }
  });

  apiTest('Wechsel auf die eigene aktuelle Firma ist idempotent (200)', async ({ request }) => {
    const headers = { Authorization: `Bearer ${adminToken()}` };
    const current = await request.get(`${API_BASE}/api/v1/companies/current`, { headers });
    apiExpect(current.status()).toBe(200);
    const company = await current.json();
    apiExpect(company?.id).toBeTruthy();

    const switchResp = await request.post(
      `${API_BASE}/api/v1/companies/current/${company.id}`,
      { headers }
    );
    apiExpect(switchResp.status()).toBe(200);
    const switched = await switchResp.json();
    apiExpect(switched.id).toBe(company.id);
  });

  apiTest('Wechsel auf fremde/unbekannte Firma wird abgelehnt (kein 200, kein 500)', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const resp = await request.post(`${API_BASE}/api/v1/companies/current/${fakeId}`, {
      headers: { Authorization: `Bearer ${viewerToken()}` },
    });
    apiExpect(resp.status()).not.toBe(200);
    apiExpect(resp.status()).not.toBe(500);
    apiExpect([400, 403, 404, 422]).toContain(resp.status());
  });

  apiTest('Dokumentenliste bleibt nach Firmenwechsel company-scoped (kein 500)', async ({ request }) => {
    const headers = { Authorization: `Bearer ${adminToken()}` };
    const current = await request.get(`${API_BASE}/api/v1/companies/current`, { headers });
    const company = await current.json();
    await request.post(`${API_BASE}/api/v1/companies/current/${company.id}`, { headers });

    const docs = await request.get(`${API_BASE}/api/v1/documents/`, { headers });
    apiExpect(docs.status()).toBe(200);
    const data = await docs.json();
    apiExpect(Array.isArray(data.documents)).toBeTruthy();
  });
});

test.describe('Firmenwechsel - UI', () => {
  // CompanySwitcher.tsx rendert ZWEI Varianten:
  // - 1 Firma:  einfache Anzeige (Name, kein Dropdown, kein aria-label)
  // - >1 Firma: Dropdown-Trigger mit aria-label "Aktuelle Firma: ..."
  // Der Test prueft die jeweils KORREKTE Variante anhand der echten Firmenzahl.
  test('CompanySwitcher zeigt die korrekte Variante fuer die Firmenzahl', async ({ authenticatedPage: page, request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/companies`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const companies = Array.isArray(body) ? body : body.companies || body.items || [];
    expect(companies.length).toBeGreaterThan(0);

    // Auf eine nicht-crashende Route wechseln: Das Admin-Dashboard ('/')
    // crasht aktuell im ErrorBoundary (App-Bug: Tooltip ohne TooltipProvider,
    // DashboardGridEnhanced.tsx:302) — dann ist auch die Sidebar samt
    // CompanySwitcher unmounted. Der Switcher ist global, /kunden ist gleichwertig.
    await page.goto('/kunden');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#main-content').waitFor({ state: 'attached', timeout: 15000 });

    // In beiden Varianten ist der Name der aktuellen Firma sichtbar
    await expect(page.getByText('E2E Test GmbH').first()).toBeVisible({ timeout: 15000 });

    const dropdownTrigger = page.getByLabel(/Aktuelle Firma:/);
    if (companies.length > 1) {
      // Multi-Company: Dropdown-Trigger muss existieren und Firmen listen
      await expect(dropdownTrigger.first()).toBeVisible({ timeout: 10000 });
      await dropdownTrigger.first().click();
      await expect(page.getByText('Firma wechseln')).toBeVisible({ timeout: 5000 });
      await expect(page.getByRole('menuitem').first()).toBeVisible();
      await page.keyboard.press('Escape');
    } else {
      // Single-Company: bewusst KEIN Wechsel-Trigger (einfache Anzeige)
      await expect(dropdownTrigger).toHaveCount(0);
    }
  });
});
