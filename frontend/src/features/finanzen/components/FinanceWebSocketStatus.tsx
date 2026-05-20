/**
 * FinanceWebSocketStatus - WebSocket Connection Status Indicator
 *
 * Zeigt den Status der WebSocket-Verbindung für Echtzeit-Updates an.
 *
 * Features:
 * - Verbindungsstatus-Anzeige (verbunden/verbindend/getrennt)
 * - Fehleranzeige
 * - Manuelle Reconnect-Option
 * - Tooltip mit Details
 * - Accessibility-konform (WCAG 2.1 AA)
 */

import { memo } from 'react'
import { Wifi, WifiOff, Loader2, AlertCircle, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useOptionalFinanceWebSocket } from '../context/FinanceWebSocketContext'

// ==================== TYPES ====================

interface FinanceWebSocketStatusProps {
  /** Additional CSS classes */
  className?: string
  /** Show compact version (icon only) */
  compact?: boolean
  /** Show reconnect button when disconnected */
  showReconnect?: boolean
}

// ==================== STATUS CONFIG ====================

const STATUS_CONFIG = {
  connected: {
    icon: Wifi,
    label: 'Verbunden',
    description: 'Echtzeit-Updates aktiv',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
    pulseColor: 'bg-green-500',
  },
  connecting: {
    icon: Loader2,
    label: 'Verbinde...',
    description: 'Verbindung wird aufgebaut',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
    pulseColor: 'bg-amber-500',
  },
  disconnected: {
    icon: WifiOff,
    label: 'Getrennt',
    description: 'Keine Echtzeit-Updates',
    color: 'text-muted-foreground',
    bgColor: 'bg-muted',
    pulseColor: 'bg-gray-400',
  },
  error: {
    icon: AlertCircle,
    label: 'Fehler',
    description: 'Verbindungsfehler',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
    pulseColor: 'bg-red-500',
  },
} as const

type ConnectionStatus = keyof typeof STATUS_CONFIG

// ==================== MAIN COMPONENT ====================

export const FinanceWebSocketStatus = memo(function FinanceWebSocketStatus({
  className,
  compact = false,
  showReconnect = true,
}: FinanceWebSocketStatusProps) {
  const ws = useOptionalFinanceWebSocket()

  // If not in provider, don't render
  if (!ws) {
    return null
  }

  const { isConnected, isConnecting, error, reconnect } = ws

  // Determine current status
  const getStatus = (): ConnectionStatus => {
    if (error) return 'error'
    if (isConnecting) return 'connecting'
    if (isConnected) return 'connected'
    return 'disconnected'
  }

  const status = getStatus()
  const config = STATUS_CONFIG[status]
  const Icon = config.icon

  // Compact version (icon only with tooltip)
  if (compact) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className={cn(
                'relative inline-flex items-center justify-center',
                'w-8 h-8 rounded-full',
                config.bgColor,
                className
              )}
              role="status"
              aria-label={`WebSocket: ${config.label}`}
            >
              <Icon
                className={cn(
                  'h-4 w-4',
                  config.color,
                  status === 'connecting' && 'animate-spin'
                )}
                aria-hidden="true"
              />
              {/* Connection pulse indicator */}
              {isConnected && (
                <span
                  className={cn(
                    'absolute top-0 right-0 w-2 h-2 rounded-full',
                    config.pulseColor,
                    'animate-pulse'
                  )}
                  aria-hidden="true"
                />
              )}
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <div className="text-sm">
              <p className="font-medium">{config.label}</p>
              <p className="text-muted-foreground">{config.description}</p>
              {error && (
                <p className="text-red-500 mt-1">{error}</p>
              )}
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  // Full version with label and optional reconnect
  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-1.5 rounded-lg',
        config.bgColor,
        className
      )}
      role="status"
      aria-live="polite"
      aria-label={`WebSocket-Status: ${config.label}`}
    >
      {/* Status icon */}
      <div className="relative">
        <Icon
          className={cn(
            'h-4 w-4',
            config.color,
            status === 'connecting' && 'animate-spin'
          )}
          aria-hidden="true"
        />
        {isConnected && (
          <span
            className={cn(
              'absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full',
              config.pulseColor,
              'animate-pulse'
            )}
            aria-hidden="true"
          />
        )}
      </div>

      {/* Status text */}
      <div className="flex flex-col">
        <span className={cn('text-sm font-medium', config.color)}>
          {config.label}
        </span>
        {error && (
          <span className="text-xs text-red-500">{error}</span>
        )}
      </div>

      {/* Reconnect button */}
      {showReconnect && (status === 'disconnected' || status === 'error') && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 ml-1"
                onClick={reconnect}
                aria-label="Verbindung wiederherstellen"
              >
                <RefreshCw className="h-3 w-3" aria-hidden="true" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Verbindung wiederherstellen</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  )
})

// ==================== MINIMAL INDICATOR ====================

/**
 * Minimale Status-Anzeige als Punkt
 * Für Header-Bars oder kompakte Layouts
 */
export const FinanceWebSocketDot = memo(function FinanceWebSocketDot({
  className,
}: {
  className?: string
}) {
  const ws = useOptionalFinanceWebSocket()

  if (!ws) return null

  const { isConnected, isConnecting, error } = ws

  const getColor = () => {
    if (error) return 'bg-red-500'
    if (isConnecting) return 'bg-amber-500 animate-pulse'
    if (isConnected) return 'bg-green-500'
    return 'bg-gray-400'
  }

  const getLabel = () => {
    if (error) return 'WebSocket-Fehler'
    if (isConnecting) return 'Verbinde...'
    if (isConnected) return 'Verbunden'
    return 'Nicht verbunden'
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              'inline-block w-2 h-2 rounded-full',
              getColor(),
              className
            )}
            role="status"
            aria-label={getLabel()}
          />
        </TooltipTrigger>
        <TooltipContent>
          <p>{getLabel()}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})

export default FinanceWebSocketStatus
