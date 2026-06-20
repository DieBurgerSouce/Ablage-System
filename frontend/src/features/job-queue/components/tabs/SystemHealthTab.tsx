/**
 * System Health Tab
 *
 * Worker-Status, GPU-Monitoring, DLQ-Management.
 */

import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Flame, Loader2, Lock, MoreHorizontal, RefreshCw, RotateCcw, Server, Skull, Trash2, Unlock, XCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

import { useWorkersList, useWorkersHealth, useDLQStats, useDLQTasks } from '../../hooks/use-jobs-query';
import { useRetryDLQTask, usePurgeDLQ } from '../../hooks/use-job-mutations';
import { useJobPermissions } from '../../hooks/use-job-permissions';
import { QueueClearDialog } from '../modals/QueueClearDialog';

// ==================== Helper Functions ====================

function formatRelativeTime(dateString?: string): string {
  if (!dateString) return 'Nie';
  const date = new Date(dateString);
  const now = new Date();
  const diffSecs = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffSecs < 60) return `vor ${diffSecs}s`;
  if (diffSecs < 3600) return `vor ${Math.floor(diffSecs / 60)}min`;
  if (diffSecs < 86400) return `vor ${Math.floor(diffSecs / 3600)}h`;
  return date.toLocaleDateString('de-DE');
}

function getWorkerStatusIcon(status: string) {
  switch (status) {
    case 'online':
      return <CheckCircle2 className="h-4 w-4 text-green-600" />;
    case 'busy':
      return <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />;
    case 'offline':
      return <XCircle className="h-4 w-4 text-red-600" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function getWorkerStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'online':
      return 'outline';
    case 'busy':
      return 'default';
    case 'offline':
      return 'destructive';
    default:
      return 'secondary';
  }
}

// ==================== Main Component ====================

export function SystemHealthTab() {
  const [purgeDLQOpen, setPurgeDLQOpen] = useState(false);

  const permissions = useJobPermissions();

  // Queries
  const { data: workers, isLoading: workersLoading, refetch: refetchWorkers } = useWorkersList();
  const { data: workersHealth } = useWorkersHealth();
  const { data: dlqStats, isLoading: dlqStatsLoading, refetch: refetchDLQ } = useDLQStats();
  const { data: dlqTasks, isLoading: dlqTasksLoading } = useDLQTasks({ perPage: 10 });

  // Mutations
  const retryDLQTask = useRetryDLQTask();
  const purgeDLQ = usePurgeDLQ();

  const handlePurgeDLQ = async (): Promise<void> => {
    return new Promise((resolve, reject) => {
      purgeDLQ.mutate(undefined, {
        onSuccess: () => {
          resolve();
        },
        onError: (error) => {
          reject(error);
        },
      });
    });
  };

  const gpu = workers?.gpu;
  const gpuMemoryPercent = gpu?.memoryPercent ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">System Gesundheit</h2>
          <p className="text-sm text-muted-foreground">
            Worker, GPU und Dead Letter Queue Status
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            refetchWorkers();
            refetchDLQ();
          }}
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Aktualisieren
        </Button>
      </div>

      {/* Worker & GPU Overview */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Workers Summary */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Server className="h-4 w-4 text-muted-foreground" />
              Worker Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            {workersLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-green-600">
                    {workers?.onlineWorkers ?? 0}
                  </span>
                  <span className="text-lg text-muted-foreground">
                    / {workers?.totalWorkers ?? 0}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {workers?.busyWorkers ?? 0} beschäftigt
                </p>
              </>
            )}
          </CardContent>
        </Card>

        {/* GPU Status */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Flame className="h-4 w-4 text-orange-600" />
              GPU VRAM
            </CardTitle>
          </CardHeader>
          <CardContent>
            {workersLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : gpu?.available ? (
              <>
                <div className="flex items-baseline gap-2">
                  <span
                    className={`text-3xl font-bold ${
                      gpuMemoryPercent >= 85
                        ? 'text-red-600'
                        : gpuMemoryPercent >= 70
                          ? 'text-yellow-600'
                          : 'text-green-600'
                    }`}
                  >
                    {gpuMemoryPercent.toFixed(0)}%
                  </span>
                </div>
                <Progress
                  value={gpuMemoryPercent}
                  className={`h-2 mt-2 ${
                    gpuMemoryPercent >= 85
                      ? '[&>div]:bg-red-600'
                      : gpuMemoryPercent >= 70
                        ? '[&>div]:bg-yellow-600'
                        : ''
                  }`}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  {gpu.memoryUsedMb?.toFixed(0) ?? 0} / {gpu.memoryTotalMb?.toFixed(0) ?? 0} MB
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Nicht verfügbar</p>
            )}
          </CardContent>
        </Card>

        {/* GPU Lock */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              {gpu?.lockHeld ? (
                <Lock className="h-4 w-4 text-yellow-600" />
              ) : (
                <Unlock className="h-4 w-4 text-green-600" />
              )}
              GPU Lock
            </CardTitle>
          </CardHeader>
          <CardContent>
            {workersLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <Badge variant={gpu?.lockHeld ? 'default' : 'outline'}>
                  {gpu?.lockHeld ? 'Gesperrt' : 'Frei'}
                </Badge>
                {gpu?.lockHolder && (
                  <p className="text-xs text-muted-foreground mt-2">
                    Gehalten von: {gpu.lockHolder}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* DLQ Status */}
        <Card
          className={
            (dlqStats?.totalTasks ?? 0) > 0
              ? 'border-yellow-500/50'
              : ''
          }
        >
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Skull className="h-4 w-4 text-red-600" />
              Dead Letter Queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            {dlqStatsLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="flex items-baseline gap-2">
                  <span
                    className={`text-3xl font-bold ${
                      (dlqStats?.totalTasks ?? 0) > 0 ? 'text-yellow-600' : 'text-green-600'
                    }`}
                  >
                    {dlqStats?.totalTasks ?? 0}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {dlqStats?.poisonPills ?? 0} Poison Pills
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Worker Details */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Worker Details</CardTitle>
          <CardDescription>Status aller registrierten Worker</CardDescription>
        </CardHeader>
        <CardContent>
          {workersLoading ? (
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : workers?.workers && workers.workers.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Worker</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Aktuelle Task</TableHead>
                  <TableHead>Verarbeitet</TableHead>
                  <TableHead>Pool</TableHead>
                  <TableHead>Letzte Aktivität</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {workers.workers.map((worker) => (
                  <TableRow key={worker.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{worker.hostname}</div>
                        <div className="text-xs text-muted-foreground">{worker.id}</div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={getWorkerStatusVariant(worker.status)}
                        className="gap-1"
                      >
                        {getWorkerStatusIcon(worker.status)}
                        {worker.status === 'online'
                          ? 'Online'
                          : worker.status === 'busy'
                            ? 'Beschäftigt'
                            : 'Offline'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {worker.currentTask ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-sm truncate max-w-[150px] block cursor-help">
                              {worker.currentTask}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            <div>
                              <strong>Task:</strong> {worker.currentTask}
                              <br />
                              <strong>ID:</strong> {worker.currentTaskId}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        <span className="text-sm text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">{worker.tasksProcessed}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">
                        {worker.activeTasks} / {worker.poolSize}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground">
                        {formatRelativeTime(worker.lastHeartbeat)}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Server className="h-12 w-12 text-muted-foreground/50 mb-2" />
              <p className="text-lg font-medium">Keine Worker gefunden</p>
              <p className="text-sm text-muted-foreground">
                Starte Worker mit: celery -A app.workers.celery_app worker
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* GPU Details */}
      {gpu?.available && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">GPU Details</CardTitle>
            <CardDescription>{gpu.name || 'NVIDIA GPU'}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-4">
              <div>
                <div className="text-sm text-muted-foreground">VRAM Nutzung</div>
                <div className="text-xl font-semibold">
                  {gpu.memoryUsedMb?.toFixed(0) ?? 0} MB
                </div>
                <Progress value={gpuMemoryPercent} className="h-2 mt-2" />
              </div>

              <div>
                <div className="text-sm text-muted-foreground">VRAM Gesamt</div>
                <div className="text-xl font-semibold">
                  {gpu.memoryTotalMb?.toFixed(0) ?? 0} MB
                </div>
              </div>

              <div>
                <div className="text-sm text-muted-foreground">Auslastung</div>
                <div className="text-xl font-semibold">
                  {gpu.utilizationPercent?.toFixed(0) ?? 0}%
                </div>
              </div>

              {gpu.temperatureCelsius !== undefined && (
                <div>
                  <div className="text-sm text-muted-foreground">Temperatur</div>
                  <div
                    className={`text-xl font-semibold ${
                      gpu.temperatureCelsius >= 80
                        ? 'text-red-600'
                        : gpu.temperatureCelsius >= 70
                          ? 'text-yellow-600'
                          : ''
                    }`}
                  >
                    {gpu.temperatureCelsius}°C
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* DLQ Tasks */}
      {permissions.canManageDLQ && (
        <Card className={(dlqStats?.totalTasks ?? 0) > 0 ? 'border-yellow-500/50' : ''}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-sm font-medium">Dead Letter Queue</CardTitle>
                <CardDescription>
                  Fehlgeschlagene Tasks die manuelle Aufmerksamkeit erfordern
                </CardDescription>
              </div>
              {permissions.canPurgeDLQ && (dlqStats?.totalTasks ?? 0) > 0 && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setPurgeDLQOpen(true)}
                  className="gap-2"
                >
                  <Trash2 className="h-4 w-4" />
                  DLQ leeren
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {dlqTasksLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : dlqTasks?.tasks && dlqTasks.tasks.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Task</TableHead>
                    <TableHead>Fehler</TableHead>
                    <TableHead>Versuche</TableHead>
                    <TableHead>Fehlgeschlagen</TableHead>
                    <TableHead className="w-[50px]"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dlqTasks.tasks.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell>
                        <div>
                          <div className="font-medium flex items-center gap-2">
                            {task.name}
                            {task.isPoisonPill && (
                              <Badge variant="destructive" className="gap-1">
                                <Skull className="h-3 w-3" />
                                Poison
                              </Badge>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground">{task.id}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div className="max-w-[200px]">
                              <Badge variant="outline" className="mb-1">
                                {task.exceptionType}
                              </Badge>
                              <p className="text-xs text-muted-foreground truncate">
                                {task.exceptionMessage}
                              </p>
                            </div>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-[400px]">
                            <pre className="text-xs whitespace-pre-wrap">
                              {task.traceback || task.exceptionMessage}
                            </pre>
                          </TooltipContent>
                        </Tooltip>
                      </TableCell>
                      <TableCell>
                        <Badge variant={task.retries >= 3 ? 'destructive' : 'secondary'}>
                          {task.retries}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {formatRelativeTime(task.failedAt)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Aktionen</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => retryDLQTask.mutate(task.id)}
                              disabled={retryDLQTask.isPending}
                            >
                              <RotateCcw className="h-4 w-4 mr-2" />
                              Wiederholen
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <CheckCircle2 className="h-12 w-12 text-green-600/50 mb-2" />
                <p className="text-lg font-medium text-green-700 dark:text-green-500">
                  DLQ ist leer
                </p>
                <p className="text-sm text-muted-foreground">
                  Keine fehlgeschlagenen Tasks erfordern Aufmerksamkeit
                </p>
              </div>
            )}

            {dlqTasks && dlqTasks.total > 10 && (
              <div className="mt-4 text-sm text-muted-foreground text-center">
                Zeige 10 von {dlqTasks.total} Tasks
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Warnings from Health Check */}
      {workersHealth && (workersHealth.warnings?.length > 0 || workersHealth.errors?.length > 0) && (
        <Card className="border-yellow-500/50 bg-yellow-50/50 dark:bg-yellow-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-yellow-700 dark:text-yellow-500">
              <AlertTriangle className="h-4 w-4" />
              System Warnungen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {workersHealth.errors?.map((error, i) => (
                <li key={`error-${i}`} className="flex items-start gap-2 text-sm text-red-600">
                  <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
                  {error}
                </li>
              ))}
              {workersHealth.warnings?.map((warning, i) => (
                <li key={`warning-${i}`} className="flex items-start gap-2 text-sm text-yellow-700 dark:text-yellow-500">
                  <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                  {warning}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Purge DLQ Dialog - Enterprise Security with LÖSCHEN confirmation */}
      <QueueClearDialog
        open={purgeDLQOpen}
        onOpenChange={setPurgeDLQOpen}
        type="dlq"
        itemCount={dlqStats?.totalTasks ?? 0}
        onConfirm={handlePurgeDLQ}
        isLoading={purgeDLQ.isPending}
      />
    </div>
  );
}

export default SystemHealthTab;
