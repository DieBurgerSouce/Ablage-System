/**
 * BPMN Start Event Node
 *
 * Visual representation of BPMN Start Events in React Flow.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { cn } from '@/lib/utils';
import { Play, Clock, Mail } from 'lucide-react';
import type { BPMNNodeData } from '../../types/bpmn-types';

interface StartEventNodeProps extends NodeProps<BPMNNodeData> {}

export const StartEventNode = memo(function StartEventNode({
  data,
  selected,
}: StartEventNodeProps) {
  const trigger = data.element.properties?.trigger as string | undefined;

  const getIcon = () => {
    switch (trigger) {
      case 'timer':
        return <Clock className="h-4 w-4" />;
      case 'message':
        return <Mail className="h-4 w-4" />;
      default:
        return <Play className="h-4 w-4" />;
    }
  };

  return (
    <div
      className={cn(
        'flex flex-col items-center gap-1',
        selected && 'opacity-100'
      )}
    >
      <div
        className={cn(
          'flex h-12 w-12 items-center justify-center rounded-full border-2 border-green-500 bg-green-50 text-green-700 transition-all',
          selected && 'ring-2 ring-green-400 ring-offset-2',
          'hover:border-green-600 hover:bg-green-100'
        )}
      >
        {getIcon()}
      </div>
      {data.label && (
        <span className="max-w-[100px] truncate text-xs font-medium text-gray-700">
          {data.label}
        </span>
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-green-500 !bg-white"
      />
    </div>
  );
});

export default StartEventNode;
