/**
 * Payment Behavior Query Hooks
 *
 * TanStack Query Hooks für Zahlungsverhaltens-Analyse.
 */

import { useQuery } from '@tanstack/react-query';
import { paymentBehaviorService } from '../api/payment-behavior-api';

// Query Keys
export const paymentBehaviorKeys = {
  all: ['payment-behavior'] as const,
  report: (periodDays?: number, topN?: number) =>
    [...paymentBehaviorKeys.all, 'report', periodDays, topN] as const,
  customer: (entityId: string, periodDays?: number) =>
    [...paymentBehaviorKeys.all, 'customer', entityId, periodDays] as const,
  ranking: (periodDays?: number, limit?: number, sortBy?: string, sortDesc?: boolean) =>
    [...paymentBehaviorKeys.all, 'ranking', periodDays, limit, sortBy, sortDesc] as const,
  distribution: (periodDays?: number) =>
    [...paymentBehaviorKeys.all, 'distribution', periodDays] as const,
};

/**
 * Hook to get payment behavior report
 */
export function usePaymentBehaviorReport(periodDays = 365, topN = 10) {
  return useQuery({
    queryKey: paymentBehaviorKeys.report(periodDays, topN),
    queryFn: () => paymentBehaviorService.getPaymentBehaviorReport(periodDays, topN),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to get customer payment behavior
 */
export function useCustomerPaymentBehavior(
  entityId: string,
  periodDays = 365,
  enabled = true
) {
  return useQuery({
    queryKey: paymentBehaviorKeys.customer(entityId, periodDays),
    queryFn: () => paymentBehaviorService.getCustomerPaymentBehavior(entityId, periodDays),
    enabled: enabled && !!entityId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to get customer ranking
 */
export function useCustomerRanking(
  periodDays = 365,
  limit = 50,
  sortBy = 'payment_score',
  sortDesc = true
) {
  return useQuery({
    queryKey: paymentBehaviorKeys.ranking(periodDays, limit, sortBy, sortDesc),
    queryFn: () =>
      paymentBehaviorService.getCustomerRanking(periodDays, limit, sortBy, sortDesc),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to get category distribution
 */
export function useCategoryDistribution(periodDays = 365) {
  return useQuery({
    queryKey: paymentBehaviorKeys.distribution(periodDays),
    queryFn: () => paymentBehaviorService.getCategoryDistribution(periodDays),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Combined hook for dashboard
 */
export function usePaymentBehaviorDashboard(periodDays = 365) {
  const reportQuery = usePaymentBehaviorReport(periodDays);
  const distributionQuery = useCategoryDistribution(periodDays);

  return {
    report: reportQuery.data,
    distribution: distributionQuery.data,
    isLoading: reportQuery.isLoading || distributionQuery.isLoading,
    isError: reportQuery.isError || distributionQuery.isError,
    error: reportQuery.error || distributionQuery.error,
    refetch: async () => {
      await Promise.all([reportQuery.refetch(), distributionQuery.refetch()]);
    },
  };
}
