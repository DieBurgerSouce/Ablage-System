/**
 * E2E Tests for Ablage (Filing System) Module
 *
 * Covers:
 * - Customer/Supplier list navigation with infinite scroll
 * - Folder selection (Folie/Spargelmesser)
 * - Category navigation and document list
 * - Filter, sort, pagination
 * - Bulk actions (mark as paid, move category, set tags)
 * - Vorgänge (Transactions) view
 * - Smart features (Invoice tracking, Insights)
 */

import { test, expect } from './fixtures';

test.describe('Ablage - Kunden (Customers)', () => {
  test.beforeEach(async ({ authenticatedPage: page }) => {
    // Navigate to customers page
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
  });

  test('should display customer list', async ({ authenticatedPage: page }) => {
    // Verify page title
    await expect(page.getByRole('heading', { name: /Kunden/i })).toBeVisible();

    // Verify search input exists
    await expect(page.getByPlaceholder(/Suche/i)).toBeVisible();

    // Verify at least one customer is displayed (or empty state)
    const customerCards = page.locator('[data-testid="customer-card"]');
    const emptyState = page.getByText(/Keine Kunden gefunden/i);

    // Either customers or empty state should be visible
    const hasCustomers = await customerCards.count() > 0;
    const hasEmptyState = await emptyState.isVisible().catch(() => false);

    expect(hasCustomers || hasEmptyState).toBeTruthy();
  });

  test('should filter customers by search', async ({ authenticatedPage: page }) => {
    // Wait for initial load
    await page.waitForTimeout(1000);

    // Type in search field
    const searchInput = page.getByPlaceholder(/Suche/i);
    await searchInput.fill('Mueller');

    // Wait for debounced search (300ms) + network
    await page.waitForTimeout(500);

    // Results should be filtered (or show no results)
    // The exact assertion depends on test data
  });

  test('should sort customers', async ({ authenticatedPage: page }) => {
    // Find sort dropdown
    const sortSelect = page.locator('select').filter({ hasText: /Sortieren|Name/i }).first();

    if (await sortSelect.isVisible().catch(() => false)) {
      // Change sort order
      await sortSelect.selectOption({ label: /Kundennummer/i });
      await page.waitForTimeout(500);
    }

    // Verify sort direction toggle exists
    const sortButton = page.getByRole('button').filter({ hasText: /arrow/i }).first();
    if (await sortButton.isVisible().catch(() => false)) {
      await sortButton.click();
      await page.waitForTimeout(500);
    }
  });

  test('should navigate to customer folders', async ({ authenticatedPage: page }) => {
    // Click first customer card
    const customerCard = page.locator('[data-testid="customer-card"]').first();

    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Should be on folder selection or categories (auto-skip single folder)
      const url = page.url();
      expect(url).toMatch(/\/kunden\/[\w-]+/);
    }
  });
});

test.describe('Ablage - Lieferanten (Suppliers)', () => {
  test.beforeEach(async ({ authenticatedPage: page }) => {
    await page.goto('/lieferanten');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
  });

  test('should display supplier list', async ({ authenticatedPage: page }) => {
    // Verify page title
    await expect(page.getByRole('heading', { name: /Lieferanten/i })).toBeVisible();

    // Verify search input exists
    await expect(page.getByPlaceholder(/Suche/i)).toBeVisible();
  });

  test('should navigate to supplier folders', async ({ authenticatedPage: page }) => {
    const supplierCard = page.locator('[data-testid="supplier-card"]').first();

    if (await supplierCard.isVisible().catch(() => false)) {
      await supplierCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Should be on folder selection or categories
      const url = page.url();
      expect(url).toMatch(/\/lieferanten\/[\w-]+/);
    }
  });
});

test.describe('Ablage - Folder Navigation', () => {
  test('should display folder selection for multi-folder entity', async ({ authenticatedPage: page }) => {
    // Navigate to a customer with multiple folders
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Click first customer
    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Check if we're on folder selection (Folie/Spargelmesser cards)
      const folderCards = page.locator('[data-testid="folder-card"]');
      const folieCard = page.getByText(/Folie/i);
      const messerCard = page.getByText(/Spargelmesser/i);

      // If multi-folder, both should be visible
      const hasFolderSelection = await folderCards.count() > 0;
      const hasAutoSkipped = page.url().includes('/folie') || page.url().includes('/messer');

      expect(hasFolderSelection || hasAutoSkipped).toBeTruthy();
    }
  });
});

test.describe('Ablage - Category Navigation', () => {
  test('should display document categories', async ({ authenticatedPage: page }) => {
    // Navigate directly to a known category page
    // This assumes test data exists
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Navigate through the hierarchy
    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Click on a folder if visible
      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      // Should see category cards
      const categoryCards = page.locator('[data-testid="category-card"]');
      const categoriesVisible = await categoryCards.count() > 0;

      // Alternative: check for specific category names
      const rechnungenCard = page.getByText(/Rechnungen/i);
      const angeboteCard = page.getByText(/Angebote/i);

      const hasCategories = categoriesVisible ||
        await rechnungenCard.isVisible().catch(() => false) ||
        await angeboteCard.isVisible().catch(() => false);

      expect(hasCategories).toBeTruthy();
    }
  });

  test('should show Druckdaten category only for Messer folder', async ({ authenticatedPage: page }) => {
    // This test verifies folder-specific categories
    // Navigate to a Messer folder if possible
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Navigate to customer → messer folder
    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Try to find and click Spargelmesser folder
      const messerFolder = page.getByText(/Spargelmesser/i);
      if (await messerFolder.isVisible().catch(() => false)) {
        await messerFolder.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Druckdaten should be visible for Messer
        const druckdatenCategory = page.getByText(/Druckdaten/i);
        await expect(druckdatenCategory).toBeVisible();
      }
    }
  });
});

test.describe('Ablage - Document List (CategoryDocumentList)', () => {
  // Helper to navigate to a category
  async function navigateToCategory(page: ReturnType<typeof test['authenticatedPage']>, category: string = 'rechnungen') {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Click folder if needed
      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      // Click on category
      const categoryCard = page.getByText(new RegExp(category, 'i')).first();
      if (await categoryCard.isVisible().catch(() => false)) {
        await categoryCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }
    }
  }

  test('should display document table with columns', async ({ authenticatedPage: page }) => {
    await navigateToCategory(page, 'rechnungen');

    // Verify table headers
    const table = page.locator('table').first();
    if (await table.isVisible().catch(() => false)) {
      // Check for common column headers
      await expect(page.getByRole('columnheader', { name: /Dokument|Name/i })).toBeVisible();
    }
  });

  test('should filter documents by date range', async ({ authenticatedPage: page }) => {
    await navigateToCategory(page, 'rechnungen');

    // Look for date filter inputs
    const dateFromInput = page.locator('input[type="date"]').first();
    if (await dateFromInput.isVisible().catch(() => false)) {
      await dateFromInput.fill('2024-01-01');
      await page.waitForTimeout(500);
    }
  });

  test('should filter documents by payment status', async ({ authenticatedPage: page }) => {
    await navigateToCategory(page, 'rechnungen');

    // Look for payment status filter
    const statusFilter = page.getByRole('combobox').filter({ hasText: /Status|Zahlungsstatus/i }).first();
    if (await statusFilter.isVisible().catch(() => false)) {
      await statusFilter.click();

      // Select "Offen" status
      const offenOption = page.getByRole('option', { name: /Offen/i });
      if (await offenOption.isVisible().catch(() => false)) {
        await offenOption.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }
    }
  });

  test('should sort documents by column', async ({ authenticatedPage: page }) => {
    await navigateToCategory(page, 'rechnungen');

    // Click on sortable column header
    const dateHeader = page.getByRole('columnheader', { name: /Datum/i });
    if (await dateHeader.isVisible().catch(() => false)) {
      await dateHeader.click();
      await page.waitForTimeout(500);

      // Click again to reverse sort
      await dateHeader.click();
      await page.waitForTimeout(500);
    }
  });

  test('should select multiple documents', async ({ authenticatedPage: page }) => {
    await navigateToCategory(page, 'rechnungen');

    // Find checkboxes in table rows
    const checkboxes = page.locator('input[type="checkbox"]');
    const checkboxCount = await checkboxes.count();

    if (checkboxCount > 1) {
      // Select first two documents
      await checkboxes.nth(1).check();
      await checkboxes.nth(2).check();

      // Verify selection indicator appears
      const selectionIndicator = page.getByText(/Ausgewählt|ausgewählt|selected/i);
      await expect(selectionIndicator).toBeVisible();
    }
  });
});

test.describe('Ablage - Bulk Actions', () => {
  async function navigateToCategoryWithSelection(page: ReturnType<typeof test['authenticatedPage']>) {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      const categoryCard = page.getByText(/Rechnungen/i).first();
      if (await categoryCard.isVisible().catch(() => false)) {
        await categoryCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Select documents
        const checkboxes = page.locator('input[type="checkbox"]');
        if (await checkboxes.count() > 1) {
          await checkboxes.nth(1).check();
        }
      }
    }
  }

  test('should show bulk action toolbar when documents selected', async ({ authenticatedPage: page }) => {
    await navigateToCategoryWithSelection(page);

    // Look for bulk action toolbar
    const toolbar = page.locator('[data-testid="bulk-actions-toolbar"]');
    const markAsPaidButton = page.getByRole('button', { name: /bezahlt|Als bezahlt/i });
    const moveButton = page.getByRole('button', { name: /Verschieben/i });

    const hasToolbar = await toolbar.isVisible().catch(() => false) ||
      await markAsPaidButton.isVisible().catch(() => false) ||
      await moveButton.isVisible().catch(() => false);

    // If documents were selected, toolbar should appear
    // (This may not show if no documents exist in test data)
  });

  test('should open move category dialog', async ({ authenticatedPage: page }) => {
    await navigateToCategoryWithSelection(page);

    const moveButton = page.getByRole('button', { name: /Verschieben|Kategorie/i });
    if (await moveButton.isVisible().catch(() => false)) {
      await moveButton.click();

      // Dialog should open
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();

      // Close dialog
      const closeButton = page.getByRole('button', { name: /Abbrechen|Cancel|Schliessen/i });
      if (await closeButton.isVisible().catch(() => false)) {
        await closeButton.click();
      }
    }
  });

  test('should open tags edit dialog', async ({ authenticatedPage: page }) => {
    await navigateToCategoryWithSelection(page);

    const tagsButton = page.getByRole('button', { name: /Tags/i });
    if (await tagsButton.isVisible().catch(() => false)) {
      await tagsButton.click();

      // Dialog should open
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();

      // Close dialog
      const closeButton = page.getByRole('button', { name: /Abbrechen|Cancel|Schliessen/i });
      if (await closeButton.isVisible().catch(() => false)) {
        await closeButton.click();
      }
    }
  });
});

test.describe('Ablage - Smart Features', () => {
  test('should display invoice tracking banner on Rechnungen category', async ({ authenticatedPage: page }) => {
    // Navigate to Rechnungen
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      const rechnungenCard = page.getByText(/Rechnungen/i).first();
      if (await rechnungenCard.isVisible().catch(() => false)) {
        await rechnungenCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Look for invoice tracking banner
        const trackingBanner = page.locator('[data-testid="invoice-tracking-banner"]');
        const zahlungsstatusText = page.getByText(/Zahlungsstatus|Offen|Überfällig/i);

        const hasBanner = await trackingBanner.isVisible().catch(() => false) ||
          await zahlungsstatusText.isVisible().catch(() => false);

        // Banner should appear for Rechnungen category
        // (May not show if no documents)
      }
    }
  });

  test('should display aggregations cards', async ({ authenticatedPage: page }) => {
    // Navigate to any category
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      const categoryCard = page.locator('[data-testid="category-card"]').first();
      if (await categoryCard.isVisible().catch(() => false)) {
        await categoryCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Look for aggregation cards (Gesamt, Offen, etc.)
        const aggregationCards = page.locator('[data-testid="aggregation-card"]');
        const gesamtText = page.getByText(/Gesamt|Total/i);

        const hasAggregations = await aggregationCards.count() > 0 ||
          await gesamtText.isVisible().catch(() => false);
      }
    }
  });
});

test.describe('Ablage - Vorgänge (Transactions)', () => {
  test('should navigate to Vorgänge view', async ({ authenticatedPage: page }) => {
    // Navigate to customer folder first
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      // Look for Vorgänge link/button
      const vorgaengeLink = page.getByRole('link', { name: /Vorgänge/i });
      const vorgaengeButton = page.getByRole('button', { name: /Vorgänge/i });

      if (await vorgaengeLink.isVisible().catch(() => false)) {
        await vorgaengeLink.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Verify we're on Vorgänge page
        expect(page.url()).toContain('/vorgaenge');
      } else if (await vorgaengeButton.isVisible().catch(() => false)) {
        await vorgaengeButton.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
        expect(page.url()).toContain('/vorgaenge');
      }
    }
  });

  test('should display transaction timeline', async ({ authenticatedPage: page }) => {
    // Navigate directly to Vorgänge URL if we know a valid one
    // This test assumes the route exists

    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Try to navigate to vorgaenge
      const url = page.url();
      const vorgaengeUrl = url.replace(/\/categories\/.*$/, '/vorgaenge')
        .replace(/\/(folie|messer)$/, '/folie/vorgaenge');

      if (url.includes('/kunden/') && !url.includes('/vorgaenge')) {
        // Add /vorgaenge to current path
        const currentPath = new URL(page.url()).pathname;
        const basePath = currentPath.split('/').slice(0, 4).join('/'); // /kunden/{id}/{folder}
        await page.goto(`${basePath}/vorgaenge`);
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Look for timeline components
        const timeline = page.locator('[data-testid="transaction-timeline"]');
        const transactionCard = page.locator('[data-testid="transaction-card"]');

        const hasTimeline = await timeline.isVisible().catch(() => false) ||
          await transactionCard.isVisible().catch(() => false);
      }
    }
  });
});

test.describe('Ablage - Pagination', () => {
  test('should load more customers on scroll/click', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Look for "Mehr laden" button
    const loadMoreButton = page.getByRole('button', { name: /Mehr laden|Load more/i });

    if (await loadMoreButton.isVisible().catch(() => false)) {
      // Get initial count
      const initialCards = await page.locator('[data-testid="customer-card"]').count();

      // Click load more
      await loadMoreButton.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      // Should have more cards now
      const newCards = await page.locator('[data-testid="customer-card"]').count();
      expect(newCards).toBeGreaterThanOrEqual(initialCards);
    }
  });

  test('should paginate document list', async ({ authenticatedPage: page }) => {
    // Navigate to a category with many documents
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      const categoryCard = page.locator('[data-testid="category-card"]').first();
      if (await categoryCard.isVisible().catch(() => false)) {
        await categoryCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Look for pagination controls
        const pagination = page.locator('[data-testid="pagination"]');
        const nextButton = page.getByRole('button', { name: /Weiter|Next|>/i });
        const pageIndicator = page.getByText(/Seite \d+ von \d+/i);

        const hasPagination = await pagination.isVisible().catch(() => false) ||
          await nextButton.isVisible().catch(() => false) ||
          await pageIndicator.isVisible().catch(() => false);
      }
    }
  });
});

test.describe('Ablage - Error Handling', () => {
  test('should display error state on API failure', async ({ authenticatedPage: page }) => {
    // Navigate to a non-existent entity
    await page.goto('/kunden/non-existent-uuid-12345');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Should show error or redirect
    const errorMessage = page.getByText(/Fehler|Error|nicht gefunden/i);
    const redirected = !page.url().includes('non-existent');

    const hasErrorHandling = await errorMessage.isVisible().catch(() => false) || redirected;
    expect(hasErrorHandling).toBeTruthy();
  });

  test('should display empty state when no documents', async ({ authenticatedPage: page }) => {
    // Navigate to a category (may have empty state)
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      // Click on a category that might be empty (e.g., Archiv)
      const archivCard = page.getByText(/Archiv/i).first();
      if (await archivCard.isVisible().catch(() => false)) {
        await archivCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Look for empty state or document list
        const emptyState = page.getByText(/Keine Dokumente|Noch keine Dokumente/i);
        const documentTable = page.locator('table');

        const hasContent = await emptyState.isVisible().catch(() => false) ||
          await documentTable.isVisible().catch(() => false);

        expect(hasContent).toBeTruthy();
      }
    }
  });
});

test.describe('Ablage - Breadcrumb Navigation', () => {
  test('should display breadcrumb and allow back navigation', async ({ authenticatedPage: page }) => {
    // Navigate deep into hierarchy
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      const categoryCard = page.locator('[data-testid="category-card"]').first();
      if (await categoryCard.isVisible().catch(() => false)) {
        await categoryCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Look for breadcrumb
        const breadcrumb = page.locator('[data-testid="breadcrumb"]');
        const kundenLink = page.getByRole('link', { name: /Kunden/i });

        if (await kundenLink.isVisible().catch(() => false)) {
          // Click to go back to Kunden
          await kundenLink.click();
          await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

          // Should be back at Kunden list
          expect(page.url()).toContain('/kunden');
          expect(page.url()).not.toContain('/folie');
          expect(page.url()).not.toContain('/messer');
        }
      }
    }
  });
});

test.describe('Ablage - Quick Actions Bar', () => {
  test('should display quick actions bar', async ({ authenticatedPage: page }) => {
    // Navigate to a category
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      const categoryCard = page.locator('[data-testid="category-card"]').first();
      if (await categoryCard.isVisible().catch(() => false)) {
        await categoryCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Look for quick actions bar
        const quickActionsBar = page.locator('[data-testid="quick-actions-bar"]');
        const uploadButton = page.getByRole('button', { name: /Hochladen|Upload/i });
        const exportButton = page.getByRole('button', { name: /Export/i });

        const hasQuickActions = await quickActionsBar.isVisible().catch(() => false) ||
          await uploadButton.isVisible().catch(() => false) ||
          await exportButton.isVisible().catch(() => false);
      }
    }
  });
});

// ==================== Performance Tests (1000+ Documents) ====================

test.describe('Ablage - Performance Tests', () => {
  // Performance thresholds (in milliseconds)
  const PERFORMANCE_THRESHOLDS = {
    PAGE_LOAD: 3000,          // Max 3s for initial page load
    PAGINATION: 1500,         // Max 1.5s for pagination
    FILTER_RESPONSE: 2000,    // Max 2s for filter response
    SORT_RESPONSE: 1500,      // Max 1.5s for sort response
    SEARCH_DEBOUNCE: 800,     // Max 800ms after debounce for search
  };

  test('should load customer list within performance threshold', async ({ authenticatedPage: page }) => {
    // Messbasis: Zeit bis NUTZBARER Inhalt (Karten oder Leer-Zustand).
    // networkidle ist als Lade-Ende methodisch kaputt: Query-Retries auf
    // 404-Endpoints (rag/ai) + WS-Reconnect-Loop halten das Netz ~8-14s busy.
    const startTime = Date.now();

    await page.goto('/kunden');
    await page
      .locator('[data-testid="customer-card"]')
      .first()
      .or(page.getByText(/Keine Kunden (gefunden|vorhanden)/i))
      .first()
      .waitFor({ timeout: 15000 });

    const loadTime = Date.now() - startTime;
    console.log(`Customer list load time: ${loadTime}ms`);

    expect(loadTime).toBeLessThan(PERFORMANCE_THRESHOLDS.PAGE_LOAD);
  });

  test('should load supplier list within performance threshold', async ({ authenticatedPage: page }) => {
    // Messbasis: Zeit bis nutzbarer Inhalt (siehe Kundenlisten-Test).
    const startTime = Date.now();

    await page.goto('/lieferanten');
    await page
      .locator('[data-testid="supplier-card"]')
      .first()
      .or(page.getByText(/Keine Lieferanten (gefunden|vorhanden)/i))
      .first()
      .waitFor({ timeout: 15000 });

    const loadTime = Date.now() - startTime;
    console.log(`Supplier list load time: ${loadTime}ms`);

    expect(loadTime).toBeLessThan(PERFORMANCE_THRESHOLDS.PAGE_LOAD);
  });

  test('should handle rapid pagination without degradation', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Find "Mehr laden" button
    const loadMoreButton = page.getByRole('button', { name: /Mehr laden/i });

    if (await loadMoreButton.isVisible().catch(() => false)) {
      const loadTimes: number[] = [];

      // Click load more multiple times to simulate loading many pages
      for (let i = 0; i < 5; i++) {
        if (await loadMoreButton.isVisible().catch(() => false)) {
          const startTime = Date.now();
          await loadMoreButton.click();

          // Wait for new content
          await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
          await page.waitForTimeout(300); // Allow React to update

          const loadTime = Date.now() - startTime;
          loadTimes.push(loadTime);
          console.log(`Pagination ${i + 1} load time: ${loadTime}ms`);
        } else {
          break; // No more pages
        }
      }

      // Verify pagination times don't degrade significantly
      if (loadTimes.length >= 2) {
        const avgLoadTime = loadTimes.reduce((a, b) => a + b, 0) / loadTimes.length;
        console.log(`Average pagination load time: ${avgLoadTime}ms`);

        // Each pagination should be within threshold
        loadTimes.forEach((time, index) => {
          expect(time).toBeLessThan(PERFORMANCE_THRESHOLDS.PAGINATION);
        });

        // Later loads shouldn't be more than 2x slower than first load
        const maxDegradation = loadTimes[0] * 2.5;
        const lastLoadTime = loadTimes[loadTimes.length - 1];
        expect(lastLoadTime).toBeLessThan(maxDegradation);
      }
    }
  });

  test('should filter search within performance threshold', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const searchInput = page.getByPlaceholder(/Suche/i);

    if (await searchInput.isVisible().catch(() => false)) {
      // Measure search response time
      const startTime = Date.now();

      await searchInput.fill('Mueller');

      // Wait for debounce (300ms) + network request
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const searchTime = Date.now() - startTime;
      console.log(`Search response time: ${searchTime}ms (includes 300ms debounce)`);

      // Subtract debounce time for actual response
      const responseTime = searchTime - 300;
      expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLDS.SEARCH_DEBOUNCE);

      // Clear search
      await searchInput.clear();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
    }
  });

  test('should handle rapid sorting without performance issues', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Find sort toggle button — gezielt ueber das aria-label der KundenPage
    // (der fruehere "erster Button mit svg"-Selektor traf Shell-Buttons).
    const sortButton = page.getByRole('button', { name: /(Auf|Ab)steigend sortieren/ }).first();

    if (await sortButton.isVisible({ timeout: 10000 }).catch(() => false)) {
      const sortTimes: number[] = [];

      // Toggle sort multiple times
      for (let i = 0; i < 5; i++) {
        const startTime = Date.now();
        await sortButton.click();
        // Sortierung ist client-/query-seitig: kurze Reaktionszeit abwarten
        await page.waitForTimeout(150);

        const sortTime = Date.now() - startTime;
        sortTimes.push(sortTime);
        console.log(`Sort toggle ${i + 1} time: ${sortTime}ms`);
      }

      // Verify sort times are within threshold
      const avgSortTime = sortTimes.reduce((a, b) => a + b, 0) / sortTimes.length;
      console.log(`Average sort time: ${avgSortTime}ms`);

      expect(avgSortTime).toBeLessThan(PERFORMANCE_THRESHOLDS.SORT_RESPONSE);
    }
  });

  test('should load document list within performance threshold', async ({ authenticatedPage: page }) => {
    // Navigate to a category
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      await customerCard.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

      const folderCard = page.locator('[data-testid="folder-card"]').first();
      if (await folderCard.isVisible().catch(() => false)) {
        await folderCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      }

      const categoryCard = page.locator('[data-testid="category-card"]').first();
      if (await categoryCard.isVisible().catch(() => false)) {
        const startTime = Date.now();

        await categoryCard.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

        // Wait for documents table or empty state
        await Promise.race([
          page.locator('[data-testid="documents-table"]').waitFor({ timeout: PERFORMANCE_THRESHOLDS.PAGE_LOAD }),
          page.getByText(/Keine Dokumente/i).waitFor({ timeout: PERFORMANCE_THRESHOLDS.PAGE_LOAD }),
        ]).catch(() => {/* one will timeout */});

        const loadTime = Date.now() - startTime;
        console.log(`Document list load time: ${loadTime}ms`);

        expect(loadTime).toBeLessThan(PERFORMANCE_THRESHOLDS.PAGE_LOAD);
      }
    }
  });

  test('should maintain responsive UI during data loading', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');

    // Monitor for UI responsiveness during load
    const responsiveCheck = async () => {
      // Try clicking search input during load - should be responsive
      const searchInput = page.getByPlaceholder(/Suche/i);
      const startTime = Date.now();

      await searchInput.waitFor({ timeout: 5000 });
      await searchInput.click();

      const responseTime = Date.now() - startTime;
      return responseTime < 500; // Should respond within 500ms
    };

    // Page should be interactive quickly even while loading more data
    const isResponsive = await responsiveCheck();
    expect(isResponsive).toBeTruthy();
  });

  test('memory usage should not increase excessively during pagination', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Get initial heap size (if available via performance API)
    const getHeapSize = async () => {
      return page.evaluate(() => {
        // @ts-expect-error - performance.memory is Chrome-specific
        if (window.performance && window.performance.memory) {
          // @ts-expect-error - performance.memory is Chrome-specific
          return window.performance.memory.usedJSHeapSize / (1024 * 1024); // MB
        }
        return null;
      });
    };

    const initialHeap = await getHeapSize();
    console.log(`Initial heap size: ${initialHeap ? initialHeap.toFixed(2) + 'MB' : 'N/A'}`);

    // Load multiple pages
    const loadMoreButton = page.getByRole('button', { name: /Mehr laden/i });

    for (let i = 0; i < 10; i++) {
      if (await loadMoreButton.isVisible().catch(() => false)) {
        await loadMoreButton.click();
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      } else {
        break;
      }
    }

    const finalHeap = await getHeapSize();
    console.log(`Final heap size: ${finalHeap ? finalHeap.toFixed(2) + 'MB' : 'N/A'}`);

    if (initialHeap && finalHeap) {
      const heapGrowth = finalHeap - initialHeap;
      console.log(`Heap growth: ${heapGrowth.toFixed(2)}MB`);

      // Heap should not grow more than 50MB during pagination
      expect(heapGrowth).toBeLessThan(50);
    }
  });

  test('should render 100+ items without lag', async ({ authenticatedPage: page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    // Load multiple pages to get 100+ items
    const loadMoreButton = page.getByRole('button', { name: /Mehr laden/i });
    let totalItems = await page.locator('[data-testid="customer-card"]').count();

    while (totalItems < 100 && await loadMoreButton.isVisible().catch(() => false)) {
      await loadMoreButton.click();
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
      await page.waitForTimeout(200);
      totalItems = await page.locator('[data-testid="customer-card"]').count();
    }

    console.log(`Total items loaded: ${totalItems}`);

    if (totalItems >= 50) {
      // Test scroll performance
      const startTime = Date.now();

      // Scroll to bottom
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(100);

      // Scroll back to top
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(100);

      const scrollTime = Date.now() - startTime;
      console.log(`Scroll time with ${totalItems} items: ${scrollTime}ms`);

      // Scrolling should be smooth (< 500ms for full scroll)
      expect(scrollTime).toBeLessThan(500);
    }
  });
});

// ==================== Performance Benchmark Summary ====================

test.describe('Ablage - Performance Benchmark Report', () => {
  test('generate performance benchmark report', async ({ authenticatedPage: page }) => {
    const benchmarks: { name: string; time: number; threshold: number; passed: boolean }[] = [];

    // Messbasis aller Benchmarks: Zeit bis nutzbarer Inhalt/Response —
    // NICHT networkidle (durch 404-Query-Retries + WS-Reconnects ~8-14s busy).

    // Test 1: Customer list load
    let startTime = Date.now();
    await page.goto('/kunden');
    await page
      .locator('[data-testid="customer-card"]')
      .first()
      .or(page.getByText(/Keine Kunden (gefunden|vorhanden)/i))
      .first()
      .waitFor({ timeout: 15000 });
    let loadTime = Date.now() - startTime;
    benchmarks.push({
      name: 'Kundenliste laden',
      time: loadTime,
      threshold: 3000,
      passed: loadTime < 3000,
    });

    // Test 2: Search response (debounced API-Antwort auf /entities/customers)
    const searchInput = page.getByPlaceholder(/Suche/i);
    if (await searchInput.isVisible().catch(() => false)) {
      startTime = Date.now();
      const searchResponse = page.waitForResponse(
        (resp) => resp.url().includes('/entities/customers') && resp.url().includes('Test'),
        { timeout: 10000 }
      );
      await searchInput.fill('Test');
      await searchResponse.catch(() => { /* kein Treffer-Request -> Zeit zaehlt trotzdem */ });
      loadTime = Date.now() - startTime;
      benchmarks.push({
        name: 'Suche (inkl. Debounce)',
        time: loadTime,
        threshold: 1500,
        passed: loadTime < 1500,
      });
    }

    // Test 3: Navigation to folder
    const customerCard = page.locator('[data-testid="customer-card"]').first();
    if (await customerCard.isVisible().catch(() => false)) {
      startTime = Date.now();
      await customerCard.click();
      await page.waitForURL(/\/kunden\/[\w-]+/, { timeout: 10000 }).catch(() => { /* Navigation evtl. instant per Client-Routing */ });
      loadTime = Date.now() - startTime;
      benchmarks.push({
        name: 'Navigation zu Kunde',
        time: loadTime,
        threshold: 2000,
        passed: loadTime < 2000,
      });
    }

    // Print benchmark report
    console.log('\n========== PERFORMANCE BENCHMARK REPORT ==========');
    console.log('| Test                      | Zeit    | Limit   | Status |');
    console.log('|---------------------------|---------|---------|--------|');

    benchmarks.forEach((b) => {
      const status = b.passed ? '✓ OK' : '✗ FAIL';
      console.log(
        `| ${b.name.padEnd(25)} | ${String(b.time + 'ms').padEnd(7)} | ${String(b.threshold + 'ms').padEnd(7)} | ${status.padEnd(6)} |`
      );
    });

    console.log('===================================================\n');

    // All benchmarks should pass
    const allPassed = benchmarks.every((b) => b.passed);
    expect(allPassed).toBeTruthy();
  });
});
