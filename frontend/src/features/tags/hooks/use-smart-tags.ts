/**
 * TanStack Query Hooks fuer Smart Auto-Tagging Feature
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { smartTagsApi } from '../api/smart-tags-api'
import type { TagCategory } from '../types'

// ============================================================================
// Query Keys
// ============================================================================

export const smartTagQueryKeys = {
    all: ['smart-tags'] as const,
    suggestions: (docId: string) =>
        [...smartTagQueryKeys.all, 'suggestions', docId] as const,
    analysis: (docId: string) =>
        [...smartTagQueryKeys.all, 'analysis', docId] as const,
    definitions: (category?: string) =>
        [...smartTagQueryKeys.all, 'definitions', category] as const,
    categories: () =>
        [...smartTagQueryKeys.all, 'categories'] as const,
}

// ============================================================================
// Hook: Tag-Vorschlaege fuer ein Dokument
// ============================================================================

export function useDocumentSmartTags(documentId: string | null) {
    return useQuery({
        queryKey: smartTagQueryKeys.suggestions(documentId ?? ''),
        queryFn: () => smartTagsApi.getSuggestions(documentId!),
        enabled: !!documentId,
        staleTime: 60000, // 60 Sekunden
    })
}

// ============================================================================
// Hook: Tag-Definitionen (alle oder nach Kategorie)
// ============================================================================

export function useSmartTagDefinitions(category?: TagCategory) {
    return useQuery({
        queryKey: smartTagQueryKeys.definitions(category),
        queryFn: () => smartTagsApi.getDefinitions(category),
        staleTime: 300000, // 5 Minuten - Definitionen aendern sich selten
    })
}

// ============================================================================
// Hook: Verfuegbare Kategorien
// ============================================================================

export function useSmartTagCategories() {
    return useQuery({
        queryKey: smartTagQueryKeys.categories(),
        queryFn: () => smartTagsApi.getCategories(),
        staleTime: 300000, // 5 Minuten
    })
}

// ============================================================================
// Hook: Dokument analysieren (Mutation)
// ============================================================================

export function useAnalyzeDocument() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({
            documentId,
            autoApply = true,
            minConfidence = 0.5,
        }: {
            documentId: string
            autoApply?: boolean
            minConfidence?: number
        }) => smartTagsApi.analyzeDocument(documentId, autoApply, minConfidence),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({
                queryKey: smartTagQueryKeys.suggestions(variables.documentId),
            })
            queryClient.invalidateQueries({
                queryKey: smartTagQueryKeys.analysis(variables.documentId),
            })
        },
    })
}
