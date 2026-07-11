/**
 * Helfer fuer die Perception-Walks: Stoppuhr, Findings-Log, Screenshots,
 * UI-Login mit Rate-Limit-Schutz, OCR-Polling, Netzwerk-/Console-Tap.
 *
 * Findings + Screenshots landen versioniert unter
 * docs/qa-reports/perception-2026-07/ (relativ zum Repo-Root).
 */
import * as fs from 'fs';
import * as path from 'path';
import type { Page } from '@playwright/test';
import { API_BASE, type Persona } from './users';

export const ITER = process.env.PERCEPTION_ITER || '01';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
export const REPORT_DIR = path.join(REPO_ROOT, 'docs', 'qa-reports', 'perception-2026-07');
const SCREENSHOT_DIR = path.join(REPORT_DIR, 'screenshots', `iter${ITER}`);
const FINDINGS_FILE = path.join(REPORT_DIR, 'findings', `iter${ITER}.json`);
const LOGIN_TIMES_FILE = path.join(REPORT_DIR, 'findings', '.login-times.json');

export interface Finding {
  id?: string;
  persona: string;
  iteration: string;
  route: string;
  severity: 'Blocker' | 'Stolper' | 'Kosmetik';
  description: string;
  languageIssue?: boolean;
  trust?: boolean;
  screenshot?: string;
  timingMs?: number;
  evidence?: string;
}

function ensureDirs(): void {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  fs.mkdirSync(path.dirname(FINDINGS_FILE), { recursive: true });
}

export function logFinding(f: Finding): void {
  ensureDirs();
  const list: Finding[] = fs.existsSync(FINDINGS_FILE)
    ? JSON.parse(fs.readFileSync(FINDINGS_FILE, 'utf-8'))
    : [];
  list.push({ ...f, iteration: ITER });
  fs.writeFileSync(FINDINGS_FILE, JSON.stringify(list, null, 2), 'utf-8');
  // Konsolen-Echo, damit der Auditor live mitliest
  console.log(`[FINDING][${f.severity}][${f.persona}] ${f.route}: ${f.description}`);
}

let shotCounter = 0;
export async function shoot(page: Page, persona: string, name: string): Promise<string> {
  ensureDirs();
  shotCounter += 1;
  const file = path.join(
    SCREENSHOT_DIR,
    `${persona}-${String(shotCounter).padStart(2, '0')}-${name}.png`
  );
  try {
    await page.screenshot({ path: file, timeout: 10_000 });
  } catch {
    // Screenshot-Fehler duerfen den Walk nie brechen
    return '';
  }
  return path.relative(REPORT_DIR, file).replace(/\\/g, '/');
}

/** Einfache Stoppuhr mit benannten Marken. */
export class Stopwatch {
  private t0 = 0;
  readonly marks: Record<string, number> = {};
  start(): void {
    this.t0 = Date.now();
  }
  mark(name: string): number {
    const ms = Date.now() - this.t0;
    this.marks[name] = ms;
    console.log(`[TIMER] ${name}: ${(ms / 1000).toFixed(1)}s`);
    return ms;
  }
  elapsed(): number {
    return Date.now() - this.t0;
  }
}

/**
 * Login-Abstandswaechter: Backend limitiert Logins auf 5/min/IP.
 * Wir erzwingen >=15s Abstand zwischen zwei Logins (Datei-basiert, damit es
 * ueber mehrere Spec-Prozesse hinweg gilt).
 */
async function respectLoginSpacing(): Promise<void> {
  ensureDirs();
  let last = 0;
  if (fs.existsSync(LOGIN_TIMES_FILE)) {
    try {
      last = JSON.parse(fs.readFileSync(LOGIN_TIMES_FILE, 'utf-8')).last || 0;
    } catch {
      last = 0;
    }
  }
  const waitMs = last + 15_000 - Date.now();
  if (waitMs > 0) {
    console.log(`[LOGIN] Rate-Schutz: warte ${(waitMs / 1000).toFixed(0)}s`);
    await new Promise((r) => setTimeout(r, waitMs));
  }
  fs.writeFileSync(LOGIN_TIMES_FILE, JSON.stringify({ last: Date.now() }), 'utf-8');
}

/**
 * Echter UI-Login ueber /login (#email/#password). Niemals falsche Passwoerter
 * (Account-Lockout nach 5 Fehlversuchen). Bei 429 einmal 60s Backoff.
 * Rueckgabe: true = eingeloggt (nicht mehr auf /login).
 */
export async function loginViaUi(page: Page, persona: Persona): Promise<boolean> {
  await respectLoginSpacing();
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await page.locator('#email').fill(persona.email);
    await page.locator('#password').fill(persona.password);
    const [resp] = await Promise.all([
      page
        .waitForResponse((r) => r.url().includes('/api/v1/auth/login'), { timeout: 20_000 })
        .catch(() => null),
      page.locator('button[type="submit"]').click(),
    ]);
    if (resp && resp.status() === 429) {
      console.log('[LOGIN] 429 — 60s Backoff, dann letzter Versuch');
      await new Promise((r) => setTimeout(r, 60_000));
      continue;
    }
    // erfolgreich, wenn wir /login verlassen
    try {
      await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20_000 });
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

/**
 * Netzwerk-/Console-Tap: sammelt 4xx/5xx-Responses und Console-Errors als
 * Kandidaten-Findings (dedupliziert), ohne den Walk zu beeinflussen.
 */
export function attachTaps(page: Page, persona: string): () => void {
  const seen = new Set<string>();
  const candidates: string[] = [];
  page.on('response', (r) => {
    const s = r.status();
    if (s >= 400) {
      const key = `${s} ${r.request().method()} ${new URL(r.url()).pathname}`;
      if (!seen.has(key)) {
        seen.add(key);
        candidates.push(key);
      }
    }
  });
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const key = `console: ${msg.text().slice(0, 160)}`;
      if (!seen.has(key)) {
        seen.add(key);
        candidates.push(key);
      }
    }
  });
  return () => {
    if (candidates.length > 0) {
      logFinding({
        persona,
        iteration: ITER,
        route: '(gesamter Walk)',
        severity: 'Stolper',
        description: `Technische Auffaelligkeiten im Hintergrund (${candidates.length})`,
        evidence: candidates.slice(0, 25).join(' | '),
      });
    }
  };
}

/** Soft-Fail-Schritt: Fehler => Finding + Screenshot, Walk laeuft weiter. */
export async function step(
  page: Page,
  persona: string,
  name: string,
  severityOnFail: Finding['severity'],
  fn: () => Promise<void>
): Promise<boolean> {
  try {
    await fn();
    return true;
  } catch (err) {
    const shot = await shoot(page, persona, `FEHLER-${name}`);
    logFinding({
      persona,
      iteration: ITER,
      route: page.url(),
      severity: severityOnFail,
      description: `Schritt "${name}" fehlgeschlagen: ${(err as Error).message.split('\n')[0]}`,
      screenshot: shot,
    });
    return false;
  }
}

/** OCR-Status-Polling via API (Cookies der eingeloggten Seite werden mitgesendet). */
export async function pollOcrStatus(
  page: Page,
  documentId: string,
  budgetMs = 300_000
): Promise<{ status: string; elapsedMs: number }> {
  const start = Date.now();
  let status = 'pending';
  while (Date.now() - start < budgetMs) {
    const resp = await page.request.get(`${API_BASE}/api/v1/documents/${documentId}`);
    if (resp.ok()) {
      status = (await resp.json()).status;
      if (status === 'completed' || status === 'failed') break;
    }
    await new Promise((r) => setTimeout(r, 5000));
  }
  return { status, elapsedMs: Date.now() - start };
}

/** Onboarding-Unterdrueckung (nur fuer P2–P4 ab Iteration 02). */
export async function suppressOnboarding(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('ablage_onboarding_v2', JSON.stringify({ completed: true }));
    window.localStorage.setItem('ablage_onboarding_complete', 'true');
    window.localStorage.setItem('ablage-first-visit-done', 'true');
  });
}

export const FIXTURE_PDF = path.join(__dirname, 'fixtures', 'eingangsrechnung-buerohaus-mueller.pdf');
