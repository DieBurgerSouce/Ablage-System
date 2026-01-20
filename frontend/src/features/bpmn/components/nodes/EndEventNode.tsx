/**
 * BPMN End Event Node
 *
 * Visual representation of BPMN End Events in React Flow.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { cn } from '@/lib/utils';
import { Square, AlertTriangle, XCircle } from 'lucide-react';
import type { BPMNNodeData } from '../../types/bpmn-types';

interface EndEventNodeProps extends NodeProps<BPMNNodeData> {}

export const EndEventNode = memo(function EndEventNode({
  data,
  selected,
}: EndEventNodeProps) {
  const trigger = data.element.properties?.trigger as string | undefined;

  const getIcon = () => {
    switch (trigger) {
      case 'error':
        return <AlertTriangle className="h-4 w-4" />;
      case 'terminate':
        return <XCircle className="h-4 w-4" />;
      default:
        return <Square className="h-3 w-3 fill-current" />;
    }
  };

  const getBorderColor = () => {
    switch (trigger) {
      case 'error':
        return 'border-orange-500 bg-orange-50 text-orange-700';
      case 'terminate':
        return 'border-red-600 bg-red-50 text-red-700';
      default:
        return 'border-red-500 bg-red-50 text-red-700';
    }
  };

  return (
    <div
      className={cn(
        'flex flex-col items-center gap-1',
        selected && 'opacity-100'
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-2 !border-red-500 !bg-white"
      />
      <div
        className={cn(
          'flex h-12 w-12 items-center justify-center rounded-full border-[3px] transition-all',
          getBorderColor(),
          selected && 'ring-2 ring-red-400 ring-offset-2',
          'hover:brightness-95'
        )}
      >
        {getIcon()}
      </div>
      {data.label && (
        <span className="max-w-[100px] truncate text-xs font-medium text-gray-700">
          {data.label}
        </span>
      )}
    </div>
  );
});

export default EndEventNode;
