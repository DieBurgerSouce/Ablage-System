/**
 * Skonto UX Types
 *
 * TypeScript-Typen für das Skonto-Feature.
 * Konsistent mit Backend SkontoService und Invoice API.
 */

// ==================== Core Types ====================

/**
 * Skonto-Informationen für eine Rechnung
 */
export interface SkontoInfo {
  invoiceId: string;
  percentage: number | null;        // z.B. 2.0 für 2%
  amount: number | null;            // Berechneter Skonto-Betrag
  deadline: string | null;          // ISO Date der Frist
  amountWithSkonto: number | null;  // Betrag nach Skonto-Abzug
  daysRemaining: number | null;     // Verbleibende Tage (null wenn abgelaufen)
  isExpired: boolean;               // True wenn Frist abgelaufen
  used: boolean;                    // True wenn Skonto genutzt wurde
  savingsPotential: number | null;  // Potenzielle Ersparnis
  message?: string;                 // Optional: "Keine Skonto-Konditionen hinterlegt"
}

/**
 * Bevorstehende Skonto-Gelegenheit
 */
export interface SkontoOpportunity {
  invoiceId: string;
  invoiceNumber: string;
  entityName: string;
  skontoDeadline: string;           // ISO Date
  skontoAmount: number;             // Ersparnis in EUR
  daysRemaining: number;            // Verbleibende Tage
  urgency: 'critical' | 'warning' | 'info';  // critical: <1 Tag, warning: <3 Tage, info: >3 Tage
}

/**
 * Verpasste Skonto-Möglichkeit
 */
export interface MissedSkontoItem {
  invoiceId: string;
  invoiceNumber: string;
  documentId: string;
  entityId: string | null;
  entityName: string;
  invoiceDate: string | null;
  amount: number;
  skontoPercentage: number;
  skontoAmount: number;
  skontoDeadline: string | null;
  daysMissedBy: number;              // Wie viele Tage zu spät
  paidAt: string | null;
  paidAmount: number | null;
}

/**
 * Verpasste Skonto Response mit Pagination
 */
export interface MissedSkontoResponse {
  items: MissedSkontoItem[];
  total: number;
  page: number;
  perPage: number;
  totalMissedAmount: number;         // Summe verpasster Ersparnisse
}

/**
 * Skonto-Statistiken für einen Zeitraum
 */
export interface SkontoStatistics {
  periodStart: string;
  periodEnd: string;
  totalInvoices: number;
  invoicesWithSkonto: number;
  skontoUsedCount: number;
  skontoMissedCount: number;
  skontoPendingCount: number;
  totalSavings: number;              // Gesparte Beträge
  missedSavings: number;             // Verpasste Ersparnisse
  potentialSavings: number;          // Noch offene potenzielle Ersparnisse
  usageRate: number;                 // Nutzungsrate in Prozent
}

/**
 * Monatliche Skonto-Zusammenfassung
 */
export interface MonthlySkontoSummary {
  year: string;
  month: string;                     // "01" bis "12"
  usedAmount: number;
  missedAmount: number;
  usedCount: number;
  missedCount: number;
  usageRate: number;                 // Prozent
}

/**
 * Skonto anwenden Request
 */
export interface ApplySkontoRequest {
  paymentAmount: number;
  paymentDate?: string;              // ISO Date, optional (default: jetzt)
  forceApply?: boolean;              // True um Skonto nach Fristablauf anzuwenden
}

/**
 * Skonto setzen Request
 */
export interface SetSkontoRequest {
  skontoPercentage: number;          // 0-10%
  skontoDays?: number;               // Default: 10
  netDays?: number;                  // Default: 30
}

// ==================== Filter Types ====================

/**
 * Filter für verpasste Skonto-Rechnungen
 */
export interface MissedSkontoFilter {
  startDate?: string;                // ISO Date
  endDate?: string;                  // ISO Date
  page?: number;
  perPage?: number;
}

// ==================== UI Labels ====================

export const SKONTO_LABELS = {
  // Status
  active: 'Aktiv',
  expiringSoon: 'Läuft bald ab',
  expired: 'Abgelaufen',
  used: 'Genutzt',

  // Actions
  applySkonto: 'Skonto anwenden',
  setSkonto: 'Skonto setzen',
  viewDetails: 'Details ansehen',

  // Urgency
  critical: 'Kritisch',
  warning: 'Warnung',
  info: 'Info',

  // Messages
  noSkontoConditions: 'Keine Skonto-Konditionen hinterlegt',
  skontoExpired: 'Skonto-Frist abgelaufen',
  skontoAlreadyUsed: 'Skonto bereits genutzt',
  deadlineApproaching: 'Skonto-Frist läuft bald ab',
  savingsOpportunity: 'Spar-Möglichkeit',

  // Export
  exportExcel: 'Als Excel exportieren',
  exportCsv: 'Als CSV exportieren',
} as const;

// ==================== Color Coding ====================

export const SKONTO_COLORS = {
  active: {
    bg: 'bg-green-50',
    border: 'border-green-200',
    text: 'text-green-700',
    badge: 'bg-green-100 text-green-800',
  },
  expiring: {
    bg: 'bg-yellow-50',
    border: 'border-yellow-200',
    text: 'text-yellow-700',
    badge: 'bg-yellow-100 text-yellow-800',
  },
  expired: {
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-700',
    badge: 'bg-red-100 text-red-800',
  },
  used: {
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    text: 'text-blue-700',
    badge: 'bg-blue-100 text-blue-800',
  },
} as const;
