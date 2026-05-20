/**
 * Papierkorb API
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
    DeletedDocumentsListResponse,
    TrashStatsResponse,
    RestoreDocumentResponse,
    PermanentDeleteResponse,
    EmptyTrashResponse,
} from './types'

const TRASH_KEYS = {
    all: ['trash'] as const,
    list: () => [...TRASH_KEYS.all, 'list'] as const,
    stats: () => [...TRASH_KEYS.all, 'stats'] as const,
}

/**
 * Papierkorb-Inhalt abrufen
 */
export function useTrashList() {
    return useQuery({
        queryKey: TRASH_KEYS.list(),
        queryFn: async () => {
            const response = await api.get<DeletedDocumentsListResponse>('/api/v1/trash')
            return response.data
        },
        staleTime: 30_000, // 30 Sekunden
    })
}

/**
 * Papierkorb-Statistiken abrufen
 */
export function useTrashStats() {
    return useQuery({
        queryKey: TRASH_KEYS.stats(),
        queryFn: async () => {
            const response = await api.get<TrashStatsResponse>('/api/v1/trash/stats')
            return response.data
        },
        staleTime: 30_000,
    })
}

/**
 * Dokument wiederherstellen
 */
export function useRestoreDocument() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: async (documentId: string) => {
            const response = await api.post<RestoreDocumentResponse>(
                `/api/v1/trash/${documentId}/restore`
            )
            return response.data
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: TRASH_KEYS.all })
            queryClient.invalidateQueries({ queryKey: ['documents'] })
        },
    })
}

/**
 * Dokument permanent löschen
 */
export function usePermanentDelete() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: async (documentId: string) => {
            const response = await api.delete<PermanentDeleteResponse>(
                `/api/v1/trash/${documentId}`
            )
            return response.data
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: TRASH_KEYS.all })
        },
    })
}

/**
 * Papierkorb leeren
 */
export function useEmptyTrash() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: async (onlyExpired: boolean = false) => {
            const response = await api.delete<EmptyTrashResponse>('/api/v1/trash', {
                params: { only_expired: onlyExpired },
            })
            return response.data
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: TRASH_KEYS.all })
        },
    })
}
