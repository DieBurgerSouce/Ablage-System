/**
 * GraphFilters - Filter fuer Entity, Zeitraum, Dokumenttyp und Ansicht
 */

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Network, Clock } from 'lucide-react';
import type { GraphFilterState, ViewMode } from '../types/document-graph-types';

interface GraphFiltersProps {
  filters: GraphFilterState;
  onFiltersChange: (filters: Partial<GraphFilterState>) => void;
}

const TIME_RANGES = [
  { value: '7d', label: 'Letzte 7 Tage' },
  { value: '30d', label: 'Letzte 30 Tage' },
  { value: '90d', label: 'Letzte 90 Tage' },
  { value: '365d', label: 'Letztes Jahr' },
  { value: 'all', label: 'Alle' },
] as const;

const DOCUMENT_TYPES = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'invoice', label: 'Rechnungen' },
  { value: 'quote', label: 'Angebote' },
  { value: 'order', label: 'Auftraege' },
  { value: 'delivery_note', label: 'Lieferscheine' },
  { value: 'credit_note', label: 'Gutschriften' },
  { value: 'reminder', label: 'Mahnungen' },
] as const;

export function GraphFilters({ filters, onFiltersChange }: GraphFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Zeitraum */}
      <Select
        value={filters.timeRange}
        onValueChange={(value) =>
          onFiltersChange({ timeRange: value as GraphFilterState['timeRange'] })
        }
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="Zeitraum" />
        </SelectTrigger>
        <SelectContent>
          {TIME_RANGES.map((range) => (
            <SelectItem key={range.value} value={range.value}>
              {range.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Dokumenttyp */}
      <Select
        value={filters.documentTypes[0] || 'all'}
        onValueChange={(value) =>
          onFiltersChange({
            documentTypes: value === 'all' ? [] : [value],
          })
        }
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="Dokumenttyp" />
        </SelectTrigger>
        <SelectContent>
          {DOCUMENT_TYPES.map((type) => (
            <SelectItem key={type.value} value={type.value}>
              {type.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Ansicht Toggle */}
      <div className="flex items-center gap-1 ml-auto">
        <Button
          variant={filters.viewMode === 'graph' ? 'default' : 'outline'}
          size="sm"
          onClick={() => onFiltersChange({ viewMode: 'graph' as ViewMode })}
          className="gap-1.5"
        >
          <Network className="h-4 w-4" />
          Graph
        </Button>
        <Button
          variant={filters.viewMode === 'timeline' ? 'default' : 'outline'}
          size="sm"
          onClick={() => onFiltersChange({ viewMode: 'timeline' as ViewMode })}
          className="gap-1.5"
        >
          <Clock className="h-4 w-4" />
          Timeline
        </Button>
      </div>
    </div>
  );
}
