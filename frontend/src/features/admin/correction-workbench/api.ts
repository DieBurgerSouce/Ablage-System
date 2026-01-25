/**
 * Correction Workbench API
 * API-Funktionen fuer OCR-Korrektur-Workbench
 */

import { api } from '@/lib/api';
import type {
  LowConfidenceDocument,
  CorrectionSubmission,
  CorrectionStats,
  TrainingExportConfig,
  TrainingExportResult,
  QueueFilters,
} from './types';

const API_BASE = '/api/v1/training';

/**
 * Dokumente mit niedriger Confidence abrufen
 */
export async function getLowConfidenceQueue(
  filters: QueueFilters,
  limit = 50,
  offset = 0
): Promise<{ documents: LowConfidenceDocument[]; total: number }> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    sort_by: 'overall_confidence',
    sort_order: 'asc',
  });

  if (filters.maxConfidence < 1) {
    params.set('max_confidence', String(filters.maxConfidence));
  }
  if (filters.backend) {
    params.set('backend', filters.backend);
  }
  if (filters.documentType) {
    params.set('document_type', filters.documentType);
  }
  if (filters.hasUmlauts !== null) {
    params.set('has_umlauts', String(filters.hasUmlauts));
  }

  const response = await api.get(`${API_BASE}/samples?${params}`);
  const data = response.data;

  return {
    documents: (data.samples || []).map((item: Record<string, unknown>) => ({
      id: String(item.id || ''),
      documentId: String(item.document_id || item.id || ''),
      filename: String(item.source_filename || item.file_path || ''),
      documentType: item.document_type ? String(item.document_type) : null,
      backendUsed: String(item.backend_used || 'unknown'),
      overallConfidence: Number(item.overall_confidence || item.confidence || 0),
      extractedText: String(item.ocr_text || item.ground_truth_text || ''),
      thumbnailUrl: item.thumbnail_url ? String(item.thumbnail_url) : undefined,
      createdAt: String(item.created_at || ''),
      fields: (item.fields as Array<Record<string, unknown>> || []).map(
        (f: Record<string, unknown>) => ({
          fieldName: String(f.field_name || ''),
          value: String(f.value || ''),
          confidence: Number(f.confidence || 0),
          correctedValue: f.corrected_value ? String(f.corrected_value) : undefined,
          correctionType: f.correction_type ? String(f.correction_type) : undefined,
        })
      ),
    })),
    total: Number(data.total || 0),
  };
}

/**
 * Korrektur einreichen
 */
export async function submitCorrection(
  correction: CorrectionSubmission
): Promise<{ success: boolean; correctionId: string }> {
  const response = await api.post(`${API_BASE}/corrections`, {
    document_id: correction.documentId,
    field_name: correction.fieldName,
    original_value: correction.originalValue,
    corrected_value: correction.correctedValue,
    correction_type: correction.correctionType,
    backend_used: correction.backendUsed,
    notes: correction.notes,
  });

  return {
    success: true,
    correctionId: String(response.data.id || ''),
  };
}

/**
 * Mehrere Korrekturen auf einmal einreichen
 */
export async function submitBatchCorrections(
  corrections: CorrectionSubmission[]
): Promise<{ success: boolean; correctionIds: string[]; errors: string[] }> {
  const response = await api.post(`${API_BASE}/corrections/batch`, {
    corrections: corrections.map((c) => ({
      document_id: c.documentId,
      field_name: c.fieldName,
      original_value: c.originalValue,
      corrected_value: c.correctedValue,
      correction_type: c.correctionType,
      backend_used: c.backendUsed,
      notes: c.notes,
    })),
  });

  return {
    success: response.data.success ?? true,
    correctionIds: (response.data.correction_ids || []).map(String),
    errors: (response.data.errors || []).map(String),
  };
}

/**
 * Korrektur-Statistiken abrufen
 */
export async function getCorrectionStats(): Promise<CorrectionStats> {
  const response = await api.get(`${API_BASE}/corrections/stats`);
  const data = response.data;

  return {
    totalCorrections: Number(data.total_corrections || 0),
    correctionsToday: Number(data.corrections_today || 0),
    correctionsThisWeek: Number(data.corrections_this_week || 0),
    pendingReview: Number(data.pending_review || 0),
    byType: data.by_type || {},
    byBackend: data.by_backend || {},
    topContributors: (data.top_contributors || []).map(
      (c: Record<string, unknown>) => ({
        userId: String(c.user_id || ''),
        userName: String(c.user_name || ''),
        correctionCount: Number(c.correction_count || 0),
      })
    ),
  };
}

/**
 * Training-Daten exportieren
 */
export async function exportTrainingData(
  config: TrainingExportConfig
): Promise<TrainingExportResult> {
  const response = await api.post(`${API_BASE}/export`, {
    format: config.format,
    split_ratio: [config.splitRatio.train, config.splitRatio.val, config.splitRatio.test],
    split_strategy: config.splitStrategy,
    filter_verified_only: config.verifiedOnly,
    min_umlaut_accuracy: config.minUmlautAccuracy,
    include_metadata: config.includeMetadata,
  });

  const data = response.data;

  return {
    success: data.success ?? true,
    exportId: String(data.export_id || ''),
    outputDir: String(data.output_dir || ''),
    format: String(data.format || config.format),
    stats: {
      totalSamples: Number(data.stats?.total_samples || 0),
      trainSamples: Number(data.stats?.train_samples || 0),
      valSamples: Number(data.stats?.val_samples || 0),
      testSamples: Number(data.stats?.test_samples || 0),
      samplesWithUmlauts: Number(data.stats?.samples_with_umlauts || 0),
      avgTextLength: Number(data.stats?.avg_text_length || 0),
      documentTypes: data.stats?.document_types || {},
      exportTimeSeconds: Number(data.stats?.export_time_seconds || 0),
      outputSizeBytes: Number(data.stats?.output_size_bytes || 0),
    },
    filesCreated: (data.files_created || []).map(String),
    errors: (data.errors || []).map(String),
    warnings: (data.warnings || []).map(String),
  };
}

/**
 * Liste der verfuegbaren Exports abrufen
 */
export async function getExportList(): Promise<
  Array<{
    exportId: string;
    createdAt: string;
    format: string;
    totalSamples: number;
    outputDir: string;
  }>
> {
  const response = await api.get(`${API_BASE}/exports`);

  return (response.data || []).map((item: Record<string, unknown>) => ({
    exportId: String(item.export_id || ''),
    createdAt: String(item.created_at || ''),
    format: String(item.format || ''),
    totalSamples: Number(item.total_samples || 0),
    outputDir: String(item.output_dir || ''),
  }));
}

/**
 * Export loeschen
 */
export async function deleteExport(exportId: string): Promise<{ success: boolean }> {
  await api.delete(`${API_BASE}/exports/${exportId}`);
  return { success: true };
}

/**
 * Verfuegbare OCR-Backends abrufen
 */
export async function getAvailableBackends(): Promise<string[]> {
  const response = await api.get('/api/v1/ocr/backends');
  return (response.data.backends || []).map((b: Record<string, unknown>) =>
    String(b.name || b)
  );
}
