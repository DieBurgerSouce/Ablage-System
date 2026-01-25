/**
 * Document Comparison API Functions
 *
 * API-Funktionen fuer Dokumentenvergleiche.
 */

import { apiClient } from '@/lib/api-client';
import type {
  CompareDocumentsRequest,
  ComparisonResult,
  ComparisonType,
  DiffReport,
  SimilarDocument,
} from './types';

const COMPARE_BASE_URL = '/api/v1/compare';

/**
 * Vergleicht zwei Dokumente.
 */
export async function compareDocuments(
  request: CompareDocumentsRequest
): Promise<ComparisonResult> {
  const response = await apiClient.post<{
    document_id_1: string;
    document_id_2: string;
    comparison_type: string;
    similarity_score: number;
    text_similarity: number;
    structure_similarity: number;
    text_differences: Array<{
      type: string;
      position_start: number;
      position_end: number;
      original_text: string;
      new_text: string;
      context_before: string;
      context_after: string;
    }>;
    field_changes: Array<{
      field_name: string;
      category: string;
      old_value: unknown;
      new_value: unknown;
      change_type: string;
      significance: string;
    }>;
    summary: string;
    compared_at: string;
  }>(`${COMPARE_BASE_URL}/documents`, {
    document_id_1: request.documentId1,
    document_id_2: request.documentId2,
    comparison_type: request.comparisonType || 'hybrid',
  });

  return {
    documentId1: response.document_id_1,
    documentId2: response.document_id_2,
    comparisonType: response.comparison_type as ComparisonType,
    similarityScore: response.similarity_score,
    textSimilarity: response.text_similarity,
    structureSimilarity: response.structure_similarity,
    textDifferences: response.text_differences.map((d) => ({
      type: d.type as 'added' | 'removed' | 'changed' | 'unchanged',
      positionStart: d.position_start,
      positionEnd: d.position_end,
      originalText: d.original_text,
      newText: d.new_text,
      contextBefore: d.context_before,
      contextAfter: d.context_after,
    })),
    fieldChanges: response.field_changes.map((f) => ({
      fieldName: f.field_name,
      category: f.category as 'identifier' | 'amount' | 'date' | 'entity' | 'address' | 'text' | 'metadata',
      oldValue: f.old_value,
      newValue: f.new_value,
      changeType: f.change_type as 'added' | 'removed' | 'changed' | 'unchanged',
      significance: f.significance as 'critical' | 'high' | 'medium' | 'low',
    })),
    summary: response.summary,
    comparedAt: response.compared_at,
  };
}

/**
 * Generiert einen Diff-Report.
 */
export async function getDiffReport(
  docId1: string,
  docId2: string,
  comparisonType: ComparisonType = 'hybrid'
): Promise<DiffReport> {
  const response = await apiClient.get<{
    document_1_info: {
      id: string;
      filename: string;
      document_type: string | null;
      created_at: string | null;
    };
    document_2_info: {
      id: string;
      filename: string;
      document_type: string | null;
      created_at: string | null;
    };
    comparison_result: {
      document_id_1: string;
      document_id_2: string;
      comparison_type: string;
      similarity_score: number;
      text_similarity: number;
      structure_similarity: number;
      text_differences: Array<{
        type: string;
        position_start: number;
        position_end: number;
        original_text: string;
        new_text: string;
        context_before: string;
        context_after: string;
      }>;
      field_changes: Array<{
        field_name: string;
        category: string;
        old_value: unknown;
        new_value: unknown;
        change_type: string;
        significance: string;
      }>;
      summary: string;
      compared_at: string;
    };
    detailed_changes: Record<string, unknown>[];
    visual_diff_available: boolean;
    recommendations: string[];
    generated_at: string;
  }>(`${COMPARE_BASE_URL}/diff/${docId1}/${docId2}?comparison_type=${comparisonType}`);

  const cr = response.comparison_result;

  return {
    document1Info: {
      id: response.document_1_info.id,
      filename: response.document_1_info.filename,
      documentType: response.document_1_info.document_type,
      createdAt: response.document_1_info.created_at,
    },
    document2Info: {
      id: response.document_2_info.id,
      filename: response.document_2_info.filename,
      documentType: response.document_2_info.document_type,
      createdAt: response.document_2_info.created_at,
    },
    comparisonResult: {
      documentId1: cr.document_id_1,
      documentId2: cr.document_id_2,
      comparisonType: cr.comparison_type as ComparisonType,
      similarityScore: cr.similarity_score,
      textSimilarity: cr.text_similarity,
      structureSimilarity: cr.structure_similarity,
      textDifferences: cr.text_differences.map((d) => ({
        type: d.type as 'added' | 'removed' | 'changed' | 'unchanged',
        positionStart: d.position_start,
        positionEnd: d.position_end,
        originalText: d.original_text,
        newText: d.new_text,
        contextBefore: d.context_before,
        contextAfter: d.context_after,
      })),
      fieldChanges: cr.field_changes.map((f) => ({
        fieldName: f.field_name,
        category: f.category as 'identifier' | 'amount' | 'date' | 'entity' | 'address' | 'text' | 'metadata',
        oldValue: f.old_value,
        newValue: f.new_value,
        changeType: f.change_type as 'added' | 'removed' | 'changed' | 'unchanged',
        significance: f.significance as 'critical' | 'high' | 'medium' | 'low',
      })),
      summary: cr.summary,
      comparedAt: cr.compared_at,
    },
    detailedChanges: response.detailed_changes,
    visualDiffAvailable: response.visual_diff_available,
    recommendations: response.recommendations,
    generatedAt: response.generated_at,
  };
}

/**
 * Findet aehnliche Dokumente.
 */
export async function findSimilarDocuments(
  docId: string,
  threshold: number = 0.8,
  limit: number = 10,
  includeSameEntity: boolean = true
): Promise<SimilarDocument[]> {
  const params = new URLSearchParams({
    threshold: threshold.toString(),
    limit: limit.toString(),
    include_same_entity: includeSameEntity.toString(),
  });

  const response = await apiClient.get<
    Array<{
      document_id: string;
      filename: string;
      document_type: string | null;
      similarity_score: number;
      matching_fields: string[];
      upload_date: string;
    }>
  >(`${COMPARE_BASE_URL}/similar/${docId}?${params}`);

  return response.map((doc) => ({
    documentId: doc.document_id,
    filename: doc.filename,
    documentType: doc.document_type,
    similarityScore: doc.similarity_score,
    matchingFields: doc.matching_fields,
    uploadDate: doc.upload_date,
  }));
}

/**
 * Findet potenzielle Duplikate.
 */
export async function findPotentialDuplicates(
  threshold: number = 0.95,
  daysBack: number = 30,
  limit: number = 50
): Promise<
  Array<{
    document1: { id: string; filename: string; createdAt: string };
    document2: { id: string; filename: string; createdAt: string };
    similarityScore: number;
    recommendation: string;
  }>
> {
  const params = new URLSearchParams({
    threshold: threshold.toString(),
    days_back: daysBack.toString(),
    limit: limit.toString(),
  });

  const response = await apiClient.get<
    Array<{
      document_1: { id: string; filename: string; created_at: string };
      document_2: { id: string; filename: string; created_at: string };
      similarity_score: number;
      recommendation: string;
    }>
  >(`${COMPARE_BASE_URL}/duplicates?${params}`);

  return response.map((dup) => ({
    document1: {
      id: dup.document_1.id,
      filename: dup.document_1.filename,
      createdAt: dup.document_1.created_at,
    },
    document2: {
      id: dup.document_2.id,
      filename: dup.document_2.filename,
      createdAt: dup.document_2.created_at,
    },
    similarityScore: dup.similarity_score,
    recommendation: dup.recommendation,
  }));
}
