/**
 * CEO Dashboard Query Hooks
 *
 * TanStack Query hooks for CEO Dashboard data fetching.
 */

import { useQuery } from '@tanstack/react-query';
import { ceoDashboardApi } from '../api';
import type { OverviewData, HealthScore, TrendData, Anomaly } from '../types';

const QUERY_KEYS = {
  overview: ['ceo-dashboard', 'overview'] as const,
  healthScore: ['ceo-dashboard', 'health-score'] as const,
  trends: (days: number) => ['ceo-dashboard', 'trends', days] as const,
  anomalies: ['ceo-dashboard', 'anomalies'] as const,
};

/**
 * Hook to fetch CEO dashboard overview
 * Refetches every minute to keep data fresh
 */
export function useCeoOverview() {
  return useQuery<OverviewData, Error>({
    queryKey: QUERY_KEYS.overview,
    queryFn: ceoDashboardApi.getOverview,
    refetchInterval: 60000, // 1 minute
    staleTime: 30000, // 30 seconds
  });
}

/**
 * Hook to fetch detailed health score
 */
export function useCeoHealthScore() {
  return useQuery<HealthScore, Error>({
    queryKey: QUERY_KEYS.healthScore,
    queryFn: ceoDashboardApi.getHealthScore,
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to fetch trend data for sparklines
 * @param days - Number of days to include (7-365)
 */
export function useCeoTrends(days: number = 30) {
  return useQuery<TrendData, Error>({
    queryKey: QUERY_KEYS.trends(days),
    queryFn: () => ceoDashboardApi.getTrends(days),
    staleTime: 300000, // 5 minutes
  });
}

/**
 * Hook to fetch detected anomalies
 */
export function useCeoAnomalies() {
  return useQuery<Anomaly[], Error>({
    queryKey: QUERY_KEYS.anomalies,
    queryFn: ceoDashboardApi.getAnomalies,
    refetchInterval: 120000, // 2 minutes
    staleTime: 60000, // 1 minute
  });
}
