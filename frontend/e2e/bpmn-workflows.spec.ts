/**
 * E2E: BPMN-Workflows
 *
 * Prueft:
 * - /workflows rendert die Workflow-Liste (verifiziert: h1 "Workflows",
 *   h2 "Workflow-Templates" aus features/workflows)
 * - GET /api/v1/workflows liefert 200 (kein 500)
 * - Unbekannte Workflow-ID liefert sauberes 404 (kein 500)
 *
 * Idempotent: rein lesend, es werden keine Workflows gestartet.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

test.describe('Workflows - UI', () => {
  test('Workflow-Liste rendert ohne Fehlerzustand', async ({ authenticatedPage: page }) => {
    const serverErrors: string[] = [];
    page.on('response', (resp) => {
      if (resp.status() >= 500 && resp.url().includes('/api/')) {
        serverErrors.push(`${resp.status()} ${resp.url()}`);
      }
    });

    await page.goto('/workflows');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    await expect(
      page.getByRole('heading', { name: 'Workflows', exact: true })
    ).toBeVisible({ timeout: 15000 });

    expect(serverErrors, `Workflow-Seite loeste 5xx aus: ${serverErrors.join(', ')}`).toHaveLength(0);
  });
});

apiTest.describe('Workflows - API', () => {
  apiTest('GET /workflows liefert 200 (kein 500)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/workflows`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
  });

  apiTest('Unbekannte Workflow-ID liefert 404 statt 500', async ({ request }) => {
    const resp = await request.get(
      `${API_BASE}/api/v1/workflows/00000000-0000-0000-0000-000000000000`,
      { headers: { Authorization: `Bearer ${adminToken()}` } }
    );
    apiExpect(resp.status()).not.toBe(500);
    apiExpect([400, 404, 422]).toContain(resp.status());
  });
});
