/**
 * Data Quality API Client - Data Quality Monitoring & Cleanup
 *
 * API-Funktionen für das Data Quality Dashboard.
 * Überwacht Datenqualität und bietet Cleanup-Aktionen.
 *
 * Backend-Endpunkte:
 * - GET /api/v1/data-quality - Qualitätsbericht
 * - GET /api/v1/data-quality/trend?months=6 - Historischer Trend
 * - POST /api/v1/data-quality/{category}/fix - Cleanup-Aktion ausführen
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface DataQualityIssue {
  category: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  description: string;
  count: number;
  action_label: string;
  action_endpoint: string;
}

export interface DataQualityReport {
  overall_score: number;
  issues: DataQualityIssue[];
  trend: 'improving' | 'stable' | 'degrading';
  last_check: string;
}

export interface TrendDataPoint {
  month: string;
  score: number;
}

export interface DataQualityTrend {
  trend_data: TrendDataPoint[];
  average_score: number;
  improvement_percentage: number;
}

export interface FixActionRequest {
  action: string;
}

export interface FixActionResponse {
  success: boolean;
  message: string;
  fixed_count?: number;
}

// ==================== Query Keys ====================

export const dataQualityKeys = {
  all: ['data-quality'] as const,
  report: () => [...dataQualityKeys.all, 'report'] as const,
  trend: (months: number) => [...dataQualityKeys.all, 'trend', months] as const,
};

// ==================== API Functions ====================

/**
 * Holt den aktuellen Datenqualitätsbericht
 */
export async function getDataQualityReport(): Promise<DataQualityReport> {
  const response = await apiClient.get<DataQualityReport>('/data-quality');
  return response.data;
}

/**
 * Holt den historischen Qualitätstrend
 *
 * @param months - Anzahl der Monate (default: 6)
 */
export async function getDataQualityTrend(months = 6): Promise<DataQualityTrend> {
  const response = await apiClient.get<DataQualityTrend>('/data-quality/trend', {
    params: { months },
  });
  return response.data;
}

/**
 * Führt eine Cleanup-Aktion für eine Kategorie aus
 *
 * @param category - Kategorie (z.B. 'duplicates', 'orphans')
 * @param action - Aktion (z.B. 'merge', 'delete')
 */
export async function fixDataQualityIssue(
  category: string,
  action: string
): Promise<FixActionResponse> {
  const response = await apiClient.post<FixActionResponse>(
    `/data-quality/${category}/fix`,
    { action }
  );
  return response.data;
}
