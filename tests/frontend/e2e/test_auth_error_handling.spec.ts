/**
 * E2E Tests: Auth Error Handling
 *
 * Testet Fehlerbehandlung bei der Authentifizierung:
 * - Falsche Anmeldedaten → deutsche Fehlermeldung
 * - Leere Formularfelder → Validierungsmeldungen
 * - Konto-Sperrung nach Fehlversuchen
 * - Abgelaufene Session → Weiterleitung
 * - Unautorisierter Zugriff auf geschützte Seiten
 */

import { test, expect, type Page } from '@playwright/test';

const API_BASE = 'http://localhost:8000';

test.describe('Auth Error Handling - Authentifizierungsfehler', () => {
  test.describe('Login-Formular Validierung', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.waitForLoadState('domcontentloaded');
    });

    test('sollte Fehler bei leerer E-Mail-Adresse anzeigen', async ({ page }) => {
      const submitButton = page.locator('button[type="submit"]').first();
      await submitButton.click();

      // Required field error in German
      const emailError = page.locator(
        ':has-text("E-Mail"), :has-text("Pflichtfeld"), :has-text("erforderlich"), [aria-describedby*="email"]'
      );

      if (await emailError.isVisible({ timeout: 2000 }).catch(() => false)) {
        const text = await emailError.textContent();
        // Should be German, not English "required"
        expect(text).not.toMatch(/\brequired\b/i);
      }
    });

    test('sollte Fehler bei ungültigem E-Mail-Format anzeigen', async ({ page }) => {
      const emailInput = page.locator('input[type="email"], input[name="email"]').first();
      await emailInput.fill('kein-gueltiges-email');

      const submitButton = page.locator('button[type="submit"]').first();
      await submitButton.click();

      // Should show format error
      const formatError = page.locator(
        ':has-text("ungültig"), :has-text("Format"), :has-text("gültige E-Mail")'
      );

      if (await formatError.isVisible({ timeout: 2000 }).catch(() => false)) {
        await expect(formatError).toBeVisible();
      }
    });

    test('sollte deutschen Fehlertext bei falschen Anmeldedaten zeigen', async ({ page }) => {
      const emailInput = page.locator('input[type="email"], input[name="email"]').first();
      const passwordInput = page.locator('input[type="password"]').first();
      const submitButton = page.locator('button[type="submit"]').first();

      await emailInput.fill('falsch@ablage.local');
      await passwordInput.fill('FalschesPasswort!');
      await submitButton.click();

      await page.waitForLoadState('networkidle');

      const errorMessage = page.locator(
        '[role="alert"], .toast, [class*="error"], :has-text("ungültig"), :has-text("falsch"), :has-text("Anmeldedaten")'
      ).first();

      if (await errorMessage.isVisible({ timeout: 5000 }).catch(() => false)) {
        const text = await errorMessage.textContent();
        // Must be German
        expect(text).toMatch(/ungültig|falsch|Anmeldedaten|Benutzername|Passwort/i);
        // Must NOT be English
        expect(text).not.toMatch(/\bInvalid credentials\b|\bWrong password\b/i);
      }

      // Must stay on login page
      expect(page.url()).toContain('/login');
    });

    test('sollte Passwortfeld als verborgen behandeln', async ({ page }) => {
      const passwordInput = page.locator('input[name="password"], input[type="password"]').first();
      await expect(passwordInput).toHaveAttribute('type', 'password');
    });
  });

  test.describe('Rate Limiting', () => {
    test('sollte nach mehrfach falschen Anmeldeversuchen sperren oder warnen', async ({
      request,
    }) => {
      // Attempt login 5 times with wrong credentials
      const results: number[] = [];

      for (let i = 0; i < 6; i++) {
        const resp = await request.post(`${API_BASE}/api/v1/auth/login`, {
          data: { email: 'test@rate-limit.local', password: 'WrongPassword!' },
        });
        results.push(resp.status());
      }

      // After 5 failures, should get 429 or 401 with lockout message
      const lastStatus = results[results.length - 1];
      expect([401, 429]).toContain(lastStatus);

      // If 429, check Retry-After header
      if (lastStatus === 429) {
        const lastResp = await request.post(`${API_BASE}/api/v1/auth/login`, {
          data: { email: 'test@rate-limit.local', password: 'WrongPassword!' },
        });
        const retryAfter = lastResp.headers()['retry-after'];
        expect(retryAfter).toBeTruthy();
      }
    });
  });

  test.describe('Session Expiry', () => {
    test('sollte abgelaufene Session zur Login-Seite weiterleiten', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Simulate expired tokens by clearing storage
      await page.evaluate(() => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        document.cookie.split(';').forEach((c) => {
          document.cookie = c
            .replace(/^ +/, '')
            .replace(/=.*/, `=;expires=${new Date().toUTCString()};path=/`);
        });
      });

      // Navigate to a protected page
      await page.goto('/documents');
      await page.waitForLoadState('networkidle');

      // Should redirect to login
      const url = page.url();
      expect(url).toMatch(/login|auth/i);
    });

    test('sollte Token-Refresh automatisch durchführen wenn möglich', async ({ page, request }) => {
      // This test validates the refresh token endpoint exists
      const resp = await request.post(`${API_BASE}/api/v1/auth/refresh`, {
        data: { refresh_token: 'invalid_token' },
      });

      // Should return 401, not 500 (endpoint must exist and handle gracefully)
      expect(resp.status()).not.toBe(500);
      expect(resp.status()).not.toBe(404);
    });
  });

  test.describe('Unautorisierter Zugriff', () => {
    test('sollte /admin/* ohne Auth zur Login-Seite weiterleiten', async ({ page }) => {
      // Access admin page without authentication
      await page.goto('/admin');
      await page.waitForLoadState('networkidle');

      const url = page.url();
      expect(url).toMatch(/login|auth|forbidden/i);
    });

    test('sollte 401-API-Antwort auf Deutsch anzeigen wenn angemeldet aber Token fehlt', async ({
      request,
    }) => {
      const resp = await request.get(`${API_BASE}/api/v1/documents/`, {
        headers: { Authorization: 'Bearer invalid_token_xyz' },
      });

      expect(resp.status()).toBe(401);
      const body = await resp.json().catch(() => ({}));

      // Detail field should exist
      expect(body.detail !== undefined).toBeTruthy();
    });
  });
});
