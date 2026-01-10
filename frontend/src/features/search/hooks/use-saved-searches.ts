/**
 * useSavedSearches - LocalStorage-basierte gespeicherte Suchen
 *
 * CRUD-Operationen fuer gespeicherte Suchen mit LocalStorage Persistenz.
 *
 * @example
 * ```tsx
 * const { savedSearches, saveSearch, deleteSearch, updateSearch } = useSavedSearches();
 *
 * // Neue Suche speichern
 * saveSearch({
 *   name: 'Rechnungen 2024',
 *   params: { q: 'rechnung', type: ['pdf'] }
 * });
 *
 * // Suche loeschen
 * deleteSearch(searchId);
 * ```
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from 'sonner';
import {
  type SavedSearch,
  type CreateSavedSearchInput,
  createSavedSearch,
  validateSavedSearches,
  SAVED_SEARCHES_STORAGE_KEY,
} from '../types/saved-search';

// ==================== Storage Helpers ====================

function loadFromStorage(): SavedSearch[] {
  try {
    const stored = localStorage.getItem(SAVED_SEARCHES_STORAGE_KEY);
    if (!stored) return [];
    const parsed = JSON.parse(stored);
    return validateSavedSearches(parsed);
  } catch (error) {
    console.error('[useSavedSearches] Fehler beim Laden:', error);
    return [];
  }
}

function saveToStorage(searches: SavedSearch[]): boolean {
  try {
    localStorage.setItem(SAVED_SEARCHES_STORAGE_KEY, JSON.stringify(searches));
    return true;
  } catch (error) {
    // Handle QuotaExceededError and Privacy Mode
    const isQuotaError =
      error instanceof Error &&
      (error.name === 'QuotaExceededError' ||
        error.message.includes('quota') ||
        error.message.includes('storage'));

    console.error('[useSavedSearches] Fehler beim Speichern:', error);

    if (isQuotaError) {
      toast.error('Speicherlimit erreicht', {
        description:
          'Der lokale Speicher ist voll. Bitte löschen Sie einige gespeicherte Suchen.',
      });
    } else {
      toast.error('Speichern nicht möglich', {
        description:
          'Die Suche konnte nicht gespeichert werden. Möglicherweise ist der private Modus aktiv.',
      });
    }
    return false;
  }
}

// ==================== Hook ====================

export interface UseSavedSearchesReturn {
  /** Alle gespeicherten Suchen */
  savedSearches: SavedSearch[];

  /** Gepinnte Suchen (fuer Sidebar) */
  pinnedSearches: SavedSearch[];

  /** Neue Suche speichern */
  saveSearch: (input: CreateSavedSearchInput) => SavedSearch;

  /** Suche loeschen */
  deleteSearch: (id: string) => void;

  /** Suche aktualisieren */
  updateSearch: (id: string, updates: Partial<SavedSearch>) => void;

  /** Suche pinnen/unpinnen */
  togglePin: (id: string) => void;

  /** Zugriff auf Suche registrieren (fuer "zuletzt verwendet") */
  recordAccess: (id: string) => void;

  /** Alle Suchen loeschen */
  clearAll: () => void;

  /** Suche nach ID finden */
  getSearchById: (id: string) => SavedSearch | undefined;

  /** Ob Limit erreicht ist */
  isLimitReached: boolean;
}

const MAX_SAVED_SEARCHES = 50;

export function useSavedSearches(): UseSavedSearchesReturn {
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);

  // Debounce timer for recordAccess to prevent excessive writes
  const accessDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingAccessUpdatesRef = useRef<Map<string, { lastAccessedAt: string; accessCount: number }>>(new Map());

  // Initial load
  useEffect(() => {
    setSavedSearches(loadFromStorage());
  }, []);

  // Persist on change
  useEffect(() => {
    if (savedSearches.length > 0 || localStorage.getItem(SAVED_SEARCHES_STORAGE_KEY)) {
      saveToStorage(savedSearches);
    }
  }, [savedSearches]);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (accessDebounceRef.current) {
        clearTimeout(accessDebounceRef.current);
      }
    };
  }, []);

  // ==================== CRUD Operations ====================

  const saveSearch = useCallback((input: CreateSavedSearchInput): SavedSearch => {
    // KRITISCH: Alles INNERHALB setState um Race Conditions zu vermeiden!
    // Das newSearch-Objekt muss im Callback erstellt werden, damit wir garantieren
    // dass prev.length der aktuelle Wert ist.
    let newSearch: SavedSearch | null = null;
    let wasLimitReached = false;

    setSavedSearches((prev) => {
      if (prev.length >= MAX_SAVED_SEARCHES) {
        wasLimitReached = true;
        return prev; // Keine Aenderung
      }
      // Erstelle newSearch INNERHALB des Callbacks mit dem garantiert aktuellen State
      newSearch = createSavedSearch(input);
      return [newSearch, ...prev];
    });

    // Toast-Nachrichten NACH dem setState basierend auf dem Ergebnis
    if (wasLimitReached) {
      toast.error('Limit erreicht', {
        description: `Maximal ${MAX_SAVED_SEARCHES} Suchen können gespeichert werden.`,
      });
      throw new Error('Saved searches limit reached');
    }

    // newSearch ist garantiert nicht null wenn wasLimitReached false ist
    toast.success('Suche gespeichert', {
      description: `"${input.name}" wurde gespeichert.`,
    });

    // TypeScript Safety: Wir wissen dass newSearch hier nicht null sein kann
    // weil wasLimitReached false ist und setState synchron den Wert gesetzt hat
    return newSearch as SavedSearch;
  }, []); // Keine Dependencies - funktionales Update Pattern

  const deleteSearch = useCallback((id: string) => {
    setSavedSearches((prev) => {
      const search = prev.find((s) => s.id === id);
      if (search) {
        toast.success('Suche gelöscht', {
          description: `"${search.name}" wurde entfernt.`,
          action: {
            label: 'Rückgängig',
            onClick: () => {
              setSavedSearches((current) => [search, ...current]);
            },
          },
        });
      }
      return prev.filter((s) => s.id !== id);
    });
  }, []);

  const updateSearch = useCallback(
    (id: string, updates: Partial<SavedSearch>) => {
      setSavedSearches((prev) =>
        prev.map((search) =>
          search.id === id ? { ...search, ...updates } : search
        )
      );
    },
    []
  );

  const togglePin = useCallback((id: string) => {
    setSavedSearches((prev) =>
      prev.map((search) =>
        search.id === id ? { ...search, pinned: !search.pinned } : search
      )
    );
  }, []);

  const recordAccess = useCallback((id: string) => {
    // Debounce access updates to prevent excessive localStorage writes
    // Collect updates and batch them after 1 second of inactivity
    const now = new Date().toISOString();
    const current = pendingAccessUpdatesRef.current.get(id);
    pendingAccessUpdatesRef.current.set(id, {
      lastAccessedAt: now,
      accessCount: (current?.accessCount ?? 0) + 1,
    });

    // Clear existing timer
    if (accessDebounceRef.current) {
      clearTimeout(accessDebounceRef.current);
    }

    // Batch update after 1 second
    accessDebounceRef.current = setTimeout(() => {
      const updates = pendingAccessUpdatesRef.current;
      if (updates.size === 0) return;

      setSavedSearches((prev) =>
        prev.map((search) => {
          const update = updates.get(search.id);
          if (!update) return search;
          return {
            ...search,
            lastAccessedAt: update.lastAccessedAt,
            accessCount: search.accessCount + update.accessCount,
          };
        })
      );

      pendingAccessUpdatesRef.current.clear();
    }, 1000);
  }, []);

  const clearAll = useCallback(() => {
    // KRITISCH: Functional update Pattern um savedSearches Dependency zu vermeiden
    // Sonst wird bei JEDEM Save ein neuer Callback erstellt (Memory Leak)
    let backup: SavedSearch[] = [];

    setSavedSearches((prev) => {
      backup = prev;
      return [];
    });

    // Toast NACH setState, backup ist jetzt gefuellt
    toast.success('Alle Suchen gelöscht', {
      description: `${backup.length} Suchen wurden entfernt.`,
      action: {
        label: 'Rückgängig',
        onClick: () => {
          // backup ist in dieser Closure stabil - kein savedSearches Dependency noetig
          setSavedSearches(backup);
        },
      },
    });
  }, []); // Keine Dependencies - functional update Pattern

  const getSearchById = useCallback(
    (id: string): SavedSearch | undefined => {
      return savedSearches.find((s) => s.id === id);
    },
    [savedSearches]
  );

  // ==================== Derived State ====================

  const pinnedSearches = savedSearches.filter((s) => s.pinned);
  const isLimitReached = savedSearches.length >= MAX_SAVED_SEARCHES;

  return {
    savedSearches,
    pinnedSearches,
    saveSearch,
    deleteSearch,
    updateSearch,
    togglePin,
    recordAccess,
    clearAll,
    getSearchById,
    isLimitReached,
  };
}

// ==================== Standalone Functions ====================

/**
 * Laedt gespeicherte Suchen direkt aus LocalStorage.
 * Nuetzlich ausserhalb von React-Komponenten.
 */
export function getSavedSearches(): SavedSearch[] {
  return loadFromStorage();
}

/**
 * Prueft ob eine Suche mit diesem Namen existiert.
 */
export function searchNameExists(name: string): boolean {
  const searches = loadFromStorage();
  return searches.some(
    (s) => s.name.toLowerCase() === name.toLowerCase().trim()
  );
}

export default useSavedSearches;
