/**
 * Digital Twin Types
 *
 * TypeScript Definitionen für das Digital Twin System (360-Grad Unternehmensansicht).
 */

// ============================================================================
// BACKEND RESPONSE TYPES (snake_case)
// ============================================================================

export interface FinancialHealthResponse {
  health_score: number;
  cashflow_current: number;
  receivables_total: number;
  payables_total: number;
  overdue_receivables: number;
  overdue_payables: number;
  liquidity_ratio: number;
}

export interface RiskEntityResponse {
  id: number;
  name: string;
  risk_score: number;
  category: string;
}

export interface RiskOverviewResponse {
  average_risk_score: number;
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  top_risks: RiskEntityResponse[];
}

export interface DocumentPipelineResponse {
  documents_today: number;
  documents_week: number;
  documents_month: number;
  pending_ocr: number;
  pending_review: number;
  pending_approval: number;
  auto_processing_rate: number;
}

export interface ComplianceResponse {
  gdpr_score: number;
  gobd_score: number;
  gdpr_violations: number;
  gobd_violations: number;
  upcoming_deadlines: number;
  overdue_actions: number;
}

export interface KeyMetricsResponse {
  total_documents: number;
  total_entities: number;
  total_invoices: number;
  ocr_accuracy: number;
  avg_processing_time: number;
}

export interface TrendPointResponse {
  date: string;
  value: number;
}

export interface TrendsResponse {
  revenue_trend: TrendPointResponse[];
  cost_trend: TrendPointResponse[];
  document_volume_trend: TrendPointResponse[];
}

export interface DigitalTwinResponse {
  financial_health: FinancialHealthResponse;
  risk_overview: RiskOverviewResponse;
  document_pipeline: DocumentPipelineResponse;
  compliance: ComplianceResponse;
  key_metrics: KeyMetricsResponse;
  trends: TrendsResponse;
  generated_at: string;
}

// ============================================================================
// FRONTEND TYPES (camelCase)
// ============================================================================

export interface FinancialHealth {
  healthScore: number;
  cashflowCurrent: number;
  receivablesTotal: number;
  payablesTotal: number;
  overdueReceivables: number;
  overduePayables: number;
  liquidityRatio: number;
}

export interface RiskEntity {
  id: number;
  name: string;
  riskScore: number;
  category: string;
}

export interface RiskOverview {
  averageRiskScore: number;
  highRiskCount: number;
  mediumRiskCount: number;
  lowRiskCount: number;
  topRisks: RiskEntity[];
}

export interface DocumentPipeline {
  documentsToday: number;
  documentsWeek: number;
  documentsMonth: number;
  pendingOcr: number;
  pendingReview: number;
  pendingApproval: number;
  autoProcessingRate: number;
}

export interface Compliance {
  gdprScore: number;
  gobdScore: number;
  gdprViolations: number;
  gobdViolations: number;
  upcomingDeadlines: number;
  overdueActions: number;
}

export interface KeyMetrics {
  totalDocuments: number;
  totalEntities: number;
  totalInvoices: number;
  ocrAccuracy: number;
  avgProcessingTime: number;
}

export interface TrendPoint {
  date: Date;
  value: number;
}

export interface Trends {
  revenueTrend: TrendPoint[];
  costTrend: TrendPoint[];
  documentVolumeTrend: TrendPoint[];
}

export interface DigitalTwin {
  financialHealth: FinancialHealth;
  riskOverview: RiskOverview;
  documentPipeline: DocumentPipeline;
  compliance: Compliance;
  keyMetrics: KeyMetrics;
  trends: Trends;
  generatedAt: Date;
}

// ============================================================================
// TRANSFORMER FUNCTIONS
// ============================================================================

export function transformFinancialHealth(
  response: FinancialHealthResponse
): FinancialHealth {
  return {
    healthScore: response.health_score,
    cashflowCurrent: response.cashflow_current,
    receivablesTotal: response.receivables_total,
    payablesTotal: response.payables_total,
    overdueReceivables: response.overdue_receivables,
    overduePayables: response.overdue_payables,
    liquidityRatio: response.liquidity_ratio,
  };
}

export function transformRiskEntity(response: RiskEntityResponse): RiskEntity {
  return {
    id: response.id,
    name: response.name,
    riskScore: response.risk_score,
    category: response.category,
  };
}

export function transformRiskOverview(
  response: RiskOverviewResponse
): RiskOverview {
  return {
    averageRiskScore: response.average_risk_score,
    highRiskCount: response.high_risk_count,
    mediumRiskCount: response.medium_risk_count,
    lowRiskCount: response.low_risk_count,
    topRisks: response.top_risks.map(transformRiskEntity),
  };
}

export function transformDocumentPipeline(
  response: DocumentPipelineResponse
): DocumentPipeline {
  return {
    documentsToday: response.documents_today,
    documentsWeek: response.documents_week,
    documentsMonth: response.documents_month,
    pendingOcr: response.pending_ocr,
    pendingReview: response.pending_review,
    pendingApproval: response.pending_approval,
    autoProcessingRate: response.auto_processing_rate,
  };
}

export function transformCompliance(response: ComplianceResponse): Compliance {
  return {
    gdprScore: response.gdpr_score,
    gobdScore: response.gobd_score,
    gdprViolations: response.gdpr_violations,
    gobdViolations: response.gobd_violations,
    upcomingDeadlines: response.upcoming_deadlines,
    overdueActions: response.overdue_actions,
  };
}

export function transformKeyMetrics(response: KeyMetricsResponse): KeyMetrics {
  return {
    totalDocuments: response.total_documents,
    totalEntities: response.total_entities,
    totalInvoices: response.total_invoices,
    ocrAccuracy: response.ocr_accuracy,
    avgProcessingTime: response.avg_processing_time,
  };
}

export function transformTrendPoint(response: TrendPointResponse): TrendPoint {
  return {
    date: new Date(response.date),
    value: response.value,
  };
}

export function transformTrends(response: TrendsResponse): Trends {
  return {
    revenueTrend: response.revenue_trend.map(transformTrendPoint),
    costTrend: response.cost_trend.map(transformTrendPoint),
    documentVolumeTrend: response.document_volume_trend.map(transformTrendPoint),
  };
}

export function transformDigitalTwin(
  response: DigitalTwinResponse
): DigitalTwin {
  return {
    financialHealth: transformFinancialHealth(response.financial_health),
    riskOverview: transformRiskOverview(response.risk_overview),
    documentPipeline: transformDocumentPipeline(response.document_pipeline),
    compliance: transformCompliance(response.compliance),
    keyMetrics: transformKeyMetrics(response.key_metrics),
    trends: transformTrends(response.trends),
    generatedAt: new Date(response.generated_at),
  };
}

// ============================================================================
// UI CONSTANTS
// ============================================================================

export function getHealthScoreColor(score: number): {
  bg: string;
  text: string;
  border: string;
} {
  if (score > 70) {
    return {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-700 dark:text-green-400',
      border: 'border-green-500',
    };
  }
  if (score > 40) {
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

export function getRiskColor(score: number): {
  bg: string;
  text: string;
  border: string;
} {
  if (score < 30) {
    return {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-700 dark:text-green-400',
      border: 'border-green-500',
    };
  }
  if (score < 60) {
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
