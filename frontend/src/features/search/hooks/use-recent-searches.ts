/**
 * useRecentSearches - Automatisch gespeicherte letzte Suchanfragen
 *
 * Speichert die letzten N Suchanfragen automatisch in LocalStorage.
 * Unterscheidet sich von useSavedSearches:
 * - Automatisch, nicht manuell gespeichert
 * - Nur die Query, keine Filter
 * - Begrenzt auf MAX_RECENT_SEARCHES
 * - LIFO-Queue (neueste zuerst)
 *
 * @example
 * ```tsx
 * const { recentSearches, addRecentSearch, clearRecentSearches } = useRecentSearches();
 * ```
 */

import { useState, useEffect, useCallback } from 'react';
import { logger } from '@/lib/logger';

// ==================== Types ====================

export interface RecentSearch {
  id: string;
  query: string;
  timestamp: number;
}

// ==================== Constants ====================

const STORAGE_KEY = 'ablage-recent-searches';
const MAX_RECENT_SEARCHES = 8;

// ==================== Storage Helpers ====================

function loadFromStorage(): RecentSearch[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];
    const parsed = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    // Validate structure
    return parsed.filter(
      (item): item is RecentSearch =>
        typeof item === 'object' &&
        typeof item.id === 'string' &&
        typeof item.query === 'string' &&
        typeof item.timestamp === 'number'
    );
  } catch (error) {
    logger.error('Fehler beim Laden der letzten Suchanfragen', error);
    return [];
  }
}

function saveToStorage(searches: RecentSearch[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(searches));
  } catch (error) {
    logger.error('Fehler beim Speichern der letzten Suchanfragen', error);
  }
}

// ==================== Hook ====================

export interface UseRecentSearchesReturn {
  /** Letzte Suchanfragen (neueste zuerst) */
  recentSearches: RecentSearch[];

  /** Fuegt eine neue Suche hinzu */
  addRecentSearch: (query: string) => void;

  /** Entfernt eine bestimmte Suche */
  removeRecentSearch: (id: string) => void;

  /** Loescht alle letzten Suchen */
  clearRecentSearches: () => void;
}

export function useRecentSearches(): UseRecentSearchesReturn {
  const [recentSearches, setRecentSearches] = useState<RecentSearch[]>([]);

  // Initial load
  useEffect(() => {
    setRecentSearches(loadFromStorage());
  }, []);

  // Persist on change
  useEffect(() => {
    saveToStorage(recentSearches);
  }, [recentSearches]);

  const addRecentSearch = useCallback((query: string) => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery || trimmedQuery.length < 2) return;

    setRecentSearches((prev) => {
      // Entferne duplikate (case-insensitive)
      const filtered = prev.filter(
        (s) => s.query.toLowerCase() !== trimmedQuery.toLowerCase()
      );

      // Neue Suche an den Anfang
      const newSearch: RecentSearch = {
        id: `recent-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        query: trimmedQuery,
        timestamp: Date.now(),
      };

      // Begrenzen auf MAX
      return [newSearch, ...filtered].slice(0, MAX_RECENT_SEARCHES);
    });
  }, []);

  const removeRecentSearch = useCallback((id: string) => {
    setRecentSearches((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const clearRecentSearches = useCallback(() => {
    setRecentSearches([]);
  }, []);

  return {
    recentSearches,
    addRecentSearch,
    removeRecentSearch,
    clearRecentSearches,
  };
}

export default useRecentSearches;
