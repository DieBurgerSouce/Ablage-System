/**
 * Job Detail Modal
 *
 * Zeigt vollständige Job-Details mit Logs, Timeline und Aktionen.
 */

import { useMemo } from 'react';
import {
  AlertCircle,
  Ban,
  Calendar,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Server,
  Skull,
  User,
  XCircle,
  Zap,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';

import { useJob } from '../../hooks/use-jobs-query';
import {
  useCancelJob,
  useRetryJob,
  usePauseJob,
  useResumeJob,
  useForceKillJob,
} from '../../hooks/use-job-mutations';
import { useJobPermissions } from '../../hooks/use-job-permissions';
import { JOB_STATUS_CONFIG, JOB_TYPE_CONFIG, type JobStatus } from '../../types/job-types';

// ==================== Helper Functions ====================

function formatDateTime(dateString?: string): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)} Minuten`;
  return `${(ms / 3600000).toFixed(1)} Stunden`;
}

function getStatusIcon(status: JobStatus) {
  const icons = {
    pending: <Clock className="h-4 w-4" />,
    queued: <Clock className="h-4 w-4" />,
    processing: <Loader2 className="h-4 w-4 animate-spin" />,
    completed: <CheckCircle2 className="h-4 w-4" />,
    failed: <XCircle className="h-4 w-4" />,
    cancelled: <Ban className="h-4 w-4" />,
  };
  return icons[status] || <Clock className="h-4 w-4" />;
}

function getStatusVariant(status: JobStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  const variants: Record<JobStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
    pending: 'secondary',
    queued: 'secondary',
    processing: 'default',
    completed: 'outline',
    failed: 'destructive',
    cancelled: 'outline',
  };
  return variants[status] || 'default';
}

// ==================== Types ====================

interface JobDetailModalProps {
  jobId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ==================== Component ====================

export function JobDetailModal({ jobId, open, onOpenChange }: JobDetailModalProps) {
  const permissions = useJobPermissions();
  const { data: job, isLoading } = useJob(jobId || '', { enabled: !!jobId && open });

  // Mutations
  const cancelJob = useCancelJob();
  const retryJob = useRetryJob();
  const pauseJob = usePauseJob();
  const resumeJob = useResumeJob();
  const forceKillJob = useForceKillJob();

  // Computed
  const statusConfig = job ? JOB_STATUS_CONFIG[job.status] : null;
  const typeConfig = job ? JOB_TYPE_CONFIG[job.jobType] : null;

  const isActive = job?.status === 'processing' || job?.status === 'queued' || job?.status === 'pending';
  const isFailed = job?.status === 'failed';

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} kopiert`);
  };

  // Timeline berechnen
  const timeline = useMemo(() => {
    if (!job) return [];

    const events = [];

    events.push({
      label: 'Erstellt',
      time: job.createdAt,
      icon: <Calendar className="h-4 w-4" />,
    });

    if (job.startedAt) {
      events.push({
        label: 'Gestartet',
        time: job.startedAt,
        icon: <Zap className="h-4 w-4 text-blue-600" />,
      });
    }

    if (job.completedAt) {
      events.push({
        label: job.status === 'completed' ? 'Abgeschlossen' : 'Beendet',
        time: job.completedAt,
        icon:
          job.status === 'completed' ? (
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          ) : job.status === 'failed' ? (
            <XCircle className="h-4 w-4 text-red-600" />
          ) : (
            <Ban className="h-4 w-4 text-muted-foreground" />
          ),
      });
    }

    return events;
  }, [job]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isLoading ? (
              <Skeleton className="h-6 w-48" />
            ) : (
              <>
                <FileText className="h-5 w-5" />
                Job Details
                {job && (
                  <Badge variant={getStatusVariant(job.status)} className="ml-2 gap-1">
                    {getStatusIcon(job.status)}
                    {statusConfig?.label ?? job.status}
                  </Badge>
                )}
              </>
            )}
          </DialogTitle>
          <DialogDescription>
            {isLoading ? (
              <Skeleton className="h-4 w-64" />
            ) : job ? (
              <span className="font-mono text-xs">{job.id}</span>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : job ? (
          <div className="space-y-6">
            {/* Progress (wenn aktiv) */}
            {isActive && job.progress !== undefined && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">Fortschritt</span>
                  <span>{job.progress.toFixed(0)}%</span>
                </div>
                <Progress value={job.progress} className="h-3" />
                {job.message && (
                  <p className="text-sm text-muted-foreground">{job.message}</p>
                )}
              </div>
            )}

            {/* Übersicht */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{typeConfig?.label ?? job.jobType}</Badge>
                  {job.backend && <Badge variant="secondary">{job.backend}</Badge>}
                </div>

                {job.documentFilename && (
                  <div className="flex items-start gap-2">
                    <FileText className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <div className="text-sm font-medium">Dokument</div>
                      <div className="text-sm text-muted-foreground">{job.documentFilename}</div>
                    </div>
                  </div>
                )}

                {job.userEmail && (
                  <div className="flex items-start gap-2">
                    <User className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <div className="text-sm font-medium">Benutzer</div>
                      <div className="text-sm text-muted-foreground">{job.userEmail}</div>
                    </div>
                  </div>
                )}

                {job.workerId && (
                  <div className="flex items-start gap-2">
                    <Server className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <div className="text-sm font-medium">Worker</div>
                      <div className="text-sm text-muted-foreground font-mono text-xs">
                        {job.workerId}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Priorität</span>
                  <Badge variant={job.priority >= 8 ? 'destructive' : 'secondary'}>
                    {job.priority}
                  </Badge>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Versuche</span>
                  <span className="text-sm">
                    {job.retryCount} / {job.maxRetries}
                  </span>
                </div>

                {job.durationMs && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Dauer</span>
                    <span className="text-sm">{formatDuration(job.durationMs)}</span>
                  </div>
                )}

                {job.waitTimeMs && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Wartezeit</span>
                    <span className="text-sm">{formatDuration(job.waitTimeMs)}</span>
                  </div>
                )}
              </div>
            </div>

            <Separator />

            {/* Timeline */}
            <div>
              <h4 className="text-sm font-medium mb-3">Zeitverlauf</h4>
              <div className="space-y-3">
                {timeline.map((event, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
                      {event.icon}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-medium">{event.label}</div>
                      <div className="text-xs text-muted-foreground">
                        {formatDateTime(event.time)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Fehler Details */}
            {job.errorMessage && (
              <Accordion type="single" collapsible defaultValue="error">
                <AccordionItem value="error" className="border-red-200 dark:border-red-900">
                  <AccordionTrigger className="text-red-600 hover:text-red-700">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4" />
                      Fehler Details
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="bg-red-50 dark:bg-red-950/50 p-3 rounded-lg">
                      <pre className="text-sm text-red-700 dark:text-red-400 whitespace-pre-wrap font-mono">
                        {job.errorMessage}
                      </pre>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-2 text-xs"
                      onClick={() => copyToClipboard(job.errorMessage!, 'Fehler')}
                    >
                      <Copy className="h-3 w-3 mr-1" />
                      Kopieren
                    </Button>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            )}

            {/* Result Details */}
            {job.result && Object.keys(job.result).length > 0 && (
              <Accordion type="single" collapsible>
                <AccordionItem value="result">
                  <AccordionTrigger>
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4" />
                      Ergebnis Details
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="bg-muted p-3 rounded-lg">
                      <pre className="text-sm whitespace-pre-wrap font-mono">
                        {JSON.stringify(job.result, null, 2)}
                      </pre>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            )}

            {/* IDs zum Kopieren */}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => copyToClipboard(job.id, 'Job-ID')}
              >
                <Copy className="h-3 w-3 mr-1" />
                Job-ID kopieren
              </Button>
              {job.documentId && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => copyToClipboard(job.documentId!, 'Dokument-ID')}
                >
                  <Copy className="h-3 w-3 mr-1" />
                  Dokument-ID kopieren
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="py-8 text-center">
            <AlertCircle className="h-12 w-12 text-muted-foreground/50 mx-auto mb-2" />
            <p className="text-muted-foreground">Job nicht gefunden</p>
          </div>
        )}

        {/* Actions */}
        {job && (
          <DialogFooter className="gap-2 sm:gap-0">
            {/* Active job actions */}
            {isActive && permissions.canManage && (
              <>
                <Button
                  variant="destructive"
                  onClick={() => {
                    cancelJob.mutate({ jobId: job.id });
                    onOpenChange(false);
                  }}
                  disabled={cancelJob.isPending}
                >
                  {cancelJob.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <XCircle className="h-4 w-4 mr-2" />
                  )}
                  Abbrechen
                </Button>

                {permissions.canPauseResume && job.status === 'processing' && !job.isPaused && (
                  <Button
                    variant="outline"
                    onClick={() => pauseJob.mutate(job.id)}
                    disabled={pauseJob.isPending}
                  >
                    <Pause className="h-4 w-4 mr-2" />
                    Pausieren
                  </Button>
                )}

                {permissions.canPauseResume && job.isPaused && (
                  <Button
                    variant="outline"
                    onClick={() => resumeJob.mutate(job.id)}
                    disabled={resumeJob.isPending}
                  >
                    <Play className="h-4 w-4 mr-2" />
                    Fortsetzen
                  </Button>
                )}

                {permissions.canForceKill && job.status === 'processing' && (
                  <Button
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => {
                      forceKillJob.mutate(job.id);
                      onOpenChange(false);
                    }}
                    disabled={forceKillJob.isPending}
                  >
                    <Skull className="h-4 w-4 mr-2" />
                    Force Kill
                  </Button>
                )}
              </>
            )}

            {/* Failed job actions */}
            {isFailed && permissions.canManage && (
              <Button
                onClick={() => {
                  retryJob.mutate({ jobId: job.id });
                  onOpenChange(false);
                }}
                disabled={retryJob.isPending}
              >
                {retryJob.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4 mr-2" />
                )}
                Wiederholen
              </Button>
            )}

            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Schließen
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default JobDetailModal;
