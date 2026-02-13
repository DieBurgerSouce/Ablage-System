/**
 * usePresence - Hook für Echtzeit-Präsenz (wer sieht ein Dokument)
 *
 * Verwendet WebSocket-Events + Polling für robuste Präsenz-Informationen.
 *
 * Backend-Endpunkt:
 * - GET /api/v1/collaboration/documents/{id}/presence
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { apiClient } from '@/lib/api/client';
import { useRealtimeEvent } from '@/lib/websocket';

// ==================== Types ====================

export interface PresenceUser {
  user_id: string;
  user_name: string;
  user_email?: string;
  user_avatar?: string;
  joined_at: string;
}

export interface PresenceResponse {
  document_id: string;
  viewers: PresenceUser[];
  viewer_count: number;
}

// ==================== Query Keys ====================

export const presenceKeys = {
  all: ['presence'] as const,
  document: (documentId: string) => [...presenceKeys.all, documentId] as const,
};

// ==================== API Functions ====================

async function getDocumentPresence(documentId: string): Promise<PresenceResponse> {
  const response = await apiClient.get<PresenceResponse>(
    `/collaboration/documents/${documentId}/presence`
  );
  return response.data;
}

// ==================== Hook ====================

/**
 * Hook für Dokument-Präsenz mit Echtzeit-Updates.
 *
 * Pollt alle 5 Sekunden und nutzt WebSocket-Events für sofortige Updates.
 *
 * @param documentId - Dokument-ID
 * @param enabled - Ob Präsenz aktiv sein soll (default: true)
 *
 * @example
 * const { viewers, viewerCount, isLoading } = usePresence(documentId);
 */
export function usePresence(documentId: string, enabled = true) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: presenceKeys.document(documentId),
    queryFn: () => getDocumentPresence(documentId),
    staleTime: 3000,
    refetchInterval: 5000,
    enabled: enabled && !!documentId,
    retry: 1,
  });

  // WebSocket-Updates für Präsenz-Änderungen
  useEffect(() => {
    if (!enabled || !documentId) return;

    // Wenn User ein Dokument öffnet/schließt
    const unsubscribeJoin = useRealtimeEvent('document.viewed', (event) => {
      if (event.payload.document_id === documentId) {
        queryClient.invalidateQueries({ queryKey: presenceKeys.document(documentId) });
      }
    });

    // Periodic invalidation for presence updates
    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: presenceKeys.document(documentId) });
    }, 15000); // 15 seconds

    return () => {
      unsubscribeJoin();
      clearInterval(interval);
    };
  }, [documentId, enabled, queryClient]);

  return {
    viewers: query.data?.viewers ?? [],
    viewerCount: query.data?.viewer_count ?? 0,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}
