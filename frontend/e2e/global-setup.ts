/**
 * Global Setup for Playwright Tests
 *
 * Logs in once per role and caches auth tokens so tests don't hit the
 * login rate limit (5/15min). Two roles are cached:
 *   - admin  -> .auth/auth-state.json    (admin@localhost.com,  is_superuser=true)
 *   - viewer -> .auth/viewer-state.json  (viewer@localhost.com, is_superuser=false)
 *
 * The viewer role is required so RBAC tests can catch real authorization
 * failures (a non-admin must be denied). Both users are provisioned by
 * scripts/seed_e2e.py.
 *
 * Resilience: if a login is rate-limited (429) but a cache file already
 * exists, the cached token is reused instead of failing the whole run.
 */

import { request } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const AUTH_DIR = path.join(__dirname, '.auth');

interface Role {
  email: string;
  password: string;
  cacheFile: string;
  fallbackRole: string;
}

const ROLES: Role[] = [
  {
    email: process.env.TEST_USER_EMAIL || 'admin@localhost.com',
    password: process.env.TEST_USER_PASSWORD || 'admin123',
    cacheFile: path.join(AUTH_DIR, 'auth-state.json'),
    fallbackRole: 'admin',
  },
  {
    email: process.env.TEST_VIEWER_EMAIL || 'viewer@localhost.com',
    password: process.env.TEST_VIEWER_PASSWORD || 'viewer123',
    cacheFile: path.join(AUTH_DIR, 'viewer-state.json'),
    fallbackRole: 'viewer',
  },
];

function cacheIsFresh(cacheFile: string): boolean {
  if (!fs.existsSync(cacheFile)) return false;
  const ageMinutes = (Date.now() - fs.statSync(cacheFile).mtimeMs) / (1000 * 60);
  // 2 statt 10 Minuten: Access-Tokens laufen nach 15 min ab. Ein voller
  // chromium-Lauf dauert mehrere Minuten — startet er mit einem 10 min alten
  // Token, liefern API-Tests am Ende 401 statt 403 (beobachtet 2026-06-12).
  // Gegen den Test-Stack (RATE_LIMIT_ENABLED=false) ist Re-Login billig;
  // bei 429 greift weiterhin der Cache-Fallback unten.
  return ageMinutes < 2;
}

async function cacheAuth(role: Role): Promise<void> {
  if (cacheIsFresh(role.cacheFile)) {
    console.log(`[Global Setup] Using cached auth for ${role.email}`);
    return;
  }

  const baseURL = process.env.BASE_URL || 'http://localhost:80';
  const apiBaseURL = baseURL.includes('5173') ? 'http://localhost:8000' : baseURL;
  const context = await request.newContext();

  try {
    const loginResponse = await context.post(apiBaseURL + '/api/v1/auth/login', {
      data: { email: role.email, password: role.password },
    });

    if (!loginResponse.ok()) {
      // Rate-limited or transient: fall back to an existing (possibly stale) cache.
      if (fs.existsSync(role.cacheFile)) {
        console.warn(
          `[Global Setup] Login for ${role.email} returned ${loginResponse.status()}; ` +
          `reusing existing cache file.`
        );
        return;
      }
      const body = await loginResponse.text();
      throw new Error(`Login failed for ${role.email}: ${loginResponse.status()} - ${body}`);
    }

    const tokens = await loginResponse.json();
    if (tokens.requires_2fa) {
      throw new Error(`2FA is enabled for ${role.email} - please disable for tests`);
    }

    const userResponse = await context.get(apiBaseURL + '/api/v1/auth/me', {
      headers: { Authorization: 'Bearer ' + tokens.access_token },
    });
    if (!userResponse.ok()) {
      throw new Error(`Failed to fetch user info for ${role.email}: ${userResponse.status()}`);
    }
    const userData = await userResponse.json();

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
        role: userData.role || (userData.is_superuser ? 'admin' : role.fallbackRole),
      },
      cached_at: new Date().toISOString(),
      // G03: Die vom Login gesetzten httpOnly-Cookies (access_token + csrf_token)
      // aus dem Request-Context mit-cachen. Die Fixture spielt sie in den
      // Browser-Context zurueck (addCookies) -> geschuetzte Daten-Endpoints
      // authentifizieren wieder ueber das Cookie statt ueber ein JS-Bearer-Token.
      cookies: (await context.storageState()).cookies,
    };

    fs.writeFileSync(role.cacheFile, JSON.stringify(authData, null, 2));
    console.log(`[Global Setup] Auth tokens cached for ${role.email}`);
  } finally {
    await context.dispose();
  }
}

async function globalSetup() {
  if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  }
  for (const role of ROLES) {
    await cacheAuth(role);
  }
}

export default globalSetup;
