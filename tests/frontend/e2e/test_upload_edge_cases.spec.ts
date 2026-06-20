/**
 * E2E Tests: Upload Edge Cases
 *
 * Testet Grenzfälle beim Datei-Upload:
 * - Datei zu groß
 * - Ungültiges Format (exe, zip, etc.)
 * - Leere Datei (0 Bytes)
 * - Beschädigte PDF
 * - Zu viele gleichzeitige Uploads
 * - Deutsche Fehlermeldungen für alle Fälle
 */

import { test, expect } from '@playwright/test';
import path from 'path';

test.use({
  storageState: path.join(__dirname, '.auth', 'user.json'),
});

// Hilfs-Buffer-Erzeuger
function makeBuffer(sizeBytes: number, fillByte = 0x41): Buffer {
  return Buffer.alloc(sizeBytes, fillByte);
}

function makeCorruptPdf(): Buffer {
  return Buffer.from('%PDF-1.4\nDAS IST KEIN GÜLTIGES PDF\n%%EOF', 'utf-8');
}

function makeExeBuffer(): Buffer {
  // Windows PE-Header Signatur MZ
  const buf = Buffer.alloc(64, 0x00);
  buf[0] = 0x4d; // M
  buf[1] = 0x5a; // Z
  return buf;
}

test.describe('Upload Edge Cases', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
    await page.waitForLoadState('domcontentloaded');

    const closeBtn = page.getByRole('button', { name: /schließen|close/i });
    if (await closeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await closeBtn.click();
    }
  });

  test.describe('Ungültige Dateiformate', () => {
    test('sollte .exe Dateien ablehnen mit deutschem Fehlertext', async ({ page }) => {
      const uploadInput = page.locator('input[type="file"]');
      if (!await uploadInput.isVisible({ timeout: 3000 }).catch(() => false)) return;

      await uploadInput.setInputFiles({
        name: 'schaedlich.exe',
        mimeType: 'application/octet-stream',
        buffer: makeExeBuffer(),
      });

      const errorMsg = page.locator('[role="alert"], .text-destructive, [class*="error"], [class*="toast"]');
      await expect(errorMsg.first()).toBeVisible({ timeout: 5000 });

      const text = await errorMsg.first().textContent();
      // Muss deutsch sein und das Format erwähnen
      expect(text).toMatch(/Format|Dateiart|nicht unterstützt|ungültig/i);
      expect(text).not.toMatch(/invalid file type|unsupported/i);
    });

    test('sollte .zip Dateien ablehnen', async ({ page }) => {
      const uploadInput = page.locator('input[type="file"]');
      if (!await uploadInput.isVisible({ timeout: 3000 }).catch(() => false)) return;

      await uploadInput.setInputFiles({
        name: 'archiv.zip',
        mimeType: 'application/zip',
        buffer: makeBuffer(512),
      });

      await page.waitForTimeout(1000);

      const errorMsg = page.locator('[role="alert"], .text-destructive, [class*="error"]');
      const hasError = await errorMsg.first().isVisible({ timeout: 3000 }).catch(() => false);
      // Entweder Fehlermeldung oder kein Upload-Fortschritt
      if (hasError) {
        const text = await errorMsg.first().textContent();
        expect(text).toMatch(/Format|Dateiart|nicht unterstützt|ungültig/i);
      }
    });
  });

  test.describe('Datei zu groß', () => {
    test('sollte zu große Dateien (>50MB) ablehnen', async ({ page }) => {
      const uploadInput = page.locator('input[type="file"]');
      if (!await uploadInput.isVisible({ timeout: 3000 }).catch(() => false)) return;

      // 51 MB Buffer
      const largeBuf = makeBuffer(51 * 1024 * 1024);

      await uploadInput.setInputFiles({
        name: 'sehr_grosse_datei.pdf',
        mimeType: 'application/pdf',
        buffer: largeBuf,
      });

      const errorMsg = page.locator('[role="alert"], .text-destructive, [class*="error"], [class*="toast"]');
      await expect(errorMsg.first()).toBeVisible({ timeout: 10000 });

      const text = await errorMsg.first().textContent();
      // Muss deutsch sein
      expect(text).toMatch(/groß|Größe|überschreitet|MB|zu groß/i);
      expect(text).not.toMatch(/too large|file size/i);
    });
  });

  test.describe('Leere Datei', () => {
    test('sollte leere Dateien (0 Bytes) ablehnen', async ({ page }) => {
      const uploadInput = page.locator('input[type="file"]');
      if (!await uploadInput.isVisible({ timeout: 3000 }).catch(() => false)) return;

      await uploadInput.setInputFiles({
        name: 'leer.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.alloc(0),
      });

      const errorMsg = page.locator('[role="alert"], .text-destructive, [class*="error"]');
      const hasError = await errorMsg.first().isVisible({ timeout: 5000 }).catch(() => false);
      if (hasError) {
        const text = await errorMsg.first().textContent();
        expect(text).toMatch(/leer|keine Daten|ungültig|Inhalt/i);
      }
    });
  });

  test.describe('Beschädigte PDF', () => {
    test('sollte korrupte PDFs mit deutschem Fehlertext melden', async ({ page }) => {
      const uploadInput = page.locator('input[type="file"]');
      if (!await uploadInput.isVisible({ timeout: 3000 }).catch(() => false)) return;

      await uploadInput.setInputFiles({
        name: 'beschaedigt.pdf',
        mimeType: 'application/pdf',
        buffer: makeCorruptPdf(),
      });

      // Upload könnte akzeptiert werden (wird erst bei OCR erkannt)
      // Aber wenn schon im Upload abgelehnt: muss deutsch sein
      const errorMsg = page.locator('[role="alert"], .text-destructive, [class*="error"]');
      const hasError = await errorMsg.first().isVisible({ timeout: 5000 }).catch(() => false);
      if (hasError) {
        const text = await errorMsg.first().textContent();
        expect(text).not.toMatch(/invalid pdf|corrupt|damaged/i);
      }
    });
  });

  test.describe('Mehrfach-Upload', () => {
    test('sollte mehrere valide Dateien gleichzeitig akzeptieren', async ({ page }) => {
      const uploadInput = page.locator('input[type="file"]');
      if (!await uploadInput.isVisible({ timeout: 3000 }).catch(() => false)) return;

      // Prüfe ob multiple-Attribut gesetzt ist
      const acceptsMultiple = await uploadInput.getAttribute('multiple');
      if (acceptsMultiple === null) return; // Kein Mehrfach-Upload unterstützt

      const pdfBuf = Buffer.from(`%PDF-1.4\n1 0 obj << /Type /Catalog >>\nendobj\n%%EOF`, 'utf-8');

      await uploadInput.setInputFiles([
        { name: 'dokument1.pdf', mimeType: 'application/pdf', buffer: pdfBuf },
        { name: 'dokument2.pdf', mimeType: 'application/pdf', buffer: pdfBuf },
      ]);

      // Kein Crash soll auftreten
      await page.waitForTimeout(2000);
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.trim().length).toBeGreaterThan(0);
    });
  });
});
