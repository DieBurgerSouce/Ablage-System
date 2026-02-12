/**
 * Workflow Rule Builder Page
 *
 * Admin-Seite für Verwaltung von Workflow-Regeln.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { GitBranch, Plus, RefreshCw, Pencil, Trash2, Loader2, Power, PowerOff } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import {
  listWorkflows,
  createWorkflow,
  updateWorkflow,
  deleteWorkflow,
  toggleWorkflow,
} from '@/features/workflows/api/workflows-api';
import type {
  Workflow,
  WorkflowCreate,
  WorkflowUpdate,
  TriggerType,
} from '@/features/workflows/types/workflow-types';

// Trigger-Type Labels
const TRIGGER_TYPE_LABELS: Record<TriggerType, string> = {
  document_event: 'Dokumenten-Ereignis',
  schedule: 'Zeitplan',
  condition: 'Bedingung',
  manual: 'Manuell',
  webhook: 'Webhook',
};

export function WorkflowRuleBuilder() {
  const queryClient = useQueryClient();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);

  // Load workflows
  const {
    data: workflowsData,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => listWorkflows({}),
  });

  const workflows = workflowsData?.items || [];

  // Create mutation
  const createMutation = useMutation({
    mutationFn: createWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      setIsCreateDialogOpen(false);
      toast.success('Workflow-Regel erfolgreich erstellt');
    },
    onError: () => {
      toast.error('Fehler beim Erstellen der Workflow-Regel');
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: WorkflowUpdate }) =>
      updateWorkflow(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      setIsEditDialogOpen(false);
      setSelectedWorkflow(null);
      toast.success('Workflow-Regel erfolgreich aktualisiert');
    },
    onError: () => {
      toast.error('Fehler beim Aktualisieren der Workflow-Regel');
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: deleteWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow-Regel erfolgreich gelöscht');
    },
    onError: () => {
      toast.error('Fehler beim Löschen der Workflow-Regel');
    },
  });

  // Toggle mutation
  const toggleMutation = useMutation({
    mutationFn: toggleWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow-Status erfolgreich geändert');
    },
    onError: () => {
      toast.error('Fehler beim Ändern des Workflow-Status');
    },
  });

  const handleEdit = (workflow: Workflow) => {
    setSelectedWorkflow(workflow);
    setIsEditDialogOpen(true);
  };

  const handleDelete = (id: string, name: string) => {
    if (confirm(`Workflow-Regel "${name}" wirklich löschen?`)) {
      deleteMutation.mutate(id);
    }
  };

  const handleToggle = (id: string) => {
    toggleMutation.mutate(id);
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <GitBranch className="h-8 w-8 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Workflow-Regeln</h1>
            <p className="text-muted-foreground">
              Workflow-Automatisierungen verwalten
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
          <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Neue Regel erstellen
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <WorkflowFormDialog
                onSubmit={(data) => createMutation.mutate(data)}
                isLoading={createMutation.isPending}
              />
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Workflows Table */}
      <Card>
        <CardHeader>
          <CardTitle>Workflow-Regeln ({workflows.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : workflows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <GitBranch className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">Keine Workflow-Regeln vorhanden</h3>
              <p className="text-sm text-muted-foreground mt-1">
                Erstellen Sie Ihre erste Regel, um Workflows zu automatisieren
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Trigger-Typ</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Ausführungen</TableHead>
                  <TableHead>Letzte Ausführung</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {workflows.map((workflow) => (
                  <TableRow key={workflow.id}>
                    <TableCell>
                      <div className="font-medium">{workflow.name}</div>
                      {workflow.description && (
                        <div className="text-sm text-muted-foreground">
                          {workflow.description}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {TRIGGER_TYPE_LABELS[workflow.trigger_type]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={workflow.is_active ? 'default' : 'secondary'}
                        className={workflow.is_active ? 'bg-green-500' : ''}
                      >
                        {workflow.is_active ? 'Aktiv' : 'Inaktiv'}
                      </Badge>
                    </TableCell>
                    <TableCell>{workflow.execution_count}</TableCell>
                    <TableCell>{formatDate(workflow.last_executed_at)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleToggle(workflow.id)}
                          title={workflow.is_active ? 'Deaktivieren' : 'Aktivieren'}
                        >
                          {workflow.is_active ? (
                            <PowerOff className="h-4 w-4 text-orange-500" />
                          ) : (
                            <Power className="h-4 w-4 text-green-500" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleEdit(workflow)}
                          title="Bearbeiten"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(workflow.id, workflow.name)}
                          title="Löschen"
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-2xl">
          {selectedWorkflow && (
            <WorkflowFormDialog
              workflow={selectedWorkflow}
              onSubmit={(data) =>
                updateMutation.mutate({ id: selectedWorkflow.id, data })
              }
              isLoading={updateMutation.isPending}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// =============================================================================
// Workflow Form Dialog
// =============================================================================

interface WorkflowFormDialogProps {
  workflow?: Workflow;
  onSubmit: (data: WorkflowCreate | WorkflowUpdate) => void;
  isLoading: boolean;
}

function WorkflowFormDialog({ workflow, onSubmit, isLoading }: WorkflowFormDialogProps) {
  const [name, setName] = useState(workflow?.name || '');
  const [description, setDescription] = useState(workflow?.description || '');
  const [triggerType, setTriggerType] = useState<TriggerType>(
    workflow?.trigger_type || 'document_event'
  );
  const [isActive, setIsActive] = useState(workflow?.is_active ?? true);
  const [timeoutSeconds, setTimeoutSeconds] = useState(
    workflow?.timeout_seconds || 300
  );
  const [eventTypes, setEventTypes] = useState<string>(
    workflow?.trigger_config?.events?.join(', ') || ''
  );
  const [cronExpression, setCronExpression] = useState(
    workflow?.trigger_config?.cron || ''
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const triggerConfig: Record<string, unknown> = {};

    if (triggerType === 'document_event') {
      triggerConfig.events = eventTypes
        .split(',')
        .map((e) => e.trim())
        .filter(Boolean);
    } else if (triggerType === 'schedule') {
      triggerConfig.cron = cronExpression;
    }

    const data: WorkflowCreate | WorkflowUpdate = {
      name,
      description: description || undefined,
      trigger_type: triggerType,
      trigger_config: triggerConfig,
      timeout_seconds: timeoutSeconds,
      is_active: isActive,
    };

    onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit}>
      <DialogHeader>
        <DialogTitle>
          {workflow ? 'Workflow-Regel bearbeiten' : 'Neue Workflow-Regel'}
        </DialogTitle>
      </DialogHeader>

      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name *</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="z.B. Rechnung automatisch ablegen"
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="description">Beschreibung</Label>
          <Textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optionale Beschreibung der Regel"
            rows={2}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="trigger-type">Trigger-Typ *</Label>
          <Select
            value={triggerType}
            onValueChange={(value) => setTriggerType(value as TriggerType)}
          >
            <SelectTrigger id="trigger-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="document_event">Dokumenten-Ereignis</SelectItem>
              <SelectItem value="schedule">Zeitplan</SelectItem>
              <SelectItem value="condition">Bedingung</SelectItem>
              <SelectItem value="manual">Manuell</SelectItem>
              <SelectItem value="webhook">Webhook</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Trigger-specific config */}
        {triggerType === 'document_event' && (
          <div className="space-y-2">
            <Label htmlFor="events">Ereignisse (kommagetrennt)</Label>
            <Input
              id="events"
              value={eventTypes}
              onChange={(e) => setEventTypes(e.target.value)}
              placeholder="uploaded, classified, approved"
            />
            <p className="text-xs text-muted-foreground">
              z.B. uploaded, classified, approved
            </p>
          </div>
        )}

        {triggerType === 'schedule' && (
          <div className="space-y-2">
            <Label htmlFor="cron">Cron-Ausdruck</Label>
            <Input
              id="cron"
              value={cronExpression}
              onChange={(e) => setCronExpression(e.target.value)}
              placeholder="0 9 * * *"
            />
            <p className="text-xs text-muted-foreground">
              z.B. 0 9 * * * (täglich um 9 Uhr)
            </p>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="timeout">Timeout (Sekunden)</Label>
          <Input
            id="timeout"
            type="number"
            value={timeoutSeconds}
            onChange={(e) => setTimeoutSeconds(parseInt(e.target.value, 10))}
            min={10}
          />
        </div>

        <div className="flex items-center space-x-2">
          <Switch
            id="active"
            checked={isActive}
            onCheckedChange={setIsActive}
          />
          <Label htmlFor="active">Aktiv</Label>
        </div>
      </div>

      <DialogFooter>
        <Button type="submit" disabled={isLoading}>
          {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {workflow ? 'Aktualisieren' : 'Erstellen'}
        </Button>
      </DialogFooter>
    </form>
  );
}
