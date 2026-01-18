/**
 * Supplier Ranking Query Hooks
 *
 * TanStack Query Hooks fuer das Lieferanten-Ranking System.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supplierRankingService } from '../api/supplier-ranking-api';

// Query Keys
export const supplierRankingKeys = {
  all: ['supplier-ranking'] as const,
  report: (periodDays?: number, topN?: number) =>
    [...supplierRankingKeys.all, 'report', periodDays, topN] as const,
  supplier: (entityId: string, periodDays?: number) =>
    [...supplierRankingKeys.all, 'supplier', entityId, periodDays] as const,
  tierDistribution: (periodDays?: number) =>
    [...supplierRankingKeys.all, 'tier-distribution', periodDays] as const,
  comparison: (entityIds: string[], periodDays?: number) =>
    [...supplierRankingKeys.all, 'comparison', entityIds.join(','), periodDays] as const,
};

/**
 * Hook to get full supplier ranking report
 */
export function useSupplierRankingReport(periodDays = 365, topN = 10) {
  return useQuery({
    queryKey: supplierRankingKeys.report(periodDays, topN),
    queryFn: () => supplierRankingService.getSupplierRankingReport(periodDays, topN),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to get ranking for a single supplier
 */
export function useSupplierRanking(entityId: string, periodDays = 365, enabled = true) {
  return useQuery({
    queryKey: supplierRankingKeys.supplier(entityId, periodDays),
    queryFn: () => supplierRankingService.getSupplierRanking(entityId, periodDays),
    enabled: enabled && !!entityId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to get tier distribution
 */
export function useTierDistribution(periodDays = 365) {
  return useQuery({
    queryKey: supplierRankingKeys.tierDistribution(periodDays),
    queryFn: () => supplierRankingService.getTierDistribution(periodDays),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to compare multiple suppliers
 */
export function useSupplierComparison(
  entityIds: string[],
  periodDays = 365,
  enabled = true
) {
  return useQuery({
    queryKey: supplierRankingKeys.comparison(entityIds, periodDays),
    queryFn: () => supplierRankingService.compareSuppliers(entityIds, periodDays),
    enabled: enabled && entityIds.length >= 2,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Mutation hook for comparing suppliers (on-demand)
 */
export function useCompareSuppliersMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      entityIds,
      periodDays = 365,
    }: {
      entityIds: string[];
      periodDays?: number;
    }) => supplierRankingService.compareSuppliers(entityIds, periodDays),
    onSuccess: (data, variables) => {
      // Cache the comparison result
      queryClient.setQueryData(
        supplierRankingKeys.comparison(variables.entityIds, variables.periodDays),
        data
      );
    },
  });
}

/**
 * Combined hook for supplier ranking dashboard
 */
export function useSupplierRankingDashboard(periodDays = 365) {
  const reportQuery = useSupplierRankingReport(periodDays);
  const tierDistributionQuery = useTierDistribution(periodDays);

  return {
    report: reportQuery.data,
    tierDistribution: tierDistributionQuery.data,
    isLoading: reportQuery.isLoading || tierDistributionQuery.isLoading,
    isError: reportQuery.isError || tierDistributionQuery.isError,
    error: reportQuery.error || tierDistributionQuery.error,
    refetch: async () => {
      await Promise.all([reportQuery.refetch(), tierDistributionQuery.refetch()]);
    },
  };
}
