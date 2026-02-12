/**
 * KanbanCard - Einzelnes Dokument-Item im Kanban-Board.
 * Zeigt: Dokumentname, Entity, Betrag, Priorität, Zugewiesener Bearbeiter
 */
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { FileText, Euro, User, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { KanbanItem } from '../hooks/use-kanban-queries';

// ==================== Configuration ====================

const PRIORITY_CONFIG = {
  urgent: { label: 'Dringend', color: 'bg-red-100 text-red-800 border-red-200' },
  high: { label: 'Hoch', color: 'bg-orange-100 text-orange-800 border-orange-200' },
  normal: { label: 'Normal', color: 'bg-blue-100 text-blue-800 border-blue-200' },
  low: { label: 'Niedrig', color: 'bg-gray-100 text-gray-800 border-gray-200' },
};

// ==================== Helper Functions ====================

/**
 * Format amount German style: 1234.56 -> "1.234,56 €"
 */
function formatEuro(amount: number): string {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(amount);
}

/**
 * Format relative time in German
 */
function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return 'Gerade eben';
  if (hours < 24) return `Seit ${hours} Std.`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'Seit 1 Tag';
  return `Seit ${days} Tagen`;
}

// ==================== Component ====================

interface KanbanCardProps {
  item: KanbanItem;
}

export function KanbanCard({ item }: KanbanCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const priorityConfig = PRIORITY_CONFIG[item.priority] || PRIORITY_CONFIG.normal;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        'bg-white rounded-lg border p-3 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow',
        isDragging && 'opacity-50 shadow-lg'
      )}
    >
      {/* Header - Document Name */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <span className="font-medium text-sm truncate">
            {item.document_name || 'Unbenanntes Dokument'}
          </span>
        </div>
      </div>

      {/* Entity Name */}
      {item.entity_name && (
        <div className="mb-2">
          <Badge variant="outline" className="text-xs">
            {item.entity_name}
          </Badge>
        </div>
      )}

      {/* Amount */}
      {item.amount !== null && (
        <div className="flex items-center gap-1 text-sm font-mono font-medium mb-2">
          <Euro className="h-3.5 w-3.5 text-muted-foreground" />
          {formatEuro(item.amount)}
        </div>
      )}

      {/* Footer - Priority, Assigned, Time */}
      <div className="flex items-center justify-between gap-2 mt-3 pt-2 border-t">
        <Badge className={cn('text-xs h-5', priorityConfig.color)}>
          {priorityConfig.label}
        </Badge>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {/* Assigned User */}
          {item.assigned_to_name ? (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1">
                    <User className="h-3 w-3" />
                    <span className="max-w-[80px] truncate">{item.assigned_to_name}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  Zugewiesen an {item.assigned_to_name}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            <div className="flex items-center gap-1 text-muted-foreground/50">
              <User className="h-3 w-3" />
              <span>Nicht zugewiesen</span>
            </div>
          )}

          {/* Time in Stage */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  <span>{formatTimeAgo(item.entered_stage_at)}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                In dieser Phase seit {formatTimeAgo(item.entered_stage_at)}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      {/* Notes Indicator */}
      {item.notes && (
        <div className="mt-2 pt-2 border-t">
          <p className="text-xs text-muted-foreground italic truncate">
            {item.notes}
          </p>
        </div>
      )}
    </div>
  );
}
