/**
 * Intercompany Reconciliation Page
 *
 * Vollständige IC-Abstimmung und Konsolidierung:
 * - Transaktionsübersicht mit Statusfilter
 * - Salden-Matrix zwischen Firmenpaarungen
 * - Differenzenliste mit Lösungsvorschlägen
 * - Eliminierungsbuchungen für Konsolidierung
 *
 * Feature 15: Intercompany Reconciliation UI
 */

import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, subMonths, startOfMonth, endOfMonth } from 'date-fns';
import { de } from 'date-fns/locale';

// UI Components
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

// Icons
import {
    ArrowLeftRight,
    Building2,
    RefreshCw,
    AlertTriangle,
    CheckCircle2,
    XCircle,
    FileText,
    Download,
    TrendingUp,
    TrendingDown,
    Minus,
    Info,
    Calculator,
    Scale,
} from 'lucide-react';

// API
import {
    getICSummary,
    getICTransactions,
    getICBalances,
    performReconciliation,
    getEliminations,
    getReconciliationReport,
    type ICTransaction,
    type ICBalance,
    type ReconciliationDifference,
    type EliminationEntry,
    type ICTransactionStatus,
    type DifferenceType,
} from './api/reconciliation-api';
import { getHoldingCompanies, type CompanySummary } from './api/holding-api';

// ==================== Types ====================

type TabValue = 'transactions' | 'balances' | 'differences' | 'eliminations';

// ==================== Helper Functions ====================

const formatCurrency = (value: number, currency = 'EUR') =>
    new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(value);

const formatDate = (dateStr: string) => {
    try {
        return format(new Date(dateStr), 'dd.MM.yyyy', { locale: de });
    } catch {
        return dateStr;
    }
};

const getStatusBadge = (status: ICTransactionStatus) => {
    const statusConfig: Record<
        ICTransactionStatus,
        { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }
    > = {
        open: { label: 'Offen', variant: 'outline' },
        matched: { label: 'Abgestimmt', variant: 'default' },
        partial_match: { label: 'Teilweise', variant: 'secondary' },
        disputed: { label: 'Streitig', variant: 'destructive' },
        closed: { label: 'Geschlossen', variant: 'secondary' },
    };
    const config = statusConfig[status] || { label: status, variant: 'outline' as const };
    return <Badge variant={config.variant}>{config.label}</Badge>;
};

const getDifferenceTypeBadge = (type: DifferenceType) => {
    const typeConfig: Record<
        DifferenceType,
        { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }
    > = {
        unmatched: { label: 'Nicht zugeordnet', variant: 'destructive' },
        amount_mismatch: { label: 'Betragsdifferenz', variant: 'destructive' },
        date_mismatch: { label: 'Datumsdifferenz', variant: 'secondary' },
        duplicate: { label: 'Duplikat', variant: 'outline' },
        partial_match: { label: 'Teilzuordnung', variant: 'secondary' },
    };
    const config = typeConfig[type] || { label: type, variant: 'outline' as const };
    return <Badge variant={config.variant}>{config.label}</Badge>;
};

// ==================== Sub-Components ====================

function SummaryCards({
    matchRate,
    totalTransactions,
    openTransactions,
    totalDifferences,
    isLoading,
}: {
    matchRate: number;
    totalTransactions: number;
    openTransactions: number;
    totalDifferences: number;
    isLoading: boolean;
}) {
    if (isLoading) {
        return (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                    <Card key={i}>
                        <CardContent className="pt-6">
                            <Skeleton className="h-8 w-24 mb-2" />
                            <Skeleton className="h-4 w-32" />
                        </CardContent>
                    </Card>
                ))}
            </div>
        );
    }

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
                <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                        <div>
                            <div className="text-2xl font-bold">
                                {(matchRate * 100).toFixed(1)}%
                            </div>
                            <div className="text-sm text-muted-foreground">Abstimmungsquote</div>
                        </div>
                        <Scale className="h-8 w-8 text-muted-foreground" />
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                        <div>
                            <div className="text-2xl font-bold">{totalTransactions}</div>
                            <div className="text-sm text-muted-foreground">Transaktionen</div>
                        </div>
                        <ArrowLeftRight className="h-8 w-8 text-muted-foreground" />
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                        <div>
                            <div className="text-2xl font-bold">{openTransactions}</div>
                            <div className="text-sm text-muted-foreground">Offene Posten</div>
                        </div>
                        <FileText className="h-8 w-8 text-muted-foreground" />
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                        <div>
                            <div
                                className={`text-2xl font-bold ${
                                    totalDifferences > 0 ? 'text-destructive' : 'text-green-600'
                                }`}
                            >
                                {totalDifferences}
                            </div>
                            <div className="text-sm text-muted-foreground">Differenzen</div>
                        </div>
                        <AlertTriangle
                            className={`h-8 w-8 ${
                                totalDifferences > 0
                                    ? 'text-destructive'
                                    : 'text-muted-foreground'
                            }`}
                        />
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

function TransactionsTable({
    transactions,
    isLoading,
}: {
    transactions: ICTransaction[];
    isLoading: boolean;
}) {
    if (isLoading) {
        return (
            <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                ))}
            </div>
        );
    }

    if (transactions.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <ArrowLeftRight className="h-12 w-12 mb-4 opacity-50" />
                <p>Keine IC-Transaktionen im gewaehlten Zeitraum</p>
            </div>
        );
    }

    return (
        <div className="border rounded-lg">
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Datum</TableHead>
                        <TableHead>Von</TableHead>
                        <TableHead>An</TableHead>
                        <TableHead>Typ</TableHead>
                        <TableHead className="text-right">Betrag</TableHead>
                        <TableHead>Referenz</TableHead>
                        <TableHead>Status</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {transactions.map((tx) => (
                        <TableRow key={tx.id}>
                            <TableCell className="font-mono text-sm">
                                {formatDate(tx.transaction_date)}
                            </TableCell>
                            <TableCell>
                                <div className="flex items-center gap-2">
                                    <Building2 className="h-4 w-4 text-muted-foreground" />
                                    {tx.from_company_name}
                                </div>
                            </TableCell>
                            <TableCell>
                                <div className="flex items-center gap-2">
                                    <Building2 className="h-4 w-4 text-muted-foreground" />
                                    {tx.to_company_name}
                                </div>
                            </TableCell>
                            <TableCell>
                                <Badge variant="outline">{tx.transaction_type}</Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono">
                                {formatCurrency(tx.amount, tx.currency)}
                            </TableCell>
                            <TableCell className="font-mono text-sm text-muted-foreground">
                                {tx.reference}
                            </TableCell>
                            <TableCell>{getStatusBadge(tx.status)}</TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    );
}

function BalancesMatrix({
    balances,
    isLoading,
}: {
    balances: ICBalance[];
    isLoading: boolean;
}) {
    if (isLoading) {
        return (
            <div className="space-y-4">
                {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-24 w-full" />
                ))}
            </div>
        );
    }

    if (balances.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Scale className="h-12 w-12 mb-4 opacity-50" />
                <p>Keine IC-Salden vorhanden</p>
            </div>
        );
    }

    return (
        <div className="grid gap-4">
            {balances.map((balance) => {
                const isBalanced = Math.abs(balance.net_balance) < 0.01;
                return (
                    <Card key={`${balance.company_a_id}-${balance.company_b_id}`}>
                        <CardContent className="pt-6">
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-4">
                                    <div className="flex items-center gap-2">
                                        <Building2 className="h-5 w-5 text-primary" />
                                        <span className="font-medium">{balance.company_a_name}</span>
                                    </div>
                                    <ArrowLeftRight className="h-4 w-4 text-muted-foreground" />
                                    <div className="flex items-center gap-2">
                                        <Building2 className="h-5 w-5 text-primary" />
                                        <span className="font-medium">{balance.company_b_name}</span>
                                    </div>
                                </div>
                                {isBalanced ? (
                                    <Badge variant="default" className="bg-green-600">
                                        <CheckCircle2 className="h-3 w-3 mr-1" />
                                        Ausgeglichen
                                    </Badge>
                                ) : (
                                    <Badge variant="destructive">
                                        <AlertTriangle className="h-3 w-3 mr-1" />
                                        Differenz
                                    </Badge>
                                )}
                            </div>

                            <div className="grid grid-cols-3 gap-4">
                                <div className="p-3 rounded-lg bg-muted">
                                    <div className="flex items-center gap-1 text-sm text-muted-foreground mb-1">
                                        <TrendingUp className="h-3 w-3" />
                                        {balance.company_a_name} schuldet
                                    </div>
                                    <div className="text-lg font-medium text-red-600">
                                        {formatCurrency(balance.balance_a_to_b, balance.currency)}
                                    </div>
                                </div>

                                <div className="p-3 rounded-lg bg-muted">
                                    <div className="flex items-center gap-1 text-sm text-muted-foreground mb-1">
                                        <TrendingDown className="h-3 w-3" />
                                        {balance.company_b_name} schuldet
                                    </div>
                                    <div className="text-lg font-medium text-red-600">
                                        {formatCurrency(balance.balance_b_to_a, balance.currency)}
                                    </div>
                                </div>

                                <div className="p-3 rounded-lg bg-muted">
                                    <div className="flex items-center gap-1 text-sm text-muted-foreground mb-1">
                                        <Minus className="h-3 w-3" />
                                        Netto-Saldo
                                    </div>
                                    <div
                                        className={`text-lg font-medium ${
                                            balance.net_balance >= 0
                                                ? 'text-green-600'
                                                : 'text-red-600'
                                        }`}
                                    >
                                        {formatCurrency(balance.net_balance, balance.currency)}
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center justify-between mt-4 pt-4 border-t text-sm text-muted-foreground">
                                <span>{balance.open_transactions_count} offene Transaktionen</span>
                                {balance.last_reconciled_at && (
                                    <span>
                                        Letzte Abstimmung: {formatDate(balance.last_reconciled_at)}
                                    </span>
                                )}
                            </div>
                        </CardContent>
                    </Card>
                );
            })}
        </div>
    );
}

function DifferencesList({
    differences,
    isLoading,
}: {
    differences: ReconciliationDifference[];
    isLoading: boolean;
}) {
    if (isLoading) {
        return (
            <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-20 w-full" />
                ))}
            </div>
        );
    }

    if (differences.length === 0) {
        return (
            <Alert>
                <CheckCircle2 className="h-4 w-4" />
                <AlertTitle>Keine Differenzen</AlertTitle>
                <AlertDescription>
                    Alle IC-Transaktionen sind korrekt abgestimmt.
                </AlertDescription>
            </Alert>
        );
    }

    return (
        <div className="space-y-4">
            {differences.map((diff) => (
                <Card key={diff.id} className="border-destructive/50">
                    <CardContent className="pt-6">
                        <div className="flex items-start justify-between mb-4">
                            <div className="flex items-center gap-2">
                                {getDifferenceTypeBadge(diff.difference_type)}
                                <span className="text-sm text-muted-foreground">
                                    {formatDate(diff.created_at)}
                                </span>
                            </div>
                            <div className="text-right">
                                <div className="text-sm text-muted-foreground">Differenz</div>
                                <div className="text-lg font-bold text-destructive">
                                    {formatCurrency(diff.difference_amount)}
                                </div>
                            </div>
                        </div>

                        <p className="text-sm mb-4">{diff.description}</p>

                        <div className="grid grid-cols-2 gap-4 mb-4">
                            <div className="p-3 rounded-lg bg-muted">
                                <div className="text-xs text-muted-foreground">Erwartet</div>
                                <div className="font-medium">{formatCurrency(diff.expected_amount)}</div>
                                {diff.expected_date && (
                                    <div className="text-xs text-muted-foreground">
                                        {formatDate(diff.expected_date)}
                                    </div>
                                )}
                            </div>
                            <div className="p-3 rounded-lg bg-muted">
                                <div className="text-xs text-muted-foreground">Tatsächlich</div>
                                <div className="font-medium">{formatCurrency(diff.actual_amount)}</div>
                                {diff.actual_date && (
                                    <div className="text-xs text-muted-foreground">
                                        {formatDate(diff.actual_date)}
                                    </div>
                                )}
                            </div>
                        </div>

                        <Alert>
                            <Info className="h-4 w-4" />
                            <AlertTitle>Empfehlung</AlertTitle>
                            <AlertDescription>{diff.recommendation}</AlertDescription>
                        </Alert>
                    </CardContent>
                </Card>
            ))}
        </div>
    );
}

function EliminationsTable({
    eliminations,
    totalEliminated,
    isLoading,
}: {
    eliminations: EliminationEntry[];
    totalEliminated: number;
    isLoading: boolean;
}) {
    if (isLoading) {
        return (
            <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                ))}
            </div>
        );
    }

    if (eliminations.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Calculator className="h-12 w-12 mb-4 opacity-50" />
                <p>Keine Eliminierungsbuchungen erforderlich</p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <Alert>
                <Calculator className="h-4 w-4" />
                <AlertTitle>Eliminierungsbuchungen für Konsolidierung</AlertTitle>
                <AlertDescription>
                    Diese Buchungen eliminieren interne Forderungen und Verbindlichkeiten.
                    Gesamtvolumen: {formatCurrency(totalEliminated)}
                </AlertDescription>
            </Alert>

            <div className="border rounded-lg">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Soll-Konto</TableHead>
                            <TableHead>Haben-Konto</TableHead>
                            <TableHead className="text-right">Betrag</TableHead>
                            <TableHead>Beschreibung</TableHead>
                            <TableHead>Typ</TableHead>
                            <TableHead>Periode</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {eliminations.map((elim) => (
                            <TableRow key={elim.id}>
                                <TableCell className="font-mono">{elim.account_debit}</TableCell>
                                <TableCell className="font-mono">{elim.account_credit}</TableCell>
                                <TableCell className="text-right font-mono">
                                    {formatCurrency(elim.amount)}
                                </TableCell>
                                <TableCell className="text-sm text-muted-foreground">
                                    {elim.description}
                                </TableCell>
                                <TableCell>
                                    <Badge variant="outline">{elim.elimination_type}</Badge>
                                </TableCell>
                                <TableCell className="font-mono text-sm">
                                    {elim.period}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}

// ==================== Main Component ====================

export function IntercompanyReconciliation() {
    const queryClient = useQueryClient();

    // State
    const [activeTab, setActiveTab] = useState<TabValue>('transactions');
    const [selectedPeriod, setSelectedPeriod] = useState('current_month');
    const [selectedCompanyId, setSelectedCompanyId] = useState<string>('all');

    // Calculate date range based on period
    const dateRange = useMemo(() => {
        const now = new Date();
        switch (selectedPeriod) {
            case 'current_month':
                return {
                    startDate: format(startOfMonth(now), 'yyyy-MM-dd'),
                    endDate: format(endOfMonth(now), 'yyyy-MM-dd'),
                };
            case 'last_month': {
                const lastMonth = subMonths(now, 1);
                return {
                    startDate: format(startOfMonth(lastMonth), 'yyyy-MM-dd'),
                    endDate: format(endOfMonth(lastMonth), 'yyyy-MM-dd'),
                };
            }
            case 'last_quarter': {
                const threeMonthsAgo = subMonths(now, 3);
                return {
                    startDate: format(startOfMonth(threeMonthsAgo), 'yyyy-MM-dd'),
                    endDate: format(endOfMonth(now), 'yyyy-MM-dd'),
                };
            }
            case 'year_to_date':
                return {
                    startDate: `${now.getFullYear()}-01-01`,
                    endDate: format(now, 'yyyy-MM-dd'),
                };
            default:
                return {
                    startDate: format(startOfMonth(now), 'yyyy-MM-dd'),
                    endDate: format(endOfMonth(now), 'yyyy-MM-dd'),
                };
        }
    }, [selectedPeriod]);

    const companyIds = useMemo(() => {
        if (selectedCompanyId === 'all') return undefined;
        return [selectedCompanyId];
    }, [selectedCompanyId]);

    // Queries
    const { data: companies = [] } = useQuery({
        queryKey: ['holding', 'companies'],
        queryFn: getHoldingCompanies,
    });

    const { data: summary, isLoading: summaryLoading } = useQuery({
        queryKey: ['ic', 'summary', companyIds],
        queryFn: () => getICSummary(companyIds),
    });

    const { data: transactions, isLoading: transactionsLoading } = useQuery({
        queryKey: ['ic', 'transactions', companyIds, dateRange],
        queryFn: () =>
            getICTransactions({
                companyIds,
                startDate: dateRange.startDate,
                endDate: dateRange.endDate,
            }),
    });

    const { data: balances, isLoading: balancesLoading } = useQuery({
        queryKey: ['ic', 'balances', companyIds],
        queryFn: () => getICBalances(companyIds),
    });

    const { data: eliminations, isLoading: eliminationsLoading } = useQuery({
        queryKey: ['ic', 'eliminations', companyIds, dateRange.startDate.slice(0, 7)],
        queryFn: () =>
            getEliminations({
                companyIds,
                period: dateRange.startDate.slice(0, 7),
            }),
    });

    // Reconciliation mutation
    const reconcileMutation = useMutation({
        mutationFn: () =>
            performReconciliation({
                companyIds,
                startDate: dateRange.startDate,
                endDate: dateRange.endDate,
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ic'] });
        },
    });

    // Computed values
    const matchRate = reconcileMutation.data?.match_rate ?? 0;
    const differences = reconcileMutation.data?.differences ?? [];

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
                        <ArrowLeftRight className="h-6 w-6" />
                        Intercompany-Abstimmung
                    </h1>
                    <p className="text-muted-foreground">
                        Abstimmung und Konsolidierung von IC-Transaktionen
                    </p>
                </div>

                <div className="flex items-center gap-4">
                    {/* Company Filter */}
                    <Select value={selectedCompanyId} onValueChange={setSelectedCompanyId}>
                        <SelectTrigger className="w-48">
                            <SelectValue placeholder="Alle Firmen" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Alle Firmen</SelectItem>
                            {companies.map((company) => (
                                <SelectItem key={company.id} value={company.id}>
                                    {company.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>

                    {/* Period Filter */}
                    <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
                        <SelectTrigger className="w-48">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="current_month">Aktueller Monat</SelectItem>
                            <SelectItem value="last_month">Letzter Monat</SelectItem>
                            <SelectItem value="last_quarter">Letztes Quartal</SelectItem>
                            <SelectItem value="year_to_date">Jahr bis heute</SelectItem>
                        </SelectContent>
                    </Select>

                    {/* Actions */}
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    onClick={() => reconcileMutation.mutate()}
                                    disabled={reconcileMutation.isPending}
                                >
                                    {reconcileMutation.isPending ? (
                                        <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                    ) : (
                                        <RefreshCw className="h-4 w-4 mr-2" />
                                    )}
                                    Abstimmen
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                                <p>Führt automatische Abstimmung aller IC-Transaktionen durch</p>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>

                    <Button variant="outline">
                        <Download className="h-4 w-4 mr-2" />
                        Bericht
                    </Button>
                </div>
            </div>

            {/* Summary Cards */}
            <SummaryCards
                matchRate={matchRate}
                totalTransactions={transactions?.total ?? 0}
                openTransactions={summary?.open_transactions ?? 0}
                totalDifferences={differences.length}
                isLoading={summaryLoading}
            />

            {/* Main Content Tabs */}
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabValue)}>
                <TabsList className="grid w-full grid-cols-4">
                    <TabsTrigger value="transactions" className="flex items-center gap-2">
                        <ArrowLeftRight className="h-4 w-4" />
                        Transaktionen
                        {transactions?.total && transactions.total > 0 && (
                            <Badge variant="secondary" className="ml-1">
                                {transactions.total}
                            </Badge>
                        )}
                    </TabsTrigger>
                    <TabsTrigger value="balances" className="flex items-center gap-2">
                        <Scale className="h-4 w-4" />
                        Salden
                        {balances?.balances && balances.balances.length > 0 && (
                            <Badge variant="secondary" className="ml-1">
                                {balances.balances.length}
                            </Badge>
                        )}
                    </TabsTrigger>
                    <TabsTrigger value="differences" className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4" />
                        Differenzen
                        {differences.length > 0 && (
                            <Badge variant="destructive" className="ml-1">
                                {differences.length}
                            </Badge>
                        )}
                    </TabsTrigger>
                    <TabsTrigger value="eliminations" className="flex items-center gap-2">
                        <Calculator className="h-4 w-4" />
                        Eliminierungen
                        {eliminations?.eliminations && eliminations.eliminations.length > 0 && (
                            <Badge variant="secondary" className="ml-1">
                                {eliminations.eliminations.length}
                            </Badge>
                        )}
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="transactions" className="mt-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>IC-Transaktionen</CardTitle>
                            <CardDescription>
                                Alle Intercompany-Transaktionen im Zeitraum {formatDate(dateRange.startDate)} bis{' '}
                                {formatDate(dateRange.endDate)}
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <TransactionsTable
                                transactions={transactions?.transactions ?? []}
                                isLoading={transactionsLoading}
                            />
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="balances" className="mt-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>IC-Salden nach Firmenpaarung</CardTitle>
                            <CardDescription>
                                Aktuelle Salden zwischen allen Firmen im Holding
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <BalancesMatrix
                                balances={balances?.balances ?? []}
                                isLoading={balancesLoading}
                            />
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="differences" className="mt-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Identifizierte Differenzen</CardTitle>
                            <CardDescription>
                                Abweichungen und Unstimmigkeiten bei der Abstimmung
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <DifferencesList
                                differences={differences}
                                isLoading={reconcileMutation.isPending}
                            />
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="eliminations" className="mt-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Eliminierungsbuchungen</CardTitle>
                            <CardDescription>
                                Buchungen für die Konzern-Konsolidierung
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <EliminationsTable
                                eliminations={eliminations?.eliminations ?? []}
                                totalEliminated={eliminations?.total_eliminated ?? 0}
                                isLoading={eliminationsLoading}
                            />
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}

export default IntercompanyReconciliation;
