/**
 * ReportListPage
 * German Enterprise Document Platform
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Search } from 'lucide-react';
import { ReportList } from '../components/ReportList';
import { useReports, useDeleteReport } from '../hooks/use-adhoc-reporting-queries';
import { DATA_SOURCE_LABELS } from '../types/adhoc-reporting-types';

export function ReportListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [dataSourceFilter, setDataSourceFilter] = useState<string>('all');

  const filters = {
    search: search || undefined,
    data_source: dataSourceFilter !== 'all' ? dataSourceFilter : undefined,
  };

  const { data: reports = [], isLoading } = useReports(filters);
  const deleteReportMutation = useDeleteReport();

  const handleCreateNew = () => {
    navigate({ to: '/adhoc-reporting/new' });
  };

  const handleExecute = (reportId: number) => {
    navigate({ to: `/adhoc-reporting/${reportId}` });
  };

  const handleEdit = (reportId: number) => {
    navigate({ to: `/adhoc-reporting/${reportId}` });
  };

  const handleDelete = async (reportId: number) => {
    if (confirm('Möchten Sie diesen Report wirklich löschen?')) {
      await deleteReportMutation.mutateAsync(reportId);
    }
  };

  const handleShare = (reportId: number) => {
    navigate({ to: `/adhoc-reporting/${reportId}`, search: { action: 'share' } });
  };

  const handleExport = (reportId: number) => {
    navigate({ to: `/adhoc-reporting/${reportId}`, search: { action: 'export' } });
  };

  const handleSchedule = (reportId: number) => {
    navigate({ to: `/adhoc-reporting/${reportId}`, search: { action: 'schedule' } });
  };

  const dataSources = Object.keys(DATA_SOURCE_LABELS);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Ad-Hoc Reports</h1>
        <p className="text-muted-foreground mt-2">
          Benutzerdefinierte Berichte erstellen und verwalten
        </p>
      </div>

      {/* Actions & Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1 flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Reports durchsuchen..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={dataSourceFilter} onValueChange={setDataSourceFilter}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Datenquelle" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Datenquellen</SelectItem>
              {dataSources.map((source) => (
                <SelectItem key={source} value={source}>
                  {DATA_SOURCE_LABELS[source]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={handleCreateNew}>
          <Plus className="h-4 w-4 mr-2" />
          Neuen Report erstellen
        </Button>
      </div>

      {/* Reports List */}
      <ReportList
        reports={reports}
        isLoading={isLoading}
        onExecute={handleExecute}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onShare={handleShare}
        onExport={handleExport}
        onSchedule={handleSchedule}
      />
    </div>
  );
}
