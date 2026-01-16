/**
 * AI Decision Review - API Client
 *
 * API-Funktionen fuer ML/AI Entscheidungen, Drift Detection,
 * SHAP Erklaerungen und A/B Testing.
 */

import { logger } from '@/lib/logger';
import type {
  DriftStatus,
  DriftReport,
  RoutingExplanation,
  GlobalImportance,
  Experiment,
  CreateExperimentRequest,
  MetricsSummary,
  AIDecision,
  AIDecisionFilters,
  AIDecisionStats,
  LearningStats,
  ConfidenceThresholds,
} from '../types/ai-types';

const API_BASE = '/api/v1/ml';

// =============================================================================
// API Client Helper
// =============================================================================

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `API Error: ${response.status}`);
  }

  return response.json();
}

// =============================================================================
// Drift Detection API
// =============================================================================

export async function getDriftStatus(): Promise<DriftStatus> {
  return apiRequest<DriftStatus>('/drift/status');
}

export async function runDriftDetection(): Promise<DriftReport> {
  return apiRequest<DriftReport>('/drift/detect', { method: 'POST' });
}

export async function getDriftHistory(limit = 10): Promise<DriftReport[]> {
  return apiRequest<DriftReport[]>(`/drift/history?limit=${limit}`);
}

export async function resetDriftReference(): Promise<{ message: string }> {
  return apiRequest<{ message: string }>('/drift/reset', { method: 'POST' });
}

// =============================================================================
// SHAP Explainability API
// =============================================================================

export async function getRoutingExplanation(
  documentId: string
): Promise<RoutingExplanation> {
  return apiRequest<RoutingExplanation>(`/explain/${documentId}`);
}

export async function getGlobalFeatureImportance(): Promise<GlobalImportance> {
  return apiRequest<GlobalImportance>('/explain/importance');
}

// =============================================================================
// A/B Testing API
// =============================================================================

export async function listExperiments(
  status?: string
): Promise<Experiment[]> {
  const query = status ? `?status=${status}` : '';
  return apiRequest<Experiment[]>(`/experiments${query}`);
}

export async function getExperiment(experimentId: string): Promise<Experiment> {
  return apiRequest<Experiment>(`/experiments/${experimentId}`);
}

export async function createExperiment(
  data: CreateExperimentRequest
): Promise<Experiment> {
  return apiRequest<Experiment>('/experiments', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function startExperiment(
  experimentId: string
): Promise<{ message: string }> {
  return apiRequest<{ message: string }>(
    `/experiments/${experimentId}/start`,
    { method: 'POST' }
  );
}

export async function concludeExperiment(
  experimentId: string
): Promise<{ message: string; winner: string | null }> {
  return apiRequest<{ message: string; winner: string | null }>(
    `/experiments/${experimentId}/conclude`,
    { method: 'POST' }
  );
}

// =============================================================================
// Metrics API
// =============================================================================

export async function getMetricsSummary(): Promise<MetricsSummary> {
  return apiRequest<MetricsSummary>('/metrics/summary');
}

// =============================================================================
// AI Decision Review API (Mock - to be implemented in backend)
// =============================================================================

export async function getAIDecisions(
  filters?: AIDecisionFilters,
  page = 1,
  pageSize = 20
): Promise<{ items: AIDecision[]; total: number }> {
  // TODO: Implement real API endpoint
  // For now, return mock data
  const mockDecisions: AIDecision[] = [
    {
      id: '1',
      document_id: 'doc-123',
      document_name: 'Rechnung_2024_001.pdf',
      timestamp: new Date().toISOString(),
      backend_used: 'deepseek-janus-pro',
      raw_confidence: 0.92,
      calibrated_confidence: 0.89,
      confidence_level: 'high',
      quality_decision: 'accept',
      explanation: null,
      needs_review: false,
      reviewed_at: null,
      reviewed_by: null,
      review_outcome: null,
    },
    {
      id: '2',
      document_id: 'doc-456',
      document_name: 'Vertrag_Draft.pdf',
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      backend_used: 'got-ocr-2.0',
      raw_confidence: 0.68,
      calibrated_confidence: 0.65,
      confidence_level: 'medium',
      quality_decision: 'request_review',
      explanation: null,
      needs_review: true,
      reviewed_at: null,
      reviewed_by: null,
      review_outcome: null,
    },
    {
      id: '3',
      document_id: 'doc-789',
      document_name: 'Fraktur_Brief.jpg',
      timestamp: new Date(Date.now() - 7200000).toISOString(),
      backend_used: 'deepseek-janus-pro',
      raw_confidence: 0.45,
      calibrated_confidence: 0.42,
      confidence_level: 'low',
      quality_decision: 'retry_different_backend',
      explanation: null,
      needs_review: true,
      reviewed_at: null,
      reviewed_by: null,
      review_outcome: null,
    },
  ];

  // Apply filters (simplified)
  let filtered = [...mockDecisions];
  if (filters?.needs_review !== undefined) {
    filtered = filtered.filter(d => d.needs_review === filters.needs_review);
  }
  if (filters?.confidence_level?.length) {
    filtered = filtered.filter(d =>
      filters.confidence_level!.includes(d.confidence_level)
    );
  }

  return {
    items: filtered,
    total: filtered.length,
  };
}

export async function getAIDecisionStats(): Promise<AIDecisionStats> {
  // TODO: Implement real API endpoint
  return {
    total_decisions: 1247,
    pending_review: 23,
    approved: 1156,
    corrected: 45,
    rejected: 23,
    avg_confidence: 0.847,
    by_backend: {
      'deepseek-janus-pro': 782,
      'got-ocr-2.0': 312,
      'surya-gpu': 98,
      'surya': 55,
    },
    by_confidence_level: {
      very_high: 423,
      high: 512,
      medium: 234,
      low: 56,
      very_low: 22,
    },
  };
}

export async function reviewAIDecision(
  decisionId: string,
  outcome: 'approved' | 'corrected' | 'rejected',
  correction?: string
): Promise<{ success: boolean }> {
  // TODO: Implement real API endpoint
  logger.debug('KI-Entscheidung überprüft:', { decisionId, outcome, correction });
  return { success: true };
}

// =============================================================================
// Learning Stats API (Mock - to be implemented in backend)
// =============================================================================

export async function getLearningStats(): Promise<LearningStats> {
  // TODO: Implement real API endpoint
  return {
    total_corrections: 245,
    corrections_applied: 198,
    model_accuracy_before: 0.823,
    model_accuracy_after: 0.867,
    improvement_percent: 5.3,
    last_training_date: new Date(Date.now() - 86400000 * 3).toISOString(),
    next_training_scheduled: new Date(Date.now() + 86400000 * 4).toISOString(),
    backends_improved: ['deepseek-janus-pro', 'got-ocr-2.0'],
  };
}

// =============================================================================
// Threshold Settings API (Mock - to be implemented in backend)
// =============================================================================

export async function getConfidenceThresholds(): Promise<ConfidenceThresholds> {
  // TODO: Implement real API endpoint
  return {
    excellent: 0.95,
    high: 0.85,
    medium: 0.70,
    low: 0.50,
    fallback_trigger: 0.65,
    reject_trigger: 0.30,
  };
}

export async function updateConfidenceThresholds(
  thresholds: Partial<ConfidenceThresholds>
): Promise<ConfidenceThresholds> {
  // TODO: Implement real API endpoint
  logger.debug('Konfidenz-Schwellenwerte aktualisiert:', thresholds);
  return {
    excellent: 0.95,
    high: 0.85,
    medium: 0.70,
    low: 0.50,
    fallback_trigger: 0.65,
    reject_trigger: 0.30,
    ...thresholds,
  };
}
