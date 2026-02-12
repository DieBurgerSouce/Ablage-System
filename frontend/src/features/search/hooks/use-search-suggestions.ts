/**
 * useSearchSuggestions - Suchvorschläge aus API
 *
 * Holt Suchvorschläge vom Backend basierend auf der aktuellen Eingabe.
 * Verwendet Debouncing um API-Calls zu reduzieren.
 * Integriert mit Backend API: /api/v1/search/suggest
 *
 * Features:
 * - Debounced API calls (300ms)
 * - Kategorisierte Vorschläge (Tags, Kunden, Dokumenttypen)
 * - Loading und Error States
 *
 * @example
 * ```tsx
 * const { suggestions, isLoading } = useSearchSuggestions(query);
 * ```
 */

import { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface SearchSuggestion {
  id: string;
  text: string;
  category: 'tag' | 'customer' | 'doctype' | 'query';
  count?: number;
  icon?: string;
}

export interface SearchSuggestionsResponse {
  suggestions: SearchSuggestion[];
  didYouMean?: string;
}

// Backend response format
interface BackendSuggestItem {
  text: string;
  type: string; // "document", "tag", "term"
  score: number;
  document_id?: string;
  highlight?: string;
}

interface BackendSuggestResponse {
  query: string;
  suggestions: BackendSuggestItem[];
  total: number;
}

// ==================== Debounce Hook ====================

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

// ==================== Helpers ====================

function mapBackendType(type: string): 'tag' | 'customer' | 'doctype' | 'query' {
  switch (type) {
    case 'tag':
      return 'tag';
    case 'document':
      return 'doctype';
    case 'term':
      return 'query';
    default:
      return 'query';
  }
}

// ==================== API Fetch ====================

async function fetchSuggestions(
  query: string
): Promise<SearchSuggestionsResponse> {
  const response = await apiClient.get<BackendSuggestResponse>(
    `/search/suggest?q=${encodeURIComponent(query)}&limit=10`
  );

  const data = response.data;

  // Transform backend format to frontend format
  const suggestions: SearchSuggestion[] = data.suggestions.map((item, idx) => ({
    id: item.document_id || `${item.type}-${idx}`,
    text: item.text,
    category: mapBackendType(item.type),
    count: undefined,
  }));

  return {
    suggestions,
    didYouMean: undefined, // Backend doesn't support did-you-mean yet
  };
}

// ==================== Hook ====================

export interface UseSearchSuggestionsOptions {
  /** Minimale Zeichenanzahl bevor Vorschläge geladen werden */
  minLength?: number;
  /** Debounce-Zeit in ms */
  debounceMs?: number;
  /** Ist die Suche aktiv? */
  enabled?: boolean;
}

export interface UseSearchSuggestionsReturn {
  /** Kategorisierte Suchvorschläge */
  suggestions: SearchSuggestion[];

  /** Gruppierte Vorschläge nach Kategorie */
  groupedSuggestions: Record<SearchSuggestion['category'], SearchSuggestion[]>;

  /** Did-you-mean Korrekturvorschlag */
  didYouMean: string | undefined;

  /** Ist am Laden */
  isLoading: boolean;

  /** Fehler beim Laden */
  error: Error | null;
}

export function useSearchSuggestions(
  query: string,
  options: UseSearchSuggestionsOptions = {}
): UseSearchSuggestionsReturn {
  const { minLength = 2, debounceMs = 300, enabled = true } = options;

  const debouncedQuery = useDebounce(query, debounceMs);

  const shouldFetch = enabled && debouncedQuery.length >= minLength;

  const { data, isLoading, error } = useQuery({
    queryKey: ['search-suggestions', debouncedQuery],
    queryFn: () => fetchSuggestions(debouncedQuery),
    enabled: shouldFetch,
    staleTime: 60000, // 1 Minute
    gcTime: 300000, // 5 Minuten (was cacheTime in v4)
  });

  // Gruppiere Vorschläge nach Kategorie
  const groupedSuggestions = useMemo(() => {
    const groups: Record<SearchSuggestion['category'], SearchSuggestion[]> = {
      tag: [],
      customer: [],
      doctype: [],
      query: [],
    };

    if (data?.suggestions) {
      data.suggestions.forEach((s) => {
        groups[s.category].push(s);
      });
    }

    return groups;
  }, [data?.suggestions]);

  return {
    suggestions: data?.suggestions ?? [],
    groupedSuggestions,
    didYouMean: data?.didYouMean,
    isLoading: shouldFetch && isLoading,
    error: error as Error | null,
  };
}

export default useSearchSuggestions;
