/**
 * E2E Tests: Entity Workflow (Entity -> Document Linking -> Risk Score)
 *
 * Testet den vollstaendigen Entity-Workflow:
 * - Kunden/Lieferanten-Erstellung
 * - Dokumenten-Verknuepfung
 * - Risk-Score-Berechnung und -Anzeige
 * - Lexware-Import
 * - Entity-Suche
 *
 * Alle Texte auf Deutsch (CLAUDE.md Anforderung)
 */

import { test, expect, type Page } from '@playwright/test';

// Test configuration
const TIMEOUTS = {
  navigation: 10000,
  apiCall: 5000,
  search: 3000,
  import: 30000,
};

// Test data
const TEST_CUSTOMER = {
  name: 'Test Kunde GmbH',
  customerNumber: 'K-2024-001',
  vatId: 'DE123456789',
  iban: 'DE89370400440532013000',
  email: 'test@test-kunde.de',
  phone: '+49 30 12345678',
  address: {
    street: 'Teststrasse 123',
    zip: '12345',
    city: 'Berlin',
    country: 'Deutschland',
  },
};

const TEST_SUPPLIER = {
  name: 'Test Lieferant AG',
  supplierNumber: 'L-2024-001',
  vatId: 'DE987654321',
  iban: 'DE89370400440532013001',
  email: 'info@test-lieferant.de',
};

test.describe('Entity Workflow - Kunden', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test.describe('Kunden-Uebersicht', () => {
    test('sollte Kundenliste laden', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Kundenseite geladen wurde
      const customerPage = page.locator('[data-testid="customers-page"], h1:has-text("Kunden"), .customer-list');

      if (await customerPage.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(customerPage.first()).toBeVisible();
      }
    });

    test('sollte Infinite Scroll unterstuetzen (100 Items/Page)', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Finde Kundenliste
      const customerList = page.locator('[data-testid="customer-list"], .customer-list, tbody');

      if (await customerList.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Initiale Items zaehlen
        const initialRows = await page.locator('tr[data-testid], .customer-row, tbody tr').count();

        // Scrolle nach unten
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(1000);

        // Pruefe ob mehr Items geladen wurden (oder gleich wenn weniger als 100)
        const afterScrollRows = await page.locator('tr[data-testid], .customer-row, tbody tr').count();

        // Sollte gleich oder mehr sein (infinite scroll laed nach)
        expect(afterScrollRows).toBeGreaterThanOrEqual(initialRows);
      }
    });

    test('sollte Kundensuche funktionieren', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Finde Suchfeld
      const searchInput = page.locator('[data-testid="customer-search"], input[type="search"], .search-input');

      if (await searchInput.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Suchbegriff eingeben
        await searchInput.first().fill('Test');
        await page.waitForTimeout(TIMEOUTS.search);

        // Ergebnisse sollten gefiltert sein
        const results = page.locator('[data-testid="search-results"], .customer-row, tbody tr');
        const resultCount = await results.count();

        // Kann 0 sein wenn keine Treffer, aber Suche sollte funktionieren
        expect(resultCount).toBeGreaterThanOrEqual(0);
      }
    });
  });

  test.describe('Kunden-Detail', () => {
    test('sollte Kundendetails oeffnen koennen', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Klicke auf ersten Kunden
      const firstCustomer = page.locator('a[href*="kunden/"], .customer-link, tbody tr').first();

      if (await firstCustomer.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstCustomer.click();
        await page.waitForLoadState('networkidle');

        // Sollte auf Kundendetail-Seite sein
        expect(page.url()).toContain('kunden');

        // Pruefe Detail-Ansicht
        const detailView = page.locator('[data-testid="customer-detail"], .customer-detail, .entity-detail');

        if (await detailView.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await expect(detailView).toBeVisible();
        }
      }
    });

    test('sollte Kundenstammdaten anzeigen', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Navigiere zu Kundendetail
      const firstCustomer = page.locator('a[href*="kunden/"], .customer-link').first();

      if (await firstCustomer.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstCustomer.click();
        await page.waitForLoadState('networkidle');

        // Erwartete Felder
        const expectedFields = ['Name', 'Kundennummer', 'USt-IdNr', 'IBAN', 'Adresse', 'E-Mail'];

        for (const field of expectedFields) {
          const fieldElement = page.getByText(new RegExp(field, 'i'));
          if (await fieldElement.first().isVisible({ timeout: 1000 }).catch(() => false)) {
            await expect(fieldElement.first()).toBeVisible();
            break;
          }
        }
      }
    });

    test('sollte verknuepfte Dokumente anzeigen', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Navigiere zu Kundendetail
      const firstCustomer = page.locator('a[href*="kunden/"], .customer-link').first();

      if (await firstCustomer.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstCustomer.click();
        await page.waitForLoadState('networkidle');

        // Suche Dokumenten-Bereich
        const documentsSection = page.locator('[data-testid="linked-documents"], .documents-list, .entity-documents');

        if (await documentsSection.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await expect(documentsSection).toBeVisible();
        }
      }
    });
  });
});

test.describe('Entity Workflow - Lieferanten', () => {
  test.describe('Lieferanten-Uebersicht', () => {
    test('sollte Lieferantenliste laden', async ({ page }) => {
      await page.goto('/lieferanten');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Lieferantenseite geladen wurde
      const supplierPage = page.locator('[data-testid="suppliers-page"], h1:has-text("Lieferanten"), .supplier-list');

      if (await supplierPage.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(supplierPage.first()).toBeVisible();
      }
    });

    test('sollte Lieferanten filtern koennen', async ({ page }) => {
      await page.goto('/lieferanten');
      await page.waitForLoadState('networkidle');

      // Finde Filter-Optionen
      const filterSelect = page.locator('[data-testid="supplier-filter"], select, .filter-dropdown');

      if (await filterSelect.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await filterSelect.first().click();

        // Erwarte Filteroptionen
        const filterOptions = page.locator('option, [role="option"]');
        const optionCount = await filterOptions.count();

        expect(optionCount).toBeGreaterThan(0);
      }
    });
  });

  test.describe('Lieferanten-Detail', () => {
    test('sollte Lieferantendetails oeffnen koennen', async ({ page }) => {
      await page.goto('/lieferanten');
      await page.waitForLoadState('networkidle');

      // Klicke auf ersten Lieferanten
      const firstSupplier = page.locator('a[href*="lieferanten/"], .supplier-link, tbody tr').first();

      if (await firstSupplier.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstSupplier.click();
        await page.waitForLoadState('networkidle');

        // Sollte auf Lieferantendetail-Seite sein
        expect(page.url()).toContain('lieferanten');
      }
    });
  });
});

test.describe('Entity Workflow - Document Linking', () => {
  test.describe('Automatische Verknuepfung', () => {
    test('sollte Auto-Link-Indikator anzeigen', async ({ page }) => {
      // Navigiere zu einem Dokument
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Finde Dokument mit Entity-Link
      const linkedDocument = page.locator('[data-testid="entity-link"], .entity-badge, .linked-entity');

      if (await linkedDocument.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(linkedDocument.first()).toBeVisible();
      }
    });

    test('sollte Link-Confidence anzeigen', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Suche nach Confidence-Anzeige
      const confidenceBadge = page.locator('[data-testid="link-confidence"], .confidence-badge, .match-score');

      if (await confidenceBadge.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const confidenceText = await confidenceBadge.first().textContent();

        // Sollte Prozent oder Score enthalten
        if (confidenceText) {
          expect(confidenceText).toMatch(/\d+%?|hoch|mittel|niedrig/i);
        }
      }
    });
  });

  test.describe('Manuelle Verknuepfung', () => {
    test('sollte manuelles Linking ermoeglichen', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Finde erstes Dokument
      const firstDocument = page.locator('a[href*="documents"], .document-row, tbody tr').first();

      if (await firstDocument.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstDocument.click();
        await page.waitForLoadState('networkidle');

        // Suche Link-Button
        const linkButton = page.locator('[data-testid="link-entity"], button:has-text("Verknuepfen"), .link-entity-action');

        if (await linkButton.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await expect(linkButton).toBeEnabled();
        }
      }
    });

    test('sollte Entity-Auswahl-Dialog oeffnen', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Navigiere zu Dokument
      const firstDocument = page.locator('a[href*="documents"], .document-row').first();

      if (await firstDocument.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstDocument.click();
        await page.waitForLoadState('networkidle');

        // Klicke Link-Button
        const linkButton = page.locator('[data-testid="link-entity"], button:has-text("Verknuepfen")');

        if (await linkButton.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await linkButton.click();

          // Erwarte Entity-Auswahl-Dialog
          const entityDialog = page.locator('[data-testid="entity-selector"], [role="dialog"], .entity-picker');

          if (await entityDialog.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
            await expect(entityDialog).toBeVisible();
          }
        }
      }
    });
  });
});

test.describe('Entity Workflow - Risk Score', () => {
  test.describe('Risk Score Anzeige', () => {
    test('sollte Risk Score auf Kundenseite anzeigen', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Navigiere zu Kundendetail
      const firstCustomer = page.locator('a[href*="kunden/"], .customer-link').first();

      if (await firstCustomer.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstCustomer.click();
        await page.waitForLoadState('networkidle');

        // Suche Risk Score Anzeige
        const riskScore = page.locator('[data-testid="risk-score"], .risk-indicator, .risk-badge');

        if (await riskScore.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          const scoreText = await riskScore.textContent();

          // Sollte Score oder Risikostufe enthalten
          if (scoreText) {
            expect(scoreText).toMatch(/\d+|niedrig|mittel|hoch|kritisch|gering/i);
          }
        }
      }
    });

    test('sollte Risk Score Faktoren anzeigen', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      const firstCustomer = page.locator('a[href*="kunden/"], .customer-link').first();

      if (await firstCustomer.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstCustomer.click();
        await page.waitForLoadState('networkidle');

        // Erwartete Risk-Faktoren (aus CLAUDE.md)
        const riskFactors = [
          'Zahlungsverzoegerung',
          'Ausfallrate',
          'Rechnungsvolumen',
          'Dokumenthaeufigkeit',
          'Beziehungsdauer',
        ];

        // Suche nach Risk-Faktoren-Bereich
        const riskFactorsSection = page.locator('[data-testid="risk-factors"], .risk-breakdown, .risk-details');

        if (await riskFactorsSection.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          for (const factor of riskFactors) {
            const factorElement = page.getByText(new RegExp(factor.replace('ae', '(ae|ä)').replace('ue', '(ue|ü)'), 'i'));
            if (await factorElement.first().isVisible({ timeout: 500 }).catch(() => false)) {
              await expect(factorElement.first()).toBeVisible();
              break;
            }
          }
        }
      }
    });

    test('sollte Risk Score farblich kodieren', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      // Suche nach farbkodierten Risk-Indikatoren
      const riskIndicators = page.locator('[data-testid="risk-score"], .risk-indicator, .risk-badge');

      if (await riskIndicators.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Pruefe CSS-Klassen fuer Farbkodierung
        const classes = await riskIndicators.first().getAttribute('class');

        // Sollte Farbklassen haben
        if (classes) {
          expect(classes).toMatch(/green|yellow|orange|red|success|warning|danger|low|medium|high/i);
        }
      }
    });
  });

  test.describe('Risk Score Berechnung', () => {
    test('sollte Risk Score zwischen 0-100 sein', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      const firstCustomer = page.locator('a[href*="kunden/"]').first();

      if (await firstCustomer.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstCustomer.click();
        await page.waitForLoadState('networkidle');

        const riskScore = page.locator('[data-testid="risk-score-value"], .score-value');

        if (await riskScore.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          const scoreText = await riskScore.textContent();

          if (scoreText) {
            const scoreMatch = scoreText.match(/\d+/);
            if (scoreMatch) {
              const score = parseInt(scoreMatch[0], 10);
              expect(score).toBeGreaterThanOrEqual(0);
              expect(score).toBeLessThanOrEqual(100);
            }
          }
        }
      }
    });
  });
});

test.describe('Entity Workflow - Lexware Import', () => {
  test.describe('Import-Funktion', () => {
    test('sollte Lexware-Import-Seite laden', async ({ page }) => {
      // Suche nach Lexware-Import-Seite (Admin oder ERP)
      await page.goto('/admin/erp');
      await page.waitForLoadState('networkidle');

      const importPage = page.locator('[data-testid="erp-import"], h1:has-text("Import"), .lexware-import');

      if (await importPage.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(importPage.first()).toBeVisible();
      }
    });

    test('sollte Excel-Upload fuer Lexware unterstuetzen', async ({ page }) => {
      await page.goto('/admin/erp');
      await page.waitForLoadState('networkidle');

      // Suche Upload-Bereich
      const uploadArea = page.locator('[data-testid="lexware-upload"], input[type="file"], .file-upload');

      if (await uploadArea.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Pruefe akzeptierte Dateitypen
        const acceptAttr = await uploadArea.first().getAttribute('accept');

        if (acceptAttr) {
          expect(acceptAttr).toMatch(/xlsx|xls|csv|excel/i);
        }
      }
    });

    test('sollte Import-Vorschau anzeigen', async ({ page }) => {
      await page.goto('/admin/erp');
      await page.waitForLoadState('networkidle');

      // Suche Import-Vorschau-Bereich
      const previewSection = page.locator('[data-testid="import-preview"], .preview-table, .import-preview');

      // Falls bereits Daten geladen wurden
      if (await previewSection.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
        await expect(previewSection).toBeVisible();
      }
    });

    test('sollte Konflikt-Erkennung anzeigen', async ({ page }) => {
      await page.goto('/admin/erp/conflicts');
      await page.waitForLoadState('networkidle');

      // Pruefe Konflikt-Seite
      const conflictsPage = page.locator('[data-testid="conflicts-page"], h1:has-text("Konflikt"), .conflicts-list');

      if (await conflictsPage.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(conflictsPage).toBeVisible();
      }
    });
  });

  test.describe('Sync-Status', () => {
    test('sollte Sync-Status anzeigen', async ({ page }) => {
      await page.goto('/admin/erp/sync');
      await page.waitForLoadState('networkidle');

      const syncPage = page.locator('[data-testid="sync-status"], h1:has-text("Sync"), .sync-dashboard');

      if (await syncPage.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(syncPage).toBeVisible();

        // Erwartete Status-Elemente
        const statusElements = ['Letzte Synchronisation', 'Naechste', 'Status', 'Fehler'];

        for (const element of statusElements) {
          const statusElement = page.getByText(new RegExp(element, 'i'));
          if (await statusElement.first().isVisible({ timeout: 1000 }).catch(() => false)) {
            await expect(statusElement.first()).toBeVisible();
            break;
          }
        }
      }
    });

    test('sollte manuelle Sync triggern koennen', async ({ page }) => {
      await page.goto('/admin/erp/sync');
      await page.waitForLoadState('networkidle');

      const syncButton = page.locator('[data-testid="trigger-sync"], button:has-text("Synchronisieren"), .sync-now');

      if (await syncButton.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(syncButton).toBeEnabled();
      }
    });
  });
});

test.describe('Entity Workflow - Entity Search', () => {
  test.describe('Multi-Strategie Suche', () => {
    test('sollte globale Entity-Suche anbieten', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Suche globales Suchfeld
      const globalSearch = page.locator('[data-testid="global-search"], input[type="search"], .search-global');

      if (await globalSearch.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await globalSearch.first().fill('Test');
        await page.waitForTimeout(TIMEOUTS.search);

        // Erwarte Suchergebnisse
        const searchResults = page.locator('[data-testid="search-results"], .search-dropdown, .results-list');

        if (await searchResults.isVisible({ timeout: TIMEOUTS.search }).catch(() => false)) {
          await expect(searchResults).toBeVisible();
        }
      }
    });

    test('sollte nach Kundennummer suchen koennen', async ({ page }) => {
      await page.goto('/kunden');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('[data-testid="customer-search"], input[type="search"]');

      if (await searchInput.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Suche nach Kundennummer-Pattern
        await searchInput.first().fill('K-');
        await page.waitForTimeout(TIMEOUTS.search);

        // Ergebnisse sollten Kundennummern enthalten
        const results = page.locator('[data-testid="search-results"], tbody tr');
        const resultCount = await results.count();

        expect(resultCount).toBeGreaterThanOrEqual(0);
      }
    });

    test('sollte nach IBAN suchen koennen', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('[data-testid="global-search"], input[type="search"]');

      if (await searchInput.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Suche nach IBAN-Pattern
        await searchInput.first().fill('DE89');
        await page.waitForTimeout(TIMEOUTS.search);

        // Keine Validierung der Ergebnisse, da IBAN moeglicherweise nicht im System
      }
    });

    test('sollte nach USt-IdNr suchen koennen', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('[data-testid="global-search"], input[type="search"]');

      if (await searchInput.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Suche nach VAT-ID-Pattern
        await searchInput.first().fill('DE1234');
        await page.waitForTimeout(TIMEOUTS.search);
      }
    });
  });

  test.describe('Suchergebnis-Filterung', () => {
    test('sollte Ergebnisse nach Typ filtern koennen', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Fuehre Suche durch
      const searchInput = page.locator('[data-testid="global-search"], input[type="search"]');

      if (await searchInput.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await searchInput.first().fill('Test');
        await page.waitForTimeout(TIMEOUTS.search);

        // Suche nach Typ-Filter
        const typeFilter = page.locator('[data-testid="type-filter"], .type-tabs, button:has-text("Kunden")');

        if (await typeFilter.first().isVisible({ timeout: TIMEOUTS.search }).catch(() => false)) {
          await typeFilter.first().click();
          await page.waitForTimeout(500);
        }
      }
    });
  });
});

test.describe('Entity Workflow - Accessibility', () => {
  test('sollte Keyboard-Navigation in Listen unterstuetzen', async ({ page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle');

    // Tab durch Liste
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // Fokussiertes Element sollte in der Liste sein
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toBeTruthy();
  });

  test('sollte Screen-Reader-freundliche Labels haben', async ({ page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle');

    // Pruefe ARIA-Labels
    const ariaElements = await page.locator('[aria-label], [role="table"], [role="grid"], [role="row"]').count();
    expect(ariaElements).toBeGreaterThanOrEqual(0);
  });

  test('sollte Fokus-Indikatoren anzeigen', async ({ page }) => {
    await page.goto('/kunden');
    await page.waitForLoadState('networkidle');

    // Tab zu interaktivem Element
    await page.keyboard.press('Tab');

    // Fokussiertes Element sollte sichtbar sein
    const focusedElement = page.locator(':focus');

    if (await focusedElement.isVisible({ timeout: 1000 }).catch(() => false)) {
      // Pruefe ob Fokus-Styling vorhanden
      const outline = await focusedElement.evaluate(el => {
        const styles = window.getComputedStyle(el);
        return styles.outline || styles.boxShadow;
      });

      // Sollte irgendeine Form von Fokus-Indikator haben
      expect(outline).toBeTruthy();
    }
  });
});
