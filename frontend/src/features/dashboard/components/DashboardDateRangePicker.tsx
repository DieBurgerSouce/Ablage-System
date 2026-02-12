/**
 * Dashboard Date Range Picker
 *
 * Globaler Datumsfilter für alle Dashboard-Widgets.
 * Bietet vordefinierte Zeiträume und einen optionalen
 * Vergleichszeitraum (Vorperiode / Vorjahr).
 *
 * Phase C: Business KPIs
 */

import { useState } from 'react';
import { CalendarDays, ChevronDown, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useDateRange, PREDEFINED_RANGES } from '../hooks/useDateRange';

const COMPARE_OPTIONS = [
  { value: 'previous_period', label: 'Vorperiode' },
  { value: 'yoy', label: 'Vorjahr' },
] as const;

export function DashboardDateRangePicker() {
  const { dateRange, setDateRange, comparePeriod, setComparePeriod } = useDateRange();
  const [open, setOpen] = useState(false);

  const handleSelectRange = (
    label: string,
    getValue: () => { from: Date; to: Date },
  ) => {
    const { from, to } = getValue();
    setDateRange({ from, to, label });
    setOpen(false);
  };

  const handleClearRange = () => {
    setDateRange({ from: undefined, to: undefined, label: 'Alle Zeiträume' });
    setComparePeriod(undefined);
    setOpen(false);
  };

  const handleToggleCompare = (value: string) => {
    if (comparePeriod === value) {
      setComparePeriod(undefined);
    } else {
      setComparePeriod(value);
    }
  };

  const hasActiveRange = dateRange.from !== undefined;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'gap-2 text-sm',
            hasActiveRange && 'border-primary text-primary',
          )}
        >
          <CalendarDays className="h-4 w-4" />
          <span>{dateRange.label}</span>
          {comparePeriod && (
            <Badge variant="secondary" className="text-xs h-5 px-1.5">
              Vgl.
            </Badge>
          )}
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3" align="end">
        <div className="space-y-3">
          {/* Vordefinierte Zeiträume */}
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-2">
              Zeitraum
            </p>
            <div className="grid gap-1">
              {PREDEFINED_RANGES.map((range) => (
                <Button
                  key={range.label}
                  variant={dateRange.label === range.label ? 'default' : 'ghost'}
                  size="sm"
                  className="justify-start text-sm h-8"
                  onClick={() => handleSelectRange(range.label, range.getValue)}
                >
                  {range.label}
                </Button>
              ))}
            </div>
          </div>

          {/* Vergleichszeitraum */}
          {hasActiveRange && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">
                Vergleichen mit
              </p>
              <div className="grid grid-cols-2 gap-1">
                {COMPARE_OPTIONS.map((option) => (
                  <Button
                    key={option.value}
                    variant={comparePeriod === option.value ? 'default' : 'outline'}
                    size="sm"
                    className="text-xs h-7"
                    onClick={() => handleToggleCompare(option.value)}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Zurücksetzen */}
          {hasActiveRange && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs text-muted-foreground gap-1"
              onClick={handleClearRange}
            >
              <X className="h-3 w-3" />
              Zurücksetzen
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
