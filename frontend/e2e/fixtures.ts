/**
 * Custom Playwright Test Fixtures for Ablage-System.
 *
 * Uses cached auth tokens from global setup to avoid rate limiting.
 */

import { test as base, expect, type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const AUTH_CACHE_FILE = path.join(__dirname, '.auth', 'auth-state.json');

interface CachedAuth {
  access_token: string;
  refresh_token: string;
  user: {
    id: string;
    email: string;
    username: string;
    full_name: string;
    is_superuser: boolean;
    is_active: boolean;
    role: string;
  };
  cached_at: string;
}

// Extend base test with custom fixtures
export const test = base.extend<{
  authenticatedPage: Page;
}>({
  authenticatedPage: async ({ page }, use) => {
    // Read cached auth data
    if (!fs.existsSync(AUTH_CACHE_FILE)) {
      throw new Error(
        'Auth cache file not found. Make sure globalSetup ran successfully. ' +
        'Expected file: ' + AUTH_CACHE_FILE
      );
    }

    const authData: CachedAuth = JSON.parse(fs.readFileSync(AUTH_CACHE_FILE, 'utf-8'));

    // Prepare auth data for injection
    const sessionData = {
      access_token: authData.access_token,
      refresh_token: authData.refresh_token,
      user: JSON.stringify(authData.user),
    };

    // Use addInitScript to set sessionStorage BEFORE React mounts
    // This ensures AuthProvider finds the auth data on first render
    await page.addInitScript((data) => {
      window.sessionStorage.setItem('auth_token', data.access_token);
      window.sessionStorage.setItem('refresh_token', data.refresh_token);
      window.sessionStorage.setItem('user', data.user);
    }, sessionData);

    // Now navigate to the app - auth data will already be in sessionStorage
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Verify we're logged in (not on login page)
    const currentUrl = page.url();
    console.log('After auth setup, current URL: ' + currentUrl);

    await expect(page).not.toHaveURL(/\/login/, { timeout: 10000 });

    // Provide the authenticated page to tests
    await use(page);
  },
});

export { expect };
