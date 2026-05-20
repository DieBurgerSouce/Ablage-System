/**
 * useActivity - Hook für Dokumenten-Aktivitätsverlauf
 *
 * Lädt die Aktivitätshistorie eines Dokuments.
 * Integriert mit Backend API: /api/v1/documents/{documentId}/activity
 *
 * Enterprise Features:
 * - Error State mit Retry-Logik
 * - Stale Time für Performance
 */

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import type { ActivitiesResponse } from '../types/collaboration.types';

// ==================== API Functions ====================

async function fetchActivities(documentId: string): Promise<ActivitiesResponse> {
  const response = await apiClient.get<ActivitiesResponse>(`/documents/${documentId}/activity`);
  return response.data;
}

// ==================== Hook ====================

export function useActivity(documentId: string) {
  return useQuery({
    queryKey: ['activity', documentId],
    queryFn: () => fetchActivities(documentId),
    staleTime: 60000, // 1 minute
    enabled: !!documentId,
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
  });
}
