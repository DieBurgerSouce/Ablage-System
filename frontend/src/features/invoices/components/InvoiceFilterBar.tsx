/**
 * InvoiceFilterBar - Filter-Komponente für Rechnungsliste
 *
 * Filter:
 * - Status: Offen, Bezahlt, Überfällig, In Mahnung
 * - Mahnstufe: 0-4
 * - Nur überfällige
 */

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { X } from 'lucide-react';
import type { InvoiceStatus, InvoiceFilter } from '../types/invoice-types';
import { UI_LABELS, STATUS_STYLES } from '../types/invoice-types';

interface InvoiceFilterBarProps {
  filter: Partial<InvoiceFilter>;
  onFilterChange: (filter: Partial<InvoiceFilter>) => void;
}

const STATUS_OPTIONS: Array<{ value: InvoiceStatus | 'all'; label: string }> = [
  { value: 'all', label: 'Alle Status' },
  { value: 'open', label: STATUS_STYLES.open.label },
  { value: 'sent', label: STATUS_STYLES.sent.label },
  { value: 'paid', label: STATUS_STYLES.paid.label },
  { value: 'overdue', label: STATUS_STYLES.overdue.label },
  { value: 'dunning', label: STATUS_STYLES.dunning.label },
  { value: 'partial', label: STATUS_STYLES.partial.label },
  { value: 'cancelled', label: STATUS_STYLES.cancelled.label },
];

export function InvoiceFilterBar({
  filter,
  onFilterChange,
}: InvoiceFilterBarProps) {
  const hasActiveFilters = filter.status || filter.overdueOnly;

  const handleStatusChange = (value: string) => {
    onFilterChange({
      ...filter,
      status: value === 'all' ? undefined : (value as InvoiceStatus),
      page: 1, // Reset to first page
    });
  };

  const handleOverdueChange = (checked: boolean) => {
    onFilterChange({
      ...filter,
      overdueOnly: checked || undefined,
      page: 1,
    });
  };

  const handleReset = () => {
    onFilterChange({
      page: 1,
      perPage: filter.perPage ?? 20,
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-4 p-4 bg-card rounded-lg border">
      {/* Status Filter */}
      <div className="flex items-center gap-2">
        <Label htmlFor="status-filter" className="text-sm font-medium">
          {UI_LABELS.filterStatus}:
        </Label>
        <Select
          value={filter.status ?? 'all'}
          onValueChange={handleStatusChange}
        >
          <SelectTrigger id="status-filter" className="w-[160px]">
            <SelectValue placeholder="Status wählen" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Separator */}
      <div className="h-6 w-px bg-border" />

      {/* Overdue Only Checkbox */}
      <div className="flex items-center gap-2">
        <Checkbox
          id="overdue-filter"
          checked={filter.overdueOnly ?? false}
          onCheckedChange={handleOverdueChange}
        />
        <Label
          htmlFor="overdue-filter"
          className="text-sm font-medium cursor-pointer"
        >
          {UI_LABELS.filterOverdueOnly}
        </Label>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Reset Button */}
      {hasActiveFilters && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleReset}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4 mr-1" />
          {UI_LABELS.filterReset}
        </Button>
      )}
    </div>
  );
}
