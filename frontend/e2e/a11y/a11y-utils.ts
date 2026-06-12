/**
 * A11y Test Utilities - WCAG 2.1 AA Compliance Testing
 *
 * Wrapper fuer @axe-core/playwright mit deutschen Fehlermeldungen.
 */
import { Page, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

export interface A11yResult {
  violations: A11yViolation[];
  passes: number;
  incomplete: number;
}

export interface A11yViolation {
  id: string;
  impact: 'minor' | 'moderate' | 'serious' | 'critical';
  description: string;
  helpUrl: string;
  nodes: number;
  targets: string[];
}

/**
 * Wartet, bis die App-Shell steht und Lade-Skeletons verschwunden sind.
 *
 * Axe soll den fertig geladenen Zustand pruefen: Der Lade-Shimmer
 * (.animate-pulse-Skeletons, Platzhalter-Buttons) erzeugt transiente
 * button-name/color-contrast-Findings, die nach dem Laden nicht mehr
 * existieren (verifiziert 2026-06-12 auf /kunden).
 */
export async function waitForAppSettled(page: Page): Promise<void> {
  await page.locator('#main-content').waitFor({ state: 'attached', timeout: 15000 });
  await page
    .waitForFunction(() => document.querySelectorAll('.animate-pulse').length === 0, undefined, {
      timeout: 15000,
    })
    .catch(() => {
      /* Skeletons bleiben sichtbar -> trotzdem scannen, dann ist es ein echter Befund */
    });
  await page.waitForTimeout(500);
}

/**
 * Runs axe-core analysis with WCAG 2.1 AA ruleset.
 * Optionally excludes specific selectors (e.g. third-party widgets).
 */
export async function checkA11y(
  page: Page,
  options?: {
    exclude?: string[];
    include?: string[];
    disableRules?: string[];
  }
): Promise<A11yResult> {
  let builder = new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']);

  if (options?.exclude) {
    for (const selector of options.exclude) {
      builder = builder.exclude(selector);
    }
  }
  if (options?.include) {
    for (const selector of options.include) {
      builder = builder.include(selector);
    }
  }
  if (options?.disableRules) {
    builder = builder.disableRules(options.disableRules);
  }

  const results = await builder.analyze();

  return {
    violations: results.violations.map((v) => ({
      id: v.id,
      impact: v.impact as A11yViolation['impact'],
      description: v.description,
      helpUrl: v.helpUrl,
      nodes: v.nodes.length,
      targets: v.nodes.flatMap((n) => n.target.map(String)),
    })),
    passes: results.passes.length,
    incomplete: results.incomplete.length,
  };
}

/**
 * Asserts zero WCAG 2.1 AA violations.
 * Prints German-formatted error report on failure.
 */
export async function expectNoA11yViolations(
  page: Page,
  context: string,
  options?: {
    exclude?: string[];
    include?: string[];
    disableRules?: string[];
  }
): Promise<void> {
  const result = await checkA11y(page, options);

  if (result.violations.length > 0) {
    const report = formatViolationsReport(result.violations, context);
    expect(result.violations, report).toHaveLength(0);
  }
}

/**
 * Formats violations into a readable German report.
 */
function formatViolationsReport(violations: A11yViolation[], context: string): string {
  const lines: string[] = [
    `\n========================================`,
    `BARRIEREFREIHEIT-VERLETZUNGEN: ${context}`,
    `========================================`,
    `Gefundene Probleme: ${violations.length}`,
    ``,
  ];

  for (const v of violations) {
    const severity = {
      critical: 'KRITISCH',
      serious: 'SCHWERWIEGEND',
      moderate: 'MITTEL',
      minor: 'GERING',
    }[v.impact];

    lines.push(`[${severity}] ${v.id}`);
    lines.push(`  Beschreibung: ${v.description}`);
    lines.push(`  Betroffene Elemente: ${v.nodes}`);
    lines.push(`  Hilfe: ${v.helpUrl}`);
    if (v.targets.length > 0) {
      lines.push(`  Selektoren: ${v.targets.slice(0, 3).join(', ')}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Checks keyboard focus management.
 * Verifies that Tab navigation reaches all interactive elements.
 */
export async function checkKeyboardNavigation(
  page: Page,
  expectedFocusableCount: number
): Promise<void> {
  const focusable: string[] = [];

  for (let i = 0; i < expectedFocusableCount + 5; i++) {
    await page.keyboard.press('Tab');
    const activeTag = await page.evaluate(() => {
      const el = document.activeElement;
      return el ? `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}` : 'none';
    });
    focusable.push(activeTag);
    if (activeTag === 'body' || activeTag === 'none') break;
  }

  expect(
    focusable.filter((f) => f !== 'body' && f !== 'none').length,
    `Erwartete mindestens ${expectedFocusableCount} fokussierbare Elemente, gefunden: ${focusable.length}`
  ).toBeGreaterThanOrEqual(expectedFocusableCount);
}
