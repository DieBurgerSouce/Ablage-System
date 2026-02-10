/**
 * Document Quality Hooks
 *
 * React Query Hooks fuer Datenqualitaets-Ampel.
 * - useDocumentQuality: Einzeldokument-Score
 * - useCompanyQualityOverview: Unternehmensweite Uebersicht
 */

import { useQuery } from '@tanstack/react-query';
import {
  fetchDocumentQuality,
  fetchCompanyQualityOverview,
  documentQualityKeys,
} from '../api/quality-api';
import type {
  DocumentQualityResponse,
  CompanyQualityOverviewResponse,
} from '../types/quality-types';

// =============================================================================
// Hooks
// =============================================================================

/**
 * Hook fuer Qualitaets-Score eines einzelnen Dokuments
 *
 * @param documentId - Die UUID des Dokuments
 * @param enabled - Optional: Query nur ausfuehren wenn true (default: true)
 */
export function useDocumentQuality(documentId: string, enabled = true) {
  return useQuery<DocumentQualityResponse, Error>({
    queryKey: documentQualityKeys.document(documentId),
    queryFn: () => fetchDocumentQuality(documentId),
    enabled: enabled && Boolean(documentId),
    staleTime: 5 * 60 * 1000,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook fuer unternehmensweite Qualitaetsuebersicht
 */
export function useCompanyQualityOverview() {
  return useQuery<CompanyQualityOverviewResponse, Error>({
    queryKey: documentQualityKeys.overview(),
    queryFn: fetchCompanyQualityOverview,
    staleTime: 5 * 60 * 1000,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}

// =============================================================================
// Formatierung
// =============================================================================

const percentFormatter = new Intl.NumberFormat('de-DE', {
  style: 'percent',
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

/**
 * Formatiere Score (0.0 - 1.0) als Prozent-String
 *
 * @example formatScorePercent(0.85) // "85 %"
 */
export function formatScorePercent(score: number): string {
  return percentFormatter.format(score);
}
