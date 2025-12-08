import { useEffect, useMemo } from 'react';
import { ReactFlow, Background, Controls, MiniMap, useNodesState, useEdgesState } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { DocumentRelationship } from '../types';
import type { Document } from '@/lib/api/services/documents';
import { DocumentNode } from './DocumentNode';

interface RelationshipGraphProps {
    relationships: DocumentRelationship[];
    documents: Document[];
    onNodeClick?: (nodeId: string) => void;
}

export function RelationshipGraph({ relationships, documents, onNodeClick }: RelationshipGraphProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

    const nodeTypes = useMemo(() => ({
        document: DocumentNode,
    }), []);

    useEffect(() => {
        if (!documents.length) return;

        // Simple grid layout
        const cols = Math.ceil(Math.sqrt(documents.length));
        const spacing = 250;

        const newNodes: Node[] = documents.map((doc, index) => ({
            id: doc.id,
            position: {
                x: (index % cols) * spacing,
                y: Math.floor(index / cols) * spacing
            },
            data: { label: doc.title || doc.name },
            type: 'document', // Use custom type
        }));

        const newEdges: Edge[] = relationships.map(rel => ({
            id: rel.id,
            source: rel.sourceDocumentId,
            target: rel.targetDocumentId,
            label: rel.type,
            type: 'smoothstep', // Better edge type
            animated: true,
            style: { stroke: 'hsl(var(--primary))' },
        }));

        setNodes(newNodes);
        setEdges(newEdges);
    }, [relationships, documents, setNodes, setEdges]);

    return (
        <div className="h-full w-full min-h-[500px] border rounded-lg bg-background/50 backdrop-blur-sm">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={(_, node) => onNodeClick?.(node.id)}
                nodeTypes={nodeTypes}
                fitView
                className="bg-muted/10"
            >
                <Background color="hsl(var(--muted-foreground))" gap={20} size={1} className="opacity-20" />
                <Controls className="bg-background border-border" />
                <MiniMap className="bg-background border-border" />
            </ReactFlow>
        </div>
    );
}
