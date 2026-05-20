/**
 * Graph Toolbar Component
 * Steuerleiste fuer View-Mode, Kantenfilter, Konfidenz und Tiefe
 */

import { useCallback, useState } from 'react';
import {
  Network,
  Link2,
  Clock,
  ShieldAlert,
  FolderTree,
  RotateCcw,
  Filter,
  Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { ViewMode } from '../types';

interface GraphToolbarProps {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  edgeFilter: string[];
  onEdgeFilterChange: (types: string[]) => void;
  confidenceMin: number;
  onConfidenceMinChange: (value: number) => void;
  depth: number;
  onDepthChange: (depth: number) => void;
  onResetView: () => void;
  disabled?: boolean;
}

/** Alle verfuegbaren Ansichtsmodi mit Label und Icon */
const VIEW_MODES: Array<{
  mode: ViewMode;
  label: string;
  icon: typeof Network;
  tooltip: string;
}> = [
  { mode: 'graph', label: 'Graph', icon: Network, tooltip: 'Standard-Graph-Ansicht' },
  { mode: 'financial', label: 'Finanzkette', icon: Link2, tooltip: 'Finanzketten-Ansicht' },
  { mode: 'timeline', label: 'Zeitlich', icon: Clock, tooltip: 'Zeitliche Ansicht' },
  { mode: 'risk', label: 'Risiko', icon: ShieldAlert, tooltip: 'Risiko-Ansicht' },
  { mode: 'family', label: 'Familien', icon: FolderTree, tooltip: 'Familien-Ansicht' },
];

/** Alle verfuegbaren Kantentypen mit deutschen Labels */
const EDGE_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'CONTAINS_DOCUMENT', label: 'Enthaelt Dokument' },
  { value: 'ISSUED_TO', label: 'Ausgestellt an' },
  { value: 'PAID_VIA', label: 'Bezahlt via' },
  { value: 'REFERENCES', label: 'Referenziert' },
  { value: 'LINKED_TO', label: 'Verknuepft mit' },
  { value: 'BASED_ON', label: 'Basiert auf' },
  { value: 'MATCHED_WITH', label: 'Zugeordnet zu' },
  { value: 'PARENT_OF', label: 'Uebergeordnet von' },
  { value: 'DERIVED_FROM', label: 'Abgeleitet von' },
  { value: 'SUPERSEDES', label: 'Ersetzt' },
  { value: 'CORRECTS', label: 'Korrigiert' },
  { value: 'DUNNING_FOR', label: 'Mahnung fuer' },
  { value: 'PARTIAL_PAYMENT', label: 'Teilzahlung' },
];

const DEPTH_OPTIONS = [1, 2, 3] as const;

export function GraphToolbar({
  viewMode,
  onViewModeChange,
  edgeFilter,
  onEdgeFilterChange,
  confidenceMin,
  onConfidenceMinChange,
  depth,
  onDepthChange,
  onResetView,
  disabled = false,
}: GraphToolbarProps) {
  const [edgeFilterOpen, setEdgeFilterOpen] = useState(false);

  const handleEdgeToggle = useCallback(
    (edgeType: string) => {
      if (edgeFilter.includes(edgeType)) {
        onEdgeFilterChange(edgeFilter.filter((t) => t !== edgeType));
      } else {
        onEdgeFilterChange([...edgeFilter, edgeType]);
      }
    },
    [edgeFilter, onEdgeFilterChange]
  );

  const handleSelectAll = useCallback(() => {
    onEdgeFilterChange(EDGE_TYPE_OPTIONS.map((opt) => opt.value));
  }, [onEdgeFilterChange]);

  const handleDeselectAll = useCallback(() => {
    onEdgeFilterChange([]);
  }, [onEdgeFilterChange]);

  const activeFilterCount = edgeFilter.length;
  const totalFilterCount = EDGE_TYPE_OPTIONS.length;

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-background/95 p-2 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/60">
        {/* View-Mode Buttons */}
        <div className="flex items-center gap-1">
          {VIEW_MODES.map(({ mode, label, icon: Icon, tooltip }) => (
            <Tooltip key={mode}>
              <TooltipTrigger asChild>
                <Button
                  variant={viewMode === mode ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => onViewModeChange(mode)}
                  disabled={disabled}
                  className="gap-1.5"
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{label}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>{tooltip}</p>
              </TooltipContent>
            </Tooltip>
          ))}
        </div>

        <Separator orientation="vertical" className="h-8" />

        {/* Edge-Type Filter */}
        <Popover open={edgeFilterOpen} onOpenChange={setEdgeFilterOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              className="gap-1.5"
            >
              <Filter className="h-4 w-4" />
              <span className="hidden sm:inline">Kantenfilter</span>
              {activeFilterCount < totalFilterCount && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">
                  {activeFilterCount}/{totalFilterCount}
                </Badge>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 p-0" align="start">
            <Command>
              <CommandInput placeholder="Beziehungstyp suchen..." />
              <CommandList>
                <CommandEmpty>Kein Beziehungstyp gefunden.</CommandEmpty>
                <CommandGroup>
                  {/* Alle/Keine Buttons */}
                  <div className="flex items-center gap-2 px-2 py-1.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={handleSelectAll}
                    >
                      Alle
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={handleDeselectAll}
                    >
                      Keine
                    </Button>
                  </div>
                  {EDGE_TYPE_OPTIONS.map((option) => {
                    const isChecked = edgeFilter.includes(option.value);
                    return (
                      <CommandItem
                        key={option.value}
                        onSelect={() => handleEdgeToggle(option.value)}
                        className="gap-2"
                      >
                        <Checkbox
                          checked={isChecked}
                          className="pointer-events-none"
                        />
                        <span className="flex-1 text-sm">{option.label}</span>
                        {isChecked && (
                          <Check className="h-4 w-4 text-primary" />
                        )}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>

        <Separator orientation="vertical" className="h-8" />

        {/* Confidence Slider */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground whitespace-nowrap">
            Konfidenz:
          </span>
          <Slider
            value={[confidenceMin]}
            onValueChange={([value]) => onConfidenceMinChange(value ?? 0)}
            min={0}
            max={100}
            step={5}
            disabled={disabled}
            className="w-24"
          />
          <span className="w-8 text-xs tabular-nums text-muted-foreground">
            {confidenceMin}%
          </span>
        </div>

        <Separator orientation="vertical" className="h-8" />

        {/* Depth Selector */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Tiefe:</span>
          {DEPTH_OPTIONS.map((d) => (
            <Button
              key={d}
              variant={depth === d ? 'default' : 'outline'}
              size="sm"
              onClick={() => onDepthChange(d)}
              disabled={disabled}
              className="h-7 w-7 p-0"
            >
              {d}
            </Button>
          ))}
        </div>

        <Separator orientation="vertical" className="h-8" />

        {/* Reset Button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={onResetView}
              disabled={disabled}
              className="gap-1.5"
            >
              <RotateCcw className="h-4 w-4" />
              <span className="hidden sm:inline">Zuruecksetzen</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>Ansicht zuruecksetzen</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}
