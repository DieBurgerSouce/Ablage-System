/**
 * FacetFilter - Hauptkomponente für Facetten-basierte Filterung
 *
 * Features:
 * - Sidebar-Layout mit mehreren Facetten-Gruppen
 * - Integration mit TanStack Table getFacetedUniqueValues()
 * - Aktive Filter anzeigen und entfernen
 * - Reset aller Filter
 * - Responsive: Collapsible auf mobilen Geräten
 */

import * as React from 'react';
import { Filter, RotateCcw, SlidersHorizontal, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { FacetGroup, type FacetValue } from './FacetGroup';

export interface FacetConfig {
  /** Eindeutiger Schlüssel für die Facette (z.B. Spalten-ID) */
  id: string;
  /** Anzeige-Titel */
  title: string;
  /** Verfügbare Werte mit Zaehler */
  values: FacetValue[];
  /** Ausgewaehlte Werte */
  selectedValues: string[];
  /** Standard-Offen-Status */
  defaultOpen?: boolean;
}

export interface FacetFilterProps {
  /** Konfiguration der Facetten-Gruppen */
  facets: FacetConfig[];
  /** Callback bei Änderung einer Facette */
  onFacetChange: (facetId: string, values: string[]) => void;
  /** Callback zum Zurücksetzen aller Filter */
  onResetAll?: () => void;
  /** Titel der Filter-Sidebar */
  title?: string;
  /** Ob die Sidebar sichtbar ist (desktop) */
  isVisible?: boolean;
  /** Callback um Sichtbarkeit zu toggeln */
  onVisibilityChange?: (visible: boolean) => void;
  /** Zusätzliche CSS-Klassen für die Sidebar */
  className?: string;
  /** Breite der Sidebar in Pixeln */
  width?: number;
}

export function FacetFilter({
  facets,
  onFacetChange,
  onResetAll,
  title = 'Filter',
  isVisible = true,
  onVisibilityChange,
  className,
  width = 280,
}: FacetFilterProps) {
  // Count total active filters
  const activeFilterCount = React.useMemo(
    () => facets.reduce((sum, f) => sum + f.selectedValues.length, 0),
    [facets]
  );

  // Get active filter tags for display
  const activeFilters = React.useMemo(() => {
    const filters: Array<{
      facetId: string;
      facetTitle: string;
      value: string;
      label: string;
    }> = [];

    facets.forEach((facet) => {
      facet.selectedValues.forEach((value) => {
        const valueInfo = facet.values.find((v) => v.value === value);
        filters.push({
          facetId: facet.id,
          facetTitle: facet.title,
          value,
          label: valueInfo?.label ?? value,
        });
      });
    });

    return filters;
  }, [facets]);

  const handleRemoveFilter = React.useCallback(
    (facetId: string, value: string) => {
      const facet = facets.find((f) => f.id === facetId);
      if (facet) {
        onFacetChange(
          facetId,
          facet.selectedValues.filter((v) => v !== value)
        );
      }
    },
    [facets, onFacetChange]
  );

  const handleResetAll = React.useCallback(() => {
    if (onResetAll) {
      onResetAll();
    } else {
      facets.forEach((facet) => {
        if (facet.selectedValues.length > 0) {
          onFacetChange(facet.id, []);
        }
      });
    }
  }, [facets, onFacetChange, onResetAll]);

  // Desktop Sidebar Content
  const sidebarContent = (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4" aria-hidden="true" />
          <h2 className="font-semibold">{title}</h2>
          {activeFilterCount > 0 && (
            <Badge variant="secondary" className="h-5 px-1.5">
              {activeFilterCount}
            </Badge>
          )}
        </div>
        {activeFilterCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleResetAll}
            className="h-8 text-xs"
            aria-label="Alle Filter zurücksetzen"
          >
            <RotateCcw className="h-3 w-3 mr-1" aria-hidden="true" />
            Zurücksetzen
          </Button>
        )}
      </div>

      <Separator />

      {/* Active Filter Tags */}
      {activeFilters.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">
            Aktive Filter
          </p>
          <div className="flex flex-wrap gap-1.5">
            {activeFilters.map((filter) => (
              <Badge
                key={`${filter.facetId}-${filter.value}`}
                variant="secondary"
                className="pl-2 pr-1 py-0.5 gap-1 text-xs"
              >
                <span className="text-muted-foreground">
                  {filter.facetTitle}:
                </span>
                <span>{filter.label}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-4 w-4 p-0 hover:bg-transparent"
                  onClick={() =>
                    handleRemoveFilter(filter.facetId, filter.value)
                  }
                  aria-label={`Filter ${filter.label} entfernen`}
                >
                  <X className="h-3 w-3" />
                </Button>
              </Badge>
            ))}
          </div>
          <Separator />
        </div>
      )}

      {/* Facet Groups */}
      <ScrollArea className="h-[calc(100vh-280px)]">
        <div className="space-y-1 pr-4">
          {facets.map((facet) => (
            <FacetGroup
              key={facet.id}
              title={facet.title}
              values={facet.values}
              selectedValues={facet.selectedValues}
              onSelectionChange={(values) => onFacetChange(facet.id, values)}
              defaultOpen={facet.defaultOpen ?? true}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  );

  return (
    <>
      {/* Mobile: Sheet Trigger */}
      <div className="lg:hidden">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm" className="h-9">
              <SlidersHorizontal className="h-4 w-4 mr-2" aria-hidden="true" />
              Filter
              {activeFilterCount > 0 && (
                <Badge
                  variant="secondary"
                  className="ml-2 h-5 px-1.5 bg-primary/10 text-primary"
                >
                  {activeFilterCount}
                </Badge>
              )}
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[300px] sm:w-[350px]">
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <Filter className="h-4 w-4" />
                {title}
              </SheetTitle>
            </SheetHeader>
            <div className="mt-4">{sidebarContent}</div>
          </SheetContent>
        </Sheet>
      </div>

      {/* Desktop: Sidebar */}
      <aside
        className={cn(
          'hidden lg:block shrink-0 border-r bg-card/50 p-4 transition-all duration-200',
          !isVisible && 'lg:hidden',
          className
        )}
        style={{ width: isVisible ? width : 0 }}
        aria-label="Filter-Sidebar"
      >
        {sidebarContent}
      </aside>
    </>
  );
}

// Hook to convert TanStack Table faceted values to FacetValue[]
export function useFacetValues(
  facetedUniqueValues: Map<string, number> | undefined,
  labelMap?: Record<string, string>
): FacetValue[] {
  return React.useMemo(() => {
    if (!facetedUniqueValues) return [];

    return Array.from(facetedUniqueValues.entries())
      .filter(([value]) => value !== undefined && value !== null && value !== '')
      .map(([value, count]) => ({
        value: String(value),
        label: labelMap?.[String(value)] ?? String(value),
        count,
      }))
      .sort((a, b) => b.count - a.count);
  }, [facetedUniqueValues, labelMap]);
}

// Toggle button to show/hide the sidebar
export function FacetFilterToggle({
  isVisible,
  onToggle,
  activeCount = 0,
  className,
}: {
  isVisible: boolean;
  onToggle: () => void;
  activeCount?: number;
  className?: string;
}) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onToggle}
      className={cn('h-9 hidden lg:flex', className)}
      aria-label={isVisible ? 'Filter verbergen' : 'Filter anzeigen'}
      aria-pressed={isVisible}
    >
      <SlidersHorizontal className="h-4 w-4 mr-2" aria-hidden="true" />
      {isVisible ? 'Filter verbergen' : 'Filter anzeigen'}
      {activeCount > 0 && (
        <Badge
          variant="secondary"
          className="ml-2 h-5 px-1.5 bg-primary/10 text-primary"
        >
          {activeCount}
        </Badge>
      )}
    </Button>
  );
}

FacetFilter.displayName = 'FacetFilter';

export default FacetFilter;
