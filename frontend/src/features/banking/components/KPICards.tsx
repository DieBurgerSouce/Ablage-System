/**
 * KPI Cards fuer Banking Dashboard
 * Zeigt 6 wichtige Kennzahlen im Grid-Layout
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
    ArrowUpRight,
    ArrowDownRight,
    Wallet,
    Receipt,
    AlertTriangle,
    Clock,
    CheckCircle2,
    TrendingUp,
} from 'lucide-react';
import { useAgingSummary, useCashFlowSummary, useDunningStats, useTransactionStats, useDSO } from '../hooks/use-banking-queries';
import { cn } from '@/lib/utils';

interface KPICardProps {
    title: string;
    value: string | number;
    subtitle?: string;
    icon: React.ReactNode;
    trend?: {
        value: number;
        label: string;
        isPositive?: boolean;
    };
    badge?: {
        label: string;
        variant: 'default' | 'secondary' | 'destructive' | 'outline';
    };
    isLoading?: boolean;
}

function KPICard({ title, value, subtitle, icon, trend, badge, isLoading }: KPICardProps) {
    if (isLoading) {
        return (
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-4 w-4" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-8 w-32 mb-1" />
                    <Skeleton className="h-3 w-20" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card role="region" aria-label={`KPI: ${title}`}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
                <div className="text-muted-foreground" aria-hidden="true">{icon}</div>
            </CardHeader>
            <CardContent>
                <div className="flex items-baseline gap-2">
                    <div className="text-2xl font-bold">{value}</div>
                    {badge && (
                        <Badge variant={badge.variant} className="text-xs">
                            {badge.label}
                        </Badge>
                    )}
                </div>
                {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
                {trend && (
                    <div className={cn(
                        'flex items-center gap-1 text-xs mt-2',
                        trend.isPositive ? 'text-green-600' : 'text-red-600'
                    )}>
                        {trend.isPositive ? (
                            <ArrowUpRight className="h-3 w-3" />
                        ) : (
                            <ArrowDownRight className="h-3 w-3" />
                        )}
                        <span>{trend.value}%</span>
                        <span className="text-muted-foreground">{trend.label}</span>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

function formatCurrency(value: number): string {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
}

function formatPercent(value: number): string {
    return new Intl.NumberFormat('de-DE', {
        style: 'percent',
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
    }).format(value / 100);
}

export function KPICards() {
    const { data: agingSummary, isLoading: agingLoading } = useAgingSummary();
    const { data: cashFlowSummary, isLoading: cashFlowLoading } = useCashFlowSummary();
    const { data: dunningStats, isLoading: dunningLoading } = useDunningStats();
    const { data: transactionStats, isLoading: transactionLoading } = useTransactionStats();
    const { data: dsoData, isLoading: dsoLoading } = useDSO(90);

    const isLoading = agingLoading || cashFlowLoading || dunningLoading || transactionLoading || dsoLoading;

    // Berechne ueberfaelligen Anteil der Forderungen
    const receivablesOverduePercent = agingSummary?.receivables?.total_amount
        ? (agingSummary.receivables.total_overdue / agingSummary.receivables.total_amount) * 100
        : 0;

    // Liquiditaetsprognose 7 Tage
    const liquidityWarning = cashFlowSummary?.warnings && cashFlowSummary.warnings.length > 0;
    const shortTermLiquidity = cashFlowSummary?.short_term?.ending_balance ?? 0;

    // Abgleich-Quote
    const matchRate = transactionStats?.match_rate ?? 0;

    // Aktive Mahnungen
    const activeDunnings = dunningStats?.total_active ?? 0;

    // DSO
    const currentDSO = dsoData?.dso ?? 0;

    return (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6" role="region" aria-label="Banking KPI Übersicht">
            {/* Offene Forderungen */}
            <KPICard
                title="Offene Forderungen"
                value={formatCurrency(agingSummary?.receivables?.total_amount ?? 0)}
                subtitle={`${agingSummary?.receivables?.total_count ?? 0} Rechnungen`}
                icon={<ArrowUpRight className="h-4 w-4" />}
                badge={
                    receivablesOverduePercent > 20
                        ? { label: `${receivablesOverduePercent.toFixed(0)}% überfällig`, variant: 'destructive' }
                        : receivablesOverduePercent > 0
                        ? { label: `${receivablesOverduePercent.toFixed(0)}% überfällig`, variant: 'secondary' }
                        : undefined
                }
                isLoading={isLoading}
            />

            {/* Offene Verbindlichkeiten */}
            <KPICard
                title="Offene Verbindlichkeiten"
                value={formatCurrency(agingSummary?.payables?.total_amount ?? 0)}
                subtitle={`${agingSummary?.payables?.total_count ?? 0} Rechnungen`}
                icon={<ArrowDownRight className="h-4 w-4" />}
                isLoading={isLoading}
            />

            {/* Liquiditaet 7 Tage */}
            <KPICard
                title="Liquidität 7 Tage"
                value={formatCurrency(shortTermLiquidity)}
                subtitle={cashFlowSummary?.short_term ? `Netto: ${formatCurrency(cashFlowSummary.short_term.net)}` : undefined}
                icon={<Wallet className="h-4 w-4" />}
                badge={
                    liquidityWarning
                        ? { label: 'Warnung', variant: 'destructive' }
                        : shortTermLiquidity > 0
                        ? { label: 'OK', variant: 'default' }
                        : undefined
                }
                isLoading={isLoading}
            />

            {/* Abgleich-Quote */}
            <KPICard
                title="Abgleich-Quote"
                value={formatPercent(matchRate)}
                subtitle={`${transactionStats?.matched_count ?? 0} von ${transactionStats?.total_count ?? 0}`}
                icon={<CheckCircle2 className="h-4 w-4" />}
                badge={
                    matchRate >= 90
                        ? { label: 'Gut', variant: 'default' }
                        : matchRate >= 70
                        ? { label: 'Mittel', variant: 'secondary' }
                        : { label: 'Niedrig', variant: 'destructive' }
                }
                isLoading={isLoading}
            />

            {/* Aktive Mahnungen */}
            <KPICard
                title="Aktive Mahnungen"
                value={activeDunnings}
                subtitle={dunningStats ? `${formatCurrency(dunningStats.total_amount_overdue)} überfällig` : undefined}
                icon={<AlertTriangle className="h-4 w-4" />}
                badge={
                    activeDunnings > 10
                        ? { label: 'Kritisch', variant: 'destructive' }
                        : activeDunnings > 5
                        ? { label: 'Mittel', variant: 'secondary' }
                        : undefined
                }
                isLoading={isLoading}
            />

            {/* DSO */}
            <KPICard
                title="DSO"
                value={`${currentDSO.toFixed(0)} Tage`}
                subtitle={dsoData?.interpretation ?? 'Days Sales Outstanding'}
                icon={<Clock className="h-4 w-4" />}
                badge={
                    currentDSO <= 30
                        ? { label: 'Ausgezeichnet', variant: 'default' }
                        : currentDSO <= 45
                        ? { label: 'Gut', variant: 'secondary' }
                        : currentDSO <= 60
                        ? { label: 'Akzeptabel', variant: 'outline' }
                        : { label: 'Kritisch', variant: 'destructive' }
                }
                isLoading={isLoading}
            />
        </div>
    );
}
