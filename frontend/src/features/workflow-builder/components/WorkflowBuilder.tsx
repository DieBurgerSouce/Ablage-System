import { useState, useRef, useCallback, type DragEvent } from 'react';
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
import {
  Workflow,
  Plus,
  Play,
  Save,
  Trash2,
  Settings,
  Boxes,
  AlertTriangle,
  CheckCircle,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { useToast } from '@/hooks/use-toast';
import { emitChecklistComplete } from '@/features/product-tour/hooks/use-checklist-events';
import WorkflowBlockNode from './WorkflowBlockNode';
import {
  useWorkflowBlocks,
  useWorkflowCategories,
  useWorkflowTemplates,
  useCreateWorkflow,
  useSimulateWorkflow,
  type BlockDefinition,
  type VisualBlock,
  type VisualEdge,
} from '../api/workflow-builder-api';

/**
 * Vordefinierte Node-Typen fuer den Visual Workflow Builder.
 * Diese erweitern die vom Backend geladenen Block-Definitionen
 * um spezialisierte Konfigurationsfelder.
 */

/** Konfigurationsfelder pro Node-Typ */
interface NodeTypeConfig {
  type: string;
  label: string;
  category: string;
  icon: string;
  description: string;
  configFields: Array<{
    key: string;
    label: string;
    type: 'text' | 'number' | 'select' | 'boolean' | 'cron';
    options?: string[];
    defaultValue?: string | number | boolean;
    required?: boolean;
  }>;
}

const WORKFLOW_NODE_TYPES: NodeTypeConfig[] = [
  {
    type: 'approval',
    label: 'Genehmigung',
    category: 'Aktionen',
    icon: 'CheckCircle',
    description: 'Genehmigungs-Schritt mit Zuweisung und Eskalation',
    configFields: [
      { key: 'assignee_role', label: 'Genehmiger-Rolle', type: 'select', options: ['manager', 'finance', 'admin', 'custom'], required: true },
      { key: 'assignee_id', label: 'Genehmiger (optional)', type: 'text' },
      { key: 'deadline_hours', label: 'Frist (Stunden)', type: 'number', defaultValue: 48 },
      { key: 'escalation_after_hours', label: 'Eskalation nach (Stunden)', type: 'number', defaultValue: 72 },
      { key: 'auto_approve_below', label: 'Auto-Genehmigung unter Betrag', type: 'number', defaultValue: 0 },
    ],
  },
  {
    type: 'timer',
    label: 'Warte-Schritt',
    category: 'Steuerung',
    icon: 'Clock',
    description: 'Wartezeit oder Zeitplan-basierter Trigger',
    configFields: [
      { key: 'wait_type', label: 'Warte-Typ', type: 'select', options: ['duration', 'cron', 'date'], defaultValue: 'duration', required: true },
      { key: 'duration_minutes', label: 'Dauer (Minuten)', type: 'number', defaultValue: 60 },
      { key: 'cron_expression', label: 'Cron-Ausdruck', type: 'cron' },
      { key: 'skip_weekends', label: 'Wochenenden ueberspringen', type: 'boolean', defaultValue: false },
    ],
  },
  {
    type: 'condition',
    label: 'Bedingung',
    category: 'Steuerung',
    icon: 'GitBranch',
    description: 'If/Else Verzweigung basierend auf Dokumentfeldern',
    configFields: [
      { key: 'field', label: 'Feld', type: 'select', options: ['amount', 'document_type', 'category', 'risk_score', 'confidence', 'entity_name'], required: true },
      { key: 'operator', label: 'Operator', type: 'select', options: ['equals', 'not_equals', 'greater_than', 'less_than', 'contains', 'in_list'], required: true },
      { key: 'value', label: 'Wert', type: 'text', required: true },
    ],
  },
  {
    type: 'notification',
    label: 'Benachrichtigung',
    category: 'Aktionen',
    icon: 'Bell',
    description: 'Benachrichtigung per E-Mail, Slack oder Push',
    configFields: [
      { key: 'channel', label: 'Kanal', type: 'select', options: ['email', 'slack', 'push', 'all'], defaultValue: 'email', required: true },
      { key: 'template', label: 'Vorlage', type: 'select', options: ['approval_request', 'deadline_reminder', 'status_update', 'custom'] },
      { key: 'recipient_type', label: 'Empfaenger-Typ', type: 'select', options: ['user', 'role', 'group', 'document_owner'], defaultValue: 'document_owner' },
      { key: 'recipient_id', label: 'Empfaenger-ID (optional)', type: 'text' },
      { key: 'custom_message', label: 'Nachricht (optional)', type: 'text' },
    ],
  },
  {
    type: 'pipeline',
    label: 'Pipeline-Trigger',
    category: 'Integration',
    icon: 'Workflow',
    description: 'Startet die Verarbeitungs-Pipeline (Kontierung + Matching)',
    configFields: [
      { key: 'skip_kontierung', label: 'Kontierung ueberspringen', type: 'boolean', defaultValue: false },
      { key: 'skip_matching', label: 'Matching ueberspringen', type: 'boolean', defaultValue: false },
      { key: 'document_type_filter', label: 'Nur fuer Dokumenttypen', type: 'select', options: ['all', 'invoice', 'order', 'delivery_note', 'offer'], defaultValue: 'all' },
    ],
  },
];

// ==================== ReactFlow Node Type Registry ====================

const workflowNodeTypes = { workflowBlock: WorkflowBlockNode };

// ==================== Conversion Helpers ====================

interface WorkflowBlockData {
  label: string;
  type: string;
  config: Record<string, unknown>;
  definition: BlockDefinition;
}

function toRfEdge(edge: VisualEdge): Edge {
  return {
    id: edge.id,
    source: edge.source_id,
    target: edge.target_id,
    sourceHandle: edge.source_handle || undefined,
    targetHandle: edge.target_handle || undefined,
    type: 'smoothstep',
    animated: true,
    label: edge.label,
  };
}

function toVisualEdge(edge: Edge): VisualEdge {
  return {
    id: edge.id,
    source_id: edge.source,
    target_id: edge.target,
    source_handle: edge.sourceHandle || '',
    target_handle: edge.targetHandle || '',
    label: typeof edge.label === 'string' ? edge.label : undefined,
  };
}

// ==================== Inner Component (uses useReactFlow) ====================

function WorkflowBuilderInner() {
  const { toast } = useToast();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useReactFlow();

  const [workflowName, setWorkflowName] = useState('Neuer Workflow');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowBlockData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const { data: categories, isLoading: categoriesLoading } = useWorkflowCategories();
  const { data: blocks, isLoading: blocksLoading } = useWorkflowBlocks(
    selectedCategory === 'all' ? undefined : selectedCategory
  );
  const { data: templates, isLoading: templatesLoading } = useWorkflowTemplates();
  const createWorkflow = useCreateWorkflow();
  const simulateWorkflow = useSimulateWorkflow();

  const selectedNode = selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) : null;

  // ==================== Drag & Drop from Palette ====================

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();

      const blockData = event.dataTransfer.getData('application/reactflow');
      if (!blockData) return;

      const blockDef: BlockDefinition = JSON.parse(blockData);
      const bounds = reactFlowWrapper.current?.getBoundingClientRect();
      if (!bounds) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      });

      const newNode: Node<WorkflowBlockData> = {
        id: `block-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        type: 'workflowBlock',
        position,
        data: {
          label: blockDef.label,
          type: blockDef.type,
          config: {},
          definition: blockDef,
        },
      };

      setNodes((nds) => [...nds, newNode]);
      toast({
        title: 'Block hinzugefuegt',
        description: `${blockDef.label} wurde zur Canvas hinzugefuegt`,
      });
    },
    [reactFlowInstance, setNodes, toast]
  );

  // ==================== Click to Add (Fallback) ====================

  const addBlockToCanvas = useCallback(
    (blockDef: BlockDefinition) => {
      const newNode: Node<WorkflowBlockData> = {
        id: `block-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        type: 'workflowBlock',
        position: { x: 100 + nodes.length * 50, y: 100 + nodes.length * 30 },
        data: {
          label: blockDef.label,
          type: blockDef.type,
          config: {},
          definition: blockDef,
        },
      };
      setNodes((nds) => [...nds, newNode]);
      toast({
        title: 'Block hinzugefuegt',
        description: `${blockDef.label} wurde zur Canvas hinzugefuegt`,
      });
    },
    [nodes.length, setNodes, toast]
  );

  // ==================== Connection Handling ====================

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `e-${connection.source}-${connection.target}-${Date.now()}`,
            type: 'smoothstep',
            animated: true,
          },
          eds
        )
      );
    },
    [setEdges]
  );

  // ==================== Selection ====================

  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }: { nodes: Node[] }) => {
      if (selectedNodes.length === 1) {
        setSelectedNodeId(selectedNodes[0].id);
      } else {
        setSelectedNodeId(null);
      }
    },
    []
  );

  // ==================== Block Config Updates ====================

  const updateBlockConfig = useCallback(
    (nodeId: string, key: string, value: unknown) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? { ...n, data: { ...n.data, config: { ...n.data.config, [key]: value } } }
            : n
        )
      );
    },
    [setNodes]
  );

  const removeSelectedBlock = useCallback(() => {
    if (!selectedNodeId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
    setEdges((eds) =>
      eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId)
    );
    setSelectedNodeId(null);
    toast({
      title: 'Block entfernt',
      description: 'Der Block wurde von der Canvas entfernt',
    });
  }, [selectedNodeId, setNodes, setEdges, toast]);

  // ==================== Save ====================

  const handleSave = useCallback(async () => {
    if (!workflowName.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Workflow-Namen ein',
        variant: 'destructive',
      });
      return;
    }

    const visualBlocks: VisualBlock[] = nodes.map((n) => ({
      id: n.id,
      type: n.data.type,
      label: n.data.label,
      config: n.data.config,
      position_x: n.position.x,
      position_y: n.position.y,
    }));

    try {
      const result = await createWorkflow.mutateAsync({
        name: workflowName,
        description: workflowDescription,
        blocks: visualBlocks,
        edges: edges.map(toVisualEdge),
      });

      toast({
        title: 'Workflow gespeichert',
        description: result.message,
      });

      emitChecklistComplete('create_workflow');

      if (result.validation_errors && result.validation_errors.length > 0) {
        toast({
          title: 'Validierungswarnungen',
          description: result.validation_errors.join(', '),
          variant: 'default',
        });
      }
    } catch (error) {
      toast({
        title: 'Fehler beim Speichern',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  }, [workflowName, workflowDescription, nodes, edges, createWorkflow, toast]);

  // ==================== Simulate ====================

  const handleSimulate = useCallback(async () => {
    if (nodes.length === 0) {
      toast({
        title: 'Fehler',
        description: 'Bitte fuegen Sie mindestens einen Block hinzu',
        variant: 'destructive',
      });
      return;
    }

    const visualBlocks: VisualBlock[] = nodes.map((n) => ({
      id: n.id,
      type: n.data.type,
      label: n.data.label,
      config: n.data.config,
      position_x: n.position.x,
      position_y: n.position.y,
    }));

    try {
      const result = await simulateWorkflow.mutateAsync({
        blocks: visualBlocks,
        edges: edges.map(toVisualEdge),
      });

      toast({
        title: result.success ? 'Simulation erfolgreich' : 'Simulation fehlgeschlagen',
        description: `Geschaetzte Dauer: ${result.duration_estimate_seconds}s`,
        variant: result.success ? 'default' : 'destructive',
      });

      if (result.warnings && result.warnings.length > 0) {
        console.warn('Simulation warnings:', result.warnings);
      }

      if (result.errors && result.errors.length > 0) {
        console.error('Simulation errors:', result.errors);
      }
    } catch (error) {
      toast({
        title: 'Simulationsfehler',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  }, [nodes, edges, simulateWorkflow, toast]);

  // ==================== Load Template ====================

  const loadTemplate = useCallback(
    (templateId: string) => {
      const template = templates?.find((t) => t.id === templateId);
      if (!template) return;

      const newNodes: Node<WorkflowBlockData>[] = template.blocks
        .map((block) => {
          const definition = blocks?.find((b) => b.type === block.type);
          if (!definition) {
            console.warn(`Block definition not found for type: ${block.type}`);
            return null;
          }
          return {
            id: block.id,
            type: 'workflowBlock' as const,
            position: { x: block.position_x, y: block.position_y },
            data: {
              label: block.label,
              type: block.type,
              config: block.config,
              definition,
            },
          };
        })
        .filter((n): n is Node<WorkflowBlockData> => n !== null);

      setNodes(newNodes);
      setEdges(template.edges.map(toRfEdge));
      setWorkflowName(template.name);
      setWorkflowDescription(template.description);
      setSelectedNodeId(null);

      setTimeout(() => reactFlowInstance.fitView({ padding: 0.2 }), 50);

      toast({
        title: 'Template geladen',
        description: `"${template.name}" wurde geladen`,
      });
    },
    [templates, blocks, setNodes, setEdges, reactFlowInstance, toast]
  );

  // ==================== Render ====================

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-background p-4">
        <div className="flex items-center gap-4">
          <Workflow className="h-6 w-6" />
          <div>
            <Input
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="mb-1 font-semibold"
              placeholder="Workflow-Name"
              aria-label="Workflow-Name"
            />
            <Input
              value={workflowDescription}
              onChange={(e) => setWorkflowDescription(e.target.value)}
              className="text-sm"
              placeholder="Beschreibung (optional)"
              aria-label="Workflow-Beschreibung"
            />
          </div>
        </div>
        <div className="flex items-center gap-2" data-tour="wf-actions">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="sm" aria-label="Templates laden">
                <Boxes className="mr-2 h-4 w-4" />
                Templates
              </Button>
            </SheetTrigger>
            <SheetContent>
              <SheetHeader>
                <SheetTitle>Workflow-Templates</SheetTitle>
              </SheetHeader>
              <ScrollArea className="mt-4 h-[calc(100vh-8rem)]">
                {templatesLoading ? (
                  <div className="space-y-2">
                    {[1, 2, 3].map((i) => (
                      <Skeleton key={i} className="h-20 w-full" />
                    ))}
                  </div>
                ) : !templates || templates.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Keine Templates vorhanden</p>
                ) : (
                  <div className="space-y-2">
                    {templates.map((template) => (
                      <Card
                        key={template.id}
                        className="cursor-pointer hover:bg-accent"
                        onClick={() => loadTemplate(template.id)}
                      >
                        <CardHeader className="p-4">
                          <CardTitle className="text-sm">{template.name}</CardTitle>
                          <CardDescription className="text-xs">
                            {template.description}
                          </CardDescription>
                        </CardHeader>
                      </Card>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </SheetContent>
          </Sheet>
          <Button
            variant="outline"
            size="sm"
            onClick={handleSimulate}
            disabled={simulateWorkflow.isPending}
            aria-label="Workflow simulieren"
          >
            {simulateWorkflow.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Simulieren
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={createWorkflow.isPending}
            aria-label="Workflow speichern"
          >
            {createWorkflow.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Speichern
          </Button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar - Block Palette */}
        <div className="w-64 border-r bg-muted/30" data-tour="wf-palette">
          <div className="p-4">
            <Label htmlFor="category-select" className="text-sm font-medium">
              Kategorie
            </Label>
            <Select value={selectedCategory} onValueChange={setSelectedCategory}>
              <SelectTrigger id="category-select" className="mt-2" aria-label="Kategorie auswaehlen">
                <SelectValue placeholder="Kategorie waehlen" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Kategorien</SelectItem>
                {categoriesLoading ? (
                  <SelectItem value="loading" disabled>
                    Laden...
                  </SelectItem>
                ) : (
                  categories?.map((cat) => (
                    <SelectItem key={cat.id} value={cat.id}>
                      {cat.label}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>
          <Separator />
          <ScrollArea className="h-[calc(100vh-12rem)]">
            <div className="space-y-2 p-4">
              {blocksLoading ? (
                <>
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </>
              ) : !blocks || blocks.length === 0 ? (
                <p className="text-sm text-muted-foreground">Keine Blocks vorhanden</p>
              ) : (
                blocks.map((block) => (
                  <Card
                    key={block.id}
                    className="cursor-grab select-none hover:bg-accent active:cursor-grabbing"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData(
                        'application/reactflow',
                        JSON.stringify(block)
                      );
                      e.dataTransfer.effectAllowed = 'move';
                    }}
                    onClick={() => addBlockToCanvas(block)}
                  >
                    <CardContent className="p-3">
                      <div className="flex items-start gap-2">
                        <div className="text-2xl">{block.icon}</div>
                        <div className="flex-1">
                          <p className="text-sm font-medium">{block.label}</p>
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {block.description}
                          </p>
                        </div>
                        <Plus className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Center - ReactFlow Canvas */}
        <div
          ref={reactFlowWrapper}
          className="flex-1"
          data-tour="wf-canvas"
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
            nodeTypes={workflowNodeTypes}
            connectionLineType={ConnectionLineType.SmoothStep}
            defaultEdgeOptions={{ type: 'smoothstep', animated: true }}
            fitView
            snapToGrid
            snapGrid={[15, 15]}
            deleteKeyCode="Delete"
            className="bg-muted/30"
            aria-label="Workflow-Diagramm"
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls showZoom showFitView />
            <MiniMap
              nodeStrokeWidth={3}
              zoomable
              pannable
              aria-label="Workflow-Minimap"
            />

            {nodes.length === 0 && (
              <Panel position="top-center" className="mt-20">
                <div className="rounded-lg border-2 border-dashed border-muted-foreground/25 bg-background/50 p-8 text-center">
                  <Workflow className="mx-auto h-12 w-12 text-muted-foreground" />
                  <p className="mt-4 text-lg font-medium">Keine Blocks vorhanden</p>
                  <p className="text-sm text-muted-foreground">
                    Ziehen Sie einen Block aus der linken Palette auf die Canvas
                  </p>
                </div>
              </Panel>
            )}
          </ReactFlow>
        </div>

        {/* Right Sidebar - Block Config */}
        {selectedNode && (
          <div className="w-80 border-l bg-muted/30" data-tour="wf-config">
            <div className="p-4">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Settings className="h-5 w-5" />
                  <h3 className="font-semibold">Block-Konfiguration</h3>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                  onClick={removeSelectedBlock}
                  aria-label="Block entfernen"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              <div className="space-y-4">
                <div>
                  <Label className="text-sm font-medium">Typ</Label>
                  <Badge variant="outline" className="mt-1">
                    {selectedNode.data.type}
                  </Badge>
                </div>
                <div>
                  <Label htmlFor="block-label" className="text-sm font-medium">
                    Label
                  </Label>
                  <Input
                    id="block-label"
                    value={selectedNode.data.label}
                    onChange={(e) =>
                      setNodes((nds) =>
                        nds.map((n) =>
                          n.id === selectedNode.id
                            ? { ...n, data: { ...n.data, label: e.target.value } }
                            : n
                        )
                      )
                    }
                    className="mt-1"
                    aria-label="Block-Label"
                  />
                </div>
                <Separator />
                <div>
                  <Label className="text-sm font-medium">Konfiguration</Label>
                  <ScrollArea className="mt-2 h-96">
                    <div className="space-y-3">
                      {Object.keys(selectedNode.data.definition.config_schema).length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Keine Konfigurationsoptionen verfuegbar
                        </p>
                      ) : (
                        Object.entries(selectedNode.data.definition.config_schema).map(
                          ([key, _schema]) => (
                            <div key={key}>
                              <Label htmlFor={`config-${key}`} className="text-sm">
                                {key}
                              </Label>
                              <Input
                                id={`config-${key}`}
                                value={
                                  selectedNode.data.config[key]?.toString() || ''
                                }
                                onChange={(e) =>
                                  updateBlockConfig(selectedNode.id, key, e.target.value)
                                }
                                className="mt-1"
                                placeholder={`${key} eingeben`}
                                aria-label={`Konfiguration: ${key}`}
                              />
                            </div>
                          )
                        )
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bottom Status Bar */}
      {simulateWorkflow.data && (
        <div className="border-t bg-background p-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {simulateWorkflow.data.success ? (
                <CheckCircle className="h-4 w-4 text-green-500" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-yellow-500" />
              )}
              <span className="text-sm">
                Simulationsergebnis: {simulateWorkflow.data.success ? 'Erfolgreich' : 'Warnungen vorhanden'}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>Blocks: {nodes.length}</span>
              <span>Verbindungen: {edges.length}</span>
              <span>Geschaetzte Dauer: {simulateWorkflow.data.duration_estimate_seconds}s</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== Main Component with Provider ====================

export function WorkflowBuilder() {
  return (
    <ReactFlowProvider>
      <WorkflowBuilderInner />
    </ReactFlowProvider>
  );
}
