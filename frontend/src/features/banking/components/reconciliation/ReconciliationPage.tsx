/**
 * Payment Reconciliation Page
 *
 * Vollstaendige Reconciliation-UI mit:
 * - Unabgeglichene Transaktionen Liste
 * - Match-Vorschlaege Panel
 * - Manuelles Matching Dialog
 * - Statistiken Dashboard
 * - Bulk-Aktionen
 * - Drag & Drop Support (optional)
 */

import { useState, useCallback } from 'react';
import {
    AlertTriangle,
    BarChart3,
    CheckCircle2,
    Filter,
    Link2,
    Loader2,
    RefreshCw,
    Settings2,
    Sparkles,
    TrendingUp,
    Unlink,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { Progress } from '@/components/ui/progress';
import {
    useAccounts,
    useBatchReconcile,
    useManualMatch,
    useUnmatchedTransactions,
    useUnmatchedDocuments,
    useTransactionStats,
} from '@/features/banking/hooks/use-banking-queries';
import { ManualMatchDialog } from './ManualMatchDialog';
import { UnmatchedList } from './UnmatchedList';
import { MatchSuggestions } from './MatchSuggestions';
import type { BankTransaction } from '@/lib/api/services/banking';
import { formatCurrency } from '@/features/banking/utils/format';
import { cn } from '@/lib/utils';

// Statistik-Karte Komponente
function StatCard({
    title,
    value,
    subtitle,
    icon: Icon,
    trend,
    color = 'default',
}: {
    title: string;
    value: string | number;
    subtitle?: string;
    icon: React.ElementType;
    trend?: { value: number; isPositive: boolean };
    color?: 'default' | 'success' | 'warning' | 'danger';
}) {
    const colorStyles = {
        default: 'text-muted-foreground',
        success: 'text-green-600',
        warning: 'text-yellow-600',
        danger: 'text-red-600',
    };

    return (
        <Card>
            <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                    <div>
                        <p className="text-sm text-muted-foreground">{title}</p>
                        <p className="text-2xl font-bold mt-1">{value}</p>
                        {subtitle && (
                            <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
                        )}
                        {trend && (
                            <div
                                className={cn(
                                    'text-xs mt-1 flex items-center gap-1',
                                    trend.isPositive ? 'text-green-600' : 'text-red-600'
                                )}
                            >
                                <TrendingUp className={cn('h-3 w-3', !trend.isPositive && 'rotate-180')} />
                                {trend.value}% vs. Vormonat
                            </div>
                        )}
                    </div>
                    <div className={cn('p-2 rounded-lg bg-muted', colorStyles[color])}>
                        <Icon className="h-5 w-5" />
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

export function ReconciliationPage() {
    const { toast } = useToast();

    // State
    const [selectedAccount, setSelectedAccount] = useState<string>('all');
    const [selectedTransaction, setSelectedTransaction] = useState<BankTransaction | null>(null);
    const [manualMatchOpen, setManualMatchOpen] = useState(false);
    const [selectedTransactionIds, setSelectedTransactionIds] = useState<string[]>([]);
    const [activeTab, setActiveTab] = useState<string>('list');

    // Data Fetching
    const { data: accounts } = useAccounts();
    const {
        data: unmatchedTx,
        isLoading: unmatchedTxLoading,
        refetch,
    } = useUnmatchedTransactions(
        selectedAccount === 'all' ? undefined : selectedAccount
    );
    const { data: unmatchedDocs } = useUnmatchedDocuments();
    const { data: stats } = useTransactionStats(
        selectedAccount === 'all' ? undefined : { bank_account_id: selectedAccount }
    );

    // Mutations
    const manualMatch = useManualMatch();
    const batchReconcile = useBatchReconcile();

    // Handlers
    const handleManualMatch = async (transactionId: string, documentId: string) => {
        try {
            await manualMatch.mutateAsync({ transactionId, documentId });
            toast({
                title: 'Erfolgreich verknuepft',
                description: 'Die Transaktion wurde mit dem Dokument verknuepft.',
            });
            refetch();
            setSelectedTransaction(null);
        } catch (err) {
            toast({
                title: 'Fehler',
                description: 'Verknuepfung fehlgeschlagen.',
                variant: 'destructive',
            });
            throw err;
        }
    };

    const handleRunReconciliation = async () => {
        try {
            const result = await batchReconcile.mutateAsync(
                selectedAccount !== 'all' ? { bank_account_id: selectedAccount } : undefined
            );
            toast({
                title: 'Abgleich abgeschlossen',
                description: `${result.matched_count} von ${result.total_processed} Transaktionen wurden abgeglichen.`,
            });
            refetch();
            setSelectedTransactionIds([]);
        } catch {
            toast({
                title: 'Fehler',
                description: 'Abgleich konnte nicht gestartet werden.',
                variant: 'destructive',
            });
        }
    };

    const handleSelectTransaction = useCallback((tx: BankTransaction) => {
        setSelectedTransaction(tx);
        // Bei Auswahl direkt zur Vorschlaege-Ansicht wechseln (auf Mobile)
        if (window.innerWidth < 1024) {
            setActiveTab('suggestions');
        }
    }, []);

    const handleMatchSuccess = useCallback(() => {
        toast({
            title: 'Erfolgreich verknuepft',
            description: 'Die Transaktion wurde zugeordnet.',
        });
        setSelectedTransaction(null);
        refetch();
    }, [toast, refetch]);

    const openManualMatch = () => {
        if (selectedTransaction) {
            setManualMatchOpen(true);
        }
    };

    const handleBulkMatch = async (transactionIds: string[]) => {
        // TODO: Implementierung von Bulk-Match
        toast({
            title: 'Bulk-Abgleich',
            description: `${transactionIds.length} Transaktionen werden verarbeitet...`,
        });
    };

    // Berechnete Werte
    const unmatchedCount = unmatchedTx?.length || 0;
    const matchedCount = stats?.matched_count || 0;
    const totalCount = stats?.total_count || 0;
    const matchRate = totalCount > 0 ? (matchedCount / totalCount) * 100 : 0;
    const unmatchedAmount = unmatchedTx?.reduce((sum, tx) => sum + Math.abs(tx.amount), 0) || 0;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Zahlungsabgleich</h1>
                    <p className="text-muted-foreground">
                        Transaktionen mit Rechnungen und Dokumenten verknuepfen
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        onClick={() => refetch()}
                        disabled={unmatchedTxLoading}
                    >
                        <RefreshCw className={cn('h-4 w-4 mr-2', unmatchedTxLoading && 'animate-spin')} />
                        Aktualisieren
                    </Button>
                    <Button
                        onClick={handleRunReconciliation}
                        disabled={batchReconcile.isPending || unmatchedCount === 0}
                    >
                        {batchReconcile.isPending ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <Sparkles className="mr-2 h-4 w-4" />
                        )}
                        Auto-Abgleich starten
                    </Button>
                </div>
            </div>

            {/* Statistik-Karten */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <StatCard
                    title="Abgleichquote"
                    value={`${matchRate.toFixed(1)}%`}
                    subtitle={`${matchedCount} von ${totalCount}`}
                    icon={BarChart3}
                    color={matchRate >= 80 ? 'success' : matchRate >= 50 ? 'warning' : 'danger'}
                />
                <StatCard
                    title="Unabgeglichen"
                    value={unmatchedCount}
                    subtitle={formatCurrency(unmatchedAmount, { currency: 'EUR' })}
                    icon={Unlink}
                    color={unmatchedCount === 0 ? 'success' : 'warning'}
                />
                <StatCard
                    title="Abgeglichen"
                    value={matchedCount}
                    icon={Link2}
                    color="success"
                />
                <StatCard
                    title="Ausstehend"
                    value={selectedTransactionIds.length}
                    subtitle="Fuer Verarbeitung markiert"
                    icon={CheckCircle2}
                    color="default"
                />
            </div>

            {/* Match-Rate Progress */}
            {totalCount > 0 && (
                <Card>
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Gesamtfortschritt</span>
                            <span className="text-sm text-muted-foreground">
                                {matchedCount} / {totalCount} abgeglichen
                            </span>
                        </div>
                        <Progress value={matchRate} className="h-2" />
                        <div className="flex justify-between mt-2 text-xs text-muted-foreground">
                            <span>0%</span>
                            <span
                                className={cn(
                                    matchRate >= 80
                                        ? 'text-green-600'
                                        : matchRate >= 50
                                            ? 'text-yellow-600'
                                            : 'text-red-600'
                                )}
                            >
                                {matchRate.toFixed(1)}%
                            </span>
                            <span>100%</span>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Filter */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                        <Filter className="h-4 w-4" />
                        Filter
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-4 md:grid-cols-3">
                        <div className="space-y-2">
                            <Label>Bankkonto</Label>
                            <Select value={selectedAccount} onValueChange={setSelectedAccount}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Alle Konten" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Alle Konten</SelectItem>
                                    {accounts?.map((account) => (
                                        <SelectItem key={account.id} value={account.id}>
                                            {account.account_name}
                                            {account.unmatched_count > 0 && (
                                                <Badge variant="secondary" className="ml-2">
                                                    {account.unmatched_count}
                                                </Badge>
                                            )}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Haupt-Content: Split View auf Desktop, Tabs auf Mobile */}
            <div className="lg:hidden">
                {/* Mobile: Tabs */}
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="list" className="gap-2">
                            <Unlink className="h-4 w-4" />
                            Transaktionen
                            {unmatchedCount > 0 && (
                                <Badge variant="secondary">{unmatchedCount}</Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger value="suggestions" className="gap-2" disabled={!selectedTransaction}>
                            <Sparkles className="h-4 w-4" />
                            Vorschlaege
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="list" className="mt-4">
                        <UnmatchedList
                            selectedAccountId={selectedAccount}
                            onSelectTransaction={handleSelectTransaction}
                            onBulkMatch={handleBulkMatch}
                            selectedTransactionIds={selectedTransactionIds}
                            onSelectionChange={setSelectedTransactionIds}
                        />
                    </TabsContent>

                    <TabsContent value="suggestions" className="mt-4">
                        {selectedTransaction ? (
                            <MatchSuggestions
                                transaction={selectedTransaction}
                                onMatchSuccess={handleMatchSuccess}
                                onClose={() => {
                                    setSelectedTransaction(null);
                                    setActiveTab('list');
                                }}
                            />
                        ) : (
                            <Card>
                                <CardContent className="py-12 text-center">
                                    <Sparkles className="mx-auto h-12 w-12 text-muted-foreground/50" />
                                    <p className="mt-4 text-muted-foreground">
                                        Waehlen Sie eine Transaktion aus der Liste
                                    </p>
                                </CardContent>
                            </Card>
                        )}
                    </TabsContent>
                </Tabs>
            </div>

            {/* Desktop: Side-by-Side */}
            <div className="hidden lg:grid lg:grid-cols-2 gap-6">
                {/* Linke Seite: Transaktionsliste */}
                <UnmatchedList
                    selectedAccountId={selectedAccount}
                    onSelectTransaction={handleSelectTransaction}
                    onBulkMatch={handleBulkMatch}
                    selectedTransactionIds={selectedTransactionIds}
                    onSelectionChange={setSelectedTransactionIds}
                />

                {/* Rechte Seite: Match-Vorschlaege */}
                {selectedTransaction ? (
                    <MatchSuggestions
                        transaction={selectedTransaction}
                        onMatchSuccess={handleMatchSuccess}
                        onClose={() => setSelectedTransaction(null)}
                    />
                ) : (
                    <Card className="flex items-center justify-center min-h-[400px]">
                        <CardContent className="text-center">
                            <Sparkles className="mx-auto h-16 w-16 text-muted-foreground/30" />
                            <h3 className="mt-4 text-lg font-medium">Keine Transaktion ausgewaehlt</h3>
                            <p className="text-muted-foreground mt-1">
                                Klicken Sie auf eine Transaktion links, um Match-Vorschlaege zu sehen.
                            </p>
                            {unmatchedCount === 0 && (
                                <div className="mt-6 p-4 bg-green-50 rounded-lg">
                                    <CheckCircle2 className="mx-auto h-8 w-8 text-green-500" />
                                    <p className="mt-2 text-green-700 font-medium">
                                        Alle Transaktionen abgeglichen!
                                    </p>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                )}
            </div>

            {/* Manual Match Dialog */}
            <ManualMatchDialog
                open={manualMatchOpen}
                onOpenChange={setManualMatchOpen}
                transaction={selectedTransaction}
                documents={unmatchedDocs || []}
                onMatch={handleManualMatch}
            />
        </div>
    );
}
