import { useQuery } from '@tanstack/react-query';
import {
    documentHintsApi,
    documentHintsQueryKeys,
    type DocumentHintsResponse,
    type BatchHintsResponse,
    type HintSummarySchema,
} from '../api/document-hints-api';

/**
 * Hook für Hinweise eines einzelnen Dokuments.
 * Aktualisiert automatisch alle 5 Minuten.
 */
export function useDocumentHints(documentId: string) {
    return useQuery<DocumentHintsResponse>({
        queryKey: documentHintsQueryKeys.single(documentId),
        queryFn: () => documentHintsApi.getDocumentHints(documentId),
        enabled: !!documentId,
        refetchInterval: 300000, // 5 Minuten
        staleTime: 240000, // 4 Minuten
    });
}

/**
 * Hook für Batch-Hinweise mehrerer Dokumente.
 * Aktualisiert automatisch alle 5 Minuten.
 */
export function useBatchDocumentHints(documentIds: string[]) {
    return useQuery<BatchHintsResponse>({
        queryKey: documentHintsQueryKeys.batch(documentIds),
        queryFn: () => documentHintsApi.getBatchDocumentHints(documentIds),
        enabled: documentIds.length > 0,
        refetchInterval: 300000, // 5 Minuten
        staleTime: 240000, // 4 Minuten
    });
}

/**
 * Hook für unternehmensweite Hinweis-Zusammenfassung.
 * Aktualisiert automatisch alle 5 Minuten.
 */
export function useHintsSummary() {
    return useQuery<HintSummarySchema>({
        queryKey: documentHintsQueryKeys.summary(),
        queryFn: () => documentHintsApi.getHintsSummary(),
        refetchInterval: 300000, // 5 Minuten
        staleTime: 240000, // 4 Minuten
    });
}
