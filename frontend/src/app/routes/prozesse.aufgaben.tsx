/**
 * BPMN Task Inbox
 *
 * Aufgaben-Inbox für Benutzer-Tasks.
 */

import { createFileRoute } from '@tanstack/react-router';
import { useState } from 'react';
import {
  useMyTasks,
  useGroupTasks,
  useTaskStatistics,
  useClaimTask,
  useCompleteTask,
  useStartTask,
} from '@/features/bpmn';
import type { ProcessTask, TaskStatus } from '@/features/bpmn';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  User,
  Users,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Play,
  Check,
  Hand,
  ArrowRight,
  Loader2,
  Inbox,
} from 'lucide-react';

export const Route = createFileRoute('/prozesse/aufgaben')({
  component: TaskInboxPage,
});

function TaskInboxPage() {
  const { data: myTasks, isLoading: loadingMyTasks } = useMyTasks();
  const { data: groupTasks, isLoading: loadingGroupTasks } = useGroupTasks();
  const { data: stats } = useTaskStatistics();

  return (
    <div className="container mx-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Aufgaben-Inbox</h1>
        <p className="mt-1 text-sm text-gray-500">
          Offene BPMN-Aufgaben bearbeiten
        </p>
      </div>

      {/* Statistics */}
      {stats && (
        <div className="mb-6 grid gap-4 md:grid-cols-4">
          <StatCard
            title="Meine Aufgaben"
            value={myTasks?.length || 0}
            icon={User}
            color="blue"
          />
          <StatCard
            title="Gruppen-Aufgaben"
            value={groupTasks?.length || 0}
            icon={Users}
            color="purple"
          />
          <StatCard
            title="Überfällig"
            value={stats.overdue || 0}
            icon={AlertTriangle}
            color="amber"
          />
          <StatCard
            title="Abgeschlossen (heute)"
            value={stats.by_status?.completed || 0}
            icon={CheckCircle2}
            color="green"
          />
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="my-tasks">
        <TabsList>
          <TabsTrigger value="my-tasks">
            <User className="mr-2 h-4 w-4" />
            Meine Aufgaben
            {myTasks && myTasks.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {myTasks.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="group-tasks">
            <Users className="mr-2 h-4 w-4" />
            Gruppen-Aufgaben
            {groupTasks && groupTasks.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {groupTasks.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="my-tasks" className="mt-4">
          {loadingMyTasks ? (
            <TaskListSkeleton />
          ) : myTasks && myTasks.length > 0 ? (
            <div className="space-y-4">
              {myTasks.map((task) => (
                <TaskCard key={task.id} task={task} showClaimButton={false} />
              ))}
            </div>
          ) : (
            <EmptyTaskList message="Keine Aufgaben zugewiesen" />
          )}
        </TabsContent>

        <TabsContent value="group-tasks" className="mt-4">
          {loadingGroupTasks ? (
            <TaskListSkeleton />
          ) : groupTasks && groupTasks.length > 0 ? (
            <div className="space-y-4">
              {groupTasks.map((task) => (
                <TaskCard key={task.id} task={task} showClaimButton={true} />
              ))}
            </div>
          ) : (
            <EmptyTaskList message="Keine Gruppen-Aufgaben verfügbar" />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  color: 'blue' | 'green' | 'purple' | 'amber';
}

function StatCard({ title, value, icon: Icon, color }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    purple: 'bg-purple-50 text-purple-600',
    amber: 'bg-amber-50 text-amber-600',
  };

  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <div className={`rounded-lg p-2 ${colorClasses[color]}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

interface TaskCardProps {
  task: ProcessTask;
  showClaimButton: boolean;
}

function TaskCard({ task, showClaimButton }: TaskCardProps) {
  const claimMutation = useClaimTask();
  const startMutation = useStartTask();
  const completeMutation = useCompleteTask();

  const handleClaim = async () => {
    try {
      await claimMutation.mutateAsync({ id: task.id });
      toast.success('Aufgabe übernommen');
    } catch {
      toast.error('Übernahme fehlgeschlagen');
    }
  };

  const handleStart = async () => {
    try {
      await startMutation.mutateAsync(task.id);
      toast.success('Aufgabe gestartet');
    } catch {
      toast.error('Start fehlgeschlagen');
    }
  };

  const handleComplete = async () => {
    try {
      await completeMutation.mutateAsync({ id: task.id });
      toast.success('Aufgabe abgeschlossen');
    } catch {
      toast.error('Abschluss fehlgeschlagen');
    }
  };

  const isOverdue =
    task.due_date && new Date(task.due_date) < new Date();

  return (
    <Card className={isOverdue ? 'border-amber-200 bg-amber-50/50' : ''}>
      <CardContent className="flex items-center justify-between p-4">
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h3 className="font-medium text-gray-900">
              {task.element_name || 'Aufgabe'}
            </h3>
            <TaskStatusBadge status={task.status} />
            {task.priority < 50 && (
              <Badge variant="destructive" className="text-xs">
                Hoch
              </Badge>
            )}
            {isOverdue && (
              <Badge variant="outline" className="border-amber-500 text-amber-600">
                <AlertTriangle className="mr-1 h-3 w-3" />
                Überfällig
              </Badge>
            )}
          </div>

          <div className="mt-2 flex items-center gap-4 text-sm text-gray-500">
            {task.due_date && (
              <span className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                Fällig: {new Date(task.due_date).toLocaleDateString('de-DE')}
              </span>
            )}
            {task.candidate_groups && task.candidate_groups.length > 0 && (
              <span className="flex items-center gap-1">
                <Users className="h-4 w-4" />
                {task.candidate_groups.join(', ')}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {showClaimButton && task.status === 'ready' && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleClaim}
              disabled={claimMutation.isPending}
            >
              {claimMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Hand className="mr-2 h-4 w-4" />
              )}
              Übernehmen
            </Button>
          )}

          {task.status === 'reserved' && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleStart}
              disabled={startMutation.isPending}
            >
              {startMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Starten
            </Button>
          )}

          {task.status === 'in_progress' && (
            <Button
              size="sm"
              onClick={handleComplete}
              disabled={completeMutation.isPending}
            >
              {completeMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Check className="mr-2 h-4 w-4" />
              )}
              Abschließen
            </Button>
          )}

          <Button variant="ghost" size="sm">
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const config: Record<TaskStatus, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
    created: { label: 'Neu', variant: 'secondary' },
    ready: { label: 'Bereit', variant: 'secondary' },
    reserved: { label: 'Reserviert', variant: 'outline' },
    in_progress: { label: 'In Bearbeitung', variant: 'default' },
    completed: { label: 'Abgeschlossen', variant: 'secondary' },
    failed: { label: 'Fehlgeschlagen', variant: 'secondary' },
    skipped: { label: 'Übersprungen', variant: 'secondary' },
  };

  const { label, variant } = config[status] || config.created;

  return <Badge variant={variant}>{label}</Badge>;
}

function TaskListSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <Skeleton className="mb-2 h-5 w-48" />
            <Skeleton className="h-4 w-32" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function EmptyTaskList({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <Inbox className="mb-4 h-12 w-12 text-gray-400" />
        <p className="text-gray-500">{message}</p>
      </CardContent>
    </Card>
  );
}
