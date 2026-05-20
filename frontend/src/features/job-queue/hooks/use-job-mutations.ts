/**
 * Job Queue Mutation Hooks
 *
 * TanStack Query Mutations für Job Queue Aktionen.
 * Enterprise-Level mit Optimistic Updates und automatische Cache-Invalidierung.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { jobQueueKeys } from '../api/query-keys';
import { jobQueueApi } from '../api/job-queue-api';
import type {
  Job,
  JobActionResponse,
  BulkActionResponse,
  QueueClearResponse,
  DLQActionResponse,
  JobListResponse,
} from '../types/job-types';
import { toast } from 'sonner';

// ==================== Optimistic Update Helpers ====================

/**
 * Helper to update a single job in the cache.
 */
function updateJobInCache(
  queryClient: ReturnType<typeof useQueryClient>,
  jobId: string,
  updater: (job: Job) => Job
): Job | undefined {
  let previousJob: Job | undefined;

  // Get all job list queries and update them
  queryClient.setQueriesData<JobListResponse>(
    { queryKey: jobQueueKeys.jobs() },
    (old) => {
      if (!old) return old;
      return {
        ...old,
        jobs: old.jobs.map((job) => {
          if (job.id === jobId) {
            previousJob = job;
            return updater(job);
          }
          return job;
        }),
      };
    }
  );

  return previousJob;
}

/**
 * Helper to revert a job update in the cache.
 */
function revertJobInCache(
  queryClient: ReturnType<typeof useQueryClient>,
  previousJob: Job | undefined
): void {
  if (!previousJob) return;

  queryClient.setQueriesData<JobListResponse>(
    { queryKey: jobQueueKeys.jobs() },
    (old) => {
      if (!old) return old;
      return {
        ...old,
        jobs: old.jobs.map((job) =>
          job.id === previousJob.id ? previousJob : job
        ),
      };
    }
  );
}

// ==================== Job Mutations ====================

/**
 * Hook zum Abbrechen eines Jobs.
 * Mit Optimistic Update für sofortiges UI-Feedback.
 */
export function useCancelJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobId, reason }: { jobId: string; reason?: string }) =>
      jobQueueApi.cancelJob(jobId, reason),
    onMutate: async ({ jobId }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: jobQueueKeys.jobs() });

      // Optimistically update the job status
      const previousJob = updateJobInCache(queryClient, jobId, (job) => ({
        ...job,
        status: 'cancelled' as const,
        completedAt: new Date().toISOString(),
      }));

      return { previousJob };
    },
    onSuccess: (data, _, context) => {
      if (data.success) {
        toast.success('Job abgebrochen', {
          description: data.message,
        });
        // Refresh stats (job list is already optimistically updated)
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
      } else {
        // Revert on server rejection
        revertJobInCache(queryClient, context?.previousJob);
        toast.error('Fehler beim Abbrechen', {
          description: data.message,
        });
      }
    },
    onError: (error, _, context) => {
      // Revert on error
      revertJobInCache(queryClient, context?.previousJob);
      toast.error('Fehler beim Abbrechen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
    onSettled: () => {
      // Always refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
    },
  });
}

/**
 * Hook zum Wiederholen eines Jobs.
 */
export function useRetryJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      jobId,
      options,
    }: {
      jobId: string;
      options?: { priority?: number; backend?: string };
    }) => jobQueueApi.retryJob(jobId, options),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Job wird wiederholt', {
          description: data.message,
        });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
      } else {
        toast.error('Fehler beim Wiederholen', {
          description: data.message,
        });
      }
    },
    onError: (error) => {
      toast.error('Fehler beim Wiederholen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

/**
 * Hook zum Ändern der Job-Priorität.
 * Mit Optimistic Update für sofortiges UI-Feedback.
 */
export function useChangeJobPriority() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobId, priority }: { jobId: string; priority: number }) =>
      jobQueueApi.changeJobPriority(jobId, priority),
    onMutate: async ({ jobId, priority }) => {
      await queryClient.cancelQueries({ queryKey: jobQueueKeys.jobs() });

      const previousJob = updateJobInCache(queryClient, jobId, (job) => ({
        ...job,
        priority,
      }));

      return { previousJob };
    },
    onSuccess: (data, _, context) => {
      if (data.success) {
        toast.success('Priorität geändert', {
          description: data.message,
        });
      } else {
        revertJobInCache(queryClient, context?.previousJob);
        toast.error('Fehler beim Ändern', {
          description: data.message,
        });
      }
    },
    onError: (error, _, context) => {
      revertJobInCache(queryClient, context?.previousJob);
      toast.error('Fehler beim Ändern der Priorität', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
    },
  });
}

/**
 * Hook zum Force-Kill eines Jobs.
 */
export function useForceKillJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => jobQueueApi.forceKillJob(jobId),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Job beendet', {
          description: data.message,
        });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.workers() });
      } else {
        toast.error('Fehler beim Beenden', {
          description: data.message,
        });
      }
    },
    onError: (error) => {
      toast.error('Fehler beim Force-Kill', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

/**
 * Hook zum Pausieren eines Jobs.
 * Mit Optimistic Update für sofortiges UI-Feedback.
 */
export function usePauseJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => jobQueueApi.pauseJob(jobId),
    onMutate: async (jobId) => {
      await queryClient.cancelQueries({ queryKey: jobQueueKeys.jobs() });

      const previousJob = updateJobInCache(queryClient, jobId, (job) => ({
        ...job,
        isPaused: true,
      }));

      return { previousJob };
    },
    onSuccess: (data, _, context) => {
      if (data.success) {
        toast.success('Job pausiert', {
          description: data.message,
        });
      } else {
        revertJobInCache(queryClient, context?.previousJob);
        toast.error('Fehler beim Pausieren', {
          description: data.message,
        });
      }
    },
    onError: (error, _, context) => {
      revertJobInCache(queryClient, context?.previousJob);
      toast.error('Fehler beim Pausieren', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
    },
  });
}

/**
 * Hook zum Fortsetzen eines Jobs.
 * Mit Optimistic Update für sofortiges UI-Feedback.
 */
export function useResumeJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => jobQueueApi.resumeJob(jobId),
    onMutate: async (jobId) => {
      await queryClient.cancelQueries({ queryKey: jobQueueKeys.jobs() });

      const previousJob = updateJobInCache(queryClient, jobId, (job) => ({
        ...job,
        isPaused: false,
      }));

      return { previousJob };
    },
    onSuccess: (data, _, context) => {
      if (data.success) {
        toast.success('Job fortgesetzt', {
          description: data.message,
        });
      } else {
        revertJobInCache(queryClient, context?.previousJob);
        toast.error('Fehler beim Fortsetzen', {
          description: data.message,
        });
      }
    },
    onError: (error, _, context) => {
      revertJobInCache(queryClient, context?.previousJob);
      toast.error('Fehler beim Fortsetzen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
    },
  });
}

// ==================== Bulk Mutations ====================

/**
 * Hook zum Abbrechen mehrerer Jobs.
 */
export function useBulkCancelJobs() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobIds, reason }: { jobIds: string[]; reason?: string }) =>
      jobQueueApi.bulkCancelJobs(jobIds, reason),
    onSuccess: (data) => {
      if (data.failedCount === 0) {
        toast.success(`${data.successCount} Jobs abgebrochen`);
      } else {
        toast.warning(`${data.successCount} von ${data.total} Jobs abgebrochen`, {
          description: `${data.failedCount} Jobs konnten nicht abgebrochen werden`,
        });
      }
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
    },
    onError: (error) => {
      toast.error('Fehler beim Massenabbruch', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

/**
 * Hook zum Wiederholen mehrerer Jobs.
 */
export function useBulkRetryJobs() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      jobIds,
      options,
    }: {
      jobIds: string[];
      options?: { priority?: number; backend?: string };
    }) => jobQueueApi.bulkRetryJobs(jobIds, options),
    onSuccess: (data) => {
      if (data.failedCount === 0) {
        toast.success(`${data.successCount} Jobs werden wiederholt`);
      } else {
        toast.warning(`${data.successCount} von ${data.total} Jobs werden wiederholt`, {
          description: `${data.failedCount} Jobs konnten nicht wiederholt werden`,
        });
      }
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
    },
    onError: (error) => {
      toast.error('Fehler beim Massen-Wiederholen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

/**
 * Hook zum Ändern der Priorität mehrerer Jobs.
 */
export function useBulkChangePriority() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobIds, priority }: { jobIds: string[]; priority: number }) =>
      jobQueueApi.bulkChangePriority(jobIds, priority),
    onSuccess: (data) => {
      if (data.failedCount === 0) {
        toast.success(`Priorität für ${data.successCount} Jobs geändert`);
      } else {
        toast.warning(`${data.successCount} von ${data.total} Jobs geändert`, {
          description: `${data.failedCount} Jobs konnten nicht geändert werden`,
        });
      }
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
    },
    onError: (error) => {
      toast.error('Fehler beim Ändern der Priorität', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

/**
 * Hook zum Leeren der Warteschlange.
 */
export function useClearQueue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (status: 'pending' | 'queued' = 'pending') => jobQueueApi.clearQueue(status),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Warteschlange geleert', {
          description: `${data.clearedCount} Jobs entfernt`,
        });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.queues() });
      } else {
        toast.error('Fehler beim Leeren', {
          description: data.message,
        });
      }
    },
    onError: (error) => {
      toast.error('Fehler beim Leeren der Warteschlange', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

// ==================== DLQ Mutations ====================

/**
 * Hook zum Wiederholen einer DLQ-Task.
 */
export function useRetryDLQTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (taskId: string) => jobQueueApi.retryDLQTask(taskId),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('DLQ-Task wird wiederholt', {
          description: data.message,
        });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.dlq() });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
      } else {
        toast.error('Fehler beim Wiederholen', {
          description: data.message,
        });
      }
    },
    onError: (error) => {
      toast.error('Fehler beim Wiederholen der DLQ-Task', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

/**
 * Hook zum Wiederholen mehrerer DLQ-Tasks.
 */
export function useBulkRetryDLQTasks() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (taskIds: string[]) => jobQueueApi.bulkRetryDLQTasks(taskIds),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('DLQ-Tasks werden wiederholt', {
          description: data.message,
        });
      } else {
        toast.warning('Teilweise fehlgeschlagen', {
          description: data.message,
        });
      }
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.dlq() });
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
    },
    onError: (error) => {
      toast.error('Fehler beim Massen-Wiederholen', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

/**
 * Hook zum Leeren der DLQ.
 */
export function usePurgeDLQ() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => jobQueueApi.purgeDLQ(),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('DLQ geleert', {
          description: data.message,
        });
        queryClient.invalidateQueries({ queryKey: jobQueueKeys.dlq() });
      } else {
        toast.error('Fehler beim Leeren', {
          description: data.message,
        });
      }
    },
    onError: (error) => {
      toast.error('Fehler beim Leeren der DLQ', {
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
      });
    },
  });
}

// ==================== Export ====================

export const jobQueueMutations = {
  useCancelJob,
  useRetryJob,
  useChangeJobPriority,
  useForceKillJob,
  usePauseJob,
  useResumeJob,
  useBulkCancelJobs,
  useBulkRetryJobs,
  useBulkChangePriority,
  useClearQueue,
  useRetryDLQTask,
  useBulkRetryDLQTasks,
  usePurgeDLQ,
};
