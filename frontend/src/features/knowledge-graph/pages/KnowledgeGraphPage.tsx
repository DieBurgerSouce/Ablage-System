/**
 * Knowledge Graph Page
 * Hauptseite fuer die interaktive Wissens-Graph-Visualisierung
 * mit Multi-View-Unterstuetzung (Graph, Finanzkette, Zeitstrahl, Risiko, Familien)
 */

import { useState, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useEntityGraph } from '../hooks/use-knowledge-graph-queries';
import { GraphCanvas } from '../components/GraphCanvas';
import { GraphSearch } from '../components/GraphSearch';
import { GraphToolbar } from '../components/GraphToolbar';
import { NodeDetailPanel } from '../components/NodeDetailPanel';
import { GraphLegend } from '../components/GraphLegend';
import { FinancialChainView } from '../views/FinancialChainView';
import { TimelineView } from '../views/TimelineView';
import { RiskNetworkView } from '../views/RiskNetworkView';
import { DocumentFamilyView } from '../views/DocumentFamilyView';
import type { GraphNode, SearchResult, ViewMode } from '../types';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';
import { emitChecklistComplete } from '@/features/product-tour/hooks/use-checklist-events';

const ALL_EDGE_TYPES = [
  'CONTAINS_DOCUMENT', 'ISSUED_TO', 'PAID_VIA', 'REFERENCES', 'LINKED_TO',
  'BASED_ON', 'MATCHED_WITH', 'PARENT_OF', 'DERIVED_FROM', 'SUPERSEDES',
  'CORRECTS', 'DUNNING_FOR', 'PARTIAL_PAYMENT',
];

export function KnowledgeGraphPage() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | undefined>();
  const [depth, setDepth] = useState(2);
  const [selectedNode, setSelectedNode] = useState<GraphNode | undefined>();
  const [viewMode, setViewMode] = useState<ViewMode>('graph');
  const [edgeFilter, setEdgeFilter] = useState<string[]>(ALL_EDGE_TYPES);
  const [confidenceMin, setConfidenceMin] = useState(0);

  const { data: graphData, isLoading, error } = useEntityGraph(selectedEntityId, depth);

  const handleSearchSelect = useCallback((result: SearchResult) => {
    setSelectedEntityId(result.id);
    setSelectedNode(undefined);
  }, []);

  const handleNodeSelect = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    emitChecklistComplete('explore_knowledge_graph');
  }, []);

  const handleLoadGraphForNode = useCallback((nodeId: string) => {
    setSelectedEntityId(nodeId);
    setSelectedNode(undefined);
  }, []);

  const handleResetView = useCallback(() => {
    setEdgeFilter(ALL_EDGE_TYPES);
    setConfidenceMin(0);
    setDepth(2);
  }, []);

  const renderViewContent = () => {
    // Welcome state (no entity selected)
    if (!selectedEntityId) {
      return (
        <div className="flex h-full items-center justify-center">
          <Card className="max-w-md">
            <CardHeader>
              <CardTitle>Willkommen im Wissens-Graph</CardTitle>
              <CardDescription>
                Nutzen Sie die Suche oben, um eine Entitaet oder ein Dokument zu finden und den zugehoerigen
                Beziehungsgraph zu visualisieren.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>
                  <strong>Funktionen:</strong>
                </p>
                <ul className="list-inside list-disc space-y-1">
                  <li>Interaktive Graph-Visualisierung</li>
                  <li>Finanzketten-Ansicht (Bestellung bis Zahlung)</li>
                  <li>Zeitstrahl fuer Dokument-Chronologie</li>
                  <li>Risiko-Netzwerk mit Communities</li>
                  <li>Dokumentenfamilien-Ansicht</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    // View-mode specific content
    switch (viewMode) {
      case 'financial':
        return (
          <UnifiedErrorBoundary variant="card" context="finance">
            <FinancialChainView
              entityId={selectedEntityId}
              onNodeSelect={handleNodeSelect}
            />
          </UnifiedErrorBoundary>
        );

      case 'timeline':
        return (
          <UnifiedErrorBoundary variant="card" context="general">
            <TimelineView
              entityId={selectedEntityId}
              onNodeSelect={handleNodeSelect}
            />
          </UnifiedErrorBoundary>
        );

      case 'risk':
        return (
          <UnifiedErrorBoundary variant="card" context="general">
            <RiskNetworkView
              entityId={selectedEntityId}
              onNodeSelect={handleNodeSelect}
            />
          </UnifiedErrorBoundary>
        );

      case 'family':
        return (
          <UnifiedErrorBoundary variant="card" context="general">
            <DocumentFamilyView
              entityId={selectedEntityId}
              documentId={selectedNode?.type === 'document' ? selectedNode.id : undefined}
              onNodeSelect={handleNodeSelect}
            />
          </UnifiedErrorBoundary>
        );

      case 'graph':
      default:
        // Standard graph view with loading/error states
        if (isLoading) {
          return (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
                <p className="text-sm text-muted-foreground">Lade Graph-Daten...</p>
              </div>
            </div>
          );
        }

        if (error) {
          return (
            <div className="flex h-full items-center justify-center">
              <Card className="max-w-md border-destructive">
                <CardHeader>
                  <CardTitle className="text-destructive">Fehler beim Laden</CardTitle>
                  <CardDescription>
                    {error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten'}
                  </CardDescription>
                </CardHeader>
              </Card>
            </div>
          );
        }

        if (graphData) {
          return (
            <UnifiedErrorBoundary variant="card" context="intelligence">
              <GraphCanvas
                data={graphData}
                onNodeSelect={handleNodeSelect}
                selectedNodeId={selectedNode?.id}
                edgeFilter={edgeFilter}
                confidenceMin={confidenceMin}
              />
              <GraphLegend />
            </UnifiedErrorBoundary>
          );
        }

        return null;
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border bg-background p-4">
        <div className="mb-4">
          <h1 className="text-2xl font-bold">Wissens-Graph</h1>
          <p className="text-sm text-muted-foreground">Visualisierung der Dokumenten-Beziehungen</p>
        </div>

        <div className="flex flex-wrap items-center gap-4" data-tour="kg-search">
          <GraphSearch onSelect={handleSearchSelect} />
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex-shrink-0 border-b border-border bg-background/95 px-4 py-2" data-tour="kg-toolbar">
        <GraphToolbar
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          edgeFilter={edgeFilter}
          onEdgeFilterChange={setEdgeFilter}
          confidenceMin={confidenceMin}
          onConfidenceMinChange={setConfidenceMin}
          depth={depth}
          onDepthChange={setDepth}
          onResetView={handleResetView}
          disabled={!selectedEntityId}
        />
      </div>

      {/* Content */}
      <div className="relative flex flex-1 overflow-hidden">
        {/* Main Content Area */}
        <div className="flex-1" data-tour="kg-canvas">
          {renderViewContent()}
        </div>

        {/* Detail Panel (Sidebar) - works for ALL view modes */}
        {selectedNode && (
          <div className="hidden w-80 flex-shrink-0 border-l border-border md:block" data-tour="kg-details">
            <NodeDetailPanel
              node={selectedNode}
              edges={graphData?.edges ?? []}
              onClose={() => setSelectedNode(undefined)}
              onLoadGraph={handleLoadGraphForNode}
            />
          </div>
        )}

        {/* Mobile Detail Panel (Overlay) */}
        {selectedNode && (
          <div className="absolute inset-0 z-10 bg-background md:hidden">
            <NodeDetailPanel
              node={selectedNode}
              edges={graphData?.edges ?? []}
              onClose={() => setSelectedNode(undefined)}
              onLoadGraph={handleLoadGraphForNode}
            />
          </div>
        )}
      </div>
    </div>
  );
}
