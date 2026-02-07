/**
 * Executive Dashboard Types
 *
 * TypeScript interfaces matching backend Pydantic schemas.
 */

/**
 * Key Performance Indicators
 */
export interface KPIResponse {
  documents_this_month: number
  documents_last_month: number
  documents_trend_percent: number
  avg_processing_time_ms: number
  processing_time_trend_percent: number
  ocr_accuracy: number
  ocr_accuracy_trend: number
  cost_per_document: number
  active_users_count: number
  pending_reviews: number
}

/**
 * Department/Area Statistics
 */
export interface DepartmentBreakdown {
  department: string
  document_count: number
  avg_processing_time_ms: number
  accuracy: number
  pending_count: number
}

/**
 * Single data point in a time series
 */
export interface TrendDataPoint {
  date: string // ISO format YYYY-MM-DD
  value: number
}

/**
 * Trend data for a metric
 */
export interface TrendResponse {
  metric: string
  data: TrendDataPoint[]
  period_days: number
}

/**
 * Complete executive summary
 */
export interface ExecutiveSummaryResponse {
  kpis: KPIResponse
  departments: DepartmentBreakdown[]
  document_trend: TrendResponse
  processing_trend: TrendResponse
  generated_at: string // ISO timestamp
}

/**
 * Supported metrics for trend queries
 */
export type TrendMetric = 'documents' | 'processing_time' | 'accuracy'
