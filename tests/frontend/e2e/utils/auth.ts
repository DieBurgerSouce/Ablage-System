/**
 * Authentication Helper Utilities for E2E Tests
 *
 * Provides reusable authentication functionality for Playwright tests.
 */

import { type Page, expect } from '@playwright/test';
import path from 'path';

// Auth state file path
export const AUTH_STATE_PATH = path.join(__dirname, '..', '.auth', 'user.json');

// Default test credentials
export const TEST_CREDENTIALS = {
  email: process.env.TEST_USER_EMAIL || 'admin@localhost.com',
  password: process.env.TEST_USER_PASSWORD || 'admin123',
};

/**
 * Perform login via UI
 */
export async function loginViaUI(
  page: Page,
  email: string = TEST_CREDENTIALS.email,
  password: string = TEST_CREDENTIALS.password
): Promise<void> {
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  const emailInput = page.locator(
    'input[type="email"], input[name="email"], input[placeholder*="mail"]'
  );
  const passwordInput = page.locator('input[type="password"], input[name="password"]');
  const submitButton = page.locator(
    'button[type="submit"], button:has-text("Anmelden"), button:has-text("Login")'
  );

  await expect(emailInput).toBeVisible({ timeout: 10000 });
  await expect(passwordInput).toBeVisible({ timeout: 10000 });

  await emailInput.fill(email);
  await passwordInput.fill(password);
  await submitButton.click();

  // Wait for redirect away from login
  await page.waitForURL(
    (url) => !url.pathname.includes('/login') && !url.pathname.includes('/auth'),
    { timeout: 15000 }
  );
}

/**
 * Perform login via API (faster)
 */
export async function loginViaAPI(
  page: Page,
  email: string = TEST_CREDENTIALS.email,
  password: string = TEST_CREDENTIALS.password
): Promise<boolean> {
  try {
    const response = await page.request.post('/api/v1/auth/login', {
      data: { email, password },
    });

    if (!response.ok()) {
      return false;
    }

    const tokens = await response.json();

    if (tokens.requires_2fa) {
      return false;
    }

    await page.goto('/');
    await page.evaluate(
      (tokenData: { access_token: string; refresh_token: string; token_type?: string }) => {
        localStorage.setItem('access_token', tokenData.access_token);
        localStorage.setItem('refresh_token', tokenData.refresh_token);
        localStorage.setItem('token_type', tokenData.token_type || 'bearer');
      },
      tokens
    );

    return true;
  } catch {
    return false;
  }
}

/**
 * Ensure user is authenticated (tries API first, falls back to UI)
 */
export async function ensureAuthenticated(
  page: Page,
  email: string = TEST_CREDENTIALS.email,
  password: string = TEST_CREDENTIALS.password
): Promise<void> {
  const apiSuccess = await loginViaAPI(page, email, password);

  if (!apiSuccess) {
    await loginViaUI(page, email, password);
  }
}

/**
 * Check if user is currently logged in
 */
export async function isLoggedIn(page: Page): Promise<boolean> {
  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  return !!token;
}

/**
 * Logout the current user
 */
export async function logout(page: Page): Promise<void> {
  await page.evaluate(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('token_type');
  });
  await page.goto('/login');
}

/**
 * Get auth headers for API requests
 */
export async function getAuthHeaders(page: Page): Promise<Record<string, string>> {
  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  const tokenType = await page.evaluate(() => localStorage.getItem('token_type') || 'bearer');

  if (!token) {
    return {};
  }

  return {
    Authorization: `${tokenType} ${token}`,
  };
}
