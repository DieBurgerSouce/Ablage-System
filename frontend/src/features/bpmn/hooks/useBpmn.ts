/**
 * BPMN Process Engine Hooks
 *
 * TanStack Query hooks for BPMN 2.0 Process Engine.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/bpmn-api';
import type { ProcessDefinitionCreate, ProcessDefinitionListParams, ProcessInstanceCreate, ProcessInstanceListParams, TaskComplete, TaskClaim, TaskDelegate, TaskListParams } from '../types/bpmn-types';

// =============================================================================
// Query Keys
// =============================================================================

export const bpmnKeys = {
  all: ['bpmn'] as const,
  // Definitions
  definitions: () => [...bpmnKeys.all, 'definitions'] as const,
  definitionsList: (params?: ProcessDefinitionListParams) =>
    [...bpmnKeys.definitions(), 'list', params] as const,
  definitionDetail: (id: string) => [...bpmnKeys.definitions(), 'detail', id] as const,
  definitionByKey: (key: string) => [...bpmnKeys.definitions(), 'key', key] as const,
  definitionStatistics: () => [...bpmnKeys.definitions(), 'statistics'] as const,
  // Instances
  instances: () => [...bpmnKeys.all, 'instances'] as const,
  instancesList: (params?: ProcessInstanceListParams) =>
    [...bpmnKeys.instances(), 'list', params] as const,
  instanceDetail: (id: string) => [...bpmnKeys.instances(), 'detail', id] as const,
  instanceHistory: (id: string) => [...bpmnKeys.instances(), 'history', id] as const,
  instanceVariables: (id: string) => [...bpmnKeys.instances(), 'variables', id] as const,
  // Tasks
  tasks: () => [...bpmnKeys.all, 'tasks'] as const,
  tasksList: (params?: TaskListParams) => [...bpmnKeys.tasks(), 'list', params] as const,
  myTasks: () => [...bpmnKeys.tasks(), 'my'] as const,
  groupTasks: () => [...bpmnKeys.tasks(), 'group'] as const,
  taskDetail: (id: string) => [...bpmnKeys.tasks(), 'detail', id] as const,
  taskStatistics: () => [...bpmnKeys.tasks(), 'statistics'] as const,
  // Timers
  timers: () => [...bpmnKeys.all, 'timers'] as const,
  timersList: (instanceId?: string) => [...bpmnKeys.timers(), 'list', instanceId] as const,
  timerStatistics: () => [...bpmnKeys.timers(), 'statistics'] as const,
};

// =============================================================================
// Process Definition Hooks
// =============================================================================

export function useDefinitions(params?: ProcessDefinitionListParams) {
  return useQuery({
    queryKey: bpmnKeys.definitionsList(params),
    queryFn: () => api.getDefinitions(params),
  });
}

export function useDefinition(id: string) {
  return useQuery({
    queryKey: bpmnKeys.definitionDetail(id),
    queryFn: () => api.getDefinition(id),
    enabled: !!id,
  });
}

export function useDefinitionByKey(key: string) {
  return useQuery({
    queryKey: bpmnKeys.definitionByKey(key),
    queryFn: () => api.getDefinitionByKey(key),
    enabled: !!key,
  });
}

export function useDefinitionStatistics() {
  return useQuery({
    queryKey: bpmnKeys.definitionStatistics(),
    queryFn: api.getDefinitionStatistics,
  });
}

export function useCreateDefinition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ProcessDefinitionCreate) => api.createDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bpmnKeys.definitions() });
    },
  });
}

export function useDeployDefinition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ProcessDefinitionCreate) => api.deployDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bpmnKeys.definitions() });
    },
  });
}

export function useActivateDefinition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.activateDefinition(id),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.definitionDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.definitions() });
    },
  });
}

export function useDeactivateDefinition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.deactivateDefinition(id),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.definitionDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.definitions() });
    },
  });
}

export function useExportDefinitionBpmn() {
  return useMutation({
    mutationFn: (id: string) => api.exportDefinitionBpmn(id),
  });
}

// =============================================================================
// Process Instance Hooks
// =============================================================================

export function useInstances(params?: ProcessInstanceListParams) {
  return useQuery({
    queryKey: bpmnKeys.instancesList(params),
    queryFn: () => api.getInstances(params),
  });
}

export function useInstance(id: string) {
  return useQuery({
    queryKey: bpmnKeys.instanceDetail(id),
    queryFn: () => api.getInstance(id),
    enabled: !!id,
  });
}

export function useInstanceHistory(id: string) {
  return useQuery({
    queryKey: bpmnKeys.instanceHistory(id),
    queryFn: () => api.getInstanceHistory(id),
    enabled: !!id,
  });
}

export function useInstanceVariables(id: string) {
  return useQuery({
    queryKey: bpmnKeys.instanceVariables(id),
    queryFn: () => api.getInstanceVariables(id),
    enabled: !!id,
  });
}

export function useStartInstance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ProcessInstanceCreate) => api.startInstance(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bpmnKeys.instances() });
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

export function useSignalInstance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      signalName,
      variables,
    }: {
      id: string;
      signalName: string;
      variables?: Record<string, unknown>;
    }) => api.signalInstance(id, signalName, variables),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.instanceDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.instances() });
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

export function useSuspendInstance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.suspendInstance(id),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.instanceDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.instances() });
    },
  });
}

export function useResumeInstance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.resumeInstance(id),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.instanceDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.instances() });
    },
  });
}

export function useTerminateInstance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      api.terminateInstance(id, reason),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.instanceDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.instances() });
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

export function useSetInstanceVariable() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      name,
      value,
    }: {
      id: string;
      name: string;
      value: unknown;
    }) => api.setInstanceVariable(id, name, value),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: bpmnKeys.instanceVariables(id) });
    },
  });
}

// =============================================================================
// Task Hooks
// =============================================================================

export function useTasks(params?: TaskListParams) {
  return useQuery({
    queryKey: bpmnKeys.tasksList(params),
    queryFn: () => api.getTasks(params),
  });
}

export function useMyTasks() {
  return useQuery({
    queryKey: bpmnKeys.myTasks(),
    queryFn: api.getMyTasks,
    refetchInterval: 30000, // Refresh every 30 seconds
  });
}

export function useGroupTasks() {
  return useQuery({
    queryKey: bpmnKeys.groupTasks(),
    queryFn: api.getGroupTasks,
    refetchInterval: 30000,
  });
}

export function useTask(id: string) {
  return useQuery({
    queryKey: bpmnKeys.taskDetail(id),
    queryFn: () => api.getTask(id),
    enabled: !!id,
  });
}

export function useTaskStatistics() {
  return useQuery({
    queryKey: bpmnKeys.taskStatistics(),
    queryFn: api.getTaskStatistics,
  });
}

export function useClaimTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data?: TaskClaim }) =>
      api.claimTask(id, data),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.taskDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

export function useUnclaimTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.unclaimTask(id),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.taskDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

export function useStartTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.startTask(id),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.taskDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

export function useCompleteTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data?: TaskComplete }) =>
      api.completeTask(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
      queryClient.invalidateQueries({ queryKey: bpmnKeys.instances() });
    },
  });
}

export function useDelegateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TaskDelegate }) =>
      api.delegateTask(id, data),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.taskDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

export function useEscalateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      api.escalateTask(id, reason),
    onSuccess: (data) => {
      queryClient.setQueryData(bpmnKeys.taskDetail(data.id), data);
      queryClient.invalidateQueries({ queryKey: bpmnKeys.tasks() });
    },
  });
}

// =============================================================================
// Timer Hooks
// =============================================================================

export function useTimers(instanceId?: string) {
  return useQuery({
    queryKey: bpmnKeys.timersList(instanceId),
    queryFn: () => api.getTimers(instanceId),
  });
}

export function useTimerStatistics() {
  return useQuery({
    queryKey: bpmnKeys.timerStatistics(),
    queryFn: api.getTimerStatistics,
  });
}

export function useCancelTimer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => api.cancelTimer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bpmnKeys.timers() });
    },
  });
}
