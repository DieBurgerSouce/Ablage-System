/**
 * DelayNode Component
 *
 * ReactFlow Knoten für Zeitverzögerungen.
 * Unterstützt Sekunden-Delays und absolute Zeitpunkte.
 */

import { memo, useMemo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { Clock, Timer, Calendar, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StepConfig } from '../../types/workflow-types';

interface DelayNodeData {
  label: string;
  config: StepConfig;
  stepName?: string;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} Sekunden`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} Minuten`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} Stunden`;
  return `${Math.floor(seconds / 86400)} Tage`;
}

function DelayNode({ data, selected }: NodeProps<DelayNodeData>) {
  const delaySeconds = data.config?.delay_seconds;
  const delayUntil = data.config?.delay_until;
  const isAbsoluteTime = !!delayUntil;

  const delaySummary = useMemo(() => {
    if (delayUntil) {
      try {
        const date = new Date(delayUntil);
        return date.toLocaleString('de-DE', {
          dateStyle: 'short',
          timeStyle: 'short',
        });
      } catch {
        return delayUntil;
      }
    }
    if (delaySeconds) {
      return formatDuration(delaySeconds);
    }
    return 'Nicht konfiguriert';
  }, [delaySeconds, delayUntil]);

  return (
    <div
      className={cn(
        'min-w-[160px] rounded-lg border-2 bg-card shadow-md transition-all',
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
      <div className="flex items-center gap-2 rounded-t-md bg-gray-500 px-3 py-2">
        <Clock className="h-4 w-4 text-white" />
        <span className="text-sm font-medium text-white">Verzögerung</span>
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        <div className="text-sm font-medium text-foreground">
          {data.stepName || data.label || 'Warten'}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {isAbsoluteTime ? (
            <Calendar className="h-3 w-3" />
          ) : (
            <Timer className="h-3 w-3" />
          )}
          <span>{delaySummary}</span>
        </div>
      </div>

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

export default memo(DelayNode);
