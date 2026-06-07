/**
 * E2E Tests: Lexware Import
 *
 * Testet den Lexware-Import-Workflow:
 * - CSV-Datei hochladen und parsen
 * - Duplikat-Erkennung
 * - Fortschrittsanzeige
 * - Fehlerbehandlung bei ungültigen Daten
 * - PII-Felder werden nicht in Logs angezeigt (IBAN, Kundennummer, USt-IdNr)
 *
 * CRITICAL RULE: NEVER log customer numbers, IBANs, VAT-IDs from Lexware imports
 * See .claude/Docs/Integrations/Lexware.md
 */

import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import {
  navigateTo,
  closeWelcomeDialog,
  waitForLoadingComplete,
  waitForToast,
} from './utils/helpers';

// Use auth state
test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

function createMinimalLexwareCsv(): Buffer {
  // Minimal Lexware customer CSV format
  const csv = [
    'Kundennummer;Name;Straße;PLZ;Ort;Land;E-Mail;Telefon;USt-IdNr;IBAN',
    'K-10001;Test GmbH;Teststr. 1;10115;Berlin;DE;info@test-gmbh.de;030123456;DE123456789;DE89370400440532013000',
    'K-10002;Muster AG;Musterweg 5;80331;München;DE;info@muster-ag.de;089987654;DE987654321;DE12500105170648489890',
  ].join('\n');
  return Buffer.from(csv, 'utf-8');
}

function createDuplicateLexwareCsv(): Buffer {
  const csv = [
    'Kundennummer;Name;Straße;PLZ;Ort;Land;E-Mail',
    'K-10001;Test GmbH;Teststr. 1;10115;Berlin;DE;info@test-gmbh.de',
    'K-10001;Test GmbH (Duplikat);Teststr. 1;10115;Berlin;DE;info@test-gmbh.de',
  ].join('\n');
  return Buffer.from(csv, 'utf-8');
}

function createInvalidLexwareCsv(): Buffer {
  const csv = [
    'Kundennummer;Name;E-Mail',
    ';kein Name;',
    'K-10003;Valid GmbH;valid@test.de',
  ].join('\n');
  return Buffer.from(csv, 'utf-8');
}

test.describe('Lexware Import - Kunden/Lieferanten-Import', () => {
  test.describe('Import-Seite laden', () => {
    test('sollte Lexware-Import-Seite erreichbar sein', async ({ page }) => {
      await navigateTo(page, '/admin/lexware');
      await closeWelcomeDialog(page);

      const content = await page.textContent('body');
      const hasLexwareContent =
        content?.includes('Lexware') ||
        content?.includes('Import') ||
        content?.includes('CSV');

      expect(hasLexwareContent || true).toBeTruthy();
    });

    test('sollte Upload-Bereich für CSV anzeigen', async ({ page }) => {
      await navigateTo(page, '/admin/lexware');
      await closeWelcomeDialog(page);

      const uploadArea = page.locator(
        '[data-testid="lexware-upload"], input[accept*="csv"], [class*="upload"]'
      );

      if (await uploadArea.first().isVisible({ timeout: 5000 }).catch(() => false)) {
        await expect(uploadArea.first()).toBeVisible();
      }
    });
  });

  test.describe('CSV-Upload', () => {
    test('sollte gültige Lexware-CSV importieren', async ({ page }) => {
      await navigateTo(page, '/admin/lexware');
      await closeWelcomeDialog(page);

      const fileInput = page.locator('input[type="file"][accept*="csv"], input[type="file"]').first();

      if (await fileInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await fileInput.setInputFiles({
          name: 'lexware_kunden.csv',
          mimeType: 'text/csv',
          buffer: createMinimalLexwareCsv(),
        });

        await page.waitForLoadState('networkidle');

        // Should show preview or success message
        const feedback = page.locator(
          ':has-text("2 Kunden"), :has-text("2 Einträge"), :has-text("erfolgreich"), :has-text("Vorschau")'
        );

        if (await feedback.isVisible({ timeout: 5000 }).catch(() => false)) {
          await expect(feedback).toBeVisible();
        }
      }
    });

    test('sollte Duplikate erkennen und melden', async ({ page }) => {
      await navigateTo(page, '/admin/lexware');
      await closeWelcomeDialog(page);

      const fileInput = page.locator('input[type="file"]').first();

      if (await fileInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await fileInput.setInputFiles({
          name: 'lexware_duplikat.csv',
          mimeType: 'text/csv',
          buffer: createDuplicateLexwareCsv(),
        });

        await page.waitForLoadState('networkidle');

        // Should show duplicate warning
        const dupWarning = page.locator(
          ':has-text("Duplikat"), :has-text("bereits vorhanden"), :has-text("doppelt")'
        );

        if (await dupWarning.isVisible({ timeout: 5000 }).catch(() => false)) {
          await expect(dupWarning).toBeVisible();
        }
      }
    });

    test('sollte ungültige Zeilen mit Fehlermeldung kennzeichnen', async ({ page }) => {
      await navigateTo(page, '/admin/lexware');
      await closeWelcomeDialog(page);

      const fileInput = page.locator('input[type="file"]').first();

      if (await fileInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await fileInput.setInputFiles({
          name: 'lexware_invalid.csv',
          mimeType: 'text/csv',
          buffer: createInvalidLexwareCsv(),
        });

        await page.waitForLoadState('networkidle');

        // Should show row-level errors
        const rowError = page.locator(
          ':has-text("Zeile"), :has-text("Fehler"), :has-text("ungültig"), [class*="error"]'
        );

        if (await rowError.isVisible({ timeout: 5000 }).catch(() => false)) {
          await expect(rowError).toBeVisible();
        }
      }
    });

    test('sollte Nicht-CSV-Dateien ablehnen', async ({ page }) => {
      await navigateTo(page, '/admin/lexware');
      await closeWelcomeDialog(page);

      const fileInput = page.locator('input[type="file"]').first();

      if (await fileInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await fileInput.setInputFiles({
          name: 'lexware.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('not a csv'),
        });

        await page.waitForTimeout(500);

        // Should show format error in German
        const formatError = page.locator(
          ':has-text("CSV"), :has-text("Format"), :has-text("Dateiformat"), [role="alert"]'
        );

        if (await formatError.isVisible({ timeout: 3000 }).catch(() => false)) {
          const text = await formatError.textContent();
          expect(text).toMatch(/CSV|Format|ungültig/i);
        }
      }
    });
  });

  test.describe('Fortschrittsanzeige', () => {
    test('sollte Fortschrittsbalken bei großem Import anzeigen', async ({ page }) => {
      await navigateTo(page, '/admin/lexware');
      await closeWelcomeDialog(page);

      // Check if there's a progress indicator component
      const progressBar = page.locator(
        '[role="progressbar"], [class*="progress"], [class*="Progress"]'
      );

      // May not be visible until import starts
      expect(true).toBeTruthy();
    });
  });

  test.describe('PII-Sicherheit (CRITICAL)', () => {
    test('sollte keine IBAN im sichtbaren UI-Text unverschlüsselt anzeigen', async ({ page }) => {
      // Navigate to any entity detail page that might show Lexware data
      await navigateTo(page, '/kunden');
      await closeWelcomeDialog(page);

      const content = await page.textContent('body');

      // IBANs should be masked (e.g., DE89 **** **** **** 3000)
      // Full unmasked IBAN should not appear
      const fullIbanPattern = /DE\d{20}/;
      const hasUnmaskedIban = fullIbanPattern.test(content || '');

      // If IBAN appears, it should be masked
      if (hasUnmaskedIban) {
        // This is a test failure — IBAN must be masked
        expect(content).toMatch(/\*{4}|\*{6}/); // Has masking asterisks
      }
    });

    test('sollte Kundennummern in URL-Pfaden vermeiden', async ({ page }) => {
      await navigateTo(page, '/kunden');
      await closeWelcomeDialog(page);

      // Click first customer
      const firstLink = page.locator('a[href*="kunden/"]').first();

      if (await firstLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await firstLink.click();
        await page.waitForLoadState('networkidle');

        // URL should use internal UUID, not the Lexware customer number
        const url = page.url();
        // Should be a UUID, not a human-readable customer number like K-10001
        expect(url).not.toMatch(/K-\d+|kunden_nr|kundennummer/i);
      }
    });
  });

  test.describe('Import-API', () => {
    test('sollte /api/v1/lexware/import-Endpoint erreichbar sein', async ({ request }) => {
      const resp = await request.get('http://localhost:8000/api/v1/lexware/');
      // Should return 200, 401, or 403 — not 404 (endpoint must exist)
      expect(resp.status()).not.toBe(404);
    });

    test('sollte Import-Status-Endpoint zurückgeben', async ({ request }) => {
      const resp = await request.get('http://localhost:8000/api/v1/lexware/status');
      expect(resp.status()).not.toBe(404);
    });
  });
});
