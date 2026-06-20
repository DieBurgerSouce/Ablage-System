/**
 * Compliance Deadline Widget für Dashboard
 *
 * Zeigt Compliance-Fristen und Aufbewahrungspflichten:
 * - GoBD-Fristen (10 Jahre)
 * - Audit-Termine
 * - GDPR-Loeschfristen
 * - Vertragsfristen
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    Scale,
    Calendar,
    AlertTriangle,
    ChevronRight,
    Clock,
    FileCheck,
    Shield,
    Trash2,
    CheckCircle2,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface ComplianceDeadline {
    id: string;
    title: string;
    category: 'gobd' | 'gdpr' | 'audit' | 'contract' | 'tax' | 'retention';
    deadline_date: string;
    days_remaining: number;
    severity: 'info' | 'warning' | 'critical';
    affected_items: number;
    action_required: string;
}

interface ComplianceSummary {
    total_deadlines: number;
    critical_count: number;
    warning_count: number;
    upcoming_7_days: number;
    upcoming_30_days: number;
    compliance_score: number;
    deadlines: ComplianceDeadline[];
    retention_summary: {
        gobd_compliant: number;
        gobd_total: number;
        gdpr_pending_deletion: number;
    };
}

// API Hook
function useComplianceSummary() {
    return useQuery({
        queryKey: ['compliance', 'summary'],
        queryFn: async (): Promise<ComplianceSummary> => {
            const response = await api.get('/compliance/summary');
            return response.data;
        },
        staleTime: 5 * 60 * 1000, // 5 minutes
        refetchInterval: 5 * 60 * 1000,
    });
}

// Helper functions

const getCategoryIcon = (category: string) => {
    switch (category) {
        case 'gobd':
            return FileCheck;
        case 'gdpr':
            return Shield;
        case 'audit':
            return Scale;
        case 'contract':
            return Calendar;
        case 'tax':
            return FileCheck;
        case 'retention':
            return Trash2;
        default:
            return Clock;
    }
};

const getCategoryLabel = (category: string): string => {
    const labels: Record<string, string> = {
        gobd: 'GoBD',
        gdpr: 'DSGVO',
        audit: 'Audit',
        contract: 'Vertrag',
        tax: 'Steuer',
        retention: 'Aufbewahrung',
    };
    return labels[category] || category;
};

const getSeverityColor = (severity: string): string => {
    switch (severity) {
        case 'critical':
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
        case 'warning':
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200';
        case 'info':
            return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200';
        default:
            return 'bg-gray-100 text-gray-800';
    }
};

const getScoreColor = (score: number): string => {
    if (score >= 90) return 'text-green-600';
    if (score >= 70) return 'text-yellow-600';
    return 'text-red-600';
};


// Components
function DeadlineItem({ deadline }: { deadline: ComplianceDeadline }) {
    const CategoryIcon = getCategoryIcon(deadline.category);
    const isCritical = deadline.severity === 'critical';
    const isWarning = deadline.severity === 'warning';

    return (
        <div className={cn(
            'p-3 rounded-lg border',
            isCritical && 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
            isWarning && 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
            !isCritical && !isWarning && 'bg-muted/30'
        )}>
            <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2 min-w-0">
                    <CategoryIcon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                        <p className="text-sm font-medium line-clamp-1">
                            {deadline.title}
                        </p>
                        <p className="text-xs text-muted-foreground">
                            {getCategoryLabel(deadline.category)} • {deadline.affected_items} Elemente
                        </p>
                    </div>
                </div>
                <Badge
                    variant="outline"
                    className={cn('text-xs shrink-0', getSeverityColor(deadline.severity))}
                >
                    {deadline.days_remaining} Tage
                </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-2 line-clamp-1">
                {deadline.action_required}
            </p>
        </div>
    );
}

function ComplianceDeadlineWidgetContent() {
    // Real-time updates
    useWidgetSubscription('compliance', {
        debounceMs: 1000,
        autoInvalidate: true,
        queryKeysToInvalidate: [['compliance']],
    });

    const {
        data: summary,
        isLoading,
        isError,
    } = useComplianceSummary();

    if (isLoading) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-20 rounded-lg" />
                <div className="space-y-2">
                    {[1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-20 rounded-lg" />
                    ))}
                </div>
            </div>
        );
    }

    if (isError || !summary) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">Compliance-Daten nicht verfügbar</p>
            </div>
        );
    }

    const hasCritical = summary.critical_count > 0;
    const hasWarning = summary.warning_count > 0;
    const gobdPercentage = summary.retention_summary.gobd_total > 0
        ? (summary.retention_summary.gobd_compliant / summary.retention_summary.gobd_total) * 100
        : 100;

    return (
        <div className="space-y-4">
            {/* Compliance Score */}
            <div className={cn(
                'p-4 rounded-lg border',
                summary.compliance_score >= 90
                    ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                    : summary.compliance_score >= 70
                        ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                        : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
            )}>
                <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                        <Scale className="h-5 w-5 text-primary" />
                        <span className="text-sm font-medium">Compliance Score</span>
                    </div>
                    <span className={cn('text-2xl font-bold', getScoreColor(summary.compliance_score))}>
                        {summary.compliance_score}%
                    </span>
                </div>
                <Progress
                    value={summary.compliance_score}
                    className="h-2"
                />
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-3 gap-2">
                <div className={cn(
                    'p-2 rounded-lg text-center',
                    hasCritical ? 'bg-red-50 dark:bg-red-900/20' : 'bg-muted/30'
                )}>
                    <p className={cn('text-lg font-bold', hasCritical && 'text-red-600')}>
                        {summary.critical_count}
                    </p>
                    <p className="text-xs text-muted-foreground">Kritisch</p>
                </div>
                <div className={cn(
                    'p-2 rounded-lg text-center',
                    hasWarning ? 'bg-yellow-50 dark:bg-yellow-900/20' : 'bg-muted/30'
                )}>
                    <p className={cn('text-lg font-bold', hasWarning && 'text-yellow-600')}>
                        {summary.warning_count}
                    </p>
                    <p className="text-xs text-muted-foreground">Warnungen</p>
                </div>
                <div className="p-2 rounded-lg text-center bg-muted/30">
                    <p className="text-lg font-bold">{summary.upcoming_7_days}</p>
                    <p className="text-xs text-muted-foreground">7 Tage</p>
                </div>
            </div>

            {/* GoBD Status */}
            <div className="p-3 rounded-lg border bg-muted/30">
                <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-muted-foreground">
                        GoBD-Konformitaet
                    </span>
                    <span className="text-sm font-medium">
                        {summary.retention_summary.gobd_compliant}/{summary.retention_summary.gobd_total}
                    </span>
                </div>
                <Progress value={gobdPercentage} className="h-1.5" />
                {summary.retention_summary.gdpr_pending_deletion > 0 && (
                    <p className="text-xs text-muted-foreground mt-2">
                        {summary.retention_summary.gdpr_pending_deletion} DSGVO-Löschungen ausstehend
                    </p>
                )}
            </div>

            {/* Upcoming Deadlines */}
            {summary.deadlines.length > 0 ? (
                <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">
                        Anstehende Fristen
                    </p>
                    {summary.deadlines.slice(0, 3).map((deadline) => (
                        <DeadlineItem key={deadline.id} deadline={deadline} />
                    ))}
                </div>
            ) : (
                <div className="text-center py-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                    <CheckCircle2 className="h-8 w-8 text-green-600 mx-auto mb-2" />
                    <p className="text-sm font-medium text-green-800 dark:text-green-200">
                        Keine dringenden Fristen
                    </p>
                </div>
            )}

            {/* Link to compliance page */}
            <Link
                to="/compliance"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                Compliance-Übersicht
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function ComplianceDeadlineWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Compliance" />}
            errorTitle="Compliance Fehler"
            errorDescription="Die Compliance-Daten konnten nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Scale className="h-5 w-5 text-primary" />
                        Compliance & Fristen
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <ComplianceDeadlineWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
