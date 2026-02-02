/**
 * LineageControls Component
 *
 * Filter- und Zoom-Steuerung fuer das Lineage-Flowchart.
 * Ermoeglicht Filterung nach Event-Typen und Zeitraum.
 */

import { memo, useMemo, useCallback, useState } from 'react';
import { useReactFlow, type FitViewOptions } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Calendar } from '@/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  ToggleGroup,
  ToggleGroupItem,
} from '@/components/ui/toggle-group';
import { Separator } from '@/components/ui/separator';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  LayoutGrid,
  LayoutList,
  Calendar as CalendarIcon,
  Filter,
  RotateCcw,
  Download,
  X,
} from 'lucide-react';
import { format, subDays, startOfDay, endOfDay, isWithinInterval } from 'date-fns';
import { de } from 'date-fns/locale';
import type { LineageEventType, EventTypeLabels } from '@/lib/api/services/lineage';

// =============================================================================
// Types
// =============================================================================

export type LayoutDirection = 'horizontal' | 'vertical';

export interface DateRange {
  from: Date | undefined;
  to: Date | undefined;
}

export interface LineageFilters {
  eventTypes: LineageEventType[];
  dateRange: DateRange;
}

export interface LineageControlsProps {
  eventTypeLabels?: EventTypeLabels;
  filters: LineageFilters;
  onFiltersChange: (filters: LineageFilters) => void;
  layout: LayoutDirection;
  onLayoutChange: (layout: LayoutDirection) => void;
  onExport?: () => void;
  className?: string;
}

// =============================================================================
// Event Type Groups (fuer bessere Organisation)
// =============================================================================

const EVENT_TYPE_GROUPS = {
  import: {
    label: 'Import',
    types: ['import'] as LineageEventType[],
  },
  ocr: {
    label: 'OCR-Verarbeitung',
    types: ['ocr_start', 'ocr_complete', 'ocr_failed'] as LineageEventType[],
  },
  classification: {
    label: 'Klassifizierung',
    types: ['classification', 'extraction'] as LineageEventType[],
  },
  entityLinking: {
    label: 'Partner-Verknuepfung',
    types: ['entity_link', 'entity_unlink'] as LineageEventType[],
  },
  modification: {
    label: 'Bearbeitungen',
    types: ['modification', 'metadata_update', 'tag_change'] as LineageEventType[],
  },
  workflow: {
    label: 'Workflow',
    types: ['approval', 'rejection', 'escalation'] as LineageEventType[],
  },
  lifecycle: {
    label: 'Lebenszyklus',
    types: ['export', 'archive', 'restore', 'soft_delete', 'hard_delete'] as LineageEventType[],
  },
};

// =============================================================================
// Date Presets
// =============================================================================

const DATE_PRESETS = [
  { label: 'Alle', value: 'all', days: null },
  { label: 'Heute', value: 'today', days: 0 },
  { label: 'Letzte 7 Tage', value: '7d', days: 7 },
  { label: 'Letzte 30 Tage', value: '30d', days: 30 },
  { label: 'Letzte 90 Tage', value: '90d', days: 90 },
];

// =============================================================================
// Fit View Options
// =============================================================================

const FIT_VIEW_OPTIONS: FitViewOptions = {
  padding: 0.2,
  duration: 300,
};

// =============================================================================
// Component
// =============================================================================

export const LineageControls = memo(function LineageControls({
  eventTypeLabels,
  filters,
  onFiltersChange,
  layout,
  onLayoutChange,
  onExport,
  className,
}: LineageControlsProps) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  // Aktive Filter zaehlen
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.eventTypes.length > 0) count++;
    if (filters.dateRange.from || filters.dateRange.to) count++;
    return count;
  }, [filters]);

  // Event-Typ Toggle Handler
  const handleEventTypeToggle = useCallback(
    (eventType: LineageEventType) => {
      const newTypes = filters.eventTypes.includes(eventType)
        ? filters.eventTypes.filter((t) => t !== eventType)
        : [...filters.eventTypes, eventType];

      onFiltersChange({
        ...filters,
        eventTypes: newTypes,
      });
    },
    [filters, onFiltersChange]
  );

  // Gruppen-Toggle Handler
  const handleGroupToggle = useCallback(
    (groupTypes: LineageEventType[]) => {
      const allSelected = groupTypes.every((t) =>
        filters.eventTypes.includes(t)
      );

      let newTypes: LineageEventType[];
      if (allSelected) {
        newTypes = filters.eventTypes.filter((t) => !groupTypes.includes(t));
      } else {
        const toAdd = groupTypes.filter((t) => !filters.eventTypes.includes(t));
        newTypes = [...filters.eventTypes, ...toAdd];
      }

      onFiltersChange({
        ...filters,
        eventTypes: newTypes,
      });
    },
    [filters, onFiltersChange]
  );

  // Date Preset Handler
  const handleDatePreset = useCallback(
    (preset: (typeof DATE_PRESETS)[number]) => {
      if (preset.days === null) {
        onFiltersChange({
          ...filters,
          dateRange: { from: undefined, to: undefined },
        });
      } else if (preset.days === 0) {
        const today = new Date();
        onFiltersChange({
          ...filters,
          dateRange: { from: startOfDay(today), to: endOfDay(today) },
        });
      } else {
        const now = new Date();
        onFiltersChange({
          ...filters,
          dateRange: {
            from: startOfDay(subDays(now, preset.days)),
            to: endOfDay(now),
          },
        });
      }
    },
    [filters, onFiltersChange]
  );

  // Filter zuruecksetzen
  const handleResetFilters = useCallback(() => {
    onFiltersChange({
      eventTypes: [],
      dateRange: { from: undefined, to: undefined },
    });
  }, [onFiltersChange]);

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-2 p-2 bg-background/95 backdrop-blur-sm',
        'border-b border-border',
        className
      )}
    >
      {/* Zoom Controls */}
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => zoomOut()}
          title="Verkleinern"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => zoomIn()}
          title="Vergroessern"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => fitView(FIT_VIEW_OPTIONS)}
          title="An Fenster anpassen"
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
      </div>

      <Separator orientation="vertical" className="h-6" />

      {/* Layout Toggle */}
      <ToggleGroup
        type="single"
        value={layout}
        onValueChange={(value) => {
          if (value) onLayoutChange(value as LayoutDirection);
        }}
        className="gap-1"
      >
        <ToggleGroupItem
          value="horizontal"
          size="sm"
          className="h-8 w-8 p-0"
          title="Horizontales Layout"
        >
          <LayoutList className="h-4 w-4" />
        </ToggleGroupItem>
        <ToggleGroupItem
          value="vertical"
          size="sm"
          className="h-8 w-8 p-0"
          title="Vertikales Layout"
        >
          <LayoutGrid className="h-4 w-4 rotate-90" />
        </ToggleGroupItem>
      </ToggleGroup>

      <Separator orientation="vertical" className="h-6" />

      {/* Filter Popover */}
      <Popover open={isFilterOpen} onOpenChange={setIsFilterOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 gap-2">
            <Filter className="h-4 w-4" />
            <span>Filter</span>
            {activeFilterCount > 0 && (
              <Badge variant="secondary" className="h-5 px-1.5">
                {activeFilterCount}
              </Badge>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 p-4" align="start">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="font-medium">Filter</h4>
              {activeFilterCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={handleResetFilters}
                >
                  <RotateCcw className="h-3 w-3 mr-1" />
                  Zuruecksetzen
                </Button>
              )}
            </div>

            <Separator />

            {/* Event Type Filter */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Event-Typen</label>
              <div className="space-y-1.5">
                {Object.entries(EVENT_TYPE_GROUPS).map(([key, group]) => {
                  const selectedCount = group.types.filter((t) =>
                    filters.eventTypes.includes(t)
                  ).length;
                  const allSelected = selectedCount === group.types.length;

                  return (
                    <div key={key} className="space-y-1">
                      <button
                        onClick={() => handleGroupToggle(group.types)}
                        className={cn(
                          'flex items-center justify-between w-full px-2 py-1 rounded text-sm',
                          'hover:bg-accent transition-colors',
                          allSelected && 'bg-accent'
                        )}
                      >
                        <span>{group.label}</span>
                        {selectedCount > 0 && (
                          <Badge variant="secondary" className="text-xs">
                            {selectedCount}/{group.types.length}
                          </Badge>
                        )}
                      </button>
                      <div className="flex flex-wrap gap-1 pl-2">
                        {group.types.map((type) => {
                          const label =
                            eventTypeLabels?.[type] || type.replace(/_/g, ' ');
                          const isSelected = filters.eventTypes.includes(type);

                          return (
                            <Badge
                              key={type}
                              variant={isSelected ? 'default' : 'outline'}
                              className={cn(
                                'cursor-pointer text-xs',
                                isSelected && 'bg-primary'
                              )}
                              onClick={() => handleEventTypeToggle(type)}
                            >
                              {label}
                              {isSelected && (
                                <X className="h-3 w-3 ml-1" />
                              )}
                            </Badge>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <Separator />

            {/* Date Range Filter */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Zeitraum</label>
              <Select
                onValueChange={(value) => {
                  const preset = DATE_PRESETS.find((p) => p.value === value);
                  if (preset) handleDatePreset(preset);
                }}
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="Zeitraum waehlen" />
                </SelectTrigger>
                <SelectContent>
                  {DATE_PRESETS.map((preset) => (
                    <SelectItem key={preset.value} value={preset.value}>
                      {preset.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Custom Date Range */}
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full h-8 justify-start text-left font-normal"
                  >
                    <CalendarIcon className="h-4 w-4 mr-2" />
                    {filters.dateRange.from ? (
                      filters.dateRange.to ? (
                        <>
                          {format(filters.dateRange.from, 'dd.MM.yy', { locale: de })} -{' '}
                          {format(filters.dateRange.to, 'dd.MM.yy', { locale: de })}
                        </>
                      ) : (
                        format(filters.dateRange.from, 'dd.MM.yyyy', { locale: de })
                      )
                    ) : (
                      'Benutzerdefiniert...'
                    )}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="range"
                    selected={{
                      from: filters.dateRange.from,
                      to: filters.dateRange.to,
                    }}
                    onSelect={(range) => {
                      onFiltersChange({
                        ...filters,
                        dateRange: {
                          from: range?.from,
                          to: range?.to,
                        },
                      });
                    }}
                    locale={de}
                    numberOfMonths={2}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </PopoverContent>
      </Popover>

      {/* Active Filters Badges */}
      {filters.eventTypes.length > 0 && (
        <div className="flex items-center gap-1">
          <Badge variant="secondary" className="text-xs">
            {filters.eventTypes.length} Event-Typ(en)
          </Badge>
        </div>
      )}

      {(filters.dateRange.from || filters.dateRange.to) && (
        <Badge variant="secondary" className="text-xs">
          {filters.dateRange.from && filters.dateRange.to
            ? `${format(filters.dateRange.from, 'dd.MM', { locale: de })} - ${format(filters.dateRange.to, 'dd.MM', { locale: de })}`
            : 'Zeitraum gesetzt'}
        </Badge>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Export Button */}
      {onExport && (
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-2"
          onClick={onExport}
        >
          <Download className="h-4 w-4" />
          <span className="hidden sm:inline">Export</span>
        </Button>
      )}
    </div>
  );
});
