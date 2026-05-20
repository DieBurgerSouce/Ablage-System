/**
 * PO-Matching API Service
 *
 * Kommuniziert mit den /api/v1/po-matching Endpoints
 * für 3-Way Purchase Order Matching.
 *
 * Features:
 * - Match-Liste mit Filtern und Paginierung
 * - Match-Detail mit Abweichungen
 * - Auto-Matching Auslösung
 * - Match-Freigabe und -Bewertung
 * - Statistiken
 */

import { apiClient } from '@/lib/api/client';
import type {
  MatchListResponse,
  MatchDetailResponse,
  MatchResponse,
  MatchStatisticsResponse,
  UnmatchedDocumentResponse,
  AutoMatchResponse,
  POMatchFilter,
  POMatchCreateRequest,
} from '../types/po-matching-types';

// ==================== API Functions ====================

/**
 * Listet PO-Matches mit Filtern und Paginierung.
 */
export async function fetchPOMatches(
  params: POMatchFilter = {}
): Promise<MatchListResponse> {
  const queryParams: Record<string, string | number> = {};

  if (params.status) queryParams.status = params.status;
  if (params.vendor_entity_id) queryParams.vendor_entity_id = params.vendor_entity_id;
  if (params.date_from) queryParams.date_from = params.date_from;
  if (params.date_to) queryParams.date_to = params.date_to;
  if (params.order_number) queryParams.order_number = params.order_number;
  if (params.page !== undefined) queryParams.page = params.page;
  if (params.page_size !== undefined) queryParams.page_size = params.page_size;

  const response = await apiClient.get<MatchListResponse>('/po-matching', {
    params: queryParams,
  });
  return response.data;
}

/**
 * Ruft einen einzelnen Match mit Abweichungen ab.
 */
export async function fetchPOMatch(
  matchId: string
): Promise<MatchDetailResponse> {
  const response = await apiClient.get<MatchDetailResponse>(
    `/po-matching/${matchId}`
  );
  return response.data;
}

/**
 * Listet ungematchte Dokumente.
 */
export async function fetchUnmatchedDocuments(
  docType?: string
): Promise<UnmatchedDocumentResponse[]> {
  const params: Record<string, string> = {};
  if (docType) params.document_type = docType;

  const response = await apiClient.get<UnmatchedDocumentResponse[]>(
    '/po-matching/unmatched',
    { params }
  );
  return response.data;
}

/**
 * Führt automatisches Matching aus.
 */
export async function triggerAutoMatch(): Promise<AutoMatchResponse> {
  const response = await apiClient.post<AutoMatchResponse>(
    '/po-matching/auto-detect'
  );
  return response.data;
}

/**
 * Erstellt einen neuen PO-Match.
 */
export async function createPOMatch(
  data: POMatchCreateRequest
): Promise<MatchResponse> {
  const response = await apiClient.post<MatchResponse>(
    '/po-matching',
    data
  );
  return response.data;
}

/**
 * Gibt einen Match frei.
 */
export async function approvePOMatch(
  matchId: string,
  notes?: string
): Promise<MatchResponse> {
  const response = await apiClient.post<MatchResponse>(
    `/po-matching/${matchId}/approve`,
    { notes }
  );
  return response.data;
}

/**
 * Bewertet einen Match und erkennt Abweichungen.
 */
export async function evaluatePOMatch(
  matchId: string
): Promise<MatchDetailResponse> {
  const response = await apiClient.post<MatchDetailResponse>(
    `/po-matching/${matchId}/evaluate`
  );
  return response.data;
}

/**
 * Ruft Matching-Statistiken für einen Zeitraum ab.
 */
export async function fetchPOMatchStats(
  periodStart: string,
  periodEnd: string
): Promise<MatchStatisticsResponse> {
  const response = await apiClient.get<MatchStatisticsResponse>(
    '/po-matching/statistics',
    {
      params: {
        period_start: periodStart,
        period_end: periodEnd,
      },
    }
  );
  return response.data;
}
