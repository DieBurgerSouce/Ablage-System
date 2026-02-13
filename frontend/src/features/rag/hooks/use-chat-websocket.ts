/**
 * WebSocket Chat Hook
 *
 * Manages WebSocket connection for real-time chat with:
 * - Automatic reconnection
 * - Token streaming
 * - Connection state management
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { logger } from '@/lib/logger';
import type {
    ChatMessage,
    ContextDocument,
    ConnectionStatus,
    WSMessage,
    ChatMessageSource,
} from '../types/chat-types';

// ==================== Types ====================

interface UseChatWebSocketOptions {
    sessionId?: string;
    onConnected?: (sessionId: string) => void;
    onMessage?: (message: ChatMessage) => void;
    onError?: (error: string) => void;
    autoConnect?: boolean;
    maxReconnectAttempts?: number;
}

interface UseChatWebSocketReturn {
    // Connection state
    status: ConnectionStatus;
    sessionId: string | null;
    error: string | null;

    // Messages
    messages: ChatMessage[];
    isStreaming: boolean;
    streamingContent: string;
    contextDocuments: ContextDocument[];
    statusMessage: string | null;

    // Actions
    connect: (sessionId?: string) => void;
    disconnect: () => void;
    sendMessage: (content: string) => void;
    clearHistory: () => void;
    getHistory: () => void;
}

// ==================== Constants ====================

const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/rag`;
const RECONNECT_DELAY = 2000;
const MAX_RECONNECT_ATTEMPTS = 5;
const PING_INTERVAL = 30000;

// ==================== Hook ====================

export function useChatWebSocket(
    options: UseChatWebSocketOptions = {}
): UseChatWebSocketReturn {
    const {
        sessionId: initialSessionId,
        onConnected,
        onMessage,
        onError,
        autoConnect = false,
        maxReconnectAttempts = MAX_RECONNECT_ATTEMPTS,
    } = options;

    // Connection state
    const [status, setStatus] = useState<ConnectionStatus>('disconnected');
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const reconnectAttempt = useRef(0);

    // Message state
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [streamingContent, setStreamingContent] = useState('');
    const [contextDocuments, setContextDocuments] = useState<ContextDocument[]>([]);
    const [statusMessage, setStatusMessage] = useState<string | null>(null);

    // Refs
    const wsRef = useRef<WebSocket | null>(null);
    const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const currentStreamingId = useRef<string | null>(null);

    // ==================== Cleanup ====================

    const cleanup = useCallback(() => {
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
    }, []);

    // ==================== Message Handlers ====================

    const handleMessage = useCallback(
        (event: MessageEvent) => {
            try {
                const data: WSMessage = JSON.parse(event.data);

                switch (data.type) {
                    case 'connected':
                        setStatus('connected');
                        setSessionId(data.session_id);
                        setError(null);
                        reconnectAttempt.current = 0;
                        onConnected?.(data.session_id);
                        break;

                    case 'token':
                        setStreamingContent((prev) => prev + data.content);
                        break;

                    case 'message_complete': {
                        const completeMessage: ChatMessage = {
                            id: data.message_id,
                            role: 'assistant',
                            content: data.content,
                            timestamp: data.timestamp,
                            sources: data.sources,
                            isStreaming: false,
                        };
                        setMessages((prev) => {
                            // Replace streaming message with complete one
                            const filtered = prev.filter(
                                (m) => m.id !== currentStreamingId.current
                            );
                            return [...filtered, completeMessage];
                        });
                        setIsStreaming(false);
                        setStreamingContent('');
                        setStatusMessage(null);
                        currentStreamingId.current = null;
                        onMessage?.(completeMessage);
                        break;
                    }

                    case 'context':
                        setContextDocuments(data.documents);
                        break;

                    case 'processing':
                    case 'generating':
                        setStatusMessage(data.message);
                        if (data.type === 'generating') {
                            setIsStreaming(true);
                            setStreamingContent('');
                            // Add placeholder for streaming message
                            const streamingId = `streaming-${Date.now()}`;
                            currentStreamingId.current = streamingId;
                            setMessages((prev) => [
                                ...prev,
                                {
                                    id: streamingId,
                                    role: 'assistant',
                                    content: '',
                                    timestamp: new Date().toISOString(),
                                    isStreaming: true,
                                },
                            ]);
                        }
                        break;

                    case 'error':
                        setError(data.message);
                        setIsStreaming(false);
                        setStatusMessage(null);
                        onError?.(data.message);
                        break;

                    case 'history':
                        setMessages(data.messages);
                        break;

                    case 'history_cleared':
                        setMessages([]);
                        break;

                    case 'pong':
                        // Connection is alive
                        break;
                }
            } catch (e) {
                logger.error('WebSocket-Nachricht konnte nicht verarbeitet werden', e);
            }
        },
        [onConnected, onMessage, onError]
    );

    // ==================== Connect ====================

    const connect = useCallback(
        (targetSessionId?: string) => {
            cleanup();

            const token = sessionStorage.getItem('auth_token');
            if (!token) {
                setError('Nicht authentifiziert');
                setStatus('error');
                return;
            }

            const sid = targetSessionId || initialSessionId || 'new';
            const wsUrl = `${WS_BASE}/ws/chat/${sid}?token=${encodeURIComponent(token)}`;

            setStatus('connecting');
            setError(null);

            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                // Start ping interval
                pingIntervalRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ type: 'ping' }));
                    }
                }, PING_INTERVAL);
            };

            ws.onmessage = handleMessage;

            ws.onclose = (event) => {
                cleanup();
                setStatus('disconnected');

                // Attempt reconnect if not intentional close
                if (event.code !== 1000 && event.code !== 1001) {
                    if (reconnectAttempt.current < maxReconnectAttempts) {
                        reconnectAttempt.current += 1;
                        setTimeout(() => connect(sid), RECONNECT_DELAY);
                    } else {
                        setError('Verbindung verloren. Bitte Seite neu laden.');
                        setStatus('error');
                    }
                }
            };

            ws.onerror = () => {
                setError('WebSocket-Verbindungsfehler');
                setStatus('error');
            };
        },
        [cleanup, handleMessage, initialSessionId, maxReconnectAttempts]
    );

    // ==================== Disconnect ====================

    const disconnect = useCallback(() => {
        cleanup();
        setStatus('disconnected');
        setSessionId(null);
        reconnectAttempt.current = 0;
    }, [cleanup]);

    // ==================== Send Message ====================

    const sendMessage = useCallback(
        (content: string) => {
            if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
                setError('Nicht verbunden');
                return;
            }

            // Add user message to state
            const userMessage: ChatMessage = {
                id: `user-${Date.now()}`,
                role: 'user',
                content,
                timestamp: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, userMessage]);

            // Send via WebSocket
            wsRef.current.send(
                JSON.stringify({
                    type: 'message',
                    content,
                })
            );
        },
        []
    );

    // ==================== Clear History ====================

    const clearHistory = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
            setError('Nicht verbunden');
            return;
        }

        wsRef.current.send(JSON.stringify({ type: 'clear_history' }));
    }, []);

    // ==================== Get History ====================

    const getHistory = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
            setError('Nicht verbunden');
            return;
        }

        wsRef.current.send(JSON.stringify({ type: 'get_history' }));
    }, []);

    // ==================== Auto-connect ====================

    useEffect(() => {
        if (autoConnect) {
            connect();
        }

        return () => {
            cleanup();
        };
    }, [autoConnect, connect, cleanup]);

    // ==================== Update streaming message ====================

    useEffect(() => {
        if (isStreaming && currentStreamingId.current && streamingContent) {
            setMessages((prev) =>
                prev.map((m) =>
                    m.id === currentStreamingId.current
                        ? { ...m, content: streamingContent }
                        : m
                )
            );
        }
    }, [isStreaming, streamingContent]);

    return {
        status,
        sessionId,
        error,
        messages,
        isStreaming,
        streamingContent,
        contextDocuments,
        statusMessage,
        connect,
        disconnect,
        sendMessage,
        clearHistory,
        getHistory,
    };
}

export default useChatWebSocket;
