/**
 * GraphEdge - Custom React Flow Edge mit Beziehungstyp-Label
 */

import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
} from '@xyflow/react';
import { Badge } from '@/components/ui/badge';
import type { EdgeRelationType } from '../types/document-graph-types';

const EDGE_LABELS: Record<EdgeRelationType, string> = {
  chain_link: 'Kette',
  lineage_parent: 'Herkunft',
  reference: 'Referenz',
};

const EDGE_COLORS: Record<EdgeRelationType, string> = {
  chain_link: 'hsl(var(--primary))',
  lineage_parent: 'hsl(var(--chart-2))',
  reference: 'hsl(var(--muted-foreground))',
};

export function GraphEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const relationType = (data?.relationType as EdgeRelationType) || 'chain_link';
  const color = EDGE_COLORS[relationType];

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 8,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{ stroke: color, strokeWidth: 2 }}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan pointer-events-auto absolute"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
          }}
        >
          <Badge
            variant="secondary"
            className="text-[10px] px-1.5 py-0 shadow-sm bg-background border"
          >
            {EDGE_LABELS[relationType]}
          </Badge>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
