/**
 * Risk Scoring Query Hooks
 *
 * TanStack Query Hooks für das Risk Scoring System.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { riskService } from '../api/risk-api';
import type {
  EntityRisk,
  RiskStatistics,
  RiskFilter,
  EntityType,
} from '../types/risk-types';

// Query Keys
export const riskKeys = {
  all: ['risk'] as const,
  statistics: (entityType?: EntityType) =>
    [...riskKeys.all, 'statistics', entityType] as const,
  entities: (filter?: RiskFilter) =>
    [...riskKeys.all, 'entities', filter] as const,
  highRisk: (filter?: RiskFilter) =>
    [...riskKeys.all, 'high-risk', filter] as const,
  entity: (entityId: string) =>
    [...riskKeys.all, 'entity', entityId] as const,
  trend: (entityId: string, days?: number) =>
    [...riskKeys.all, 'trend', entityId, days] as const,
};

/**
 * Hook to get risk statistics
 */
export function useRiskStatistics(entityType?: EntityType) {
  return useQuery({
    queryKey: riskKeys.statistics(entityType),
    queryFn: () => riskService.getRiskStatistics(entityType),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to get all entities with risk scores
 */
export function useEntitiesWithRisk(filter?: RiskFilter) {
  return useQuery({
    queryKey: riskKeys.entities(filter),
    queryFn: () => riskService.getAllEntitiesWithRisk(filter),
    staleTime: 2 * 60 * 1000, // 2 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Hook to get high-risk entities
 */
export function useHighRiskEntities(filter?: RiskFilter) {
  return useQuery({
    queryKey: riskKeys.highRisk(filter),
    queryFn: () => riskService.getHighRiskEntities(filter),
    staleTime: 2 * 60 * 1000, // 2 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Hook to get risk score for a single entity
 */
export function useEntityRisk(entityId: string, enabled = true) {
  return useQuery({
    queryKey: riskKeys.entity(entityId),
    queryFn: () => riskService.getEntityRisk(entityId),
    enabled: enabled && !!entityId,
    staleTime: 2 * 60 * 1000, // 2 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Hook to get risk trend for an entity
 */
export function useEntityRiskTrend(entityId: string, days = 30, enabled = true) {
  return useQuery({
    queryKey: riskKeys.trend(entityId, days),
    queryFn: () => riskService.getEntityRiskTrend(entityId, days),
    enabled: enabled && !!entityId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to recalculate risk score for a single entity
 */
export function useCalculateEntityRisk() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (entityId: string) => riskService.calculateEntityRisk(entityId),
    onSuccess: (data, entityId) => {
      // Update entity risk cache
      queryClient.setQueryData<EntityRisk>(riskKeys.entity(entityId), (old) =>
        old
          ? {
              ...old,
              riskScore: data.riskScore,
              riskFactors: data.riskFactors,
              calculatedAt: data.calculatedAt,
            }
          : old
      );

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: riskKeys.entities() });
      queryClient.invalidateQueries({ queryKey: riskKeys.highRisk() });
      queryClient.invalidateQueries({ queryKey: riskKeys.statistics() });
      queryClient.invalidateQueries({
        queryKey: riskKeys.trend(entityId),
      });
    },
  });
}

/**
 * Hook to recalculate all risk scores
 */
export function useCalculateAllRisks() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params?: { entityType?: EntityType; limit?: number }) =>
      riskService.calculateAllRisks(params),
    onSuccess: () => {
      // Invalidate all risk-related queries
      queryClient.invalidateQueries({ queryKey: riskKeys.all });
    },
  });
}

/**
 * Combined hook for risk dashboard data
 */
export function useRiskDashboard(entityType?: EntityType) {
  const statisticsQuery = useRiskStatistics(entityType);
  const highRiskQuery = useHighRiskEntities({
    entityType,
    sortBy: 'risk_score',
    sortOrder: 'desc',
    perPage: 10,
  });

  return {
    statistics: statisticsQuery.data,
    highRiskEntities: highRiskQuery.data?.entities ?? [],
    isLoading: statisticsQuery.isLoading || highRiskQuery.isLoading,
    isError: statisticsQuery.isError || highRiskQuery.isError,
    error: statisticsQuery.error || highRiskQuery.error,
    refetch: async () => {
      await Promise.all([statisticsQuery.refetch(), highRiskQuery.refetch()]);
    },
  };
}

/**
 * Hook for risk mutations
 */
export function useRiskMutations() {
  const calculateSingle = useCalculateEntityRisk();
  const calculateAll = useCalculateAllRisks();

  return {
    calculateEntityRisk: calculateSingle,
    calculateAllRisks: calculateAll,
  };
}
