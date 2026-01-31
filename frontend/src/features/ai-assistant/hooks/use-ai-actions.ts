/**
 * AI Actions Query Hooks
 *
 * TanStack Query Hooks fuer role-basierte AI-Aktionen.
 * Unterstuetzt alle drei Autonomie-Level: Viewer, Editor, Admin.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import {
    aiActionsApi,
    AIActionType,
    AIActionStatus,
    AIActionAutonomyLevel,
    ACTION_METADATA,
    type AIActionRequest,
    type AIActionConfirmRequest,
    type AIActionResult,
    type AIActionListResponse,
    type AIContextInfo,
    type AIActionSuggestion,
} from '@/lib/api/services/ai-actions';

// Re-export types for convenience
export {
    AIActionType,
    AIActionStatus,
    AIActionAutonomyLevel,
    ACTION_METADATA,
    type AIActionRequest,
    type AIActionConfirmRequest,
    type AIActionResult,
    type AIActionListResponse,
    type AIContextInfo,
    type AIActionSuggestion,
};

// ==================== Query Keys ====================

export const aiActionKeys = {
    all: ['ai-actions'] as const,
    actions: () => [...aiActionKeys.all, 'available'] as const,
    actionList: (contextType?: string) => [...aiActionKeys.actions(), contextType] as const,
    context: () => [...aiActionKeys.all, 'context'] as const,
    contextInfo: (pageType: string, docId?: string, entityId?: string) =>
        [...aiActionKeys.context(), pageType, docId, entityId] as const,
    pending: () => [...aiActionKeys.all, 'pending'] as const,
};

// ==================== Queries ====================

/**
 * Hook zum Abrufen verfuegbarer AI-Aktionen basierend auf User-Rolle.
 */
export function useAvailableActions(contextType?: string, enabled = true) {
    return useQuery({
        queryKey: aiActionKeys.actionList(contextType),
        queryFn: () => aiActionsApi.getAvailableActions(contextType),
        staleTime: 5 * 60 * 1000, // 5 Minuten - Rollen aendern sich selten
        enabled,
    });
}

/**
 * Hook zum Abrufen von Kontext-Informationen fuer die aktuelle Seite.
 */
export function useAIContextInfo(
    pageType: string,
    documentId?: string,
    entityId?: string,
    enabled = true
) {
    return useQuery({
        queryKey: aiActionKeys.contextInfo(pageType, documentId, entityId),
        queryFn: () => aiActionsApi.getContextInfo(pageType, documentId, entityId),
        staleTime: 30 * 1000, // 30 Sekunden - Kontext kann sich aendern
        enabled: enabled && !!pageType,
    });
}

// ==================== Mutations ====================

/**
 * Hook zum Ausfuehren einer AI-Aktion.
 *
 * Verhaelt sich unterschiedlich je nach Autonomie-Level:
 * - Viewer: Nur read-only Aktionen, direkte Ausfuehrung
 * - Editor: Gibt Suggestion zurueck, erfordert Bestaetigung
 * - Admin: Kann mit auto_execute direkt ausfuehren
 */
export function useExecuteAction() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (request: AIActionRequest) => aiActionsApi.executeAction(request),
        onSuccess: (result) => {
            // Refresh pending count
            queryClient.invalidateQueries({ queryKey: aiActionKeys.actions() });

            // Show toast based on status
            const actionMeta = ACTION_METADATA[result.action_type];
            const actionName = actionMeta?.name || result.action_type;

            if (result.status === AIActionStatus.COMPLETED) {
                toast.success(`${actionName}: ${result.message}`);
            } else if (result.status === AIActionStatus.SUGGESTED) {
                // Don't show toast for suggestions - handled by UI
            } else if (result.status === AIActionStatus.FAILED) {
                toast.error(`${actionName} fehlgeschlagen: ${result.message}`);
            }
        },
        onError: (error: Error) => {
            toast.error(`Fehler bei AI-Aktion: ${error.message}`);
        },
    });
}

/**
 * Hook zum Bestaetigen oder Ablehnen einer vorgeschlagenen Aktion.
 */
export function useConfirmAction() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (request: AIActionConfirmRequest) => aiActionsApi.confirmAction(request),
        onSuccess: (result, variables) => {
            // Refresh actions
            queryClient.invalidateQueries({ queryKey: aiActionKeys.actions() });

            const actionMeta = ACTION_METADATA[result.action_type];
            const actionName = actionMeta?.name || result.action_type;

            if (variables.confirmed) {
                if (result.status === AIActionStatus.COMPLETED) {
                    toast.success(`${actionName}: ${result.message}`);
                } else if (result.status === AIActionStatus.FAILED) {
                    toast.error(`${actionName} fehlgeschlagen: ${result.message}`);
                }
            } else {
                toast.info(`${actionName} abgebrochen`);
            }
        },
        onError: (error: Error) => {
            toast.error(`Fehler bei Bestaetigung: ${error.message}`);
        },
    });
}

// ==================== Utility Hooks ====================

/**
 * Hook zum Pruefen ob eine bestimmte Aktion verfuegbar ist.
 */
export function useCanExecuteAction(actionType: AIActionType): {
    canExecute: boolean;
    requiresConfirmation: boolean;
    autonomyLevel: AIActionAutonomyLevel | null;
    isLoading: boolean;
} {
    const { data, isLoading } = useAvailableActions();

    if (isLoading || !data) {
        return {
            canExecute: false,
            requiresConfirmation: true,
            autonomyLevel: null,
            isLoading,
        };
    }

    const requiredLevel = ACTION_METADATA[actionType]?.requiredLevel;
    const userLevel = data.autonomy_level;

    // Check if user has sufficient permissions
    const levelOrder = [AIActionAutonomyLevel.VIEWER, AIActionAutonomyLevel.EDITOR, AIActionAutonomyLevel.ADMIN];
    const userLevelIndex = levelOrder.indexOf(userLevel);
    const requiredLevelIndex = levelOrder.indexOf(requiredLevel);

    const canExecute = userLevelIndex >= requiredLevelIndex;
    const requiresConfirmation =
        userLevel === AIActionAutonomyLevel.EDITOR && requiredLevel !== AIActionAutonomyLevel.VIEWER;

    return {
        canExecute,
        requiresConfirmation,
        autonomyLevel: userLevel,
        isLoading: false,
    };
}

/**
 * Hook fuer kontextbewusste Action-Execution.
 * Kombiniert Kontext-Detection mit Action-Execution.
 */
export function useContextAwareAction(
    pageType: string,
    documentId?: string,
    entityId?: string
) {
    const { data: contextInfo, isLoading: contextLoading } = useAIContextInfo(
        pageType,
        documentId,
        entityId
    );
    const { data: actionsData, isLoading: actionsLoading } = useAvailableActions(pageType);
    const executeAction = useExecuteAction();
    const confirmAction = useConfirmAction();

    const executeWithContext = async (
        actionType: AIActionType,
        parameters: Record<string, unknown> = {},
        autoExecute = false
    ): Promise<AIActionResult> => {
        return executeAction.mutateAsync({
            action_type: actionType,
            context_type: pageType,
            context_id: documentId || entityId,
            parameters,
            auto_execute: autoExecute,
        });
    };

    const confirm = async (
        actionId: string,
        confirmed: boolean,
        modifiedParams?: Record<string, unknown>
    ): Promise<AIActionResult> => {
        return confirmAction.mutateAsync({
            action_id: actionId,
            confirmed,
            modified_parameters: modifiedParams,
        });
    };

    return {
        // Data
        contextInfo,
        availableActions: actionsData?.available_actions || [],
        autonomyLevel: actionsData?.autonomy_level || AIActionAutonomyLevel.VIEWER,
        pendingSuggestions: actionsData?.pending_suggestions || 0,

        // Loading states
        isLoading: contextLoading || actionsLoading,
        isExecuting: executeAction.isPending,
        isConfirming: confirmAction.isPending,

        // Actions
        executeWithContext,
        confirm,

        // Last result (for handling suggestions)
        lastResult: executeAction.data,
        lastConfirmResult: confirmAction.data,
    };
}

/**
 * Hook fuer Action-Suggestions Queue (Editor-Level).
 * Verwaltet ausstehende Vorschlaege die auf Bestaetigung warten.
 */
export function useActionSuggestions() {
    const queryClient = useQueryClient();
    const confirmAction = useConfirmAction();

    // Local state for current suggestions (in-memory queue)
    // In a full implementation, this would come from the backend
    const { data: actionsData } = useAvailableActions();

    const confirmAll = async (suggestions: AIActionSuggestion[]) => {
        const results: AIActionResult[] = [];
        for (const suggestion of suggestions) {
            try {
                const result = await confirmAction.mutateAsync({
                    action_id: suggestion.action_id,
                    confirmed: true,
                });
                results.push(result);
            } catch (error) {
                // Continue with remaining suggestions
                logger.error(`AI-Aktion fehlgeschlagen: ${suggestion.title}`, error);
            }
        }
        return results;
    };

    const rejectAll = async (suggestions: AIActionSuggestion[]) => {
        const results: AIActionResult[] = [];
        for (const suggestion of suggestions) {
            try {
                const result = await confirmAction.mutateAsync({
                    action_id: suggestion.action_id,
                    confirmed: false,
                });
                results.push(result);
            } catch (error) {
                logger.error(`AI-Aktion fehlgeschlagen: ${suggestion.title}`, error);
            }
        }
        return results;
    };

    return {
        pendingCount: actionsData?.pending_suggestions || 0,
        isConfirming: confirmAction.isPending,
        confirmSingle: (actionId: string, params?: Record<string, unknown>) =>
            confirmAction.mutateAsync({ action_id: actionId, confirmed: true, modified_parameters: params }),
        rejectSingle: (actionId: string) =>
            confirmAction.mutateAsync({ action_id: actionId, confirmed: false }),
        confirmAll,
        rejectAll,
        invalidate: () => queryClient.invalidateQueries({ queryKey: aiActionKeys.all }),
    };
}
