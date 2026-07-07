/**
 * Eingefrorene Module — Odoo-Neuausrichtung (Phase 1, Freeze-Gates)
 *
 * Statischer Spiegel des Backend-Freeze (app/core/module_registry.py):
 * Seit der Odoo-Umstellung (Go-Live 08/2026) übernimmt Odoo die ERP-Prozesse
 * (Banking, Mahnwesen, Buchhaltung, Fakturierung, DATEV, E-Rechnung-Erzeugung, …).
 * Die hier gelisteten Frontend-Sektionen sind eingefroren: Ihre Parent-Routen
 * leiten per beforeLoad auf /frozen um, die Sidebar bietet sie nicht mehr an.
 * Das Backend liefert für die zugehörigen Router 404.
 *
 * TODO: später via GET /api/v1/system/modules hydratisieren (Backend-Registry
 * als Quelle der Wahrheit; bis dahin müssen Backend- und Frontend-Liste manuell
 * synchron gehalten werden — identische Modul-Keys!).
 *
 * BEWUSST AKTIV GELASSEN (Kandidaten, konservativ NICHT eingefroren):
 * - /finanzen (Ablage-Ansicht „Finanz- & Steuerdokumente nach Jahr" inkl. Upload/
 *   Versionen → Archiv-Kern, KEIN ERP-Doppel; nur /finanzen/zahlungsverhalten
 *   ist als Analytics-Subroute eingefroren)
 * - /tax-package (Steuerberater-Paket; StB erhält DATEV künftig aus Odoo)
 * - /admin/risk-scoring (Admin-Dashboard des eingefrorenen Risk-Moduls)
 * - /admin/digital-twin (Admin-Konfig des eingefrorenen Digital-Twin)
 * - /admin/dunning-templates + /admin/automation/dunning (Mahnwesen-Randflächen)
 * - /reports/cashflow-forecast (Berichte bleiben laut Vorgabe aktiv)
 * - /matching (3-Way-Matching; laut Vorgabe aktiv)
 * - /sendungen (Kandidat, laut Vorgabe aktiv)
 * - /inventory (Lagerverwaltung; Odoo übernimmt Lager — Kandidat für Welle 2)
 * - /admin/ai-admin, /admin/ai-decisions, /admin/autonomous, /automation
 *   (Dokument-Automatisierung/KI-Verwaltung des Archiv-Workflows)
 * - zero-touch: keine eigene Frontend-Route vorhanden (nichts einzufrieren)
 */

import { redirect } from '@tanstack/react-router'

export type FrozenModuleKey =
  | 'banking'
  | 'accounting'
  | 'finance'
  | 'invoice_tracking'
  | 'datev'
  | 'einvoice'
  | 'streckengeschaeft'
  | 'lexware'
  | 'holding'
  | 'kasse'
  | 'risk_finanzki'
  | 'ai_speculative'
  | 'document_chains'

export interface FrozenSection {
  /** Modul-Key — identisch mit dem Backend-Key in app/core/module_registry.py */
  key: FrozenModuleKey
  /** Deutsches Label für die „Modul eingefroren"-Seite */
  label: string
  /** Routen-Präfixe (segmentgenau gematcht: exakter Pfad oder Präfix + '/') */
  routePrefixes: string[]
}

export const FROZEN_SECTIONS: FrozenSection[] = [
  {
    key: 'banking',
    label: 'Banking, Zahlungsverkehr & Mahnwesen',
    routePrefixes: ['/banking', '/admin/banking', '/admin/mahnungen'],
  },
  {
    key: 'accounting',
    label: 'Buchhaltung (USt-VA, BWA, EÜR, ELSTER)',
    routePrefixes: ['/german-finance', '/admin/euer-export', '/admin/elster-export'],
  },
  {
    key: 'finance',
    label: 'Finanz-Analysen & Forecasting',
    routePrefixes: [
      '/finanzen/zahlungsverhalten',
      '/cashflow',
      '/po-matching',
      '/recurring-invoices',
      '/spesen',
    ],
  },
  {
    key: 'invoice_tracking',
    label: 'Rechnungsverfolgung & Rechnungsworkflow',
    routePrefixes: ['/invoice-workflow', '/admin/rechnungen'],
  },
  {
    key: 'datev',
    label: 'DATEV-Export & DATEVconnect',
    routePrefixes: ['/admin/datev', '/admin/datev-connect'],
  },
  {
    key: 'einvoice',
    label: 'E-Rechnung (Erzeugung)',
    routePrefixes: ['/admin/einvoice'],
  },
  {
    key: 'streckengeschaeft',
    label: 'Streckengeschäft',
    routePrefixes: ['/streckengeschaeft'],
  },
  {
    key: 'lexware',
    label: 'Lexware-Import',
    routePrefixes: ['/admin/lexware'],
  },
  {
    key: 'holding',
    label: 'Holding & Intercompany',
    routePrefixes: ['/holding'],
  },
  {
    key: 'kasse',
    label: 'Kassenbuch',
    routePrefixes: ['/kasse'],
  },
  {
    key: 'risk_finanzki',
    label: 'Risiko-Scoring & Fraud Detection',
    routePrefixes: ['/risk', '/fraud'],
  },
  {
    key: 'ai_speculative',
    label: 'KI-Analyse & experimentelle Bereiche',
    routePrefixes: [
      '/predictive',
      '/digital-twin',
      '/command-center',
      '/proactive-assistant',
      '/trust-dashboard',
      '/executive',
      '/smart-dashboard',
      '/ki-pipeline',
      '/ml-dashboard',
      '/knowledge-graph',
      '/adhoc-reporting',
      '/admin/esg',
    ],
  },
  {
    key: 'document_chains',
    label: 'Auftragsketten',
    routePrefixes: ['/document-chains'],
  },
]

/**
 * Prüft segmentgenau, ob ein Pfad zu einer eingefrorenen Sektion gehört.
 * '/admin/datev' matcht '/admin/datev' und '/admin/datev/export',
 * aber NICHT '/admin/datev-connect' (eigener Präfix-Eintrag).
 */
export function isPathFrozen(pathname: string): { frozen: boolean; key?: FrozenModuleKey } {
  for (const section of FROZEN_SECTIONS) {
    for (const prefix of section.routePrefixes) {
      if (pathname === prefix || pathname.startsWith(prefix + '/')) {
        return { frozen: true, key: section.key }
      }
    }
  }
  return { frozen: false }
}

/** Liefert die Sektion zu einem Modul-Key (z. B. für die /frozen-Seite). */
export function getFrozenSection(key: string | undefined): FrozenSection | undefined {
  if (!key) {
    return undefined
  }
  return FROZEN_SECTIONS.find((section) => section.key === key)
}

/**
 * Guard für beforeLoad der eingefrorenen Sektions-Routen.
 * Wirft immer einen Redirect auf die statische „Modul eingefroren"-Seite.
 * Bewusst statisch (kein API-Call) — Router-Registrierung/Freeze ist eine
 * Deploy-Zeit-Entscheidung, keine Laufzeit-Evaluation.
 */
export function frozenModuleGuard(key: FrozenModuleKey): never {
  throw redirect({ to: '/frozen', search: { module: key }, replace: true })
}
