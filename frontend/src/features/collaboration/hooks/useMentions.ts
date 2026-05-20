/**
 * useMentions - Hook für @mentions (ungelesene Erwähnungen)
 *
 * Ermöglicht das Abrufen ungelesener Mentions und das Erstellen neuer Mentions.
 *
 * Backend-Endpunkte:
 * - GET /api/v1/collaboration/mentions
 * - POST /api/v1/collaboration/documents/{id}/mentions
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { toast } from '@/components/ui/use-toast';

// ==================== Types ====================

export interface MentionItem {
  id: string;
  document_id: string;
  document_name: string;
  comment_id: string;
  comment_text: string;
  mentioned_by_user_id: string;
  mentioned_by_user_name: string;
  mentioned_by_user_avatar?: string;
  mentioned_at: string;
  is_read: boolean;
}

export interface MentionsResponse {
  mentions: MentionItem[];
  unread_count: number;
  total: number;
}

export interface CreateMentionPayload {
  comment_id: string;
  mentioned_user_ids: string[];
}

// ==================== Query Keys ====================

export const mentionsKeys = {
  all: ['mentions'] as const,
  list: (filters?: { unread_only?: boolean }) => [...mentionsKeys.all, 'list', filters] as const,
  unreadCount: () => [...mentionsKeys.all, 'unread-count'] as const,
};

// ==================== API Functions ====================

async function getMentions(unreadOnly = false): Promise<MentionsResponse> {
  const response = await apiClient.get<MentionsResponse>('/collaboration/mentions', {
    params: { unread_only: unreadOnly },
  });
  return response.data;
}

async function createMentions(
  documentId: string,
  payload: CreateMentionPayload
): Promise<void> {
  await apiClient.post(`/collaboration/documents/${documentId}/mentions`, payload);
}

async function markMentionAsRead(mentionId: string): Promise<void> {
  await apiClient.patch(`/collaboration/mentions/${mentionId}/read`);
}

// ==================== Hooks ====================

/**
 * Hook für ungelesene Mentions.
 *
 * Pollt alle 30 Sekunden für neue Mentions.
 *
 * @param unreadOnly - Nur ungelesene Mentions laden
 */
export function useMentions(unreadOnly = true) {
  return useQuery({
    queryKey: mentionsKeys.list({ unread_only: unreadOnly }),
    queryFn: () => getMentions(unreadOnly),
    staleTime: 20000,
    refetchInterval: 30000,
    retry: 2,
  });
}

/**
 * Hook für ungelesene Mention-Anzahl.
 *
 * Optimiert für Badge-Display (nur Count, keine Details).
 */
export function useUnreadMentionsCount() {
  const { data } = useMentions(true);
  return data?.unread_count ?? 0;
}

/**
 * Hook zum Erstellen neuer Mentions.
 *
 * Wird beim Kommentieren mit @mentions verwendet.
 */
export function useCreateMentions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ documentId, payload }: { documentId: string; payload: CreateMentionPayload }) =>
      createMentions(documentId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mentionsKeys.all });
    },
    onError: (error: Error) => {
      toast({
        title: 'Erwähnung fehlgeschlagen',
        description: error.message || 'Die Erwähnung konnte nicht erstellt werden',
        variant: 'destructive',
      });
    },
  });
}

/**
 * Hook zum Markieren einer Mention als gelesen.
 */
export function useMarkMentionAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (mentionId: string) => markMentionAsRead(mentionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mentionsKeys.all });
    },
    onError: (error: Error) => {
      toast({
        title: 'Aktion fehlgeschlagen',
        description: error.message || 'Die Erwähnung konnte nicht als gelesen markiert werden',
        variant: 'destructive',
      });
    },
  });
}
