/**
 * DocumentTasksPanel - Aufgaben-Bereich fuer Dokumente
 *
 * Zeigt alle Aufgaben zu einem Dokument und ermoeglicht
 * das Erstellen, Filtern und Verwalten von Aufgaben.
 */

import { useState, useMemo, useCallback } from 'react';
import { ClipboardList, Loader2, Plus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  useDocumentTasks,
  useStartTask,
  useCompleteTask,
  useCancelTask,
  useBlockTask,
  useUnblockTask,
  useDeleteTask,
} from '../hooks/use-document-tasks';
import { TaskCard } from './TaskCard';
import { CreateTaskDialog } from './CreateTaskDialog';
import { useAuth } from '@/lib/auth/AuthContext';
import type { DocumentTask } from '../api/document-tasks-api';

// ==================== Filter Types ====================

type TaskFilter = 'all' | 'open' | 'mine' | 'overdue';

const FILTER_LABELS: Record<TaskFilter, string> = {
  all: 'Alle',
  open: 'Offen',
  mine: 'Meine',
  overdue: 'Ueberfaellig',
};

// ==================== Helpers ====================

function isOverdue(task: DocumentTask): boolean {
  if (!task.due_date) return false;
  if (task.status === 'completed' || task.status === 'cancelled') return false;
  return new Date(task.due_date) < new Date();
}

// ==================== Component ====================

interface DocumentTasksPanelProps {
  documentId: string;
  className?: string;
}

export function DocumentTasksPanel({ documentId, className }: DocumentTasksPanelProps) {
  const { data, isLoading, error, isError } = useDocumentTasks(documentId);
  const { user } = useAuth();

  const startMutation = useStartTask();
  const completeMutation = useCompleteTask();
  const cancelMutation = useCancelTask();
  const blockMutation = useBlockTask();
  const unblockMutation = useUnblockTask();
  const deleteMutation = useDeleteTask();

  const [activeFilter, setActiveFilter] = useState<TaskFilter>('all');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Filter tasks based on active filter
  const filteredTasks = useMemo(() => {
    const items = data?.items ?? [];

    switch (activeFilter) {
      case 'open':
        return items.filter(
          (t) => t.status === 'pending' || t.status === 'in_progress' || t.status === 'blocked',
        );
      case 'mine':
        return items.filter((t) => t.assignee_id === user?.id);
      case 'overdue':
        return items.filter(isOverdue);
      default:
        return items;
    }
  }, [data?.items, activeFilter, user?.id]);

  // Action handlers
  const handleStart = useCallback(
    (id: string) => startMutation.mutate(id),
    [startMutation],
  );
  const handleComplete = useCallback(
    (id: string) => completeMutation.mutate(id),
    [completeMutation],
  );
  const handleCancel = useCallback(
    (id: string) => cancelMutation.mutate(id),
    [cancelMutation],
  );
  const handleBlock = useCallback(
    (id: string) => blockMutation.mutate(id),
    [blockMutation],
  );
  const handleUnblock = useCallback(
    (id: string) => unblockMutation.mutate(id),
    [unblockMutation],
  );
  const handleDelete = useCallback(
    (id: string) => deleteMutation.mutate(id),
    [deleteMutation],
  );

  // Loading state
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Lade Aufgaben...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (isError) {
    return (
      <Card className={className}>
        <CardContent className="py-8">
          <div className="text-center text-destructive">
            <p>Aufgaben konnten nicht geladen werden.</p>
            <p className="text-xs mt-1">{(error as Error)?.message}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const totalCount = data?.total ?? 0;

  return (
    <>
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center justify-between text-lg">
            <div className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5" />
              Aufgaben
              {totalCount > 0 && (
                <span className="text-sm font-normal text-muted-foreground">
                  ({totalCount})
                </span>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="gap-1"
              onClick={() => setCreateDialogOpen(true)}
            >
              <Plus className="h-4 w-4" />
              Aufgabe erstellen
            </Button>
          </CardTitle>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Filter row */}
          <div className="flex items-center gap-1">
            {(Object.keys(FILTER_LABELS) as TaskFilter[]).map((filter) => (
              <Button
                key={filter}
                variant={activeFilter === filter ? 'default' : 'ghost'}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setActiveFilter(filter)}
              >
                {FILTER_LABELS[filter]}
              </Button>
            ))}
          </div>

          <Separator />

          {/* Task list */}
          {filteredTasks.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <ClipboardList className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Keine Aufgaben fuer dieses Dokument</p>
              <p className="text-xs mt-1">
                Erstellen Sie die erste Aufgabe mit dem Button oben.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredTasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onStart={handleStart}
                  onComplete={handleComplete}
                  onCancel={handleCancel}
                  onBlock={handleBlock}
                  onUnblock={handleUnblock}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <CreateTaskDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        documentId={documentId}
      />
    </>
  );
}

export default DocumentTasksPanel;
