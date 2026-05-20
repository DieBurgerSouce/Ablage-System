/**
 * Graph Legend Component
 * Legende für Knoten- und Kantentypen im Graph
 */

import { Card } from '@/components/ui/card';
import { Building2, FileText, Receipt, ArrowRightLeft, CreditCard } from 'lucide-react';
import type { NodeType } from '../types';

const NODE_TYPES: Array<{ type: NodeType; label: string; color: string; icon: typeof FileText }> = [
  { type: 'entity', label: 'Entität', color: '#3b82f6', icon: Building2 },
  { type: 'document', label: 'Dokument', color: '#22c55e', icon: FileText },
  { type: 'invoice', label: 'Rechnung', color: '#f97316', icon: Receipt },
  { type: 'transaction', label: 'Transaktion', color: '#a855f7', icon: ArrowRightLeft },
  { type: 'payment', label: 'Zahlung', color: '#14b8a6', icon: CreditCard },
];

const EDGE_TYPES = [
  { type: 'CONTAINS_DOCUMENT', label: 'Enthält Dokument' },
  { type: 'ISSUED_TO', label: 'Ausgestellt an' },
  { type: 'PAID_VIA', label: 'Bezahlt via' },
  { type: 'REFERENCES', label: 'Referenziert' },
  { type: 'LINKED_TO', label: 'Verknüpft mit' },
];

export function GraphLegend() {
  return (
    <Card className="absolute bottom-4 left-4 max-w-xs space-y-3 p-3 shadow-lg">
      <div>
        <h3 className="mb-2 text-xs font-semibold text-muted-foreground">Knotentypen</h3>
        <div className="space-y-1.5">
          {NODE_TYPES.map(({ type, label, color, icon: Icon }) => (
            <div key={type} className="flex items-center gap-2 text-xs">
              <div className="flex h-5 w-5 items-center justify-center rounded-full" style={{ backgroundColor: color }}>
                <Icon className="h-3 w-3 text-white" />
              </div>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-border pt-3">
        <h3 className="mb-2 text-xs font-semibold text-muted-foreground">Beziehungstypen</h3>
        <div className="space-y-1.5">
          {EDGE_TYPES.map(({ type, label }) => (
            <div key={type} className="flex items-center gap-2 text-xs">
              <div className="h-0.5 w-4 bg-slate-500"></div>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
