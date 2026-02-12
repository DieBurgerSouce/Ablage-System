/**
 * Workflow React Query Hooks
 *
 * React Query Hooks für Workflow-Automation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import * as workflowsApi from '../api/workflows-api';
import type {
  Workflow,
  WorkflowCreate,
  WorkflowUpdate,
  WorkflowListParams,
  WorkflowStep,
  StepCreate,
  StepUpdate,
  StepReorderItem,
  WorkflowExecution,
  ExecutionListParams,
  ExecutionStart,
} from '../types/workflow-types';

// =============================================================================
// Query Keys
// =============================================================================

export const workflowKeys = {
  all: ['workflows'] as const,
  lists: () => [...workflowKeys.all, 'list'] as const,
  list: (params: WorkflowListParams) =>
    [...workflowKeys.lists(), params] as const,
  details: () => [...workflowKeys.all, 'detail'] as const,
  detail: (id: string) => [...workflowKeys.details(), id] as const,
  steps: (workflowId: string) =>
    [...workflowKeys.detail(workflowId), 'steps'] as const,
  executions: (workflowId: string) =>
    [...workflowKeys.detail(workflowId), 'executions'] as const,
  execution: (executionId: string) =>
    [...workflowKeys.all, 'execution', executionId] as const,
  stepExecutions: (executionId: string) =>
    [...workflowKeys.execution(executionId), 'steps'] as const,
  stats: (workflowId: string) =>
    [...workflowKeys.detail(workflowId), 'stats'] as const,
  overviewStats: () => [...workflowKeys.all, 'overview-stats'] as const,
  executionHistory: (days: number) =>
    [...workflowKeys.all, 'history', days] as const,
  templates: () => [...workflowKeys.all, 'templates'] as const,
  operators: () => [...workflowKeys.all, 'operators'] as const,
  fields: () => [...workflowKeys.all, 'fields'] as const,
  webhookConfig: (workflowId: string) =>
    [...workflowKeys.detail(workflowId), 'webhook'] as const,
};

// =============================================================================
// Workflow Queries
// =============================================================================

/**
 * Hook für Workflow-Liste.
 */
export function useWorkflows(params: WorkflowListParams = {}) {
  return useQuery({
    queryKey: workflowKeys.list(params),
    queryFn: () => workflowsApi.listWorkflows(params),
  });
}

/**
 * Hook für einzelnen Workflow.
 */
export function useWorkflow(workflowId: string, enabled = true) {
  return useQuery({
    queryKey: workflowKeys.detail(workflowId),
    queryFn: () => workflowsApi.getWorkflow(workflowId),
    enabled: enabled && !!workflowId,
  });
}

/**
 * Hook für Workflow-Steps.
 */
export function useWorkflowSteps(workflowId: string, enabled = true) {
  return useQuery({
    queryKey: workflowKeys.steps(workflowId),
    queryFn: () => workflowsApi.getWorkflowSteps(workflowId),
    enabled: enabled && !!workflowId,
  });
}

/**
 * Hook für Workflow-Statistiken.
 */
export function useWorkflowStats(workflowId: string, enabled = true) {
  return useQuery({
    queryKey: workflowKeys.stats(workflowId),
    queryFn: () => workflowsApi.getWorkflowStats(workflowId),
    enabled: enabled && !!workflowId,
  });
}

/**
 * Hook für Gesamt-Statistiken.
 */
export function useOverviewStats() {
  return useQuery({
    queryKey: workflowKeys.overviewStats(),
    queryFn: () => workflowsApi.getOverviewStats(),
  });
}

/**
 * Hook für Ausführungs-Historie.
 */
export function useExecutionHistory(days = 30) {
  return useQuery({
    queryKey: workflowKeys.executionHistory(days),
    queryFn: () => workflowsApi.getExecutionHistory(days),
  });
}

/**
 * Hook für Templates.
 */
export function useTemplates(category?: string) {
  return useQuery({
    queryKey: workflowKeys.templates(),
    queryFn: () => workflowsApi.listTemplates(category),
  });
}

/**
 * Hook für verfügbare Operatoren.
 */
export function useOperators() {
  return useQuery({
    queryKey: workflowKeys.operators(),
    queryFn: () => workflowsApi.getAvailableOperators(),
    staleTime: Infinity, // Operatoren ändern sich nicht
  });
}

/**
 * Hook für verfügbare Felder.
 */
export function useFields() {
  return useQuery({
    queryKey: workflowKeys.fields(),
    queryFn: () => workflowsApi.getAvailableFields(),
    staleTime: Infinity, // Felder ändern sich nicht
  });
}

/**
 * Hook für Webhook-Konfiguration.
 */
export function useWebhookConfig(workflowId: string, enabled = true) {
  return useQuery({
    queryKey: workflowKeys.webhookConfig(workflowId),
    queryFn: () => workflowsApi.getWebhookConfig(workflowId),
    enabled: enabled && !!workflowId,
  });
}

// =============================================================================
// Workflow Mutations
// =============================================================================

/**
 * Hook für Workflow-Erstellung.
 */
export function useCreateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: WorkflowCreate) => workflowsApi.createWorkflow(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      toast.success('Workflow erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Hook für Workflow-Update.
 */
export function useUpdateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      data,
    }: {
      workflowId: string;
      data: WorkflowUpdate;
    }) => workflowsApi.updateWorkflow(workflowId, data),
    onSuccess: (workflow) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.detail(workflow.id),
      });
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      toast.success('Workflow erfolgreich aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook für Workflow-Löschung.
 */
export function useDeleteWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workflowId: string) => workflowsApi.deleteWorkflow(workflowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      toast.success('Workflow erfolgreich gelöscht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Löschen: ${error.message}`);
    },
  });
}

/**
 * Hook für Workflow-Duplizierung.
 */
export function useDuplicateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      newName,
    }: {
      workflowId: string;
      newName?: string;
    }) => workflowsApi.duplicateWorkflow(workflowId, newName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      toast.success('Workflow erfolgreich dupliziert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Duplizieren: ${error.message}`);
    },
  });
}

/**
 * Hook für Workflow-Toggle.
 */
export function useToggleWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workflowId: string) => workflowsApi.toggleWorkflow(workflowId),
    onSuccess: (workflow) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.detail(workflow.id),
      });
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      toast.success(
        workflow.is_active
          ? 'Workflow aktiviert'
          : 'Workflow deaktiviert'
      );
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Umschalten: ${error.message}`);
    },
  });
}

/**
 * Hook für Workflow-Validierung.
 */
export function useValidateWorkflow() {
  return useMutation({
    mutationFn: (workflowId: string) =>
      workflowsApi.validateWorkflow(workflowId),
  });
}

// =============================================================================
// Step Mutations
// =============================================================================

/**
 * Hook für Step-Erstellung.
 */
export function useCreateStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      data,
    }: {
      workflowId: string;
      data: StepCreate;
    }) => workflowsApi.createStep(workflowId, data),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.steps(workflowId),
      });
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Hook für Step-Update.
 */
export function useUpdateStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      stepId,
      data,
    }: {
      workflowId: string;
      stepId: string;
      data: StepUpdate;
    }) => workflowsApi.updateStep(workflowId, stepId, data),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.steps(workflowId),
      });
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook für Step-Löschung.
 */
export function useDeleteStep() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      stepId,
    }: {
      workflowId: string;
      stepId: string;
    }) => workflowsApi.deleteStep(workflowId, stepId),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.steps(workflowId),
      });
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Löschen: ${error.message}`);
    },
  });
}

/**
 * Hook für Step-Neuordnung.
 */
export function useReorderSteps() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      stepOrders,
    }: {
      workflowId: string;
      stepOrders: StepReorderItem[];
    }) => workflowsApi.reorderSteps(workflowId, stepOrders),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.steps(workflowId),
      });
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Neuordnen: ${error.message}`);
    },
  });
}

/**
 * Hook für Batch Step-Update.
 */
export function useBatchUpdateSteps() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      stepsData,
    }: {
      workflowId: string;
      stepsData: Record<string, unknown>[];
    }) => workflowsApi.batchUpdateSteps(workflowId, stepsData),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.steps(workflowId),
      });
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Batch-Update: ${error.message}`);
    },
  });
}

// =============================================================================
// Execution Queries & Mutations
// =============================================================================

/**
 * Hook für Workflow-Ausführungen.
 */
export function useWorkflowExecutions(
  workflowId: string,
  params: ExecutionListParams = {},
  enabled = true
) {
  return useQuery({
    queryKey: workflowKeys.executions(workflowId),
    queryFn: () => workflowsApi.getWorkflowExecutions(workflowId, params),
    enabled: enabled && !!workflowId,
  });
}

/**
 * Hook für einzelne Ausführung.
 */
export function useExecution(executionId: string, enabled = true) {
  return useQuery({
    queryKey: workflowKeys.execution(executionId),
    queryFn: () => workflowsApi.getExecution(executionId),
    enabled: enabled && !!executionId,
    refetchInterval: (data) =>
      data?.status === 'running' ? 2000 : false, // Auto-refresh bei laufender Execution
  });
}

/**
 * Hook für Step-Ausführungen.
 */
export function useStepExecutions(executionId: string, enabled = true) {
  return useQuery({
    queryKey: workflowKeys.stepExecutions(executionId),
    queryFn: () => workflowsApi.getStepExecutions(executionId),
    enabled: enabled && !!executionId,
  });
}

/**
 * Hook für Workflow-Ausführung.
 */
export function useExecuteWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      data,
    }: {
      workflowId: string;
      data?: ExecutionStart;
    }) => workflowsApi.executeWorkflow(workflowId, data),
    onSuccess: (_, { workflowId }) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.executions(workflowId),
      });
      queryClient.invalidateQueries({
        queryKey: workflowKeys.overviewStats(),
      });
      toast.success('Workflow gestartet');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Starten: ${error.message}`);
    },
  });
}

/**
 * Hook für Execution-Pause.
 */
export function usePauseExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (executionId: string) =>
      workflowsApi.pauseExecution(executionId),
    onSuccess: (_, executionId) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.execution(executionId),
      });
      toast.success('Ausführung pausiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Pausieren: ${error.message}`);
    },
  });
}

/**
 * Hook für Execution-Resume.
 */
export function useResumeExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (executionId: string) =>
      workflowsApi.resumeExecution(executionId),
    onSuccess: (_, executionId) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.execution(executionId),
      });
      toast.success('Ausführung fortgesetzt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Fortsetzen: ${error.message}`);
    },
  });
}

/**
 * Hook für Execution-Cancel.
 */
export function useCancelExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (executionId: string) =>
      workflowsApi.cancelExecution(executionId),
    onSuccess: (_, executionId) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.execution(executionId),
      });
      toast.success('Ausführung abgebrochen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Abbrechen: ${error.message}`);
    },
  });
}

/**
 * Hook für Execution-Retry.
 */
export function useRetryExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (executionId: string) =>
      workflowsApi.retryExecution(executionId),
    onSuccess: (execution) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.executions(execution.workflow_id),
      });
      toast.success('Ausführung wird wiederholt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Wiederholen: ${error.message}`);
    },
  });
}

// =============================================================================
// Template Mutations
// =============================================================================

/**
 * Hook für Template-Instanziierung.
 */
export function useInstantiateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      templateId,
      name,
      companyId,
    }: {
      templateId: string;
      name?: string;
      companyId?: string;
    }) => workflowsApi.instantiateTemplate(templateId, name, companyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      toast.success('Workflow aus Template erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

// =============================================================================
// Webhook Mutations
// =============================================================================

/**
 * Hook für Webhook-Secret-Regenerierung.
 */
export function useRegenerateWebhookSecret() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workflowId: string) =>
      workflowsApi.regenerateWebhookSecret(workflowId),
    onSuccess: (_, workflowId) => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.webhookConfig(workflowId),
      });
      toast.success('Webhook-Secret regeneriert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Regenerieren: ${error.message}`);
    },
  });
}
