/**
 * Graph Canvas Component
 * Interaktive Graph-Visualisierung mit @xyflow/react
 */

import { useEffect, useMemo, useCallback, type CSSProperties } from 'react';
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
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Building2,
  FileText,
  Receipt,
  ArrowRightLeft,
  CreditCard,
} from 'lucide-react';
import type { GraphData, GraphNode, NodeType } from '../types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_COLORS: Record<NodeType, string> = {
  entity: '#3b82f6',
  document: '#22c55e',
  invoice: '#f97316',
  transaction: '#a855f7',
  payment: '#14b8a6',
};

const NODE_ICONS: Record<NodeType, typeof Building2> = {
  entity: Building2,
  document: FileText,
  invoice: Receipt,
  transaction: ArrowRightLeft,
  payment: CreditCard,
};

const NODE_SIZE = 44;
const LAYOUT_RADIUS = 280;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GraphNodeData extends Record<string, unknown> {
  graphNode: GraphNode;
  isSelected: boolean;
  isHighlighted: boolean;
}

type GraphFlowNode = Node<GraphNodeData, 'graphNode'>;
type GraphFlowEdge = Edge;

interface GraphCanvasProps {
  data: GraphData;
  onNodeSelect: (node: GraphNode) => void;
  selectedNodeId?: string;
  highlightedPath?: string[];
  edgeFilter?: string[];
  confidenceMin?: number;
}

// ---------------------------------------------------------------------------
// Custom Node Component (defined outside render to avoid re-registration)
// ---------------------------------------------------------------------------

function GraphNodeComponent({ data }: NodeProps<GraphFlowNode>) {
  const nodeData = data as unknown as GraphNodeData;
  const { graphNode, isSelected, isHighlighted } = nodeData;
  const color = NODE_COLORS[graphNode.type];
  const Icon = NODE_ICONS[graphNode.type];

  const outerStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    cursor: 'pointer',
  };

  const ringStyle: CSSProperties = {
    width: NODE_SIZE + 12,
    height: NODE_SIZE + 12,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: isSelected
      ? '3px solid #fbbf24'
      : isHighlighted
        ? '3px solid #fbbf24'
        : '3px solid transparent',
    boxShadow: isHighlighted ? '0 0 12px 2px rgba(251, 191, 36, 0.5)' : 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
  };

  const circleStyle: CSSProperties = {
    width: NODE_SIZE,
    height: NODE_SIZE,
    borderRadius: '50%',
    backgroundColor: color,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '2px solid white',
    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
  };

  const labelStyle: CSSProperties = {
    marginTop: 6,
    fontSize: 11,
    fontWeight: 500,
    textAlign: 'center',
    maxWidth: 100,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    color: 'var(--foreground, #1f2937)',
  };

  const truncatedLabel =
    graphNode.label.length > 20
      ? graphNode.label.slice(0, 20) + '...'
      : graphNode.label;

  return (
    <div style={outerStyle}>
      <div style={ringStyle}>
        <div style={circleStyle}>
          <Icon
            style={{ width: 20, height: 20, color: 'white' }}
          />
        </div>
      </div>
      <div style={labelStyle}>{truncatedLabel}</div>
    </div>
  );
}

/** nodeTypes must be defined outside the component to avoid re-registration */
const nodeTypes = { graphNode: GraphNodeComponent };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildFlowNodes(
  nodes: GraphNode[],
  selectedNodeId: string | undefined,
  highlightedPath: string[] | undefined
): GraphFlowNode[] {
  const count = nodes.length;
  if (count === 0) return [];

  const centerX = 400;
  const centerY = 300;
  const radius = Math.max(LAYOUT_RADIUS, count * 30);
  const angleStep = (2 * Math.PI) / count;

  return nodes.map((node, i) => {
    const x = centerX + radius * Math.cos(i * angleStep);
    const y = centerY + radius * Math.sin(i * angleStep);
    const isSelected = node.id === selectedNodeId;
    const isHighlighted = highlightedPath?.includes(node.id) ?? false;

    return {
      id: node.id,
      type: 'graphNode',
      position: { x, y },
      data: {
        graphNode: node,
        isSelected,
        isHighlighted,
      },
    };
  });
}

function buildFlowEdges(
  edges: GraphData['edges'],
  highlightedPath: string[] | undefined,
  edgeFilter: string[] | undefined,
  _confidenceMin: number | undefined
): GraphFlowEdge[] {
  return edges
    .filter((edge) => {
      // Apply edge type filter
      if (edgeFilter && edgeFilter.length > 0 && !edgeFilter.includes(edge.type)) {
        return false;
      }
      // Confidence filter could be applied here when edge confidence data is available
      return true;
    })
    .map((edge, idx) => {
      const isOnPath =
        highlightedPath != null &&
        highlightedPath.includes(edge.source) &&
        highlightedPath.includes(edge.target);

      return {
        id: `e-${edge.source}-${edge.target}-${idx}`,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 16,
          height: 16,
          color: isOnPath ? '#fbbf24' : '#64748b',
        },
        style: {
          stroke: isOnPath ? '#fbbf24' : '#64748b',
          strokeWidth: isOnPath ? 3 : 1.5,
          strokeDasharray: isOnPath ? '6 3' : 'none',
        },
        animated: isOnPath,
        labelStyle: {
          fontSize: 10,
          fontWeight: 500,
          fill: 'var(--foreground, #374151)',
        },
        labelBgStyle: {
          fill: 'var(--background, white)',
          fillOpacity: 0.85,
          stroke: '#e2e8f0',
          strokeWidth: 0.5,
          rx: 4,
          ry: 4,
        },
        labelBgPadding: [4, 6] as [number, number],
        labelShowBg: true,
      };
    });
}

// ---------------------------------------------------------------------------
// MiniMap color callback
// ---------------------------------------------------------------------------

function miniMapNodeColor(node: Node): string {
  const nodeData = node.data as GraphNodeData | undefined;
  if (nodeData?.graphNode) {
    return NODE_COLORS[nodeData.graphNode.type] ?? '#64748b';
  }
  return '#64748b';
}

// ---------------------------------------------------------------------------
// Graph Canvas Component
// ---------------------------------------------------------------------------

export function GraphCanvas({
  data,
  onNodeSelect,
  selectedNodeId,
  highlightedPath,
  edgeFilter,
  confidenceMin,
}: GraphCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<GraphFlowEdge>([]);

  // Build flow nodes whenever data, selection, or highlighting changes
  const flowNodes = useMemo(
    () => buildFlowNodes(data.nodes, selectedNodeId, highlightedPath),
    [data.nodes, selectedNodeId, highlightedPath]
  );

  const flowEdges = useMemo(
    () => buildFlowEdges(data.edges, highlightedPath, edgeFilter, confidenceMin),
    [data.edges, highlightedPath, edgeFilter, confidenceMin]
  );

  // Sync flow state when input data changes
  useEffect(() => {
    setNodes(flowNodes);
  }, [flowNodes, setNodes]);

  useEffect(() => {
    setEdges(flowEdges);
  }, [flowEdges, setEdges]);

  // Handle node click
  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const nodeData = node.data as GraphNodeData | undefined;
      if (nodeData?.graphNode) {
        onNodeSelect(nodeData.graphNode);
      }
    },
    [onNodeSelect]
  );

  // Empty state
  if (data.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <p>Keine Daten zum Anzeigen</p>
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.5 }}
        minZoom={0.1}
        maxZoom={4}
        attributionPosition="bottom-right"
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--border, #e2e8f0)"
        />
        <Controls
          showInteractive={false}
          position="top-right"
        />
        <MiniMap
          nodeColor={miniMapNodeColor}
          nodeStrokeWidth={2}
          pannable
          zoomable
          position="bottom-right"
          style={{
            backgroundColor: 'var(--background, white)',
            border: '1px solid var(--border, #e2e8f0)',
            borderRadius: 8,
          }}
        />
      </ReactFlow>
    </div>
  );
}
