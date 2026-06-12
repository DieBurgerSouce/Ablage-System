/**
 * E2E: Ablage-Vorschlag Accept-Flow (W3-F1 Vertrauens-Loop)
 *
 * Journey (API-getrieben, da der Vorschlag asynchron nach Upload entsteht):
 * 1. Dokument hochladen (POST /api/v1/documents)
 * 2. Vorschlaege abrufen: GET /api/v1/automation/filing-suggestions/{docId}
 *    (Antwort: Liste, ggf. leer — beides legitime, ehrliche Zustaende)
 * 3. Accept: POST /api/v1/automation/filing-suggestions/{docId}/accept
 *    mit target_category (vorgeschlagene oder explizit gewaehlte Kategorie)
 *    -> 200 und Bestaetigung
 *
 * Verifizierte Vertragsdetails aus frontend/src/lib/api/services/automation.ts
 * und tests/integration/test_filing_accept.py.
 * Idempotent: eigenes frisches Dokument pro Lauf.
 */

import { test as apiTest, expect as apiExpect } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

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
<< /Length 52 >>
stream
BT /F1 12 Tf 100 700 Td (Rechnung E2E Filing) Tj ET
endstream
endobj
trailer << /Size 5 /Root 1 0 R >>
%%EOF`,
  'latin1'
);

apiTest.describe('Ablage-Vorschlag (W3-F1)', () => {
  apiTest('Upload -> Vorschlaege abrufen -> Accept setzt Kategorie', async ({ request }) => {
    apiTest.setTimeout(120_000);
    const headers = { Authorization: `Bearer ${adminToken()}` };

    // 1. Upload
    const uploadResp = await request.post(`${API_BASE}/api/v1/documents`, {
      headers,
      multipart: {
        file: {
          name: `e2e-filing-${Date.now()}.pdf`,
          mimeType: 'application/pdf',
          buffer: MINIMAL_PDF,
        },
        ocr_backend: 'auto',
      },
    });
    apiExpect([200, 201, 202]).toContain(uploadResp.status());
    const doc = await uploadResp.json();
    apiExpect(doc.id).toBeTruthy();

    // 2. Vorschlaege: Endpoint muss antworten (Liste, ggf. leer), kein 500
    const suggResp = await request.get(
      `${API_BASE}/api/v1/automation/filing-suggestions/${doc.id}`,
      { headers }
    );
    apiExpect(suggResp.status()).not.toBe(500);
    apiExpect(suggResp.status()).toBe(200);
    const suggestions = await suggResp.json();
    apiExpect(Array.isArray(suggestions)).toBeTruthy();

    // 3. Accept: vorgeschlagene Kategorie (falls vorhanden) oder explizite Wahl
    const targetCategory: string =
      suggestions.length > 0 && suggestions[0].category
        ? suggestions[0].category
        : 'rechnungen';

    const acceptResp = await request.post(
      `${API_BASE}/api/v1/automation/filing-suggestions/${doc.id}/accept`,
      { headers, data: { target_category: targetCategory } }
    );
    apiExpect(acceptResp.status()).not.toBe(500);
    apiExpect([200, 201]).toContain(acceptResp.status());
    const accepted = await acceptResp.json();
    // Vertrag aus test_filing_accept.py: Antwort enthaelt eine Bestaetigung
    apiExpect(accepted).toBeTruthy();
  });

  apiTest('Accept fuer fremdes/unbekanntes Dokument wird abgelehnt (kein 500)', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const resp = await request.post(
      `${API_BASE}/api/v1/automation/filing-suggestions/${fakeId}/accept`,
      {
        headers: { Authorization: `Bearer ${adminToken()}` },
        data: { target_category: 'rechnungen' },
      }
    );
    apiExpect(resp.status()).not.toBe(500);
    apiExpect([400, 403, 404, 422]).toContain(resp.status());
  });
});
