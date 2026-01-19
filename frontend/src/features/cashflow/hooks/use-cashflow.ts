/**
 * Predictive Cash-Flow React Query Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getLiquidityForecast,
  predictPayment,
  getPaymentRecommendations,
  runScenario,
  getCashflowSummary,
  ScenarioRequest,
} from '../api/cashflow-api';

// ==================== Query Keys ====================

export const cashflowKeys = {
  all: ['cashflow'] as const,
  forecast: (days: number) => [...cashflowKeys.all, 'forecast', days] as const,
  prediction: (invoiceId: string) => [...cashflowKeys.all, 'prediction', invoiceId] as const,
  recommendations: () => [...cashflowKeys.all, 'recommendations'] as const,
  summary: () => [...cashflowKeys.all, 'summary'] as const,
};

// ==================== Hooks ====================

export function useLiquidityForecast(days: number = 30) {
  return useQuery({
    queryKey: cashflowKeys.forecast(days),
    queryFn: () => getLiquidityForecast(days),
    staleTime: 1000 * 60 * 5, // 5 Minuten
  });
}

export function usePaymentPrediction(invoiceId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: cashflowKeys.prediction(invoiceId),
    queryFn: () => predictPayment(invoiceId),
    enabled: enabled && !!invoiceId,
    staleTime: 1000 * 60 * 10, // 10 Minuten
  });
}

export function usePaymentRecommendations() {
  return useQuery({
    queryKey: cashflowKeys.recommendations(),
    queryFn: getPaymentRecommendations,
    staleTime: 1000 * 60 * 5,
  });
}

export function useCashflowSummary() {
  return useQuery({
    queryKey: cashflowKeys.summary(),
    queryFn: getCashflowSummary,
    staleTime: 1000 * 60 * 2, // 2 Minuten
  });
}

export function useRunScenario() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ScenarioRequest) => runScenario(request),
    onSuccess: () => {
      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: cashflowKeys.all });
    },
  });
}
