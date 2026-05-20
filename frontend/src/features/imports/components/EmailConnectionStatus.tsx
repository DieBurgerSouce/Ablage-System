/**
 * EmailConnectionStatus Component
 *
 * Zeigt detaillierten Verbindungsstatus für eine Email-Konfiguration.
 * Ermöglicht Verbindungstest und zeigt Fehlermeldungen an.
 */

import { useState } from 'react';
import { formatDistanceToNow, format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  RefreshCw,
  Loader2,
  Mail,
  Server,
  Clock,
  FileText,
  AlertTriangle,
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
  useEmailConfig,
  useTestEmailConnection,
  useTriggerEmailSync,
} from '../hooks/use-import-queries';
import type { ConnectionStatus } from '../types/import-types';

// ==================== Types ====================

interface EmailConnectionStatusProps {
  configId: string;
  compact?: boolean;
  className?: string;
}

// ==================== Status Config ====================

const STATUS_CONFIG: Record<
  ConnectionStatus,
  {
    label: string;
    description: string;
    icon: typeof CheckCircle;
    color: string;
    bgColor: string;
    borderColor: string;
  }
> = {
  connected: {
    label: 'Verbunden',
    description: 'Verbindung zum IMAP-Server aktiv',
    icon: CheckCircle,
    color: 'text-green-600',
    bgColor: 'bg-green-50 dark:bg-green-950/30',
    borderColor: 'border-green-200 dark:border-green-800',
  },
  disconnected: {
    label: 'Getrennt',
    description: 'Keine aktive Verbindung',
    icon: XCircle,
    color: 'text-gray-600',
    bgColor: 'bg-gray-50 dark:bg-gray-950/30',
    borderColor: 'border-gray-200 dark:border-gray-700',
  },
  error: {
    label: 'Fehler',
    description: 'Verbindungsfehler aufgetreten',
    icon: AlertCircle,
    color: 'text-red-600',
    bgColor: 'bg-red-50 dark:bg-red-950/30',
    borderColor: 'border-red-200 dark:border-red-800',
  },
  unknown: {
    label: 'Unbekannt',
    description: 'Status noch nicht geprüft',
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
  const { data: config, isLoading } = useEmailConfig(configId);
  const testConnection = useTestEmailConnection();
  const { toast } = useToast();

  if (isLoading || !config) {
    return (
      <div className={cn('flex items-center gap-2', className)}>
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Lade...</span>
      </div>
    );
  }

  const status = STATUS_CONFIG[config.connectionStatus] || STATUS_CONFIG.unknown;
  const Icon = status.icon;

  const handleTest = async () => {
    try {
      const result = await testConnection.mutateAsync(configId);
      toast({
        title: result.success ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen',
        description: result.message,
        variant: result.success ? 'default' : 'destructive',
      });
    } catch (err) {
      toast({
        title: 'Fehler beim Verbindungstest',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

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
              onClick={handleTest}
              disabled={testConnection.isPending}
              className="h-7 w-7 p-0"
            >
              {testConnection.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>Verbindung testen</TooltipContent>
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
  const { data: config, isLoading, error, refetch } = useEmailConfig(configId);
  const testConnection = useTestEmailConnection();
  const triggerSync = useTriggerEmailSync();

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

  const status = STATUS_CONFIG[config.connectionStatus] || STATUS_CONFIG.unknown;
  const Icon = status.icon;

  const handleTest = async () => {
    try {
      const result = await testConnection.mutateAsync(configId);
      toast({
        title: result.success ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen',
        description: result.message,
        variant: result.success ? 'default' : 'destructive',
      });
    } catch (err) {
      toast({
        title: 'Fehler beim Verbindungstest',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleSync = async () => {
    try {
      await triggerSync.mutateAsync(configId);
      toast({
        title: 'Synchronisierung gestartet',
        description: `Email-Sync für "${config.name}" wurde gestartet.`,
      });
    } catch (err) {
      toast({
        title: 'Fehler beim Starten der Synchronisierung',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  // Calculate health percentage (simple heuristic)
  const healthScore = config.connectionStatus === 'connected'
    ? (config.errorCount === 0 ? 100 : Math.max(50, 100 - config.errorCount * 10))
    : config.connectionStatus === 'error'
    ? 25
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
          <Badge
            variant={config.isActive ? 'default' : 'secondary'}
            className={config.isActive ? 'bg-green-100 text-green-800' : ''}
          >
            {config.isActive ? 'Aktiv' : 'Inaktiv'}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        {/* Health Score */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Verbindungsqualität</span>
            <span className={cn('text-sm font-bold', status.color)}>{healthScore}%</span>
          </div>
          <Progress value={healthScore} className="h-2" />
        </div>

        {/* Connection Details */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Server</p>
              <p className="text-sm font-medium">{config.imapServer}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Ordner</p>
              <p className="text-sm font-medium">{config.imapFolder}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Letzte Synchronisierung</p>
              <p className="text-sm font-medium">
                {config.lastSyncAt
                  ? formatDistanceToNow(new Date(config.lastSyncAt), {
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
                {config.errorCount > 0 && (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                    {config.errorCount} Fehler insgesamt
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="flex-1"
            onClick={handleTest}
            disabled={testConnection.isPending}
          >
            {testConnection.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Verbindung testen
          </Button>

          <Button
            className="flex-1"
            onClick={handleSync}
            disabled={triggerSync.isPending || !config.isActive}
          >
            {triggerSync.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Mail className="mr-2 h-4 w-4" />
            )}
            Jetzt synchronisieren
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Main Component ====================

export function EmailConnectionStatus({
  configId,
  compact = false,
  className,
}: EmailConnectionStatusProps) {
  if (compact) {
    return <CompactStatus configId={configId} className={className} />;
  }

  return <FullStatusCard configId={configId} className={className} />;
}

export default EmailConnectionStatus;
