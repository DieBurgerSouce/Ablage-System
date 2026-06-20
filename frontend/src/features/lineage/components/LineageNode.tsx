/**
 * LineageNode Component
 *
 * Custom Node für React Flow mit Event-spezifischen Icons und Styling.
 * Zeigt Lineage-Events mit visueller Unterscheidung nach Typ.
 */

import { memo, useMemo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { cn } from '@/lib/utils';
import { formatDateTimeDE, formatNumberDE } from '@/lib/format';
import { Badge } from '@/components/ui/badge';
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
} from 'lucide-react';
import type { LineageEventType } from '@/lib/api/services/lineage';

// =============================================================================
// Types
// =============================================================================

export type LineageNodeData = {
  id: string;
  eventType: LineageEventType;
  eventData: Record<string, unknown>;
  timestamp: string;
  durationMs: number | null;
  confidence: number | null;
  userId: string | null;
  sourceService: string | null;
  label: string;
  selected?: boolean;
};

export type LineageFlowNode = Node<LineageNodeData, 'lineageEvent'>;

// =============================================================================
// Event Configuration
// =============================================================================

interface EventConfig {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bgColor: string;
  borderColor: string;
  darkBgColor: string;
  darkBorderColor: string;
}

const EVENT_CONFIG: Record<LineageEventType, EventConfig> = {
  import: {
    icon: FileUp,
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    darkBgColor: 'dark:bg-blue-950',
    darkBorderColor: 'dark:border-blue-800',
  },
  ocr_start: {
    icon: ScanSearch,
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
    darkBgColor: 'dark:bg-amber-950',
    darkBorderColor: 'dark:border-amber-800',
  },
  ocr_complete: {
    icon: CheckCircle2,
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
    darkBgColor: 'dark:bg-green-950',
    darkBorderColor: 'dark:border-green-800',
  },
  ocr_failed: {
    icon: XCircle,
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    darkBgColor: 'dark:bg-red-950',
    darkBorderColor: 'dark:border-red-800',
  },
  classification: {
    icon: Tag,
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
    darkBgColor: 'dark:bg-purple-950',
    darkBorderColor: 'dark:border-purple-800',
  },
  extraction: {
    icon: FileText,
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-50',
    borderColor: 'border-indigo-200',
    darkBgColor: 'dark:bg-indigo-950',
    darkBorderColor: 'dark:border-indigo-800',
  },
  entity_link: {
    icon: Link2,
    color: 'text-cyan-600 dark:text-cyan-400',
    bgColor: 'bg-cyan-50',
    borderColor: 'border-cyan-200',
    darkBgColor: 'dark:bg-cyan-950',
    darkBorderColor: 'dark:border-cyan-800',
  },
  entity_unlink: {
    icon: Unlink2,
    color: 'text-slate-600 dark:text-slate-400',
    bgColor: 'bg-slate-50',
    borderColor: 'border-slate-200',
    darkBgColor: 'dark:bg-slate-950',
    darkBorderColor: 'dark:border-slate-800',
  },
  modification: {
    icon: Edit3,
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
    darkBgColor: 'dark:bg-orange-950',
    darkBorderColor: 'dark:border-orange-800',
  },
  metadata_update: {
    icon: Edit3,
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
    darkBgColor: 'dark:bg-orange-950',
    darkBorderColor: 'dark:border-orange-800',
  },
  tag_change: {
    icon: Tag,
    color: 'text-pink-600 dark:text-pink-400',
    bgColor: 'bg-pink-50',
    borderColor: 'border-pink-200',
    darkBgColor: 'dark:bg-pink-950',
    darkBorderColor: 'dark:border-pink-800',
  },
  approval: {
    icon: ThumbsUp,
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50',
    borderColor: 'border-emerald-200',
    darkBgColor: 'dark:bg-emerald-950',
    darkBorderColor: 'dark:border-emerald-800',
  },
  rejection: {
    icon: ThumbsDown,
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    darkBgColor: 'dark:bg-red-950',
    darkBorderColor: 'dark:border-red-800',
  },
  escalation: {
    icon: AlertTriangle,
    color: 'text-yellow-600 dark:text-yellow-400',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-200',
    darkBgColor: 'dark:bg-yellow-950',
    darkBorderColor: 'dark:border-yellow-800',
  },
  export: {
    icon: Download,
    color: 'text-teal-600 dark:text-teal-400',
    bgColor: 'bg-teal-50',
    borderColor: 'border-teal-200',
    darkBgColor: 'dark:bg-teal-950',
    darkBorderColor: 'dark:border-teal-800',
  },
  archive: {
    icon: Archive,
    color: 'text-gray-600 dark:text-gray-400',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
    darkBgColor: 'dark:bg-gray-950',
    darkBorderColor: 'dark:border-gray-800',
  },
  restore: {
    icon: RotateCcw,
    color: 'text-lime-600 dark:text-lime-400',
    bgColor: 'bg-lime-50',
    borderColor: 'border-lime-200',
    darkBgColor: 'dark:bg-lime-950',
    darkBorderColor: 'dark:border-lime-800',
  },
  soft_delete: {
    icon: Trash2,
    color: 'text-rose-600 dark:text-rose-400',
    bgColor: 'bg-rose-50',
    borderColor: 'border-rose-200',
    darkBgColor: 'dark:bg-rose-950',
    darkBorderColor: 'dark:border-rose-800',
  },
  hard_delete: {
    icon: Trash2,
    color: 'text-red-700 dark:text-red-500',
    bgColor: 'bg-red-100',
    borderColor: 'border-red-300',
    darkBgColor: 'dark:bg-red-950',
    darkBorderColor: 'dark:border-red-900',
  },
};

// =============================================================================
// Helper Functions
// =============================================================================

function formatDuration(ms: number | null): string {
  if (ms === null) return '-';

  if (ms < 1000) {
    return `${ms}ms`;
  }

  const seconds = ms / 1000;
  if (seconds < 60) {
    return `${formatNumberDE(seconds, 1)}s`;
  }

  const minutes = seconds / 60;
  return `${formatNumberDE(minutes, 1)}min`;
}

function formatConfidence(confidence: number | null): string {
  if (confidence === null) return '-';
  return `${formatNumberDE(confidence * 100, 0)}%`;
}

// =============================================================================
// Component
// =============================================================================

export const LineageNode = memo(function LineageNode({
  data,
  selected,
}: NodeProps<LineageFlowNode>) {
  const config = useMemo(
    () => EVENT_CONFIG[data.eventType] || EVENT_CONFIG.modification,
    [data.eventType]
  );

  const Icon = config.icon;

  const isSelected = selected || data.selected;

  return (
    <div
      className={cn(
        'min-w-[200px] max-w-[280px] rounded-lg border-2 shadow-md transition-all duration-200',
        config.bgColor,
        config.borderColor,
        config.darkBgColor,
        config.darkBorderColor,
        isSelected && 'ring-2 ring-primary ring-offset-2 scale-105 shadow-lg'
      )}
    >
      {/* Input Handle (links) */}
      <Handle
        type="target"
        position={Position.Left}
        className={cn(
          'w-3 h-3 border-2 bg-background',
          config.borderColor,
          config.darkBorderColor
        )}
      />

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-inherit">
        <div
          className={cn(
            'flex items-center justify-center w-8 h-8 rounded-full',
            config.bgColor,
            config.darkBgColor
          )}
        >
          <Icon className={cn('w-4 h-4', config.color)} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{data.label}</p>
          <p className="text-xs text-muted-foreground">
            {formatDateTimeDE(data.timestamp)}
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="px-3 py-2 space-y-1.5">
        {/* Confidence Badge */}
        {data.confidence !== null && (
          <div className="flex items-center gap-1.5 text-xs">
            <Gauge className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Konfidenz:</span>
            <Badge
              variant={data.confidence >= 0.8 ? 'default' : 'secondary'}
              className="text-xs px-1.5 py-0"
            >
              {formatConfidence(data.confidence)}
            </Badge>
          </div>
        )}

        {/* Duration */}
        {data.durationMs !== null && (
          <div className="flex items-center gap-1.5 text-xs">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Dauer:</span>
            <span className="font-medium">{formatDuration(data.durationMs)}</span>
          </div>
        )}

        {/* Source Service */}
        {data.sourceService && (
          <div className="flex items-center gap-1.5 text-xs">
            <ScanSearch className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Service:</span>
            <span className="font-medium truncate">{data.sourceService}</span>
          </div>
        )}

        {/* User */}
        {data.userId && (
          <div className="flex items-center gap-1.5 text-xs">
            <User className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Benutzer:</span>
            <span className="font-medium truncate">{data.userId.slice(0, 8)}...</span>
          </div>
        )}

        {/* Event-specific data preview */}
        {data.eventData && Object.keys(data.eventData).length > 0 && (
          <div className="pt-1 border-t border-inherit">
            {renderEventDataPreview(data.eventType, data.eventData)}
          </div>
        )}
      </div>

      {/* Output Handle (rechts) */}
      <Handle
        type="source"
        position={Position.Right}
        className={cn(
          'w-3 h-3 border-2 bg-background',
          config.borderColor,
          config.darkBorderColor
        )}
      />
    </div>
  );
});

// =============================================================================
// Event Data Preview Renderer
// =============================================================================

function renderEventDataPreview(
  eventType: LineageEventType,
  eventData: Record<string, unknown>
): React.ReactNode {
  switch (eventType) {
    case 'import':
      return (
        <div className="text-xs space-y-0.5">
          {Boolean(eventData.source_type) && (
            <p>
              <span className="text-muted-foreground">Quelle: </span>
              <span className="font-medium">{String(eventData.source_type)}</span>
            </p>
          )}
          {Boolean(eventData.filename) && (
            <p className="truncate">
              <span className="text-muted-foreground">Datei: </span>
              <span className="font-medium">{String(eventData.filename)}</span>
            </p>
          )}
        </div>
      );

    case 'ocr_complete':
    case 'ocr_failed':
      return (
        <div className="text-xs space-y-0.5">
          {Boolean(eventData.backend) && (
            <p>
              <span className="text-muted-foreground">Backend: </span>
              <span className="font-medium">{String(eventData.backend)}</span>
            </p>
          )}
          {eventData.pages !== undefined && eventData.pages !== null && (
            <p>
              <span className="text-muted-foreground">Seiten: </span>
              <span className="font-medium">{String(eventData.pages)}</span>
            </p>
          )}
        </div>
      );

    case 'classification':
      return (
        <div className="text-xs space-y-0.5">
          {Boolean(eventData.document_type) && (
            <p>
              <span className="text-muted-foreground">Typ: </span>
              <span className="font-medium">{String(eventData.document_type)}</span>
            </p>
          )}
        </div>
      );

    case 'entity_link':
      return (
        <div className="text-xs space-y-0.5">
          {Boolean(eventData.entity_name) && (
            <p className="truncate">
              <span className="text-muted-foreground">Partner: </span>
              <span className="font-medium">{String(eventData.entity_name)}</span>
            </p>
          )}
          {Boolean(eventData.match_type) && (
            <p>
              <span className="text-muted-foreground">Match: </span>
              <span className="font-medium">{String(eventData.match_type)}</span>
            </p>
          )}
        </div>
      );

    case 'export':
      return (
        <div className="text-xs space-y-0.5">
          {Boolean(eventData.format) && (
            <p>
              <span className="text-muted-foreground">Format: </span>
              <span className="font-medium">{String(eventData.format)}</span>
            </p>
          )}
          {Boolean(eventData.destination) && (
            <p className="truncate">
              <span className="text-muted-foreground">Ziel: </span>
              <span className="font-medium">{String(eventData.destination)}</span>
            </p>
          )}
        </div>
      );

    case 'modification':
    case 'metadata_update':
      return (
        <div className="text-xs space-y-0.5">
          {Boolean(eventData.field) && (
            <p>
              <span className="text-muted-foreground">Feld: </span>
              <span className="font-medium">{String(eventData.field)}</span>
            </p>
          )}
          {Boolean(eventData.reason) && (
            <p className="truncate">
              <span className="text-muted-foreground">Grund: </span>
              <span className="font-medium">{String(eventData.reason)}</span>
            </p>
          )}
        </div>
      );

    default:
      return null;
  }
}
