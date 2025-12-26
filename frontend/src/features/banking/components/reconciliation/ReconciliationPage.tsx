/**
 * Reconciliation Page
 * Transaktionen mit Dokumenten abgleichen
 */

import { useState } from 'react';
import { Link2, RefreshCw, Filter, Loader2, CheckCircle2 } from 'lucide-react';
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
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/use-toast';
import {
    useAccounts,
    useBatchReconcile,
    useManualMatch,
    useUnmatchedTransactions,
    useUnmatchedDocuments,
} from '@/features/banking/hooks/use-banking-queries';
import { ManualMatchDialog } from './ManualMatchDialog';
import type { BankTransaction } from '@/lib/api/services/banking';

export function ReconciliationPage() {
    const { toast } = useToast();
    const [selectedAccount, setSelectedAccount] = useState<string>('all');
    const [selectedTransaction, setSelectedTransaction] = useState<BankTransaction | null>(null);
    const [manualMatchOpen, setManualMatchOpen] = useState(false);

    const { data: accounts } = useAccounts();
    const { data: unmatchedTx, isLoading: unmatchedTxLoading, refetch } = useUnmatchedTransactions(
        selectedAccount === 'all' ? undefined : selectedAccount
    );
    const { data: unmatchedDocs } = useUnmatchedDocuments();

    const manualMatch = useManualMatch();
    const batchReconcile = useBatchReconcile();

    const handleManualMatch = async (transactionId: string, documentId: string) => {
        try {
            await manualMatch.mutateAsync({ transactionId, documentId });
            toast({
                title: 'Manuell verknuepft',
                description: 'Die Transaktion wurde mit dem Dokument verknuepft.',
            });
            refetch();
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
        } catch {
            toast({
                title: 'Fehler',
                description: 'Abgleich konnte nicht gestartet werden.',
                variant: 'destructive',
            });
        }
    };

    const openManualMatch = (tx: BankTransaction) => {
        setSelectedTransaction(tx);
        setManualMatchOpen(true);
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Abgleich</h2>
                    <p className="text-muted-foreground">
                        Transaktionen mit Rechnungen und Dokumenten verknuepfen.
                    </p>
                </div>
                <Button
                    onClick={handleRunReconciliation}
                    disabled={batchReconcile.isPending}
                >
                    {batchReconcile.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                        <RefreshCw className="mr-2 h-4 w-4" />
                    )}
                    Auto-Abgleich starten
                </Button>
            </div>

            {/* Filter */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                        <Filter className="h-4 w-4" />
                        Filter
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                            <Label>Konto</Label>
                            <Select value={selectedAccount} onValueChange={setSelectedAccount}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Alle Konten" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Alle Konten</SelectItem>
                                    {accounts?.map((account) => (
                                        <SelectItem key={account.id} value={account.id}>
                                            {account.account_name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Unmatched Transactions */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Link2 className="h-5 w-5" />
                        Unabgeglichene Transaktionen
                        {unmatchedTx && unmatchedTx.length > 0 && (
                            <Badge variant="outline" className="ml-2">
                                {unmatchedTx.length}
                            </Badge>
                        )}
                    </CardTitle>
                    <CardDescription>
                        Diese Transaktionen haben noch kein verknuepftes Dokument.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {unmatchedTxLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : !unmatchedTx?.length ? (
                        <div className="py-8 text-center text-muted-foreground">
                            <CheckCircle2 className="mx-auto h-12 w-12 text-green-500/50" />
                            <h3 className="mt-4 text-lg font-semibold">Alle Transaktionen abgeglichen!</h3>
                            <p>Es gibt keine offenen Transaktionen zum Verknuepfen.</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {unmatchedTx.slice(0, 20).map((tx) => (
                                <div
                                    key={tx.id}
                                    className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                                >
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="text-sm text-muted-foreground">
                                                {new Date(tx.booking_date).toLocaleDateString('de-DE')}
                                            </span>
                                            <span className="font-medium truncate">
                                                {tx.counterparty_name || 'Unbekannt'}
                                            </span>
                                        </div>
                                        <p className="text-sm text-muted-foreground truncate">
                                            {tx.reference_text}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <span
                                            className={`font-mono font-medium whitespace-nowrap ${
                                                tx.amount >= 0 ? 'text-green-600' : 'text-red-600'
                                            }`}
                                        >
                                            {tx.amount >= 0 ? '+' : ''}
                                            {tx.amount.toLocaleString('de-DE', {
                                                style: 'currency',
                                                currency: tx.currency,
                                            })}
                                        </span>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => openManualMatch(tx)}
                                        >
                                            <Link2 className="h-4 w-4 mr-1" />
                                            Verknuepfen
                                        </Button>
                                    </div>
                                </div>
                            ))}
                            {unmatchedTx.length > 20 && (
                                <p className="text-center text-sm text-muted-foreground pt-2">
                                    ... und {unmatchedTx.length - 20} weitere
                                </p>
                            )}
                        </div>
                    )}
                </CardContent>
            </Card>

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
