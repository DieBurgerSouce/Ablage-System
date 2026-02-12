/**
 * Missed Skonto Types
 * TypeScript-Definitionen für verpasste Skonto-Möglichkeiten
 */

/**
 * Verpasste Skonto-Gelegenheit
 */
export interface MissedSkontoItem {
  invoiceId: string;
  invoiceNumber: string;
  documentId: string;
  entityId?: string;
  entityName: string;
  invoiceDate: string;
  amount: number;
  skontoPercentage: number;
  skontoAmount: number;
  skontoDeadline: string;
  daysMissedBy: number;
  paidAt?: string;
  paidAmount?: number;
}

/**
 * Skonto-Statistiken
 */
export interface SkontoStatistics {
  periodStart: string;
  periodEnd: string;
  totalInvoices: number;
  invoicesWithSkonto: number;
  skontoUsedCount: number;
  skontoMissedCount: number;
  skontoPendingCount: number;
  totalSavings: number;
  missedSavings: number;
  potentialSavings: number;
  usageRate: number;
}

/**
 * Zeitraum für Statistik-Abfrage
 */
export type StatsPeriod = 'month' | 'quarter' | 'year' | 'custom';

/**
 * API Response für Missed Skonto Liste
 */
export interface MissedSkontoResponse {
  items: MissedSkontoItem[];
  total: number;
  totalMissedAmount: number;
}

/**
 * Filter-Parameter
 */
export interface MissedSkontoFilters {
  startDate?: string;
  endDate?: string;
  entityId?: string;
  minAmount?: number;
  page?: number;
  perPage?: number;
}

/**
 * Monatliche Zusammenfassung
 */
export interface MonthlySkontoSummary {
  month: string;
  year: number;
  usedCount: number;
  missedCount: number;
  usedAmount: number;
  missedAmount: number;
  usageRate: number;
}
