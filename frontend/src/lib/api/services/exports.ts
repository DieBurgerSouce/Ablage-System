/**
 * Exports API Service
 *
 * Kommuniziert mit den /api/v1/exports Endpoints
 * fuer Export-Job Verwaltung und Echtzeit-Updates.
 *
 * Features:
 * - Export-Jobs erstellen (async via Celery)
 * - Export-Job Status abfragen (Polling)
 * - Export-Job abbrechen/pausieren/fortsetzen
 * - WebSocket fuer Echtzeit-Updates
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';

// ==================== Types ====================

export type ExportFormat = 'json' | 'csv' | 'zip' | 'pdf';
export type ExportJobStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled' | 'paused';

export interface ExportJobRequest {
  documentIds: string[];
  format?: ExportFormat;
  includeText?: boolean;
  includeMetadata?: boolean;
}

export interface ExportJobCreatedResponse {
  jobId: string;
  status: ExportJobStatus;
  message: string;
  totalDocuments: number;
  createdAt: string;
}

export interface ExportJobStatusResponse {
  jobId: string;
  status: ExportJobStatus;
  progress: number;
  totalDocuments: number;
  processedDocuments: number;
  failedDocuments: number;
  currentDocument: string | null;
  message: string;
  downloadUrl: string | null;
  isCancelled: boolean;
  isPaused: boolean;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}

export interface ExportJobListItem {
  jobId: string;
  status: ExportJobStatus;
  progress: number;
  totalDocuments: number;
  processedDocuments: number;
  format: ExportFormat;
  createdAt: string;
  completedAt: string | null;
}

export interface ExportJobListResponse {
  jobs: ExportJobListItem[];
  total: number;
}

export interface CancelJobResponse {
  jobId: string;
  status: string;
  message: string;
  cancelledAt: string;
}

// ==================== Backend Types ====================

interface ExportJobCreatedBackend {
  job_id: string;
  status: string;
  message: string;
  total_documents: number;
  created_at: string;
}

interface ExportJobStatusBackend {
  job_id: string;
  status: string;
  progress: number;
  total_documents: number;
  processed_documents: number;
  failed_documents: number;
  current_document: string | null;
  message: string;
  download_url: string | null;
  is_cancelled: boolean;
  is_paused: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

interface ExportJobListBackend {
  jobs: {
    job_id: string;
    status: string;
    progress: number;
    total_documents: number;
    processed_documents: number;
    format: string;
    created_at: string;
    completed_at: string | null;
  }[];
  total: number;
}

interface CancelJobBackend {
  job_id: string;
  status: string;
  message: string;
  cancelled_at: string;
}

// ==================== Error Classes ====================

export class ExportApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'ExportApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Transformers ====================

function transformJobCreated(data: ExportJobCreatedBackend): ExportJobCreatedResponse {
  return {
    jobId: data.job_id,
    status: data.status as ExportJobStatus,
    message: data.message,
    totalDocuments: data.total_documents,
    createdAt: data.created_at,
  };
}

function transformJobStatus(data: ExportJobStatusBackend): ExportJobStatusResponse {
  return {
    jobId: data.job_id,
    status: data.status as ExportJobStatus,
    progress: data.progress,
    totalDocuments: data.total_documents,
    processedDocuments: data.processed_documents,
    failedDocuments: data.failed_documents,
    currentDocument: data.current_document,
    message: data.message,
    downloadUrl: data.download_url,
    isCancelled: data.is_cancelled,
    isPaused: data.is_paused,
    createdAt: data.created_at,
    startedAt: data.started_at,
    completedAt: data.completed_at,
  };
}

function transformJobList(data: ExportJobListBackend): ExportJobListResponse {
  return {
    jobs: data.jobs.map((job) => ({
      jobId: job.job_id,
      status: job.status as ExportJobStatus,
      progress: job.progress,
      totalDocuments: job.total_documents,
      processedDocuments: job.processed_documents,
      format: job.format as ExportFormat,
      createdAt: job.created_at,
      completedAt: job.completed_at,
    })),
    total: data.total,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    throw new ExportApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new ExportApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Export Service ====================

export const exportsService = {
  /**
   * Erstellt einen neuen Export-Job
   */
  createJob: async (request: ExportJobRequest): Promise<ExportJobCreatedResponse> => {
    try {
      const response = await apiClient.post<ExportJobCreatedBackend>('/exports/jobs', {
        document_ids: request.documentIds,
        format: request.format || 'json',
        include_text: request.includeText ?? true,
        include_metadata: request.includeMetadata ?? true,
      });

      return transformJobCreated(response.data);
    } catch (error) {
      handleApiError(error, 'Export-Job erstellen');
    }
  },

  /**
   * Holt den Status eines Export-Jobs
   */
  getJobStatus: async (jobId: string): Promise<ExportJobStatusResponse> => {
    try {
      const response = await apiClient.get<ExportJobStatusBackend>(`/exports/jobs/${jobId}`);
      return transformJobStatus(response.data);
    } catch (error) {
      handleApiError(error, 'Export-Job Status abrufen');
    }
  },

  /**
   * Listet alle Export-Jobs des Benutzers auf
   */
  listJobs: async (
    status?: ExportJobStatus,
    limit?: number,
    offset?: number
  ): Promise<ExportJobListResponse> => {
    try {
      const params = new URLSearchParams();
      if (status) params.append('status', status);
      if (limit) params.append('limit', String(limit));
      if (offset) params.append('offset', String(offset));

      const response = await apiClient.get<ExportJobListBackend>(
        `/exports/jobs${params.toString() ? `?${params.toString()}` : ''}`
      );

      return transformJobList(response.data);
    } catch (error) {
      handleApiError(error, 'Export-Jobs auflisten');
    }
  },

  /**
   * Bricht einen Export-Job ab
   */
  cancelJob: async (jobId: string): Promise<CancelJobResponse> => {
    try {
      const response = await apiClient.post<CancelJobBackend>(`/exports/jobs/${jobId}/cancel`);
      return {
        jobId: response.data.job_id,
        status: response.data.status,
        message: response.data.message,
        cancelledAt: response.data.cancelled_at,
      };
    } catch (error) {
      handleApiError(error, 'Export-Job abbrechen');
    }
  },

  /**
   * Pausiert einen Export-Job
   */
  pauseJob: async (jobId: string): Promise<ExportJobStatusResponse> => {
    try {
      const response = await apiClient.post<ExportJobStatusBackend>(`/exports/jobs/${jobId}/pause`);
      return transformJobStatus(response.data);
    } catch (error) {
      handleApiError(error, 'Export-Job pausieren');
    }
  },

  /**
   * Setzt einen pausierten Export-Job fort
   */
  resumeJob: async (jobId: string): Promise<ExportJobStatusResponse> => {
    try {
      const response = await apiClient.post<ExportJobStatusBackend>(`/exports/jobs/${jobId}/resume`);
      return transformJobStatus(response.data);
    } catch (error) {
      handleApiError(error, 'Export-Job fortsetzen');
    }
  },

  /**
   * Erstellt eine WebSocket-Verbindung fuer Echtzeit-Updates
   */
  createWebSocketConnection: (
    jobId: string,
    onMessage: (data: ExportJobStatusResponse) => void,
    onError?: (error: Event) => void,
    onClose?: () => void
  ): WebSocket | null => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/api/v1/exports/jobs/${jobId}/ws`;

      const ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          onMessage({
            jobId: data.job_id,
            status: data.status,
            progress: data.progress,
            totalDocuments: data.total_documents,
            processedDocuments: data.processed_documents,
            failedDocuments: data.failed_documents,
            currentDocument: data.current_document,
            message: data.message,
            downloadUrl: data.download_url,
            isCancelled: data.is_cancelled,
            isPaused: data.is_paused,
            createdAt: data.created_at,
            startedAt: data.started_at,
            completedAt: data.completed_at,
          });
        } catch {
          console.error('Failed to parse WebSocket message');
        }
      };

      ws.onerror = (error) => {
        if (onError) onError(error);
      };

      ws.onclose = () => {
        if (onClose) onClose();
      };

      return ws;
    } catch {
      console.error('Failed to create WebSocket connection');
      return null;
    }
  },
};
