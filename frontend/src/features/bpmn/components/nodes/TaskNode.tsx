/**
 * BPMN Task Node
 *
 * Visual representation of BPMN Tasks (User, Service, Script, etc.) in React Flow.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { cn } from '@/lib/utils';
import {
  User,
  Cog,
  Code,
  Hand,
  Send,
  Inbox,
  BookOpen,
} from 'lucide-react';
import type { BPMNNodeData, BPMNElementType } from '../../types/bpmn-types';

interface TaskNodeProps extends NodeProps<BPMNNodeData> {}

const taskIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  userTask: User,
  serviceTask: Cog,
  scriptTask: Code,
  manualTask: Hand,
  sendTask: Send,
  receiveTask: Inbox,
  businessRuleTask: BookOpen,
};

const taskColors: Record<string, string> = {
  userTask: 'border-blue-400 bg-blue-50',
  serviceTask: 'border-purple-400 bg-purple-50',
  scriptTask: 'border-amber-400 bg-amber-50',
  manualTask: 'border-gray-400 bg-gray-50',
  sendTask: 'border-cyan-400 bg-cyan-50',
  receiveTask: 'border-teal-400 bg-teal-50',
  businessRuleTask: 'border-indigo-400 bg-indigo-50',
};

const taskIconColors: Record<string, string> = {
  userTask: 'text-blue-600',
  serviceTask: 'text-purple-600',
  scriptTask: 'text-amber-600',
  manualTask: 'text-gray-600',
  sendTask: 'text-cyan-600',
  receiveTask: 'text-teal-600',
  businessRuleTask: 'text-indigo-600',
};

export const TaskNode = memo(function TaskNode({
  data,
  selected,
}: TaskNodeProps) {
  const taskType = data.type as BPMNElementType;
  const Icon = taskIcons[taskType] || Cog;
  const colorClass = taskColors[taskType] || 'border-gray-400 bg-gray-50';
  const iconColor = taskIconColors[taskType] || 'text-gray-600';

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
        className="!h-3 !w-3 !border-2 !border-gray-400 !bg-white"
      />
      <div
        className={cn(
          'relative min-w-[140px] rounded-lg border-2 px-4 py-3 shadow-sm transition-all',
          colorClass,
          selected && 'ring-2 ring-blue-400 ring-offset-2',
          'hover:shadow-md'
        )}
      >
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded',
              iconColor
            )}
          >
            <Icon className="h-4 w-4" />
          </div>
          <span className="max-w-[120px] truncate text-sm font-medium text-gray-800">
            {data.label || 'Task'}
          </span>
        </div>
        {data.element.description && (
          <p className="mt-1 text-xs text-gray-500 line-clamp-2">
            {data.element.description}
          </p>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-gray-400 !bg-white"
      />
    </div>
  );
});

export default TaskNode;
