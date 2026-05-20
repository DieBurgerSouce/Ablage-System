import { test, expect } from '@playwright/test';

// QA-Durchlauf für Ablage-System
// Systematischer Test aller Kernfunktionen

test.describe('Ablage-System QA-Durchlauf', () => {
  // Fehler-Sammlung
  const errors: string[] = [];
  const consoleErrors: string[] = [];
  const networkErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    // Console-Errors sammeln
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(`Console Error: ${msg.text()}`);
      }
    });

    // Netzwerk-Fehler sammeln
    page.on('response', response => {
      if (response.status() >= 400) {
        networkErrors.push(`HTTP ${response.status()}: ${response.url()}`);
      }
    });
  });

  test('Phase 1: Startseite laden und Accessibility prüfen', async ({ page }) => {
    await page.goto('http://localhost:80', { waitUntil: 'networkidle' });

    // Screenshot als Baseline
    await page.screenshot({ path: 'test-results/01-startseite.png', fullPage: true });

    // Prüfen ob Login-Form oder Dashboard angezeigt wird
    const loginForm = page.locator('form');
    const isLoginPage = await loginForm.count() > 0;

    console.log(`Startseite geladen. Login-Seite: ${isLoginPage}`);

    // Grundlegende Accessibility-Prüfung
    const title = await page.title();
    expect(title).toContain('Ablage');

    // HTML lang Attribut prüfen
    const lang = await page.getAttribute('html', 'lang');
    expect(lang).toBe('de');
  });

  test('Phase 2: Login-Flow testen', async ({ page }) => {
    await page.goto('http://localhost:80', { waitUntil: 'networkidle' });

    // Login-Formular finden
    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="mail"]').first();
    const passwordInput = page.locator('input[type="password"]').first();
    const submitButton = page.locator('button[type="submit"], button:has-text("Anmelden")').first();

    if (await emailInput.count() > 0) {
      // Login-Formular ausfüllen
      await emailInput.fill('admin@localhost.com');
      await passwordInput.fill('admin123');

      await page.screenshot({ path: 'test-results/02-login-form.png' });

      // Absenden
      await submitButton.click();

      // Warten auf Navigation
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: 'test-results/03-nach-login.png', fullPage: true });
    }
  });

  test('Phase 3: Alle API-Endpoints prüfen', async ({ request }) => {
    const endpoints = [
      '/api/v1/health',
      '/api/v1/documents/',
      '/api/v1/companies/current',
      '/api/v1/dashboard/stats',
      '/api/v1/admin/jobs',
    ];

    for (const endpoint of endpoints) {
      try {
        const response = await request.get(`http://localhost:8000${endpoint}`);
        console.log(`${endpoint}: HTTP ${response.status()}`);

        // 500er Fehler sind kritisch
        if (response.status() >= 500) {
          errors.push(`KRITISCH: ${endpoint} liefert ${response.status()}`);
        }
      } catch (e) {
        errors.push(`FEHLER bei ${endpoint}: ${e}`);
      }
    }

    console.log(`API-Test abgeschlossen. Fehler: ${errors.length}`);
  });

  test('Phase 4: Navigation testen', async ({ page }) => {
    await page.goto('http://localhost:80', { waitUntil: 'networkidle' });

    // Alle Links auf der Seite finden
    const links = await page.locator('a[href], button').all();
    console.log(`Gefundene interaktive Elemente: ${links.length}`);

    // Navigation-Links testen
    const navLinks = await page.locator('nav a, [role="navigation"] a').all();

    for (let i = 0; i < Math.min(navLinks.length, 5); i++) {
      const link = navLinks[i];
      const href = await link.getAttribute('href');
      const text = await link.textContent();

      try {
        await link.click();
        await page.waitForLoadState('networkidle');
        await page.screenshot({ path: `test-results/nav-${i}-${text?.replace(/\s/g, '-') || 'link'}.png` });
        console.log(`Navigation zu "${text}" (${href}): OK`);
      } catch (e) {
        errors.push(`Navigation "${text}" fehlgeschlagen: ${e}`);
      }

      // Zurück zur Startseite
      await page.goto('http://localhost:80', { waitUntil: 'networkidle' });
    }
  });

  test('Phase 5: Error-Cards und interne Fehler suchen', async ({ page }) => {
    await page.goto('http://localhost:80', { waitUntil: 'networkidle' });

    // Nach Error-Indikatoren suchen
    const errorIndicators = [
      'text="Error"',
      'text="Fehler"',
      'text="Internal Server Error"',
      'text="500"',
      'text="404"',
      '[class*="error"]',
      '[class*="Error"]',
      '[data-error]',
      '.toast-error',
      '.alert-danger',
      '.error-message',
    ];

    for (const selector of errorIndicators) {
      try {
        const elements = await page.locator(selector).all();
        if (elements.length > 0) {
          for (const el of elements) {
            const text = await el.textContent();
            errors.push(`Error-Element gefunden: ${selector} - "${text?.substring(0, 100)}"`);
          }
          await page.screenshot({ path: `test-results/error-found-${Date.now()}.png` });
        }
      } catch (e) {
        // Selector nicht gefunden - ok
      }
    }

    // Nicht geladene Cards (Skeleton Loader die nicht verschwinden)
    await page.waitForTimeout(3000);
    const skeletons = await page.locator('[class*="skeleton"], [class*="loading"], [class*="Skeleton"]').all();
    if (skeletons.length > 0) {
      errors.push(`${skeletons.length} Skeleton/Loading-Elemente nach 3s noch sichtbar`);
      await page.screenshot({ path: 'test-results/skeleton-found.png' });
    }
  });

  test('Phase 6: Deutsche Zeichen und Umlaute', async ({ page }) => {
    await page.goto('http://localhost:80', { waitUntil: 'networkidle' });

    // Alle sichtbaren Texte prüfen
    const bodyText = await page.locator('body').innerText();

    // Auf korrekte deutsche Zeichen prüfen
    const hasUmlauts = /[äöüÄÖÜß]/.test(bodyText);

    // Auf kaputte Zeichen prüfen
    const brokenChars = /[ï¿½�]/.test(bodyText);

    if (brokenChars) {
      errors.push('KRITISCH: Kaputte Unicode-Zeichen auf der Seite gefunden');
      await page.screenshot({ path: 'test-results/broken-unicode.png' });
    }

    console.log(`Deutsche Zeichen vorhanden: ${hasUmlauts}`);
    console.log(`Kaputte Zeichen gefunden: ${brokenChars}`);
  });

  test.afterAll(async () => {
    console.log('\n========== QA-BERICHT ==========');
    console.log(`Gefundene Fehler: ${errors.length}`);
    console.log(`Console-Errors: ${consoleErrors.length}`);
    console.log(`Network-Errors: ${networkErrors.length}`);

    if (errors.length > 0) {
      console.log('\nFEHLER:');
      errors.forEach(e => console.log(`  - ${e}`));
    }

    if (consoleErrors.length > 0) {
      console.log('\nCONSOLE ERRORS:');
      consoleErrors.forEach(e => console.log(`  - ${e}`));
    }

    if (networkErrors.length > 0) {
      console.log('\nNETWORK ERRORS:');
      networkErrors.forEach(e => console.log(`  - ${e}`));
    }

    console.log('================================\n');
  });
});
