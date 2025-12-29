/**
 * ExportJobList Component
 *
 * Zeigt eine Liste aller Export-Jobs des Benutzers:
 * - Tabelle mit Status, Fortschritt, Dokumente
 * - Filter nach Status
 * - Quick-Actions (Cancel, Download)
 * - Auto-Refresh alle 5 Sekunden
 *
 * Feinpoliert und durchdacht - Enterprise-ready Component.
 */

import { useState, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Download,
  FileArchive,
  FileJson,
  FileSpreadsheet,
  FileText,
  Loader2,
  RefreshCw,
  StopCircle,
  XCircle,
} from 'lucide-react';
import { useExportJobList } from '../hooks/useExportJob';
import {
  type ExportJobStatus,
  type ExportFormat,
  exportsService,
} from '@/lib/api/services/exports';

interface ExportJobListProps {
  /** Callback wenn Job angeklickt wird */
  onJobClick?: (jobId: string) => void;
  /** Auto-Refresh Intervall in ms (0 = deaktiviert) */
  refreshInterval?: number;
}

// Status-Badge Konfiguration
const statusConfig: Record<ExportJobStatus, {
  variant: 'default' | 'secondary' | 'destructive' | 'outline';
  label: string;
  icon: React.ReactNode;
}> = {
  queued: {
    variant: 'secondary',
    label: 'Warteschlange',
    icon: <Clock className="h-3 w-3" />,
  },
  processing: {
    variant: 'default',
    label: 'Verarbeitung',
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
    icon: <Clock className="h-3 w-3" />,
  },
};

// Format-Icon Mapping
const formatIcons: Record<ExportFormat, React.ReactNode> = {
  json: <FileJson className="h-4 w-4" />,
  csv: <FileSpreadsheet className="h-4 w-4" />,
  zip: <FileArchive className="h-4 w-4" />,
  pdf: <FileText className="h-4 w-4" />,
};

export function ExportJobList({
  onJobClick,
  refreshInterval = 5000,
}: ExportJobListProps) {
  const [statusFilter, setStatusFilter] = useState<ExportJobStatus | 'all'>('all');

  const { jobs, total, isLoading, error, refresh } = useExportJobList(
    statusFilter === 'all' ? undefined : statusFilter,
    refreshInterval
  );

  const handleCancel = useCallback(async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await exportsService.cancelJob(jobId);
      refresh();
    } catch (err) {
      console.error('Failed to cancel job:', err);
    }
  }, [refresh]);

  // Ladestand
  if (isLoading && jobs.length === 0) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Export-Jobs werden geladen...</span>
        </CardContent>
      </Card>
    );
  }

  // Fehler
  if (error && jobs.length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Export-Jobs</CardTitle>
            <CardDescription>
              {total} Export{total !== 1 ? 's' : ''} insgesamt
            </CardDescription>
          </div>

          <div className="flex items-center gap-2">
            <Select
              value={statusFilter}
              onValueChange={(value) => setStatusFilter(value as ExportJobStatus | 'all')}
            >
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Status filtern" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Status</SelectItem>
                <SelectItem value="queued">Warteschlange</SelectItem>
                <SelectItem value="processing">Verarbeitung</SelectItem>
                <SelectItem value="completed">Abgeschlossen</SelectItem>
                <SelectItem value="failed">Fehlgeschlagen</SelectItem>
                <SelectItem value="cancelled">Abgebrochen</SelectItem>
              </SelectContent>
            </Select>

            <Button variant="outline" size="icon" onClick={refresh}>
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FileArchive className="mb-4 h-12 w-12" />
            <p>Keine Export-Jobs vorhanden</p>
            {statusFilter !== 'all' && (
              <Button
                variant="link"
                size="sm"
                onClick={() => setStatusFilter('all')}
              >
                Alle Jobs anzeigen
              </Button>
            )}
          </div>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Format</TableHead>
                  <TableHead>Fortschritt</TableHead>
                  <TableHead>Dokumente</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => {
                  const config = statusConfig[job.status];
                  const isActive = job.status === 'processing' || job.status === 'paused';
                  const isComplete = job.status === 'completed';

                  return (
                    <TableRow
                      key={job.jobId}
                      className={onJobClick ? 'cursor-pointer hover:bg-muted/50' : ''}
                      onClick={() => onJobClick?.(job.jobId)}
                    >
                      <TableCell>
                        <Badge variant={config.variant} className="gap-1">
                          {config.icon}
                          {config.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {formatIcons[job.format]}
                          <span className="uppercase text-xs font-medium">
                            {job.format}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={job.progress} className="w-20" />
                          <span className="text-sm">{job.progress}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm">
                          {job.processedDocuments} / {job.totalDocuments}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {new Date(job.createdAt).toLocaleString('de-DE', {
                            day: '2-digit',
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          {isActive && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={(e) => handleCancel(job.jobId, e)}
                              title="Abbrechen"
                            >
                              <XCircle className="h-4 w-4" />
                            </Button>
                          )}
                          {isComplete && (
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Herunterladen"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
