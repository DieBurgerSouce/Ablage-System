/**
 * Digital Twin Query Hooks
 *
 * TanStack Query hooks for Digital Twin data fetching.
 */

import { useQuery } from '@tanstack/react-query';
import { digitalTwinApi } from '../api/digital-twin-api';
import type {
  DigitalTwin,
  FinancialHealth,
  RiskOverview,
  DocumentPipeline,
  Compliance,
  KeyMetrics,
  Trends,
} from '../types/digital-twin-types';

const QUERY_KEYS = {
  digitalTwin: ['digital-twin'] as const,
  financialHealth: ['digital-twin', 'financial-health'] as const,
  riskOverview: ['digital-twin', 'risk-overview'] as const,
  documentPipeline: ['digital-twin', 'document-pipeline'] as const,
  compliance: ['digital-twin', 'compliance'] as const,
  keyMetrics: ['digital-twin', 'key-metrics'] as const,
  trends: ['digital-twin', 'trends'] as const,
};

/**
 * Hook to fetch full digital twin data
 * Auto-refreshes every 60 seconds
 */
export function useDigitalTwin() {
  return useQuery<DigitalTwin, Error>({
    queryKey: QUERY_KEYS.digitalTwin,
    queryFn: digitalTwinApi.getDigitalTwin,
    refetchInterval: 60000, // 60 seconds
    staleTime: 30000, // 30 seconds
  });
}

/**
 * Hook to fetch financial health only
 */
export function useFinancialHealth() {
  return useQuery<FinancialHealth, Error>({
    queryKey: QUERY_KEYS.financialHealth,
    queryFn: digitalTwinApi.getFinancialHealth,
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch risk overview only
 */
export function useRiskOverview() {
  return useQuery<RiskOverview, Error>({
    queryKey: QUERY_KEYS.riskOverview,
    queryFn: digitalTwinApi.getRiskOverview,
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch document pipeline only
 */
export function useDocumentPipeline() {
  return useQuery<DocumentPipeline, Error>({
    queryKey: QUERY_KEYS.documentPipeline,
    queryFn: digitalTwinApi.getDocumentPipeline,
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch compliance only
 */
export function useCompliance() {
  return useQuery<Compliance, Error>({
    queryKey: QUERY_KEYS.compliance,
    queryFn: digitalTwinApi.getCompliance,
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch key metrics only
 */
export function useKeyMetrics() {
  return useQuery<KeyMetrics, Error>({
    queryKey: QUERY_KEYS.keyMetrics,
    queryFn: digitalTwinApi.getKeyMetrics,
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

/**
 * Hook to fetch trends only
 */
export function useTrends() {
  return useQuery<Trends, Error>({
    queryKey: QUERY_KEYS.trends,
    queryFn: digitalTwinApi.getTrends,
    refetchInterval: 300000, // 5 minutes
    staleTime: 60000, // 1 minute
  });
}
