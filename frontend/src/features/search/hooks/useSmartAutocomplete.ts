import { useQuery } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import {
    smartSearchApi,
    smartSearchQueryKeys,
    type AutocompleteResponse,
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

// ==================== Autocomplete Hook ====================

export interface UseSmartAutocompleteOptions {
    /** Minimale Zeichenanzahl bevor Vorschläge geladen werden */
    minLength?: number;
    /** Debounce-Zeit in ms */
    debounceMs?: number;
    /** Ist die Suche aktiv? */
    enabled?: boolean;
}

export interface UseSmartAutocompleteReturn {
    /** Autocomplete-Vorschläge */
    suggestions: AutocompleteResponse['suggestions'];
    /** Ist am Laden */
    isLoading: boolean;
    /** Fehler beim Laden */
    error: Error | null;
}

/**
 * React Query Hook für Smart Search Autocomplete.
 *
 * Lädt Autocomplete-Vorschläge während der Eingabe mit Debouncing.
 *
 * @param partial - Teilweise eingegebener Suchtext
 * @param options - Autocomplete-Optionen
 * @returns Autocomplete-Vorschläge
 *
 * @example
 * ```tsx
 * const { suggestions, isLoading } = useSmartAutocomplete(inputValue, {
 *   minLength: 2,
 *   debounceMs: 300,
 * });
 * ```
 */
export function useSmartAutocomplete(
    partial: string,
    options: UseSmartAutocompleteOptions = {}
): UseSmartAutocompleteReturn {
    const { minLength = 2, debounceMs = 300, enabled = true } = options;

    const debouncedPartial = useDebounce(partial, debounceMs);

    const shouldFetch = enabled && debouncedPartial.trim().length >= minLength;

    const { data, isLoading, error } = useQuery<AutocompleteResponse, Error>({
        queryKey: smartSearchQueryKeys.autocomplete(debouncedPartial),
        queryFn: () => smartSearchApi.autocomplete(debouncedPartial),
        enabled: shouldFetch,
        staleTime: 60 * 1000, // 1 Minute
        gcTime: 5 * 60 * 1000, // 5 Minuten Cache
        refetchOnWindowFocus: false,
    });

    return {
        suggestions: data?.suggestions ?? [],
        isLoading: shouldFetch && isLoading,
        error: error,
    };
}

export default useSmartAutocomplete;
