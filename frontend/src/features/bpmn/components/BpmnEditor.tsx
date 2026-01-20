/**
 * BPMN Process Editor
 *
 * Visual drag & drop editor for BPMN 2.0 processes using React Flow.
 */

import { useCallback, useRef, useState, useMemo } from 'react';
import ReactFlow, {
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type OnConnect,
  BackgroundVariant,
  MarkerType,
  ConnectionMode,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Save,
  Play,
  Undo,
  Redo,
  ZoomIn,
  ZoomOut,
  Maximize,
  Download,
} from 'lucide-react';
import { bpmnNodeTypes } from './nodes';
import { BpmnPalette } from './BpmnPalette';
import { BpmnPropertiesPanel } from './BpmnPropertiesPanel';
import type { BPMNElement, BPMNFlow, BPMNProcessData, BPMNNodeData } from '../types/bpmn-types';

interface BpmnEditorProps {
  initialData?: BPMNProcessData;
  onSave?: (data: BPMNProcessData) => void;
  onDeploy?: (data: BPMNProcessData) => void;
  readOnly?: boolean;
  className?: string;
}

// Convert BPMN elements to React Flow nodes
function elementsToNodes(elements: BPMNElement[]): Node<BPMNNodeData>[] {
  return elements.map((element, index) => ({
    id: element.id,
    type: element.type,
    position: element.position || { x: 100 + index * 200, y: 100 },
    data: {
      element,
      label: element.name || element.id,
      type: element.type,
    },
  }));
}

// Convert BPMN flows to React Flow edges
function flowsToEdges(flows: BPMNFlow[]): Edge[] {
  return flows.map((flow) => ({
    id: flow.id,
    source: flow.source,
    target: flow.target,
    label: flow.name,
    type: 'smoothstep',
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 20,
      height: 20,
    },
    data: { flow },
  }));
}

// Convert React Flow nodes back to BPMN elements
function nodesToElements(nodes: Node<BPMNNodeData>[]): BPMNElement[] {
  return nodes.map((node) => ({
    ...node.data.element,
    position: node.position,
  }));
}

// Convert React Flow edges back to BPMN flows
function edgesToFlows(edges: Edge[]): BPMNFlow[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    name: edge.label as string | undefined,
    condition: edge.data?.condition,
  }));
}

function BpmnEditorInner({
  initialData,
  onSave,
  onDeploy,
  readOnly = false,
  className,
}: BpmnEditorProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [selectedNode, setSelectedNode] = useState<Node<BPMNNodeData> | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);

  // Initialize nodes and edges from initial data
  const initialNodes = useMemo(
    () => elementsToNodes(initialData?.elements || []),
    [initialData]
  );
  const initialEdges = useMemo(
    () => flowsToEdges(initialData?.flows || []),
    [initialData]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Handle new connections
  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;
      const newEdge: Edge = {
        ...connection,
        id: `flow_${Date.now()}`,
        type: 'smoothstep',
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 20,
          height: 20,
        },
      } as Edge;
      setEdges((eds) => addEdge(newEdge, eds));
    },
    [readOnly, setEdges]
  );

  // Handle node selection
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node<BPMNNodeData>) => {
      setSelectedNode(node);
      setSelectedEdge(null);
    },
    []
  );

  // Handle edge selection
  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
  }, []);

  // Handle pane click (deselect)
  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  // Handle drag and drop from palette
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      if (readOnly) return;
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      if (!type || !reactFlowWrapper.current) return;

      const reactFlowBounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = {
        x: event.clientX - reactFlowBounds.left - 75,
        y: event.clientY - reactFlowBounds.top - 25,
      };

      const newElement: BPMNElement = {
        id: `${type}_${Date.now()}`,
        type: type as BPMNElement['type'],
        name: getDefaultName(type),
        position,
        properties: {},
      };

      const newNode: Node<BPMNNodeData> = {
        id: newElement.id,
        type: newElement.type,
        position,
        data: {
          element: newElement,
          label: newElement.name || newElement.id,
          type: newElement.type,
        },
      };

      setNodes((nds) => [...nds, newNode]);
    },
    [readOnly, setNodes]
  );

  // Get default name for element type
  const getDefaultName = (type: string): string => {
    const names: Record<string, string> = {
      startEvent: 'Start',
      endEvent: 'Ende',
      userTask: 'Benutzer-Aufgabe',
      serviceTask: 'Service-Aufgabe',
      scriptTask: 'Script-Aufgabe',
      exclusiveGateway: 'Entscheidung',
      parallelGateway: 'Parallel',
      inclusiveGateway: 'Inklusiv',
    };
    return names[type] || type;
  };

  // Build process data from current state
  const buildProcessData = useCallback((): BPMNProcessData => {
    return {
      id: initialData?.id || `process_${Date.now()}`,
      name: initialData?.name || 'Neuer Prozess',
      elements: nodesToElements(nodes),
      flows: edgesToFlows(edges),
      metadata: initialData?.metadata,
    };
  }, [nodes, edges, initialData]);

  // Handle save
  const handleSave = useCallback(() => {
    const data = buildProcessData();
    onSave?.(data);
  }, [buildProcessData, onSave]);

  // Handle deploy
  const handleDeploy = useCallback(() => {
    const data = buildProcessData();
    onDeploy?.(data);
  }, [buildProcessData, onDeploy]);

  // Update node data
  const updateNodeData = useCallback(
    (nodeId: string, updates: Partial<BPMNElement>) => {
      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === nodeId) {
            const updatedElement = { ...node.data.element, ...updates };
            return {
              ...node,
              data: {
                ...node.data,
                element: updatedElement,
                label: updates.name || node.data.label,
              },
            };
          }
          return node;
        })
      );
    },
    [setNodes]
  );

  // Delete selected node
  const deleteSelectedNode = useCallback(() => {
    if (selectedNode) {
      setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
      setEdges((eds) =>
        eds.filter(
          (e) => e.source !== selectedNode.id && e.target !== selectedNode.id
        )
      );
      setSelectedNode(null);
    }
  }, [selectedNode, setNodes, setEdges]);

  return (
    <div className={cn('flex h-full w-full', className)}>
      {/* Palette */}
      {!readOnly && <BpmnPalette className="w-60 border-r" />}

      {/* Main Editor */}
      <div className="flex-1" ref={reactFlowWrapper}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={readOnly ? undefined : onNodesChange}
          onEdgesChange={readOnly ? undefined : onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          onDragOver={onDragOver}
          onDrop={onDrop}
          nodeTypes={bpmnNodeTypes}
          connectionMode={ConnectionMode.Loose}
          fitView
          attributionPosition="bottom-left"
          className="bg-slate-50"
          deleteKeyCode={readOnly ? null : 'Delete'}
          selectionKeyCode={readOnly ? null : 'Shift'}
          multiSelectionKeyCode={readOnly ? null : 'Meta'}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls showInteractive={!readOnly} />
          <MiniMap
            nodeStrokeWidth={3}
            zoomable
            pannable
            className="!bg-white/80"
          />

          {/* Toolbar */}
          <Panel position="top-right" className="flex gap-2">
            {!readOnly && (
              <>
                <Button variant="outline" size="sm" onClick={handleSave}>
                  <Save className="mr-1 h-4 w-4" />
                  Speichern
                </Button>
                <Button variant="default" size="sm" onClick={handleDeploy}>
                  <Play className="mr-1 h-4 w-4" />
                  Bereitstellen
                </Button>
              </>
            )}
            <Button variant="outline" size="icon" className="h-8 w-8">
              <Download className="h-4 w-4" />
            </Button>
          </Panel>

          {/* Status */}
          <Panel position="bottom-right" className="text-xs text-gray-500">
            {nodes.length} Elemente | {edges.length} Verbindungen
          </Panel>
        </ReactFlow>
      </div>

      {/* Properties Panel */}
      {(selectedNode || selectedEdge) && !readOnly && (
        <BpmnPropertiesPanel
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          onUpdateNode={updateNodeData}
          onDeleteNode={deleteSelectedNode}
          onClose={() => {
            setSelectedNode(null);
            setSelectedEdge(null);
          }}
          className="w-72 border-l"
        />
      )}
    </div>
  );
}

export function BpmnEditor(props: BpmnEditorProps) {
  return (
    <ReactFlowProvider>
      <BpmnEditorInner {...props} />
    </ReactFlowProvider>
  );
}

export default BpmnEditor;
