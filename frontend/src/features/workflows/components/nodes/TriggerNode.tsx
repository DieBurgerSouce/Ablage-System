/**
 * TriggerNode Component
 *
 * ReactFlow Knoten für Workflow-Trigger.
 * Zeigt Trigger-Typ und Konfiguration an.
 */

import { memo, useMemo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import {
  FileText,
  Clock,
  Filter,
  Play,
  Webhook,
  Settings,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TriggerType, TriggerConfig } from '../../types/workflow-types';

interface TriggerNodeData {
  label: string;
  triggerType: TriggerType;
  config: TriggerConfig;
  isActive?: boolean;
}

const triggerIcons: Record<TriggerType, React.ElementType> = {
  document_event: FileText,
  schedule: Clock,
  condition: Filter,
  manual: Play,
  webhook: Webhook,
};

const triggerLabels: Record<TriggerType, string> = {
  document_event: 'Dokument-Event',
  schedule: 'Zeitplan',
  condition: 'Bedingung',
  manual: 'Manuell',
  webhook: 'Webhook',
};

const triggerColors: Record<TriggerType, string> = {
  document_event: 'bg-blue-500',
  schedule: 'bg-purple-500',
  condition: 'bg-orange-500',
  manual: 'bg-green-500',
  webhook: 'bg-pink-500',
};

function TriggerNode({ data, selected }: NodeProps<TriggerNodeData>) {
  const Icon = triggerIcons[data.triggerType] || Play;
  const label = triggerLabels[data.triggerType] || 'Trigger';
  const colorClass = triggerColors[data.triggerType] || 'bg-gray-500';

  const configSummary = useMemo(() => {
    const config = data.config;
    switch (data.triggerType) {
      case 'document_event':
        return config.events?.join(', ') || 'Alle Events';
      case 'schedule':
        return config.cron || 'Nicht konfiguriert';
      case 'condition':
        return config.watch_fields?.join(', ') || 'Keine Felder';
      case 'webhook':
        return config.webhook_path || '/webhook';
      case 'manual':
        return 'Klick zum Starten';
      default:
        return '';
    }
  }, [data.triggerType, data.config]);

  return (
    <div
      className={cn(
        'min-w-[180px] rounded-lg border-2 bg-card shadow-md transition-all',
        selected ? 'border-primary ring-2 ring-primary/20' : 'border-border',
        !data.isActive && 'opacity-60'
      )}
    >
      {/* Header */}
      <div className={cn('flex items-center gap-2 rounded-t-md px-3 py-2', colorClass)}>
        <Icon className="h-4 w-4 text-white" />
        <span className="text-sm font-medium text-white">{label}</span>
        {data.isActive === false && (
          <span className="ml-auto text-xs text-white/70">Inaktiv</span>
        )}
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        <div className="text-sm font-medium text-foreground">
          {data.label || 'Workflow-Start'}
        </div>
        <div className="text-xs text-muted-foreground">{configSummary}</div>
      </div>

      {/* Settings Indicator */}
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

export default memo(TriggerNode);
