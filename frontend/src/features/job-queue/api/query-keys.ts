/**
 * Job Queue Query Keys
 *
 * Zentralisierte Query Key Verwaltung fuer TanStack Query.
 */

import type { JobListFilters, SortDirection } from '../types/job-types';

export const jobQueueKeys = {
  all: ['job-queue'] as const,

  // Jobs
  jobs: () => [...jobQueueKeys.all, 'jobs'] as const,
  jobsList: (params?: {
    page?: number;
    perPage?: number;
    filters?: JobListFilters;
    sortBy?: string;
    sortOrder?: SortDirection;
  }) => [...jobQueueKeys.jobs(), 'list', params] as const,
  jobsActive: () => [...jobQueueKeys.jobs(), 'active'] as const,
  jobsHistory: (params?: {
    page?: number;
    perPage?: number;
    filters?: JobListFilters;
  }) => [...jobQueueKeys.jobs(), 'history', params] as const,
  job: (id: string) => [...jobQueueKeys.jobs(), id] as const,

  // Stats
  stats: () => [...jobQueueKeys.all, 'stats'] as const,
  statsSummary: () => [...jobQueueKeys.stats(), 'summary'] as const,

  // Queues
  queues: () => [...jobQueueKeys.all, 'queues'] as const,
  queuesList: () => [...jobQueueKeys.queues(), 'list'] as const,
  queue: (name: string) => [...jobQueueKeys.queues(), name] as const,
  queueStats: (name: string) => [...jobQueueKeys.queue(name), 'stats'] as const,

  // Workers
  workers: () => [...jobQueueKeys.all, 'workers'] as const,
  workersList: () => [...jobQueueKeys.workers(), 'list'] as const,
  workersHealth: () => [...jobQueueKeys.workers(), 'health'] as const,

  // DLQ
  dlq: () => [...jobQueueKeys.all, 'dlq'] as const,
  dlqStats: () => [...jobQueueKeys.dlq(), 'stats'] as const,
  dlqTasks: (params?: {
    page?: number;
    perPage?: number;
    exceptionFilter?: string;
    taskFilter?: string;
  }) => [...jobQueueKeys.dlq(), 'tasks', params] as const,

  // Health (combined)
  health: () => [...jobQueueKeys.all, 'health'] as const,
};
