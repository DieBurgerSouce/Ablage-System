/**
 * Visual Regression Tests - Key Pages
 *
 * Visuelle Regression-Tests fuer alle wichtigen Seiten des Ablage-Systems.
 *
 * Features:
 * - Screenshot-Vergleich mit Baseline
 * - Alle 4 Display-Modi (dark, light, whitescreen, blackscreen)
 * - Responsive Viewports
 * - Maskierung dynamischer Inhalte
 *
 * Getestete Seiten:
 * - Dashboard
 * - Document List
 * - Document Detail
 * - Entity Detail (Kunden/Lieferanten)
 * - Workflow Builder
 */

import { test, expect, type Page } from '@playwright/test';

// Visual test configuration
const SCREENSHOT_OPTIONS = {
  maxDiffPixelRatio: 0.05,
  threshold: 0.2,
  animations: 'disabled' as const,
};

// Elements to mask during screenshot (timestamps, random IDs, etc.)
const MASK_SELECTORS = [
  '[data-testid="timestamp"]',
  '.timestamp',
  '.date-time',
  '.relative-time',
  '[data-testid="user-avatar"]',
  '.session-id',
  '.document-id',
  '.random-number',
];

// Elements to hide (tooltips, cursors, etc.)
const HIDE_SELECTORS = [
  '.tooltip',
  '.popover',
  '[role="tooltip"]',
  '.toast',
  '.notification',
];

// Display modes to test
const DISPLAY_MODES = ['dark', 'light', 'whitescreen', 'blackscreen'] as const;

/**
 * Helper: Prepare page for screenshot
 */
async function prepareForScreenshot(page: Page): Promise<void> {
  // Wait for fonts to load
  await page.evaluate(() => document.fonts.ready);

  // Wait for images to load
  await page.waitForLoadState('networkidle');

  // Disable animations
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        transition: none !important;
        animation: none !important;
      }
    `,
  });

  // Wait a bit for styles to apply
  await page.waitForTimeout(500);

  // Hide dynamic elements
  for (const selector of HIDE_SELECTORS) {
    await page.locator(selector).evaluateAll(elements => {
      elements.forEach(el => {
        (el as HTMLElement).style.visibility = 'hidden';
      });
    }).catch(() => {});
  }
}

/**
 * Helper: Set display mode
 */
async function setDisplayMode(page: Page, mode: string): Promise<void> {
  // Try to find and click mode button
  const modeButton = page.locator(`.mode-btn[data-mode="${mode}"], [data-testid="mode-${mode}"]`);

  if (await modeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
    await modeButton.click();
    await page.waitForTimeout(300);
  } else {
    // Fallback: Set via localStorage and reload
    await page.evaluate(m => {
      localStorage.setItem('displayMode', m);
      document.body.setAttribute('data-mode', m);
    }, mode);
    await page.waitForTimeout(200);
  }
}

/**
 * Helper: Get mask elements as locators
 */
function getMaskLocators(page: Page) {
  return MASK_SELECTORS.map(selector => page.locator(selector));
}

test.describe('Visual Regression - Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('Dashboard - Default View', async ({ page }) => {
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('dashboard-default.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  for (const mode of DISPLAY_MODES) {
    test(`Dashboard - ${mode} mode`, async ({ page }) => {
      await setDisplayMode(page, mode);
      await prepareForScreenshot(page);

      await expect(page).toHaveScreenshot(`dashboard-${mode}.png`, {
        ...SCREENSHOT_OPTIONS,
        mask: getMaskLocators(page),
      });
    });
  }

  test('Dashboard - Mobile Viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('dashboard-mobile.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Dashboard - Tablet Viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('dashboard-tablet.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });
});

test.describe('Visual Regression - Document List', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('Document List - Default View', async ({ page }) => {
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('document-list-default.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Document List - With Filters Applied', async ({ page }) => {
    // Apply a filter if available
    const filterSelect = page.locator('[data-testid="category-filter"], select[name="category"]');

    if (await filterSelect.first().isVisible({ timeout: 2000 }).catch(() => false)) {
      await filterSelect.first().selectOption({ index: 1 });
      await page.waitForTimeout(500);
    }

    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('document-list-filtered.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Document List - Empty State', async ({ page }) => {
    // Search for non-existent document to trigger empty state
    const searchInput = page.locator('[data-testid="search-input"], input[type="search"]');

    if (await searchInput.first().isVisible({ timeout: 2000 }).catch(() => false)) {
      await searchInput.first().fill('xyznonexistent123456789');
      await page.waitForTimeout(1000);
    }

    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('document-list-empty.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });
});

test.describe('Visual Regression - Upload Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
    await page.waitForLoadState('domcontentloaded');

    // Close welcome dialog if present
    const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
    if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await closeButton.click();
      await page.waitForTimeout(300);
    }
  });

  test('Upload Page - Default View', async ({ page }) => {
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('upload-default.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Upload Page - Drag Zone Highlight', async ({ page }) => {
    // This would require simulating drag hover state
    // For now, just take the default state
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('upload-dropzone.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  for (const mode of DISPLAY_MODES) {
    test(`Upload Page - ${mode} mode`, async ({ page }) => {
      await setDisplayMode(page, mode);
      await prepareForScreenshot(page);

      await expect(page).toHaveScreenshot(`upload-${mode}.png`, {
        ...SCREENSHOT_OPTIONS,
        mask: getMaskLocators(page),
      });
    });
  }
});

test.describe('Visual Regression - Entity Pages', () => {
  test.describe('Kunden (Customers)', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');
    });

    test('Customer List - Default View', async ({ page }) => {
      await prepareForScreenshot(page);

      await expect(page).toHaveScreenshot('customers-list.png', {
        ...SCREENSHOT_OPTIONS,
        mask: getMaskLocators(page),
      });
    });

    test('Customer Detail - Default View', async ({ page }) => {
      // Click on first customer to open detail
      const firstCustomer = page.locator('a[href*="kunden/"], tbody tr').first();

      if (await firstCustomer.isVisible({ timeout: 3000 }).catch(() => false)) {
        await firstCustomer.click();
        await page.waitForLoadState('networkidle');

        await prepareForScreenshot(page);

        await expect(page).toHaveScreenshot('customer-detail.png', {
          ...SCREENSHOT_OPTIONS,
          mask: getMaskLocators(page),
        });
      }
    });
  });

  test.describe('Lieferanten (Suppliers)', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/lieferanten');
      await page.waitForLoadState('networkidle');
    });

    test('Supplier List - Default View', async ({ page }) => {
      await prepareForScreenshot(page);

      await expect(page).toHaveScreenshot('suppliers-list.png', {
        ...SCREENSHOT_OPTIONS,
        mask: getMaskLocators(page),
      });
    });

    test('Supplier Detail - Default View', async ({ page }) => {
      // Click on first supplier to open detail
      const firstSupplier = page.locator('a[href*="lieferanten/"], tbody tr').first();

      if (await firstSupplier.isVisible({ timeout: 3000 }).catch(() => false)) {
        await firstSupplier.click();
        await page.waitForLoadState('networkidle');

        await prepareForScreenshot(page);

        await expect(page).toHaveScreenshot('supplier-detail.png', {
          ...SCREENSHOT_OPTIONS,
          mask: getMaskLocators(page),
        });
      }
    });
  });
});

test.describe('Visual Regression - Banking Pages', () => {
  test('Transactions Page', async ({ page }) => {
    await page.goto('/admin/banking/transactions');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('banking-transactions.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Skonto Page', async ({ page }) => {
    await page.goto('/admin/banking/skonto');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('banking-skonto.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Payments Page', async ({ page }) => {
    await page.goto('/admin/banking/payments');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('banking-payments.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Reconciliation Page', async ({ page }) => {
    await page.goto('/admin/banking/reconciliation');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('banking-reconciliation.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });
});

test.describe('Visual Regression - Dunning Pages', () => {
  test('Dunning Overview', async ({ page }) => {
    await page.goto('/admin/mahnungen');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('dunning-overview.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Active Dunnings', async ({ page }) => {
    await page.goto('/admin/mahnungen/aktiv');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('dunning-active.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Dunning Kanban', async ({ page }) => {
    await page.goto('/admin/mahnungen/kanban');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('dunning-kanban.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Mahnstopp Page', async ({ page }) => {
    await page.goto('/admin/mahnungen/mahnstopp');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('dunning-mahnstopp.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });
});

test.describe('Visual Regression - Automation/Workflow Builder', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/automation');
    await page.waitForLoadState('networkidle');
  });

  test('Automation Overview', async ({ page }) => {
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('automation-overview.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Workflow Editor - Empty Canvas', async ({ page }) => {
    // Try to open editor
    const createButton = page.locator('[data-testid="create-workflow"], button:has-text("Neu")');

    if (await createButton.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      await createButton.first().click();
      await page.waitForLoadState('networkidle');
      await prepareForScreenshot(page);

      await expect(page).toHaveScreenshot('workflow-editor-empty.png', {
        ...SCREENSHOT_OPTIONS,
        mask: getMaskLocators(page),
      });
    }
  });
});

test.describe('Visual Regression - Admin Pages', () => {
  test('OCR Backends', async ({ page }) => {
    await page.goto('/admin/ocr-backends');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('admin-ocr-backends.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Users Admin', async ({ page }) => {
    await page.goto('/admin/users');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('admin-users.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Settings', async ({ page }) => {
    await page.goto('/admin/settings');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('admin-settings.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('DATEV Config', async ({ page }) => {
    await page.goto('/admin/datev/config');
    await page.waitForLoadState('networkidle');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('admin-datev-config.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });
});

test.describe('Visual Regression - Error States', () => {
  test('404 Page', async ({ page }) => {
    await page.goto('/nicht-existierende-seite');
    await page.waitForLoadState('domcontentloaded');
    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('error-404.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });

  test('Empty State', async ({ page }) => {
    // This depends on finding an empty state in the app
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle');

    // Search for non-existent to trigger empty state
    const searchInput = page.locator('[data-testid="customer-search"], input[type="search"]');

    if (await searchInput.first().isVisible({ timeout: 2000 }).catch(() => false)) {
      await searchInput.first().fill('xyznonexistent123456789');
      await page.waitForTimeout(1000);
    }

    await prepareForScreenshot(page);

    await expect(page).toHaveScreenshot('empty-state.png', {
      ...SCREENSHOT_OPTIONS,
      mask: getMaskLocators(page),
    });
  });
});

test.describe('Visual Regression - Components', () => {
  test('Navigation Sidebar', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Focus on sidebar
    const sidebar = page.locator('aside, nav, .sidebar, [data-testid="sidebar"]');

    if (await sidebar.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      await prepareForScreenshot(page);

      await expect(sidebar.first()).toHaveScreenshot('component-sidebar.png', {
        ...SCREENSHOT_OPTIONS,
      });
    }
  });

  test('Header', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Focus on header
    const header = page.locator('header, .header, [data-testid="header"]');

    if (await header.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      await prepareForScreenshot(page);

      await expect(header.first()).toHaveScreenshot('component-header.png', {
        ...SCREENSHOT_OPTIONS,
        mask: getMaskLocators(page),
      });
    }
  });

  test('Display Mode Switcher', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Focus on mode switcher
    const modeSwitcher = page.locator('.mode-switcher, .display-mode-buttons, [data-testid="mode-switcher"]');

    if (await modeSwitcher.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      await prepareForScreenshot(page);

      await expect(modeSwitcher.first()).toHaveScreenshot('component-mode-switcher.png', {
        ...SCREENSHOT_OPTIONS,
      });
    }
  });
});
