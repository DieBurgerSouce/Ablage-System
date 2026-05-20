/**
 * ReportBuilder Component
 * German Enterprise Document Platform
 */

import { useState, useEffect } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Save, Play } from 'lucide-react';
import { nanoid } from 'nanoid';
import { DataSourceSelector } from './DataSourceSelector';
import { ColumnConfigurator } from './ColumnConfigurator';
import { FilterBuilder } from './FilterBuilder';
import { GroupingAggregation } from './GroupingAggregation';
import { ReportPreview } from './ReportPreview';
import { useDataSources, useDataSourceColumns, useExecuteReportMutation } from '../hooks/use-adhoc-reporting-queries';
import type { ReportConfig } from '../types/adhoc-reporting-types';
import type { FilterConfig, AggregationConfig } from '../types/adhoc-reporting-types';

interface ReportBuilderProps {
  initialConfig?: Partial<ReportConfig>;
  onSave: (config: ReportConfig) => void;
  onCancel?: () => void;
  isSaving?: boolean;
}

export function ReportBuilder({
  initialConfig,
  onSave,
  onCancel,
  isSaving = false,
}: ReportBuilderProps) {
  // Report metadata
  const [name, setName] = useState(initialConfig?.name || '');
  const [description, setDescription] = useState(initialConfig?.description || '');

  // Report configuration
  const [selectedSource, setSelectedSource] = useState<string | null>(
    initialConfig?.data_source || null
  );
  const [selectedColumns, setSelectedColumns] = useState<string[]>(
    initialConfig?.columns || []
  );
  const [filters, setFilters] = useState<FilterConfig[]>(
    initialConfig?.filters?.map(f => ({ ...f, id: nanoid() })) || []
  );
  const [groupBy, setGroupBy] = useState<string[]>(initialConfig?.group_by || []);
  const [aggregations, setAggregations] = useState<AggregationConfig[]>(
    initialConfig?.aggregations?.map(a => ({ ...a, id: nanoid() })) || []
  );

  // Data fetching
  const { data: dataSources = [], isLoading: isLoadingDataSources } = useDataSources();
  const { data: columns = [], isLoading: isLoadingColumns } = useDataSourceColumns(selectedSource);
  const executeReportMutation = useExecuteReportMutation();

  // Preview state
  const [showPreview, setShowPreview] = useState(false);

  // Reset columns when data source changes
  useEffect(() => {
    if (selectedSource !== initialConfig?.data_source) {
      setSelectedColumns([]);
      setFilters([]);
      setGroupBy([]);
      setAggregations([]);
    }
  }, [selectedSource]);

  const handlePreview = () => {
    if (!selectedSource || selectedColumns.length === 0) {
      return;
    }

    const config: ReportConfig = {
      name: name || 'Vorschau',
      description,
      data_source: selectedSource,
      columns: selectedColumns,
      filters: filters.map(({ id, ...f }) => f),
      group_by: groupBy.length > 0 ? groupBy : undefined,
      aggregations: aggregations.length > 0 ? aggregations.map(({ id, ...a }) => a) : undefined,
    };

    // Create temporary report for preview (backend would need to support this)
    // For now, we'll just show the preview section
    setShowPreview(true);
  };

  const handleSave = () => {
    if (!selectedSource || selectedColumns.length === 0 || !name) {
      return;
    }

    const config: ReportConfig = {
      name,
      description,
      data_source: selectedSource,
      columns: selectedColumns,
      filters: filters.length > 0 ? filters.map(({ id, ...f }) => f) : undefined,
      group_by: groupBy.length > 0 ? groupBy : undefined,
      aggregations: aggregations.length > 0 ? aggregations.map(({ id, ...a }) => a) : undefined,
    };

    onSave(config);
  };

  const isValid = selectedSource && selectedColumns.length > 0 && name.trim().length > 0;

  return (
    <div className="space-y-6">
      {/* Report Metadata */}
      <Card className="p-6">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="report-name">Report Name *</Label>
            <Input
              id="report-name"
              placeholder="z.B. 'Monatliche Rechnungsübersicht'"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="report-description">Beschreibung (optional)</Label>
            <Textarea
              id="report-description"
              placeholder="Beschreiben Sie den Zweck dieses Reports..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
        </div>
      </Card>

      <Separator />

      {/* Data Source Selection */}
      <Card className="p-6">
        <DataSourceSelector
          dataSources={dataSources}
          selectedSource={selectedSource}
          onSelectSource={setSelectedSource}
          isLoading={isLoadingDataSources}
        />
      </Card>

      {selectedSource && (
        <>
          <Separator />

          {/* Column Configuration */}
          <Card className="p-6">
            <ColumnConfigurator
              columns={columns}
              selectedColumns={selectedColumns}
              onColumnsChange={setSelectedColumns}
              isLoading={isLoadingColumns}
            />
          </Card>

          <Separator />

          {/* Filters */}
          <Card className="p-6">
            <FilterBuilder
              columns={columns}
              filters={filters}
              onFiltersChange={setFilters}
            />
          </Card>

          <Separator />

          {/* Grouping & Aggregation */}
          <Card className="p-6">
            <GroupingAggregation
              columns={columns}
              groupBy={groupBy}
              aggregations={aggregations}
              onGroupByChange={setGroupBy}
              onAggregationsChange={setAggregations}
            />
          </Card>

          {showPreview && (
            <>
              <Separator />
              <div className="space-y-3">
                <h3 className="text-lg font-semibold">Vorschau</h3>
                <ReportPreview
                  result={executeReportMutation.data || null}
                  isLoading={executeReportMutation.isPending}
                  error={executeReportMutation.error}
                />
              </div>
            </>
          )}
        </>
      )}

      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-6 border-t">
        <div>
          {onCancel && (
            <Button type="button" variant="outline" onClick={onCancel}>
              Abbrechen
            </Button>
          )}
        </div>
        <div className="flex space-x-2">
          <Button
            type="button"
            variant="outline"
            onClick={handlePreview}
            disabled={!isValid}
          >
            <Play className="h-4 w-4 mr-2" />
            Vorschau
          </Button>
          <Button
            onClick={handleSave}
            disabled={!isValid || isSaving}
          >
            <Save className="h-4 w-4 mr-2" />
            {isSaving ? 'Speichern...' : 'Report speichern'}
          </Button>
        </div>
      </div>
    </div>
  );
}
