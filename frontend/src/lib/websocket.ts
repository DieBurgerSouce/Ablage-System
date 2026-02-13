/**
 * WebSocket Client für Echtzeit-Updates.
 *
 * Features:
 * - Automatische Reconnection mit exponential backoff
 * - Event Subscriptions
 * - Heartbeat/Ping-Pong
 * - Event History bei Reconnection
 * - React Hooks für einfache Integration
 */

import { useEffect, useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { logger } from './logger';

// Create WebSocket-specific logger
const wsLogger = logger.withLabels({ component: 'WebSocket' });

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
  | 'user.mention'
  // Comment Events (Collaboration)
  | 'comment.created'
  | 'comment.updated'
  | 'comment.deleted'
  | 'comment.replied'
  | 'comment.reaction_added'
  | 'comment.reaction_removed'
  // Widget Events (Real-time Updates)
  | 'widget.update'
  | 'widget.data_changed'
  | 'widget.refresh_required'
  // Notification Events (Phase C)
  | 'notification.received'
  // Import Events (Email/Folder Import)
  | 'import.started'
  | 'import.progress'
  | 'import.completed'
  | 'import.error';

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
    this.reconnectAttempts = 0;
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
    // Frischen Token aus sessionStorage holen (falls refreshed)
    const freshToken = sessionStorage.getItem('auth_token');
    if (freshToken) {
      this.token = freshToken;
    }
    const wsUrl = `${this.url}?token=${this.token}`;

    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventListeners();
    } catch (error) {
      wsLogger.error('WebSocket creation failed', error);
      this.handleReconnect();
    }
  }

  private setupEventListeners(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      wsLogger.debug('WebSocket connected');
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
      wsLogger.debug('WebSocket closed', { code: event.code, reason: event.reason });
      this.stopPingInterval();

      if (event.code !== 1000) {
        // Abnormal close, try to reconnect
        this.handleReconnect();
      } else {
        this.setState('disconnected');
      }
    };

    this.ws.onerror = (error) => {
      wsLogger.error('WebSocket error', error);
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        wsLogger.error('Failed to parse WebSocket message', error);
      }
    };
  }

  private handleMessage(message: WSMessage): void {
    switch (message.type) {
      case 'connected':
        wsLogger.debug('WebSocket authenticated', message.payload);
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
        wsLogger.debug('Subscribed to events', message.payload);
        break;

      case 'unsubscribed':
        wsLogger.debug('Unsubscribed from events', message.payload);
        break;

      default:
        wsLogger.debug('Unknown message type', { type: message.type });
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
          wsLogger.error('Event handler error', error);
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
          wsLogger.error('Wildcard handler error', error);
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
      wsLogger.error('Max reconnect attempts reached');
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

    wsLogger.debug('Reconnecting', { delay, attempt: this.reconnectAttempts });

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
          wsLogger.error('State change handler error', error);
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
 * Hook für WebSocket-Verbindungsstatus.
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
 * Hook für Event-Subscriptions.
 *
 * @param eventType - Event-Typ oder '*' für alle Events
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
 * Hook für Event-Subscriptions mit Query Invalidation.
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
 * Hook für alle Events mit automatischer Cache-Invalidation.
 *
 * Optimiert für Dashboard-Nutzung mit intelligenter Query-Invalidation.
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
      // Notification Events
      'notification.received': [['notifications']],
      // Import Events
      'import.started': [['email-import'], ['email-history']],
      'import.progress': [['email-import']],
      'import.completed': [['email-import'], ['email-history'], ['email-stats'], ['documents']],
      'import.error': [['email-import'], ['email-history'], ['email-stats']],
      // Comment Events
      'comment.created': [['comments'], ['documents']],
      'comment.updated': [['comments']],
      'comment.deleted': [['comments']],
      'comment.replied': [['comments']],
      'comment.reaction_added': [['comments']],
      'comment.reaction_removed': [['comments']],
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
 * Hook für Event-Stream (alle Events sammeln).
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
 * Hook für OCR Progress Tracking.
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

/**
 * Hook für Kommentar-Echtzeit-Updates auf einer Dokument-Seite.
 *
 * Abonniert alle Comment-Events für ein bestimmtes Dokument und
 * invalidiert automatisch die relevanten Query-Caches.
 *
 * @param documentId - Document ID für das Kommentare überwacht werden
 * @param onNewComment - Optional: Callback bei neuen Kommentaren (z.B. für Toast)
 * @param onReply - Optional: Callback bei Antworten auf Threads
 *
 * @example
 * useCommentRealtime(documentId, {
 *   onNewComment: (event) => toast.info('Neuer Kommentar von ' + event.payload.user_name),
 *   onReply: (event) => toast.info('Neue Antwort im Thread'),
 * });
 */
export function useCommentRealtime(
  documentId: string,
  options?: {
    onNewComment?: (event: RealtimeEvent) => void;
    onReply?: (event: RealtimeEvent) => void;
    onUpdate?: (event: RealtimeEvent) => void;
    onDelete?: (event: RealtimeEvent) => void;
    onReaction?: (event: RealtimeEvent) => void;
  }
): void {
  const queryClient = useQueryClient();
  const optionsRef = useRef(options);

  // Update options ref
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  // Comment Created
  useRealtimeEvent('comment.created', (event) => {
    if (event.payload.document_id === documentId) {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      optionsRef.current?.onNewComment?.(event);
    }
  });

  // Comment Replied (Thread)
  useRealtimeEvent('comment.replied', (event) => {
    if (event.payload.document_id === documentId) {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      // Auch den spezifischen Thread invalidieren
      if (event.payload.parent_id) {
        queryClient.invalidateQueries({
          queryKey: ['comments', 'thread', event.payload.parent_id],
        });
      }
      optionsRef.current?.onReply?.(event);
    }
  });

  // Comment Updated
  useRealtimeEvent('comment.updated', (event) => {
    if (event.payload.document_id === documentId) {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      optionsRef.current?.onUpdate?.(event);
    }
  });

  // Comment Deleted
  useRealtimeEvent('comment.deleted', (event) => {
    if (event.payload.document_id === documentId) {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      optionsRef.current?.onDelete?.(event);
    }
  });

  // Reactions
  useRealtimeEvent('comment.reaction_added', (event) => {
    if (event.payload.document_id === documentId) {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      optionsRef.current?.onReaction?.(event);
    }
  });

  useRealtimeEvent('comment.reaction_removed', (event) => {
    if (event.payload.document_id === documentId) {
      queryClient.invalidateQueries({ queryKey: ['comments', documentId] });
      optionsRef.current?.onReaction?.(event);
    }
  });
}

/**
 * Hook für User-Mentions Benachrichtigungen.
 *
 * Wird ausgelöst wenn der aktuelle User in einem Kommentar erwähnt wird.
 *
 * @param userId - User ID des aktuellen Benutzers
 * @param onMention - Callback bei Erwähnung
 *
 * @example
 * useMentionNotifications(currentUser.id, (event) => {
 *   toast.info(`${event.payload.mentioned_by_name} hat Sie erwähnt`);
 * });
 */
export function useMentionNotifications(
  userId: string,
  onMention: (event: RealtimeEvent) => void
): void {
  const onMentionRef = useRef(onMention);

  useEffect(() => {
    onMentionRef.current = onMention;
  }, [onMention]);

  useRealtimeEvent('user.mention', (event) => {
    if (event.payload.mentioned_user_id === userId) {
      onMentionRef.current(event);
    }
  });
}

// ============================================================================
// Widget Subscription Hooks (Phase 4.7)
// ============================================================================

/**
 * Widget-Typen für Echtzeit-Subscriptions.
 */
export type WidgetType =
  | 'cashflow'
  | 'recent_documents'
  | 'finance_status'
  | 'dunning'
  | 'ocr_performance'
  | 'aging_report'
  | 'skonto'
  | 'system_status'
  | 'today'
  | 'quick_links'
  | 'upload';

/**
 * Widget Update Event Payload.
 */
export interface WidgetUpdatePayload {
  widget_type: WidgetType;
  update_type: 'full' | 'partial' | 'refresh_hint';
  data?: Record<string, unknown>;
  changed_fields?: string[];
  timestamp: string;
}

interface UseWidgetSubscriptionOptions {
  /** Debounce-Zeit in ms (default: 500ms) */
  debounceMs?: number;
  /** Callback bei Widget-Update */
  onUpdate?: (payload: WidgetUpdatePayload) => void;
  /** Query Keys die bei Update invalidiert werden sollen */
  queryKeysToInvalidate?: string[][];
  /** Automatische Query-Invalidation aktivieren */
  autoInvalidate?: boolean;
}

/**
 * Hook für Widget-spezifische Echtzeit-Updates mit Debouncing.
 *
 * Bietet:
 * - Automatische Query-Invalidation bei Updates
 * - Debouncing für häufige Updates (konfigurierbar)
 * - Widget-spezifische Event-Filterung
 *
 * @param widgetType - Widget-Typ
 * @param options - Optionale Konfiguration
 *
 * @example
 * // Einfache Nutzung mit Auto-Invalidation
 * useWidgetSubscription('cashflow', {
 *   autoInvalidate: true,
 *   queryKeysToInvalidate: [['cashflow'], ['finance']],
 * });
 *
 * @example
 * // Mit Custom Handler
 * useWidgetSubscription('dunning', {
 *   debounceMs: 1000,
 *   onUpdate: (payload) => {
 *     console.log('Dunning widget updated:', payload);
 *   },
 * });
 */
export function useWidgetSubscription(
  widgetType: WidgetType,
  options: UseWidgetSubscriptionOptions = {}
): void {
  const {
    debounceMs = 500,
    onUpdate,
    queryKeysToInvalidate,
    autoInvalidate = true,
  } = options;

  const queryClient = useQueryClient();
  const onUpdateRef = useRef(onUpdate);
  const pendingUpdateRef = useRef<WidgetUpdatePayload | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Update refs
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  // Process update with debouncing
  const processUpdate = useCallback(
    (payload: WidgetUpdatePayload) => {
      // Store pending update
      pendingUpdateRef.current = payload;

      // Clear existing timer
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      // Set new timer
      debounceTimerRef.current = setTimeout(() => {
        const update = pendingUpdateRef.current;
        if (!update) return;

        // Clear pending
        pendingUpdateRef.current = null;

        // Call custom handler
        onUpdateRef.current?.(update);

        // Auto-invalidate queries
        if (autoInvalidate && queryKeysToInvalidate) {
          queryKeysToInvalidate.forEach((key) => {
            queryClient.invalidateQueries({ queryKey: key });
          });
        }
      }, debounceMs);
    },
    [debounceMs, autoInvalidate, queryKeysToInvalidate, queryClient]
  );

  // Subscribe to widget.update events
  useRealtimeEvent('widget.update', (event) => {
    const payload = event.payload as unknown as WidgetUpdatePayload;
    if (payload.widget_type === widgetType) {
      processUpdate(payload);
    }
  });

  // Subscribe to widget.data_changed events
  useRealtimeEvent('widget.data_changed', (event) => {
    const payload = event.payload as unknown as WidgetUpdatePayload;
    if (payload.widget_type === widgetType) {
      processUpdate(payload);
    }
  });

  // Subscribe to widget.refresh_required events (immediate, no debounce)
  useRealtimeEvent('widget.refresh_required', (event) => {
    const payload = event.payload as unknown as WidgetUpdatePayload;
    if (payload.widget_type === widgetType) {
      // Clear any pending debounced update
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      pendingUpdateRef.current = null;

      // Immediate callback
      onUpdateRef.current?.(payload);

      // Immediate invalidation
      if (autoInvalidate && queryKeysToInvalidate) {
        queryKeysToInvalidate.forEach((key) => {
          queryClient.invalidateQueries({ queryKey: key });
        });
      }
    }
  });
}

/**
 * Hook für mehrere Widget-Subscriptions gleichzeitig.
 *
 * Optimiert für Dashboard-Nutzung mit intelligenter Query-Invalidation.
 *
 * @param widgetConfigs - Map von Widget-Typ zu Query-Keys
 *
 * @example
 * useMultiWidgetSubscription({
 *   cashflow: [['cashflow'], ['finance']],
 *   dunning: [['dunning'], ['invoices']],
 *   recent_documents: [['documents']],
 * });
 */
export function useMultiWidgetSubscription(
  widgetConfigs: Partial<Record<WidgetType, string[][]>>
): void {
  const queryClient = useQueryClient();
  const configRef = useRef(widgetConfigs);

  // Update ref
  useEffect(() => {
    configRef.current = widgetConfigs;
  }, [widgetConfigs]);

  // Handle widget updates with minimal re-renders
  useRealtimeEvent('widget.update', (event) => {
    const payload = event.payload as unknown as WidgetUpdatePayload;
    const queryKeys = configRef.current[payload.widget_type];
    if (queryKeys) {
      queryKeys.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
    }
  });

  useRealtimeEvent('widget.data_changed', (event) => {
    const payload = event.payload as unknown as WidgetUpdatePayload;
    const queryKeys = configRef.current[payload.widget_type];
    if (queryKeys) {
      queryKeys.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
    }
  });

  useRealtimeEvent('widget.refresh_required', (event) => {
    const payload = event.payload as unknown as WidgetUpdatePayload;
    const queryKeys = configRef.current[payload.widget_type];
    if (queryKeys) {
      queryKeys.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
    }
  });
}

/**
 * Hook zum Senden von Widget-Refresh-Anfragen.
 *
 * Wird vom Server verwendet, um Widget-Updates anzufordern.
 * Frontend kann dies nutzen um manuelle Refreshes zu triggern.
 */
export function useWidgetRefreshTrigger() {
  const queryClient = useQueryClient();

  const triggerRefresh = useCallback(
    (widgetType: WidgetType, queryKeys?: string[][]) => {
      // Immediately invalidate local queries
      if (queryKeys) {
        queryKeys.forEach((key) => {
          queryClient.invalidateQueries({ queryKey: key });
        });
      }
    },
    [queryClient]
  );

  return { triggerRefresh };
}

export default RealtimeWebSocketClient;
