/**
 * Finance WebSocket Context - Shared WebSocket connection for Finance module
 *
 * Provides:
 * - Shared WebSocket connection across components
 * - Real-time event notifications
 * - Connection status indicator
 * - Toast notifications for important events
 */

import {
  createContext,
  useContext,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react'
import { useToast } from '@/components/ui/use-toast'
import {
  useFinanceWebSocket,
  type FinanceWebSocketEvent,
  type UseFinanceWebSocketReturn,
} from '../hooks/use-finance-websocket'

// ==================== CONTEXT ====================

interface FinanceWebSocketContextValue extends UseFinanceWebSocketReturn {
  /** Subscribe to specific event types */
  subscribe: (
    eventTypes: string[],
    handler: (event: FinanceWebSocketEvent) => void
  ) => () => void
}

const FinanceWebSocketContext = createContext<FinanceWebSocketContextValue | null>(null)

// ==================== PROVIDER ====================

interface FinanceWebSocketProviderProps {
  children: ReactNode
  /** Show toast notifications for events? */
  showNotifications?: boolean
  /** Auto-connect on mount? */
  autoConnect?: boolean
}

export function FinanceWebSocketProvider({
  children,
  showNotifications = true,
  autoConnect = true,
}: FinanceWebSocketProviderProps) {
  const { toast } = useToast()

  // Event handler with notifications
  const handleEvent = useCallback(
    (event: FinanceWebSocketEvent) => {
      if (!showNotifications) return

      switch (event.type) {
        case 'document.ocr_completed':
          toast({
            title: 'OCR abgeschlossen',
            description: event.data.message || 'Dokument wurde verarbeitet',
          })
          break

        case 'deadline.reminder':
          toast({
            title: 'Frist-Erinnerung',
            description: `${event.data.message || 'Frist'} in ${event.data.daysUntil} Tagen`,
            variant: 'default',
          })
          break

        case 'deadline.overdue':
          toast({
            title: 'Frist ueberschritten',
            description: event.data.message || 'Eine Frist wurde ueberschritten',
            variant: 'destructive',
          })
          break

        case 'export.completed':
          toast({
            title: 'Export abgeschlossen',
            description: event.data.message || 'Export ist bereit zum Download',
          })
          break

        case 'export.failed':
          toast({
            title: 'Export fehlgeschlagen',
            description: event.data.error || 'Ein Fehler ist aufgetreten',
            variant: 'destructive',
          })
          break

        case 'bulk.completed':
          toast({
            title: 'Massenoperation abgeschlossen',
            description: event.data.message || 'Alle Dokumente wurden verarbeitet',
          })
          break
      }
    },
    [showNotifications, toast]
  )

  const ws = useFinanceWebSocket({
    autoConnect,
    onEvent: handleEvent,
  })

  // Subscription system for targeted event handling
  const subscriptionsRef = useMemo(() => new Map<string, Set<(event: FinanceWebSocketEvent) => void>>(), [])

  const subscribe = useCallback(
    (eventTypes: string[], handler: (event: FinanceWebSocketEvent) => void) => {
      // Add handler to each event type
      for (const type of eventTypes) {
        if (!subscriptionsRef.has(type)) {
          subscriptionsRef.set(type, new Set())
        }
        subscriptionsRef.get(type)!.add(handler)
      }

      // Return unsubscribe function
      return () => {
        for (const type of eventTypes) {
          subscriptionsRef.get(type)?.delete(handler)
        }
      }
    },
    [subscriptionsRef]
  )

  const contextValue = useMemo(
    () => ({
      ...ws,
      subscribe,
    }),
    [ws, subscribe]
  )

  return (
    <FinanceWebSocketContext.Provider value={contextValue}>
      {children}
    </FinanceWebSocketContext.Provider>
  )
}

// ==================== HOOK ====================

export function useFinanceWebSocketContext(): FinanceWebSocketContextValue {
  const context = useContext(FinanceWebSocketContext)

  if (!context) {
    throw new Error(
      'useFinanceWebSocketContext must be used within a FinanceWebSocketProvider'
    )
  }

  return context
}

// ==================== OPTIONAL HOOK (returns null if not in provider) ====================

export function useOptionalFinanceWebSocket(): FinanceWebSocketContextValue | null {
  return useContext(FinanceWebSocketContext)
}

export default FinanceWebSocketProvider
