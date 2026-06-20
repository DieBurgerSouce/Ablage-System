/**
 * Queue Status Tab
 *
 * Visualisierung aller Queues mit Details und Verwaltung.
 */

import { useState } from 'react';
import { AlertTriangle, BarChart3, CheckCircle2, ChevronRight, Gauge, Layers, ListOrdered, Loader2, RefreshCw, Trash2, XCircle, Zap } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';

import { useQueuesList, useQueueStats } from '../../hooks/use-jobs-query';
import { useClearQueue } from '../../hooks/use-job-mutations';
import { useJobPermissions } from '../../hooks/use-job-permissions';
import { QUEUE_PRIORITY_CONFIG } from '../../types/job-types';

// ==================== Queue Card Component ====================

interface QueueCardProps {
  queue: {
    name: string;
    length: number;
    processing: number;
    priority: number;
    description: string;
  };
  onClear?: () => void;
  canClear: boolean;
}

function QueueCard({ queue, onClear, canClear }: QueueCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { data: stats, isLoading } = useQueueStats(queue.name, { enabled: expanded });

  const priorityConfig = QUEUE_PRIORITY_CONFIG[queue.priority] || {
    label: 'Normal',
    color: 'default',
  };

  const getQueueHealth = () => {
    if (queue.length > 100) return 'critical';
    if (queue.length > 50) return 'warning';
    return 'healthy';
  };

  const health = getQueueHealth();

  return (
    <Card
      className={`transition-colors ${
        health === 'critical'
          ? 'border-red-500/50'
          : health === 'warning'
            ? 'border-yellow-500/50'
            : ''
      }`}
    >
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`p-2 rounded-lg ${
                  health === 'critical'
                    ? 'bg-red-100 dark:bg-red-950'
                    : health === 'warning'
                      ? 'bg-yellow-100 dark:bg-yellow-950'
                      : 'bg-muted'
                }`}
              >
                <ListOrdered
                  className={`h-5 w-5 ${
                    health === 'critical'
                      ? 'text-red-600'
                      : health === 'warning'
                        ? 'text-yellow-600'
                        : 'text-muted-foreground'
                  }`}
                />
              </div>
              <div>
                <CardTitle className="text-lg">{queue.name}</CardTitle>
                <CardDescription>{queue.description}</CardDescription>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {/* Stats */}
              <div className="text-right">
                <div className="text-2xl font-bold">{queue.length}</div>
                <div className="text-xs text-muted-foreground">in Warteschlange</div>
              </div>

              <div className="text-right">
                <div className="text-lg font-semibold text-blue-600">{queue.processing}</div>
                <div className="text-xs text-muted-foreground">aktiv</div>
              </div>

              {/* Priority Badge */}
              <Badge
                variant={
                  priorityConfig.color === 'destructive'
                    ? 'destructive'
                    : priorityConfig.color === 'warning'
                      ? 'default'
                      : 'secondary'
                }
              >
                {priorityConfig.label}
              </Badge>

              {/* Expand Toggle */}
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="icon">
                  <ChevronRight
                    className={`h-4 w-4 transition-transform ${expanded ? 'rotate-90' : ''}`}
                  />
                </Button>
              </CollapsibleTrigger>
            </div>
          </div>
        </CardHeader>

        <CollapsibleContent>
          <CardContent className="pt-0">
            <div className="border-t pt-4 mt-2">
              {isLoading ? (
                <div className="grid gap-4 md:grid-cols-4">
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </div>
              ) : stats ? (
                <div className="space-y-4">
                  {/* Stats Grid */}
                  <div className="grid gap-4 md:grid-cols-4">
                    <div className="p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                        <CheckCircle2 className="h-4 w-4" />
                        Letzte Stunde
                      </div>
                      <div className="text-xl font-semibold text-green-600">
                        {stats.completedLastHour}
                      </div>
                      <div className="text-xs text-muted-foreground">abgeschlossen</div>
                    </div>

                    <div className="p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                        <XCircle className="h-4 w-4" />
                        Letzte Stunde
                      </div>
                      <div className="text-xl font-semibold text-red-600">
                        {stats.failedLastHour}
                      </div>
                      <div className="text-xs text-muted-foreground">fehlgeschlagen</div>
                    </div>

                    <div className="p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                        <Gauge className="h-4 w-4" />
                        Durchsatz
                      </div>
                      <div className="text-xl font-semibold">
                        {stats.throughputPerMinute.toFixed(1)}
                      </div>
                      <div className="text-xs text-muted-foreground">Jobs/Minute</div>
                    </div>

                    <div className="p-3 bg-muted/50 rounded-lg">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                        <Zap className="h-4 w-4" />
                        Avg. Dauer
                      </div>
                      <div className="text-xl font-semibold">
                        {stats.avgProcessingTimeMs < 1000
                          ? `${stats.avgProcessingTimeMs.toFixed(0)}ms`
                          : `${(stats.avgProcessingTimeMs / 1000).toFixed(1)}s`}
                      </div>
                      <div className="text-xs text-muted-foreground">pro Job</div>
                    </div>
                  </div>

                  {/* Actions */}
                  {canClear && queue.length > 0 && (
                    <div className="flex justify-end">
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={onClear}
                        className="gap-2"
                      >
                        <Trash2 className="h-4 w-4" />
                        Queue leeren ({queue.length} Jobs)
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Keine detaillierten Statistiken verfügbar
                </p>
              )}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

// ==================== Main Component ====================

export function QueueStatusTab() {
  const [clearQueueName, setClearQueueName] = useState<string | null>(null);

  const permissions = useJobPermissions();
  const { data: queuesData, isLoading, refetch } = useQueuesList();
  const clearQueue = useClearQueue();

  const handleClearQueue = () => {
    if (!clearQueueName) return;
    clearQueue.mutate('pending', {
      onSuccess: () => {
        setClearQueueName(null);
      },
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Queue Übersicht</h2>
          <p className="text-sm text-muted-foreground">
            Status aller Warteschlangen im System
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Aktualisieren
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Layers className="h-4 w-4 text-muted-foreground" />
              Gesamt Wartend
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-3xl font-bold">{queuesData?.totalPending ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Zap className="h-4 w-4 text-blue-600" />
              Gesamt Aktiv
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-3xl font-bold text-blue-600">
                {queuesData?.totalProcessing ?? 0}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              Queues
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-3xl font-bold">{queuesData?.queues?.length ?? 0}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Queue Cards */}
      <div className="space-y-4">
        {isLoading ? (
          [...Array(3)].map((_, i) => (
            <Card key={i}>
              <CardHeader>
                <div className="flex items-center gap-3">
                  <Skeleton className="h-10 w-10 rounded-lg" />
                  <div className="space-y-2">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-4 w-48" />
                  </div>
                </div>
              </CardHeader>
            </Card>
          ))
        ) : queuesData?.queues && queuesData.queues.length > 0 ? (
          queuesData.queues
            .sort((a, b) => b.priority - a.priority) // Höchste Priorität zuerst
            .map((queue) => (
              <QueueCard
                key={queue.name}
                queue={queue}
                canClear={permissions.canClearQueue}
                onClear={() => setClearQueueName(queue.name)}
              />
            ))
        ) : (
          <Card>
            <CardContent className="py-12">
              <div className="flex flex-col items-center justify-center text-center">
                <ListOrdered className="h-12 w-12 text-muted-foreground/50 mb-2" />
                <p className="text-lg font-medium">Keine Queues gefunden</p>
                <p className="text-sm text-muted-foreground">
                  Es sind derzeit keine Warteschlangen konfiguriert.
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Health Indicator */}
      {queuesData && (queuesData.totalPending > 100 || queuesData.totalProcessing === 0) && (
        <Card
          className={`${
            queuesData.totalPending > 100
              ? 'border-yellow-500/50 bg-yellow-50/50 dark:bg-yellow-950/20'
              : 'border-blue-500/50 bg-blue-50/50 dark:bg-blue-950/20'
          }`}
        >
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              {queuesData.totalPending > 100 ? (
                <>
                  <AlertTriangle className="h-4 w-4 text-yellow-600" />
                  <span className="text-yellow-700 dark:text-yellow-500">Hohe Warteschlange</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4 text-blue-600" />
                  <span className="text-blue-700 dark:text-blue-500">System bereit</span>
                </>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {queuesData.totalPending > 100
                ? `Es befinden sich ${queuesData.totalPending} Jobs in der Warteschlange. Prüfe ob ausreichend Worker aktiv sind.`
                : 'Alle Queues sind im normalen Bereich. Das System arbeitet effizient.'}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Clear Queue Dialog */}
      <AlertDialog open={!!clearQueueName} onOpenChange={(open) => !open && setClearQueueName(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Queue leeren?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Sie sind dabei, alle wartenden Jobs aus der Queue "{clearQueueName}" zu entfernen.
              <br />
              <br />
              <strong className="text-destructive">
                Diese Aktion kann nicht rückgängig gemacht werden!
              </strong>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleClearQueue}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {clearQueue.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Queue leeren
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default QueueStatusTab;
