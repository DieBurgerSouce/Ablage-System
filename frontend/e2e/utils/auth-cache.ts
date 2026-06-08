/**
 * Reads role tokens cached by global-setup.ts (.auth/<role>-state.json).
 *
 * Tests must NOT log in themselves — the login endpoint is rate-limited
 * (5/15min). globalSetup logs in once per role and caches the token; tests
 * read it from disk via these helpers.
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const AUTH_DIR = path.join(__dirname, '..', '.auth');

export function readCachedToken(cacheFile: string, label: string): string {
  const p = path.join(AUTH_DIR, cacheFile);
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

export const adminToken = (): string => readCachedToken('auth-state.json', 'Admin');
export const viewerToken = (): string => readCachedToken('viewer-state.json', 'Viewer');
