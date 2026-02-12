/**
 * TemplateFilters - Filter-Komponente für Vorlagen
 *
 * Features:
 * - Kategorie-Filter
 * - Status-Filter (Aktiv/Inaktiv)
 * - Freitextsuche
 * - Tag-Filter
 */

import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Search, X } from 'lucide-react';
import {
  TemplateCategory,
  TEMPLATE_CATEGORY_LABELS,
  type TemplateListParams,
} from '../types/template-types';

interface TemplateFiltersProps {
  filters: TemplateListParams;
  onFiltersChange: (filters: TemplateListParams) => void;
}

export function TemplateFilters({ filters, onFiltersChange }: TemplateFiltersProps) {
  const handleSearchChange = (value: string) => {
    onFiltersChange({ ...filters, search: value || undefined, offset: 0 });
  };

  const handleCategoryChange = (value: string) => {
    onFiltersChange({
      ...filters,
      category: value === 'all' ? undefined : (value as TemplateCategory),
      offset: 0,
    });
  };

  const handleActiveChange = (value: string) => {
    let isActive: boolean | undefined;
    if (value === 'active') isActive = true;
    else if (value === 'inactive') isActive = false;
    else isActive = undefined;

    onFiltersChange({ ...filters, is_active: isActive, offset: 0 });
  };

  const handleDefaultChange = (value: string) => {
    let isDefault: boolean | undefined;
    if (value === 'default') isDefault = true;
    else if (value === 'not_default') isDefault = false;
    else isDefault = undefined;

    onFiltersChange({ ...filters, is_default: isDefault, offset: 0 });
  };

  const handleClearFilters = () => {
    onFiltersChange({
      offset: 0,
      limit: filters.limit,
    });
  };

  const hasActiveFilters =
    filters.search ||
    filters.category ||
    filters.is_active !== undefined ||
    filters.is_default !== undefined;

  return (
    <div className="flex flex-wrap items-center gap-4">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px] max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Vorlagen durchsuchen..."
          value={filters.search || ''}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Category Filter */}
      <Select
        value={filters.category || 'all'}
        onValueChange={handleCategoryChange}
      >
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder="Kategorie" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle Kategorien</SelectItem>
          {Object.entries(TEMPLATE_CATEGORY_LABELS).map(([value, label]) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Active Filter */}
      <Select
        value={
          filters.is_active === true
            ? 'active'
            : filters.is_active === false
            ? 'inactive'
            : 'all'
        }
        onValueChange={handleActiveChange}
      >
        <SelectTrigger className="w-[150px]">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle</SelectItem>
          <SelectItem value="active">Aktiv</SelectItem>
          <SelectItem value="inactive">Inaktiv</SelectItem>
        </SelectContent>
      </Select>

      {/* Default Filter */}
      <Select
        value={
          filters.is_default === true
            ? 'default'
            : filters.is_default === false
            ? 'not_default'
            : 'all'
        }
        onValueChange={handleDefaultChange}
      >
        <SelectTrigger className="w-[150px]">
          <SelectValue placeholder="Standard" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Alle</SelectItem>
          <SelectItem value="default">Standard</SelectItem>
          <SelectItem value="not_default">Kein Standard</SelectItem>
        </SelectContent>
      </Select>

      {/* Clear Filters */}
      {hasActiveFilters && (
        <Button variant="ghost" size="sm" onClick={handleClearFilters}>
          <X className="h-4 w-4 mr-1" />
          Filter löschen
        </Button>
      )}
    </div>
  );
}
