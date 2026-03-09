/**
 * SpotlightResults Component
 *
 * Rendert die gruppierten Suchergebnisse:
 * Vorschlaege, Dokumente, Kunden & Lieferanten.
 */

import { CommandGroup, CommandEmpty } from '@/components/ui/command';
import { SuggestionItem, DocumentItem, EntityItem } from './SpotlightResultItem';
import type { SpotlightResultsResponse } from '../types/spotlight-types';

// ==================== Props ====================

interface SpotlightResultsProps {
  results: SpotlightResultsResponse;
  query: string;
  onSelect: () => void;
}

// ==================== Component ====================

export function SpotlightResults({ results, query, onSelect }: SpotlightResultsProps) {
  const { suggestions, documents, entities } = results;
  const hasResults = suggestions.length > 0 || documents.length > 0 || entities.length > 0;

  if (!hasResults && query.length >= 2) {
    return (
      <CommandEmpty>
        Keine Ergebnisse gefunden fuer &ldquo;{query}&rdquo;
      </CommandEmpty>
    );
  }

  return (
    <>
      {suggestions.length > 0 && (
        <CommandGroup heading="Vorschlaege">
          {suggestions.map((suggestion, index) => (
            <SuggestionItem
              key={`suggestion-${index}-${suggestion.text}`}
              suggestion={suggestion}
              onSelect={onSelect}
            />
          ))}
        </CommandGroup>
      )}

      {documents.length > 0 && (
        <CommandGroup heading="Dokumente">
          {documents.map((doc) => (
            <DocumentItem
              key={doc.documentId}
              document={doc}
              onSelect={onSelect}
            />
          ))}
        </CommandGroup>
      )}

      {entities.length > 0 && (
        <CommandGroup heading="Kunden & Lieferanten">
          {entities.map((entity) => (
            <EntityItem
              key={entity.entityId}
              entity={entity}
              onSelect={onSelect}
            />
          ))}
        </CommandGroup>
      )}
    </>
  );
}
