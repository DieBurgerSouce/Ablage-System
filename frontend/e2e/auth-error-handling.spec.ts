/**
 * E2E Tests: Auth Error Handling
 *
 * Testet Fehlerbehandlung bei der Authentifizierung mit ECHTEN Invarianten
 * (keine vacuous `if (visible) { expect }`-Muster):
 * - Falsche/leere Anmeldedaten -> KEIN Login (bleibt auf /login)
 * - Passwortfeld ist maskiert
 * - Rate-Limiting greift nach mehreren Fehlversuchen (401 oder 429)
 * - Abgelaufene Session -> Weiterleitung zur Login-Seite
 * - Geschuetzte API ohne gueltigen Token -> 401 mit strukturiertem Body
 * - /admin ohne Auth -> Weiterleitung
 *
 * Diese Specs nutzen KEINEN Auth-Fixture (sie testen den unauthentifizierten
 * Zustand). API-Checks laufen ueber den `request`-Fixture.
 */

import { test, expect } from '@playwright/test';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Auth Error Handling - Login-Formular', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');
  });

  test('Login-Seite zeigt E-Mail-, Passwort-Feld und Submit-Button', async ({ page }) => {
    await expect(
      page.locator('input[type="email"], input[name="email"]').first()
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('input[type="password"], input[name="password"]').first()
    ).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button[type="submit"]').first()).toBeVisible();
  });

  test('Passwortfeld ist maskiert (type=password)', async ({ page }) => {
    const passwordInput = page.locator('input[name="password"], input[type="password"]').first();
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });

  test('Leeres Formular fuehrt NICHT zum Login (bleibt auf /login)', async ({ page }) => {
    await page.locator('button[type="submit"]').first().click();
    await page.waitForTimeout(1000);
    expect(page.url()).toContain('/login');
  });

  test('Falsche Anmeldedaten fuehren NICHT zum Login (bleibt auf /login)', async ({ page }) => {
    await page.locator('input[type="email"], input[name="email"]').first().fill('falsch@ablage.local');
    await page.locator('input[type="password"]').first().fill('FalschesPasswort!');
    await page.locator('button[type="submit"]').first().click();
    await page.waitForTimeout(1500);
    // Sicherheits-Invariante: ungueltige Credentials duerfen niemals einloggen.
    expect(page.url()).toContain('/login');
  });
});

test.describe('Auth Error Handling - API', () => {
  test('Rate-Limiting/Abweisung nach mehreren Fehlversuchen (401 oder 429)', async ({ request }) => {
    const statuses: number[] = [];
    for (let i = 0; i < 6; i++) {
      // WICHTIG: keine .local-Domain verwenden — der Backend-E-Mail-Validator
      // (pydantic/email-validator) lehnt Special-Use-Domains wie .local mit
      // 422 ab, BEVOR die Credential-Pruefung greift (verifiziert 2026-06-12).
      const resp = await request.post(`${API_BASE}/api/v1/auth/login`, {
        data: { email: 'falsche-creds@example.com', password: 'WrongPassword!' },
      });
      statuses.push(resp.status());
    }
    const last = statuses[statuses.length - 1];
    // Jede Fehlanmeldung muss abgewiesen werden; nach mehreren ggf. 429.
    expect([401, 429]).toContain(last);
    // Keine einzige darf faelschlich 2xx/5xx liefern.
    for (const s of statuses) {
      expect(s).not.toBe(200);
      expect(s).toBeLessThan(500);
    }
  });

  test('Geschuetzte API ohne gueltigen Token -> 401 mit Body', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/documents/`, {
      headers: { Authorization: 'Bearer invalid_token_xyz' },
    });
    expect(resp.status()).toBe(401);
    const body = await resp.json().catch(() => null);
    expect(body).not.toBeNull();
    // Strukturiertes Fehler-Envelope (fehler) oder FastAPI-Standard (detail).
    expect(body.fehler ?? body.detail).toBeTruthy();
  });

  test('Refresh mit ungueltigem Token crasht nicht (kein 500/404)', async ({ request }) => {
    const resp = await request.post(`${API_BASE}/api/v1/auth/refresh`, {
      data: { refresh_token: 'invalid_token' },
    });
    expect(resp.status()).not.toBe(500);
    expect(resp.status()).not.toBe(404);
  });
});

test.describe('Auth Error Handling - Geschuetzte Routen ohne Auth', () => {
  test('Abgelaufene Session leitet zur Login-Seite weiter', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Alle Auth-Spuren entfernen (Session simuliert abgelaufen).
    await page.evaluate(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
      document.cookie.split(';').forEach((c) => {
        document.cookie = c
          .replace(/^ +/, '')
          .replace(/=.*/, `=;expires=${new Date().toUTCString()};path=/`);
      });
    });

    await page.goto('/documents');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
    await expect(page).toHaveURL(/login|auth/i, { timeout: 10000 });
  });

  test('/admin ohne Auth leitet weiter (kein Admin-Inhalt)', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/');
    await page.evaluate(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });
    await page.goto('/admin');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
    await expect(page).toHaveURL(/login|auth|forbidden/i, { timeout: 10000 });
  });
});
