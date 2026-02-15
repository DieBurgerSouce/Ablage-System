/**
 * GroupingAggregation Component
 * German Enterprise Document Platform
 */

import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Trash2, BarChart3 } from 'lucide-react';
import { nanoid } from 'nanoid';
import type { Column, AggregationFunction } from '../types/adhoc-reporting-types';
import { AGGREGATION_FUNCTION_LABELS } from '../types/adhoc-reporting-types';

interface AggregationConfig {
  id: string;
  field: string;
  function: AggregationFunction;
  alias?: string;
}

interface GroupingAggregationProps {
  columns: Column[];
  groupBy: string[];
  aggregations: AggregationConfig[];
  onGroupByChange: (groupBy: string[]) => void;
  onAggregationsChange: (aggregations: AggregationConfig[]) => void;
}

const AGGREGATION_FUNCTIONS: AggregationFunction[] = ['count', 'sum', 'avg', 'min', 'max'];

export function GroupingAggregation({
  columns,
  groupBy,
  aggregations,
  onGroupByChange,
  onAggregationsChange,
}: GroupingAggregationProps) {
  const addAggregation = () => {
    const aggregatableColumns = columns.filter((col) => col.aggregatable);
    const newAggregation: AggregationConfig = {
      id: nanoid(),
      field: aggregatableColumns[0]?.key || '',
      function: 'count',
      alias: '',
    };
    onAggregationsChange([...aggregations, newAggregation]);
  };

  const removeAggregation = (aggId: string) => {
    onAggregationsChange(aggregations.filter((a) => a.id !== aggId));
  };

  const updateAggregation = (aggId: string, updates: Partial<AggregationConfig>) => {
    onAggregationsChange(
      aggregations.map((a) => (a.id === aggId ? { ...a, ...updates } : a))
    );
  };

  const handleToggleGroupBy = (columnKey: string) => {
    if (groupBy.includes(columnKey)) {
      onGroupByChange(groupBy.filter((key) => key !== columnKey));
    } else {
      onGroupByChange([...groupBy, columnKey]);
    }
  };

  const aggregatableColumns = columns.filter((col) => col.aggregatable);

  return (
    <div className="space-y-6">
      {/* Group By Section */}
      <div className="space-y-3">
        <Label>Gruppierung</Label>
        {columns.length === 0 ? (
          <Card className="p-6 text-center">
            <p className="text-sm text-muted-foreground">
              Keine Spalten für Gruppierung verfügbar
            </p>
          </Card>
        ) : (
          <Card className="p-4">
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {columns.map((column) => {
                const isSelected = groupBy.includes(column.key);

                return (
                  <div key={column.key} className="flex items-center space-x-3">
                    <Checkbox
                      id={`group-${column.key}`}
                      checked={isSelected}
                      onCheckedChange={() => handleToggleGroupBy(column.key)}
                    />
                    <Label
                      htmlFor={`group-${column.key}`}
                      className="font-normal cursor-pointer text-sm flex-1"
                    >
                      {column.name}
                    </Label>
                  </div>
                );
              })}
            </div>
          </Card>
        )}
      </div>

      {/* Aggregations Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label>Aggregationen</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addAggregation}
            disabled={aggregatableColumns.length === 0}
          >
            <Plus className="h-4 w-4 mr-2" />
            Aggregation hinzufügen
          </Button>
        </div>

        {aggregatableColumns.length === 0 ? (
          <Card className="p-8 text-center">
            <BarChart3 className="h-12 w-12 mx-auto text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              Keine aggregierbaren Spalten verfügbar
            </p>
          </Card>
        ) : aggregations.length === 0 ? (
          <Card className="p-6 text-center">
            <p className="text-sm text-muted-foreground">
              Keine Aggregationen definiert. Klicken Sie auf "Aggregation hinzufügen".
            </p>
          </Card>
        ) : (
          <div className="space-y-3">
            {aggregations.map((agg) => (
              <Card key={agg.id} className="p-4">
                <div className="flex items-start space-x-3">
                  <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <Label className="text-xs mb-1.5 block">Feld</Label>
                      <Select
                        value={agg.field}
                        onValueChange={(value) => updateAggregation(agg.id, { field: value })}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Feld auswählen" />
                        </SelectTrigger>
                        <SelectContent>
                          {aggregatableColumns.map((col) => (
                            <SelectItem key={col.key} value={col.key}>
                              {col.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label className="text-xs mb-1.5 block">Funktion</Label>
                      <Select
                        value={agg.function}
                        onValueChange={(value) =>
                          updateAggregation(agg.id, { function: value as AggregationFunction })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Funktion auswählen" />
                        </SelectTrigger>
                        <SelectContent>
                          {AGGREGATION_FUNCTIONS.map((func) => (
                            <SelectItem key={func} value={func}>
                              {AGGREGATION_FUNCTION_LABELS[func]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label className="text-xs mb-1.5 block">Alias (optional)</Label>
                      <Input
                        placeholder="z.B. 'Gesamt'"
                        value={agg.alias || ''}
                        onChange={(e) => updateAggregation(agg.id, { alias: e.target.value })}
                      />
                    </div>
                  </div>

                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="mt-6"
                    onClick={() => removeAggregation(agg.id)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
