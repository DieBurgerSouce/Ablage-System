/**
 * ReportViewPage
 * German Enterprise Document Platform
 */

import { useState } from 'react';
import { useParams, useNavigate, useSearch } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ArrowLeft, Play, Share2, Calendar, Edit2, Trash2 } from 'lucide-react';
import { ReportPreview } from '../components/ReportPreview';
import { ExportButtons } from '../components/ExportButtons';
import { ShareDialog } from '../components/ShareDialog';
import { ScheduleEditor } from '../components/ScheduleEditor';
import {
  useReport,
  useExecuteReport,
  useExportReport,
  useShareReport,
  useRemoveShare,
  useScheduleReport,
  useDeleteReport,
} from '../hooks/use-adhoc-reporting-queries';
import { DATA_SOURCE_LABELS } from '../types/adhoc-reporting-types';
import type { Schedule } from '../types/adhoc-reporting-types';

export function ReportViewPage() {
  const { id } = useParams({ from: '/adhoc-reporting/$id' });
  const navigate = useNavigate();
  const search = useSearch({ from: '/adhoc-reporting/$id' });

  const reportId = parseInt(id, 10);
  const { data: report, isLoading: isLoadingReport } = useReport(reportId);

  const [executeEnabled, setExecuteEnabled] = useState(true);
  const executionResult = useExecuteReport(reportId, undefined, { enabled: executeEnabled });

  const exportReportMutation = useExportReport();
  const shareReportMutation = useShareReport(reportId);
  const removeShareMutation = useRemoveShare(reportId);
  const scheduleReportMutation = useScheduleReport(reportId);
  const deleteReportMutation = useDeleteReport();

  // Dialog states
  const [showShareDialog, setShowShareDialog] = useState(search?.action === 'share');
  const [showScheduleDialog, setShowScheduleDialog] = useState(search?.action === 'schedule');

  const handleExecute = () => {
    setExecuteEnabled(false);
    setTimeout(() => setExecuteEnabled(true), 100);
  };

  const handleExport = (format: 'pdf' | 'excel' | 'csv') => {
    exportReportMutation.mutate({ reportId, format });
  };

  const handleShare = async (userIds: number[], permission: 'read' | 'write') => {
    await shareReportMutation.mutateAsync({ user_ids: userIds, permission });
  };

  const handleRemoveShare = async (shareId: number) => {
    await removeShareMutation.mutateAsync(shareId);
  };

  const handleScheduleSave = async (schedule: Partial<Schedule>) => {
    await scheduleReportMutation.mutateAsync({
      frequency: schedule.frequency!,
      time: schedule.time!,
      recipients: schedule.recipients!,
      active: schedule.active,
    });
    setShowScheduleDialog(false);
  };

  const handleEdit = () => {
    // In a real implementation, you'd navigate to an edit page
    // For now, we'll navigate to the builder with the report data
    navigate({ to: '/adhoc-reporting/new' });
  };

  const handleDelete = async () => {
    if (confirm('Möchten Sie diesen Report wirklich löschen?')) {
      await deleteReportMutation.mutateAsync(reportId);
      navigate({ to: '/adhoc-reporting' });
    }
  };

  if (isLoadingReport) {
    return (
      <div className="space-y-6">
        <div className="h-12 bg-muted animate-pulse rounded" />
        <div className="h-64 bg-muted animate-pulse rounded" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-semibold mb-2">Report nicht gefunden</h2>
        <Button onClick={() => navigate({ to: '/adhoc-reporting' })}>
          Zurück zur Übersicht
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-4">
          <Button variant="ghost" size="icon" onClick={() => navigate({ to: '/adhoc-reporting' })}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center space-x-3 mb-2">
              <h1 className="text-3xl font-bold tracking-tight">{report.name}</h1>
              <Badge variant="secondary">
                {DATA_SOURCE_LABELS[report.data_source] || report.data_source}
              </Badge>
            </div>
            {report.description && (
              <p className="text-muted-foreground">{report.description}</p>
            )}
            <div className="flex items-center space-x-4 mt-2 text-sm text-muted-foreground">
              <span>
                Erstellt: {report.created_at ? new Date(report.created_at).toLocaleDateString('de-DE') : '-'}
              </span>
              {report.last_executed_at && (
                <span>
                  Zuletzt ausgeführt: {new Date(report.last_executed_at).toLocaleDateString('de-DE')}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex space-x-2">
          <Button variant="outline" onClick={handleEdit}>
            <Edit2 className="h-4 w-4 mr-2" />
            Bearbeiten
          </Button>
          <Button variant="outline" onClick={() => setShowShareDialog(true)}>
            <Share2 className="h-4 w-4 mr-2" />
            Freigeben
          </Button>
          <Button variant="outline" onClick={() => setShowScheduleDialog(true)}>
            <Calendar className="h-4 w-4 mr-2" />
            Zeitplan
          </Button>
          <Button variant="outline" onClick={handleDelete} className="text-destructive">
            <Trash2 className="h-4 w-4 mr-2" />
            Löschen
          </Button>
        </div>
      </div>

      {/* Actions */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <Button onClick={handleExecute}>
            <Play className="h-4 w-4 mr-2" />
            Report ausführen
          </Button>
          <ExportButtons
            reportId={reportId}
            onExport={handleExport}
            isExporting={exportReportMutation.isPending}
          />
        </div>
      </Card>

      {/* Report Configuration */}
      <Card className="p-6">
        <h3 className="font-semibold mb-4">Report-Konfiguration</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Spalten:</span>
            <div className="font-medium">{report.columns.length}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Filter:</span>
            <div className="font-medium">{report.filters?.length || 0}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Gruppierung:</span>
            <div className="font-medium">{report.group_by?.length || 0} Felder</div>
          </div>
          <div>
            <span className="text-muted-foreground">Aggregationen:</span>
            <div className="font-medium">{report.aggregations?.length || 0}</div>
          </div>
        </div>
      </Card>

      {/* Results */}
      <ReportPreview
        result={executionResult.data || null}
        isLoading={executionResult.isLoading}
        error={executionResult.error}
      />

      {/* Share Dialog */}
      <ShareDialog
        open={showShareDialog}
        onOpenChange={setShowShareDialog}
        shares={[]} // Would come from report.shares in real implementation
        onShare={handleShare}
        onRemoveShare={handleRemoveShare}
        isLoading={shareReportMutation.isPending}
      />

      {/* Schedule Dialog */}
      <Dialog open={showScheduleDialog} onOpenChange={setShowScheduleDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Report-Zeitplan konfigurieren</DialogTitle>
            <DialogDescription>
              Legen Sie fest, wann dieser Report automatisch ausgeführt werden soll
            </DialogDescription>
          </DialogHeader>
          <ScheduleEditor
            onSave={handleScheduleSave}
            onCancel={() => setShowScheduleDialog(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
