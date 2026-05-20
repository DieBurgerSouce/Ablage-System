/**
 * Invoice Tracking Types
 *
 * TypeScript Typen für das Rechnungsverfolgung-Feature.
 * Konsistent mit Backend-Schema: InvoiceTracking Model und API Responses.
 */

// ==================== Status Enums ====================

export type InvoiceStatus =
  | 'open'       // Offen
  | 'sent'       // Versendet
  | 'paid'       // Bezahlt
  | 'overdue'    // Überfällig
  | 'dunning'    // In Mahnung
  | 'cancelled'  // Storniert
  | 'partial';   // Teilbezahlt

export type DunningLevel = 0 | 1 | 2 | 3 | 4;

// ==================== Skonto Types ====================

/**
 * Skonto-Informationen für eine Rechnung
 */
export interface SkontoInfo {
  percentage: number | null;      // z.B. 2.0 für 2%
  days: number | null;            // Tage für Skonto-Frist
  deadline: string | null;        // ISO Date der Frist
  amount: number | null;          // Berechneter Skonto-Betrag
  used: boolean;                  // True wenn Skonto genutzt wurde
  netAmount: number | null;       // Betrag nach Skonto-Abzug
}

/**
 * Skonto-Update Payload
 */
export interface SkontoUpdate {
  percentage?: number;
  days?: number;
}

/**
 * Bevorstehende Skonto-Frist
 */
export interface UpcomingSkontoDeadline {
  invoiceId: string;
  invoiceNumber: string | null;
  deadline: string;
  daysUntilDeadline: number;
  skontoAmount: number;
  skontoPercentage: number;
  totalAmount: number;
  businessEntityName?: string;
}

// ==================== Teilzahlung Types ====================

/**
 * Einzelne Zahlung (Teilzahlung)
 */
export interface PaymentTransaction {
  id: string;
  invoiceTrackingId: string;
  amount: number;
  paidAt: string;
  paymentMethod: string | null;
  reference: string | null;
  bankTransactionId: string | null;
  reconciliationStatus: 'pending' | 'matched' | 'unmatched';
  notes: string | null;
  createdAt: string;
}

/**
 * Backend Response für PaymentTransaction
 */
export interface PaymentTransactionBackend {
  id: string;
  invoice_tracking_id: string;
  amount: number;
  paid_at: string;
  payment_method: string | null;
  reference: string | null;
  bank_transaction_id: string | null;
  reconciliation_status: 'pending' | 'matched' | 'unmatched';
  notes: string | null;
  created_at: string;
}

/**
 * Payload zum Erfassen einer Teilzahlung
 */
export interface PaymentCreate {
  amount: number;
  paidAt?: string;
  paymentMethod?: string;
  reference?: string;
  notes?: string;
}

/**
 * Zahlungsübersicht für eine Rechnung
 */
export interface PaymentSummary {
  totalPaid: number;
  outstandingAmount: number;
  paymentCount: number;
  payments: PaymentTransaction[];
  isFullyPaid: boolean;
}

// ==================== API Response Types ====================

/**
 * Einzelne Rechnungsverfolgung (Backend Response)
 */
export interface InvoiceTrackingResponse {
  id: string;
  documentId: string;
  invoiceNumber: string | null;
  invoiceDate: string | null;
  dueDate: string | null;
  amount: number;
  currency: string;
  status: InvoiceStatus;
  dunningLevel: DunningLevel;
  paidAt: string | null;
  paidAmount: number | null;
  lastDunningAt: string | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
  // Computed fields (from API)
  isOverdue: boolean;
  daysOverdue: number;
  // Skonto-Felder (NEU)
  skontoPercentage: number | null;
  skontoDays: number | null;
  skontoDeadline: string | null;
  skontoAmount: number | null;
  skontoUsed: boolean;
  // Teilzahlung-Felder (NEU)
  outstandingAmount: number | null;
  isPartialPayment: boolean;
}

/**
 * Backend Response (snake_case) - für Transformer
 */
export interface InvoiceTrackingBackend {
  id: string;
  document_id: string;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  amount: number;
  currency: string;
  status: InvoiceStatus;
  dunning_level: DunningLevel;
  paid_at: string | null;
  paid_amount: number | null;
  last_dunning_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  is_overdue?: boolean;
  days_overdue?: number;
  // Skonto-Felder (NEU)
  skonto_percentage?: number | null;
  skonto_days?: number | null;
  skonto_deadline?: string | null;
  skonto_amount?: number | null;
  skonto_used?: boolean;
  // Teilzahlung-Felder (NEU)
  outstanding_amount?: number | null;
  is_partial_payment?: boolean;
}

/**
 * Statistiken Response
 */
export interface InvoiceStatisticsResponse {
  totalInvoices: number;
  totalAmount: number;
  statusDistribution: Record<string, { count: number; amount: number }>;
  overdueInvoices: {
    count: number;
    amount: number;
  };
  generatedAt: string;
}

/**
 * Backend Statistics Response
 * (Note: Statistics use camelCase unlike InvoiceTrackingBackend)
 */
export interface InvoiceStatisticsBackend {
  totalInvoices: number;
  totalAmount: number;
  statusDistribution: Record<string, { count: number; amount: number }>;
  overdueInvoices: {
    count: number;
    amount: number;
  };
  generatedAt: string;
}

// ==================== Filter Types ====================

/**
 * Filter für Rechnungsliste
 */
export interface InvoiceFilter {
  page: number;
  perPage: number;
  status?: InvoiceStatus;
  overdueOnly?: boolean;
  documentId?: string;
}

// ==================== Create/Update Types ====================

/**
 * Payload zum Erstellen einer Rechnungsverfolgung
 */
export interface InvoiceTrackingCreate {
  documentId: string;
  invoiceNumber?: string;
  invoiceDate?: string;
  dueDate: string;
  amount: number;
  currency?: string;
  status?: InvoiceStatus;
}

/**
 * Payload zum Aktualisieren einer Rechnungsverfolgung
 */
export interface InvoiceTrackingUpdate {
  invoiceNumber?: string;
  invoiceDate?: string;
  dueDate?: string;
  amount?: number;
  currency?: string;
  status?: InvoiceStatus;
  paidAt?: string;
  paidAmount?: number;
  notes?: string;
}

// ==================== UI Types ====================

/**
 * UI Labels (Deutsch)
 */
export const UI_LABELS = {
  // Page
  pageTitle: 'Rechnungsverfolgung',
  tabOverview: 'Übersicht',
  tabAllInvoices: 'Alle Rechnungen',

  // Stats
  statOpenAmount: 'Offene Forderungen',
  statOverdueAmount: 'Überfällige Forderungen',
  statAvgPaymentDays: 'Ø Zahlungsziel',
  statActiveDunnings: 'Aktive Mahnungen',

  // Actions
  actionMarkPaid: 'Als bezahlt markieren',
  actionIncreaseDunning: 'Mahnstufe erhöhen',
  actionViewDetails: 'Details anzeigen',
  actionEdit: 'Bearbeiten',
  actionDelete: 'Löschen',

  // Toasts
  successMarkPaid: 'Rechnung als bezahlt markiert',
  successIncreaseDunning: 'Mahnstufe erhöht',
  successCreate: 'Rechnungsverfolgung erstellt',
  successUpdate: 'Rechnungsverfolgung aktualisiert',
  successDelete: 'Rechnungsverfolgung gelöscht',

  // Errors
  errorLoad: 'Fehler beim Laden der Rechnungen',
  errorMarkPaid: 'Fehler beim Markieren als bezahlt',
  errorIncreaseDunning: 'Fehler beim Erhöhen der Mahnstufe',

  // Status Labels
  statusOpen: 'Offen',
  statusSent: 'Versendet',
  statusPaid: 'Bezahlt',
  statusOverdue: 'Überfällig',
  statusDunning: 'In Mahnung',
  statusCancelled: 'Storniert',
  statusPartial: 'Teilbezahlt',

  // Dunning Level Labels
  dunningLevel0: '-',
  dunningLevel1: 'Erinnerung',
  dunningLevel2: '1. Mahnung',
  dunningLevel3: '2. Mahnung',
  dunningLevel4: 'Letzte Mahnung',

  // Table Headers
  tableInvoiceNumber: 'Rechnungsnr.',
  tablePartner: 'Geschäftspartner',
  tableAmount: 'Betrag',
  tableDueDate: 'Fällig am',
  tableStatus: 'Status',
  tableDunningLevel: 'Mahnstufe',
  tableDaysOverdue: 'Tage überfällig',
  tableActions: 'Aktionen',

  // Filter Labels
  filterStatus: 'Status',
  filterDunningLevel: 'Mahnstufe',
  filterPartner: 'Geschäftspartner',
  filterDateRange: 'Zeitraum',
  filterOverdueOnly: 'Nur überfällige',
  filterReset: 'Filter zurücksetzen',

  // Skonto Labels (NEU)
  skontoTitle: 'Skonto',
  skontoPercentage: 'Skonto-Prozent',
  skontoDays: 'Skonto-Tage',
  skontoDeadline: 'Skonto-Frist',
  skontoAmount: 'Skonto-Betrag',
  skontoSavings: 'Ersparnis',
  skontoExpiring: 'Skonto läuft ab',
  skontoExpired: 'Skonto abgelaufen',
  skontoAvailable: 'Skonto verfügbar',
  skontoUsed: 'Skonto genutzt',
  skontoNotConfigured: 'Kein Skonto',
  skontoApply: 'Skonto anwenden',
  skontoEdit: 'Skonto bearbeiten',
  skontoUpcoming: 'Bevorstehende Skonto-Fristen',
  actionApplySkonto: 'Mit Skonto bezahlen',

  // Teilzahlung Labels (NEU)
  partialPaymentTitle: 'Teilzahlungen',
  partialPaymentAdd: 'Zahlung erfassen',
  partialPaymentHistory: 'Zahlungsverlauf',
  partialPaymentAmount: 'Zahlungsbetrag',
  partialPaymentDate: 'Zahlungsdatum',
  partialPaymentMethod: 'Zahlungsart',
  partialPaymentReference: 'Referenz',
  partialPaymentOutstanding: 'Ausstehend',
  partialPaymentTotal: 'Gesamt bezahlt',
  partialPaymentDelete: 'Zahlung löschen',
  partialPaymentReconciled: 'Abgeglichen',
  partialPaymentPending: 'Offen',
  partialPaymentUnmatched: 'Nicht zugeordnet',

  // Toasts (NEU)
  successApplySkonto: 'Skonto angewendet',
  successUpdateSkonto: 'Skonto aktualisiert',
  successAddPayment: 'Zahlung erfasst',
  successDeletePayment: 'Zahlung gelöscht',
  errorApplySkonto: 'Fehler beim Anwenden des Skontos',
  errorUpdateSkonto: 'Fehler beim Aktualisieren des Skontos',
  errorAddPayment: 'Fehler beim Erfassen der Zahlung',
  errorDeletePayment: 'Fehler beim Löschen der Zahlung',
  errorLoadPayments: 'Fehler beim Laden der Zahlungen',
} as const;

/**
 * Status Badge Styles
 */
export const STATUS_STYLES: Record<InvoiceStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  open: { label: UI_LABELS.statusOpen, variant: 'secondary' },
  sent: { label: UI_LABELS.statusSent, variant: 'outline' },
  paid: { label: UI_LABELS.statusPaid, variant: 'default' },
  overdue: { label: UI_LABELS.statusOverdue, variant: 'destructive' },
  dunning: { label: UI_LABELS.statusDunning, variant: 'destructive' },
  cancelled: { label: UI_LABELS.statusCancelled, variant: 'outline' },
  partial: { label: UI_LABELS.statusPartial, variant: 'secondary' },
};

/**
 * Dunning Level Badge Styles
 */
export const DUNNING_LEVEL_STYLES: Record<DunningLevel, { label: string; className: string }> = {
  0: { label: UI_LABELS.dunningLevel0, className: 'bg-gray-100 text-gray-600 border-gray-200' },
  1: { label: UI_LABELS.dunningLevel1, className: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  2: { label: UI_LABELS.dunningLevel2, className: 'bg-orange-50 text-orange-700 border-orange-200' },
  3: { label: UI_LABELS.dunningLevel3, className: 'bg-red-50 text-red-700 border-red-200' },
  4: { label: UI_LABELS.dunningLevel4, className: 'bg-red-100 text-red-900 border-red-300' },
};
