/**
 * Node Detail Panel Component
 * Zeigt Details zum ausgewählten Knoten im Graph
 */

import { X, ExternalLink } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { GraphNode, GraphEdge, NodeType } from '../types';

interface NodeDetailPanelProps {
  node: GraphNode;
  edges: GraphEdge[];
  onClose: () => void;
  onLoadGraph: (nodeId: string) => void;
}

const NODE_TYPE_LABELS: Record<NodeType, string> = {
  entity: 'Entität',
  document: 'Dokument',
  invoice: 'Rechnung',
  transaction: 'Transaktion',
  payment: 'Zahlung',
};

const NODE_TYPE_COLORS: Record<NodeType, string> = {
  entity: 'blue',
  document: 'green',
  invoice: 'orange',
  transaction: 'purple',
  payment: 'teal',
};

export function NodeDetailPanel({ node, edges, onClose, onLoadGraph }: NodeDetailPanelProps) {
  // Finde verwandte Kanten
  const relatedEdges = edges.filter((edge) => edge.source === node.id || edge.target === node.id);
  const incomingEdges = relatedEdges.filter((edge) => edge.target === node.id);
  const outgoingEdges = relatedEdges.filter((edge) => edge.source === node.id);

  // Bestimme Link zu Detail-Seite
  const getEntityLink = (): string | null => {
    if (node.type === 'entity' && node.data.id) {
      return `/entities/${node.data.id}`;
    }
    if (node.type === 'document' && node.data.id) {
      return `/documents/${node.data.id}`;
    }
    if (node.type === 'invoice' && node.data.id) {
      return `/invoices/${node.data.id}`;
    }
    return null;
  };

  const entityLink = getEntityLink();

  return (
    <Card className="flex h-full flex-col shadow-lg">
      <CardHeader className="flex-shrink-0 border-b border-border">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="mb-2">
              <Badge
                variant="outline"
                className="text-xs"
                style={{
                  borderColor: `var(--${NODE_TYPE_COLORS[node.type]}-500)`,
                  color: `var(--${NODE_TYPE_COLORS[node.type]}-700)`,
                }}
              >
                {NODE_TYPE_LABELS[node.type]}
              </Badge>
            </div>
            <CardTitle className="text-lg">{node.label}</CardTitle>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="flex-1 space-y-6 overflow-y-auto p-4">
        {/* Knotendaten */}
        <div>
          <h3 className="mb-2 text-sm font-semibold">Details</h3>
          <div className="space-y-2">
            {Object.entries(node.data).map(([key, value]) => (
              <div key={key} className="flex gap-2 text-sm">
                <span className="font-medium text-muted-foreground">{key}:</span>
                <span className="flex-1 break-words">
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Eingehende Verbindungen */}
        {incomingEdges.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Eingehende Verbindungen ({incomingEdges.length})</h3>
            <div className="space-y-1">
              {incomingEdges.map((edge, idx) => (
                <div key={idx} className="rounded border border-border p-2 text-sm">
                  <Badge variant="secondary" className="mb-1 text-xs">
                    {edge.type}
                  </Badge>
                  <div className="text-muted-foreground">{edge.label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Ausgehende Verbindungen */}
        {outgoingEdges.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Ausgehende Verbindungen ({outgoingEdges.length})</h3>
            <div className="space-y-1">
              {outgoingEdges.map((edge, idx) => (
                <div key={idx} className="rounded border border-border p-2 text-sm">
                  <Badge variant="secondary" className="mb-1 text-xs">
                    {edge.type}
                  </Badge>
                  <div className="text-muted-foreground">{edge.label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Aktionen */}
        <div className="space-y-2 border-t border-border pt-4">
          <Button variant="outline" className="w-full" onClick={() => onLoadGraph(node.id)}>
            Graph um diesen Knoten laden
          </Button>
          {entityLink && (
            <Button variant="outline" className="w-full" asChild>
              <a href={entityLink} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="mr-2 h-4 w-4" />
                Details anzeigen
              </a>
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
