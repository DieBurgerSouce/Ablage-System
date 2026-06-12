import { apiClient } from '@/lib/api/client';
import type { OcrRegion, OcrRegionBackend, OcrFeedbackRequest, SelfLearningStats, SelfLearningStatsBackend, DocumentVersion, DocumentVersionBackend } from '../types';
import {
  transformOcrRegion,
  transformOcrFeedback,
  transformSelfLearningStats,
  transformDocumentVersion,
} from '../types';

// ============================================================================
// OCR Regions API
// ============================================================================

export async function getOcrRegions(documentId: string): Promise<OcrRegion[]> {
  const response = await apiClient.get<OcrRegionBackend[]>(
    `/ocr/documents/${documentId}/regions`
  );
  return response.data.map(transformOcrRegion);
}

// ============================================================================
// OCR Feedback API
// ============================================================================

export async function submitOcrFeedback(
  documentId: string,
  feedback: OcrFeedbackRequest
): Promise<void> {
  const backendFeedback = transformOcrFeedback(feedback);
  await apiClient.post(`/ocr/documents/${documentId}/feedback`, backendFeedback);
}

// ============================================================================
// Self-Learning Stats API
// ============================================================================

export async function getSelfLearningStats(): Promise<SelfLearningStats> {
  const response = await apiClient.get<SelfLearningStatsBackend>(
    '/ocr/self-learning/stats'
  );
  return transformSelfLearningStats(response.data);
}

// ============================================================================
// Document Versions API
// ============================================================================

export async function getDocumentVersions(
  documentId: string
): Promise<DocumentVersion[]> {
  const response = await apiClient.get<DocumentVersionBackend[]>(
    `/documents/${documentId}/versions`
  );
  return response.data.map(transformDocumentVersion);
}

export async function getDocumentVersion(
  documentId: string,
  versionId: string
): Promise<DocumentVersion> {
  const response = await apiClient.get<DocumentVersionBackend>(
    `/documents/${documentId}/versions/${versionId}`
  );
  return transformDocumentVersion(response.data);
}
