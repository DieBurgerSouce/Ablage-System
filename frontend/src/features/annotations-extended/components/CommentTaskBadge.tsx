import { CheckSquare, Clock, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { AnnotationTask } from "../types/annotations-extended-types";
import {
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
  TASK_STATUS_COLORS,
  TASK_PRIORITY_COLORS,
} from "../types/annotations-extended-types";

interface CommentTaskBadgeProps {
  task: AnnotationTask;
  onClick?: () => void;
}

export function CommentTaskBadge({ task, onClick }: CommentTaskBadgeProps) {
  const statusColor = TASK_STATUS_COLORS[task.status];
  const priorityColor = TASK_PRIORITY_COLORS[task.priority];

  const formatDate = (date: Date) => {
    return new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(date);
  };

  const isOverdue =
    task.dueDate && task.status !== "erledigt" && task.dueDate < new Date();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className="inline-flex items-center gap-1"
          onClick={(e) => {
            e.stopPropagation();
            onClick?.();
          }}
        >
          <Badge
            variant="outline"
            className={`${statusColor} cursor-pointer hover:opacity-80 transition-opacity`}
          >
            <CheckSquare className="w-3 h-3 mr-1" />
            {TASK_STATUS_LABELS[task.status]}
          </Badge>

          {isOverdue && (
            <Badge variant="destructive" className="ml-1">
              Überfällig
            </Badge>
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent className="w-80" onClick={(e) => e.stopPropagation()}>
        <div className="space-y-3">
          {/* Title */}
          <div>
            <h4 className="font-semibold text-sm mb-1">Aufgabe</h4>
            <p className="text-sm">{task.title}</p>
          </div>

          {/* Status & Priority */}
          <div className="flex gap-2">
            <Badge className={statusColor}>
              {TASK_STATUS_LABELS[task.status]}
            </Badge>
            <Badge className={priorityColor}>
              {TASK_PRIORITY_LABELS[task.priority]}
            </Badge>
          </div>

          {/* Assignee */}
          {task.assignee && (
            <div className="flex items-center gap-2 text-sm">
              <User className="w-4 h-4 text-muted-foreground" />
              <span className="text-muted-foreground">Zugewiesen an:</span>
              <span className="font-medium">{task.assignee}</span>
            </div>
          )}

          {/* Due Date */}
          {task.dueDate && (
            <div
              className={`flex items-center gap-2 text-sm ${
                isOverdue ? "text-red-600 font-medium" : ""
              }`}
            >
              <Clock className="w-4 h-4 text-muted-foreground" />
              <span className="text-muted-foreground">Fällig am:</span>
              <span>{formatDate(task.dueDate)}</span>
            </div>
          )}

          {/* Created */}
          <div className="text-xs text-muted-foreground pt-2 border-t">
            Erstellt am {formatDate(task.createdAt)}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
