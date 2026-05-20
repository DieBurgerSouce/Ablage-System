/**
 * AI Autonomy API Client
 *
 * TypeScript Client für die AI Autonomy Endpoints.
 */

import { api, handleApiError } from '@/lib/api';

// =============================================================================
// Types
// =============================================================================

export interface ThresholdConfig {
  decision_type: string;
  auto_threshold: number;
  suggest_threshold: number;
  is_enabled: boolean;
  allow_auto_apply: boolean;
  display_name?: string;
  description?: string;
}

export interface ThresholdUpdateRequest {
  auto_threshold?: number;
  suggest_threshold?: number;
  is_enabled?: boolean;
  allow_auto_apply?: boolean;
}

export interface AIDecision {
  id: string;
  decision_type: string;
  document_id?: string;
  decision_value: Record<string, unknown>;
  confidence: number;
  calibrated_confidence?: number;
  confidence_level: 'auto' | 'suggest' | 'manual';
  auto_applied: boolean;
  requires_review: boolean;
  is_final: boolean;
  explanation?: Record<string, unknown>;
  reviewed_by_id?: string;
  reviewed_at?: string;
  review_action?: 'approved' | 'rejected' | 'modified';
  created_at: string;
}

export interface ReviewRequest {
  action: 'approved' | 'rejected' | 'modified';
  modified_value?: Record<string, unknown>;
  comment?: string;
}

export interface CategorySuggestion {
  category: string;
  display_name: string;
  confidence: number;
  is_primary: boolean;
}

export interface MatchCandidate {
  document_id: string;
  match_type: string;
  confidence: number;
  feature_scores: Record<string, number>;
  matched_values: Record<string, unknown>;
}

export interface AnomalyItem {
  anomaly_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  confidence: number;
  description: string;
  recommendation?: string;
  details: Record<string, unknown>;
}

export interface AnomalyCheckResponse {
  has_anomalies: boolean;
  is_suspicious: boolean;
  risk_score: number;
  anomalies: AnomalyItem[];
}

export interface DuplicateCandidate {
  document_id: string;
  duplicate_type: string;
  similarity: number;
  matched_fields: string[];
}

export interface DuplicateCheckResponse {
  has_duplicates: boolean;
  candidates: DuplicateCandidate[];
}

export interface AccuracyStats {
  decision_type: string;
  total_decisions: number;
  auto_applied: number;
  reviewed: number;
  approved: number;
  corrected: number;
  rejected: number;
  accuracy_rate: number;
  correction_rate: number;
  avg_confidence: number;
}

export interface ThresholdAdjustmentSuggestion {
  decision_type: string;
  current_auto: number;
  current_suggest: number;
  suggested_auto: number;
  suggested_suggest: number;
  reason: string;
}

export interface LearningReport {
  generated_at: string;
  period_days: number;
  company_id?: string;
  summary: {
    total_decision_types: number;
    overall_accuracy: number;
    overall_correction_rate: number;
    pending_adjustments: number;
  };
  by_decision_type: Array<{
    decision_type: string;
    total_decisions: number;
    auto_applied: number;
    reviewed: number;
    approved: number;
    corrected: number;
    rejected: number;
    accuracy_rate: number;
    correction_rate: number;
    avg_confidence: number;
  }>;
  suggested_adjustments: Array<{
    decision_type: string;
    current_auto_threshold: number;
    current_suggest_threshold: number;
    suggested_auto_threshold: number;
    suggested_suggest_threshold: number;
    reason: string;
  }>;
}

// =============================================================================
// Decision Endpoints
// =============================================================================

export async function listDecisions(params?: {
  decision_type?: string;
  requires_review?: boolean;
  limit?: number;
  offset?: number;
}): Promise<AIDecision[]> {
  try {
    const searchParams = new URLSearchParams();
    if (params?.decision_type) searchParams.set('decision_type', params.decision_type);
    if (params?.requires_review !== undefined) searchParams.set('requires_review', String(params.requires_review));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));

    const response = await api.get(`/ai/decisions?${searchParams}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getDecision(decisionId: string): Promise<AIDecision> {
  try {
    const response = await api.get(`/ai/decisions/${decisionId}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function reviewDecision(
  decisionId: string,
  request: ReviewRequest
): Promise<{ success: boolean; message: string }> {
  try {
    const response = await api.post(`/ai/decisions/${decisionId}/review`, request);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

// =============================================================================
// Threshold Endpoints
// =============================================================================

export async function listThresholds(): Promise<ThresholdConfig[]> {
  try {
    const response = await api.get('/ai/thresholds');
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function updateThreshold(
  decisionType: string,
  request: ThresholdUpdateRequest
): Promise<{ success: boolean; message: string }> {
  try {
    const response = await api.put(`/ai/thresholds/${decisionType}`, request);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

// =============================================================================
// Document AI Endpoints
// =============================================================================

export async function categorizeDocument(
  documentId: string,
  autoApply = true
): Promise<{
  decision_id: string;
  category: string;
  display_name: string;
  confidence: number;
  confidence_level: string;
  auto_applied: boolean;
}> {
  try {
    const response = await api.post(`/ai/documents/${documentId}/categorize?auto_apply=${autoApply}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getCategorySuggestions(documentId: string): Promise<CategorySuggestion[]> {
  try {
    const response = await api.get(`/ai/documents/${documentId}/category-suggestions`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function findDocumentMatches(
  documentId: string,
  limit = 10
): Promise<MatchCandidate[]> {
  try {
    const response = await api.get(`/ai/documents/${documentId}/matches?limit=${limit}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function checkDocumentAnomalies(documentId: string): Promise<AnomalyCheckResponse> {
  try {
    const response = await api.get(`/ai/documents/${documentId}/anomalies`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function checkDocumentDuplicates(
  documentId: string,
  includeNear = true
): Promise<DuplicateCheckResponse> {
  try {
    const response = await api.get(`/ai/documents/${documentId}/duplicates?include_near=${includeNear}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

// =============================================================================
// Statistics & Learning Endpoints
// =============================================================================

export async function getAccuracyStats(days = 30): Promise<AccuracyStats[]> {
  try {
    const response = await api.get(`/ai/stats/accuracy?days=${days}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getLearningProgress(days = 30): Promise<LearningReport> {
  try {
    const response = await api.get(`/ai/stats/learning?days=${days}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getThresholdSuggestions(days = 30): Promise<ThresholdAdjustmentSuggestion[]> {
  try {
    const response = await api.get(`/ai/stats/threshold-suggestions?days=${days}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function applyThresholdSuggestion(
  decisionType: string
): Promise<{
  success: boolean;
  message: string;
  new_auto_threshold: number;
  new_suggest_threshold: number;
}> {
  try {
    const response = await api.post(`/ai/stats/threshold-suggestions/${decisionType}/apply`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getPendingReviewCount(): Promise<Record<string, number>> {
  try {
    const response = await api.get('/ai/pending-review-count');
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}
