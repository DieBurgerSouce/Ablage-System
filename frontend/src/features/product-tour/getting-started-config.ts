/**
 * Getting Started Konfiguration
 *
 * Definiert die Checklist-Items fuer neue Benutzer.
 * Completion wird via localStorage getrackt.
 *
 * Die Haupt-GettingStartedChecklist in components/GettingStartedChecklist.tsx
 * verwendet ihre eigenen CHECKLIST_ITEMS. Diese Konfiguration bietet
 * zusaetzliche Items, die programmatisch getrackt werden koennen.
 */

export interface GettingStartedItem {
  id: string
  label: string
  description: string
  storageKey: string
}

const STORAGE_PREFIX = 'ablage-gs-'

export const GETTING_STARTED_ITEMS: GettingStartedItem[] = [
  {
    id: 'company_setup',
    label: 'Firma eingerichtet',
    description: 'Richten Sie Ihre Firmendaten ein (Name, Adresse, Steuernummer)',
    storageKey: `${STORAGE_PREFIX}company_setup`,
  },
  {
    id: 'first_upload',
    label: 'Erstes Dokument hochgeladen',
    description: 'Laden Sie Ihr erstes Dokument hoch und lassen Sie es per OCR verarbeiten',
    storageKey: `${STORAGE_PREFIX}first_upload`,
  },
  {
    id: 'first_correction',
    label: 'Erste OCR-Korrektur gemacht',
    description: 'Korrigieren Sie ein OCR-Ergebnis, um das System zu verbessern',
    storageKey: `${STORAGE_PREFIX}first_correction`,
  },
  {
    id: 'first_search',
    label: 'Erste Suche durchgefuehrt',
    description: 'Finden Sie ein Dokument ueber die Schnellsuche',
    storageKey: `${STORAGE_PREFIX}first_search`,
  },
  {
    id: 'entity_linked',
    label: 'Dokument mit Lieferant verknuepft',
    description: 'Verknuepfen Sie ein Dokument mit einem Lieferanten oder Kunden',
    storageKey: `${STORAGE_PREFIX}entity_linked`,
  },
]

/**
 * Markiert ein Getting-Started-Item als abgeschlossen
 */
export function markGettingStartedComplete(itemId: string): void {
  const item = GETTING_STARTED_ITEMS.find((i) => i.id === itemId)
  if (item) {
    window.localStorage.setItem(item.storageKey, 'true')
  }
}

/**
 * Prueft ob ein Getting-Started-Item abgeschlossen ist
 */
export function isGettingStartedComplete(itemId: string): boolean {
  const item = GETTING_STARTED_ITEMS.find((i) => i.id === itemId)
  if (!item) return false
  return window.localStorage.getItem(item.storageKey) === 'true'
}

/**
 * Gibt die Anzahl abgeschlossener Items zurueck
 */
export function getGettingStartedProgress(): { completed: number; total: number } {
  const completed = GETTING_STARTED_ITEMS.filter((item) =>
    window.localStorage.getItem(item.storageKey) === 'true'
  ).length
  return { completed, total: GETTING_STARTED_ITEMS.length }
}
