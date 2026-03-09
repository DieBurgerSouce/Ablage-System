/**
 * SpotlightDialog Component
 *
 * Globaler Such-Dialog (Cmd+K / Ctrl+K).
 * Nutzt shadcn/ui Command-Komponenten mit Debounced API-Suche.
 */

import { useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandSeparator,
} from '@/components/ui/command';
import { useSpotlight } from '../hooks/use-spotlight';
import { useRecentSearches } from '../hooks/use-recent-searches';
import { RecentSearches } from './RecentSearches';
import { SpotlightResults } from './SpotlightResults';

// ==================== Component ====================

export function SpotlightDialog() {
  const {
    isOpen,
    close,
    query,
    setQuery,
    debouncedQuery,
    results,
    isLoading,
  } = useSpotlight();

  const {
    recentSearches,
    addSearch,
    removeSearch,
  } = useRecentSearches();

  // Suche ausfuehren und Dialog schliessen
  const handleSelect = useCallback(() => {
    if (query.trim().length >= 2) {
      addSearch(query.trim());
    }
    close();
  }, [query, addSearch, close]);

  // Letzte Suche wiederholen
  const handleRecentSelect = useCallback(
    (recentQuery: string) => {
      setQuery(recentQuery);
      addSearch(recentQuery);
    },
    [setQuery, addSearch]
  );

  // Dialog open/close Handler
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        close();
      }
    },
    [close]
  );

  const showRecentSearches = query.length < 2 && recentSearches.length > 0;
  const showResults = results && debouncedQuery.length >= 2;
  const showEmptyState = !showRecentSearches && !showResults && !isLoading && query.length < 2;

  return (
    <CommandDialog open={isOpen} onOpenChange={handleOpenChange}>
      <CommandInput
        placeholder="Suchen oder Befehl eingeben..."
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        {/* Ladeindikator */}
        {isLoading && (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">
              Suche...
            </span>
          </div>
        )}

        {/* Leerer Zustand - Hinweis zum Tippen */}
        {showEmptyState && (
          <CommandEmpty>
            Mindestens 2 Zeichen eingeben um zu suchen
          </CommandEmpty>
        )}

        {/* Letzte Suchen (nur wenn keine aktive Suche) */}
        {showRecentSearches && (
          <RecentSearches
            searches={recentSearches}
            onSelect={handleRecentSelect}
            onRemove={removeSearch}
          />
        )}

        {/* Suchergebnisse */}
        {showResults && !isLoading && (
          <SpotlightResults
            results={results}
            query={debouncedQuery}
            onSelect={handleSelect}
          />
        )}
      </CommandList>

      {/* Footer mit Suchzeit und Interpretation */}
      {showResults && !isLoading && (
        <>
          <CommandSeparator />
          <div className="flex items-center justify-between px-3 py-2 text-xs text-muted-foreground">
            <span>
              {results.totalDocuments} Dokument{results.totalDocuments !== 1 ? 'e' : ''} gefunden
            </span>
            <div className="flex items-center gap-2">
              {results.interpretation && (
                <span className="italic">
                  {results.interpretation.searchMode === 'nlq'
                    ? 'KI-Suche'
                    : 'Stichwortsuche'}
                  {results.interpretation.interpretedAs !== results.interpretation.originalQuery && (
                    <> &middot; &ldquo;{results.interpretation.interpretedAs}&rdquo;</>
                  )}
                </span>
              )}
              <span>{results.searchTimeMs}ms</span>
            </div>
          </div>
        </>
      )}
    </CommandDialog>
  );
}
