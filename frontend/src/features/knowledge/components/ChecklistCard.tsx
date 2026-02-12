/**
 * ChecklistCard - Einzelne Checklisten-Karte
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  CheckSquare,
  MoreVertical,
  Edit,
  Trash2,
  Copy,
  Plus,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import type { KnowledgeChecklist, KnowledgeChecklistItem } from '../types/knowledge-types';
import { cn } from '@/lib/utils';

interface ChecklistCardProps {
  checklist: KnowledgeChecklist;
  onEdit: (checklist: KnowledgeChecklist) => void;
  onDelete: (checklist: KnowledgeChecklist) => void;
  onDuplicate?: (checklist: KnowledgeChecklist) => void;
  onToggleItem: (checklistId: string, itemId: string, isCompleted: boolean) => void;
  onAddItem?: (checklistId: string) => void;
}

export function ChecklistCard({
  checklist,
  onEdit,
  onDelete,
  onDuplicate,
  onToggleItem,
  onAddItem,
}: ChecklistCardProps) {
  const [expanded, setExpanded] = useState(true);

  const completedCount = checklist.items.filter((item) => item.is_completed).length;
  const totalCount = checklist.items.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const isCompleted = completedCount === totalCount && totalCount > 0;

  // Sortiere Items nach sort_order
  const sortedItems = [...checklist.items].sort((a, b) => a.sort_order - b.sort_order);

  return (
    <Card className={cn('transition-shadow', isCompleted && 'border-green-500')}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div
              className={cn(
                'p-1.5 rounded',
                isCompleted ? 'bg-green-500' : 'bg-blue-500',
                'text-white flex-shrink-0'
              )}
            >
              <CheckSquare className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <CardTitle className="text-base truncate">{checklist.title}</CardTitle>
              {checklist.description && (
                <CardDescription className="text-xs truncate">
                  {checklist.description}
                </CardDescription>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onEdit(checklist)}>
                  <Edit className="h-4 w-4 mr-2" />
                  Bearbeiten
                </DropdownMenuItem>
                {onDuplicate && (
                  <DropdownMenuItem onClick={() => onDuplicate(checklist)}>
                    <Copy className="h-4 w-4 mr-2" />
                    Duplizieren
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => onDelete(checklist)} className="text-destructive">
                  <Trash2 className="h-4 w-4 mr-2" />
                  Löschen
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <div className="flex items-center gap-3 mt-2">
          <Progress value={progress} className="flex-1 h-2" />
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {completedCount}/{totalCount}
          </span>
          {checklist.is_template && (
            <Badge variant="outline" className="text-xs">
              Vorlage
            </Badge>
          )}
        </div>
      </CardHeader>

      {expanded && (
        <CardContent>
          <div className="space-y-2">
            {sortedItems.map((item) => (
              <ChecklistItemRow
                key={item.id}
                item={item}
                onToggle={(isCompleted) => onToggleItem(checklist.id, item.id, isCompleted)}
              />
            ))}
            {sortedItems.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-2">
                Keine Einträge
              </p>
            )}
          </div>

          {onAddItem && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full mt-2"
              onClick={() => onAddItem(checklist.id)}
            >
              <Plus className="h-4 w-4 mr-2" />
              Eintrag hinzufügen
            </Button>
          )}

          <div className="flex items-center justify-between mt-3 pt-3 border-t">
            <span className="text-xs text-muted-foreground">
              Aktualisiert{' '}
              {formatDistanceToNow(new Date(checklist.updated_at), {
                addSuffix: true,
                locale: de,
              })}
            </span>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

interface ChecklistItemRowProps {
  item: KnowledgeChecklistItem;
  onToggle: (isCompleted: boolean) => void;
}

function ChecklistItemRow({ item, onToggle }: ChecklistItemRowProps) {
  const isOverdue = item.due_date && !item.is_completed && new Date(item.due_date) < new Date();

  return (
    <div
      className={cn(
        'flex items-start gap-3 p-2 rounded hover:bg-muted/50 transition-colors',
        item.is_completed && 'opacity-60'
      )}
    >
      <Checkbox
        checked={item.is_completed}
        onCheckedChange={(checked) => onToggle(!!checked)}
        className="mt-0.5"
      />
      <div className="flex-1 min-w-0">
        <p className={cn('text-sm', item.is_completed && 'line-through')}>
          {item.text}
        </p>
        {item.description && (
          <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
        )}
        {item.due_date && (
          <p className={cn('text-xs mt-1', isOverdue ? 'text-destructive' : 'text-muted-foreground')}>
            Fällig: {new Date(item.due_date).toLocaleDateString('de-DE')}
          </p>
        )}
      </div>
    </div>
  );
}
