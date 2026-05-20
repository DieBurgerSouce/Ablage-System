/**
 * Data Quality Types
 *
 * TypeScript Definitionen für das Data Quality Cockpit.
 */

// ============================================================================
// BACKEND RESPONSE TYPES (snake_case)
// ============================================================================

export type QualityCategory =
  | 'missing_category'
  | 'missing_amount'
  | 'missing_date'
  | 'missing_entity'
  | 'duplicate_detection'
  | 'invalid_format'
  | 'ocr_low_confidence'
  | 'missing_metadata';

export type QualitySeverity = 'low' | 'medium' | 'high' | 'critical';

export interface QualityIssueResponse {
  category: QualityCategory;
  severity: QualitySeverity;
  count: number;
  affected_documents: number[];
  description: string;
  fix_available: boolean;
}

export interface QualityReportResponse {
  overall_score: number;
  total_documents: number;
  issues: QualityIssueResponse[];
  calculated_at: string;
}

export interface QualityTrendPointResponse {
  date: string;
  score: number;
}

export interface QualityTrendResponse {
  trend: QualityTrendPointResponse[];
}

export interface FixResultResponse {
  success: boolean;
  fixed_count: number;
  error_count: number;
  message: string;
}

// ============================================================================
// FRONTEND TYPES (camelCase)
// ============================================================================

export interface QualityIssue {
  category: QualityCategory;
  severity: QualitySeverity;
  count: number;
  affectedDocuments: number[];
  description: string;
  fixAvailable: boolean;
}

export interface QualityReport {
  overallScore: number;
  totalDocuments: number;
  issues: QualityIssue[];
  calculatedAt: Date;
}

export interface QualityTrendPoint {
  date: Date;
  score: number;
}

export interface QualityTrend {
  trend: QualityTrendPoint[];
}

export interface FixResult {
  success: boolean;
  fixedCount: number;
  errorCount: number;
  message: string;
}

// ============================================================================
// TRANSFORMER FUNCTIONS
// ============================================================================

export function transformQualityIssue(
  response: QualityIssueResponse
): QualityIssue {
  return {
    category: response.category,
    severity: response.severity,
    count: response.count,
    affectedDocuments: response.affected_documents,
    description: response.description,
    fixAvailable: response.fix_available,
  };
}

export function transformQualityReport(
  response: QualityReportResponse
): QualityReport {
  return {
    overallScore: response.overall_score,
    totalDocuments: response.total_documents,
    issues: response.issues.map(transformQualityIssue),
    calculatedAt: new Date(response.calculated_at),
  };
}

export function transformQualityTrendPoint(
  response: QualityTrendPointResponse
): QualityTrendPoint {
  return {
    date: new Date(response.date),
    score: response.score,
  };
}

export function transformQualityTrend(
  response: QualityTrendResponse
): QualityTrend {
  return {
    trend: response.trend.map(transformQualityTrendPoint),
  };
}

export function transformFixResult(response: FixResultResponse): FixResult {
  return {
    success: response.success,
    fixedCount: response.fixed_count,
    errorCount: response.error_count,
    message: response.message,
  };
}

// ============================================================================
// UI CONSTANTS
// ============================================================================

export const CATEGORY_LABELS: Record<QualityCategory, string> = {
  missing_category: 'Fehlende Kategorie',
  missing_amount: 'Fehlender Betrag',
  missing_date: 'Fehlendes Datum',
  missing_entity: 'Fehlende Entität',
  duplicate_detection: 'Mögliche Duplikate',
  invalid_format: 'Ungültiges Format',
  ocr_low_confidence: 'Niedrige OCR-Konfidenz',
  missing_metadata: 'Fehlende Metadaten',
};

export const CATEGORY_ICONS: Record<QualityCategory, string> = {
  missing_category: 'folder-x',
  missing_amount: 'euro',
  missing_date: 'calendar-x',
  missing_entity: 'users-x',
  duplicate_detection: 'copy',
  invalid_format: 'file-warning',
  ocr_low_confidence: 'eye-off',
  missing_metadata: 'info',
};

export const SEVERITY_COLORS: Record<
  QualitySeverity,
  { bg: string; text: string; border: string }
> = {
  low: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-700 dark:text-blue-400',
    border: 'border-blue-500',
  },
  medium: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-700 dark:text-yellow-400',
    border: 'border-yellow-500',
  },
  high: {
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-700 dark:text-orange-400',
    border: 'border-orange-500',
  },
  critical: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-500',
  },
};

export const SEVERITY_LABELS: Record<QualitySeverity, string> = {
  low: 'Niedrig',
  medium: 'Mittel',
  high: 'Hoch',
  critical: 'Kritisch',
};

export function getQualityScoreColor(score: number): {
  bg: string;
  text: string;
  border: string;
} {
  if (score >= 70) {
    return {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-700 dark:text-green-400',
      border: 'border-green-500',
    };
  }
  if (score >= 40) {
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

export function getQualityScoreLabel(score: number): string {
  if (score >= 90) return 'Exzellent';
  if (score >= 70) return 'Gut';
  if (score >= 50) return 'Befriedigend';
  if (score >= 30) return 'Ausreichend';
  return 'Mangelhaft';
}
