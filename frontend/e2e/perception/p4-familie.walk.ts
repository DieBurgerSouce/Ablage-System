/**
 * P4 Familienmitglied — Privat-Space-Grundflow: hinkommen, verstehen,
 * Trennung von Firmendaten wahrnehmen. Nur eigener Test-Space, keine echten Daten.
 */
import { test, expect } from '@playwright/test';
import { PERSONAS } from './users';
import {
  ITER,
  attachTaps,
  logFinding,
  loginViaUi,
  shoot,
  step,
  dismissFirstRunOverlays,
  suppressOnboarding,
} from './helpers';

const P = 'p4-familie';

test('P4 Familienmitglied: Privat-Space-Grundflow', async ({ page }) => {
  if (parseInt(ITER, 10) >= 2) await suppressOnboarding(page);
  const flushTaps = attachTaps(page, P);

  const loggedIn = await loginViaUi(page, PERSONAS.p4);
  expect(loggedIn, 'Login als Familienmitglied muss moeglich sein').toBe(true);
  await page.waitForTimeout(2000);
  await shoot(page, P, 'nach-login');
  await dismissFirstRunOverlays(page);

  // Privat-Bereich ueber die Navigation finden (wie ein Mensch)
  const navFound = await step(page, P, 'privat-in-navigation-finden', 'Stolper', async () => {
    const navLink = page.locator('nav a, aside a').filter({ hasText: /privat/i }).first();
    await navLink.waitFor({ state: 'visible', timeout: 5000 });
    await navLink.click();
    await page.waitForURL(/privat/, { timeout: 10_000 });
  });
  if (!navFound) {
    logFinding({
      persona: P,
      iteration: ITER,
      route: '/privat',
      severity: 'Stolper',
      description:
        'Privat-Bereich ist ueber die sichtbare Navigation nicht auffindbar — Familienmitglied muesste die URL kennen.',
    });
    await page.goto('/privat', { waitUntil: 'domcontentloaded' });
  }
  await page.waitForTimeout(2500);
  await shoot(page, P, 'privat-startansicht');

  // Grundflow-Wahrnehmung: Empty-State, Anleitung, deutscher Ton
  await step(page, P, 'privat-verstaendlichkeit', 'Stolper', async () => {
    const text = (await page.locator('main').innerText().catch(() => '')) || '';
    if (/404|nicht gefunden|Fehler|kein Zugriff/i.test(text.slice(0, 1500))) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: '/privat',
        severity: 'Blocker',
        description: 'Privat-Bereich laedt nicht (Fehler-/Sperrseite statt Grundflow).',
      });
      return;
    }
    const guided = /hochladen|hinzufügen|hinzufuegen|anlegen|beginnen|erste/i.test(text);
    if (!guided) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: '/privat',
        severity: 'Stolper',
        description:
          'Privat-Bereich ohne erkennbare Handlungsaufforderung — neuer Nutzer weiss nicht, wie er startet.',
      });
    }
    // Trennung wahrnehmbar? (Heading/Badge/Beschriftung "Privat")
    const separationVisible = /privat/i.test(text.slice(0, 3000));
    if (!separationVisible) {
      logFinding({
        persona: P,
        iteration: ITER,
        route: '/privat',
        severity: 'Stolper',
        description:
          'Nicht klar erkennbar, dass man sich im PRIVATEN Bereich (getrennt von Firmendaten) befindet.',
      });
    }
  });

  // Ein Klick tiefer, wenn es eine offensichtliche Aktion gibt (nur ansehen)
  await step(page, P, 'privat-erste-aktion', 'Kosmetik', async () => {
    const cta = page
      .locator('main')
      .getByRole('button', { name: /hochladen|hinzufügen|anlegen|neu/i })
      .first();
    if (await cta.isVisible({ timeout: 3000 }).catch(() => false)) {
      await cta.click({ timeout: 5000 }).catch(() => undefined);
      await page.waitForTimeout(1500);
      await shoot(page, P, 'privat-erste-aktion');
      await page.keyboard.press('Escape').catch(() => undefined);
    }
  });

  flushTaps();
});
