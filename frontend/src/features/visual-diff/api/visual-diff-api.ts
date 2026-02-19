/**
 * Visual Diff API Client - Document Version Comparison
 *
 * API-Funktionen für den visuellen Dokumentenvergleich.
 * Vergleicht Texte und zeigt Änderungen seite-an-seite an.
 *
 * Backend-Endpunkte:
 * - POST /api/v1/visual-diff/compare - Vollständiger Vergleich
 * - POST /api/v1/visual-diff/compare/summary - Nur Zusammenfassung
 * - POST /api/v1/visual-diff/hash - Text-Hash berechnen
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface DiffBlock {
  diff_type: 'added' | 'deleted' | 'modified' | 'unchanged';
  old_text: string;
  new_text: string;
  old_line_start: number;
  old_line_end: number;
  new_line_start: number;
  new_line_end: number;
  page_number: number;
}

export interface DiffResponse {
  document_a_id: string;
  document_b_id: string;
  total_changes: number;
  additions: number;
  deletions: number;
  modifications: number;
  similarity_ratio: number;
  blocks: DiffBlock[];
  summary: string;
}

export interface DiffRequest {
  text_a: string;
  text_b: string;
  document_a_id?: string;
  document_b_id?: string;
  context_lines?: number;
}

export interface ChangeSummary {
  total_changes: number;
  additions: number;
  deletions: number;
  modifications: number;
  similarity_percentage: number;
  key_changes: string[];
  risk_level: string;
}

export interface HashResponse {
  hash: string;
}

// ==================== Query Keys ====================

export const visualDiffKeys = {
  all: ['visual-diff'] as const,
  compare: () => [...visualDiffKeys.all, 'compare'] as const,
  summary: () => [...visualDiffKeys.all, 'summary'] as const,
  hash: (text: string) => [...visualDiffKeys.all, 'hash', text] as const,
  imageDiff: () => [...visualDiffKeys.all, 'image-diff'] as const,
};

// ==================== API Functions ====================

/**
 * Vergleicht zwei Texte und gibt vollständiges Diff zurück
 */
export async function compareTexts(request: DiffRequest): Promise<DiffResponse> {
  const response = await apiClient.post<DiffResponse>('/visual-diff/compare', request);
  return response.data;
}

/**
 * Vergleicht zwei Texte und gibt nur die Zusammenfassung zurück
 */
export async function compareTextsSummary(request: DiffRequest): Promise<ChangeSummary> {
  const response = await apiClient.post<ChangeSummary>(
    '/visual-diff/compare/summary',
    request
  );
  return response.data;
}

/**
 * Berechnet SHA-256 Hash eines Textes
 */
export async function computeTextHash(text: string): Promise<HashResponse> {
  const response = await apiClient.post<HashResponse>('/visual-diff/hash', { text });
  return response.data;
}

// ==================== Image Diff Types ====================

export interface ImageDiffRequest {
  document_a_id: string;
  document_b_id: string;
  page?: number;
  threshold?: number;
}

export interface ImageDiffResponse {
  similarity_score: number;
  changed_percentage: number;
  diff_image_base64: string;
  overlay_image_base64: string;
  dimensions: [number, number];
}

// ==================== Image Diff API ====================

/**
 * Vergleicht zwei Dokumente pixelweise als Bilder
 */
export async function compareDocumentImages(
  request: ImageDiffRequest
): Promise<ImageDiffResponse> {
  const response = await apiClient.post<ImageDiffResponse>(
    '/visual-diff/compare/image',
    request
  );
  return response.data;
}
