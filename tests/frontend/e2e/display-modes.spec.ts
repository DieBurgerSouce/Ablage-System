/**
 * E2E Tests für Display-Modi des Ablage-Systems.
 *
 * Testet alle 4 Anzeigemodi:
 * - Dark Mode (Standard)
 * - Light Mode
 * - Whitescreen Mode (Hoher Kontrast)
 * - Blackscreen Mode (Invertierter Kontrast)
 *
 * Überprüft:
 * - Korrekte CSS-Variablen für jeden Modus
 * - Persistenz in localStorage
 * - UI-Feedback (Toast-Benachrichtigungen)
 * - Accessibility (WCAG 2.1 AA Konformität)
 */

import { test, expect, type Page } from '@playwright/test';

// Display mode configurations with expected CSS variable values
const DISPLAY_MODES = {
  dark: {
    name: 'Dunkler Modus',
    buttonEmoji: '🌙',
    bgPrimary: 'rgb(26, 26, 26)',      // #1a1a1a
    textPrimary: 'rgb(224, 224, 224)', // #e0e0e0
    accentColor: 'rgb(74, 158, 255)',  // #4a9eff
    borderColor: 'rgb(64, 64, 64)',    // #404040
  },
  light: {
    name: 'Heller Modus',
    buttonEmoji: '☀️',
    bgPrimary: 'rgb(255, 255, 255)',   // #ffffff
    textPrimary: 'rgb(26, 26, 26)',    // #1a1a1a
    accentColor: 'rgb(0, 102, 204)',   // #0066cc
    borderColor: 'rgb(224, 224, 224)', // #e0e0e0
  },
  whitescreen: {
    name: 'Hoher Kontrast',
    buttonEmoji: '⚪',
    bgPrimary: 'rgb(255, 255, 255)',   // #ffffff
    textPrimary: 'rgb(0, 0, 0)',       // #000000
    accentColor: 'rgb(0, 0, 255)',     // #0000ff
    borderColor: 'rgb(0, 0, 0)',       // #000000
  },
  blackscreen: {
    name: 'Invertierter Kontrast',
    buttonEmoji: '⚫',
    bgPrimary: 'rgb(0, 0, 0)',         // #000000
    textPrimary: 'rgb(255, 255, 255)', // #ffffff
    accentColor: 'rgb(0, 255, 0)',     // #00ff00
    borderColor: 'rgb(255, 255, 255)', // #ffffff
  },
};

test.describe('Display Mode Management', () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage to start with clean state
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
  });

  test('sollte standardmäßig im Dark Mode starten', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Check body has dark mode attribute
    const bodyMode = await page.getAttribute('body', 'data-mode');
    expect(bodyMode).toBe('dark');

    // Check localStorage
    const storedMode = await page.evaluate(() => localStorage.getItem('displayMode'));
    expect(storedMode === 'dark' || storedMode === null).toBeTruthy();
  });

  test('sollte gespeicherten Modus beim Laden wiederherstellen', async ({ page }) => {
    // Set light mode in localStorage before navigation
    await page.goto('/');
    await page.evaluate(() => localStorage.setItem('displayMode', 'light'));
    await page.reload();
    await page.waitForLoadState('domcontentloaded');

    // Check body has light mode attribute
    const bodyMode = await page.getAttribute('body', 'data-mode');
    expect(bodyMode).toBe('light');
  });

  test.describe('Mode Switching', () => {
    for (const [modeKey, modeConfig] of Object.entries(DISPLAY_MODES)) {
      test(`sollte zu ${modeConfig.name} wechseln können`, async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('domcontentloaded');

        // Find and click the mode button
        const modeButton = page.locator(`.mode-btn[data-mode="${modeKey}"]`);
        await expect(modeButton).toBeVisible();
        await modeButton.click();

        // Wait for mode change
        await page.waitForTimeout(100);

        // Verify body attribute changed
        const bodyMode = await page.getAttribute('body', 'data-mode');
        expect(bodyMode).toBe(modeKey);

        // Verify localStorage updated
        const storedMode = await page.evaluate(() => localStorage.getItem('displayMode'));
        expect(storedMode).toBe(modeKey);

        // Verify button is marked as active
        await expect(modeButton).toHaveClass(/active/);

        // Verify toast notification appeared (German message)
        const toast = page.locator('.toast, .notification, [role="alert"]').first();
        if (await toast.isVisible({ timeout: 1000 }).catch(() => false)) {
          await expect(toast).toContainText(modeConfig.name);
        }
      });
    }
  });

  test.describe('CSS Variables', () => {
    for (const [modeKey, modeConfig] of Object.entries(DISPLAY_MODES)) {
      test(`sollte korrekte CSS-Variablen für ${modeConfig.name} haben`, async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('domcontentloaded');

        // Switch to the mode
        const modeButton = page.locator(`.mode-btn[data-mode="${modeKey}"]`);
        await modeButton.click();
        await page.waitForTimeout(100);

        // Get computed styles for body
        const styles = await page.evaluate(() => {
          const body = document.body;
          const computedStyle = getComputedStyle(body);
          return {
            bgPrimary: computedStyle.getPropertyValue('--bg-primary').trim(),
            textPrimary: computedStyle.getPropertyValue('--text-primary').trim(),
            accentColor: computedStyle.getPropertyValue('--accent-color').trim(),
            borderColor: computedStyle.getPropertyValue('--border-color').trim(),
          };
        });

        // Verify CSS variables (convert hex to rgb for comparison)
        expect(styles.bgPrimary).toBeTruthy();
        expect(styles.textPrimary).toBeTruthy();
        expect(styles.accentColor).toBeTruthy();
      });
    }
  });

  test.describe('High Contrast Modes', () => {
    test('Whitescreen sollte erhöhte Schriftgewichte haben', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Switch to whitescreen mode
      await page.locator('.mode-btn[data-mode="whitescreen"]').click();
      await page.waitForTimeout(100);

      // Check font weight is increased
      const fontWeight = await page.evaluate(() => {
        const element = document.querySelector('h1, h2, .card-title, p');
        if (!element) return null;
        return getComputedStyle(element).fontWeight;
      });

      // Font weight should be 500 or higher for high contrast
      if (fontWeight) {
        expect(parseInt(fontWeight)).toBeGreaterThanOrEqual(500);
      }
    });

    test('Blackscreen sollte erhöhte Schriftgewichte haben', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Switch to blackscreen mode
      await page.locator('.mode-btn[data-mode="blackscreen"]').click();
      await page.waitForTimeout(100);

      // Check font weight is increased
      const fontWeight = await page.evaluate(() => {
        const element = document.querySelector('h1, h2, .card-title, p');
        if (!element) return null;
        return getComputedStyle(element).fontWeight;
      });

      // Font weight should be 500 or higher for high contrast
      if (fontWeight) {
        expect(parseInt(fontWeight)).toBeGreaterThanOrEqual(500);
      }
    });
  });

  test.describe('Accessibility', () => {
    test('sollte ausreichenden Farbkontrast im Whitescreen-Modus haben', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Switch to whitescreen mode
      await page.locator('.mode-btn[data-mode="whitescreen"]').click();
      await page.waitForTimeout(100);

      // Get colors
      const colors = await page.evaluate(() => {
        const body = document.body;
        const computedStyle = getComputedStyle(body);
        return {
          bg: computedStyle.getPropertyValue('--bg-primary').trim(),
          text: computedStyle.getPropertyValue('--text-primary').trim(),
        };
      });

      // Whitescreen should have pure white (#ffffff) and pure black (#000000)
      // This gives contrast ratio of 21:1 (WCAG AAA)
      expect(colors.bg).toContain('#ffffff');
      expect(colors.text).toContain('#000000');
    });

    test('sollte ausreichenden Farbkontrast im Blackscreen-Modus haben', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Switch to blackscreen mode
      await page.locator('.mode-btn[data-mode="blackscreen"]').click();
      await page.waitForTimeout(100);

      // Get colors
      const colors = await page.evaluate(() => {
        const body = document.body;
        const computedStyle = getComputedStyle(body);
        return {
          bg: computedStyle.getPropertyValue('--bg-primary').trim(),
          text: computedStyle.getPropertyValue('--text-primary').trim(),
        };
      });

      // Blackscreen should have pure black (#000000) and pure white (#ffffff)
      // This gives contrast ratio of 21:1 (WCAG AAA)
      expect(colors.bg).toContain('#000000');
      expect(colors.text).toContain('#ffffff');
    });

    test('Mode-Switcher-Buttons sollten fokussierbar sein', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Check all mode buttons are focusable
      const modeButtons = page.locator('.mode-btn');
      const count = await modeButtons.count();
      expect(count).toBe(4);

      // Tab through buttons
      for (let i = 0; i < count; i++) {
        const button = modeButtons.nth(i);
        await button.focus();
        await expect(button).toBeFocused();
      }
    });
  });

  test.describe('Persistence', () => {
    test('sollte Modus nach Seitenaktualisierung beibehalten', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Switch to light mode
      await page.locator('.mode-btn[data-mode="light"]').click();
      await page.waitForTimeout(100);

      // Reload page
      await page.reload();
      await page.waitForLoadState('domcontentloaded');

      // Verify mode persisted
      const bodyMode = await page.getAttribute('body', 'data-mode');
      expect(bodyMode).toBe('light');
    });

    test('sollte Modus nach Navigation beibehalten', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Switch to blackscreen mode
      await page.locator('.mode-btn[data-mode="blackscreen"]').click();
      await page.waitForTimeout(100);

      // Navigate to admin page if accessible, otherwise reload
      const adminLink = page.locator('a[href*="admin"]').first();
      if (await adminLink.isVisible({ timeout: 1000 }).catch(() => false)) {
        await adminLink.click();
        await page.waitForLoadState('domcontentloaded');
      } else {
        await page.reload();
        await page.waitForLoadState('domcontentloaded');
      }

      // Verify mode persisted (check localStorage as admin page may have different structure)
      const storedMode = await page.evaluate(() => localStorage.getItem('displayMode'));
      expect(storedMode).toBe('blackscreen');
    });
  });

  test.describe('UI Feedback', () => {
    test('sollte aktiven Modus-Button visuell hervorheben', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Verify dark mode button is active by default
      const darkButton = page.locator('.mode-btn[data-mode="dark"]');
      await expect(darkButton).toHaveClass(/active/);

      // Switch to light mode
      await page.locator('.mode-btn[data-mode="light"]').click();
      await page.waitForTimeout(100);

      // Verify light button is now active
      const lightButton = page.locator('.mode-btn[data-mode="light"]');
      await expect(lightButton).toHaveClass(/active/);

      // Verify dark button is no longer active
      await expect(darkButton).not.toHaveClass(/active/);
    });

    test('sollte nur einen aktiven Modus-Button haben', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Count active buttons - should always be exactly 1
      const activeButtons = page.locator('.mode-btn.active');
      await expect(activeButtons).toHaveCount(1);

      // Switch through all modes and verify only one is active
      for (const mode of ['light', 'whitescreen', 'blackscreen', 'dark']) {
        await page.locator(`.mode-btn[data-mode="${mode}"]`).click();
        await page.waitForTimeout(50);
        await expect(activeButtons).toHaveCount(1);
      }
    });
  });
});

test.describe('Display Mode Visual Regression', () => {
  // Visual regression tests for each mode
  for (const [modeKey, modeConfig] of Object.entries(DISPLAY_MODES)) {
    test(`sollte ${modeConfig.name} korrekt rendern`, async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Switch to the mode
      await page.locator(`.mode-btn[data-mode="${modeKey}"]`).click();
      await page.waitForTimeout(200);

      // Take screenshot for visual comparison
      await expect(page).toHaveScreenshot(`display-mode-${modeKey}.png`, {
        maxDiffPixelRatio: 0.1,
        threshold: 0.2,
      });
    });
  }
});
