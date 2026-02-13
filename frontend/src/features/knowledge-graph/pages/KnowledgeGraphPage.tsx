/**
 * Knowledge Graph Page
 * Hauptseite für die interaktive Wissens-Graph-Visualisierung
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useEntityGraph } from '../hooks/use-knowledge-graph-queries';
import { GraphCanvas } from '../components/GraphCanvas';
import { GraphSearch } from '../components/GraphSearch';
import { NodeDetailPanel } from '../components/NodeDetailPanel';
import { GraphLegend } from '../components/GraphLegend';
import type { GraphNode, SearchResult } from '../types';

export function KnowledgeGraphPage() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | undefined>();
  const [depth, setDepth] = useState(2);
  const [selectedNode, setSelectedNode] = useState<GraphNode | undefined>();

  const { data: graphData, isLoading, error } = useEntityGraph(selectedEntityId, depth);

  const handleSearchSelect = (result: SearchResult) => {
    setSelectedEntityId(result.id);
    setSelectedNode(undefined);
  };

  const handleNodeSelect = (node: GraphNode) => {
    setSelectedNode(node);
  };

  const handleLoadGraphForNode = (nodeId: string) => {
    setSelectedEntityId(nodeId);
    setSelectedNode(undefined);
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border bg-background p-4">
        <div className="mb-4">
          <h1 className="text-2xl font-bold">Wissens-Graph</h1>
          <p className="text-sm text-muted-foreground">Visualisierung der Dokumenten-Beziehungen</p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <GraphSearch onSelect={handleSearchSelect} />

          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Tiefe:</span>
            {[1, 2, 3].map((d) => (
              <Button
                key={d}
                variant={depth === d ? 'default' : 'outline'}
                size="sm"
                onClick={() => setDepth(d)}
                disabled={!selectedEntityId}
              >
                {d}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="relative flex flex-1 overflow-hidden">
        {/* Graph Canvas */}
        <div className="flex-1">
          {!selectedEntityId ? (
            <div className="flex h-full items-center justify-center">
              <Card className="max-w-md">
                <CardHeader>
                  <CardTitle>Willkommen im Wissens-Graph</CardTitle>
                  <CardDescription>
                    Nutzen Sie die Suche oben, um eine Entität oder ein Dokument zu finden und den zugehörigen
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
                      <li>Klicken Sie auf Knoten für Details</li>
                      <li>Ziehen Sie Knoten zum Verschieben</li>
                      <li>Mausrad zum Zoomen</li>
                      <li>Konfigurierbarer Tiefe-Level (1-3)</li>
                    </ul>
                  </div>
                </CardContent>
              </Card>
            </div>
          ) : isLoading ? (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
                <p className="text-sm text-muted-foreground">Lade Graph-Daten...</p>
              </div>
            </div>
          ) : error ? (
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
          ) : graphData ? (
            <>
              <GraphCanvas
                data={graphData}
                onNodeSelect={handleNodeSelect}
                selectedNodeId={selectedNode?.id}
              />
              <GraphLegend />
            </>
          ) : null}
        </div>

        {/* Detail Panel (Sidebar) */}
        {selectedNode && graphData && (
          <div className="hidden w-80 flex-shrink-0 border-l border-border md:block">
            <NodeDetailPanel
              node={selectedNode}
              edges={graphData.edges}
              onClose={() => setSelectedNode(undefined)}
              onLoadGraph={handleLoadGraphForNode}
            />
          </div>
        )}

        {/* Mobile Detail Panel (Overlay) */}
        {selectedNode && graphData && (
          <div className="absolute inset-0 z-10 bg-background md:hidden">
            <NodeDetailPanel
              node={selectedNode}
              edges={graphData.edges}
              onClose={() => setSelectedNode(undefined)}
              onLoadGraph={handleLoadGraphForNode}
            />
          </div>
        )}
      </div>
    </div>
  );
}
