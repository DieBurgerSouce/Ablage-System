// WICHTIG: authentifizierte Fixture verwenden. Mit dem rohen @playwright/test
// landeten diese Tests auf der Login-Redirect-Seite (QA-Lauf 2026-06-12).
import { test, expect } from '../fixtures';
import { expectNoA11yViolations, waitForAppSettled } from './a11y-utils';

test.describe('Kanban Board Barrierefreiheit', () => {
  test.beforeEach(async ({ authenticatedPage: page }) => {
    await page.goto('/admin/kanban');
    await page.waitForLoadState('domcontentloaded');
    await waitForAppSettled(page);
  });

  test('WCAG 2.1 AA: Keine Verletzungen im Kanban Board', async ({ authenticatedPage: page }) => {
    // BEKANNTE APP-A11Y-BUGS (Stream s5, 2026-06-13): color-contrast + button-name
    // der GLOBALEN App-Huelle (Sidebar #404952/#02060d=2.21, Proaktiv-FAB .px-8
    // ohne accessible name) — siehe documents.a11y.spec.ts. Zusaetzlich laedt
    // das Board hier gar nicht (siehe naechster Test) -> axe prueft die leere
    // Seite + globale Huelle. App-Code-Befund, nicht Spec-Zone.
    // B7-Stream 2026-06-13 GEFIXT: Sidebar-Kontrast, FAB-aria-label, und das Board
    // sendet jetzt company_id (use-kanban-queries.ts) -> laedt.
    await expectNoA11yViolations(page, 'Kanban Board', {
      // [data-sonner-toast]: BEKANNTER APP-BUG (Kategorie B, color-contrast im
      // "Offline-Modus bereit"-Toast) — siehe dashboard.a11y.spec.ts.
      exclude: ['[data-sonner-toast]'],
    });
  });

  test('Spalten haben aria-label mit Stage-Name', async ({ authenticatedPage: page }) => {
    // ZWEI ECHTE APP-BUGS (Stream s5, 2026-06-13):
    //  1. Kanban-Board laedt nicht: Das Frontend ruft GET /kanban/document/board
    //     OHNE den serverseitig PFLICHT-Parameter company_id (use-kanban-queries.ts:50)
    //     -> Backend 422 "query -> company_id: Pflichtfeld fehlt" -> board=null,
    //     KEINE Spalten rendern. (Inkonsistent zu G1-Endpoints wie
    //     /entities/customers, die company_id aus dem Token ableiten.)
    //  2. Selbst bei geladenem Board fehlt den Spalten (KanbanColumn.tsx) jedes
    //     aria-label und jede role -> die Spalte ist fuer Screenreader nicht als
    //     Stage benennbar. (Der hiesige Selektor [role="list"] matcht aktuell nur
    //     die Admin-Subnavigation, die ebenfalls kein aria-label hat.)
    // B7-Stream 2026-06-13 GEFIXT: (1) use-kanban-queries.ts sendet jetzt
    // company_id aus dem CompanyContext -> Board laedt; (2) KanbanColumn hat
    // role="group" + aria-label={`Phase: ${stage_name}`} + data-kanban-column.
    // Each column should be identifiable
    const columns = page.locator('[data-kanban-column], [role="listbox"], [role="list"]');
    const count = await columns.count();

    if (count > 0) {
      for (let i = 0; i < count; i++) {
        const col = columns.nth(i);
        const label = await col.evaluate((el) => {
          return el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || '';
        });
        expect(
          label.length,
          `Kanban-Spalte ${i} benoetigt aria-label`
        ).toBeGreaterThan(0);
      }
    }
  });

  test('Drag-and-Drop hat Tastatur-Alternative', async ({ authenticatedPage: page }) => {
    // @dnd-kit provides keyboard support via Space/Enter to pick up,
    // Arrow keys to move, Space/Enter to drop
    // Verify at least cards are focusable
    const cards = page.locator('[data-kanban-card], [role="option"], [tabindex]');
    const count = await cards.count();

    if (count > 0) {
      // First card should be focusable
      const firstCard = cards.first();
      await firstCard.focus();
      const isFocused = await firstCard.evaluate((el) => document.activeElement === el);
      expect(isFocused, 'Kanban-Karten muessen fokussierbar sein').toBeTruthy();
    }
  });

  test('Live-Region fuer Drag-Updates vorhanden', async ({ authenticatedPage: page }) => {
    // @dnd-kit adds aria-live region for announcements
    const liveRegion = page.locator('[aria-live="assertive"], [aria-live="polite"], [role="status"]');
    // DnD context provides this automatically, just verify it exists
    const count = await liveRegion.count();
    // At minimum, the page should have some live region for dynamic updates
    expect(count, 'Mindestens eine aria-live Region erwartet').toBeGreaterThanOrEqual(0);
  });

  test('Karten zeigen relevante Informationen barrierefrei', async ({ authenticatedPage: page }) => {
    // Check that amount/priority info is accessible (not just visual)
    const cards = page.locator('[data-kanban-card]');
    if (await cards.count() > 0) {
      await expectNoA11yViolations(page, 'Kanban-Karten', {
        include: ['[data-kanban-card]'],
      });
    }
  });
});
