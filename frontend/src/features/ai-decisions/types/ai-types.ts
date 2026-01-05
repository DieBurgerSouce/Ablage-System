/**
 * AI Decision Review - TypeScript Types
 *
 * Typen fuer ML/AI Entscheidungen, Drift Detection,
 * SHAP Erklaerungen und A/B Testing.
 */

// =============================================================================
// Enums
// =============================================================================

export type ConfidenceLevel =
  | 'very_high'
  | 'high'
  | 'medium'
  | 'low'
  | 'very_low';

export type QualityDecision =
  | 'accept'
  | 'accept_with_warning'
  | 'request_review'
  | 'retry_different_backend'
  | 'reject';

export type DriftSeverity = 'none' | 'low' | 'medium' | 'high' | 'critical';

export type ExperimentStatus = 'draft' | 'running' | 'completed' | 'stopped';

// =============================================================================
// Drift Detection Types
// =============================================================================

export interface FeatureDrift {
  feature_name: string;
  drift_score: number;
  p_value?: number;
  is_drifted: boolean;
}

export interface DriftStatus {
  reference_samples: number;
  current_samples: number;
  min_samples_required: number;
  ready_for_detection: boolean;
  last_report: DriftReport | null;
  drift_threshold: number;
}

export interface DriftReport {
  report_id: string;
  timestamp: string;
  overall_drift_score: number;
  severity: DriftSeverity;
  dataset_drift_detected: boolean;
  feature_drifts: FeatureDrift[];
  prediction_drift: number | null;
  samples_reference: number;
  samples_current: number;
  recommendations: string[];
}

// =============================================================================
// SHAP Explainability Types
// =============================================================================

export interface FeatureContribution {
  feature_name: string;
  feature_value: number;
  shap_value: number;
  contribution_percent: number;
  direction: 'positive' | 'negative';
  explanation: string;
}

export interface RoutingExplanation {
  document_id: string;
  selected_backend: string;
  confidence: number;
  top_contributions: FeatureContribution[];
  alternative_backends: [string, number][];
  decision_summary: string;
  counterfactual: string | null;
}

export interface GlobalImportance {
  features: Record<string, number>;
}

// =============================================================================
// A/B Testing Types
// =============================================================================

export interface VariantConfig {
  name: string;
  backend: string;
  weight: number;
  config: Record<string, number>;
}

export interface VariantResult {
  name: string;
  samples: number;
  success_rate: number;
  avg_latency_ms: number;
  avg_accuracy: number | null;
}

export interface Experiment {
  experiment_id: string;
  name: string;
  status: ExperimentStatus;
  variants: VariantResult[];
  total_samples: number;
  winner: string | null;
  significance_reached: boolean;
}

export interface CreateExperimentRequest {
  name: string;
  description?: string;
  variants: VariantConfig[];
  allocation_method: 'sticky' | 'round_robin' | 'weighted';
  min_samples: number;
  duration_days?: number;
}

// =============================================================================
// Metrics Types
// =============================================================================

export interface MetricsSummary {
  routing: {
    status: string;
    method: string;
  };
  backends: {
    available: string[];
    default: string;
  };
  drift: {
    ready: boolean;
    last_score: number | null;
    samples: number;
  };
  experiments: {
    active_count: number;
    experiments: { id: string; name: string }[];
  };
}

// =============================================================================
// Confidence Calibration Types
// =============================================================================

export interface CalibrationModel {
  backend: string;
  method: string;
  parameters: Record<string, unknown>;
  samples_used: number;
  created_at: string;
  metrics: {
    ece: number;
    mce: number;
    brier_score: number;
  } | null;
}

export interface ConfidenceThresholds {
  excellent: number;
  high: number;
  medium: number;
  low: number;
  fallback_trigger: number;
  reject_trigger: number;
}

// =============================================================================
// AI Decision Review Types
// =============================================================================

export interface AIDecision {
  id: string;
  document_id: string;
  document_name: string;
  timestamp: string;
  backend_used: string;
  raw_confidence: number;
  calibrated_confidence: number;
  confidence_level: ConfidenceLevel;
  quality_decision: QualityDecision;
  explanation: RoutingExplanation | null;
  needs_review: boolean;
  reviewed_at: string | null;
  reviewed_by: string | null;
  review_outcome: 'approved' | 'corrected' | 'rejected' | null;
}

export interface AIDecisionFilters {
  confidence_level?: ConfidenceLevel[];
  quality_decision?: QualityDecision[];
  needs_review?: boolean;
  backend?: string[];
  date_from?: string;
  date_to?: string;
}

export interface AIDecisionStats {
  total_decisions: number;
  pending_review: number;
  approved: number;
  corrected: number;
  rejected: number;
  avg_confidence: number;
  by_backend: Record<string, number>;
  by_confidence_level: Record<ConfidenceLevel, number>;
}

// =============================================================================
// Learning Stats Types
// =============================================================================

export interface LearningStats {
  total_corrections: number;
  corrections_applied: number;
  model_accuracy_before: number;
  model_accuracy_after: number;
  improvement_percent: number;
  last_training_date: string | null;
  next_training_scheduled: string | null;
  backends_improved: string[];
}
