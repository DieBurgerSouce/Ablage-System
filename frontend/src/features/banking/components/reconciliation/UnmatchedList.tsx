/**
 * Unmatched Transactions List
 *
 * Zeigt alle unabgeglichenen Transaktionen mit:
 * - Filterung und Sortierung
 * - Match-Vorschläge-Anzeige pro Transaktion
 * - Bulk-Aktionen
 * - Priorisierung nach Alter und Betrag
 */

import { useState, useMemo } from 'react';
import {
    AlertCircle,
    ArrowUpDown,
    Calendar,
    ChevronDown,
    ChevronUp,
    Clock,
    Filter,
    Link2,
    Loader2,
    Search,
    Sparkles,
    TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import { useUnmatchedTransactionsEnhanced, useAccounts } from '@/features/banking/hooks/use-banking-queries';
import type { BankTransaction } from '@/lib/api/services/banking';
import { cn } from '@/lib/utils';

interface UnmatchedListProps {
    selectedAccountId?: string;
    onSelectTransaction: (transaction: BankTransaction) => void;
    onBulkMatch?: (transactionIds: string[]) => void;
    selectedTransactionIds?: string[];
    onSelectionChange?: (ids: string[]) => void;
}

// Hilfsfunktion für Dringlichkeits-Badge
function UrgencyBadge({ daysSince }: { daysSince: number }) {
    if (daysSince >= 30) {
        return (
            <Badge variant="destructive" className="gap-1">
                <AlertCircle className="h-3 w-3" />
                {daysSince} Tage
            </Badge>
        );
    }
    if (daysSince >= 14) {
        return (
            <Badge variant="default" className="gap-1 bg-yellow-500">
                <Clock className="h-3 w-3" />
                {daysSince} Tage
            </Badge>
        );
    }
    if (daysSince >= 7) {
        return (
            <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" />
                {daysSince} Tage
            </Badge>
        );
    }
    return (
        <span className="text-sm text-muted-foreground">{daysSince} Tage</span>
    );
}

// Konfidenz-Indikator
function ConfidenceIndicator({ confidence }: { confidence: number | null }) {
    if (confidence === null) return null;

    const percent = Math.round(confidence * 100);
    const getColor = () => {
        if (percent >= 90) return 'bg-green-500';
        if (percent >= 70) return 'bg-yellow-500';
        if (percent >= 50) return 'bg-orange-500';
        return 'bg-red-500';
    };

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className="flex items-center gap-1.5">
                        <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
                        <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                            <div
                                className={cn('h-full transition-all', getColor())}
                                style={{ width: `${percent}%` }}
                            />
                        </div>
                        <span className="text-xs text-muted-foreground w-8">
                            {percent}%
                        </span>
                    </div>
                </TooltipTrigger>
                <TooltipContent>
                    <p>Beste Match-Konfidenz: {percent}%</p>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

export function UnmatchedList({
    selectedAccountId,
    onSelectTransaction,
    onBulkMatch,
    selectedTransactionIds = [],
    onSelectionChange,
}: UnmatchedListProps) {
    // State
    const [searchText, setSearchText] = useState('');
    const [sortBy, setSortBy] = useState<'date' | 'amount' | 'urgency'>('date');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
    const [minAmount, setMinAmount] = useState<string>('');
    const [showFilters, setShowFilters] = useState(false);

    // Data Fetching
    const { data: accounts } = useAccounts();
    const {
        data: unmatchedTx,
        isLoading,
        refetch,
    } = useUnmatchedTransactionsEnhanced({
        bank_account_id: selectedAccountId === 'all' ? undefined : selectedAccountId,
        limit: 100,
    });

    // Erweiterte Transaktionsdaten mit Backend-Feldern
    const enrichedTransactions = useMemo(() => {
        if (!unmatchedTx) return [];

        const now = new Date();
        return unmatchedTx.map((tx) => {
            const bookingDate = new Date(tx.booking_date);
            const daysSince = tx.days_since_booking ?? Math.floor(
                (now.getTime() - bookingDate.getTime()) / (1000 * 60 * 60 * 24)
            );

            return {
                ...tx,
                daysSince,
                suggestionCount: tx.suggestion_count ?? 0,
                bestMatchConfidence: tx.best_match_confidence ?? null,
            };
        });
    }, [unmatchedTx]);

    // Filterung
    const filteredTransactions = useMemo(() => {
        let filtered = [...enrichedTransactions];

        // Textsuche
        if (searchText.trim()) {
            const search = searchText.toLowerCase();
            filtered = filtered.filter(
                (tx) =>
                    tx.counterparty_name?.toLowerCase().includes(search) ||
                    tx.reference_text?.toLowerCase().includes(search) ||
                    tx.counterparty_iban?.toLowerCase().includes(search)
            );
        }

        // Mindestbetrag
        if (minAmount && !isNaN(parseFloat(minAmount))) {
            const min = parseFloat(minAmount);
            filtered = filtered.filter((tx) => Math.abs(tx.amount) >= min);
        }

        return filtered;
    }, [enrichedTransactions, searchText, minAmount]);

    // Sortierung
    const sortedTransactions = useMemo(() => {
        const sorted = [...filteredTransactions];

        sorted.sort((a, b) => {
            let comparison = 0;

            switch (sortBy) {
                case 'date':
                    comparison = new Date(a.booking_date).getTime() - new Date(b.booking_date).getTime();
                    break;
                case 'amount':
                    comparison = Math.abs(a.amount) - Math.abs(b.amount);
                    break;
                case 'urgency':
                    comparison = a.daysSince - b.daysSince;
                    break;
            }

            return sortOrder === 'desc' ? -comparison : comparison;
        });

        return sorted;
    }, [filteredTransactions, sortBy, sortOrder]);

    // Checkbox-Handler
    const handleSelectAll = () => {
        if (!onSelectionChange) return;

        if (selectedTransactionIds.length === sortedTransactions.length) {
            onSelectionChange([]);
        } else {
            onSelectionChange(sortedTransactions.map((tx) => tx.id));
        }
    };

    const handleSelectOne = (id: string) => {
        if (!onSelectionChange) return;

        if (selectedTransactionIds.includes(id)) {
            onSelectionChange(selectedTransactionIds.filter((i) => i !== id));
        } else {
            onSelectionChange([...selectedTransactionIds, id]);
        }
    };

    const toggleSort = (field: typeof sortBy) => {
        if (sortBy === field) {
            setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
        } else {
            setSortBy(field);
            setSortOrder('desc');
        }
    };

    // Zusammenfassung
    const summary = useMemo(() => {
        const total = sortedTransactions.length;
        const totalAmount = sortedTransactions.reduce((sum, tx) => sum + Math.abs(tx.amount), 0);
        const urgent = sortedTransactions.filter((tx) => tx.daysSince >= 14).length;
        const withSuggestions = sortedTransactions.filter(
            (tx) => tx.bestMatchConfidence && tx.bestMatchConfidence >= 0.7
        ).length;

        return { total, totalAmount, urgent, withSuggestions };
    }, [sortedTransactions]);

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Unabgeglichene Transaktionen</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {[1, 2, 3, 4, 5].map((i) => (
                            <Skeleton key={i} className="h-16 w-full" />
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                        Unabgeglichene Transaktionen
                        <Badge variant="outline">{summary.total}</Badge>
                        {summary.urgent > 0 && (
                            <Badge variant="destructive">{summary.urgent} dringend</Badge>
                        )}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                        {selectedTransactionIds.length > 0 && onBulkMatch && (
                            <Button
                                size="sm"
                                onClick={() => onBulkMatch(selectedTransactionIds)}
                            >
                                <Link2 className="h-4 w-4 mr-1" />
                                {selectedTransactionIds.length} ausgewählt
                            </Button>
                        )}
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowFilters(!showFilters)}
                        >
                            <Filter className="h-4 w-4 mr-1" />
                            Filter
                            {showFilters ? (
                                <ChevronUp className="h-4 w-4 ml-1" />
                            ) : (
                                <ChevronDown className="h-4 w-4 ml-1" />
                            )}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => refetch()}>
                            <Loader2 className={cn('h-4 w-4', isLoading && 'animate-spin')} />
                        </Button>
                    </div>
                </div>

                {/* Summary Stats */}
                <div className="flex gap-4 text-sm text-muted-foreground mt-2">
                    <span>
                        Gesamt: {formatCurrency(summary.totalAmount, { currency: 'EUR' })}
                    </span>
                    {summary.withSuggestions > 0 && (
                        <span className="text-green-600">
                            <Sparkles className="h-3 w-3 inline mr-1" />
                            {summary.withSuggestions} mit guten Vorschlägen
                        </span>
                    )}
                </div>
            </CardHeader>

            <CardContent>
                {/* Filter Section */}
                {showFilters && (
                    <div className="grid gap-4 md:grid-cols-3 mb-4 p-4 bg-muted/50 rounded-lg">
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Suche</label>
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Name, IBAN, Verwendungszweck..."
                                    className="pl-9"
                                    value={searchText}
                                    onChange={(e) => setSearchText(e.target.value)}
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Mindestbetrag</label>
                            <Input
                                type="number"
                                placeholder="0,00"
                                value={minAmount}
                                onChange={(e) => setMinAmount(e.target.value)}
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Sortierung</label>
                            <Select
                                value={`${sortBy}-${sortOrder}`}
                                onValueChange={(v) => {
                                    const [field, order] = v.split('-');
                                    setSortBy(field as typeof sortBy);
                                    setSortOrder(order as typeof sortOrder);
                                }}
                            >
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="date-desc">Neueste zuerst</SelectItem>
                                    <SelectItem value="date-asc">Älteste zuerst</SelectItem>
                                    <SelectItem value="amount-desc">Höchster Betrag</SelectItem>
                                    <SelectItem value="amount-asc">Niedrigster Betrag</SelectItem>
                                    <SelectItem value="urgency-desc">Dringendste zuerst</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                )}

                {/* Transactions Table */}
                {sortedTransactions.length === 0 ? (
                    <div className="py-12 text-center">
                        <TrendingUp className="mx-auto h-12 w-12 text-green-500/50" />
                        <h3 className="mt-4 text-lg font-semibold">
                            Alle Transaktionen abgeglichen!
                        </h3>
                        <p className="text-muted-foreground">
                            Es gibt keine offenen Transaktionen zum Verknüpfen.
                        </p>
                    </div>
                ) : (
                    <div className="border rounded-lg">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    {onSelectionChange && (
                                        <TableHead className="w-10">
                                            <Checkbox
                                                checked={
                                                    selectedTransactionIds.length ===
                                                    sortedTransactions.length
                                                }
                                                onCheckedChange={handleSelectAll}
                                                aria-label="Alle auswählen"
                                            />
                                        </TableHead>
                                    )}
                                    <TableHead
                                        className="cursor-pointer hover:bg-muted/50"
                                        onClick={() => toggleSort('date')}
                                    >
                                        <div className="flex items-center gap-1">
                                            <Calendar className="h-4 w-4" />
                                            Datum
                                            {sortBy === 'date' && (
                                                <ArrowUpDown className="h-4 w-4" />
                                            )}
                                        </div>
                                    </TableHead>
                                    <TableHead>Gegenpartei</TableHead>
                                    <TableHead>Verwendungszweck</TableHead>
                                    <TableHead
                                        className="text-right cursor-pointer hover:bg-muted/50"
                                        onClick={() => toggleSort('amount')}
                                    >
                                        <div className="flex items-center justify-end gap-1">
                                            Betrag
                                            {sortBy === 'amount' && (
                                                <ArrowUpDown className="h-4 w-4" />
                                            )}
                                        </div>
                                    </TableHead>
                                    <TableHead
                                        className="cursor-pointer hover:bg-muted/50"
                                        onClick={() => toggleSort('urgency')}
                                    >
                                        <div className="flex items-center gap-1">
                                            Alter
                                            {sortBy === 'urgency' && (
                                                <ArrowUpDown className="h-4 w-4" />
                                            )}
                                        </div>
                                    </TableHead>
                                    <TableHead>Match</TableHead>
                                    <TableHead className="w-10" />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {sortedTransactions.map((tx) => (
                                    <TableRow
                                        key={tx.id}
                                        className={cn(
                                            'cursor-pointer hover:bg-muted/50',
                                            selectedTransactionIds.includes(tx.id) && 'bg-primary/5'
                                        )}
                                        onClick={() => onSelectTransaction(tx)}
                                    >
                                        {onSelectionChange && (
                                            <TableCell onClick={(e) => e.stopPropagation()}>
                                                <Checkbox
                                                    checked={selectedTransactionIds.includes(tx.id)}
                                                    onCheckedChange={() => handleSelectOne(tx.id)}
                                                    aria-label={`Transaktion ${tx.counterparty_name} auswählen`}
                                                />
                                            </TableCell>
                                        )}
                                        <TableCell className="font-medium">
                                            {formatDate(tx.booking_date)}
                                        </TableCell>
                                        <TableCell>
                                            <div className="max-w-[200px]">
                                                <p className="font-medium truncate">
                                                    {tx.counterparty_name || 'Unbekannt'}
                                                </p>
                                                {tx.counterparty_iban && (
                                                    <p className="text-xs text-muted-foreground truncate">
                                                        {tx.counterparty_iban}
                                                    </p>
                                                )}
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <p className="text-sm text-muted-foreground truncate max-w-[250px]">
                                                {tx.reference_text || '-'}
                                            </p>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <span
                                                className={cn(
                                                    'font-mono font-medium',
                                                    tx.amount >= 0 ? 'text-green-600' : 'text-red-600'
                                                )}
                                            >
                                                {tx.amount >= 0 ? '+' : ''}
                                                {formatCurrency(tx.amount, { currency: tx.currency })}
                                            </span>
                                        </TableCell>
                                        <TableCell>
                                            <UrgencyBadge daysSince={tx.daysSince} />
                                        </TableCell>
                                        <TableCell>
                                            <ConfidenceIndicator confidence={tx.bestMatchConfidence} />
                                        </TableCell>
                                        <TableCell>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onSelectTransaction(tx);
                                                }}
                                            >
                                                <Link2 className="h-4 w-4" />
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
