/**
 * WebSocket Initialization Hook.
 *
 * Stellt die WebSocket-Verbindung automatisch her, wenn der Benutzer
 * authentifiziert ist. Trennt die Verbindung bei Logout.
 *
 * Wird einmalig im Root-Layout gemountet.
 */

import { useEffect, useRef } from 'react';
import { useAuth } from '@/lib/auth/AuthContext';
import { getAuthToken } from '@/lib/api/services/auth';
import { getWebSocketClient } from '@/lib/websocket';
import { logger } from '@/lib/logger';

const wsLogger = logger.withLabels({ component: 'WebSocketInit' });

export function useWebSocketInit(): void {
  const { isAuthenticated } = useAuth();
  const connectedRef = useRef(false);

  useEffect(() => {
    if (isAuthenticated) {
      const token = getAuthToken();
      if (token && !connectedRef.current) {
        wsLogger.debug('WebSocket-Verbindung wird hergestellt');
        getWebSocketClient().connect(token);
        connectedRef.current = true;
      }
    } else {
      if (connectedRef.current) {
        wsLogger.debug('WebSocket-Verbindung wird getrennt');
        getWebSocketClient().disconnect();
        connectedRef.current = false;
      }
    }

    return () => {
      if (connectedRef.current) {
        getWebSocketClient().disconnect();
        connectedRef.current = false;
      }
    };
  }, [isAuthenticated]);
}
