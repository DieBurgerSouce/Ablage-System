/**
 * Executive Dashboard Hooks
 *
 * TanStack Query hooks for executive reporting data.
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import type {
  KPIResponse,
  DepartmentBreakdown,
  TrendResponse,
  ExecutiveSummaryResponse,
  TrendMetric,
} from '../types/executive-types'
import { getKPIs, getDepartments, getTrend, getSummary } from '../api/executive-api'

/**
 * Query key factory for executive reporting
 */
export const executiveKeys = {
  all: ['executive'] as const,
  kpis: () => [...executiveKeys.all, 'kpis'] as const,
  departments: () => [...executiveKeys.all, 'departments'] as const,
  trend: (metric: TrendMetric, days: number) =>
    [...executiveKeys.all, 'trend', metric, days] as const,
  summary: () => [...executiveKeys.all, 'summary'] as const,
}

/**
 * Hook to fetch KPIs
 */
export function useKPIs(): UseQueryResult<KPIResponse> {
  return useQuery({
    queryKey: executiveKeys.kpis(),
    queryFn: getKPIs,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000, // Auto-refresh every 5 minutes
  })
}

/**
 * Hook to fetch department breakdown
 */
export function useDepartments(): UseQueryResult<DepartmentBreakdown[]> {
  return useQuery({
    queryKey: executiveKeys.departments(),
    queryFn: getDepartments,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })
}

/**
 * Hook to fetch trend data
 */
export function useTrend(
  metric: TrendMetric,
  days: number = 30
): UseQueryResult<TrendResponse> {
  return useQuery({
    queryKey: executiveKeys.trend(metric, days),
    queryFn: () => getTrend(metric, days),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })
}

/**
 * Hook to fetch complete executive summary
 */
export function useExecutiveSummary(): UseQueryResult<ExecutiveSummaryResponse> {
  return useQuery({
    queryKey: executiveKeys.summary(),
    queryFn: getSummary,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })
}
