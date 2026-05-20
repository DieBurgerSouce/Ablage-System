/**
 * WebSocketStatusIndicator - Collaboration WebSocket Verbindungsstatus
 *
 * Kompakter Indikator für den Collaboration-WebSocket:
 * - Grün = Verbunden
 * - Gelb + Spinner = Verbindung wird hergestellt...
 * - Rot = Getrennt (mit Reconnect-Button)
 * - Tooltip mit Verbindungsdetails
 *
 * Hinweis: Dies ist die Collaboration-spezifische Variante.
 * Die globale Variante liegt in components/layout/WebSocketStatusIndicator.tsx
 */

import { memo } from 'react';
import { Wifi, WifiOff, Loader2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Button } from '@/components/ui/button';
import type { ConnectionStatus } from '../hooks/use-realtime';

// ==================== Status Config ====================

const STATUS_CONFIG: Record<
  ConnectionStatus,
  {
    icon: typeof Wifi;
    label: string;
    description: string;
    dotColor: string;
    iconColor: string;
    animate?: boolean;
  }
> = {
  connected: {
    icon: Wifi,
    label: 'Verbunden',
    description: 'Echtzeit-Collaboration aktiv',
    dotColor: 'bg-green-500',
    iconColor: 'text-green-600 dark:text-green-400',
  },
  connecting: {
    icon: Loader2,
    label: 'Verbindung wird hergestellt...',
    description: 'WebSocket-Verbindung wird aufgebaut',
    dotColor: 'bg-amber-500',
    iconColor: 'text-amber-600 dark:text-amber-400',
    animate: true,
  },
  disconnected: {
    icon: WifiOff,
    label: 'Getrennt',
    description: 'Keine Echtzeit-Verbindung',
    dotColor: 'bg-red-500',
    iconColor: 'text-red-600 dark:text-red-400',
  },
  error: {
    icon: WifiOff,
    label: 'Verbindungsfehler',
    description: 'Verbindung konnte nicht hergestellt werden',
    dotColor: 'bg-red-500',
    iconColor: 'text-red-600 dark:text-red-400',
  },
};

// ==================== Component ====================

interface CollabWebSocketStatusIndicatorProps {
  status: ConnectionStatus;
  onReconnect?: () => void;
  compact?: boolean;
  className?: string;
}

export const CollabWebSocketStatusIndicator = memo(function CollabWebSocketStatusIndicator({
  status,
  onReconnect,
  compact = false,
  className,
}: CollabWebSocketStatusIndicatorProps) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;
  const showReconnect = (status === 'disconnected' || status === 'error') && onReconnect;

  if (compact) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className={cn('flex items-center gap-1.5', className)}
              role="status"
              aria-label={`Collaboration: ${config.label}`}
            >
              <span
                className={cn(
                  'w-2 h-2 rounded-full',
                  config.dotColor,
                  config.animate && 'animate-pulse',
                )}
                aria-hidden="true"
              />
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p className="font-medium text-sm">{config.label}</p>
            <p className="text-xs text-muted-foreground">{config.description}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'flex items-center gap-1.5 px-2 py-1 rounded-md',
              'hover:bg-accent/50 transition-colors cursor-default',
              className,
            )}
            role="status"
            aria-label={`Collaboration: ${config.label}`}
          >
            <span
              className={cn(
                'w-2 h-2 rounded-full',
                config.dotColor,
                config.animate && 'animate-pulse',
              )}
              aria-hidden="true"
            />
            <Icon
              className={cn(
                'h-3.5 w-3.5',
                config.iconColor,
                config.animate && 'animate-spin',
              )}
              aria-hidden="true"
            />
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" align="end">
          <div className="text-sm space-y-1">
            <p className="font-medium">{config.label}</p>
            <p className="text-muted-foreground text-xs">{config.description}</p>
            {showReconnect && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-full text-xs mt-1"
                onClick={(e) => {
                  e.stopPropagation();
                  onReconnect();
                }}
              >
                <RefreshCw className="h-3 w-3 mr-1" />
                Erneut verbinden
              </Button>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
});

export default CollabWebSocketStatusIndicator;
