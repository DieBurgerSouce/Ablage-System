/**
 * GDPR Art.30 Verarbeitungsverzeichnis - API Hooks
 *
 * TanStack Query Hooks fuer das Verzeichnis von Verarbeitungstaetigkeiten
 * (Art. 30 DSGVO). Liest GET /api/v1/admin/gdpr/processing-activities (Admin).
 */

import { useQuery } from '@tanstack/react-query';
import { fetchWithAuth } from '@/lib/api';

// ==================== Types ====================

export interface ProcessingActivityEntry {
  id: string;
  document_id: string | null;
  subject_id: string | null;
  data_categories: string[];
  purpose: string;
  legal_basis: string;
  retention_period_days: number;
  retention_expires_at: string | null;
  processing_backend: string | null;
  created_at: string | null;
}

export interface ProcessingActivityRegisterResponse {
  total: number;
  limit: number;
  offset: number;
  activities: ProcessingActivityEntry[];
  gdpr_articles_covered: string[];
  hinweis: string;
}

export interface ProcessingActivityParams {
  limit?: number;
  offset?: number;
  purpose?: string;
}

// ==================== Query Keys ====================

export const gdprProcessingKeys = {
  all: ['admin', 'gdpr', 'processing-activities'] as const,
  list: (params: ProcessingActivityParams) =>
    [...gdprProcessingKeys.all, params] as const,
};

// ==================== API Functions ====================

async function fetchProcessingActivities(
  params: ProcessingActivityParams,
): Promise<ProcessingActivityRegisterResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set('limit', String(params.limit ?? 100));
  searchParams.set('offset', String(params.offset ?? 0));
  if (params.purpose) searchParams.set('purpose', params.purpose);

  // URL ist RELATIV zur apiClient-baseURL ('/api/v1') — NICHT '/api/v1/...'.
  return fetchWithAuth<ProcessingActivityRegisterResponse>(
    `/admin/gdpr/processing-activities?${searchParams.toString()}`,
  );
}

// ==================== Hooks ====================

export function useProcessingActivities(params: ProcessingActivityParams = {}) {
  return useQuery({
    queryKey: gdprProcessingKeys.list(params),
    queryFn: () => fetchProcessingActivities(params),
    staleTime: 60_000, // 1 Minute
  });
}
