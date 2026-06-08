/**
 * E2E Tests: File Upload Validation
 *
 * Testet die Dateivalidierung beim Upload auf API-Ebene (deterministisch,
 * statt brittle UI-`if (visible)`-No-Ops):
 * - Verbotene Endungen (.exe/.bat/.js/.sh) -> 400 mit deutscher Fehlermeldung
 * - MIME-Spoofing (PE-Bytes als .pdf) -> 400 (Magic-Byte-Pruefung)
 * - Fehlende Datei / fehlender Name -> 4xx (kein 500-Crash)
 * - Upload ohne Auth -> abgewiesen (CSRF/401)
 * - Upload-Seite rendert ein Datei-Eingabefeld (authentifizierter UI-Smoke)
 *
 * Echter Endpoint: POST /api/v1/documents/ (app/api/v1/documents.py:188).
 * Wir nutzen den VIEWER-Token (genau EINE Company -> require_company ist
 * eindeutig, kein X-Company-ID noetig). Bearer-Auth umgeht CSRF
 * (csrf.py bearer_token_bypass=True). Validierung: Endung (Z.245) +
 * Magic-Byte-Pruefung (file_validation), beide mit deutscher Meldung.
 */

import { test, expect } from '@playwright/test';
import { viewerToken } from './utils/auth-cache';
import { test as authTest, expect as authExpect } from './fixtures';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';
const UPLOAD_URL = `${API_BASE}/api/v1/documents/`;

function authHeader() {
  return { Authorization: `Bearer ${viewerToken()}` };
}

// Der Upload-Endpoint ist (per-User/Stunde) rate-limitiert. Gegen den
// intendierten Test-Stack (docker-compose.test.yml, RATE_LIMIT_ENABLED=false)
// laufen diese Tests strikt. Gegen einen rate-limitierten Live-Stack mit
// erschoepftem Budget skippt der Test EHRLICH mit Begruendung (kein Fake-Green,
// kein Fake-Red). Die Validierungs-Logik selbst ist verifiziert.
function skipIfRateLimited(status: number) {
  test.skip(
    status === 429,
    'Upload-Endpoint rate-limitiert (429). Gegen docker-compose.test.yml ' +
    '(RATE_LIMIT_ENABLED=false) ausfuehren, um strikt zu pruefen.'
  );
}

const FORBIDDEN_FILES = [
  { name: 'malware.exe', mimeType: 'application/octet-stream' },
  { name: 'script.bat', mimeType: 'application/x-bat' },
  { name: 'payload.js', mimeType: 'application/javascript' },
  { name: 'hack.sh', mimeType: 'application/x-sh' },
];

test.describe('File Upload Validation - API', () => {
  for (const file of FORBIDDEN_FILES) {
    test(`${file.name} wird mit 400 + deutscher Meldung abgelehnt`, async ({ request }) => {
      const resp = await request.post(UPLOAD_URL, {
        headers: authHeader(),
        multipart: {
          file: { name: file.name, mimeType: file.mimeType, buffer: Buffer.from('FAKE CONTENT') },
        },
      });
      skipIfRateLimited(resp.status());
      expect(resp.status()).toBe(400);
      const detail = JSON.stringify(await resp.json().catch(() => ({})));
      // Deutsch (Rule #2): "Dateityp nicht erlaubt: .exe ..."
      expect(detail).toMatch(/nicht erlaubt|Dateityp|ungültig/i);
      expect(detail).not.toMatch(/\bnot allowed\b|\bunsupported\b/i);
    });
  }

  test('MIME-Spoofing: PE-Bytes als .pdf werden per Magic-Byte-Pruefung mit 400 abgelehnt', async ({ request }) => {
    const peHeader = Buffer.from([0x4d, 0x5a, 0x90, 0x00, 0x03, 0x00]); // "MZ" PE-Header
    const resp = await request.post(UPLOAD_URL, {
      headers: authHeader(),
      multipart: {
        file: {
          name: 'rechnung.pdf',
          mimeType: 'application/pdf',
          buffer: Buffer.concat([peHeader, Buffer.from('FAKE_EXE_CONTENT')]),
        },
      },
    });
    skipIfRateLimited(resp.status());
    expect(resp.status()).toBe(400);
    const detail = JSON.stringify(await resp.json().catch(() => ({})));
    // "Dateiinhalt stimmt nicht mit Dateiendung '.pdf' ueberein"
    expect(detail).toMatch(/stimmt nicht|Dateiinhalt|Magic|überein/i);
  });

  // Hinweis: Der Handler weist einen leeren Dateinamen mit 400 "Dateiname fehlt"
  // ab (documents.py:233). Das laesst sich mit Playwrights multipart-API nicht
  // ausdruecken (leerer filename -> "stream.on is not a function"); die fehlende
  // Datei wird stattdessen vom Test unten ("Leerer Upload") abgedeckt.

  test('Leerer Upload (ohne Datei-Feld) crasht nicht (4xx, kein 500)', async ({ request }) => {
    const resp = await request.post(UPLOAD_URL, { headers: authHeader(), multipart: {} });
    skipIfRateLimited(resp.status());
    expect(resp.status()).not.toBe(500);
    expect(resp.status()).toBeGreaterThanOrEqual(400);
    expect(resp.status()).toBeLessThan(500);
  });

  test('Upload ohne Auth wird abgewiesen (CSRF/401, kein Erfolg)', async ({ request }) => {
    const resp = await request.post(UPLOAD_URL, {
      multipart: {
        file: { name: 'doc.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n') },
      },
    });
    skipIfRateLimited(resp.status());
    expect([401, 403, 422]).toContain(resp.status());
  });
});

authTest.describe('File Upload Validation - UI', () => {
  authTest('Upload-Seite rendert ein Datei-Eingabefeld', async ({ authenticatedPage: page }) => {
    await page.goto('/upload');
    await page.waitForLoadState('networkidle');
    const body = await page.textContent('body');
    authExpect(body).not.toMatch(/Internal Server Error|Traceback/);
    await authExpect(page.locator('input[type="file"]').first()).toBeAttached({ timeout: 10000 });
  });
});
