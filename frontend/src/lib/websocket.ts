/**
 * WebSocket Client fuer Echtzeit-Updates.
 *
 * Features:
 * - Automatische Reconnection mit exponential backoff
 * - Event Subscriptions
 * - Heartbeat/Ping-Pong
 * - Event History bei Reconnection
 * - React Hooks fuer einfache Integration
 */

import { useEffect, useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

// ============================================================================
// Types
// ============================================================================

export type RealtimeEventType =
  // Document Events
  | 'document.uploaded'
  | 'document.ocr_started'
  | 'document.ocr_progress'
  | 'document.ocr_completed'
  | 'document.categorized'
  | 'document.deleted'
  | 'document.updated'
  // Validation Events
  | 'validation.item_added'
  | 'validation.item_resolved'
  | 'validation.queue_updated'
  // Approval Events
  | 'approval.requested'
  | 'approval.approved'
  | 'approval.rejected'
  | 'approval.escalated'
  // Finance Events
  | 'invoice.created'
  | 'invoice.paid'
  | 'invoice.overdue'
  | 'payment.received'
  | 'cashflow.updated'
  | 'budget.alert'
  // Banking Events
  | 'transaction.imported'
  | 'reconciliation.match'
  | 'dunning.escalated'
  // Entity Events
  | 'entity.linked'
  | 'entity.risk_changed'
  // System Events
  | 'system.notification'
  | 'system.error'
  | 'system.maintenance'
  // User Events
  | 'user.task_assigned'
  | 'user.mention';

export interface RealtimeEvent {
  event_type: RealtimeEventType;
  payload: Record<string, unknown>;
  event_id: string;
  timestamp: string;
  priority: 'low' | 'normal' | 'high' | 'critical';
}

export interface WSMessage {
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

export type EventHandler = (event: RealtimeEvent) => void;

// ============================================================================
// WebSocket Client Class
// ============================================================================

class RealtimeWebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private token: string | null = null;
  private state: ConnectionState = 'disconnected';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000; // Start with 1 second
  private maxReconnectDelay = 30000; // Max 30 seconds
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private lastEventTimestamp: string | null = null;

  // Event handlers
  private eventHandlers: Map<RealtimeEventType | '*', Set<EventHandler>> = new Map();
  private stateChangeHandlers: Set<(state: ConnectionState) => void> = new Set();

  constructor(baseUrl?: string) {
    // Determine WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = baseUrl || window.location.host;
    this.url = `${wsProtocol}//${host}/api/v1/ws/realtime`;
  }

  // ---------------------------------------------------------------------------
  // Public Methods
  // ---------------------------------------------------------------------------

  connect(token: string): void {
    if (this.state === 'connected' || this.state === 'connecting') {
      return;
    }

    this.token = token;
    this.setState('connecting');
    this.createConnection();
  }

  disconnect(): void {
    this.stopPingInterval();

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.setState('disconnected');
    this.reconnectAttempts = 0;
  }

  subscribe(eventType: RealtimeEventType | '*', handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);

    // Send subscribe message if connected
    if (this.state === 'connected' && eventType !== '*') {
      this.send({ type: 'subscribe', event_types: [eventType] });
    }

    // Return unsubscribe function
    return () => {
      const handlers = this.eventHandlers.get(eventType);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          this.eventHandlers.delete(eventType);
        }
      }
    };
  }

  onStateChange(handler: (state: ConnectionState) => void): () => void {
    this.stateChangeHandlers.add(handler);
    return () => {
      this.stateChangeHandlers.delete(handler);
    };
  }

  getState(): ConnectionState {
    return this.state;
  }

  // ---------------------------------------------------------------------------
  // Private Methods
  // ---------------------------------------------------------------------------

  private createConnection(): void {
    const wsUrl = `${this.url}?token=${this.token}`;

    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventListeners();
    } catch (error) {
      console.error('WebSocket creation failed:', error);
      this.handleReconnect();
    }
  }

  private setupEventListeners(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.setState('connected');
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;
      this.startPingInterval();

      // Request event history if reconnecting
      if (this.lastEventTimestamp) {
        this.send({
          type: 'get_history',
          since: this.lastEventTimestamp,
        });
      }

      // Re-subscribe to all event types
      const eventTypes = Array.from(this.eventHandlers.keys()).filter(
        (t) => t !== '*'
      ) as RealtimeEventType[];
      if (eventTypes.length > 0) {
        this.send({ type: 'subscribe', event_types: eventTypes });
      }
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason);
      this.stopPingInterval();

      if (event.code !== 1000) {
        // Abnormal close, try to reconnect
        this.handleReconnect();
      } else {
        this.setState('disconnected');
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
  }

  private handleMessage(message: WSMessage): void {
    switch (message.type) {
      case 'connected':
        console.log('WebSocket authenticated:', message.payload);
        break;

      case 'pong':
        // Server responded to ping
        break;

      case 'ping':
        // Server ping, respond with pong
        this.send({ type: 'pong' });
        break;

      case 'event':
        this.handleEvent(message.payload as unknown as RealtimeEvent);
        break;

      case 'history':
        this.handleHistory(message.payload as { events: RealtimeEvent[] });
        break;

      case 'subscribed':
        console.log('Subscribed to events:', message.payload);
        break;

      case 'unsubscribed':
        console.log('Unsubscribed from events:', message.payload);
        break;

      default:
        console.log('Unknown message type:', message.type);
    }
  }

  private handleEvent(event: RealtimeEvent): void {
    // Update last event timestamp for reconnection
    this.lastEventTimestamp = event.timestamp;

    // Call specific handlers
    const handlers = this.eventHandlers.get(event.event_type);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(event);
        } catch (error) {
          console.error('Event handler error:', error);
        }
      });
    }

    // Call wildcard handlers
    const wildcardHandlers = this.eventHandlers.get('*');
    if (wildcardHandlers) {
      wildcardHandlers.forEach((handler) => {
        try {
          handler(event);
        } catch (error) {
          console.error('Wildcard handler error:', error);
        }
      });
    }
  }

  private handleHistory(payload: { events: RealtimeEvent[] }): void {
    // Process missed events
    payload.events.forEach((event) => {
      this.handleEvent(event);
    });
  }

  private handleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached');
      this.setState('disconnected');
      return;
    }

    this.setState('reconnecting');
    this.reconnectAttempts++;

    // Exponential backoff
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      if (this.state === 'reconnecting' && this.token) {
        this.createConnection();
      }
    }, delay);
  }

  private send(data: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private startPingInterval(): void {
    this.stopPingInterval();
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping' });
    }, 25000); // Ping every 25 seconds
  }

  private stopPingInterval(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private setState(state: ConnectionState): void {
    if (this.state !== state) {
      this.state = state;
      this.stateChangeHandlers.forEach((handler) => {
        try {
          handler(state);
        } catch (error) {
          console.error('State change handler error:', error);
        }
      });
    }
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

let wsClientInstance: RealtimeWebSocketClient | null = null;

export function getWebSocketClient(): RealtimeWebSocketClient {
  if (!wsClientInstance) {
    wsClientInstance = new RealtimeWebSocketClient();
  }
  return wsClientInstance;
}

// ============================================================================
// React Hooks
// ============================================================================

/**
 * Hook fuer WebSocket-Verbindungsstatus.
 *
 * @example
 * const { state, connect, disconnect } = useWebSocket();
 */
export function useWebSocket() {
  const [state, setState] = useState<ConnectionState>('disconnected');
  const client = useRef(getWebSocketClient());

  useEffect(() => {
    const unsubscribe = client.current.onStateChange(setState);
    setState(client.current.getState());
    return unsubscribe;
  }, []);

  const connect = useCallback((token: string) => {
    client.current.connect(token);
  }, []);

  const disconnect = useCallback(() => {
    client.current.disconnect();
  }, []);

  return { state, connect, disconnect };
}

/**
 * Hook fuer Event-Subscriptions.
 *
 * @param eventType - Event-Typ oder '*' fuer alle Events
 * @param handler - Event Handler Funktion
 *
 * @example
 * useRealtimeEvent('document.ocr_completed', (event) => {
 *   console.log('OCR completed:', event.payload);
 * });
 */
export function useRealtimeEvent(
  eventType: RealtimeEventType | '*',
  handler: EventHandler
): void {
  const client = useRef(getWebSocketClient());
  const handlerRef = useRef(handler);

  // Update handler ref
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    const wrappedHandler = (event: RealtimeEvent) => {
      handlerRef.current(event);
    };

    const unsubscribe = client.current.subscribe(eventType, wrappedHandler);
    return unsubscribe;
  }, [eventType]);
}

/**
 * Hook fuer Event-Subscriptions mit Query Invalidation.
 *
 * Invalidiert automatisch React Query Caches bei bestimmten Events.
 *
 * @param eventType - Event-Typ
 * @param queryKeys - Query Keys die invalidiert werden sollen
 *
 * @example
 * useRealtimeInvalidation('document.ocr_completed', [['documents']]);
 */
export function useRealtimeInvalidation(
  eventType: RealtimeEventType,
  queryKeys: string[][]
): void {
  const queryClient = useQueryClient();

  useRealtimeEvent(eventType, () => {
    queryKeys.forEach((key) => {
      queryClient.invalidateQueries({ queryKey: key });
    });
  });
}

/**
 * Hook fuer alle Events mit automatischer Cache-Invalidation.
 *
 * Optimiert fuer Dashboard-Nutzung mit intelligenter Query-Invalidation.
 *
 * @example
 * useRealtimeDashboard();
 */
export function useRealtimeDashboard(): void {
  const queryClient = useQueryClient();

  useRealtimeEvent('*', (event) => {
    // Map event types to query keys for intelligent invalidation
    const invalidationMap: Partial<Record<RealtimeEventType, string[][]>> = {
      'document.uploaded': [['documents'], ['dashboard']],
      'document.ocr_completed': [['documents'], ['dashboard'], ['validation-queue']],
      'document.categorized': [['documents']],
      'validation.item_added': [['validation-queue']],
      'validation.item_resolved': [['validation-queue']],
      'validation.queue_updated': [['validation-queue']],
      'approval.requested': [['approvals']],
      'approval.approved': [['approvals']],
      'approval.rejected': [['approvals']],
      'invoice.created': [['invoices'], ['finance']],
      'invoice.paid': [['invoices'], ['finance'], ['cashflow']],
      'invoice.overdue': [['invoices'], ['finance']],
      'transaction.imported': [['transactions'], ['banking'], ['cashflow']],
      'cashflow.updated': [['cashflow'], ['finance']],
      'budget.alert': [['budgets'], ['finance']],
    };

    const queryKeysToInvalidate = invalidationMap[event.event_type];
    if (queryKeysToInvalidate) {
      queryKeysToInvalidate.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
    }
  });
}

/**
 * Hook fuer Event-Stream (alle Events sammeln).
 *
 * @param maxEvents - Maximale Anzahl Events im Buffer
 * @returns Array von Events (neueste zuerst)
 *
 * @example
 * const events = useEventStream(50);
 */
export function useEventStream(maxEvents = 50): RealtimeEvent[] {
  const [events, setEvents] = useState<RealtimeEvent[]>([]);

  useRealtimeEvent('*', (event) => {
    setEvents((prev) => {
      const newEvents = [event, ...prev];
      return newEvents.slice(0, maxEvents);
    });
  });

  return events;
}

/**
 * Hook fuer OCR Progress Tracking.
 *
 * @param documentId - Document ID
 * @returns Progress (0-100) und Stage
 *
 * @example
 * const { progress, stage } = useOCRProgress('doc-123');
 */
export function useOCRProgress(
  documentId: string
): { progress: number; stage: string } {
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('');

  useRealtimeEvent('document.ocr_progress', (event) => {
    if (event.payload.document_id === documentId) {
      setProgress((event.payload.progress as number) || 0);
      setStage((event.payload.stage as string) || '');
    }
  });

  useRealtimeEvent('document.ocr_completed', (event) => {
    if (event.payload.document_id === documentId) {
      setProgress(100);
      setStage('completed');
    }
  });

  return { progress, stage };
}

export default RealtimeWebSocketClient;
