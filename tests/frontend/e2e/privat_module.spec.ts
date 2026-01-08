/**
 * Privat-Modul E2E-Tests
 *
 * Testet alle Privat-Module mit und ohne spaceId in der URL.
 * Verifiziert den useDefaultSpace Fix.
 */

import { test, expect } from '@playwright/test';
import path from 'path';

// Use auth state from setup
test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

test.describe('Privat-Modul Tests', () => {
  test.describe('Module ohne spaceId in URL', () => {
    const moduleUrls = [
      { path: '/privat', name: 'Übersicht' },
      { path: '/privat/fahrzeuge', name: 'Fahrzeuge' },
      { path: '/privat/immobilien', name: 'Immobilien' },
      { path: '/privat/versicherungen', name: 'Versicherungen' },
      { path: '/privat/finanzen', name: 'Finanzen' },
      { path: '/privat/fristen', name: 'Fristen' },
    ];

    for (const { path: url, name } of moduleUrls) {
      test(`${name}-Seite lädt ohne Fehler`, async ({ page }) => {
        // Navigate to module page
        await page.goto(url);
        await page.waitForLoadState('networkidle');

        // Check for error messages
        const errorMessage = page.locator('text=Kein Bereich ausgewählt');
        const isErrorVisible = await errorMessage.isVisible({ timeout: 2000 }).catch(() => false);

        // If there are no spaces, we should see a different message
        const noSpacesMessage = page.locator('text=Noch keine Bereiche');
        const isNoSpacesVisible = await noSpacesMessage.isVisible({ timeout: 2000 }).catch(() => false);

        // Should not show the "no space selected" error
        if (!isNoSpacesVisible) {
          expect(isErrorVisible).toBe(false);
        }

        // Check for NaN or undefined in visible text
        const pageText = await page.locator('body').innerText();
        expect(pageText).not.toContain('NaN undefined');
        expect(pageText).not.toContain('undefined undefined');

        // Take screenshot for manual review
        await page.screenshot({ path: `test-results/privat-${name.toLowerCase()}.png` });
      });
    }
  });

  test.describe('SpaceDetail mit Tabs', () => {
    test('Alle Tabs laden korrekt mit spaceId', async ({ page }) => {
      // First get a space from the overview
      await page.goto('/privat');
      await page.waitForLoadState('networkidle');

      // Look for a space card/link
      const spaceLink = page.locator('a[href*="/privat/spaces/"]').first();
      const hasSpaces = await spaceLink.isVisible({ timeout: 5000 }).catch(() => false);

      if (!hasSpaces) {
        test.skip();
        return;
      }

      // Click on first space
      await spaceLink.click();
      await page.waitForLoadState('networkidle');

      // Check URL contains spaceId
      expect(page.url()).toContain('/privat/spaces/');

      // Test each tab
      const tabs = ['Übersicht', 'Immobilien', 'Fahrzeuge', 'Versicherungen', 'Finanzen', 'Fristen'];

      for (const tabName of tabs) {
        const tab = page.locator(`button:has-text("${tabName}")`);
        const isTabVisible = await tab.isVisible({ timeout: 2000 }).catch(() => false);

        if (isTabVisible) {
          await tab.click();
          await page.waitForLoadState('networkidle');

          // Should not show error after clicking tab
          const errorVisible = await page.locator('text=Kein Bereich ausgewählt').isVisible({ timeout: 1000 }).catch(() => false);
          expect(errorVisible).toBe(false);
        }
      }
    });
  });

  test.describe('NaN/undefined Bug Fix Verification', () => {
    test('Space-Cards zeigen keine NaN Werte', async ({ page }) => {
      await page.goto('/privat');
      await page.waitForLoadState('networkidle');

      // Get all text content
      const pageContent = await page.locator('body').innerText();

      // Should not contain NaN in displayed text
      expect(pageContent).not.toMatch(/\bNaN\b/);
      expect(pageContent).not.toMatch(/undefined\s+undefined/);

      // Check specific stat areas if they exist
      const statElements = page.locator('[class*="stat"], [class*="card"], dd');
      const count = await statElements.count();

      for (let i = 0; i < count; i++) {
        const text = await statElements.nth(i).innerText();
        expect(text).not.toMatch(/\bNaN\b/);
      }
    });
  });
});
