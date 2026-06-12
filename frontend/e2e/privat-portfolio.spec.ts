/**
 * E2E: Privat-Bereich / Portfolio
 *
 * Prueft:
 * - /privat/portfolio rendert die Portfolio-Seite (verifiziert: h2 "Portfolio"
 *   aus features/privat) ohne Fehlerzustand und ohne 5xx im Hintergrund
 * - /privat (Index) laedt ohne Fehlerzustand
 *
 * Idempotent: rein lesend.
 */

import { test, expect } from './fixtures';

test.describe('Privat - Portfolio', () => {
  test('Portfolio-Seite rendert ohne 5xx und ohne Fehlerzustand', async ({ authenticatedPage: page }) => {
    const serverErrors: string[] = [];
    page.on('response', (resp) => {
      if (resp.status() >= 500 && resp.url().includes('/api/')) {
        serverErrors.push(`${resp.status()} ${resp.url()}`);
      }
    });

    await page.goto('/privat/portfolio');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    await expect(
      page.getByRole('heading', { name: 'Portfolio' })
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Etwas ist schiefgelaufen|[Uu]nerwarteter Fehler|Anwendungsfehler/)).toHaveCount(0);

    expect(serverErrors, `Portfolio loeste 5xx aus: ${serverErrors.join(', ')}`).toHaveLength(0);
  });

  test('Privat-Index laedt ohne Fehlerzustand', async ({ authenticatedPage: page }) => {
    await page.goto('/privat');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
    await expect(page.getByText(/Etwas ist schiefgelaufen|[Uu]nerwarteter Fehler|Anwendungsfehler/)).toHaveCount(0);
    await expect(page.getByRole('heading').first()).toBeVisible({ timeout: 15000 });
  });
});
