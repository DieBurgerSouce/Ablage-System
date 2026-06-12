/**
 * FacetSidebar - Facetten-Filter für die Suchseite
 *
 * Zeigt Facetten-Gruppen mit Anzahlen vom /search/facets Endpoint.
 * Alle Texte in Deutsch.
 */
import { useFacets } from '../hooks/useFacets';
import { FacetSection } from './FacetSection';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import {
  Filter,
  Bookmark,
  Share2,
  Trash2,
  Users,
} from 'lucide-react';
import { useSavedSearches } from '../hooks/use-saved-searches';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import type { SavedSearch } from '../types/saved-search';
import { cn } from '@/lib/utils';

interface FacetSidebarProps {
  selectedTypes: string[];
  onTypesChange: (types: string[]) => void;
  selectedStatuses: string[];
  onStatusesChange: (statuses: string[]) => void;
  selectedTags: string[];
  onTagsChange: (tags: string[]) => void;
  selectedBackends: string[];
  onBackendsChange: (backends: string[]) => void;
}

/** Zuordnung von Backend-Feldnamen zu deutschen Sidebar-Überschriften */
const SECTION_LABELS: Record<string, string> = {
  document_type: 'Dokumenttyp',
  status: 'Status',
  tags: 'Tags',
  ocr_backend_used: 'OCR-Backend',
};

export function FacetSidebar({
  selectedTypes,
  onTypesChange,
  selectedStatuses,
  onStatusesChange,
  selectedTags,
  onTagsChange,
  selectedBackends,
  onBackendsChange,
}: FacetSidebarProps) {
  const { data, isLoading } = useFacets({
    documentType: selectedTypes.length === 1 ? selectedTypes[0] : undefined,
    status: selectedStatuses.length === 1 ? selectedStatuses[0] : undefined,
  });

  // Load saved searches from localStorage
  const { savedSearches, deleteSearch } = useSavedSearches();

  // Load shared filters from backend (optional - can be mocked for now)
  const { data: sharedFilters } = useQuery({
    queryKey: ['saved-filters', 'shared'],
    queryFn: async () => {
      try {
        const response = await apiClient.get<{ filters: SavedSearch[] }>('/saved-filters/shared');
        return response.data.filters || [];
      } catch (error) {
        // Endpoint might not exist yet - return empty array
        return [];
      }
    },
    // Don't retry if endpoint doesn't exist
    retry: false,
    // Cache for 5 minutes
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="h-4 w-4" />
          <span className="font-medium text-sm">Filter</span>
        </div>
        {[1, 2, 3].map(i => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-3/4" />
          </div>
        ))}
      </div>
    );
  }

  const facetGroups = data?.facets || [];

  /** Zuordnung: Feld-Name -> onChange-Handler und selected-Array */
  const sectionHandlers: Record<string, { selected: string[]; onChange: (v: string[]) => void }> = {
    document_type: { selected: selectedTypes, onChange: onTypesChange },
    status: { selected: selectedStatuses, onChange: onStatusesChange },
    tags: { selected: selectedTags, onChange: onTagsChange },
    ocr_backend_used: { selected: selectedBackends, onChange: onBackendsChange },
  };

  /** Gewünschte Reihenfolge der Sektionen */
  const fieldOrder = ['document_type', 'status', 'tags', 'ocr_backend_used'];

  /** Facet-Gruppen nach Feld sortieren und nur bekannte Felder anzeigen */
  const orderedGroups = fieldOrder
    .map(field => facetGroups.find(g => g.field === field))
    .filter((g): g is NonNullable<typeof g> => g !== undefined && g.values.length > 0);

  const handleApplySavedSearch = (search: SavedSearch) => {
    // Apply the saved search filters
    if (search.params.type) onTypesChange(search.params.type as string[]);
    if (search.params.ocrStatus) onStatusesChange(search.params.ocrStatus as string[]);
    // Additional filter mappings can be added here
  };

  return (
    <div className="p-4 space-y-4">
      {/* Saved Filters Section */}
      {(savedSearches.length > 0 || (sharedFilters && sharedFilters.length > 0)) && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 pb-2 border-b">
            <Bookmark className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium text-sm">Gespeicherte Filter</span>
          </div>

          {/* Personal Saved Searches */}
          {savedSearches.length > 0 && (
            <div className="space-y-1">
              {savedSearches.slice(0, 5).map((search) => (
                <button
                  key={search.id}
                  onClick={() => handleApplySavedSearch(search)}
                  className={cn(
                    'w-full flex items-center justify-between gap-2',
                    'px-2 py-1.5 rounded-md text-sm',
                    'hover:bg-accent hover:text-accent-foreground',
                    'transition-colors text-left'
                  )}
                  title={search.description || search.name}
                >
                  <span className="truncate flex-1">{search.name}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    {search.pinned && (
                      <Bookmark className="h-3 w-3 fill-current" />
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-5 w-5"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSearch(search.id);
                      }}
                      title="Filter löschen"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </button>
              ))}
              {savedSearches.length > 5 && (
                <p className="text-xs text-muted-foreground px-2 pt-1">
                  +{savedSearches.length - 5} weitere
                </p>
              )}
            </div>
          )}

          {/* Shared Filters */}
          {sharedFilters && sharedFilters.length > 0 && (
            <div className="space-y-1 mt-3">
              <div className="flex items-center gap-1.5 px-2">
                <Users className="h-3 w-3 text-muted-foreground" />
                <span className="text-xs font-medium text-muted-foreground">
                  Geteilte Filter
                </span>
              </div>
              {sharedFilters.slice(0, 3).map((filter) => (
                <button
                  key={filter.id}
                  onClick={() => handleApplySavedSearch(filter)}
                  className={cn(
                    'w-full flex items-center justify-between gap-2',
                    'px-2 py-1.5 rounded-md text-sm',
                    'hover:bg-accent hover:text-accent-foreground',
                    'transition-colors text-left'
                  )}
                >
                  <span className="truncate flex-1">{filter.name}</span>
                  <Share2 className="h-3 w-3 shrink-0 text-muted-foreground" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Facets Section */}
      <div className="space-y-1">
        <div className="flex items-center gap-2 pb-2 border-b">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-sm">Facetten-Filter</span>
          {data?.total_documents !== undefined && (
            <span className="text-xs text-muted-foreground ml-auto">
              {data.total_documents} Dokumente
            </span>
          )}
        </div>

        {orderedGroups.map((group) => {
          const handler = sectionHandlers[group.field];
          if (!handler) return null;

          return (
            <FacetSection
              key={group.field}
              title={SECTION_LABELS[group.field] || group.label}
              buckets={group.values}
              selected={handler.selected}
              onChange={handler.onChange}
            />
          );
        })}

        {orderedGroups.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Keine Facetten verfügbar
          </p>
        )}
      </div>
    </div>
  );
}
