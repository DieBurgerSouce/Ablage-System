/**
 * E2E: DATEV-Export mit Kontierungs-Validator-Gate (W3-F4)
 *
 * Prueft das F4-Verhalten: Der "Export starten"-Button ist gesperrt, bis eine
 * Vorschau (Vorpruefung) erstellt wurde und Dokumente enthaelt. Kein blinder
 * Export moeglich.
 *
 * Verifizierte UI-Texte (ExportPage.tsx): CardTitle "Neuen Export erstellen",
 * Buttons "Vorschau" und "Export starten", Hinweis "Bitte zuerst eine
 * Vorschau erstellen, um den Export zu prüfen."
 *
 * Idempotent: Es wird KEIN Export ausgeloest, nur das Gating geprueft.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('DATEV-Export - Validator-Gate (W3-F4)', () => {
  test('Export-Button ist ohne Vorschau gesperrt', async ({ authenticatedPage: page }) => {
    await page.goto('/admin/datev/export');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    await expect(page.getByText('Neuen Export erstellen')).toBeVisible({ timeout: 15000 });

    const exportButton = page.getByRole('button', { name: /Export starten/ });
    await expect(exportButton).toBeVisible();
    // F4: ohne erfolgreiche Vorpruefung bleibt der Export gesperrt
    await expect(exportButton).toBeDisabled();

    // Der erklaerende Hinweis ist sichtbar
    await expect(
      page.getByText(/Bitte zuerst eine Vorschau erstellen/)
    ).toBeVisible();
  });

  test('Vorschau-Button existiert und ist nicht im Lade-Zustand haengend', async ({ authenticatedPage: page }) => {
    await page.goto('/admin/datev/export');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const previewButton = page.getByRole('button', { name: /Vorschau/ });
    await expect(previewButton).toBeVisible({ timeout: 15000 });
    // Kein Dauerspinner: Der Button zeigt "Vorschau", nicht "Analysiere..."
    await expect(page.getByRole('button', { name: /Analysiere/ })).toHaveCount(0);
  });
});

apiTest.describe('DATEV-Export - API-Invarianten', () => {
  apiTest('DATEV-Konfigurationsliste laedt (GET /datev/config)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/datev/config`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).toBe(200);
    const body = await resp.json();
    apiExpect(Array.isArray(body)).toBeTruthy();
  });

  apiTest('Export-Historie laedt (GET /datev/export/history)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/datev/export/history`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
  });
});
