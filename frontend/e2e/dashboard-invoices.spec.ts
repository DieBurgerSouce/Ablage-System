/**
 * E2E: Dashboard + Rechnungsverfolgung
 *
 * Prueft:
 * - Das rollenbasierte Dashboard (/) laedt fuer den Admin ohne Fehlerzustand
 *   und ohne 5xx-API-Antworten im Hintergrund
 * - Rechnungs-API: GET /invoices (Liste) und /invoices/statistics/summary
 *   liefern 200 (kein 500) — Grundlage der Dashboard-Widgets
 *
 * Idempotent: rein lesend.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken, viewerToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Dashboard - UI', () => {
  test('Admin-Dashboard laedt ohne 5xx und ohne Fehlerzustand', async ({ authenticatedPage: page }) => {
    const serverErrors: string[] = [];
    page.on('response', (resp) => {
      if (resp.status() >= 500 && resp.url().includes('/api/')) {
        serverErrors.push(`${resp.status()} ${resp.url()}`);
      }
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Kein React-Error-Boundary / kein unbehandelter Fehler sichtbar.
    // HINWEIS: Schlaegt aktuell KORREKT fehl — bekannter App-Bug (Kategorie B,
    // 2026-06-12): Das Admin-Dashboard ('/') crasht in den Root-ErrorBoundary
    // ("Anwendungsfehler"), weil WidgetSyncStatus <Tooltip> ohne
    // TooltipProvider rendert (DashboardGridEnhanced.tsx:302).
    await expect(page.getByText(/Etwas ist schiefgelaufen|[Uu]nerwarteter Fehler|Anwendungsfehler/)).toHaveCount(0);
    // Dashboard hat mindestens eine Ueberschrift gerendert (kein Blank-Screen)
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 15000 });

    expect(serverErrors, `Dashboard loeste 5xx aus: ${serverErrors.join(', ')}`).toHaveLength(0);
  });
});

apiTest.describe('Rechnungsverfolgung - API', () => {
  apiTest('GET /invoices liefert 200 fuer Admin und Viewer (company-scoped)', async ({ request }) => {
    for (const token of [adminToken(), viewerToken()]) {
      const resp = await request.get(`${API_BASE}/api/v1/invoices`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      apiExpect(resp.status()).not.toBe(500);
      apiExpect(resp.status()).toBe(200);
    }
  });

  apiTest('GET /invoices/statistics/summary liefert 200 mit Kennzahlen', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/invoices/statistics/summary`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
    const body = await resp.json();
    apiExpect(typeof body).toBe('object');
  });

  apiTest('Skonto-Deadlines antworten ohne 500', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/invoices/skonto/upcoming`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
  });
});
