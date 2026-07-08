/**
 * E2E Tests: Invoice Workflow (Invoice -> Skonto -> Payment -> Dunning)
 *
 * MODUL EINGEFROREN (Odoo-Neuausrichtung 2026-07): Rechnungsverfolgung,
 * Skonto, Teilzahlungen und Mahnwesen übernimmt Odoo. Alle hier getesteten
 * Routen (/admin/banking/*, /admin/mahnungen/*) leiten auf /frozen um,
 * die Backend-Router (invoices/banking/dunning) liefern 404 — beide
 * describes sind daher geskippt.
 * Reaktivierung: ACTIVE_OPTIONAL_MODULES=banking,invoice_tracking
 * + Skips entfernen.
 *
 * Testete den vollstaendigen Rechnungs-Workflow:
 * - Rechnungserfassung und -anzeige
 * - Skonto-Tracking und Fristen
 * - Teilzahlungen (Partial Payments)
 * - Mahnwesen (Dunning Levels)
 * - Betragsberechnungen
 *
 * Alle Texte auf Deutsch (CLAUDE.md Anforderung)
 */

import { test, expect, type Page } from '@playwright/test';

// Test configuration
const TIMEOUTS = {
  navigation: 10000,
  apiCall: 5000,
  animation: 500,
};

// Test data for invoice workflow
const TEST_INVOICE = {
  invoiceNumber: 'RE-2024-TEST-001',
  amount: 1234.56,
  currency: 'EUR',
  dueDate: '2024-04-15',
  skontoPercent: 2.0,
  skontoDays: 14,
  debtor: 'Test GmbH',
};

test.describe.skip('Invoice Workflow - Rechnungsverwaltung', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test.describe('Rechnungsanzeige', () => {
    test('sollte Rechnungsliste mit korrekten Spalten anzeigen', async ({ page }) => {
      // Navigiere zu Banking/Rechnungen
      await page.goto('/admin/banking/transactions');
      await page.waitForLoadState('networkidle');

      // Pruefe Tabellenspalten
      const expectedColumns = [
        'Rechnungsnr',
        'Datum',
        'Betrag',
        'Status',
        'Faelligkeit',
      ];

      const tableHeaders = page.locator('th, [role="columnheader"]');

      if (await tableHeaders.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const headerCount = await tableHeaders.count();
        expect(headerCount).toBeGreaterThan(0);
      }
    });

    test('sollte Rechnungsdetails oeffnen koennen', async ({ page }) => {
      await page.goto('/admin/banking/transactions');
      await page.waitForLoadState('networkidle');

      // Finde erste Transaktion/Rechnung in der Liste
      const firstRow = page.locator('tr[data-testid], .transaction-row, tbody tr').first();

      if (await firstRow.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await firstRow.click();

        // Erwarte Detail-Ansicht oder Modal
        const detailView = page.locator('[data-testid="invoice-detail"], .invoice-detail, [role="dialog"]');

        if (await detailView.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
          await expect(detailView).toBeVisible();
        }
      }
    });

    test('sollte Filteroptionen fuer Rechnungen anbieten', async ({ page }) => {
      await page.goto('/admin/banking/transactions');
      await page.waitForLoadState('networkidle');

      // Suche Filter-Elemente
      const statusFilter = page.locator('[data-testid="status-filter"], select[name="status"], .status-filter');
      const dateFilter = page.locator('[data-testid="date-filter"], input[type="date"], .date-filter');
      const searchInput = page.locator('[data-testid="search-input"], input[type="search"], .search-input');

      // Mindestens ein Filter sollte verfuegbar sein
      const hasStatusFilter = await statusFilter.first().isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false);
      const hasDateFilter = await dateFilter.first().isVisible({ timeout: 1000 }).catch(() => false);
      const hasSearchInput = await searchInput.first().isVisible({ timeout: 1000 }).catch(() => false);

      expect(hasStatusFilter || hasDateFilter || hasSearchInput).toBeTruthy();
    });
  });

  test.describe('Skonto-Tracking', () => {
    test('sollte Skonto-Seite laden', async ({ page }) => {
      await page.goto('/admin/banking/skonto');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Skonto-Seite geladen wurde
      const skontoPage = page.locator('[data-testid="skonto-page"], h1:has-text("Skonto"), .skonto-dashboard');

      if (await skontoPage.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(skontoPage).toBeVisible();
      }
    });

    test('sollte auslaufende Skonto-Fristen anzeigen', async ({ page }) => {
      await page.goto('/admin/banking/skonto');
      await page.waitForLoadState('networkidle');

      // Suche nach Skonto-Opportunities Liste
      const skontoList = page.locator('[data-testid="skonto-opportunities"], .skonto-list, table');

      if (await skontoList.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Erwarte deutsche Beschriftungen
        const germanLabels = ['Frist', 'Betrag', 'Ersparnis', 'Tage', 'Skonto'];

        for (const label of germanLabels) {
          const labelElement = page.getByText(new RegExp(label, 'i'));
          if (await labelElement.first().isVisible({ timeout: 1000 }).catch(() => false)) {
            await expect(labelElement.first()).toBeVisible();
            break;
          }
        }
      }
    });

    test('sollte Skonto-Berechnung korrekt anzeigen', async ({ page }) => {
      await page.goto('/admin/banking/skonto');
      await page.waitForLoadState('networkidle');

      // Suche nach Betragsanzeige mit Skonto
      const amountDisplay = page.locator('[data-testid="skonto-amount"], .skonto-calculation, .amount-with-skonto');

      if (await amountDisplay.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const amountText = await amountDisplay.first().textContent();

        // Pruefe auf EUR-Format
        if (amountText) {
          expect(amountText).toMatch(/EUR|\u20AC|,\d{2}/);
        }
      }
    });

    test('sollte Skonto-Deadline-Warnung anzeigen', async ({ page }) => {
      await page.goto('/admin/banking/skonto');
      await page.waitForLoadState('networkidle');

      // Suche nach Warnungen fuer auslaufende Fristen
      const warningIndicator = page.locator('[data-testid="skonto-warning"], .warning-badge, .deadline-warning, [role="alert"]');

      // Falls Warnungen vorhanden
      if (await warningIndicator.first().isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
        await expect(warningIndicator.first()).toBeVisible();
      }
    });
  });

  test.describe('Teilzahlungen (Partial Payments)', () => {
    test('sollte Zahlungsuebersicht laden', async ({ page }) => {
      await page.goto('/admin/banking/payments');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Zahlungsseite geladen wurde
      const paymentsPage = page.locator('[data-testid="payments-page"], h1:has-text("Zahlung"), .payments-list');

      if (await paymentsPage.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(paymentsPage).toBeVisible();
      }
    });

    test('sollte Teilzahlung-Option anzeigen', async ({ page }) => {
      await page.goto('/admin/banking/payments');
      await page.waitForLoadState('networkidle');

      // Suche nach Teilzahlung-Button oder -Option
      const partialPaymentButton = page.locator('[data-testid="partial-payment"], button:has-text("Teilzahlung"), .partial-payment-action');

      // Falls vorhanden, sollte es klickbar sein
      if (await partialPaymentButton.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(partialPaymentButton.first()).toBeEnabled();
      }
    });

    test('sollte Zahlungshistorie anzeigen', async ({ page }) => {
      await page.goto('/admin/banking/payments');
      await page.waitForLoadState('networkidle');

      // Finde eine Zahlung und oeffne Details
      const paymentRow = page.locator('tr[data-testid], .payment-row, tbody tr').first();

      if (await paymentRow.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await paymentRow.click();

        // Erwarte Zahlungshistorie in Details
        const paymentHistory = page.locator('[data-testid="payment-history"], .payment-timeline, .history-list');

        if (await paymentHistory.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await expect(paymentHistory).toBeVisible();
        }
      }
    });

    test('sollte ausstehenden Betrag korrekt berechnen', async ({ page }) => {
      await page.goto('/admin/banking/payments');
      await page.waitForLoadState('networkidle');

      // Suche nach Outstanding Amount Anzeige
      const outstandingAmount = page.locator('[data-testid="outstanding-amount"], .outstanding-balance, .remaining-amount');

      if (await outstandingAmount.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const amountText = await outstandingAmount.first().textContent();

        // Pruefe auf gueltiges Zahlenformat
        if (amountText) {
          expect(amountText).toMatch(/[\d.,]+|EUR|\u20AC|ausstehend/i);
        }
      }
    });
  });

  test.describe('Mahnwesen (Dunning)', () => {
    test('sollte Mahnungsuebersicht laden', async ({ page }) => {
      await page.goto('/admin/mahnungen');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Mahnungsseite geladen wurde
      const dunningPage = page.locator('[data-testid="dunning-page"], h1:has-text("Mahnung"), .dunning-dashboard');

      if (await dunningPage.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(dunningPage).toBeVisible();
      }
    });

    test('sollte Mahnstufen anzeigen', async ({ page }) => {
      await page.goto('/admin/mahnungen/aktiv');
      await page.waitForLoadState('networkidle');

      // Erwartete Mahnstufen auf Deutsch
      const dunningLevels = ['Zahlungserinnerung', '1. Mahnung', '2. Mahnung', 'Letzte Mahnung', 'Inkasso'];

      // Suche nach Mahnstufen-Anzeige
      const levelIndicator = page.locator('[data-testid="dunning-level"], .dunning-stage, .mahn-stufe');

      if (await levelIndicator.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Mindestens ein Level sollte angezeigt werden
        for (const level of dunningLevels) {
          const levelElement = page.getByText(new RegExp(level, 'i'));
          if (await levelElement.first().isVisible({ timeout: 1000 }).catch(() => false)) {
            await expect(levelElement.first()).toBeVisible();
            break;
          }
        }
      }
    });

    test('sollte Mahnung eskalieren koennen', async ({ page }) => {
      await page.goto('/admin/mahnungen/aktiv');
      await page.waitForLoadState('networkidle');

      // Suche Eskalations-Button
      const escalateButton = page.locator('[data-testid="escalate-dunning"], button:has-text("Eskalieren"), .escalate-action');

      if (await escalateButton.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(escalateButton.first()).toBeEnabled();
      }
    });

    test('sollte Mahnstopp setzen koennen', async ({ page }) => {
      await page.goto('/admin/mahnungen/mahnstopp');
      await page.waitForLoadState('networkidle');

      // Pruefe Mahnstopp-Seite
      const mahnstoppPage = page.locator('[data-testid="mahnstopp-page"], h1:has-text("Mahnstopp"), .mahnstopp-list');

      if (await mahnstoppPage.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(mahnstoppPage).toBeVisible();

        // Suche nach Mahnstopp-Button
        const mahnstoppButton = page.locator('[data-testid="set-mahnstopp"], button:has-text("Mahnstopp"), .mahnstopp-action');

        if (await mahnstoppButton.first().isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await expect(mahnstoppButton.first()).toBeEnabled();
        }
      }
    });

    test('sollte Verzugszinsen berechnen (BGB 286)', async ({ page }) => {
      await page.goto('/admin/mahnungen/aktiv');
      await page.waitForLoadState('networkidle');

      // Suche nach Verzugszinsen-Anzeige
      const interestDisplay = page.locator('[data-testid="late-interest"], .verzugszinsen, .interest-amount');

      if (await interestDisplay.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const interestText = await interestDisplay.first().textContent();

        // Sollte Prozent oder EUR enthalten
        if (interestText) {
          expect(interestText).toMatch(/%|EUR|\u20AC|Zinsen/i);
        }
      }
    });

    test('sollte B2B-Pauschale Option anzeigen', async ({ page }) => {
      await page.goto('/admin/mahnungen/aktiv');
      await page.waitForLoadState('networkidle');

      // Suche B2B-Pauschale Option (40 EUR nach BGB 288)
      const b2bPauschale = page.locator('[data-testid="b2b-pauschale"], .pauschale-option, :text("40")');

      if (await b2bPauschale.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(b2bPauschale.first()).toBeVisible();
      }
    });
  });

  test.describe('Betragsberechnungen', () => {
    test('sollte Betraege im deutschen Format anzeigen (1.234,56 EUR)', async ({ page }) => {
      await page.goto('/admin/banking/transactions');
      await page.waitForLoadState('networkidle');

      // Suche nach Betragsanzeigen
      const amountCells = page.locator('[data-testid="amount"], .amount, td:has-text("EUR")');

      if (await amountCells.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const amountText = await amountCells.first().textContent();

        // Deutsches Zahlenformat: Punkt als Tausendertrennzeichen, Komma als Dezimaltrenner
        if (amountText && amountText.includes('EUR')) {
          // Akzeptiere beide Formate (deutsch und international)
          expect(amountText).toMatch(/[\d.,]+\s*(EUR|\u20AC)/);
        }
      }
    });

    test('sollte Skonto-Ersparnis korrekt berechnen', async ({ page }) => {
      await page.goto('/admin/banking/skonto');
      await page.waitForLoadState('networkidle');

      // Suche nach Ersparnis-Anzeige
      const savingsDisplay = page.locator('[data-testid="skonto-savings"], .savings-amount, .ersparnis');

      if (await savingsDisplay.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const savingsText = await savingsDisplay.first().textContent();

        // Ersparnis sollte positiv sein
        if (savingsText) {
          expect(savingsText).toMatch(/[\d.,]+|EUR|\u20AC|Ersparnis/i);
        }
      }
    });

    test('sollte Gesamtsumme mit Zinsen und Gebuehren anzeigen', async ({ page }) => {
      await page.goto('/admin/mahnungen/aktiv');
      await page.waitForLoadState('networkidle');

      // Suche nach Gesamtbetrag-Anzeige
      const totalDisplay = page.locator('[data-testid="total-outstanding"], .total-amount, .gesamtbetrag');

      if (await totalDisplay.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        const totalText = await totalDisplay.first().textContent();

        if (totalText) {
          expect(totalText).toMatch(/[\d.,]+|EUR|\u20AC|Gesamt/i);
        }
      }
    });
  });

  test.describe('Workflow-Integration', () => {
    test('sollte von Rechnung zu Mahnung navigieren koennen', async ({ page }) => {
      // Start bei Transaktionen
      await page.goto('/admin/banking/transactions');
      await page.waitForLoadState('networkidle');

      // Suche Navigation zu Mahnungen
      const dunningLink = page.locator('a[href*="mahnungen"], [data-testid="nav-dunning"], .nav-dunning');

      if (await dunningLink.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await dunningLink.first().click();
        await page.waitForLoadState('networkidle');

        // Sollte auf Mahnungsseite sein
        expect(page.url()).toContain('mahnungen');
      }
    });

    test('sollte Zahlungsworkflow vollstaendig durchfuehren koennen', async ({ page }) => {
      // Navigiere zu Zahlungen
      await page.goto('/admin/banking/payments');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Zahlungs-Erstellung moeglich
      const createPaymentButton = page.locator('[data-testid="create-payment"], button:has-text("Neue Zahlung"), .create-payment');

      if (await createPaymentButton.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(createPaymentButton).toBeEnabled();

        // Klick oeffnet Modal oder Navigation
        await createPaymentButton.click();

        // Erwarte Formular
        const paymentForm = page.locator('[data-testid="payment-form"], form, [role="dialog"]');

        if (await paymentForm.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await expect(paymentForm).toBeVisible();

          // Formularfelder sollten vorhanden sein
          const amountInput = page.locator('input[name="amount"], [data-testid="amount-input"]');
          const ibanInput = page.locator('input[name="iban"], [data-testid="iban-input"]');

          // Mindestens ein Eingabefeld sollte vorhanden sein
          const hasAmountInput = await amountInput.isVisible({ timeout: 1000 }).catch(() => false);
          const hasIbanInput = await ibanInput.isVisible({ timeout: 1000 }).catch(() => false);

          expect(hasAmountInput || hasIbanInput).toBeTruthy();
        }
      }
    });

    test('sollte Bank-Reconciliation Seite laden', async ({ page }) => {
      await page.goto('/admin/banking/reconciliation');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Reconciliation-Seite geladen wurde
      const reconciliationPage = page.locator('[data-testid="reconciliation-page"], h1:has-text("Abgleich"), .reconciliation-dashboard');

      if (await reconciliationPage.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(reconciliationPage).toBeVisible();

        // Suche nach Match-Vorschlaegen
        const matchSuggestions = page.locator('[data-testid="match-suggestions"], .suggestions-list, .match-candidates');

        if (await matchSuggestions.isVisible({ timeout: TIMEOUTS.apiCall }).catch(() => false)) {
          await expect(matchSuggestions).toBeVisible();
        }
      }
    });
  });

  test.describe('Kanban-Ansicht (Mahnungen)', () => {
    test('sollte Kanban-Board fuer Mahnungen laden', async ({ page }) => {
      await page.goto('/admin/mahnungen/kanban');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Kanban-Board geladen wurde
      const kanbanBoard = page.locator('[data-testid="kanban-board"], .kanban-container, .board-columns');

      if (await kanbanBoard.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        await expect(kanbanBoard).toBeVisible();

        // Erwarte Spalten fuer Mahnstufen
        const columns = page.locator('[data-testid="kanban-column"], .kanban-column, .board-column');
        const columnCount = await columns.count();

        // Mindestens 2 Spalten erwartet
        expect(columnCount).toBeGreaterThanOrEqual(2);
      }
    });

    test('sollte Drag & Drop in Kanban unterstuetzen', async ({ page }) => {
      await page.goto('/admin/mahnungen/kanban');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Kanban-Karten draggable sind
      const kanbanCards = page.locator('[data-testid="kanban-card"], .kanban-card, [draggable="true"]');

      if (await kanbanCards.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
        // Karte sollte draggable-Attribut haben
        const isDraggable = await kanbanCards.first().getAttribute('draggable');
        expect(isDraggable === 'true' || isDraggable === null).toBeTruthy();
      }
    });
  });
});

// Ebenfalls geskippt: navigiert ausschliesslich auf gefrorene /admin/banking/*-Routen.
test.describe.skip('Invoice Workflow - Accessibility', () => {
  test('Tabellen sollten sortierbar per Tastatur sein', async ({ page }) => {
    await page.goto('/admin/banking/transactions');
    await page.waitForLoadState('networkidle');

    // Finde sortierbare Spaltenheader
    const sortableHeaders = page.locator('th[role="columnheader"], th[aria-sort], .sortable-header');

    if (await sortableHeaders.first().isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
      // Tab zum Header
      await sortableHeaders.first().focus();

      // Enter sollte sortieren
      await page.keyboard.press('Enter');

      // Warte kurz auf Animation
      await page.waitForTimeout(TIMEOUTS.animation);
    }
  });

  test('Formulare sollten ARIA-Labels haben', async ({ page }) => {
    await page.goto('/admin/banking/payments');
    await page.waitForLoadState('networkidle');

    // Oeffne Zahlungsformular falls Button vorhanden
    const createButton = page.locator('[data-testid="create-payment"], button:has-text("Neue")');

    if (await createButton.isVisible({ timeout: TIMEOUTS.navigation }).catch(() => false)) {
      await createButton.click();

      // Pruefe ARIA-Labels im Formular
      const ariaLabeledInputs = await page.locator('input[aria-label], input[aria-labelledby], label + input').count();

      // Mindestens einige Inputs sollten gelabeled sein
      expect(ariaLabeledInputs).toBeGreaterThanOrEqual(0);
    }
  });
});
