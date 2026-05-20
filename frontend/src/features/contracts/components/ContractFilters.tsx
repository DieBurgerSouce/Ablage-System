/**
 * ContractFilters - Filter-Leiste für Vertrags-Liste
 *
 * Filter:
 * - Status (Entwurf, Aktiv, Ablaufend, etc.)
 * - Vertragstyp
 * - Suche
 * - Zeitraum (ablaufend innerhalb X Tage)
 */

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Search, X, Filter, Plus } from 'lucide-react';
import {
  ContractStatus,
  ContractType,
  CONTRACT_STATUS_LABELS,
  CONTRACT_TYPE_LABELS,
} from '../types/contract-types';
import type { ContractListParams } from '../types/contract-types';

interface ContractFiltersProps {
  filters: ContractListParams;
  onFiltersChange: (filters: ContractListParams) => void;
  onCreateContract: () => void;
}

const EXPIRING_OPTIONS = [
  { value: 'all', label: 'Alle Verträge' },
  { value: '30', label: 'Ablaufend in 30 Tagen' },
  { value: '60', label: 'Ablaufend in 60 Tagen' },
  { value: '90', label: 'Ablaufend in 90 Tagen' },
];

export function ContractFilters({
  filters,
  onFiltersChange,
  onCreateContract,
}: ContractFiltersProps) {
  const [searchInput, setSearchInput] = useState(filters.search || '');

  const handleSearchSubmit = () => {
    onFiltersChange({ ...filters, search: searchInput || undefined, offset: 0 });
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearchSubmit();
    }
  };

  const handleStatusChange = (value: string) => {
    onFiltersChange({
      ...filters,
      status: value === 'all' ? undefined : (value as ContractStatus),
      offset: 0,
    });
  };

  const handleTypeChange = (value: string) => {
    onFiltersChange({
      ...filters,
      contract_type: value === 'all' ? undefined : (value as ContractType),
      offset: 0,
    });
  };

  const handleExpiringChange = (value: string) => {
    onFiltersChange({
      ...filters,
      expiring_within_days: value === 'all' ? undefined : parseInt(value, 10),
      offset: 0,
    });
  };

  const clearFilters = () => {
    setSearchInput('');
    onFiltersChange({
      offset: 0,
      limit: filters.limit,
    });
  };

  const hasActiveFilters =
    filters.status ||
    filters.contract_type ||
    filters.search ||
    filters.expiring_within_days;

  const activeFilterCount = [
    filters.status,
    filters.contract_type,
    filters.search,
    filters.expiring_within_days,
  ].filter(Boolean).length;

  return (
    <div className="space-y-4">
      {/* Top Row: Search + Create Button */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Verträge durchsuchen..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            className="pl-9 pr-24"
          />
          <Button
            variant="secondary"
            size="sm"
            className="absolute right-1 top-1/2 -translate-y-1/2"
            onClick={handleSearchSubmit}
          >
            Suchen
          </Button>
        </div>
        <Button onClick={onCreateContract} className="shrink-0">
          <Plus className="h-4 w-4 mr-2" />
          Neuer Vertrag
        </Button>
      </div>

      {/* Filter Row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Filter:</span>
        </div>

        {/* Status Filter */}
        <Select
          value={filters.status || 'all'}
          onValueChange={handleStatusChange}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Status</SelectItem>
            {Object.entries(CONTRACT_STATUS_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Type Filter */}
        <Select
          value={filters.contract_type || 'all'}
          onValueChange={handleTypeChange}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Vertragstyp" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Typen</SelectItem>
            {Object.entries(CONTRACT_TYPE_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Expiring Filter */}
        <Select
          value={filters.expiring_within_days?.toString() || 'all'}
          onValueChange={handleExpiringChange}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Laufzeit" />
          </SelectTrigger>
          <SelectContent>
            {EXPIRING_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Active Filters Badge + Clear */}
        {hasActiveFilters && (
          <div className="flex items-center gap-2">
            <Badge variant="secondary">
              {activeFilterCount} Filter aktiv
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="h-8 px-2"
            >
              <X className="h-4 w-4 mr-1" />
              Zurücksetzen
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
