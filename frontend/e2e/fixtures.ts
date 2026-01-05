/**
 * Custom Playwright Test Fixtures for Ablage-System.
 *
 * Provides authenticated page fixture that handles sessionStorage auth.
 */

import { test as base, expect, type Page } from '@playwright/test';

// Test user credentials from environment variables or defaults
const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'admin@localhost.com';
const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD || 'admin123';

// Extend base test with custom fixtures
export const test = base.extend<{
  authenticatedPage: Page;
}>({
  authenticatedPage: async ({ page, request }, use) => {
    // Determine the API base URL
    const baseURL = process.env.BASE_URL || 'http://localhost:80';
    const apiBaseURL = baseURL.includes('5173') ? 'http://localhost:8000' : baseURL;

    // Login via API
    const loginResponse = await request.post(`${apiBaseURL}/api/v1/auth/login`, {
      data: {
        email: TEST_USER_EMAIL,
        password: TEST_USER_PASSWORD,
      },
    });

    if (!loginResponse.ok()) {
      throw new Error(`Login failed: ${loginResponse.status()}`);
    }

    const tokens = await loginResponse.json();

    if (tokens.requires_2fa) {
      throw new Error('2FA is enabled for test user - please disable for tests');
    }

    // Fetch user info
    const userResponse = await request.get(`${apiBaseURL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });

    if (!userResponse.ok()) {
      throw new Error(`Failed to fetch user info: ${userResponse.status()}`);
    }

    const userData = await userResponse.json();

    // Prepare auth data for injection
    const authData = {
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token || '',
      user: JSON.stringify({
        id: userData.id,
        email: userData.email,
        username: userData.username,
        full_name: userData.full_name,
        is_superuser: userData.is_superuser,
        is_active: userData.is_active,
        role: userData.role || (userData.is_superuser ? 'admin' : 'viewer'),
      }),
    };

    // Use addInitScript to set sessionStorage BEFORE React mounts
    // This ensures AuthProvider finds the auth data on first render
    await page.addInitScript((data) => {
      window.sessionStorage.setItem('auth_token', data.access_token);
      window.sessionStorage.setItem('refresh_token', data.refresh_token);
      window.sessionStorage.setItem('user', data.user);
    }, authData);

    // Now navigate to the app - auth data will already be in sessionStorage
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Verify we're logged in (not on login page)
    const currentUrl = page.url();
    console.log(`After auth setup, current URL: ${currentUrl}`);

    await expect(page).not.toHaveURL(/\/login/, { timeout: 10000 });

    // Provide the authenticated page to tests
    await use(page);
  },
});

export { expect };
