/**
 * E2E: Admin-Bereich (Rollen / Job-Queue / System)
 *
 * Prueft:
 * - /admin rendert die Admin-Uebersicht (verifiziert: h1 "Admin-Übersicht",
 *   Karten "Dokumente gesamt", "Warteschlange")
 * - Job-Queue: GET /api/v1/admin/jobs (Admin 200, Viewer 403 — Rollen-Gate)
 * - System-Queue/Health: /admin/system/queue + /admin/system/health (kein 500)
 * - Rate-Limit-Verhalten: 403 fuer Viewer kommt als deutsches JSON-Envelope
 *   (Detail-Pruefung der Limits selbst: rbac-permissions.spec.ts +
 *   tests/integration/test_rate_limit_e2e.py decken das API-seitig ab)
 *
 * Idempotent: rein lesend.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken, viewerToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Admin - UI', () => {
  test('Admin-Uebersicht rendert mit Kennzahlen-Karten', async ({ authenticatedPage: page }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    await expect(
      page.getByRole('heading', { name: 'Admin-Übersicht' })
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Dokumente gesamt').first()).toBeVisible();
    await expect(page.getByText('Warteschlange').first()).toBeVisible();
  });
});

apiTest.describe('Admin - Rollen und Job-Queue', () => {
  apiTest('Job-Queue: Admin 200, Viewer 403 (Rollen-Gate beweist beides)', async ({ request }) => {
    const adminResp = await request.get(`${API_BASE}/api/v1/admin/jobs`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(adminResp.status()).toBe(200);

    const viewerResp = await request.get(`${API_BASE}/api/v1/admin/jobs`, {
      headers: { Authorization: `Bearer ${viewerToken()}` },
    });
    apiExpect(viewerResp.status()).toBe(403);
    const body = await viewerResp.json();
    apiExpect(body.status_code).toBe(403);
    apiExpect(body.fehler).toBeTruthy();
  });

  apiTest('System-Queue und -Health antworten fuer Admin ohne 500', async ({ request }) => {
    for (const ep of ['/api/v1/admin/system/queue', '/api/v1/admin/system/health']) {
      const resp = await request.get(`${API_BASE}${ep}`, {
        headers: { Authorization: `Bearer ${adminToken()}` },
      });
      apiExpect(resp.status(), `${ep} darf nicht crashen`).not.toBe(500);
      apiExpect(resp.status()).toBe(200);
    }
  });

  apiTest('Benutzerliste ist nur fuer Admin zugaenglich', async ({ request }) => {
    const adminResp = await request.get(`${API_BASE}/api/v1/admin/users`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(adminResp.status()).toBe(200);

    const viewerResp = await request.get(`${API_BASE}/api/v1/admin/users`, {
      headers: { Authorization: `Bearer ${viewerToken()}` },
    });
    apiExpect(viewerResp.status()).toBe(403);
  });
});
