/**
 * EventDetailPanel Component
 *
 * Seitenpanel mit detaillierten Informationen zu einem ausgewählten Lineage-Event.
 * Zeigt alle Event-Daten und ermöglicht Interaktionen.
 */

import { memo, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { formatDateTimeDE, formatNumberDE, formatPercentDE } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  FileUp,
  FileText,
  ScanSearch,
  CheckCircle2,
  XCircle,
  Tag,
  Link2,
  Unlink2,
  Edit3,
  ThumbsUp,
  ThumbsDown,
  AlertTriangle,
  Download,
  Archive,
  RotateCcw,
  Trash2,
  Clock,
  Gauge,
  User,
  Server,
  Calendar,
  ExternalLink,
  Copy,
  Check,
} from 'lucide-react';
import { useState } from 'react';
import type { LineageEventType, EventTypeLabels } from '@/lib/api/services/lineage';
import type { TimelineEntry } from '@/lib/api/services/lineage';

// =============================================================================
// Types
// =============================================================================

export interface EventDetailPanelProps {
  event: TimelineEntry | null;
  eventTypeLabels?: EventTypeLabels;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigateToDocument?: (documentId: string) => void;
  onNavigateToEntity?: (entityId: string) => void;
}

// =============================================================================
// Event Configuration
// =============================================================================

const EVENT_ICONS: Record<LineageEventType, React.ComponentType<{ className?: string }>> = {
  import: FileUp,
  ocr_start: ScanSearch,
  ocr_complete: CheckCircle2,
  ocr_failed: XCircle,
  classification: Tag,
  extraction: FileText,
  entity_link: Link2,
  entity_unlink: Unlink2,
  modification: Edit3,
  metadata_update: Edit3,
  tag_change: Tag,
  approval: ThumbsUp,
  rejection: ThumbsDown,
  escalation: AlertTriangle,
  export: Download,
  archive: Archive,
  restore: RotateCcw,
  soft_delete: Trash2,
  hard_delete: Trash2,
};

const EVENT_COLORS: Record<LineageEventType, string> = {
  import: 'text-blue-600 dark:text-blue-400',
  ocr_start: 'text-amber-600 dark:text-amber-400',
  ocr_complete: 'text-green-600 dark:text-green-400',
  ocr_failed: 'text-red-600 dark:text-red-400',
  classification: 'text-purple-600 dark:text-purple-400',
  extraction: 'text-indigo-600 dark:text-indigo-400',
  entity_link: 'text-cyan-600 dark:text-cyan-400',
  entity_unlink: 'text-slate-600 dark:text-slate-400',
  modification: 'text-orange-600 dark:text-orange-400',
  metadata_update: 'text-orange-600 dark:text-orange-400',
  tag_change: 'text-pink-600 dark:text-pink-400',
  approval: 'text-emerald-600 dark:text-emerald-400',
  rejection: 'text-red-600 dark:text-red-400',
  escalation: 'text-yellow-600 dark:text-yellow-400',
  export: 'text-teal-600 dark:text-teal-400',
  archive: 'text-gray-600 dark:text-gray-400',
  restore: 'text-lime-600 dark:text-lime-400',
  soft_delete: 'text-rose-600 dark:text-rose-400',
  hard_delete: 'text-red-700 dark:text-red-500',
};

// =============================================================================
// Helper Components
// =============================================================================

interface InfoRowProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: React.ReactNode;
  className?: string;
}

function InfoRow({ icon: Icon, label, value, className }: InfoRowProps) {
  return (
    <div className={cn('flex items-start gap-3', className)}>
      <Icon className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-muted-foreground">{label}</p>
        <div className="text-sm font-medium break-words">{value}</div>
      </div>
    </div>
  );
}

interface CopyableValueProps {
  value: string;
  displayValue?: string;
}

function CopyableValue({ value, displayValue }: CopyableValueProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      <span className="truncate">{displayValue || value}</span>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 flex-shrink-0"
        onClick={handleCopy}
        title="In Zwischenablage kopieren"
      >
        {copied ? (
          <Check className="h-3 w-3 text-green-500" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </Button>
    </div>
  );
}

// =============================================================================
// Component
// =============================================================================

export const EventDetailPanel = memo(function EventDetailPanel({
  event,
  eventTypeLabels,
  open,
  onOpenChange,
  onNavigateToDocument,
  onNavigateToEntity,
}: EventDetailPanelProps) {
  const Icon = useMemo(
    () =>
      event ? EVENT_ICONS[event.eventType] || Edit3 : Edit3,
    [event]
  );

  const iconColor = useMemo(
    () =>
      event ? EVENT_COLORS[event.eventType] || 'text-slate-600' : 'text-slate-600',
    [event]
  );

  const eventLabel = useMemo(
    () =>
      event && eventTypeLabels
        ? eventTypeLabels[event.eventType] || event.eventType.replace(/_/g, ' ')
        : event?.eventType.replace(/_/g, ' ') || '',
    [event, eventTypeLabels]
  );

  if (!event) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[400px] sm:w-[540px] p-0">
        <SheetHeader className="px-6 py-4 border-b">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'flex items-center justify-center w-10 h-10 rounded-full bg-muted'
              )}
            >
              <Icon className={cn('w-5 h-5', iconColor)} />
            </div>
            <div>
              <SheetTitle>{eventLabel}</SheetTitle>
              <SheetDescription>
                {formatDateTimeDE(event.timestamp, true)}
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-120px)]">
          <div className="px-6 py-4 space-y-6">
            {/* Basis-Informationen */}
            <section className="space-y-4">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                Basis-Informationen
              </h3>

              <InfoRow
                icon={Calendar}
                label="Zeitstempel"
                value={formatDateTimeDE(event.timestamp, true)}
              />

              <InfoRow
                icon={Tag}
                label="Event-ID"
                value={<CopyableValue value={event.id} displayValue={event.id.slice(0, 8) + '...'} />}
              />

              {event.confidence !== null && (
                <InfoRow
                  icon={Gauge}
                  label="Konfidenz"
                  value={
                    <Badge
                      variant={event.confidence >= 0.8 ? 'default' : event.confidence >= 0.5 ? 'secondary' : 'destructive'}
                    >
                      {formatPercentDE(event.confidence, 1, false)}
                    </Badge>
                  }
                />
              )}

              {event.durationMs !== null && (
                <InfoRow
                  icon={Clock}
                  label="Verarbeitungsdauer"
                  value={
                    event.durationMs < 1000
                      ? `${event.durationMs}ms`
                      : `${formatNumberDE(event.durationMs / 1000, 2)}s`
                  }
                />
              )}

              {event.sourceService && (
                <InfoRow
                  icon={Server}
                  label="Quell-Service"
                  value={event.sourceService}
                />
              )}

              {event.userId && (
                <InfoRow
                  icon={User}
                  label="Benutzer"
                  value={
                    <CopyableValue
                      value={event.userId}
                      displayValue={event.userId.slice(0, 8) + '...'}
                    />
                  }
                />
              )}
            </section>

            <Separator />

            {/* Event-spezifische Details */}
            {event.eventData && Object.keys(event.eventData).length > 0 && (
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                  Event-Details
                </h3>

                <EventDataRenderer
                  eventType={event.eventType}
                  eventData={event.eventData}
                  onNavigateToDocument={onNavigateToDocument}
                  onNavigateToEntity={onNavigateToEntity}
                />
              </section>
            )}

            {/* Rohe Event-Daten (Debug) */}
            <section className="space-y-4">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                Rohe Daten
              </h3>

              <div className="bg-muted rounded-lg p-4 overflow-x-auto">
                <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-words">
                  {JSON.stringify(event.eventData, null, 2)}
                </pre>
              </div>
            </section>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
});

// =============================================================================
// Event Data Renderer
// =============================================================================

interface EventDataRendererProps {
  eventType: LineageEventType;
  eventData: Record<string, unknown>;
  onNavigateToDocument?: (documentId: string) => void;
  onNavigateToEntity?: (entityId: string) => void;
}

function EventDataRenderer({
  eventType,
  eventData,
  onNavigateToDocument,
  onNavigateToEntity,
}: EventDataRendererProps) {
  switch (eventType) {
    case 'import':
      return (
        <div className="space-y-3">
          {eventData.source_type && (
            <InfoRow
              icon={FileUp}
              label="Import-Quelle"
              value={
                <Badge variant="outline">
                  {String(eventData.source_type).replace(/_/g, ' ')}
                </Badge>
              }
            />
          )}
          {eventData.filename && (
            <InfoRow
              icon={FileText}
              label="Dateiname"
              value={String(eventData.filename)}
            />
          )}
          {eventData.file_size && (
            <InfoRow
              icon={FileText}
              label="Dateigröße"
              value={formatFileSize(Number(eventData.file_size))}
            />
          )}
          {eventData.mime_type && (
            <InfoRow
              icon={Tag}
              label="MIME-Typ"
              value={String(eventData.mime_type)}
            />
          )}
        </div>
      );

    case 'ocr_complete':
    case 'ocr_failed':
      return (
        <div className="space-y-3">
          {eventData.backend && (
            <InfoRow
              icon={ScanSearch}
              label="OCR-Backend"
              value={
                <Badge variant="outline">
                  {String(eventData.backend)}
                </Badge>
              }
            />
          )}
          {eventData.pages !== undefined && (
            <InfoRow
              icon={FileText}
              label="Verarbeitete Seiten"
              value={String(eventData.pages)}
            />
          )}
          {eventData.error && (
            <InfoRow
              icon={XCircle}
              label="Fehler"
              value={
                <span className="text-red-600 dark:text-red-400">
                  {String(eventData.error)}
                </span>
              }
            />
          )}
        </div>
      );

    case 'classification':
      return (
        <div className="space-y-3">
          {eventData.document_type && (
            <InfoRow
              icon={Tag}
              label="Dokumenttyp"
              value={
                <Badge>{String(eventData.document_type)}</Badge>
              }
            />
          )}
          {eventData.direction && (
            <InfoRow
              icon={FileUp}
              label="Richtung"
              value={
                <Badge variant={eventData.direction === 'incoming' ? 'default' : 'secondary'}>
                  {eventData.direction === 'incoming' ? 'Eingang' : 'Ausgang'}
                </Badge>
              }
            />
          )}
        </div>
      );

    case 'entity_link':
    case 'entity_unlink':
      return (
        <div className="space-y-3">
          {eventData.entity_name && (
            <InfoRow
              icon={Link2}
              label="Geschäftspartner"
              value={
                <div className="flex items-center gap-2">
                  <span>{String(eventData.entity_name)}</span>
                  {eventData.entity_id && onNavigateToEntity && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={() => onNavigateToEntity(String(eventData.entity_id))}
                      title="Zum Geschäftspartner"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              }
            />
          )}
          {eventData.match_type && (
            <InfoRow
              icon={Tag}
              label="Match-Methode"
              value={
                <Badge variant="outline">
                  {String(eventData.match_type).replace(/_/g, ' ')}
                </Badge>
              }
            />
          )}
          {eventData.reason && (
            <InfoRow
              icon={FileText}
              label="Begründung"
              value={String(eventData.reason)}
            />
          )}
        </div>
      );

    case 'export':
      return (
        <div className="space-y-3">
          {eventData.format && (
            <InfoRow
              icon={Download}
              label="Export-Format"
              value={
                <Badge variant="outline">
                  {String(eventData.format).toUpperCase()}
                </Badge>
              }
            />
          )}
          {eventData.destination && (
            <InfoRow
              icon={Server}
              label="Ziel"
              value={String(eventData.destination)}
            />
          )}
        </div>
      );

    case 'modification':
    case 'metadata_update':
      return (
        <div className="space-y-3">
          {eventData.field && (
            <InfoRow
              icon={Edit3}
              label="Bearbeitetes Feld"
              value={String(eventData.field)}
            />
          )}
          {eventData.old_value !== undefined && (
            <InfoRow
              icon={FileText}
              label="Alter Wert"
              value={
                <span className="text-muted-foreground line-through">
                  {String(eventData.old_value)}
                </span>
              }
            />
          )}
          {eventData.new_value !== undefined && (
            <InfoRow
              icon={FileText}
              label="Neuer Wert"
              value={
                <span className="text-green-600 dark:text-green-400">
                  {String(eventData.new_value)}
                </span>
              }
            />
          )}
          {eventData.reason && (
            <InfoRow
              icon={FileText}
              label="Begründung"
              value={String(eventData.reason)}
            />
          )}
        </div>
      );

    case 'approval':
    case 'rejection':
      return (
        <div className="space-y-3">
          {eventData.comment && (
            <InfoRow
              icon={FileText}
              label="Kommentar"
              value={String(eventData.comment)}
            />
          )}
          {eventData.workflow_step && (
            <InfoRow
              icon={Tag}
              label="Workflow-Schritt"
              value={String(eventData.workflow_step)}
            />
          )}
        </div>
      );

    default:
      return null;
  }
}

// =============================================================================
// Helper Functions
// =============================================================================

function formatFileSize(bytes: number): string {
  const units = ['Bytes', 'KB', 'MB', 'GB'];
  let unitIndex = 0;
  let size = bytes;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  return `${formatNumberDE(size, unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}
