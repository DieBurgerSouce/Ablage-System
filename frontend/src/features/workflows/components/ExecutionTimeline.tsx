/**
 * Execution Timeline
 *
 * Vertikale Zeitleiste der Workflow-Ausfuehrung.
 */

import { useState } from 'react';
import {
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useExecutionTimeline } from '../hooks/useWorkflowExecution';

interface ExecutionTimelineProps {
  executionId: string;
}

const statusIcons: Record<string, React.ElementType> = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle,
  failed: XCircle,
  paused: Clock,
  cancelled: XCircle,
  timeout: XCircle,
  warning: AlertTriangle,
};

const statusColors: Record<string, string> = {
  pending: 'text-muted-foreground',
  running: 'text-blue-500',
  completed: 'text-green-500',
  failed: 'text-red-500',
  paused: 'text-yellow-500',
  cancelled: 'text-gray-500',
  timeout: 'text-red-500',
  warning: 'text-yellow-500',
};

const statusLabels: Record<string, string> = {
  pending: 'Ausstehend',
  running: 'Läuft',
  completed: 'Abgeschlossen',
  failed: 'Fehlgeschlagen',
  paused: 'Pausiert',
  cancelled: 'Abgebrochen',
  timeout: 'Zeitüberschreitung',
  warning: 'Warnung',
};

function formatDuration(durationMs?: number | null): string {
  if (!durationMs) return '-';
  if (durationMs < 1000) return `${durationMs}ms`;
  if (durationMs < 60000) return `${(durationMs / 1000).toFixed(1)}s`;
  return `${(durationMs / 60000).toFixed(1)}min`;
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

interface TimelineItemProps {
  stepId: string;
  stepName: string;
  stepType: string;
  status: string;
  startedAt: string;
  completedAt?: string | null;
  durationMs?: number | null;
  inputSummary?: string | null;
  outputSummary?: string | null;
  errorMessage?: string | null;
  isActive?: boolean;
  isLast?: boolean;
}

function TimelineItem({
  stepName,
  stepType,
  status,
  startedAt,
  completedAt,
  durationMs,
  inputSummary,
  outputSummary,
  errorMessage,
  isActive = false,
  isLast = false,
}: TimelineItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const StatusIcon = statusIcons[status] || Clock;
  const statusColor = statusColors[status] || 'text-muted-foreground';
  const statusLabel = statusLabels[status] || status;

  const hasDetails = !!(inputSummary || outputSummary || errorMessage);

  return (
    <div className="relative flex gap-4">
      {/* Timeline Line */}
      {!isLast && (
        <div
          className={cn(
            'absolute left-5 top-8 w-0.5 h-full',
            isActive ? 'bg-blue-500' : 'bg-border'
          )}
        />
      )}

      {/* Status Icon */}
      <div
        className={cn(
          'relative z-10 flex h-10 w-10 items-center justify-center rounded-full border-2 bg-background',
          isActive ? 'border-blue-500' : 'border-border',
          isActive && 'shadow-lg shadow-blue-500/20'
        )}
      >
        <StatusIcon
          className={cn('h-5 w-5', statusColor, status === 'running' && 'animate-spin')}
        />
        {isActive && (
          <span className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-blue-500 animate-pulse" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 pb-8">
        <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h4 className="font-medium">{stepName}</h4>
                <Badge variant="outline" className="text-xs">
                  {stepType}
                </Badge>
                <Badge variant={status === 'completed' ? 'default' : 'secondary'}>
                  {statusLabel}
                </Badge>
              </div>
              <div className="mt-1 flex items-center gap-4 text-xs text-muted-foreground">
                <span>
                  <Clock className="mr-1 inline h-3 w-3" />
                  {formatTimestamp(startedAt)}
                </span>
                {durationMs && (
                  <span className="font-medium">{formatDuration(durationMs)}</span>
                )}
              </div>
              {completedAt && (
                <div className="mt-1 text-xs text-muted-foreground">
                  Abgeschlossen: {formatTimestamp(completedAt)}
                </div>
              )}
              {errorMessage && (
                <div className="mt-2 rounded-md bg-red-50 p-2 text-xs text-red-600">
                  <AlertTriangle className="mr-1 inline h-3 w-3" />
                  {errorMessage}
                </div>
              )}
            </div>
            {hasDetails && (
              <CollapsibleTrigger asChild>
                <button className="ml-2 text-muted-foreground hover:text-foreground">
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </button>
              </CollapsibleTrigger>
            )}
          </div>

          {hasDetails && (
            <CollapsibleContent className="mt-3 space-y-2">
              {inputSummary && (
                <div className="rounded-md bg-muted p-3 text-xs">
                  <p className="font-medium mb-1">Eingabe:</p>
                  <p className="text-muted-foreground">{inputSummary}</p>
                </div>
              )}
              {outputSummary && (
                <div className="rounded-md bg-muted p-3 text-xs">
                  <p className="font-medium mb-1">Ausgabe:</p>
                  <p className="text-muted-foreground">{outputSummary}</p>
                </div>
              )}
            </CollapsibleContent>
          )}
        </Collapsible>
      </div>
    </div>
  );
}

export default function ExecutionTimeline({ executionId }: ExecutionTimelineProps) {
  const { data: timeline, isLoading } = useExecutionTimeline(executionId);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Zeitleiste</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="flex gap-4">
              <Skeleton className="h-10 w-10 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-48" />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!timeline || timeline.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Zeitleiste</CardTitle>
        </CardHeader>
        <CardContent className="p-8 text-center text-muted-foreground">
          <Clock className="mx-auto h-12 w-12 mb-4" />
          <p>Keine Timeline-Eintraege vorhanden</p>
        </CardContent>
      </Card>
    );
  }

  // Finde aktiven Step (status = running)
  const activeStepIndex = timeline.findIndex((entry) => entry.status === 'running');

  return (
    <Card>
      <CardHeader>
        <CardTitle>Zeitleiste</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-0">
          {timeline.map((entry, index) => (
            <TimelineItem
              key={entry.step_id}
              stepId={entry.step_id}
              stepName={entry.step_name}
              stepType={entry.step_type}
              status={entry.status}
              startedAt={entry.started_at}
              completedAt={entry.completed_at}
              durationMs={entry.duration_ms}
              inputSummary={entry.input_summary}
              outputSummary={entry.output_summary}
              errorMessage={entry.error_message}
              isActive={index === activeStepIndex}
              isLast={index === timeline.length - 1}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
