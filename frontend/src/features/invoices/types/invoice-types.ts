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
