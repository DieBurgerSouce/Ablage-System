/**
 * Common Test Helpers for E2E Tests
 *
 * Provides reusable utility functions for Playwright tests.
 */

import { type Page, type Locator, expect } from '@playwright/test';

// ============================================================================
// Navigation Helpers
// ============================================================================

/**
 * Navigate to a page and wait for network idle
 */
export async function navigateTo(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
}

/**
 * Navigate and verify the page title contains expected text (German)
 */
export async function navigateAndVerifyTitle(
  page: Page,
  path: string,
  expectedTitleText: string
): Promise<void> {
  await navigateTo(page, path);
  const heading = page.locator('h1, h2').first();
  await expect(heading).toContainText(expectedTitleText, { timeout: 10000 });
}

// ============================================================================
// Dialog/Modal Helpers
// ============================================================================

/**
 * Close any visible welcome or intro dialogs
 */
export async function closeWelcomeDialog(page: Page): Promise<void> {
  const closeButton = page.getByRole('button', { name: /Schliessen|Close|Verstanden|OK/i });
  if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
    await closeButton.click();
    await page.waitForTimeout(200);
  }
}

/**
 * Confirm a dialog (OK, Bestaetigen, Ja, etc.)
 */
export async function confirmDialog(page: Page): Promise<void> {
  const confirmButton = page.getByRole('button', {
    name: /Bestaetigen|Ja|OK|Speichern|Weiter|Fortfahren/i,
  });
  await expect(confirmButton).toBeVisible();
  await confirmButton.click();
}

/**
 * Cancel a dialog (Abbrechen, Nein, etc.)
 */
export async function cancelDialog(page: Page): Promise<void> {
  const cancelButton = page.getByRole('button', { name: /Abbrechen|Nein|Zurueck/i });
  await expect(cancelButton).toBeVisible();
  await cancelButton.click();
}

/**
 * Wait for a dialog/modal to appear
 */
export async function waitForDialog(page: Page): Promise<Locator> {
  const dialog = page.locator(
    '[role="dialog"], [data-state="open"], .modal, [class*="Dialog"]'
  );
  await expect(dialog.first()).toBeVisible({ timeout: 5000 });
  return dialog.first();
}

// ============================================================================
// Tab Helpers
// ============================================================================

/**
 * Click on a tab by its label (German)
 */
export async function clickTab(page: Page, tabLabel: string): Promise<void> {
  const tab = page.locator(`[role="tab"]:has-text("${tabLabel}")`);
  await expect(tab).toBeVisible();
  await tab.click();
  await page.waitForTimeout(200);
}

/**
 * Verify a tab panel is visible
 */
export async function verifyTabPanelVisible(
  page: Page,
  tabValue: string
): Promise<void> {
  const tabPanel = page.locator(`[role="tabpanel"][data-state="active"]`);
  await expect(tabPanel).toBeVisible({ timeout: 5000 });
}

// ============================================================================
// Form Helpers
// ============================================================================

/**
 * Fill a form field by label (German labels)
 */
export async function fillField(
  page: Page,
  labelText: string,
  value: string
): Promise<void> {
  const field = page.locator(`input:near(:text("${labelText}")), textarea:near(:text("${labelText}"))`).first();
  await field.fill(value);
}

/**
 * Select an option from a dropdown by label
 */
export async function selectOption(
  page: Page,
  labelText: string,
  optionText: string
): Promise<void> {
  const select = page.locator(`[role="combobox"]:near(:text("${labelText}"))`).first();
  await select.click();
  await page.getByRole('option', { name: optionText }).click();
}

/**
 * Toggle a switch by label
 */
export async function toggleSwitch(
  page: Page,
  labelText: string,
  shouldBeChecked: boolean
): Promise<void> {
  const switchElement = page.locator(
    `[role="switch"]:near(:text("${labelText}")), button[role="switch"]:near(:text("${labelText}"))`
  ).first();

  const isCurrentlyChecked = await switchElement.getAttribute('aria-checked') === 'true';

  if (isCurrentlyChecked !== shouldBeChecked) {
    await switchElement.click();
  }
}

// ============================================================================
// Table Helpers
// ============================================================================

/**
 * Get table row count
 */
export async function getTableRowCount(page: Page, tableSelector?: string): Promise<number> {
  const table = tableSelector
    ? page.locator(tableSelector)
    : page.locator('table, [role="table"]').first();
  const rows = table.locator('tbody tr, [role="row"]');
  return rows.count();
}

/**
 * Click on a table row by text content
 */
export async function clickTableRow(page: Page, rowText: string): Promise<void> {
  const row = page.locator(`tr:has-text("${rowText}"), [role="row"]:has-text("${rowText}")`).first();
  await row.click();
}

/**
 * Sort table by column header
 */
export async function sortTableByColumn(
  page: Page,
  columnName: string
): Promise<void> {
  const header = page.locator(
    `th:has-text("${columnName}"), [role="columnheader"]:has-text("${columnName}")`
  ).first();
  await header.click();
  await page.waitForTimeout(300);
}

// ============================================================================
// Toast/Notification Helpers
// ============================================================================

/**
 * Wait for a toast notification with specific text
 */
export async function waitForToast(
  page: Page,
  expectedText: string | RegExp,
  timeout = 5000
): Promise<void> {
  const toast = page.locator(
    '[role="alert"], .toast, [data-sonner-toast], [class*="Toast"]'
  );
  await expect(toast.filter({ hasText: expectedText })).toBeVisible({ timeout });
}

/**
 * Verify success toast appeared
 */
export async function verifySuccessToast(page: Page, timeout = 5000): Promise<void> {
  const toast = page.locator(
    '[role="alert"], .toast, [data-sonner-toast]'
  ).first();
  await expect(toast).toBeVisible({ timeout });
}

/**
 * Verify error toast appeared
 */
export async function verifyErrorToast(page: Page, timeout = 5000): Promise<void> {
  const toast = page.locator(
    '[role="alert"][data-type="error"], .toast-error, [data-sonner-toast][data-type="error"]'
  ).first();
  await expect(toast).toBeVisible({ timeout });
}

// ============================================================================
// Loading State Helpers
// ============================================================================

/**
 * Wait for loading spinner to disappear
 */
export async function waitForLoadingComplete(
  page: Page,
  timeout = 30000
): Promise<void> {
  const loadingIndicator = page.locator(
    '[data-loading], .loading, .spinner, [class*="Skeleton"], [aria-busy="true"]'
  );

  // Wait for loading to appear (briefly)
  await page.waitForTimeout(100);

  // Wait for loading to disappear
  if (await loadingIndicator.first().isVisible({ timeout: 500 }).catch(() => false)) {
    await expect(loadingIndicator.first()).not.toBeVisible({ timeout });
  }
}

/**
 * Verify skeleton loading is complete
 */
export async function waitForSkeletonsToDisappear(
  page: Page,
  timeout = 10000
): Promise<void> {
  const skeletons = page.locator('[class*="Skeleton"], .skeleton');
  await expect(skeletons.first()).not.toBeVisible({ timeout });
}

// ============================================================================
// Accessibility Helpers
// ============================================================================

/**
 * Check for basic accessibility issues
 */
export async function checkBasicAccessibility(page: Page): Promise<{
  hasMainLandmark: boolean;
  hasHeading: boolean;
  imagesHaveAlt: boolean;
  buttonsHaveLabels: boolean;
}> {
  const hasMainLandmark = (await page.locator('main, [role="main"]').count()) > 0;
  const hasHeading = (await page.locator('h1').count()) > 0;

  // Check images have alt text
  const images = await page.locator('img').all();
  const imagesWithAlt = await Promise.all(
    images.map(async (img) => {
      const alt = await img.getAttribute('alt');
      return alt !== null;
    })
  );
  const imagesHaveAlt = imagesWithAlt.every(Boolean) || images.length === 0;

  // Check buttons have accessible names
  const buttons = await page.locator('button').all();
  const buttonsWithLabels = await Promise.all(
    buttons.map(async (btn) => {
      const text = await btn.textContent();
      const ariaLabel = await btn.getAttribute('aria-label');
      const title = await btn.getAttribute('title');
      return !!(text?.trim() || ariaLabel || title);
    })
  );
  const buttonsHaveLabels = buttonsWithLabels.every(Boolean) || buttons.length === 0;

  return { hasMainLandmark, hasHeading, imagesHaveAlt, buttonsHaveLabels };
}

/**
 * Verify element is keyboard focusable
 */
export async function verifyKeyboardFocusable(
  page: Page,
  selector: string
): Promise<void> {
  const element = page.locator(selector).first();
  await element.focus();
  await expect(element).toBeFocused();
}

// ============================================================================
// Keyboard Navigation Helpers
// ============================================================================

/**
 * Press keyboard shortcut
 */
export async function pressShortcut(
  page: Page,
  shortcut: string
): Promise<void> {
  // Handle shortcuts like 'ctrl+k', 'alt+h', etc.
  const keys = shortcut.toLowerCase().split('+');
  const modifiers: string[] = [];
  let key = '';

  for (const k of keys) {
    if (['ctrl', 'control', 'meta', 'alt', 'shift'].includes(k)) {
      modifiers.push(k === 'ctrl' ? 'Control' : k.charAt(0).toUpperCase() + k.slice(1));
    } else {
      key = k;
    }
  }

  await page.keyboard.press([...modifiers, key].join('+'));
}

/**
 * Press a key sequence (e.g., 'g' then 'd')
 */
export async function pressKeySequence(
  page: Page,
  sequence: string[]
): Promise<void> {
  for (const key of sequence) {
    await page.keyboard.press(key);
    await page.waitForTimeout(100);
  }
}

// ============================================================================
// Display Mode Helpers
// ============================================================================

/**
 * Get current display mode
 */
export async function getCurrentDisplayMode(page: Page): Promise<string | null> {
  return page.getAttribute('body', 'data-mode');
}

/**
 * Set display mode
 */
export async function setDisplayMode(
  page: Page,
  mode: 'dark' | 'light' | 'whitescreen' | 'blackscreen'
): Promise<void> {
  const modeButton = page.locator(`.mode-btn[data-mode="${mode}"]`);
  if (await modeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
    await modeButton.click();
    await page.waitForTimeout(200);
  }
}

// ============================================================================
// Scroll Helpers
// ============================================================================

/**
 * Scroll to bottom of page
 */
export async function scrollToBottom(page: Page): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(500);
}

/**
 * Scroll to element
 */
export async function scrollToElement(page: Page, selector: string): Promise<void> {
  const element = page.locator(selector).first();
  await element.scrollIntoViewIfNeeded();
}

// ============================================================================
// Date/Time Helpers
// ============================================================================

/**
 * Format date for German locale
 */
export function formatGermanDate(date: Date): string {
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

/**
 * Format currency for German locale
 */
export function formatGermanCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

// ============================================================================
// Screenshot Helpers
// ============================================================================

/**
 * Take screenshot with timestamp
 */
export async function takeTimestampedScreenshot(
  page: Page,
  name: string
): Promise<void> {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  await page.screenshot({
    path: `test-results/${name}_${timestamp}.png`,
    fullPage: true,
  });
}

// ============================================================================
// Wait Helpers
// ============================================================================

/**
 * Wait for API request to complete
 */
export async function waitForApiRequest(
  page: Page,
  urlPattern: string | RegExp,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH' = 'GET'
): Promise<void> {
  await page.waitForResponse(
    (response) =>
      (typeof urlPattern === 'string'
        ? response.url().includes(urlPattern)
        : urlPattern.test(response.url())) &&
      response.request().method() === method
  );
}

/**
 * Wait for element to be stable (no layout shifts)
 */
export async function waitForElementStable(
  page: Page,
  selector: string,
  timeout = 5000
): Promise<void> {
  const element = page.locator(selector).first();
  await expect(element).toBeVisible({ timeout });

  // Wait for layout stability
  let previousBox = await element.boundingBox();
  let stable = false;
  const startTime = Date.now();

  while (!stable && Date.now() - startTime < timeout) {
    await page.waitForTimeout(100);
    const currentBox = await element.boundingBox();

    if (
      previousBox &&
      currentBox &&
      previousBox.x === currentBox.x &&
      previousBox.y === currentBox.y &&
      previousBox.width === currentBox.width &&
      previousBox.height === currentBox.height
    ) {
      stable = true;
    }

    previousBox = currentBox;
  }
}
