import { useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
    ReactFlow,
    MiniMap,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    addEdge,
    type Node,
    type NodeProps,
    type Edge,
    type Connection,
    BackgroundVariant,
    Handle,
    Position
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Zap, GitBranch, Play, Save } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { automationService, type AutomationRule } from '@/lib/api/services/automation';

interface RuleNodeData extends Record<string, unknown> {
    label?: string;
    config?: {
        event?: string;
        field?: string;
        action?: string;
    };
}

const TriggerNode = ({ data, selected }: NodeProps<Node<RuleNodeData>>) => (
    <div className={cn("p-4 rounded-xl border-2 bg-card min-w-[250px] shadow-sm transition-all", selected ? "border-primary ring-2 ring-primary/20" : "border-border")}>
        <Handle type="source" position={Position.Bottom} className="w-3 h-3 bg-primary border-2 border-background" />
        <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-500">
                <Zap className="w-5 h-5" />
            </div>
            <div>
                <span className="font-display font-semibold block text-sm">Trigger</span>
                <span className="text-xs text-muted-foreground">Startet den Workflow</span>
            </div>
        </div>
        <Select defaultValue={data.config?.event || "document_uploaded"}>
            <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Event wählen" />
            </SelectTrigger>
            <SelectContent>
                <SelectItem value="document_uploaded">Dokument hochgeladen</SelectItem>
                <SelectItem value="ocr_completed">OCR abgeschlossen</SelectItem>
                <SelectItem value="schedule">Zeitplan</SelectItem>
            </SelectContent>
        </Select>
    </div>
);

const ConditionNode = ({ data, selected }: NodeProps<Node<RuleNodeData>>) => (
    <div className={cn("p-4 rounded-xl border-2 bg-card min-w-[250px] shadow-sm transition-all", selected ? "border-primary ring-2 ring-primary/20" : "border-border")}>
        <Handle type="target" position={Position.Top} className="w-3 h-3 bg-muted-foreground border-2 border-background" />
        <Handle type="source" position={Position.Bottom} className="w-3 h-3 bg-primary border-2 border-background" />
        <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-500">
                <GitBranch className="w-5 h-5" />
            </div>
            <div>
                <span className="font-display font-semibold block text-sm">Bedingung</span>
                <span className="text-xs text-muted-foreground">Prüft Kriterien</span>
            </div>
        </div>
        <Select defaultValue={data.config?.field || "ocr_confidence"}>
            <SelectTrigger className="h-8 text-xs mb-2">
                <SelectValue placeholder="Feld wählen" />
            </SelectTrigger>
            <SelectContent>
                <SelectItem value="ocr_confidence">OCR Konfidenz</SelectItem>
                <SelectItem value="document_type">Dokumententyp</SelectItem>
                <SelectItem value="file_size">Dateigröße</SelectItem>
            </SelectContent>
        </Select>
        <div className="flex gap-2">
            <Select defaultValue="gt">
                <SelectTrigger className="h-8 text-xs w-20">
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="gt">&gt;</SelectItem>
                    <SelectItem value="lt">&lt;</SelectItem>
                    <SelectItem value="eq">=</SelectItem>
                </SelectContent>
            </Select>
            <input
                type="text"
                className="flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="Wert"
                defaultValue="80"
            />
        </div>
    </div>
);

const ActionNode = ({ data, selected }: NodeProps<Node<RuleNodeData>>) => (
    <div className={cn("p-4 rounded-xl border-2 bg-card min-w-[250px] shadow-sm transition-all", selected ? "border-primary ring-2 ring-primary/20" : "border-border")}>
        <Handle type="target" position={Position.Top} className="w-3 h-3 bg-muted-foreground border-2 border-background" />
        <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-green-500/10 text-green-500">
                <Play className="w-5 h-5" />
            </div>
            <div>
                <span className="font-display font-semibold block text-sm">Aktion</span>
                <span className="text-xs text-muted-foreground">Führt Aufgabe aus</span>
            </div>
        </div>
        <Select defaultValue={data.config?.action || "move_file"}>
            <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Aktion wählen" />
            </SelectTrigger>
            <SelectContent>
                <SelectItem value="move_file">Datei verschieben</SelectItem>
                <SelectItem value="send_email">E-Mail senden</SelectItem>
                <SelectItem value="webhook">Webhook aufrufen</SelectItem>
            </SelectContent>
        </Select>
    </div>
);

const nodeTypes = {
    trigger: TriggerNode,
    condition: ConditionNode,
    action: ActionNode
};

const initialNodes: Node[] = [
    { id: '1', type: 'trigger', position: { x: 250, y: 0 }, data: { label: 'Start' } },
    { id: '2', type: 'condition', position: { x: 250, y: 150 }, data: { label: 'Check Confidence' } },
    { id: '3', type: 'action', position: { x: 250, y: 350 }, data: { label: 'Move to Archive' } },
];

const initialEdges: Edge[] = [
    { id: 'e1-2', source: '1', target: '2', animated: true, style: { stroke: 'var(--primary)' } },
    { id: 'e2-3', source: '2', target: '3', animated: true, style: { stroke: 'var(--primary)' } },
];

export function RuleBuilder() {
    const [nodes, , onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    // Fetch existing rules (prefetching for future use)
    useQuery({
        queryKey: ['rules'],
        queryFn: automationService.getAllRules
    });

    const saveMutation = useMutation({
        mutationFn: (ruleData: Omit<AutomationRule, 'id' | 'createdAt' | 'updatedAt'>) => automationService.createRule(ruleData),
        onSuccess: () => {
            // Success feedback handled by UI
        }
    });

    const onConnect = useCallback((params: Connection) => {
        setEdges((eds) => addEdge({ ...params, animated: true, style: { stroke: 'var(--primary)' } }, eds));
    }, [setEdges]);

    const onSave = () => {
        saveMutation.mutate({
            name: 'New Rule',
            enabled: true,
            nodes,
            edges
        });
    };

    const onDragStart = (event: React.DragEvent, nodeType: string) => {
        event.dataTransfer.setData('application/reactflow', nodeType);
        event.dataTransfer.effectAllowed = 'move';
    };

    return (
        <div className="flex h-[600px] border rounded-xl overflow-hidden bg-background">
            {/* Sidebar Palette */}
            <div className="w-64 border-r bg-muted/30 p-4 flex flex-col gap-4">
                <div>
                    <h3 className="font-display font-semibold mb-1">Bausteine</h3>
                    <p className="text-xs text-muted-foreground">Ziehen Sie Elemente auf die Fläche</p>
                </div>

                <div className="space-y-2">
                    <div
                        className="p-3 bg-card border rounded-lg cursor-grab active:cursor-grabbing hover:border-primary transition-colors flex items-center gap-3 shadow-sm"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'trigger')}
                    >
                        <div className="p-1.5 rounded bg-amber-500/10 text-amber-500"><Zap className="w-4 h-4" /></div>
                        <span className="text-sm font-medium">Trigger</span>
                    </div>
                    <div
                        className="p-3 bg-card border rounded-lg cursor-grab active:cursor-grabbing hover:border-primary transition-colors flex items-center gap-3 shadow-sm"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'condition')}
                    >
                        <div className="p-1.5 rounded bg-blue-500/10 text-blue-500"><GitBranch className="w-4 h-4" /></div>
                        <span className="text-sm font-medium">Bedingung</span>
                    </div>
                    <div
                        className="p-3 bg-card border rounded-lg cursor-grab active:cursor-grabbing hover:border-primary transition-colors flex items-center gap-3 shadow-sm"
                        draggable
                        onDragStart={(e) => onDragStart(e, 'action')}
                    >
                        <div className="p-1.5 rounded bg-green-500/10 text-green-500"><Play className="w-4 h-4" /></div>
                        <span className="text-sm font-medium">Aktion</span>
                    </div>
                </div>

                <div className="mt-auto">
                    <Button className="w-full gap-2" onClick={onSave} disabled={saveMutation.isPending}>
                        {saveMutation.isPending ? 'Speichern...' : (
                            <>
                                <Save className="w-4 h-4" /> Regel speichern
                            </>
                        )}
                    </Button>
                </div>
            </div>

            {/* Canvas */}
            <div className="flex-1 h-full relative">
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    nodeTypes={nodeTypes}
                    fitView
                    className="bg-muted/5"
                >
                    <Background color="var(--muted-foreground)" gap={20} size={1} variant={BackgroundVariant.Dots} />
                    <Controls className="bg-card border shadow-sm" />
                    <MiniMap className="bg-card border shadow-sm" nodeColor="var(--primary)" />
                </ReactFlow>
            </div>
        </div>
    );
}
