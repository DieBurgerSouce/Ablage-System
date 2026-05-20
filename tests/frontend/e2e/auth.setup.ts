/**
 * Playwright Authentication Setup.
 *
 * Authentifiziert einen Testbenutzer und speichert den Auth-State
 * fuer nachfolgende Tests.
 *
 * Umgebungsvariablen:
 * - TEST_USER_EMAIL: E-Mail des Testbenutzers (Standard: test@ablage.local)
 * - TEST_USER_PASSWORD: Passwort des Testbenutzers (Standard: Test123!@#)
 */

import { test as setup, expect } from '@playwright/test';
import path from 'path';

// Auth state file path
export const AUTH_STATE_PATH = path.join(__dirname, '.auth', 'user.json');

// Test user credentials from environment variables or defaults
// Default credentials for local development
const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'admin@localhost.com';
const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD || 'admin123';

setup('authenticate', async ({ page, request }) => {
  console.log(`Authenticating as ${TEST_USER_EMAIL}...`);

  // Method 1: Try API-based authentication first (faster)
  try {
    const loginResponse = await request.post('/api/v1/auth/login', {
      data: {
        email: TEST_USER_EMAIL,
        password: TEST_USER_PASSWORD,
      },
    });

    if (loginResponse.ok()) {
      const tokens = await loginResponse.json();

      // Check if 2FA is required
      if (tokens.requires_2fa) {
        console.warn('2FA is enabled for test user - using UI login instead');
        throw new Error('2FA required - fallback to UI');
      }

      // Store tokens in localStorage via page context
      await page.goto('/');
      await page.evaluate((tokenData) => {
        localStorage.setItem('access_token', tokenData.access_token);
        localStorage.setItem('refresh_token', tokenData.refresh_token);
        localStorage.setItem('token_type', tokenData.token_type || 'bearer');
      }, tokens);

      // Verify authentication worked by navigating to a protected page
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Check if we're on the dashboard (not login page)
      const currentUrl = page.url();
      if (!currentUrl.includes('/login') && !currentUrl.includes('/auth')) {
        console.log('API authentication successful');
        await page.context().storageState({ path: AUTH_STATE_PATH });
        return;
      }
    }
  } catch (error) {
    console.log('API login failed, falling back to UI login:', error);
  }

  // Method 2: UI-based authentication (fallback)
  console.log('Using UI-based authentication...');

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
    const path = url.pathname;
    return !path.includes('/login') && !path.includes('/auth');
  }, { timeout: 15000 });

  console.log('UI authentication successful');

  // Save authentication state
  await page.context().storageState({ path: AUTH_STATE_PATH });
});
