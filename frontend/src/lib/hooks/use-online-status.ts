/**
 * useOnlineStatus Hook
 *
 * Detects online/offline status and provides network state information.
 * Enterprise-grade implementation with:
 * - Browser Online/Offline events
 * - Optional ping-based verification
 * - Reconnection detection
 */

import { useState, useEffect, useCallback, useRef } from 'react';

interface OnlineStatusOptions {
  /** Enable ping-based verification (default: false) */
  pingVerification?: boolean;
  /** Ping endpoint URL (default: /api/v1/health) */
  pingUrl?: string;
  /** Ping interval in ms when online (default: 30000) */
  pingIntervalMs?: number;
  /** Ping timeout in ms (default: 5000) */
  pingTimeoutMs?: number;
  /** Callback when going offline */
  onOffline?: () => void;
  /** Callback when coming back online */
  onOnline?: () => void;
}

interface OnlineStatusResult {
  /** Whether the browser reports being online */
  isOnline: boolean;
  /** Whether the API is reachable (if pingVerification enabled) */
  isApiReachable: boolean;
  /** Combined status: truly connected to backend */
  isConnected: boolean;
  /** Time of last successful ping */
  lastPingAt: Date | null;
  /** Time when we went offline */
  offlineSince: Date | null;
  /** Manually trigger a connectivity check */
  checkConnection: () => Promise<boolean>;
}

export function useOnlineStatus(options: OnlineStatusOptions = {}): OnlineStatusResult {
  const {
    pingVerification = false,
    pingUrl = '/api/v1/health',
    pingIntervalMs = 30000,
    pingTimeoutMs = 5000,
    onOffline,
    onOnline,
  } = options;

  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );
  const [isApiReachable, setIsApiReachable] = useState(true);
  const [lastPingAt, setLastPingAt] = useState<Date | null>(null);
  const [offlineSince, setOfflineSince] = useState<Date | null>(null);

  const wasOnlineRef = useRef(isOnline);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  /**
   * Check if API is reachable via ping
   */
  const checkConnection = useCallback(async (): Promise<boolean> => {
    if (!pingVerification) {
      return navigator.onLine;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), pingTimeoutMs);

      const response = await fetch(pingUrl, {
        method: 'HEAD',
        signal: controller.signal,
        cache: 'no-store',
      });

      clearTimeout(timeoutId);

      const reachable = response.ok;
      setIsApiReachable(reachable);

      if (reachable) {
        setLastPingAt(new Date());
      }

      return reachable;
    } catch {
      setIsApiReachable(false);
      return false;
    }
  }, [pingVerification, pingUrl, pingTimeoutMs]);

  /**
   * Handle online event
   */
  const handleOnline = useCallback(() => {
    setIsOnline(true);
    setOfflineSince(null);

    // Verify connection if ping verification is enabled
    if (pingVerification) {
      checkConnection();
    }

    // Fire callback only on transition from offline to online
    if (!wasOnlineRef.current && onOnline) {
      onOnline();
    }
    wasOnlineRef.current = true;
  }, [pingVerification, checkConnection, onOnline]);

  /**
   * Handle offline event
   */
  const handleOffline = useCallback(() => {
    setIsOnline(false);
    setIsApiReachable(false);
    setOfflineSince(new Date());

    // Fire callback only on transition from online to offline
    if (wasOnlineRef.current && onOffline) {
      onOffline();
    }
    wasOnlineRef.current = false;
  }, [onOffline]);

  /**
   * Setup event listeners
   */
  useEffect(() => {
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Initial check
    if (navigator.onLine) {
      handleOnline();
    } else {
      handleOffline();
    }

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [handleOnline, handleOffline]);

  /**
   * Setup ping interval if enabled
   */
  useEffect(() => {
    if (!pingVerification || !isOnline) {
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
      return;
    }

    // Initial ping
    checkConnection();

    // Setup interval
    pingIntervalRef.current = setInterval(checkConnection, pingIntervalMs);

    return () => {
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
    };
  }, [pingVerification, isOnline, pingIntervalMs, checkConnection]);

  // Combined connection status
  const isConnected = pingVerification ? isOnline && isApiReachable : isOnline;

  return {
    isOnline,
    isApiReachable,
    isConnected,
    lastPingAt,
    offlineSince,
    checkConnection,
  };
}

export default useOnlineStatus;
