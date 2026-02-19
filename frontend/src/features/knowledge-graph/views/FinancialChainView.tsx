/**
 * Financial Chain View
 * Spezialisierte Ansicht fuer Finanzketten: Bestellung > Lieferschein > Rechnung > Zahlung > Mahnung
 * Horizontales Layout mit @xyflow/react
 */

import { useCallback, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
  MarkerType,
  BackgroundVariant,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  FileText,
  Receipt,
  CreditCard,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react';
import type { GraphNode } from '../types';
import { useFinancialChain } from '../hooks/use-knowledge-graph-queries';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FinancialChainViewProps {
  entityId: string;
  onNodeSelect: (node: GraphNode) => void;
}

type FinancialStage = 'bestellung' | 'lieferschein' | 'rechnung' | 'zahlung' | 'mahnung';

type MatchStatus = 'matched' | 'partial' | 'unmatched';

interface FinancialDocument {
  id: string;
  stage: FinancialStage;
  documentNumber: string;
  label: string;
  amount: number | null;
  currency: string;
  status: string;
  matchStatus: MatchStatus;
  date: string;
}

interface FinancialChainLink {
  sourceId: string;
  targetId: string;
  amountDifference: number | null;
  currency: string;
}

interface FinancialChainData {
  documents: FinancialDocument[];
  links: FinancialChainLink[];
  overallMatchStatus: MatchStatus;
}

interface FinancialNodeData extends Record<string, unknown> {
  stage: FinancialStage;
  documentNumber: string;
  label: string;
  amount: number | null;
  currency: string;
  status: string;
  matchStatus: MatchStatus;
  date: string;
  stageColor: string;
  graphNode: GraphNode;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STAGE_CONFIG: Record<
  FinancialStage,
  { x: number; color: string; label: string; icon: typeof FileText }
> = {
  bestellung: { x: 100, color: '#3b82f6', label: 'Bestellung', icon: FileText },
  lieferschein: { x: 350, color: '#22c55e', label: 'Lieferschein', icon: FileText },
  rechnung: { x: 600, color: '#f97316', label: 'Rechnung', icon: Receipt },
  zahlung: { x: 850, color: '#a855f7', label: 'Zahlung', icon: CreditCard },
  mahnung: { x: 1100, color: '#ef4444', label: 'Mahnung', icon: AlertTriangle },
};

const MATCH_STATUS_CONFIG: Record<
  MatchStatus,
  { label: string; color: string; bgColor: string; icon: typeof CheckCircle2 }
> = {
  matched: {
    label: 'Vollstaendig abgeglichen',
    color: '#16a34a',
    bgColor: '#f0fdf4',
    icon: CheckCircle2,
  },
  partial: {
    label: 'Teilweise abgeglichen',
    color: '#ca8a04',
    bgColor: '#fefce8',
    icon: Clock,
  },
  unmatched: {
    label: 'Nicht abgeglichen',
    color: '#dc2626',
    bgColor: '#fef2f2',
    icon: XCircle,
  },
};

// ---------------------------------------------------------------------------
// Mock Data Generator
// ---------------------------------------------------------------------------

function generateMockFinancialChain(entityId: string): FinancialChainData {
  const baseAmount = 1250.0 + (entityId.charCodeAt(0) % 10) * 100;

  const documents: FinancialDocument[] = [
    {
      id: `${entityId}-best-001`,
      stage: 'bestellung',
      documentNumber: 'BE-2026-001',
      label: 'Bestellung #001',
      amount: baseAmount,
      currency: 'EUR',
      status: 'Abgeschlossen',
      matchStatus: 'matched',
      date: '2026-01-15',
    },
    {
      id: `${entityId}-lief-001`,
      stage: 'lieferschein',
      documentNumber: 'LS-2026-001',
      label: 'Lieferschein #001',
      amount: baseAmount,
      currency: 'EUR',
      status: 'Zugestellt',
      matchStatus: 'matched',
      date: '2026-01-20',
    },
    {
      id: `${entityId}-rech-001`,
      stage: 'rechnung',
      documentNumber: 'RE-2026-001',
      label: 'Rechnung #001',
      amount: baseAmount + 50,
      currency: 'EUR',
      status: 'Offen',
      matchStatus: 'partial',
      date: '2026-01-22',
    },
    {
      id: `${entityId}-zahl-001`,
      stage: 'zahlung',
      documentNumber: 'ZA-2026-001',
      label: 'Zahlung #001',
      amount: baseAmount,
      currency: 'EUR',
      status: 'Gebucht',
      matchStatus: 'partial',
      date: '2026-02-01',
    },
    {
      id: `${entityId}-best-002`,
      stage: 'bestellung',
      documentNumber: 'BE-2026-002',
      label: 'Bestellung #002',
      amount: 780.0,
      currency: 'EUR',
      status: 'Abgeschlossen',
      matchStatus: 'matched',
      date: '2026-02-05',
    },
    {
      id: `${entityId}-lief-002`,
      stage: 'lieferschein',
      documentNumber: 'LS-2026-002',
      label: 'Lieferschein #002',
      amount: 780.0,
      currency: 'EUR',
      status: 'Zugestellt',
      matchStatus: 'matched',
      date: '2026-02-10',
    },
    {
      id: `${entityId}-rech-002`,
      stage: 'rechnung',
      documentNumber: 'RE-2026-002',
      label: 'Rechnung #002',
      amount: 780.0,
      currency: 'EUR',
      status: 'Bezahlt',
      matchStatus: 'matched',
      date: '2026-02-12',
    },
    {
      id: `${entityId}-mahn-001`,
      stage: 'mahnung',
      documentNumber: 'MA-2026-001',
      label: 'Mahnung #001',
      amount: baseAmount + 50 + 15,
      currency: 'EUR',
      status: 'Versendet',
      matchStatus: 'unmatched',
      date: '2026-02-15',
    },
  ];

  const links: FinancialChainLink[] = [
    {
      sourceId: `${entityId}-best-001`,
      targetId: `${entityId}-lief-001`,
      amountDifference: 0,
      currency: 'EUR',
    },
    {
      sourceId: `${entityId}-lief-001`,
      targetId: `${entityId}-rech-001`,
      amountDifference: 50,
      currency: 'EUR',
    },
    {
      sourceId: `${entityId}-rech-001`,
      targetId: `${entityId}-zahl-001`,
      amountDifference: -50,
      currency: 'EUR',
    },
    {
      sourceId: `${entityId}-rech-001`,
      targetId: `${entityId}-mahn-001`,
      amountDifference: 15,
      currency: 'EUR',
    },
    {
      sourceId: `${entityId}-best-002`,
      targetId: `${entityId}-lief-002`,
      amountDifference: 0,
      currency: 'EUR',
    },
    {
      sourceId: `${entityId}-lief-002`,
      targetId: `${entityId}-rech-002`,
      amountDifference: 0,
      currency: 'EUR',
    },
  ];

  return {
    documents,
    links,
    overallMatchStatus: 'partial',
  };
}

// ---------------------------------------------------------------------------
// Data Hook
// ---------------------------------------------------------------------------

/** Wird spaeter durch einen echten API-Aufruf ersetzt */
function useFinancialChainData(entityId: string) {
  const mockData = useMemo(() => generateMockFinancialChain(entityId), [entityId]);
  return { data: mockData, isLoading: false, error: null as Error | null };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
  }).format(amount);
}

function toGraphNode(doc: FinancialDocument): GraphNode {
  return {
    id: doc.id,
    type: doc.stage === 'zahlung' ? 'payment' : doc.stage === 'rechnung' ? 'invoice' : 'document',
    label: doc.label,
    data: {
      documentNumber: doc.documentNumber,
      amount: doc.amount,
      currency: doc.currency,
      status: doc.status,
      matchStatus: doc.matchStatus,
      date: doc.date,
      stage: doc.stage,
    },
  };
}

// ---------------------------------------------------------------------------
// Custom Node Component
// ---------------------------------------------------------------------------

function FinancialChainNode({ data }: NodeProps<Node<FinancialNodeData>>) {
  const nodeData = data as FinancialNodeData;
  const stageConfig = STAGE_CONFIG[nodeData.stage];
  const matchConfig = MATCH_STATUS_CONFIG[nodeData.matchStatus];
  const StageIcon = stageConfig.icon;
  const MatchIcon = matchConfig.icon;

  return (
    <div className="rounded-lg border border-border bg-card shadow-md" style={{ minWidth: 180 }}>
      <Handle type="target" position={Position.Left} className="!bg-slate-400" />

      {/* Farbiger Header */}
      <div
        className="flex items-center gap-2 rounded-t-lg px-3 py-2"
        style={{ backgroundColor: stageConfig.color }}
      >
        <StageIcon className="h-4 w-4 text-white" />
        <span className="text-xs font-semibold text-white">{stageConfig.label}</span>
      </div>

      {/* Body */}
      <div className="space-y-1.5 px-3 py-2">
        <p className="text-sm font-medium text-foreground">{nodeData.documentNumber}</p>

        {nodeData.amount !== null && (
          <p className="text-sm font-semibold text-foreground">
            {formatCurrency(nodeData.amount, nodeData.currency)}
          </p>
        )}

        <div className="flex items-center justify-between gap-1">
          <Badge variant="secondary" className="text-[10px]">
            {nodeData.status}
          </Badge>

          <MatchIcon
            className="h-4 w-4 flex-shrink-0"
            style={{ color: matchConfig.color }}
            aria-label={matchConfig.label}
          />
        </div>

        <p className="text-[10px] text-muted-foreground">{nodeData.date}</p>
      </div>

      <Handle type="source" position={Position.Right} className="!bg-slate-400" />
    </div>
  );
}

const financialNodeTypes = { financialNode: FinancialChainNode };

// ---------------------------------------------------------------------------
// Layout Helpers
// ---------------------------------------------------------------------------

function buildNodesAndEdges(chainData: FinancialChainData): {
  nodes: Node<FinancialNodeData>[];
  edges: Edge[];
} {
  // Group documents by stage to compute y-offset within each stage column
  const stageCounters: Record<FinancialStage, number> = {
    bestellung: 0,
    lieferschein: 0,
    rechnung: 0,
    zahlung: 0,
    mahnung: 0,
  };

  const Y_SPACING = 180;
  const Y_OFFSET = 80;

  const nodes: Node<FinancialNodeData>[] = chainData.documents.map((doc) => {
    const stageConfig = STAGE_CONFIG[doc.stage];
    const yIndex = stageCounters[doc.stage];
    stageCounters[doc.stage] += 1;

    return {
      id: doc.id,
      type: 'financialNode',
      position: {
        x: stageConfig.x,
        y: Y_OFFSET + yIndex * Y_SPACING,
      },
      data: {
        stage: doc.stage,
        documentNumber: doc.documentNumber,
        label: doc.label,
        amount: doc.amount,
        currency: doc.currency,
        status: doc.status,
        matchStatus: doc.matchStatus,
        date: doc.date,
        stageColor: stageConfig.color,
        graphNode: toGraphNode(doc),
      },
    };
  });

  const edges: Edge[] = chainData.links.map((link, idx) => {
    let edgeLabel = '';
    if (link.amountDifference !== null && link.amountDifference !== 0) {
      const sign = link.amountDifference > 0 ? '+' : '';
      edgeLabel = `${sign}${formatCurrency(link.amountDifference, link.currency)} Differenz`;
    }

    return {
      id: `edge-${idx}`,
      source: link.sourceId,
      target: link.targetId,
      type: 'default',
      animated: true,
      label: edgeLabel || undefined,
      labelStyle: { fontSize: 10, fill: '#64748b' },
      labelBgStyle: { fill: 'var(--background)', fillOpacity: 0.8 },
      labelBgPadding: [4, 2] as [number, number],
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#94a3b8',
      },
      style: { stroke: '#94a3b8', strokeWidth: 2 },
    };
  });

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function FinancialChainView({ entityId, onNodeSelect }: FinancialChainViewProps) {
  const { data: apiData, isLoading, error } = useFinancialChain(entityId);

  const chainData = useMemo((): FinancialChainData => {
    if (apiData?.stages?.length) {
      const STAGE_MAP: Record<string, FinancialStage> = {
        order: 'bestellung',
        delivery: 'lieferschein',
        invoice: 'rechnung',
        payment: 'zahlung',
        dunning: 'mahnung',
      };
      const documents: FinancialDocument[] = [];
      for (const stage of apiData.stages) {
        const mappedStage: FinancialStage = STAGE_MAP[stage.stage] ?? 'bestellung';
        for (const node of stage.documents) {
          documents.push({
            id: node.id,
            stage: mappedStage,
            documentNumber: String(node.data?.documentNumber ?? node.id),
            label: node.label,
            amount: typeof node.data?.amount === 'number' ? node.data.amount : null,
            currency: String(node.data?.currency ?? 'EUR'),
            status: String(node.data?.status ?? ''),
            matchStatus: (['matched', 'partial', 'unmatched'].includes(String(node.data?.matchStatus))
              ? node.data?.matchStatus
              : 'unmatched') as MatchStatus,
            date: String(node.data?.date ?? ''),
          });
        }
      }
      const matchStatusMap: Record<string, MatchStatus> = {
        full: 'matched',
        partial: 'partial',
        none: 'unmatched',
      };
      return {
        documents,
        links: [],
        overallMatchStatus: matchStatusMap[apiData.matchStatus] ?? 'unmatched',
      };
    }
    return generateMockFinancialChain(entityId);
  }, [apiData, entityId]);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    if (!chainData || chainData.documents.length === 0) {
      return { nodes: [] as Node<FinancialNodeData>[], edges: [] as Edge[] };
    }
    return buildNodesAndEdges(chainData);
  }, [chainData]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const nodeData = node.data as FinancialNodeData;
      if (nodeData.graphNode) {
        onNodeSelect(nodeData.graphNode);
      }
    },
    [onNodeSelect],
  );

  // Loading state
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-muted-foreground">Lade Finanzketten-Daten...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md border-destructive">
          <CardContent className="p-6 text-center">
            <AlertTriangle className="mx-auto mb-2 h-8 w-8 text-destructive" />
            <p className="text-sm text-destructive">
              {error.message || 'Fehler beim Laden der Finanzketten-Daten'}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Empty state
  if (!chainData || chainData.documents.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <Receipt className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Keine Finanzketten fuer diese Entitaet gefunden
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const matchStatusConfig = MATCH_STATUS_CONFIG[chainData.overallMatchStatus];
  const OverallMatchIcon = matchStatusConfig.icon;

  return (
    <div className="relative flex h-full flex-col">
      {/* 3-Way Match Status Header */}
      <div className="flex-shrink-0 border-b border-border p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold">Finanzkette</h2>
            <Badge variant="outline" className="text-xs">
              {chainData.documents.length} Dokumente
            </Badge>
          </div>

          <div
            className="flex items-center gap-2 rounded-md border px-3 py-1.5"
            style={{
              backgroundColor: matchStatusConfig.bgColor,
              borderColor: matchStatusConfig.color,
            }}
          >
            <OverallMatchIcon
              className="h-4 w-4"
              style={{ color: matchStatusConfig.color }}
            />
            <span
              className="text-xs font-semibold"
              style={{ color: matchStatusConfig.color }}
            >
              {matchStatusConfig.label}
            </span>
          </div>
        </div>

        {/* Stage Legend */}
        <div className="mt-2 flex items-center gap-4">
          {(Object.keys(STAGE_CONFIG) as FinancialStage[]).map((stage) => {
            const config = STAGE_CONFIG[stage];
            const StageIcon = config.icon;
            return (
              <div key={stage} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <div
                  className="flex h-4 w-4 items-center justify-center rounded-full"
                  style={{ backgroundColor: config.color }}
                >
                  <StageIcon className="h-2.5 w-2.5 text-white" />
                </div>
                <span>{config.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ReactFlow Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          nodeTypes={financialNodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          defaultEdgeOptions={{ animated: true }}
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
          maxZoom={2}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e2e8f0" />
          <Controls
            showInteractive={false}
            position="bottom-right"
          />
          <MiniMap
            position="bottom-left"
            nodeColor={(node) => {
              const nodeData = node.data as FinancialNodeData;
              return nodeData.stageColor || '#64748b';
            }}
            maskColor="rgba(0, 0, 0, 0.1)"
            className="rounded-lg border border-border"
          />
        </ReactFlow>
      </div>
    </div>
  );
}
