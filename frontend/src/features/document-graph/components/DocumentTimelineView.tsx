/**
 * DocumentTimelineView - Vertikaler Zeitstrahl mit Events
 *
 * Zeigt Lineage-Events eines Dokuments chronologisch.
 * Gruppiert nach Tag, mit Icon + Farbe pro Event-Type.
 */

import { useMemo } from 'react';
import {
  FileText,
  Upload,
  ScanLine,
  Tag,
  Link2,
  Edit,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Download,
  Archive,
  RotateCcw,
  Trash2,
  Clock,
  type LucideIcon,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { TimelineEntry } from '@/lib/api/services/lineage';

// ==================== Types ====================

interface DocumentTimelineViewProps {
  events: TimelineEntry[];
  isLoading: boolean;
  documentTitle?: string;
}

// ==================== Event Config ====================

interface EventConfig {
  icon: LucideIcon;
  label: string;
  bgColor: string;
  borderColor: string;
  textColor: string;
}

const EVENT_CONFIG: Record<string, EventConfig> = {
  import: {
    icon: Upload,
    label: 'Importiert',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
    borderColor: 'border-blue-500',
    textColor: 'text-blue-600 dark:text-blue-400',
  },
  ocr_start: {
    icon: ScanLine,
    label: 'OCR gestartet',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
    borderColor: 'border-amber-500',
    textColor: 'text-amber-600 dark:text-amber-400',
  },
  ocr_complete: {
    icon: ScanLine,
    label: 'OCR abgeschlossen',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
    borderColor: 'border-green-500',
    textColor: 'text-green-600 dark:text-green-400',
  },
  ocr_failed: {
    icon: XCircle,
    label: 'OCR fehlgeschlagen',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
    borderColor: 'border-red-500',
    textColor: 'text-red-600 dark:text-red-400',
  },
  classification: {
    icon: Tag,
    label: 'Klassifiziert',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30',
    borderColor: 'border-purple-500',
    textColor: 'text-purple-600 dark:text-purple-400',
  },
  extraction: {
    icon: FileText,
    label: 'Daten extrahiert',
    bgColor: 'bg-cyan-100 dark:bg-cyan-900/30',
    borderColor: 'border-cyan-500',
    textColor: 'text-cyan-600 dark:text-cyan-400',
  },
  entity_link: {
    icon: Link2,
    label: 'Verknuepft',
    bgColor: 'bg-indigo-100 dark:bg-indigo-900/30',
    borderColor: 'border-indigo-500',
    textColor: 'text-indigo-600 dark:text-indigo-400',
  },
  entity_unlink: {
    icon: Link2,
    label: 'Verknuepfung entfernt',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30',
    borderColor: 'border-orange-500',
    textColor: 'text-orange-600 dark:text-orange-400',
  },
  modification: {
    icon: Edit,
    label: 'Bearbeitet',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30',
    borderColor: 'border-amber-500',
    textColor: 'text-amber-600 dark:text-amber-400',
  },
  metadata_update: {
    icon: Edit,
    label: 'Metadaten aktualisiert',
    bgColor: 'bg-slate-100 dark:bg-slate-900/30',
    borderColor: 'border-slate-500',
    textColor: 'text-slate-600 dark:text-slate-400',
  },
  tag_change: {
    icon: Tag,
    label: 'Tags geaendert',
    bgColor: 'bg-pink-100 dark:bg-pink-900/30',
    borderColor: 'border-pink-500',
    textColor: 'text-pink-600 dark:text-pink-400',
  },
  approval: {
    icon: CheckCircle,
    label: 'Genehmigt',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
    borderColor: 'border-green-500',
    textColor: 'text-green-600 dark:text-green-400',
  },
  rejection: {
    icon: XCircle,
    label: 'Abgelehnt',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
    borderColor: 'border-red-500',
    textColor: 'text-red-600 dark:text-red-400',
  },
  escalation: {
    icon: AlertTriangle,
    label: 'Eskaliert',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30',
    borderColor: 'border-orange-500',
    textColor: 'text-orange-600 dark:text-orange-400',
  },
  export: {
    icon: Download,
    label: 'Exportiert',
    bgColor: 'bg-emerald-100 dark:bg-emerald-900/30',
    borderColor: 'border-emerald-500',
    textColor: 'text-emerald-600 dark:text-emerald-400',
  },
  archive: {
    icon: Archive,
    label: 'Archiviert',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
    borderColor: 'border-gray-500',
    textColor: 'text-gray-600 dark:text-gray-400',
  },
  restore: {
    icon: RotateCcw,
    label: 'Wiederhergestellt',
    bgColor: 'bg-teal-100 dark:bg-teal-900/30',
    borderColor: 'border-teal-500',
    textColor: 'text-teal-600 dark:text-teal-400',
  },
  soft_delete: {
    icon: Trash2,
    label: 'Geloescht',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
    borderColor: 'border-red-500',
    textColor: 'text-red-600 dark:text-red-400',
  },
  hard_delete: {
    icon: Trash2,
    label: 'Endgueltig geloescht',
    bgColor: 'bg-red-200 dark:bg-red-900/50',
    borderColor: 'border-red-700',
    textColor: 'text-red-700 dark:text-red-300',
  },
};

const DEFAULT_EVENT_CONFIG: EventConfig = {
  icon: FileText,
  label: 'Ereignis',
  bgColor: 'bg-muted',
  borderColor: 'border-muted-foreground',
  textColor: 'text-muted-foreground',
};

// ==================== Helpers ====================

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatRelativeTime(ts: string): string {
  const diffMs = Date.now() - new Date(ts).getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'Heute';
  if (diffDays === 1) return 'Gestern';
  if (diffDays < 7) return `Vor ${diffDays} Tagen`;
  if (diffDays < 30) return `Vor ${Math.floor(diffDays / 7)} Wochen`;
  if (diffDays < 365) return `Vor ${Math.floor(diffDays / 30)} Monaten`;
  return `Vor ${Math.floor(diffDays / 365)} Jahren`;
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
}

type GroupedEvents = Array<{ date: string; events: TimelineEntry[] }>;

function groupByDate(events: TimelineEntry[]): GroupedEvents {
  const groups = new Map<string, TimelineEntry[]>();

  for (const event of events) {
    const dateKey = new Date(event.timestamp).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    });
    const existing = groups.get(dateKey);
    if (existing) {
      existing.push(event);
    } else {
      groups.set(dateKey, [event]);
    }
  }

  return Array.from(groups.entries()).map(([date, groupEvents]) => ({
    date,
    events: groupEvents,
  }));
}

// ==================== Sub-Components ====================

function TimelineSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex gap-4">
          <Skeleton className="h-10 w-10 rounded-full shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

function TimelineEmpty() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Clock className="h-12 w-12 text-muted-foreground mb-4" />
      <p className="text-muted-foreground">Keine Ereignisse gefunden</p>
      <p className="text-sm text-muted-foreground/70 mt-1">
        Dokumenten-Aktivitaeten werden hier chronologisch angezeigt.
      </p>
    </div>
  );
}

// ==================== Main Component ====================

export function DocumentTimelineView({
  events,
  isLoading,
  documentTitle,
}: DocumentTimelineViewProps) {
  // Sort newest first and group
  const grouped = useMemo(() => {
    const sorted = [...events].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
    return groupByDate(sorted);
  }, [events]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Clock className="h-5 w-5" />
          Dokumenten-Timeline
        </CardTitle>
        <CardDescription>
          {documentTitle
            ? `Chronologischer Verlauf fuer "${documentTitle}"`
            : 'Chronologischer Verlauf aller Ereignisse'}
        </CardDescription>
        {events.length > 0 && (
          <Badge variant="outline" className="w-fit">
            {events.length} Ereignisse
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <TimelineSkeleton />
        ) : events.length === 0 ? (
          <TimelineEmpty />
        ) : (
          <ScrollArea className="max-h-[600px]">
            <div className="space-y-6">
              {grouped.map((group) => (
                <div key={group.date}>
                  {/* Date Header */}
                  <div className="sticky top-0 z-10 bg-background pb-2">
                    <Badge variant="secondary" className="text-xs">
                      {group.date}
                    </Badge>
                  </div>

                  {/* Events */}
                  <div className="relative ml-1">
                    {group.events.map((event, index) => {
                      const config = EVENT_CONFIG[event.eventType] || DEFAULT_EVENT_CONFIG;
                      const Icon = config.icon;
                      const isLast = index === group.events.length - 1;

                      return (
                        <div key={event.id} className="relative flex gap-4">
                          {/* Timeline Line */}
                          {!isLast && (
                            <div className="absolute left-5 top-10 bottom-0 w-0.5 bg-border" />
                          )}

                          {/* Event Icon */}
                          <div
                            className={cn(
                              'relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2',
                              config.bgColor,
                              config.borderColor
                            )}
                          >
                            <Icon className={cn('h-4 w-4', config.textColor)} />
                          </div>

                          {/* Event Content */}
                          <div className="flex-1 pb-4">
                            <div className="rounded-lg border bg-card p-3">
                              <div className="flex items-start justify-between gap-2">
                                <div>
                                  <h4 className="font-medium text-sm">
                                    {config.label}
                                  </h4>
                                  {event.confidence != null && (
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                      Konfidenz: {(event.confidence * 100).toFixed(0)}%
                                    </p>
                                  )}
                                </div>
                                <div className="text-right shrink-0">
                                  <p className="text-xs text-muted-foreground">
                                    {formatRelativeTime(event.timestamp)}
                                  </p>
                                  <p className="text-[10px] text-muted-foreground/70">
                                    {formatTimestamp(event.timestamp)}
                                  </p>
                                </div>
                              </div>

                              {/* Duration + Source */}
                              <div className="mt-2 flex flex-wrap gap-1">
                                {event.durationMs != null && event.durationMs > 0 && (
                                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                                    {formatDuration(event.durationMs)}
                                  </Badge>
                                )}
                                {event.sourceService && (
                                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                                    {event.sourceService}
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
