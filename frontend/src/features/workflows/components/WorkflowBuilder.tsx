/**
 * WorkflowBuilder Component
 *
 * Visueller Workflow-Editor mit ReactFlow.
 * Ermoeglicht Drag-and-Drop Erstellung von Workflows.
 */

import { useCallback, useMemo, useState, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Panel,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type EdgeChange,
  type OnConnect,
  BackgroundVariant,
  ConnectionLineType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { v4 as uuidv4 } from 'uuid';
import {
  Save,
  Play,
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Maximize,
  Plus,
  Trash2,
  Copy,
  Undo,
  Redo,
  Settings,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { nodeTypes, type NodeType } from './nodes';
import type {
  Workflow,
  WorkflowNode,
  WorkflowEdge,
  TriggerType,
  StepType,
  ActionType,
} from '../types/workflow-types';

interface WorkflowBuilderProps {
  workflow?: Workflow;
  onSave?: (nodes: WorkflowNode[], edges: WorkflowEdge[]) => void;
  onExecute?: () => void;
  onValidate?: () => Promise<{ valid: boolean; errors: string[]; warnings: string[] }>;
  isLoading?: boolean;
  readOnly?: boolean;
}

interface NodeTemplate {
  type: NodeType;
  label: string;
  icon: string;
  category: 'trigger' | 'logic' | 'action';
  defaultData: Record<string, unknown>;
}

const nodeTemplates: NodeTemplate[] = [
  // Triggers
  {
    type: 'trigger',
    label: 'Dokument-Event',
    icon: 'file',
    category: 'trigger',
    defaultData: { triggerType: 'document_event', config: { events: ['created'] }, isActive: true },
  },
  {
    type: 'trigger',
    label: 'Zeitplan',
    icon: 'clock',
    category: 'trigger',
    defaultData: { triggerType: 'schedule', config: { cron: '0 9 * * *' }, isActive: true },
  },
  {
    type: 'trigger',
    label: 'Webhook',
    icon: 'webhook',
    category: 'trigger',
    defaultData: { triggerType: 'webhook', config: { webhook_path: '/trigger' }, isActive: true },
  },
  {
    type: 'trigger',
    label: 'Manuell',
    icon: 'play',
    category: 'trigger',
    defaultData: { triggerType: 'manual', config: {}, isActive: true },
  },
  // Logic
  {
    type: 'condition',
    label: 'Bedingung',
    icon: 'filter',
    category: 'logic',
    defaultData: { config: { conditions: { operator: 'AND', rules: [] } } },
  },
  {
    type: 'branch',
    label: 'Verzweigung',
    icon: 'git-branch',
    category: 'logic',
    defaultData: { config: { branches: [], default_branch: 'default' } },
  },
  {
    type: 'delay',
    label: 'Verzoegerung',
    icon: 'clock',
    category: 'logic',
    defaultData: { config: { delay_seconds: 60 } },
  },
  {
    type: 'parallel',
    label: 'Parallel',
    icon: 'git-fork',
    category: 'logic',
    defaultData: { config: { steps: [] } },
  },
  {
    type: 'loop',
    label: 'Schleife',
    icon: 'repeat',
    category: 'logic',
    defaultData: { config: { loop_type: 'count', count: 3 } },
  },
  // Actions
  {
    type: 'action',
    label: 'Ordner verschieben',
    icon: 'folder',
    category: 'action',
    defaultData: { config: { action_type: 'move_folder' } },
  },
  {
    type: 'action',
    label: 'Tags zuweisen',
    icon: 'tag',
    category: 'action',
    defaultData: { config: { action_type: 'assign_tags', tag_names: [] } },
  },
  {
    type: 'action',
    label: 'Benachrichtigung',
    icon: 'bell',
    category: 'action',
    defaultData: { config: { action_type: 'send_notification' } },
  },
  {
    type: 'action',
    label: 'E-Mail senden',
    icon: 'mail',
    category: 'action',
    defaultData: { config: { action_type: 'send_email' } },
  },
  {
    type: 'action',
    label: 'OCR starten',
    icon: 'scan',
    category: 'action',
    defaultData: { config: { action_type: 'start_ocr', backend: 'auto' } },
  },
  {
    type: 'action',
    label: 'KI-Kategorisierung',
    icon: 'brain',
    category: 'action',
    defaultData: { config: { action_type: 'ai_categorization' } },
  },
  {
    type: 'action',
    label: 'Webhook aufrufen',
    icon: 'webhook',
    category: 'action',
    defaultData: { config: { action_type: 'call_webhook' } },
  },
  {
    type: 'action',
    label: 'HTTP-Request',
    icon: 'globe',
    category: 'action',
    defaultData: { config: { action_type: 'http_request', method: 'POST' } },
  },
];

export default function WorkflowBuilder({
  workflow,
  onSave,
  onExecute,
  onValidate,
  isLoading = false,
  readOnly = false,
}: WorkflowBuilderProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(
    workflow?.nodes?.map((n) => ({
      ...n,
      data: n.data,
    })) || []
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(workflow?.edges || []);
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [validation, setValidation] = useState<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  } | null>(null);
  const [history, setHistory] = useState<{ nodes: Node[]; edges: Edge[] }[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Handle connections
  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `e-${connection.source}-${connection.target}-${uuidv4().slice(0, 8)}`,
            type: 'smoothstep',
            animated: true,
          },
          eds
        )
      );
    },
    [setEdges]
  );

  // Track selection
  const onSelectionChange = useCallback(({ nodes: selected }: { nodes: Node[] }) => {
    setSelectedNodes(selected.map((n) => n.id));
  }, []);

  // Add node from palette
  const addNode = useCallback(
    (template: NodeTemplate) => {
      const position = {
        x: Math.random() * 300 + 100,
        y: Math.random() * 200 + 100,
      };

      const newNode: Node = {
        id: `node-${uuidv4()}`,
        type: template.type,
        position,
        data: {
          label: template.label,
          ...template.defaultData,
        },
      };

      setNodes((nds) => [...nds, newNode]);
    },
    [setNodes]
  );

  // Delete selected nodes
  const deleteSelected = useCallback(() => {
    setNodes((nds) => nds.filter((n) => !selectedNodes.includes(n.id)));
    setEdges((eds) =>
      eds.filter(
        (e) => !selectedNodes.includes(e.source) && !selectedNodes.includes(e.target)
      )
    );
    setSelectedNodes([]);
  }, [selectedNodes, setNodes, setEdges]);

  // Duplicate selected nodes
  const duplicateSelected = useCallback(() => {
    const selectedNodeObjects = nodes.filter((n) => selectedNodes.includes(n.id));
    const newNodes = selectedNodeObjects.map((n) => ({
      ...n,
      id: `node-${uuidv4()}`,
      position: {
        x: n.position.x + 50,
        y: n.position.y + 50,
      },
    }));
    setNodes((nds) => [...nds, ...newNodes]);
  }, [nodes, selectedNodes, setNodes]);

  // Save history for undo/redo
  const saveHistory = useCallback(() => {
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push({ nodes: [...nodes], edges: [...edges] });
    setHistory(newHistory.slice(-50)); // Keep last 50 states
    setHistoryIndex(newHistory.length - 1);
  }, [nodes, edges, history, historyIndex]);

  // Undo
  const undo = useCallback(() => {
    if (historyIndex > 0) {
      const prevState = history[historyIndex - 1];
      setNodes(prevState.nodes);
      setEdges(prevState.edges);
      setHistoryIndex(historyIndex - 1);
    }
  }, [history, historyIndex, setNodes, setEdges]);

  // Redo
  const redo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const nextState = history[historyIndex + 1];
      setNodes(nextState.nodes);
      setEdges(nextState.edges);
      setHistoryIndex(historyIndex + 1);
    }
  }, [history, historyIndex, setNodes, setEdges]);

  // Handle save
  const handleSave = useCallback(() => {
    const workflowNodes: WorkflowNode[] = nodes.map((n) => ({
      id: n.id,
      type: n.type || 'action',
      position: n.position,
      data: n.data as Record<string, unknown>,
    }));

    const workflowEdges: WorkflowEdge[] = edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle || undefined,
      targetHandle: e.targetHandle || undefined,
      label: e.label as string | undefined,
    }));

    onSave?.(workflowNodes, workflowEdges);
  }, [nodes, edges, onSave]);

  // Handle validation
  const handleValidate = useCallback(async () => {
    if (onValidate) {
      const result = await onValidate();
      setValidation(result);
    }
  }, [onValidate]);

  // Reset workflow
  const handleReset = useCallback(() => {
    if (workflow) {
      setNodes(
        workflow.nodes?.map((n) => ({
          ...n,
          data: n.data,
        })) || []
      );
      setEdges(workflow.edges || []);
    } else {
      setNodes([]);
      setEdges([]);
    }
    setValidation(null);
  }, [workflow, setNodes, setEdges]);

  // Group templates by category
  const groupedTemplates = useMemo(() => {
    return {
      trigger: nodeTemplates.filter((t) => t.category === 'trigger'),
      logic: nodeTemplates.filter((t) => t.category === 'logic'),
      action: nodeTemplates.filter((t) => t.category === 'action'),
    };
  }, []);

  return (
    <div className="flex h-full w-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b bg-background p-2">
        {/* Add Node Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={readOnly}>
              <Plus className="mr-2 h-4 w-4" />
              Knoten hinzufuegen
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
              Trigger
            </div>
            {groupedTemplates.trigger.map((template) => (
              <DropdownMenuItem key={template.label} onClick={() => addNode(template)}>
                {template.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
              Logik
            </div>
            {groupedTemplates.logic.map((template) => (
              <DropdownMenuItem key={template.label} onClick={() => addNode(template)}>
                {template.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
              Aktionen
            </div>
            {groupedTemplates.action.map((template) => (
              <DropdownMenuItem key={template.label} onClick={() => addNode(template)}>
                {template.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <Separator orientation="vertical" className="h-6" />

        {/* Undo/Redo */}
        <Button
          variant="ghost"
          size="icon"
          onClick={undo}
          disabled={historyIndex <= 0 || readOnly}
          title="Rueckgaengig"
        >
          <Undo className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={redo}
          disabled={historyIndex >= history.length - 1 || readOnly}
          title="Wiederholen"
        >
          <Redo className="h-4 w-4" />
        </Button>

        <Separator orientation="vertical" className="h-6" />

        {/* Selection Actions */}
        <Button
          variant="ghost"
          size="icon"
          onClick={duplicateSelected}
          disabled={selectedNodes.length === 0 || readOnly}
          title="Duplizieren"
        >
          <Copy className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={deleteSelected}
          disabled={selectedNodes.length === 0 || readOnly}
          title="Loeschen"
        >
          <Trash2 className="h-4 w-4" />
        </Button>

        <Separator orientation="vertical" className="h-6" />

        {/* Reset */}
        <Button variant="ghost" size="icon" onClick={handleReset} title="Zuruecksetzen">
          <RotateCcw className="h-4 w-4" />
        </Button>

        <div className="flex-1" />

        {/* Validation Status */}
        {validation && (
          <div className="flex items-center gap-2">
            {validation.valid ? (
              <Badge variant="outline" className="gap-1 text-green-600">
                <CheckCircle className="h-3 w-3" />
                Gueltig
              </Badge>
            ) : (
              <Badge variant="outline" className="gap-1 text-red-600">
                <AlertCircle className="h-3 w-3" />
                {validation.errors.length} Fehler
              </Badge>
            )}
          </div>
        )}

        {/* Actions */}
        <Button variant="outline" size="sm" onClick={handleValidate} disabled={isLoading}>
          <CheckCircle className="mr-2 h-4 w-4" />
          Validieren
        </Button>

        <Button variant="outline" size="sm" onClick={onExecute} disabled={isLoading || readOnly}>
          <Play className="mr-2 h-4 w-4" />
          Ausfuehren
        </Button>

        <Button size="sm" onClick={handleSave} disabled={isLoading || readOnly}>
          <Save className="mr-2 h-4 w-4" />
          Speichern
        </Button>
      </div>

      {/* ReactFlow Canvas */}
      <div ref={reactFlowWrapper} className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onSelectionChange={onSelectionChange}
          nodeTypes={nodeTypes}
          connectionLineType={ConnectionLineType.SmoothStep}
          fitView
          snapToGrid
          snapGrid={[15, 15]}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable={!readOnly}
          deleteKeyCode={readOnly ? null : 'Delete'}
          className="bg-muted/30"
        >
          <Background variant={BackgroundVariant.Dots} gap={15} size={1} />
          <Controls showZoom showFitView showInteractive={false} />
          <MiniMap
            nodeStrokeWidth={3}
            zoomable
            pannable
            className="!bottom-4 !right-4"
          />
        </ReactFlow>
      </div>

      {/* Status Bar */}
      <div className="flex items-center justify-between border-t bg-muted/30 px-4 py-1 text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>{nodes.length} Knoten</span>
          <span>{edges.length} Verbindungen</span>
          {selectedNodes.length > 0 && (
            <span>{selectedNodes.length} ausgewaehlt</span>
          )}
        </div>
        {workflow && (
          <div className="flex items-center gap-4">
            <span>
              Ausfuehrungen: {workflow.execution_count}
            </span>
            {workflow.last_executed_at && (
              <span>
                Letzte Ausfuehrung:{' '}
                {new Date(workflow.last_executed_at).toLocaleString('de-DE')}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
