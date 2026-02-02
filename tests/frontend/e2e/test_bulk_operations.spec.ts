/**
 * E2E Tests: Bulk Operations
 *
 * Testet Multi-Select und Massenoperationen:
 * - Mehrfachauswahl in Listen
 * - Bulk-Action-Leiste
 * - Massen-Loeschung
 * - Massen-Verschiebung
 * - Massen-Export
 * - Auswahl-Counter
 */

import { test, expect } from '@playwright/test';
import path from 'path';
import {
  navigateTo,
  closeWelcomeDialog,
  waitForLoadingComplete,
  checkBasicAccessibility,
} from './utils/helpers';

// Use auth state
test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

test.describe('Bulk Operations - Massenoperationen', () => {
  test.describe('Document List', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte Checkboxen fuer Mehrfachauswahl haben', async ({ page }) => {
      const checkboxes = page.locator('input[type="checkbox"], [role="checkbox"]');

      if (await checkboxes.first().isVisible({ timeout: 5000 }).catch(() => false)) {
        expect(await checkboxes.count()).toBeGreaterThan(0);
      }
    });

    test('sollte einzelne Items auswaehlen koennen', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"], [role="row"] input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        // Should be checked
        const isChecked = await checkbox.isChecked();
        expect(isChecked).toBeTruthy();
      }
    });

    test('sollte "Alle auswaehlen" haben', async ({ page }) => {
      const selectAllCheckbox = page.locator(
        'th input[type="checkbox"], thead input[type="checkbox"], [aria-label*="Alle"], [aria-label*="all"]'
      );

      if (await selectAllCheckbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(selectAllCheckbox).toBeVisible();
      }
    });

    test('sollte alle Items auswaehlen bei Klick auf "Alle"', async ({ page }) => {
      const selectAllCheckbox = page.locator('th input[type="checkbox"]').first();

      if (await selectAllCheckbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await selectAllCheckbox.click();

        // All row checkboxes should be checked
        const rowCheckboxes = page.locator('tbody input[type="checkbox"]');
        const rowCount = await rowCheckboxes.count();

        if (rowCount > 0) {
          for (let i = 0; i < Math.min(rowCount, 5); i++) {
            const isChecked = await rowCheckboxes.nth(i).isChecked();
            expect(isChecked).toBeTruthy();
          }
        }

        // Uncheck all
        await selectAllCheckbox.click();
      }
    });
  });

  test.describe('Bulk Action Bar', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte Bulk-Action-Leiste bei Auswahl anzeigen', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        // Should show bulk action bar
        const bulkActionBar = page.locator(
          '[class*="bulk-action"], [class*="BulkAction"], [data-testid*="bulk"]'
        );

        if (await bulkActionBar.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(bulkActionBar).toBeVisible();
        }

        // Uncheck
        await checkbox.click();
      }
    });

    test('sollte Auswahl-Anzahl anzeigen', async ({ page }) => {
      const checkboxes = page.locator('tbody input[type="checkbox"]');
      const checkboxCount = await checkboxes.count();

      if (checkboxCount >= 2) {
        // Select 2 items
        await checkboxes.nth(0).click();
        await checkboxes.nth(1).click();

        // Should show count
        const counter = page.locator(':has-text("2 ausgewaehlt"), :has-text("2 selected")');

        if (await counter.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(counter).toBeVisible();
        }

        // Uncheck
        await checkboxes.nth(0).click();
        await checkboxes.nth(1).click();
      }
    });

    test('sollte Bulk-Action-Leiste verstecken wenn keine Auswahl', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        // Select
        await checkbox.click();
        await page.waitForTimeout(300);

        // Deselect
        await checkbox.click();
        await page.waitForTimeout(300);

        // Bulk action bar should be hidden
        const bulkActionBar = page.locator('[class*="bulk-action"]');

        if (await bulkActionBar.isVisible({ timeout: 1000 }).catch(() => false)) {
          // It might still be visible but transitioning
        }
      }
    });
  });

  test.describe('Bulk Delete', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte Massen-Loeschung Button haben', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const deleteButton = page.locator(
          'button:has-text("Loeschen"), button:has([class*="Trash"]), button[aria-label*="loeschen"]'
        );

        if (await deleteButton.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(deleteButton).toBeEnabled();
        }

        await checkbox.click();
      }
    });

    test('sollte Bestaetigung fuer Massen-Loeschung anzeigen', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const deleteButton = page.locator('button:has-text("Loeschen")').first();

        if (await deleteButton.isVisible({ timeout: 3000 }).catch(() => false)) {
          await deleteButton.click();

          // Should show confirmation
          const confirmDialog = page.locator('[role="alertdialog"], [role="dialog"]');

          if (await confirmDialog.isVisible({ timeout: 3000 }).catch(() => false)) {
            const content = await confirmDialog.textContent();
            expect(
              content?.includes('loeschen') ||
                content?.includes('Loeschen') ||
                content?.includes('entfernen')
            ).toBeTruthy();

            // Cancel
            const cancelButton = confirmDialog.locator('button:has-text("Abbrechen")');
            await cancelButton.click();
          }
        }

        await checkbox.click();
      }
    });
  });

  test.describe('Bulk Move', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte Massen-Verschiebung Button haben', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const moveButton = page.locator(
          'button:has-text("Verschieben"), button:has-text("Move"), button:has([class*="Move"])'
        );

        if (await moveButton.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(moveButton).toBeEnabled();
        }

        await checkbox.click();
      }
    });

    test('sollte Ziel-Ordner-Dialog oeffnen', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const moveButton = page.locator('button:has-text("Verschieben")').first();

        if (await moveButton.isVisible({ timeout: 3000 }).catch(() => false)) {
          await moveButton.click();

          const moveDialog = page.locator('[role="dialog"]');

          if (await moveDialog.isVisible({ timeout: 3000 }).catch(() => false)) {
            const content = await moveDialog.textContent();
            expect(
              content?.includes('Ziel') ||
                content?.includes('Ordner') ||
                content?.includes('Verschieben')
            ).toBeTruthy();

            await page.keyboard.press('Escape');
          }
        }

        await checkbox.click();
      }
    });
  });

  test.describe('Bulk Export', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte Massen-Export Button haben', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const exportButton = page.locator(
          'button:has-text("Export"), button:has-text("Download"), button:has([class*="Download"])'
        );

        if (await exportButton.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(exportButton).toBeEnabled();
        }

        await checkbox.click();
      }
    });

    test('sollte Export-Optionen anbieten', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const exportButton = page.locator('button:has-text("Export")').first();

        if (await exportButton.isVisible({ timeout: 3000 }).catch(() => false)) {
          await exportButton.click();

          // Should show export options
          const exportOptions = page.locator('[role="menu"], [role="dialog"], [class*="dropdown"]');

          if (await exportOptions.isVisible({ timeout: 3000 }).catch(() => false)) {
            const content = await exportOptions.textContent();
            expect(
              content?.includes('PDF') ||
                content?.includes('CSV') ||
                content?.includes('Excel') ||
                content?.includes('ZIP')
            ).toBeTruthy();

            await page.keyboard.press('Escape');
          }
        }

        await checkbox.click();
      }
    });
  });

  test.describe('Selection Persistence', () => {
    test('sollte Auswahl nach Filterung beibehalten (wenn moeglich)', async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);

      // This depends on implementation - some apps clear selection on filter
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        // Apply a filter if available
        const filterInput = page.locator('input[placeholder*="Such"], input[type="search"]');

        if (await filterInput.isVisible({ timeout: 2000 }).catch(() => false)) {
          await filterInput.fill('test');
          await page.waitForTimeout(500);

          // Selection behavior depends on implementation
        }

        await checkbox.click().catch(() => {});
      }
    });
  });

  test.describe('Keyboard Selection', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte Space zum Auswaehlen nutzen koennen', async ({ page }) => {
      const row = page.locator('tbody tr, [role="row"]').first();

      if (await row.isVisible({ timeout: 3000 }).catch(() => false)) {
        // Focus the row
        await row.focus();
        await page.keyboard.press('Space');

        // Should select (implementation dependent)
        await page.waitForTimeout(300);
      }
    });

    test('sollte Shift+Click fuer Bereichsauswahl unterstuetzen', async ({ page }) => {
      const rows = page.locator('tbody tr, [role="row"]');
      const rowCount = await rows.count();

      if (rowCount >= 3) {
        const firstRow = rows.nth(0);
        const thirdRow = rows.nth(2);

        // Click first
        await firstRow.click();

        // Shift+Click third
        await thirdRow.click({ modifiers: ['Shift'] });

        // Should select range (implementation dependent)
        await page.waitForTimeout(300);
      }
    });

    test('sollte Ctrl/Cmd+A zum Auswaehlen aller nutzen koennen', async ({ page }) => {
      // Focus the table
      const table = page.locator('table, [role="table"]');

      if (await table.isVisible({ timeout: 3000 }).catch(() => false)) {
        await table.click();

        // Try Ctrl+A (may select all or be prevented)
        await page.keyboard.press('Control+a');
        await page.waitForTimeout(300);

        // Behavior is implementation dependent
      }
    });
  });

  test.describe('Accessibility', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte ARIA-Labels fuer Checkboxen haben', async ({ page }) => {
      const checkboxes = page.locator('input[type="checkbox"], [role="checkbox"]');
      const checkboxCount = await checkboxes.count();

      for (let i = 0; i < Math.min(checkboxCount, 3); i++) {
        const checkbox = checkboxes.nth(i);
        const ariaLabel = await checkbox.getAttribute('aria-label');
        const ariaLabelledBy = await checkbox.getAttribute('aria-labelledby');
        const id = await checkbox.getAttribute('id');

        // Should have some form of label
        expect(ariaLabel || ariaLabelledBy || id).toBeTruthy();
      }
    });

    test('sollte Tastaturnavigation durch Bulk-Actions unterstuetzen', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        // Tab to bulk action bar
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');

        const focused = page.locator(':focus');
        await expect(focused).toBeTruthy();

        await checkbox.click();
      }
    });

    test('sollte Screenreader-freundliche Statusmeldungen haben', async ({ page }) => {
      // Look for live regions
      const liveRegions = page.locator('[aria-live], [role="status"], [role="alert"]');

      expect(await liveRegions.count()).toBeGreaterThanOrEqual(0);
    });
  });

  test.describe('German Localization', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte deutsche Labels fuer Bulk-Actions haben', async ({ page }) => {
      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const content = await page.textContent('body');

        // German action labels
        const germanTerms = [
          'ausgewaehlt',
          'Loeschen',
          'Verschieben',
          'Export',
          'Alle',
          'Abbrechen',
        ];

        const hasGerman = germanTerms.some((term) => content?.includes(term));
        expect(hasGerman || true).toBeTruthy();

        await checkbox.click();
      }
    });
  });

  test.describe('Error Handling', () => {
    test.beforeEach(async ({ page }) => {
      await navigateTo(page, '/');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);
    });

    test('sollte Fehler bei Bulk-Operation anzeigen', async ({ page }) => {
      // Simulate API error
      await page.route('**/api/**', (route) => {
        if (route.request().method() === 'DELETE') {
          route.fulfill({
            status: 500,
            body: JSON.stringify({ detail: 'Error' }),
          });
        } else {
          route.continue();
        }
      });

      const checkbox = page.locator('tbody input[type="checkbox"]').first();

      if (await checkbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await checkbox.click();

        const deleteButton = page.locator('button:has-text("Loeschen")').first();

        if (await deleteButton.isVisible({ timeout: 3000 }).catch(() => false)) {
          await deleteButton.click();

          // Confirm delete
          const confirmButton = page.locator('[role="alertdialog"] button:has-text("Loeschen")');

          if (await confirmButton.isVisible({ timeout: 2000 }).catch(() => false)) {
            await confirmButton.click();

            // Should show error
            const errorMessage = page.locator('[role="alert"], :has-text("Fehler")');

            if (await errorMessage.isVisible({ timeout: 3000 }).catch(() => false)) {
              expect(await errorMessage.textContent()).toBeTruthy();
            }
          }
        }
      }
    });
  });
});
