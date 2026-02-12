/**
 * useRealtime - WebSocket Hook für Echtzeit-Collaboration
 *
 * Verwaltet die WebSocket-Verbindung für:
 * - Präsenz (wer betrachtet ein Dokument)
 * - Kommentar-Updates in Echtzeit
 * - Aktivitäts-Stream
 *
 * Features:
 * - Automatischer Reconnect mit Exponential Backoff
 * - Room-basierte Subscriptions (join/leave)
 * - Verbindungsstatus-Tracking
 * - Message-Handler-Registrierung
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { collaborationKeys } from '../api/collaboration-api';

// ==================== Types ====================

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface PresenceUser {
  userId: string;
  userName: string;
  userAvatar?: string;
  joinedAt: string;
}

export interface RealtimeMessage {
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

type MessageHandler = (message: RealtimeMessage) => void;

interface UseRealtimeOptions {
  /** WebSocket aktivieren */
  enabled?: boolean;
  /** Maximale Reconnect-Versuche */
  maxRetries?: number;
  /** Initiale Verzögerung zwischen Reconnects (ms) */
  retryDelay?: number;
  /** Callback bei Verbindungsstatus-Änderung */
  onStatusChange?: (status: ConnectionStatus) => void;
}

interface UseRealtimeReturn {
  /** Aktueller Verbindungsstatus */
  status: ConnectionStatus;
  /** In einem Dokument-Room anmelden */
  joinRoom: (roomId: string) => void;
  /** Einen Dokument-Room verlassen */
  leaveRoom: (roomId: string) => void;
  /** Message-Handler registrieren (gibt Unsubscribe-Funktion zurück) */
  onMessage: (handler: MessageHandler) => () => void;
  /** Verbindung manuell trennen */
  disconnect: () => void;
  /** Verbindung neu aufbauen */
  reconnect: () => void;
  /** Präsenz-User im aktuellen Room */
  presenceUsers: PresenceUser[];
}

// ==================== Hook ====================

export function useRealtime(options: UseRealtimeOptions = {}): UseRealtimeReturn {
  const queryClient = useQueryClient();

  const stableOpts = useMemo(
    () => ({
      enabled: options.enabled ?? true,
      maxRetries: options.maxRetries ?? 8,
      retryDelay: options.retryDelay ?? 1000,
    }),
    [options.enabled, options.maxRetries, options.retryDelay],
  );

  const onStatusChangeRef = useRef(options.onStatusChange);
  useEffect(() => {
    onStatusChangeRef.current = options.onStatusChange;
  }, [options.onStatusChange]);

  // State
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [presenceUsers, setPresenceUsers] = useState<PresenceUser[]>([]);

  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlersRef = useRef<Set<MessageHandler>>(new Set());
  const joinedRoomsRef = useRef<Set<string>>(new Set());

  // Update status and notify
  const updateStatus = useCallback((newStatus: ConnectionStatus) => {
    setStatus(newStatus);
    onStatusChangeRef.current?.(newStatus);
  }, []);

  // Send JSON message to WebSocket
  const sendMessage = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  // Handle incoming messages
  const handleMessage = useCallback(
    (message: RealtimeMessage) => {
      // Dispatch to all registered handlers
      handlersRef.current.forEach((handler) => {
        try {
          handler(message);
        } catch {
          // Handler errors should not break the connection
        }
      });

      // Built-in handling for presence and comment updates
      switch (message.type) {
        case 'presence_update': {
          const users = message.payload.users as PresenceUser[] | undefined;
          if (users) {
            setPresenceUsers(users);
          }
          break;
        }
        case 'user_joined': {
          const user = message.payload as unknown as PresenceUser;
          if (user?.userId) {
            setPresenceUsers((prev) => {
              if (prev.some((u) => u.userId === user.userId)) return prev;
              return [...prev, user];
            });
          }
          break;
        }
        case 'user_left': {
          const userId = message.payload.userId as string;
          if (userId) {
            setPresenceUsers((prev) => prev.filter((u) => u.userId !== userId));
          }
          break;
        }
        case 'event': {
          // Delegate to the existing realtime websocket system for query invalidation
          const eventType = message.payload.event_type as string;
          if (eventType?.startsWith('comment.')) {
            const docId = message.payload.payload
              ? (message.payload.payload as Record<string, unknown>).document_id as string
              : undefined;
            if (docId) {
              queryClient.invalidateQueries({
                queryKey: collaborationKeys.comments(docId),
              });
            }
          }
          break;
        }
      }
    },
    [queryClient],
  );

  // Use a ref to hold the connect function to avoid circular dependency
  const connectRef = useRef<() => void>(() => {});

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!stableOpts.enabled) return;
    if (wsRef.current) {
      wsRef.current.close();
    }

    updateStatus('connecting');

    const token = sessionStorage.getItem('auth_token');
    if (!token) {
      updateStatus('error');
      return;
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${wsProtocol}//${host}/api/v1/ws/realtime?token=${encodeURIComponent(token)}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        updateStatus('connected');
        retryCountRef.current = 0;

        // Re-join all previously joined rooms
        joinedRoomsRef.current.forEach((roomId) => {
          sendMessage({ type: 'join_room', room_id: roomId });
        });
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as RealtimeMessage;
          handleMessage(message);
        } catch {
          // Ignore parse errors
        }
      };

      ws.onerror = () => {
        updateStatus('error');
      };

      ws.onclose = (event) => {
        wsRef.current = null;

        if (event.code === 1000) {
          updateStatus('disconnected');
          return;
        }

        // Exponential backoff reconnect
        if (retryCountRef.current < stableOpts.maxRetries) {
          const delay = stableOpts.retryDelay * Math.pow(2, retryCountRef.current);
          retryCountRef.current++;
          retryTimeoutRef.current = setTimeout(() => connectRef.current(), delay);
          updateStatus('connecting');
        } else {
          updateStatus('error');
        }
      };
    } catch {
      updateStatus('error');
    }
  }, [stableOpts, handleMessage, sendMessage, updateStatus]);

  // Keep connectRef in sync (must be in useEffect, not render)
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Disconnect
  const disconnect = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    updateStatus('disconnected');
    setPresenceUsers([]);
  }, [updateStatus]);

  // Reconnect
  const reconnect = useCallback(() => {
    retryCountRef.current = 0;
    disconnect();
    connect();
  }, [connect, disconnect]);

  // Join a document room
  const joinRoom = useCallback(
    (roomId: string) => {
      joinedRoomsRef.current.add(roomId);
      sendMessage({ type: 'join_room', room_id: roomId });
    },
    [sendMessage],
  );

  // Leave a document room
  const leaveRoom = useCallback(
    (roomId: string) => {
      joinedRoomsRef.current.delete(roomId);
      sendMessage({ type: 'leave_room', room_id: roomId });
      setPresenceUsers([]);
    },
    [sendMessage],
  );

  // Register a message handler
  const onMessage = useCallback((handler: MessageHandler): (() => void) => {
    handlersRef.current.add(handler);
    return () => {
      handlersRef.current.delete(handler);
    };
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    if (stableOpts.enabled) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- connect() manages external WS; setState is side-effect of WS lifecycle
      connect();
    }
    return () => {
      disconnect();
    };
  }, [stableOpts.enabled, connect, disconnect]);

  return {
    status,
    joinRoom,
    leaveRoom,
    onMessage,
    disconnect,
    reconnect,
    presenceUsers,
  };
}
