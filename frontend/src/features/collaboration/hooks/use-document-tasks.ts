/**
 * useDocumentTasks - Hooks fuer Dokumenten-Aufgaben
 *
 * Ermoeglicht das Laden, Erstellen, Aktualisieren und Verwalten von Aufgaben.
 * Integriert mit Backend API: /api/v1/document-tasks
 *
 * Enterprise Features:
 * - Error Handling mit Toast-Benachrichtigungen
 * - Query Invalidation nach Mutations
 * - Deutsche Fehlermeldungen
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  fetchDocumentTasks,
  fetchMyTasks,
  fetchOverdueTasks,
  fetchTaskStatistics,
  createTask,
  updateTask,
  deleteTask,
  startTask,
  completeTask,
  cancelTask,
  blockTask,
  unblockTask,
  assignTask,
  unassignTask,
  type TaskCreate,
  type TaskUpdate,
  type TaskStatus,
  type TaskPriority,
} from '../api/document-tasks-api';

// ==================== Query Keys ====================

export const documentTaskKeys = {
  all: ['document-tasks'] as const,
  list: (documentId: string) => [...documentTaskKeys.all, 'list', documentId] as const,
  my: () => [...documentTaskKeys.all, 'my'] as const,
  overdue: () => [...documentTaskKeys.all, 'overdue'] as const,
  statistics: () => [...documentTaskKeys.all, 'statistics'] as const,
};

// ==================== Query Hooks ====================

export function useDocumentTasks(
  documentId: string,
  filters?: { status?: TaskStatus; priority?: TaskPriority },
) {
  return useQuery({
    queryKey: [...documentTaskKeys.list(documentId), filters],
    queryFn: () => fetchDocumentTasks({ document_id: documentId, ...filters }),
    staleTime: 30000,
    enabled: !!documentId,
  });
}

export function useMyTasks() {
  return useQuery({
    queryKey: documentTaskKeys.my(),
    queryFn: fetchMyTasks,
    staleTime: 30000,
  });
}

export function useOverdueTasks() {
  return useQuery({
    queryKey: documentTaskKeys.overdue(),
    queryFn: fetchOverdueTasks,
    staleTime: 30000,
  });
}

export function useTaskStatistics() {
  return useQuery({
    queryKey: documentTaskKeys.statistics(),
    queryFn: fetchTaskStatistics,
    staleTime: 60000,
  });
}

// ==================== Mutation Helpers ====================

function useInvalidateTasks() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: documentTaskKeys.all });
  };
}

// ==================== Mutation Hooks ====================

export function useCreateTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (payload: TaskCreate) => createTask(payload),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe erstellt');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Erstellen der Aufgabe', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useUpdateTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: ({ taskId, payload }: { taskId: string; payload: TaskUpdate }) =>
      updateTask(taskId, payload),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe aktualisiert');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Aktualisieren', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useDeleteTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe geloescht');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Loeschen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useStartTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (taskId: string) => startTask(taskId),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe gestartet');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Starten', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useCompleteTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (taskId: string) => completeTask(taskId),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe abgeschlossen');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Abschliessen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useCancelTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (taskId: string) => cancelTask(taskId),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe abgebrochen');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Abbrechen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useBlockTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (taskId: string) => blockTask(taskId),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe blockiert');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Blockieren', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useUnblockTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (taskId: string) => unblockTask(taskId),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe freigegeben');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Freigeben', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useAssignTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: ({ taskId, assigneeId }: { taskId: string; assigneeId: string }) =>
      assignTask(taskId, assigneeId),
    onSuccess: () => {
      invalidate();
      toast.success('Aufgabe zugewiesen');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Zuweisen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}

export function useUnassignTask() {
  const invalidate = useInvalidateTasks();

  return useMutation({
    mutationFn: (taskId: string) => unassignTask(taskId),
    onSuccess: () => {
      invalidate();
      toast.success('Zuweisung entfernt');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Entfernen der Zuweisung', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}
