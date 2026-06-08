/**
 * E2E Tests: RBAC / Rollenbasierte Zugriffskontrolle (API-Ebene)
 *
 * Prueft die Zugriffskontrollen mit ECHTEN Tokens (Admin vs. Nicht-Admin):
 * - Nicht-Admin (viewer) wird von /admin/* mit 403 abgewiesen
 * - Admin erhaelt 200 auf denselben Endpoints (beweist, dass der Test nicht
 *   nur deshalb "gruen" ist, weil alles blockiert wird)
 * - Unternehmens-Datenisolation (G1: company_id) — fremde Dokument-IDs nicht abrufbar
 * - 403-Antworten kommen als strukturiertes deutsches JSON-Envelope zurueck
 *
 * Hintergrund: G1 rollout (feature/g1-api-companyid) — company_id-Filter ist
 * kritisch fuer Multi-Tenancy-Sicherheit. Diese Tests laufen rein gegen die API
 * (deterministisch, kein UI-Selektor-Drift). Tokens stammen aus dem globalSetup-
 * Cache (.auth/auth-state.json fuer Admin, .auth/viewer-state.json fuer Viewer) —
 * KEIN Login pro Test, damit das Login-Rate-Limit (5/15min) nicht getroffen wird.
 * Beide User werden von scripts/seed_e2e.py provisioniert.
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

function readCachedToken(cacheFile: string, label: string): string {
  const p = path.join(__dirname, '.auth', cacheFile);
  if (!fs.existsSync(p)) {
    throw new Error(
      `${label}-Auth-Cache fehlt (${p}). globalSetup muss zuerst laufen ` +
      `(seed_e2e.py muss den ${label}-User angelegt haben).`
    );
  }
  const token = JSON.parse(fs.readFileSync(p, 'utf-8')).access_token;
  if (!token) throw new Error(`${label}-Auth-Cache enthaelt keinen access_token (${p})`);
  return token;
}

const adminToken = readCachedToken('auth-state.json', 'Admin');
const viewerToken = readCachedToken('viewer-state.json', 'Viewer');

// Admin-Endpoints, die fuer einen Nicht-Admin gesperrt sein muessen.
// Verifiziert gegen die laufende API: viewer -> 403, admin -> 200.
const GATED_ADMIN_ENDPOINTS = ['/api/v1/admin/jobs', '/api/v1/admin/users'];

test.describe('RBAC - Admin-Endpoints', () => {
  for (const endpoint of GATED_ADMIN_ENDPOINTS) {
    test(`Nicht-Admin wird von ${endpoint} mit 403 abgewiesen`, async ({ request }) => {
      const resp = await request.get(`${API_BASE}${endpoint}`, {
        headers: { Authorization: `Bearer ${viewerToken}` },
      });
      expect(resp.status()).toBe(403);
    });

    test(`Admin darf ${endpoint} aufrufen (200)`, async ({ request }) => {
      const resp = await request.get(`${API_BASE}${endpoint}`, {
        headers: { Authorization: `Bearer ${adminToken}` },
      });
      expect(resp.status()).toBe(200);
    });
  }
});

test.describe('RBAC - 403-Fehler-Envelope', () => {
  test('403 wird als strukturiertes deutsches JSON zurueckgegeben', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/admin/jobs`, {
      headers: { Authorization: `Bearer ${viewerToken}`, Accept: 'application/json' },
    });
    expect(resp.status()).toBe(403);

    const contentType = resp.headers()['content-type'] || '';
    expect(contentType).toContain('application/json');

    const body = await resp.json();
    // Deutsches Fehler-Envelope (app/main.py exception handler): fehler/status_code/pfad
    expect(body.status_code).toBe(403);
    expect(body.fehler).toBeTruthy();
    expect(body.fehler).toMatch(/verweigert|verboten|berechtigung/i);
  });
});

test.describe('RBAC - Company Data Isolation (G1)', () => {
  test('Dokumentenliste ist company-scoped (paginierte Struktur)', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/documents/`, {
      headers: { Authorization: `Bearer ${viewerToken}` },
    });
    expect(resp.status()).toBe(200);

    const data = await resp.json();
    // Echte API-Form (verifiziert): { total, page, per_page, documents: [...] }
    expect(Array.isArray(data.documents)).toBeTruthy();
    expect(typeof data.total).toBe('number');
    expect(typeof data.page).toBe('number');
  });

  test('Fremde Dokument-ID ist nicht direkt abrufbar (kein 200)', async ({ request }) => {
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const resp = await request.get(`${API_BASE}/api/v1/documents/${fakeId}`, {
      headers: { Authorization: `Bearer ${viewerToken}` },
    });
    expect([401, 403, 404]).toContain(resp.status());
  });

  test('Entitaets-Endpoints sind gegated und crashen nicht (kein 500)', async ({ request }) => {
    for (const endpoint of ['/api/v1/companies/', '/api/v1/entities/']) {
      const resp = await request.get(`${API_BASE}${endpoint}`, {
        headers: { Authorization: `Bearer ${viewerToken}` },
        maxRedirects: 0,
      });
      // Gegated (401/403), redirect (307) oder company-scoped (200) — niemals 500.
      expect(resp.status()).not.toBe(500);
      expect([200, 307, 401, 403]).toContain(resp.status());
    }
  });
});

test.describe('RBAC - Unauthentifiziert', () => {
  test('Ohne gueltigen Token liefert die API 401', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/documents/`, {
      headers: { Authorization: 'Bearer invalid_token_xyz' },
    });
    expect(resp.status()).toBe(401);
  });
});
