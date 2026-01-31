/**
 * Approvals Widget fuer Dashboard
 *
 * Zeigt ausstehende Genehmigungsanfragen:
 * - Anzahl offener Genehmigungen
 * - Kritische/ueberfaellige Anfragen
 * - Schnellzugriff auf Genehmigungsliste
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary fuer graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    CheckCircle2,
    Clock,
    AlertTriangle,
    ChevronRight,
    XCircle,
    Loader2,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface ApprovalSummary {
    total_pending: number;
    total_approved: number;
    total_rejected: number;
    total_escalated: number;
    avg_resolution_hours: number;
    overdue_count: number;
    my_pending: number;
}

interface ApprovalRequest {
    id: string;
    title: string;
    entity_type: string;
    amount: string | null;
    currency: string;
    priority: string;
    status: string;
    current_step: number;
    total_steps: number;
    due_date: string | null;
    created_at: string;
}

// API Hooks
function useApprovalSummary() {
    return useQuery({
        queryKey: ['approvals', 'summary'],
        queryFn: async (): Promise<ApprovalSummary> => {
            const response = await api.get('/api/v1/approvals/summary');
            return response.data;
        },
        staleTime: 60 * 1000, // 1 minute
        refetchInterval: 60 * 1000,
    });
}

function useMyPendingApprovals(limit: number = 5) {
    return useQuery({
        queryKey: ['approvals', 'my-pending', { limit }],
        queryFn: async (): Promise<{ requests: ApprovalRequest[]; total: number }> => {
            const response = await api.get('/api/v1/approvals/requests', {
                params: {
                    my_pending: true,
                    status_filter: 'pending',
                    limit,
                },
            });
            return response.data;
        },
        staleTime: 30 * 1000,
    });
}

// Helper functions
const formatCurrency = (value: string | null, currency: string = 'EUR'): string => {
    if (!value) return '-';
    const numValue = parseFloat(value);
    if (isNaN(numValue)) return value;

    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency,
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
    }).format(numValue);
};

const getPriorityColor = (priority: string): string => {
    switch (priority) {
        case 'critical':
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
        case 'high':
            return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200';
        case 'normal':
            return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200';
        case 'low':
            return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
        default:
            return 'bg-gray-100 text-gray-800';
    }
};

const getPriorityLabel = (priority: string): string => {
    const labels: Record<string, string> = {
        critical: 'Kritisch',
        high: 'Hoch',
        normal: 'Normal',
        low: 'Niedrig',
    };
    return labels[priority] || priority;
};

const getEntityTypeLabel = (type: string): string => {
    const labels: Record<string, string> = {
        invoice: 'Rechnung',
        expense: 'Ausgabe',
        document: 'Dokument',
        contract: 'Vertrag',
        purchase_order: 'Bestellung',
    };
    return labels[type] || type;
};

// Components
function ApprovalItem({ request }: { request: ApprovalRequest }) {
    const isOverdue = request.due_date && new Date(request.due_date) < new Date();

    return (
        <Link
            to="/workflows"
            search={{ requestId: request.id }}
            className="block"
        >
            <div className={cn(
                'p-3 rounded-lg border transition-colors hover:bg-accent/50',
                isOverdue && 'border-red-200 dark:border-red-800'
            )}>
                <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm truncate">
                            {request.title}
                        </p>
                        <p className="text-xs text-muted-foreground">
                            {getEntityTypeLabel(request.entity_type)}
                            {request.amount && ` • ${formatCurrency(request.amount, request.currency)}`}
                        </p>
                    </div>
                    <Badge
                        variant="outline"
                        className={cn('text-xs shrink-0', getPriorityColor(request.priority))}
                    >
                        {getPriorityLabel(request.priority)}
                    </Badge>
                </div>

                <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                    <span>
                        Schritt {request.current_step}/{request.total_steps}
                    </span>
                    {isOverdue ? (
                        <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                            <AlertTriangle className="h-3 w-3" />
                            Ueberfaellig
                        </span>
                    ) : request.due_date && (
                        <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            Faellig: {new Date(request.due_date).toLocaleDateString('de-DE')}
                        </span>
                    )}
                </div>
            </div>
        </Link>
    );
}

function ApprovalsWidgetContent() {
    // Real-time updates
    useWidgetSubscription('approvals', {
        debounceMs: 500,
        autoInvalidate: true,
        queryKeysToInvalidate: [['approvals']],
    });

    const {
        data: summary,
        isLoading: summaryLoading,
        isError: summaryError,
    } = useApprovalSummary();

    const {
        data: pendingData,
        isLoading: pendingLoading,
    } = useMyPendingApprovals(5);

    const isLoading = summaryLoading || pendingLoading;

    if (isLoading) {
        return (
            <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                    {[1, 2, 3, 4].map((i) => (
                        <Skeleton key={i} className="h-16 rounded-lg" />
                    ))}
                </div>
                <Skeleton className="h-32 rounded-lg" />
            </div>
        );
    }

    if (summaryError || !summary) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">Genehmigungsdaten nicht verfuegbar</p>
            </div>
        );
    }

    const hasUrgent = summary.overdue_count > 0 || summary.total_escalated > 0;

    return (
        <div className="space-y-4">
            {/* Summary Stats */}
            <div className="grid grid-cols-2 gap-3">
                <div className={cn(
                    'p-3 rounded-lg border',
                    summary.my_pending > 0
                        ? 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800'
                        : 'bg-muted/30'
                )}>
                    <div className="flex items-center gap-2">
                        <Clock className={cn(
                            'h-4 w-4',
                            summary.my_pending > 0 ? 'text-orange-600' : 'text-muted-foreground'
                        )} />
                        <span className="text-xs font-medium text-muted-foreground">
                            Meine Aufgaben
                        </span>
                    </div>
                    <p className="text-2xl font-bold mt-1">{summary.my_pending}</p>
                </div>

                <div className={cn(
                    'p-3 rounded-lg border',
                    hasUrgent
                        ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                        : 'bg-muted/30'
                )}>
                    <div className="flex items-center gap-2">
                        <AlertTriangle className={cn(
                            'h-4 w-4',
                            hasUrgent ? 'text-red-600' : 'text-muted-foreground'
                        )} />
                        <span className="text-xs font-medium text-muted-foreground">
                            Ueberfaellig
                        </span>
                    </div>
                    <p className="text-2xl font-bold mt-1">{summary.overdue_count}</p>
                </div>

                <div className="p-3 rounded-lg border bg-muted/30">
                    <div className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                        <span className="text-xs font-medium text-muted-foreground">
                            Genehmigt
                        </span>
                    </div>
                    <p className="text-2xl font-bold mt-1">{summary.total_approved}</p>
                </div>

                <div className="p-3 rounded-lg border bg-muted/30">
                    <div className="flex items-center gap-2">
                        <XCircle className="h-4 w-4 text-red-600" />
                        <span className="text-xs font-medium text-muted-foreground">
                            Abgelehnt
                        </span>
                    </div>
                    <p className="text-2xl font-bold mt-1">{summary.total_rejected}</p>
                </div>
            </div>

            {/* Pending Approvals List */}
            {pendingData && pendingData.requests.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-sm font-medium text-muted-foreground">
                        Wartende Genehmigungen
                    </h4>
                    <div className="space-y-2">
                        {pendingData.requests.slice(0, 3).map((request) => (
                            <ApprovalItem key={request.id} request={request} />
                        ))}
                    </div>
                </div>
            )}

            {/* Empty State */}
            {summary.my_pending === 0 && (
                <div className="text-center py-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                    <CheckCircle2 className="h-8 w-8 text-green-600 mx-auto mb-2" />
                    <p className="text-sm font-medium text-green-800 dark:text-green-200">
                        Keine ausstehenden Genehmigungen
                    </p>
                </div>
            )}

            {/* Link to full list */}
            <Link
                to="/workflows"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                Alle Genehmigungen anzeigen
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function ApprovalsWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Genehmigungen" />}
            errorTitle="Genehmigungen Fehler"
            errorDescription="Die Genehmigungsdaten konnten nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <CheckCircle2 className="h-5 w-5 text-primary" />
                        Genehmigungen
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <ApprovalsWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
