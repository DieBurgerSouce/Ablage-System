/**
 * useSearchSuggestions - Suchvorschlaege aus API
 *
 * Holt Suchvorschlaege vom Backend basierend auf der aktuellen Eingabe.
 * Verwendet Debouncing um API-Calls zu reduzieren.
 *
 * Features:
 * - Debounced API calls (300ms)
 * - Kategorisierte Vorschlaege (Tags, Kunden, Dokumenttypen)
 * - Did-you-mean Korrekturvorschlaege
 * - Loading und Error States
 *
 * @example
 * ```tsx
 * const { suggestions, isLoading, didYouMean } = useSearchSuggestions(query);
 * ```
 */

import { useState, useEffect, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';

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

// ==================== Debounce Hook ====================

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

// ==================== Mock Data (bis API verfuegbar) ====================

// Mock-Daten fuer Entwicklung - wird spaeter durch echte API ersetzt
const MOCK_TAGS = [
  'Rechnung',
  'Vertrag',
  'Angebot',
  'Lieferschein',
  'Mahnung',
  'Gutschrift',
  'Bestellung',
  'Quittung',
];

const MOCK_CUSTOMERS = [
  'Mustermann GmbH',
  'Schmidt & Partner',
  'Meier AG',
  'Fischer KG',
  'Weber Consulting',
];

const MOCK_DOCTYPES = ['PDF', 'Bild', 'Office', 'Email'];

function getMockSuggestions(query: string): SearchSuggestionsResponse {
  const lowerQuery = query.toLowerCase();
  const suggestions: SearchSuggestion[] = [];

  // Tag-Vorschlaege
  MOCK_TAGS.filter((tag) => tag.toLowerCase().includes(lowerQuery)).forEach(
    (tag, i) => {
      suggestions.push({
        id: `tag-${i}`,
        text: tag,
        category: 'tag',
        count: Math.floor(Math.random() * 50) + 1,
      });
    }
  );

  // Kunden-Vorschlaege
  MOCK_CUSTOMERS.filter((c) => c.toLowerCase().includes(lowerQuery)).forEach(
    (customer, i) => {
      suggestions.push({
        id: `customer-${i}`,
        text: customer,
        category: 'customer',
        count: Math.floor(Math.random() * 20) + 1,
      });
    }
  );

  // Dokumenttyp-Vorschlaege
  MOCK_DOCTYPES.filter((d) => d.toLowerCase().includes(lowerQuery)).forEach(
    (doctype, i) => {
      suggestions.push({
        id: `doctype-${i}`,
        text: doctype,
        category: 'doctype',
      });
    }
  );

  // Did-you-mean (simple typo detection)
  let didYouMean: string | undefined;
  const typoMap: Record<string, string> = {
    rechnugn: 'rechnung',
    rechung: 'rechnung',
    rechnunge: 'rechnung',
    vertarg: 'vertrag',
    anegbot: 'angebot',
    liferung: 'lieferung',
    lieferschien: 'lieferschein',
    mahung: 'mahnung',
    gutschirft: 'gutschrift',
    bestllung: 'bestellung',
    quitung: 'quittung',
  };

  if (typoMap[lowerQuery]) {
    didYouMean = typoMap[lowerQuery];
  }

  return {
    suggestions: suggestions.slice(0, 8),
    didYouMean,
  };
}

// ==================== API Fetch ====================

async function fetchSuggestions(
  query: string
): Promise<SearchSuggestionsResponse> {
  // TODO: Ersetze mit echtem API-Call wenn Backend verfuegbar
  // const response = await fetch(`/api/v1/search/suggestions?q=${encodeURIComponent(query)}`);
  // if (!response.ok) throw new Error('Suggestions API error');
  // return response.json();

  // Simuliere Netzwerk-Latenz
  await new Promise((resolve) => setTimeout(resolve, 100));
  return getMockSuggestions(query);
}

// ==================== Hook ====================

export interface UseSearchSuggestionsOptions {
  /** Minimale Zeichenanzahl bevor Vorschlaege geladen werden */
  minLength?: number;
  /** Debounce-Zeit in ms */
  debounceMs?: number;
  /** Ist die Suche aktiv? */
  enabled?: boolean;
}

export interface UseSearchSuggestionsReturn {
  /** Kategorisierte Suchvorschlaege */
  suggestions: SearchSuggestion[];

  /** Gruppierte Vorschlaege nach Kategorie */
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

  // Gruppiere Vorschlaege nach Kategorie
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
