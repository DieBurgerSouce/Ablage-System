/**
 * useSpotlightSearch - Spotlight-Suche (Cmd+K) Hook
 *
 * Kombiniert useSmartSearch (Volltextsuche) und useSmartAutocomplete
 * (Autocomplete-Vorschlaege) fuer die Spotlight-Dialog-Komponente.
 * Nutzt useRecentSearches fuer letzte Suchanfragen.
 *
 * @example
 * ```tsx
 * const { results, suggestions, entities, isLoading, interpretation } = useSpotlightSearch(query);
 * ```
 */

import { useSmartSearch } from './useSmartSearch';
import { useSmartAutocomplete } from './useSmartAutocomplete';
import { useRecentSearches } from './use-recent-searches';
import type {
    SmartSearchResult,
    EntityMatch,
    QueryInterpretation,
    AutocompleteResult,
} from '../api/smart-search-api';

// ==================== Types ====================

export interface UseSpotlightSearchReturn {
    /** Dokument-Suchergebnisse */
    results: SmartSearchResult[];
    /** Entity-Treffer (Kunden, Lieferanten) */
    entities: EntityMatch[];
    /** Autocomplete-Vorschlaege */
    suggestions: AutocompleteResult[];
    /** Query-Interpretation (Modus, Ausfuehrungszeit) */
    interpretation: QueryInterpretation | undefined;
    /** Gesamtanzahl Ergebnisse */
    total: number;
    /** Suchzeit in ms */
    searchTimeMs: number | undefined;
    /** Suchmodus (nlq / keyword) */
    searchMode: 'nlq' | 'keyword' | undefined;
    /** Suchergebnisse werden geladen */
    isSearchLoading: boolean;
    /** Autocomplete wird geladen */
    isAutocompleteLoading: boolean;
    /** Irgendein Ladevorgang aktiv */
    isLoading: boolean;
    /** Letzte Suchen (Hook) */
    recentSearches: ReturnType<typeof useRecentSearches>;
}

// ==================== Hook ====================

export function useSpotlightSearch(query: string): UseSpotlightSearchReturn {
    // Autocomplete: kuerzeres Debounce (150ms), feuert schneller
    const autocomplete = useSmartAutocomplete(query, {
        minLength: 2,
        debounceMs: 150,
        enabled: true,
    });

    // Volltextsuche: Standard-Debounce (300ms)
    const search = useSmartSearch({
        query,
        limit: 8,
        includeSuggestions: false,
        minQueryLength: 2,
        debounceMs: 300,
    });

    // Letzte Suchen
    const recentSearches = useRecentSearches();

    return {
        results: search.data?.results ?? [],
        entities: search.data?.entities ?? [],
        suggestions: autocomplete.suggestions,
        interpretation: search.data?.interpretation,
        total: search.data?.total ?? 0,
        searchTimeMs: search.data?.search_time_ms,
        searchMode: search.data?.search_mode,
        isSearchLoading: search.isLoading || search.isFetching,
        isAutocompleteLoading: autocomplete.isLoading,
        isLoading: search.isLoading || autocomplete.isLoading,
        recentSearches,
    };
}

export default useSpotlightSearch;
