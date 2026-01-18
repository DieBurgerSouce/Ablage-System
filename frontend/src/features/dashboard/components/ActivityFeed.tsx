/**
 * ActivityFeed Component.
 *
 * Live-Feed von System-Aktivitaeten mit Echtzeit-Updates via WebSocket.
 *
 * Features:
 * - Echtzeit-Updates ohne Refresh
 * - Event-Kategorisierung mit Icons
 * - Zeitstempel mit relative Zeit
 * - Click-Handler fuer Navigation
 * - Expandable Details
 * - Priorisierung (kritische Events oben)
 */

import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  FileText,
  ScanLine,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  CreditCard,
  Users,
  Bell,
  Link2,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';

import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  useWebSocket,
  useEventStream,
  type RealtimeEvent,
  type RealtimeEventType,
  type ConnectionState,
} from '@/lib/websocket';

// ============================================================================
// Types
// ============================================================================

interface ActivityFeedProps {
  /** Maximale Anzahl angezeigter Events */
  maxEvents?: number;
  /** Hoehe der ScrollArea */
  height?: string;
  /** Nur bestimmte Event-Kategorien zeigen */
  categories?: string[];
  /** Callback bei Event-Klick */
  onEventClick?: (event: RealtimeEvent) => void;
  /** Kompakte Darstellung */
  compact?: boolean;
  /** Zeige Verbindungsstatus */
  showConnectionStatus?: boolean;
}

interface EventConfig {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  color: string;
  bgColor: string;
  category: string;
}

// ============================================================================
// Event Configuration
// ============================================================================

const eventConfig: Record<string, EventConfig> = {
  // Document Events
  'document.uploaded': {
    icon: FileText,
    label: 'Dokument hochgeladen',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'document',
  },
  'document.ocr_started': {
    icon: ScanLine,
    label: 'OCR gestartet',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    category: 'document',
  },
  'document.ocr_progress': {
    icon: RefreshCw,
    label: 'OCR Fortschritt',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    category: 'document',
  },
  'document.ocr_completed': {
    icon: CheckCircle,
    label: 'OCR abgeschlossen',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    category: 'document',
  },
  'document.categorized': {
    icon: FileText,
    label: 'Dokument kategorisiert',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'document',
  },
  'document.deleted': {
    icon: XCircle,
    label: 'Dokument geloescht',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    category: 'document',
  },

  // Validation Events
  'validation.item_added': {
    icon: AlertTriangle,
    label: 'Validierung erforderlich',
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-50',
    category: 'validation',
  },
  'validation.item_resolved': {
    icon: CheckCircle,
    label: 'Validierung abgeschlossen',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    category: 'validation',
  },
  'validation.queue_updated': {
    icon: Clock,
    label: 'Queue aktualisiert',
    color: 'text-gray-600',
    bgColor: 'bg-gray-50',
    category: 'validation',
  },

  // Approval Events
  'approval.requested': {
    icon: Clock,
    label: 'Genehmigung angefordert',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    category: 'approval',
  },
  'approval.approved': {
    icon: CheckCircle,
    label: 'Genehmigt',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    category: 'approval',
  },
  'approval.rejected': {
    icon: XCircle,
    label: 'Abgelehnt',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    category: 'approval',
  },
  'approval.escalated': {
    icon: AlertTriangle,
    label: 'Eskaliert',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    category: 'approval',
  },

  // Finance Events
  'invoice.created': {
    icon: FileText,
    label: 'Rechnung erstellt',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'finance',
  },
  'invoice.paid': {
    icon: CheckCircle,
    label: 'Rechnung bezahlt',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    category: 'finance',
  },
  'invoice.overdue': {
    icon: AlertTriangle,
    label: 'Rechnung ueberfaellig',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    category: 'finance',
  },
  'payment.received': {
    icon: CreditCard,
    label: 'Zahlung eingegangen',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    category: 'finance',
  },
  'cashflow.updated': {
    icon: TrendingUp,
    label: 'Cashflow aktualisiert',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'finance',
  },
  'budget.alert': {
    icon: AlertTriangle,
    label: 'Budget-Warnung',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    category: 'finance',
  },

  // Banking Events
  'transaction.imported': {
    icon: CreditCard,
    label: 'Transaktion importiert',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'banking',
  },
  'reconciliation.match': {
    icon: Link2,
    label: 'Abgleich gefunden',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    category: 'banking',
  },
  'dunning.escalated': {
    icon: AlertTriangle,
    label: 'Mahnung eskaliert',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    category: 'banking',
  },

  // Entity Events
  'entity.linked': {
    icon: Link2,
    label: 'Entity verknuepft',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'entity',
  },
  'entity.risk_changed': {
    icon: AlertTriangle,
    label: 'Risiko-Score geaendert',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    category: 'entity',
  },

  // System Events
  'system.notification': {
    icon: Bell,
    label: 'Benachrichtigung',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'system',
  },
  'system.error': {
    icon: XCircle,
    label: 'Systemfehler',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    category: 'system',
  },
  'system.maintenance': {
    icon: RefreshCw,
    label: 'Wartung',
    color: 'text-gray-600',
    bgColor: 'bg-gray-50',
    category: 'system',
  },

  // User Events
  'user.task_assigned': {
    icon: Users,
    label: 'Aufgabe zugewiesen',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    category: 'user',
  },
  'user.mention': {
    icon: Bell,
    label: 'Erwaehnung',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    category: 'user',
  },
};

// ============================================================================
// Helper Functions
// ============================================================================

function getEventConfig(eventType: RealtimeEventType): EventConfig {
  return (
    eventConfig[eventType] || {
      icon: Bell,
      label: eventType,
      color: 'text-gray-600',
      bgColor: 'bg-gray-50',
      category: 'other',
    }
  );
}

function formatRelativeTime(timestamp: string): string {
  try {
    return formatDistanceToNow(new Date(timestamp), {
      addSuffix: true,
      locale: de,
    });
  } catch {
    return timestamp;
  }
}

function getPriorityOrder(priority: string): number {
  const order: Record<string, number> = {
    critical: 0,
    high: 1,
    normal: 2,
    low: 3,
  };
  return order[priority] ?? 2;
}

function getEventDescription(event: RealtimeEvent): string {
  const payload = event.payload;

  switch (event.event_type) {
    case 'document.uploaded':
      return `"${payload.filename || 'Dokument'}" wurde hochgeladen`;
    case 'document.ocr_completed':
      return `OCR fuer "${payload.filename || 'Dokument'}" abgeschlossen`;
    case 'document.categorized':
      return `Dokument als "${payload.category || 'Unbekannt'}" kategorisiert`;
    case 'validation.item_added':
      return `Neues Item zur Validierung: ${payload.field || 'Feld'} pruefen`;
    case 'approval.requested':
      return `Genehmigung fuer ${payload.title || 'Antrag'} erforderlich`;
    case 'approval.approved':
      return `${payload.title || 'Antrag'} wurde genehmigt`;
    case 'approval.rejected':
      return `${payload.title || 'Antrag'} wurde abgelehnt`;
    case 'invoice.paid':
      return `Rechnung bezahlt: ${payload.amount ? `${payload.amount}€` : ''}`;
    case 'invoice.overdue':
      return `Rechnung ueberfaellig seit ${payload.days_overdue || '?'} Tagen`;
    case 'payment.received':
      return `Zahlung eingegangen: ${payload.amount ? `${payload.amount}€` : ''}`;
    case 'budget.alert':
      return `Budget ${payload.budget_name || ''} zu ${payload.percent_used || '?'}% ausgeschoepft`;
    case 'transaction.imported':
      return `${payload.count || 1} Transaktion(en) importiert`;
    case 'entity.risk_changed':
      return `Risiko-Score geaendert auf ${payload.new_score || '?'}`;
    case 'system.notification':
      return typeof payload.message === 'string' ? payload.message : 'System-Benachrichtigung';
    case 'system.error':
      return typeof payload.message === 'string' ? payload.message : 'Systemfehler aufgetreten';
    default:
      return event.event_type;
  }
}

// ============================================================================
// Connection Status Component
// ============================================================================

function ConnectionStatus({ state }: { state: ConnectionState }) {
  const statusConfig: Record<
    ConnectionState,
    { icon: React.ComponentType<{ className?: string }>; label: string; color: string }
  > = {
    connected: { icon: Wifi, label: 'Verbunden', color: 'text-green-500' },
    connecting: { icon: RefreshCw, label: 'Verbinde...', color: 'text-yellow-500' },
    disconnected: { icon: WifiOff, label: 'Getrennt', color: 'text-red-500' },
    reconnecting: { icon: RefreshCw, label: 'Verbinde erneut...', color: 'text-yellow-500' },
  };

  const config = statusConfig[state];
  const Icon = config.icon;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1">
            <Icon
              className={cn(
                'h-4 w-4',
                config.color,
                (state === 'connecting' || state === 'reconnecting') && 'animate-spin'
              )}
            />
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p>{config.label}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ============================================================================
// Activity Item Component
// ============================================================================

interface ActivityItemProps {
  event: RealtimeEvent;
  onClick?: () => void;
  compact?: boolean;
}

function ActivityItem({ event, onClick, compact = false }: ActivityItemProps) {
  const [expanded, setExpanded] = useState(false);
  const config = getEventConfig(event.event_type);
  const Icon = config.icon;

  const handleClick = () => {
    if (onClick) {
      onClick();
    } else {
      setExpanded(!expanded);
    }
  };

  return (
    <div
      className={cn(
        'group relative flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-muted/50 cursor-pointer',
        event.priority === 'critical' && 'border-l-2 border-red-500',
        event.priority === 'high' && 'border-l-2 border-orange-500'
      )}
      onClick={handleClick}
    >
      {/* Icon */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          config.bgColor
        )}
      >
        <Icon className={cn('h-4 w-4', config.color)} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium truncate">{config.label}</span>
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {formatRelativeTime(event.timestamp)}
          </span>
        </div>

        {!compact && (
          <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">
            {getEventDescription(event)}
          </p>
        )}

        {/* Priority Badge */}
        {(event.priority === 'critical' || event.priority === 'high') && (
          <Badge
            variant="outline"
            className={cn(
              'mt-1 text-xs',
              event.priority === 'critical' && 'border-red-300 text-red-600',
              event.priority === 'high' && 'border-orange-300 text-orange-600'
            )}
          >
            {event.priority === 'critical' ? 'Kritisch' : 'Wichtig'}
          </Badge>
        )}

        {/* Expanded Details */}
        {expanded && !compact && (
          <div className="mt-2 p-2 bg-muted rounded text-xs">
            <pre className="whitespace-pre-wrap overflow-auto max-h-32">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* Expand Icon */}
      {!compact && (
        <div className="opacity-0 group-hover:opacity-100 transition-opacity">
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function ActivityFeed({
  maxEvents = 50,
  height = '400px',
  categories,
  onEventClick,
  compact = false,
  showConnectionStatus = true,
}: ActivityFeedProps) {
  const navigate = useNavigate();
  const { state } = useWebSocket();
  const events = useEventStream(maxEvents);

  // Filter events by category
  const filteredEvents = useMemo(() => {
    let result = events;

    if (categories && categories.length > 0) {
      result = events.filter((event) => {
        const config = getEventConfig(event.event_type);
        return categories.includes(config.category);
      });
    }

    // Sort by priority (critical first) then by timestamp
    return result.sort((a, b) => {
      const priorityDiff = getPriorityOrder(a.priority) - getPriorityOrder(b.priority);
      if (priorityDiff !== 0) return priorityDiff;
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    });
  }, [events, categories]);

  const handleEventClick = (event: RealtimeEvent) => {
    if (onEventClick) {
      onEventClick(event);
      return;
    }

    // Default navigation based on event type
    const payload = event.payload;
    switch (event.event_type) {
      case 'document.uploaded':
      case 'document.ocr_completed':
      case 'document.categorized':
        if (payload.document_id) {
          navigate({ to: `/documents/${payload.document_id}` });
        }
        break;
      case 'validation.item_added':
      case 'validation.item_resolved':
        navigate({ to: '/validation' });
        break;
      case 'approval.requested':
      case 'approval.approved':
      case 'approval.rejected':
        if (payload.approval_id) {
          navigate({ to: `/approvals/${payload.approval_id}` });
        }
        break;
      case 'invoice.created':
      case 'invoice.paid':
      case 'invoice.overdue':
        if (payload.invoice_id) {
          navigate({ to: `/invoices/${payload.invoice_id}` });
        }
        break;
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <h3 className="text-sm font-semibold">Aktivitaeten</h3>
        <div className="flex items-center gap-2">
          {showConnectionStatus && <ConnectionStatus state={state} />}
          <Badge variant="secondary" className="text-xs">
            {filteredEvents.length}
          </Badge>
        </div>
      </div>

      {/* Event List */}
      <ScrollArea style={{ height }} className="flex-1">
        <div className="p-2 space-y-1">
          {filteredEvents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <Bell className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">Keine Aktivitaeten</p>
              {state !== 'connected' && (
                <p className="text-xs mt-1">WebSocket nicht verbunden</p>
              )}
            </div>
          ) : (
            filteredEvents.map((event) => (
              <ActivityItem
                key={event.event_id}
                event={event}
                onClick={() => handleEventClick(event)}
                compact={compact}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

// ============================================================================
// Widget Export (fuer Dashboard)
// ============================================================================

export function ActivityFeedWidget() {
  return (
    <div className="h-full border rounded-lg overflow-hidden bg-card">
      <ActivityFeed height="100%" maxEvents={20} compact />
    </div>
  );
}

export default ActivityFeed;
