/**
 * ReportsDashboard Component
 *
 * Haupt-Dashboard für den Report-Builder mit Tabs für Reports und Historie.
 */

import { useState } from 'react';
import {
  BarChart3,
  Clock,
  Download,
  FileText,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Share2,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatDistanceToNow, format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  useTemplates,
  useExecutions,
  useSharedWithMe,
  useCancelExecution,
} from '../hooks/useReports';
import { getDownloadUrl } from '../api';
import type { ReportTemplate, ReportExecution, ExecutionStatus } from '../types';
import { ReportsList } from './ReportsList';
import { ReportBuilder } from './ReportBuilder';

const statusLabels: Record<ExecutionStatus, string> = {
  pending: 'Wartend',
  running: 'Läuft',
  completed: 'Abgeschlossen',
  failed: 'Fehlgeschlagen',
  cancelled: 'Abgebrochen',
};

const statusColors: Record<ExecutionStatus, string> = {
  pending: 'bg-yellow-500/10 text-yellow-600',
  running: 'bg-blue-500/10 text-blue-600',
  completed: 'bg-green-500/10 text-green-600',
  failed: 'bg-red-500/10 text-red-600',
  cancelled: 'bg-gray-500/10 text-gray-600',
};

export function ReportsDashboard() {
  const [activeTab, setActiveTab] = useState('reports');
  const [builderOpen, setBuilderOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<ReportTemplate | undefined>();

  const { data: templates, isLoading: templatesLoading } = useTemplates();
  const { data: executions, isLoading: executionsLoading, refetch: refetchExecutions } = useExecutions({ limit: 50 });
  const { data: sharedReports, isLoading: sharedLoading } = useSharedWithMe();
  const cancelMutation = useCancelExecution();

  const handleNewReport = () => {
    setEditingTemplate(undefined);
    setBuilderOpen(true);
  };

  const handleEditReport = (template: ReportTemplate) => {
    setEditingTemplate(template);
    setBuilderOpen(true);
  };

  const handleBuilderClose = () => {
    setBuilderOpen(false);
    setEditingTemplate(undefined);
  };

  const handleDownload = (execution: ReportExecution) => {
    if (execution.status === 'completed') {
      window.open(getDownloadUrl(execution.id), '_blank');
    }
  };

  const handleCancel = (execution: ReportExecution) => {
    cancelMutation.mutate(execution.id);
  };

  // Statistiken berechnen
  const stats = {
    totalTemplates: templates?.length || 0,
    scheduledTemplates: templates?.filter((t) => t.is_scheduled).length || 0,
    totalExecutions: executions?.length || 0,
    failedExecutions: executions?.filter((e) => e.status === 'failed').length || 0,
    sharedCount: sharedReports?.length || 0,
  };

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Reports</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalTemplates}</div>
            <p className="text-xs text-muted-foreground">
              {stats.scheduledTemplates} geplant
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Ausführungen</CardTitle>
            <History className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalExecutions}</div>
            <p className="text-xs text-muted-foreground">
              Letzte 50 Ausführungen
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Fehlgeschlagen</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              {stats.failedExecutions}
            </div>
            <p className="text-xs text-muted-foreground">
              In den letzten 50 Ausführungen
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Geteilt mit mir</CardTitle>
            <Share2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.sharedCount}</div>
            <p className="text-xs text-muted-foreground">
              Von anderen Nutzern geteilt
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="reports" className="gap-2">
              <FileText className="h-4 w-4" />
              Meine Reports
            </TabsTrigger>
            <TabsTrigger value="shared" className="gap-2">
              <Share2 className="h-4 w-4" />
              Geteilt mit mir
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2">
              <History className="h-4 w-4" />
              Ausführungen
            </TabsTrigger>
          </TabsList>

          <Button onClick={handleNewReport}>
            <Plus className="h-4 w-4 mr-2" />
            Neuer Report
          </Button>
        </div>

        <TabsContent value="reports" className="mt-6">
          <ReportsList onEdit={handleEditReport} />
        </TabsContent>

        <TabsContent value="shared" className="mt-6">
          {sharedLoading ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <Card key={i}>
                  <CardHeader>
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-20" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : sharedReports && sharedReports.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {sharedReports.map((share) => (
                <Card key={share.id}>
                  <CardHeader>
                    <CardTitle className="text-base">{share.template_name}</CardTitle>
                    <CardDescription>
                      Geteilt von {share.shared_with_name || share.shared_with_email}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-2">
                      {share.can_view && <Badge variant="outline">Ansehen</Badge>}
                      {share.can_execute && <Badge variant="outline">Ausführen</Badge>}
                      {share.can_edit && <Badge variant="outline">Bearbeiten</Badge>}
                    </div>
                    {share.expires_at && (
                      <p className="text-xs text-muted-foreground mt-2">
                        Läuft ab: {format(new Date(share.expires_at), 'dd.MM.yyyy', { locale: de })}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Share2 className="h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium">Keine geteilten Reports</h3>
                <p className="text-muted-foreground text-sm mt-1">
                  Es wurden noch keine Reports mit Ihnen geteilt.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Ausführungs-Historie</CardTitle>
                <CardDescription>
                  Übersicht über alle Report-Ausführungen.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={() => refetchExecutions()}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Aktualisieren
              </Button>
            </CardHeader>
            <CardContent>
              {executionsLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : executions && executions.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Report</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Format</TableHead>
                      <TableHead>Zeilen</TableHead>
                      <TableHead>Dauer</TableHead>
                      <TableHead>Erstellt</TableHead>
                      <TableHead className="text-right">Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {executions.map((execution) => (
                      <TableRow key={execution.id}>
                        <TableCell className="font-medium">
                          {execution.template_name || 'Unbekannt'}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="secondary"
                            className={statusColors[execution.status]}
                          >
                            {execution.status === 'running' && (
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                            )}
                            {statusLabels[execution.status]}
                          </Badge>
                        </TableCell>
                        <TableCell className="uppercase">
                          {execution.format}
                        </TableCell>
                        <TableCell>
                          {execution.row_count?.toLocaleString() || '-'}
                        </TableCell>
                        <TableCell>
                          {execution.duration_ms
                            ? `${(execution.duration_ms / 1000).toFixed(1)}s`
                            : '-'}
                        </TableCell>
                        <TableCell>
                          {formatDistanceToNow(new Date(execution.created_at), {
                            addSuffix: true,
                            locale: de,
                          })}
                        </TableCell>
                        <TableCell className="text-right">
                          {execution.status === 'completed' && execution.download_url && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDownload(execution)}
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                          )}
                          {(execution.status === 'pending' ||
                            execution.status === 'running') && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCancel(execution)}
                            >
                              Abbrechen
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="text-center text-muted-foreground py-8">
                  <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>Keine Ausführungen vorhanden.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Report Builder Sheet */}
      <ReportBuilder
        template={editingTemplate}
        open={builderOpen}
        onClose={handleBuilderClose}
      />
    </div>
  );
}
