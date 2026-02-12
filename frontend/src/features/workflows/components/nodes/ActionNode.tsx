/**
 * ActionNode Component
 *
 * ReactFlow Knoten für Workflow-Aktionen.
 * Unterstützt 20+ verschiedene Aktionstypen.
 */

import { memo, useMemo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import {
  FolderOpen,
  Tag,
  FileType,
  RefreshCw,
  Trash2,
  Bell,
  Mail,
  Webhook,
  Globe,
  FileSearch,
  Brain,
  Download,
  Copy,
  Clock,
  Variable,
  MessageSquare,
  UserPlus,
  ListTodo,
  CheckCircle,
  Zap,
  Settings,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActionType, StepConfig } from '../../types/workflow-types';

interface ActionNodeData {
  label: string;
  config: StepConfig;
  stepName?: string;
  retryOnFailure?: boolean;
}

const actionIcons: Record<ActionType, React.ElementType> = {
  move_folder: FolderOpen,
  assign_tags: Tag,
  assign_document_type: FileType,
  update_status: RefreshCw,
  delete_document: Trash2,
  send_notification: Bell,
  send_email: Mail,
  call_webhook: Webhook,
  http_request: Globe,
  start_ocr: FileSearch,
  ai_categorization: Brain,
  export_document: Download,
  duplicate_check: Copy,
  delay: Clock,
  set_variable: Variable,
  log_message: MessageSquare,
  assign_user: UserPlus,
  create_task: ListTodo,
  request_approval: CheckCircle,
};

const actionLabels: Record<ActionType, string> = {
  move_folder: 'In Ordner verschieben',
  assign_tags: 'Tags zuweisen',
  assign_document_type: 'Dokumenttyp setzen',
  update_status: 'Status ändern',
  delete_document: 'Dokument löschen',
  send_notification: 'Benachrichtigung',
  send_email: 'E-Mail senden',
  call_webhook: 'Webhook aufrufen',
  http_request: 'HTTP-Request',
  start_ocr: 'OCR starten',
  ai_categorization: 'KI-Kategorisierung',
  export_document: 'Exportieren',
  duplicate_check: 'Duplikat-Prüfung',
  delay: 'Verzögerung',
  set_variable: 'Variable setzen',
  log_message: 'Log-Nachricht',
  assign_user: 'Benutzer zuweisen',
  create_task: 'Aufgabe erstellen',
  request_approval: 'Genehmigung anfordern',
};

const actionColors: Record<ActionType, string> = {
  move_folder: 'bg-blue-500',
  assign_tags: 'bg-cyan-500',
  assign_document_type: 'bg-indigo-500',
  update_status: 'bg-teal-500',
  delete_document: 'bg-red-500',
  send_notification: 'bg-amber-500',
  send_email: 'bg-pink-500',
  call_webhook: 'bg-violet-500',
  http_request: 'bg-purple-500',
  start_ocr: 'bg-emerald-500',
  ai_categorization: 'bg-fuchsia-500',
  export_document: 'bg-lime-500',
  duplicate_check: 'bg-sky-500',
  delay: 'bg-gray-500',
  set_variable: 'bg-slate-500',
  log_message: 'bg-stone-500',
  assign_user: 'bg-rose-500',
  create_task: 'bg-yellow-500',
  request_approval: 'bg-green-500',
};

function ActionNode({ data, selected }: NodeProps<ActionNodeData>) {
  const actionType = data.config?.action_type;
  const Icon = actionType ? actionIcons[actionType] || Zap : Zap;
  const label = actionType ? actionLabels[actionType] || 'Aktion' : 'Aktion';
  const colorClass = actionType ? actionColors[actionType] || 'bg-gray-500' : 'bg-gray-500';

  const configSummary = useMemo(() => {
    const config = data.config;
    if (!config || !actionType) return '';

    switch (actionType) {
      case 'move_folder':
        return config.folder_id ? 'Ordner ausgewählt' : 'Ordner wählen...';
      case 'assign_tags':
        return config.tag_names?.join(', ') || config.tag_ids?.length
          ? `${(config.tag_names || config.tag_ids)?.length} Tags`
          : 'Tags wählen...';
      case 'assign_document_type':
        return config.document_type || 'Typ wählen...';
      case 'update_status':
        return config.status || 'Status wählen...';
      case 'send_notification':
        return config.title || 'Titel eingeben...';
      case 'send_email':
        return config.to?.length ? `${config.to.length} Empfänger` : 'Empfänger...';
      case 'http_request':
        return config.method && config.url ? `${config.method} ${config.url}` : 'URL eingeben...';
      case 'delay':
        return config.delay_seconds
          ? `${config.delay_seconds} Sekunden`
          : config.delay_until || 'Zeit konfigurieren...';
      case 'set_variable':
        return config.name ? `${config.name} = ...` : 'Variable...';
      case 'start_ocr':
        return config.backend || 'Auto-Backend';
      default:
        return '';
    }
  }, [actionType, data.config]);

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
      <div className={cn('flex items-center gap-2 rounded-t-md px-3 py-2', colorClass)}>
        <Icon className="h-4 w-4 text-white" />
        <span className="text-sm font-medium text-white">{label}</span>
        {data.retryOnFailure && (
          <RefreshCw className="ml-auto h-3 w-3 text-white/70" title="Retry bei Fehler" />
        )}
      </div>

      {/* Body */}
      <div className="space-y-2 p-3">
        <div className="text-sm font-medium text-foreground">
          {data.stepName || data.label || 'Aktion ausführen'}
        </div>
        {configSummary && (
          <div className="text-xs text-muted-foreground">{configSummary}</div>
        )}
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

export default memo(ActionNode);
