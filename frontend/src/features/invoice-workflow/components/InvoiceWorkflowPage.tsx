/**
 * Invoice Workflow Page - Vollautomatischer Rechnungsworkflow
 *
 * Dashboard für automatische Rechnungsverarbeitung und Freigabe-Pipeline.
 * - Pipeline-Visualisierung (Eingang -> OCR -> Zuordnung -> Prüfung -> Freigabe -> Zahlung)
 * - Automatisierungsstatistiken
 * - Freigabe-Warteschlange mit Approve/Reject-Aktionen
 */

import { useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  usePipelineStatus,
  useApprovalQueue,
  useAutomationStats,
  useApproveInvoice,
  useRejectInvoice,
} from '../hooks/use-invoice-workflow';
import { emitChecklistComplete } from '@/features/product-tour';
import {
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  TrendingUp,
  Activity,
  Zap,
  FileText,
  Users,
  DollarSign,
  ChevronRight,
} from 'lucide-react';

export function InvoiceWorkflowPage() {
  const { data: pipeline, isLoading: pipelineLoading, error: pipelineError, isRefetching } = usePipelineStatus();
  const { data: queue, isLoading: queueLoading, error: queueError } = useApprovalQueue();
  const { data: stats, isLoading: statsLoading } = useAutomationStats();
  const approveMutation = useApproveInvoice();
  const rejectMutation = useRejectInvoice();

  useEffect(() => {
    emitChecklistComplete('view_invoices')
  }, [])

  if (pipelineLoading || queueLoading || statsLoading) {
    return <DashboardSkeleton />;
  }

  if (pipelineError || queueError) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden des Rechnungsworkflows. Bitte versuchen Sie es später erneut.
        </AlertDescription>
      </Alert>
    );
  }

  if (!pipeline || !queue || !stats) {
    return null;
  }

  const handleApprove = (id: string) => {
    approveMutation.mutate(id);
  };

  const handleReject = (id: string) => {
    rejectMutation.mutate(id);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight font-display">
            Rechnungsworkflow
          </h2>
          <p className="text-muted-foreground mt-1">
            Automatische Rechnungsverarbeitung und Freigabe-Pipeline
          </p>
        </div>
        {isRefetching && (
          <Badge variant="outline" className="animate-pulse">
            <Activity className="mr-2 h-3 w-3" />
            Aktualisierung...
          </Badge>
        )}
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-6 md:grid-cols-4" data-tour="workflow-stats">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Verarbeitet</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_processed}</div>
            <p className="text-xs text-muted-foreground">
              Gesamt verarbeitete Rechnungen
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Auto-Genehmigt</CardTitle>
            <Zap className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats.auto_approved}</div>
            <p className="text-xs text-muted-foreground">
              Automatisch freigegeben
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Manuell</CardTitle>
            <Users className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-yellow-600">{stats.manual_review}</div>
            <p className="text-xs text-muted-foreground">
              Manuelle Prüfung erforderlich
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Durchschnittliche Zeit</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats.avg_processing_time_seconds.toFixed(1)}s
            </div>
            <p className="text-xs text-muted-foreground">
              Bearbeitungszeit pro Rechnung
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Automation Rate */}
      <Card data-tour="workflow-approval">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Automatisierungsrate
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="h-4 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full bg-green-600 transition-all"
                  style={{ width: `${stats.approval_rate * 100}%` }}
                />
              </div>
            </div>
            <div className="text-2xl font-bold text-green-600">
              {(stats.approval_rate * 100).toFixed(1)}%
            </div>
          </div>
          <p className="text-sm text-muted-foreground mt-2">
            {stats.auto_approved} von {stats.total_processed} Rechnungen wurden automatisch verarbeitet
          </p>
        </CardContent>
      </Card>

      {/* Pipeline Visualization */}
      <Card data-tour="workflow-pipeline">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Verarbeitungs-Pipeline
          </CardTitle>
          <CardDescription>
            Aktueller Status der Rechnungsverarbeitung
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-2">
            {pipeline.stages.map((stage, idx) => (
              <div key={stage.name} className="flex items-center gap-2 flex-1">
                <div className="flex-1">
                  <Card
                    className={`border-2 ${
                      stage.status === 'completed'
                        ? 'border-green-600 bg-green-50 dark:bg-green-950'
                        : stage.status === 'processing'
                        ? 'border-blue-600 bg-blue-50 dark:bg-blue-950'
                        : stage.status === 'error'
                        ? 'border-red-600 bg-red-50 dark:bg-red-950'
                        : 'border-muted'
                    }`}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium">{stage.name}</span>
                        {getStageIcon(stage.status)}
                      </div>
                      <div className="text-2xl font-bold">{stage.count}</div>
                      <Badge variant="outline" className="mt-2 text-xs">
                        {getStageStatusLabel(stage.status)}
                      </Badge>
                    </CardContent>
                  </Card>
                </div>
                {idx < pipeline.stages.length - 1 && (
                  <ChevronRight className="h-6 w-6 text-muted-foreground flex-shrink-0" />
                )}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-4 mt-6 pt-6 border-t">
            <div>
              <p className="text-sm text-muted-foreground">Gesamt verarbeitet</p>
              <p className="text-xl font-semibold">{pipeline.total_processed}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Automatisch freigegeben</p>
              <p className="text-xl font-semibold text-green-600">{pipeline.auto_approved}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Warten auf Prüfung</p>
              <p className="text-xl font-semibold text-yellow-600">{pipeline.pending_review}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Approval Queue */}
      <Card data-tour="workflow-review">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Freigabe-Warteschlange
          </CardTitle>
          <CardDescription>
            {queue.total} {queue.total === 1 ? 'Rechnung wartet' : 'Rechnungen warten'} auf manuelle Prüfung
          </CardDescription>
        </CardHeader>
        <CardContent>
          {queue.items.length > 0 ? (
            <div className="space-y-4">
              {queue.items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-start justify-between gap-4 p-4 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className="flex-1 space-y-2">
                    <div className="flex items-start gap-3">
                      <FileText className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
                      <div className="space-y-1 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-semibold">{item.document_title}</h4>
                          <Badge
                            variant={item.confidence >= 0.8 ? 'default' : 'secondary'}
                            className="flex-shrink-0"
                          >
                            {(item.confidence * 100).toFixed(0)}% Konfidenz
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Users className="h-4 w-4" />
                            {item.supplier_name}
                          </span>
                          <span className="flex items-center gap-1">
                            <DollarSign className="h-4 w-4" />
                            {item.amount.toLocaleString('de-DE', {
                              style: 'currency',
                              currency: item.currency,
                            })}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-4 w-4" />
                            {new Date(item.created_at).toLocaleString('de-DE')}
                          </span>
                        </div>
                        <div className="flex items-start gap-2 mt-2 p-2 rounded bg-muted/50">
                          <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5 flex-shrink-0" />
                          <div className="text-sm">
                            <p className="font-medium text-yellow-600">
                              Empfohlene Aktion: {item.suggested_action}
                            </p>
                            <p className="text-muted-foreground mt-1">{item.reason}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <Button
                      size="sm"
                      variant="default"
                      onClick={() => handleApprove(item.id)}
                      disabled={approveMutation.isPending || rejectMutation.isPending}
                      className="bg-green-600 hover:bg-green-700"
                    >
                      <CheckCircle2 className="mr-2 h-4 w-4" />
                      Genehmigen
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleReject(item.id)}
                      disabled={approveMutation.isPending || rejectMutation.isPending}
                    >
                      <XCircle className="mr-2 h-4 w-4" />
                      Ablehnen
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <CheckCircle2 className="h-16 w-16 text-green-600 mx-auto mb-4" />
              <h3 className="text-xl font-semibold mb-2">Keine Rechnungen zur Prüfung</h3>
              <p className="text-muted-foreground">
                Alle Rechnungen wurden automatisch verarbeitet oder es gibt keine neuen Einträge.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ==================== Helper Functions ====================

function getStageIcon(status: string) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-5 w-5 text-green-600" />;
    case 'processing':
      return <Activity className="h-5 w-5 text-blue-600 animate-pulse" />;
    case 'error':
      return <XCircle className="h-5 w-5 text-red-600" />;
    default:
      return <Clock className="h-5 w-5 text-muted-foreground" />;
  }
}

function getStageStatusLabel(status: string): string {
  switch (status) {
    case 'completed':
      return 'Abgeschlossen';
    case 'processing':
      return 'In Bearbeitung';
    case 'error':
      return 'Fehler';
    default:
      return 'Ausstehend';
  }
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96 mt-2" />
      </div>
      <div className="grid gap-6 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-3 w-32 mt-2" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}
