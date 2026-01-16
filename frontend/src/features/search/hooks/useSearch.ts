import { useQuery, keepPreviousData } from '@tanstack/react-query';
import {
    searchApi,
    searchQueryKeys,
    type SearchParams,
    type SearchResponse,
    type SearchType,
} from '../api/search-api';

export interface UseSearchOptions {
    /** Aktiviert/deaktiviert die Query */
    enabled?: boolean;
    /** Minimale Query-Länge für Suche */
    minQueryLength?: number;
    /** Refetch bei Fenster-Fokus */
    refetchOnWindowFocus?: boolean;
}

/**
 * React Query Hook für Dokumentensuche.
 *
 * @param params - Such-Parameter
 * @param options - Query-Optionen
 * @returns Query-Ergebnis mit Suchergebnissen
 */
export function useSearch(params: SearchParams, options: UseSearchOptions = {}) {
    const {
        enabled = true,
        minQueryLength = 2,
        refetchOnWindowFocus = false,
    } = options;

    const hasValidQuery = params.query.trim().length >= minQueryLength;

    return useQuery<SearchResponse, Error>({
        queryKey: searchQueryKeys.search(params),
        queryFn: () => searchApi.search(params),
        enabled: enabled && hasValidQuery,
        staleTime: 30 * 1000, // 30 Sekunden
        gcTime: 5 * 60 * 1000, // 5 Minuten Cache
        refetchOnWindowFocus,
        placeholderData: keepPreviousData, // Zeigt vorherige Daten während Refresh
    });
}

/**
 * Standard-Such-Parameter.
 */
export const defaultSearchParams: Partial<SearchParams> = {
    searchType: 'hybrid' as SearchType,
    page: 1,
    perPage: 20,
    sortBy: 'relevance',
    sortOrder: 'desc',
    highlight: true,
    similarityThreshold: 0.5,
};

export { type SearchParams, type SearchResponse, type SearchType };
