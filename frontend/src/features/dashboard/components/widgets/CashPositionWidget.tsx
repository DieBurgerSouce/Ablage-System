/**
 * Cash Position Widget für Dashboard
 *
 * Zeigt Echtzeit-Kassenstand und Liquidität:
 * - Aktueller Kontostand (alle Konten)
 * - Tagesbewegungen
 * - Liquiditätsprognose
 * - Kritische Zahlungen
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    Wallet,
    TrendingUp,
    TrendingDown,
    ChevronRight,
    AlertTriangle,
    ArrowUpRight,
    ArrowDownRight,
    Building,
    CalendarClock,
    Banknote,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface BankAccountBalance {
    account_id: string;
    account_name: string;
    bank_name: string;
    balance: number;
    currency: string;
    last_sync: string;
}

interface DailyMovement {
    date: string;
    inflows: number;
    outflows: number;
    net: number;
}

interface UpcomingPayment {
    id: string;
    description: string;
    amount: number;
    due_date: string;
    days_until_due: number;
    type: 'inflow' | 'outflow';
    is_critical: boolean;
}

interface CashPositionSummary {
    total_balance: number;
    currency: string;
    balance_change_today: number;
    balance_change_percent: number;
    accounts: BankAccountBalance[];
    today_movements: DailyMovement;
    forecast_7_days: number;
    forecast_30_days: number;
    upcoming_payments: UpcomingPayment[];
    liquidity_status: 'healthy' | 'warning' | 'critical';
    last_updated: string;
}

// API Hook
function useCashPosition() {
    return useQuery({
        queryKey: ['banking', 'cash-position'],
        queryFn: async (): Promise<CashPositionSummary> => {
            const response = await api.get('/api/v1/banking/cash-position');
            return response.data;
        },
        staleTime: 60 * 1000, // 1 minute
        refetchInterval: 2 * 60 * 1000, // 2 minutes
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

const formatCurrencyCompact = (value: number, currency: string = 'EUR'): string => {
    const absValue = Math.abs(value);
    if (absValue >= 1000000) {
        return `${(value / 1000000).toFixed(1)}M ${currency}`;
    }
    if (absValue >= 1000) {
        return `${(value / 1000).toFixed(1)}K ${currency}`;
    }
    return formatCurrency(value, currency);
};

const formatPercent = (value: number): string => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(1)}%`;
};

const formatRelativeTime = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Gerade aktualisiert';
    if (diffMins < 60) return `vor ${diffMins} Min.`;

    return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
};

const getLiquidityColor = (status: string): string => {
    switch (status) {
        case 'healthy':
            return 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800';
        case 'warning':
            return 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800';
        case 'critical':
            return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';
        default:
            return 'bg-muted/30';
    }
};

const getLiquidityTextColor = (status: string): string => {
    switch (status) {
        case 'healthy':
            return 'text-green-600';
        case 'warning':
            return 'text-yellow-600';
        case 'critical':
            return 'text-red-600';
        default:
            return '';
    }
};

// Components
function AccountBalanceItem({ account }: { account: BankAccountBalance }) {
    return (
        <div className="flex items-center justify-between py-1.5">
            <div className="flex items-center gap-2 min-w-0">
                <Building className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="text-xs truncate">{account.account_name}</span>
            </div>
            <span className="text-xs font-medium">
                {formatCurrency(account.balance, account.currency)}
            </span>
        </div>
    );
}

function UpcomingPaymentItem({ payment }: { payment: UpcomingPayment }) {
    const isInflow = payment.type === 'inflow';

    return (
        <div className={cn(
            'p-2 rounded-lg border',
            payment.is_critical && 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
            !payment.is_critical && 'bg-muted/30'
        )}>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                    {isInflow ? (
                        <ArrowDownRight className="h-3 w-3 text-green-600 shrink-0" />
                    ) : (
                        <ArrowUpRight className="h-3 w-3 text-red-600 shrink-0" />
                    )}
                    <span className="text-xs font-medium truncate">
                        {payment.description}
                    </span>
                </div>
                <span className={cn(
                    'text-xs font-medium',
                    isInflow ? 'text-green-600' : 'text-red-600'
                )}>
                    {isInflow ? '+' : '-'}{formatCurrency(Math.abs(payment.amount))}
                </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
                {payment.days_until_due === 0 ? 'Heute' :
                 payment.days_until_due === 1 ? 'Morgen' :
                 `in ${payment.days_until_due} Tagen`}
            </p>
        </div>
    );
}

function CashPositionWidgetContent() {
    // Real-time updates
    useWidgetSubscription('cash-position', {
        debounceMs: 500,
        autoInvalidate: true,
        queryKeysToInvalidate: [['banking', 'cash-position']],
    });

    const {
        data: summary,
        isLoading,
        isError,
    } = useCashPosition();

    if (isLoading) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-20 rounded-lg" />
                <div className="grid grid-cols-2 gap-2">
                    <Skeleton className="h-16 rounded-lg" />
                    <Skeleton className="h-16 rounded-lg" />
                </div>
                <Skeleton className="h-24 rounded-lg" />
            </div>
        );
    }

    if (isError || !summary) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">Kontodaten nicht verfügbar</p>
            </div>
        );
    }

    const isPositiveChange = summary.balance_change_today >= 0;
    const TrendIcon = isPositiveChange ? TrendingUp : TrendingDown;
    const hasCriticalPayments = summary.upcoming_payments.some(p => p.is_critical);

    return (
        <div className="space-y-4">
            {/* Total Balance */}
            <div className={cn('p-4 rounded-lg border', getLiquidityColor(summary.liquidity_status))}>
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs font-medium text-muted-foreground">
                            Gesamtsaldo
                        </p>
                        <p className={cn('text-2xl font-bold', getLiquidityTextColor(summary.liquidity_status))}>
                            {formatCurrency(summary.total_balance, summary.currency)}
                        </p>
                    </div>
                    <div className={cn(
                        'flex items-center gap-1 px-2 py-1 rounded',
                        isPositiveChange
                            ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300'
                            : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300'
                    )}>
                        <TrendIcon className="h-4 w-4" />
                        <span className="text-sm font-medium">
                            {formatPercent(summary.balance_change_percent)}
                        </span>
                    </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                    {isPositiveChange ? '+' : ''}{formatCurrency(summary.balance_change_today, summary.currency)} heute
                    {' '}• {formatRelativeTime(summary.last_updated)}
                </p>
            </div>

            {/* Today's Movements */}
            <div className="grid grid-cols-2 gap-2">
                <div className="p-3 rounded-lg border bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
                    <div className="flex items-center gap-1 mb-1">
                        <ArrowDownRight className="h-3 w-3 text-green-600" />
                        <span className="text-xs font-medium text-muted-foreground">
                            Eingänge
                        </span>
                    </div>
                    <p className="text-lg font-bold text-green-600">
                        +{formatCurrencyCompact(summary.today_movements.inflows, summary.currency)}
                    </p>
                </div>
                <div className="p-3 rounded-lg border bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
                    <div className="flex items-center gap-1 mb-1">
                        <ArrowUpRight className="h-3 w-3 text-red-600" />
                        <span className="text-xs font-medium text-muted-foreground">
                            Ausgänge
                        </span>
                    </div>
                    <p className="text-lg font-bold text-red-600">
                        -{formatCurrencyCompact(Math.abs(summary.today_movements.outflows), summary.currency)}
                    </p>
                </div>
            </div>

            {/* Forecast */}
            <div className="p-3 rounded-lg border bg-muted/30">
                <div className="flex items-center gap-2 mb-2">
                    <CalendarClock className="h-4 w-4 text-muted-foreground" />
                    <span className="text-xs font-medium text-muted-foreground">
                        Liquiditätsprognose
                    </span>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                        <span className="text-muted-foreground">7 Tage: </span>
                        <span className={cn(
                            'font-medium',
                            summary.forecast_7_days >= 0 ? 'text-green-600' : 'text-red-600'
                        )}>
                            {formatCurrency(summary.forecast_7_days, summary.currency)}
                        </span>
                    </div>
                    <div>
                        <span className="text-muted-foreground">30 Tage: </span>
                        <span className={cn(
                            'font-medium',
                            summary.forecast_30_days >= 0 ? 'text-green-600' : 'text-red-600'
                        )}>
                            {formatCurrency(summary.forecast_30_days, summary.currency)}
                        </span>
                    </div>
                </div>
            </div>

            {/* Account Breakdown */}
            {summary.accounts.length > 0 && (
                <div className="p-3 rounded-lg border bg-muted/30">
                    <p className="text-xs font-medium text-muted-foreground mb-2">
                        Konten ({summary.accounts.length})
                    </p>
                    <div className="divide-y">
                        {summary.accounts.slice(0, 3).map((account) => (
                            <AccountBalanceItem key={account.account_id} account={account} />
                        ))}
                    </div>
                </div>
            )}

            {/* Upcoming Payments */}
            {summary.upcoming_payments.length > 0 && (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        <Banknote className="h-4 w-4 text-muted-foreground" />
                        <p className="text-xs font-medium text-muted-foreground">
                            Nächste Zahlungen
                        </p>
                        {hasCriticalPayments && (
                            <Badge variant="destructive" className="text-xs h-4 px-1">
                                Kritisch
                            </Badge>
                        )}
                    </div>
                    {summary.upcoming_payments.slice(0, 2).map((payment) => (
                        <UpcomingPaymentItem key={payment.id} payment={payment} />
                    ))}
                </div>
            )}

            {/* Link to banking */}
            <Link
                to="/banking"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                Banking-Übersicht
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function CashPositionWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Kassenstand" />}
            errorTitle="Kassenstand Fehler"
            errorDescription="Die Kontodaten konnten nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Wallet className="h-5 w-5 text-primary" />
                        Kassenstand
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <CashPositionWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
