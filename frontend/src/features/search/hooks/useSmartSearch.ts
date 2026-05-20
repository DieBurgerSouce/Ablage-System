import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import {
    smartSearchApi,
    smartSearchQueryKeys,
    type SmartSearchRequest,
    type SmartSearchResponse,
    type SmartSearchFilters,
} from '../api/smart-search-api';

// ==================== Debounce Hook ====================

function useDebounce<T>(value: T, delay: number): T {
    const [debouncedValue, setDebouncedValue] = useState<T>(value);

    useEffect(() => {
        const handler = setTimeout(() => setDebouncedValue(value), delay);
        return () => clearTimeout(handler);
    }, [value, delay]);

    return debouncedValue;
}

// ==================== Main Smart Search Hook ====================

export interface UseSmartSearchOptions {
    /** Query-String */
    query: string;
    /** Filter-Optionen */
    filters?: SmartSearchFilters;
    /** Anzahl der Ergebnisse */
    limit?: number;
    /** Vorschläge inkludieren */
    includeSuggestions?: boolean;
    /** Suchmodus erzwingen */
    forceMode?: 'nlq' | 'keyword' | null;
    /** Aktiviert/deaktiviert die Query */
    enabled?: boolean;
    /** Minimale Query-Länge für Suche */
    minQueryLength?: number;
    /** Debounce-Zeit in ms */
    debounceMs?: number;
}

export interface UseSmartSearchReturn {
    /** Suchergebnisse */
    data: SmartSearchResponse | undefined;
    /** Ist am Laden */
    isLoading: boolean;
    /** Fehler beim Laden */
    error: Error | null;
    /** Ist am Fetchen (inkl. Background Refetch) */
    isFetching: boolean;
    /** Ist erfolgreich geladen */
    isSuccess: boolean;
}

/**
 * React Query Hook für Smart Search mit NLQ-Erkennung und Entity-Linking.
 *
 * @param options - Such-Optionen
 * @returns Query-Ergebnis mit Suchergebnissen, Entities und Vorschlägen
 *
 * @example
 * ```tsx
 * const { data, isLoading } = useSmartSearch({
 *   query: 'offene Rechnungen von Mueller',
 *   filters: { status: ['pending'] },
 * });
 * ```
 */
export function useSmartSearch(options: UseSmartSearchOptions): UseSmartSearchReturn {
    const {
        query,
        filters,
        limit = 20,
        includeSuggestions = true,
        forceMode = null,
        enabled = true,
        minQueryLength = 2,
        debounceMs = 300,
    } = options;

    // Debounce query to reduce API calls
    const debouncedQuery = useDebounce(query, debounceMs);

    const hasValidQuery = debouncedQuery.trim().length >= minQueryLength;

    const request: SmartSearchRequest = {
        query: debouncedQuery,
        filters,
        limit,
        include_suggestions: includeSuggestions,
        force_mode: forceMode,
    };

    const queryResult = useQuery<SmartSearchResponse, Error>({
        queryKey: smartSearchQueryKeys.search(request),
        queryFn: () => smartSearchApi.search(request),
        enabled: enabled && hasValidQuery,
        staleTime: 30 * 1000, // 30 Sekunden
        gcTime: 5 * 60 * 1000, // 5 Minuten Cache
        refetchOnWindowFocus: false,
        placeholderData: keepPreviousData, // Zeigt vorherige Daten während Refresh
    });

    return {
        data: queryResult.data,
        isLoading: queryResult.isLoading,
        error: queryResult.error,
        isFetching: queryResult.isFetching,
        isSuccess: queryResult.isSuccess,
    };
}

/**
 * Standard Smart Search Parameter.
 */
export const defaultSmartSearchOptions: Partial<UseSmartSearchOptions> = {
    limit: 20,
    includeSuggestions: true,
    forceMode: null,
    minQueryLength: 2,
    debounceMs: 300,
};

export { type SmartSearchRequest, type SmartSearchResponse, type SmartSearchFilters };
