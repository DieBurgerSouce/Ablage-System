/**
 * Regressionstests: apiClient-URL-Bildung (Doppel-Prefix-Bug)
 *
 * Hintergrund (fix/w3b-tsc-zero, 2026-06-12):
 * apiClient hat baseURL '/api/v1'. Call-Sites, die zusaetzlich mit '/api/v1/...'
 * aufrufen, erzeugten zur Laufzeit '/api/v1/api/v1/...' -> Backend 404.
 * Betroffen waren 44 Dateien / 160 Call-Sites (axios kombiniert baseURL + url,
 * solange url keine absolute URL mit Schema ist).
 *
 * Diese Tests sichern:
 * 1. den baseURL-Vertrag (relative Pfade werden korrekt unter /api/v1 aufgeloest),
 * 2. die Bug-Klasse als Demonstration (Doppel-Prefix entsteht wirklich),
 * 3. statisch, dass keine Call-Site mehr mit '/api/v1'-Prefix in den
 *    axios-Client (api/apiClient/fetchWithAuth) geht.
 */
import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { apiClient } from '../client';

describe('apiClient URL-Bildung (Doppel-Prefix-Regression)', () => {
  it('loest relative Pfade unter der baseURL /api/v1 auf', () => {
    expect(apiClient.defaults.baseURL).toBe('/api/v1');
    expect(apiClient.getUri({ url: '/documents' })).toBe('/api/v1/documents');
    expect(apiClient.getUri({ url: '/notifications/unread-count' })).toBe(
      '/api/v1/notifications/unread-count'
    );
  });

  it('erzeugt bei /api/v1-praefixierten URLs einen Doppel-Prefix (Bug-Klasse)', () => {
    // Genau deshalb duerfen Call-Sites NIE mit '/api/v1/...' aufrufen:
    expect(apiClient.getUri({ url: '/api/v1/documents' })).toBe(
      '/api/v1/api/v1/documents'
    );
  });
});

describe('Statischer Guard: keine /api/v1-praefixierten axios-Call-Sites', () => {
  const SRC_ROOT = path.resolve(__dirname, '../../..');

  // Direkte Aufrufe von api.<method>('/api/v1/...) bzw. apiClient.<method>(...)
  // sowie fetchWithAuth('/api/v1/...) — mehrzeilige Aufrufe eingeschlossen.
  const ANTI_PATTERNS: RegExp[] = [
    /\b(?:api|apiClient)\s*\.\s*(?:get|post|put|patch|delete|request)\s*(?:<[^>]*>)?\(\s*[`'"]\/api\/v1/,
    /\bfetchWithAuth\s*(?:<[^>]*>)?\(\s*[`'"]\/api\/v1/,
  ];

  function collectSourceFiles(dir: string, acc: string[] = []): string[] {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
        collectSourceFiles(full, acc);
      } else if (
        /\.(ts|tsx)$/.test(entry.name) &&
        !/\.(test|spec)\.(ts|tsx)$/.test(entry.name) &&
        !entry.name.endsWith('.d.ts')
      ) {
        acc.push(full);
      }
    }
    return acc;
  }

  it('keine Quelldatei ruft den axios-Client mit /api/v1-Prefix auf', () => {
    const offenders: string[] = [];
    for (const file of collectSourceFiles(SRC_ROOT)) {
      const content = fs.readFileSync(file, 'utf-8');
      if (!content.includes('/api/v1')) continue;
      if (ANTI_PATTERNS.some((re) => re.test(content))) {
        offenders.push(path.relative(SRC_ROOT, file));
      }
    }
    expect(
      offenders,
      `Doppel-Prefix-Gefahr: Diese Dateien rufen api/apiClient/fetchWithAuth mit '/api/v1/...' auf ` +
        `(baseURL ist bereits '/api/v1' -> ergibt '/api/v1/api/v1/...'): ${offenders.join(', ')}`
    ).toEqual([]);
  });
});
