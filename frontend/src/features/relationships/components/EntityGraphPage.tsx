/**
 * EntityGraphPage Component
 *
 * Vollstaendige Seite fuer die Entity-Graph-Visualisierung.
 * Nutzt @xyflow/react fuer interaktive Graph-Darstellung.
 */

import { useState, useCallback, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    ReactFlow,
    MiniMap,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    type Node,
    type Edge,
    type ReactFlowInstance,
    MarkerType,
    BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { Network, Loader2, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

import { EntityNode } from './EntityNode';
import { DocumentNode } from './DocumentNode';
import { GraphControls } from './GraphControls';
import {
    fetchEntityGraphData,
    relationshipsQueryKeys,
    type GraphParams,
    type EntityType,
} from '../api/relationships-api';

// ==================== Node Types ====================

const nodeTypes = {
    entityNode: EntityNode,
    documentNode: DocumentNode,
};

// ==================== Default Edge Options ====================

const defaultEdgeOptions = {
    type: 'smoothstep',
    markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 15,
        height: 15,
    },
    style: {
        strokeWidth: 1.5,
    },
};

// ==================== Component ====================

export function EntityGraphPage() {
    // State fuer Filter
    const [entityType, setEntityType] = useState<string>('all');
    const [minDocuments, setMinDocuments] = useState(1);
    const [includeDocuments, setIncludeDocuments] = useState(false);
    const [limit, setLimit] = useState(50);

    // React Flow Instanz
    const reactFlowInstance = useRef<ReactFlowInstance | null>(null);

    // React Flow State
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    // Query Params
    const queryParams: GraphParams = useMemo(() => ({
        entityType: entityType !== 'all' ? entityType as EntityType : undefined,
        minDocuments,
        includeDocuments,
        limit,
    }), [entityType, minDocuments, includeDocuments, limit]);

    // Fetch Graph Data
    const {
        data,
        isLoading,
        isError,
        error,
        refetch,
        isFetching,
    } = useQuery({
        queryKey: relationshipsQueryKeys.graph(queryParams),
        queryFn: () => fetchEntityGraphData(queryParams),
    });

    // Update Nodes & Edges wenn Daten sich aendern
    useMemo(() => {
        if (data) {
            // Konvertiere API Response zu React Flow Format
            const flowNodes: Node[] = data.nodes.map((node) => ({
                id: node.id,
                type: node.type,
                position: node.position,
                data: node.data,
            }));

            const flowEdges: Edge[] = data.edges.map((edge) => ({
                id: edge.id,
                source: edge.source,
                target: edge.target,
                type: edge.type || 'smoothstep',
                animated: edge.animated,
                style: edge.style,
            }));

            setNodes(flowNodes);
            setEdges(flowEdges);
        }
    }, [data, setNodes, setEdges]);

    // Fit View Handler
    const handleFitView = useCallback(() => {
        if (reactFlowInstance.current) {
            reactFlowInstance.current.fitView({ padding: 0.2, duration: 300 });
        }
    }, []);

    // On Init Handler
    const onInit = useCallback((instance: ReactFlowInstance) => {
        reactFlowInstance.current = instance;
        // Initial Fit View nach kurzer Verzoegerung
        setTimeout(() => {
            instance.fitView({ padding: 0.2, duration: 300 });
        }, 100);
    }, []);

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <Card className="mb-4">
                <CardHeader className="pb-3">
                    <CardTitle className="text-xl flex items-center gap-2">
                        <Network className="h-5 w-5" />
                        Entity-Graph
                    </CardTitle>
                    <CardDescription>
                        Interaktive Visualisierung der Geschaeftspartner-Beziehungen
                    </CardDescription>
                </CardHeader>
            </Card>

            {/* Controls */}
            <GraphControls
                entityType={entityType}
                onEntityTypeChange={setEntityType}
                minDocuments={minDocuments}
                onMinDocumentsChange={setMinDocuments}
                includeDocuments={includeDocuments}
                onIncludeDocumentsChange={setIncludeDocuments}
                limit={limit}
                onLimitChange={setLimit}
                statistics={data?.statistics}
                isLoading={isLoading}
                isFetching={isFetching}
                onRefresh={() => refetch()}
                onFitView={handleFitView}
            />

            {/* Graph Container */}
            <Card className="flex-1 overflow-hidden">
                <CardContent className="p-0 h-full">
                    {isLoading ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-center">
                                <Loader2 className="h-10 w-10 animate-spin mx-auto mb-4 text-muted-foreground" />
                                <p className="text-muted-foreground">Graph wird geladen...</p>
                            </div>
                        </div>
                    ) : isError ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-center max-w-md">
                                <AlertCircle className="h-10 w-10 mx-auto mb-4 text-destructive" />
                                <p className="text-destructive font-medium mb-2">
                                    Fehler beim Laden des Graphen
                                </p>
                                <p className="text-sm text-muted-foreground mb-4">
                                    {error instanceof Error ? error.message : 'Unbekannter Fehler'}
                                </p>
                                <Button variant="outline" onClick={() => refetch()}>
                                    Erneut versuchen
                                </Button>
                            </div>
                        </div>
                    ) : nodes.length === 0 ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-center max-w-md">
                                <Network className="h-10 w-10 mx-auto mb-4 text-muted-foreground" />
                                <p className="text-muted-foreground font-medium mb-2">
                                    Keine Entities gefunden
                                </p>
                                <p className="text-sm text-muted-foreground">
                                    Versuchen Sie, die Filter anzupassen oder die Mindestanzahl
                                    an Dokumenten zu reduzieren.
                                </p>
                            </div>
                        </div>
                    ) : (
                        <ReactFlow
                            nodes={nodes}
                            edges={edges}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesChange}
                            onInit={onInit}
                            nodeTypes={nodeTypes}
                            defaultEdgeOptions={defaultEdgeOptions}
                            fitView
                            minZoom={0.1}
                            maxZoom={2}
                            proOptions={{ hideAttribution: true }}
                            className="bg-muted/30"
                        >
                            <Background
                                variant={BackgroundVariant.Dots}
                                gap={20}
                                size={1}
                                className="opacity-50"
                            />
                            <Controls
                                showInteractive={false}
                                className="bg-background border rounded-lg shadow-sm"
                            />
                            <MiniMap
                                nodeStrokeWidth={3}
                                pannable
                                zoomable
                                className="bg-background border rounded-lg shadow-sm"
                                nodeColor={(node) => {
                                    if (node.type === 'documentNode') return '#94a3b8';
                                    const data = node.data as { nodeType?: string };
                                    return data.nodeType === 'customer' ? '#3b82f6' : '#f59e0b';
                                }}
                            />
                        </ReactFlow>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}

export default EntityGraphPage;
