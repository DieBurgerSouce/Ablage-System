/**
 * ColumnConfigurator Component
 * German Enterprise Document Platform
 */

import { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowUp, ArrowDown, Columns } from 'lucide-react';
import type { Column } from '../types/adhoc-reporting-types';

interface ColumnConfiguratorProps {
  columns: Column[];
  selectedColumns: string[];
  onColumnsChange: (columns: string[]) => void;
  isLoading?: boolean;
}

export function ColumnConfigurator({
  columns,
  selectedColumns,
  onColumnsChange,
  isLoading = false,
}: ColumnConfiguratorProps) {
  const [aliases, setAliases] = useState<Record<string, string>>({});

  const handleToggleColumn = (columnKey: string) => {
    if (selectedColumns.includes(columnKey)) {
      onColumnsChange(selectedColumns.filter((key) => key !== columnKey));
    } else {
      onColumnsChange([...selectedColumns, columnKey]);
    }
  };

  const handleMoveUp = (columnKey: string) => {
    const index = selectedColumns.indexOf(columnKey);
    if (index > 0) {
      const newColumns = [...selectedColumns];
      [newColumns[index - 1], newColumns[index]] = [newColumns[index], newColumns[index - 1]];
      onColumnsChange(newColumns);
    }
  };

  const handleMoveDown = (columnKey: string) => {
    const index = selectedColumns.indexOf(columnKey);
    if (index < selectedColumns.length - 1) {
      const newColumns = [...selectedColumns];
      [newColumns[index], newColumns[index + 1]] = [newColumns[index + 1], newColumns[index]];
      onColumnsChange(newColumns);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Label>Spalten auswählen</Label>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (columns.length === 0) {
    return (
      <div className="space-y-3">
        <Label>Spalten auswählen</Label>
        <Card className="p-8 text-center">
          <Columns className="h-12 w-12 mx-auto text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">
            Keine Spalten verfügbar. Bitte wählen Sie zuerst eine Datenquelle aus.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Spalten auswählen</Label>
        <span className="text-xs text-muted-foreground">
          {selectedColumns.length} von {columns.length} ausgewählt
        </span>
      </div>
      <Card className="p-4">
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {columns.map((column) => {
            const isSelected = selectedColumns.includes(column.key);
            const selectedIndex = selectedColumns.indexOf(column.key);

            return (
              <div
                key={column.key}
                className={`flex items-start space-x-3 p-2 rounded transition-colors ${
                  isSelected ? 'bg-muted/50' : ''
                }`}
              >
                <Checkbox
                  id={`column-${column.key}`}
                  checked={isSelected}
                  onCheckedChange={() => handleToggleColumn(column.key)}
                  className="mt-1"
                />
                <div className="flex-1 min-w-0">
                  <Label
                    htmlFor={`column-${column.key}`}
                    className="font-medium cursor-pointer text-sm"
                  >
                    {column.name}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {column.data_type}
                    {column.aggregatable && ' • Aggregierbar'}
                  </p>
                  {isSelected && (
                    <Input
                      placeholder="Alias (optional)"
                      value={aliases[column.key] || ''}
                      onChange={(e) =>
                        setAliases((prev) => ({ ...prev, [column.key]: e.target.value }))
                      }
                      className="mt-2 h-8 text-xs"
                    />
                  )}
                </div>
                {isSelected && (
                  <div className="flex flex-col space-y-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={() => handleMoveUp(column.key)}
                      disabled={selectedIndex === 0}
                    >
                      <ArrowUp className="h-3 w-3" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={() => handleMoveDown(column.key)}
                      disabled={selectedIndex === selectedColumns.length - 1}
                    >
                      <ArrowDown className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
