/**
 * FilterBuilder Component
 * German Enterprise Document Platform
 */

import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Trash2, Filter } from 'lucide-react';
import { nanoid } from 'nanoid';
import type { Column, FilterConfig, FilterOperator } from '../types/adhoc-reporting-types';
import { FILTER_OPERATOR_LABELS } from '../types/adhoc-reporting-types';

interface FilterBuilderProps {
  columns: Column[];
  filters: FilterConfig[];
  onFiltersChange: (filters: FilterConfig[]) => void;
}

const OPERATOR_OPTIONS: FilterOperator[] = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'contains', 'in'];

export function FilterBuilder({ columns, filters, onFiltersChange }: FilterBuilderProps) {
  const addFilter = () => {
    const newFilter: FilterConfig = {
      id: nanoid(),
      field: columns[0]?.key || '',
      operator: 'eq',
      value: '',
    };
    onFiltersChange([...filters, newFilter]);
  };

  const removeFilter = (filterId: string) => {
    onFiltersChange(filters.filter((f) => f.id !== filterId));
  };

  const updateFilter = (filterId: string, updates: Partial<FilterConfig>) => {
    onFiltersChange(
      filters.map((f) => (f.id === filterId ? { ...f, ...updates } : f))
    );
  };

  const filterableColumns = columns.filter((col) => col.filterable);

  if (filterableColumns.length === 0) {
    return (
      <div className="space-y-3">
        <Label>Filter</Label>
        <Card className="p-8 text-center">
          <Filter className="h-12 w-12 mx-auto text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">
            Keine filterbaren Spalten verfügbar
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Filter</Label>
        <Button type="button" variant="outline" size="sm" onClick={addFilter}>
          <Plus className="h-4 w-4 mr-2" />
          Filter hinzufügen
        </Button>
      </div>

      {filters.length === 0 ? (
        <Card className="p-6 text-center">
          <p className="text-sm text-muted-foreground">
            Keine Filter definiert. Klicken Sie auf "Filter hinzufügen", um zu beginnen.
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {filters.map((filter, index) => (
            <Card key={filter.id} className="p-4">
              <div className="flex items-start space-x-3">
                <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <Label className="text-xs mb-1.5 block">Feld</Label>
                    <Select
                      value={filter.field}
                      onValueChange={(value) => updateFilter(filter.id, { field: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Feld auswählen" />
                      </SelectTrigger>
                      <SelectContent>
                        {filterableColumns.map((col) => (
                          <SelectItem key={col.key} value={col.key}>
                            {col.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-xs mb-1.5 block">Operator</Label>
                    <Select
                      value={filter.operator}
                      onValueChange={(value) =>
                        updateFilter(filter.id, { operator: value as FilterOperator })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Operator auswählen" />
                      </SelectTrigger>
                      <SelectContent>
                        {OPERATOR_OPTIONS.map((op) => (
                          <SelectItem key={op} value={op}>
                            {FILTER_OPERATOR_LABELS[op]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-xs mb-1.5 block">Wert</Label>
                    <Input
                      placeholder="Wert eingeben"
                      value={String(filter.value)}
                      onChange={(e) => updateFilter(filter.id, { value: e.target.value })}
                    />
                  </div>
                </div>

                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="mt-6"
                  onClick={() => removeFilter(filter.id)}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
              {index < filters.length - 1 && (
                <div className="mt-3 text-center">
                  <span className="text-xs font-medium text-muted-foreground bg-muted px-2 py-1 rounded">
                    UND
                  </span>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
