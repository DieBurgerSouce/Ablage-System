/**
 * useExportJob Hook
 *
 * Verwaltet den Zustand eines Export-Jobs mit:
 * - Echtzeit-Updates via WebSocket (mit Polling-Fallback)
 * - Automatisches Reconnect bei Verbindungsproblemen
 * - Cancel/Pause/Resume Aktionen
 *
 * Feinpoliert und durchdacht - Enterprise-ready Hook.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  exportsService,
  ExportJobStatusResponse,
  ExportJobStatus,
} from '@/lib/api/services/exports';

interface UseExportJobOptions {
  /** Job-ID zum Verfolgen */
  jobId: string;
  /** Polling-Intervall in ms (Fallback wenn WebSocket nicht verfuegbar) */
  pollingInterval?: number;
  /** Aktiviert WebSocket fuer Echtzeit-Updates */
  useWebSocket?: boolean;
  /** Callback wenn Job abgeschlossen */
  onComplete?: (status: ExportJobStatusResponse) => void;
  /** Callback bei Fehler */
  onError?: (error: Error) => void;
}

interface UseExportJobReturn {
  /** Aktueller Job-Status */
  status: ExportJobStatusResponse | null;
  /** Ladezustand */
  isLoading: boolean;
  /** Fehler */
  error: Error | null;
  /** WebSocket verbunden? */
  isConnected: boolean;
  /** Job abbrechen */
  cancel: () => Promise<void>;
  /** Job pausieren */
  pause: () => Promise<void>;
  /** Job fortsetzen */
  resume: () => Promise<void>;
  /** Status manuell aktualisieren */
  refresh: () => Promise<void>;
}

/**
 * Hook fuer Export-Job Verwaltung mit Echtzeit-Updates
 */
export function useExportJob(options: UseExportJobOptions): UseExportJobReturn {
  const {
    jobId,
    pollingInterval = 2000,
    useWebSocket = true,
    onComplete,
    onError,
  } = options;

  const [status, setStatus] = useState<ExportJobStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  // Hilfsfunktion: Ist der Job abgeschlossen?
  const isJobComplete = useCallback((jobStatus: ExportJobStatus): boolean => {
    return ['completed', 'failed', 'cancelled'].includes(jobStatus);
  }, []);

  // Status abrufen (Polling)
  const fetchStatus = useCallback(async () => {
    if (!mountedRef.current) return;

    try {
      const jobStatus = await exportsService.getJobStatus(jobId);
      if (!mountedRef.current) return;

      setStatus(jobStatus);
      setError(null);

      if (isJobComplete(jobStatus.status)) {
        // Polling stoppen wenn abgeschlossen
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }

        // Callback aufrufen
        if (onComplete) {
          onComplete(jobStatus);
        }
      }
    } catch (err) {
      if (!mountedRef.current) return;

      const error = err instanceof Error ? err : new Error('Unbekannter Fehler');
      setError(error);

      if (onError) {
        onError(error);
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [jobId, isJobComplete, onComplete, onError]);

  // WebSocket einrichten
  const setupWebSocket = useCallback(() => {
    if (!useWebSocket || wsRef.current) return;

    const ws = exportsService.createWebSocketConnection(
      jobId,
      // onMessage
      (data) => {
        if (!mountedRef.current) return;

        setStatus(data);

        if (isJobComplete(data.status)) {
          // WebSocket schliessen wenn abgeschlossen
          if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
          }

          if (onComplete) {
            onComplete(data);
          }
        }
      },
      // onError
      () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        // Fallback zu Polling
        startPolling();
      },
      // onClose
      () => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        wsRef.current = null;
      }
    );

    if (ws) {
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        // Polling stoppen wenn WebSocket verbunden
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      };
    } else {
      // WebSocket nicht verfuegbar, Fallback zu Polling
      startPolling();
    }
  }, [jobId, useWebSocket, isJobComplete, onComplete]);

  // Polling starten
  const startPolling = useCallback(() => {
    if (pollingRef.current) return;

    pollingRef.current = setInterval(fetchStatus, pollingInterval);
  }, [fetchStatus, pollingInterval]);

  // Cancel
  const cancel = useCallback(async () => {
    try {
      await exportsService.cancelJob(jobId);
      await fetchStatus();
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Abbrechen fehlgeschlagen');
      setError(error);
      if (onError) onError(error);
    }
  }, [jobId, fetchStatus, onError]);

  // Pause
  const pause = useCallback(async () => {
    try {
      const newStatus = await exportsService.pauseJob(jobId);
      setStatus(newStatus);
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Pausieren fehlgeschlagen');
      setError(error);
      if (onError) onError(error);
    }
  }, [jobId, onError]);

  // Resume
  const resume = useCallback(async () => {
    try {
      const newStatus = await exportsService.resumeJob(jobId);
      setStatus(newStatus);
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Fortsetzen fehlgeschlagen');
      setError(error);
      if (onError) onError(error);
    }
  }, [jobId, onError]);

  // Initialisierung
  useEffect(() => {
    mountedRef.current = true;

    // Initial fetch
    fetchStatus().then(() => {
      // WebSocket oder Polling starten (nur wenn Job nicht abgeschlossen)
      if (status && !isJobComplete(status.status)) {
        if (useWebSocket) {
          setupWebSocket();
        } else {
          startPolling();
        }
      }
    });

    return () => {
      mountedRef.current = false;

      // Cleanup WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      // Cleanup Polling
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [jobId]); // Nur bei jobId-Aenderung neu initialisieren

  // WebSocket setup nach initialem Fetch
  useEffect(() => {
    if (status && !isJobComplete(status.status) && useWebSocket && !wsRef.current) {
      setupWebSocket();
    }
  }, [status, useWebSocket, isJobComplete, setupWebSocket]);

  return {
    status,
    isLoading,
    error,
    isConnected,
    cancel,
    pause,
    resume,
    refresh: fetchStatus,
  };
}

/**
 * Hook fuer Export-Job Liste
 */
export function useExportJobList(
  statusFilter?: ExportJobStatus,
  refreshInterval?: number
) {
  const [jobs, setJobs] = useState<ExportJobStatusResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const response = await exportsService.listJobs(statusFilter, 50, 0);
      setJobs(response.jobs as unknown as ExportJobStatusResponse[]);
      setTotal(response.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Laden fehlgeschlagen'));
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchJobs();

    let interval: ReturnType<typeof setInterval> | null = null;
    if (refreshInterval && refreshInterval > 0) {
      interval = setInterval(fetchJobs, refreshInterval);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [fetchJobs, refreshInterval]);

  return {
    jobs,
    total,
    isLoading,
    error,
    refresh: fetchJobs,
  };
}
