/**
 * Workflow Execution Visualization Hooks
 *
 * React Query Hooks für Echtzeit-Ausführungsvisualisierung.
 * Auto-refresh bei laufenden Ausführungen.
 */

import { useQuery } from '@tanstack/react-query';
import * as workflowsApi from '../api/workflows-api';

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
 * Hook für Execution State mit Auto-Refresh bei laufenden Ausführungen.
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
 * Hook für Execution Timeline mit Auto-Refresh bei laufenden Ausführungen.
 */
export function useExecutionTimeline(instanceId: string, enabled = true) {
  return useQuery({
    queryKey: executionVizKeys.timeline(instanceId),
    queryFn: () => workflowsApi.getExecutionTimeline(instanceId),
    enabled: enabled && !!instanceId,
    refetchInterval: (data) => {
      // Auto-refresh alle 3 Sekunden wenn noch Einträge mit Status "running" vorhanden
      const hasRunning = data?.some((entry) => entry.status === 'running');
      return hasRunning ? 3000 : false;
    },
  });
}

/**
 * Hook für Execution Metrics mit Auto-Refresh bei laufenden Ausführungen.
 */
export function useExecutionMetrics(instanceId: string, enabled = true) {
  return useQuery({
    queryKey: executionVizKeys.metrics(instanceId),
    queryFn: () => workflowsApi.getExecutionMetrics(instanceId),
    enabled: enabled && !!instanceId,
    refetchInterval: 5000, // Auto-refresh alle 5 Sekunden
  });
}
