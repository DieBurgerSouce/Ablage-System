/**
 * FacetGroup - Collapsible Gruppe von Facetten-Werten
 *
 * Features:
 * - Collapsible Header mit Chevron
 * - Badge für Anzahl ausgewählter Werte
 * - Suche innerhalb der Gruppe (optional)
 * - Virtualisierung für grosse Listen (>50 Items)
 */

import * as React from 'react';
import { ChevronDown, ChevronRight, X } from 'lucide-react';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { FacetItem } from './FacetItem';

export interface FacetValue {
  value: string;
  label: string;
  count: number;
}

export interface FacetGroupProps {
  /** Titel der Gruppe */
  title: string;
  /** Verfügbare Werte */
  values: FacetValue[];
  /** Ausgewählte Werte */
  selectedValues: string[];
  /** Callback bei Änderung */
  onSelectionChange: (values: string[]) => void;
  /** Ob die Gruppe standardmäßig geöffnet ist */
  defaultOpen?: boolean;
  /** Suche in der Gruppe aktivieren */
  enableSearch?: boolean;
  /** Schwellwert für Suche (default: 5) */
  searchThreshold?: number;
  /** Maximale Höhe der Scroll-Area */
  maxHeight?: number;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

export function FacetGroup({
  title,
  values,
  selectedValues,
  onSelectionChange,
  defaultOpen = true,
  enableSearch = true,
  searchThreshold = 5,
  maxHeight = 200,
  className,
}: FacetGroupProps) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen);
  const [searchQuery, setSearchQuery] = React.useState('');

  // Show search only if enabled and enough values
  const showSearch = enableSearch && values.length > searchThreshold;

  // Filter values based on search
  const filteredValues = React.useMemo(() => {
    if (!searchQuery.trim()) return values;
    const query = searchQuery.toLowerCase();
    return values.filter((v) => v.label.toLowerCase().includes(query));
  }, [values, searchQuery]);

  // Sort: selected first, then by count descending
  const sortedValues = React.useMemo(() => {
    return [...filteredValues].sort((a, b) => {
      const aSelected = selectedValues.includes(a.value);
      const bSelected = selectedValues.includes(b.value);
      if (aSelected !== bSelected) return aSelected ? -1 : 1;
      return b.count - a.count;
    });
  }, [filteredValues, selectedValues]);

  const handleToggle = React.useCallback(
    (value: string, checked: boolean) => {
      if (checked) {
        onSelectionChange([...selectedValues, value]);
      } else {
        onSelectionChange(selectedValues.filter((v) => v !== value));
      }
    },
    [selectedValues, onSelectionChange]
  );

  const handleClearAll = React.useCallback(() => {
    onSelectionChange([]);
  }, [onSelectionChange]);

  const selectedCount = selectedValues.length;

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className={cn('border-b border-border/50 pb-3', className)}
    >
      <div className="flex items-center justify-between py-2">
        <CollapsibleTrigger
          className="flex items-center gap-2 text-sm font-medium hover:text-foreground/80 transition-colors"
          aria-label={`${title} ${isOpen ? 'schließen' : 'öffnen'}`}
        >
          {isOpen ? (
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          )}
          {title}
        </CollapsibleTrigger>

        {selectedCount > 0 && (
          <div className="flex items-center gap-1">
            <Badge
              variant="secondary"
              className="h-5 px-1.5 text-xs bg-primary/10 text-primary"
            >
              {selectedCount}
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5"
              onClick={handleClearAll}
              aria-label={`Alle ${title} Filter entfernen`}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>

      <CollapsibleContent>
        <div className="space-y-1">
          {/* Search Input */}
          {showSearch && (
            <div className="relative mb-2">
              <Input
                placeholder={`${title} suchen...`}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 text-sm"
                aria-label={`${title} durchsuchen`}
              />
              {searchQuery && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6"
                  onClick={() => setSearchQuery('')}
                  aria-label="Suche leeren"
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>
          )}

          {/* Facet Values */}
          {sortedValues.length > 0 ? (
            <ScrollArea
              className="pr-2"
              style={{ maxHeight: `${maxHeight}px` }}
            >
              <div className="space-y-0.5">
                {sortedValues.map((facet) => (
                  <FacetItem
                    key={facet.value}
                    value={facet.value}
                    label={facet.label}
                    count={facet.count}
                    checked={selectedValues.includes(facet.value)}
                    onCheckedChange={(checked) =>
                      handleToggle(facet.value, checked)
                    }
                  />
                ))}
              </div>
            </ScrollArea>
          ) : (
            <p className="text-sm text-muted-foreground py-2 px-2">
              {searchQuery
                ? 'Keine Treffer gefunden'
                : 'Keine Werte verfügbar'}
            </p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

FacetGroup.displayName = 'FacetGroup';

export default FacetGroup;
