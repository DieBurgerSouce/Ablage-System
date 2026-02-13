/**
 * CEO Dashboard Types
 *
 * TypeScript Definitionen für das CEO Dashboard System.
 */

// ============================================================================
// BACKEND RESPONSE TYPES (snake_case)
// ============================================================================

export interface HealthDimensionResponse {
  score: number;
  label: string;
  weight: number;
  details: Record<string, number | string>;
}

export interface HealthScoreResponse {
  overall_score: number;
  label: string;
  dimensions: {
    financial: HealthDimensionResponse;
    operations: HealthDimensionResponse;
    risk: HealthDimensionResponse;
    compliance: HealthDimensionResponse;
  };
  calculated_at: string;
}

export interface DocumentStatsResponse {
  processed_today: number;
  processed_month: number;
  total_documents: number;
}

export interface InvoiceStatsResponse {
  open_count: number;
  open_total: number;
  overdue_count: number;
  overdue_total: number;
}

export interface AlertStatsResponse {
  active_count: number;
  critical_count: number;
}

export interface OverviewResponse {
  health_score: HealthScoreResponse;
  documents: DocumentStatsResponse;
  invoices: InvoiceStatsResponse;
  alerts: AlertStatsResponse;
  auto_process_rate: number;
  generated_at: string;
}

export interface TrendPointResponse {
  date: string;
  value: number;
}

export interface TrendDataResponse {
  documents_processed: TrendPointResponse[];
  invoice_volume: TrendPointResponse[];
  auto_process_rate: TrendPointResponse[];
  alert_count: TrendPointResponse[];
}

export type AnomalySeverity = 'info' | 'warning' | 'critical';

export interface AnomalyResponse {
  type: string;
  severity: AnomalySeverity;
  metric: string;
  message: string;
  detected_at: string;
  details?: Record<string, unknown>;
}

// ============================================================================
// FRONTEND TYPES (camelCase)
// ============================================================================

export interface HealthDimension {
  score: number;
  label: string;
  weight: number;
  details: Record<string, number | string>;
}

export interface HealthScore {
  overallScore: number;
  label: string;
  dimensions: {
    financial: HealthDimension;
    operations: HealthDimension;
    risk: HealthDimension;
    compliance: HealthDimension;
  };
  calculatedAt: Date;
}

export interface DocumentStats {
  processedToday: number;
  processedMonth: number;
  totalDocuments: number;
}

export interface InvoiceStats {
  openCount: number;
  openTotal: number;
  overdueCount: number;
  overdueTotal: number;
}

export interface AlertStats {
  activeCount: number;
  criticalCount: number;
}

export interface OverviewData {
  healthScore: HealthScore;
  documents: DocumentStats;
  invoices: InvoiceStats;
  alerts: AlertStats;
  autoProcessRate: number;
  generatedAt: Date;
}

export interface TrendPoint {
  date: Date;
  value: number;
}

export interface TrendData {
  documentsProcessed: TrendPoint[];
  invoiceVolume: TrendPoint[];
  autoProcessRate: TrendPoint[];
  alertCount: TrendPoint[];
}

export interface Anomaly {
  type: string;
  severity: AnomalySeverity;
  metric: string;
  message: string;
  detectedAt: Date;
  details?: Record<string, unknown>;
}

// ============================================================================
// TRANSFORMER FUNCTIONS
// ============================================================================

export function transformHealthDimension(
  response: HealthDimensionResponse
): HealthDimension {
  return {
    score: response.score,
    label: response.label,
    weight: response.weight,
    details: response.details,
  };
}

export function transformHealthScore(response: HealthScoreResponse): HealthScore {
  return {
    overallScore: response.overall_score,
    label: response.label,
    dimensions: {
      financial: transformHealthDimension(response.dimensions.financial),
      operations: transformHealthDimension(response.dimensions.operations),
      risk: transformHealthDimension(response.dimensions.risk),
      compliance: transformHealthDimension(response.dimensions.compliance),
    },
    calculatedAt: new Date(response.calculated_at),
  };
}

export function transformDocumentStats(response: DocumentStatsResponse): DocumentStats {
  return {
    processedToday: response.processed_today,
    processedMonth: response.processed_month,
    totalDocuments: response.total_documents,
  };
}

export function transformInvoiceStats(response: InvoiceStatsResponse): InvoiceStats {
  return {
    openCount: response.open_count,
    openTotal: response.open_total,
    overdueCount: response.overdue_count,
    overdueTotal: response.overdue_total,
  };
}

export function transformAlertStats(response: AlertStatsResponse): AlertStats {
  return {
    activeCount: response.active_count,
    criticalCount: response.critical_count,
  };
}

export function transformOverviewData(response: OverviewResponse): OverviewData {
  return {
    healthScore: transformHealthScore(response.health_score),
    documents: transformDocumentStats(response.documents),
    invoices: transformInvoiceStats(response.invoices),
    alerts: transformAlertStats(response.alerts),
    autoProcessRate: response.auto_process_rate,
    generatedAt: new Date(response.generated_at),
  };
}

export function transformTrendPoint(response: TrendPointResponse): TrendPoint {
  return {
    date: new Date(response.date),
    value: response.value,
  };
}

export function transformTrendData(response: TrendDataResponse): TrendData {
  return {
    documentsProcessed: response.documents_processed.map(transformTrendPoint),
    invoiceVolume: response.invoice_volume.map(transformTrendPoint),
    autoProcessRate: response.auto_process_rate.map(transformTrendPoint),
    alertCount: response.alert_count.map(transformTrendPoint),
  };
}

export function transformAnomaly(response: AnomalyResponse): Anomaly {
  return {
    type: response.type,
    severity: response.severity,
    metric: response.metric,
    message: response.message,
    detectedAt: new Date(response.detected_at),
    details: response.details,
  };
}

// ============================================================================
// UI CONSTANTS
// ============================================================================

export const SEVERITY_COLORS: Record<
  AnomalySeverity,
  { bg: string; text: string; border: string }
> = {
  info: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-700 dark:text-blue-400',
    border: 'border-blue-500',
  },
  warning: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-700 dark:text-yellow-400',
    border: 'border-yellow-500',
  },
  critical: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-500',
  },
};

export const SEVERITY_LABELS: Record<AnomalySeverity, string> = {
  info: 'Information',
  warning: 'Warnung',
  critical: 'Kritisch',
};

export function getHealthScoreColor(score: number): {
  bg: string;
  text: string;
  border: string;
} {
  if (score > 80) {
    return {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-700 dark:text-green-400',
      border: 'border-green-500',
    };
  }
  if (score > 60) {
    return {
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
      text: 'text-yellow-700 dark:text-yellow-400',
      border: 'border-yellow-500',
    };
  }
  return {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-500',
  };
}
