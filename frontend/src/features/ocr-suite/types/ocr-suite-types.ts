// OCR Suite Type Definitions

// ============================================================================
// OCR Region Types
// ============================================================================

export interface OcrRegionBackend {
  id: string;
  document_id: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  confidence: number;
  field_type: string;
}

export interface OcrRegion {
  id: string;
  documentId: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  confidence: number;
  fieldType: string;
}

// ============================================================================
// OCR Feedback Types
// ============================================================================

export interface OcrFeedbackRequest {
  regionId: string;
  correctedText: string;
  isCorrect: boolean;
}

export interface OcrFeedbackBackend {
  region_id: string;
  corrected_text: string;
  is_correct: boolean;
}

// ============================================================================
// Self-Learning Stats Types
// ============================================================================

export interface SelfLearningStatsBackend {
  total_corrections: number;
  accuracy_improvement: number;
  documents_processed: number;
  active_models: number;
  last_training: string | null;
}

export interface SelfLearningStats {
  totalCorrections: number;
  accuracyImprovement: number;
  documentsProcessed: number;
  activeModels: number;
  lastTraining: string | null;
}

// ============================================================================
// Document Version Types
// ============================================================================

export interface DocumentVersionBackend {
  id: string;
  version_number: number;
  created_at: string;
  ocr_text: string;
  metadata: Record<string, unknown>;
}

export interface DocumentVersion {
  id: string;
  versionNumber: number;
  createdAt: string;
  ocrText: string;
  metadata: Record<string, unknown>;
}

// ============================================================================
// OCR Template Types
// ============================================================================

export interface TemplateZoneBackend {
  id: string;
  name: string;
  field_type: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TemplateZone {
  id: string;
  name: string;
  fieldType: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface OcrTemplateBackend {
  id: string;
  name: string;
  document_type: string;
  zones: TemplateZoneBackend[];
  created_at: string;
  updated_at: string;
}

export interface OcrTemplate {
  id: string;
  name: string;
  documentType: string;
  zones: TemplateZone[];
  createdAt: string;
  updatedAt: string;
}

// ============================================================================
// Transformer Functions
// ============================================================================

export function transformOcrRegion(backend: OcrRegionBackend): OcrRegion {
  return {
    id: backend.id,
    documentId: backend.document_id,
    page: backend.page,
    x: backend.x,
    y: backend.y,
    width: backend.width,
    height: backend.height,
    text: backend.text,
    confidence: backend.confidence,
    fieldType: backend.field_type,
  };
}

export function transformOcrFeedback(frontend: OcrFeedbackRequest): OcrFeedbackBackend {
  return {
    region_id: frontend.regionId,
    corrected_text: frontend.correctedText,
    is_correct: frontend.isCorrect,
  };
}

export function transformSelfLearningStats(
  backend: SelfLearningStatsBackend
): SelfLearningStats {
  return {
    totalCorrections: backend.total_corrections,
    accuracyImprovement: backend.accuracy_improvement,
    documentsProcessed: backend.documents_processed,
    activeModels: backend.active_models,
    lastTraining: backend.last_training,
  };
}

export function transformDocumentVersion(
  backend: DocumentVersionBackend
): DocumentVersion {
  return {
    id: backend.id,
    versionNumber: backend.version_number,
    createdAt: backend.created_at,
    ocrText: backend.ocr_text,
    metadata: backend.metadata,
  };
}

export function transformTemplateZone(backend: TemplateZoneBackend): TemplateZone {
  return {
    id: backend.id,
    name: backend.name,
    fieldType: backend.field_type,
    x: backend.x,
    y: backend.y,
    width: backend.width,
    height: backend.height,
  };
}

export function transformOcrTemplate(backend: OcrTemplateBackend): OcrTemplate {
  return {
    id: backend.id,
    name: backend.name,
    documentType: backend.document_type,
    zones: backend.zones.map(transformTemplateZone),
    createdAt: backend.created_at,
    updatedAt: backend.updated_at,
  };
}
