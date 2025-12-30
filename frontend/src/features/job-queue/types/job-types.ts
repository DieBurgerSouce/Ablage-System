/**
 * Job Queue TypeScript Types
 *
 * Enterprise-Level Type Definitionen für das Job Queue Management.
 */

// ==================== Enums ====================

export type JobType =
  | 'ocr'
  | 'embedding'
  | 'validation'
  | 'export'
  | 'backup'
  | 'gdpr'
  | 'rag'
  | 'maintenance'
  | 'cleanup'
  | 'metrics';

export type JobStatus =
  | 'pending'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type QueueHealthStatus = 'healthy' | 'warning' | 'critical' | 'error';

export type WorkerStatusType = 'online' | 'offline' | 'busy';

// ==================== Job Interfaces ====================

/**
 * Fix 11: Stricter TypeScript type für Job-Result
 * Ersetzt Record<string, unknown> mit konkreten Feldern
 */
export interface JobResult {
  progress?: number;
  message?: string;
  paused?: boolean;
  outputPath?: string;
  pageCount?: number;
  characterCount?: number;
  processingTimeMs?: number;
  warnings?: string[];
}

export interface Job {
  id: string;
  documentId?: string;
  documentFilename?: string;
  userId?: string;
  userEmail?: string;
  jobType: JobType;
  backend?: string;
  status: JobStatus;
  priority: number;
  retryCount: number;
  maxRetries: number;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  errorMessage?: string;
  workerId?: string;
  /** Fix 11: Stricter type statt Record<string, unknown> */
  result?: JobResult;
  durationMs?: number;
  waitTimeMs?: number;
  progress?: number;
  message?: string;
  isPaused?: boolean;
}

export interface JobListFilters {
  status?: JobStatus;
  backend?: string;
  userId?: string;
  priority?: number;
  hasError?: boolean;
  createdFrom?: string;
  createdTo?: string;
  jobType?: JobType;
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  perPage: number;
  totalPages: number;
  statusSummary: Record<string, number>;
}

// ==================== Job Statistics ====================

export interface JobStats {
  statusSummary: Record<string, number>;
  totalJobs: number;
  activeJobs: number;
  queuedJobs: number;
  jobs24h: number;
  completed24h: number;
  failed24h: number;
  successRate24h: number;
  throughputPerHour: number;
  avgProcessingTimeMs: number;
  avgWaitTimeMs: number;
  jobsByBackend: Record<string, number>;
  jobsByType: Record<string, number>;
}

// ==================== Queue Interfaces ====================

export interface QueueStatus {
  name: string;
  length: number;
  processing: number;
  priority: number;
  description: string;
}

export interface QueueListResponse {
  queues: QueueStatus[];
  totalPending: number;
  totalProcessing: number;
}

export interface QueueStats {
  name: string;
  length: number;
  processing: number;
  completedLastHour: number;
  failedLastHour: number;
  avgProcessingTimeMs: number;
  throughputPerMinute: number;
}

// ==================== Worker Interfaces ====================

export interface WorkerStatus {
  id: string;
  hostname: string;
  status: WorkerStatusType;
  activeTasks: number;
  currentTask?: string;
  currentTaskId?: string;
  lastHeartbeat?: string;
  tasksProcessed: number;
  poolSize: number;
  prefetchCount: number;
}

export interface GPUStatus {
  available: boolean;
  name?: string;
  memoryUsedMb: number;
  memoryTotalMb: number;
  memoryPercent: number;
  utilizationPercent: number;
  temperatureCelsius?: number;
  lockHeld: boolean;
  lockHolder?: string;
}

export interface WorkerListResponse {
  workers: WorkerStatus[];
  totalWorkers: number;
  onlineWorkers: number;
  busyWorkers: number;
  gpu: GPUStatus;
}

export interface WorkerHealth {
  workers: Array<{
    id: string;
    hostname: string;
    status: string;
    lastHeartbeat?: string;
  }>;
  totalWorkers: number;
  healthyWorkers: number;
  unhealthyWorkers: number;
  staleTasks: Array<{
    taskId: string;
    taskName: string;
    startedAt: string;
    durationSeconds: number;
  }>;
  warnings: string[];
  errors: string[];
  gpuLock?: {
    locked: boolean;
    owner?: string;
    ttlSeconds?: number;
  };
}

// ==================== DLQ Interfaces ====================

export interface DLQTask {
  id: string;
  name: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
  exceptionType: string;
  exceptionMessage: string;
  traceback?: string;
  failedAt?: string;
  retries: number;
  originalQueue: string;
  isPoisonPill: boolean;
}

export interface DLQStats {
  totalTasks: number;
  poisonPills: number;
  oldestTaskAgeHours?: number;
  tasksByException: Record<string, number>;
  tasksByName: Record<string, number>;
  status: QueueHealthStatus;
  statusMessage: string;
}

export interface DLQTaskListResponse {
  tasks: DLQTask[];
  total: number;
  page: number;
  perPage: number;
  totalPages: number;
}

export interface DLQActionResponse {
  success: boolean;
  message: string;
  taskId?: string;
  details?: Record<string, unknown>;
}

// ==================== Action Responses ====================

export interface JobActionResponse {
  success: boolean;
  jobId: string;
  action: string;
  message: string;
}

export interface BulkActionResponse {
  success: Array<{ originalJobId: string; newJobId?: string }>;
  failed: Array<{ jobId: string; reason: string }>;
  total: number;
  successCount: number;
  failedCount: number;
}

export interface QueueClearResponse {
  success: boolean;
  clearedCount: number;
  message: string;
}

// ==================== User Settings ====================

export interface JobNotificationSettings {
  onComplete: boolean;
  onFailure: boolean;
  onStuck: boolean;
  soundEnabled: boolean;
  retentionDays: number;
}

// ==================== Utility Types ====================

export type SortDirection = 'asc' | 'desc';

export interface PaginationParams {
  page: number;
  perPage: number;
}

export interface SortParams {
  sortBy: string;
  sortOrder: SortDirection;
}

// ==================== Status Helpers ====================

export const JOB_STATUS_CONFIG: Record<JobStatus, { label: string; color: string; icon: string }> = {
  pending: { label: 'Wartend', color: 'secondary', icon: 'Clock' },
  queued: { label: 'In Warteschlange', color: 'secondary', icon: 'ListOrdered' },
  processing: { label: 'In Bearbeitung', color: 'default', icon: 'Loader2' },
  completed: { label: 'Abgeschlossen', color: 'success', icon: 'CheckCircle' },
  failed: { label: 'Fehlgeschlagen', color: 'destructive', icon: 'XCircle' },
  cancelled: { label: 'Abgebrochen', color: 'outline', icon: 'Ban' },
};

export const JOB_TYPE_CONFIG: Record<JobType, { label: string; icon: string }> = {
  ocr: { label: 'OCR', icon: 'FileText' },
  embedding: { label: 'Embedding', icon: 'Brain' },
  validation: { label: 'Validierung', icon: 'CheckSquare' },
  export: { label: 'Export', icon: 'Download' },
  backup: { label: 'Backup', icon: 'Database' },
  gdpr: { label: 'GDPR', icon: 'Shield' },
  rag: { label: 'RAG', icon: 'MessageSquare' },
  maintenance: { label: 'Wartung', icon: 'Wrench' },
  cleanup: { label: 'Bereinigung', icon: 'Trash2' },
  metrics: { label: 'Metriken', icon: 'BarChart' },
};

export const QUEUE_PRIORITY_CONFIG: Record<number, { label: string; color: string }> = {
  10: { label: 'Hoechste', color: 'destructive' },
  9: { label: 'Sehr Hoch', color: 'destructive' },
  8: { label: 'Hoch', color: 'warning' },
  7: { label: 'Erhoht', color: 'warning' },
  6: { label: 'Leicht Erhoht', color: 'default' },
  5: { label: 'Normal', color: 'default' },
  4: { label: 'Leicht Niedrig', color: 'secondary' },
  3: { label: 'Niedrig', color: 'secondary' },
  2: { label: 'Sehr Niedrig', color: 'muted' },
  1: { label: 'Niedrigste', color: 'muted' },
};
