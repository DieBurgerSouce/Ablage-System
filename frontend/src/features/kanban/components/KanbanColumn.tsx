/**
 * KanbanColumn - Eine Spalte im Kanban-Board.
 * Zeigt Stage-Name, Item-Count Badge, und die Items als KanbanCards.
 */
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { FileX } from 'lucide-react';
import { KanbanCard } from './KanbanCard';
import type { KanbanStage } from '../hooks/use-kanban-queries';

// ==================== Component ====================

interface KanbanColumnProps {
  stage: KanbanStage;
}

export function KanbanColumn({ stage }: KanbanColumnProps) {
  const { setNodeRef } = useDroppable({
    id: stage.id,
  });

  const itemIds = stage.items.map((item) => item.id);

  return (
    <div className="flex flex-col min-w-[280px] max-w-[320px] border rounded-lg bg-muted/20">
      {/* Column Header */}
      <div className="p-3 border-b bg-white/80 rounded-t-lg">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {/* Stage Color Indicator */}
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: stage.color }}
            />
            <span className="font-semibold text-sm">{stage.stage_name}</span>
          </div>
          <Badge variant="secondary" className="text-xs">
            {stage.item_count}
          </Badge>
        </div>

        {/* Stage Icon */}
        {stage.icon && (
          <div className="text-xs text-muted-foreground">
            {stage.icon}
          </div>
        )}
      </div>

      {/* Droppable Area with Cards */}
      <ScrollArea className="flex-1 p-2" style={{ maxHeight: '600px' }}>
        <div
          ref={setNodeRef}
          className="space-y-2 min-h-[100px]"
        >
          <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
            {stage.items.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                <FileX className="h-8 w-8 mb-2 opacity-50" />
                <p className="text-sm">Keine Dokumente</p>
              </div>
            ) : (
              stage.items.map((item) => (
                <KanbanCard key={item.id} item={item} />
              ))
            )}
          </SortableContext>
        </div>
      </ScrollArea>

      {/* Final Stage Indicator */}
      {stage.is_final && (
        <div className="p-2 border-t bg-green-50/50 rounded-b-lg">
          <p className="text-xs text-green-700 text-center font-medium">
            Abgeschlossene Phase
          </p>
        </div>
      )}
    </div>
  );
}
