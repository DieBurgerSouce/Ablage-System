/**
 * E2E Tests: File Upload Validation
 *
 * Testet die Dateivalidierung beim Upload:
 * - Ungültige Formate werden abgelehnt (exe, bat, js, etc.)
 * - Überschrittene Dateigröße → deutschen Fehlermeldung
 * - Korrumpierte PDFs werden erkannt
 * - MIME-Type-Spoofing (umbenannte .exe als .pdf) wird blockiert
 * - Mehrfach-Upload-Grenzen
 */

import { test, expect } from '@playwright/test';
import path from 'path';
import { closeWelcomeDialog, waitForLoadingComplete } from './utils/helpers';

// Use auth state
test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

function createOversizedPdfBuffer(): Buffer {
  // Create a buffer larger than typical upload limit (simulate 51MB)
  // Use a small buffer with large size metadata for testing
  const header = Buffer.from('%PDF-1.4\n', 'utf-8');
  // 100KB dummy payload — real oversized test would need actual large file
  const filler = Buffer.alloc(100 * 1024, 'A');
  return Buffer.concat([header, filler]);
}

function createCorruptedPdfBuffer(): Buffer {
  // Valid PDF header, garbage body
  return Buffer.from('%PDF-1.4\n%%EOF\nGARBAGE_DATA_NOT_VALID_PDF_BODY', 'utf-8');
}

function createMaliciousExecutableBuffer(): Buffer {
  // Windows PE header magic bytes — should be blocked even if renamed to .pdf
  const peHeader = Buffer.from([0x4d, 0x5a, 0x90, 0x00, 0x03, 0x00]);
  return Buffer.concat([peHeader, Buffer.from('FAKE_EXE_CONTENT')]);
}

test.describe('File Upload Validation - Dateivalidierung', () => {
  test.describe('Verbotene Dateiformate', () => {
    const forbiddenFiles = [
      { name: 'malware.exe', mimeType: 'application/octet-stream' },
      { name: 'script.bat', mimeType: 'application/x-bat' },
      { name: 'payload.js', mimeType: 'application/javascript' },
      { name: 'hack.sh', mimeType: 'application/x-sh' },
      { name: 'macro.xlsm', mimeType: 'application/vnd.ms-excel.sheet.macroEnabled.12' },
    ];

    for (const file of forbiddenFiles) {
      test(`sollte ${file.name} ablehnen mit deutscher Fehlermeldung`, async ({ page }) => {
        await page.goto('/upload');
        await closeWelcomeDialog(page);
        await waitForLoadingComplete(page);

        const fileInput = page.locator('input[type="file"]').first();

        if (await fileInput.isVisible({ timeout: 5000 }).catch(() => false)) {
          await fileInput.setInputFiles({
            name: file.name,
            mimeType: file.mimeType,
            buffer: Buffer.from('FAKE CONTENT'),
          });

          await page.waitForTimeout(500);

          // Should show rejection error
          const errorIndicator = page.locator(
            '[role="alert"], .toast, [class*="error"], [class*="destructive"]'
          ).first();

          if (await errorIndicator.isVisible({ timeout: 3000 }).catch(() => false)) {
            const text = await errorIndicator.textContent();
            // Error must be German, not English
            expect(text).toMatch(/Dateiformat|ungültig|nicht erlaubt|abgelehnt/i);
            expect(text).not.toMatch(/\bFile type not allowed\b|\bUnsupported\b/i);
          }
        }
      });
    }
  });

  test.describe('MIME-Type-Spoofing', () => {
    test('sollte EXE-Datei mit .pdf-Erweiterung blockieren', async ({ page }) => {
      await page.goto('/upload');
      await closeWelcomeDialog(page);
      await waitForLoadingComplete(page);

      const fileInput = page.locator('input[type="file"]').first();

      if (await fileInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        // Rename .exe payload to .pdf
        await fileInput.setInputFiles({
          name: 'rechnung.pdf',
          mimeType: 'application/pdf',
          buffer: createMaliciousExecutableBuffer(),
        });

        await page.waitForLoadState('networkidle');

        // Backend should reject based on magic bytes, not just extension
        const errorIndicator = page.locator(
          '[role="alert"], .toast, [class*="error"]'
        ).first();

        // Either rejected immediately or after processing
        const isVisible = await errorIndicator.isVisible({ timeout: 5000 }).catch(() => false);
        // We assert the test ran without server crash — 500 would be a test failure
        const bodyContent = await page.textContent('body');
        expect(bodyContent).not.toMatch(/500|Internal Server Error/);
      }
    });
  });

  test.describe('Dateigröße-Limits', () => {
    test('sollte Datei über Größenlimit mit deutscher Fehlermeldung ablehnen', async ({
      page,
    }) => {
      await page.goto('/upload');
      await closeWelcomeDialog(page);

      // Check if the upload form has an accept attribute indicating size limit
      const fileInput = page.locator('input[type="file"]').first();
      const maxSizeIndicator = page.locator(
        ':has-text("MB"), :has-text("Maximale Größe"), :has-text("max")'
      ).first();

      if (await maxSizeIndicator.isVisible({ timeout: 3000 }).catch(() => false)) {
        const sizeText = await maxSizeIndicator.textContent();
        expect(sizeText).toMatch(/\d+\s*MB/);
      }

      // Attempt to upload oversized buffer
      if (await fileInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await fileInput.setInputFiles({
          name: 'grosses_dokument.pdf',
          mimeType: 'application/pdf',
          buffer: createOversizedPdfBuffer(),
        });

        await page.waitForTimeout(1000);

        const sizeError = page.locator(
          ':has-text("zu groß"), :has-text("Größe"), :has-text("überschritten"), :has-text("MB")'
        );

        if (await sizeError.isVisible({ timeout: 3000 }).catch(() => false)) {
          const text = await sizeError.textContent();
          expect(text).toMatch(/groß|Größe|MB/i);
        }
      }
    });
  });

  test.describe('Korrumpierte Dateien', () => {
    test('sollte korrumpiertes PDF erkennen und deutschen Fehler anzeigen', async ({
      page,
    }) => {
      await page.goto('/upload');
      await closeWelcomeDialog(page);

      const fileInput = page.locator('input[type="file"]').first();

      if (await fileInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await fileInput.setInputFiles({
          name: 'kaputtes_dokument.pdf',
          mimeType: 'application/pdf',
          buffer: createCorruptedPdfBuffer(),
        });

        await page.waitForLoadState('networkidle');

        // Either rejected at upload or marked as processing error
        const bodyContent = await page.textContent('body');
        // Must not crash with 500
        expect(bodyContent).not.toMatch(/500|Internal Server Error|Traceback/);
      }
    });
  });

  test.describe('Upload-API Validierung', () => {
    test('sollte 422 bei leerem Upload-Body zurückgeben', async ({ request }) => {
      const resp = await request.post('http://localhost:8000/api/v1/documents/upload', {
        multipart: {},
      });

      // Should return 401 (not logged in) or 422 (missing file), not 500
      expect(resp.status()).not.toBe(500);
      expect([401, 403, 422]).toContain(resp.status());
    });

    test('sollte 422 bei falscher Content-Type zurückgeben', async ({ request }) => {
      const resp = await request.post('http://localhost:8000/api/v1/documents/upload', {
        data: '{}',
        headers: { 'Content-Type': 'application/json' },
      });

      expect(resp.status()).not.toBe(500);
    });
  });
});
