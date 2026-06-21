/**
 * E2E: Suche mit Umlauten + Spotlight (Befehlspalette)
 *
 * Prueft:
 * - /search rendert die Suchseite (verifizierter Placeholder:
 *   "Dokumente durchsuchen (Volltext & Semantisch)...")
 * - Eine Umlaut-Suche ("Müller") fuehrt zu einer ehrlichen Antwort:
 *   Ergebnisliste ODER der verifizierte Leer-Zustand "Keine Ergebnisse
 *   gefunden" — niemals ein Fehlerzustand/500
 * - API: GET /documents/search/ mit Umlaut-Query liefert 200
 * - Spotlight: Strg+K oeffnet die globale Befehlspalette (GlobalCommandDialog)
 *
 * Idempotent: rein lesend.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Suche - UI', () => {
  test('Umlaut-Suche liefert Ergebnisse oder ehrlichen Leer-Zustand (kein Fehler)', async ({ authenticatedPage: page }) => {
    // 500er auf Such-Endpoints wuerden den Test hart fehlschlagen lassen
    const serverErrors: string[] = [];
    page.on('response', (resp) => {
      if (resp.status() >= 500 && resp.url().includes('/api/')) {
        serverErrors.push(`${resp.status()} ${resp.url()}`);
      }
    });

    await page.goto('/search');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const input = page.getByPlaceholder(/Dokumente durchsuchen/);
    await expect(input).toBeVisible({ timeout: 15000 });

    await input.click();
    await input.fill('Müller');

    // Die SearchPanel-Eingabe entprellt die Query 300ms, bevor sie in die URL
    // (?q=...) geschrieben wird; erst dann startet die URL-getriebene Suche
    // (search.tsx: hasSearch = q.length >= 2). Ein sofortiges Enter rast dem
    // Debounce davon -> die Query landete leer in der URL (?q=) und es lief
    // NIE eine Suche (verifiziert Stream s5, 2026-06-13). Deshalb auf die
    // Uebernahme in die URL warten statt auf Enter zu setzen.
    await page.waitForURL(/[?&]q=M/, { timeout: 10000 });

    // Ehrliches Entweder-Oder: Ergebnisse ODER verifizierter Leer-Zustand.
    // Ein haengender Spinner oder eine Fehlermeldung erfuellt KEINEN der Pfade.
    const emptyState = page.getByText('Keine Ergebnisse gefunden');
    const resultsArea = page.getByText(/Ergebnis|Treffer/).first();
    await expect(emptyState.or(resultsArea)).toBeVisible({ timeout: 30000 });

    expect(serverErrors, `Such-Backend antwortete mit 5xx: ${serverErrors.join(', ')}`).toHaveLength(0);
  });

  test('Spotlight (Strg+K) oeffnet die Befehlspalette', async ({ authenticatedPage: page }) => {
    // Reaktiviert 2026-06-21: Die doppelte Strg+K-Palette ist behoben (B8) —
    // der SpotlightDialog wurde aus AppLayout.tsx entfernt, nur der
    // GlobalCommandDialog (via __root.tsx) ist noch global gemountet. Strg+K
    // oeffnet genau einen Dialog, Escape schliesst ihn.
    await page.goto('/kunden');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#main-content').waitFor({ state: 'attached', timeout: 15000 });
    await page.keyboard.press('Control+k');
    // Befehlspalette mit Eingabefeld oeffnet
    const dialog = page.getByRole('dialog');
    await expect(dialog.first()).toBeVisible({ timeout: 10000 });
    await expect(
      dialog.first().getByRole('combobox').or(dialog.first().locator('input')).first()
    ).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0, { timeout: 5000 });
  });
});

apiTest.describe('Suche - API', () => {
  apiTest('Umlaut-Query liefert 200 (kein 500, korrektes UTF-8-Handling)', async ({ request }) => {
    const resp = await request.get(
      `${API_BASE}/api/v1/documents/search/?q=${encodeURIComponent('Müller Größe')}`,
      { headers: { Authorization: `Bearer ${adminToken()}` } }
    );
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
  });
});
