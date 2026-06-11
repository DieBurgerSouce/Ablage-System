/**
 * BPMN Process Engine API
 *
 * API client for BPMN 2.0 Process Engine endpoints.
 */

import { api } from '@/lib/api';
import type { ProcessDefinition, ProcessDefinitionCreate, ProcessDefinitionListParams, ProcessInstance, ProcessInstanceCreate, ProcessInstanceListParams, ProcessTask, TaskComplete, TaskClaim, TaskDelegate, TaskListParams, ProcessHistory, ProcessTimer, DefinitionStatistics, TaskStatistics, TimerStatistics } from '../types/bpmn-types';

const BASE_URL = '/bpmn';

// =============================================================================
// Process Definitions
// =============================================================================

export async function getDefinitions(
  params?: ProcessDefinitionListParams
): Promise<ProcessDefinition[]> {
  const response = await api.get<ProcessDefinition[]>(`${BASE_URL}/definitions`, {
    params,
  });
  return response.data;
}

export async function getDefinition(id: string): Promise<ProcessDefinition> {
  const response = await api.get<ProcessDefinition>(`${BASE_URL}/definitions/${id}`);
  return response.data;
}

export async function getDefinitionByKey(key: string): Promise<ProcessDefinition> {
  const response = await api.get<ProcessDefinition>(`${BASE_URL}/definitions/key/${key}`);
  return response.data;
}

export async function createDefinition(
  data: ProcessDefinitionCreate
): Promise<ProcessDefinition> {
  const response = await api.post<ProcessDefinition>(`${BASE_URL}/definitions`, data);
  return response.data;
}

export async function deployDefinition(
  data: ProcessDefinitionCreate
): Promise<ProcessDefinition> {
  const response = await api.post<ProcessDefinition>(`${BASE_URL}/definitions/deploy`, data);
  return response.data;
}

export async function activateDefinition(id: string): Promise<ProcessDefinition> {
  const response = await api.post<ProcessDefinition>(`${BASE_URL}/definitions/${id}/activate`);
  return response.data;
}

export async function deactivateDefinition(id: string): Promise<ProcessDefinition> {
  const response = await api.post<ProcessDefinition>(`${BASE_URL}/definitions/${id}/deactivate`);
  return response.data;
}

export async function exportDefinitionBpmn(id: string): Promise<string> {
  const response = await api.get<{ bpmn_xml: string }>(`${BASE_URL}/definitions/${id}/export`);
  return response.data.bpmn_xml;
}

export async function getDefinitionStatistics(): Promise<DefinitionStatistics> {
  const response = await api.get<DefinitionStatistics>(`${BASE_URL}/definitions/statistics`);
  return response.data;
}

// =============================================================================
// Process Instances
// =============================================================================

export async function getInstances(
  params?: ProcessInstanceListParams
): Promise<ProcessInstance[]> {
  const response = await api.get<ProcessInstance[]>(`${BASE_URL}/instances`, {
    params,
  });
  return response.data;
}

export async function getInstance(id: string): Promise<ProcessInstance> {
  const response = await api.get<ProcessInstance>(`${BASE_URL}/instances/${id}`);
  return response.data;
}

export async function startInstance(
  data: ProcessInstanceCreate
): Promise<ProcessInstance> {
  const response = await api.post<ProcessInstance>(`${BASE_URL}/instances/start`, data);
  return response.data;
}

export async function signalInstance(
  id: string,
  signalName: string,
  variables?: Record<string, unknown>
): Promise<ProcessInstance> {
  const response = await api.post<ProcessInstance>(`${BASE_URL}/instances/${id}/signal`, {
    signal_name: signalName,
    variables,
  });
  return response.data;
}

export async function suspendInstance(id: string): Promise<ProcessInstance> {
  const response = await api.post<ProcessInstance>(`${BASE_URL}/instances/${id}/suspend`);
  return response.data;
}

export async function resumeInstance(id: string): Promise<ProcessInstance> {
  const response = await api.post<ProcessInstance>(`${BASE_URL}/instances/${id}/resume`);
  return response.data;
}

export async function terminateInstance(
  id: string,
  reason?: string
): Promise<ProcessInstance> {
  const response = await api.post<ProcessInstance>(`${BASE_URL}/instances/${id}/terminate`, {
    reason,
  });
  return response.data;
}

export async function getInstanceHistory(id: string): Promise<ProcessHistory[]> {
  const response = await api.get<ProcessHistory[]>(`${BASE_URL}/instances/${id}/history`);
  return response.data;
}

export async function getInstanceVariables(
  id: string
): Promise<Record<string, unknown>> {
  const response = await api.get<Record<string, unknown>>(
    `${BASE_URL}/instances/${id}/variables`
  );
  return response.data;
}

export async function setInstanceVariable(
  id: string,
  name: string,
  value: unknown
): Promise<void> {
  await api.put(`${BASE_URL}/instances/${id}/variables/${name}`, { value });
}

// =============================================================================
// Tasks
// =============================================================================

export async function getTasks(params?: TaskListParams): Promise<ProcessTask[]> {
  const response = await api.get<ProcessTask[]>(`${BASE_URL}/tasks`, {
    params,
  });
  return response.data;
}

export async function getMyTasks(): Promise<ProcessTask[]> {
  const response = await api.get<ProcessTask[]>(`${BASE_URL}/tasks/my`);
  return response.data;
}

export async function getGroupTasks(): Promise<ProcessTask[]> {
  const response = await api.get<ProcessTask[]>(`${BASE_URL}/tasks/group`);
  return response.data;
}

export async function getTask(id: string): Promise<ProcessTask> {
  const response = await api.get<ProcessTask>(`${BASE_URL}/tasks/${id}`);
  return response.data;
}

export async function claimTask(id: string, data?: TaskClaim): Promise<ProcessTask> {
  const response = await api.post<ProcessTask>(`${BASE_URL}/tasks/${id}/claim`, data);
  return response.data;
}

export async function unclaimTask(id: string): Promise<ProcessTask> {
  const response = await api.post<ProcessTask>(`${BASE_URL}/tasks/${id}/unclaim`);
  return response.data;
}

export async function startTask(id: string): Promise<ProcessTask> {
  const response = await api.post<ProcessTask>(`${BASE_URL}/tasks/${id}/start`);
  return response.data;
}

export async function completeTask(
  id: string,
  data?: TaskComplete
): Promise<ProcessTask> {
  const response = await api.post<ProcessTask>(`${BASE_URL}/tasks/${id}/complete`, data);
  return response.data;
}

export async function delegateTask(id: string, data: TaskDelegate): Promise<ProcessTask> {
  const response = await api.post<ProcessTask>(`${BASE_URL}/tasks/${id}/delegate`, data);
  return response.data;
}

export async function escalateTask(
  id: string,
  reason?: string
): Promise<ProcessTask> {
  const response = await api.post<ProcessTask>(`${BASE_URL}/tasks/${id}/escalate`, {
    reason,
  });
  return response.data;
}

export async function getTaskStatistics(): Promise<TaskStatistics> {
  const response = await api.get<TaskStatistics>(`${BASE_URL}/tasks/statistics`);
  return response.data;
}

// =============================================================================
// Timers
// =============================================================================

export async function getTimers(instanceId?: string): Promise<ProcessTimer[]> {
  const response = await api.get<ProcessTimer[]>(`${BASE_URL}/timers`, {
    params: { instance_id: instanceId },
  });
  return response.data;
}

export async function cancelTimer(id: string): Promise<void> {
  await api.post(`${BASE_URL}/timers/${id}/cancel`);
}

export async function getTimerStatistics(): Promise<TimerStatistics> {
  const response = await api.get<TimerStatistics>(`${BASE_URL}/timers/statistics`);
  return response.data;
}
