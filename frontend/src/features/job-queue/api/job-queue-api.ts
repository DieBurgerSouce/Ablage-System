/**
 * Job Queue API Service
 *
 * Enterprise-Level API Service für Job Queue Management.
 * Feinpoliert und durchdacht.
 */

import { apiClient } from '@/lib/api/client';
import type {
  Job,
  JobResult,
  JobListFilters,
  JobListResponse,
  JobStats,
  JobActionResponse,
  BulkActionResponse,
  QueueClearResponse,
  QueueListResponse,
  QueueStats,
  WorkerListResponse,
  WorkerHealth,
  DLQStats,
  DLQTaskListResponse,
  DLQActionResponse,
  SortDirection,
} from '../types/job-types';

// ==================== Jobs API ====================

/**
 * Listet alle Jobs mit Filterung und Pagination auf.
 */
export async function listJobs(params: {
  page?: number;
  perPage?: number;
  filters?: JobListFilters;
  sortBy?: string;
  sortOrder?: SortDirection;
}): Promise<JobListResponse> {
  const {
    page = 1,
    perPage = 20,
    filters = {},
    sortBy = 'created_at',
    sortOrder = 'desc',
  } = params;

  const searchParams = new URLSearchParams({
    page: page.toString(),
    per_page: perPage.toString(),
    sort_by: sortBy,
    sort_order: sortOrder.toUpperCase(),
  });

  // Add filters
  if (filters.status) searchParams.append('status', filters.status);
  if (filters.backend) searchParams.append('backend', filters.backend);
  if (filters.userId) searchParams.append('user_id', filters.userId);
  if (filters.priority) searchParams.append('priority', filters.priority.toString());
  if (filters.hasError !== undefined) searchParams.append('has_error', filters.hasError.toString());
  if (filters.createdFrom) searchParams.append('created_from', filters.createdFrom);
  if (filters.createdTo) searchParams.append('created_to', filters.createdTo);

  const response = await apiClient.get<{
    jobs: Array<{
      id: string;
      document_id?: string;
      document_filename?: string;
      user_id?: string;
      user_email?: string;
      job_type: string;
      backend?: string;
      status: string;
      priority: number;
      retry_count: number;
      max_retries: number;
      created_at: string;
      started_at?: string;
      completed_at?: string;
      error_message?: string;
      worker_id?: string;
      result?: Record<string, unknown>;
      duration_ms?: number;
      wait_time_ms?: number;
    }>;
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
    status_summary: Record<string, number>;
  }>(`/admin/jobs?${searchParams.toString()}`);

  // Transform snake_case to camelCase
  return {
    jobs: response.data.jobs.map(transformJob),
    total: response.data.total,
    page: response.data.page,
    perPage: response.data.per_page,
    totalPages: response.data.total_pages,
    statusSummary: response.data.status_summary,
  };
}

/**
 * Ruft einen einzelnen Job ab.
 */
export async function getJob(jobId: string): Promise<Job> {
  const response = await apiClient.get(`/admin/jobs/${jobId}`);
  return transformJob(response.data);
}

/**
 * Ruft Job-Statistiken ab.
 */
export async function getJobStats(): Promise<JobStats> {
  const response = await apiClient.get<{
    status_summary: Record<string, number>;
    total_jobs: number;
    active_jobs: number;
    queued_jobs: number;
    jobs_24h: number;
    completed_24h: number;
    failed_24h: number;
    success_rate_24h: number;
    throughput_per_hour: number;
    avg_processing_time_ms: number;
    avg_wait_time_ms: number;
    jobs_by_backend: Record<string, number>;
    jobs_by_type: Record<string, number>;
  }>('/admin/jobs/stats/summary');

  return {
    statusSummary: response.data.status_summary,
    totalJobs: response.data.total_jobs,
    activeJobs: response.data.active_jobs,
    queuedJobs: response.data.queued_jobs,
    jobs24h: response.data.jobs_24h,
    completed24h: response.data.completed_24h,
    failed24h: response.data.failed_24h,
    successRate24h: response.data.success_rate_24h,
    throughputPerHour: response.data.throughput_per_hour,
    avgProcessingTimeMs: response.data.avg_processing_time_ms,
    avgWaitTimeMs: response.data.avg_wait_time_ms,
    jobsByBackend: response.data.jobs_by_backend,
    jobsByType: response.data.jobs_by_type,
  };
}

// ==================== Job Actions ====================

/**
 * Bricht einen Job ab.
 */
export async function cancelJob(jobId: string, reason?: string): Promise<JobActionResponse> {
  const params = reason ? `?reason=${encodeURIComponent(reason)}` : '';
  const response = await apiClient.post(`/admin/jobs/${jobId}/cancel${params}`);
  return transformActionResponse(response.data);
}

/**
 * Wiederholt einen fehlgeschlagenen Job.
 */
export async function retryJob(
  jobId: string,
  options?: { priority?: number; backend?: string }
): Promise<JobActionResponse> {
  const params = new URLSearchParams();
  if (options?.priority) params.append('priority', options.priority.toString());
  if (options?.backend) params.append('backend', options.backend);
  const queryString = params.toString() ? `?${params.toString()}` : '';

  const response = await apiClient.post(`/admin/jobs/${jobId}/retry${queryString}`);
  return transformActionResponse(response.data);
}

/**
 * Aendert die Prioritaet eines Jobs.
 */
export async function changeJobPriority(jobId: string, priority: number): Promise<JobActionResponse> {
  const response = await apiClient.patch(`/admin/jobs/${jobId}/priority?priority=${priority}`);
  return transformActionResponse(response.data);
}

/**
 * Beendet einen Job erzwungen (SIGKILL).
 */
export async function forceKillJob(jobId: string): Promise<JobActionResponse> {
  const response = await apiClient.post(`/admin/jobs/${jobId}/force-kill`);
  return transformActionResponse(response.data);
}

/**
 * Pausiert einen Job.
 */
export async function pauseJob(jobId: string): Promise<JobActionResponse> {
  const response = await apiClient.post(`/admin/jobs/${jobId}/pause`);
  return transformActionResponse(response.data);
}

/**
 * Setzt einen pausierten Job fort.
 */
export async function resumeJob(jobId: string): Promise<JobActionResponse> {
  const response = await apiClient.post(`/admin/jobs/${jobId}/resume`);
  return transformActionResponse(response.data);
}

// ==================== Bulk Actions ====================

/**
 * Bricht mehrere Jobs ab.
 */
export async function bulkCancelJobs(jobIds: string[], reason?: string): Promise<BulkActionResponse> {
  const params = reason ? `?reason=${encodeURIComponent(reason)}` : '';
  const response = await apiClient.post(`/admin/jobs/bulk/cancel${params}`, jobIds);
  return transformBulkResponse(response.data);
}

/**
 * Wiederholt mehrere fehlgeschlagene Jobs.
 */
export async function bulkRetryJobs(
  jobIds: string[],
  options?: { priority?: number; backend?: string }
): Promise<BulkActionResponse> {
  const params = new URLSearchParams();
  if (options?.priority) params.append('priority', options.priority.toString());
  if (options?.backend) params.append('backend', options.backend);
  const queryString = params.toString() ? `?${params.toString()}` : '';

  const response = await apiClient.post(`/admin/jobs/bulk/retry${queryString}`, jobIds);
  return transformBulkResponse(response.data);
}

/**
 * Aendert die Prioritaet mehrerer Jobs.
 */
export async function bulkChangePriority(
  jobIds: string[],
  priority: number
): Promise<BulkActionResponse> {
  const response = await apiClient.post(`/admin/jobs/bulk/priority?priority=${priority}`, jobIds);
  return transformBulkResponse(response.data);
}

/**
 * Leert die Warteschlange.
 */
export async function clearQueue(status: 'pending' | 'queued' = 'pending'): Promise<QueueClearResponse> {
  const response = await apiClient.post<{
    success: boolean;
    cleared_count: number;
    message: string;
  }>(`/admin/jobs/queue/clear?status=${status}`);

  return {
    success: response.data.success,
    clearedCount: response.data.cleared_count,
    message: response.data.message,
  };
}

// ==================== Queues API ====================

/**
 * Listet alle Queues auf.
 */
export async function listQueues(): Promise<QueueListResponse> {
  const response = await apiClient.get<{
    queues: Array<{
      name: string;
      length: number;
      processing: number;
      priority: number;
      description: string;
    }>;
    total_pending: number;
    total_processing: number;
  }>('/admin/queues');

  return {
    queues: response.data.queues,
    totalPending: response.data.total_pending,
    totalProcessing: response.data.total_processing,
  };
}

/**
 * Ruft Queue-Statistiken ab.
 */
export async function getQueueStats(queueName: string): Promise<QueueStats> {
  const response = await apiClient.get<{
    name: string;
    length: number;
    processing: number;
    completed_last_hour: number;
    failed_last_hour: number;
    avg_processing_time_ms: number;
    throughput_per_minute: number;
  }>(`/admin/queues/${queueName}/stats`);

  return {
    name: response.data.name,
    length: response.data.length,
    processing: response.data.processing,
    completedLastHour: response.data.completed_last_hour,
    failedLastHour: response.data.failed_last_hour,
    avgProcessingTimeMs: response.data.avg_processing_time_ms,
    throughputPerMinute: response.data.throughput_per_minute,
  };
}

// ==================== Workers API ====================

/**
 * Listet alle Worker auf.
 */
export async function listWorkers(): Promise<WorkerListResponse> {
  const response = await apiClient.get<{
    workers: Array<{
      id: string;
      hostname: string;
      status: string;
      active_tasks: number;
      current_task?: string;
      current_task_id?: string;
      last_heartbeat?: string;
      tasks_processed: number;
      pool_size: number;
      prefetch_count: number;
    }>;
    total_workers: number;
    online_workers: number;
    busy_workers: number;
    gpu: {
      available: boolean;
      name?: string;
      memory_used_mb: number;
      memory_total_mb: number;
      memory_percent: number;
      utilization_percent: number;
      temperature_celsius?: number;
      lock_held: boolean;
      lock_holder?: string;
    };
  }>('/admin/queues/workers');

  return {
    workers: response.data.workers.map((w) => ({
      id: w.id,
      hostname: w.hostname,
      status: w.status as 'online' | 'offline' | 'busy',
      activeTasks: w.active_tasks,
      currentTask: w.current_task,
      currentTaskId: w.current_task_id,
      lastHeartbeat: w.last_heartbeat,
      tasksProcessed: w.tasks_processed,
      poolSize: w.pool_size,
      prefetchCount: w.prefetch_count,
    })),
    totalWorkers: response.data.total_workers,
    onlineWorkers: response.data.online_workers,
    busyWorkers: response.data.busy_workers,
    gpu: {
      available: response.data.gpu.available,
      name: response.data.gpu.name,
      memoryUsedMb: response.data.gpu.memory_used_mb,
      memoryTotalMb: response.data.gpu.memory_total_mb,
      memoryPercent: response.data.gpu.memory_percent,
      utilizationPercent: response.data.gpu.utilization_percent,
      temperatureCelsius: response.data.gpu.temperature_celsius,
      lockHeld: response.data.gpu.lock_held,
      lockHolder: response.data.gpu.lock_holder,
    },
  };
}

/**
 * Ruft Worker-Gesundheitsinformationen ab.
 */
export async function getWorkersHealth(): Promise<WorkerHealth> {
  const response = await apiClient.get('/admin/queues/workers/health');
  return response.data;
}

// ==================== DLQ API ====================

/**
 * Ruft DLQ-Statistiken ab.
 */
export async function getDLQStats(): Promise<DLQStats> {
  const response = await apiClient.get<{
    total_tasks: number;
    poison_pills: number;
    oldest_task_age_hours?: number;
    tasks_by_exception: Record<string, number>;
    tasks_by_name: Record<string, number>;
    status: string;
    status_message: string;
  }>('/admin/dlq/stats');

  return {
    totalTasks: response.data.total_tasks,
    poisonPills: response.data.poison_pills,
    oldestTaskAgeHours: response.data.oldest_task_age_hours,
    tasksByException: response.data.tasks_by_exception,
    tasksByName: response.data.tasks_by_name,
    status: response.data.status as 'healthy' | 'warning' | 'critical' | 'error',
    statusMessage: response.data.status_message,
  };
}

/**
 * Listet DLQ-Tasks auf.
 */
export async function listDLQTasks(params: {
  page?: number;
  perPage?: number;
  exceptionFilter?: string;
  taskFilter?: string;
}): Promise<DLQTaskListResponse> {
  const { page = 1, perPage = 20, exceptionFilter, taskFilter } = params;

  const searchParams = new URLSearchParams({
    page: page.toString(),
    per_page: perPage.toString(),
  });

  if (exceptionFilter) searchParams.append('exception_filter', exceptionFilter);
  if (taskFilter) searchParams.append('task_filter', taskFilter);

  const response = await apiClient.get<{
    tasks: Array<{
      id: string;
      name: string;
      args?: unknown[];
      kwargs?: Record<string, unknown>;
      exception_type: string;
      exception_message: string;
      traceback?: string;
      failed_at?: string;
      retries: number;
      original_queue: string;
      is_poison_pill: boolean;
    }>;
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
  }>(`/admin/dlq/tasks?${searchParams.toString()}`);

  return {
    tasks: response.data.tasks.map((t) => ({
      id: t.id,
      name: t.name,
      args: t.args,
      kwargs: t.kwargs,
      exceptionType: t.exception_type,
      exceptionMessage: t.exception_message,
      traceback: t.traceback,
      failedAt: t.failed_at,
      retries: t.retries,
      originalQueue: t.original_queue,
      isPoisonPill: t.is_poison_pill,
    })),
    total: response.data.total,
    page: response.data.page,
    perPage: response.data.per_page,
    totalPages: response.data.total_pages,
  };
}

/**
 * Wiederholt eine DLQ-Task.
 */
export async function retryDLQTask(taskId: string): Promise<DLQActionResponse> {
  const response = await apiClient.post(`/admin/dlq/${taskId}/retry`);
  return transformDLQActionResponse(response.data);
}

/**
 * Wiederholt mehrere DLQ-Tasks.
 */
export async function bulkRetryDLQTasks(taskIds: string[]): Promise<DLQActionResponse> {
  const response = await apiClient.post('/admin/dlq/bulk/retry', taskIds);
  return transformDLQActionResponse(response.data);
}

/**
 * Leert die DLQ.
 */
export async function purgeDLQ(): Promise<DLQActionResponse> {
  const response = await apiClient.post('/admin/dlq/purge?confirm=true');
  return transformDLQActionResponse(response.data);
}

// ==================== Transform Functions ====================

function transformJob(data: Record<string, unknown>): Job {
  // Fix 11: Stricter type casting für result
  const rawResult = data.result as Record<string, unknown> | undefined;
  const result: JobResult | undefined = rawResult ? {
    progress: rawResult.progress as number | undefined,
    message: rawResult.message as string | undefined,
    paused: rawResult.paused as boolean | undefined,
    outputPath: rawResult.output_path as string | undefined,
    pageCount: rawResult.page_count as number | undefined,
    characterCount: rawResult.character_count as number | undefined,
    processingTimeMs: rawResult.processing_time_ms as number | undefined,
    warnings: rawResult.warnings as string[] | undefined,
  } : undefined;

  return {
    id: data.id as string,
    documentId: data.document_id as string | undefined,
    documentFilename: data.document_filename as string | undefined,
    userId: data.user_id as string | undefined,
    userEmail: data.user_email as string | undefined,
    jobType: data.job_type as Job['jobType'],
    backend: data.backend as string | undefined,
    status: data.status as Job['status'],
    priority: data.priority as number,
    retryCount: data.retry_count as number,
    maxRetries: data.max_retries as number,
    createdAt: data.created_at as string,
    startedAt: data.started_at as string | undefined,
    completedAt: data.completed_at as string | undefined,
    errorMessage: data.error_message as string | undefined,
    workerId: data.worker_id as string | undefined,
    result,
    durationMs: data.duration_ms as number | undefined,
    waitTimeMs: data.wait_time_ms as number | undefined,
    progress: result?.progress,
    message: result?.message,
    isPaused: result?.paused,
  };
}

function transformActionResponse(data: Record<string, unknown>): JobActionResponse {
  return {
    success: data.success as boolean,
    jobId: data.job_id as string,
    action: data.action as string,
    message: data.message as string,
  };
}

function transformBulkResponse(data: Record<string, unknown>): BulkActionResponse {
  return {
    success: (data.success as Array<{ original_job_id: string; new_job_id?: string }>).map((s) => ({
      originalJobId: s.original_job_id,
      newJobId: s.new_job_id,
    })),
    failed: (data.failed as Array<{ job_id: string; reason: string }>).map((f) => ({
      jobId: f.job_id,
      reason: f.reason,
    })),
    total: data.total as number,
    successCount: data.success_count as number,
    failedCount: data.failed_count as number,
  };
}

function transformDLQActionResponse(data: Record<string, unknown>): DLQActionResponse {
  return {
    success: data.success as boolean,
    message: data.message as string,
    taskId: data.task_id as string | undefined,
    details: data.details as Record<string, unknown> | undefined,
  };
}

// ==================== Export ====================

export const jobQueueApi = {
  // Jobs
  listJobs,
  getJob,
  getJobStats,
  cancelJob,
  retryJob,
  changeJobPriority,
  forceKillJob,
  pauseJob,
  resumeJob,
  bulkCancelJobs,
  bulkRetryJobs,
  bulkChangePriority,
  clearQueue,
  // Queues
  listQueues,
  getQueueStats,
  // Workers
  listWorkers,
  getWorkersHealth,
  // DLQ
  getDLQStats,
  listDLQTasks,
  retryDLQTask,
  bulkRetryDLQTasks,
  purgeDLQ,
};
