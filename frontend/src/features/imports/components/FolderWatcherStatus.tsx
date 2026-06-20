/**
 * FolderWatcherStatus Component
 *
 * Zeigt detaillierten Watcher-Status für eine Ordner-Konfiguration.
 * Ermöglicht Starten/Stoppen des Watchers und zeigt Statistiken an.
 */

import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  PlayCircle,
  StopCircle,
  AlertCircle,
  RefreshCw,
  Loader2,
  FolderOpen,
  Clock,
  FileText,
  AlertTriangle,
  Activity,
  HardDrive,
  Eye,
  EyeOff,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useToast } from '@/components/ui/use-toast';
import { cn } from '@/lib/utils';

import {
  useFolderConfig,
  useStartFolderWatcher,
  useStopFolderWatcher,
  useTriggerFolderPoll,
} from '../hooks/use-import-queries';
import type { WatcherStatus } from '../types/import-types';

// ==================== Types ====================

interface FolderWatcherStatusProps {
  configId: string;
  compact?: boolean;
  className?: string;
}

// ==================== Status Config ====================

const STATUS_CONFIG: Record<
  WatcherStatus,
  {
    label: string;
    description: string;
    icon: typeof PlayCircle;
    color: string;
    bgColor: string;
    borderColor: string;
  }
> = {
  running: {
    label: 'Aktiv',
    description: 'Watcher überwacht den Ordner',
    icon: PlayCircle,
    color: 'text-green-600',
    bgColor: 'bg-green-50 dark:bg-green-950/30',
    borderColor: 'border-green-200 dark:border-green-800',
  },
  stopped: {
    label: 'Gestoppt',
    description: 'Watcher ist deaktiviert',
    icon: StopCircle,
    color: 'text-gray-600',
    bgColor: 'bg-gray-50 dark:bg-gray-950/30',
    borderColor: 'border-gray-200 dark:border-gray-700',
  },
  error: {
    label: 'Fehler',
    description: 'Watcher-Fehler aufgetreten',
    icon: AlertCircle,
    color: 'text-red-600',
    bgColor: 'bg-red-50 dark:bg-red-950/30',
    borderColor: 'border-red-200 dark:border-red-800',
  },
  unknown: {
    label: 'Unbekannt',
    description: 'Status noch nicht ermittelt',
    icon: AlertTriangle,
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-50 dark:bg-yellow-950/30',
    borderColor: 'border-yellow-200 dark:border-yellow-800',
  },
};

// ==================== Compact Version ====================

function CompactStatus({
  configId,
  className,
}: {
  configId: string;
  className?: string;
}) {
  const { data: config, isLoading } = useFolderConfig(configId);
  const startWatcher = useStartFolderWatcher();
  const stopWatcher = useStopFolderWatcher();
  const { toast } = useToast();

  if (isLoading || !config) {
    return (
      <div className={cn('flex items-center gap-2', className)}>
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Lade...</span>
      </div>
    );
  }

  const status = STATUS_CONFIG[config.watcherStatus] || STATUS_CONFIG.unknown;
  const Icon = status.icon;
  const isRunning = config.watcherStatus === 'running';

  const handleToggle = async () => {
    try {
      if (isRunning) {
        await stopWatcher.mutateAsync(configId);
        toast({
          title: 'Watcher gestoppt',
          description: `Ordner-Überwachung für "${config.name}" wurde gestoppt.`,
        });
      } else {
        await startWatcher.mutateAsync(configId);
        toast({
          title: 'Watcher gestartet',
          description: `Ordner-Überwachung für "${config.name}" wurde gestartet.`,
        });
      }
    } catch (err) {
      toast({
        title: 'Fehler',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const isPending = startWatcher.isPending || stopWatcher.isPending;

  return (
    <TooltipProvider>
      <div className={cn('flex items-center gap-2', className)}>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className={cn('flex items-center gap-1.5 px-2 py-1 rounded-md', status.bgColor)}>
              <Icon className={cn('h-4 w-4', status.color)} />
              <span className={cn('text-sm font-medium', status.color)}>{status.label}</span>
            </div>
          </TooltipTrigger>
          <TooltipContent>
            <p>{status.description}</p>
            {config.lastError && (
              <p className="text-destructive mt-1">{config.lastError}</p>
            )}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleToggle}
              disabled={isPending || !config.isActive}
              className="h-7 w-7 p-0"
            >
              {isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : isRunning ? (
                <EyeOff className="h-3.5 w-3.5" />
              ) : (
                <Eye className="h-3.5 w-3.5" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{isRunning ? 'Watcher stoppen' : 'Watcher starten'}</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}

// ==================== Full Card Version ====================

function FullStatusCard({
  configId,
  className,
}: {
  configId: string;
  className?: string;
}) {
  const { toast } = useToast();
  const { data: config, isLoading, error, refetch } = useFolderConfig(configId);
  const startWatcher = useStartFolderWatcher();
  const stopWatcher = useStopFolderWatcher();
  const pollNow = useTriggerFolderPoll();

  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Lade Status...</span>
        </CardContent>
      </Card>
    );
  }

  if (error || !config) {
    return (
      <Card className={className}>
        <CardContent className="flex flex-col items-center justify-center py-8 text-destructive">
          <AlertCircle className="h-8 w-8 mb-2" />
          <p>Fehler beim Laden des Status</p>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  const status = STATUS_CONFIG[config.watcherStatus] || STATUS_CONFIG.unknown;
  const Icon = status.icon;
  const isRunning = config.watcherStatus === 'running';

  const handleToggle = async () => {
    try {
      if (isRunning) {
        await stopWatcher.mutateAsync(configId);
        toast({
          title: 'Watcher gestoppt',
          description: `Ordner-Überwachung für "${config.name}" wurde gestoppt.`,
        });
      } else {
        await startWatcher.mutateAsync(configId);
        toast({
          title: 'Watcher gestartet',
          description: `Ordner-Überwachung für "${config.name}" wurde gestartet.`,
        });
      }
    } catch (err) {
      toast({
        title: 'Fehler',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handlePoll = async () => {
    try {
      await pollNow.mutateAsync(configId);
      toast({
        title: 'Scan gestartet',
        description: 'Der Ordner wird jetzt nach neuen Dateien durchsucht.',
      });
    } catch (err) {
      toast({
        title: 'Fehler beim Scan',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const isPending = startWatcher.isPending || stopWatcher.isPending;

  // Calculate activity (files processed today as percentage of total, capped at 100)
  const activityScore = config.totalFilesProcessed > 0
    ? Math.min(100, (config.filesProcessedToday / Math.max(1, config.totalFilesProcessed / 30)) * 100)
    : 0;

  return (
    <Card className={cn(status.borderColor, 'border-2', className)}>
      <CardHeader className={cn(status.bgColor, 'rounded-t-lg')}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={cn('p-2 rounded-full', status.bgColor)}>
              <Icon className={cn('h-6 w-6', status.color)} />
            </div>
            <div>
              <CardTitle className="text-lg">{config.name}</CardTitle>
              <CardDescription>{status.description}</CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isRunning && (
              <Badge variant="outline" className="bg-green-100 text-green-800 animate-pulse">
                <Activity className="mr-1 h-3 w-3" />
                Live
              </Badge>
            )}
            <Badge
              variant={config.isActive ? 'default' : 'secondary'}
              className={config.isActive ? 'bg-green-100 text-green-800' : ''}
            >
              {config.isActive ? 'Aktiv' : 'Inaktiv'}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        {/* Activity Indicator */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Heutige Aktivität</span>
            <span className="text-sm text-muted-foreground">
              {config.filesProcessedToday} Dateien heute
            </span>
          </div>
          <Progress value={activityScore} className="h-2" />
        </div>

        {/* Folder Details */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted-foreground">Überwachter Pfad</p>
              <p className="text-sm font-medium truncate" title={config.watchPath}>
                {config.watchPath}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Netzwerkpfad</p>
              <p className="text-sm font-medium">
                {config.isNetworkPath ? 'Ja' : 'Nein'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Letzter Scan</p>
              <p className="text-sm font-medium">
                {config.lastPollAt
                  ? formatDistanceToNow(new Date(config.lastPollAt), {
                      addSuffix: true,
                      locale: de,
                    })
                  : 'Nie'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Dokumente erstellt</p>
              <p className="text-sm font-medium">
                {config.totalDocumentsCreated.toLocaleString('de-DE')}
              </p>
            </div>
          </div>
        </div>

        {/* Configuration Summary */}
        <div className="flex flex-wrap gap-2">
          {config.recursive && (
            <Badge variant="outline" className="text-xs">
              Rekursiv
            </Badge>
          )}
          {config.deleteAfterProcessing && (
            <Badge variant="outline" className="text-xs bg-yellow-50 text-yellow-800">
              Löscht Dateien
            </Badge>
          )}
          {config.moveAfterProcessing && (
            <Badge variant="outline" className="text-xs">
              Verschiebt nach: {config.processedSubfolder}
            </Badge>
          )}
          {config.autoOcr && (
            <Badge variant="outline" className="text-xs bg-blue-50 text-blue-800">
              Auto-OCR
            </Badge>
          )}
          <Badge variant="outline" className="text-xs">
            Intervall: {config.pollIntervalSeconds}s
          </Badge>
        </div>

        {/* File Patterns */}
        {config.includePatterns.length > 0 && (
          <div className="text-sm">
            <span className="text-muted-foreground">Dateimuster: </span>
            <span className="font-mono text-xs">
              {config.includePatterns.join(', ')}
            </span>
          </div>
        )}

        {/* Error Display */}
        {config.lastError && (
          <div className="p-3 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-red-800 dark:text-red-200">
                  Letzter Fehler
                </p>
                <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                  {config.lastError}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            variant={isRunning ? 'destructive' : 'default'}
            className="flex-1"
            onClick={handleToggle}
            disabled={isPending || !config.isActive}
          >
            {isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : isRunning ? (
              <StopCircle className="mr-2 h-4 w-4" />
            ) : (
              <PlayCircle className="mr-2 h-4 w-4" />
            )}
            {isRunning ? 'Watcher stoppen' : 'Watcher starten'}
          </Button>

          <Button
            variant="outline"
            className="flex-1"
            onClick={handlePoll}
            disabled={pollNow.isPending}
          >
            {pollNow.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Jetzt scannen
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Main Component ====================

export function FolderWatcherStatus({
  configId,
  compact = false,
  className,
}: FolderWatcherStatusProps) {
  if (compact) {
    return <CompactStatus configId={configId} className={className} />;
  }

  return <FullStatusCard configId={configId} className={className} />;
}

export default FolderWatcherStatus;
