/**
 * ExportJobProgress Component
 *
 * Zeigt den Fortschritt eines Export-Jobs an mit:
 * - Progress-Bar mit Prozent-Anzeige
 * - Aktuelles Dokument
 * - Cancel/Pause/Resume Buttons
 * - Echtzeit-Updates via WebSocket (mit Polling-Fallback)
 *
 * Feinpoliert und durchdacht - Enterprise-ready Component.
 */

import { useCallback } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Download,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  StopCircle,
  Wifi,
  WifiOff,
  XCircle,
} from 'lucide-react';
import { useExportJob } from '../hooks/useExportJob';
import { type ExportJobStatus, type ExportJobStatusResponse } from '@/lib/api/services/exports';

interface ExportJobProgressProps {
  /** Job-ID zum Verfolgen */
  jobId: string;
  /** Callback wenn Job abgeschlossen */
  onComplete?: (status: ExportJobStatusResponse) => void;
  /** Callback wenn Job abgebrochen wird */
  onCancel?: () => void;
  /** Verstecke Action-Buttons */
  hideActions?: boolean;
  /** Kompakte Anzeige */
  compact?: boolean;
}

// Status-Badge Mapping
const statusBadgeConfig: Record<ExportJobStatus, {
  variant: 'default' | 'secondary' | 'destructive' | 'outline';
  label: string;
  icon: React.ReactNode;
}> = {
  queued: {
    variant: 'secondary',
    label: 'In Warteschlange',
    icon: <Clock className="h-3 w-3" />,
  },
  processing: {
    variant: 'default',
    label: 'Wird verarbeitet',
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
  completed: {
    variant: 'outline',
    label: 'Abgeschlossen',
    icon: <CheckCircle2 className="h-3 w-3 text-green-500" />,
  },
  failed: {
    variant: 'destructive',
    label: 'Fehlgeschlagen',
    icon: <XCircle className="h-3 w-3" />,
  },
  cancelled: {
    variant: 'secondary',
    label: 'Abgebrochen',
    icon: <StopCircle className="h-3 w-3" />,
  },
  paused: {
    variant: 'outline',
    label: 'Pausiert',
    icon: <Pause className="h-3 w-3" />,
  },
};

export function ExportJobProgress({
  jobId,
  onComplete,
  onCancel,
  hideActions = false,
  compact = false,
}: ExportJobProgressProps) {
  const {
    status,
    isLoading,
    error,
    isConnected,
    cancel,
    pause,
    resume,
    refresh,
  } = useExportJob({
    jobId,
    useWebSocket: true,
    pollingInterval: 2000,
    onComplete,
  });

  const handleCancel = useCallback(async () => {
    await cancel();
    if (onCancel) onCancel();
  }, [cancel, onCancel]);

  // Ladestand
  if (isLoading && !status) {
    return (
      <Card className={compact ? 'p-4' : ''}>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Wird geladen...</span>
        </CardContent>
      </Card>
    );
  }

  // Fehler
  if (error && !status) {
    return (
      <Card className={compact ? 'p-4' : ''}>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-4">
            <AlertCircle className="h-12 w-12 text-destructive" />
            <div className="text-center">
              <p className="font-medium text-destructive">Fehler beim Laden</p>
              <p className="text-sm text-muted-foreground">{error.message}</p>
            </div>
            <Button variant="outline" size="sm" onClick={refresh}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Erneut versuchen
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!status) return null;

  const badgeConfig = statusBadgeConfig[status.status];
  const isActive = status.status === 'processing' || status.status === 'paused';
  const isComplete = status.status === 'completed';
  const canDownload = isComplete && status.downloadUrl;

  if (compact) {
    return (
      <Card className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {badgeConfig.icon}
            <div>
              <p className="text-sm font-medium">{badgeConfig.label}</p>
              <p className="text-xs text-muted-foreground">
                {status.processedDocuments} / {status.totalDocuments} Dokumente
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Progress value={status.progress} className="w-32" />
            <span className="text-sm font-medium">{status.progress}%</span>
          </div>

          {!hideActions && isActive && (
            <div className="flex gap-1">
              {status.status === 'processing' && (
                <Button variant="ghost" size="icon" onClick={pause}>
                  <Pause className="h-4 w-4" />
                </Button>
              )}
              {status.status === 'paused' && (
                <Button variant="ghost" size="icon" onClick={resume}>
                  <Play className="h-4 w-4" />
                </Button>
              )}
              <Button variant="ghost" size="icon" onClick={handleCancel}>
                <XCircle className="h-4 w-4" />
              </Button>
            </div>
          )}

          {canDownload && (
            <Button asChild size="sm">
              <a href={status.downloadUrl!} download>
                <Download className="mr-2 h-4 w-4" />
                Herunterladen
              </a>
            </Button>
          )}
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              Export-Job
              <Badge variant={badgeConfig.variant} className="ml-2">
                {badgeConfig.icon}
                <span className="ml-1">{badgeConfig.label}</span>
              </Badge>
            </CardTitle>
            <CardDescription className="mt-1">
              Job-ID: {jobId}
            </CardDescription>
          </div>

          <div className="flex items-center gap-2">
            {isConnected ? (
              <Badge variant="outline" className="text-green-600">
                <Wifi className="mr-1 h-3 w-3" />
                Live
              </Badge>
            ) : (
              <Badge variant="outline" className="text-yellow-600">
                <WifiOff className="mr-1 h-3 w-3" />
                Polling
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Progress Section */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Fortschritt</span>
            <span className="font-medium">{status.progress}%</span>
          </div>
          <Progress value={status.progress} className="h-3" />
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {status.processedDocuments} von {status.totalDocuments} Dokumenten
            </span>
            {status.failedDocuments > 0 && (
              <span className="text-destructive">
                {status.failedDocuments} fehlgeschlagen
              </span>
            )}
          </div>
        </div>

        {/* Current Document */}
        {status.currentDocument && status.status === 'processing' && (
          <div className="rounded-lg bg-muted/50 p-3">
            <p className="text-xs text-muted-foreground">Aktuelles Dokument</p>
            <p className="truncate text-sm font-medium">{status.currentDocument}</p>
          </div>
        )}

        {/* Message */}
        {status.message && (
          <p className="text-sm text-muted-foreground">{status.message}</p>
        )}

        {/* Error State */}
        {status.status === 'failed' && (
          <div className="flex items-start gap-3 rounded-lg bg-destructive/10 p-4">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Export fehlgeschlagen</p>
              <p className="text-sm text-muted-foreground">
                {status.message || 'Ein unbekannter Fehler ist aufgetreten.'}
              </p>
            </div>
          </div>
        )}

        {/* Success State */}
        {isComplete && (
          <div className="flex items-start gap-3 rounded-lg bg-green-50 p-4 dark:bg-green-950/20">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            <div>
              <p className="font-medium text-green-700 dark:text-green-400">
                Export erfolgreich abgeschlossen
              </p>
              <p className="text-sm text-muted-foreground">
                {status.processedDocuments} Dokumente wurden exportiert.
              </p>
            </div>
          </div>
        )}

        {/* Actions */}
        {!hideActions && (
          <div className="flex justify-end gap-2 border-t pt-4">
            {isActive && (
              <>
                {status.status === 'processing' && (
                  <Button variant="outline" onClick={pause}>
                    <Pause className="mr-2 h-4 w-4" />
                    Pausieren
                  </Button>
                )}
                {status.status === 'paused' && (
                  <Button variant="outline" onClick={resume}>
                    <Play className="mr-2 h-4 w-4" />
                    Fortsetzen
                  </Button>
                )}
                <Button variant="destructive" onClick={handleCancel}>
                  <XCircle className="mr-2 h-4 w-4" />
                  Abbrechen
                </Button>
              </>
            )}

            {canDownload && (
              <Button asChild>
                <a href={status.downloadUrl!} download>
                  <Download className="mr-2 h-4 w-4" />
                  Herunterladen
                </a>
              </Button>
            )}

            <Button variant="ghost" size="icon" onClick={refresh}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Timestamps */}
        <div className="grid grid-cols-2 gap-4 border-t pt-4 text-xs text-muted-foreground">
          <div>
            <p className="font-medium">Erstellt</p>
            <p>{new Date(status.createdAt).toLocaleString('de-DE')}</p>
          </div>
          {status.startedAt && (
            <div>
              <p className="font-medium">Gestartet</p>
              <p>{new Date(status.startedAt).toLocaleString('de-DE')}</p>
            </div>
          )}
          {status.completedAt && (
            <div>
              <p className="font-medium">Abgeschlossen</p>
              <p>{new Date(status.completedAt).toLocaleString('de-DE')}</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
