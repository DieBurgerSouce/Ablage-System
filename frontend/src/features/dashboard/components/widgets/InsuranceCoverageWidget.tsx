/**
 * Insurance Coverage Widget fuer Dashboard
 *
 * Zeigt Versicherungsschutz-Uebersicht:
 * - Deckungsluecken
 * - Kuendigungsfristen
 * - Praemien-Uebersicht
 * - Status der Policen
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary fuer graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    ShieldCheck,
    ShieldAlert,
    ShieldX,
    ChevronRight,
    AlertTriangle,
    Clock,
    Euro,
    Calendar,
    CheckCircle2,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface CoverageGap {
    category: string;
    description: string;
    risk_level: 'low' | 'medium' | 'high';
    recommendation: string;
}

interface UpcomingDeadline {
    policy_id: string;
    policy_name: string;
    deadline_type: 'cancellation' | 'renewal' | 'payment';
    deadline_date: string;
    days_remaining: number;
}

interface InsuranceSummary {
    total_policies: number;
    active_policies: number;
    total_annual_premium: number;
    coverage_score: number;
    coverage_gaps: CoverageGap[];
    upcoming_deadlines: UpcomingDeadline[];
    currency: string;
}

// API Hook
function useInsuranceSummary() {
    return useQuery({
        queryKey: ['insurance', 'summary'],
        queryFn: async (): Promise<InsuranceSummary> => {
            const response = await api.get('/api/v1/insurance/summary');
            return response.data;
        },
        staleTime: 10 * 60 * 1000, // 10 minutes
        refetchInterval: 10 * 60 * 1000,
    });
}

// Helper functions
const formatCurrency = (value: number, currency: string = 'EUR'): string => {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency,
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
};

const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    });
};

const getRiskColor = (level: string): string => {
    switch (level) {
        case 'high':
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
        case 'medium':
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200';
        case 'low':
            return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200';
        default:
            return 'bg-gray-100 text-gray-800';
    }
};

const getRiskLabel = (level: string): string => {
    const labels: Record<string, string> = {
        high: 'Hoch',
        medium: 'Mittel',
        low: 'Gering',
    };
    return labels[level] || level;
};

const getDeadlineTypeLabel = (type: string): string => {
    const labels: Record<string, string> = {
        cancellation: 'Kuendigungsfrist',
        renewal: 'Verlaengerung',
        payment: 'Zahlung',
    };
    return labels[type] || type;
};

const getCoverageScoreColor = (score: number): string => {
    if (score >= 80) return 'text-green-600';
    if (score >= 60) return 'text-yellow-600';
    return 'text-red-600';
};

const getCoverageScoreIcon = (score: number) => {
    if (score >= 80) return ShieldCheck;
    if (score >= 60) return ShieldAlert;
    return ShieldX;
};

// Components
function CoverageGapItem({ gap }: { gap: CoverageGap }) {
    return (
        <div className="p-2 rounded-lg border bg-muted/30">
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <p className="text-sm font-medium">{gap.category}</p>
                    <p className="text-xs text-muted-foreground line-clamp-1">
                        {gap.description}
                    </p>
                </div>
                <Badge
                    variant="outline"
                    className={cn('text-xs shrink-0', getRiskColor(gap.risk_level))}
                >
                    {getRiskLabel(gap.risk_level)}
                </Badge>
            </div>
        </div>
    );
}

function DeadlineItem({ deadline }: { deadline: UpcomingDeadline }) {
    const isUrgent = deadline.days_remaining <= 14;
    const isWarning = deadline.days_remaining <= 30;

    return (
        <div className={cn(
            'p-2 rounded-lg border',
            isUrgent
                ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                : isWarning
                    ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                    : 'bg-muted/30'
        )}>
            <div className="flex items-center justify-between">
                <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                        {deadline.policy_name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                        {getDeadlineTypeLabel(deadline.deadline_type)}
                    </p>
                </div>
                <div className="text-right shrink-0">
                    <p className={cn(
                        'text-sm font-medium',
                        isUrgent ? 'text-red-600' : isWarning ? 'text-yellow-600' : ''
                    )}>
                        {deadline.days_remaining} Tage
                    </p>
                    <p className="text-xs text-muted-foreground">
                        {formatDate(deadline.deadline_date)}
                    </p>
                </div>
            </div>
        </div>
    );
}

function InsuranceCoverageWidgetContent() {
    // Real-time updates
    useWidgetSubscription('insurance', {
        debounceMs: 1000,
        autoInvalidate: true,
        queryKeysToInvalidate: [['insurance']],
    });

    const {
        data: summary,
        isLoading,
        isError,
    } = useInsuranceSummary();

    if (isLoading) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-20 rounded-lg" />
                <div className="space-y-2">
                    {[1, 2].map((i) => (
                        <Skeleton key={i} className="h-16 rounded-lg" />
                    ))}
                </div>
            </div>
        );
    }

    if (isError || !summary) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">Versicherungsdaten nicht verfuegbar</p>
            </div>
        );
    }

    const ScoreIcon = getCoverageScoreIcon(summary.coverage_score);
    const hasGaps = summary.coverage_gaps.length > 0;
    const hasUrgentDeadlines = summary.upcoming_deadlines.some(d => d.days_remaining <= 14);

    return (
        <div className="space-y-4">
            {/* Coverage Score */}
            <div className={cn(
                'p-4 rounded-lg border',
                summary.coverage_score >= 80
                    ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                    : summary.coverage_score >= 60
                        ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                        : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
            )}>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <ScoreIcon className={cn('h-8 w-8', getCoverageScoreColor(summary.coverage_score))} />
                        <div>
                            <p className="text-sm font-medium text-muted-foreground">
                                Abdeckungsgrad
                            </p>
                            <p className={cn('text-2xl font-bold', getCoverageScoreColor(summary.coverage_score))}>
                                {summary.coverage_score}%
                            </p>
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="text-xs text-muted-foreground">
                            {summary.active_policies}/{summary.total_policies} Policen aktiv
                        </p>
                        <p className="text-sm font-medium">
                            {formatCurrency(summary.total_annual_premium, summary.currency)}/Jahr
                        </p>
                    </div>
                </div>
            </div>

            {/* Coverage Gaps Warning */}
            {hasGaps && (
                <Alert variant="destructive" className="py-2">
                    <ShieldAlert className="h-4 w-4" />
                    <AlertDescription className="text-xs">
                        {summary.coverage_gaps.length} Deckungsluecke{summary.coverage_gaps.length > 1 ? 'n' : ''} erkannt
                    </AlertDescription>
                </Alert>
            )}

            {/* Coverage Gaps */}
            {summary.coverage_gaps.length > 0 && (
                <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">
                        Deckungsluecken
                    </p>
                    {summary.coverage_gaps.slice(0, 2).map((gap, index) => (
                        <CoverageGapItem key={index} gap={gap} />
                    ))}
                </div>
            )}

            {/* Upcoming Deadlines */}
            {summary.upcoming_deadlines.length > 0 && (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-muted-foreground" />
                        <p className="text-xs font-medium text-muted-foreground">
                            Anstehende Fristen
                        </p>
                    </div>
                    {summary.upcoming_deadlines.slice(0, 2).map((deadline) => (
                        <DeadlineItem key={deadline.policy_id} deadline={deadline} />
                    ))}
                </div>
            )}

            {/* All OK State */}
            {!hasGaps && summary.upcoming_deadlines.length === 0 && (
                <div className="text-center py-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                    <CheckCircle2 className="h-8 w-8 text-green-600 mx-auto mb-2" />
                    <p className="text-sm font-medium text-green-800 dark:text-green-200">
                        Versicherungsschutz vollstaendig
                    </p>
                    <p className="text-xs text-green-600 dark:text-green-400">
                        Keine Luecken oder dringenden Fristen
                    </p>
                </div>
            )}

            {/* Link to insurance page */}
            <Link
                to="/portfolio/insurance"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                Alle Versicherungen anzeigen
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function InsuranceCoverageWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Versicherungen" />}
            errorTitle="Versicherungen Fehler"
            errorDescription="Die Versicherungsdaten konnten nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <ShieldCheck className="h-5 w-5 text-primary" />
                        Versicherungsschutz
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <InsuranceCoverageWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
