/**
 * Validation API Client
 *
 * API-Client für das OCR-Training und Validierungs-System.
 * Basiert auf den existierenden Backend-Endpoints in app/api/v1/training.py
 */

import { apiClient } from '@/lib/api/client';
import type {
  TrainingSample,
  TrainingSampleListResponse,
  TrainingSampleCreate,
  TrainingSampleUpdate,
  Correction,
  CorrectionCreate,
  CorrectionListResponse,
  TrainingBatch,
  BatchCreate,
  BatchDetailResponse,
  BatchListResponse,
  BatchItemUpdate,
  BatchItem,
  TrainingStatsResponse,
  BackendComparisonResponse,
  TrainingSampleStatus,
} from '../types';

// Note: apiClient already has baseURL '/api/v1', so we only add the resource path
const BASE_URL = '/training';

// ==================== Training Samples ====================

export interface ListSamplesParams {
  status?: TrainingSampleStatus | string;
  language?: string;
  document_type?: string;
  has_ground_truth?: boolean;
  verified_only?: boolean;
  limit?: number;
  offset?: number;
}

/**
 * Listet Training-Samples mit optionalen Filtern auf.
 */
export async function listTrainingSamples(
  params: ListSamplesParams = {}
): Promise<TrainingSampleListResponse> {
  const searchParams = new URLSearchParams();

  if (params.status && params.status !== 'all') {
    searchParams.append('status', params.status);
  }
  if (params.language) {
    searchParams.append('language', params.language);
  }
  if (params.document_type) {
    searchParams.append('document_type', params.document_type);
  }
  if (params.has_ground_truth !== undefined) {
    searchParams.append('has_ground_truth', String(params.has_ground_truth));
  }
  if (params.verified_only) {
    searchParams.append('verified_only', 'true');
  }
  if (params.limit) {
    searchParams.append('limit', String(params.limit));
  }
  if (params.offset) {
    searchParams.append('offset', String(params.offset));
  }

  const url = `${BASE_URL}/samples${searchParams.toString() ? `?${searchParams}` : ''}`;
  const response = await apiClient.get<TrainingSampleListResponse>(url);
  return response.data;
}

/**
 * Holt ein einzelnes Training-Sample.
 */
export async function getTrainingSample(sampleId: string): Promise<TrainingSample> {
  const response = await apiClient.get<TrainingSample>(`${BASE_URL}/samples/${sampleId}`);
  return response.data;
}

/**
 * Erstellt ein neues Training-Sample.
 */
export async function createTrainingSample(
  data: TrainingSampleCreate
): Promise<TrainingSample> {
  const response = await apiClient.post<TrainingSample>(`${BASE_URL}/samples`, data);
  return response.data;
}

/**
 * Aktualisiert ein Training-Sample (Editor-Annotation).
 */
export async function updateTrainingSample(
  sampleId: string,
  data: TrainingSampleUpdate
): Promise<TrainingSample> {
  const response = await apiClient.put<TrainingSample>(
    `${BASE_URL}/samples/${sampleId}`,
    data
  );
  return response.data;
}

/**
 * Verifiziert ein Training-Sample (Admin-only).
 */
export async function verifyTrainingSample(
  sampleId: string,
  approved: boolean,
  notes?: string
): Promise<TrainingSample> {
  const searchParams = new URLSearchParams();
  searchParams.append('approved', String(approved));
  if (notes) {
    searchParams.append('notes', notes);
  }

  const response = await apiClient.post<TrainingSample>(
    `${BASE_URL}/samples/${sampleId}/verify?${searchParams}`
  );
  return response.data;
}

/**
 * Holt die Vorschau-URL für ein Sample.
 */
export function getSamplePreviewUrl(sampleId: string, page: number = 0): string {
  return `${BASE_URL}/samples/${sampleId}/preview?page=${page}`;
}

// ==================== Corrections ====================

export interface ListCorrectionsParams {
  backend?: string;
  correction_type?: string;
  learning_processed?: boolean;
  page?: number;
  per_page?: number;
}

/**
 * Listet OCR-Korrekturen auf.
 */
export async function listCorrections(
  params: ListCorrectionsParams = {}
): Promise<CorrectionListResponse> {
  const searchParams = new URLSearchParams();

  if (params.backend) {
    searchParams.append('backend', params.backend);
  }
  if (params.correction_type) {
    searchParams.append('correction_type', params.correction_type);
  }
  if (params.learning_processed !== undefined) {
    searchParams.append('learning_processed', String(params.learning_processed));
  }
  if (params.page) {
    searchParams.append('page', String(params.page));
  }
  if (params.per_page) {
    searchParams.append('per_page', String(params.per_page));
  }

  const url = `${BASE_URL}/corrections${searchParams.toString() ? `?${searchParams}` : ''}`;
  const response = await apiClient.get<CorrectionListResponse>(url);
  return response.data;
}

/**
 * Erstellt eine neue OCR-Korrektur (Self-Learning).
 */
export async function createCorrection(data: CorrectionCreate): Promise<Correction> {
  const response = await apiClient.post<Correction>(`${BASE_URL}/corrections`, data);
  return response.data;
}

// ==================== Batches (Stichproben) ====================

export interface ListBatchesParams {
  status?: string;
  limit?: number;
  offset?: number;
}

/**
 * Listet Stichproben-Batches auf.
 */
export async function listBatches(
  params: ListBatchesParams = {}
): Promise<BatchListResponse> {
  const searchParams = new URLSearchParams();

  if (params.status) {
    searchParams.append('status', params.status);
  }
  if (params.limit) {
    searchParams.append('limit', String(params.limit));
  }
  if (params.offset) {
    searchParams.append('offset', String(params.offset));
  }

  const url = `${BASE_URL}/batches${searchParams.toString() ? `?${searchParams}` : ''}`;
  const response = await apiClient.get<BatchListResponse>(url);
  return response.data;
}

/**
 * Holt einen Batch mit allen Items.
 */
export async function getBatch(batchId: string): Promise<BatchDetailResponse> {
  const response = await apiClient.get<BatchDetailResponse>(
    `${BASE_URL}/batches/${batchId}`
  );
  return response.data;
}

/**
 * Erstellt einen neuen Stichproben-Batch.
 */
export async function createBatch(data: BatchCreate): Promise<TrainingBatch> {
  const response = await apiClient.post<TrainingBatch>(`${BASE_URL}/batches`, data);
  return response.data;
}

/**
 * Aktualisiert ein Batch-Item.
 */
export async function updateBatchItem(
  batchId: string,
  itemId: string,
  data: BatchItemUpdate
): Promise<BatchItem> {
  const response = await apiClient.put<BatchItem>(
    `${BASE_URL}/batches/${batchId}/items/${itemId}`,
    data
  );
  return response.data;
}

/**
 * Startet einen Batch (startet die Validierung).
 * Backend-Endpoint: POST /batches/{batch_id}/start
 */
export async function startBatch(batchId: string): Promise<TrainingBatch> {
  const response = await apiClient.post<TrainingBatch>(
    `${BASE_URL}/batches/${batchId}/start`
  );
  return response.data;
}

/**
 * Schließt einen Batch ab.
 * Backend-Endpoint: POST /batches/{batch_id}/complete
 */
export async function completeBatch(batchId: string): Promise<TrainingBatch> {
  const response = await apiClient.post<TrainingBatch>(
    `${BASE_URL}/batches/${batchId}/complete`
  );
  return response.data;
}

// Backward-compatibility aliases (deprecated)
/** @deprecated Use startBatch instead */
export const activateBatch = startBatch;
/** @deprecated Use completeBatch instead */
export const cancelBatch = completeBatch;

// ==================== Statistics ====================

/**
 * Holt die Übersichts-Statistiken.
 */
export async function getTrainingStats(): Promise<TrainingStatsResponse> {
  const response = await apiClient.get<TrainingStatsResponse>(`${BASE_URL}/stats/overview`);
  return response.data;
}

/**
 * Holt den Backend-Vergleich.
 */
export async function getBackendComparison(): Promise<BackendComparisonResponse> {
  const response = await apiClient.get<BackendComparisonResponse>(
    `${BASE_URL}/benchmarks/compare`
  );
  return response.data;
}

// ==================== Benchmarks ====================

export interface RunBenchmarkParams {
  sample_ids: string[];
  backends?: string[];
  force_rerun?: boolean;
}

export interface BenchmarkRunResponse {
  task_id: string | null;
  success: boolean;
  samples_processed: number;
  samples_failed: number;
  backends_used: string[];
  total_time_ms: number;
}

/**
 * Startet einen Benchmark-Lauf.
 */
export async function runBenchmarks(
  params: RunBenchmarkParams
): Promise<BenchmarkRunResponse> {
  const response = await apiClient.post<BenchmarkRunResponse>(
    `${BASE_URL}/benchmarks/run`,
    params
  );
  return response.data;
}

// ==================== Export Object ====================

export const validationApi = {
  // Samples
  listSamples: listTrainingSamples,
  getSample: getTrainingSample,
  createSample: createTrainingSample,
  updateSample: updateTrainingSample,
  verifySample: verifyTrainingSample,
  getSamplePreviewUrl,

  // Corrections
  listCorrections,
  createCorrection,

  // Batches
  listBatches,
  getBatch,
  createBatch,
  updateBatchItem,
  startBatch,
  completeBatch,
  // Backward-compatibility (deprecated)
  activateBatch,
  cancelBatch,

  // Stats
  getStats: getTrainingStats,
  getBackendComparison,

  // Benchmarks
  runBenchmarks,
};

export default validationApi;
