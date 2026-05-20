/**
 * Widget Sync Status
 *
 * Shows the sync status of dashboard widget configuration.
 * Displays last sync time and sync button.
 */

import { Cloud, CloudOff, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface WidgetSyncStatusProps {
  isLoading?: boolean;
  isSyncing?: boolean;
  lastSynced?: Date | null;
  error?: Error | null;
  onSync?: () => void;
  className?: string;
}

function formatLastSynced(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) {
    return 'Gerade eben';
  } else if (diffMinutes < 60) {
    return `Vor ${diffMinutes} Min.`;
  } else if (diffHours < 24) {
    return `Vor ${diffHours} Std.`;
  } else if (diffDays === 1) {
    return 'Gestern';
  } else if (diffDays < 7) {
    return `Vor ${diffDays} Tagen`;
  } else {
    return date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
    });
  }
}

export function WidgetSyncStatus({
  isLoading,
  isSyncing,
  lastSynced,
  error,
  onSync,
  className,
}: WidgetSyncStatusProps) {
  const getStatusIcon = () => {
    if (isLoading || isSyncing) {
      return <Loader2 className="h-4 w-4 animate-spin" />;
    }
    if (error) {
      return <CloudOff className="h-4 w-4 text-destructive" />;
    }
    return <Cloud className="h-4 w-4 text-muted-foreground" />;
  };

  const getStatusText = () => {
    if (isLoading) {
      return 'Lade...';
    }
    if (isSyncing) {
      return 'Synchronisiere...';
    }
    if (error) {
      return 'Sync fehlgeschlagen';
    }
    if (lastSynced) {
      return `Zuletzt: ${formatLastSynced(lastSynced)}`;
    }
    return 'Nicht synchronisiert';
  };

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {getStatusIcon()}
            <span className="hidden sm:inline">{getStatusText()}</span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <p className="text-xs">
            {error
              ? 'Dashboard-Konfiguration konnte nicht synchronisiert werden'
              : 'Dashboard-Konfiguration wird automatisch gespeichert'}
          </p>
          {lastSynced && (
            <p className="text-xs text-muted-foreground mt-1">
              Letzte Synchronisierung:{' '}
              {lastSynced.toLocaleString('de-DE', {
                dateStyle: 'short',
                timeStyle: 'short',
              })}
            </p>
          )}
        </TooltipContent>
      </Tooltip>

      {onSync && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={onSync}
              disabled={isLoading || isSyncing}
            >
              <RefreshCw
                className={cn(
                  'h-3.5 w-3.5',
                  isSyncing && 'animate-spin'
                )}
              />
              <span className="sr-only">Jetzt synchronisieren</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="text-xs">Jetzt synchronisieren</p>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}
