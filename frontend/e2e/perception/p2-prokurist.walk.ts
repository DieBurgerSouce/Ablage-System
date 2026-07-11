/**
 * P2 Prokurist — "Finde Beleg von Lieferant Müller" ueber die Suche (<10s?)
 * + Detailansicht ohne Erklaerung verstehen (deutsche, klare Labels).
 * Fallback: laedt die Fixture selbst ueber die Upload-UI hoch, falls noch kein
 * Dokument existiert (P1 blockiert) — P2 darf nie an P1 scheitern.
 */
import * as fs from 'fs';
import * as path from 'path';
import { test, expect } from '@playwright/test';
import { PERSONAS, API_BASE } from './users';
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
  suppressOnboarding,
} from './helpers';

const P = 'p2-prokurist';

test('P2 Prokurist: Beleg via Suche finden + Detail verstehen', async ({ page }) => {
  if (parseInt(ITER, 10) >= 2) await suppressOnboarding(page);
  const flushTaps = attachTaps(page, P);

  const loggedIn = await loginViaUi(page, PERSONAS.p2);
  expect(loggedIn, 'Login als Prokurist muss moeglich sein').toBe(true);
  await page.waitForTimeout(2000);
  await shoot(page, P, 'nach-login');

  // Vorbedingung: existiert ein durchsuchbares Dokument? Sonst selbst hochladen.
  const listResp = await page.request.get(`${API_BASE}/api/v1/documents?limit=1`);
  const hasDocs =
    listResp.ok() &&
    (((await listResp.json().catch(() => ({}))) as { items?: unknown[]; total?: number })
      .items?.length ?? 0) > 0;
  if (!hasDocs) {
    logFinding({
      persona: P,
      iteration: ITER,
      route: '/upload',
      severity: 'Stolper',
      description:
        'Kein Dokument vorhanden (P1-Upload fehlgeschlagen?) — P2 laedt Fallback-Beleg selbst hoch.',
    });
    await step(page, P, 'fallback-upload', 'Blocker', async () => {
      await page.goto('/upload', { waitUntil: 'domcontentloaded' });
      const respPromise = page.waitForResponse(
        (r) => r.url().includes('/api/v1/documents') && r.request().method() === 'POST',
        { timeout: 60_000 }
      );
      await page.locator('input[type="file"]').first().setInputFiles(FIXTURE_PDF);
      const startBtn = page
        .getByRole('button', { name: /hochladen|upload starten|starten/i })
        .first();
      if (await startBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await startBtn.click();
      }
      const resp = await respPromise;
      const body = await resp.json().catch(() => ({} as { id?: string }));
      if (body?.id) await pollOcrStatus(page, body.id, 300_000);
    });
  }

  // Kernszenario: Suche nach "Müller" — Stoppuhr Query -> Treffer sichtbar
  const watch = new Stopwatch();
  await step(page, P, 'suche-mueller', 'Blocker', async () => {
    const globalSearch = page
      .locator('header input, [role="search"] input, input[type="search"], input[placeholder*="uch"]')
      .first();
    if (await globalSearch.isVisible({ timeout: 4000 }).catch(() => false)) {
      await globalSearch.fill('Müller');
      watch.start();
      await globalSearch.press('Enter');
    } else {
      await page.goto('/search', { waitUntil: 'domcontentloaded' });
      const input = page.locator('main input').first();
      await input.fill('Müller');
      watch.start();
      await input.press('Enter');
    }
    const result = page.locator('main a[href*="/documents/"], main [role="row"]').first();
    await result.waitFor({ state: 'visible', timeout: 30_000 });
    const searchMs = watch.mark('treffer_sichtbar');
    await shoot(page, P, 'suchergebnis');
    if (searchMs > 10_000) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: page.url(),
        severity: 'Stolper',
        description: `Suche nach "Müller" brauchte ${(searchMs / 1000).toFixed(1)}s bis zum sichtbaren Treffer (Ziel <10s).`,
        timingMs: searchMs,
      });
    }
    await result.click();
    await page.waitForURL(/documents\//, { timeout: 15_000 });
  });

  // Detailansicht: versteht ein Prokurist sie ohne Erklaerung?
  await step(page, P, 'detail-verstaendlichkeit', 'Stolper', async () => {
    await page.waitForTimeout(2500);
    await shoot(page, P, 'detail-oben');
    const bodyText = (await page.locator('main').innerText().catch(() => '')) || '';
    const checks: Array<[string, RegExp]> = [
      ['Lieferant/Absender', /Lieferant|Absender|Entität|Entitaet|Firma/i],
      ['Betrag', /Betrag|Summe|EUR|€/i],
      ['Datum', /Datum|\d{2}\.\d{2}\.\d{4}/i],
      ['Status', /Status|Verarbeitet|Abgeschlossen|completed/i],
    ];
    const missing = checks.filter(([, re]) => !re.test(bodyText)).map(([label]) => label);
    if (missing.length > 0) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: page.url(),
        severity: 'Stolper',
        description: `Detailansicht laesst Kernfragen offen — nicht erkennbar: ${missing.join(', ')}.`,
      });
    }
    if (/completed|pending|processing|failed/i.test(bodyText)) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: page.url(),
        severity: 'Kosmetik',
        languageIssue: true,
        description:
          'Detailansicht zeigt englische Status-Rohwerte (completed/pending/…) statt deutscher Begriffe.',
      });
    }
    await page.mouse.wheel(0, 900);
    await page.waitForTimeout(800);
    await shoot(page, P, 'detail-unten');
  });

  fs.mkdirSync(path.join(REPORT_DIR, 'findings'), { recursive: true });
  fs.writeFileSync(
    path.join(REPORT_DIR, 'findings', `iter${ITER}-timings-p2.json`),
    JSON.stringify({ persona: P, iteration: ITER, marks: watch.marks }, null, 2),
    'utf-8'
  );

  flushTaps();
});
