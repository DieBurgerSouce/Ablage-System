/**
 * Document Tasks API Client
 *
 * API-Funktionen fuer Aufgaben-Verwaltung an Dokumenten.
 * Backend-Endpunkte: /api/v1/document-tasks/*
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export type TaskStatus = 'pending' | 'in_progress' | 'blocked' | 'completed' | 'cancelled';
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

export interface DocumentTask {
  id: string;
  document_id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: TaskPriority;
  assignee_id?: string;
  assignee_name?: string;
  creator_id: string;
  creator_name: string;
  due_date?: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface TaskCreate {
  document_id: string;
  title: string;
  description?: string;
  priority: TaskPriority;
  assignee_id?: string;
  due_date?: string;
}

export interface TaskUpdate {
  title?: string;
  description?: string;
  priority?: TaskPriority;
  due_date?: string | null;
}

export interface TaskListResponse {
  items: DocumentTask[];
  total: number;
}

export interface TaskStatistics {
  total: number;
  pending: number;
  in_progress: number;
  blocked: number;
  completed: number;
  cancelled: number;
  overdue: number;
}

// ==================== API Functions ====================

export async function fetchDocumentTasks(params: {
  document_id?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  assignee_id?: string;
}): Promise<TaskListResponse> {
  const response = await apiClient.get<TaskListResponse>('/document-tasks', { params });
  return response.data;
}

export async function fetchMyTasks(): Promise<TaskListResponse> {
  const response = await apiClient.get<TaskListResponse>('/document-tasks/my');
  return response.data;
}

export async function fetchOverdueTasks(): Promise<TaskListResponse> {
  const response = await apiClient.get<TaskListResponse>('/document-tasks/overdue');
  return response.data;
}

export async function fetchTaskStatistics(): Promise<TaskStatistics> {
  const response = await apiClient.get<TaskStatistics>('/document-tasks/statistics');
  return response.data;
}

export async function createTask(payload: TaskCreate): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>('/document-tasks', payload);
  return response.data;
}

export async function updateTask(taskId: string, payload: TaskUpdate): Promise<DocumentTask> {
  const response = await apiClient.patch<DocumentTask>(`/document-tasks/${taskId}`, payload);
  return response.data;
}

export async function deleteTask(taskId: string): Promise<void> {
  await apiClient.delete(`/document-tasks/${taskId}`);
}

export async function startTask(taskId: string): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>(`/document-tasks/${taskId}/start`);
  return response.data;
}

export async function completeTask(taskId: string): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>(`/document-tasks/${taskId}/complete`);
  return response.data;
}

export async function cancelTask(taskId: string): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>(`/document-tasks/${taskId}/cancel`);
  return response.data;
}

export async function blockTask(taskId: string): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>(`/document-tasks/${taskId}/block`);
  return response.data;
}

export async function unblockTask(taskId: string): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>(`/document-tasks/${taskId}/unblock`);
  return response.data;
}

export async function assignTask(taskId: string, assigneeId: string): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>(`/document-tasks/${taskId}/assign`, {
    assignee_id: assigneeId,
  });
  return response.data;
}

export async function unassignTask(taskId: string): Promise<DocumentTask> {
  const response = await apiClient.post<DocumentTask>(`/document-tasks/${taskId}/unassign`);
  return response.data;
}
