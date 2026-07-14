/**
 * Trust-Theater K1 — Live-Beweis-Screenshots (2026-07-12)
 *
 * Standalone-Playwright-Skript (kein Test-Runner):
 *  ① Grüner Beweis LIVE gegen das echte archivierte Dokument
 *  ② Roter Beweis über Response-Interception (das echte Archiv wird
 *     NIEMALS manipuliert — Backend-Rot ist in
 *     tests/unit/test_prove_integrity_logic.py isoliert bewiesen)
 *
 * Aufruf: node e2e/perception/trust-proof.mjs <documentId>
 */
import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const BASE = process.env.TRUST_BASE_URL || 'http://localhost'
const DOC_ID = process.argv[2]
const OUT_DIR = path.resolve(
  process.cwd(),
  '..',
  'docs/qa-reports/trust-theater-2026-07/screenshots'
)

if (!DOC_ID) {
  console.error('Nutzung: node trust-proof.mjs <documentId>')
  process.exit(1)
}
fs.mkdirSync(OUT_DIR, { recursive: true })

const TAMPERED_PROOF = {
  document_id: DOC_ID,
  verdict: 'tampered',
  file_hash_matches: false,
  baseline_source: 'archiv',
  stored_hash: '5b24928acf74bc08697dc6a5e9c92455e2935f09e35840e0e491f16940364e80',
  computed_hash: 'deadbeef00000000000000000000000000000000000000000000000000000000',
  hash_algorithm: 'sha256',
  archived_at: '2026-07-12T19:40:00Z',
  archive_id: 'a83f1060-af61-4b64-8a01-8b35f6e29a4f',
  chain: {
    entries_total: 3,
    entries_verified: 3,
    valid: true,
    broken_at_sequence: null,
    first_entry_at: '2026-07-12T19:40:00Z',
    last_entry_at: '2026-07-12T19:45:00Z',
    message: '3 Protokoll-Einträge geprüft — Verkettung lückenlos intakt.',
  },
  tsa: {
    present: false,
    valid: null,
    message:
      'Kein qualifizierter RFC-3161-Zeitstempel vorhanden — die Versiegelung basiert auf der internen Hash-Beweiskette.',
  },
  verified_at: new Date('2026-07-12T20:05:00Z').toISOString(),
  message_de:
    'Integritätsprüfung FEHLGESCHLAGEN: Der aktuelle Dateiinhalt stimmt NICHT mit dem versiegelten Archiv-Hash überein — mögliche Manipulation! Dokument nicht weiterverwenden, umgehend den Administrator informieren und das Original aus dem Backup wiederherstellen.',
}

async function dismissOverlays(page) {
  const wizardSkip = page
    .getByRole('button', { name: /Onboarding ueberspringen|Onboarding überspringen/i })
    .first()
  if (await wizardSkip.isVisible({ timeout: 3000 }).catch(() => false)) {
    await wizardSkip.click({ timeout: 5000 }).catch(() => undefined)
    await page.waitForTimeout(600)
  }
  for (let i = 0; i < 3; i += 1) {
    await page.keyboard.press('Escape').catch(() => undefined)
    await page.waitForTimeout(250)
  }
}

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1600, height: 950 } })
const page = await context.newPage()

// Onboarding unterdruecken (Keys aus helpers.ts suppressOnboarding)
await page.addInitScript(() => {
  window.localStorage.setItem('ablage_onboarding_v2', JSON.stringify({ completed: true }))
  window.localStorage.setItem('ablage_onboarding_complete', 'true')
  window.localStorage.setItem('ablage-first-visit-done', 'true')
})

// ---------- Login (prokurist, Perception-Persona) ----------
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.locator('#email').fill('prokurist@localhost.com')
await page.locator('#password').fill('prokurist123')
const [resp] = await Promise.all([
  page
    .waitForResponse((r) => r.url().includes('/api/v1/auth/login'), { timeout: 30000 })
    .catch(() => null),
  page.locator('button[type="submit"]').click(),
])
if (resp && resp.status() === 429) {
  console.log('[LOGIN] 429 — 65s Backoff')
  await page.waitForTimeout(65000)
  await page.locator('#password').fill('prokurist123')
  await page.locator('button[type="submit"]').click()
}
await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 30000 })
console.log('[LOGIN] ok')
await dismissOverlays(page)

// ---------- ① Detailseite + Badge + gruener Live-Beweis ----------
await page.goto(`${BASE}/documents/${DOC_ID}`, { waitUntil: 'domcontentloaded' })
await dismissOverlays(page)
await page.waitForSelector('[data-testid="document-integrity-panel"]', { timeout: 30000 })
// Badge fertig geladen (nicht mehr "wird geladen")
await page
  .waitForFunction(
    () =>
      !document
        .querySelector('[data-testid="document-integrity-panel"]')
        ?.textContent?.includes('wird geladen'),
    { timeout: 20000 }
  )
  .catch(() => undefined)
await page.screenshot({
  path: path.join(OUT_DIR, '01-detail-header-mit-siegel-badge.png'),
  fullPage: false,
})
console.log('[SHOT] 01 Badge')

await page.locator('[data-testid="prove-integrity-button"]').click()
await page.waitForSelector('[data-testid="integrity-result"]', { timeout: 60000 })
const verdictGruen = await page
  .locator('[data-testid="integrity-result"]')
  .getAttribute('data-verdict')
console.log('[PROOF] Live-Verdict:', verdictGruen)
// Technische Details aufklappen fuer den Beweis-Screenshot
const detailsBtn = page.getByRole('button', { name: /Technische Details/i })
if (await detailsBtn.isVisible().catch(() => false)) {
  const expanded = await page
    .locator('[data-testid="integrity-technical-details"]')
    .isVisible()
    .catch(() => false)
  if (!expanded) await detailsBtn.click()
  await page.waitForTimeout(400)
}
await page.screenshot({
  path: path.join(OUT_DIR, '02-beweis-gruen-live.png'),
  fullPage: false,
})
console.log('[SHOT] 02 Gruen (live)')
if (verdictGruen !== 'verified') {
  console.error(`FEHLER: Live-Beweis nicht gruen (verdict=${verdictGruen})`)
  await browser.close()
  process.exit(2)
}
await page.keyboard.press('Escape')
await page.waitForTimeout(500)

// ---------- ② Roter Beweis (Interception — echtes Archiv unberuehrt) ----------
await page.route('**/integrity/documents/**/prove', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(TAMPERED_PROOF),
  })
})
await page.locator('[data-testid="prove-integrity-button"]').click()
await page.waitForSelector('[data-testid="integrity-result"][data-verdict="tampered"]', {
  timeout: 30000,
})
await page.waitForTimeout(400)
await page.screenshot({
  path: path.join(OUT_DIR, '03-beweis-rot-manipulation-erkannt.png'),
  fullPage: false,
})
console.log('[SHOT] 03 Rot (Interception)')

await browser.close()
console.log('FERTIG — Screenshots unter', OUT_DIR)
