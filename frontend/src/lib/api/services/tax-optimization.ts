/**
 * Tax Optimization API Service
 *
 * Enterprise-Level Steueroptimierung fuer das Privat-Modul:
 * - Steuerabzuege nach Kategorien (Werbungskosten, Sonderausgaben, etc.)
 * - Steuerliche Fristen und Deadlines
 * - Absetzbarkeitspruefung fuer Dokumente
 * - DATEV-Export
 * - Jahresvergleich
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';

// ==================== Error Class ====================

export class TaxOptimizationApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'TaxOptimizationApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new TaxOptimizationApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new TaxOptimizationApiError(`${context}: ${message}`, 400, error);
    }

    throw new TaxOptimizationApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new TaxOptimizationApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Types ====================

/** Steuer-Kategorien mit Paragraph-Referenz */
export type TaxCategory =
  | 'werbungskosten'
  | 'sonderausgaben'
  | 'aussergewoehnliche_belastungen'
  | 'haushaltsnahe_dienstleistungen'
  | 'handwerkerleistungen'
  | 'doppelte_haushaltsfuehrung'
  | 'homeoffice'
  | 'kinderbetreuung'
  | 'spenden'
  | 'kirchensteuer';

/** Steuer-Fristen-Typen */
export type TaxDeadlineType =
  | 'einkommensteuer'
  | 'gewerbesteuer'
  | 'umsatzsteuer_voranmeldung'
  | 'umsatzsteuer_erklaerung'
  | 'grundsteuer'
  | 'koerperschaftsteuer'
  | 'lohnsteuer'
  | 'fristverlaengerung';

/** Optimierungs-Bewertung */
export type TaxRating = 'optimal' | 'gut' | 'verbesserbar' | 'optimierungsbedarf';

/** Einzelner absetzbarer Posten */
export interface TaxDeductionItem {
  category: TaxCategory;
  description: string;
  grossAmount: number;
  deductibleAmount: number;
  documentId?: string;
  documentDate?: string;
  confidence: number;
  isVerified: boolean;
  notes?: string;
}

/** Zusammenfassung einer Kategorie */
export interface TaxDeductionSummary {
  category: TaxCategory;
  categoryName: string;
  totalGross: number;
  totalDeductible: number;
  maxDeductible?: number;
  utilizationPercent?: number;
  items: TaxDeductionItem[];
  recommendations: string[];
}

/** Steuerliche Frist */
export interface TaxDeadline {
  deadlineType: TaxDeadlineType;
  title: string;
  dueDate: string;
  description: string;
  isRecurring: boolean;
  recurrencePattern?: 'monthly' | 'quarterly' | 'yearly';
  daysUntilDue: number;
  isOverdue: boolean;
  reminderSent: boolean;
}

/** Vollstaendiges Steueroptimierungs-Ergebnis */
export interface TaxOptimizationResult {
  spaceId: string;
  taxYear: number;
  totalDeductible: number;
  estimatedTaxSavings: number;
  optimizationRating: TaxRating;
  deductionSummaries: TaxDeductionSummary[];
  upcomingDeadlines: TaxDeadline[];
  overdueDeadlines: TaxDeadline[];
  optimizationSuggestions: string[];
  missingDeductions: string[];
  datevExportReady: boolean;
  datevExportNotes?: string;
  calculatedAt: string;
}

/** Absetzbarkeitspruefung Ergebnis */
export interface DeductibilityCheckResult {
  isDeductible: boolean;
  confidence: number;
  category?: TaxCategory;
  categoryName?: string;
  matchedKeywords?: string[];
  amount?: string;
  deductibleAmount?: string;
  maxDeductible?: string;
  deductionRules?: string[];
  recommendations: string[];
  reason?: string;
}

/** DATEV Export Daten */
export interface DATEVExportData {
  formatVersion: string;
  taxYear: number;
  exportDate: string;
  totalDeductible: string;
  categories: Array<{
    category: TaxCategory;
    categoryName: string;
    totalGross: string;
    totalDeductible: string;
    itemCount: number;
    suggestedAccounts: Array<{
      konto: string;
      bezeichnung: string;
    }>;
  }>;
}

/** Jahresvergleich */
export interface TaxYearComparison {
  currentYear: number;
  previousYear: number;
  currentYearTotal: number;
  previousYearTotal: number;
  difference: number;
  differencePercent: number;
  categoryComparison: Array<{
    category: TaxCategory;
    categoryName: string;
    currentYearAmount: number;
    previousYearAmount: number;
    difference: number;
  }>;
}

// ==================== Backend Types ====================

interface TaxDeductionItemBackend {
  category: TaxCategory;
  description: string;
  gross_amount: number;
  deductible_amount: number;
  document_id?: string;
  document_date?: string;
  confidence: number;
  is_verified: boolean;
  notes?: string;
}

interface TaxDeductionSummaryBackend {
  category: TaxCategory;
  category_name: string;
  total_gross: number;
  total_deductible: number;
  max_deductible?: number;
  utilization_percent?: number;
  items: TaxDeductionItemBackend[];
  recommendations: string[];
}

interface TaxDeadlineBackend {
  deadline_type: TaxDeadlineType;
  title: string;
  due_date: string;
  description: string;
  is_recurring: boolean;
  recurrence_pattern?: 'monthly' | 'quarterly' | 'yearly';
  days_until_due: number;
  is_overdue: boolean;
  reminder_sent: boolean;
}

interface TaxOptimizationResultBackend {
  space_id: string;
  tax_year: number;
  total_deductible: number;
  estimated_tax_savings: number;
  optimization_rating: TaxRating;
  deduction_summaries: TaxDeductionSummaryBackend[];
  upcoming_deadlines: TaxDeadlineBackend[];
  overdue_deadlines: TaxDeadlineBackend[];
  optimization_suggestions: string[];
  missing_deductions: string[];
  datev_export_ready: boolean;
  datev_export_notes?: string;
  calculated_at: string;
}

interface DeductibilityCheckResultBackend {
  is_deductible: boolean;
  confidence: number;
  category?: TaxCategory;
  category_name?: string;
  matched_keywords?: string[];
  amount?: string;
  deductible_amount?: string;
  max_deductible?: string;
  deduction_rules?: string[];
  recommendations: string[];
  reason?: string;
}

interface DATEVExportDataBackend {
  format_version: string;
  tax_year: number;
  export_date: string;
  total_deductible: string;
  categories: Array<{
    category: TaxCategory;
    category_name: string;
    total_gross: string;
    total_deductible: string;
    item_count: number;
    suggested_accounts: Array<{
      konto: string;
      bezeichnung: string;
    }>;
  }>;
}

interface TaxYearComparisonBackend {
  current_year: number;
  previous_year: number;
  current_year_total: number;
  previous_year_total: number;
  difference: number;
  difference_percent: number;
  category_comparison: Array<{
    category: TaxCategory;
    category_name: string;
    current_year_amount: number;
    previous_year_amount: number;
    difference: number;
  }>;
}

// ==================== Transformers ====================

function transformDeductionItem(item: TaxDeductionItemBackend): TaxDeductionItem {
  return {
    category: item.category,
    description: item.description,
    grossAmount: item.gross_amount,
    deductibleAmount: item.deductible_amount,
    documentId: item.document_id,
    documentDate: item.document_date,
    confidence: item.confidence,
    isVerified: item.is_verified,
    notes: item.notes,
  };
}

function transformDeductionSummary(summary: TaxDeductionSummaryBackend): TaxDeductionSummary {
  return {
    category: summary.category,
    categoryName: summary.category_name,
    totalGross: summary.total_gross,
    totalDeductible: summary.total_deductible,
    maxDeductible: summary.max_deductible,
    utilizationPercent: summary.utilization_percent,
    items: summary.items.map(transformDeductionItem),
    recommendations: summary.recommendations,
  };
}

function transformDeadline(deadline: TaxDeadlineBackend): TaxDeadline {
  return {
    deadlineType: deadline.deadline_type,
    title: deadline.title,
    dueDate: deadline.due_date,
    description: deadline.description,
    isRecurring: deadline.is_recurring,
    recurrencePattern: deadline.recurrence_pattern,
    daysUntilDue: deadline.days_until_due,
    isOverdue: deadline.is_overdue,
    reminderSent: deadline.reminder_sent,
  };
}

function transformTaxOptimizationResult(data: TaxOptimizationResultBackend): TaxOptimizationResult {
  return {
    spaceId: data.space_id,
    taxYear: data.tax_year,
    totalDeductible: data.total_deductible,
    estimatedTaxSavings: data.estimated_tax_savings,
    optimizationRating: data.optimization_rating,
    deductionSummaries: data.deduction_summaries.map(transformDeductionSummary),
    upcomingDeadlines: data.upcoming_deadlines.map(transformDeadline),
    overdueDeadlines: data.overdue_deadlines.map(transformDeadline),
    optimizationSuggestions: data.optimization_suggestions,
    missingDeductions: data.missing_deductions,
    datevExportReady: data.datev_export_ready,
    datevExportNotes: data.datev_export_notes,
    calculatedAt: data.calculated_at,
  };
}

function transformDeductibilityCheck(data: DeductibilityCheckResultBackend): DeductibilityCheckResult {
  return {
    isDeductible: data.is_deductible,
    confidence: data.confidence,
    category: data.category,
    categoryName: data.category_name,
    matchedKeywords: data.matched_keywords,
    amount: data.amount,
    deductibleAmount: data.deductible_amount,
    maxDeductible: data.max_deductible,
    deductionRules: data.deduction_rules,
    recommendations: data.recommendations,
    reason: data.reason,
  };
}

function transformDATEVExport(data: DATEVExportDataBackend): DATEVExportData {
  return {
    formatVersion: data.format_version,
    taxYear: data.tax_year,
    exportDate: data.export_date,
    totalDeductible: data.total_deductible,
    categories: data.categories.map((cat) => ({
      category: cat.category,
      categoryName: cat.category_name,
      totalGross: cat.total_gross,
      totalDeductible: cat.total_deductible,
      itemCount: cat.item_count,
      suggestedAccounts: cat.suggested_accounts,
    })),
  };
}

function transformYearComparison(data: TaxYearComparisonBackend): TaxYearComparison {
  return {
    currentYear: data.current_year,
    previousYear: data.previous_year,
    currentYearTotal: data.current_year_total,
    previousYearTotal: data.previous_year_total,
    difference: data.difference,
    differencePercent: data.difference_percent,
    categoryComparison: data.category_comparison.map((cat) => ({
      category: cat.category,
      categoryName: cat.category_name,
      currentYearAmount: cat.current_year_amount,
      previousYearAmount: cat.previous_year_amount,
      difference: cat.difference,
    })),
  };
}

// ==================== API Service ====================

export const taxOptimizationService = {
  /**
   * Analysiert Steueroptimierungsmoeglichkeiten fuer einen Space
   */
  analyzeTaxOptimization: async (
    spaceId: string,
    options?: {
      taxYear?: number;
      estimatedGrossIncome?: number;
      isMarried?: boolean;
    }
  ): Promise<TaxOptimizationResult> => {
    try {
      const params = new URLSearchParams();
      if (options?.taxYear) params.append('tax_year', String(options.taxYear));
      if (options?.estimatedGrossIncome) params.append('estimated_gross_income', String(options.estimatedGrossIncome));
      if (options?.isMarried !== undefined) params.append('is_married', String(options.isMarried));

      const url = `/privat/analytics/spaces/${spaceId}/tax-optimization${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const response = await apiClient.get<TaxOptimizationResultBackend>(url);
      return transformTaxOptimizationResult(response.data);
    } catch (error) {
      handleApiError(error, 'Steueroptimierung analysieren');
    }
  },

  /**
   * Holt Steuerabzuege nach Kategorie
   */
  getDeductionsByCategory: async (
    spaceId: string,
    category: TaxCategory,
    taxYear?: number
  ): Promise<TaxDeductionSummary> => {
    try {
      const params = new URLSearchParams();
      if (taxYear) params.append('tax_year', String(taxYear));

      const url = `/privat/analytics/spaces/${spaceId}/tax-deductions/${category}${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const response = await apiClient.get<TaxDeductionSummaryBackend>(url);
      return transformDeductionSummary(response.data);
    } catch (error) {
      handleApiError(error, 'Steuerabzuege laden');
    }
  },

  /**
   * Holt alle Steuerfristen
   */
  getTaxDeadlines: async (
    spaceId: string,
    taxYear?: number
  ): Promise<{ upcoming: TaxDeadline[]; overdue: TaxDeadline[] }> => {
    try {
      const params = new URLSearchParams();
      if (taxYear) params.append('tax_year', String(taxYear));

      const url = `/privat/analytics/spaces/${spaceId}/tax-deadlines${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const response = await apiClient.get<{
        upcoming: TaxDeadlineBackend[];
        overdue: TaxDeadlineBackend[];
      }>(url);
      return {
        upcoming: response.data.upcoming.map(transformDeadline),
        overdue: response.data.overdue.map(transformDeadline),
      };
    } catch (error) {
      handleApiError(error, 'Steuerfristen laden');
    }
  },

  /**
   * Prueft ob ein Dokument steuerlich absetzbar ist
   */
  checkDeductibility: async (
    documentId: string,
    options?: {
      documentText?: string;
      documentType?: string;
      amount?: number;
    }
  ): Promise<DeductibilityCheckResult> => {
    try {
      const response = await apiClient.post<DeductibilityCheckResultBackend>(
        `/privat/analytics/documents/${documentId}/check-deductibility`,
        {
          document_text: options?.documentText,
          document_type: options?.documentType,
          amount: options?.amount,
        }
      );
      return transformDeductibilityCheck(response.data);
    } catch (error) {
      handleApiError(error, 'Absetzbarkeit pruefen');
    }
  },

  /**
   * Generiert DATEV-Export
   */
  generateDATEVExport: async (spaceId: string, taxYear: number): Promise<DATEVExportData> => {
    try {
      const response = await apiClient.post<DATEVExportDataBackend>(
        `/privat/analytics/spaces/${spaceId}/tax-optimization/datev-export`,
        { tax_year: taxYear }
      );
      return transformDATEVExport(response.data);
    } catch (error) {
      handleApiError(error, 'DATEV-Export generieren');
    }
  },

  /**
   * Ladet DATEV-Export als Datei herunter
   */
  downloadDATEVExport: async (spaceId: string, taxYear: number): Promise<Blob> => {
    try {
      const response = await apiClient.get(
        `/privat/analytics/spaces/${spaceId}/tax-optimization/datev-export/download?tax_year=${taxYear}`,
        { responseType: 'blob' }
      );
      return response.data;
    } catch (error) {
      handleApiError(error, 'DATEV-Export herunterladen');
    }
  },

  /**
   * Holt Jahresvergleich
   */
  getYearComparison: async (spaceId: string, currentYear?: number): Promise<TaxYearComparison> => {
    try {
      const params = new URLSearchParams();
      if (currentYear) params.append('current_year', String(currentYear));

      const url = `/privat/analytics/spaces/${spaceId}/tax-optimization/year-comparison${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const response = await apiClient.get<TaxYearComparisonBackend>(url);
      return transformYearComparison(response.data);
    } catch (error) {
      handleApiError(error, 'Jahresvergleich laden');
    }
  },

  /**
   * Holt Steueroptimierungs-Tipps
   */
  getOptimizationTips: async (spaceId: string, taxYear?: number): Promise<string[]> => {
    try {
      const params = new URLSearchParams();
      if (taxYear) params.append('tax_year', String(taxYear));

      const url = `/privat/analytics/spaces/${spaceId}/tax-optimization/tips${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const response = await apiClient.get<{ tips: string[] }>(url);
      return response.data.tips;
    } catch (error) {
      handleApiError(error, 'Optimierungstipps laden');
    }
  },
};

export default taxOptimizationService;
