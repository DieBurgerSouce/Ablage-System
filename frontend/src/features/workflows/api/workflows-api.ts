/**
 * Workflow API Client
 *
 * TypeScript API Client für Workflow-Automation.
 */

import { apiClient } from '@/lib/api/client';
import type { Workflow, WorkflowCreate, WorkflowUpdate, WorkflowListResponse, WorkflowListParams, WorkflowStep, StepCreate, StepUpdate, StepReorderItem, WorkflowExecution, ExecutionListResponse, ExecutionListParams, ExecutionStart, StepExecution, WorkflowValidationResponse, WorkflowValidationStatusResponse, WorkflowStats, OverviewStats, ExecutionHistoryItem, WebhookConfig, OperatorInfo } from '../types/workflow-types';

const BASE_URL = '/workflows';

// =============================================================================
// Workflow CRUD
// =============================================================================

/**
 * Erstellt einen neuen Workflow.
 */
export async function createWorkflow(data: WorkflowCreate): Promise<Workflow> {
  const response = await apiClient.post<Workflow>(BASE_URL, data);
  return response.data;
}

/**
 * Listet Workflows mit Filtern.
 */
export async function listWorkflows(
  params: WorkflowListParams = {}
): Promise<WorkflowListResponse> {
  const response = await apiClient.get<WorkflowListResponse>(BASE_URL, {
    params,
  });
  return response.data;
}

/**
 * Ruft einen Workflow nach ID ab.
 */
export async function getWorkflow(workflowId: string): Promise<Workflow> {
  const response = await apiClient.get<Workflow>(`${BASE_URL}/${workflowId}`);
  return response.data;
}

/**
 * Aktualisiert einen Workflow.
 */
export async function updateWorkflow(
  workflowId: string,
  data: WorkflowUpdate
): Promise<Workflow> {
  const response = await apiClient.put<Workflow>(
    `${BASE_URL}/${workflowId}`,
    data
  );
  return response.data;
}

/**
 * Löscht einen Workflow.
 */
export async function deleteWorkflow(workflowId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/${workflowId}`);
}

/**
 * Dupliziert einen Workflow.
 */
export async function duplicateWorkflow(
  workflowId: string,
  newName?: string
): Promise<Workflow> {
  const response = await apiClient.post<Workflow>(
    `${BASE_URL}/${workflowId}/duplicate`,
    null,
    { params: { new_name: newName } }
  );
  return response.data;
}

/**
 * Aktiviert/Deaktiviert einen Workflow.
 */
export async function toggleWorkflow(workflowId: string): Promise<Workflow> {
  const response = await apiClient.patch<Workflow>(
    `${BASE_URL}/${workflowId}/toggle`
  );
  return response.data;
}

/**
 * Validiert einen Workflow (Full Validation mit Cycle Detection).
 */
export async function validateWorkflow(
  workflowId: string
): Promise<WorkflowValidationResponse> {
  const response = await apiClient.post<WorkflowValidationResponse>(
    `${BASE_URL}/${workflowId}/validate`
  );
  return response.data;
}

/**
 * Ruft den Validierungs-Status eines Workflows ab (Lightweight).
 */
export async function getValidationStatus(
  workflowId: string
): Promise<WorkflowValidationStatusResponse> {
  const response = await apiClient.get<WorkflowValidationStatusResponse>(
    `${BASE_URL}/${workflowId}/validation-status`
  );
  return response.data;
}

// =============================================================================
// Workflow Steps
// =============================================================================

/**
 * Ruft alle Steps eines Workflows ab.
 */
export async function getWorkflowSteps(
  workflowId: string
): Promise<WorkflowStep[]> {
  const response = await apiClient.get<WorkflowStep[]>(
    `${BASE_URL}/${workflowId}/steps`
  );
  return response.data;
}

/**
 * Erstellt einen neuen Step.
 */
export async function createStep(
  workflowId: string,
  data: StepCreate
): Promise<WorkflowStep> {
  const response = await apiClient.post<WorkflowStep>(
    `${BASE_URL}/${workflowId}/steps`,
    data
  );
  return response.data;
}

/**
 * Aktualisiert einen Step.
 */
export async function updateStep(
  workflowId: string,
  stepId: string,
  data: StepUpdate
): Promise<WorkflowStep> {
  const response = await apiClient.put<WorkflowStep>(
    `${BASE_URL}/${workflowId}/steps/${stepId}`,
    data
  );
  return response.data;
}

/**
 * Löscht einen Step.
 */
export async function deleteStep(
  workflowId: string,
  stepId: string
): Promise<void> {
  await apiClient.delete(`${BASE_URL}/${workflowId}/steps/${stepId}`);
}

/**
 * Ordnet Steps neu an.
 */
export async function reorderSteps(
  workflowId: string,
  stepOrders: StepReorderItem[]
): Promise<WorkflowStep[]> {
  const response = await apiClient.post<WorkflowStep[]>(
    `${BASE_URL}/${workflowId}/steps/reorder`,
    stepOrders
  );
  return response.data;
}

/**
 * Aktualisiert mehrere Steps (Batch).
 */
export async function batchUpdateSteps(
  workflowId: string,
  stepsData: Record<string, unknown>[]
): Promise<WorkflowStep[]> {
  const response = await apiClient.post<WorkflowStep[]>(
    `${BASE_URL}/${workflowId}/steps/batch`,
    stepsData
  );
  return response.data;
}

// =============================================================================
// Workflow Execution
// =============================================================================

/**
 * Startet eine Workflow-Ausführung.
 */
export async function executeWorkflow(
  workflowId: string,
  data: ExecutionStart = {}
): Promise<WorkflowExecution> {
  const response = await apiClient.post<WorkflowExecution>(
    `${BASE_URL}/${workflowId}/execute`,
    data
  );
  return response.data;
}

/**
 * Ruft Ausführungen eines Workflows ab.
 */
export async function getWorkflowExecutions(
  workflowId: string,
  params: ExecutionListParams = {}
): Promise<ExecutionListResponse> {
  const response = await apiClient.get<ExecutionListResponse>(
    `${BASE_URL}/${workflowId}/executions`,
    { params }
  );
  return response.data;
}

/**
 * Ruft eine Ausführung nach ID ab.
 */
export async function getExecution(
  executionId: string
): Promise<WorkflowExecution> {
  const response = await apiClient.get<WorkflowExecution>(
    `${BASE_URL}/executions/${executionId}`
  );
  return response.data;
}

/**
 * Ruft Step-Ausführungen ab.
 */
export async function getStepExecutions(
  executionId: string
): Promise<StepExecution[]> {
  const response = await apiClient.get<StepExecution[]>(
    `${BASE_URL}/executions/${executionId}/steps`
  );
  return response.data;
}

/**
 * Pausiert eine Ausführung.
 */
export async function pauseExecution(
  executionId: string
): Promise<{ paused: boolean }> {
  const response = await apiClient.post<{ paused: boolean }>(
    `${BASE_URL}/executions/${executionId}/pause`
  );
  return response.data;
}

/**
 * Setzt eine Ausführung fort.
 */
export async function resumeExecution(
  executionId: string
): Promise<{ resumed: boolean }> {
  const response = await apiClient.post<{ resumed: boolean }>(
    `${BASE_URL}/executions/${executionId}/resume`
  );
  return response.data;
}

/**
 * Bricht eine Ausführung ab.
 */
export async function cancelExecution(
  executionId: string
): Promise<{ cancelled: boolean }> {
  const response = await apiClient.post<{ cancelled: boolean }>(
    `${BASE_URL}/executions/${executionId}/cancel`
  );
  return response.data;
}

/**
 * Wiederholt eine fehlgeschlagene Ausführung.
 */
export async function retryExecution(
  executionId: string
): Promise<WorkflowExecution> {
  const response = await apiClient.post<WorkflowExecution>(
    `${BASE_URL}/executions/${executionId}/retry`
  );
  return response.data;
}

// =============================================================================
// Templates
// =============================================================================

/**
 * Listet verfügbare Templates.
 */
export async function listTemplates(category?: string): Promise<Workflow[]> {
  const response = await apiClient.get<Workflow[]>(`${BASE_URL}/templates`, {
    params: { category },
  });
  return response.data;
}

/**
 * Ruft ein Template nach ID ab.
 */
export async function getTemplate(templateId: string): Promise<Workflow> {
  const response = await apiClient.get<Workflow>(
    `${BASE_URL}/templates/${templateId}`
  );
  return response.data;
}

/**
 * Erstellt einen Workflow aus einem Template.
 */
export async function instantiateTemplate(
  templateId: string,
  name?: string,
  companyId?: string
): Promise<Workflow> {
  const response = await apiClient.post<Workflow>(
    `${BASE_URL}/templates/${templateId}/instantiate`,
    { name, company_id: companyId }
  );
  return response.data;
}

/**
 * Erstellt ein neues Template (Admin).
 */
export async function createTemplate(data: WorkflowCreate): Promise<Workflow> {
  const response = await apiClient.post<Workflow>(
    `${BASE_URL}/templates`,
    data
  );
  return response.data;
}

// =============================================================================
// Webhook
// =============================================================================

/**
 * Ruft die Webhook-Konfiguration ab.
 */
export async function getWebhookConfig(
  workflowId: string
): Promise<WebhookConfig> {
  const response = await apiClient.get<WebhookConfig>(
    `${BASE_URL}/${workflowId}/webhook-config`
  );
  return response.data;
}

/**
 * Generiert ein neues Webhook-Secret.
 */
export async function regenerateWebhookSecret(
  workflowId: string
): Promise<{ secret: string }> {
  const response = await apiClient.post<{ secret: string }>(
    `${BASE_URL}/${workflowId}/regenerate-webhook-secret`
  );
  return response.data;
}

// =============================================================================
// Statistics
// =============================================================================

/**
 * Ruft Workflow-Statistiken ab.
 */
export async function getWorkflowStats(
  workflowId: string
): Promise<WorkflowStats> {
  const response = await apiClient.get<WorkflowStats>(
    `${BASE_URL}/${workflowId}/stats`
  );
  return response.data;
}

/**
 * Ruft Gesamt-Statistiken ab.
 */
export async function getOverviewStats(): Promise<OverviewStats> {
  const response = await apiClient.get<OverviewStats>(
    `${BASE_URL}/stats/overview`
  );
  return response.data;
}

/**
 * Ruft Ausführungs-Historie ab.
 */
export async function getExecutionHistory(
  days: number = 30
): Promise<ExecutionHistoryItem[]> {
  const response = await apiClient.get<ExecutionHistoryItem[]>(
    `${BASE_URL}/stats/execution-history`,
    { params: { days } }
  );
  return response.data;
}

// =============================================================================
// Utility
// =============================================================================

/**
 * Ruft verfügbare Operatoren ab.
 */
export async function getAvailableOperators(): Promise<OperatorInfo[]> {
  const response = await apiClient.get<OperatorInfo[]>(`${BASE_URL}/operators`);
  return response.data;
}

/**
 * Ruft verfügbare Felder ab.
 */
export async function getAvailableFields(): Promise<Record<string, string>> {
  const response = await apiClient.get<Record<string, string>>(
    `${BASE_URL}/fields`
  );
  return response.data;
}

// =============================================================================
// Execution Visualization (Phase B)
// =============================================================================

/**
 * Ruft den aktuellen Ausführungs-Status ab.
 */
export async function getExecutionState(instanceId: string): Promise<import('../types/workflow-types').ExecutionState> {
  const response = await apiClient.get<import('../types/workflow-types').ExecutionState>(
    `${BASE_URL}/executions/${instanceId}/state`
  );
  return response.data;
}

/**
 * Ruft die Ausführungs-Timeline ab.
 */
export async function getExecutionTimeline(instanceId: string): Promise<import('../types/workflow-types').TimelineEntry[]> {
  const response = await apiClient.get<import('../types/workflow-types').TimelineEntry[]>(
    `${BASE_URL}/executions/${instanceId}/timeline`
  );
  return response.data;
}

/**
 * Ruft die Ausführungs-Metriken ab.
 */
export async function getExecutionMetrics(instanceId: string): Promise<import('../types/workflow-types').ExecutionMetrics> {
  const response = await apiClient.get<import('../types/workflow-types').ExecutionMetrics>(
    `${BASE_URL}/executions/${instanceId}/metrics`
  );
  return response.data;
}
