/**
 * ActivityFilterBar Component
 *
 * Filterleiste fuer die Activity Timeline.
 */

import { useState } from 'react';
import { Search, Filter, X, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Calendar as CalendarComponent } from '@/components/ui/calendar';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ActivitySource } from '../types';
import { ACTIVITY_SOURCE_LABELS, ACTIVITY_TYPE_LABELS } from '../types';

interface ActivityFilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  source: ActivitySource | 'all';
  onSourceChange: (value: ActivitySource | 'all') => void;
  activityType: string;
  onActivityTypeChange: (value: string) => void;
  dateFrom?: Date;
  onDateFromChange: (value: Date | undefined) => void;
  dateUntil?: Date;
  onDateUntilChange: (value: Date | undefined) => void;
  onClearFilters: () => void;
}

const ACTIVITY_TYPE_OPTIONS = Object.entries(ACTIVITY_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

export function ActivityFilterBar({
  search,
  onSearchChange,
  source,
  onSourceChange,
  activityType,
  onActivityTypeChange,
  dateFrom,
  onDateFromChange,
  dateUntil,
  onDateUntilChange,
  onClearFilters,
}: ActivityFilterBarProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  const hasFilters =
    search ||
    source !== 'all' ||
    activityType !== 'all' ||
    dateFrom ||
    dateUntil;

  const activeFilterCount = [
    search,
    source !== 'all' ? source : null,
    activityType !== 'all' ? activityType : null,
    dateFrom,
    dateUntil,
  ].filter(Boolean).length;

  return (
    <div className="space-y-4">
      {/* Main Filter Row */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Aktivitaeten durchsuchen..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-9"
          />
          {search && (
            <Button
              variant="ghost"
              size="sm"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
              onClick={() => onSearchChange('')}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>

        {/* Source Filter */}
        <Select value={source} onValueChange={(v) => onSourceChange(v as ActivitySource | 'all')}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Quelle" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Quellen</SelectItem>
            {Object.entries(ACTIVITY_SOURCE_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Advanced Filter Toggle */}
        <Button
          variant={showAdvanced ? 'secondary' : 'outline'}
          size="icon"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="relative"
        >
          <Filter className="h-4 w-4" />
          {activeFilterCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-2 -right-2 h-5 w-5 p-0 flex items-center justify-center text-xs"
            >
              {activeFilterCount}
            </Badge>
          )}
        </Button>

        {/* Clear Filters */}
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={onClearFilters}>
            <X className="h-4 w-4 mr-1" />
            Zuruecksetzen
          </Button>
        )}
      </div>

      {/* Advanced Filters */}
      {showAdvanced && (
        <div className="flex flex-wrap gap-3 p-4 bg-muted/50 rounded-lg">
          {/* Activity Type */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Aktivitaetstyp</label>
            <Select value={activityType} onValueChange={onActivityTypeChange}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Alle Typen" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Typen</SelectItem>
                {ACTIVITY_TYPE_OPTIONS.map(({ value, label }) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Date From */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Von</label>
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={cn(
                    'w-[160px] justify-start text-left font-normal',
                    !dateFrom && 'text-muted-foreground'
                  )}
                >
                  <Calendar className="mr-2 h-4 w-4" />
                  {dateFrom ? (
                    dateFrom.toLocaleDateString('de-DE')
                  ) : (
                    <span>Startdatum</span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <CalendarComponent
                  mode="single"
                  selected={dateFrom}
                  onSelect={onDateFromChange}
                  initialFocus
                />
                {dateFrom && (
                  <div className="p-2 border-t">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full"
                      onClick={() => onDateFromChange(undefined)}
                    >
                      Entfernen
                    </Button>
                  </div>
                )}
              </PopoverContent>
            </Popover>
          </div>

          {/* Date Until */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Bis</label>
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={cn(
                    'w-[160px] justify-start text-left font-normal',
                    !dateUntil && 'text-muted-foreground'
                  )}
                >
                  <Calendar className="mr-2 h-4 w-4" />
                  {dateUntil ? (
                    dateUntil.toLocaleDateString('de-DE')
                  ) : (
                    <span>Enddatum</span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <CalendarComponent
                  mode="single"
                  selected={dateUntil}
                  onSelect={onDateUntilChange}
                  initialFocus
                />
                {dateUntil && (
                  <div className="p-2 border-t">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full"
                      onClick={() => onDateUntilChange(undefined)}
                    >
                      Entfernen
                    </Button>
                  </div>
                )}
              </PopoverContent>
            </Popover>
          </div>
        </div>
      )}

      {/* Active Filter Tags */}
      {hasFilters && (
        <div className="flex flex-wrap gap-2">
          {search && (
            <Badge variant="secondary" className="gap-1">
              Suche: {search}
              <X
                className="h-3 w-3 cursor-pointer"
                onClick={() => onSearchChange('')}
              />
            </Badge>
          )}
          {source !== 'all' && (
            <Badge variant="secondary" className="gap-1">
              {ACTIVITY_SOURCE_LABELS[source]}
              <X
                className="h-3 w-3 cursor-pointer"
                onClick={() => onSourceChange('all')}
              />
            </Badge>
          )}
          {activityType !== 'all' && (
            <Badge variant="secondary" className="gap-1">
              {ACTIVITY_TYPE_LABELS[activityType] || activityType}
              <X
                className="h-3 w-3 cursor-pointer"
                onClick={() => onActivityTypeChange('all')}
              />
            </Badge>
          )}
          {dateFrom && (
            <Badge variant="secondary" className="gap-1">
              Ab: {dateFrom.toLocaleDateString('de-DE')}
              <X
                className="h-3 w-3 cursor-pointer"
                onClick={() => onDateFromChange(undefined)}
              />
            </Badge>
          )}
          {dateUntil && (
            <Badge variant="secondary" className="gap-1">
              Bis: {dateUntil.toLocaleDateString('de-DE')}
              <X
                className="h-3 w-3 cursor-pointer"
                onClick={() => onDateUntilChange(undefined)}
              />
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}
