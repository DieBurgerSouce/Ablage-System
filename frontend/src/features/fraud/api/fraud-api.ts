/**
 * Fraud Detection API Client
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface FraudAlert {
  type: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  description: string;
  amount?: number;
  confidence: number;
  detected_at: string;
  invoice_id?: string;
  entity_id?: string;
  entity_name?: string;
  related_invoice_id?: string;
  document_ids?: string[];
}

export interface FraudSummary {
  total_alerts: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  estimated_risk_amount: number;
}

export interface FraudAnalysis {
  company_id: string;
  analysis_period: {
    start: string;
    end: string;
  };
  summary: FraudSummary;
  alerts: FraudAlert[];
  analyzed_at: string;
}

export interface FraudDashboardStats {
  total_alerts_30d: number;
  critical_alerts: number;
  high_risk_amount: number;
  top_fraud_types: Array<{ type: string; count: number }>;
  trend: 'increasing' | 'stable' | 'decreasing';
}

export interface FraudConfig {
  price_deviation_threshold: number;
  duplicate_similarity_threshold: number;
  phantom_supplier_days: number;
  expense_pattern_threshold: number;
  approval_threshold: number;
}

export interface FraudType {
  type: string;
  name: string;
  description: string;
}

export interface RiskLevel {
  level: string;
  name: string;
  description: string;
  color: string;
}

export interface EntityRiskProfile {
  entity_id: string;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  total_alerts: number;
  alerts_by_type: Record<string, number>;
  recent_alerts: FraudAlert[];
  recommendation: string;
}

// ==================== API Functions ====================

export async function analyzeFraud(days: number = 90): Promise<FraudAnalysis> {
  const response = await apiClient.get<FraudAnalysis>(`/fraud/analyze?days=${days}`);
  return response.data;
}

export async function getFraudDashboard(): Promise<FraudDashboardStats> {
  const response = await apiClient.get<FraudDashboardStats>('/fraud/dashboard');
  return response.data;
}

export async function getFraudAlerts(params?: {
  fraud_type?: string;
  risk_level?: string;
  days?: number;
  limit?: number;
  offset?: number;
}): Promise<FraudAlert[]> {
  const searchParams = new URLSearchParams();
  if (params?.fraud_type) searchParams.append('fraud_type', params.fraud_type);
  if (params?.risk_level) searchParams.append('risk_level', params.risk_level);
  if (params?.days) searchParams.append('days', params.days.toString());
  if (params?.limit) searchParams.append('limit', params.limit.toString());
  if (params?.offset) searchParams.append('offset', params.offset.toString());

  const response = await apiClient.get<FraudAlert[]>(`/fraud/alerts?${searchParams}`);
  return response.data;
}

export async function getFraudConfig(): Promise<FraudConfig> {
  const response = await apiClient.get<FraudConfig>('/fraud/config');
  return response.data;
}

export async function updateFraudConfig(config: Partial<FraudConfig>): Promise<FraudConfig> {
  const response = await apiClient.patch<FraudConfig>('/fraud/config', config);
  return response.data;
}

export async function getFraudTypes(): Promise<FraudType[]> {
  const response = await apiClient.get<FraudType[]>('/fraud/types');
  return response.data;
}

export async function getRiskLevels(): Promise<RiskLevel[]> {
  const response = await apiClient.get<RiskLevel[]>('/fraud/risk-levels');
  return response.data;
}

export async function getEntityRiskProfile(entityId: string): Promise<EntityRiskProfile> {
  const response = await apiClient.get<EntityRiskProfile>(`/fraud/entity/${entityId}/risk-profile`);
  return response.data;
}
