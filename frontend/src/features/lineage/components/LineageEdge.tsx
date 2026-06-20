/**
 * LineageEdge Component
 *
 * Custom Edge für React Flow mit Timing-Anzeige zwischen Events.
 * Zeigt die Zeitdifferenz zwischen aufeinanderfolgenden Events.
 */

import { memo, useMemo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react';
import { cn } from '@/lib/utils';
import { formatNumberDE } from '@/lib/format';
import { Clock } from 'lucide-react';

// =============================================================================
// Types
// =============================================================================

export type LineageEdgeData = {
  /** Zeit zwischen den Events in Millisekunden */
  timeDeltaMs?: number;
  /** Zeige Timing-Label an */
  showTiming?: boolean;
  /** Edge-Typ für unterschiedliches Styling */
  edgeType?: 'default' | 'success' | 'error' | 'warning';
};

export type LineageFlowEdge = Edge<LineageEdgeData, 'lineageTiming'>;

// =============================================================================
// Helper Functions
// =============================================================================

function formatTimeDelta(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }

  const seconds = ms / 1000;
  if (seconds < 60) {
    return `${formatNumberDE(seconds, 1)}s`;
  }

  const minutes = seconds / 60;
  if (minutes < 60) {
    return `${formatNumberDE(minutes, 1)}min`;
  }

  const hours = minutes / 60;
  if (hours < 24) {
    return `${formatNumberDE(hours, 1)}h`;
  }

  const days = hours / 24;
  return `${formatNumberDE(days, 0)}d`;
}

function getEdgeColor(edgeType?: string): { stroke: string; label: string } {
  switch (edgeType) {
    case 'success':
      return {
        stroke: 'stroke-green-500 dark:stroke-green-400',
        label: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
      };
    case 'error':
      return {
        stroke: 'stroke-red-500 dark:stroke-red-400',
        label: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
      };
    case 'warning':
      return {
        stroke: 'stroke-amber-500 dark:stroke-amber-400',
        label: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
      };
    default:
      return {
        stroke: 'stroke-slate-400 dark:stroke-slate-500',
        label: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
      };
  }
}

// =============================================================================
// Component
// =============================================================================

export const LineageEdge = memo(function LineageEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  style,
}: EdgeProps<LineageFlowEdge>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const colors = useMemo(() => getEdgeColor(data?.edgeType), [data?.edgeType]);

  const showTimingLabel = data?.showTiming !== false && data?.timeDeltaMs !== undefined;

  return (
    <>
      {/* Edge Path */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          strokeWidth: selected ? 3 : 2,
        }}
        className={cn(
          colors.stroke,
          'transition-all duration-200',
          selected && 'stroke-primary'
        )}
        markerEnd="url(#lineage-arrow)"
      />

      {/* Timing Label */}
      {showTimingLabel && data?.timeDeltaMs !== undefined && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
          >
            <div
              className={cn(
                'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                'border shadow-sm',
                colors.label,
                'transition-all duration-200',
                selected && 'ring-2 ring-primary ring-offset-1'
              )}
            >
              <Clock className="w-3 h-3" />
              <span>{formatTimeDelta(data.timeDeltaMs)}</span>
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});

// =============================================================================
// SVG Defs for Arrow Marker
// =============================================================================

export function LineageEdgeMarkerDefs() {
  return (
    <svg style={{ position: 'absolute', width: 0, height: 0 }}>
      <defs>
        <marker
          id="lineage-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path
            d="M 0 0 L 10 5 L 0 10 z"
            className="fill-slate-400 dark:fill-slate-500"
          />
        </marker>
      </defs>
    </svg>
  );
}
