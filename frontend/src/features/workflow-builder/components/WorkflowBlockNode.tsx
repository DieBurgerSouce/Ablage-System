import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { cn } from '@/lib/utils';

interface WorkflowBlockData {
  label: string;
  type: string;
  config: Record<string, unknown>;
  definition: {
    icon: string;
    description?: string;
    inputs: Array<{ id: string; label: string; type: string }>;
    outputs: Array<{ id: string; label: string; type: string }>;
    config_schema: Record<string, unknown>;
  };
}

function WorkflowBlockNode({ data, selected }: NodeProps<WorkflowBlockData>) {
  const { definition } = data;
  const configEntries = Object.entries(data.config).filter(
    ([, v]) => v !== undefined && v !== ''
  );

  return (
    <div
      className={cn(
        'min-w-[180px] max-w-[220px] rounded-lg border-2 bg-card shadow-md transition-all',
        selected ? 'border-primary ring-2 ring-primary/20' : 'border-border'
      )}
    >
      {/* Target handles (inputs) */}
      {definition.inputs.length > 0 ? (
        definition.inputs.map((input, idx) => (
          <Handle
            key={input.id}
            id={input.id}
            type="target"
            position={Position.Top}
            className="!h-3 !w-3 !border-2 !border-background !bg-primary"
            style={
              definition.inputs.length > 1
                ? {
                    left: `${((idx + 1) / (definition.inputs.length + 1)) * 100}%`,
                  }
                : undefined
            }
            title={input.label}
          />
        ))
      ) : (
        <Handle
          type="target"
          position={Position.Top}
          className="!h-3 !w-3 !border-2 !border-background !bg-primary"
        />
      )}

      {/* Header */}
      <div className="flex items-center gap-2 rounded-t-[5px] bg-primary/10 px-3 py-2">
        <span className="text-lg leading-none" aria-hidden="true">
          {definition.icon}
        </span>
        <span className="truncate text-sm font-medium text-foreground">
          {data.label}
        </span>
      </div>

      {/* Body */}
      <div className="space-y-1 px-3 py-2">
        <span className="inline-block rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          {data.type}
        </span>
        {configEntries.length > 0 && (
          <p className="truncate text-xs text-muted-foreground">
            {configEntries
              .slice(0, 2)
              .map(([k, v]) => `${k}: ${String(v)}`)
              .join(', ')}
            {configEntries.length > 2 && ` +${configEntries.length - 2}`}
          </p>
        )}
      </div>

      {/* Source handles (outputs) */}
      {definition.outputs.length > 0 ? (
        definition.outputs.map((output, idx) => (
          <Handle
            key={output.id}
            id={output.id}
            type="source"
            position={Position.Bottom}
            className="!h-3 !w-3 !border-2 !border-background !bg-primary"
            style={
              definition.outputs.length > 1
                ? {
                    left: `${((idx + 1) / (definition.outputs.length + 1)) * 100}%`,
                  }
                : undefined
            }
            title={output.label}
          />
        ))
      ) : (
        <Handle
          type="source"
          position={Position.Bottom}
          className="!h-3 !w-3 !border-2 !border-background !bg-primary"
        />
      )}
    </div>
  );
}

export default memo(WorkflowBlockNode);
