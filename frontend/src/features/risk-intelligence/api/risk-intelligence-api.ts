/**
 * Risk Intelligence API Client
 *
 * Erweiterte Risikoanalyse mit Branchen-Benchmarks, Trends und Netzwerk-Analyse.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface TrendAnalysis {
  direction: 'improving' | 'stable' | 'deteriorating' | 'critical';
  change_percentage: number;
  quarters: Array<{
    quarter: string;
    avg_payment_delay: number;
    invoice_count: number;
    default_rate: number;
  }>;
  trend_score: number;
}

export interface BenchmarkComparison {
  industry: string;
  benchmark: {
    avg_payment_delay: number;
    default_rate: number;
    industry_risk_factor: number;
  };
  actual_payment_delay: number;
  actual_default_rate: number;
  delay_deviation: number;
  default_deviation: number;
  performance: 'excellent' | 'good' | 'average' | 'below_average' | 'poor';
  benchmark_score: number;
}

export interface NetworkConnection {
  entity_id: string;
  entity_name: string;
  connection_type: 'shared_iban' | 'shared_address';
  risk_indicator: 'high' | 'medium' | 'low';
  details: string;
}

export interface NetworkAnalysis {
  connections: NetworkConnection[];
  connection_count: number;
  network_risk_score: number;
  has_suspicious_connections: boolean;
}

export interface Recommendation {
  priority: 'high' | 'medium' | 'low';
  category: string;
  title: string;
  description: string;
  action: string;
}

export interface RiskProfile {
  entity_id: string;
  entity_name: string;
  entity_type: 'customer' | 'supplier';
  industry: string;
  overall_risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  analysis: {
    internal: {
      base_score: number;
      payment_delay_avg: number;
      default_rate: number;
      total_invoices: number;
      overdue_invoices: number;
    };
    trend: TrendAnalysis;
    benchmark: BenchmarkComparison;
    network: NetworkAnalysis;
  };
  recommendations: Recommendation[];
  analyzed_at: string;
}

export interface PortfolioRiskOverview {
  total_entities: number;
  risk_distribution: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
  high_risk_entities: Array<{
    entity_id: string;
    entity_name: string;
    risk_score: number;
    risk_level: string;
    primary_concern: string;
  }>;
  total_exposure: number;
  portfolio_risk_score: number;
  analyzed_at: string;
}

export interface ExternalSourceCheck {
  entity_id: string;
  entity_name: string;
  sources_checked: Array<{
    source: string;
    name: string;
    status: 'checked' | 'not_configured' | 'error';
    last_checked?: string;
  }>;
  alerts: Array<{
    source: string;
    severity: 'critical' | 'warning' | 'info';
    message: string;
    details?: string;
  }>;
  last_checked: string;
}

export interface IndustryBenchmark {
  industry: string;
  avg_payment_delay: number;
  default_rate: number;
  industry_risk_factor: number;
}

export interface TrendDirection {
  direction: string;
  name: string;
  description: string;
  color: string;
}

export interface ExternalSource {
  source: string;
  name: string;
  description: string;
  status: 'available' | 'not_configured' | 'error';
}

// ==================== API Functions ====================

/**
 * Liefert umfassendes Risikoprofil fuer eine Entity
 */
export async function getEntityRiskProfile(entityId: string): Promise<RiskProfile> {
  const response = await apiClient.get<RiskProfile>(
    `/risk-intelligence/entity/${entityId}/profile`
  );
  return response.data;
}

/**
 * Liefert Trend-Analyse fuer eine Entity
 */
export async function getEntityTrend(
  entityId: string,
  quarters: number = 4
): Promise<{ entity_id: string; trend: TrendAnalysis }> {
  const response = await apiClient.get<{ entity_id: string; trend: TrendAnalysis }>(
    `/risk-intelligence/entity/${entityId}/trend`,
    { params: { quarters } }
  );
  return response.data;
}

/**
 * Liefert Benchmark-Vergleich fuer eine Entity
 */
export async function getEntityBenchmark(
  entityId: string,
  industry?: string
): Promise<{ entity_id: string; benchmark_comparison: BenchmarkComparison }> {
  const response = await apiClient.get<{ entity_id: string; benchmark_comparison: BenchmarkComparison }>(
    `/risk-intelligence/entity/${entityId}/benchmark`,
    { params: industry ? { industry } : undefined }
  );
  return response.data;
}

/**
 * Liefert Netzwerk-Analyse fuer eine Entity
 */
export async function getEntityNetwork(
  entityId: string
): Promise<{ entity_id: string; network: NetworkAnalysis }> {
  const response = await apiClient.get<{ entity_id: string; network: NetworkAnalysis }>(
    `/risk-intelligence/entity/${entityId}/network`
  );
  return response.data;
}

/**
 * Prueft externe Datenquellen fuer eine Entity
 */
export async function checkExternalSources(entityId: string): Promise<ExternalSourceCheck> {
  const response = await apiClient.get<ExternalSourceCheck>(
    `/risk-intelligence/entity/${entityId}/external`
  );
  return response.data;
}

/**
 * Liefert Portfolio-Risikouebersicht
 */
export async function getPortfolioRisk(
  entityType?: 'customer' | 'supplier'
): Promise<PortfolioRiskOverview> {
  const response = await apiClient.get<PortfolioRiskOverview>(
    '/risk-intelligence/portfolio',
    { params: entityType ? { entity_type: entityType } : undefined }
  );
  return response.data;
}

/**
 * Liefert verfuegbare Branchen-Benchmarks
 */
export async function getIndustryBenchmarks(): Promise<IndustryBenchmark[]> {
  const response = await apiClient.get<IndustryBenchmark[]>('/risk-intelligence/benchmarks');
  return response.data;
}

/**
 * Liefert alle moeglichen Trend-Richtungen
 */
export async function getTrendDirections(): Promise<TrendDirection[]> {
  const response = await apiClient.get<TrendDirection[]>('/risk-intelligence/trend-directions');
  return response.data;
}

/**
 * Liefert verfuegbare externe Datenquellen
 */
export async function getExternalSources(): Promise<ExternalSource[]> {
  const response = await apiClient.get<ExternalSource[]>('/risk-intelligence/external-sources');
  return response.data;
}
