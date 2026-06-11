/**
 * Fraud Detection React Query Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { analyzeFraud, getFraudDashboard, getFraudAlerts, getFraudConfig, updateFraudConfig, getFraudTypes, getRiskLevels, getEntityRiskProfile, type FraudConfig } from '../api/fraud-api';

// ==================== Query Keys ====================

export const fraudKeys = {
  all: ['fraud'] as const,
  analysis: (days: number) => [...fraudKeys.all, 'analysis', days] as const,
  dashboard: () => [...fraudKeys.all, 'dashboard'] as const,
  alerts: (params?: Record<string, unknown>) => [...fraudKeys.all, 'alerts', params] as const,
  config: () => [...fraudKeys.all, 'config'] as const,
  types: () => [...fraudKeys.all, 'types'] as const,
  riskLevels: () => [...fraudKeys.all, 'risk-levels'] as const,
  entityProfile: (entityId: string) => [...fraudKeys.all, 'entity', entityId] as const,
};

// ==================== Hooks ====================

export function useFraudAnalysis(days: number = 90) {
  return useQuery({
    queryKey: fraudKeys.analysis(days),
    queryFn: () => analyzeFraud(days),
    staleTime: 1000 * 60 * 10, // 10 Minuten - Fraud-Analyse ist rechenintensiv
  });
}

export function useFraudDashboard() {
  return useQuery({
    queryKey: fraudKeys.dashboard(),
    queryFn: getFraudDashboard,
    staleTime: 1000 * 60 * 5, // 5 Minuten
  });
}

export function useFraudAlerts(params?: {
  fraud_type?: string;
  risk_level?: string;
  days?: number;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: fraudKeys.alerts(params),
    queryFn: () => getFraudAlerts(params),
    staleTime: 1000 * 60 * 5,
  });
}

export function useFraudConfig() {
  return useQuery({
    queryKey: fraudKeys.config(),
    queryFn: getFraudConfig,
    staleTime: 1000 * 60 * 30, // 30 Minuten - Konfiguration ändert sich selten
  });
}

export function useUpdateFraudConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (config: Partial<FraudConfig>) => updateFraudConfig(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: fraudKeys.config() });
      // Auch Analyse neu laden, da Konfiguration Einfluss hat
      queryClient.invalidateQueries({ queryKey: fraudKeys.all });
    },
  });
}

export function useFraudTypes() {
  return useQuery({
    queryKey: fraudKeys.types(),
    queryFn: getFraudTypes,
    staleTime: Infinity, // Statische Daten
  });
}

export function useRiskLevels() {
  return useQuery({
    queryKey: fraudKeys.riskLevels(),
    queryFn: getRiskLevels,
    staleTime: Infinity, // Statische Daten
  });
}

export function useEntityRiskProfile(entityId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: fraudKeys.entityProfile(entityId),
    queryFn: () => getEntityRiskProfile(entityId),
    enabled: enabled && !!entityId,
    staleTime: 1000 * 60 * 10,
  });
}
