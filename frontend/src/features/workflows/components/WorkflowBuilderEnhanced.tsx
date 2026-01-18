/**
 * WorkflowBuilderEnhanced Component
 *
 * Enhanced visual workflow editor with drag-and-drop palette,
 * node configuration panel, and export/import functionality.
 *
 * Phase 3.2 der Feature-Roadmap (Januar 2026)
 */

import {
  useCallback,
  useMemo,
  useState,
  useRef,
  type DragEvent,
} from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Panel,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
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
  Undo,
  Redo,
  CheckCircle,
  AlertCircle,
  Download,
  Upload,
  PanelLeftClose,
  PanelRightClose,
  Copy,
  Trash2,
  FileJson,
  Maximize,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { nodeTypes } from './nodes';
import { NodePalette, type NodeTemplate } from './NodePalette';
import { NodeConfigPanel } from './NodeConfigPanel';
import type {
  Workflow,
  WorkflowNode,
  WorkflowEdge,
} from '../types/workflow-types';

// ==================== Types ====================

interface WorkflowBuilderEnhancedProps {
  workflow?: Workflow;
  onSave?: (nodes: WorkflowNode[], edges: WorkflowEdge[]) => void;
  onExecute?: () => void;
  onValidate?: () => Promise<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  }>;
  isLoading?: boolean;
  readOnly?: boolean;
}

interface HistoryState {
  nodes: Node[];
  edges: Edge[];
}

// ==================== Inner Component ====================

function WorkflowBuilderInner({
  workflow,
  onSave,
  onExecute,
  onValidate,
  isLoading = false,
  readOnly = false,
}: WorkflowBuilderEnhancedProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useReactFlow();

  // State
  const [nodes, setNodes, onNodesChange] = useNodesState(
    workflow?.nodes?.map((n) => ({
      ...n,
      data: n.data,
    })) || []
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(workflow?.edges || []);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [showPalette, setShowPalette] = useState(true);
  const [showConfigPanel, setShowConfigPanel] = useState(true);
  const [validation, setValidation] = useState<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  } | null>(null);

  // History for undo/redo
  const [history, setHistory] = useState<HistoryState[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Import/Export dialogs
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importJson, setImportJson] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ==================== Connections ====================

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
      saveHistory();
    },
    [setEdges, saveHistory]
  );

  // ==================== Selection ====================

  const onSelectionChange = useCallback(
    ({ nodes: selected }: { nodes: Node[] }) => {
      if (selected.length === 1) {
        setSelectedNode(selected[0]);
        if (!showConfigPanel) setShowConfigPanel(true);
      } else {
        setSelectedNode(null);
      }
    },
    [showConfigPanel]
  );

  // ==================== Node Update ====================

  const handleNodeUpdate = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
        )
      );
      // Update selected node reference
      setSelectedNode((prev) =>
        prev?.id === nodeId ? { ...prev, data: { ...prev.data, ...data } } : prev
      );
    },
    [setNodes]
  );

  // ==================== Drag & Drop ====================

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();

      const templateData = event.dataTransfer.getData('application/reactflow');
      if (!templateData) return;

      const template: NodeTemplate = JSON.parse(templateData);

      // Get position relative to canvas
      const reactFlowBounds = reactFlowWrapper.current?.getBoundingClientRect();
      if (!reactFlowBounds) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX - reactFlowBounds.left,
        y: event.clientY - reactFlowBounds.top,
      });

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
      saveHistory();

      toast.success('Knoten hinzugefuegt', {
        description: template.label,
      });
    },
    [reactFlowInstance, setNodes, saveHistory]
  );

  // ==================== History ====================

  const saveHistory = useCallback(() => {
    setHistory((prev) => {
      const newHistory = prev.slice(0, historyIndex + 1);
      newHistory.push({ nodes: [...nodes], edges: [...edges] });
      return newHistory.slice(-50);
    });
    setHistoryIndex((prev) => Math.min(prev + 1, 49));
  }, [nodes, edges, historyIndex]);

  const undo = useCallback(() => {
    if (historyIndex > 0) {
      const prevState = history[historyIndex - 1];
      setNodes(prevState.nodes);
      setEdges(prevState.edges);
      setHistoryIndex(historyIndex - 1);
    }
  }, [history, historyIndex, setNodes, setEdges]);

  const redo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const nextState = history[historyIndex + 1];
      setNodes(nextState.nodes);
      setEdges(nextState.edges);
      setHistoryIndex(historyIndex + 1);
    }
  }, [history, historyIndex, setNodes, setEdges]);

  // ==================== Actions ====================

  const deleteSelected = useCallback(() => {
    if (!selectedNode) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
    setEdges((eds) =>
      eds.filter(
        (e) => e.source !== selectedNode.id && e.target !== selectedNode.id
      )
    );
    setSelectedNode(null);
    saveHistory();
    toast.success('Knoten geloescht');
  }, [selectedNode, setNodes, setEdges, saveHistory]);

  const duplicateSelected = useCallback(() => {
    if (!selectedNode) return;
    const newNode: Node = {
      ...selectedNode,
      id: `node-${uuidv4()}`,
      position: {
        x: selectedNode.position.x + 50,
        y: selectedNode.position.y + 50,
      },
    };
    setNodes((nds) => [...nds, newNode]);
    saveHistory();
    toast.success('Knoten dupliziert');
  }, [selectedNode, setNodes, saveHistory]);

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
    setSelectedNode(null);
    toast.info('Workflow zurueckgesetzt');
  }, [workflow, setNodes, setEdges]);

  // ==================== Save ====================

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

  // ==================== Validation ====================

  const handleValidate = useCallback(async () => {
    if (onValidate) {
      const result = await onValidate();
      setValidation(result);
      if (result.valid) {
        toast.success('Workflow ist gueltig');
      } else {
        toast.error('Validierungsfehler', {
          description: `${result.errors.length} Fehler gefunden`,
        });
      }
    }
  }, [onValidate]);

  // ==================== Export/Import ====================

  const exportWorkflow = useMemo(() => {
    return JSON.stringify(
      {
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.type,
          position: n.position,
          data: n.data,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle,
          label: e.label,
        })),
        exportedAt: new Date().toISOString(),
        version: '1.0',
      },
      null,
      2
    );
  }, [nodes, edges]);

  const handleExport = useCallback(() => {
    const blob = new Blob([exportWorkflow], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `workflow-${workflow?.name || 'export'}-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    setShowExportDialog(false);
    toast.success('Workflow exportiert');
  }, [exportWorkflow, workflow?.name]);

  const handleImport = useCallback(() => {
    try {
      const data = JSON.parse(importJson);

      if (!data.nodes || !Array.isArray(data.nodes)) {
        throw new Error('Ungueltige Workflow-Daten: nodes fehlt');
      }

      setNodes(data.nodes);
      setEdges(data.edges || []);
      setShowImportDialog(false);
      setImportJson('');
      saveHistory();
      toast.success('Workflow importiert', {
        description: `${data.nodes.length} Knoten geladen`,
      });
    } catch (error) {
      toast.error('Import fehlgeschlagen', {
        description: error instanceof Error ? error.message : 'Ungueltiges JSON',
      });
    }
  }, [importJson, setNodes, setEdges, saveHistory]);

  const handleFileImport = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      const reader = new FileReader();

      reader.onload = (e) => {
        const content = e.target?.result;
        if (typeof content === 'string') {
          setImportJson(content);
        } else {
          toast.error('Datei konnte nicht gelesen werden', {
            description: 'Unerwartetes Datenformat',
          });
        }
      };

      reader.onerror = () => {
        toast.error('Datei konnte nicht gelesen werden', {
          description: reader.error?.message || 'Unbekannter Fehler beim Lesen der Datei',
        });
      };

      reader.readAsText(file);
      event.target.value = '';
    },
    []
  );

  const handleCopyToClipboard = useCallback(() => {
    navigator.clipboard.writeText(exportWorkflow);
    toast.success('In Zwischenablage kopiert');
  }, [exportWorkflow]);

  // ==================== Keyboard Shortcuts ====================

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (readOnly) return;

      // Ctrl+Z = Undo
      if (event.ctrlKey && event.key === 'z' && !event.shiftKey) {
        event.preventDefault();
        undo();
      }
      // Ctrl+Shift+Z or Ctrl+Y = Redo
      if (
        (event.ctrlKey && event.shiftKey && event.key === 'z') ||
        (event.ctrlKey && event.key === 'y')
      ) {
        event.preventDefault();
        redo();
      }
      // Delete
      if (event.key === 'Delete' && selectedNode) {
        event.preventDefault();
        deleteSelected();
      }
      // Ctrl+D = Duplicate
      if (event.ctrlKey && event.key === 'd' && selectedNode) {
        event.preventDefault();
        duplicateSelected();
      }
      // Ctrl+S = Save
      if (event.ctrlKey && event.key === 's') {
        event.preventDefault();
        handleSave();
      }
    },
    [readOnly, undo, redo, selectedNode, deleteSelected, duplicateSelected, handleSave]
  );

  // ==================== Render ====================

  return (
    <div
      className="flex h-full w-full"
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="application"
      aria-label="Workflow-Editor"
    >
      {/* Node Palette */}
      {showPalette && (
        <NodePalette disabled={readOnly} className="shrink-0" />
      )}

      {/* Main Editor Area */}
      <div className="flex flex-1 flex-col">
        {/* Toolbar */}
        <div
          className="flex items-center gap-2 border-b bg-background p-2"
          role="toolbar"
          aria-label="Workflow-Werkzeugleiste"
        >
          <TooltipProvider>
            {/* Toggle Palette */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowPalette(!showPalette)}
                  aria-label={showPalette ? 'Palette ausblenden' : 'Palette einblenden'}
                >
                  <PanelLeftClose
                    className={cn('h-4 w-4', !showPalette && 'rotate-180')}
                  />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {showPalette ? 'Palette ausblenden' : 'Palette einblenden'}
              </TooltipContent>
            </Tooltip>

            <Separator orientation="vertical" className="h-6" />

            {/* Undo/Redo */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={undo}
                  disabled={historyIndex <= 0 || readOnly}
                  aria-label="Rueckgaengig (Strg+Z)"
                >
                  <Undo className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Rueckgaengig (Strg+Z)</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={redo}
                  disabled={historyIndex >= history.length - 1 || readOnly}
                  aria-label="Wiederholen (Strg+Y)"
                >
                  <Redo className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Wiederholen (Strg+Y)</TooltipContent>
            </Tooltip>

            <Separator orientation="vertical" className="h-6" />

            {/* Selection Actions */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={duplicateSelected}
                  disabled={!selectedNode || readOnly}
                  aria-label="Duplizieren (Strg+D)"
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Duplizieren (Strg+D)</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={deleteSelected}
                  disabled={!selectedNode || readOnly}
                  aria-label="Loeschen (Entf)"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Loeschen (Entf)</TooltipContent>
            </Tooltip>

            <Separator orientation="vertical" className="h-6" />

            {/* Reset */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleReset}
                  aria-label="Zuruecksetzen"
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Zuruecksetzen</TooltipContent>
            </Tooltip>

            {/* Export/Import */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Export/Import">
                  <FileJson className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem onClick={() => setShowExportDialog(true)}>
                  <Download className="mr-2 h-4 w-4" />
                  Exportieren
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => setShowImportDialog(true)}
                  disabled={readOnly}
                >
                  <Upload className="mr-2 h-4 w-4" />
                  Importieren
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <div className="flex-1" />

            {/* Validation Status */}
            {validation && (
              <div className="flex items-center gap-2" role="status" aria-live="polite">
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

            {/* Main Actions */}
            <Button
              variant="outline"
              size="sm"
              onClick={handleValidate}
              disabled={isLoading}
            >
              <CheckCircle className="mr-2 h-4 w-4" />
              Validieren
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={onExecute}
              disabled={isLoading || readOnly}
            >
              <Play className="mr-2 h-4 w-4" />
              Ausfuehren
            </Button>

            <Button
              size="sm"
              onClick={handleSave}
              disabled={isLoading || readOnly}
            >
              <Save className="mr-2 h-4 w-4" />
              Speichern
            </Button>

            <Separator orientation="vertical" className="h-6" />

            {/* Toggle Config Panel */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowConfigPanel(!showConfigPanel)}
                  aria-label={
                    showConfigPanel
                      ? 'Konfiguration ausblenden'
                      : 'Konfiguration einblenden'
                  }
                >
                  <PanelRightClose
                    className={cn('h-4 w-4', !showConfigPanel && 'rotate-180')}
                  />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {showConfigPanel
                  ? 'Konfiguration ausblenden'
                  : 'Konfiguration einblenden'}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* ReactFlow Canvas */}
        <div
          ref={reactFlowWrapper}
          className="flex-1"
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
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
            aria-label="Workflow-Diagramm"
          >
            <Background variant={BackgroundVariant.Dots} gap={15} size={1} />
            <Controls showZoom showFitView showInteractive={false} />
            <MiniMap
              nodeStrokeWidth={3}
              zoomable
              pannable
              className="!bottom-4 !right-4"
              aria-label="Workflow-Minimap"
            />

            {/* Drop Zone Indicator */}
            {nodes.length === 0 && (
              <Panel position="top-center" className="mt-20">
                <div className="rounded-lg border-2 border-dashed border-muted-foreground/25 bg-background/50 p-8 text-center">
                  <p className="text-lg font-medium text-muted-foreground">
                    Ziehen Sie Knoten aus der Palette hierher
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground/75">
                    oder verwenden Sie das Menue oben links
                  </p>
                </div>
              </Panel>
            )}
          </ReactFlow>
        </div>

        {/* Status Bar */}
        <div className="flex items-center justify-between border-t bg-muted/30 px-4 py-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span>{nodes.length} Knoten</span>
            <span>{edges.length} Verbindungen</span>
            {selectedNode && <span>1 ausgewaehlt</span>}
          </div>
          {workflow && (
            <div className="flex items-center gap-4">
              <span>Ausfuehrungen: {workflow.execution_count}</span>
              {workflow.last_executed_at && (
                <span>
                  Letzte: {new Date(workflow.last_executed_at).toLocaleString('de-DE')}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Node Config Panel */}
      {showConfigPanel && (
        <NodeConfigPanel
          selectedNode={selectedNode}
          onNodeUpdate={handleNodeUpdate}
          onClose={() => setShowConfigPanel(false)}
          disabled={readOnly}
          className="shrink-0"
        />
      )}

      {/* Export Dialog */}
      <Dialog open={showExportDialog} onOpenChange={setShowExportDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Workflow exportieren</DialogTitle>
            <DialogDescription>
              Exportieren Sie den Workflow als JSON-Datei
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={exportWorkflow}
            readOnly
            rows={15}
            className="font-mono text-xs"
          />
          <DialogFooter>
            <Button variant="outline" onClick={handleCopyToClipboard}>
              <Copy className="mr-2 h-4 w-4" />
              Kopieren
            </Button>
            <Button onClick={handleExport}>
              <Download className="mr-2 h-4 w-4" />
              Herunterladen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import Dialog */}
      <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Workflow importieren</DialogTitle>
            <DialogDescription>
              Fuegen Sie JSON-Daten ein oder laden Sie eine Datei
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleFileImport}
                className="hidden"
              />
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                className="w-full"
              >
                <Upload className="mr-2 h-4 w-4" />
                JSON-Datei waehlen
              </Button>
            </div>
            <div className="relative">
              <div className="absolute inset-x-0 top-1/2 flex items-center">
                <Separator className="flex-1" />
                <span className="px-2 text-xs text-muted-foreground">oder</span>
                <Separator className="flex-1" />
              </div>
            </div>
            <Textarea
              value={importJson}
              onChange={(e) => setImportJson(e.target.value)}
              placeholder="JSON hier einfuegen..."
              rows={10}
              className="mt-4 font-mono text-xs"
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowImportDialog(false);
                setImportJson('');
              }}
            >
              Abbrechen
            </Button>
            <Button onClick={handleImport} disabled={!importJson.trim()}>
              <Upload className="mr-2 h-4 w-4" />
              Importieren
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ==================== Main Component ====================

export function WorkflowBuilderEnhanced(props: WorkflowBuilderEnhancedProps) {
  return (
    <ReactFlowProvider>
      <WorkflowBuilderInner {...props} />
    </ReactFlowProvider>
  );
}

export default WorkflowBuilderEnhanced;
