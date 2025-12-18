/**
 * Types für OCR Review Feature
 */

// Queue Item vom Backend
export interface QueueItem {
    sample_id: string
    document_type: string
    priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
    priority_score: number
    reason: string
    ocr_text_preview: string
    confidence: number
    is_spot_check: boolean
    created_at: string
    file_path: string
    document_id: string | null  // Verknüpfung zu Document für ExtractedData
    // NEU: Extrahierte Daten direkt vom Backend (aus Document oder Sample)
    extracted_data?: import('@/features/extracted-data/types/extracted-data.types').ExtractedDocumentData | Record<string, unknown> | null
}

// Queue Stats vom Backend
export interface QueueStats {
    total_pending: number
    pending_by_priority: Record<string, number>
    pending_by_type: Record<string, number>
    spot_checks_pending: number
    coverage_gaps: CoverageGap[]
    oldest_item_days: number
}

export interface CoverageGap {
    document_type: string
    current_coverage: number
    target_coverage: number
    samples_needed: number
}

// Training Sample Details
export interface TrainingSampleDetail {
    id: string
    file_path: string
    file_hash: string
    thumbnail_path?: string
    ground_truth_text?: string
    language: string
    document_type: string
    difficulty?: string
    has_umlauts: boolean
    has_tables: boolean
    has_handwriting: boolean
    status: 'pending' | 'annotated' | 'verified' | 'rejected'
    auto_accepted: boolean
    auto_acceptance_confidence?: number
    needs_spot_check: boolean
    llm_review_status?: string
    llm_review_result?: LLMReviewResult
    llm_corrected_text?: string
    created_at: string
    extracted_fields?: Record<string, string>
    benchmarks?: Record<string, BenchmarkResult>
}

export interface BenchmarkResult {
    backend_name: string
    raw_text: string
    confidence_score: number
    cer?: number
    wer?: number
    umlaut_accuracy?: number
    processing_time_ms: number
}

// LLM Review
export interface LLMReviewResult {
    quality_score: number
    recommendation: 'accept' | 'reject' | 'needs_human'
    issues_found: string[]
    corrected_text?: string
    reasoning: string
    reviewed_at: string
}

// Verification Request
export interface VerifyRequest {
    approved: boolean
    corrected_text?: string
    correction_notes?: string
}

// Correction Types
export type CorrectionType =
    | 'UMLAUT'
    | 'DATE'
    | 'AMOUNT'
    | 'NUMBER'
    | 'NAME'
    | 'IBAN'
    | 'VAT_ID'
    | 'GENERAL'

// Correction Submit
export interface CorrectionCreate {
    document_id?: string
    training_sample_id?: string
    original_text: string
    corrected_text: string
    correction_type: CorrectionType
    field_corrected?: string
    backend_used: string
    confidence_before?: number
    applies_to_training: boolean
}

// Learned Weights
export interface LearnedWeights {
    weights: Record<string, number>
    last_updated: string
    samples_analyzed: number
    confidence: number
    error_patterns?: Record<string, BackendErrorPattern>
}

export interface BackendErrorPattern {
    backend_name: string
    total_corrections: number
    correction_types: Record<string, number>
    umlaut_errors: number
    number_errors: number
    date_errors: number
    currency_errors: number
    error_rate_score: number
}

// Session Stats (für Fortschritt)
export interface SessionStats {
    reviewed_today: number
    corrections_today: number
    accepted_today: number
    rejected_today: number
    skipped_today: number
    avg_review_time_seconds: number
}

// Next Sample Response
export interface NextSampleResponse {
    item: QueueItem | null
    sample?: TrainingSampleDetail
    llm_review?: LLMReviewResult
    remaining_count: number
}

// =============================================================================
// Strukturierte Review Types
// =============================================================================

/**
 * Flag-Grund warum ein Sample zur Review markiert wurde
 */
export type FlagType = 'coverage_gap' | 'low_confidence' | 'spot_check' | 'validation_error' | 'business_critical'

export interface FlagReason {
    type: FlagType
    label: string
    details: string
    severity: 'critical' | 'high' | 'medium' | 'low'
    affectedFields?: string[]
}

/**
 * Validierungsfehler für ein extrahiertes Feld
 */
export interface ValidationError {
    field: string
    fieldLabel: string
    error: string
    severity: 'error'
}

/**
 * Zustand eines editierbaren Feldes
 */
export type FieldStatus = 'normal' | 'low_confidence' | 'validation_error' | 'editing' | 'confirmed'

/**
 * Korrektur für ein einzelnes Feld
 */
export interface FieldCorrection {
    field: string
    fieldLabel: string
    originalValue: string | number | null
    correctedValue: string | number | null
    correctionType: CorrectionType
    timestamp: string
}

/**
 * Zustand der strukturierten Review
 */
export interface StructuredReviewState {
    isLoading: boolean
    hasExtractedData: boolean
    extractedData: import('@/features/extracted-data/types/extracted-data.types').ExtractedDocumentData | null
    flagReasons: FlagReason[]
    validationErrors: ValidationError[]
    lowConfidenceFields: string[]
    fieldCorrections: Map<string, FieldCorrection>
    confirmedFields: Set<string>
}

/**
 * Props für editierbare Feld-Komponente
 */
export interface EditableFieldProps<T = string> {
    fieldPath: string
    fieldLabel: string
    value: T | null | undefined
    confidence?: number
    confidenceThreshold?: number
    hasValidationError?: boolean
    validationErrorMessage?: string
    onEdit: (value: T) => void
    onConfirm: () => void
    disabled?: boolean
    type?: 'text' | 'number' | 'date' | 'currency'
    placeholder?: string
}

/**
 * Session-Progress für Review
 */
export interface ReviewProgress {
    reviewedToday: number
    correctionsToday: number
    targetToday: number
    avgReviewTimeSeconds: number
}
