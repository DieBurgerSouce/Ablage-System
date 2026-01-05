/**
 * Chat React Query Hooks
 *
 * Hooks for chat session management using React Query.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    listSessions,
    createSession,
    getSessionHistory,
    deleteSession,
    clearSessionHistory,
    getChatStatus,
    sendMessage,
    chatKeys,
} from '../api/chat-api';
import type { SendMessageRequest } from '../types/chat-types';

// ==================== Sessions ====================

/**
 * Hook to list all chat sessions.
 */
export function useChatSessions() {
    return useQuery({
        queryKey: chatKeys.sessions(),
        queryFn: listSessions,
        staleTime: 30000, // 30 seconds
    });
}

/**
 * Hook to get session history.
 */
export function useSessionHistory(sessionId: string | null) {
    return useQuery({
        queryKey: chatKeys.history(sessionId || ''),
        queryFn: () => getSessionHistory(sessionId!),
        enabled: !!sessionId,
        staleTime: 10000, // 10 seconds
    });
}

/**
 * Hook to create a new session.
 */
export function useCreateSession() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: createSession,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: chatKeys.sessions() });
        },
    });
}

/**
 * Hook to delete a session.
 */
export function useDeleteSession() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: deleteSession,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: chatKeys.sessions() });
        },
    });
}

/**
 * Hook to clear session history.
 */
export function useClearSessionHistory() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: clearSessionHistory,
        onSuccess: (_, sessionId) => {
            queryClient.invalidateQueries({
                queryKey: chatKeys.history(sessionId),
            });
        },
    });
}

// ==================== Chat Status ====================

/**
 * Hook to get chat service status.
 */
export function useChatStatus() {
    return useQuery({
        queryKey: chatKeys.status(),
        queryFn: getChatStatus,
        staleTime: 60000, // 1 minute
        refetchInterval: 60000, // Refetch every minute
    });
}

// ==================== Messages (REST) ====================

/**
 * Hook to send a message via REST API.
 * Use this for non-streaming, simple request/response.
 */
export function useSendMessage() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (request: SendMessageRequest) => sendMessage(request),
        onSuccess: (data) => {
            // Invalidate session history to show new messages
            queryClient.invalidateQueries({
                queryKey: chatKeys.history(data.session_id),
            });
        },
    });
}
