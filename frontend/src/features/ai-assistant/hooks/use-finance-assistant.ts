/**
 * React Query Hooks for Finance Assistant
 *
 * Vision 2.0 - Phase 1 (Januar 2026)
 *
 * Provides type-safe hooks for interacting with the Finance Assistant API:
 * - Chat mutations with optimistic updates
 * - Action execution with confirmation
 * - Proactive insights queries
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState, useEffect } from 'react';
import { chatWithAssistant, executeAction, rollbackAction, getInsights, getAssistantHelp, type ChatRequest, type ChatResponse, type ExecuteActionRequest, type ExecuteActionResponse, type InsightsListResponse, type AssistantHelpResponse, type ActionData, type BookingSuggestionData, createConversation, getConversationBySession, listConversations, updateConversation, deleteConversation, getConversationMessages, getConversationActions, confirmConversationAction, cancelConversationAction, addMessageFeedback, getConversationStats, type ConversationSummary, type ConversationDetail, type ConversationMessage, type ConversationAction, type ConversationListResponse, type ActionStatus, type FeedbackType } from '@/lib/api/services/finance-assistant';
import { useAIAssistantStore } from '../stores/ai-assistant-store';

// ===== Query Keys =====

export const financeAssistantKeys = {
  all: ['finance-assistant'] as const,
  insights: () => [...financeAssistantKeys.all, 'insights'] as const,
  insightsWithPredictions: (includePredictions: boolean) =>
    [...financeAssistantKeys.insights(), { includePredictions }] as const,
  help: () => [...financeAssistantKeys.all, 'help'] as const,
  chat: () => [...financeAssistantKeys.all, 'chat'] as const,
  actions: () => [...financeAssistantKeys.all, 'actions'] as const,
  // Conversation persistence keys
  conversations: () => [...financeAssistantKeys.all, 'conversations'] as const,
  conversationsList: (params?: { is_active?: boolean; is_starred?: boolean }) =>
    [...financeAssistantKeys.conversations(), 'list', params] as const,
  conversation: (id: string) => [...financeAssistantKeys.conversations(), id] as const,
  conversationBySession: (sessionId: string) =>
    [...financeAssistantKeys.conversations(), 'session', sessionId] as const,
  conversationMessages: (id: string) =>
    [...financeAssistantKeys.conversation(id), 'messages'] as const,
  conversationActions: (id: string) =>
    [...financeAssistantKeys.conversation(id), 'actions'] as const,
  stats: () => [...financeAssistantKeys.all, 'stats'] as const,
};

// ===== Chat Hook =====

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: ChatResponse;
  isLoading?: boolean;
  error?: string;
}

export interface UseFinanceAssistantChatOptions {
  sessionId?: string;
  onSuccess?: (response: ChatResponse) => void;
  onError?: (error: Error) => void;
}

export function useFinanceAssistantChat(options: UseFinanceAssistantChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingActions, setPendingActions] = useState<ActionData[]>([]);
  const [pendingBookings, setPendingBookings] = useState<BookingSuggestionData[]>([]);
  const { pageContext } = useAIAssistantStore();
  const queryClient = useQueryClient();

  const chatMutation = useMutation({
    mutationFn: chatWithAssistant,
    onMutate: async (request: ChatRequest) => {
      // Add user message immediately
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: request.message,
        timestamp: new Date(),
      };

      // Add loading message for assistant
      const loadingMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isLoading: true,
      };

      setMessages((prev) => [...prev, userMessage, loadingMessage]);

      return { userMessage, loadingMessage };
    },
    onSuccess: (response, _request, context) => {
      // Update the loading message with the actual response
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === context?.loadingMessage.id
            ? {
                ...msg,
                content: response.message,
                response,
                isLoading: false,
              }
            : msg
        )
      );

      // Store pending actions and booking suggestions
      if (response.actions.length > 0) {
        setPendingActions(response.actions);
      }
      if (response.booking_suggestions.length > 0) {
        setPendingBookings(response.booking_suggestions);
      }

      // Invalidate insights if the response contains new insights
      if (response.insights.length > 0) {
        queryClient.invalidateQueries({ queryKey: financeAssistantKeys.insights() });
      }

      options.onSuccess?.(response);
    },
    onError: (error: Error, _request, context) => {
      // Update the loading message with error
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === context?.loadingMessage.id
            ? {
                ...msg,
                content: 'Entschuldigung, es ist ein Fehler aufgetreten.',
                isLoading: false,
                error: error.message,
            }
            : msg
        )
      );

      options.onError?.(error);
    },
  });

  const sendMessage = useCallback(
    (message: string, selectedDocuments?: string[]) => {
      const request: ChatRequest = {
        message,
        current_page: pageContext?.pageType,
        selected_documents: selectedDocuments,
        session_id: options.sessionId,
      };
      chatMutation.mutate(request);
    },
    [chatMutation, pageContext, options.sessionId]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setPendingActions([]);
    setPendingBookings([]);
  }, []);

  const dismissAction = useCallback((actionType: string) => {
    setPendingActions((prev) => prev.filter((a) => a.action_type !== actionType));
  }, []);

  const dismissBooking = useCallback((index: number) => {
    setPendingBookings((prev) => prev.filter((_, i) => i !== index));
  }, []);

  return {
    messages,
    pendingActions,
    pendingBookings,
    sendMessage,
    clearMessages,
    dismissAction,
    dismissBooking,
    isLoading: chatMutation.isPending,
    error: chatMutation.error,
  };
}

// ===== Action Execution Hook =====

export interface UseExecuteActionOptions {
  onSuccess?: (response: ExecuteActionResponse) => void;
  onError?: (error: Error) => void;
}

export function useExecuteAction(options: UseExecuteActionOptions = {}) {
  const [executedActions, setExecutedActions] = useState<ExecuteActionResponse[]>([]);
  const queryClient = useQueryClient();

  const executeMutation = useMutation({
    mutationFn: executeAction,
    onSuccess: (response) => {
      setExecutedActions((prev) => [...prev, response]);

      // Invalidate related queries based on action type
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.insights() });

      options.onSuccess?.(response);
    },
    onError: (error: Error) => {
      options.onError?.(error);
    },
  });

  const execute = useCallback(
    (actionType: string, parameters: Record<string, unknown>) => {
      const request: ExecuteActionRequest = { action_type: actionType, parameters };
      return executeMutation.mutateAsync(request);
    },
    [executeMutation]
  );

  const rollbackMutation = useMutation({
    mutationFn: rollbackAction,
    onSuccess: (response) => {
      // Remove from executed actions
      setExecutedActions((prev) =>
        prev.filter((a) => a.action_id !== response.action_id)
      );

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
    },
  });

  const rollback = useCallback(
    (actionId: string) => {
      return rollbackMutation.mutateAsync({ action_id: actionId });
    },
    [rollbackMutation]
  );

  return {
    executedActions,
    execute,
    rollback,
    isExecuting: executeMutation.isPending,
    isRollingBack: rollbackMutation.isPending,
    executeError: executeMutation.error,
    rollbackError: rollbackMutation.error,
  };
}

// ===== Insights Query Hook =====

export interface UseInsightsOptions {
  includePredictions?: boolean;
  enabled?: boolean;
  refetchInterval?: number;
}

export function useInsights(options: UseInsightsOptions = {}) {
  const { includePredictions = true, enabled = true, refetchInterval } = options;

  return useQuery<InsightsListResponse, Error>({
    queryKey: financeAssistantKeys.insightsWithPredictions(includePredictions),
    queryFn: () => getInsights(includePredictions),
    enabled,
    refetchInterval,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// ===== Help Query Hook =====

export function useAssistantHelp() {
  return useQuery<AssistantHelpResponse, Error>({
    queryKey: financeAssistantKeys.help(),
    queryFn: getAssistantHelp,
    staleTime: 60 * 60 * 1000, // 1 hour - help rarely changes
  });
}

// ===== Combined Finance Assistant Hook =====

export interface UseFinanceAssistantOptions {
  sessionId?: string;
  autoFetchInsights?: boolean;
  insightsRefetchInterval?: number;
}

export function useFinanceAssistant(options: UseFinanceAssistantOptions = {}) {
  const {
    sessionId,
    autoFetchInsights = true,
    insightsRefetchInterval = 5 * 60 * 1000, // 5 minutes
  } = options;

  const chat = useFinanceAssistantChat({ sessionId });
  const actions = useExecuteAction();
  const insights = useInsights({
    enabled: autoFetchInsights,
    refetchInterval: insightsRefetchInterval,
  });
  const help = useAssistantHelp();

  // Execute a pending action with confirmation
  const executeWithConfirmation = useCallback(
    async (action: ActionData) => {
      if (action.requires_confirmation) {
        // The UI should show a confirmation dialog before calling this
        return actions.execute(action.action_type, action.parameters);
      }
      return actions.execute(action.action_type, action.parameters);
    },
    [actions]
  );

  return {
    // Chat
    messages: chat.messages,
    sendMessage: chat.sendMessage,
    clearMessages: chat.clearMessages,
    isChatLoading: chat.isLoading,
    chatError: chat.error,

    // Pending items from chat responses
    pendingActions: chat.pendingActions,
    pendingBookings: chat.pendingBookings,
    dismissAction: chat.dismissAction,
    dismissBooking: chat.dismissBooking,

    // Action execution
    executedActions: actions.executedActions,
    executeAction: actions.execute,
    executeWithConfirmation,
    rollbackAction: actions.rollback,
    isExecuting: actions.isExecuting,
    isRollingBack: actions.isRollingBack,

    // Insights
    insights: insights.data?.insights ?? [],
    insightsCount: insights.data?.count ?? 0,
    insightsGeneratedAt: insights.data?.generated_at,
    isLoadingInsights: insights.isLoading,
    insightsError: insights.error,
    refetchInsights: insights.refetch,

    // Help
    capabilities: help.data?.capabilities ?? [],
    helpVersion: help.data?.version,
    requiresOllama: help.data?.requires_ollama ?? true,
    isLoadingHelp: help.isLoading,
  };
}

// ===== Conversation Persistence Hooks =====

/**
 * Hook for listing conversations with pagination
 */
export interface UseConversationsOptions {
  page?: number;
  pageSize?: number;
  isActive?: boolean;
  isStarred?: boolean;
  search?: string;
  enabled?: boolean;
}

export function useConversations(options: UseConversationsOptions = {}) {
  const { page = 1, pageSize = 20, isActive, isStarred, search, enabled = true } = options;

  return useQuery<ConversationListResponse, Error>({
    queryKey: financeAssistantKeys.conversationsList({ is_active: isActive, is_starred: isStarred }),
    queryFn: () =>
      listConversations({
        page,
        page_size: pageSize,
        is_active: isActive,
        is_starred: isStarred,
        search,
      }),
    enabled,
  });
}

/**
 * Hook for managing a single conversation with persistence
 */
export interface UsePersistentConversationOptions {
  sessionId?: string;
  contextPage?: string;
  autoCreate?: boolean;
  onConversationCreated?: (conversation: ConversationDetail) => void;
}

export function usePersistentConversation(options: UsePersistentConversationOptions = {}) {
  const { sessionId, contextPage, autoCreate = true, onConversationCreated } = options;
  const queryClient = useQueryClient();
  const { setSessionId } = useAIAssistantStore();

  // Try to get existing conversation by session ID
  const conversationQuery = useQuery<ConversationDetail, Error>({
    queryKey: financeAssistantKeys.conversationBySession(sessionId || ''),
    queryFn: () => getConversationBySession(sessionId!),
    enabled: !!sessionId,
    retry: false,
  });

  // Create conversation mutation
  const createMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (newConversation) => {
      setSessionId(newConversation.session_id);
      queryClient.setQueryData(
        financeAssistantKeys.conversationBySession(newConversation.session_id),
        newConversation
      );
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.conversationsList() });
      onConversationCreated?.(newConversation);
    },
  });

  // Auto-create conversation if not exists and autoCreate is true
  useEffect(() => {
    if (autoCreate && !sessionId && !conversationQuery.data && !createMutation.isPending) {
      createMutation.mutate({ context_page: contextPage });
    }
  }, [autoCreate, sessionId, conversationQuery.data, createMutation, contextPage]);

  // Update conversation mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Parameters<typeof updateConversation>[1]) =>
      updateConversation(id, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(financeAssistantKeys.conversation(updated.id), updated);
      queryClient.setQueryData(
        financeAssistantKeys.conversationBySession(updated.session_id),
        updated
      );
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.conversationsList() });
    },
  });

  // Delete conversation mutation
  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_data, conversationId) => {
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.conversation(conversationId) });
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.conversationsList() });
    },
  });

  const conversation = conversationQuery.data;

  const starConversation = useCallback(
    (starred: boolean) => {
      if (conversation) {
        updateMutation.mutate({ id: conversation.id, is_starred: starred });
      }
    },
    [conversation, updateMutation]
  );

  const setTitle = useCallback(
    (title: string) => {
      if (conversation) {
        updateMutation.mutate({ id: conversation.id, title });
      }
    },
    [conversation, updateMutation]
  );

  const archiveConversation = useCallback(() => {
    if (conversation) {
      updateMutation.mutate({ id: conversation.id, is_active: false });
    }
  }, [conversation, updateMutation]);

  const removeConversation = useCallback(() => {
    if (conversation) {
      deleteMutation.mutate(conversation.id);
    }
  }, [conversation, deleteMutation]);

  return {
    conversation,
    isLoading: conversationQuery.isLoading || createMutation.isPending,
    error: conversationQuery.error || createMutation.error,
    starConversation,
    setTitle,
    archiveConversation,
    removeConversation,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  };
}

/**
 * Hook for loading conversation messages
 */
export interface UseConversationMessagesOptions {
  conversationId: string;
  limit?: number;
  enabled?: boolean;
}

export function useConversationMessages(options: UseConversationMessagesOptions) {
  const { conversationId, limit = 50, enabled = true } = options;

  return useQuery({
    queryKey: financeAssistantKeys.conversationMessages(conversationId),
    queryFn: () => getConversationMessages(conversationId, { limit }),
    enabled: enabled && !!conversationId,
  });
}

/**
 * Hook for managing conversation actions
 */
export interface UseConversationActionsOptions {
  conversationId: string;
  status?: ActionStatus;
  enabled?: boolean;
}

export function useConversationActionsQuery(options: UseConversationActionsOptions) {
  const { conversationId, status, enabled = true } = options;
  const queryClient = useQueryClient();

  const actionsQuery = useQuery({
    queryKey: financeAssistantKeys.conversationActions(conversationId),
    queryFn: () => getConversationActions(conversationId, { status }),
    enabled: enabled && !!conversationId,
  });

  const confirmMutation = useMutation({
    mutationFn: (actionId: string) => confirmConversationAction(conversationId, actionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: financeAssistantKeys.conversationActions(conversationId),
      });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (actionId: string) => cancelConversationAction(conversationId, actionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: financeAssistantKeys.conversationActions(conversationId),
      });
    },
  });

  return {
    actions: actionsQuery.data?.actions ?? [],
    total: actionsQuery.data?.total ?? 0,
    isLoading: actionsQuery.isLoading,
    error: actionsQuery.error,
    confirmAction: confirmMutation.mutate,
    cancelAction: cancelMutation.mutate,
    isConfirming: confirmMutation.isPending,
    isCancelling: cancelMutation.isPending,
  };
}

/**
 * Hook for adding feedback to messages
 */
export function useMessageFeedback() {
  const queryClient = useQueryClient();

  const feedbackMutation = useMutation({
    mutationFn: ({
      messageId,
      feedbackType,
      rating,
      comment,
      correction,
      expectedIntent,
    }: {
      messageId: string;
      feedbackType: FeedbackType;
      rating?: number;
      comment?: string;
      correction?: string;
      expectedIntent?: string;
    }) =>
      addMessageFeedback(messageId, {
        feedback_type: feedbackType,
        rating,
        comment,
        correction,
        expected_intent: expectedIntent,
      }),
    onSuccess: () => {
      // Could invalidate specific message queries if needed
      queryClient.invalidateQueries({ queryKey: financeAssistantKeys.stats() });
    },
  });

  return {
    addFeedback: feedbackMutation.mutate,
    addFeedbackAsync: feedbackMutation.mutateAsync,
    isSubmitting: feedbackMutation.isPending,
    error: feedbackMutation.error,
  };
}

/**
 * Hook for conversation statistics
 */
export function useConversationStats(enabled = true) {
  return useQuery({
    queryKey: financeAssistantKeys.stats(),
    queryFn: getConversationStats,
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Re-export types for convenience
export type {
  ConversationSummary,
  ConversationDetail,
  ConversationMessage,
  ConversationAction,
  ActionStatus,
  FeedbackType,
};
