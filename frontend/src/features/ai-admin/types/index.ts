/**
 * AI Admin Types
 *
 * TypeScript-Typen fuer AI Autonomy API.
 */

export type DecisionType =
  | 'document_classification'
  | 'entity_linking'
  | 'invoice_matching'
  | 'payment_matching'
  | 'ocr_correction'
  | 'anomaly_detection'
  | 'duplicate_detection'
  | 'auto_categorization';

export type ConfidenceLevel = 'high' | 'medium' | 'low';

export type ReviewAction = 'approved' | 'rejected' | 'modified';

export interface ThresholdConfig {
  decision_type: DecisionType;
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

export interface Decision {
  id: string;
  decision_type: DecisionType;
  document_id?: string;
  decision_value: Record<string, unknown>;
  confidence: number;
  calibrated_confidence?: number;
  confidence_level: ConfidenceLevel;
  auto_applied: boolean;
  requires_review: boolean;
  is_final: boolean;
  explanation?: Record<string, unknown>;
  reviewed_by_id?: string;
  reviewed_at?: string;
  review_action?: ReviewAction;
  created_at: string;
}

export interface ReviewRequest {
  action: ReviewAction;
  modified_value?: Record<string, unknown>;
  comment?: string;
}

export interface AccuracyStats {
  decision_type: DecisionType;
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

export interface ThresholdSuggestion {
  decision_type: DecisionType;
  current_auto: number;
  current_suggest: number;
  suggested_auto: number;
  suggested_suggest: number;
  reason: string;
}

export interface PendingReviewCount {
  [key: string]: number;
}

export interface LearningProgressReport {
  total_decisions: number;
  accuracy_trend: Array<{
    date: string;
    accuracy: number;
  }>;
  improvement_rate: number;
  recent_corrections: number;
  [key: string]: unknown;
}
