/**
 * E2E: Banking-Journey CSV-Import -> Transaktionsliste -> Abgleich
 *
 * MODUL EINGEFROREN (Odoo-Neuausrichtung 2026-07): Banking/Zahlungsabgleich
 * übernimmt Odoo. Der Backend-Router /api/v1/banking liefert 404, die
 * /admin/banking/*-Routen leiten auf /frozen um (frontend/src/lib/
 * frozen-modules.ts, Key 'banking'). Beide describes sind daher geskippt;
 * den Freeze-Zustand selbst beweist frozen-modules.spec.ts.
 * Reaktivierung: ACTIVE_OPTIONAL_MODULES=banking + Skips entfernen.
 *
 * Journey:
 * 1. Sicherstellen, dass ein Bankkonto existiert (API, idempotent: nur
 *    anlegen wenn keines da ist)
 * 2. /admin/banking/import: Sparkasse-CSV (echtes Parser-Format aus
 *    tests/unit/services/banking/test_bank_csv_parsers.py) hochladen,
 *    Konto waehlen, Vorschau anzeigen, importieren
 * 3. /admin/banking/transactions: Transaktionsliste laedt
 * 4. /admin/banking/reconciliation: Zahlungsabgleich-Seite laedt
 *
 * Verifizierte UI-Texte: h1 "Transaktionen importieren" / "Zahlungsabgleich",
 * Buttons "Vorschau anzeigen", "... Transaktionen importieren", "Zurück".
 *
 * Seriell-tauglich: Duplikat-Erkennung beim Re-Import ist erlaubtes Verhalten
 * (Vorschau zeigt dann 0 neue Transaktionen) — beide Pfade werden ehrlich
 * behandelt, ohne Tautologie: Die Vorschau MUSS erscheinen, der Import-Pfad
 * wird nur betreten, wenn neue Transaktionen vorhanden sind.
 */

import { test, expect } from './fixtures';
import { test as apiTest, expect as apiExpect, type APIRequestContext } from '@playwright/test';
import { adminToken } from './utils/auth-cache';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

const SPARKASSE_CSV = [
  '"Auftragskonto";"Buchungstag";"Valutadatum";"Buchungstext";"Verwendungszweck";"Glaeubiger ID";"Mandatsreferenz";"Kundenreferenz (End-to-End)";"Sammlerreferenz";"Lastschrift Ursprungsbetrag";"Auslagenersatz Ruecklastschrift";"Begünstigter/Zahlungspflichtiger";"Kontonummer/IBAN";"BIC (SWIFT-Code)";"Betrag";"Währung";"Info"',
  '"DE89370400440532013000";"15.03.2024";"16.03.2024";"Lastschrift";"Strom Maerz 2024 E2E";"DE98ZZZ09999999999";"MNDT-2024-001";"E2E-2024-001";"";"";"";"Stadtwerke Berlin";"DE02100500000024290661";"BELADEBEXXX";"-149,50";"EUR";"Umsatz gebucht"',
].join('\n');

async function ensureBankAccount(request: APIRequestContext): Promise<void> {
  const headers = { Authorization: `Bearer ${adminToken()}` };
  const listResp = await request.get(`${API_BASE}/api/v1/banking/accounts`, { headers });
  apiExpect(listResp.status()).toBe(200);
  const body = await listResp.json();
  const accounts = Array.isArray(body) ? body : body.accounts || body.items || [];
  if (accounts.length > 0) return;

  const createResp = await request.post(`${API_BASE}/api/v1/banking/accounts`, {
    headers,
    data: {
      account_name: 'E2E Geschäftskonto',
      iban: 'DE89370400440532013000',
      bank_name: 'E2E Testbank',
    },
  });
  apiExpect([200, 201]).toContain(createResp.status());
}

apiTest.describe.skip('Banking - API-Vorbedingungen', () => {
  apiTest('Bankkonto existiert (oder wird idempotent angelegt)', async ({ request }) => {
    await ensureBankAccount(request);
  });

  apiTest('Transaktionsliste antwortet ohne 500', async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/banking/transactions`, {
      headers: { Authorization: `Bearer ${adminToken()}` },
    });
    apiExpect(resp.status()).not.toBe(500);
    apiExpect(resp.status()).toBe(200);
  });
});

test.describe.skip('Banking - CSV-Import-Journey', () => {
  // Reaktiviert 2026-06-21: Der React.lazy-Suspense-Hang der /admin/banking/*-
  // Kinderrouten ist behoben — sie nutzen jetzt lazyRoute
  // (src/lib/lazyRoute.tsx), das den dynamischen Import via setState erzwingt;
  // der lazy Inhalts-Outlet mountet im Build.

  test('CSV hochladen, Vorschau erstellen, ggf. importieren', async ({ authenticatedPage: page }) => {
    test.setTimeout(120_000);
    await page.goto('/admin/banking/import');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });

    await expect(
      page.getByRole('heading', { name: 'Transaktionen importieren' })
    ).toBeVisible({ timeout: 15000 });

    // Datei in den versteckten Input legen (ImportPage: #file-input)
    await page.setInputFiles('#file-input', {
      name: 'e2e-sparkasse.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(SPARKASSE_CSV, 'utf-8'),
    });

    // ZIELKONTO waehlen (nicht .first()!): ImportPage hat ZWEI Comboboxen —
    // den Bankformat-Selektor UND das Zielkonto-Select. "Vorschau anzeigen" ist
    // disabled, solange `selectedAccount` leer ist (ImportPage.tsx:241). Der
    // fruehere .first()-Selektor traf den Format-Selektor -> Zielkonto blieb
    // "Konto wählen..." -> Button dauerhaft disabled (verifiziert 2026-06-21).
    // Gezielt das Zielkonto-Select ueber seinen Placeholder ansprechen.
    const accountSelect = page.getByRole('combobox').filter({ hasText: /Konto wählen/ });
    await expect(accountSelect).toBeVisible({ timeout: 10000 });
    await accountSelect.click();
    await page.getByRole('option').first().click();

    const previewButton = page.getByRole('button', { name: /Vorschau anzeigen/ });
    await expect(previewButton).toBeEnabled({ timeout: 10000 });
    await previewButton.click();

    // Vorschau-Schritt MUSS erscheinen (kein 500, kein Haengenbleiben)
    const importButton = page.getByRole('button', { name: /Transaktionen importieren$/ });
    await expect(importButton).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole('button', { name: 'Zurück' })).toBeVisible();

    const label = (await importButton.textContent()) || '';
    const count = parseInt(label.trim().split(' ')[0], 10);
    expect(Number.isNaN(count)).toBeFalsy();

    if (count > 0) {
      // Neue Transaktionen -> echter Import
      await importButton.click();
      // Erfolg: Import-Spinner verschwindet wieder, kein Fehlerzustand
      await expect(
        page.getByText('Transaktionen werden importiert...')
      ).toHaveCount(0, { timeout: 60000 });
    } else {
      // Re-Run: Duplikate erkannt -> Import-Button ist ehrlich gesperrt
      await expect(importButton).toBeDisabled();
    }
  });

  test('Transaktionsliste und Zahlungsabgleich laden ohne Fehlerseite', async ({ authenticatedPage: page }) => {
    await page.goto('/admin/banking/transactions');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
    // Seite darf keinen unbehandelten Fehler zeigen
    await expect(page.getByText(/Etwas ist schiefgelaufen|[Uu]nerwarteter Fehler|Anwendungsfehler/)).toHaveCount(0);

    await page.goto('/admin/banking/reconciliation');
    await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => { /* networkidle ggf. unerreichbar: WS-Reconnect-Loop (App-Bug: ws/realtime 500) + Query-Retries auf 404-Endpoints pollen dauerhaft */ });
    await expect(
      page.getByRole('heading', { name: 'Zahlungsabgleich' })
    ).toBeVisible({ timeout: 15000 });
  });
});
