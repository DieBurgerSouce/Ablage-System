import { test, expect } from '@playwright/test';

/**
 * Dashboard Tests - Nach Login ausgeführt
 * Testet das gesamte Dashboard auf Fehler, nicht-ladende Cards und interne Fehlermeldungen
 */

test.describe('Dashboard Deep Test', () => {
  const foundErrors: string[] = [];
  const consoleErrors: string[] = [];
  const networkErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    // Console-Errors sammeln
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(`[CONSOLE] ${msg.text()}`);
      }
    });

    // Netzwerk-Fehler sammeln (nur 500er sind kritisch)
    page.on('response', response => {
      if (response.status() >= 500) {
        networkErrors.push(`[HTTP ${response.status()}] ${response.url()}`);
      }
    });
  });

  test('Dashboard nach Login vollständig laden', async ({ page }) => {
    // Zum Dashboard navigieren (sollte auth-state haben)
    await page.goto('/', { waitUntil: 'networkidle' });

    // Screenshot vom Dashboard
    await page.screenshot({ path: 'test-results/dashboard-initial.png', fullPage: true });

    // Prüfen ob wir auf dem Dashboard sind (nicht Login)
    const url = page.url();
    const isOnDashboard = !url.includes('/login') && !url.includes('/auth');

    console.log(`URL nach Navigation: ${url}`);
    console.log(`Auf Dashboard: ${isOnDashboard}`);

    if (!isOnDashboard) {
      foundErrors.push('KRITISCH: Nicht auf Dashboard nach Login');
    }

    // Warten auf Dashboard-Elemente
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'test-results/dashboard-after-3s.png', fullPage: true });
  });

  test('Alle Dashboard-Cards prüfen', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Nach Card-Elementen suchen
    const cards = await page.locator('[class*="Card"], [class*="card"], .bg-card, [data-testid*="card"]').all();
    console.log(`Gefundene Cards: ${cards.length}`);

    // Skeleton/Loading-Elemente die noch sichtbar sind
    const skeletons = await page.locator('[class*="skeleton"], [class*="Skeleton"], [class*="loading"], [class*="spinner"]').all();
    if (skeletons.length > 0) {
      foundErrors.push(`${skeletons.length} Skeleton/Loading-Elemente nach 2s noch sichtbar`);
      await page.screenshot({ path: 'test-results/skeletons-visible.png', fullPage: true });
    }

    // Error-States in Cards
    const errorCards = await page.locator('[class*="error"], [class*="Error"], .text-destructive, .text-red').all();
    if (errorCards.length > 0) {
      for (const card of errorCards) {
        const text = await card.textContent();
        if (text && (text.includes('Error') || text.includes('Fehler') || text.includes('500'))) {
          foundErrors.push(`Error in Card: "${text.substring(0, 100)}"`);
        }
      }
    }
  });

  test('Navigation durch alle Haupt-Seiten', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });

    // Haupt-Navigation finden
    const navItems = await page.locator('nav a, aside a, [role="navigation"] a').all();
    console.log(`Navigation Items: ${navItems.length}`);

    const visitedPages: string[] = [];

    for (const navItem of navItems) {
      const href = await navItem.getAttribute('href');
      const text = await navItem.textContent();

      if (!href || href === '#' || href.startsWith('http') || visitedPages.includes(href)) {
        continue;
      }

      console.log(`Navigiere zu: ${text} (${href})`);

      try {
        await navItem.click();
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1000);

        // Screenshot
        const safeText = (text || 'page').replace(/[^a-zA-Z0-9]/g, '-').substring(0, 20);
        await page.screenshot({ path: `test-results/page-${safeText}.png`, fullPage: true });

        // Nach Fehlern auf der Seite suchen
        const pageText = await page.locator('body').innerText();
        if (pageText.includes('Internal Server Error') || pageText.includes('500')) {
          foundErrors.push(`500 Error auf ${href}`);
        }

        visitedPages.push(href);
      } catch (e) {
        console.log(`Navigation zu ${href} fehlgeschlagen: ${e}`);
      }
    }

    console.log(`Besuchte Seiten: ${visitedPages.length}`);
  });

  test('Dokumente-Seite prüfen', async ({ page }) => {
    await page.goto('/documents', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'test-results/documents-page.png', fullPage: true });

    // Prüfen ob Dokumente geladen wurden oder eine leere State-Meldung
    const hasDocuments = await page.locator('table tbody tr, [class*="DocumentCard"], [data-testid*="document"]').count() > 0;
    const hasEmptyState = await page.locator('text="Keine Dokumente"').count() > 0;

    console.log(`Dokumente vorhanden: ${hasDocuments}, Empty State: ${hasEmptyState}`);

    // Suche nach Error-Toast oder Error-Meldungen
    const errorToast = await page.locator('[class*="toast"][class*="error"], [class*="Toast"][class*="error"]').count();
    if (errorToast > 0) {
      foundErrors.push('Error-Toast auf Dokumente-Seite');
      await page.screenshot({ path: 'test-results/documents-error.png' });
    }
  });

  test('Admin-Bereich prüfen', async ({ page }) => {
    await page.goto('/admin', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'test-results/admin-page.png', fullPage: true });

    // Nach Admin-Elementen oder Access-Denied suchen
    const adminContent = await page.locator('body').innerText();

    if (adminContent.includes('Zugriff verweigert') || adminContent.includes('Access Denied')) {
      console.log('Admin-Bereich: Zugriff verweigert (möglicherweise korrekt)');
    } else if (adminContent.includes('Error') || adminContent.includes('500')) {
      foundErrors.push('Fehler im Admin-Bereich');
    }
  });

  test.afterAll(async () => {
    console.log('\n========== DASHBOARD TEST REPORT ==========');
    console.log(`Gefundene Fehler: ${foundErrors.length}`);
    console.log(`Console-Errors: ${consoleErrors.length}`);
    console.log(`Network 500er: ${networkErrors.length}`);

    if (foundErrors.length > 0) {
      console.log('\n⚠️  FEHLER:');
      foundErrors.forEach(e => console.log(`  - ${e}`));
    }

    if (consoleErrors.length > 0) {
      console.log('\n📋 CONSOLE ERRORS:');
      consoleErrors.forEach(e => console.log(`  - ${e}`));
    }

    if (networkErrors.length > 0) {
      console.log('\n🌐 NETWORK 500 ERRORS:');
      networkErrors.forEach(e => console.log(`  - ${e}`));
    }

    console.log('============================================\n');

    // Test schlägt fehl wenn kritische Fehler gefunden wurden
    if (networkErrors.length > 0) {
      throw new Error(`${networkErrors.length} kritische 500er Fehler gefunden!`);
    }
  });
});
