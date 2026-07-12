/**
 * P3 Steuerberaterin/Prueferin (Viewer-Rolle) — Wirkt das Archiv VERTRAUENSWUERDIG?
 * Audit-Trail sichtbar? Hash/TSA irgendwo erlebbar? Verfahrensdoku auffindbar?
 * Alle Findings hier: trust=true -> separate Report-Sektion (Input fuer den
 * Trust-Theater-Folge-Prompt). Gefixt wird davon nur, was Blocker ist.
 */
import { test, expect } from '@playwright/test';
import { PERSONAS } from './users';
import {
  ITER,
  attachTaps,
  logFinding,
  loginViaUi,
  searchFor,
  shoot,
  step,
  dismissFirstRunOverlays,
  suppressOnboarding,
} from './helpers';

const P = 'p3-steuerberaterin';

test('P3 Prueferin: Vertrauens-Oberflaechen sichten', async ({ page }) => {
  if (parseInt(ITER, 10) >= 2) await suppressOnboarding(page);
  const flushTaps = attachTaps(page, P);

  const loggedIn = await loginViaUi(page, PERSONAS.p3);
  expect(loggedIn, 'Login als Prueferin (Viewer) muss moeglich sein').toBe(true);
  await page.waitForTimeout(2000);
  await shoot(page, P, 'nach-login-viewer-sicht');
  await dismissFirstRunOverlays(page);

  // Nebenbefund: /documents (Index) liefert eine 404-Seite (keine Route) —
  // ein Pruefer, der die URL raet, landet auf „Seite nicht gefunden".
  await page.goto('/documents', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  const notFound = /Seite nicht gefunden|404/i.test(
    (await page.locator('main').innerText().catch(() => '')) || ''
  );
  if (notFound) {
    logFinding({
      persona: P,
      iteration: ITER,
      route: '/documents',
      severity: 'Stolper',
      description:
        '/documents (Dokument-Index) zeigt eine 404-Seite — es gibt keine Sammel-Dokumentliste; Dokumente sind nur ueber Suche/Smart Inbox erreichbar.',
      screenshot: await shoot(page, P, 'documents-404'),
    });
  }

  // 1) Dokument ueber die (funktionierende) Suche oeffnen: Verlauf/Audit sichtbar?
  await step(page, P, 'dokument-detail-verlauf', 'Stolper', async () => {
    await searchFor(page, 'Müller');
    await page.waitForTimeout(1500);
    const first = page.locator('main a[href*="/documents/"], main [role="row"]').first();
    await first.waitFor({ state: 'visible', timeout: 15_000 });
    await first.click();
    await page.waitForURL(/documents\//, { timeout: 15_000 });
    await page.waitForTimeout(2500);

    const bodyText = (await page.locator('main').innerText().catch(() => '')) || '';
    const hasTrail = /Verlauf|Historie|Audit|Protokoll|Aktivität|Aktivitaet|Lebenszyklus/i.test(
      bodyText
    );
    const trailTab = page
      .getByRole('tab', { name: /Verlauf|Historie|Audit|Protokoll|Lebenszyklus/i })
      .first();
    if (await trailTab.isVisible({ timeout: 2000 }).catch(() => false)) {
      await trailTab.click();
      await page.waitForTimeout(1500);
      await shoot(page, P, 'audit-trail-tab');
    } else {
      await shoot(page, P, 'detail-ohne-trail-tab');
    }
    if (!hasTrail) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: page.url(),
        severity: 'Stolper',
        trust: true,
        description:
          'Dokument-Detail zeigt keinen erkennbaren Verlauf/Audit-Trail — Prüferin sieht nicht, wer wann was getan hat.',
      });
    }
    const hasHash = /SHA|Hash|Prüfsumme|Pruefsumme|Zeitstempel|TSA|Signatur|Integrität|Integritaet/i.test(
      bodyText
    );
    if (!hasHash) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: page.url(),
        severity: 'Stolper',
        trust: true,
        description:
          'Keine erlebbare Integritaets-Information am Dokument (Hash/Prüfsumme/Zeitstempel/Signatur nicht sichtbar).',
      });
    }
  });

  // 2) Compliance-/Audit-Seiten aus Sicht der Viewer-Rolle
  for (const route of ['/compliance', '/audit-trail', '/audit-logs']) {
    await step(page, P, `route-${route.replace(/\//g, '')}`, 'Kosmetik', async () => {
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      await shoot(page, P, `seite${route.replace(/\//g, '-')}`);
      const text = (await page.locator('body').innerText().catch(() => '')) || '';
      if (/404|nicht gefunden|kein Zugriff|nicht berechtigt|Fehler/i.test(text.slice(0, 2000))) {
        logFinding({
          persona: P,
          iteration: ITER,
          route,
          severity: 'Stolper',
          trust: true,
          description: `Seite ${route} ist fuer die Prüfer-Rolle nicht nutzbar (Fehler-/Sperrseite) — was darf ein Prüfer hier eigentlich sehen?`,
        });
      }
    });
  }

  // 3) Verfahrensdokumentation auffindbar?
  await step(page, P, 'verfahrensdoku-suchen', 'Stolper', async () => {
    const navText = (await page.locator('nav, aside').allInnerTexts().catch(() => [])).join(' ');
    const inNav = /Verfahrensdoku/i.test(navText);
    let found = inNav;
    if (!found) {
      const globalSearch = page
        .locator('header input, [role="search"] input, input[type="search"], input[placeholder*="uch"]')
        .first();
      if (await globalSearch.isVisible({ timeout: 3000 }).catch(() => false)) {
        await globalSearch.fill('Verfahrensdokumentation');
        await globalSearch.press('Enter');
        await page.waitForTimeout(3000);
        await shoot(page, P, 'suche-verfahrensdoku');
        const resultText = (await page.locator('main').innerText().catch(() => '')) || '';
        found = /Verfahrensdoku/i.test(resultText);
      }
    }
    if (!found) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: page.url(),
        severity: 'Stolper',
        trust: true,
        description:
          'Verfahrensdokumentation ist aus der UI heraus nicht auffindbar (weder Navigation noch Suche) — existiert nur "hinter den Kulissen".',
      });
    }
  });

  flushTaps();
});
