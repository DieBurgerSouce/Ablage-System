/**
 * WebSocket Hook für Task-Status Updates.
 *
 * Verbindet sich mit dem Backend WebSocket-Endpoint für Live-Updates
 * von Celery-Tasks (z.B. Benchmark-Läufe, Batch-Verarbeitung).
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { logger } from '@/lib/logger'

export interface TaskStatus {
  task_id: string
  state: 'PENDING' | 'STARTED' | 'PROGRESS' | 'SUCCESS' | 'FAILURE' | 'REVOKED'
  progress: number
  message: string
  current: number
  total: number
  result?: Record<string, unknown>
  error?: string
}

interface UseTaskWebSocketOptions {
  /** Auto-reconnect bei Verbindungsabbruch */
  autoReconnect?: boolean
  /** Maximale Reconnect-Versuche */
  maxRetries?: number
  /** Verzögerung zwischen Reconnects (ms) */
  retryDelay?: number
  /** Callback bei Statusänderung */
  onStatusChange?: (status: TaskStatus) => void
  /** Callback bei Task-Abschluss */
  onComplete?: (result: TaskStatus) => void
  /** Callback bei Fehler */
  onError?: (error: string) => void
}

interface UseTaskWebSocketReturn {
  /** Aktueller Task-Status */
  status: TaskStatus | null
  /** WebSocket verbunden? */
  isConnected: boolean
  /** Verbindung wird aufgebaut? */
  isConnecting: boolean
  /** Fehler aufgetreten? */
  error: string | null
  /** Task abgeschlossen? */
  isComplete: boolean
  /** Fortschritt in Prozent (0-100) */
  progress: number
  /** Verbindung manuell schließen */
  disconnect: () => void
  /** Verbindung neu aufbauen */
  reconnect: () => void
}

export function useTaskWebSocket(
  taskId: string | null,
  options: UseTaskWebSocketOptions = {}
): UseTaskWebSocketReturn {
  // Stabilisiere primitive Options mit useMemo
  const stableOpts = useMemo(() => ({
    autoReconnect: options.autoReconnect ?? true,
    maxRetries: options.maxRetries ?? 3,
    retryDelay: options.retryDelay ?? 2000,
  }), [
    options.autoReconnect,
    options.maxRetries,
    options.retryDelay,
  ])

  // Callbacks in Refs speichern um Stale Closures zu vermeiden
  const onStatusChangeRef = useRef(options.onStatusChange)
  const onCompleteRef = useRef(options.onComplete)
  const onErrorRef = useRef(options.onError)

  // Refs aktualisieren wenn Callbacks sich ändern
  useEffect(() => {
    onStatusChangeRef.current = options.onStatusChange
  }, [options.onStatusChange])
  useEffect(() => {
    onCompleteRef.current = options.onComplete
  }, [options.onComplete])
  useEffect(() => {
    onErrorRef.current = options.onError
  }, [options.onError])

  const [status, setStatus] = useState<TaskStatus | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const retryCountRef = useRef(0)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Ref für isComplete um Stale Closures im onclose Handler zu vermeiden
  const isCompleteRef = useRef(false)

  const isComplete = status?.state === 'SUCCESS' || status?.state === 'FAILURE'
  const progress = status?.progress ?? 0

  // isCompleteRef synchron halten
  useEffect(() => {
    isCompleteRef.current = isComplete
  }, [isComplete])

  const disconnect = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
    setIsConnecting(false)
  }, [])

  const connect = useCallback(() => {
    if (!taskId) return

    // Bestehende Verbindung schließen
    if (wsRef.current) {
      wsRef.current.close()
    }

    setIsConnecting(true)
    setError(null)

    // WebSocket URL bauen (relativ zum aktuellen Host)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname
    const port = import.meta.env.DEV ? '8000' : window.location.port
    const wsUrl = `${protocol}//${host}:${port}/api/v1/tasks/ws/${taskId}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      setIsConnecting(false)
      retryCountRef.current = 0
      logger.debug(`WebSocket mit Task verbunden: ${taskId}`)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as TaskStatus
        setStatus(data)
        onStatusChangeRef.current?.(data)

        // Task abgeschlossen?
        if (data.state === 'SUCCESS' || data.state === 'FAILURE') {
          onCompleteRef.current?.(data)
          if (data.state === 'FAILURE' && data.error) {
            onErrorRef.current?.(data.error)
          }
        }
      } catch (e) {
        logger.error('WebSocket Nachricht konnte nicht geparst werden', e)
      }
    }

    ws.onerror = (event) => {
      logger.error('WebSocket-Fehler aufgetreten', event)
      setError('WebSocket-Verbindungsfehler')
    }

    ws.onclose = () => {
      setIsConnected(false)
      setIsConnecting(false)
      wsRef.current = null

      // Nicht reconnecten wenn Task abgeschlossen oder autoReconnect deaktiviert
      // Nutze Ref um Stale Closure zu vermeiden
      if (isCompleteRef.current || !stableOpts.autoReconnect) return

      // Reconnect-Logik
      if (retryCountRef.current < stableOpts.maxRetries) {
        retryCountRef.current++
        logger.debug(`WebSocket wird neu verbunden (${retryCountRef.current}/${stableOpts.maxRetries})`)
        retryTimeoutRef.current = setTimeout(connect, stableOpts.retryDelay)
      } else {
        setError('Verbindung konnte nicht wiederhergestellt werden')
        onErrorRef.current?.('Maximale Reconnect-Versuche erreicht')
      }
    }
  }, [taskId, stableOpts]) // Nur taskId und stabile Optionen als Dependencies

  const reconnect = useCallback(() => {
    retryCountRef.current = 0
    connect()
  }, [connect])

  // Verbindung aufbauen wenn taskId gesetzt wird
  useEffect(() => {
    if (taskId) {
      connect()
    } else {
      disconnect()
      setStatus(null)
    }

    return () => {
      disconnect()
    }
  }, [taskId, connect, disconnect])

  return {
    status,
    isConnected,
    isConnecting,
    error,
    isComplete,
    progress,
    disconnect,
    reconnect,
  }
}

export default useTaskWebSocket
