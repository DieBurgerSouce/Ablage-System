/**
 * useRecentItems - Generischer Hook für zuletzt verwendete Elemente
 *
 * Speichert die letzten N Elemente automatisch in LocalStorage.
 * LIFO-Queue (neueste zuerst) mit Deduplizierung.
 *
 * @example
 * ```tsx
 * const { items, addItem, removeItem, clear, hasItems } = useRecentItems<Document>({
 *   storageKey: 'ablage-recent-documents',
 *   maxItems: 15,
 * });
 * ```
 */

import { useState, useEffect, useCallback } from 'react';

// ==================== Types ====================

interface RecentItem<T> {
  item: T;
  timestamp: number;
}

interface UseRecentItemsOptions {
  /** localStorage Schlüssel */
  storageKey: string;
  /** Maximale Anzahl gespeicherter Elemente (Standard: 10) */
  maxItems?: number;
  /** Schlüssel für Deduplizierung (Standard: 'id') */
  dedupKey?: string;
}

interface UseRecentItemsReturn<T> {
  /** Zuletzt verwendete Elemente (neueste zuerst) */
  items: T[];
  /** Fügt ein Element hinzu */
  addItem: (item: T) => void;
  /** Entfernt ein Element anhand der ID */
  removeItem: (id: string) => void;
  /** Löscht alle gespeicherten Elemente */
  clear: () => void;
  /** Ob Elemente vorhanden sind */
  hasItems: boolean;
}

// ==================== Storage Helpers ====================

function loadFromStorage<T>(key: string): RecentItem<T>[] {
  try {
    const stored = localStorage.getItem(key);
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is RecentItem<T> =>
        typeof entry === 'object' &&
        entry !== null &&
        'item' in entry &&
        typeof (entry as RecentItem<T>).timestamp === 'number'
    );
  } catch {
    return [];
  }
}

function saveToStorage<T>(key: string, entries: RecentItem<T>[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(entries));
  } catch {
    // Quota exceeded or storage unavailable
  }
}

// ==================== Hook ====================

export function useRecentItems<T extends Record<string, unknown> & { id: string }>(
  options: UseRecentItemsOptions
): UseRecentItemsReturn<T> {
  const { storageKey, maxItems = 10, dedupKey = 'id' } = options;

  const [entries, setEntries] = useState<RecentItem<T>[]>([]);

  // Initial load
  useEffect(() => {
    setEntries(loadFromStorage<T>(storageKey));
  }, [storageKey]);

  // Persist on change
  useEffect(() => {
    saveToStorage(storageKey, entries);
  }, [storageKey, entries]);

  const addItem = useCallback(
    (item: T) => {
      setEntries((prev) => {
        const key = dedupKey as keyof T;
        const itemKey = String(item[key]);

        // Entferne Duplikat falls vorhanden
        const filtered = prev.filter(
          (entry) => String(entry.item[key]) !== itemKey
        );

        // Neues Element an den Anfang
        const newEntry: RecentItem<T> = {
          item,
          timestamp: Date.now(),
        };

        return [newEntry, ...filtered].slice(0, maxItems);
      });
    },
    [dedupKey, maxItems]
  );

  const removeItem = useCallback(
    (id: string) => {
      const key = dedupKey as keyof T;
      setEntries((prev) =>
        prev.filter((entry) => String(entry.item[key]) !== id)
      );
    },
    [dedupKey]
  );

  const clear = useCallback(() => {
    setEntries([]);
  }, []);

  return {
    items: entries.map((e) => e.item),
    addItem,
    removeItem,
    clear,
    hasItems: entries.length > 0,
  };
}
