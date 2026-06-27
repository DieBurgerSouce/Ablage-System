/**
 * Collaboration API Client - Präsenz und Aktivitäts-Feed
 *
 * API-Funktionen und TanStack Query Hooks für:
 * - Präsenz-Informationen (wer sieht ein Dokument)
 * - Aktivitäts-Feed (globaler Verlauf)
 *
 * Hinweis: Kommentar-CRUD liegt in hooks/use-comments.ts
 *
 * Backend-Endpunkte:
 * - GET /ws/presence/{documentId}
 * - GET /documents/activity
 */

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import type { ActivitiesResponse } from '../types/collaboration.types';

// ==================== Types ====================

export interface PresenceUser {
  user_id: string;
  username: string;
  email?: string;
  avatar?: string;
  connected_at: string;
  current_document?: string;
}

export interface DocumentPresenceResponse {
  document_id: string;
  viewers: PresenceUser[];
  viewer_count: number;
}

export interface ActivityFeedParams {
  limit?: number;
  offset?: number;
  type?: string;
}

// ==================== Query Keys ====================

export const collaborationKeys = {
  all: ['collaboration'] as const,
  comments: (documentId: string) => [...collaborationKeys.all, 'comments', documentId] as const,
  activity: (documentId: string) => [...collaborationKeys.all, 'activity', documentId] as const,
  activityFeed: (params?: ActivityFeedParams) => [...collaborationKeys.all, 'activity-feed', params] as const,
  presence: (documentId: string) => [...collaborationKeys.all, 'presence', documentId] as const,
};

// ==================== API Functions ====================

async function getDocumentPresence(
  documentId: string,
): Promise<DocumentPresenceResponse> {
  // G03: Auth über httpOnly-Cookie (apiClient withCredentials) statt Query-Token.
  const response = await apiClient.get<DocumentPresenceResponse>(
    `/ws/presence/${documentId}`,
  );
  return response.data;
}

async function getActivityFeed(
  params: ActivityFeedParams = {},
): Promise<ActivitiesResponse> {
  const response = await apiClient.get<ActivitiesResponse>(
    '/documents/activity',
    { params },
  );
  return response.data;
}

// ==================== TanStack Query Hooks ====================

/**
 * Hook für Dokument-Präsenz (wer schaut gerade).
 *
 * Pollt alle 15 Sekunden und nutzt zusätzlich WebSocket-Events
 * für sofortige Updates.
 *
 * @param documentId - Dokument-ID
 */
export function useDocumentPresence(documentId: string) {
  return useQuery({
    queryKey: collaborationKeys.presence(documentId),
    queryFn: () => getDocumentPresence(documentId),
    staleTime: 10000,
    refetchInterval: 15000,
    enabled: !!documentId,
    retry: 1,
  });
}

/**
 * Hook für den globalen Aktivitäts-Feed.
 *
 * @param params - Filter-Parameter (limit, offset, type)
 */
export function useActivityFeed(params?: ActivityFeedParams) {
  return useQuery({
    queryKey: collaborationKeys.activityFeed(params),
    queryFn: () => getActivityFeed(params),
    staleTime: 30000,
    retry: 2,
  });
}
