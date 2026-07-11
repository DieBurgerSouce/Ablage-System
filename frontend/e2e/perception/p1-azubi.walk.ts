/**
 * P1 Azubi — Erste Eingangsrechnung hochladen -> OCR -> Dokument wiederfinden.
 * Misst Time-to-First-Value (TTFV): erste Login-Interaktion bis Dokument-Detail
 * ueber die Suche geoeffnet. Frischer Kontext MIT Onboarding (gehoert zur
 * Wahrnehmung). Soft-Fail: Reibungen werden protokolliert, der Walk laeuft weiter.
 */
import * as fs from 'fs';
import * as path from 'path';
import { test, expect } from '@playwright/test';
import { PERSONAS } from './users';
import {
  FIXTURE_PDF,
  ITER,
  REPORT_DIR,
  Stopwatch,
  attachTaps,
  logFinding,
  loginViaUi,
  pollOcrStatus,
  shoot,
  step,
} from './helpers';

const P = 'p1-azubi';

test('P1 Azubi: Upload -> OCR -> Wiederfinden (TTFV)', async ({ page }) => {
  const flushTaps = attachTaps(page, P);
  const watch = new Stopwatch();

  // Erster Eindruck: unangemeldet auf die App
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await shoot(page, P, 'erster-eindruck');

  // Stoppuhr ab erster Login-Interaktion
  watch.start();
  const loggedIn = await loginViaUi(page, PERSONAS.p1);
  expect(loggedIn, 'Login als Azubi muss moeglich sein').toBe(true);
  watch.mark('login');
  await page.waitForTimeout(2500);
  await shoot(page, P, 'nach-login-so-wie-es-ist');

  // Onboarding wie ein echter Azubi durchlaufen (max. 8 Klicks, screenshotten)
  await step(page, P, 'onboarding-durchlaufen', 'Stolper', async () => {
    for (let i = 0; i < 8; i += 1) {
      const btn = page
        .getByRole('button', {
          name: /^(Los geht's|Weiter|Fertig|Abschließen|Überspringen|Tour überspringen|Verstanden|Schließen)$/i,
        })
        .first();
      if (!(await btn.isVisible({ timeout: 2000 }).catch(() => false))) break;
      await shoot(page, P, `onboarding-schritt-${i + 1}`);
      await btn.click();
      await page.waitForTimeout(800);
    }
  });
  watch.mark('onboarding');

  // Upload ueber die Navigation finden (wie ein Mensch), sonst Befund + direkt hin
  const navFound = await step(page, P, 'upload-in-navigation-finden', 'Stolper', async () => {
    const navLink = page
      .locator('nav a, aside a')
      .filter({ hasText: /hochladen|upload/i })
      .first();
    await navLink.waitFor({ state: 'visible', timeout: 5000 });
    await navLink.click();
    await page.waitForURL(/upload/, { timeout: 10_000 });
  });
  if (!navFound) {
    logFinding({
      persona: P,
      iteration: ITER,
      route: '/upload',
      severity: 'Stolper',
      description:
        'Upload ist ueber die sichtbare Navigation nicht auffindbar — Azubi muesste die URL kennen.',
    });
    await page.goto('/upload', { waitUntil: 'domcontentloaded' });
  }
  await expect(
    page.getByRole('heading', { name: 'Dokumente hochladen', level: 1 })
  ).toBeVisible({ timeout: 15_000 });
  await shoot(page, P, 'upload-seite');

  // Fixture-Rechnung hochladen; Dokument-ID aus der Upload-Response schnappen
  let documentId = '';
  await step(page, P, 'datei-hochladen', 'Blocker', async () => {
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/v1/documents') && r.request().method() === 'POST',
      { timeout: 60_000 }
    );
    await page.locator('input[type="file"]').first().setInputFiles(FIXTURE_PDF);
    // Falls der Wizard einen expliziten Start-Button hat, druecken
    const startBtn = page
      .getByRole('button', { name: /hochladen|upload starten|starten/i })
      .first();
    if (await startBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await startBtn.click();
    }
    const resp = await respPromise;
    const body = await resp.json().catch(() => ({}));
    documentId = body?.id || body?.document?.id || '';
    if (resp.status() >= 400) {
      throw new Error(`Upload-Antwort ${resp.status()}: ${JSON.stringify(body).slice(0, 200)}`);
    }
  });
  watch.mark('upload');
  await page.waitForTimeout(2000);
  await shoot(page, P, 'upload-feedback');

  // OCR abwarten (Budget 300s) — sichtbar fuer den User? (Wahrnehmung!)
  if (documentId) {
    const { status, elapsedMs } = await pollOcrStatus(page, documentId, 300_000);
    watch.mark('ocr');
    if (status !== 'completed') {
      logFinding({
        persona: P,
        iteration: ITER,
        route: '/upload',
        severity: 'Blocker',
        description: `OCR endet nicht in "completed" (Status "${status}" nach ${(elapsedMs / 1000).toFixed(0)}s) — Azubi sieht kein fertiges Dokument.`,
      });
    }
  } else {
    logFinding({
      persona: P,
      iteration: ITER,
      route: '/upload',
      severity: 'Blocker',
      description: 'Upload lieferte keine Dokument-ID — Verarbeitung nicht nachvollziehbar.',
    });
  }

  // Wiederfinden ueber die Suche ("Müller")
  const searched = await step(page, P, 'dokument-per-suche-finden', 'Blocker', async () => {
    const globalSearch = page
      .locator('header input, [role="search"] input, input[type="search"], input[placeholder*="uch"]')
      .first();
    if (await globalSearch.isVisible({ timeout: 4000 }).catch(() => false)) {
      await globalSearch.fill('Müller');
      await globalSearch.press('Enter');
    } else {
      logFinding({
        persona: P,
        iteration: ITER,
        route: page.url(),
        severity: 'Stolper',
        description: 'Keine globale Suche sichtbar — Azubi muss die Suchseite selbst finden.',
      });
      await page.goto('/search', { waitUntil: 'domcontentloaded' });
      const input = page.locator('main input').first();
      await input.fill('Müller');
      await input.press('Enter');
    }
    await page.waitForTimeout(2500);
    await shoot(page, P, 'suchergebnis');
    const result = page.locator('main a[href*="/documents/"], main [role="row"]').first();
    await result.waitFor({ state: 'visible', timeout: 20_000 });
    await result.click();
    await page.waitForURL(/documents\//, { timeout: 15_000 });
  });
  if (searched) {
    watch.mark('gefunden_TTFV');
    await page.waitForTimeout(2000);
    await shoot(page, P, 'dokument-detail');
  }

  // Timings persistieren
  fs.mkdirSync(path.join(REPORT_DIR, 'findings'), { recursive: true });
  fs.writeFileSync(
    path.join(REPORT_DIR, 'findings', `iter${ITER}-timings-p1.json`),
    JSON.stringify({ persona: P, iteration: ITER, marks: watch.marks }, null, 2),
    'utf-8'
  );
  console.log(`[TTFV] P1 gesamt: ${(watch.elapsed() / 1000 / 60).toFixed(1)} min`);

  flushTaps();
});
