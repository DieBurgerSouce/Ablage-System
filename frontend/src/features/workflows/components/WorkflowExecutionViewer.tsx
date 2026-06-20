/**
 * Workflow Execution Viewer
 *
 * Echtzeit-Visualisierung einer Workflow-Ausführung.
 * Zeigt Knoten mit farbcodierten Status und animierten Kanten.
 */

import { useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  type Node,
  type Edge,
  BackgroundVariant,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Loader2, CheckCircle, XCircle, AlertTriangle, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useExecutionState } from '../hooks/useWorkflowExecution';
import { useWorkflow } from '../hooks/useWorkflows';
import type { NodeExecutionStatus } from '../types/workflow-types';

interface WorkflowExecutionViewerProps {
  executionId: string;
}

const statusColors: Record<NodeExecutionStatus, string> = {
  pending: 'bg-muted border-muted-foreground',
  active: 'bg-blue-100 border-blue-500 animate-pulse',
  completed: 'bg-green-100 border-green-500',
  failed: 'bg-red-100 border-red-500',
  skipped: 'bg-gray-50 border-gray-300 opacity-50',
  warning: 'bg-yellow-100 border-yellow-500',
};

const statusIcons: Record<NodeExecutionStatus, React.ElementType> = {
  pending: Clock,
  active: Loader2,
  completed: CheckCircle,
  failed: XCircle,
  skipped: Clock,
  warning: AlertTriangle,
};

const statusLabels: Record<NodeExecutionStatus, string> = {
  pending: 'Ausstehend',
  active: 'Aktiv',
  completed: 'Abgeschlossen',
  failed: 'Fehlgeschlagen',
  skipped: 'Übersprungen',
  warning: 'Warnung',
};

function formatDuration(durationMs?: number | null): string {
  if (!durationMs) return '-';
  if (durationMs < 1000) return `${durationMs}ms`;
  if (durationMs < 60000) return `${(durationMs / 1000).toFixed(1)}s`;
  return `${(durationMs / 60000).toFixed(1)}min`;
}

export default function WorkflowExecutionViewer({
  executionId,
}: WorkflowExecutionViewerProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Lade Execution State
  const { data: executionState, isLoading: stateLoading } = useExecutionState(executionId);

  // Lade Workflow Definition
  const { data: workflow, isLoading: workflowLoading } = useWorkflow(
    executionState?.workflow_id || '',
    !!executionState?.workflow_id
  );

  const isLoading = stateLoading || workflowLoading;

  // Erstelle React Flow Nodes mit Status-Farben
  const nodes: Node[] = useMemo(() => {
    if (!workflow || !executionState) return [];

    return workflow.nodes.map((node) => {
      const nodeState = executionState.nodes.find((n) => n.node_id === node.id);
      const status = nodeState?.status || 'pending';
      const StatusIcon = statusIcons[status];

      return {
        id: node.id,
        type: node.type,
        position: node.position,
        data: {
          ...node.data,
          label: (
            <div className={cn('p-3 rounded-lg border-2', statusColors[status])}>
              <div className="flex items-center gap-2">
                <StatusIcon
                  className={cn('h-4 w-4', status === 'active' && 'animate-spin')}
                />
                <span className="font-medium">{typeof node.data.label === 'string' ? node.data.label : 'Unbenannt'}</span>
              </div>
              {nodeState?.duration_ms && (
                <div className="text-xs mt-1 text-muted-foreground">
                  {formatDuration(nodeState.duration_ms)}
                </div>
              )}
            </div>
          ),
          isExecuting: status === 'active',
          executionStatus: status,
        },
        draggable: false,
        selectable: true,
      };
    });
  }, [workflow, executionState]);

  // Erstelle React Flow Edges
  const edges: Edge[] = useMemo(() => {
    if (!workflow) return [];
    return workflow.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      label: edge.label,
      animated: executionState?.active_step_ids.includes(edge.target) || false,
    }));
  }, [workflow, executionState]);

  const selectedNode = useMemo(() => {
    if (!selectedNodeId || !executionState) return null;
    return executionState.nodes.find((n) => n.node_id === selectedNodeId);
  }, [selectedNodeId, executionState]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-8 w-64" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[600px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!executionState || !workflow) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-destructive" />
          <p className="mt-4 text-lg font-medium">
            Ausführung nicht gefunden
          </p>
        </CardContent>
      </Card>
    );
  }

  const statusBadgeVariants: Record<string, 'default' | 'secondary' | 'destructive'> = {
    pending: 'secondary',
    running: 'default',
    paused: 'secondary',
    completed: 'default',
    failed: 'destructive',
    cancelled: 'secondary',
    timeout: 'destructive',
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl">{executionState.workflow_name}</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                Ausführungs-ID: {executionState.instance_id}
              </p>
            </div>
            <Badge variant={statusBadgeVariants[executionState.status] || 'secondary'}>
              {executionState.status === 'running' && (
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
              )}
              {executionState.status === 'completed' && (
                <CheckCircle className="mr-2 h-3 w-3" />
              )}
              {executionState.status === 'failed' && (
                <XCircle className="mr-2 h-3 w-3" />
              )}
              {executionState.status === 'running' ? 'Läuft' :
               executionState.status === 'completed' ? 'Abgeschlossen' :
               executionState.status === 'failed' ? 'Fehlgeschlagen' :
               executionState.status === 'paused' ? 'Pausiert' :
               executionState.status === 'cancelled' ? 'Abgebrochen' :
               executionState.status === 'timeout' ? 'Zeitüberschreitung' :
               'Ausstehend'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Fortschritt</span>
              <span className="font-medium">{executionState.progress_percent}%</span>
            </div>
            <Progress value={executionState.progress_percent} />
          </div>
        </CardContent>
      </Card>

      {/* React Flow Canvas */}
      <Card>
        <CardContent className="p-0">
          <div className="h-[600px] w-full">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodeClick={(_, node) => setSelectedNodeId(node.id)}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={true}
            >
              <Background variant={BackgroundVariant.Dots} />
              <Controls />
            </ReactFlow>
          </div>
        </CardContent>
      </Card>

      {/* Node Details Sheet */}
      <Sheet open={!!selectedNodeId} onOpenChange={() => setSelectedNodeId(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Schritt-Details</SheetTitle>
            <SheetDescription>
              Informationen zur Ausführung dieses Schritts
            </SheetDescription>
          </SheetHeader>
          {selectedNode && (
            <div className="mt-6 space-y-4">
              <div>
                <label className="text-sm font-medium">Name</label>
                <p className="text-sm text-muted-foreground">
                  {selectedNode.node_name}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium">Typ</label>
                <p className="text-sm text-muted-foreground">
                  {selectedNode.node_type}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium">Status</label>
                <Badge variant="outline" className="mt-1">
                  {statusLabels[selectedNode.status]}
                </Badge>
              </div>
              {selectedNode.started_at && (
                <div>
                  <label className="text-sm font-medium">Gestartet</label>
                  <p className="text-sm text-muted-foreground">
                    {new Date(selectedNode.started_at).toLocaleString('de-DE')}
                  </p>
                </div>
              )}
              {selectedNode.completed_at && (
                <div>
                  <label className="text-sm font-medium">Abgeschlossen</label>
                  <p className="text-sm text-muted-foreground">
                    {new Date(selectedNode.completed_at).toLocaleString('de-DE')}
                  </p>
                </div>
              )}
              {selectedNode.duration_ms && (
                <div>
                  <label className="text-sm font-medium">Dauer</label>
                  <p className="text-sm text-muted-foreground">
                    {formatDuration(selectedNode.duration_ms)}
                  </p>
                </div>
              )}
              {selectedNode.error_message && (
                <div>
                  <label className="text-sm font-medium text-destructive">
                    Fehlermeldung
                  </label>
                  <p className="text-sm text-destructive mt-1">
                    {selectedNode.error_message}
                  </p>
                </div>
              )}
              {selectedNode.sla_deadline && (
                <div>
                  <label className="text-sm font-medium">SLA Deadline</label>
                  <p className="text-sm text-muted-foreground">
                    {new Date(selectedNode.sla_deadline).toLocaleString('de-DE')}
                  </p>
                  {selectedNode.sla_status && (
                    <Badge
                      variant={selectedNode.sla_status === 'met' ? 'default' : 'destructive'}
                      className="mt-1"
                    >
                      {selectedNode.sla_status === 'met' ? 'Eingehalten' : 'Überschritten'}
                    </Badge>
                  )}
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
