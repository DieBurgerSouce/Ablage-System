/**
 * WorkflowExecutionHistory Component
 *
 * Zeigt Ausfuehrungs-Historie eines Workflows an.
 */

import { useState } from 'react';
import {
  Play,
  Pause,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  RefreshCw,
  Ban,
  Timer,
  ChevronDown,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  useWorkflowExecutions,
  useStepExecutions,
  usePauseExecution,
  useResumeExecution,
  useCancelExecution,
  useRetryExecution,
} from '../hooks/useWorkflows';
import type { ExecutionStatus, WorkflowExecution, StepExecution } from '../types/workflow-types';

const statusConfig: Record<
  ExecutionStatus,
  { icon: React.ElementType; label: string; color: string }
> = {
  pending: { icon: Clock, label: 'Ausstehend', color: 'text-gray-500' },
  running: { icon: RefreshCw, label: 'Laeuft', color: 'text-blue-500' },
  paused: { icon: Pause, label: 'Pausiert', color: 'text-yellow-500' },
  completed: { icon: CheckCircle, label: 'Abgeschlossen', color: 'text-green-500' },
  failed: { icon: XCircle, label: 'Fehlgeschlagen', color: 'text-red-500' },
  cancelled: { icon: Ban, label: 'Abgebrochen', color: 'text-gray-500' },
  timeout: { icon: Timer, label: 'Timeout', color: 'text-orange-500' },
};

interface ExecutionRowProps {
  execution: WorkflowExecution;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
}

function ExecutionRow({
  execution,
  onPause,
  onResume,
  onCancel,
  onRetry,
}: ExecutionRowProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { data: steps, isLoading: stepsLoading } = useStepExecutions(
    execution.id,
    isOpen
  );

  const statusInfo = statusConfig[execution.status] || statusConfig.pending;
  const StatusIcon = statusInfo.icon;

  const duration = execution.completed_at
    ? new Date(execution.completed_at).getTime() -
      new Date(execution.started_at).getTime()
    : null;

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}min`;
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <TableRow className={cn(isOpen && 'bg-muted/50')}>
        <TableCell>
          <CollapsibleTrigger className="flex items-center gap-2">
            {isOpen ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            <code className="text-xs">{execution.id.slice(0, 8)}...</code>
          </CollapsibleTrigger>
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <StatusIcon
              className={cn('h-4 w-4', statusInfo.color, {
                'animate-spin': execution.status === 'running',
              })}
            />
            <span>{statusInfo.label}</span>
          </div>
        </TableCell>
        <TableCell>
          <div className="w-32">
            <Progress value={execution.progress_percent} className="h-2" />
            <span className="text-xs text-muted-foreground">
              {execution.progress_percent}%
            </span>
          </div>
        </TableCell>
        <TableCell>
          {new Date(execution.started_at).toLocaleString('de-DE', {
            dateStyle: 'short',
            timeStyle: 'short',
          })}
        </TableCell>
        <TableCell>
          {duration ? formatDuration(duration) : '-'}
        </TableCell>
        <TableCell>
          {execution.document_id ? (
            <a
              href={`/documents/${execution.document_id}`}
              className="flex items-center gap-1 text-primary hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              Dokument
            </a>
          ) : (
            '-'
          )}
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-1">
            {execution.status === 'running' && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onPause(execution.id)}
                  title="Pausieren"
                >
                  <Pause className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onCancel(execution.id)}
                  title="Abbrechen"
                >
                  <Ban className="h-4 w-4" />
                </Button>
              </>
            )}
            {execution.status === 'paused' && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onResume(execution.id)}
                  title="Fortsetzen"
                >
                  <Play className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onCancel(execution.id)}
                  title="Abbrechen"
                >
                  <Ban className="h-4 w-4" />
                </Button>
              </>
            )}
            {(execution.status === 'failed' || execution.status === 'cancelled') && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => onRetry(execution.id)}
                title="Wiederholen"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            )}
          </div>
        </TableCell>
      </TableRow>

      <CollapsibleContent asChild>
        <TableRow className="bg-muted/30">
          <TableCell colSpan={7} className="p-4">
            {execution.error_message && (
              <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                <strong>Fehler:</strong> {execution.error_message}
              </div>
            )}

            <div className="text-sm font-medium mb-2">Schritt-Ausfuehrungen</div>

            {stepsLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : steps && steps.length > 0 ? (
              <div className="rounded border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Schritt</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Start</TableHead>
                      <TableHead>Ende</TableHead>
                      <TableHead>Fehler</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {steps.map((step: StepExecution) => {
                      const stepStatus = statusConfig[step.status] || statusConfig.pending;
                      const StepStatusIcon = stepStatus.icon;
                      return (
                        <TableRow key={step.id}>
                          <TableCell className="font-mono text-xs">
                            {step.step_id.slice(0, 8)}...
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1">
                              <StepStatusIcon
                                className={cn('h-3 w-3', stepStatus.color)}
                              />
                              <span className="text-xs">{stepStatus.label}</span>
                            </div>
                          </TableCell>
                          <TableCell className="text-xs">
                            {new Date(step.started_at).toLocaleTimeString('de-DE')}
                          </TableCell>
                          <TableCell className="text-xs">
                            {step.completed_at
                              ? new Date(step.completed_at).toLocaleTimeString('de-DE')
                              : '-'}
                          </TableCell>
                          <TableCell className="max-w-[200px] truncate text-xs text-red-500">
                            {step.error_message || '-'}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Keine Schritt-Ausfuehrungen verfuegbar.
              </p>
            )}

            {/* Variables Preview */}
            {Object.keys(execution.variables || {}).length > 0 && (
              <div className="mt-4">
                <div className="text-sm font-medium mb-2">Variablen</div>
                <pre className="rounded bg-muted p-2 text-xs overflow-auto max-h-32">
                  {JSON.stringify(execution.variables, null, 2)}
                </pre>
              </div>
            )}
          </TableCell>
        </TableRow>
      </CollapsibleContent>
    </Collapsible>
  );
}

interface WorkflowExecutionHistoryProps {
  workflowId: string;
}

export default function WorkflowExecutionHistory({
  workflowId,
}: WorkflowExecutionHistoryProps) {
  const [statusFilter, setStatusFilter] = useState<ExecutionStatus | 'all'>('all');

  const { data, isLoading, error, refetch } = useWorkflowExecutions(workflowId, {
    status: statusFilter !== 'all' ? statusFilter : undefined,
    limit: 50,
  });

  const pauseExecution = usePauseExecution();
  const resumeExecution = useResumeExecution();
  const cancelExecution = useCancelExecution();
  const retryExecution = useRetryExecution();

  const handlePause = async (id: string) => {
    await pauseExecution.mutateAsync(id);
    refetch();
  };

  const handleResume = async (id: string) => {
    await resumeExecution.mutateAsync(id);
    refetch();
  };

  const handleCancel = async (id: string) => {
    await cancelExecution.mutateAsync(id);
    refetch();
  };

  const handleRetry = async (id: string) => {
    await retryExecution.mutateAsync(id);
    refetch();
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
        <AlertTriangle className="inline-block mr-2 h-5 w-5" />
        Fehler beim Laden der Ausfuehrungen: {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium">Ausfuehrungs-Historie</h3>
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as ExecutionStatus | 'all')}
            className="rounded border px-3 py-1.5 text-sm"
          >
            <option value="all">Alle Status</option>
            <option value="pending">Ausstehend</option>
            <option value="running">Laeuft</option>
            <option value="paused">Pausiert</option>
            <option value="completed">Abgeschlossen</option>
            <option value="failed">Fehlgeschlagen</option>
            <option value="cancelled">Abgebrochen</option>
          </select>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Aktualisieren
          </Button>
        </div>
      </div>

      {!data?.items.length ? (
        <div className="rounded border p-8 text-center text-muted-foreground">
          <Clock className="mx-auto h-12 w-12 mb-4" />
          <p>Noch keine Ausfuehrungen vorhanden.</p>
          <p className="text-sm">
            Fuehre den Workflow aus, um die Historie zu sehen.
          </p>
        </div>
      ) : (
        <div className="rounded border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Fortschritt</TableHead>
                <TableHead>Gestartet</TableHead>
                <TableHead>Dauer</TableHead>
                <TableHead>Dokument</TableHead>
                <TableHead>Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((execution) => (
                <ExecutionRow
                  key={execution.id}
                  execution={execution}
                  onPause={handlePause}
                  onResume={handleResume}
                  onCancel={handleCancel}
                  onRetry={handleRetry}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {data && data.total > data.items.length && (
        <p className="text-center text-sm text-muted-foreground">
          {data.items.length} von {data.total} Ausfuehrungen angezeigt
        </p>
      )}
    </div>
  );
}
