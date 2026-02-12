/**
 * Job Queue WebSocket Hook
 *
 * Hybrid Real-Time Updates für Job Queue:
 * - WebSocket für aktive Job-Updates (wenn verfügbar)
 * - Polling Fallback wenn WebSocket nicht verfügbar
 * - Automatischer Reconnect mit Exponential Backoff
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { jobQueueKeys } from '../api/query-keys';
import { buildWebSocketUrl, wsLogger } from '../config/websocket-config';
import { getAuthToken } from '@/lib/api/services/auth';
import type { Job, JobStatus } from '../types/job-types';

// ==================== Types ====================

export interface JobWebSocketMessage {
  type: 'job_update' | 'job_created' | 'job_completed' | 'job_failed' | 'stats_update' | 'ping';
  job?: Partial<Job>;
  jobId?: string;
  stats?: {
    activeJobs: number;
    queuedJobs: number;
    completedToday: number;
    failedToday: number;
  };
  timestamp?: string;
}

interface UseJobWebSocketOptions {
  /** WebSocket aktivieren */
  enabled?: boolean;
  /** Auto-reconnect bei Verbindungsabbruch */
  autoReconnect?: boolean;
  /** Maximale Reconnect-Versuche */
  maxRetries?: number;
  /** Initiale Verzögerung zwischen Reconnects (ms) */
  retryDelay?: number;
  /** Fallback zu Polling wenn WebSocket nicht verfügbar */
  pollingFallback?: boolean;
  /** Polling-Intervall in ms */
  pollingInterval?: number;
  /** Callback bei Job-Update */
  onJobUpdate?: (job: Partial<Job>) => void;
  /** Callback bei Job-Abschluss */
  onJobCompleted?: (jobId: string) => void;
  /** Callback bei Job-Fehler */
  onJobFailed?: (jobId: string, error?: string) => void;
  /** Callback bei Verbindungsstatus-Änderung */
  onConnectionChange?: (connected: boolean) => void;
}

interface UseJobWebSocketReturn {
  /** WebSocket verbunden? */
  isConnected: boolean;
  /** Verbindung wird aufgebaut? */
  isConnecting: boolean;
  /** Nutzt Polling-Fallback? */
  isPolling: boolean;
  /** Verbindungsfehler */
  error: string | null;
  /** Letzte Aktualisierung */
  lastUpdate: Date | null;
  /** Verbindung manuell schließen */
  disconnect: () => void;
  /** Verbindung neu aufbauen */
  reconnect: () => void;
}

// ==================== Hook ====================

export function useJobWebSocket(options: UseJobWebSocketOptions = {}): UseJobWebSocketReturn {
  const queryClient = useQueryClient();

  // Stabilisiere Options
  const stableOpts = useMemo(
    () => ({
      enabled: options.enabled ?? true,
      autoReconnect: options.autoReconnect ?? true,
      maxRetries: options.maxRetries ?? 5,
      retryDelay: options.retryDelay ?? 1000,
      pollingFallback: options.pollingFallback ?? true,
      pollingInterval: options.pollingInterval ?? 10000,
    }),
    [
      options.enabled,
      options.autoReconnect,
      options.maxRetries,
      options.retryDelay,
      options.pollingFallback,
      options.pollingInterval,
    ]
  );

  // Callbacks in Refs speichern
  const onJobUpdateRef = useRef(options.onJobUpdate);
  const onJobCompletedRef = useRef(options.onJobCompleted);
  const onJobFailedRef = useRef(options.onJobFailed);
  const onConnectionChangeRef = useRef(options.onConnectionChange);

  useEffect(() => {
    onJobUpdateRef.current = options.onJobUpdate;
  }, [options.onJobUpdate]);
  useEffect(() => {
    onJobCompletedRef.current = options.onJobCompleted;
  }, [options.onJobCompleted]);
  useEffect(() => {
    onJobFailedRef.current = options.onJobFailed;
  }, [options.onJobFailed]);
  useEffect(() => {
    onConnectionChangeRef.current = options.onConnectionChange;
  }, [options.onConnectionChange]);

  // State
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Handle incoming WebSocket message
  const handleMessage = useCallback(
    (message: JobWebSocketMessage) => {
      setLastUpdate(new Date());

      switch (message.type) {
        case 'job_update':
          if (message.job) {
            onJobUpdateRef.current?.(message.job);
            // Invalidate relevant queries
            queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
            if (message.job.id) {
              queryClient.invalidateQueries({ queryKey: jobQueueKeys.job(message.job.id) });
            }
          }
          break;

        case 'job_created':
          queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
          queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
          break;

        case 'job_completed':
          if (message.jobId) {
            onJobCompletedRef.current?.(message.jobId);
            queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
            queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
          }
          break;

        case 'job_failed':
          if (message.jobId) {
            onJobFailedRef.current?.(message.jobId, message.job?.errorMessage);
            queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
            queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
            queryClient.invalidateQueries({ queryKey: jobQueueKeys.dlq() });
          }
          break;

        case 'stats_update':
          queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
          break;

        case 'ping':
          // Heartbeat - no action needed
          break;
      }
    },
    [queryClient]
  );

  // Start polling fallback
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) return;

    setIsPolling(true);
    wsLogger.debug('Starting polling fallback');

    pollingIntervalRef.current = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.jobs() });
      queryClient.invalidateQueries({ queryKey: jobQueueKeys.stats() });
      setLastUpdate(new Date());
    }, stableOpts.pollingInterval);
  }, [queryClient, stableOpts.pollingInterval]);

  // Stop polling
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  // Disconnect
  const disconnect = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    stopPolling();
    setIsConnected(false);
    setIsConnecting(false);
  }, [stopPolling]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!stableOpts.enabled) return;

    // Cleanup existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }
    stopPolling();

    setIsConnecting(true);
    setError(null);

    // Build WebSocket URL mit Auth-Token
    const token = getAuthToken();
    if (!token) {
      wsLogger.error('No auth token available for WebSocket');
      setIsConnecting(false);
      setError('Authentifizierung erforderlich');
      if (stableOpts.pollingFallback) {
        startPolling();
      }
      return;
    }

    // Token als Query-Parameter anhängen (wie chat_ws.py erwartet)
    const wsUrl = buildWebSocketUrl(`/api/v1/admin/jobs/ws?token=${encodeURIComponent(token)}`);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setIsConnecting(false);
        setError(null);
        retryCountRef.current = 0;
        onConnectionChangeRef.current?.(true);
        wsLogger.debug('Connected with authentication');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as JobWebSocketMessage;
          handleMessage(message);
        } catch (e) {
          wsLogger.error('Parse error:', e);
        }
      };

      ws.onerror = (event) => {
        wsLogger.error('Error:', event);
        setError('WebSocket-Verbindungsfehler');
      };

      ws.onclose = () => {
        setIsConnected(false);
        setIsConnecting(false);
        wsRef.current = null;
        onConnectionChangeRef.current?.(false);

        if (!stableOpts.autoReconnect) {
          if (stableOpts.pollingFallback) {
            startPolling();
          }
          return;
        }

        // Exponential backoff reconnect
        if (retryCountRef.current < stableOpts.maxRetries) {
          const delay = stableOpts.retryDelay * Math.pow(2, retryCountRef.current);
          retryCountRef.current++;
          wsLogger.debug(
            `Reconnecting in ${delay}ms (${retryCountRef.current}/${stableOpts.maxRetries})...`
          );
          retryTimeoutRef.current = setTimeout(connect, delay);
        } else {
          setError('Verbindung konnte nicht wiederhergestellt werden');
          if (stableOpts.pollingFallback) {
            startPolling();
          }
        }
      };
    } catch (e) {
      wsLogger.error('Connection failed:', e);
      setIsConnecting(false);
      setError('WebSocket nicht verfügbar');
      if (stableOpts.pollingFallback) {
        startPolling();
      }
    }
  }, [stableOpts, handleMessage, stopPolling, startPolling]);

  // Reconnect
  const reconnect = useCallback(() => {
    retryCountRef.current = 0;
    connect();
  }, [connect]);

  // Connect on mount
  useEffect(() => {
    if (stableOpts.enabled) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [stableOpts.enabled, connect, disconnect]);

  return {
    isConnected,
    isConnecting,
    isPolling,
    error,
    lastUpdate,
    disconnect,
    reconnect,
  };
}

// ==================== Single Job WebSocket Hook ====================

interface UseJobStatusWebSocketOptions {
  /** WebSocket aktivieren */
  enabled?: boolean;
  /** Callback bei Status-Änderung */
  onStatusChange?: (status: JobStatus) => void;
  /** Callback bei Abschluss */
  onComplete?: () => void;
  /** Callback bei Fehler */
  onError?: (error: string) => void;
}

interface UseJobStatusWebSocketReturn {
  /** Aktueller Status */
  status: JobStatus | null;
  /** Fortschritt (0-100) */
  progress: number;
  /** Status-Nachricht */
  message: string | null;
  /** WebSocket verbunden? */
  isConnected: boolean;
  /** Task abgeschlossen? */
  isComplete: boolean;
  /** Fehler aufgetreten? */
  error: string | null;
}

/**
 * Hook für Live-Updates eines einzelnen Jobs.
 */
export function useJobStatusWebSocket(
  jobId: string | null,
  options: UseJobStatusWebSocketOptions = {}
): UseJobStatusWebSocketReturn {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onStatusChangeRef = useRef(options.onStatusChange);
  const onCompleteRef = useRef(options.onComplete);
  const onErrorRef = useRef(options.onError);

  useEffect(() => {
    onStatusChangeRef.current = options.onStatusChange;
  }, [options.onStatusChange]);
  useEffect(() => {
    onCompleteRef.current = options.onComplete;
  }, [options.onComplete]);
  useEffect(() => {
    onErrorRef.current = options.onError;
  }, [options.onError]);

  const wsRef = useRef<WebSocket | null>(null);

  const isComplete = status === 'completed' || status === 'failed' || status === 'cancelled';

  useEffect(() => {
    if (!jobId || !options.enabled) {
      return;
    }

    // Auth-Token holen
    const token = getAuthToken();
    if (!token) {
      setError('Authentifizierung erforderlich');
      return;
    }

    const wsUrl = buildWebSocketUrl(`/api/v1/tasks/ws/${jobId}?token=${encodeURIComponent(token)}`);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const newStatus = data.state?.toLowerCase() as JobStatus;
        if (newStatus) {
          setStatus(newStatus);
          onStatusChangeRef.current?.(newStatus);
        }
        if (typeof data.progress === 'number') {
          setProgress(data.progress);
        }
        if (data.message) {
          setMessage(data.message);
        }

        // Check for completion
        if (
          newStatus === 'completed' ||
          data.state === 'SUCCESS' ||
          data.state === 'completed'
        ) {
          onCompleteRef.current?.();
        }
        if (newStatus === 'failed' || data.state === 'FAILURE') {
          onErrorRef.current?.(data.error || data.message || 'Unbekannter Fehler');
        }
      } catch (e) {
        wsLogger.error('JobStatus Parse error:', e);
      }
    };

    ws.onerror = () => {
      setError('WebSocket-Verbindungsfehler');
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [jobId, options.enabled]);

  return {
    status,
    progress,
    message,
    isConnected,
    isComplete,
    error,
  };
}

export default useJobWebSocket;
