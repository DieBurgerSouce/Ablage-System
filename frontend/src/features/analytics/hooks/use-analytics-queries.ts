// Analytics Dashboard React Query Hooks
// Query key factory + hooks with auto-refresh

import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { toast } from 'sonner';
import { analyticsApi } from '../api/analytics-api';
import {
  type OperationsData,
  type FinanceData,
  type TeamStats,
  type WorkloadData,
  type AnalyticsPeriod,
  transformOperationsData,
  transformFinanceData,
  transformTeamStats,
  transformWorkloadData,
  PERIOD_OPTIONS,
} from '../types/analytics-types';

// ============================================================================
// QUERY KEY FACTORY
// ============================================================================

export const analyticsKeys = {
  all: ['analytics'] as const,
  operations: (period: string) => [...analyticsKeys.all, 'operations', period] as const,
  finance: (period: string) => [...analyticsKeys.all, 'finance', period] as const,
  team: (period: string) => [...analyticsKeys.all, 'team', period] as const,
  workload: (period: string) => [...analyticsKeys.all, 'workload', period] as const,
};

// ============================================================================
// HELPER: Period to API value
// ============================================================================

function periodToApi(period: AnalyticsPeriod): string {
  const option = PERIOD_OPTIONS.find((o) => o.value === period);
  return option?.apiValue ?? 'month';
}

// ============================================================================
// OPERATIONS DATA
// ============================================================================

export function useOperationsData(period: AnalyticsPeriod): UseQueryResult<OperationsData, Error> {
  const apiPeriod = periodToApi(period);
  return useQuery({
    queryKey: analyticsKeys.operations(apiPeriod),
    queryFn: async () => {
      const data = await analyticsApi.getOperationsData(apiPeriod);
      return transformOperationsData(data);
    },
    staleTime: 60 * 1000, // 60s
    refetchInterval: 60 * 1000, // Auto-refresh every 60s
  });
}

// ============================================================================
// FINANCE DATA
// ============================================================================

export function useFinanceData(period: AnalyticsPeriod): UseQueryResult<FinanceData, Error> {
  const apiPeriod = periodToApi(period);
  return useQuery({
    queryKey: analyticsKeys.finance(apiPeriod),
    queryFn: async () => {
      const data = await analyticsApi.getFinanceData(apiPeriod);
      return transformFinanceData(data);
    },
    staleTime: 2 * 60 * 1000, // 2min
    refetchInterval: 2 * 60 * 1000, // Auto-refresh every 2min
  });
}

// ============================================================================
// TEAM STATS
// ============================================================================

export function useTeamStats(period: AnalyticsPeriod): UseQueryResult<TeamStats, Error> {
  const apiPeriod = periodToApi(period);
  return useQuery({
    queryKey: analyticsKeys.team(apiPeriod),
    queryFn: async () => {
      const data = await analyticsApi.getTeamStats(apiPeriod);
      return transformTeamStats(data);
    },
    staleTime: 5 * 60 * 1000, // 5min
    refetchInterval: 5 * 60 * 1000, // Auto-refresh every 5min
  });
}

// ============================================================================
// WORKLOAD DATA (Heatmap)
// ============================================================================

export function useWorkloadData(period: AnalyticsPeriod): UseQueryResult<WorkloadData, Error> {
  const apiPeriod = periodToApi(period);
  return useQuery({
    queryKey: analyticsKeys.workload(apiPeriod),
    queryFn: async () => {
      const data = await analyticsApi.getWorkloadData(apiPeriod);
      return transformWorkloadData(data);
    },
    staleTime: 5 * 60 * 1000, // 5min
    refetchInterval: 5 * 60 * 1000, // Auto-refresh every 5min
  });
}

// ============================================================================
// INVALIDATE ALL
// ============================================================================

export function useInvalidateAnalytics() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.invalidateQueries({ queryKey: analyticsKeys.all });
    toast.success('Dashboard aktualisiert');
  };
}
