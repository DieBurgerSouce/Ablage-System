/**
 * FacetSidebar - Facetten-Filter fuer die Suchseite
 *
 * Zeigt Facetten-Gruppen mit Anzahlen vom /search/facets Endpoint.
 * Alle Texte in Deutsch.
 */
import { useFacets } from '../hooks/useFacets';
import { FacetSection } from './FacetSection';
import { Skeleton } from '@/components/ui/skeleton';
import { Filter } from 'lucide-react';

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

/** Zuordnung von Backend-Feldnamen zu deutschen Sidebar-Ueberschriften */
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

  /** Gewuenschte Reihenfolge der Sektionen */
  const fieldOrder = ['document_type', 'status', 'tags', 'ocr_backend_used'];

  /** Facet-Gruppen nach Feld sortieren und nur bekannte Felder anzeigen */
  const orderedGroups = fieldOrder
    .map(field => facetGroups.find(g => g.field === field))
    .filter((g): g is NonNullable<typeof g> => g !== undefined && g.values.length > 0);

  return (
    <div className="p-4 space-y-1">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b">
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
          Keine Facetten verfuegbar
        </p>
      )}
    </div>
  );
}
