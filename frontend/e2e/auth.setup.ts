/**
 * Playwright Authentication Setup for Frontend Tests.
 *
 * Authentifiziert einen Testbenutzer und speichert den Auth-State
 * fuer nachfolgende Tests.
 *
 * Umgebungsvariablen:
 * - TEST_USER_EMAIL: E-Mail des Testbenutzers (Standard: admin@localhost.com)
 * - TEST_USER_PASSWORD: Passwort des Testbenutzers (Standard: admin123)
 */

import { test as setup, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Auth state file path
export const AUTH_STATE_PATH = path.join(__dirname, '.auth', 'user.json');

// Test user credentials from environment variables or defaults
const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'admin@localhost.com';
const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD || 'admin123';

setup('authenticate', async ({ page }) => {
  console.log(`Authenticating as ${TEST_USER_EMAIL}...`);

  // Navigate to login page
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  // Wait for login form to be visible
  const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="mail"]');
  const passwordInput = page.locator('input[type="password"], input[name="password"]');
  const submitButton = page.locator('button[type="submit"], button:has-text("Anmelden"), button:has-text("Login")');

  await expect(emailInput).toBeVisible({ timeout: 10000 });
  await expect(passwordInput).toBeVisible({ timeout: 10000 });

  // Fill in credentials
  await emailInput.fill(TEST_USER_EMAIL);
  await passwordInput.fill(TEST_USER_PASSWORD);

  // Submit form
  await submitButton.click();

  // Wait for successful login (redirect away from login page)
  await page.waitForURL((url) => {
    const pathname = url.pathname;
    return !pathname.includes('/login') && !pathname.includes('/auth');
  }, { timeout: 15000 });

  console.log('UI authentication successful');

  // Save authentication state (includes localStorage and cookies)
  // Note: sessionStorage is not persisted, but the UI login sets cookies too
  await page.context().storageState({ path: AUTH_STATE_PATH });
});
