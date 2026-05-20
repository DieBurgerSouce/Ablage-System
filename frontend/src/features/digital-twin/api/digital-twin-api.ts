/**
 * Digital Twin API Client - 360° Business Snapshot
 *
 * API-Funktionen für die Digital Twin Dashboard-Ansicht.
 * Liefert einen umfassenden Überblick über:
 * - Finanzielle Gesundheit
 * - Risiko-Übersicht
 * - Dokument-Pipeline
 * - Compliance-Status
 * - Wichtige Metriken
 * - Trends
 *
 * Backend-Endpunkte:
 * - GET /api/v1/digital-twin - Vollständiger Snapshot
 * - GET /api/v1/digital-twin/{section} - Spezifische Sektion
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface FinancialHealth {
  score: number;
  cashflow: {
    current_month: number;
    trend: 'up' | 'down' | 'stable';
    percentage_change: number;
  };
  receivables: {
    total: number;
    overdue: number;
    overdue_percentage: number;
  };
  payables: {
    total: number;
    overdue: number;
    overdue_percentage: number;
  };
  liquidity_ratio: number;
}

export interface RiskEntity {
  entity_id: string;
  entity_name: string;
  entity_type: 'customer' | 'supplier' | 'other';
  risk_score: number;
  risk_category: string;
  issues: string[];
}

export interface RiskOverview {
  average_risk_score: number;
  high_risk_count: number;
  total_entities: number;
  top_risks: RiskEntity[];
  risk_distribution: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
}

export interface DocumentPipeline {
  documents_today: number;
  documents_week: number;
  documents_month: number;
  pending_ocr: number;
  pending_review: number;
  pending_approval: number;
  processing_time_avg_seconds: number;
}

export interface ComplianceStatus {
  compliance_score: number;
  gdpr_compliant: boolean;
  gobd_compliant: boolean;
  issues: string[];
  last_audit_date: string | null;
  next_audit_date: string | null;
}

export interface KeyMetrics {
  total_documents: number;
  total_entities: number;
  avg_processing_time: number;
  success_rate: number;
  storage_used_gb: number;
  active_users: number;
}

export interface TrendIndicator {
  metric: string;
  current_value: number;
  previous_value: number;
  change_percentage: number;
  trend: 'up' | 'down' | 'stable';
  period: string;
}

export interface Trends {
  indicators: TrendIndicator[];
}

export interface DigitalTwinSnapshot {
  financial_health: FinancialHealth;
  risk_overview: RiskOverview;
  document_pipeline: DocumentPipeline;
  compliance_status: ComplianceStatus;
  key_metrics: KeyMetrics;
  trends: Trends;
  generated_at: string;
}

// ==================== Query Keys ====================

export const digitalTwinKeys = {
  all: ['digital-twin'] as const,
  snapshot: () => [...digitalTwinKeys.all, 'snapshot'] as const,
  section: (section: string) => [...digitalTwinKeys.all, 'section', section] as const,
};

// ==================== API Functions ====================

/**
 * Holt den vollständigen Digital Twin Snapshot
 */
export async function getDigitalTwinSnapshot(): Promise<DigitalTwinSnapshot> {
  const response = await apiClient.get<DigitalTwinSnapshot>('/digital-twin');
  return response.data;
}

/**
 * Holt eine spezifische Sektion des Digital Twin
 */
export async function getDigitalTwinSection<T = unknown>(section: string): Promise<T> {
  const response = await apiClient.get<T>(`/digital-twin/${section}`);
  return response.data;
}
