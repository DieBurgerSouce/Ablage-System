/**
 * Recent Searches Hook
 *
 * Verwaltet kuerzliche Suchbegriffe mit localStorage-Persistenz
 * und Frecency-Algorithmus fuer intelligente Sortierung.
 */

import { useState, useCallback, useEffect } from 'react';
import type { RecentSearch, RecentSearchEntry } from '../types/spotlight-types';

// ==================== Constants ====================

const STORAGE_KEY = 'ablage_spotlight_recent';
const MAX_RECENT_SEARCHES = 10;

// Frecency: Gewichtung nach Aktualitaet
const RECENCY_WEIGHTS = {
  last24h: 1.0,
  lastWeek: 0.7,
  older: 0.4,
} as const;

const ONE_DAY_MS = 24 * 60 * 60 * 1000;
const ONE_WEEK_MS = 7 * ONE_DAY_MS;

// ==================== Helpers ====================

function loadFromStorage(): RecentSearch[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as RecentSearch[];
  } catch {
    return [];
  }
}

function saveToStorage(searches: RecentSearch[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(searches));
  } catch {
    // localStorage voll oder nicht verfuegbar - ignorieren
  }
}

function calculateRecencyWeight(timestamp: number): number {
  const age = Date.now() - timestamp;

  if (age < ONE_DAY_MS) return RECENCY_WEIGHTS.last24h;
  if (age < ONE_WEEK_MS) return RECENCY_WEIGHTS.lastWeek;
  return RECENCY_WEIGHTS.older;
}

function calculateScore(search: RecentSearch): number {
  const recencyWeight = calculateRecencyWeight(search.timestamp);
  return search.frequency * recencyWeight;
}

function sortByFrecency(searches: RecentSearch[]): RecentSearchEntry[] {
  return searches
    .map((search) => ({
      ...search,
      score: calculateScore(search),
    }))
    .sort((a, b) => b.score - a.score);
}

// ==================== Hook ====================

export interface UseRecentSearchesReturn {
  recentSearches: RecentSearchEntry[];
  addSearch: (query: string) => void;
  removeSearch: (query: string) => void;
  clearAll: () => void;
}

export function useRecentSearches(): UseRecentSearchesReturn {
  const [searches, setSearches] = useState<RecentSearch[]>(() => loadFromStorage());

  // Sync mit localStorage bei Aenderungen
  useEffect(() => {
    saveToStorage(searches);
  }, [searches]);

  const addSearch = useCallback((query: string) => {
    const trimmed = query.trim();
    if (trimmed.length < 2) return;

    setSearches((prev) => {
      const existing = prev.find(
        (s) => s.query.toLowerCase() === trimmed.toLowerCase()
      );

      let updated: RecentSearch[];

      if (existing) {
        // Frequenz erhoehen und Zeitstempel aktualisieren
        updated = prev.map((s) =>
          s.query.toLowerCase() === trimmed.toLowerCase()
            ? { ...s, frequency: s.frequency + 1, timestamp: Date.now() }
            : s
        );
      } else {
        // Neuen Eintrag hinzufuegen
        const newEntry: RecentSearch = {
          query: trimmed,
          timestamp: Date.now(),
          frequency: 1,
        };
        updated = [newEntry, ...prev];
      }

      // Auf Maximum begrenzen (nach Frecency sortiert, aelteste entfernen)
      if (updated.length > MAX_RECENT_SEARCHES) {
        const sorted = sortByFrecency(updated);
        updated = sorted.slice(0, MAX_RECENT_SEARCHES).map(({ score: _score, ...rest }) => rest);
      }

      return updated;
    });
  }, []);

  const removeSearch = useCallback((query: string) => {
    setSearches((prev) =>
      prev.filter((s) => s.query.toLowerCase() !== query.toLowerCase())
    );
  }, []);

  const clearAll = useCallback(() => {
    setSearches([]);
  }, []);

  const recentSearches = sortByFrecency(searches);

  return {
    recentSearches,
    addSearch,
    removeSearch,
    clearAll,
  };
}
