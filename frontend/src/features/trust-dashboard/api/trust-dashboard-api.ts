/**
 * Trust Dashboard API Client - Security & Compliance Monitoring
 *
 * API-Funktionen für das Trust Dashboard.
 * Überwacht Sicherheitsereignisse, Anomalien und Compliance.
 *
 * Backend-Endpunkte:
 * - GET /api/v1/trust-dashboard/?days=30 - Hauptdaten
 * - GET /api/v1/trust-dashboard/access-log - Zugriffsprotokolle
 * - GET /api/v1/trust-dashboard/export-log - Export-Protokolle
 * - GET /api/v1/trust-dashboard/anomalies - Erkannte Anomalien
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface MetricsResponse {
  total_accesses: number;
  sensitive_accesses: number;
  export_count: number;
  anomaly_count: number;
  compliance_score: number;
}

export interface SecurityEvent {
  id: string;
  action: string;
  user_id: string | null;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  success: boolean;
  error_message: string | null;
  created_at: string;
}

export interface Anomaly {
  id: string;
  type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  user_id: string | null;
  action: string;
  error_message: string | null;
  ip_address: string | null;
  created_at: string;
}

export interface TrustDashboardSnapshot {
  metrics: MetricsResponse;
  recent_events: SecurityEvent[];
  top_documents: Array<{
    document_id: string;
    filename: string;
    access_count: number;
  }>;
  user_activity: Array<{
    user_id: string;
    username: string;
    action_count: number;
  }>;
}

export interface SecurityEventsResponse {
  events: SecurityEvent[];
  total: number;
}

export interface AnomaliesResponse {
  anomalies: Anomaly[];
  total: number;
}

// ==================== Query Keys ====================

export const trustDashboardKeys = {
  all: ['trust-dashboard'] as const,
  snapshot: (days: number) => [...trustDashboardKeys.all, 'snapshot', days] as const,
  accessLog: (days: number, limit: number, offset: number) =>
    [...trustDashboardKeys.all, 'access-log', days, limit, offset] as const,
  exportLog: (days: number, limit: number, offset: number) =>
    [...trustDashboardKeys.all, 'export-log', days, limit, offset] as const,
  anomalies: (days: number, limit: number) =>
    [...trustDashboardKeys.all, 'anomalies', days, limit] as const,
};

// ==================== API Functions ====================

/**
 * Holt den Trust Dashboard Snapshot mit Metriken und Events
 */
export async function getTrustDashboardSnapshot(days = 30): Promise<TrustDashboardSnapshot> {
  const response = await apiClient.get<TrustDashboardSnapshot>('/trust-dashboard/', {
    params: { days },
  });
  return response.data;
}

/**
 * Holt das Zugriffsprotokolle
 */
export async function getAccessLog(
  days = 30,
  limit = 100,
  offset = 0
): Promise<SecurityEventsResponse> {
  const response = await apiClient.get<SecurityEventsResponse>('/trust-dashboard/access-log', {
    params: { days, limit, offset },
  });
  return response.data;
}

/**
 * Holt das Export-Protokolle
 */
export async function getExportLog(
  days = 30,
  limit = 100,
  offset = 0
): Promise<SecurityEventsResponse> {
  const response = await apiClient.get<SecurityEventsResponse>('/trust-dashboard/export-log', {
    params: { days, limit, offset },
  });
  return response.data;
}

/**
 * Holt erkannte Anomalien
 */
export async function getAnomalies(days = 7, limit = 50): Promise<AnomaliesResponse> {
  const response = await apiClient.get<AnomaliesResponse>('/trust-dashboard/anomalies', {
    params: { days, limit },
  });
  return response.data;
}
