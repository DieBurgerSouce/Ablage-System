/**
 * Filing-Vorschlag Query Hooks (F1 Vertrauens-Loop)
 *
 * Lädt Ablage-Vorschläge für ein hochgeladenes Dokument und bestätigt
 * (oder korrigiert) die Ablage.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { automationService } from '@/lib/api/services/automation';

export const filingQueryKeys = {
    all: ['filing'] as const,
    suggestions: (documentId: string) =>
        [...filingQueryKeys.all, 'suggestions', documentId] as const,
};

/** Ablage-Vorschläge für ein Dokument. */
export function useFilingSuggestions(
    documentId: string,
    options?: { enabled?: boolean }
) {
    return useQuery({
        queryKey: filingQueryKeys.suggestions(documentId),
        queryFn: () => automationService.getFilingSuggestions(documentId),
        enabled: options?.enabled !== false && !!documentId,
        staleTime: 30_000,
        retry: (failureCount, error) => {
            // 4xx nicht wiederholen
            const status = (error as { response?: { status?: number } })?.response?.status;
            if (status && status >= 400 && status < 500) return false;
            return failureCount < 2;
        },
    });
}

/** Ablage bestätigen/korrigieren. */
export function useAcceptFiling() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({
            documentId,
            targetCategory,
        }: {
            documentId: string;
            targetCategory: string;
        }) => automationService.acceptFilingSuggestion(documentId, targetCategory),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({
                queryKey: filingQueryKeys.suggestions(variables.documentId),
            });
            // Dokumentenlisten ggf. aktualisieren
            queryClient.invalidateQueries({ queryKey: ['documents'] });
        },
    });
}
