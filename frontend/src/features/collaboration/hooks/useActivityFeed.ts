/**
 * useActivityFeed - Hook für Aktivitäts-Feeds
 *
 * Ermöglicht das Abrufen von:
 * - Dokument-spezifischer Aktivität
 * - Benutzer-spezifischer Aktivität
 *
 * Backend-Endpunkte:
 * - GET /api/v1/collaboration/documents/{id}/activity
 * - GET /api/v1/collaboration/activity/feed
 */

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import type { Activity, ActivitiesResponse } from '../types/collaboration.types';

// ==================== Query Keys ====================

export const activityKeys = {
  all: ['activity-feed'] as const,
  document: (documentId: string) => [...activityKeys.all, 'document', documentId] as const,
  user: (userId: string) => [...activityKeys.all, 'user', userId] as const,
  global: (params?: ActivityFeedParams) => [...activityKeys.all, 'global', params] as const,
};

// ==================== Types ====================

export interface ActivityFeedParams {
  limit?: number;
  offset?: number;
  type?: string;
  user_id?: string;
}

// ==================== API Functions ====================

async function getDocumentActivity(documentId: string): Promise<ActivitiesResponse> {
  const response = await apiClient.get<ActivitiesResponse>(
    `/collaboration/documents/${documentId}/activity`
  );
  return response.data;
}

async function getUserActivityFeed(params?: ActivityFeedParams): Promise<ActivitiesResponse> {
  const response = await apiClient.get<ActivitiesResponse>(
    '/collaboration/activity/feed',
    { params }
  );
  return response.data;
}

// ==================== Hooks ====================

/**
 * Hook für Dokument-Aktivitätsverlauf.
 *
 * Zeigt alle Aktivitäten eines bestimmten Dokuments.
 *
 * @param documentId - Dokument-ID
 */
export function useDocumentActivity(documentId: string) {
  return useQuery({
    queryKey: activityKeys.document(documentId),
    queryFn: () => getDocumentActivity(documentId),
    staleTime: 30000,
    enabled: !!documentId,
    retry: 2,
  });
}

/**
 * Hook für Benutzer-Aktivitätsfeed.
 *
 * Zeigt globale Aktivitäten mit optionalen Filtern.
 *
 * @param params - Filter-Parameter
 */
export function useUserActivityFeed(params?: ActivityFeedParams) {
  return useQuery({
    queryKey: activityKeys.global(params),
    queryFn: () => getUserActivityFeed(params),
    staleTime: 30000,
    retry: 2,
  });
}

/**
 * Hook für Dokument-Aktivitätsverlauf mit Echtzeit-Updates.
 *
 * Kombiniert API-Polling mit WebSocket-Events für sofortige Updates.
 *
 * @param documentId - Dokument-ID
 */
export function useDocumentActivityRealtime(documentId: string) {
  const query = useDocumentActivity(documentId);

  // WebSocket-Updates werden über ActivityTimeline Component gehandhabt

  return {
    activities: query.data?.activities ?? [],
    total: query.data?.total ?? 0,
    hasMore: query.data?.hasMore ?? false,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}
