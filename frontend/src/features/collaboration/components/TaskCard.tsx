/**
 * TaskCard - Einzelne Aufgabe als Karte
 *
 * Zeigt Titel, Zuweiser, Prioritaet-Badge, Faelligkeit
 * und status-abhaengige Aktions-Buttons.
 */

import { useState } from 'react';
import {
  Play,
  CheckCircle2,
  Ban,
  Lock,
  Unlock,
  Calendar,
  User,
  Trash2,
  ChevronDown,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import type { DocumentTask, TaskStatus, TaskPriority } from '../api/document-tasks-api';

// ==================== Badge Config ====================

const PRIORITY_STYLES: Record<TaskPriority, string> = {
  urgent: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
};

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  urgent: 'Dringend',
  high: 'Hoch',
  medium: 'Mittel',
  low: 'Niedrig',
};

const STATUS_STYLES: Record<TaskStatus, string> = {
  pending: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  in_progress: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
  blocked: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  cancelled: 'bg-gray-100 text-gray-500 dark:bg-gray-900/30 dark:text-gray-500',
};

const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: 'Offen',
  in_progress: 'In Bearbeitung',
  blocked: 'Blockiert',
  completed: 'Abgeschlossen',
  cancelled: 'Abgebrochen',
};

// ==================== Helpers ====================

function isOverdue(task: DocumentTask): boolean {
  if (!task.due_date) return false;
  if (task.status === 'completed' || task.status === 'cancelled') return false;
  return new Date(task.due_date) < new Date();
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

// ==================== Component ====================

interface TaskCardProps {
  task: DocumentTask;
  onStart: (id: string) => void;
  onComplete: (id: string) => void;
  onCancel: (id: string) => void;
  onBlock: (id: string) => void;
  onUnblock: (id: string) => void;
  onDelete: (id: string) => void;
}

export function TaskCard({
  task,
  onStart,
  onComplete,
  onCancel,
  onBlock,
  onUnblock,
  onDelete,
}: TaskCardProps) {
  const [descOpen, setDescOpen] = useState(false);
  const overdue = isOverdue(task);

  return (
    <div
      className={`rounded-lg border p-3 space-y-2 transition-colors ${
        overdue ? 'border-l-4 border-l-red-500' : ''
      }`}
    >
      {/* Header: Title + Priority + Status */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium leading-tight truncate">{task.title}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            von {task.creator_name}
          </p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <Badge variant="outline" className={`text-xs ${PRIORITY_STYLES[task.priority]}`}>
            {PRIORITY_LABELS[task.priority]}
          </Badge>
          <Badge variant="outline" className={`text-xs ${STATUS_STYLES[task.status]}`}>
            {STATUS_LABELS[task.status]}
          </Badge>
        </div>
      </div>

      {/* Description (collapsible) */}
      {task.description && (
        <Collapsible open={descOpen} onOpenChange={setDescOpen}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronDown
                className={`h-3 w-3 transition-transform ${descOpen ? 'rotate-180' : ''}`}
              />
              Beschreibung
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <p className="text-xs text-muted-foreground mt-1 pl-4 whitespace-pre-wrap">
              {task.description}
            </p>
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Meta row: Assignee, Due Date, Overdue */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {task.assignee_name && (
          <span className="flex items-center gap-1">
            <User className="h-3 w-3" />
            {task.assignee_name}
          </span>
        )}
        {task.due_date && (
          <span className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            {formatDate(task.due_date)}
          </span>
        )}
        {overdue && (
          <span className="text-red-600 dark:text-red-400 font-medium">
            Ueberfaellig
          </span>
        )}
      </div>

      {/* Action buttons (status-dependent) */}
      <div className="flex items-center gap-1 pt-1">
        {task.status === 'pending' && (
          <>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => onStart(task.id)}
            >
              <Play className="h-3 w-3" />
              Starten
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => onBlock(task.id)}
            >
              <Lock className="h-3 w-3" />
              Blockieren
            </Button>
          </>
        )}

        {task.status === 'in_progress' && (
          <>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => onComplete(task.id)}
            >
              <CheckCircle2 className="h-3 w-3" />
              Abschliessen
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => onBlock(task.id)}
            >
              <Lock className="h-3 w-3" />
              Blockieren
            </Button>
          </>
        )}

        {task.status === 'blocked' && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() => onUnblock(task.id)}
          >
            <Unlock className="h-3 w-3" />
            Freigeben
          </Button>
        )}

        {/* Cancel and Delete are always available for non-terminal statuses */}
        {task.status !== 'completed' && task.status !== 'cancelled' && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 text-xs text-muted-foreground"
            onClick={() => onCancel(task.id)}
          >
            <Ban className="h-3 w-3" />
            Abbrechen
          </Button>
        )}

        <div className="flex-1" />

        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1 text-xs text-destructive hover:text-destructive"
          onClick={() => onDelete(task.id)}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
