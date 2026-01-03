/**
 * ParallelNode Component
 *
 * ReactFlow Knoten fuer parallele Ausfuehrung.
 * Zeigt mehrere gleichzeitig ausgefuehrte Schritte an.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { GitFork, Layers, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StepConfig } from '../../types/workflow-types';

interface ParallelNodeData {
  label: string;
  config: StepConfig;
  stepName?: string;
}

function ParallelNode({ data, selected }: NodeProps<ParallelNodeData>) {
  const steps = data.config?.steps || [];
  const stepCount = steps.length;

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
      <div className="flex items-center gap-2 rounded-t-md bg-cyan-500 px-3 py-2">
        <GitFork className="h-4 w-4 text-white" />
        <span className="text-sm font-medium text-white">Parallel</span>
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        <div className="text-sm font-medium text-foreground">
          {data.stepName || data.label || 'Parallele Ausfuehrung'}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Layers className="h-3 w-3" />
          <span>
            {stepCount > 0
              ? `${stepCount} Schritte gleichzeitig`
              : 'Keine Schritte konfiguriert'}
          </span>
        </div>
      </div>

      {/* Step References */}
      {stepCount > 0 && (
        <div className="border-t border-border px-3 py-2">
          <div className="flex flex-wrap gap-1">
            {steps.slice(0, 4).map((stepId: string, index: number) => (
              <span
                key={stepId}
                className="rounded bg-cyan-100 px-1.5 py-0.5 text-xs text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300"
              >
                #{index + 1}
              </span>
            ))}
            {stepCount > 4 && (
              <span className="text-xs text-muted-foreground">
                +{stepCount - 4} mehr
              </span>
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-end border-t border-border px-2 py-1">
        <Settings className="h-3 w-3 text-muted-foreground" />
      </div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-3 !w-3 !border-2 !border-background !bg-primary"
      />
    </div>
  );
}

export default memo(ParallelNode);
