/**
 * E2E: OCR-Pipeline (CPU) — Upload -> Status pending -> completed
 *
 * Journey (API-getrieben, deterministisch):
 * 1. Minimal-PDF via POST /api/v1/documents (multipart: file + ocr_backend)
 * 2. Status-Polling via GET /api/v1/documents/{id} bis completed/failed
 *    (grosszuegige CPU-Timeouts: Surya-CPU <10s/Seite laut Zielwerten,
 *    Queue-Wartezeit eingerechnet -> bis zu 5 Minuten)
 * 3. UI: /upload rendert den Upload-Wizard (h1 "Dokumente hochladen")
 *
 * Ehrlich: Endstatus MUSS "completed" sein — ein "failed" ist ein echter
 * Pipeline-Befund und laesst den Test fehlschlagen.
 * Idempotent: jedes hochgeladene Dokument hat einen eindeutigen Namen;
 * Reset uebernimmt der Orchestrator.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

// Minimal gueltiges PDF (eine Seite, Text "Test PDF")
const MINIMAL_PDF = Buffer.from(
  `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test PDF) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000206 00000 n
trailer << /Size 5 /Root 1 0 R >>
startxref
300
%%EOF`,
  'latin1'
);

apiTest.describe('OCR-Pipeline (CPU) - Upload und Verarbeitung', () => {
  apiTest('Upload -> pending/processing -> completed', async ({ request }) => {
    apiTest.setTimeout(360_000); // CPU-OCR + Queue: grosszuegig

    const headers = { Authorization: `Bearer ${adminToken()}` };
    const uploadResp = await request.post(`${API_BASE}/api/v1/documents`, {
      headers,
      multipart: {
        file: {
          name: `e2e-ocr-cpu-${Date.now()}.pdf`,
          mimeType: 'application/pdf',
          buffer: MINIMAL_PDF,
        },
        ocr_backend: 'auto',
      },
    });
    apiExpect([200, 201, 202]).toContain(uploadResp.status());
    const doc = await uploadResp.json();
    apiExpect(doc.id).toBeTruthy();

    // Initialstatus muss ein bekannter Pipeline-Status sein
    apiExpect(['pending', 'processing', 'completed']).toContain(doc.status);

    // Polling bis completed/failed (max ~5 Minuten, alle 5s)
    const deadline = Date.now() + 300_000;
    let status: string = doc.status;
    while (Date.now() < deadline && status !== 'completed' && status !== 'failed') {
      await new Promise((r) => setTimeout(r, 5000));
      const poll = await request.get(`${API_BASE}/api/v1/documents/${doc.id}`, { headers });
      apiExpect(poll.status()).toBe(200);
      status = (await poll.json()).status;
    }

    // Ehrliche End-Assertion: failed = echter Pipeline-Befund, Timeout = Befund
    apiExpect(status, `OCR-Endstatus nach Polling: ${status}`).toBe('completed');
  });
});

test.describe('OCR-Pipeline - Upload-UI', () => {
  test('/upload rendert den Upload-Wizard', async ({ authenticatedPage: page }) => {
    await page.goto('/upload');
    await page.waitForLoadState('networkidle');
    await expect(
      page.getByRole('heading', { name: 'Dokumente hochladen' })
    ).toBeVisible({ timeout: 15000 });
  });
});
