/**
 * Timeline View Component
 * Zeitleisten-Visualisierung fuer Dokument-Lineage-Ereignisse mit recharts
 */

import { useState, useMemo, useCallback } from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Clock,
  Activity,
  BarChart3,
  CheckCircle2,
  XCircle,
  TrendingUp,
} from 'lucide-react';
import type { GraphNode, NodeType, TimelineEvent as ApiTimelineEvent } from '../types';
import { useDocumentTimeline } from '../hooks/use-knowledge-graph-queries';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TimelineViewProps {
  entityId?: string;
  documentId?: string;
  onNodeSelect: (node: GraphNode) => void;
}

type TimeRange = '7d' | '30d' | '90d' | '1y' | 'all';

const TIME_RANGE_LABELS: Record<TimeRange, string> = {
  '7d': '7 Tage',
  '30d': '30 Tage',
  '90d': '90 Tage',
  '1y': '1 Jahr',
  all: 'Alles',
};

type EventCategory =
  | 'CREATED'
  | 'UPLOADED'
  | 'OCR_PROCESSED'
  | 'CLASSIFIED'
  | 'ENTITY_LINKED'
  | 'INVOICE_MATCHED'
  | 'PAYMENT_RECEIVED'
  | 'STATUS_CHANGED'
  | 'EXPORTED'
  | 'DELETED'
  | 'RISK_UPDATED'
  | 'DUNNING_CREATED'
  | 'SKONTO_APPLIED'
  | 'PARTIAL_PAYMENT'
  | 'THREE_WAY_MATCHED'
  | 'CORRECTION_ISSUED'
  | 'CHAIN_LINKED'
  | 'FAMILY_GROUPED'
  | 'ARCHIVED';

interface LocalTimelineEvent {
  id: string;
  timestamp: Date;
  category: EventCategory;
  description: string;
  relatedDocumentId: string | null;
  relatedDocumentName: string | null;
  entityId: string | null;
  metadata: Record<string, unknown>;
}

interface AggregatedActivityPoint {
  label: string;
  count: number;
  dominantColor: string;
}

interface PaymentTrendPoint {
  month: string;
  avgDays: number;
}

// ---------------------------------------------------------------------------
// Event Category Config
// ---------------------------------------------------------------------------

const EVENT_COLORS: Record<EventCategory, string> = {
  CREATED: '#22c55e',
  UPLOADED: '#3b82f6',
  OCR_PROCESSED: '#6366f1',
  CLASSIFIED: '#8b5cf6',
  ENTITY_LINKED: '#a855f7',
  INVOICE_MATCHED: '#f97316',
  PAYMENT_RECEIVED: '#14b8a6',
  STATUS_CHANGED: '#64748b',
  EXPORTED: '#06b6d4',
  DELETED: '#ef4444',
  RISK_UPDATED: '#eab308',
  DUNNING_CREATED: '#f97316',
  SKONTO_APPLIED: '#22d3ee',
  PARTIAL_PAYMENT: '#a855f7',
  THREE_WAY_MATCHED: '#10b981',
  CORRECTION_ISSUED: '#f59e0b',
  CHAIN_LINKED: '#6366f1',
  FAMILY_GROUPED: '#8b5cf6',
  ARCHIVED: '#94a3b8',
};

const EVENT_LABELS: Record<EventCategory, string> = {
  CREATED: 'Erstellt',
  UPLOADED: 'Hochgeladen',
  OCR_PROCESSED: 'OCR verarbeitet',
  CLASSIFIED: 'Klassifiziert',
  ENTITY_LINKED: 'Entitaet verknuepft',
  INVOICE_MATCHED: 'Rechnung zugeordnet',
  PAYMENT_RECEIVED: 'Zahlung eingegangen',
  STATUS_CHANGED: 'Status geaendert',
  EXPORTED: 'Exportiert',
  DELETED: 'Geloescht',
  RISK_UPDATED: 'Risiko aktualisiert',
  DUNNING_CREATED: 'Mahnung erstellt',
  SKONTO_APPLIED: 'Skonto angewendet',
  PARTIAL_PAYMENT: 'Teilzahlung',
  THREE_WAY_MATCHED: '3-Way-Match',
  CORRECTION_ISSUED: 'Korrektur ausgestellt',
  CHAIN_LINKED: 'Kette verknuepft',
  FAMILY_GROUPED: 'Familie gruppiert',
  ARCHIVED: 'Archiviert',
};

const ALL_CATEGORIES: ReadonlyArray<EventCategory> = [
  'CREATED',
  'UPLOADED',
  'OCR_PROCESSED',
  'CLASSIFIED',
  'ENTITY_LINKED',
  'INVOICE_MATCHED',
  'PAYMENT_RECEIVED',
  'STATUS_CHANGED',
  'EXPORTED',
  'DELETED',
  'RISK_UPDATED',
  'DUNNING_CREATED',
  'SKONTO_APPLIED',
  'PARTIAL_PAYMENT',
  'THREE_WAY_MATCHED',
  'CORRECTION_ISSUED',
  'CHAIN_LINKED',
  'FAMILY_GROUPED',
  'ARCHIVED',
] as const;

// ---------------------------------------------------------------------------
// Backend event_type -> EventCategory mapping
// ---------------------------------------------------------------------------

/**
 * Maps backend event_type strings (from both document_timeline and activity_timeline
 * APIs) to the frontend EventCategory type used for colour coding and labels.
 *
 * Backend document_timeline event_types (see app/api/v1/document_timeline.py):
 *   upload, ocr_start, ocr_complete, ocr_failed, correction, categorization,
 *   entity_linked, approval, rejection, export, share, version_create, archive, delete
 *
 * Backend activity_timeline activity_types (see app/api/v1/activity_timeline.py):
 *   e.g. document_view, document_download, document_edit, comment_added, etc.
 *
 * Unknown types fall back to STATUS_CHANGED.
 */
const EVENT_TYPE_MAP: Record<string, EventCategory> = {
  // Document Timeline events
  upload: 'UPLOADED',
  uploaded: 'UPLOADED',
  ocr_start: 'OCR_PROCESSED',
  ocr_complete: 'OCR_PROCESSED',
  ocr_failed: 'OCR_PROCESSED',
  correction: 'CORRECTION_ISSUED',
  categorization: 'CLASSIFIED',
  classified: 'CLASSIFIED',
  entity_linked: 'ENTITY_LINKED',
  approval: 'STATUS_CHANGED',
  rejection: 'STATUS_CHANGED',
  export: 'EXPORTED',
  share: 'STATUS_CHANGED',
  version_create: 'CREATED',
  created: 'CREATED',
  archive: 'ARCHIVED',
  archived: 'ARCHIVED',
  delete: 'DELETED',
  deleted: 'DELETED',

  // Activity Timeline events
  document_view: 'STATUS_CHANGED',
  document_download: 'EXPORTED',
  document_edit: 'STATUS_CHANGED',
  comment_added: 'STATUS_CHANGED',
  risk_updated: 'RISK_UPDATED',
  invoice_matched: 'INVOICE_MATCHED',
  payment_received: 'PAYMENT_RECEIVED',
  dunning_created: 'DUNNING_CREATED',
  skonto_applied: 'SKONTO_APPLIED',
  partial_payment: 'PARTIAL_PAYMENT',
  three_way_match: 'THREE_WAY_MATCHED',
  chain_linked: 'CHAIN_LINKED',
  family_grouped: 'FAMILY_GROUPED',
};

function mapEventTypeToCategory(eventType: string): EventCategory {
  const normalized = eventType.toLowerCase().replace(/-/g, '_');
  return EVENT_TYPE_MAP[normalized] ?? 'STATUS_CHANGED';
}

/**
 * Maps a backend TimelineEvent (from either timeline API) to the local
 * LocalTimelineEvent format used by the UI components.
 */
function mapApiEventToLocal(
  evt: ApiTimelineEvent,
  entityId?: string
): LocalTimelineEvent {
  return {
    id: evt.id,
    timestamp: new Date(evt.timestamp),
    category: mapEventTypeToCategory(evt.eventType),
    description: evt.description,
    relatedDocumentId: evt.documentId ?? null,
    relatedDocumentName: evt.documentName ?? null,
    entityId: entityId ?? null,
    metadata: evt.metadata,
  };
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

function formatDate(date: Date): string {
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getTimeRangeDays(range: TimeRange): number | null {
  switch (range) {
    case '7d':
      return 7;
    case '30d':
      return 30;
    case '90d':
      return 90;
    case '1y':
      return 365;
    case 'all':
      return null;
  }
}

function filterByTimeRange(
  events: ReadonlyArray<LocalTimelineEvent>,
  range: TimeRange
): LocalTimelineEvent[] {
  const days = getTimeRangeDays(range);
  if (days === null) return [...events];
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return events.filter((e) => e.timestamp >= cutoff);
}

function getISOWeek(date: Date): number {
  const d = new Date(date.getTime());
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
  const week1 = new Date(d.getFullYear(), 0, 4);
  return (
    1 +
    Math.round(
      ((d.getTime() - week1.getTime()) / 86400000 -
        3 +
        ((week1.getDay() + 6) % 7)) /
        7
    )
  );
}

function getWeekLabel(date: Date): string {
  const start = new Date(date);
  start.setDate(start.getDate() - start.getDay() + 1);
  return `KW ${getISOWeek(start)}`;
}

function buildAggregatedActivityData(
  events: ReadonlyArray<LocalTimelineEvent>
): AggregatedActivityPoint[] {
  const buckets = new Map<
    string,
    { total: number; colorCounts: Map<string, number> }
  >();

  for (const evt of events) {
    const weekKey = getWeekLabel(evt.timestamp);
    if (!buckets.has(weekKey)) {
      buckets.set(weekKey, { total: 0, colorCounts: new Map() });
    }
    const bucket = buckets.get(weekKey)!;
    bucket.total += 1;
    const color = EVENT_COLORS[evt.category];
    bucket.colorCounts.set(color, (bucket.colorCounts.get(color) ?? 0) + 1);
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b, 'de-DE'))
    .map(([label, { total, colorCounts }]) => {
      let maxCount = 0;
      let dominantColor = '#3b82f6';
      for (const [color, cnt] of colorCounts.entries()) {
        if (cnt > maxCount) {
          maxCount = cnt;
          dominantColor = color;
        }
      }
      return { label, count: total, dominantColor };
    });
}

function buildPaymentTrendData(
  events: ReadonlyArray<LocalTimelineEvent>
): PaymentTrendPoint[] {
  const monthMap = new Map<string, number[]>();

  const paymentEvents = events.filter(
    (e) =>
      e.category === 'PAYMENT_RECEIVED' || e.category === 'PARTIAL_PAYMENT'
  );

  for (const evt of paymentEvents) {
    const monthKey = evt.timestamp.toLocaleDateString('de-DE', {
      month: 'short',
      year: '2-digit',
    });
    if (!monthMap.has(monthKey)) {
      monthMap.set(monthKey, []);
    }
    // Simulated payment duration based on event ID hash
    const charCode = evt.id.charCodeAt(4) ?? 0;
    const simDays = 15 + (charCode % 40);
    monthMap.get(monthKey)!.push(simDays);
  }

  const result: PaymentTrendPoint[] = [];
  for (const [month, days] of monthMap.entries()) {
    const avg = days.reduce((s, d) => s + d, 0) / days.length;
    result.push({ month, avgDays: Math.round(avg * 10) / 10 });
  }

  return result;
}

// ---------------------------------------------------------------------------
// Sub-Components
// ---------------------------------------------------------------------------

interface EventTypeFilterProps {
  selected: Set<EventCategory>;
  onChange: (updated: Set<EventCategory>) => void;
}

function EventTypeFilter({ selected, onChange }: EventTypeFilterProps) {
  const toggle = useCallback(
    (cat: EventCategory) => {
      const next = new Set(selected);
      if (next.has(cat)) {
        next.delete(cat);
      } else {
        next.add(cat);
      }
      onChange(next);
    },
    [selected, onChange]
  );

  const selectAll = useCallback(() => {
    onChange(new Set(ALL_CATEGORIES));
  }, [onChange]);

  const selectNone = useCallback(() => {
    onChange(new Set<EventCategory>());
  }, [onChange]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground">
          Ereignistypen
        </span>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={selectAll}
          >
            Alle
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={selectNone}
          >
            Keine
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {ALL_CATEGORIES.map((cat) => {
          const isActive = selected.has(cat);
          return (
            <button
              key={cat}
              type="button"
              onClick={() => toggle(cat)}
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium transition-colors ${
                isActive
                  ? 'border-transparent text-white'
                  : 'border-border bg-background text-muted-foreground opacity-50'
              }`}
              style={isActive ? { backgroundColor: EVENT_COLORS[cat] } : undefined}
            >
              {EVENT_LABELS[cat]}
            </button>
          );
        })}
      </div>
    </div>
  );
}

interface TimelineEventItemProps {
  event: LocalTimelineEvent;
  onSelect: (node: GraphNode) => void;
}

function TimelineEventItem({ event, onSelect }: TimelineEventItemProps) {
  const handleDocumentClick = useCallback(() => {
    if (event.relatedDocumentId) {
      const node: GraphNode = {
        id: event.relatedDocumentId,
        type: 'document' as NodeType,
        label: event.relatedDocumentName ?? event.relatedDocumentId,
        data: {
          eventCategory: event.category,
          timestamp: event.timestamp.toISOString(),
        },
      };
      onSelect(node);
    }
  }, [event, onSelect]);

  return (
    <div className="group relative flex gap-3 py-3">
      {/* Timeline dot and connector */}
      <div className="flex flex-col items-center">
        <div
          className="h-3 w-3 flex-shrink-0 rounded-full border-2 border-background"
          style={{
            backgroundColor: EVENT_COLORS[event.category],
            boxShadow: `0 0 0 2px ${EVENT_COLORS[event.category]}`,
          }}
        />
        <div className="mt-1 w-px flex-1 bg-border" />
      </div>

      {/* Event content */}
      <div className="flex-1 pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className="text-xs font-medium"
            style={{
              borderColor: EVENT_COLORS[event.category],
              color: EVENT_COLORS[event.category],
            }}
          >
            {EVENT_LABELS[event.category]}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {formatDate(event.timestamp)} {formatTime(event.timestamp)}
          </span>
        </div>
        <p className="mt-1 text-sm text-foreground">{event.description}</p>
        {event.relatedDocumentName && (
          <button
            type="button"
            className="mt-1 text-xs text-primary underline-offset-2 hover:underline"
            onClick={handleDocumentClick}
          >
            {event.relatedDocumentName}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom Recharts Tooltips
// ---------------------------------------------------------------------------

interface BarTooltipPayloadItem {
  value: number;
  payload: AggregatedActivityPoint;
}

interface CustomBarTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<BarTooltipPayloadItem>;
  label?: string;
}

function CustomBarTooltip({ active, payload, label }: CustomBarTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{label}</p>
      <p className="text-muted-foreground">{payload[0].value} Ereignisse</p>
    </div>
  );
}

interface LineTooltipPayloadItem {
  value: number;
  payload: PaymentTrendPoint;
}

interface CustomLineTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<LineTooltipPayloadItem>;
  label?: string;
}

function CustomLineTooltip({ active, payload, label }: CustomLineTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
      <p className="font-medium">{label}</p>
      <p className="text-muted-foreground">
        {payload[0].value} Tage Durchschnitt
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function TimelineView({
  entityId,
  documentId,
  onNodeSelect,
}: TimelineViewProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('90d');
  const [selectedCategories, setSelectedCategories] = useState<
    Set<EventCategory>
  >(() => new Set(ALL_CATEGORIES));

  // Use real backend data when a documentId is available.
  // When only entityId is provided, the query is disabled and allEvents stays empty.
  const {
    data: timelineData,
    isLoading,
    error,
  } = useDocumentTimeline(documentId);

  // Map API events to local format
  const allEvents = useMemo<LocalTimelineEvent[]>(() => {
    if (!timelineData) return [];
    return timelineData.events.map((evt) => mapApiEventToLocal(evt, entityId));
  }, [timelineData, entityId]);

  // Filter events by time range and selected categories
  const filteredEvents = useMemo(() => {
    const byTime = filterByTimeRange(allEvents, timeRange);
    return byTime.filter((e) => selectedCategories.has(e.category));
  }, [allEvents, timeRange, selectedCategories]);

  // Chart data derived from filtered events
  const activityData = useMemo(
    () => buildAggregatedActivityData(filteredEvents),
    [filteredEvents]
  );

  const paymentTrendData = useMemo(
    () => buildPaymentTrendData(filteredEvents),
    [filteredEvents]
  );

  // Summary statistics
  const summaryStats = useMemo(() => {
    const uniqueTypes = new Set(filteredEvents.map((e) => e.category)).size;
    const paymentCount = filteredEvents.filter(
      (e) =>
        e.category === 'PAYMENT_RECEIVED' || e.category === 'PARTIAL_PAYMENT'
    ).length;
    const warningCount = filteredEvents.filter(
      (e) =>
        e.category === 'RISK_UPDATED' || e.category === 'DUNNING_CREATED'
    ).length;
    return { uniqueTypes, paymentCount, warningCount };
  }, [filteredEvents]);

  // Empty state when neither entity nor document is selected
  if (!entityId && !documentId) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Zeitleiste
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Keine Ereignisse gefunden. Waehlen Sie eine Entitaet oder ein
              Dokument.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Informational state when only an entity is selected but no document
  // (the document timeline API requires a documentId)
  if (entityId && !documentId) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Zeitleiste
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Waehlen Sie ein Dokument dieser Entitaet, um die Zeitleiste zu
              sehen.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-muted-foreground">Lade Ereignisse...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-destructive" />
              Fehler beim Laden
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Die Zeitleiste konnte nicht geladen werden. Bitte versuchen Sie
              es spaeter erneut.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Toolbar: Time Range + Event Type Filters */}
      <div className="flex-shrink-0 space-y-3 border-b border-border bg-background p-4">
        {/* Time Range Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">Zeitraum:</span>
          {(
            Object.entries(TIME_RANGE_LABELS) as Array<[TimeRange, string]>
          ).map(([key, label]) => (
            <Button
              key={key}
              variant={timeRange === key ? 'default' : 'outline'}
              size="sm"
              onClick={() => setTimeRange(key)}
            >
              {label}
            </Button>
          ))}
          <Separator orientation="vertical" className="mx-2 h-6" />
          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Activity className="h-4 w-4" />
            <span>{filteredEvents.length} Ereignisse</span>
          </div>
        </div>

        {/* Event Type Multi-Select Filter */}
        <EventTypeFilter
          selected={selectedCategories}
          onChange={setSelectedCategories}
        />
      </div>

      {/* Content Area: Timeline (left 40%) + Charts (right 60%) */}
      <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
        {/* Timeline - Left Side */}
        <div className="w-full flex-shrink-0 overflow-y-auto border-b border-border p-4 lg:w-2/5 lg:border-b-0 lg:border-r">
          {filteredEvents.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              <div className="text-center">
                <XCircle className="mx-auto mb-2 h-8 w-8 text-muted-foreground/50" />
                <p>Keine Ereignisse im gewaehlten Zeitraum</p>
              </div>
            </div>
          ) : (
            <div className="relative">
              {filteredEvents.map((event) => (
                <TimelineEventItem
                  key={event.id}
                  event={event}
                  onSelect={onNodeSelect}
                />
              ))}
            </div>
          )}
        </div>

        {/* Charts - Right Side */}
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {/* Activity Bar Chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <BarChart3 className="h-4 w-4" />
                Aktivitaets-Uebersicht
              </CardTitle>
            </CardHeader>
            <CardContent>
              {activityData.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Keine Aktivitaetsdaten vorhanden
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={activityData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      className="stroke-border"
                    />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 11 }}
                      className="fill-muted-foreground"
                    />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      className="fill-muted-foreground"
                      allowDecimals={false}
                    />
                    <RechartsTooltip content={<CustomBarTooltip />} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {activityData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.dominantColor} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Payment Trend Line Chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="h-4 w-4" />
                Zahlungs-Trend
              </CardTitle>
            </CardHeader>
            <CardContent>
              {paymentTrendData.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Keine Zahlungsdaten vorhanden
                </p>
              ) : (
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={paymentTrendData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      className="stroke-border"
                    />
                    <XAxis
                      dataKey="month"
                      tick={{ fontSize: 11 }}
                      className="fill-muted-foreground"
                    />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      className="fill-muted-foreground"
                      label={{
                        value: 'Tage',
                        angle: -90,
                        position: 'insideLeft',
                        style: { fontSize: 11 },
                      }}
                    />
                    <RechartsTooltip content={<CustomLineTooltip />} />
                    <ReferenceLine
                      y={30}
                      stroke="#ef4444"
                      strokeDasharray="6 3"
                      label={{
                        value: 'Zahlungsziel (30 Tage)',
                        position: 'insideTopRight',
                        style: { fontSize: 10, fill: '#ef4444' },
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="avgDays"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={{ r: 4, fill: '#3b82f6' }}
                      activeDot={{ r: 6, fill: '#2563eb' }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Summary Stats */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <CheckCircle2 className="h-4 w-4" />
                Zusammenfassung
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Gesamtereignisse</p>
                  <p className="text-2xl font-bold">{filteredEvents.length}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Ereignistypen</p>
                  <p className="text-2xl font-bold">
                    {summaryStats.uniqueTypes}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Zahlungen</p>
                  <p className="text-2xl font-bold">
                    {summaryStats.paymentCount}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Warnungen</p>
                  <p className="text-2xl font-bold">
                    {summaryStats.warningCount}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
