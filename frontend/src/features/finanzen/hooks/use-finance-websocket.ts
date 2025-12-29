/**
 * Finance WebSocket Hook - Echtzeit-Updates fuer Finanz-Dokumente
 *
 * Verbindet sich mit dem Backend WebSocket-Endpoint fuer:
 * - Dokument-Verarbeitungsstatus
 * - OCR-Abschluss-Benachrichtigungen
 * - Export-Fortschritt
 * - Frist-Erinnerungen
 *
 * Features:
 * - Auto-Reconnect mit Exponential Backoff
 * - Heartbeat-Ping zur Verbindungspruefung
 * - Event-basierte Architektur
 * - Query-Cache-Invalidation
 */

import { useEffect, useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { finanzenQueryKeys } from './use-finanzen-queries'

// ==================== TYPES ====================

export type FinanceEventType =
  | 'document.created'
  | 'document.updated'
  | 'document.deleted'
  | 'document.ocr_completed'
  | 'document.processing'
  | 'deadline.reminder'
  | 'deadline.overdue'
  | 'export.progress'
  | 'export.completed'
  | 'export.failed'
  | 'bulk.progress'
  | 'bulk.completed'

export interface FinanceWebSocketEvent {
  type: FinanceEventType
  timestamp: string
  data: {
    documentId?: string
    documentIds?: string[]
    year?: string
    category?: string
    status?: string
    progress?: number
    message?: string
    deadline?: string
    daysUntil?: number
    exportId?: string
    downloadUrl?: string
    error?: string
    [key: string]: unknown
  }
}

export interface UseFinanceWebSocketOptions {
  /** Automatisch verbinden? */
  autoConnect?: boolean
  /** Auto-Reconnect bei Verbindungsabbruch */
  autoReconnect?: boolean
  /** Maximale Reconnect-Versuche */
  maxRetries?: number
  /** Initiale Verzögerung zwischen Reconnects (ms) */
  initialRetryDelay?: number
  /** Maximale Verzögerung (ms) */
  maxRetryDelay?: number
  /** Heartbeat-Intervall (ms) */
  heartbeatInterval?: number
  /** Event-Handler */
  onEvent?: (event: FinanceWebSocketEvent) => void
  /** Verbindungs-Handler */
  onConnect?: () => void
  /** Disconnect-Handler */
  onDisconnect?: () => void
  /** Error-Handler */
  onError?: (error: string) => void
}

export interface UseFinanceWebSocketReturn {
  /** WebSocket verbunden? */
  isConnected: boolean
  /** Verbindung wird aufgebaut? */
  isConnecting: boolean
  /** Fehler aufgetreten? */
  error: string | null
  /** Letzte empfangene Events */
  lastEvents: FinanceWebSocketEvent[]
  /** Manuell verbinden */
  connect: () => void
  /** Manuell trennen */
  disconnect: () => void
  /** Verbindung neu aufbauen */
  reconnect: () => void
  /** Event an Server senden */
  send: (event: { type: string; data?: unknown }) => boolean
}

// ==================== HOOK ====================

export function useFinanceWebSocket(
  options: UseFinanceWebSocketOptions = {}
): UseFinanceWebSocketReturn {
  const {
    autoConnect = true,
    autoReconnect = true,
    maxRetries = 5,
    initialRetryDelay = 1000,
    maxRetryDelay = 30000,
    heartbeatInterval = 30000,
    onEvent,
    onConnect,
    onDisconnect,
    onError,
  } = options

  const queryClient = useQueryClient()

  const [isConnected, setIsConnected] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastEvents, setLastEvents] = useState<FinanceWebSocketEvent[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const retryCountRef = useRef(0)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectingRef = useRef(false)

  // Callbacks in Refs speichern
  const onEventRef = useRef(onEvent)
  const onConnectRef = useRef(onConnect)
  const onDisconnectRef = useRef(onDisconnect)
  const onErrorRef = useRef(onError)

  useEffect(() => { onEventRef.current = onEvent }, [onEvent])
  useEffect(() => { onConnectRef.current = onConnect }, [onConnect])
  useEffect(() => { onDisconnectRef.current = onDisconnect }, [onDisconnect])
  useEffect(() => { onErrorRef.current = onError }, [onError])

  // Calculate exponential backoff delay
  const getRetryDelay = useCallback(() => {
    const delay = initialRetryDelay * Math.pow(2, retryCountRef.current)
    return Math.min(delay, maxRetryDelay)
  }, [initialRetryDelay, maxRetryDelay])

  // Clear all timers
  const clearTimers = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current)
      heartbeatIntervalRef.current = null
    }
  }, [])

  // Handle incoming events
  const handleEvent = useCallback((event: FinanceWebSocketEvent) => {
    // Store last events (keep last 50)
    setLastEvents((prev) => [event, ...prev].slice(0, 50))

    // Call event handler
    onEventRef.current?.(event)

    // Invalidate relevant query caches based on event type
    switch (event.type) {
      case 'document.created':
      case 'document.updated':
      case 'document.deleted':
        // Invalidate document lists
        queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.categoryDocuments() })
        if (event.data.documentId) {
          queryClient.invalidateQueries({
            queryKey: finanzenQueryKeys.document(event.data.documentId)
          })
        }
        // Invalidate aggregations
        queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.overallAggregations() })
        if (event.data.year) {
          queryClient.invalidateQueries({
            queryKey: finanzenQueryKeys.yearAggregations(event.data.year)
          })
        }
        break

      case 'document.ocr_completed':
        if (event.data.documentId) {
          queryClient.invalidateQueries({
            queryKey: finanzenQueryKeys.document(event.data.documentId)
          })
          queryClient.invalidateQueries({
            queryKey: finanzenQueryKeys.documentVersions(event.data.documentId)
          })
        }
        break

      case 'deadline.reminder':
      case 'deadline.overdue':
        queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.deadlines() })
        break

      case 'bulk.completed':
        // Full refresh after bulk operations
        queryClient.invalidateQueries({ queryKey: finanzenQueryKeys.all })
        break
    }
  }, [queryClient])

  // Start heartbeat
  const startHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current)
    }

    heartbeatIntervalRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, heartbeatInterval)
  }, [heartbeatInterval])

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return // Already connected
    }

    if (isConnecting || reconnectingRef.current) {
      return // Connection in progress
    }

    setIsConnecting(true)
    setError(null)

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname
    const port = import.meta.env.DEV ? '8000' : window.location.port
    const wsUrl = `${protocol}//${host}:${port}/api/v1/finance/ws`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        setIsConnecting(false)
        setError(null)
        retryCountRef.current = 0
        reconnectingRef.current = false

        // Start heartbeat
        startHeartbeat()

        // Call connect handler
        onConnectRef.current?.()

        console.debug('[FinanceWS] Connected')
      }

      ws.onmessage = (messageEvent) => {
        try {
          const data = JSON.parse(messageEvent.data)

          // Handle pong
          if (data.type === 'pong') {
            return
          }

          // Handle finance events
          if (data.type && data.timestamp) {
            handleEvent(data as FinanceWebSocketEvent)
          }
        } catch {
          console.warn('[FinanceWS] Failed to parse message:', messageEvent.data)
        }
      }

      ws.onerror = () => {
        setError('WebSocket-Verbindungsfehler')
        onErrorRef.current?.('WebSocket connection error')
      }

      ws.onclose = (closeEvent) => {
        setIsConnected(false)
        setIsConnecting(false)
        wsRef.current = null

        clearTimers()
        onDisconnectRef.current?.()

        console.debug('[FinanceWS] Disconnected', closeEvent.code)

        // Auto-reconnect if enabled and not manually closed
        if (autoReconnect && closeEvent.code !== 1000 && !reconnectingRef.current) {
          if (retryCountRef.current < maxRetries) {
            reconnectingRef.current = true
            const delay = getRetryDelay()
            retryCountRef.current++

            console.debug(`[FinanceWS] Reconnecting in ${delay}ms (${retryCountRef.current}/${maxRetries})`)

            retryTimeoutRef.current = setTimeout(() => {
              reconnectingRef.current = false
              connect()
            }, delay)
          } else {
            setError('Verbindung konnte nicht wiederhergestellt werden')
            onErrorRef.current?.('Max reconnect attempts reached')
          }
        }
      }
    } catch (err) {
      setIsConnecting(false)
      setError('WebSocket konnte nicht erstellt werden')
      onErrorRef.current?.('Failed to create WebSocket')
    }
  }, [autoReconnect, maxRetries, getRetryDelay, startHeartbeat, handleEvent, clearTimers, isConnecting])

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    clearTimers()
    reconnectingRef.current = false
    retryCountRef.current = 0

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect')
      wsRef.current = null
    }

    setIsConnected(false)
    setIsConnecting(false)
  }, [clearTimers])

  // Reconnect
  const reconnect = useCallback(() => {
    disconnect()
    retryCountRef.current = 0
    setTimeout(connect, 100)
  }, [disconnect, connect])

  // Send event to server
  const send = useCallback((event: { type: string; data?: unknown }): boolean => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(event))
      return true
    }
    return false
  }, [])

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    isConnected,
    isConnecting,
    error,
    lastEvents,
    connect,
    disconnect,
    reconnect,
    send,
  }
}

export default useFinanceWebSocket
