/**
 * DocumentGraphView - React Flow Graph (Nodes=Dokumente, Edges=Beziehungen)
 *
 * Zeigt Dokumenten-Ketten als interaktiven Graphen.
 * Nutzt @xyflow/react mit Custom Nodes und Edges.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  BackgroundVariant,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { Loader2, AlertCircle } from 'lucide-react';

import { GraphNode } from './GraphNode';
import { GraphEdge } from './GraphEdge';
import { GraphDetailPanel } from './GraphDetailPanel';

import type { DocumentChain, ChainDocument, GraphNodeData } from '../types/document-graph-types';

// ==================== Types ====================

interface DocumentGraphViewProps {
  chains: DocumentChain[];
  isLoading: boolean;
  error: Error | null;
  onDocumentClick?: (documentId: string) => void;
}

// ==================== Node Types ====================

const nodeTypes = {
  chainDocument: GraphNode,
};

const edgeTypes = {
  chainEdge: GraphEdge,
};

const defaultEdgeOptions = {
  type: 'chainEdge',
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 12,
    height: 12,
  },
};

// ==================== Layout ====================

function layoutChains(chains: DocumentChain[]): {
  nodes: Node[];
  edges: Edge[];
} {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const CHAIN_SPACING_Y = 180;
  const NODE_SPACING_X = 280;

  chains.forEach((chain, chainIndex) => {
    const yOffset = chainIndex * CHAIN_SPACING_Y;

    // Sort documents by chain position
    const sortedDocs = [...chain.documents].sort(
      (a, b) => a.chainPosition - b.chainPosition
    );

    sortedDocs.forEach((doc, docIndex) => {
      const nodeId = doc.id;

      nodes.push({
        id: nodeId,
        type: 'chainDocument',
        position: {
          x: docIndex * NODE_SPACING_X,
          y: yOffset,
        },
        data: {
          label: doc.filename,
          documentType: doc.documentType,
          date: doc.documentDate,
          amount: doc.amount,
          status: chain.isComplete ? 'complete' : 'open',
          chainId: chain.chainId,
          chainPosition: doc.chainPosition,
        } satisfies GraphNodeData,
      });

      // Edge to next document in chain
      if (docIndex < sortedDocs.length - 1) {
        const nextDoc = sortedDocs[docIndex + 1];
        edges.push({
          id: `${nodeId}-${nextDoc.id}`,
          source: nodeId,
          target: nextDoc.id,
          type: 'chainEdge',
          data: { relationType: 'chain_link', label: 'Kette' },
        });
      }
    });
  });

  return { nodes, edges };
}

// ==================== Component ====================

export function DocumentGraphView({
  chains,
  isLoading,
  error,
  onDocumentClick,
}: DocumentGraphViewProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedDocument, setSelectedDocument] = useState<ChainDocument | null>(null);
  const [selectedChainId, setSelectedChainId] = useState<string | null>(null);

  // Build graph layout from chains
  useEffect(() => {
    if (!chains.length) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const layout = layoutChains(chains);
    setNodes(layout.nodes);
    setEdges(layout.edges);
  }, [chains, setNodes, setEdges]);

  // Find document by node ID across all chains
  const findDocument = useCallback(
    (nodeId: string): { doc: ChainDocument; chainId: string } | null => {
      for (const chain of chains) {
        const doc = chain.documents.find((d) => d.id === nodeId);
        if (doc) return { doc, chainId: chain.chainId };
      }
      return null;
    },
    [chains]
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const result = findDocument(node.id);
      if (result) {
        setSelectedDocument(result.doc);
        setSelectedChainId(result.chainId);
        onDocumentClick?.(node.id);
      }
    },
    [findDocument, onDocumentClick]
  );

  const handleClosePanel = useCallback(() => {
    setSelectedDocument(null);
    setSelectedChainId(null);
  }, []);

  // Loading state
  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Lade Dokumenten-Graph...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm text-destructive">
            Fehler beim Laden des Graphen
          </p>
          <p className="text-xs text-muted-foreground max-w-sm">
            {error.message}
          </p>
        </div>
      </div>
    );
  }

  // Empty state
  if (!chains.length) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <p className="text-muted-foreground">Keine Auftragsketten gefunden</p>
          <p className="text-xs text-muted-foreground max-w-sm">
            Verknuepfen Sie Dokumente zu Auftragsketten, um sie hier zu visualisieren.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex">
      <div className="flex-1 min-h-[500px]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          className="bg-muted/10"
          minZoom={0.2}
          maxZoom={2}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} className="opacity-30" />
          <Controls className="bg-background border-border" />
          <MiniMap
            className="bg-background border-border"
            nodeColor="hsl(var(--primary))"
            maskColor="hsl(var(--background) / 0.7)"
          />
        </ReactFlow>
      </div>

      {/* Detail Panel */}
      {selectedDocument && (
        <GraphDetailPanel
          document={selectedDocument}
          chainId={selectedChainId}
          onClose={handleClosePanel}
        />
      )}
    </div>
  );
}
