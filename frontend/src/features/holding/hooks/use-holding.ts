/**
 * Holding Dashboard React Query Hooks
 */

import { useQuery } from '@tanstack/react-query';
import {
  getHoldingOverview,
  getHoldingCompanies,
  compareCompanies,
  getIntercompanyMetrics,
  getCashFlowOverview,
  ComparisonMetric,
  CashFlowPeriod,
} from '../api/holding-api';

// ==================== Query Keys ====================

export const holdingKeys = {
  all: ['holding'] as const,
  overview: (companyIds?: string[]) =>
    [...holdingKeys.all, 'overview', companyIds] as const,
  companies: () => [...holdingKeys.all, 'companies'] as const,
  comparison: (metric: ComparisonMetric, companyIds?: string[]) =>
    [...holdingKeys.all, 'comparison', metric, companyIds] as const,
  intercompany: (companyIds?: string[]) =>
    [...holdingKeys.all, 'intercompany', companyIds] as const,
  cashflow: (period: CashFlowPeriod, companyIds?: string[]) =>
    [...holdingKeys.all, 'cashflow', period, companyIds] as const,
};

// ==================== Hooks ====================

/**
 * Hole konsolidierte Holding-Übersicht
 */
export function useHoldingOverview(companyIds?: string[]) {
  return useQuery({
    queryKey: holdingKeys.overview(companyIds),
    queryFn: () => getHoldingOverview(companyIds),
    staleTime: 1000 * 60 * 5, // 5 Minuten
  });
}

/**
 * Hole alle Firmen
 */
export function useHoldingCompanies() {
  return useQuery({
    queryKey: holdingKeys.companies(),
    queryFn: getHoldingCompanies,
    staleTime: 1000 * 60 * 10, // 10 Minuten
  });
}

/**
 * Vergleiche Firmen
 */
export function useCompanyComparison(
  metric: ComparisonMetric,
  companyIds?: string[],
  enabled: boolean = true
) {
  return useQuery({
    queryKey: holdingKeys.comparison(metric, companyIds),
    queryFn: () => compareCompanies(metric, companyIds),
    enabled,
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hole Intercompany-Metriken
 */
export function useIntercompanyMetrics(companyIds?: string[]) {
  return useQuery({
    queryKey: holdingKeys.intercompany(companyIds),
    queryFn: () => getIntercompanyMetrics(companyIds),
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hole Cashflow-Übersicht
 */
export function useCashFlowOverview(
  period: CashFlowPeriod = 'monthly',
  companyIds?: string[]
) {
  return useQuery({
    queryKey: holdingKeys.cashflow(period, companyIds),
    queryFn: () => getCashFlowOverview(period, companyIds),
    staleTime: 1000 * 60 * 5,
  });
}
