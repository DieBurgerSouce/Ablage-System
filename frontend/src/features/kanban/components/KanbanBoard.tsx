/**
 * KanbanBoard - Hauptkomponente für das Dokument-Workflow-Board.
 * Drag-and-Drop zwischen Spalten mit @dnd-kit.
 */
import { useState, useCallback } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCorners,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { RefreshCw, LayoutGrid, AlertCircle } from 'lucide-react';
import { useKanbanBoard, useMoveItem } from '../hooks/use-kanban-queries';
import { KanbanColumn } from './KanbanColumn';
import { KanbanCard } from './KanbanCard';
import { cn } from '@/lib/utils';
import type { KanbanItem } from '../hooks/use-kanban-queries';

// ==================== Props ====================

interface KanbanBoardProps {
  workflowType?: string;
}

// ==================== Component ====================

export function KanbanBoard({ workflowType = 'document' }: KanbanBoardProps) {
  const [activeItem, setActiveItem] = useState<KanbanItem | null>(null);

  const { data: board, isLoading, isError, error, refetch } = useKanbanBoard(workflowType);
  const moveItemMutation = useMoveItem();

  // Configure sensors for drag-and-drop
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Prevent accidental drags
      },
    }),
    useSensor(KeyboardSensor)
  );

  // Handle drag start
  const handleDragStart = useCallback((event: DragStartEvent) => {
    const { active } = event;

    // Find the item being dragged
    if (board) {
      for (const stage of board.stages) {
        const item = stage.items.find((i) => i.id === active.id);
        if (item) {
          setActiveItem(item);
          break;
        }
      }
    }
  }, [board]);

  // Handle drag end
  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;

    setActiveItem(null);

    if (!over) return;

    // Get target stage ID (over.id is the stage ID from useDroppable)
    const targetStageId = over.id.toString();
    const itemId = active.id.toString();

    // Find current stage
    const currentStage = board?.stages.find((s) =>
      s.items.some((i) => i.id === itemId)
    );

    if (!currentStage) return;

    // Don't move if dropping in the same stage
    if (currentStage.id === targetStageId) return;

    // Execute move mutation
    moveItemMutation.mutate({
      itemId,
      targetStageId,
    });
  }, [board, moveItemMutation]);

  // Loading state
  if (isLoading) {
    return (
      <div
        role="group"
        aria-label="Kanban-Board wird geladen"
        tabIndex={0}
        className="flex gap-4 overflow-x-auto pb-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-md"
      >
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="min-w-[280px]">
            <Skeleton className="h-[600px] w-full rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <Card className="border-red-200 bg-red-50/50">
        <CardContent className="py-8">
          <div className="flex flex-col items-center justify-center space-y-4">
            <AlertCircle className="h-12 w-12 text-red-500" />
            <div className="text-center">
              <h3 className="font-semibold text-red-700">
                Fehler beim Laden des Kanban-Boards
              </h3>
              <p className="text-sm text-muted-foreground mt-1">
                {error instanceof Error
                  ? error.message
                  : 'Das Kanban-Board konnte nicht geladen werden.'}
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => refetch()}
              className="border-red-300 hover:bg-red-100"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Erneut versuchen
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!board) {
    return null;
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LayoutGrid className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Dokumenten-Workflow</h2>
          <Badge variant="secondary" className="ml-2">
            {board.total_items} Dokumente
          </Badge>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isLoading}
        >
          <RefreshCw className={cn('h-4 w-4 mr-2', isLoading && 'animate-spin')} />
          Aktualisieren
        </Button>
      </div>

      {/* Kanban Board */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        {/* a11y (WCAG 2.1 AA scrollable-region-focusable): Die horizontal
            scrollbare Board-Leiste muss per Tastatur fokussierbar sein und
            einen sprechenden Namen tragen. */}
        <div
          role="group"
          aria-label="Kanban-Board mit Workflow-Phasen"
          tabIndex={0}
          className="flex gap-4 overflow-x-auto pb-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-md"
          style={{ minHeight: '600px' }}
        >
          {board.stages
            .sort((a, b) => a.stage_order - b.stage_order)
            .map((stage) => (
              <KanbanColumn key={stage.id} stage={stage} />
            ))}
        </div>

        {/* Drag Overlay */}
        <DragOverlay>
          {activeItem ? (
            <div className="opacity-90">
              <KanbanCard item={activeItem} />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

// Helper component for badge
function Badge({ children, variant = 'default', className = '' }: {
  children: React.ReactNode;
  variant?: 'default' | 'secondary';
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset',
        variant === 'secondary' && 'bg-gray-50 text-gray-600 ring-gray-500/10',
        variant === 'default' && 'bg-blue-50 text-blue-700 ring-blue-700/10',
        className
      )}
    >
      {children}
    </span>
  );
}
