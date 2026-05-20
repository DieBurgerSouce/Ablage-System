// Finanzen-Modul: Typen und Kategorien-Definitionen

import type { DocumentCategoryInfo } from '../ablage/types';

// ==================== ENTITY TYPES ====================

/**
 * Erweiterte Entity-Types inkl. Finanzen
 */
export type FinanceEntityType = 'customer' | 'supplier' | 'finance';

// ==================== KATEGORIEN ====================

/**
 * Alle Finanz-Dokumentkategorien
 */
export type FinanceDocumentCategory =
  // Steuern-Paket
  | 'grundabgabenbescheid'
  | 'steuerbescheide'
  | 'vorauszahlungen'
  | 'steuererklärungen'
  | 'finanzamt_korrespondenz'
  // Personal-Paket
  | 'lohn_gehalt'
  | 'sozialversicherung'
  | 'berufsgenossenschaft'
  | 'arbeitsverträge'
  // Versicherungs-Paket
  | 'betriebshaftpflicht'
  | 'sachversicherungen'
  | 'kfz_versicherung'
  | 'rechtsschutz'
  // Bank-Paket
  | 'kontoauszüge'
  | 'kreditverträge'
  | 'buergschaften'
  | 'darlehen';

/**
 * Steuerart für Steuerdokumente
 */
export type TaxType =
  | 'einkommensteuer'
  | 'koerperschaftsteuer'
  | 'gewerbesteuer'
  | 'umsatzsteuer'
  | 'lohnsteuer'
  | 'kirchensteuer'
  | 'solidaritaetszuschlag'
  | 'grundsteuer'
  | 'kfz_steuer'
  | 'sonstige';

/**
 * Paket-Typ für Kategorien-Gruppierung
 */
export type FinancePackageType = 'steuern' | 'personal' | 'versicherung' | 'bank';

// ==================== INTERFACES ====================

/**
 * Erweiterte Kategorie-Info mit Paket-Zuordnung
 */
export interface FinanceCategoryInfo extends DocumentCategoryInfo {
  package: FinancePackageType;
}

/**
 * Paket-Definition für UI-Gruppierung
 */
export interface FinanceCategoryPackage {
  id: FinancePackageType;
  label: string;
  icon: string;
  color: string;
  bgColor: string;
  borderColor: string;
  categories: FinanceCategoryInfo[];
}

/**
 * Finanz-spezifische extrahierte Daten
 */
export interface FinanceExtractedData {
  // Fristen
  fälligkeitsdatum?: string;
  einspruchsfrist?: string;

  // Finanzamt-Referenzen
  aktenzeichen?: string;
  steuernummer?: string;
  finanzamt?: string;

  // Steuer-Details
  steuerart?: TaxType;
  zeitraum?: string;

  // Beträge
  nachzahlung?: number;
  erstattung?: number;

  // Versicherung/Verträge
  versicherungsnummer?: string;
  vertragsnummer?: string;
  policennummer?: string;
}

/**
 * Jahr-Ordner für Finanzen
 */
export interface FinanceYear {
  id: string;
  year: number;
  isActive: boolean;
  lastDocumentDate: string;
  documentCounts: Record<FinanceDocumentCategory, number>;
  totalDocuments: number;
  totalNachzahlung: number;
  totalErstattung: number;
  pendingDeadlines: number;
}

/**
 * Aggregationen für Finanzen-Dashboard
 */
export interface FinanceAggregations {
  totalDocuments: number;
  totalNachzahlung: number;
  totalErstattung: number;
  saldo: number;
  pendingDeadlines: number;
  documentsByPackage: Record<FinancePackageType, number>;
}

// ==================== KATEGORIEN-DEFINITIONEN ====================

/**
 * Alle Finanz-Kategorien mit Metadaten
 */
export const FINANCE_CATEGORIES: FinanceCategoryInfo[] = [
  // STEUERN-PAKET
  {
    id: 'grundabgabenbescheid',
    label: 'Grundabgabenbescheid',
    icon: 'Landmark',
    package: 'steuern'
  },
  {
    id: 'steuerbescheide',
    label: 'Steuerbescheide',
    shortCode: 'STB',
    icon: 'FileText',
    package: 'steuern'
  },
  {
    id: 'vorauszahlungen',
    label: 'Vorauszahlungen',
    shortCode: 'VAZ',
    icon: 'Calculator',
    package: 'steuern'
  },
  {
    id: 'steuererklärungen',
    label: 'Steuererklärungen',
    shortCode: 'STE',
    icon: 'ClipboardList',
    package: 'steuern'
  },
  {
    id: 'finanzamt_korrespondenz',
    label: 'Finanzamt Korrespondenz',
    icon: 'Mail',
    package: 'steuern'
  },

  // PERSONAL-PAKET
  {
    id: 'lohn_gehalt',
    label: 'Lohn & Gehalt',
    shortCode: 'LG',
    icon: 'Wallet',
    package: 'personal'
  },
  {
    id: 'sozialversicherung',
    label: 'Sozialversicherung',
    shortCode: 'SV',
    icon: 'Shield',
    package: 'personal'
  },
  {
    id: 'berufsgenossenschaft',
    label: 'Berufsgenossenschaft',
    shortCode: 'BG',
    icon: 'HardHat',
    package: 'personal'
  },
  {
    id: 'arbeitsverträge',
    label: 'Arbeitsverträge',
    shortCode: 'AV',
    icon: 'FileSignature',
    package: 'personal'
  },

  // VERSICHERUNGS-PAKET
  {
    id: 'betriebshaftpflicht',
    label: 'Betriebshaftpflicht',
    shortCode: 'BH',
    icon: 'ShieldCheck',
    package: 'versicherung'
  },
  {
    id: 'sachversicherungen',
    label: 'Sachversicherungen',
    shortCode: 'SAV',
    icon: 'Home',
    package: 'versicherung'
  },
  {
    id: 'kfz_versicherung',
    label: 'KFZ-Versicherung',
    shortCode: 'KFZ',
    icon: 'Car',
    package: 'versicherung'
  },
  {
    id: 'rechtsschutz',
    label: 'Rechtsschutz',
    shortCode: 'RS',
    icon: 'Scale',
    package: 'versicherung'
  },

  // BANK-PAKET
  {
    id: 'kontoauszüge',
    label: 'Kontoauszüge',
    shortCode: 'KA',
    icon: 'CreditCard',
    package: 'bank'
  },
  {
    id: 'kreditverträge',
    label: 'Kreditverträge',
    shortCode: 'KV',
    icon: 'FileText',
    package: 'bank'
  },
  {
    id: 'buergschaften',
    label: 'Bürgschaften',
    shortCode: 'BUE',
    icon: 'Handshake',
    package: 'bank'
  },
  {
    id: 'darlehen',
    label: 'Darlehen',
    shortCode: 'DAR',
    icon: 'Banknote',
    package: 'bank'
  },
];

/**
 * Paket-Definitionen mit Farben und Icons
 */
export const FINANCE_PACKAGES: FinanceCategoryPackage[] = [
  {
    id: 'steuern',
    label: 'Steuern',
    icon: 'Receipt',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-950',
    borderColor: 'border-emerald-200 dark:border-emerald-800',
    categories: FINANCE_CATEGORIES.filter(c => c.package === 'steuern'),
  },
  {
    id: 'personal',
    label: 'Personal',
    icon: 'Users',
    color: 'text-violet-600 dark:text-violet-400',
    bgColor: 'bg-violet-50 dark:bg-violet-950',
    borderColor: 'border-violet-200 dark:border-violet-800',
    categories: FINANCE_CATEGORIES.filter(c => c.package === 'personal'),
  },
  {
    id: 'versicherung',
    label: 'Versicherungen',
    icon: 'Shield',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-950',
    borderColor: 'border-blue-200 dark:border-blue-800',
    categories: FINANCE_CATEGORIES.filter(c => c.package === 'versicherung'),
  },
  {
    id: 'bank',
    label: 'Bank',
    icon: 'Building',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-950',
    borderColor: 'border-amber-200 dark:border-amber-800',
    categories: FINANCE_CATEGORIES.filter(c => c.package === 'bank'),
  },
];

/**
 * Kategorien mit Fristen (für spezielle Behandlung)
 */
export const FINANCE_CATEGORIES_WITH_DEADLINES = [
  'grundabgabenbescheid',
  'steuerbescheide',
  'vorauszahlungen',
];

/**
 * Kategorien mit Zahlungsbeträgen
 */
export const FINANCE_CATEGORIES_WITH_AMOUNTS = [
  'grundabgabenbescheid',
  'steuerbescheide',
  'vorauszahlungen',
  'lohn_gehalt',
  'betriebshaftpflicht',
  'sachversicherungen',
  'kfz_versicherung',
  'rechtsschutz',
  'kreditverträge',
  'darlehen',
];

/**
 * Mapping von Kategorie zu Backend document_type
 */
export const FINANCE_CATEGORY_TO_DOCUMENT_TYPE: Record<FinanceDocumentCategory, string> = {
  grundabgabenbescheid: 'tax_assessment',
  steuerbescheide: 'tax_notice',
  vorauszahlungen: 'tax_prepayment',
  steuererklärungen: 'tax_return',
  finanzamt_korrespondenz: 'tax_correspondence',
  lohn_gehalt: 'payroll',
  sozialversicherung: 'social_security',
  berufsgenossenschaft: 'trade_association',
  arbeitsverträge: 'employment_contract',
  betriebshaftpflicht: 'liability_insurance',
  sachversicherungen: 'property_insurance',
  kfz_versicherung: 'vehicle_insurance',
  rechtsschutz: 'legal_insurance',
  kontoauszüge: 'bank_statement',
  kreditverträge: 'credit_agreement',
  buergschaften: 'guarantee',
  darlehen: 'loan',
};

/**
 * Steuerart-Labels für UI
 */
export const TAX_TYPE_LABELS: Record<TaxType, string> = {
  einkommensteuer: 'Einkommensteuer',
  koerperschaftsteuer: 'Körperschaftsteuer',
  gewerbesteuer: 'Gewerbesteuer',
  umsatzsteuer: 'Umsatzsteuer',
  lohnsteuer: 'Lohnsteuer',
  kirchensteuer: 'Kirchensteuer',
  solidaritaetszuschlag: 'Solidaritätszuschlag',
  grundsteuer: 'Grundsteuer',
  kfz_steuer: 'KFZ-Steuer',
  sonstige: 'Sonstige',
};

// ==================== STRICT TYPES FOR TABLE/SORT ====================

/**
 * Strict Union Type für Sortier-Felder
 */
export type FinanceSortField = 'document_date' | 'created_at' | 'filename' | 'amount' | 'category';

/**
 * Sortier-Reihenfolge
 */
export type SortOrder = 'asc' | 'desc';

/**
 * Type-safe Icon Map für alle Kategorien
 */
export const CATEGORY_ICON_MAP: Record<FinanceDocumentCategory, string> = {
  grundabgabenbescheid: 'Landmark',
  steuerbescheide: 'FileText',
  vorauszahlungen: 'Calculator',
  steuererklärungen: 'ClipboardList',
  finanzamt_korrespondenz: 'Mail',
  lohn_gehalt: 'Wallet',
  sozialversicherung: 'Shield',
  berufsgenossenschaft: 'HardHat',
  arbeitsverträge: 'FileSignature',
  betriebshaftpflicht: 'ShieldCheck',
  sachversicherungen: 'Home',
  kfz_versicherung: 'Car',
  rechtsschutz: 'Scale',
  kontoauszüge: 'CreditCard',
  kreditverträge: 'FileText',
  buergschaften: 'Handshake',
  darlehen: 'Banknote',
} as const;

/**
 * Type-safe Package Icon Map
 */
export const PACKAGE_ICON_MAP: Record<FinancePackageType, string> = {
  steuern: 'Receipt',
  personal: 'Users',
  versicherung: 'Shield',
  bank: 'Building',
} as const;

// ==================== HELPER FUNCTIONS ====================

/**
 * Findet Kategorie-Info anhand der ID
 */
export function getFinanceCategoryById(categoryId: string): FinanceCategoryInfo | undefined {
  return FINANCE_CATEGORIES.find(c => c.id === categoryId);
}

/**
 * Findet Paket anhand der ID
 */
export function getFinancePackageById(packageId: FinancePackageType): FinanceCategoryPackage | undefined {
  return FINANCE_PACKAGES.find(p => p.id === packageId);
}

/**
 * Prüft ob Kategorie Fristen hat
 */
export function categoryHasDeadlines(categoryId: string): boolean {
  return FINANCE_CATEGORIES_WITH_DEADLINES.includes(categoryId);
}

/**
 * Prüft ob Kategorie Beträge hat
 */
export function categoryHasAmounts(categoryId: string): boolean {
  return FINANCE_CATEGORIES_WITH_AMOUNTS.includes(categoryId);
}
