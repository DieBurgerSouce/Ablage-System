import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Upload,
  ScanLine,
  Tag,
  FileText,
  Link2,
  Edit,
  ThumbsUp,
  ThumbsDown,
  Download,
  Archive,
  RefreshCw,
  ShieldCheck,
  Settings,
  Eye,
  Trash2,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  LucideIcon,
} from 'lucide-react';
import { type LifecycleEvent as LifecycleEventType } from '../api/lifecycle-api';

interface LifecycleEventProps {
  event: LifecycleEventType;
}

// Mapping von Event-Typ zu Icon und Farbe
const EVENT_TYPE_CONFIG: Record<
  string,
  { icon: LucideIcon; colorClass: string; label: string }
> = {
  IMPORT: { icon: Upload, colorClass: 'text-blue-500', label: 'Importiert' },
  OCR_START: { icon: ScanLine, colorClass: 'text-yellow-500', label: 'OCR gestartet' },
  OCR_COMPLETE: { icon: ScanLine, colorClass: 'text-green-500', label: 'OCR abgeschlossen' },
  CLASSIFICATION: { icon: Tag, colorClass: 'text-purple-500', label: 'Klassifiziert' },
  EXTRACTION: { icon: FileText, colorClass: 'text-indigo-500', label: 'Daten extrahiert' },
  ENTITY_LINK: { icon: Link2, colorClass: 'text-cyan-500', label: 'Entität verknüpft' },
  MODIFICATION: { icon: Edit, colorClass: 'text-orange-500', label: 'Bearbeitet' },
  APPROVAL: { icon: ThumbsUp, colorClass: 'text-green-600', label: 'Freigegeben' },
  REJECTION: { icon: ThumbsDown, colorClass: 'text-red-500', label: 'Abgelehnt' },
  EXPORT: { icon: Download, colorClass: 'text-blue-600', label: 'Exportiert' },
  ARCHIVE: { icon: Archive, colorClass: 'text-gray-500', label: 'Archiviert' },
  REPROCESSING: { icon: RefreshCw, colorClass: 'text-yellow-600', label: 'Neu verarbeitet' },
  QUALITY_CHECK: { icon: ShieldCheck, colorClass: 'text-green-500', label: 'Qualitätsprüfung' },
  METADATA_UPDATE: { icon: Settings, colorClass: 'text-gray-400', label: 'Metadaten aktualisiert' },
  ACCESS: { icon: Eye, colorClass: 'text-gray-400', label: 'Aufgerufen' },
  DELETION_REQUEST: { icon: Trash2, colorClass: 'text-red-400', label: 'Löschung angefordert' },
  DELETION_COMPLETE: { icon: Trash2, colorClass: 'text-red-600', label: 'Gelöscht' },
  RESTORATION: { icon: RotateCcw, colorClass: 'text-green-400', label: 'Wiederhergestellt' },
};

export function LifecycleEvent({ event }: LifecycleEventProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const config = EVENT_TYPE_CONFIG[event.event_type] || {
    icon: FileText,
    colorClass: 'text-gray-500',
    label: event.event_type,
  };

  const Icon = config.icon;

  // Relative Zeitangabe
  const relativeTime = formatDistanceToNow(new Date(event.timestamp), {
    addSuffix: true,
    locale: de,
  });

  // Formatiere Dauer
  const duration = event.duration_ms !== null
    ? `${(event.duration_ms / 1000).toFixed(1)}s`
    : null;

  // Formatiere Confidence
  const confidence = event.confidence !== null
    ? `${Math.round(event.confidence * 100)}%`
    : null;

  // Check ob event_data nicht leer ist
  const hasEventData = event.event_data && Object.keys(event.event_data).length > 0;

  return (
    <div className="flex gap-3 py-3 border-b border-border/50 last:border-0">
      {/* Icon */}
      <div className="flex-shrink-0">
        <div className={`${config.colorClass} p-2 rounded-full bg-background border`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-sm">{config.label}</h4>
            <p className="text-xs text-muted-foreground">{relativeTime}</p>
          </div>

          {/* Metadata */}
          <div className="flex gap-2 text-xs text-muted-foreground flex-shrink-0">
            {duration && (
              <span className="px-2 py-0.5 bg-muted rounded">{duration}</span>
            )}
            {confidence && (
              <span className="px-2 py-0.5 bg-muted rounded">{confidence}</span>
            )}
          </div>
        </div>

        {/* Expandable Event Data */}
        {hasEventData && (
          <div className="mt-2">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              aria-label={isExpanded ? 'Details verbergen' : 'Details anzeigen'}
            >
              {isExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              <span>Details {isExpanded ? 'verbergen' : 'anzeigen'}</span>
            </button>

            {isExpanded && (
              <div className="mt-2 p-3 bg-muted/30 rounded-md text-xs space-y-1">
                {Object.entries(event.event_data).map(([key, value]) => (
                  <div key={key} className="grid grid-cols-3 gap-2">
                    <span className="font-medium text-muted-foreground truncate">
                      {key}:
                    </span>
                    <span className="col-span-2 break-words">
                      {typeof value === 'object' && value !== null
                        ? JSON.stringify(value, null, 2)
                        : String(value)}
                    </span>
                  </div>
                ))}

                {/* Additional metadata */}
                {event.source_service && (
                  <div className="grid grid-cols-3 gap-2 pt-2 mt-2 border-t border-border/50">
                    <span className="font-medium text-muted-foreground">Service:</span>
                    <span className="col-span-2">{event.source_service}</span>
                  </div>
                )}
                {event.user_id && (
                  <div className="grid grid-cols-3 gap-2">
                    <span className="font-medium text-muted-foreground">Benutzer-ID:</span>
                    <span className="col-span-2">{event.user_id}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
