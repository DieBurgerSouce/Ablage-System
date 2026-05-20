/**
 * OCR Self-Learning API Client
 *
 * API für das Self-Learning OCR System.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface CorrectionFeedbackRequest {
  document_id: string;
  field_name: string;
  original_value: string;
  corrected_value: string;
  ocr_backend: string;
  original_confidence: number;
  correction_type?: 'text' | 'amount' | 'date' | 'entity';
}

export interface CorrectionFeedbackResponse {
  processed: boolean;
  learning_mode: string;
  confidence_adjustment: number;
  training_sample_id?: string;
  rollback_triggered: boolean;
  adjustments: Array<{
    type: string;
    backend: string;
    field: string;
    value: number;
  }>;
}

export interface CalibratedConfidenceRequest {
  backend: string;
  field: string;
  raw_confidence: number;
}

export interface CalibratedConfidenceResponse {
  backend: string;
  field: string;
  raw_confidence: number;
  calibrated_confidence: number;
  adjustment_applied: number;
}

export interface ConfidenceStats {
  backend_adjustments: Record<string, number>;
  field_adjustments: Record<string, Record<string, number>>;
  learning_mode: string;
}

export interface ABTestStartRequest {
  test_id: string;
  candidate_version: 'candidate_a' | 'candidate_b';
  traffic_split?: number;
  min_samples?: number;
  max_duration_days?: number;
}

export interface ABTestConfig {
  test_id: string;
  baseline_version: string;
  candidate_version: string;
  traffic_split: number;
  min_samples: number;
  max_duration_days: number;
  started_at: string;
}

export interface ABTestResult {
  test_id: string;
  improvement_percent: number;
  is_significant: boolean;
  recommendation: 'promote' | 'rollback' | 'continue';
  confidence_level: number;
  baseline_quality_score: number;
  candidate_quality_score: number;
}

export interface LearningStats {
  learning_mode: string;
  training_samples: number;
  total_corrections: number;
  backend_adjustments: Record<string, number>;
  field_adjustments: Record<string, Record<string, number>>;
  active_ab_tests: Array<{
    test_id: string;
    candidate: string;
    traffic_split: number;
    started_at: string;
    is_expired: boolean;
  }>;
  model_metrics: Record<string, {
    total_documents: number;
    corrections_count: number;
    accuracy_rate: number;
    quality_score: number;
  }>;
}

export interface ModelVersionResponse {
  model_version: string;
  test_id?: string;
}

// ==================== API Functions ====================

/**
 * Übermittle Korrektur-Feedback
 */
export async function submitCorrectionFeedback(
  feedback: CorrectionFeedbackRequest
): Promise<CorrectionFeedbackResponse> {
  const response = await apiClient.post<CorrectionFeedbackResponse>(
    '/ocr-learning/feedback',
    feedback
  );
  return response.data;
}

/**
 * Liefere kalibrierte Confidence
 */
export async function getCalibratedConfidence(
  request: CalibratedConfidenceRequest
): Promise<CalibratedConfidenceResponse> {
  const response = await apiClient.post<CalibratedConfidenceResponse>(
    '/ocr-learning/calibrate',
    request
  );
  return response.data;
}

/**
 * Liefere Confidence-Statistiken
 */
export async function getConfidenceStats(
  backend?: string
): Promise<ConfidenceStats> {
  const response = await apiClient.get<ConfidenceStats>(
    '/ocr-learning/confidence-stats',
    { params: backend ? { backend } : undefined }
  );
  return response.data;
}

/**
 * Starte A/B Test
 */
export async function startABTest(
  request: ABTestStartRequest
): Promise<ABTestConfig> {
  const response = await apiClient.post<ABTestConfig>(
    '/ocr-learning/ab-test/start',
    request
  );
  return response.data;
}

/**
 * Liefere A/B Test Ergebnis
 */
export async function getABTestResult(testId: string): Promise<ABTestResult> {
  const response = await apiClient.get<ABTestResult>(
    `/ocr-learning/ab-test/${testId}`
  );
  return response.data;
}

/**
 * Beende A/B Test
 */
export async function endABTest(
  testId: string,
  action: 'promote' | 'rollback'
): Promise<{ success: boolean; test_id: string; action: string; result: { improvement_percent: number; recommendation: string } }> {
  const response = await apiClient.post(
    `/ocr-learning/ab-test/${testId}/end`,
    { action }
  );
  return response.data;
}

/**
 * Liefere Learning-Statistiken
 */
export async function getLearningStats(): Promise<LearningStats> {
  const response = await apiClient.get<LearningStats>('/ocr-learning/stats');
  return response.data;
}

/**
 * Setze Learning-Modus
 */
export async function setLearningMode(
  mode: 'aggressive' | 'cautious' | 'batch'
): Promise<{ success: boolean; learning_mode: string }> {
  const response = await apiClient.post(`/ocr-learning/mode/${mode}`);
  return response.data;
}

/**
 * Liefere aktuelle Modell-Version
 */
export async function getCurrentModelVersion(
  testId?: string
): Promise<ModelVersionResponse> {
  const response = await apiClient.get<ModelVersionResponse>(
    '/ocr-learning/model-version',
    { params: testId ? { test_id: testId } : undefined }
  );
  return response.data;
}
