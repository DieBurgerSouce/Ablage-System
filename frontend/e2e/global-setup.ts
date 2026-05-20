/**
 * Global Setup for Playwright Tests
 *
 * Logs in once and caches auth tokens so tests don't hit rate limits.
 */

import { request } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'admin@localhost.com';
const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD || 'admin123';
const AUTH_CACHE_FILE = path.join(__dirname, '.auth', 'auth-state.json');

async function globalSetup() {
  // Ensure auth directory exists
  const authDir = path.dirname(AUTH_CACHE_FILE);
  if (!fs.existsSync(authDir)) {
    fs.mkdirSync(authDir, { recursive: true });
  }

  // Check if cached auth is still valid (less than 10 minutes old)
  if (fs.existsSync(AUTH_CACHE_FILE)) {
    const stats = fs.statSync(AUTH_CACHE_FILE);
    const ageMs = Date.now() - stats.mtimeMs;
    const ageMinutes = ageMs / (1000 * 60);

    if (ageMinutes < 10) {
      console.log('[Global Setup] Using cached auth (' + ageMinutes.toFixed(1) + ' min old)');
      return;
    }
  }

  console.log('[Global Setup] Logging in to cache auth tokens...');

  const baseURL = process.env.BASE_URL || 'http://localhost:80';
  const apiBaseURL = baseURL.includes('5173') ? 'http://localhost:8000' : baseURL;

  const context = await request.newContext();

  try {
    // Login via API
    const loginResponse = await context.post(apiBaseURL + '/api/v1/auth/login', {
      data: {
        email: TEST_USER_EMAIL,
        password: TEST_USER_PASSWORD,
      },
    });

    if (!loginResponse.ok()) {
      const body = await loginResponse.text();
      throw new Error('Login failed: ' + loginResponse.status() + ' - ' + body);
    }

    const tokens = await loginResponse.json();

    if (tokens.requires_2fa) {
      throw new Error('2FA is enabled for test user - please disable for tests');
    }

    // Fetch user info
    const userResponse = await context.get(apiBaseURL + '/api/v1/auth/me', {
      headers: { Authorization: 'Bearer ' + tokens.access_token },
    });

    if (!userResponse.ok()) {
      throw new Error('Failed to fetch user info: ' + userResponse.status());
    }

    const userData = await userResponse.json();

    // Cache auth data
    const authData = {
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token || '',
      user: {
        id: userData.id,
        email: userData.email,
        username: userData.username,
        full_name: userData.full_name,
        is_superuser: userData.is_superuser,
        is_active: userData.is_active,
        role: userData.role || (userData.is_superuser ? 'admin' : 'viewer'),
      },
      cached_at: new Date().toISOString(),
    };

    fs.writeFileSync(AUTH_CACHE_FILE, JSON.stringify(authData, null, 2));
    console.log('[Global Setup] Auth tokens cached successfully');

  } finally {
    await context.dispose();
  }
}

export default globalSetup;
