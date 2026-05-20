/**
 * GraphNode - Custom React Flow Node fuer Dokumente
 *
 * Zeigt Dokument-Typ Icon, Titel, Datum und Betrag.
 */

import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import {
  FileText,
  Receipt,
  Truck,
  FileCheck,
  ClipboardList,
  CreditCard,
  AlertTriangle,
  File,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { GraphNodeData } from '../types/document-graph-types';

// ==================== Icon Mapping ====================

const DOCUMENT_TYPE_CONFIG: Record<string, {
  icon: LucideIcon;
  label: string;
  color: string;
}> = {
  quote: { icon: ClipboardList, label: 'Angebot', color: 'text-blue-500 bg-blue-500/10' },
  order: { icon: FileCheck, label: 'Auftrag', color: 'text-green-500 bg-green-500/10' },
  delivery_note: { icon: Truck, label: 'Lieferschein', color: 'text-orange-500 bg-orange-500/10' },
  invoice: { icon: Receipt, label: 'Rechnung', color: 'text-purple-500 bg-purple-500/10' },
  credit_note: { icon: CreditCard, label: 'Gutschrift', color: 'text-emerald-500 bg-emerald-500/10' },
  reminder: { icon: AlertTriangle, label: 'Mahnung', color: 'text-red-500 bg-red-500/10' },
  dunning: { icon: AlertTriangle, label: 'Inkasso', color: 'text-red-700 bg-red-700/10' },
  receipt: { icon: FileText, label: 'Beleg', color: 'text-cyan-500 bg-cyan-500/10' },
};

const DEFAULT_CONFIG = { icon: File, label: 'Dokument', color: 'text-muted-foreground bg-muted' };

// ==================== Helpers ====================

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function formatAmount(amount: number | null): string {
  if (amount == null) return '';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

// ==================== Component ====================

export function GraphNode({ data, selected }: NodeProps) {
  const nodeData = data as unknown as GraphNodeData;
  const config = DOCUMENT_TYPE_CONFIG[nodeData.documentType] || DEFAULT_CONFIG;
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'px-4 py-3 shadow-md rounded-lg bg-card border-2 min-w-[200px] max-w-[260px] transition-all',
        selected ? 'border-primary ring-2 ring-primary/20' : 'border-border hover:border-primary/50'
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="w-3 h-3 !bg-muted-foreground"
      />

      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className={cn('p-2 rounded-md shrink-0', config.color)}>
          <Icon className="w-4 h-4" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
              {config.label}
            </Badge>
            {nodeData.chainPosition > 0 && (
              <span className="text-[10px] text-muted-foreground">
                #{nodeData.chainPosition}
              </span>
            )}
          </div>
          <p className="text-sm font-medium truncate mt-1" title={nodeData.label}>
            {nodeData.label}
          </p>
          <div className="flex items-center justify-between gap-2 mt-1">
            <span className="text-xs text-muted-foreground">
              {formatDate(nodeData.date)}
            </span>
            {nodeData.amount != null && (
              <span className="text-xs font-medium text-foreground">
                {formatAmount(nodeData.amount)}
              </span>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="w-3 h-3 !bg-muted-foreground"
      />
    </div>
  );
}
