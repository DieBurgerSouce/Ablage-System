/**
 * Document Model Types
 *
 * Typen fuer Dokumente und dokumentbezogene Operationen.
 */

import type { SoftDeleteFields } from '../api/common';

// ==================== Document Status ====================

/**
 * OCR processing status
 */
export type OcrStatus = 'pending' | 'processing' | 'completed' | 'failed';

/**
 * Quick classification status
 */
export type ClassificationStatus = 'pending' | 'processing' | 'completed' | 'failed';

/**
 * Document direction (Eingangs-/Ausgangsrechnung)
 */
export type DocumentDirection = 'incoming' | 'outgoing' | 'unknown';

/**
 * Entity match method
 */
export type EntityMatchMethod = 'vat_id' | 'iban' | 'name';

/**
 * Entity type
 */
export type EntityType = 'supplier' | 'customer' | 'both';

// ==================== Bounding Box ====================

/**
 * OCR bounding box for text regions
 */
export interface BoundingBox {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    confidence: number;
    text?: string;
}

// ==================== Quick Classification ====================

/**
 * Rename suggestion from quick classification
 */
export interface RenameSuggestion {
    suggestedFilename: string;
    supplierName: string;
    invoiceNumber: string;
    source: 'entity_match' | 'ocr_extraction';
    confidence: number;
    applied?: boolean;
    appliedFilename?: string;
}

/**
 * Quick classification result
 */
export interface QuickClassificationResult {
    direction?: DocumentDirection;
    confidence?: number;
    reason?: string;
    tagAssigned?: boolean;
    tagName?: string;
    // Business Entity Matching
    matchedEntityId?: string;
    matchedEntityName?: string;
    matchedEntityType?: EntityType;
    entityMatchMethod?: EntityMatchMethod;
    entityConfidence?: number;
    entityAutoLinked?: boolean;
    // Rename Suggestion
    renameSuggestion?: RenameSuggestion;
}

// ==================== OCR Results ====================

/**
 * Single page OCR result
 */
export interface OcrPageResult {
    text: string;
    confidence: number;
    boxes?: BoundingBox[];
}

/**
 * Complete OCR results
 */
export interface OcrResults {
    pages: OcrPageResult[];
}

// ==================== Document ====================

/**
 * Document entity (frontend format, camelCase)
 */
export interface Document {
    id: string;
    name: string;
    title?: string;
    mimeType: string;
    size: number;
    createdAt: string;
    ocrStatus: OcrStatus;
    ocrConfidence?: number;
    thumbnail?: string;
    fileUrl?: string;
    extractedText?: string;
    ocrResults?: OcrResults;
    /** Celery Task ID for OCR progress tracking */
    taskId?: string;
    /** Quick Classification Status */
    quickClassificationStatus?: ClassificationStatus;
    /** Quick Classification Result */
    quickClassificationResult?: QuickClassificationResult;
}

/**
 * Document entity (backend format, snake_case)
 * Used for API request/response transformation
 */
export interface DocumentBackend {
    id: string;
    filename: string;
    original_filename: string;
    file_size: number;
    mime_type: string;
    status: OcrStatus;
    ocr_confidence?: number;
    extracted_text?: string;
    file_path?: string;
    processing_job_id?: string;
    quick_classification_status?: ClassificationStatus;
    quick_classification_result?: {
        direction?: DocumentDirection;
        confidence?: number;
        reason?: string;
        tag_assigned?: boolean;
        tag_name?: string;
        matched_entity_id?: string;
        matched_entity_name?: string;
        matched_entity_type?: EntityType;
        entity_match_method?: EntityMatchMethod;
        entity_confidence?: number;
        entity_auto_linked?: boolean;
        rename_suggestion?: {
            suggested_filename: string;
            supplier_name: string;
            invoice_number: string;
            source: 'entity_match' | 'ocr_extraction';
            confidence: number;
            applied?: boolean;
            applied_filename?: string;
        };
    };
}

// ==================== Document Filters ====================

/**
 * Document filter parameters
 */
export interface DocumentFilter {
    type?: string;
    ocrStatus?: string;
    dateRange?: string;
    query?: string;
    sort?: 'date_asc' | 'date_desc' | 'name_asc' | 'name_desc';
    limit?: number;
}

// ==================== Document Operations ====================

/**
 * Classification confirmation request
 */
export interface ClassificationConfirmRequest {
    invoice_direction: DocumentDirection;
    user_overridden: boolean;
}

/**
 * Classification confirmation response
 */
export interface ClassificationConfirmResponse {
    status: string;
    document_id: string;
    applied_tag: string;
    invoice_direction: DocumentDirection;
}

/**
 * Rename confirmation response
 */
export interface RenameConfirmResponse {
    success: boolean;
    document_id: string;
    old_filename: string;
    new_filename: string;
    message: string;
}

/**
 * Extracted invoice data
 */
export interface ExtractedInvoiceData {
    invoice_direction?: DocumentDirection;
    invoice_direction_confidence?: number;
    invoice_direction_reason?: string;
}

/**
 * Extracted document data
 */
export interface ExtractedData {
    invoice?: ExtractedInvoiceData;
}

// ==================== Document with GDPR ====================

/**
 * Document with soft delete support
 */
export interface DocumentWithGdpr extends Document, SoftDeleteFields {}

// ==================== Document Tags ====================

/**
 * Document tag
 */
export interface DocumentTag {
    id: string;
    name: string;
    color?: string;
    description?: string;
}

/**
 * Document with tags
 */
export interface DocumentWithTags extends Document {
    tags: DocumentTag[];
}
