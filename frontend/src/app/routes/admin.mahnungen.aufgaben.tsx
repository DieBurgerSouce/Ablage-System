/**
 * Admin Mahnungen - Aufgaben (MahnTasks)
 *
 * Zeigt anstehende Mahnaufgaben mit Wiedervorlage
 */

import { createFileRoute } from '@tanstack/react-router';
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/components/ui/use-toast';
import {
    ClipboardList,
    Clock,
    CheckCircle2,
    Phone,
    Mail,
    MoreHorizontal,
    AlertTriangle,
    CalendarDays,
} from 'lucide-react';
import { useMahnTasks, useCompleteMahnTask, useSnoozeMahnTask } from '@/features/banking/hooks/use-banking-queries';
import type { MahnTask } from '@/types/models/banking';
import { cn } from '@/lib/utils';

export const Route = createFileRoute('/admin/mahnungen/aufgaben')({
    component: AufgabenPage,
});

// ==================== Helper Functions ====================

function isToday(date: Date): boolean {
    const today = new Date();
    return date.getDate() === today.getDate() &&
        date.getMonth() === today.getMonth() &&
        date.getFullYear() === today.getFullYear();
}

function isTomorrow(date: Date): boolean {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return date.getDate() === tomorrow.getDate() &&
        date.getMonth() === tomorrow.getMonth() &&
        date.getFullYear() === tomorrow.getFullYear();
}

function isPast(date: Date): boolean {
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    return date < now;
}

function addDays(date: Date, days: number): Date {
    const result = new Date(date);
    result.setDate(result.getDate() + days);
    return result;
}

function formatDateDe(date: Date, pattern: 'short' | 'full' = 'full'): string {
    if (pattern === 'short') {
        return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
    }
    return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function getTaskTypeIcon(taskType: string) {
    switch (taskType) {
        case 'phone_call':
            return <Phone className="h-4 w-4" />;
        case 'send_reminder':
        case 'escalate':
            return <Mail className="h-4 w-4" />;
        default:
            return <ClipboardList className="h-4 w-4" />;
    }
}

function getTaskTypeLabel(taskType: string) {
    const labels: Record<string, string> = {
        'phone_call': 'Telefonat',
        'send_reminder': 'Mahnung senden',
        'escalate': 'Eskalieren',
        'follow_up': 'Nachfassen',
        'review': 'Pruefen',
    };
    return labels[taskType] || taskType;
}

function getDueDateLabel(dateStr: string | null) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    if (isToday(date)) return 'Heute';
    if (isTomorrow(date)) return 'Morgen';
    if (isPast(date)) return `Ueberfaellig (${formatDateDe(date, 'short')})`;
    return formatDateDe(date, 'full');
}

function getDueDateBadgeVariant(dateStr: string | null): 'default' | 'secondary' | 'destructive' | 'outline' {
    if (!dateStr) return 'outline';
    const date = new Date(dateStr);
    if (isPast(date) && !isToday(date)) return 'destructive';
    if (isToday(date)) return 'default';
    return 'secondary';
}

// ==================== Task Row Component ====================

function TaskRow({
    task,
    onComplete,
    onSnooze,
}: {
    task: MahnTask;
    onComplete: (taskId: string) => void;
    onSnooze: (taskId: string, days: number) => void;
}) {
    return (
        <TableRow className={cn(task.status === 'completed' && 'opacity-50')}>
            <TableCell>
                <div className="flex items-center gap-2">
                    {getTaskTypeIcon(task.task_type)}
                    <span className="font-medium">{getTaskTypeLabel(task.task_type)}</span>
                </div>
            </TableCell>
            <TableCell>{task.dunning_record_id?.slice(0, 8) || '-'}</TableCell>
            <TableCell>
                {task.completion_notes || '-'}
            </TableCell>
            <TableCell>
                <Badge variant={getDueDateBadgeVariant(task.due_date)}>
                    <Clock className="h-3 w-3 mr-1" />
                    {getDueDateLabel(task.due_date)}
                </Badge>
            </TableCell>
            <TableCell>
                <Badge variant={task.priority >= 3 ? 'destructive' : 'secondary'}>
                    {task.priority >= 3 ? 'Hoch' : task.priority >= 2 ? 'Mittel' : 'Normal'}
                </Badge>
            </TableCell>
            <TableCell>
                {task.snooze_count > 0 && (
                    <span className="text-xs text-muted-foreground">
                        {task.snooze_count}/3 verschoben
                    </span>
                )}
            </TableCell>
            <TableCell>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" disabled={task.status === 'completed'}>
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => onComplete(task.id)}>
                            <CheckCircle2 className="h-4 w-4 mr-2" />
                            Erledigt
                        </DropdownMenuItem>
                        {task.snooze_count < 3 && (
                            <>
                                <DropdownMenuItem onClick={() => onSnooze(task.id, 1)}>
                                    <CalendarDays className="h-4 w-4 mr-2" />
                                    +1 Tag
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => onSnooze(task.id, 3)}>
                                    <CalendarDays className="h-4 w-4 mr-2" />
                                    +3 Tage
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => onSnooze(task.id, 7)}>
                                    <CalendarDays className="h-4 w-4 mr-2" />
                                    +7 Tage
                                </DropdownMenuItem>
                            </>
                        )}
                    </DropdownMenuContent>
                </DropdownMenu>
            </TableCell>
        </TableRow>
    );
}

// ==================== Main Component ====================

function AufgabenPage() {
    const { toast } = useToast();
    const [filter, setFilter] = useState<'pending' | 'today' | 'overdue' | 'completed'>('pending');

    const { data: tasksData, isLoading, refetch } = useMahnTasks({
        status: filter === 'completed' ? 'completed' : 'pending',
    });

    const tasks = tasksData?.items ?? [];

    const completeMutation = useCompleteMahnTask();
    const snoozeMutation = useSnoozeMahnTask();

    const handleComplete = async (taskId: string) => {
        try {
            await completeMutation.mutateAsync({ taskId, outcome: 'completed' });
            toast({ title: 'Aufgabe erledigt' });
            refetch();
        } catch {
            toast({ variant: 'destructive', title: 'Fehler beim Abschliessen der Aufgabe' });
        }
    };

    const handleSnooze = async (taskId: string, days: number) => {
        try {
            const newDate = addDays(new Date(), days);
            await snoozeMutation.mutateAsync({
                taskId,
                newDueDate: newDate.toISOString().split('T')[0],
            });
            toast({ title: `Aufgabe um ${days} Tag${days > 1 ? 'e' : ''} verschoben` });
            refetch();
        } catch {
            toast({ variant: 'destructive', title: 'Aufgabe konnte nicht verschoben werden' });
        }
    };

    // Filter tasks
    const filteredTasks = tasks.filter((task) => {
        if (filter === 'today') {
            return task.due_date && isToday(new Date(task.due_date));
        }
        if (filter === 'overdue') {
            return task.due_date && isPast(new Date(task.due_date)) && !isToday(new Date(task.due_date));
        }
        return true;
    });

    const overdueTasks = tasks.filter(
        (t) => t.due_date && isPast(new Date(t.due_date)) && !isToday(new Date(t.due_date)) && t.status !== 'completed'
    );
    const todayTasks = tasks.filter(
        (t) => t.due_date && isToday(new Date(t.due_date)) && t.status !== 'completed'
    );

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-4 w-64" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[400px] w-full" />
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Alert for overdue tasks */}
            {overdueTasks.length > 0 && (
                <Card className="border-destructive bg-destructive/5">
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                            <AlertTriangle className="h-5 w-5 text-destructive" />
                            <span className="font-medium text-destructive">
                                {overdueTasks.length} ueberfaellige Aufgabe{overdueTasks.length !== 1 ? 'n' : ''}
                            </span>
                        </div>
                    </CardContent>
                </Card>
            )}

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <ClipboardList className="h-5 w-5" />
                        Mahnaufgaben
                    </CardTitle>
                    <CardDescription>
                        Anstehende Aufgaben fuer das Mahnwesen (Anrufe, Erinnerungen, Eskalationen)
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Tabs value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
                        <TabsList className="mb-4">
                            <TabsTrigger value="pending">
                                Offen
                                <Badge variant="secondary" className="ml-1.5">
                                    {tasks.filter((t) => t.status !== 'completed').length}
                                </Badge>
                            </TabsTrigger>
                            <TabsTrigger value="today">
                                Heute
                                {todayTasks.length > 0 && (
                                    <Badge variant="default" className="ml-1.5">
                                        {todayTasks.length}
                                    </Badge>
                                )}
                            </TabsTrigger>
                            <TabsTrigger value="overdue">
                                Ueberfaellig
                                {overdueTasks.length > 0 && (
                                    <Badge variant="destructive" className="ml-1.5">
                                        {overdueTasks.length}
                                    </Badge>
                                )}
                            </TabsTrigger>
                            <TabsTrigger value="completed">
                                Erledigt
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value={filter} className="mt-0">
                            {filteredTasks.length === 0 ? (
                                <div className="text-center py-12 text-muted-foreground">
                                    <ClipboardList className="h-12 w-12 mx-auto mb-3 opacity-50" />
                                    <p>Keine Aufgaben in dieser Kategorie</p>
                                </div>
                            ) : (
                                <div className="rounded-md border">
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>Typ</TableHead>
                                                <TableHead>Vorgang</TableHead>
                                                <TableHead>Beschreibung</TableHead>
                                                <TableHead>Faellig</TableHead>
                                                <TableHead>Prioritaet</TableHead>
                                                <TableHead>Verschoben</TableHead>
                                                <TableHead className="w-[50px]"></TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {filteredTasks.map((task) => (
                                                <TaskRow
                                                    key={task.id}
                                                    task={task}
                                                    onComplete={handleComplete}
                                                    onSnooze={handleSnooze}
                                                />
                                            ))}
                                        </TableBody>
                                    </Table>
                                </div>
                            )}
                        </TabsContent>
                    </Tabs>
                </CardContent>
            </Card>
        </div>
    );
}
