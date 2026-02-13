/**
 * CEO Dashboard API Service
 *
 * Handles all API calls for the CEO Dashboard feature.
 */

import { apiClient } from '@/lib/api/client';
import type {
  OverviewResponse,
  HealthScoreResponse,
  TrendDataResponse,
  AnomalyResponse,
  OverviewData,
  HealthScore,
  TrendData,
  Anomaly,
} from '../types';
import {
  transformOverviewData,
  transformHealthScore,
  transformTrendData,
  transformAnomaly,
} from '../types';

const BASE_PATH = '/ceo-dashboard';

/**
 * Get full CEO dashboard overview with all metrics
 */
export async function getOverview(): Promise<OverviewData> {
  const response = await apiClient.get<OverviewResponse>(`${BASE_PATH}/overview`);
  return transformOverviewData(response.data);
}

/**
 * Get detailed health score breakdown
 */
export async function getHealthScore(): Promise<HealthScore> {
  const response = await apiClient.get<HealthScoreResponse>(`${BASE_PATH}/health-score`);
  return transformHealthScore(response.data);
}

/**
 * Get trend data for sparklines
 * @param days - Number of days to include (7-365)
 */
export async function getTrends(days: number = 30): Promise<TrendData> {
  const response = await apiClient.get<TrendDataResponse>(`${BASE_PATH}/trends`, {
    params: { days },
  });
  return transformTrendData(response.data);
}

/**
 * Get detected anomalies
 */
export async function getAnomalies(): Promise<Anomaly[]> {
  const response = await apiClient.get<AnomalyResponse[]>(`${BASE_PATH}/anomalies`);
  return response.data.map(transformAnomaly);
}

// Export all functions as a service object
export const ceoDashboardApi = {
  getOverview,
  getHealthScore,
  getTrends,
  getAnomalies,
};
