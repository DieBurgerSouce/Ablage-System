// Smart Dashboard React Query Hooks
// Query key factory + hooks with optimistic updates

import { useQuery, useMutation, useQueryClient, UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import { toast } from 'sonner';
import { smartDashboardApi } from '../api/smart-dashboard-api';
import {
  KPIData,
  TabData,
  WidgetData,
  DocumentProgress,
  BatchProgress,
  TrendData,
  WidgetLayout,
  DashboardTabKey,
  transformKPIData,
  transformTabData,
  transformWidgetData,
  transformDocumentProgress,
  transformBatchProgress,
  transformTrendData,
} from '../types/smart-dashboard-types';

// ============================================================================
// QUERY KEY FACTORY
// ============================================================================

export const smartDashboardKeys = {
  all: ['smart-dashboard'] as const,
  kpis: () => [...smartDashboardKeys.all, 'kpis'] as const,
  tabs: () => [...smartDashboardKeys.all, 'tabs'] as const,
  tab: (tab: DashboardTabKey, role?: string) =>
    [...smartDashboardKeys.tabs(), tab, { role }] as const,
  widgets: (role?: string) => [...smartDashboardKeys.all, 'widgets', { role }] as const,
  trends: (kpiKey?: string) => [...smartDashboardKeys.all, 'trends', { kpiKey }] as const,
  progress: (documentId: number) => [...smartDashboardKeys.all, 'progress', documentId] as const,
  batchProgress: (batchId: string) => [...smartDashboardKeys.all, 'batch-progress', batchId] as const,
};

// ============================================================================
// KPI QUERIES (Real-time with short staleTime)
// ============================================================================

export function useKPIs(): UseQueryResult<KPIData[], Error> {
  return useQuery({
    queryKey: smartDashboardKeys.kpis(),
    queryFn: async () => {
      const data = await smartDashboardApi.getKPIs();
      return data.map(transformKPIData);
    },
    staleTime: 30 * 1000, // 30s for real-time feel
    refetchInterval: 30 * 1000, // Auto-refresh every 30s
  });
}

// ============================================================================
// TAB DATA QUERIES
// ============================================================================

export function useTabData(tab: DashboardTabKey, role?: string): UseQueryResult<TabData, Error> {
  return useQuery({
    queryKey: smartDashboardKeys.tab(tab, role),
    queryFn: async () => {
      const data = await smartDashboardApi.getTabData(tab, role);
      return transformTabData(data);
    },
    staleTime: 60 * 1000, // 1 minute
  });
}

// ============================================================================
// WIDGET CONFIG QUERIES
// ============================================================================

export function useWidgets(role?: string): UseQueryResult<WidgetData[], Error> {
  return useQuery({
    queryKey: smartDashboardKeys.widgets(role),
    queryFn: async () => {
      const data = await smartDashboardApi.getWidgets(role);
      return data.map(transformWidgetData);
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// ============================================================================
// LAYOUT MUTATION (with optimistic update)
// ============================================================================

export function useSaveLayout(): UseMutationResult<void, Error, WidgetLayout[], unknown> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (layout: WidgetLayout[]) => {
      await smartDashboardApi.saveLayout(layout);
    },
    onMutate: async (newLayout) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: smartDashboardKeys.all });

      // Snapshot previous value
      const previousLayout = queryClient.getQueryData(smartDashboardKeys.all);

      // Optimistically update
      // (Note: We'd need to update specific tab data if we had layout stored there)

      return { previousLayout };
    },
    onError: (error, variables, context) => {
      // Rollback on error
      if (context?.previousLayout) {
        queryClient.setQueryData(smartDashboardKeys.all, context.previousLayout);
      }
      toast.error('Fehler beim Speichern des Layouts');
      console.error('Layout save failed:', error);
    },
    onSuccess: () => {
      toast.success('Layout erfolgreich gespeichert');
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: smartDashboardKeys.all });
    },
  });
}

// ============================================================================
// TREND DATA QUERIES
// ============================================================================

export function useTrends(kpiKey?: string): UseQueryResult<TrendData[], Error> {
  return useQuery({
    queryKey: smartDashboardKeys.trends(kpiKey),
    queryFn: async () => {
      const data = await smartDashboardApi.getTrends(kpiKey);
      return data.map(transformTrendData);
    },
    staleTime: 60 * 1000, // 1 minute
    enabled: !!kpiKey, // Only fetch if kpiKey is provided
  });
}

// ============================================================================
// PROGRESS QUERIES (with polling for active documents)
// ============================================================================

export function useDocumentProgress(
  documentId: number | null,
  options?: { enabled?: boolean; polling?: boolean }
): UseQueryResult<DocumentProgress, Error> {
  const { enabled = true, polling = false } = options || {};

  return useQuery({
    queryKey: documentId ? smartDashboardKeys.progress(documentId) : ['no-document'],
    queryFn: async () => {
      if (!documentId) throw new Error('No document ID');
      const data = await smartDashboardApi.getDocumentProgress(documentId);
      return transformDocumentProgress(data);
    },
    enabled: enabled && documentId !== null,
    staleTime: polling ? 0 : 60 * 1000,
    refetchInterval: polling ? 5000 : false, // Poll every 5s if active
  });
}

export function useBatchProgress(
  batchId: string | null,
  options?: { enabled?: boolean; polling?: boolean }
): UseQueryResult<BatchProgress, Error> {
  const { enabled = true, polling = false } = options || {};

  return useQuery({
    queryKey: batchId ? smartDashboardKeys.batchProgress(batchId) : ['no-batch'],
    queryFn: async () => {
      if (!batchId) throw new Error('No batch ID');
      const data = await smartDashboardApi.getBatchProgress(batchId);
      return transformBatchProgress(data);
    },
    enabled: enabled && batchId !== null,
    staleTime: polling ? 0 : 60 * 1000,
    refetchInterval: polling ? 5000 : false, // Poll every 5s if active
  });
}

// ============================================================================
// UTILITY HOOKS
// ============================================================================

/**
 * Invalidate all smart dashboard queries (useful for manual refresh)
 */
export function useInvalidateSmartDashboard() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.invalidateQueries({ queryKey: smartDashboardKeys.all });
    toast.success('Dashboard aktualisiert');
  };
}
