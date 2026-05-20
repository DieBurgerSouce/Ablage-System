/**
 * RecentSearches Component
 *
 * Zeigt kuerzliche Suchbegriffe als CommandGroup an.
 * Klick fuehrt die Suche erneut aus, X-Button entfernt einzelne Eintraege.
 */

import { Clock, X } from 'lucide-react';
import {
  CommandGroup,
  CommandItem,
} from '@/components/ui/command';
import type { RecentSearchEntry } from '../types/spotlight-types';

// ==================== Props ====================

interface RecentSearchesProps {
  searches: RecentSearchEntry[];
  onSelect: (query: string) => void;
  onRemove: (query: string) => void;
}

// ==================== Component ====================

export function RecentSearches({
  searches,
  onSelect,
  onRemove,
}: RecentSearchesProps) {
  if (searches.length === 0) return null;

  return (
    <CommandGroup heading="Letzte Suchen">
      {searches.map((search) => (
        <CommandItem
          key={search.query}
          value={`recent-${search.query}`}
          onSelect={() => onSelect(search.query)}
          className="flex items-center justify-between gap-2"
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{search.query}</span>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRemove(search.query);
            }}
            className="shrink-0 p-0.5 rounded hover:bg-muted transition-colors"
            aria-label={`"${search.query}" aus letzten Suchen entfernen`}
          >
            <X className="h-3 w-3 text-muted-foreground" />
          </button>
        </CommandItem>
      ))}
    </CommandGroup>
  );
}
