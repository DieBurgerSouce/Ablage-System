/**
 * KI-Chat Hooks - TanStack Query Hooks fuer den Chat-Assistenten
 *
 * Stellt Hooks bereit fuer:
 * - Session-Verwaltung (auflisten, erstellen)
 * - Nachrichten laden
 * - Streaming-Nachrichten senden mit optimistischen Updates
 */

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getChatSessions,
  createChatSession,
  getChatMessages,
  sendChatMessageStream,
  sendChatMessage,
} from '../api/chat-api';
import type {
  ChatMessage,
  ChatSendPayload,
  ChatSessionCreate,
  ChatSource,
  StreamEvent,
} from '../types/chat-types';

// ==================== Query Keys ====================

export const kiChatKeys = {
  all: ['ki-chat'] as const,
  sessions: () => [...kiChatKeys.all, 'sessions'] as const,
  messages: (sessionId: string) =>
    [...kiChatKeys.all, 'messages', sessionId] as const,
};

// ==================== Session Hooks ====================

export function useChatSessions() {
  return useQuery({
    queryKey: kiChatKeys.sessions(),
    queryFn: getChatSessions,
    staleTime: 1000 * 60,
  });
}

export function useCreateChatSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ChatSessionCreate) => createChatSession(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: kiChatKeys.sessions() });
    },
  });
}

// ==================== Message Hooks ====================

export function useChatMessages(sessionId: string) {
  return useQuery({
    queryKey: kiChatKeys.messages(sessionId),
    queryFn: () => getChatMessages(sessionId),
    enabled: !!sessionId,
    staleTime: 1000 * 10,
  });
}

// ==================== Send Message Hook ====================

/**
 * Hook fuer Chat-Nachrichten mit Streaming-Support.
 *
 * Verwaltet:
 * - Optimistisches Hinzufuegen der User-Nachricht
 * - SSE-Streaming der Assistant-Antwort
 * - Quellen-Sammlung waehrend des Streams
 * - Fallback auf Non-Streaming
 */
export function useSendMessage(sessionId: string) {
  const queryClient = useQueryClient();
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const sendStreaming = useCallback(
    async (message: string, context?: Pick<ChatSendPayload, 'context_type' | 'context_id'>) => {
      if (!sessionId) return;

      setIsStreaming(true);
      setStreamingContent('');
      setStreamError(null);

      // Optimistisch: User-Nachricht sofort anzeigen
      queryClient.setQueryData<ChatMessage[]>(
        kiChatKeys.messages(sessionId),
        (old) => [
          ...(old || []),
          {
            id: `temp-user-${Date.now()}`,
            session_id: sessionId,
            role: 'user' as const,
            content: message,
            created_at: new Date().toISOString(),
          },
        ]
      );

      let accumulatedContent = '';
      const collectedSources: ChatSource[] = [];

      await sendChatMessageStream(
        {
          message,
          session_id: sessionId,
          ...context,
        },
        (event: StreamEvent) => {
          switch (event.type) {
            case 'chunk':
              accumulatedContent += event.content;
              setStreamingContent(accumulatedContent);
              break;

            case 'source':
              collectedSources.push(event.source);
              break;

            case 'done': {
              setIsStreaming(false);
              setStreamingContent('');

              // Vollstaendige Assistant-Nachricht in den Cache
              queryClient.setQueryData<ChatMessage[]>(
                kiChatKeys.messages(sessionId),
                (old) => [
                  ...(old || []),
                  {
                    id: event.message_id,
                    session_id: event.session_id,
                    role: 'assistant' as const,
                    content: accumulatedContent,
                    sources: collectedSources.length > 0 ? collectedSources : undefined,
                    created_at: new Date().toISOString(),
                  },
                ]
              );

              // Sessions aktualisieren (message_count)
              queryClient.invalidateQueries({ queryKey: kiChatKeys.sessions() });
              break;
            }

            case 'error':
              setIsStreaming(false);
              setStreamingContent('');
              setStreamError(event.error);
              break;
          }
        },
        (error: string) => {
          setIsStreaming(false);
          setStreamingContent('');
          setStreamError(error);
        }
      );
    },
    [sessionId, queryClient]
  );

  // Non-Streaming Fallback
  const sendNonStreaming = useMutation({
    mutationFn: (payload: ChatSendPayload) => sendChatMessage(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: kiChatKeys.messages(sessionId) });
      queryClient.invalidateQueries({ queryKey: kiChatKeys.sessions() });
    },
  });

  return {
    sendStreaming,
    sendNonStreaming: sendNonStreaming.mutate,
    streamingContent,
    isStreaming,
    isSending: sendNonStreaming.isPending,
    streamError,
  };
}
