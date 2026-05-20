/**
 * Types fuer Batch-OCR-Korrektur Feature
 */

export type BatchCorrectionStatus = 'pending' | 'reviewed' | 'corrected' | 'confirmed'

export interface OcrBatchDocument {
    id: string
    filename: string
    document_type: string
    ocr_confidence: number
    status: BatchCorrectionStatus
    created_at: string
    extracted_fields: Record<string, OcrExtractedField>
}

export interface OcrExtractedField {
    value: string | number | null
    confidence: number
    field_type: 'text' | 'number' | 'date' | 'currency'
}

export interface BatchCorrectionPayload {
    document_id: string
    corrections: Array<{
        field: string
        original_value: string
        corrected_value: string
        correction_type: string
    }>
}

export interface BatchConfirmPayload {
    document_ids: string[]
}

export interface BatchDocumentsResponse {
    items: OcrBatchDocument[]
    total: number
    page: number
    per_page: number
}

export type ConfidenceRange = 'all' | 'low' | 'medium' | 'high'

export interface BatchFilterState {
    documentType: string
    confidenceRange: ConfidenceRange
    status: string
    page: number
    perPage: number
}
