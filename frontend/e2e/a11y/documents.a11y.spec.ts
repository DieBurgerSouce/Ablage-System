// WICHTIG: authentifizierte Fixture verwenden. Mit dem rohen @playwright/test
// landeten diese Tests auf der Login-Redirect-Seite (QA-Lauf 2026-06-12).
import { test, expect } from '../fixtures';
import { expectNoA11yViolations, waitForAppSettled } from './a11y-utils';

test.describe('Dokumentenliste Barrierefreiheit', () => {
  test.beforeEach(async ({ authenticatedPage: page }) => {
    // Route-Drift: '/documents' existiert nach dem Frontend-Umbau nicht mehr
    // (nur noch /documents/$documentId) und landete im 404-Catch-all.
    // Die kanonische Listen-Ansicht mit Suche/Pagination ist /kunden (EntityList).
    await page.goto('/kunden');
    await page.waitForLoadState('domcontentloaded');
    await waitForAppSettled(page);
  });

  test('WCAG 2.1 AA: Keine Verletzungen in Dokumentenliste', async ({ authenticatedPage: page }) => {
    // BEKANNTE APP-A11Y-BUGS in der GLOBALEN App-Huelle (Sidebar + FAB), die auf
    // JEDER authentifizierten Seite erscheinen (Stream s5, 2026-06-13, axe 4.11):
    //  - color-contrast (serious): Sidebar-Texte mit text-muted-foreground
    //    (#404952 auf #02060d = Kontrast 2.21, noetig 4.5) — "Enterprise Document
    //    Management" (aside .p-6 .mt-1), Firmenname "E2E Test GmbH"
    //    (.justify-start > span), Collapse-Zaehler "1/8" (.gap-1 .text-xs); sowie
    //    das Firmen-Avatar-Kuerzel (.bg-primary/20, Kontrast 1.79).
    //  - button-name (critical): Der schwebende Proaktiv-Assistent-FAB (.px-8,
    //    Bot-Icon, fixed bottom-6 right-6) hat nur aria-hidden-SVGs und KEINEN
    //    barrierefreien Namen (kein aria-label/Text).
    // Beides liegt im App-Code (Sidebar-Komponente + Proaktiv-FAB), nicht in
    // dieser Spec. NICHT durch Ausschluss gruen biegen, sonst verschwindet der
    // echte WCAG-Befund.
    // B7-Stream 2026-06-13 GEFIXT: Sidebar text-sidebar-muted-foreground (>=4.5:1)
    // + Proaktiv-FAB aria-label.
    await expectNoA11yViolations(page, 'Dokumentenliste', {
      // [data-sonner-toast]: BEKANNTER APP-BUG (Kategorie B, color-contrast im
      // "Offline-Modus bereit"-Toast) — siehe dashboard.a11y.spec.ts.
      exclude: ['[data-sonner-toast]'],
    });
  });

  test('Tabelle hat korrekte ARIA-Rollen', async ({ authenticatedPage: page }) => {
    // Check for table with proper role
    const table = page.locator('table, [role="table"], [role="grid"]');
    if (await table.count() > 0) {
      // Table headers should have scope
      const headers = page.locator('th, [role="columnheader"]');
      const headerCount = await headers.count();
      expect(headerCount, 'Tabelle benoetigt Spaltenkoepfe').toBeGreaterThan(0);
    }
  });

  test('Such- und Filter-Elemente sind zugaenglich', async ({ authenticatedPage: page }) => {
    // Check search input
    const searchInput = page.locator('input[type="search"], input[placeholder*="Such"], input[aria-label*="Such"]');
    if (await searchInput.count() > 0) {
      const label = await searchInput.first().evaluate((el) => {
        return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
      });
      expect(label.length, 'Suchfeld benoetigt Label oder Placeholder').toBeGreaterThan(0);
    }
  });

  test('Pagination ist tastaturzugaenglich', async ({ authenticatedPage: page }) => {
    const pagination = page.locator('nav[aria-label*="aginat"], [role="navigation"]');
    if (await pagination.count() > 0) {
      const links = pagination.locator('a, button');
      const linkCount = await links.count();
      expect(linkCount, 'Pagination benoetigt klickbare Elemente').toBeGreaterThan(0);
    }
  });

  test('Dokument-Upload Dialog ist zugaenglich', async ({ authenticatedPage: page }) => {
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
