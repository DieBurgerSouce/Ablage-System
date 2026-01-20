/**
 * BPMN Gateway Node
 *
 * Visual representation of BPMN Gateways (Exclusive, Parallel, Inclusive, etc.) in React Flow.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { cn } from '@/lib/utils';
import { X, Plus, Circle, Zap, Asterisk } from 'lucide-react';
import type { BPMNNodeData, BPMNElementType } from '../../types/bpmn-types';

interface GatewayNodeProps extends NodeProps<BPMNNodeData> {}

const gatewayIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  exclusiveGateway: X,
  parallelGateway: Plus,
  inclusiveGateway: Circle,
  eventBasedGateway: Zap,
  complexGateway: Asterisk,
};

const gatewayColors: Record<string, string> = {
  exclusiveGateway: 'border-amber-500 bg-amber-50',
  parallelGateway: 'border-blue-500 bg-blue-50',
  inclusiveGateway: 'border-green-500 bg-green-50',
  eventBasedGateway: 'border-purple-500 bg-purple-50',
  complexGateway: 'border-gray-500 bg-gray-50',
};

const gatewayIconColors: Record<string, string> = {
  exclusiveGateway: 'text-amber-600',
  parallelGateway: 'text-blue-600',
  inclusiveGateway: 'text-green-600',
  eventBasedGateway: 'text-purple-600',
  complexGateway: 'text-gray-600',
};

export const GatewayNode = memo(function GatewayNode({
  data,
  selected,
}: GatewayNodeProps) {
  const gatewayType = data.type as BPMNElementType;
  const Icon = gatewayIcons[gatewayType] || X;
  const colorClass = gatewayColors[gatewayType] || 'border-amber-500 bg-amber-50';
  const iconColor = gatewayIconColors[gatewayType] || 'text-amber-600';

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
        className="!h-3 !w-3 !border-2 !border-amber-500 !bg-white"
      />
      {/* Top handle for incoming from above */}
      <Handle
        type="target"
        position={Position.Top}
        id="top"
        className="!h-3 !w-3 !border-2 !border-amber-500 !bg-white"
      />
      <div
        className={cn(
          'flex h-12 w-12 rotate-45 items-center justify-center border-2 transition-all',
          colorClass,
          selected && 'ring-2 ring-amber-400 ring-offset-2',
          'hover:shadow-md'
        )}
      >
        <div className="-rotate-45">
          <Icon className={cn('h-5 w-5', iconColor)} />
        </div>
      </div>
      {data.label && (
        <span className="max-w-[100px] truncate text-xs font-medium text-gray-700">
          {data.label}
        </span>
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-amber-500 !bg-white"
      />
      {/* Bottom handle for outgoing downwards */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        className="!h-3 !w-3 !border-2 !border-amber-500 !bg-white"
      />
    </div>
  );
});

export default GatewayNode;
