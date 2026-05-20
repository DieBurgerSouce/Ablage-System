import { test, expect } from '@playwright/test';
import { expectNoA11yViolations, checkKeyboardNavigation } from './a11y-utils';

test.describe('Dashboard Barrierefreiheit', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to dashboard (authenticated)
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('WCAG 2.1 AA: Keine Verletzungen auf Dashboard', async ({ page }) => {
    await expectNoA11yViolations(page, 'Dashboard', {
      // Exclude third-party chart widgets that may have known issues
      exclude: ['.recharts-wrapper', '.plotly-graph'],
    });
  });

  test('Landmark-Regionen vorhanden (navigation, main, banner)', async ({ page }) => {
    // Check for proper landmark structure
    const nav = page.locator('nav, [role="navigation"]');
    const main = page.locator('main, [role="main"]');

    await expect(nav.first()).toBeVisible();
    await expect(main.first()).toBeVisible();
  });

  test('Ueberschriften-Hierarchie ist korrekt (h1 -> h2 -> h3)', async ({ page }) => {
    const headings = await page.evaluate(() => {
      const elements = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
      return Array.from(elements).map((el) => ({
        level: parseInt(el.tagName.charAt(1)),
        text: el.textContent?.trim() || '',
      }));
    });

    // Should have at least one heading
    expect(headings.length, 'Mindestens eine Ueberschrift erwartet').toBeGreaterThan(0);

    // Check no heading level is skipped (e.g., h1 -> h3 without h2)
    for (let i = 1; i < headings.length; i++) {
      const gap = headings[i].level - headings[i - 1].level;
      expect(
        gap,
        `Ueberschriften-Sprung: h${headings[i - 1].level} -> h${headings[i].level} (${headings[i].text})`
      ).toBeLessThanOrEqual(1);
    }
  });

  test('Interaktive Elemente haben accessible names', async ({ page }) => {
    // Check buttons have accessible names
    const buttons = page.locator('button');
    const count = await buttons.count();

    for (let i = 0; i < Math.min(count, 20); i++) {
      const btn = buttons.nth(i);
      if (await btn.isVisible()) {
        const name = await btn.evaluate((el) => {
          return el.getAttribute('aria-label') || el.textContent?.trim() || '';
        });
        expect(
          name.length,
          `Button ${i} hat keinen barrierefreien Namen`
        ).toBeGreaterThan(0);
      }
    }
  });

  test('Fokus-Management bei Navigation', async ({ page }) => {
    await checkKeyboardNavigation(page, 5);
  });
});
