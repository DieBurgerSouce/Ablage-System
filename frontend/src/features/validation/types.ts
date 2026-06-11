/**
 * Validation Feature Types
 *
 * TypeScript-Definitionen für das OCR-Training und Validierungs-System.
 * Enterprise-Level mit vollständiger Type-Safety.
 */

// ==================== Enums ====================

export const TrainingSampleStatus = {
  PENDING: 'pending',
  IN_PROGRESS: 'in_progress',
  ANNOTATED: 'annotated',
  VERIFIED: 'verified',
  REJECTED: 'rejected',
} as const;
export type TrainingSampleStatus = (typeof TrainingSampleStatus)[keyof typeof TrainingSampleStatus];

export const CorrectionType = {
  UMLAUT: 'umlaut',
  DATE: 'date',
  AMOUNT: 'amount',
  NAME: 'name',
  IBAN: 'iban',
  VAT_ID: 'vat_id',
  GENERAL: 'general',
} as const;
export type CorrectionType = (typeof CorrectionType)[keyof typeof CorrectionType];

export const TrainingBatchType = {
  RANDOM: 'random',
  STRATIFIED: 'stratified',
  TARGETED: 'targeted',
  LOW_CONFIDENCE: 'low_confidence',
} as const;
export type TrainingBatchType = (typeof TrainingBatchType)[keyof typeof TrainingBatchType];

export const TrainingBatchStatus = {
  DRAFT: 'draft',
  ACTIVE: 'active',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
} as const;
export type TrainingBatchStatus = (typeof TrainingBatchStatus)[keyof typeof TrainingBatchStatus];

// ==================== Label Maps (Deutsche UI) ====================

export const SAMPLE_STATUS_LABELS: Record<TrainingSampleStatus, string> = {
  [TrainingSampleStatus.PENDING]: 'Ausstehend',
  [TrainingSampleStatus.IN_PROGRESS]: 'In Bearbeitung',
  [TrainingSampleStatus.ANNOTATED]: 'Annotiert',
  [TrainingSampleStatus.VERIFIED]: 'Verifiziert',
  [TrainingSampleStatus.REJECTED]: 'Abgelehnt',
};

export const CORRECTION_TYPE_LABELS: Record<CorrectionType, string> = {
  [CorrectionType.UMLAUT]: 'Umlaut-Fehler',
  [CorrectionType.DATE]: 'Datumsfehler',
  [CorrectionType.AMOUNT]: 'Betragsfehler',
  [CorrectionType.NAME]: 'Namensfehler',
  [CorrectionType.IBAN]: 'IBAN-Fehler',
  [CorrectionType.VAT_ID]: 'USt-IdNr-Fehler',
  [CorrectionType.GENERAL]: 'Allgemeiner Fehler',
};

export const BATCH_TYPE_LABELS: Record<TrainingBatchType, string> = {
  [TrainingBatchType.RANDOM]: 'Zufällig',
  [TrainingBatchType.STRATIFIED]: 'Stratifiziert',
  [TrainingBatchType.TARGETED]: 'Gezielt',
  [TrainingBatchType.LOW_CONFIDENCE]: 'Niedrige Konfidenz',
};

export const BATCH_STATUS_LABELS: Record<TrainingBatchStatus, string> = {
  [TrainingBatchStatus.DRAFT]: 'Entwurf',
  [TrainingBatchStatus.ACTIVE]: 'Aktiv',
  [TrainingBatchStatus.COMPLETED]: 'Abgeschlossen',
  [TrainingBatchStatus.CANCELLED]: 'Abgebrochen',
};

// ==================== Training Sample Types ====================

export interface SampleBenchmark {
  id: string;
  training_sample_id: string;
  backend_name: string;
  backend_version: string | null;
  raw_text: string | null;
  confidence_score: number | null;
  cer: number | null;
  wer: number | null;
  umlaut_accuracy: number | null;
  capitalization_accuracy: number | null;
  field_accuracies: Record<string, number> | null;
  error_patterns: string[] | null;
  processing_time_ms: number | null;
  processed_at: string | null;
}

export interface TrainingSample {
  id: string;
  file_path: string;
  file_hash: string;
  thumbnail_path: string | null;
  ground_truth_text: string | null;
  language: string;
  document_type: string | null;
  difficulty: 'easy' | 'medium' | 'hard';
  has_umlauts: boolean;
  has_fraktur: boolean;
  has_tables: boolean;
  has_handwriting: boolean;
  has_stamps: boolean;
  has_signatures: boolean;
  umlaut_words: string[];
  extracted_fields: Record<string, unknown>;
  status: TrainingSampleStatus;
  annotated_by_id: string | null;
  verified_by_id: string | null;
  annotation_notes: string | null;
  created_at: string;
  updated_at: string;
  annotated_at: string | null;
  verified_at: string | null;
  // Optional: Benchmark-Daten (werden separat geladen)
  benchmarks?: SampleBenchmark[];
  // Cached Konfidenz-Wert aus Benchmarks
  avg_confidence?: number;
}

export interface TrainingSampleListResponse {
  total: number;
  limit: number;
  offset: number;
  samples: TrainingSample[];
}

export interface TrainingSampleCreate {
  file_path: string;
  file_hash: string;
  thumbnail_path?: string;
  ground_truth_text?: string;
  language?: string;
  document_type?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  has_umlauts?: boolean;
  has_fraktur?: boolean;
  has_tables?: boolean;
  has_handwriting?: boolean;
  has_stamps?: boolean;
  has_signatures?: boolean;
  umlaut_words?: string[];
  extracted_fields?: Record<string, unknown>;
}

export interface TrainingSampleUpdate {
  ground_truth_text?: string;
  language?: string;
  document_type?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  has_umlauts?: boolean;
  has_fraktur?: boolean;
  has_tables?: boolean;
  has_handwriting?: boolean;
  umlaut_words?: string[];
  extracted_fields?: Record<string, unknown>;
  annotation_notes?: string;
  status?: TrainingSampleStatus;
}

// ==================== Benchmark Types ====================

export interface Benchmark {
  id: string;
  training_sample_id: string;
  backend_name: string;
  backend_version: string | null;
  raw_text: string | null;
  confidence_score: number | null;
  cer: number | null;
  wer: number | null;
  umlaut_accuracy: number | null;
  capitalization_accuracy: number | null;
  field_accuracies: Record<string, number>;
  error_patterns: Record<string, number>;
  insertions: number;
  deletions: number;
  substitutions: number;
  processing_time_ms: number | null;
  gpu_memory_mb: number | null;
  processed_at: string;
}

export interface BackendComparisonResponse {
  backends: Record<string, Record<string, unknown>>;
  best_backend: string | null;
  sample_count: number;
}

// ==================== Correction Types ====================

export interface Correction {
  id: string;
  document_id: string | null;
  original_text: string;
  corrected_text: string;
  correction_type: CorrectionType;
  field_corrected: string | null;
  backend_used: string;
  confidence_before: number | null;
  applies_to_training: boolean;
  learning_processed: boolean;
  learning_processed_at: string | null;
  corrector_id: string | null;
  created_at: string;
}

export interface CorrectionCreate {
  document_id?: string;
  original_text: string;
  corrected_text: string;
  correction_type: CorrectionType;
  field_corrected?: string;
  backend_used: string;
  confidence_before?: number;
  applies_to_training?: boolean;
}

export interface CorrectionListResponse {
  total: number;
  page: number;
  per_page: number;
  corrections: Correction[];
}

// ==================== Batch Types ====================

export interface StratificationConfig {
  by_document_type: boolean;
  by_language: boolean;
  by_difficulty: boolean;
  type_weights: Record<string, number>;
  language_weights: Record<string, number>;
}

export interface TrainingBatch {
  id: string;
  name: string;
  description: string | null;
  batch_type: TrainingBatchType;
  stratification_config: StratificationConfig | null;
  target_size: number;
  actual_size: number;
  status: TrainingBatchStatus;
  items_pending: number;
  items_completed: number;
  progress_percent: number;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface BatchItem {
  id: string;
  batch_id: string;
  training_sample_id: string;
  sequence_number: number;
  assigned_to_id: string | null;
  status: string;
  validation_notes: string | null;
  validation_time_seconds: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  sample: TrainingSample | null;
}

export interface BatchCreate {
  name: string;
  description?: string;
  batch_type?: TrainingBatchType;
  target_size?: number;
  stratification_config?: StratificationConfig;
}

export interface BatchDetailResponse extends TrainingBatch {
  items: BatchItem[];
}

export interface BatchListResponse {
  total: number;
  batches: TrainingBatch[];
}

export interface BatchItemUpdate {
  status?: string;
  validation_notes?: string;
  validation_time_seconds?: number;
}

// ==================== Statistics Types ====================

export interface BackendStats {
  backend_name: string;
  samples_processed: number;
  avg_cer: number | null;
  avg_wer: number | null;
  avg_umlaut_accuracy: number | null;
  avg_processing_time_ms: number | null;
  p50_cer: number | null;
  p90_cer: number | null;
  p95_cer: number | null;
}

export interface TrainingOverviewStats {
  total_samples: number;
  verified_samples: number;
  pending_annotations: number;
  active_batches: number;
  recent_corrections_24h: number;
  unprocessed_corrections: number;
  samples_by_language: Record<string, number>;
  samples_by_document_type: Record<string, number>;
}

export interface TrainingStatsResponse {
  overview: TrainingOverviewStats;
  backend_stats?: BackendStats[];
}

// ==================== Filter Types ====================

export interface ValidationFilters {
  status?: TrainingSampleStatus | 'all';
  language?: string;
  document_type?: string;
  has_ground_truth?: boolean;
  verified_only?: boolean;
  search?: string;
}

export interface ValidationPagination {
  limit: number;
  offset: number;
}

// ==================== UI Helper Types ====================

export interface ValidationQueueItem {
  id: string;
  documentName: string;
  documentType: string | null;
  confidence: number;
  status: TrainingSampleStatus;
  createdAt: string;
  fieldsToReview: number;
  hasUmlauts: boolean;
  hasTables: boolean;
}

/**
 * Berechnet die durchschnittliche Konfidenz aus Benchmark-Daten.
 */
export function calculateConfidenceFromBenchmarks(benchmarks?: SampleBenchmark[]): number {
  if (!benchmarks || benchmarks.length === 0) {
    return 0.85; // Default wenn keine Benchmarks vorhanden
  }

  const validScores = benchmarks
    .map(b => b.confidence_score)
    .filter((score): score is number => score !== null && score !== undefined);

  if (validScores.length === 0) {
    return 0.85;
  }

  return validScores.reduce((sum, score) => sum + score, 0) / validScores.length;
}

/**
 * Holt die Konfidenz für ein spezifisches Feld aus Benchmark-Daten.
 */
export function getFieldConfidenceFromBenchmarks(
  benchmarks: SampleBenchmark[] | undefined,
  fieldName: string
): number {
  if (!benchmarks || benchmarks.length === 0) {
    return 0.85;
  }

  // Suche nach Feld-spezifischer Konfidenz in den Benchmarks
  for (const benchmark of benchmarks) {
    if (benchmark.field_accuracies && benchmark.field_accuracies[fieldName] !== undefined) {
      return benchmark.field_accuracies[fieldName];
    }
  }

  // Fallback auf durchschnittliche Konfidenz
  return calculateConfidenceFromBenchmarks(benchmarks);
}

/**
 * Konvertiert ein TrainingSample zu einem ValidationQueueItem für die UI
 */
export function toValidationQueueItem(sample: TrainingSample): ValidationQueueItem {
  // Berechne Anzahl der zu prüfenden Felder
  const fieldsToReview = Object.keys(sample.extracted_fields || {}).length;

  // Extrahiere Dokumentname aus file_path
  const documentName = sample.file_path.split('/').pop() || sample.file_path;

  // Durchschnittliche Konfidenz aus Benchmark-Daten oder cached Wert
  const confidence = sample.avg_confidence ?? calculateConfidenceFromBenchmarks(sample.benchmarks);

  return {
    id: sample.id,
    documentName,
    documentType: sample.document_type,
    confidence,
    status: sample.status,
    createdAt: sample.created_at,
    fieldsToReview,
    hasUmlauts: sample.has_umlauts,
    hasTables: sample.has_tables,
  };
}

// ==================== Color Utilities ====================

export function getStatusColor(status: TrainingSampleStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  const colors: Record<TrainingSampleStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
    [TrainingSampleStatus.PENDING]: 'outline',
    [TrainingSampleStatus.IN_PROGRESS]: 'secondary',
    [TrainingSampleStatus.ANNOTATED]: 'secondary',
    [TrainingSampleStatus.VERIFIED]: 'default',
    [TrainingSampleStatus.REJECTED]: 'destructive',
  };
  return colors[status];
}

export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.9) return 'text-green-600';
  if (confidence >= 0.7) return 'text-yellow-600';
  return 'text-red-600';
}

export function getConfidenceBgColor(confidence: number): string {
  if (confidence >= 0.9) return 'bg-green-500/10';
  if (confidence >= 0.7) return 'bg-yellow-500/10';
  return 'bg-red-500/10';
}
