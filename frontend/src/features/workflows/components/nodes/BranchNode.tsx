/**
 * BranchNode Component
 *
 * ReactFlow Knoten für Verzweigungen (If-Then-Else).
 * Unterstützt mehrere benannte Ausgänge.
 */

import { memo, useMemo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { GitBranch, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StepConfig, Branch } from '../../types/workflow-types';

interface BranchNodeData {
  label: string;
  config: StepConfig;
  stepName?: string;
}

function BranchNode({ data, selected }: NodeProps<BranchNodeData>) {
  const branches = data.config?.branches || [];
  const defaultBranch = data.config?.default_branch || 'default';

  const handlePositions = useMemo(() => {
    const total = branches.length + 1; // +1 for default branch
    const positions: { id: string; label: string; position: number }[] = [];

    branches.forEach((branch: Branch, index: number) => {
      positions.push({
        id: branch.name,
        label: branch.name,
        position: ((index + 1) / (total + 1)) * 100,
      });
    });

    // Default branch at the end
    positions.push({
      id: 'default',
      label: defaultBranch,
      position: (total / (total + 1)) * 100,
    });

    return positions;
  }, [branches, defaultBranch]);

  return (
    <div
      className={cn(
        'min-w-[200px] rounded-lg border-2 bg-card shadow-md transition-all',
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
      <div className="flex items-center gap-2 rounded-t-md bg-violet-500 px-3 py-2">
        <GitBranch className="h-4 w-4 text-white" />
        <span className="text-sm font-medium text-white">Verzweigung</span>
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        <div className="text-sm font-medium text-foreground">
          {data.stepName || data.label || 'Verzweigung'}
        </div>
        <div className="text-xs text-muted-foreground">
          {branches.length} Zweige + Standard
        </div>
      </div>

      {/* Branch Labels */}
      <div className="flex justify-between border-t border-border px-2 py-1">
        {handlePositions.map((handle, _index) => (
          <div
            key={handle.id}
            className={cn(
              'text-xs',
              handle.id === 'default' ? 'text-muted-foreground' : 'text-primary'
            )}
          >
            {handle.label}
          </div>
        ))}
        <Settings className="h-3 w-3 text-muted-foreground" />
      </div>

      {/* Output Handles */}
      {handlePositions.map((handle) => (
        <Handle
          key={handle.id}
          type="source"
          position={Position.Bottom}
          id={handle.id}
          style={{ left: `${handle.position}%` }}
          className={cn(
            '!h-3 !w-3 !border-2 !border-background',
            handle.id === 'default' ? '!bg-gray-400' : '!bg-violet-500'
          )}
        />
      ))}
    </div>
  );
}

export default memo(BranchNode);
