/**
 * WorkflowsList Component
 *
 * Listenansicht aller Workflows mit Aktionen.
 */

import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Play, Pause, Trash2, Copy, Edit, MoreHorizontal, Plus, Search, Filter, Clock, AlertTriangle, FileText, Webhook, Calendar, Hand, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import {
  useWorkflows,
  useDeleteWorkflow,
  useDuplicateWorkflow,
  useToggleWorkflow,
  useExecuteWorkflow,
} from '../hooks/useWorkflows';
import type { Workflow, TriggerType } from '../types/workflow-types';

const triggerIcons: Record<TriggerType, React.ElementType> = {
  document_event: FileText,
  schedule: Calendar,
  condition: Filter,
  manual: Hand,
  webhook: Webhook,
};

const triggerLabels: Record<TriggerType, string> = {
  document_event: 'Dokument-Event',
  schedule: 'Zeitplan',
  condition: 'Bedingung',
  manual: 'Manuell',
  webhook: 'Webhook',
};

interface WorkflowCardProps {
  workflow: Workflow;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
  onDuplicate: (id: string) => void;
  onToggle: (id: string) => void;
  onExecute: (id: string) => void;
  onViewExecution?: (id: string) => void;
}

function WorkflowCard({
  workflow,
  onEdit,
  onDelete,
  onDuplicate,
  onToggle,
  onExecute,
  onViewExecution,
}: WorkflowCardProps) {
  const TriggerIcon = triggerIcons[workflow.trigger_type] || FileText;
  const triggerLabel = triggerLabels[workflow.trigger_type] || 'Unbekannt';

  return (
    <Card className={cn('transition-opacity', !workflow.is_active && 'opacity-60')}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <TriggerIcon className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-lg">{workflow.name}</CardTitle>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onEdit(workflow.id)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onDuplicate(workflow.id)}>
                <Copy className="mr-2 h-4 w-4" />
                Duplizieren
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onExecute(workflow.id)}>
                <Play className="mr-2 h-4 w-4" />
                Ausführen
              </DropdownMenuItem>
              {onViewExecution && (
                <DropdownMenuItem onClick={() => onViewExecution(workflow.id)}>
                  <Eye className="mr-2 h-4 w-4" />
                  Ausführung anzeigen
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => onToggle(workflow.id)}>
                {workflow.is_active ? (
                  <>
                    <Pause className="mr-2 h-4 w-4" />
                    Deaktivieren
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Aktivieren
                  </>
                )}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete(workflow.id)}
                className="text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Löschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <CardDescription className="line-clamp-2">
          {workflow.description || 'Keine Beschreibung'}
        </CardDescription>
      </CardHeader>
      <CardContent className="pb-2">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="gap-1">
            <TriggerIcon className="h-3 w-3" />
            {triggerLabel}
          </Badge>
          <Badge variant={workflow.is_active ? 'default' : 'secondary'}>
            {workflow.is_active ? 'Aktiv' : 'Inaktiv'}
          </Badge>
          {workflow.is_template && (
            <Badge variant="outline" className="border-purple-500 text-purple-600">
              Template
            </Badge>
          )}
        </div>
      </CardContent>
      <CardFooter className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1">
            <Play className="h-3 w-3" />
            {workflow.execution_count} Ausführungen
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {workflow.nodes?.length || 0} Knoten
          </span>
        </div>
        {workflow.last_executed_at && (
          <span>
            Letzte: {new Date(workflow.last_executed_at).toLocaleDateString('de-DE')}
          </span>
        )}
      </CardFooter>
    </Card>
  );
}

function WorkflowCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-5" />
            <Skeleton className="h-6 w-32" />
          </div>
          <Skeleton className="h-8 w-8" />
        </div>
        <Skeleton className="h-4 w-48" />
      </CardHeader>
      <CardContent className="pb-2">
        <div className="flex gap-2">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-5 w-16" />
        </div>
      </CardContent>
      <CardFooter>
        <Skeleton className="h-4 w-32" />
      </CardFooter>
    </Card>
  );
}

export default function WorkflowsList() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [triggerFilter, setTriggerFilter] = useState<TriggerType | 'all'>('all');
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const { data, isLoading, error } = useWorkflows({
    search: search || undefined,
    trigger_type: triggerFilter !== 'all' ? triggerFilter : undefined,
    is_active: activeFilter === 'all' ? undefined : activeFilter === 'active',
    limit: 50,
  });

  const deleteWorkflow = useDeleteWorkflow();
  const duplicateWorkflow = useDuplicateWorkflow();
  const toggleWorkflow = useToggleWorkflow();
  const executeWorkflow = useExecuteWorkflow();

  const handleEdit = (id: string) => {
    navigate({ to: '/workflows/$workflowId', params: { workflowId: id } });
  };

  const handleDelete = async () => {
    if (deleteId) {
      await deleteWorkflow.mutateAsync(deleteId);
      setDeleteId(null);
    }
  };

  const handleDuplicate = async (id: string) => {
    await duplicateWorkflow.mutateAsync({ workflowId: id });
  };

  const handleToggle = async (id: string) => {
    await toggleWorkflow.mutateAsync(id);
  };

  const handleExecute = async (id: string) => {
    await executeWorkflow.mutateAsync({ workflowId: id });
  };

  const handleViewExecution = (id: string) => {
    navigate({ to: '/workflows/$workflowId/history', params: { workflowId: id } });
  };

  const handleCreateNew = () => {
    navigate({ to: '/workflows/new' });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Workflows</h1>
          <p className="text-muted-foreground">
            Automatisierte Dokumentverarbeitungs-Pipelines
          </p>
        </div>
        <Button onClick={handleCreateNew}>
          <Plus className="mr-2 h-4 w-4" />
          Neuer Workflow
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Workflows durchsuchen..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select
          value={triggerFilter}
          onValueChange={(v) => setTriggerFilter(v as TriggerType | 'all')}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Trigger-Typ" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Trigger</SelectItem>
            <SelectItem value="document_event">Dokument-Event</SelectItem>
            <SelectItem value="schedule">Zeitplan</SelectItem>
            <SelectItem value="webhook">Webhook</SelectItem>
            <SelectItem value="manual">Manuell</SelectItem>
            <SelectItem value="condition">Bedingung</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={activeFilter}
          onValueChange={(v) => setActiveFilter(v as 'all' | 'active' | 'inactive')}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle</SelectItem>
            <SelectItem value="active">Aktiv</SelectItem>
            <SelectItem value="inactive">Inaktiv</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Workflow Grid */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <WorkflowCardSkeleton key={i} />
          ))}
        </div>
      ) : error ? (
        <Card className="p-8 text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-destructive" />
          <p className="mt-4 text-lg font-medium">Fehler beim Laden der Workflows</p>
          <p className="text-muted-foreground">{(error as Error).message}</p>
        </Card>
      ) : data?.items.length === 0 ? (
        <Card className="p-8 text-center">
          <FileText className="mx-auto h-12 w-12 text-muted-foreground" />
          <p className="mt-4 text-lg font-medium">Keine Workflows gefunden</p>
          <p className="text-muted-foreground">
            Erstelle deinen ersten Workflow, um Dokumente automatisch zu verarbeiten.
          </p>
          <Button onClick={handleCreateNew} className="mt-4">
            <Plus className="mr-2 h-4 w-4" />
            Neuer Workflow
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data?.items.map((workflow) => (
            <WorkflowCard
              key={workflow.id}
              workflow={workflow}
              onEdit={handleEdit}
              onDelete={setDeleteId}
              onDuplicate={handleDuplicate}
              onToggle={handleToggle}
              onExecute={handleExecute}
              onViewExecution={handleViewExecution}
            />
          ))}
        </div>
      )}

      {/* Pagination Info */}
      {data && data.total > 0 && (
        <div className="text-center text-sm text-muted-foreground">
          {data.items.length} von {data.total} Workflows
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Workflow löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Diese Aktion kann nicht rückgängig gemacht werden. Der Workflow und
              alle zugehörigen Ausführungen werden dauerhaft gelöscht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
