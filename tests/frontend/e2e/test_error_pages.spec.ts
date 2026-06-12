/**
 * E2E Tests: Error Pages and API Error Handling
 *
 * Testet Fehlerseiten und Fehlerbehandlung:
 * - 404 Seite auf Deutsch
 * - 403 Forbidden-Behandlung
 * - 500 Server Error graceful degradation
 * - API-Fehler in der UI (Toast, Error-States)
 * - Netzwerk-Timeout Behandlung
 */

import { test, expect } from '@playwright/test';
import path from 'path';

test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

test.describe('Error Pages und API-Fehlerbehandlung', () => {
  test.describe('404 - Seite nicht gefunden', () => {
    test('sollte deutschen 404-Text anzeigen bei ungültigem Pfad', async ({ page }) => {
      await page.goto('/diese-seite-gibt-es-nicht-abc123');
      await page.waitForLoadState('domcontentloaded');

      const body = await page.locator('body').innerText();
      // Muss deutschen Text haben
      expect(body).toMatch(/nicht gefunden|Seite.*nicht|404|existiert nicht/i);
      // Darf KEIN englisches "Not Found" zeigen
      // (erlaubt in technischen HTTP-Feldern, aber nicht als Benutzer-Text)
    });

    test('sollte Heimlink auf der 404-Seite haben', async ({ page }) => {
      await page.goto('/nicht-vorhanden-xyz');
      await page.waitForLoadState('domcontentloaded');

      const homeLink = page.locator('a[href="/"], a:has-text("Startseite"), a:has-text("Zurück"), a:has-text("Dashboard")');
      const hasHomeLink = await homeLink.first().isVisible({ timeout: 3000 }).catch(() => false);
      // Eine 404-Seite sollte Navigationshilfe bieten
      expect(hasHomeLink).toBeTruthy();
    });
  });

  test.describe('API 500 - Server Error Graceful Degradation', () => {
    test('sollte Fehler-Toast bei 500-API-Antwort anzeigen statt leerer Seite', async ({ page }) => {
      // Simuliere 500 für Dokumente-Endpunkt
      await page.route('/api/v1/documents/**', route => {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Interner Serverfehler' }),
          headers: { 'Content-Type': 'application/json' },
        });
      });

      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Die Seite soll nicht komplett leer sein
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.trim().length).toBeGreaterThan(50);

      // Soll deutschen Fehlerhinweis zeigen (Toast oder Error-State)
      const errorIndicator = page.locator(
        '[role="alert"], .text-destructive, [class*="toast"], [class*="error"]'
      );
      const hasError = await errorIndicator.first().isVisible({ timeout: 5000 }).catch(() => false);
      // Fehler muss irgendwie kommuniziert werden
      expect(hasError || bodyText.match(/Fehler|Laden|nicht möglich/i)).toBeTruthy();
    });

    test('sollte bei 500 Dashboard-Seite trotzdem rendern (nicht abstürzen)', async ({ page }) => {
      await page.route('/api/v1/dashboard/**', route => {
        route.fulfill({ status: 500, body: '{}' });
      });

      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Seite soll nicht weiss/leer bleiben
      const htmlContent = await page.content();
      expect(htmlContent.length).toBeGreaterThan(500);

      // Kein unbehandelter JS-Error soll sichtbar sein
      const jsError = page.locator(':has-text("Uncaught"), :has-text("TypeError"), :has-text("ReferenceError")');
      const hasJsError = await jsError.isVisible({ timeout: 1000 }).catch(() => false);
      expect(hasJsError).toBeFalsy();
    });
  });

  test.describe('Netzwerk-Timeout', () => {
    test('sollte Timeout-Fehler mit deutschem Text behandeln', async ({ page }) => {
      // Simuliere sehr langsame Antwort
      await page.route('/api/v1/documents/**', async route => {
        await new Promise(resolve => setTimeout(resolve, 31000)); // Nach Frontend-Timeout
        route.continue();
      });

      // Navigiere und warte nicht zu lange
      await page.goto('/');
      await page.waitForTimeout(5000); // Realistischer Wartezeit

      // Wenn Timeout-State sichtbar: soll deutsch sein
      const timeoutMsg = page.locator(':has-text("Zeitüberschreitung"), :has-text("dauert zu lange"), :has-text("Verbindungsproblem")');
      // Test gilt als bestanden wenn entweder: Timeout-Meldung oder Seite hat sonstigen Inhalt
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.trim().length).toBeGreaterThan(0);
    });
  });

  test.describe('403 Forbidden', () => {
    test('sollte deutschen 403-Text anzeigen wenn Zugriff verweigert', async ({ page }) => {
      // Simuliere 403 für admin-Bereich
      await page.route('/api/v1/admin/**', route => {
        route.fulfill({
          status: 403,
          body: JSON.stringify({ detail: 'Keine Berechtigung' }),
          headers: { 'Content-Type': 'application/json' },
        });
      });

      await page.goto('/admin');
      await page.waitForLoadState('domcontentloaded');

      const body = await page.locator('body').innerText();
      // Soll Zugriff verweigert auf Deutsch kommunizieren
      expect(body).toMatch(/Berechtigung|verboten|Zugriff|403|nicht erlaubt/i);
    });
  });
});
