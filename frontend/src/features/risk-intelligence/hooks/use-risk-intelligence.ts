/**
 * Risk Intelligence React Query Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getEntityRiskProfile,
  getEntityTrend,
  getEntityBenchmark,
  getEntityNetwork,
  checkExternalSources,
  getPortfolioRisk,
  getIndustryBenchmarks,
  getTrendDirections,
  getExternalSources,
} from '../api/risk-intelligence-api';

// ==================== Query Keys ====================

export const riskIntelligenceKeys = {
  all: ['risk-intelligence'] as const,
  profile: (entityId: string) => [...riskIntelligenceKeys.all, 'profile', entityId] as const,
  trend: (entityId: string, quarters?: number) =>
    [...riskIntelligenceKeys.all, 'trend', entityId, quarters] as const,
  benchmark: (entityId: string, industry?: string) =>
    [...riskIntelligenceKeys.all, 'benchmark', entityId, industry] as const,
  network: (entityId: string) => [...riskIntelligenceKeys.all, 'network', entityId] as const,
  external: (entityId: string) => [...riskIntelligenceKeys.all, 'external', entityId] as const,
  portfolio: (entityType?: string) => [...riskIntelligenceKeys.all, 'portfolio', entityType] as const,
  benchmarks: () => [...riskIntelligenceKeys.all, 'benchmarks'] as const,
  trendDirections: () => [...riskIntelligenceKeys.all, 'trend-directions'] as const,
  externalSources: () => [...riskIntelligenceKeys.all, 'external-sources'] as const,
};

// ==================== Hooks ====================

/**
 * Hook für umfassendes Risikoprofil einer Entity
 */
export function useEntityRiskProfile(entityId: string | undefined) {
  return useQuery({
    queryKey: riskIntelligenceKeys.profile(entityId || ''),
    queryFn: () => getEntityRiskProfile(entityId!),
    enabled: !!entityId,
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

/**
 * Hook für Trend-Analyse einer Entity
 */
export function useEntityTrend(entityId: string | undefined, quarters: number = 4) {
  return useQuery({
    queryKey: riskIntelligenceKeys.trend(entityId || '', quarters),
    queryFn: () => getEntityTrend(entityId!, quarters),
    enabled: !!entityId,
    staleTime: 10 * 60 * 1000, // 10 Minuten
  });
}

/**
 * Hook für Benchmark-Vergleich einer Entity
 */
export function useEntityBenchmark(entityId: string | undefined, industry?: string) {
  return useQuery({
    queryKey: riskIntelligenceKeys.benchmark(entityId || '', industry),
    queryFn: () => getEntityBenchmark(entityId!, industry),
    enabled: !!entityId,
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * Hook für Netzwerk-Analyse einer Entity
 */
export function useEntityNetwork(entityId: string | undefined) {
  return useQuery({
    queryKey: riskIntelligenceKeys.network(entityId || ''),
    queryFn: () => getEntityNetwork(entityId!),
    enabled: !!entityId,
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * Hook für externe Quellenprüfung einer Entity
 */
export function useExternalSourceCheck(entityId: string | undefined) {
  return useQuery({
    queryKey: riskIntelligenceKeys.external(entityId || ''),
    queryFn: () => checkExternalSources(entityId!),
    enabled: !!entityId,
    staleTime: 30 * 60 * 1000, // 30 Minuten (externe Abfragen)
  });
}

/**
 * Hook für Portfolio-Risikoübersicht
 */
export function usePortfolioRisk(entityType?: 'customer' | 'supplier') {
  return useQuery({
    queryKey: riskIntelligenceKeys.portfolio(entityType),
    queryFn: () => getPortfolioRisk(entityType),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook für Branchen-Benchmarks
 */
export function useIndustryBenchmarks() {
  return useQuery({
    queryKey: riskIntelligenceKeys.benchmarks(),
    queryFn: getIndustryBenchmarks,
    staleTime: 60 * 60 * 1000, // 1 Stunde (statische Daten)
  });
}

/**
 * Hook für Trend-Richtungen
 */
export function useTrendDirections() {
  return useQuery({
    queryKey: riskIntelligenceKeys.trendDirections(),
    queryFn: getTrendDirections,
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * Hook für externe Datenquellen
 */
export function useExternalSources() {
  return useQuery({
    queryKey: riskIntelligenceKeys.externalSources(),
    queryFn: getExternalSources,
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * Hook zum manuellen Neuladen des Risikoprofils
 */
export function useRefreshRiskProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (entityId: string) => {
      // Invalidate all related queries
      await queryClient.invalidateQueries({
        queryKey: riskIntelligenceKeys.profile(entityId),
      });
      await queryClient.invalidateQueries({
        queryKey: riskIntelligenceKeys.trend(entityId),
      });
      await queryClient.invalidateQueries({
        queryKey: riskIntelligenceKeys.benchmark(entityId),
      });
      await queryClient.invalidateQueries({
        queryKey: riskIntelligenceKeys.network(entityId),
      });
      // Fetch fresh data
      return getEntityRiskProfile(entityId);
    },
  });
}
