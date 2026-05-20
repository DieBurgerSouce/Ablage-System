/**
 * Job Queue Query Hooks
 *
 * TanStack Query Hooks für Job Queue Daten.
 * Enterprise-Level Data Fetching mit Caching und Auto-Refetch.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { jobQueueKeys } from '../api/query-keys';
import { jobQueueApi } from '../api/job-queue-api';
import { QUERY_REALTIME } from '@/lib/api/query-config';
import type {
  JobListFilters,
  SortDirection,
  Job,
  JobStats,
  QueueListResponse,
  QueueStats,
  WorkerListResponse,
  WorkerHealth,
  DLQStats,
  DLQTaskListResponse,
} from '../types/job-types';

// ==================== Job Queries ====================

/**
 * Hook für Job-Liste mit Filterung und Pagination.
 */
export function useJobsList(params?: {
  page?: number;
  perPage?: number;
  filters?: JobListFilters;
  sortBy?: string;
  sortOrder?: SortDirection;
  enabled?: boolean;
}) {
  const { enabled = true, ...queryParams } = params || {};

  return useQuery({
    queryKey: jobQueueKeys.jobsList(queryParams),
    queryFn: () => jobQueueApi.listJobs(queryParams),
    enabled,
    refetchInterval: 10000, // Alle 10 Sekunden refreshen
    staleTime: QUERY_REALTIME.staleTime, // 5s - Echtzeit
  });
}

/**
 * Hook für aktive Jobs (processing + queued).
 */
export function useActiveJobs(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.jobsActive(),
    queryFn: () =>
      jobQueueApi.listJobs({
        filters: { status: 'processing' },
        perPage: 100,
        sortBy: 'started_at',
        sortOrder: 'desc',
      }),
    enabled: options?.enabled ?? true,
    refetchInterval: 5000, // Aktive Jobs alle 5 Sekunden refreshen
    staleTime: 2000,
  });
}

/**
 * Hook für Job-Historie.
 */
export function useJobHistory(params?: {
  page?: number;
  perPage?: number;
  filters?: JobListFilters;
  enabled?: boolean;
}) {
  const { enabled = true, ...queryParams } = params || {};

  // Standardmaessig nur abgeschlossene/fehlgeschlagene Jobs
  const filters = {
    ...queryParams.filters,
    status: queryParams.filters?.status || undefined,
  };

  return useQuery({
    queryKey: jobQueueKeys.jobsHistory({ ...queryParams, filters }),
    queryFn: () =>
      jobQueueApi.listJobs({
        ...queryParams,
        filters,
        sortBy: 'completed_at',
        sortOrder: 'desc',
      }),
    enabled,
    refetchInterval: 30000, // Historie weniger oft refreshen
    staleTime: 10000,
  });
}

/**
 * Hook für einzelnen Job.
 */
export function useJob(jobId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.job(jobId),
    queryFn: () => jobQueueApi.getJob(jobId),
    enabled: (options?.enabled ?? true) && !!jobId,
    refetchInterval: 5000,
    staleTime: 2000,
  });
}

/**
 * Hook für Job-Statistiken.
 */
export function useJobStats(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.statsSummary(),
    queryFn: () => jobQueueApi.getJobStats(),
    enabled: options?.enabled ?? true,
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

// ==================== Queue Queries ====================

/**
 * Hook für Queue-Liste.
 */
export function useQueuesList(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.queuesList(),
    queryFn: () => jobQueueApi.listQueues(),
    enabled: options?.enabled ?? true,
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

/**
 * Hook für Queue-Statistiken.
 */
export function useQueueStats(queueName: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.queueStats(queueName),
    queryFn: () => jobQueueApi.getQueueStats(queueName),
    enabled: (options?.enabled ?? true) && !!queueName,
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

// ==================== Worker Queries ====================

/**
 * Hook für Worker-Liste mit GPU-Status.
 */
export function useWorkersList(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.workersList(),
    queryFn: () => jobQueueApi.listWorkers(),
    enabled: options?.enabled ?? true,
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

/**
 * Hook für Worker-Gesundheit.
 */
export function useWorkersHealth(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.workersHealth(),
    queryFn: () => jobQueueApi.getWorkersHealth(),
    enabled: options?.enabled ?? true,
    refetchInterval: 15000,
    staleTime: 10000,
  });
}

// ==================== DLQ Queries ====================

/**
 * Hook für DLQ-Statistiken.
 */
export function useDLQStats(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: jobQueueKeys.dlqStats(),
    queryFn: () => jobQueueApi.getDLQStats(),
    enabled: options?.enabled ?? true,
    refetchInterval: 30000, // DLQ weniger oft refreshen
    staleTime: 15000,
  });
}

/**
 * Hook für DLQ-Tasks.
 */
export function useDLQTasks(
  params?: {
    page?: number;
    perPage?: number;
    exceptionFilter?: string;
    taskFilter?: string;
  },
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: jobQueueKeys.dlqTasks(params),
    queryFn: () => jobQueueApi.listDLQTasks(params || {}),
    enabled: options?.enabled ?? true,
    refetchInterval: 30000,
    staleTime: 15000,
  });
}

// ==================== Combined Health Query ====================

/**
 * Hook für kombinierte System-Gesundheit.
 */
export function useSystemHealth(options?: { enabled?: boolean }) {
  const workersQuery = useWorkersList({ enabled: options?.enabled });
  const dlqQuery = useDLQStats({ enabled: options?.enabled });
  const statsQuery = useJobStats({ enabled: options?.enabled });

  return {
    workers: workersQuery.data,
    dlq: dlqQuery.data,
    stats: statsQuery.data,
    isLoading: workersQuery.isLoading || dlqQuery.isLoading || statsQuery.isLoading,
    isError: workersQuery.isError || dlqQuery.isError || statsQuery.isError,
    error: workersQuery.error || dlqQuery.error || statsQuery.error,
    refetch: () => {
      workersQuery.refetch();
      dlqQuery.refetch();
      statsQuery.refetch();
    },
  };
}

// ==================== Export ====================

export const jobQueueQueries = {
  useJobsList,
  useActiveJobs,
  useJobHistory,
  useJob,
  useJobStats,
  useQueuesList,
  useQueueStats,
  useWorkersList,
  useWorkersHealth,
  useDLQStats,
  useDLQTasks,
  useSystemHealth,
};
