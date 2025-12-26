/**
 * Ablage-Struktur:
 *
 * Kunden (Liste)
 *   └── Kunde (z.B. Mustermann GmbH)
 *         └── Spargelmesser (Ablage-Ordner)
 *               └── Anfragen, Angebote, Rechnungen, etc.
 *         └── Folie (Ablage-Ordner)
 *               └── Anfragen, Angebote, Rechnungen, etc.
 *
 * Lieferanten (Liste)
 *   └── Lieferant (z.B. Technik Zulieferer AG)
 *         └── Spargelmesser1 (Ablage-Ordner)
 *               └── Anfragen, Angebote, Bestellungen, etc.
 *         └── Folie (Ablage-Ordner)
 *               └── Anfragen, Angebote, Bestellungen, etc.
 */

import type { DocumentCounts } from './types'

// ==================== TYPES ====================

export interface Customer {
  id: string
  name: string
  displayName: string
  isActive: boolean
  lastActivityDate: string
  /** Ordner innerhalb dieses Kunden */
  folders: CustomerFolder[]
}

export interface CustomerFolder {
  id: 'spargelmesser' | 'folie'
  name: string
  documentCounts: DocumentCounts
  totalDocuments: number
  lastDocumentDate: string
}

export interface Supplier {
  id: string
  name: string
  displayName: string
  isActive: boolean
  lastActivityDate: string
  /** Ordner innerhalb dieses Lieferanten */
  folders: SupplierFolder[]
}

export interface SupplierFolder {
  id: 'spargelmesser1' | 'folie'
  name: string
  documentCounts: DocumentCounts
  totalDocuments: number
  lastDocumentDate: string
}

// ==================== KUNDEN ====================

export const MOCK_CUSTOMERS: Customer[] = [
  {
    id: 'mustermann-gmbh',
    name: 'Mustermann GmbH',
    displayName: 'Mustermann GmbH',
    isActive: true,
    lastActivityDate: '2024-12-20',
    folders: [
      {
        id: 'spargelmesser',
        name: 'Spargelmesser',
        documentCounts: {
          anfragen: 5,
          angebote: 12,
          auftragsbestaetigung: 8,
          lieferscheine: 6,
          rechnungen: 24,
          storno: 2,
          mahnungen: 1,
          offene_rechnungen: 3,
          offene_angebote: 4,
          offene_anfragen: 2,
          reklamation: 1,
          kommunikation: 15,
          archiv: 8,
        },
        totalDocuments: 89,
        lastDocumentDate: '2024-12-20',
      },
      {
        id: 'folie',
        name: 'Folie',
        documentCounts: {
          anfragen: 2,
          angebote: 6,
          auftragsbestaetigung: 4,
          lieferscheine: 3,
          rechnungen: 15,
          storno: 0,
          mahnungen: 0,
          offene_rechnungen: 1,
          offene_angebote: 2,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 5,
          archiv: 2,
        },
        totalDocuments: 40,
        lastDocumentDate: '2024-12-18',
      },
    ],
  },
  {
    id: 'schmidt-metallbau',
    name: 'Schmidt Metallbau AG',
    displayName: 'Schmidt Metallbau',
    isActive: true,
    lastActivityDate: '2024-12-22',
    folders: [
      {
        id: 'spargelmesser',
        name: 'Spargelmesser',
        documentCounts: {
          anfragen: 8,
          angebote: 15,
          auftragsbestaetigung: 10,
          lieferscheine: 12,
          rechnungen: 35,
          storno: 1,
          mahnungen: 2,
          offene_rechnungen: 5,
          offene_angebote: 3,
          offene_anfragen: 1,
          reklamation: 2,
          kommunikation: 20,
          archiv: 12,
        },
        totalDocuments: 126,
        lastDocumentDate: '2024-12-22',
      },
      {
        id: 'folie',
        name: 'Folie',
        documentCounts: {
          anfragen: 1,
          angebote: 3,
          auftragsbestaetigung: 2,
          lieferscheine: 2,
          rechnungen: 8,
          storno: 0,
          mahnungen: 0,
          offene_rechnungen: 0,
          offene_angebote: 1,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 3,
          archiv: 1,
        },
        totalDocuments: 21,
        lastDocumentDate: '2024-12-15',
      },
    ],
  },
  {
    id: 'technik-partner',
    name: 'Technik Partner GmbH & Co. KG',
    displayName: 'Technik Partner',
    isActive: true,
    lastActivityDate: '2024-12-19',
    folders: [
      {
        id: 'spargelmesser',
        name: 'Spargelmesser',
        documentCounts: {
          anfragen: 3,
          angebote: 7,
          auftragsbestaetigung: 5,
          lieferscheine: 4,
          rechnungen: 18,
          storno: 0,
          mahnungen: 0,
          offene_rechnungen: 2,
          offene_angebote: 1,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 8,
          archiv: 5,
        },
        totalDocuments: 53,
        lastDocumentDate: '2024-12-19',
      },
      {
        id: 'folie',
        name: 'Folie',
        documentCounts: {
          anfragen: 4,
          angebote: 9,
          auftragsbestaetigung: 6,
          lieferscheine: 5,
          rechnungen: 22,
          storno: 1,
          mahnungen: 0,
          offene_rechnungen: 1,
          offene_angebote: 2,
          offene_anfragen: 1,
          reklamation: 1,
          kommunikation: 10,
          archiv: 6,
        },
        totalDocuments: 68,
        lastDocumentDate: '2024-12-17',
      },
    ],
  },
  {
    id: 'weber-elektronik',
    name: 'Weber Elektronik Systems GmbH',
    displayName: 'Weber Elektronik',
    isActive: false,
    lastActivityDate: '2024-11-30',
    folders: [
      {
        id: 'spargelmesser',
        name: 'Spargelmesser',
        documentCounts: {
          anfragen: 2,
          angebote: 4,
          auftragsbestaetigung: 3,
          lieferscheine: 3,
          rechnungen: 12,
          storno: 0,
          mahnungen: 0,
          offene_rechnungen: 0,
          offene_angebote: 0,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 5,
          archiv: 10,
        },
        totalDocuments: 39,
        lastDocumentDate: '2024-11-30',
      },
      {
        id: 'folie',
        name: 'Folie',
        documentCounts: {
          anfragen: 1,
          angebote: 2,
          auftragsbestaetigung: 1,
          lieferscheine: 1,
          rechnungen: 5,
          storno: 0,
          mahnungen: 0,
          offene_rechnungen: 0,
          offene_angebote: 0,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 2,
          archiv: 4,
        },
        totalDocuments: 16,
        lastDocumentDate: '2024-11-25',
      },
    ],
  },
]

// ==================== LIEFERANTEN ====================

export const MOCK_SUPPLIERS: Supplier[] = [
  {
    id: 'zulieferer-nord',
    name: 'Zulieferer Nord GmbH',
    displayName: 'Zulieferer Nord',
    isActive: true,
    lastActivityDate: '2024-12-21',
    folders: [
      {
        id: 'spargelmesser1',
        name: 'Spargelmesser1',
        documentCounts: {
          anfragen: 3,
          angebote: 8,
          bestellungen: 15,
          auftragsbestaetigung: 12,
          lieferscheine: 10,
          rechnungen: 42,
          storno: 1,
          mahnungen: 0,
          offene_rechnungen: 2,
          offene_angebote: 1,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 8,
          archiv: 6,
        },
        totalDocuments: 108,
        lastDocumentDate: '2024-12-21',
      },
      {
        id: 'folie',
        name: 'Folie',
        documentCounts: {
          anfragen: 1,
          angebote: 4,
          bestellungen: 7,
          auftragsbestaetigung: 5,
          lieferscheine: 6,
          rechnungen: 18,
          storno: 0,
          mahnungen: 0,
          offene_rechnungen: 0,
          offene_angebote: 0,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 3,
          archiv: 2,
        },
        totalDocuments: 46,
        lastDocumentDate: '2024-12-19',
      },
    ],
  },
  {
    id: 'material-express',
    name: 'Material Express AG',
    displayName: 'Material Express',
    isActive: true,
    lastActivityDate: '2024-12-20',
    folders: [
      {
        id: 'spargelmesser1',
        name: 'Spargelmesser1',
        documentCounts: {
          anfragen: 5,
          angebote: 12,
          bestellungen: 20,
          auftragsbestaetigung: 18,
          lieferscheine: 15,
          rechnungen: 55,
          storno: 2,
          mahnungen: 1,
          offene_rechnungen: 4,
          offene_angebote: 2,
          offene_anfragen: 1,
          reklamation: 1,
          kommunikation: 12,
          archiv: 8,
        },
        totalDocuments: 156,
        lastDocumentDate: '2024-12-20',
      },
      {
        id: 'folie',
        name: 'Folie',
        documentCounts: {
          anfragen: 2,
          angebote: 6,
          bestellungen: 10,
          auftragsbestaetigung: 8,
          lieferscheine: 9,
          rechnungen: 28,
          storno: 0,
          mahnungen: 0,
          offene_rechnungen: 1,
          offene_angebote: 1,
          offene_anfragen: 0,
          reklamation: 0,
          kommunikation: 5,
          archiv: 3,
        },
        totalDocuments: 73,
        lastDocumentDate: '2024-12-18',
      },
    ],
  },
  {
    id: 'stahl-mueller',
    name: 'Stahlwerk Mueller GmbH & Co. KG',
    displayName: 'Stahl Mueller',
    isActive: true,
    lastActivityDate: '2024-12-22',
    folders: [
      {
        id: 'spargelmesser1',
        name: 'Spargelmesser1',
        documentCounts: {
          anfragen: 6,
          angebote: 14,
          bestellungen: 25,
          auftragsbestaetigung: 22,
          lieferscheine: 20,
          rechnungen: 68,
          storno: 3,
          mahnungen: 2,
          offene_rechnungen: 6,
          offene_angebote: 3,
          offene_anfragen: 2,
          reklamation: 2,
          kommunikation: 15,
          archiv: 10,
        },
        totalDocuments: 198,
        lastDocumentDate: '2024-12-22',
      },
      {
        id: 'folie',
        name: 'Folie',
        documentCounts: {
          anfragen: 3,
          angebote: 8,
          bestellungen: 12,
          auftragsbestaetigung: 10,
          lieferscheine: 11,
          rechnungen: 35,
          storno: 1,
          mahnungen: 0,
          offene_rechnungen: 2,
          offene_angebote: 1,
          offene_anfragen: 0,
          reklamation: 1,
          kommunikation: 7,
          archiv: 4,
        },
        totalDocuments: 95,
        lastDocumentDate: '2024-12-20',
      },
    ],
  },
]

// ==================== HELPER FUNCTIONS ====================

/**
 * Alle Kunden abrufen
 */
export function getAllCustomers(): Customer[] {
  return MOCK_CUSTOMERS
}

/**
 * Kunde nach ID finden
 */
export function getCustomerById(customerId: string): Customer | undefined {
  return MOCK_CUSTOMERS.find((c) => c.id === customerId)
}

/**
 * Ordner eines Kunden finden
 */
export function getCustomerFolder(
  customerId: string,
  folderId: string
): CustomerFolder | undefined {
  const customer = getCustomerById(customerId)
  return customer?.folders.find((f) => f.id === folderId)
}

/**
 * Alle Lieferanten abrufen
 */
export function getAllSuppliers(): Supplier[] {
  return MOCK_SUPPLIERS
}

/**
 * Lieferant nach ID finden
 */
export function getSupplierById(supplierId: string): Supplier | undefined {
  return MOCK_SUPPLIERS.find((s) => s.id === supplierId)
}

/**
 * Ordner eines Lieferanten finden
 */
export function getSupplierFolder(
  supplierId: string,
  folderId: string
): SupplierFolder | undefined {
  const supplier = getSupplierById(supplierId)
  return supplier?.folders.find((f) => f.id === folderId)
}

/**
 * Gesamtanzahl Dokumente eines Kunden
 */
export function getCustomerTotalDocuments(customer: Customer): number {
  return customer.folders.reduce((sum, f) => sum + f.totalDocuments, 0)
}

/**
 * Gesamtanzahl offene Rechnungen eines Kunden
 */
export function getCustomerOpenInvoices(customer: Customer): number {
  return customer.folders.reduce((sum, f) => sum + (f.documentCounts.offene_rechnungen ?? 0), 0)
}

/**
 * Gesamtanzahl Dokumente eines Lieferanten
 */
export function getSupplierTotalDocuments(supplier: Supplier): number {
  return supplier.folders.reduce((sum, f) => sum + f.totalDocuments, 0)
}

/**
 * Gesamtanzahl offene Rechnungen eines Lieferanten
 */
export function getSupplierOpenInvoices(supplier: Supplier): number {
  return supplier.folders.reduce((sum, f) => sum + (f.documentCounts.offene_rechnungen ?? 0), 0)
}
