/**
 * Risk Network View Component
 * Risiko-gewichtete Netzwerk-Visualisierung mit @xyflow/react
 */

import { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  MarkerType,
  BackgroundVariant,
  Handle,
  Position,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  ShieldAlert,
  AlertTriangle,
  Building2,
  TrendingUp,
  TrendingDown,
  Users,
} from 'lucide-react';
import type { GraphNode, NodeType } from '../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RiskNetworkViewProps {
  entityId?: string;
  onNodeSelect: (node: GraphNode) => void;
}

interface RiskEntity {
  entityId: string;
  entityName: string;
  riskScore: number;
  transactionVolume: number;
  communityId: string;
  paymentBehaviorScore: number;
  industryRisk: number;
  volumeScore: number;
  lastAnomaly: string | null;
}

interface RiskEdge {
  source: string;
  target: string;
  transactionCount: number;
}

interface RiskCommunity {
  id: string;
  name: string;
  memberIds: string[];
  color: string;
}

interface RiskNetworkMockData {
  entities: RiskEntity[];
  edges: RiskEdge[];
  communities: RiskCommunity[];
}

/** Data attached to the custom RiskNode for ReactFlow */
interface RiskNodeFlowData {
  entityName: string;
  riskScore: number;
  transactionVolume: number;
  communityId: string;
  paymentBehaviorScore: number;
  industryRisk: number;
  volumeScore: number;
  lastAnomaly: string | null;
  nodeColor: string;
  onSelect: (node: GraphNode) => void;
  [key: string]: unknown;
}

type RiskFlowNode = Node<RiskNodeFlowData, 'riskNode'>;

// ---------------------------------------------------------------------------
// Risk Thresholds & Color + Sizing Helpers
// ---------------------------------------------------------------------------

const RISK_THRESHOLD_LOW = 30;
const RISK_THRESHOLD_MEDIUM = 60;
const RISK_THRESHOLD_HIGH = 80;

function getRiskColor(score: number): string {
  if (score <= RISK_THRESHOLD_LOW) return '#22c55e';
  if (score <= RISK_THRESHOLD_MEDIUM) return '#eab308';
  if (score <= RISK_THRESHOLD_HIGH) return '#f97316';
  return '#ef4444';
}

function getNodeSize(volume: number, minVol: number, maxVol: number): number {
  const MIN_SIZE = 40;
  const MAX_SIZE = 100;
  if (maxVol === minVol) return (MIN_SIZE + MAX_SIZE) / 2;
  const ratio = (volume - minVol) / (maxVol - minVol);
  return MIN_SIZE + ratio * (MAX_SIZE - MIN_SIZE);
}

function formatGermanCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

// ---------------------------------------------------------------------------
// Seeded Random (deterministic per entityId)
// ---------------------------------------------------------------------------

function seededRandom(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

// ---------------------------------------------------------------------------
// Mock Data Generation
// ---------------------------------------------------------------------------

const GERMAN_COMPANIES = [
  'Mueller GmbH',
  'Schmidt & Soehne KG',
  'Bauer Maschinenbau AG',
  'Fischer Logistik GmbH',
  'Weber Consulting',
  'Schneider IT Services',
  'Hoffmann Elektrotechnik',
  'Koch Handelsgesellschaft',
  'Wagner Metallbau',
  'Becker Transport AG',
  'Richter Pharma GmbH',
  'Klein Bauunternehmen',
  'Wolf Textilien',
  'Schaefer Automotive',
  'Neumann Chemie GmbH',
  'Schwarz Lebensmittel AG',
  'Zimmermann Holzbau',
  'Braun Medizintechnik',
  'Krueger Versicherung',
  'Hartmann Energietechnik',
  'Lange Stahlwerke',
  'Werner Gebaeudetechnik',
  'Lehmann Druckerei',
  'Schmitt Verpackung GmbH',
  'Roth Elektronik AG',
];

const COMMUNITY_NAMES = [
  'Lieferkette Sued',
  'Industriecluster Nord',
  'Handelspartner West',
  'Technologie-Verbund',
];

const COMMUNITY_COLORS = [
  'rgba(59, 130, 246, 0.08)',
  'rgba(34, 197, 94, 0.08)',
  'rgba(168, 85, 247, 0.08)',
  'rgba(249, 115, 22, 0.08)',
];

function generateMockRiskNetwork(entityId?: string): RiskNetworkMockData {
  const seed = (entityId ?? 'global')
    .split('')
    .reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  const rng = seededRandom(seed || 42);

  const entityCount = Math.floor(rng() * 11) + 15; // 15-25
  const communityCount = Math.min(4, Math.max(3, Math.floor(rng() * 2) + 3));

  // Build communities
  const communities: RiskCommunity[] = [];
  for (let c = 0; c < communityCount; c++) {
    communities.push({
      id: `community-${c}`,
      name: COMMUNITY_NAMES[c % COMMUNITY_NAMES.length],
      memberIds: [],
      color: COMMUNITY_COLORS[c % COMMUNITY_COLORS.length],
    });
  }

  // Build entities
  const entities: RiskEntity[] = [];
  const usedNames = new Set<string>();

  for (let i = 0; i < entityCount; i++) {
    let name = GERMAN_COMPANIES[Math.floor(rng() * GERMAN_COMPANIES.length)];
    while (usedNames.has(name)) {
      name =
        GERMAN_COMPANIES[Math.floor(rng() * GERMAN_COMPANIES.length)] +
        ` (${Math.floor(rng() * 99) + 1})`;
    }
    usedNames.add(name);

    const communityIdx = Math.floor(rng() * communityCount);
    const community = communities[communityIdx];
    const entId = `risk-ent-${i}`;
    community.memberIds.push(entId);

    const riskScore = Math.floor(rng() * 86) + 10; // 10-95
    const transactionVolume =
      Math.floor(rng() * 4990000) + 10000; // 10,000 - 5,000,000

    entities.push({
      entityId: entId,
      entityName: name,
      riskScore,
      transactionVolume,
      communityId: community.id,
      paymentBehaviorScore: Math.floor(rng() * 100),
      industryRisk: Math.floor(rng() * 100),
      volumeScore: Math.floor(rng() * 100),
      lastAnomaly:
        riskScore > 60
          ? new Date(
              Date.now() - Math.floor(rng() * 90 * 24 * 60 * 60 * 1000)
            ).toLocaleDateString('de-DE')
          : null,
    });
  }

  // Build edges - connect entities within and across communities
  const edges: RiskEdge[] = [];
  const edgeSet = new Set<string>();

  for (const community of communities) {
    const members = community.memberIds;
    // Connect within community (most members connected)
    for (let i = 0; i < members.length; i++) {
      for (let j = i + 1; j < members.length; j++) {
        if (rng() > 0.4) {
          const edgeKey = `${members[i]}-${members[j]}`;
          if (!edgeSet.has(edgeKey)) {
            edgeSet.add(edgeKey);
            edges.push({
              source: members[i],
              target: members[j],
              transactionCount: Math.floor(rng() * 50) + 1,
            });
          }
        }
      }
    }
  }

  // Cross-community edges (fewer)
  for (let i = 0; i < Math.floor(entityCount * 0.3); i++) {
    const srcIdx = Math.floor(rng() * entityCount);
    const tgtIdx = Math.floor(rng() * entityCount);
    if (srcIdx !== tgtIdx) {
      const src = entities[srcIdx].entityId;
      const tgt = entities[tgtIdx].entityId;
      const edgeKey = `${src}-${tgt}`;
      const reverseKey = `${tgt}-${src}`;
      if (!edgeSet.has(edgeKey) && !edgeSet.has(reverseKey)) {
        edgeSet.add(edgeKey);
        edges.push({
          source: src,
          target: tgt,
          transactionCount: Math.floor(rng() * 20) + 1,
        });
      }
    }
  }

  return { entities, edges, communities };
}

function useRiskNetworkData(entityId?: string) {
  const mockData = useMemo(
    () => generateMockRiskNetwork(entityId),
    [entityId]
  );
  return { data: mockData, isLoading: false, error: null };
}

// ---------------------------------------------------------------------------
// Custom Risk Node Component
// ---------------------------------------------------------------------------

function RiskNodeComponent({ data }: NodeProps<RiskFlowNode>) {
  const color = data.nodeColor;
  const showAlert = data.riskScore > 70;
  const formattedVolume = formatGermanCurrency(data.transactionVolume);

  const handleClick = useCallback(() => {
    const graphNode: GraphNode = {
      id: data.entityName, // use name as stable identifier for display
      type: 'entity' as NodeType,
      label: data.entityName,
      data: {
        riskScore: data.riskScore,
        transactionVolume: data.transactionVolume,
        communityId: data.communityId,
        paymentBehaviorScore: data.paymentBehaviorScore,
        industryRisk: data.industryRisk,
        volumeScore: data.volumeScore,
        lastAnomaly: data.lastAnomaly,
      },
    };
    data.onSelect(graphNode);
  }, [data]);

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className="cursor-pointer rounded-lg border-2 bg-card p-3 shadow-md transition-shadow hover:shadow-lg"
            style={{ borderColor: color, minWidth: 140 }}
            onClick={handleClick}
          >
            <Handle type="target" position={Position.Left} className="opacity-0" />
            <Handle type="source" position={Position.Right} className="opacity-0" />

            {/* Entity Name */}
            <div className="mb-1.5 flex items-center gap-1.5">
              <Building2
                className="h-3.5 w-3.5 flex-shrink-0"
                style={{ color }}
              />
              <span className="truncate text-xs font-semibold text-foreground">
                {data.entityName}
              </span>
              {showAlert && (
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 text-red-500" />
              )}
            </div>

            {/* Risk Score Badge */}
            <div className="mb-1.5">
              <Badge
                variant="outline"
                className="text-[10px] font-bold"
                style={{ borderColor: color, color }}
              >
                Risiko: {data.riskScore}/100
              </Badge>
            </div>

            {/* Transaction Volume */}
            <div className="text-[10px] text-muted-foreground">
              {formattedVolume}
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent side="right" className="max-w-xs">
          <div className="space-y-1.5 text-xs">
            <p className="font-semibold">{data.entityName}</p>
            <div className="space-y-1">
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">
                  Zahlungsverhalten-Score
                </span>
                <span className="font-medium">
                  {data.paymentBehaviorScore}/100
                </span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">Branchenrisiko</span>
                <span className="font-medium">{data.industryRisk}/100</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-muted-foreground">Volumen-Score</span>
                <span className="font-medium">{data.volumeScore}/100</span>
              </div>
              {data.lastAnomaly && (
                <div className="flex justify-between gap-4">
                  <span className="text-muted-foreground">
                    Letzte Anomalie
                  </span>
                  <span className="font-medium text-red-500">
                    {data.lastAnomaly}
                  </span>
                </div>
              )}
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

const nodeTypes = {
  riskNode: RiskNodeComponent,
};

// ---------------------------------------------------------------------------
// Layout: Position nodes in community clusters
// ---------------------------------------------------------------------------

function layoutNodes(
  entities: ReadonlyArray<RiskEntity>,
  communities: ReadonlyArray<RiskCommunity>,
  minVol: number,
  maxVol: number,
  onSelect: (node: GraphNode) => void
): { flowNodes: RiskFlowNode[]; groupNodes: Node[] } {
  const flowNodes: RiskFlowNode[] = [];
  const groupNodes: Node[] = [];

  // Cluster layout: arrange communities in a grid
  const cols = Math.ceil(Math.sqrt(communities.length));
  const CLUSTER_SPACING_X = 600;
  const CLUSTER_SPACING_Y = 500;

  communities.forEach((community, cIdx) => {
    const col = cIdx % cols;
    const row = Math.floor(cIdx / cols);
    const clusterCenterX = col * CLUSTER_SPACING_X + CLUSTER_SPACING_X / 2;
    const clusterCenterY = row * CLUSTER_SPACING_Y + CLUSTER_SPACING_Y / 2;

    const members = entities.filter((e) => e.communityId === community.id);

    // Place members in a circle within the cluster
    const radius = Math.max(120, members.length * 25);

    members.forEach((entity, mIdx) => {
      const angle = (2 * Math.PI * mIdx) / members.length;
      const x = clusterCenterX + radius * Math.cos(angle);
      const y = clusterCenterY + radius * Math.sin(angle);
      const nodeSize = getNodeSize(entity.transactionVolume, minVol, maxVol);
      const color = getRiskColor(entity.riskScore);

      flowNodes.push({
        id: entity.entityId,
        type: 'riskNode',
        position: { x: x - nodeSize, y: y - nodeSize / 2 },
        data: {
          entityName: entity.entityName,
          riskScore: entity.riskScore,
          transactionVolume: entity.transactionVolume,
          communityId: entity.communityId,
          paymentBehaviorScore: entity.paymentBehaviorScore,
          industryRisk: entity.industryRisk,
          volumeScore: entity.volumeScore,
          lastAnomaly: entity.lastAnomaly,
          nodeColor: color,
          onSelect,
        },
      });
    });

    // Group node as semi-transparent background for the cluster
    const padding = 80;
    const groupX = clusterCenterX - radius - padding;
    const groupY = clusterCenterY - radius - padding;
    const groupWidth = (radius + padding) * 2;
    const groupHeight = (radius + padding) * 2;

    groupNodes.push({
      id: `group-${community.id}`,
      type: 'group',
      position: { x: groupX, y: groupY },
      style: {
        width: groupWidth,
        height: groupHeight,
        backgroundColor: community.color,
        borderRadius: 16,
        border: '1px dashed rgba(100, 116, 139, 0.3)',
        zIndex: -1,
      },
      data: { label: community.name },
      selectable: false,
      draggable: false,
    });
  });

  return { flowNodes, groupNodes };
}

function buildFlowEdges(
  riskEdges: ReadonlyArray<RiskEdge>,
  entities: ReadonlyArray<RiskEntity>
): Edge[] {
  const entityMap = new Map<string, RiskEntity>();
  for (const e of entities) {
    entityMap.set(e.entityId, e);
  }

  const maxTxCount = Math.max(...riskEdges.map((e) => e.transactionCount), 1);

  return riskEdges.map((re, idx) => {
    const srcEntity = entityMap.get(re.source);
    const tgtEntity = entityMap.get(re.target);
    const bothHighRisk =
      (srcEntity?.riskScore ?? 0) > 60 && (tgtEntity?.riskScore ?? 0) > 60;
    const strokeWidth = 1 + (re.transactionCount / maxTxCount) * 4;

    return {
      id: `edge-${idx}`,
      source: re.source,
      target: re.target,
      style: {
        stroke: bothHighRisk ? '#ef444480' : '#64748b40',
        strokeWidth,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: bothHighRisk ? '#ef4444' : '#64748b',
        width: 12,
        height: 12,
      },
      label: `${re.transactionCount} Transaktionen`,
      labelStyle: { fontSize: 9, fill: '#94a3b8' },
      labelBgStyle: { fill: 'transparent' },
    };
  });
}

// ---------------------------------------------------------------------------
// Risk Summary Panel
// ---------------------------------------------------------------------------

interface RiskSummaryPanelProps {
  entities: ReadonlyArray<RiskEntity>;
}

function RiskSummaryPanel({ entities }: RiskSummaryPanelProps) {
  const stats = useMemo(() => {
    let low = 0;
    let medium = 0;
    let high = 0;
    let critical = 0;
    let totalRisk = 0;
    let highestRisk = 0;
    let highestName = '';

    for (const e of entities) {
      totalRisk += e.riskScore;
      if (e.riskScore > highestRisk) {
        highestRisk = e.riskScore;
        highestName = e.entityName;
      }
      if (e.riskScore <= RISK_THRESHOLD_LOW) low++;
      else if (e.riskScore <= RISK_THRESHOLD_MEDIUM) medium++;
      else if (e.riskScore <= RISK_THRESHOLD_HIGH) high++;
      else critical++;
    }

    const avgRisk =
      entities.length > 0 ? Math.round(totalRisk / entities.length) : 0;

    return { low, medium, high, critical, avgRisk, highestRisk, highestName };
  }, [entities]);

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-3 text-sm">
      <div className="flex items-center gap-1.5">
        <Users className="h-4 w-4 text-muted-foreground" />
        <span className="font-medium">{entities.length}</span>
        <span className="text-muted-foreground">Entitaeten</span>
      </div>

      <div className="h-4 w-px bg-border" />

      <div className="flex items-center gap-2">
        <Badge
          variant="outline"
          className="text-xs"
          style={{ borderColor: '#22c55e', color: '#22c55e' }}
        >
          {stats.low} niedrig
        </Badge>
        <Badge
          variant="outline"
          className="text-xs"
          style={{ borderColor: '#eab308', color: '#eab308' }}
        >
          {stats.medium} mittel
        </Badge>
        <Badge
          variant="outline"
          className="text-xs"
          style={{ borderColor: '#f97316', color: '#f97316' }}
        >
          {stats.high} hoch
        </Badge>
        <Badge
          variant="outline"
          className="text-xs"
          style={{ borderColor: '#ef4444', color: '#ef4444' }}
        >
          {stats.critical} kritisch
        </Badge>
      </div>

      <div className="h-4 w-px bg-border" />

      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground">Durchschnitt:</span>
        <span
          className="font-semibold"
          style={{ color: getRiskColor(stats.avgRisk) }}
        >
          {stats.avgRisk}/100
        </span>
      </div>

      <div className="h-4 w-px bg-border" />

      <div className="flex items-center gap-1.5">
        {stats.highestRisk > 70 ? (
          <TrendingUp className="h-3.5 w-3.5 text-red-500" />
        ) : (
          <TrendingDown className="h-3.5 w-3.5 text-green-500" />
        )}
        <span className="text-muted-foreground">Hoechstes Risiko:</span>
        <span className="font-medium text-foreground">
          {stats.highestName}
        </span>
        <span
          className="font-semibold"
          style={{ color: getRiskColor(stats.highestRisk) }}
        >
          ({stats.highestRisk})
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MiniMap Node Color
// ---------------------------------------------------------------------------

function miniMapNodeColor(node: Node): string {
  if (node.type === 'group') return 'transparent';
  const flowData = node.data as RiskNodeFlowData | undefined;
  if (flowData?.riskScore !== undefined) {
    return getRiskColor(flowData.riskScore as number);
  }
  return '#64748b';
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function RiskNetworkView({
  entityId,
  onNodeSelect,
}: RiskNetworkViewProps) {
  const { data: mockData, isLoading } = useRiskNetworkData(entityId);

  // Compute volume range for node sizing
  const { minVol, maxVol } = useMemo(() => {
    if (!mockData || mockData.entities.length === 0)
      return { minVol: 0, maxVol: 1 };
    const volumes = mockData.entities.map((e) => e.transactionVolume);
    return {
      minVol: Math.min(...volumes),
      maxVol: Math.max(...volumes),
    };
  }, [mockData]);

  // Build ReactFlow nodes and edges from mock data
  const initialNodes = useMemo<Node[]>(() => {
    if (!mockData) return [];
    const { flowNodes, groupNodes } = layoutNodes(
      mockData.entities,
      mockData.communities,
      minVol,
      maxVol,
      onNodeSelect
    );
    return [...groupNodes, ...flowNodes];
  }, [mockData, minVol, maxVol, onNodeSelect]);

  const initialEdges = useMemo<Edge[]>(() => {
    if (!mockData) return [];
    return buildFlowEdges(mockData.edges, mockData.entities);
  }, [mockData]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  // Empty state
  if (!entityId) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5" />
              Risiko-Netzwerk
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Keine Risiko-Daten verfuegbar. Waehlen Sie eine Entitaet.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-muted-foreground">
            Lade Risiko-Netzwerk...
          </p>
        </div>
      </div>
    );
  }

  if (!mockData || mockData.entities.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5" />
              Risiko-Netzwerk
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Keine Risiko-Daten verfuegbar. Waehlen Sie eine Entitaet.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Risk Summary Panel */}
      <div className="flex-shrink-0 border-b border-border bg-background p-3">
        <RiskSummaryPanel entities={mockData.entities} />
      </div>

      {/* ReactFlow Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.1}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="#64748b20"
          />
          <Controls
            showInteractive={false}
            position="bottom-left"
          />
          <MiniMap
            nodeColor={miniMapNodeColor}
            maskColor="rgba(0, 0, 0, 0.1)"
            position="bottom-right"
            style={{ width: 150, height: 100 }}
          />
        </ReactFlow>
      </div>

      {/* Community Legend */}
      <div className="flex-shrink-0 border-t border-border bg-background px-4 py-2">
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <span className="font-semibold text-muted-foreground">
            Cluster:
          </span>
          {mockData.communities.map((community) => (
            <div key={community.id} className="flex items-center gap-1.5">
              <div
                className="h-3 w-3 rounded border"
                style={{
                  backgroundColor: community.color.replace('0.08', '0.3'),
                  borderColor: community.color.replace('0.08', '0.5'),
                }}
              />
              <span className="text-muted-foreground">
                {community.name} ({community.memberIds.length})
              </span>
            </div>
          ))}
          <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-1">
              <div className="h-2.5 w-2.5 rounded-full bg-green-500" />
              <span className="text-muted-foreground">0-30</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2.5 w-2.5 rounded-full bg-yellow-500" />
              <span className="text-muted-foreground">31-60</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2.5 w-2.5 rounded-full bg-orange-500" />
              <span className="text-muted-foreground">61-80</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2.5 w-2.5 rounded-full bg-red-500" />
              <span className="text-muted-foreground">81-100</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
