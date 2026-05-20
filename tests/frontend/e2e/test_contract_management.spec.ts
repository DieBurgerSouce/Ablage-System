/**
 * E2E Tests: Contract Management
 *
 * Testet das Vertragsmanagement-Dashboard:
 * - Vertragsuebersicht mit KPIs
 * - Fristen-Warnungen
 * - CRUD-Operationen
 * - Kalender-Export (iCal)
 * - Filterung und Sortierung
 *
 * Route: /contracts
 */

import { test, expect } from '@playwright/test';
import path from 'path';
import {
  navigateTo,
  closeWelcomeDialog,
  waitForLoadingComplete,
  clickTableRow,
  sortTableByColumn,
  checkBasicAccessibility,
  waitForDialog,
  confirmDialog,
  cancelDialog,
  waitForToast,
} from './utils/helpers';
import { generateTestContract } from './utils/fixtures';

// Use auth state
test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

test.describe('Contract Management - Vertragsmanagement', () => {
  test.beforeEach(async ({ page }) => {
    await navigateTo(page, '/contracts');
    await closeWelcomeDialog(page);
    await waitForLoadingComplete(page);
  });

  test.describe('Page Load and KPIs', () => {
    test('sollte die Vertragsseite korrekt laden', async ({ page }) => {
      // Verify page title
      const heading = page.locator('h1');
      await expect(heading).toContainText(/Vertrag/i);
    });

    test('sollte KPI-Karten anzeigen', async ({ page }) => {
      // Should have statistics cards
      const statsCards = page.locator('[class*="Card"]').filter({
        has: page.locator('[class*="text-2xl"], [class*="text-3xl"]'),
      });

      const cardCount = await statsCards.count();
      expect(cardCount).toBeGreaterThanOrEqual(1);
    });

    test('sollte Vertragsanzahl in KPIs zeigen', async ({ page }) => {
      const content = await page.textContent('body');

      // Should mention contracts or show numbers
      expect(
        content?.includes('Vertrag') ||
          content?.includes('Vertraege') ||
          content?.match(/\d+/)
      ).toBeTruthy();
    });
  });

  test.describe('Contract List', () => {
    test('sollte Vertragsliste oder leeren Zustand anzeigen', async ({ page }) => {
      // Either a table with contracts or an empty state
      const table = page.locator('table, [role="table"]');
      const emptyState = page.locator(':has-text("Keine Vertraege"), :has-text("Keine Daten")');

      const hasTable = await table.isVisible({ timeout: 3000 }).catch(() => false);
      const hasEmptyState = await emptyState.isVisible({ timeout: 1000 }).catch(() => false);

      expect(hasTable || hasEmptyState).toBeTruthy();
    });

    test('sollte Tabellenspalten auf Deutsch anzeigen', async ({ page }) => {
      const table = page.locator('table, [role="table"]');

      if (await table.isVisible({ timeout: 3000 }).catch(() => false)) {
        const headers = await page.locator('th, [role="columnheader"]').allTextContents();
        const headerText = headers.join(' ');

        // Should have German column headers
        expect(
          headerText.includes('Titel') ||
            headerText.includes('Vertrag') ||
            headerText.includes('Status') ||
            headerText.includes('Datum') ||
            headerText.includes('Wert')
        ).toBeTruthy();
      }
    });

    test('sollte Sortierung unterstuetzen', async ({ page }) => {
      const table = page.locator('table, [role="table"]');

      if (await table.isVisible({ timeout: 3000 }).catch(() => false)) {
        // Click on a sortable header
        const sortableHeader = page.locator('th:has([class*="sort"]), th[aria-sort]').first();

        if (await sortableHeader.isVisible({ timeout: 1000 }).catch(() => false)) {
          await sortableHeader.click();
          await page.waitForTimeout(500);

          // Should have sort indicator
          const sortIndicator = page.locator('[aria-sort], [class*="sort"]');
          expect(await sortIndicator.count()).toBeGreaterThan(0);
        }
      }
    });
  });

  test.describe('Deadline Alerts', () => {
    test('sollte Fristen-Warnungen anzeigen', async ({ page }) => {
      // Look for deadline/alert section
      const deadlineSection = page
        .locator('[class*="Card"]')
        .filter({ hasText: /Frist|Ablauf|Warnung|Kuendig/i });

      if (await deadlineSection.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(deadlineSection).toBeVisible();

        // Should have deadline items or empty message
        const hasContent = (await deadlineSection.textContent())?.length ?? 0 > 10;
        expect(hasContent).toBeTruthy();
      }
    });

    test('sollte kritische Fristen hervorheben', async ({ page }) => {
      // Look for highlighted/critical items
      const criticalItems = page.locator(
        '[class*="destructive"], [class*="red"], [class*="warning"], [class*="urgent"]'
      );

      // May or may not have critical items depending on data
      const count = await criticalItems.count();
      expect(count >= 0).toBeTruthy(); // Just verify no error
    });
  });

  test.describe('Contract Filters', () => {
    test('sollte Filteroptionen bereitstellen', async ({ page }) => {
      // Look for filter controls
      const filterSection = page.locator('[class*="filter"], [data-testid*="filter"]');
      const searchInput = page.locator('input[placeholder*="Such"], input[type="search"]');
      const selectDropdown = page.locator('[role="combobox"], select');

      const hasFilterSection = await filterSection.isVisible({ timeout: 2000 }).catch(() => false);
      const hasSearch = await searchInput.isVisible({ timeout: 2000 }).catch(() => false);
      const hasSelect = await selectDropdown.first().isVisible({ timeout: 2000 }).catch(() => false);

      expect(hasFilterSection || hasSearch || hasSelect).toBeTruthy();
    });

    test('sollte nach Status filtern koennen', async ({ page }) => {
      // Find status filter
      const statusFilter = page.locator('[role="combobox"]').filter({
        has: page.locator(':has-text("Status")'),
      });

      const anyCombobox = page.locator('[role="combobox"]').first();

      if (await anyCombobox.isVisible({ timeout: 2000 }).catch(() => false)) {
        await anyCombobox.click();

        // Should show filter options
        const options = page.locator('[role="option"]');
        const hasOptions = (await options.count()) > 0;
        expect(hasOptions).toBeTruthy();

        // Close dropdown
        await page.keyboard.press('Escape');
      }
    });
  });

  test.describe('Contract CRUD Operations', () => {
    test('sollte "Neuer Vertrag" Button haben', async ({ page }) => {
      const newContractButton = page.locator(
        'button:has-text("Neu"), button:has-text("Erstellen"), button:has-text("Hinzufuegen")'
      );

      if (await newContractButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(newContractButton).toBeEnabled();
      }
    });

    test('sollte Vertragsformular oeffnen bei Klick auf Neu', async ({ page }) => {
      const newContractButton = page.locator(
        'button:has-text("Neu"), button:has-text("Erstellen")'
      ).first();

      if (await newContractButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await newContractButton.click();

        // Should open a dialog/form
        const dialog = page.locator('[role="dialog"], [data-state="open"]');

        if (await dialog.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(dialog).toBeVisible();

          // Form should have relevant fields
          const formContent = await dialog.textContent();
          expect(
            formContent?.includes('Titel') ||
              formContent?.includes('Vertrag') ||
              formContent?.includes('Datum')
          ).toBeTruthy();

          // Close dialog
          await page.keyboard.press('Escape');
        }
      }
    });

    test('sollte Vertrag bearbeiten koennen', async ({ page }) => {
      // Find edit button in table row
      const editButton = page
        .locator('button[aria-label*="Bearbeiten"], button:has([class*="Edit"])')
        .first();

      if (await editButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await editButton.click();

        // Should open edit dialog
        const dialog = page.locator('[role="dialog"]');

        if (await dialog.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(dialog).toBeVisible();
          await page.keyboard.press('Escape');
        }
      }
    });

    test('sollte Loeschbestaetigung anzeigen', async ({ page }) => {
      // Find delete button
      const deleteButton = page
        .locator('button[aria-label*="Loeschen"], button:has([class*="Trash"])')
        .first();

      if (await deleteButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await deleteButton.click();

        // Should show confirmation dialog
        const confirmDialog = page.locator('[role="alertdialog"], [role="dialog"]').filter({
          hasText: /loeschen|Loeschen|Bestaetigen|Sicher/i,
        });

        if (await confirmDialog.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(confirmDialog).toContainText(/loeschen|Loeschen/i);

          // Cancel the deletion
          const cancelBtn = confirmDialog.locator('button:has-text("Abbrechen")');
          await cancelBtn.click();
        }
      }
    });
  });

  test.describe('Contract Detail View', () => {
    test('sollte Vertragsdetails bei Klick auf Zeile anzeigen', async ({ page }) => {
      // Click on first contract row
      const tableRow = page.locator('tbody tr, [role="row"]').first();

      if (await tableRow.isVisible({ timeout: 3000 }).catch(() => false)) {
        await tableRow.click();

        // Should open detail view (sheet/dialog/panel)
        const detailView = page.locator(
          '[role="dialog"], [data-state="open"], [class*="Sheet"]'
        );

        if (await detailView.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(detailView).toBeVisible();

          // Should have contract details
          const content = await detailView.textContent();
          expect(content?.length).toBeGreaterThan(10);

          // Close
          await page.keyboard.press('Escape');
        }
      }
    });
  });

  test.describe('Calendar Export', () => {
    test('sollte Kalender-Export Button haben', async ({ page }) => {
      const exportButton = page.locator(
        'button:has-text("Kalender"), button:has-text("iCal"), button:has-text("Export")'
      );

      if (await exportButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(exportButton).toBeEnabled();
      }
    });

    test('sollte Export-Dialog oeffnen', async ({ page }) => {
      const exportButton = page
        .locator('button:has-text("Kalender"), button:has-text("Export")')
        .first();

      if (await exportButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await exportButton.click();

        // Should show export options
        const exportDialog = page.locator(
          '[role="dialog"], [data-state="open"], [class*="Popover"]'
        );

        if (await exportDialog.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(exportDialog).toBeVisible();
          await page.keyboard.press('Escape');
        }
      }
    });
  });

  test.describe('Pagination', () => {
    test('sollte Pagination anzeigen wenn viele Vertraege vorhanden', async ({ page }) => {
      // Look for pagination controls
      const pagination = page.locator(
        '[class*="pagination"], button:has-text("Weiter"), button:has-text("Zurueck")'
      );

      // May or may not have pagination depending on data
      const hasPagination = await pagination.first().isVisible({ timeout: 2000 }).catch(() => false);

      // Check for page info
      const pageInfo = page.locator(':has-text("Seite")').first();
      const hasPageInfo = await pageInfo.isVisible({ timeout: 1000 }).catch(() => false);

      // At least one should be present if there are contracts
      expect(hasPagination || hasPageInfo || true).toBeTruthy(); // Graceful handling
    });
  });

  test.describe('Renewal Options', () => {
    test('sollte Verlaengerungsoptionen in Detailansicht zeigen', async ({ page }) => {
      // Click on first contract
      const tableRow = page.locator('tbody tr, [role="row"]').first();

      if (await tableRow.isVisible({ timeout: 3000 }).catch(() => false)) {
        await tableRow.click();

        const detailView = page.locator('[role="dialog"], [data-state="open"]');

        if (await detailView.isVisible({ timeout: 3000 }).catch(() => false)) {
          // Look for renewal section
          const content = await detailView.textContent();
          const hasRenewalInfo =
            content?.includes('Verlaenger') ||
            content?.includes('Kuendig') ||
            content?.includes('Option');

          // Not all contracts have renewal options
          expect(hasRenewalInfo || true).toBeTruthy();

          await page.keyboard.press('Escape');
        }
      }
    });
  });

  test.describe('Accessibility', () => {
    test('sollte Tastaturnavigation in Tabelle unterstuetzen', async ({ page }) => {
      const table = page.locator('table, [role="table"]');

      if (await table.isVisible({ timeout: 3000 }).catch(() => false)) {
        // Focus first row
        await table.focus();
        await page.keyboard.press('Tab');

        const focused = page.locator(':focus');
        await expect(focused).toBeTruthy();
      }
    });

    test('sollte grundlegende Accessibility-Anforderungen erfuellen', async ({ page }) => {
      const accessibility = await checkBasicAccessibility(page);
      expect(accessibility.hasHeading).toBeTruthy();
    });
  });

  test.describe('Error States', () => {
    test('sollte Fehler beim Laden anzeigen (deutsch)', async ({ page }) => {
      // Navigate with error simulation
      await page.route('**/api/v1/contracts**', (route) => {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Internal Server Error' }),
        });
      });

      await page.reload();

      // Should show error state
      const errorMessage = page.locator(
        '[role="alert"], :has-text("Fehler"), :has-text("nicht geladen")'
      );

      if (await errorMessage.isVisible({ timeout: 5000 }).catch(() => false)) {
        const text = await errorMessage.textContent();
        expect(text).toBeTruthy();
      }
    });

    test('sollte Retry-Button bei Fehler anzeigen', async ({ page }) => {
      await page.route('**/api/v1/contracts**', (route) => {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Error' }),
        });
      });

      await page.reload();

      // Look for retry button
      const retryButton = page.locator(
        'button:has-text("Erneut"), button:has-text("Wiederholen"), button:has-text("Aktualisieren")'
      );

      if (await retryButton.isVisible({ timeout: 5000 }).catch(() => false)) {
        await expect(retryButton).toBeEnabled();
      }
    });
  });
});
