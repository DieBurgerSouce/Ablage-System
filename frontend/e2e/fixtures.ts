/**
 * Custom Playwright Test Fixtures for Ablage-System.
 *
 * Uses cached auth tokens from global setup to avoid rate limiting.
 * Implements automatic session refresh to prevent timeout during long tests.
 */

import { test as base, expect, type Page, request } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const AUTH_CACHE_FILE = path.join(__dirname, '.auth', 'auth-state.json');

// Session refresh interval (refresh every 10 minutes to stay within 15 min expiry)
const SESSION_REFRESH_INTERVAL_MS = 10 * 60 * 1000;

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

/**
 * Refreshes the auth token via API.
 * Updates cache file and returns new tokens.
 */
async function refreshAuthToken(currentAuth: CachedAuth): Promise<CachedAuth> {
  const baseURL = process.env.BASE_URL || 'http://localhost:80';
  const apiBaseURL = baseURL.includes('5173') ? 'http://localhost:8000' : baseURL;

  const context = await request.newContext();

  try {
    const refreshResponse = await context.post(`${apiBaseURL}/api/v1/auth/refresh`, {
      headers: {
        Authorization: `Bearer ${currentAuth.access_token}`,
      },
      data: {
        refresh_token: currentAuth.refresh_token,
      },
    });

    if (refreshResponse.ok()) {
      const tokens = await refreshResponse.json();
      const newAuth: CachedAuth = {
        ...currentAuth,
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token || currentAuth.refresh_token,
        cached_at: new Date().toISOString(),
      };

      // Update cache file
      fs.writeFileSync(AUTH_CACHE_FILE, JSON.stringify(newAuth, null, 2));
      console.log('[Fixtures] Session refreshed successfully');
      return newAuth;
    } else {
      console.warn('[Fixtures] Session refresh failed:', refreshResponse.status());
      return currentAuth;
    }
  } catch (error) {
    console.warn('[Fixtures] Session refresh error:', error);
    return currentAuth;
  } finally {
    await context.dispose();
  }
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

    let authData: CachedAuth = JSON.parse(fs.readFileSync(AUTH_CACHE_FILE, 'utf-8'));

    // Check if auth needs refresh (older than 10 minutes)
    const cachedTime = new Date(authData.cached_at).getTime();
    const ageMs = Date.now() - cachedTime;
    if (ageMs > SESSION_REFRESH_INTERVAL_MS) {
      console.log('[Fixtures] Auth cache is ' + (ageMs / 60000).toFixed(1) + ' min old, refreshing...');
      authData = await refreshAuthToken(authData);
    }

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

      // Onboarding/Touren unterdruecken: Jeder frische Browser-Context gilt sonst
      // als "Erstbesuch" und die App legt einen modalen OnboardingWizard (Radix-
      // Dialog -> aria-hidden auf dem Rest der App) plus Produkt-Tour-Spotlight
      // (z-[9998]-Overlay, faengt alle Klicks ab) ueber jede Seite.
      // Keys stammen aus:
      //  - features/onboarding/hooks/use-onboarding.ts  (ablage_onboarding_v2)
      //  - components/onboarding/WelcomeModal.tsx       (ablage_onboarding_complete)
      //  - features/product-tour/components/TourProvider.tsx (ablage-first-visit-done)
      window.localStorage.setItem(
        'ablage_onboarding_v2',
        JSON.stringify({
          completed: true,
          skipped: true,
          currentStep: 0,
          companyConfigured: true,
          documentUploaded: false,
        })
      );
      window.localStorage.setItem('ablage_onboarding_complete', 'true');
      window.localStorage.setItem('ablage-first-visit-done', 'true');
    }, sessionData);

    // Set up automatic session refresh during long tests
    let refreshInterval: ReturnType<typeof setInterval> | null = null;
    const startSessionRefresh = () => {
      refreshInterval = setInterval(async () => {
        try {
          const currentAuth: CachedAuth = JSON.parse(fs.readFileSync(AUTH_CACHE_FILE, 'utf-8'));
          const newAuth = await refreshAuthToken(currentAuth);

          // Update sessionStorage in the browser
          await page.evaluate((tokens) => {
            window.sessionStorage.setItem('auth_token', tokens.access_token);
            window.sessionStorage.setItem('refresh_token', tokens.refresh_token);
          }, {
            access_token: newAuth.access_token,
            refresh_token: newAuth.refresh_token,
          });
        } catch (error) {
          console.warn('[Fixtures] Background refresh error:', error);
        }
      }, SESSION_REFRESH_INTERVAL_MS);
    };

    // HINWEIS (B5, 2026-06-12): Der fruehere Notifications-Shim wurde
    // entfernt - der Frontend-API-Layer normalisiert den echten Backend-
    // Vertrag ({notifications, unreadCount, total}) jetzt selbst
    // (frontend/src/features/notifications/api/index.ts).

    // Now navigate to the app - auth data will already be in sessionStorage
    // Kein 'networkidle': Das Dashboard laedt dauerhaft nach (Notifications,
    // KI-Insights, WebSocket-Reconnects) und unter Last retried TanStack Query —
    // 'networkidle' wird dann nie erreicht und riss ganze Spec-Dateien per
    // 30s-Timeout ab (QA-Lauf 2026-06-12). Stattdessen auf die App-Shell warten.
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Verify we're logged in (not on login page)
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 });
    // BEWUSST KEIN Warten auf #main-content: Die Ziel-Routen der Tests
    // rendern nach page.goto() ohnehin frisch. (Der fruehere deterministische
    // Dashboard-Crash - WidgetSyncStatus ohne TooltipProvider - ist seit
    // 2026-06-12 behoben, B1.)

    const currentUrl = page.url();
    console.log('[Fixtures] After auth setup, current URL: ' + currentUrl);

    // Start background session refresh for long-running tests
    startSessionRefresh();

    // Provide the authenticated page to tests
    await use(page);

    // Cleanup: stop refresh interval
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    // Offene Route-Handler (aus einzelnen Specs) sauber abraeumen, damit
    // In-Flight-Requests beim Page-Close keine Teardown-Fehler ausloesen.
    await page.unrouteAll({ behavior: 'ignoreErrors' }).catch(() => {});
  },
});

export { expect };
