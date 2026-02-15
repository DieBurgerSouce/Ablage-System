import { useState } from "react";
import { CheckSquare, Filter, User, Clock, FileText } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useTasks, useUpdateTask } from "../hooks/use-annotations-extended-queries";
import type {
  AnnotationTaskStatus,
  AnnotationTask,
} from "../types/annotations-extended-types";
import {
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
  TASK_STATUS_COLORS,
  TASK_PRIORITY_COLORS,
} from "../types/annotations-extended-types";

export function AnnotationTasksPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [assigneeFilter, setAssigneeFilter] = useState<string>("all");

  const { data: tasks = [], isLoading } = useTasks(
    statusFilter !== "all" ? { status: statusFilter } : undefined
  );

  const updateTaskMutation = useUpdateTask();

  const formatDate = (date: Date) => {
    return new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(date);
  };

  const isOverdue = (task: AnnotationTask) => {
    return (
      task.dueDate && task.status !== "erledigt" && task.dueDate < new Date()
    );
  };

  const handleStatusChange = (taskId: number, status: AnnotationTaskStatus) => {
    updateTaskMutation.mutate({ taskId, data: { status } });
  };

  // Filter tasks
  const filteredTasks = tasks.filter((task) => {
    if (assigneeFilter !== "all" && task.assignee !== assigneeFilter) {
      return false;
    }
    return true;
  });

  // Get unique assignees for filter
  const uniqueAssignees = Array.from(
    new Set(tasks.map((t) => t.assignee).filter(Boolean))
  );

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Annotations-Aufgaben</h1>
        <p className="text-muted-foreground mt-1">
          Aufgaben aus Dokumenten-Annotationen
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Filter className="w-4 h-4" />
            Filter
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            {/* Status Filter */}
            <div className="flex-1">
              <label className="text-sm font-medium mb-1 block">Status</label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle Status</SelectItem>
                  <SelectItem value="offen">Offen</SelectItem>
                  <SelectItem value="in_bearbeitung">In Bearbeitung</SelectItem>
                  <SelectItem value="erledigt">Erledigt</SelectItem>
                  <SelectItem value="abgebrochen">Abgebrochen</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Assignee Filter */}
            <div className="flex-1">
              <label className="text-sm font-medium mb-1 block">
                Zugewiesen an
              </label>
              <Select value={assigneeFilter} onValueChange={setAssigneeFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle Benutzer</SelectItem>
                  {uniqueAssignees.map((assignee) => (
                    <SelectItem key={assignee} value={assignee || ""}>
                      {assignee}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Task List */}
      <div className="space-y-4">
        {isLoading ? (
          // Loading Skeletons
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-6 w-3/4 mb-3" />
                <Skeleton className="h-4 w-1/2 mb-2" />
                <Skeleton className="h-4 w-1/3" />
              </CardContent>
            </Card>
          ))
        ) : filteredTasks.length === 0 ? (
          // Empty State
          <Card>
            <CardContent className="py-12 text-center">
              <CheckSquare className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">Keine Aufgaben gefunden</p>
            </CardContent>
          </Card>
        ) : (
          // Task Cards
          filteredTasks.map((task) => (
            <Card
              key={task.id}
              className={isOverdue(task) ? "border-red-300 dark:border-red-700" : ""}
            >
              <CardContent className="pt-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-3">
                    {/* Title */}
                    <h3 className="font-semibold text-lg">{task.title}</h3>

                    {/* Badges */}
                    <div className="flex flex-wrap gap-2">
                      <Badge className={TASK_STATUS_COLORS[task.status]}>
                        {TASK_STATUS_LABELS[task.status]}
                      </Badge>
                      <Badge className={TASK_PRIORITY_COLORS[task.priority]}>
                        {TASK_PRIORITY_LABELS[task.priority]}
                      </Badge>
                      {isOverdue(task) && (
                        <Badge variant="destructive">Überfällig</Badge>
                      )}
                    </div>

                    {/* Metadata */}
                    <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                      {task.assignee && (
                        <div className="flex items-center gap-1">
                          <User className="w-4 h-4" />
                          {task.assignee}
                        </div>
                      )}

                      {task.dueDate && (
                        <div
                          className={`flex items-center gap-1 ${
                            isOverdue(task) ? "text-red-600 font-medium" : ""
                          }`}
                        >
                          <Clock className="w-4 h-4" />
                          Fällig: {formatDate(task.dueDate)}
                        </div>
                      )}

                      <div className="flex items-center gap-1">
                        <FileText className="w-4 h-4" />
                        Kommentar #{task.commentId}
                      </div>
                    </div>
                  </div>

                  {/* Status Quick Actions */}
                  <div className="flex flex-col gap-2">
                    <Select
                      value={task.status}
                      onValueChange={(value) =>
                        handleStatusChange(task.id, value as AnnotationTaskStatus)
                      }
                    >
                      <SelectTrigger className="w-40">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="offen">Offen</SelectItem>
                        <SelectItem value="in_bearbeitung">
                          In Bearbeitung
                        </SelectItem>
                        <SelectItem value="erledigt">Erledigt</SelectItem>
                        <SelectItem value="abgebrochen">Abgebrochen</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Footer */}
                <div className="mt-4 pt-4 border-t text-xs text-muted-foreground">
                  Erstellt am {formatDate(task.createdAt)}
                  {task.updatedAt &&
                    ` • Aktualisiert am ${formatDate(task.updatedAt)}`}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
