import { useQuery } from '@tanstack/react-query';
import { documentsService, type SimilarDocument } from '@/lib/api/services/documents';

export interface UseSimilarDocumentsOptions {
    /** Maximale Anzahl ähnlicher Dokumente */
    limit?: number;
    /** Minimale Ähnlichkeit (0-1) */
    similarityThreshold?: number;
    /** Dokumente des gleichen Typs ausschließen */
    excludeSameType?: boolean;
    /** Query aktivieren/deaktivieren */
    enabled?: boolean;
}

/**
 * React Query Hook zum Laden ähnlicher Dokumente.
 *
 * @param documentId - ID des Referenzdokuments
 * @param options - Konfigurationsoptionen
 * @returns Query-Ergebnis mit ähnlichen Dokumenten
 */
export function useSimilarDocuments(
    documentId: string | undefined,
    options: UseSimilarDocumentsOptions = {}
) {
    const {
        limit = 10,
        similarityThreshold = 0.6,
        excludeSameType = false,
        enabled = true,
    } = options;

    return useQuery<SimilarDocument[], Error>({
        queryKey: ['documents', documentId, 'similar', { limit, similarityThreshold, excludeSameType }],
        queryFn: () => {
            if (!documentId) {
                throw new Error('Document ID is required');
            }
            return documentsService.getSimilarDocuments(documentId, {
                limit,
                similarityThreshold,
                excludeSameType,
            });
        },
        enabled: enabled && !!documentId,
        staleTime: 5 * 60 * 1000, // 5 Minuten Cache
        gcTime: 10 * 60 * 1000, // 10 Minuten im Cache behalten
    });
}

/**
 * Query-Key Factory für ähnliche Dokumente.
 * Nützlich für Invalidierung und Prefetching.
 */
export const similarDocumentsQueryKeys = {
    all: ['documents', 'similar'] as const,
    byDocument: (documentId: string) => ['documents', documentId, 'similar'] as const,
};
