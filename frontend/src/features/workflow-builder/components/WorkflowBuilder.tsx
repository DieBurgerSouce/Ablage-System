import { useState, useRef, useCallback } from 'react';
import {
  Workflow,
  Plus,
  Play,
  Save,
  Trash2,
  Settings,
  Boxes,
  ChevronRight,
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

interface CanvasBlock extends VisualBlock {
  definition: BlockDefinition;
}

export function WorkflowBuilder() {
  const { toast } = useToast();
  const [workflowName, setWorkflowName] = useState('Neuer Workflow');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [canvasBlocks, setCanvasBlocks] = useState<CanvasBlock[]>([]);
  const [edges, setEdges] = useState<VisualEdge[]>([]);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<{
    blockId: string;
    handleId: string;
  } | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const { data: categories, isLoading: categoriesLoading } = useWorkflowCategories();
  const { data: blocks, isLoading: blocksLoading } = useWorkflowBlocks(
    selectedCategory === 'all' ? undefined : selectedCategory
  );
  const { data: templates, isLoading: templatesLoading } = useWorkflowTemplates();
  const createWorkflow = useCreateWorkflow();
  const simulateWorkflow = useSimulateWorkflow();

  const selectedBlock = canvasBlocks.find((b) => b.id === selectedBlockId);

  const addBlockToCanvas = useCallback((blockDef: BlockDefinition) => {
    const newBlock: CanvasBlock = {
      id: `block-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type: blockDef.type,
      label: blockDef.label,
      config: {},
      position_x: 100 + canvasBlocks.length * 50,
      position_y: 100 + canvasBlocks.length * 30,
      definition: blockDef,
    };
    setCanvasBlocks((prev) => [...prev, newBlock]);
    toast({
      title: 'Block hinzugefügt',
      description: `${blockDef.label} wurde zur Canvas hinzugefügt`,
    });
  }, [canvasBlocks.length, toast]);

  const removeBlock = useCallback((blockId: string) => {
    setCanvasBlocks((prev) => prev.filter((b) => b.id !== blockId));
    setEdges((prev) =>
      prev.filter((e) => e.source_id !== blockId && e.target_id !== blockId)
    );
    if (selectedBlockId === blockId) {
      setSelectedBlockId(null);
    }
    toast({
      title: 'Block entfernt',
      description: 'Der Block wurde von der Canvas entfernt',
    });
  }, [selectedBlockId, toast]);

  const handleOutputClick = useCallback((blockId: string, handleId: string) => {
    if (connectingFrom) {
      // Complete connection
      if (connectingFrom.blockId !== blockId) {
        const newEdge: VisualEdge = {
          id: `edge-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          source_id: connectingFrom.blockId,
          target_id: blockId,
          source_handle: connectingFrom.handleId,
          target_handle: handleId,
        };
        setEdges((prev) => [...prev, newEdge]);
        toast({
          title: 'Verbindung erstellt',
          description: 'Blocks wurden erfolgreich verbunden',
        });
      }
      setConnectingFrom(null);
    } else {
      // Start connection
      setConnectingFrom({ blockId, handleId });
    }
  }, [connectingFrom, toast]);

  const updateBlockConfig = useCallback((blockId: string, key: string, value: unknown) => {
    setCanvasBlocks((prev) =>
      prev.map((block) =>
        block.id === blockId
          ? { ...block, config: { ...block.config, [key]: value } }
          : block
      )
    );
  }, []);

  const handleSave = useCallback(async () => {
    if (!workflowName.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Workflow-Namen ein',
        variant: 'destructive',
      });
      return;
    }

    try {
      const result = await createWorkflow.mutateAsync({
        name: workflowName,
        description: workflowDescription,
        blocks: canvasBlocks.map(({ definition, ...block }) => block),
        edges,
      });

      toast({
        title: 'Workflow gespeichert',
        description: result.message,
      });

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
  }, [workflowName, workflowDescription, canvasBlocks, edges, createWorkflow, toast]);

  const handleSimulate = useCallback(async () => {
    if (canvasBlocks.length === 0) {
      toast({
        title: 'Fehler',
        description: 'Bitte fügen Sie mindestens einen Block hinzu',
        variant: 'destructive',
      });
      return;
    }

    try {
      const result = await simulateWorkflow.mutateAsync({
        blocks: canvasBlocks.map(({ definition, ...block }) => block),
        edges,
      });

      toast({
        title: result.success ? 'Simulation erfolgreich' : 'Simulation fehlgeschlagen',
        description: `Geschätzte Dauer: ${result.duration_estimate_seconds}s`,
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
  }, [canvasBlocks, edges, simulateWorkflow, toast]);

  const loadTemplate = useCallback((templateId: string) => {
    const template = templates?.find((t) => t.id === templateId);
    if (!template) return;

    const blocksWithDefs = template.blocks.map((block) => {
      const definition = blocks?.find((b) => b.type === block.type);
      if (!definition) {
        console.warn(`Block definition not found for type: ${block.type}`);
        return null;
      }
      return { ...block, definition };
    }).filter((b): b is CanvasBlock => b !== null);

    setCanvasBlocks(blocksWithDefs);
    setEdges(template.edges);
    setWorkflowName(template.name);
    setWorkflowDescription(template.description);
    toast({
      title: 'Template geladen',
      description: `"${template.name}" wurde geladen`,
    });
  }, [templates, blocks, toast]);

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
        <div className="flex items-center gap-2">
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
        <div className="w-64 border-r bg-muted/30">
          <div className="p-4">
            <Label htmlFor="category-select" className="text-sm font-medium">
              Kategorie
            </Label>
            <Select value={selectedCategory} onValueChange={setSelectedCategory}>
              <SelectTrigger id="category-select" className="mt-2" aria-label="Kategorie auswählen">
                <SelectValue placeholder="Kategorie wählen" />
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
                    className="cursor-pointer hover:bg-accent"
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

        {/* Center - Canvas */}
        <div className="flex-1 overflow-auto bg-grid-pattern" ref={canvasRef}>
          <div className="relative min-h-full min-w-full p-8">
            {canvasBlocks.length === 0 ? (
              <div className="flex h-96 items-center justify-center">
                <div className="text-center">
                  <Workflow className="mx-auto h-12 w-12 text-muted-foreground" />
                  <p className="mt-4 text-lg font-medium">Keine Blocks vorhanden</p>
                  <p className="text-sm text-muted-foreground">
                    Wählen Sie einen Block aus der linken Palette
                  </p>
                </div>
              </div>
            ) : (
              <>
                {/* Render edges as SVG lines */}
                <svg className="pointer-events-none absolute inset-0 h-full w-full">
                  {edges.map((edge) => {
                    const sourceBlock = canvasBlocks.find((b) => b.id === edge.source_id);
                    const targetBlock = canvasBlocks.find((b) => b.id === edge.target_id);
                    if (!sourceBlock || !targetBlock) return null;

                    const x1 = sourceBlock.position_x + 200;
                    const y1 = sourceBlock.position_y + 40;
                    const x2 = targetBlock.position_x;
                    const y2 = targetBlock.position_y + 40;

                    return (
                      <line
                        key={edge.id}
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke="hsl(var(--primary))"
                        strokeWidth="2"
                        markerEnd="url(#arrowhead)"
                      />
                    );
                  })}
                  <defs>
                    <marker
                      id="arrowhead"
                      markerWidth="10"
                      markerHeight="10"
                      refX="8"
                      refY="3"
                      orient="auto"
                    >
                      <polygon
                        points="0 0, 10 3, 0 6"
                        fill="hsl(var(--primary))"
                      />
                    </marker>
                  </defs>
                </svg>

                {/* Render blocks */}
                {canvasBlocks.map((block) => (
                  <div
                    key={block.id}
                    className="absolute"
                    style={{
                      left: `${block.position_x}px`,
                      top: `${block.position_y}px`,
                    }}
                    draggable
                    onDragEnd={(e) => {
                      const rect = canvasRef.current?.getBoundingClientRect();
                      if (rect) {
                        const newX = e.clientX - rect.left;
                        const newY = e.clientY - rect.top;
                        setCanvasBlocks((prev) =>
                          prev.map((b) =>
                            b.id === block.id
                              ? { ...b, position_x: newX, position_y: newY }
                              : b
                          )
                        );
                      }
                    }}
                  >
                    <Card
                      className={`w-48 cursor-move ${
                        selectedBlockId === block.id ? 'ring-2 ring-primary' : ''
                      }`}
                      onClick={() => setSelectedBlockId(block.id)}
                    >
                      <CardHeader className="p-3">
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-lg">{block.definition.icon}</span>
                            <CardTitle className="text-sm">{block.label}</CardTitle>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={(e) => {
                              e.stopPropagation();
                              removeBlock(block.id);
                            }}
                            aria-label="Block entfernen"
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent className="p-3 pt-0">
                        {/* Input handles */}
                        {block.definition.inputs.length > 0 && (
                          <div className="mb-2 space-y-1">
                            {block.definition.inputs.map((input) => (
                              <div
                                key={input.id}
                                className="flex items-center gap-1 text-xs"
                              >
                                <div
                                  className="h-2 w-2 cursor-pointer rounded-full bg-primary hover:bg-primary/80"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleOutputClick(block.id, input.id);
                                  }}
                                  aria-label={`Input: ${input.label}`}
                                />
                                <span className="text-muted-foreground">{input.label}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Output handles */}
                        {block.definition.outputs.length > 0 && (
                          <div className="space-y-1">
                            {block.definition.outputs.map((output) => (
                              <div
                                key={output.id}
                                className="flex items-center justify-end gap-1 text-xs"
                              >
                                <span className="text-muted-foreground">{output.label}</span>
                                <div
                                  className="h-2 w-2 cursor-pointer rounded-full bg-primary hover:bg-primary/80"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleOutputClick(block.id, output.id);
                                  }}
                                  aria-label={`Output: ${output.label}`}
                                />
                              </div>
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Right Sidebar - Block Config */}
        {selectedBlock && (
          <div className="w-80 border-l bg-muted/30">
            <div className="p-4">
              <div className="mb-4 flex items-center gap-2">
                <Settings className="h-5 w-5" />
                <h3 className="font-semibold">Block-Konfiguration</h3>
              </div>
              <div className="space-y-4">
                <div>
                  <Label className="text-sm font-medium">Typ</Label>
                  <Badge variant="outline" className="mt-1">
                    {selectedBlock.type}
                  </Badge>
                </div>
                <div>
                  <Label htmlFor="block-label" className="text-sm font-medium">
                    Label
                  </Label>
                  <Input
                    id="block-label"
                    value={selectedBlock.label}
                    onChange={(e) =>
                      setCanvasBlocks((prev) =>
                        prev.map((b) =>
                          b.id === selectedBlock.id ? { ...b, label: e.target.value } : b
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
                      {Object.keys(selectedBlock.definition.config_schema).length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Keine Konfigurationsoptionen verfügbar
                        </p>
                      ) : (
                        Object.entries(selectedBlock.definition.config_schema).map(
                          ([key, schema]) => (
                            <div key={key}>
                              <Label htmlFor={`config-${key}`} className="text-sm">
                                {key}
                              </Label>
                              <Input
                                id={`config-${key}`}
                                value={
                                  selectedBlock.config[key]?.toString() || ''
                                }
                                onChange={(e) =>
                                  updateBlockConfig(selectedBlock.id, key, e.target.value)
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
              <span>Blocks: {canvasBlocks.length}</span>
              <span>Verbindungen: {edges.length}</span>
              <span>Geschätzte Dauer: {simulateWorkflow.data.duration_estimate_seconds}s</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
