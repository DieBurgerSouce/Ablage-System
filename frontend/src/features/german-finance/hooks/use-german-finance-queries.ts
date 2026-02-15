/**
 * German Finance Query Hooks
 *
 * TanStack Query hooks for USt, BWA, and Cashflow
 */

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import {
  generateUStReport,
  getUStReports,
  getUStReport,
  generateBWAReport,
  getBWAReports,
  getBWAReport,
  getBWAComparison,
  updateCashflow,
  getCashflowForecast,
  getLiquidityWarnings,
  runCashflowScenario,
  getCashflowScenarios,
  getCashflowHistory,
} from '../api/german-finance-api';
import type {
  UStReport,
  BWAReport,
  CashflowForecast,
  LiquidityWarning,
  CashflowScenario,
  CashflowHistory,
  GenerateUStRequest,
  GenerateBWARequest,
  UpdateCashflowRequest,
  RunScenarioRequest,
} from '../types/german-finance-types';
import {
  transformUStReport,
  transformBWAReport,
  transformCashflowForecast,
  transformLiquidityWarning,
  transformCashflowScenario,
  transformCashflowHistory,
} from '../types/german-finance-types';

// ============================================================================
// Query Keys
// ============================================================================

export const germanFinanceKeys = {
  all: ['german-finance'] as const,
  ustReports: (params?: { year?: number; status?: string }) =>
    ['german-finance', 'ust', 'reports', params] as const,
  ustReport: (reportId: string) => ['german-finance', 'ust', 'report', reportId] as const,
  bwaReports: (params?: { year?: number; month?: number }) =>
    ['german-finance', 'bwa', 'reports', params] as const,
  bwaReport: (reportId: string) => ['german-finance', 'bwa', 'report', reportId] as const,
  bwaComparison: (report1Id: string, report2Id: string) =>
    ['german-finance', 'bwa', 'comparison', report1Id, report2Id] as const,
  cashflowForecast: (days?: number) => ['german-finance', 'cashflow', 'forecast', days] as const,
  cashflowWarnings: () => ['german-finance', 'cashflow', 'warnings'] as const,
  cashflowScenarios: () => ['german-finance', 'cashflow', 'scenarios'] as const,
  cashflowHistory: (params?: { start_date?: string; end_date?: string }) =>
    ['german-finance', 'cashflow', 'history', params] as const,
};

// ============================================================================
// USt-Voranmeldung Queries
// ============================================================================

export function useUStReports(params?: { year?: number; status?: 'draft' | 'submitted' | 'approved' }) {
  return useQuery({
    queryKey: germanFinanceKeys.ustReports(params),
    queryFn: async () => {
      const reports = await getUStReports(params);
      return reports.map(transformUStReport);
    },
  });
}

export function useUStReport(reportId: string, options?: Partial<UseQueryOptions<UStReport>>) {
  return useQuery({
    queryKey: germanFinanceKeys.ustReport(reportId),
    queryFn: async () => {
      const report = await getUStReport(reportId);
      return transformUStReport(report);
    },
    enabled: !!reportId,
    ...options,
  });
}

export function useGenerateUStReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: GenerateUStRequest) => {
      const report = await generateUStReport(data);
      return transformUStReport(report);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: germanFinanceKeys.ustReports() });
    },
  });
}

// ============================================================================
// BWA Queries
// ============================================================================

export function useBWAReports(params?: { year?: number; month?: number }) {
  return useQuery({
    queryKey: germanFinanceKeys.bwaReports(params),
    queryFn: async () => {
      const reports = await getBWAReports(params);
      return reports.map(transformBWAReport);
    },
  });
}

export function useBWAReport(reportId: string, options?: Partial<UseQueryOptions<BWAReport>>) {
  return useQuery({
    queryKey: germanFinanceKeys.bwaReport(reportId),
    queryFn: async () => {
      const report = await getBWAReport(reportId);
      return transformBWAReport(report);
    },
    enabled: !!reportId,
    ...options,
  });
}

export function useGenerateBWAReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: GenerateBWARequest) => {
      const report = await generateBWAReport(data);
      return transformBWAReport(report);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: germanFinanceKeys.bwaReports() });
    },
  });
}

export function useBWAComparison(report1Id: string, report2Id: string) {
  return useQuery({
    queryKey: germanFinanceKeys.bwaComparison(report1Id, report2Id),
    queryFn: async () => {
      const comparison = await getBWAComparison({
        report1_id: report1Id,
        report2_id: report2Id,
      });
      return {
        report1: transformBWAReport(comparison.report1),
        report2: transformBWAReport(comparison.report2),
        differences: comparison.differences,
      };
    },
    enabled: !!report1Id && !!report2Id,
  });
}

// ============================================================================
// Cashflow Queries
// ============================================================================

export function useCashflowForecast(days?: 30 | 60 | 90) {
  return useQuery({
    queryKey: germanFinanceKeys.cashflowForecast(days),
    queryFn: async () => {
      const forecast = await getCashflowForecast({ days });
      return forecast.map(transformCashflowForecast);
    },
  });
}

export function useLiquidityWarnings() {
  return useQuery({
    queryKey: germanFinanceKeys.cashflowWarnings(),
    queryFn: async () => {
      const warnings = await getLiquidityWarnings();
      return warnings.map(transformLiquidityWarning);
    },
    refetchInterval: 300000, // Refresh every 5 minutes
  });
}

export function useCashflowScenarios() {
  return useQuery({
    queryKey: germanFinanceKeys.cashflowScenarios(),
    queryFn: async () => {
      const scenarios = await getCashflowScenarios();
      return scenarios.map(transformCashflowScenario);
    },
  });
}

export function useCashflowHistory(params?: { start_date?: string; end_date?: string }) {
  return useQuery({
    queryKey: germanFinanceKeys.cashflowHistory(params),
    queryFn: async () => {
      const history = await getCashflowHistory(params);
      return history.map(transformCashflowHistory);
    },
  });
}

export function useUpdateCashflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateCashflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: germanFinanceKeys.cashflowForecast() });
      queryClient.invalidateQueries({ queryKey: germanFinanceKeys.cashflowWarnings() });
      queryClient.invalidateQueries({ queryKey: germanFinanceKeys.cashflowHistory() });
    },
  });
}

export function useRunCashflowScenario() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: RunScenarioRequest) => {
      const scenario = await runCashflowScenario(data);
      return transformCashflowScenario(scenario);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: germanFinanceKeys.cashflowScenarios() });
    },
  });
}
