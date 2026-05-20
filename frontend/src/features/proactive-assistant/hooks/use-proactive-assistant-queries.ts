// Proactive Assistant Query Hooks

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { proactiveAssistantApi } from '../api/proactive-assistant-api';
import {
  transformDashboardSummary,
  transformHintList,
  transformHint,
  transformStatistics,
  transformHintRule,
  UI_LABELS,
  type DashboardSummary,
  type HintList,
  type Hint,
  type Statistics,
  type HintRule,
  type HintStatus,
  type HintCategory,
  type HintPriority,
} from '../types/proactive-assistant-types';

// ============================================================================
// Query Key Factory
// ============================================================================

export const proactiveAssistantKeys = {
  all: ['proactive-assistant'] as const,
  dashboard: () => [...proactiveAssistantKeys.all, 'dashboard'] as const,
  hints: (filters?: {
    category?: HintCategory;
    priority?: HintPriority;
    status?: HintStatus;
    limit?: number;
    offset?: number;
  }) => [...proactiveAssistantKeys.all, 'hints', filters] as const,
  statistics: () => [...proactiveAssistantKeys.all, 'statistics'] as const,
  rules: () => [...proactiveAssistantKeys.all, 'rules'] as const,
  context: (entityType: string, entityId: string) =>
    [...proactiveAssistantKeys.all, 'context', entityType, entityId] as const,
};

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Get dashboard summary
 */
export function useDashboardQuery() {
  return useQuery<DashboardSummary>({
    queryKey: proactiveAssistantKeys.dashboard(),
    queryFn: async () => {
      const response = await proactiveAssistantApi.getDashboard();
      return transformDashboardSummary(response);
    },
    staleTime: 2 * 60 * 1000, // 2 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Get filtered hints with pagination
 */
export function useHintsQuery(filters?: {
  category?: HintCategory;
  priority?: HintPriority;
  status?: HintStatus;
  limit?: number;
  offset?: number;
}) {
  return useQuery<HintList>({
    queryKey: proactiveAssistantKeys.hints(filters),
    queryFn: async () => {
      const response = await proactiveAssistantApi.getHints(filters);
      return transformHintList(response);
    },
    staleTime: 2 * 60 * 1000, // 2 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Get context hints for entity
 */
export function useContextHintsQuery(
  entityType: string,
  entityId: string,
  enabled = true
) {
  return useQuery<Hint[]>({
    queryKey: proactiveAssistantKeys.context(entityType, entityId),
    queryFn: async () => {
      const response = await proactiveAssistantApi.getContextHints({
        entity_type: entityType,
        entity_id: entityId,
      });
      return response.map(transformHint);
    },
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Get statistics
 */
export function useStatisticsQuery() {
  return useQuery<Statistics>({
    queryKey: proactiveAssistantKeys.statistics(),
    queryFn: async () => {
      const response = await proactiveAssistantApi.getStatistics();
      return transformStatistics(response);
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Get hint rules
 */
export function useRulesQuery() {
  return useQuery<HintRule[]>({
    queryKey: proactiveAssistantKeys.rules(),
    queryFn: async () => {
      const response = await proactiveAssistantApi.getRules();
      return response.map(transformHintRule);
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 30 * 60 * 1000, // 30 minutes
  });
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Update hint status
 */
export function useUpdateHintStatusMutation() {
  const queryClient = useQueryClient();

  return useMutation<Hint, Error, { hintId: string; status: HintStatus }>({
    mutationFn: async ({ hintId, status }) => {
      const response = await proactiveAssistantApi.updateHintStatus(
        hintId,
        status
      );
      return transformHint(response);
    },
    onSuccess: () => {
      // Invalidate all hint-related queries
      queryClient.invalidateQueries({
        queryKey: proactiveAssistantKeys.all,
      });
      toast.success(UI_LABELS.messages.statusUpdated);
    },
    onError: () => {
      toast.error(UI_LABELS.messages.errorUpdatingStatus);
    },
  });
}

/**
 * Generate new hints
 */
export function useGenerateHintsMutation() {
  const queryClient = useQueryClient();

  return useMutation<{ message: string; hints_generated: number }, Error>({
    mutationFn: async () => {
      return await proactiveAssistantApi.generateHints();
    },
    onSuccess: (data) => {
      // Invalidate all queries to refresh data
      queryClient.invalidateQueries({
        queryKey: proactiveAssistantKeys.all,
      });
      toast.success(`${UI_LABELS.messages.hintsGenerated} (${data.hints_generated})`);
    },
    onError: () => {
      toast.error(UI_LABELS.messages.errorGeneratingHints);
    },
  });
}

/**
 * Update hint rule
 */
export function useUpdateRuleMutation() {
  const queryClient = useQueryClient();

  return useMutation<
    HintRule,
    Error,
    {
      ruleId: string;
      data: {
        name?: string;
        enabled?: boolean;
        conditions?: Record<string, unknown>;
        template?: string;
        priority?: HintPriority;
      };
    }
  >({
    mutationFn: async ({ ruleId, data }) => {
      const response = await proactiveAssistantApi.updateRule(ruleId, data);
      return transformHintRule(response);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: proactiveAssistantKeys.rules(),
      });
      toast.success('Regel erfolgreich aktualisiert');
    },
    onError: () => {
      toast.error('Fehler beim Aktualisieren der Regel');
    },
  });
}

// ============================================================================
// Combined Hooks
// ============================================================================

/**
 * Combined dashboard hook - loads dashboard + recent hints
 */
export function useDashboardData() {
  const dashboardQuery = useDashboardQuery();
  const hintsQuery = useHintsQuery({
    status: 'new',
    limit: 10,
  });

  return {
    dashboard: dashboardQuery.data,
    hints: hintsQuery.data?.hints || [],
    isLoading: dashboardQuery.isLoading || hintsQuery.isLoading,
    error: dashboardQuery.error || hintsQuery.error,
    refetch: () => {
      dashboardQuery.refetch();
      hintsQuery.refetch();
    },
  };
}
