/**
 * WebSocketStatusIndicator - Global WebSocket Connection Status
 *
 * Zeigt den Status der globalen WebSocket-Verbindung an.
 * Kompakter Indikator für Header/Statusbar.
 *
 * Features:
 * - Echtzeit-Status (verbunden/verbindend/getrennt/reconnecting)
 * - Tooltip mit Details
 * - WCAG 2.1 AA konform
 */

import { memo } from 'react'
import { Wifi, WifiOff, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useWebSocket, type ConnectionState } from '@/lib/websocket'

// ==================== STATUS CONFIG ====================

const STATUS_CONFIG: Record<ConnectionState, {
  icon: typeof Wifi
  label: string
  description: string
  color: string
  bgColor: string
  animate?: boolean
}> = {
  connected: {
    icon: Wifi,
    label: 'Verbunden',
    description: 'Echtzeit-Updates aktiv',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-500',
  },
  connecting: {
    icon: Loader2,
    label: 'Verbinde...',
    description: 'Verbindung wird aufgebaut',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-500',
    animate: true,
  },
  reconnecting: {
    icon: Loader2,
    label: 'Verbinde erneut...',
    description: 'Verbindung wird wiederhergestellt',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-500',
    animate: true,
  },
  disconnected: {
    icon: WifiOff,
    label: 'Offline',
    description: 'Keine Echtzeit-Updates',
    color: 'text-muted-foreground',
    bgColor: 'bg-gray-400',
  },
}

// ==================== COMPONENT ====================

interface WebSocketStatusIndicatorProps {
  className?: string
}

export const WebSocketStatusIndicator = memo(function WebSocketStatusIndicator({
  className,
}: WebSocketStatusIndicatorProps) {
  const { state } = useWebSocket()
  const config = STATUS_CONFIG[state]
  const Icon = config.icon

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'relative flex items-center gap-1.5 px-2 py-1 rounded-md',
              'hover:bg-accent/50 transition-colors cursor-default',
              className
            )}
            role="status"
            aria-label={`WebSocket: ${config.label}`}
          >
            {/* Status dot */}
            <span
              className={cn(
                'w-2 h-2 rounded-full',
                config.bgColor,
                config.animate && 'animate-pulse'
              )}
              aria-hidden="true"
            />
            {/* Icon */}
            <Icon
              className={cn(
                'h-3.5 w-3.5',
                config.color,
                config.animate && 'animate-spin'
              )}
              aria-hidden="true"
            />
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" align="end">
          <div className="text-sm">
            <p className="font-medium">{config.label}</p>
            <p className="text-muted-foreground text-xs">{config.description}</p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})

export default WebSocketStatusIndicator
