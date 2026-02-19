/**
 * Document Family View
 * Gruppiert verwandte Dokumente um ein zentrales Stammdokument / einen Hauptvertrag
 * Radiales Layout mit @xyflow/react
 */

import { useCallback, useMemo } from 'react';
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
  Mail,
  Paperclip,
  FileCheck,
  AlertTriangle,
  Link2,
  Building2,
} from 'lucide-react';
import type { GraphNode } from '../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DocumentFamilyViewProps {
  documentId?: string;
  entityId?: string;
  onNodeSelect: (node: GraphNode) => void;
}

type DocumentCategory =
  | 'vertrag'
  | 'anlage'
  | 'rechnung'
  | 'lieferschein'
  | 'korrespondenz'
  | 'email'
  | 'sonstiges';

interface FamilyDocument {
  id: string;
  category: DocumentCategory;
  filename: string;
  date: string;
  ring: number;
  isOrphan: boolean;
  parentId: string | null;
}

interface DocumentFamilyData {
  documents: FamilyDocument[];
  links: Array<{ sourceId: string; targetId: string; relationship: string }>;
}

interface FamilyNodeData extends Record<string, unknown> {
  category: DocumentCategory;
  filename: string;
  date: string;
  ring: number;
  isOrphan: boolean;
  categoryColor: string;
  graphNode: GraphNode;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CATEGORY_CONFIG: Record<
  DocumentCategory,
  { color: string; label: string; icon: typeof FileText }
> = {
  vertrag: { color: '#3b82f6', label: 'Vertrag', icon: FileCheck },
  anlage: { color: '#6366f1', label: 'Anlage', icon: Paperclip },
  rechnung: { color: '#f97316', label: 'Rechnung', icon: Receipt },
  lieferschein: { color: '#22c55e', label: 'Lieferschein', icon: FileText },
  korrespondenz: { color: '#8b5cf6', label: 'Korrespondenz', icon: Building2 },
  email: { color: '#06b6d4', label: 'E-Mail', icon: Mail },
  sonstiges: { color: '#64748b', label: 'Sonstiges', icon: FileText },
};

const RING_CONFIG: Record<number, { radius: number; label: string; bgColor: string }> = {
  0: { radius: 0, label: 'Hauptdokument', bgColor: 'rgba(59, 130, 246, 0.05)' },
  1: { radius: 200, label: 'Direkte Anhaenge', bgColor: 'rgba(99, 102, 241, 0.04)' },
  2: { radius: 350, label: 'Rechnungen & Lieferscheine', bgColor: 'rgba(249, 115, 22, 0.03)' },
  3: { radius: 500, label: 'Korrespondenz & E-Mails', bgColor: 'rgba(139, 92, 246, 0.03)' },
};

// ---------------------------------------------------------------------------
// Mock Data Generator
// ---------------------------------------------------------------------------

function generateMockDocumentFamily(
  documentId?: string,
  entityId?: string,
): DocumentFamilyData {
  const seed = documentId || entityId || 'default';
  const seedNum = seed.charCodeAt(0) % 5;

  const documents: FamilyDocument[] = [
    // Ring 0 - Hauptvertrag
    {
      id: `${seed}-vertrag-001`,
      category: 'vertrag',
      filename: 'Rahmenvertrag_2026.pdf',
      date: '2026-01-10',
      ring: 0,
      isOrphan: false,
      parentId: null,
    },
    // Ring 1 - Direkte Anhaenge
    {
      id: `${seed}-anlage-001`,
      category: 'anlage',
      filename: 'Anlage_A_Leistungsbeschreibung.pdf',
      date: '2026-01-10',
      ring: 1,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    {
      id: `${seed}-anlage-002`,
      category: 'anlage',
      filename: 'Nachtrag_01_Preisanpassung.pdf',
      date: '2026-01-25',
      ring: 1,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    {
      id: `${seed}-anlage-003`,
      category: 'anlage',
      filename: `Anlage_B_AGB${seedNum > 2 ? '_v2' : ''}.pdf`,
      date: '2026-01-10',
      ring: 1,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    // Ring 2 - Rechnungen, Lieferscheine
    {
      id: `${seed}-rechnung-001`,
      category: 'rechnung',
      filename: 'RE-2026-0042.pdf',
      date: '2026-02-01',
      ring: 2,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    {
      id: `${seed}-rechnung-002`,
      category: 'rechnung',
      filename: 'RE-2026-0078.pdf',
      date: '2026-02-15',
      ring: 2,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    {
      id: `${seed}-liefer-001`,
      category: 'lieferschein',
      filename: 'LS-2026-0042.pdf',
      date: '2026-01-28',
      ring: 2,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    {
      id: `${seed}-liefer-002`,
      category: 'lieferschein',
      filename: 'LS-2026-0078.pdf',
      date: '2026-02-12',
      ring: 2,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    // Ring 3 - Korrespondenz, E-Mails
    {
      id: `${seed}-email-001`,
      category: 'email',
      filename: 'Auftragsbestaetigung_Mueller.eml',
      date: '2026-01-11',
      ring: 3,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    {
      id: `${seed}-korr-001`,
      category: 'korrespondenz',
      filename: 'Schreiben_Nachverhandlung.pdf',
      date: '2026-01-20',
      ring: 3,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    {
      id: `${seed}-email-002`,
      category: 'email',
      filename: 'Liefertermin_Bestaetigung.eml',
      date: '2026-01-26',
      ring: 3,
      isOrphan: false,
      parentId: `${seed}-vertrag-001`,
    },
    // Orphan documents
    {
      id: `${seed}-sonstig-001`,
      category: 'sonstiges',
      filename: 'Notiz_Telefonat_15012026.pdf',
      date: '2026-01-15',
      ring: 3,
      isOrphan: true,
      parentId: null,
    },
  ];

  const links = documents
    .filter((doc) => doc.parentId !== null)
    .map((doc) => ({
      sourceId: doc.parentId as string,
      targetId: doc.id,
      relationship: doc.ring === 1 ? 'Anlage' : doc.ring === 2 ? 'Beleg' : 'Bezug',
    }));

  return { documents, links };
}

// ---------------------------------------------------------------------------
// Data Hook
// ---------------------------------------------------------------------------

/** Wird spaeter durch einen echten API-Aufruf ersetzt */
function useDocumentFamilyData(documentId?: string, entityId?: string) {
  const mockData = useMemo(
    () => generateMockDocumentFamily(documentId, entityId),
    [documentId, entityId],
  );
  return { data: mockData, isLoading: false, error: null as Error | null };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncateFilename(filename: string, maxLength: number = 22): string {
  if (filename.length <= maxLength) return filename;
  const ext = filename.lastIndexOf('.');
  if (ext > 0 && filename.length - ext <= 5) {
    const nameEnd = maxLength - (filename.length - ext) - 3;
    return filename.slice(0, Math.max(nameEnd, 4)) + '...' + filename.slice(ext);
  }
  return filename.slice(0, maxLength - 3) + '...';
}

function toGraphNode(doc: FamilyDocument): GraphNode {
  return {
    id: doc.id,
    type: doc.category === 'rechnung' ? 'invoice' : 'document',
    label: doc.filename,
    data: {
      category: doc.category,
      filename: doc.filename,
      date: doc.date,
      ring: doc.ring,
      isOrphan: doc.isOrphan,
    },
  };
}

// ---------------------------------------------------------------------------
// Custom Node Component
// ---------------------------------------------------------------------------

function DocumentFamilyNode({ data }: NodeProps<Node<FamilyNodeData>>) {
  const nodeData = data as FamilyNodeData;
  const catConfig = CATEGORY_CONFIG[nodeData.category];
  const CatIcon = catConfig.icon;
  const isCenter = nodeData.ring === 0;

  return (
    <div
      className="rounded-lg border bg-card shadow-sm"
      style={{
        minWidth: isCenter ? 200 : 170,
        borderColor: isCenter ? catConfig.color : 'var(--border)',
        borderWidth: isCenter ? 2 : 1,
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />

      {/* Header mit Icon */}
      <div className="flex items-center gap-2 px-3 py-2">
        <div
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: catConfig.color }}
        >
          <CatIcon className="h-3.5 w-3.5 text-white" />
        </div>
        <span
          className="text-xs font-medium"
          style={{ color: catConfig.color }}
        >
          {catConfig.label}
        </span>
      </div>

      {/* Body */}
      <div className="space-y-1 border-t border-border px-3 py-2">
        <p className="text-xs font-medium text-foreground" title={nodeData.filename}>
          {truncateFilename(nodeData.filename)}
        </p>

        <div className="flex items-center gap-1.5">
          <Badge variant="secondary" className="text-[10px]">
            {nodeData.date}
          </Badge>

          {nodeData.isOrphan && (
            <Badge
              variant="outline"
              className="border-amber-400 text-[10px] text-amber-600"
            >
              <AlertTriangle className="mr-0.5 h-2.5 w-2.5" />
              Unverknuepft
            </Badge>
          )}
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
    </div>
  );
}

const familyNodeTypes = { familyNode: DocumentFamilyNode };

// ---------------------------------------------------------------------------
// Layout Helpers
// ---------------------------------------------------------------------------

function buildNodesAndEdges(
  familyData: DocumentFamilyData,
): { nodes: Node<FamilyNodeData>[]; edges: Edge[] } {
  const CENTER_X = 500;
  const CENTER_Y = 450;

  // Group documents by ring
  const ringGroups = new Map<number, FamilyDocument[]>();
  for (const doc of familyData.documents) {
    const group = ringGroups.get(doc.ring) ?? [];
    group.push(doc);
    ringGroups.set(doc.ring, group);
  }

  const nodes: Node<FamilyNodeData>[] = [];

  // Place nodes in concentric rings
  for (const [ring, docs] of ringGroups.entries()) {
    const ringConfig = RING_CONFIG[ring];
    if (!ringConfig) continue;

    if (ring === 0) {
      // Center node
      for (const doc of docs) {
        nodes.push(createFamilyNode(doc, CENTER_X - 100, CENTER_Y - 40));
      }
    } else {
      // Distribute around the ring
      const count = docs.length;
      const angleStep = (2 * Math.PI) / Math.max(count, 1);
      // Start from top (-PI/2) for a nicer layout
      const startAngle = -Math.PI / 2;

      docs.forEach((doc, idx) => {
        const angle = startAngle + idx * angleStep;
        const x = CENTER_X + ringConfig.radius * Math.cos(angle) - 85;
        const y = CENTER_Y + ringConfig.radius * Math.sin(angle) - 30;
        nodes.push(createFamilyNode(doc, x, y));
      });
    }
  }

  const edges: Edge[] = familyData.links.map((link, idx) => ({
    id: `family-edge-${idx}`,
    source: link.sourceId,
    target: link.targetId,
    type: 'default',
    animated: false,
    label: link.relationship,
    labelStyle: { fontSize: 9, fill: '#94a3b8' },
    labelBgStyle: { fill: 'var(--background)', fillOpacity: 0.8 },
    labelBgPadding: [3, 1.5] as [number, number],
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: '#cbd5e1',
    },
    style: { stroke: '#cbd5e1', strokeWidth: 1.5 },
  }));

  return { nodes, edges };
}

function createFamilyNode(doc: FamilyDocument, x: number, y: number): Node<FamilyNodeData> {
  const catConfig = CATEGORY_CONFIG[doc.category];
  return {
    id: doc.id,
    type: 'familyNode',
    position: { x, y },
    data: {
      category: doc.category,
      filename: doc.filename,
      date: doc.date,
      ring: doc.ring,
      isOrphan: doc.isOrphan,
      categoryColor: catConfig.color,
      graphNode: toGraphNode(doc),
    },
  };
}

// ---------------------------------------------------------------------------
// Stats Calculation
// ---------------------------------------------------------------------------

interface FamilyStats {
  total: number;
  linked: number;
  orphans: number;
}

function computeStats(docs: FamilyDocument[]): FamilyStats {
  const orphans = docs.filter((d) => d.isOrphan).length;
  return {
    total: docs.length,
    linked: docs.length - orphans,
    orphans,
  };
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function DocumentFamilyView({
  documentId,
  entityId,
  onNodeSelect,
}: DocumentFamilyViewProps) {
  const { data: familyData, isLoading, error } = useDocumentFamilyData(documentId, entityId);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    if (!familyData || familyData.documents.length === 0) {
      return { nodes: [] as Node<FamilyNodeData>[], edges: [] as Edge[] };
    }
    return buildNodesAndEdges(familyData);
  }, [familyData]);

  const stats = useMemo(() => {
    if (!familyData) return { total: 0, linked: 0, orphans: 0 };
    return computeStats(familyData.documents);
  }, [familyData]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const nodeData = node.data as FamilyNodeData;
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
          <p className="text-sm text-muted-foreground">Lade Dokumentenfamilie...</p>
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
              {error.message || 'Fehler beim Laden der Dokumentenfamilie'}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Empty state - no document or entity selected
  if (!documentId && !entityId) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <Link2 className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Keine Dokumentenfamilie gefunden. Waehlen Sie ein Dokument oder eine Entitaet.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Empty state - no data returned
  if (!familyData || familyData.documents.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-6 text-center">
            <Link2 className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Keine Dokumentenfamilie gefunden. Waehlen Sie ein Dokument oder eine Entitaet.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col">
      {/* Stats Panel Header */}
      <div className="flex-shrink-0 border-b border-border p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Dokumentenfamilie</h2>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>
              <span className="font-semibold text-foreground">{stats.total}</span> Dokumente
            </span>
            <span className="text-border">|</span>
            <span>
              <span className="font-semibold text-green-600">{stats.linked}</span> verknuepft
            </span>
            <span className="text-border">|</span>
            <span>
              <span className="font-semibold text-amber-600">{stats.orphans}</span> unverknuepft
            </span>
          </div>
        </div>

        {/* Category Legend */}
        <div className="mt-2 flex flex-wrap items-center gap-3">
          {(Object.keys(CATEGORY_CONFIG) as DocumentCategory[]).map((cat) => {
            const config = CATEGORY_CONFIG[cat];
            const CatIcon = config.icon;
            return (
              <div key={cat} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <div
                  className="flex h-4 w-4 items-center justify-center rounded-full"
                  style={{ backgroundColor: config.color }}
                >
                  <CatIcon className="h-2.5 w-2.5 text-white" />
                </div>
                <span>{config.label}</span>
              </div>
            );
          })}
        </div>

        {/* Ring Legend */}
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          {Object.entries(RING_CONFIG).map(([ring, config]) => (
            <div key={ring} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <div
                className="h-2.5 w-2.5 rounded-full border"
                style={{
                  backgroundColor: config.bgColor,
                  borderColor: '#e2e8f0',
                }}
              />
              <span>
                Ring {ring}: {config.label}
              </span>
            </div>
          ))}
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
          nodeTypes={familyNodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          minZoom={0.2}
          maxZoom={2}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e2e8f0" />
          <Controls
            showInteractive={false}
            position="bottom-right"
          />
          <MiniMap
            position="bottom-left"
            nodeColor={(node) => {
              const nodeData = node.data as FamilyNodeData;
              return nodeData.categoryColor || '#64748b';
            }}
            maskColor="rgba(0, 0, 0, 0.1)"
            className="rounded-lg border border-border"
          />
        </ReactFlow>
      </div>
    </div>
  );
}
