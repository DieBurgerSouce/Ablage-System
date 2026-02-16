/**
 * useOnlineStatus - Network connectivity hook
 *
 * Überwacht den Online/Offline-Status des Browsers.
 * Nutzt navigator.onLine + Event-Listener für Echtzeit-Updates.
 */

import { useState, useEffect, useCallback } from 'react';

export interface OnlineStatus {
  /** Ob der Browser online ist */
  isOnline: boolean;
  /** Ob der Browser offline ist */
  isOffline: boolean;
  /** Zeitpunkt des letzten Status-Wechsels */
  lastChanged: Date | null;
}

export function useOnlineStatus(): OnlineStatus {
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );
  const [lastChanged, setLastChanged] = useState<Date | null>(null);

  const handleOnline = useCallback(() => {
    setIsOnline(true);
    setLastChanged(new Date());
  }, []);

  const handleOffline = useCallback(() => {
    setIsOnline(false);
    setLastChanged(new Date());
  }, []);

  useEffect(() => {
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [handleOnline, handleOffline]);

  return {
    isOnline,
    isOffline: !isOnline,
    lastChanged,
  };
}
