/**
 * LoopNode Component
 *
 * ReactFlow Knoten für Schleifen.
 * Unterstützt count, while und for_each Schleifentypen.
 */

import { memo, useMemo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { Repeat, Hash, RefreshCw, List, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StepConfig } from '../../types/workflow-types';

interface LoopNodeData {
  label: string;
  config: StepConfig;
  stepName?: string;
}

type LoopType = 'count' | 'while' | 'for_each';

const loopIcons: Record<LoopType, React.ElementType> = {
  count: Hash,
  while: RefreshCw,
  for_each: List,
};

const loopLabels: Record<LoopType, string> = {
  count: 'Anzahl-Schleife',
  while: 'While-Schleife',
  for_each: 'Für jedes Element',
};

function LoopNode({ data, selected }: NodeProps<LoopNodeData>) {
  const loopType = (data.config?.loop_type as LoopType) || 'count';
  const Icon = loopIcons[loopType] || Repeat;
  const typeLabel = loopLabels[loopType] || 'Schleife';

  const loopSummary = useMemo(() => {
    const config = data.config;
    if (!config) return 'Nicht konfiguriert';

    switch (loopType) {
      case 'count':
        return config.count ? `${config.count} Durchläufe` : 'Anzahl festlegen...';
      case 'while':
        return config.max_iterations
          ? `Max. ${config.max_iterations} Iterationen`
          : 'Bedingung festlegen...';
      case 'for_each':
        return config.items_field
          ? `Über: ${config.items_field}`
          : 'Feld auswählen...';
      default:
        return '';
    }
  }, [loopType, data.config]);

  return (
    <div
      className={cn(
        'min-w-[180px] rounded-lg border-2 bg-card shadow-md transition-all',
        selected ? 'border-primary ring-2 ring-primary/20' : 'border-border'
      )}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Top}
        className="!h-3 !w-3 !border-2 !border-background !bg-primary"
      />

      {/* Header */}
      <div className="flex items-center gap-2 rounded-t-md bg-indigo-500 px-3 py-2">
        <Repeat className="h-4 w-4 text-white" />
        <span className="text-sm font-medium text-white">Schleife</span>
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        <div className="text-sm font-medium text-foreground">
          {data.stepName || data.label || 'Wiederholen'}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Icon className="h-3 w-3" />
          <span>{typeLabel}</span>
        </div>
        <div className="text-xs text-muted-foreground">{loopSummary}</div>
      </div>

      {/* Loop Indicator */}
      <div className="flex items-center justify-between border-t border-border px-2 py-1">
        <div className="flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400">
          <Repeat className="h-3 w-3" />
          <span>Inhalt</span>
        </div>
        <Settings className="h-3 w-3 text-muted-foreground" />
        <div className="text-xs text-muted-foreground">Weiter</div>
      </div>

      {/* Output Handles */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="loop"
        className="!left-[25%] !h-3 !w-3 !border-2 !border-background !bg-indigo-500"
        title="Schleifeninhalt"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="continue"
        className="!left-[75%] !h-3 !w-3 !border-2 !border-background !bg-primary"
        title="Nach Schleife"
      />
    </div>
  );
}

export default memo(LoopNode);
