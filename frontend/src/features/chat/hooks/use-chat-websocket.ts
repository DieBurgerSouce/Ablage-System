/**
 * WebSocket Hook für Chat Real-time Collaboration.
 *
 * Bietet:
 * - Automatische Verbindung/Reconnection
 * - Typing-Indikatoren
 * - Presence-Tracking
 * - AI-Streaming-Empfang
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { logger } from '@/lib/logger';
import type {
    WSMessage,
    WSPresenceUser,
    WSPresenceUpdate,
    WSNewMessage,
    WSTypingUpdate,
    WSUserJoinLeave,
    WSAIChunk,
    WSAIDone,
    ChatMessage,
} from '@/lib/api/chat-api';

// ============================================================================
// TYPES
// ============================================================================

interface UseChatWebSocketOptions {
    /** Session ID zum Verbinden (null = keine Verbindung) */
    sessionId: string | null;
    /** Callback wenn neue Nachricht empfangen */
    onNewMessage?: (message: ChatMessage) => void;
    /** Callback wenn Typing-Update empfangen */
    onTypingUpdate?: (userId: string, username: string, isTyping: boolean) => void;
    /** Callback wenn Presence-Update empfangen */
    onPresenceUpdate?: (users: WSPresenceUser[]) => void;
    /** Callback wenn User beitritt */
    onUserJoined?: (userId: string, username: string) => void;
    /** Callback wenn User verlässt */
    onUserLeft?: (userId: string, username: string) => void;
    /** Callback für AI-Streaming-Chunk */
    onAIChunk?: (chunk: string, messageId?: string) => void;
    /** Callback wenn AI-Streaming fertig */
    onAIDone?: (messageId: string, fullContent: string) => void;
    /** Callback bei Verbindungsstatus-Änderung */
    onConnectionChange?: (connected: boolean) => void;
    /** Callback bei Fehler */
    onError?: (error: string) => void;
    /** WebSocket aktivieren (default: false) */
    enabled?: boolean;
}

interface UseChatWebSocketReturn {
    /** Verbindungsstatus */
    isConnected: boolean;
    /** Aktuell online User */
    onlineUsers: WSPresenceUser[];
    /** Verbindung manuell trennen */
    disconnect: () => void;
    /** Typing-Status senden */
    sendTyping: (isTyping: boolean) => void;
    /** Presence anfordern */
    requestPresence: () => void;
}

// ============================================================================
// CONSTANTS
// ============================================================================

const RECONNECT_INTERVAL = 3000; // 3 Sekunden
const MAX_RECONNECT_ATTEMPTS = 5;
const PING_INTERVAL = 30000; // 30 Sekunden

// ============================================================================
// HOOK
// ============================================================================

export function useChatWebSocket(
    options: UseChatWebSocketOptions
): UseChatWebSocketReturn {
    const {
        sessionId,
        onNewMessage,
        onTypingUpdate,
        onPresenceUpdate,
        onUserJoined,
        onUserLeft,
        onAIChunk,
        onAIDone,
        onConnectionChange,
        onError,
        enabled = false, // Default deaktiviert um Endlos-Reconnect zu vermeiden
    } = options;

    const [isConnected, setIsConnected] = useState(false);
    const [onlineUsers, setOnlineUsers] = useState<WSPresenceUser[]>([]);

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Refs für Callbacks um sie nicht in Dependencies aufnehmen zu müssen
    const callbacksRef = useRef({
        onNewMessage,
        onTypingUpdate,
        onPresenceUpdate,
        onUserJoined,
        onUserLeft,
        onAIChunk,
        onAIDone,
        onConnectionChange,
        onError,
    });

    // Callbacks aktualisieren
    useEffect(() => {
        callbacksRef.current = {
            onNewMessage,
            onTypingUpdate,
            onPresenceUpdate,
            onUserJoined,
            onUserLeft,
            onAIChunk,
            onAIDone,
            onConnectionChange,
            onError,
        };
    });

    // Cleanup-Funktion
    const cleanup = useCallback(() => {
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
        }
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }
    }, []);

    // Nachricht verarbeiten
    const handleMessage = useCallback(
        (data: WSMessage, currentSessionId: string) => {
            const callbacks = callbacksRef.current;

            switch (data.type) {
                case 'presence': {
                    const presenceData = data as WSPresenceUpdate;
                    setOnlineUsers(presenceData.users);
                    callbacks.onPresenceUpdate?.(presenceData.users);
                    break;
                }

                case 'new_message': {
                    const msgData = data as WSNewMessage;
                    const chatMessage: ChatMessage = {
                        id: msgData.message.id,
                        session_id: currentSessionId,
                        role: msgData.message.role,
                        content: msgData.message.content,
                        created_at: msgData.message.created_at,
                    };
                    callbacks.onNewMessage?.(chatMessage);
                    break;
                }

                case 'typing_start': {
                    const typingData = data as WSTypingUpdate;
                    callbacks.onTypingUpdate?.(typingData.user_id, typingData.username, true);
                    break;
                }

                case 'typing_stop': {
                    const typingData = data as WSTypingUpdate;
                    callbacks.onTypingUpdate?.(typingData.user_id, typingData.username, false);
                    break;
                }

                case 'user_joined': {
                    const joinData = data as WSUserJoinLeave;
                    callbacks.onUserJoined?.(joinData.user_id, joinData.username);
                    break;
                }

                case 'user_left': {
                    const leaveData = data as WSUserJoinLeave;
                    callbacks.onUserLeft?.(leaveData.user_id, leaveData.username);
                    break;
                }

                case 'ai_chunk': {
                    const chunkData = data as WSAIChunk;
                    callbacks.onAIChunk?.(chunkData.chunk, chunkData.message_id);
                    break;
                }

                case 'ai_done': {
                    const doneData = data as WSAIDone;
                    callbacks.onAIDone?.(doneData.message_id, doneData.full_content);
                    break;
                }

                case 'error': {
                    const errorMsg = (data as { message?: string }).message || 'Unbekannter Fehler';
                    callbacks.onError?.(errorMsg);
                    break;
                }

                case 'pong':
                    // Keep-alive response, nichts zu tun
                    break;

                default:
                    logger.debug('Unbekannter WebSocket-Nachrichtentyp', { type: data.type });
            }
        },
        []
    );

    // Verbindung trennen
    const disconnect = useCallback(() => {
        cleanup();
        if (wsRef.current) {
            wsRef.current.close(1000);
            wsRef.current = null;
        }
        setIsConnected(false);
        setOnlineUsers([]);
    }, [cleanup]);

    // Typing-Status senden
    const sendTyping = useCallback((isTyping: boolean) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(
                JSON.stringify({
                    type: isTyping ? 'typing_start' : 'typing_stop',
                })
            );
        }
    }, []);

    // Presence anfordern
    const requestPresence = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'get_presence' }));
        }
    }, []);

    // Verbindung aufbauen wenn sessionId sich ändert
    // WICHTIG: Nur sessionId und enabled als Dependencies!
    useEffect(() => {
        // Nicht verbinden wenn deaktiviert
        if (!enabled || !sessionId) {
            return;
        }

        // Cookie-Auth (G03): Kein JS-Token mehr noetig — das Auth-Cookie wird beim
        // Same-Origin-WebSocket-Handshake automatisch mitgesendet. Fehlt das
        // Cookie, schliesst der Server die Verbindung selbst (Code 4001/4003).
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/api/v1/rag/ws/chat/${sessionId}`;

        let ws: WebSocket | null = null;
        let localPingInterval: ReturnType<typeof setInterval> | null = null;
        let localReconnectTimeout: ReturnType<typeof setTimeout> | null = null;
        let reconnectAttempts = 0;
        let isMounted = true;

        const scheduleReconnect = () => {
            if (!isMounted || reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
                    callbacksRef.current.onError?.('Maximale Verbindungsversuche erreicht');
                }
                return;
            }

            reconnectAttempts += 1;
            const delay = RECONNECT_INTERVAL * Math.pow(2, reconnectAttempts - 1);

            localReconnectTimeout = setTimeout(() => {
                if (isMounted) {
                    connectWs();
                }
            }, delay);
        };

        const connectWs = () => {
            if (!isMounted) return;

            try {
                ws = new WebSocket(wsUrl);
                wsRef.current = ws;

                ws.onopen = () => {
                    if (!isMounted) return;
                    setIsConnected(true);
                    reconnectAttempts = 0;
                    callbacksRef.current.onConnectionChange?.(true);

                    // Ping-Intervall starten
                    localPingInterval = setInterval(() => {
                        if (ws?.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ type: 'ping' }));
                        }
                    }, PING_INTERVAL);
                    pingIntervalRef.current = localPingInterval;
                };

                ws.onmessage = (event) => {
                    if (!isMounted) return;
                    try {
                        const data = JSON.parse(event.data) as WSMessage;
                        handleMessage(data, sessionId);
                    } catch (e) {
                        logger.error('WebSocket-Nachricht konnte nicht geparst werden', e);
                    }
                };

                ws.onclose = (event) => {
                    if (!isMounted) return;
                    setIsConnected(false);
                    callbacksRef.current.onConnectionChange?.(false);

                    if (localPingInterval) {
                        clearInterval(localPingInterval);
                        localPingInterval = null;
                    }

                    // Reconnect wenn nicht absichtlich geschlossen
                    if (event.code !== 1000 && event.code !== 4001 && event.code !== 4003) {
                        scheduleReconnect();
                    }
                };

                ws.onerror = () => {
                    if (!isMounted) return;
                    // Fehler nur loggen, nicht an User zeigen (onclose kommt danach)
                    logger.debug('WebSocket Fehler-Event');
                };
            } catch (e) {
                logger.error('WebSocket-Verbindungsfehler', e);
                if (isMounted) {
                    scheduleReconnect();
                }
            }
        };

        connectWs();

        return () => {
            isMounted = false;
            if (localPingInterval) {
                clearInterval(localPingInterval);
            }
            if (localReconnectTimeout) {
                clearTimeout(localReconnectTimeout);
            }
            if (ws) {
                ws.close(1000);
            }
            wsRef.current = null;
            setIsConnected(false);
            setOnlineUsers([]);
        };
    }, [sessionId, enabled, handleMessage]);

    return {
        isConnected,
        onlineUsers,
        disconnect,
        sendTyping,
        requestPresence,
    };
}

export default useChatWebSocket;
