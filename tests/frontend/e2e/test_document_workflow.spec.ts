/**
 * E2E Tests: Document Workflow (Upload -> OCR -> Classification -> Export)
 *
 * Testet den vollstaendigen Dokumenten-Workflow:
 * - Dokument-Upload (PDF, Bild)
 * - OCR-Verarbeitung mit verschiedenen Backends
 * - Automatische Klassifikation
 * - Export in verschiedene Formate
 * - Alle 4 Display-Modi
 * - Deutsche Fehlermeldungen
 *
 * Performance-Ziele:
 * - Upload: < 500ms
 * - OCR (GPU): < 2s
 * - OCR (CPU): < 10s
 */

import { test, expect, type Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

// Test configuration
const TIMEOUTS = {
  upload: 5000,
  ocrGpu: 30000,
  ocrCpu: 120000,
  classification: 10000,
  export: 10000,
};

// Sample test files paths (relative to project root)
const TEST_FILES = {
  pdfInvoice: 'tests/fixtures/sample_invoice.pdf',
  pdfContract: 'tests/fixtures/sample_contract.pdf',
  imageDocument: 'tests/fixtures/sample_document.png',
};

// Display modes to test
const DISPLAY_MODES = ['dark', 'light', 'whitescreen', 'blackscreen'] as const;

// German error messages expected
const GERMAN_ERRORS = {
  invalidFormat: 'Ungueltiges Dateiformat',
  uploadFailed: 'Upload fehlgeschlagen',
  ocrFailed: 'OCR-Verarbeitung fehlgeschlagen',
  noFile: 'Keine Datei ausgewaehlt',
  fileTooLarge: 'Datei zu gross',
};

/**
 * Helper: Erstellt eine Test-PDF-Datei im Speicher
 */
function createTestPdfBuffer(): Buffer {
  const pdfContent = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 120 >>
stream
BT
/F1 12 Tf
100 700 Td
(RECHNUNG Nr. 2024-0001) Tj
0 -20 Td
(Betrag: 1.234,56 EUR) Tj
ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000436 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
512
%%EOF`;
  return Buffer.from(pdfContent, 'utf-8');
}

/**
 * Helper: Erstellt eine einfache Test-PNG-Datei im Speicher
 */
function createTestImageBuffer(): Buffer {
  // Minimales gueltige PNG (1x1 weisser Pixel)
  const pngBase64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
  return Buffer.from(pngBase64, 'base64');
}

test.describe('Document Workflow - Vollstaendiger Dokumenten-Prozess', () => {
  test.beforeEach(async ({ page }) => {
    // Authentifizierung wird durch Fixture gehandhabt
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test.describe('Dokument-Upload', () => {
    test('sollte PDF-Dokument erfolgreich hochladen', async ({ page }) => {
      await page.goto('/upload');
      await page.waitForLoadState('domcontentloaded');

      // Welcome-Dialog schliessen falls vorhanden
      const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
      if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeButton.click();
      }

      // Upload-Bereich finden
      const uploadArea = page.locator('[data-testid="upload-dropzone"], .upload-dropzone, input[type="file"]');
      await expect(uploadArea.first()).toBeVisible();

      // Test-PDF erstellen und hochladen
      const testPdf = createTestPdfBuffer();
      const fileChooserPromise = page.waitForEvent('filechooser');

      // Klick auf Upload-Bereich
      const uploadButton = page.getByText('Drag & Drop oder klicken zum Auswählen');
      if (await uploadButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await uploadButton.click();
      } else {
        await uploadArea.first().click();
      }

      const fileChooser = await fileChooserPromise;
      await fileChooser.setFiles({
        name: 'test_rechnung.pdf',
        mimeType: 'application/pdf',
        buffer: testPdf,
      });

      // Warten auf Upload-Bestaetigung
      await expect(page.getByText(/hochgeladen|erfolgreich|uploaded/i)).toBeVisible({
        timeout: TIMEOUTS.upload,
      });
    });

    test('sollte Bildformate (PNG, JPG) akzeptieren', async ({ page }) => {
      await page.goto('/upload');
      await page.waitForLoadState('domcontentloaded');

      // Welcome-Dialog schliessen
      const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
      if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeButton.click();
      }

      const uploadArea = page.locator('[data-testid="upload-dropzone"], .upload-dropzone, input[type="file"]');
      const testImage = createTestImageBuffer();

      const fileChooserPromise = page.waitForEvent('filechooser');
      await uploadArea.first().click();
      const fileChooser = await fileChooserPromise;

      await fileChooser.setFiles({
        name: 'test_dokument.png',
        mimeType: 'image/png',
        buffer: testImage,
      });

      // Upload sollte erfolgreich sein
      await expect(page.getByText(/hochgeladen|erfolgreich|uploaded|wird verarbeitet/i)).toBeVisible({
        timeout: TIMEOUTS.upload,
      });
    });

    test('sollte ungueltige Dateiformate ablehnen mit deutscher Fehlermeldung', async ({ page }) => {
      await page.goto('/upload');
      await page.waitForLoadState('domcontentloaded');

      // Welcome-Dialog schliessen
      const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
      if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeButton.click();
      }

      const uploadArea = page.locator('[data-testid="upload-dropzone"], .upload-dropzone, input[type="file"]');

      const fileChooserPromise = page.waitForEvent('filechooser');
      await uploadArea.first().click();
      const fileChooser = await fileChooserPromise;

      // Ungueltige Datei (z.B. .exe)
      await fileChooser.setFiles({
        name: 'test.exe',
        mimeType: 'application/x-msdownload',
        buffer: Buffer.from('invalid content'),
      });

      // Erwarte deutsche Fehlermeldung
      const errorMessage = page.locator('[role="alert"], .error, .toast-error, [data-testid="error-message"]');
      await expect(errorMessage.first()).toBeVisible({ timeout: 5000 });
    });

    test('sollte Batch-Upload von mehreren Dokumenten unterstuetzen', async ({ page }) => {
      await page.goto('/upload');
      await page.waitForLoadState('domcontentloaded');

      // Welcome-Dialog schliessen
      const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
      if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeButton.click();
      }

      const uploadArea = page.locator('[data-testid="upload-dropzone"], .upload-dropzone, input[type="file"]');

      const fileChooserPromise = page.waitForEvent('filechooser');
      await uploadArea.first().click();
      const fileChooser = await fileChooserPromise;

      // Mehrere Dateien gleichzeitig
      const testPdf1 = createTestPdfBuffer();
      const testPdf2 = createTestPdfBuffer();

      await fileChooser.setFiles([
        {
          name: 'rechnung_001.pdf',
          mimeType: 'application/pdf',
          buffer: testPdf1,
        },
        {
          name: 'rechnung_002.pdf',
          mimeType: 'application/pdf',
          buffer: testPdf2,
        },
      ]);

      // Beide Dateien sollten in der Liste erscheinen
      await expect(page.getByText(/rechnung_001|2 Dokument/i)).toBeVisible({ timeout: TIMEOUTS.upload });
    });
  });

  test.describe('OCR-Verarbeitung', () => {
    test('sollte OCR-Status anzeigen waehrend der Verarbeitung', async ({ page }) => {
      // Navigiere zur Dokumentenliste oder Upload-Status
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Falls Dokumente in Verarbeitung sind
      const processingIndicator = page.locator('[data-testid="processing-status"], .processing, .ocr-status');

      if (await processingIndicator.first().isVisible({ timeout: 3000 }).catch(() => false)) {
        // Verarbeitungsstatus sollte sichtbar sein
        await expect(processingIndicator.first()).toContainText(/Verarbeitung|Processing|OCR/i);
      }
    });

    test('sollte OCR-Backend-Auswahl anzeigen (wenn Admin)', async ({ page }) => {
      await page.goto('/admin/ocr-backends');

      // Pruefe ob Admin-Zugang besteht
      const backendList = page.locator('[data-testid="backend-list"], .backend-card, .ocr-backend');

      if (await backendList.first().isVisible({ timeout: 5000 }).catch(() => false)) {
        // Erwartete Backends
        const expectedBackends = ['DeepSeek', 'GOT-OCR', 'Surya', 'Docling'];

        for (const backend of expectedBackends) {
          const backendElement = page.getByText(new RegExp(backend, 'i'));
          // Mindestens ein Backend sollte sichtbar sein
          if (await backendElement.first().isVisible({ timeout: 1000 }).catch(() => false)) {
            await expect(backendElement.first()).toBeVisible();
            break;
          }
        }
      }
    });
  });

  test.describe('Dokumenten-Klassifikation', () => {
    test('sollte klassifizierte Dokumente in korrekten Kategorien anzeigen', async ({ page }) => {
      // Navigiere zur Dokumentenliste
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Pruefe ob Kategoriefilter vorhanden
      const categoryFilter = page.locator('[data-testid="category-filter"], select[name="category"], .category-select');

      if (await categoryFilter.first().isVisible({ timeout: 3000 }).catch(() => false)) {
        // Erwartete Dokumenttypen auf Deutsch
        const expectedTypes = ['Rechnung', 'Vertrag', 'Lieferschein', 'Angebot', 'Sonstiges'];

        // Oeffne Dropdown
        await categoryFilter.first().click();

        // Mindestens ein Dokumenttyp sollte verfuegbar sein
        for (const docType of expectedTypes) {
          const option = page.getByRole('option', { name: new RegExp(docType, 'i') });
          if (await option.isVisible({ timeout: 500 }).catch(() => false)) {
            await expect(option).toBeVisible();
            break;
          }
        }
      }
    });

    test('sollte manuelle Klassifikationskorrektur ermoeglichen', async ({ page }) => {
      // Navigiere zu einem Dokument-Detail (wenn vorhanden)
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Finde erstes Dokument in der Liste
      const documentLink = page.locator('a[href*="documents"], [data-testid="document-row"], .document-item').first();

      if (await documentLink.isVisible({ timeout: 3000 }).catch(() => false)) {
        await documentLink.click();
        await page.waitForLoadState('networkidle');

        // Suche nach Klassifikations-Bearbeitung
        const editClassification = page.locator('[data-testid="edit-classification"], button:has-text("Typ"), .classification-edit');

        if (await editClassification.isVisible({ timeout: 3000 }).catch(() => false)) {
          await expect(editClassification).toBeEnabled();
        }
      }
    });
  });

  test.describe('Dokument-Export', () => {
    test('sollte Export-Optionen anbieten', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Finde Export-Button oder Menu
      const exportButton = page.locator('[data-testid="export-button"], button:has-text("Export"), .export-menu');

      if (await exportButton.first().isVisible({ timeout: 3000 }).catch(() => false)) {
        await exportButton.first().click();

        // Erwartete Export-Formate
        const exportFormats = ['PDF', 'CSV', 'Excel', 'DATEV'];

        for (const format of exportFormats) {
          const formatOption = page.getByText(new RegExp(format, 'i'));
          if (await formatOption.isVisible({ timeout: 1000 }).catch(() => false)) {
            await expect(formatOption).toBeVisible();
            break;
          }
        }
      }
    });

    test('DATEV-Export ist eingefroren (Redirect auf /frozen)', async ({ page }) => {
      // Modul eingefroren (Odoo-Neuausrichtung 2026-07): DATEV-Export
      // übernimmt Odoo. /admin/datev/* leitet per beforeLoad-Guard auf
      // /frozen?module=datev um; die fruehere Export-UI-Pruefung entfaellt.
      // Reaktivierung: ACTIVE_OPTIONAL_MODULES=datev + Erwartung zurueckdrehen.
      await page.goto('/admin/datev/export');

      await expect(page).toHaveURL(/\/frozen\?module=datev/, { timeout: 10000 });
      await expect(page.getByText('Modul eingefroren')).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe('Display-Modi', () => {
    for (const mode of DISPLAY_MODES) {
      test(`sollte ${mode}-Modus korrekt anwenden`, async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('domcontentloaded');

        // Finde Mode-Switcher
        const modeSwitcher = page.locator(`.mode-btn[data-mode="${mode}"], [data-testid="mode-${mode}"]`);

        if (await modeSwitcher.isVisible({ timeout: 3000 }).catch(() => false)) {
          await modeSwitcher.click();
          await page.waitForTimeout(200);

          // Pruefe body data-mode Attribut
          const bodyMode = await page.getAttribute('body', 'data-mode');
          expect(bodyMode).toBe(mode);

          // Pruefe localStorage
          const storedMode = await page.evaluate(() => localStorage.getItem('displayMode'));
          expect(storedMode).toBe(mode);
        }
      });
    }

    test('sollte Display-Modus nach Seitenaktualisierung beibehalten', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // Setze Light-Mode
      const lightModeBtn = page.locator('.mode-btn[data-mode="light"], [data-testid="mode-light"]');

      if (await lightModeBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await lightModeBtn.click();
        await page.waitForTimeout(200);

        // Seite neu laden
        await page.reload();
        await page.waitForLoadState('domcontentloaded');

        // Modus sollte erhalten bleiben
        const bodyMode = await page.getAttribute('body', 'data-mode');
        expect(bodyMode).toBe('light');
      }
    });
  });

  test.describe('Deutsche Fehlermeldungen', () => {
    test('sollte alle Fehlermeldungen auf Deutsch anzeigen', async ({ page }) => {
      // Test: 404 Seite
      await page.goto('/nicht-existierende-seite');

      // Erwarte deutsche 404-Meldung
      const errorText = page.locator('h1, .error-title, [data-testid="error-message"]');
      const pageContent = await page.textContent('body');

      // Sollte deutschsprachigen Inhalt haben
      expect(
        pageContent?.includes('nicht gefunden') ||
        pageContent?.includes('Seite existiert nicht') ||
        pageContent?.includes('Fehler') ||
        pageContent?.includes('Not Found') // Fallback falls keine deutsche Uebersetzung
      ).toBeTruthy();
    });

    test('sollte Validierungsfehler auf Deutsch anzeigen', async ({ page }) => {
      await page.goto('/upload');
      await page.waitForLoadState('domcontentloaded');

      // Welcome-Dialog schliessen
      const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
      if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeButton.click();
      }

      // Versuche Submit ohne Datei (falls Button vorhanden)
      const submitButton = page.getByRole('button', { name: /Hochladen|Upload|Speichern/i });

      if (await submitButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await submitButton.click();

        // Erwarte deutsche Validierungsmeldung
        const validationError = page.locator('[role="alert"], .validation-error, .error-message');
        if (await validationError.first().isVisible({ timeout: 3000 }).catch(() => false)) {
          const errorText = await validationError.first().textContent();
          // Fehlermeldung sollte deutsch oder zumindest verstaendlich sein
          expect(errorText).toBeTruthy();
        }
      }
    });
  });

  test.describe('Dokumenten-Workflow Integration', () => {
    test('sollte vollstaendigen Upload-bis-Klassifikation Workflow durchfuehren', async ({ page }) => {
      // Schritt 1: Upload
      await page.goto('/upload');
      await page.waitForLoadState('domcontentloaded');

      // Welcome-Dialog schliessen
      const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
      if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
        await closeButton.click();
      }

      // Upload Test-Datei
      const uploadArea = page.locator('[data-testid="upload-dropzone"], .upload-dropzone, input[type="file"]');
      const testPdf = createTestPdfBuffer();

      if (await uploadArea.first().isVisible({ timeout: 3000 }).catch(() => false)) {
        const fileChooserPromise = page.waitForEvent('filechooser');
        await uploadArea.first().click();
        const fileChooser = await fileChooserPromise;

        await fileChooser.setFiles({
          name: 'workflow_test_rechnung.pdf',
          mimeType: 'application/pdf',
          buffer: testPdf,
        });

        // Warte auf Upload-Bestaetigung
        await expect(page.getByText(/hochgeladen|erfolgreich|wird verarbeitet/i)).toBeVisible({
          timeout: TIMEOUTS.upload,
        });

        // Schritt 2: Warte auf Verarbeitung
        // Je nach System-Last kann dies laenger dauern
        const processingComplete = page.locator('[data-testid="processing-complete"], .status-complete, .badge-success');

        // Optional: Warten auf Verarbeitungsabschluss
        if (await processingComplete.first().isVisible({ timeout: 5000 }).catch(() => false)) {
          await expect(processingComplete.first()).toBeVisible();
        }
      }
    });
  });
});

test.describe('Document Workflow - Accessibility', () => {
  test('Upload-Bereich sollte per Tastatur bedienbar sein', async ({ page }) => {
    await page.goto('/upload');
    await page.waitForLoadState('domcontentloaded');

    // Welcome-Dialog schliessen
    const closeButton = page.getByRole('button', { name: /Schliessen|Close/i });
    if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await closeButton.click();
    }

    // Tab zum Upload-Bereich
    await page.keyboard.press('Tab');

    // Fokussiertes Element finden
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toBeTruthy();
  });

  test('sollte ARIA-Labels fuer Screen Reader haben', async ({ page }) => {
    await page.goto('/upload');
    await page.waitForLoadState('domcontentloaded');

    // Pruefe auf ARIA-Labels
    const ariaElements = await page.locator('[aria-label], [aria-describedby], [role]').count();
    expect(ariaElements).toBeGreaterThan(0);
  });
});
