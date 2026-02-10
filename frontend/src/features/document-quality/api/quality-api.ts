/**
 * Document Quality API Service
 *
 * API-Funktionen fuer die Datenqualitaets-Ampel:
 * - Einzeldokument-Score mit Ampel-Status
 * - Unternehmensweite Qualitaetsuebersicht
 */

import { apiClient } from '@/lib/api/client';
import type {
  DocumentQualityResponse,
  CompanyQualityOverviewResponse,
} from '../types/quality-types';

const BASE_URL = '/document-quality';

// =============================================================================
// API Functions
// =============================================================================

/**
 * Hole Qualitaets-Score fuer ein einzelnes Dokument
 *
 * @param documentId - Die UUID des Dokuments
 * @returns Qualitaetsbewertung mit Ampel-Status und Dimensionen
 */
export async function fetchDocumentQuality(
  documentId: string,
): Promise<DocumentQualityResponse> {
  const response = await apiClient.get<DocumentQualityResponse>(
    `${BASE_URL}/${documentId}/score`,
  );
  return response.data;
}

/**
 * Hole unternehmensweite Qualitaetsuebersicht
 *
 * @returns Ampel-Verteilung und Durchschnittswerte
 */
export async function fetchCompanyQualityOverview(): Promise<CompanyQualityOverviewResponse> {
  const response = await apiClient.get<CompanyQualityOverviewResponse>(
    `${BASE_URL}/overview`,
  );
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const documentQualityKeys = {
  all: ['document-quality'] as const,
  document: (documentId: string) =>
    [...documentQualityKeys.all, 'document', documentId] as const,
  overview: () => [...documentQualityKeys.all, 'overview'] as const,
};
