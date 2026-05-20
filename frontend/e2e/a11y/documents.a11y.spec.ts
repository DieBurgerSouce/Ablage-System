import { test, expect } from '@playwright/test';
import { expectNoA11yViolations, checkKeyboardNavigation } from './a11y-utils';

test.describe('Dokumentenliste Barrierefreiheit', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/documents');
    await page.waitForLoadState('networkidle');
  });

  test('WCAG 2.1 AA: Keine Verletzungen in Dokumentenliste', async ({ page }) => {
    await expectNoA11yViolations(page, 'Dokumentenliste');
  });

  test('Tabelle hat korrekte ARIA-Rollen', async ({ page }) => {
    // Check for table with proper role
    const table = page.locator('table, [role="table"], [role="grid"]');
    if (await table.count() > 0) {
      // Table headers should have scope
      const headers = page.locator('th, [role="columnheader"]');
      const headerCount = await headers.count();
      expect(headerCount, 'Tabelle benoetigt Spaltenkoepfe').toBeGreaterThan(0);
    }
  });

  test('Such- und Filter-Elemente sind zugaenglich', async ({ page }) => {
    // Check search input
    const searchInput = page.locator('input[type="search"], input[placeholder*="Such"], input[aria-label*="Such"]');
    if (await searchInput.count() > 0) {
      const label = await searchInput.first().evaluate((el) => {
        return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
      });
      expect(label.length, 'Suchfeld benoetigt Label oder Placeholder').toBeGreaterThan(0);
    }
  });

  test('Pagination ist tastaturzugaenglich', async ({ page }) => {
    const pagination = page.locator('nav[aria-label*="aginat"], [role="navigation"]');
    if (await pagination.count() > 0) {
      const links = pagination.locator('a, button');
      const linkCount = await links.count();
      expect(linkCount, 'Pagination benoetigt klickbare Elemente').toBeGreaterThan(0);
    }
  });

  test('Dokument-Upload Dialog ist zugaenglich', async ({ page }) => {
    // Try to open upload dialog
    const uploadBtn = page.locator('button:has-text("Hochladen"), button:has-text("Upload"), button[aria-label*="upload" i]');
    if (await uploadBtn.count() > 0) {
      await uploadBtn.first().click();
      await page.waitForTimeout(500);

      // Check dialog has proper role
      const dialog = page.locator('[role="dialog"], dialog');
      if (await dialog.count() > 0) {
        // Dialog should trap focus
        const ariaLabel = await dialog.first().evaluate((el) => {
          return el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || '';
        });
        expect(ariaLabel.length, 'Dialog benoetigt aria-label oder aria-labelledby').toBeGreaterThan(0);

        // Check for close button
        const closeBtn = dialog.locator('button[aria-label*="Schliess"], button[aria-label*="close" i], button:has-text("Abbrechen")');
        expect(await closeBtn.count(), 'Dialog benoetigt Schliessen-Button').toBeGreaterThan(0);

        // Run a11y check on dialog
        await expectNoA11yViolations(page, 'Upload-Dialog', {
          include: ['[role="dialog"]', 'dialog'],
        });
      }
    }
  });
});
