/**
 * Workflow Execution Visualization Hooks
 *
 * React Query Hooks fuer Echtzeit-Ausfuehrungsvisualisierung.
 * Auto-refresh bei laufenden Ausfuehrungen.
 */

import { useQuery } from '@tanstack/react-query';
import * as workflowsApi from '../api/workflows-api';
import type { ExecutionState, TimelineEntry, ExecutionMetrics } from '../types/workflow-types';

// =============================================================================
// Query Keys
// =============================================================================

export const executionVizKeys = {
  state: (id: string) => ['workflow-execution', id, 'state'] as const,
  timeline: (id: string) => ['workflow-execution', id, 'timeline'] as const,
  metrics: (id: string) => ['workflow-execution', id, 'metrics'] as const,
};

// =============================================================================
// Execution Visualization Queries
// =============================================================================

/**
 * Hook fuer Execution State mit Auto-Refresh bei laufenden Ausfuehrungen.
 */
export function useExecutionState(instanceId: string, enabled = true) {
  return useQuery({
    queryKey: executionVizKeys.state(instanceId),
    queryFn: () => workflowsApi.getExecutionState(instanceId),
    enabled: enabled && !!instanceId,
    refetchInterval: (data) => {
      // Auto-refresh alle 2 Sekunden wenn Status "running" ist
      return data?.status === 'running' ? 2000 : false;
    },
  });
}

/**
 * Hook fuer Execution Timeline mit Auto-Refresh bei laufenden Ausfuehrungen.
 */
export function useExecutionTimeline(instanceId: string, enabled = true) {
  return useQuery({
    queryKey: executionVizKeys.timeline(instanceId),
    queryFn: () => workflowsApi.getExecutionTimeline(instanceId),
    enabled: enabled && !!instanceId,
    refetchInterval: (data) => {
      // Auto-refresh alle 3 Sekunden wenn noch Eintraege mit Status "running" vorhanden
      const hasRunning = data?.some((entry) => entry.status === 'running');
      return hasRunning ? 3000 : false;
    },
  });
}

/**
 * Hook fuer Execution Metrics mit Auto-Refresh bei laufenden Ausfuehrungen.
 */
export function useExecutionMetrics(instanceId: string, enabled = true) {
  return useQuery({
    queryKey: executionVizKeys.metrics(instanceId),
    queryFn: () => workflowsApi.getExecutionMetrics(instanceId),
    enabled: enabled && !!instanceId,
    refetchInterval: 5000, // Auto-refresh alle 5 Sekunden
  });
}
