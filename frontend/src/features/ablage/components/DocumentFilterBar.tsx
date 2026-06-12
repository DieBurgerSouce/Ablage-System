/**
 * DocumentFilterBar - Erweiterte Filter-Leiste für Kategorie-Dokumente
 *
 * Features:
 * - Debounced Search Input
 * - Datum-Range (Von/Bis)
 * - Betrags-Range (Min/Max)
 * - Status Multi-Select
 * - Zahlungsstatus Multi-Select (nur für Rechnungen)
 * - Filter-Reset
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Search,
  Calendar,
  Euro,
  Filter,
  CheckCircle2,
  CreditCard,
  X,
  RotateCcw,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import type {
  CategoryDocumentFilter,
  DocumentProcessingStatus,
  PaymentStatus,
} from '../types';
import {
  PROCESSING_STATUS_CONFIG,
  PAYMENT_STATUS_CONFIG,
  CATEGORIES_WITH_PAYMENT_STATUS,
} from '../types';

// ==================== Types ====================

interface DocumentFilterBarProps {
  category: string;
  filter: Partial<CategoryDocumentFilter>;
  onChange: (filter: Partial<CategoryDocumentFilter>) => void;
  totalCount?: number;
  className?: string;
}

type FilterKey = keyof CategoryDocumentFilter;

// ==================== Debounce Hook ====================

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

// ==================== Main Component ====================

export function DocumentFilterBar({
  category,
  filter,
  onChange,
  totalCount,
  className,
}: DocumentFilterBarProps) {
  const [searchText, setSearchText] = useState(filter.search || '');
  const debouncedSearch = useDebounce(searchText, 300);

  // Update filter when debounced search changes
  useEffect(() => {
    if (debouncedSearch !== filter.search) {
      onChange({ ...filter, search: debouncedSearch || undefined, page: 1 });
    }
  }, [debouncedSearch]); // Only run when debouncedSearch changes

  // Show payment status filter only for invoice-related categories
  const showPaymentStatus = CATEGORIES_WITH_PAYMENT_STATUS.includes(category);

  // Count active filters
  const activeFilterCount = [
    filter.dateFrom || filter.dateTo,
    filter.amountMin !== undefined || filter.amountMax !== undefined,
    filter.processingStatus?.length,
    showPaymentStatus && filter.paymentStatus?.length,
  ].filter(Boolean).length;

  // Reset all filters
  const handleReset = useCallback(() => {
    setSearchText('');
    onChange({
      businessEntityId: filter.businessEntityId,
      folderId: filter.folderId,
      category: filter.category,
      entityType: filter.entityType,
      sortBy: filter.sortBy,
      sortOrder: filter.sortOrder,
      page: 1,
      pageSize: filter.pageSize,
    });
  }, [filter, onChange]);

  // Update single filter value
  const updateFilter = useCallback(
    (key: FilterKey, value: unknown) => {
      onChange({ ...filter, [key]: value, page: 1 });
    },
    [filter, onChange]
  );

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3',
        className
      )}
      role="search"
      aria-label="Dokumente filtern"
    >
      {/* Search Input */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <Input
          placeholder="Dateiname, Dokumentnummer..."
          className="pl-9 h-9"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          aria-label="Dokumente durchsuchen"
          role="searchbox"
        />
        {searchText && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
            onClick={() => setSearchText('')}
            aria-label="Suche leeren"
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </Button>
        )}
      </div>

      <div className="flex items-center gap-2">
        {/* Date Range Filter */}
        <DateRangePopover
          dateFrom={filter.dateFrom}
          dateTo={filter.dateTo}
          onChange={(from, to) => {
            onChange({
              ...filter,
              dateFrom: from,
              dateTo: to,
              page: 1,
            });
          }}
        />

        {/* Amount Range Filter */}
        <AmountRangePopover
          amountMin={filter.amountMin}
          amountMax={filter.amountMax}
          onChange={(min, max) => {
            onChange({
              ...filter,
              amountMin: min,
              amountMax: max,
              page: 1,
            });
          }}
        />

        {/* Processing Status Filter */}
        <StatusMultiSelect
          icon={CheckCircle2}
          label="Status"
          options={Object.entries(PROCESSING_STATUS_CONFIG).map(([key, config]) => ({
            id: key as DocumentProcessingStatus,
            label: config.label,
          }))}
          selected={filter.processingStatus || []}
          onChange={(values) => updateFilter('processingStatus', values.length ? values : undefined)}
        />

        {/* Payment Status Filter (only for invoices) */}
        {showPaymentStatus && (
          <StatusMultiSelect
            icon={CreditCard}
            label="Zahlung"
            options={Object.entries(PAYMENT_STATUS_CONFIG).map(([key, config]) => ({
              id: key as PaymentStatus,
              label: config.label,
            }))}
            selected={filter.paymentStatus || []}
            onChange={(values) => updateFilter('paymentStatus', values.length ? values : undefined)}
          />
        )}

        {/* Active Filter Badge + Reset */}
        {activeFilterCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-9 text-muted-foreground hover:text-destructive"
            onClick={handleReset}
            aria-label={`Alle ${activeFilterCount} Filter zurücksetzen`}
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
            Zurücksetzen
            <Badge variant="secondary" className="ml-2 h-5 px-1.5" aria-hidden="true">
              {activeFilterCount}
            </Badge>
          </Button>
        )}
      </div>

      {/* Document Count */}
      {totalCount !== undefined && (
        <div
          className="ml-auto flex items-center gap-2 text-sm text-muted-foreground"
          aria-live="polite"
          aria-atomic="true"
        >
          <Filter className="h-4 w-4" aria-hidden="true" />
          <span>{totalCount.toLocaleString('de-DE')} Dokumente</span>
        </div>
      )}
    </div>
  );
}

// ==================== Date Range Popover ====================

interface DateRangePopoverProps {
  dateFrom?: string;
  dateTo?: string;
  onChange: (from?: string, to?: string) => void;
}

function DateRangePopover({ dateFrom, dateTo, onChange }: DateRangePopoverProps) {
  const hasValue = dateFrom || dateTo;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'h-9 border-dashed',
            hasValue && 'border-primary bg-primary/5 text-primary border-solid'
          )}
          aria-label={hasValue ? `Zeitraum: ${dateFrom || 'offen'} bis ${dateTo || 'offen'}` : 'Zeitraum filtern'}
          aria-expanded={undefined}
        >
          <Calendar className="h-4 w-4 mr-2" aria-hidden="true" />
          Zeitraum
          {hasValue && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5 bg-primary/10 text-primary" aria-hidden="true">
              1
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" align="start" aria-label="Zeitraum auswählen">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="date-from">Von</Label>
            <Input
              id="date-from"
              type="date"
              value={dateFrom || ''}
              onChange={(e) => onChange(e.target.value || undefined, dateTo)}
              aria-describedby="date-range-hint"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="date-to">Bis</Label>
            <Input
              id="date-to"
              type="date"
              value={dateTo || ''}
              onChange={(e) => onChange(dateFrom, e.target.value || undefined)}
            />
          </div>
          <p id="date-range-hint" className="sr-only">
            Wählen Sie einen Zeitraum um Dokumente nach Datum zu filtern
          </p>
          {hasValue && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => onChange(undefined, undefined)}
              aria-label="Datumsfilter zurücksetzen"
            >
              Zurücksetzen
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ==================== Amount Range Popover ====================

interface AmountRangePopoverProps {
  amountMin?: number;
  amountMax?: number;
  onChange: (min?: number, max?: number) => void;
}

function AmountRangePopover({ amountMin, amountMax, onChange }: AmountRangePopoverProps) {
  const [localMin, setLocalMin] = useState(amountMin?.toString() || '');
  const [localMax, setLocalMax] = useState(amountMax?.toString() || '');
  const hasValue = amountMin !== undefined || amountMax !== undefined;

  // Apply changes when popover closes
  const handleApply = () => {
    const min = localMin ? parseFloat(localMin) : undefined;
    const max = localMax ? parseFloat(localMax) : undefined;
    onChange(min, max);
  };

  return (
    <Popover onOpenChange={(open) => !open && handleApply()}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'h-9 border-dashed',
            hasValue && 'border-primary bg-primary/5 text-primary border-solid'
          )}
        >
          <Euro className="h-4 w-4 mr-2" />
          Betrag
          {hasValue && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5 bg-primary/10 text-primary">
              1
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" align="start">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="amount-min">Mindestbetrag</Label>
            <div className="relative">
              <Input
                id="amount-min"
                type="number"
                step="0.01"
                min="0"
                placeholder="0,00"
                className="pr-8"
                value={localMin}
                onChange={(e) => setLocalMin(e.target.value)}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
                EUR
              </span>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="amount-max">Höchstbetrag</Label>
            <div className="relative">
              <Input
                id="amount-max"
                type="number"
                step="0.01"
                min="0"
                placeholder="0,00"
                className="pr-8"
                value={localMax}
                onChange={(e) => setLocalMax(e.target.value)}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
                EUR
              </span>
            </div>
          </div>
          {hasValue && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => {
                setLocalMin('');
                setLocalMax('');
                onChange(undefined, undefined);
              }}
            >
              Zurücksetzen
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ==================== Status Multi-Select ====================

interface StatusOption<T> {
  id: T;
  label: string;
}

interface StatusMultiSelectProps<T extends string> {
  icon: React.ElementType;
  label: string;
  options: StatusOption<T>[];
  selected: T[];
  onChange: (values: T[]) => void;
}

function StatusMultiSelect<T extends string>({
  icon: Icon,
  label,
  options,
  selected,
  onChange,
}: StatusMultiSelectProps<T>) {
  const hasValue = selected.length > 0;
  const listId = `status-list-${label.toLowerCase().replace(/\s/g, '-')}`;

  const toggleOption = (id: T) => {
    if (selected.includes(id)) {
      onChange(selected.filter((v) => v !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'h-9 border-dashed',
            hasValue && 'border-primary bg-primary/5 text-primary border-solid'
          )}
          aria-label={hasValue ? `${label}: ${selected.length} ausgewählt` : `${label} filtern`}
        >
          <Icon className="h-4 w-4 mr-2" aria-hidden="true" />
          {label}
          {hasValue && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5 bg-primary/10 text-primary" aria-hidden="true">
              {selected.length}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-2" align="start" aria-label={`${label} auswählen`}>
        <div className="space-y-1" role="group" aria-labelledby={listId}>
          <span id={listId} className="sr-only">{label} Optionen</span>
          {options.map((option) => {
            const checked = selected.includes(option.id);
            const checkboxId = `${listId}-${option.id}`;
            return (
              <div
                key={option.id}
                className="flex items-center gap-2 px-2 py-1.5 hover:bg-muted rounded-sm cursor-pointer"
                onClick={() => toggleOption(option.id)}
                role="checkbox"
                aria-checked={checked}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleOption(option.id);
                  }
                }}
              >
                <Checkbox
                  id={checkboxId}
                  checked={checked}
                  aria-labelledby={`${checkboxId}-label`}
                  tabIndex={-1}
                />
                <span id={`${checkboxId}-label`} className="text-sm">{option.label}</span>
              </div>
            );
          })}
        </div>
        {hasValue && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2"
            onClick={() => onChange([])}
            aria-label={`Alle ${label} Filter abwählen`}
          >
            Alle abwählen
          </Button>
        )}
      </PopoverContent>
    </Popover>
  );
}

export default DocumentFilterBar;
