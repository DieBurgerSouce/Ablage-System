/**
 * Process Mining Hooks
 *
 * Hooks für Process Mining Dashboard.
 * Vision 2.0 Phase 3: Process Mining & Autonome Automatisierung
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// Types
// =============================================================================

export type SuggestionStatus = 'pending' | 'activated' | 'rejected';
export type SuggestionType =
  | 'auto_classification'
  | 'auto_routing'
  | 'auto_approval'
  | 'auto_entity_link'
  | 'workflow_optimization';

export type BottleneckType = 'duration' | 'queue' | 'failure' | 'resource';
export type BottleneckSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface Bottleneck {
  type: BottleneckType;
  location: string;
  score: number;
  severity: BottleneckSeverity;
  details: Record<string, unknown>;
  recommendation: string;
}

export interface BottleneckAnalysis {
  bottlenecks: Bottleneck[];
  overall_score: number;
  overall_severity: BottleneckSeverity;
  bottleneck_count: number;
  period_days: number;
}

export interface ProcessHealth {
  health_score: number;
  health_grade: string;
  components: {
    bottleneck_score: number;
    success_rate: number;
    automation_rate: number;
  };
  bottleneck_count: number;
  top_bottleneck: Bottleneck | null;
  period_days: number;
}

export interface AutomationSuggestion {
  id: string;
  suggestion_type: SuggestionType;
  title: string;
  description: string | null;
  pattern_description: string | null;
  confidence: number;
  potential_savings_hours: number | null;
  potential_savings_cost: number | null;
  affected_steps: string[];
  trigger_conditions: Record<string, unknown>;
  suggested_actions: Array<Record<string, unknown>>;
  frequency_per_week: number | null;
  status: SuggestionStatus;
  activated_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  created_at: string | null;
}

export interface SuggestionStats {
  by_status: Record<string, { count: number; savings: number }>;
  total_pending: number;
  total_activated: number;
  realized_savings_hours: number;
  realized_savings_cost: number;
}

export interface HeatmapData {
  data: Array<{
    day: number;
    day_name: string;
    hour: number;
    count: number;
    avg_duration_ms: number;
  }>;
  period_days: number;
}

export interface FlowDiagram {
  nodes: Array<{
    id: string;
    label: string;
    count: number;
    avg_duration_ms: number;
  }>;
  edges: Array<{
    source: string;
    target: string;
    count: number;
    percentage: number;
  }>;
  variants: Array<{
    path: string[];
    count: number;
    percentage: number;
  }>;
  statistics: Record<string, unknown>;
}

export interface MetricsSummary {
  period_days: number;
  total_events: number;
  unique_documents: number;
  success_rate: number;
  automation_rate: number;
  avg_duration_ms: number;
  manual_events: number;
  automated_events: number;
}

// =============================================================================
// Query Keys
// =============================================================================

export const processMiningKeys = {
  all: ['process-mining'] as const,
  health: (days: number) => [...processMiningKeys.all, 'health', days] as const,
  bottlenecks: (days: number) => [...processMiningKeys.all, 'bottlenecks', days] as const,
  heatmap: (days: number) => [...processMiningKeys.all, 'heatmap', days] as const,
  suggestions: (status?: SuggestionStatus) => [...processMiningKeys.all, 'suggestions', status] as const,
  suggestionStats: () => [...processMiningKeys.all, 'suggestion-stats'] as const,
  flowDiagram: (days: number) => [...processMiningKeys.all, 'flow-diagram', days] as const,
  metricsSummary: (days: number) => [...processMiningKeys.all, 'metrics-summary', days] as const,
  variants: (days: number) => [...processMiningKeys.all, 'variants', days] as const,
};

// =============================================================================
// Hooks
// =============================================================================

/**
 * Hook zum Abrufen der Prozessgesundheit
 */
export function useProcessHealth(days = 30) {
  return useQuery({
    queryKey: processMiningKeys.health(days),
    queryFn: async () => {
      const response = await api.get<ProcessHealth>(`/process-mining/health?days=${days}`);
      return response.data;
    },
    staleTime: 60_000, // 1 Minute
  });
}

/**
 * Hook zum Abrufen der Bottleneck-Analyse
 */
export function useBottlenecks(days = 30) {
  return useQuery({
    queryKey: processMiningKeys.bottlenecks(days),
    queryFn: async () => {
      const response = await api.get<BottleneckAnalysis>(`/process-mining/bottlenecks?days=${days}`);
      return response.data;
    },
    staleTime: 60_000,
  });
}

/**
 * Hook zum Abrufen der Heatmap-Daten
 */
export function useBottleneckHeatmap(days = 7) {
  return useQuery({
    queryKey: processMiningKeys.heatmap(days),
    queryFn: async () => {
      const response = await api.get<HeatmapData>(`/process-mining/bottlenecks/heatmap?days=${days}`);
      return response.data;
    },
    staleTime: 300_000, // 5 Minuten
  });
}

/**
 * Hook zum Abrufen der Automatisierungsvorschläge
 */
export function useAutomationSuggestions(status?: SuggestionStatus, limit = 20) {
  return useQuery({
    queryKey: processMiningKeys.suggestions(status),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      params.set('limit', String(limit));

      const response = await api.get<{ items: AutomationSuggestion[]; total: number }>(
        `/process-mining/suggestions?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 30_000,
  });
}

/**
 * Hook zum Abrufen der Vorschlags-Statistiken
 */
export function useSuggestionStats() {
  return useQuery({
    queryKey: processMiningKeys.suggestionStats(),
    queryFn: async () => {
      const response = await api.get<SuggestionStats>('/process-mining/suggestions/statistics');
      return response.data;
    },
    staleTime: 60_000,
  });
}

/**
 * Hook zum Abrufen des Prozessfluss-Diagramms
 */
export function useFlowDiagram(days = 30, minFrequency = 5) {
  return useQuery({
    queryKey: processMiningKeys.flowDiagram(days),
    queryFn: async () => {
      const response = await api.get<FlowDiagram>(
        `/process-mining/flow-diagram?days=${days}&min_frequency=${minFrequency}`
      );
      return response.data;
    },
    staleTime: 300_000,
  });
}

/**
 * Hook zum Abrufen der Metriken-Zusammenfassung
 */
export function useMetricsSummary(days = 30) {
  return useQuery({
    queryKey: processMiningKeys.metricsSummary(days),
    queryFn: async () => {
      const response = await api.get<MetricsSummary>(`/process-mining/metrics/summary?days=${days}`);
      return response.data;
    },
    staleTime: 60_000,
  });
}

/**
 * Hook zum Abrufen der Prozessvarianten
 */
export function useProcessVariants(days = 30, limit = 10) {
  return useQuery({
    queryKey: processMiningKeys.variants(days),
    queryFn: async () => {
      const response = await api.get<Array<{
        path: string[];
        count: number;
        percentage: number;
        avg_duration_ms: number;
      }>>(`/process-mining/variants?days=${days}&limit=${limit}`);
      return response.data;
    },
    staleTime: 300_000,
  });
}

/**
 * Hook zum Generieren neuer Vorschläge
 */
export function useGenerateSuggestions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ days = 30, save = true }: { days?: number; save?: boolean }) => {
      const response = await api.post<{ items: AutomationSuggestion[]; total: number }>(
        `/process-mining/suggestions/generate?days=${days}&save=${save}`
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: processMiningKeys.suggestions() });
      queryClient.invalidateQueries({ queryKey: processMiningKeys.suggestionStats() });
    },
  });
}

/**
 * Hook zum Aktivieren eines Vorschlags
 */
export function useActivateSuggestion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ suggestionId }: { suggestionId: string }) => {
      const response = await api.post<AutomationSuggestion>(
        `/process-mining/suggestions/${suggestionId}/activate`,
        {}
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: processMiningKeys.suggestions() });
      queryClient.invalidateQueries({ queryKey: processMiningKeys.suggestionStats() });
    },
  });
}

/**
 * Hook zum Ablehnen eines Vorschlags
 */
export function useRejectSuggestion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ suggestionId, reason }: { suggestionId: string; reason?: string }) => {
      const response = await api.post<AutomationSuggestion>(
        `/process-mining/suggestions/${suggestionId}/reject`,
        { reason }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: processMiningKeys.suggestions() });
      queryClient.invalidateQueries({ queryKey: processMiningKeys.suggestionStats() });
    },
  });
}
