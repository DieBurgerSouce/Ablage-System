/**
 * Transactions Page
 * Transaktionen anzeigen, filtern und verwalten
 */

import { useState, useMemo } from 'react';
import { ArrowLeftRight, Search, Filter, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
// Badge importiert aber nicht genutzt - entfernt
import { Skeleton } from '@/components/ui/skeleton';
import { useTransactions, useAccounts } from '@/features/banking/hooks/use-banking-queries';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import { TransactionStatusBadge } from './TransactionStatusBadge';
import type { TransactionFilter, ReconciliationStatus } from '@/lib/api/services/banking';

const PAGE_SIZE = 25;

const RECONCILIATION_STATUS_OPTIONS: { value: ReconciliationStatus | 'all'; label: string }[] = [
    { value: 'all', label: 'Alle Status' },
    { value: 'unmatched', label: 'Unabgeglichen' },
    { value: 'matched', label: 'Abgeglichen' },
    { value: 'partial', label: 'Teilweise' },
    { value: 'manual', label: 'Manuell' },
    { value: 'ignored', label: 'Ignoriert' },
];

export function TransactionsPage() {
    const [page, setPage] = useState(0);
    const [filters, setFilters] = useState<TransactionFilter>({});
    const [searchText, setSearchText] = useState('');

    // Accounts für Filter-Dropdown
    const { data: accounts } = useAccounts();

    // Aktuelle Filter mit Pagination
    const currentFilters = useMemo(
        () => ({
            ...filters,
            search: searchText || undefined,
            offset: page * PAGE_SIZE,
            limit: PAGE_SIZE,
        }),
        [filters, searchText, page]
    );

    const { data, isLoading, error } = useTransactions(currentFilters);

    const handleFilterChange = (key: keyof TransactionFilter, value: string | undefined) => {
        setPage(0); // Reset page when filter changes
        setFilters((prev) => ({
            ...prev,
            [key]: value === 'all' ? undefined : value,
        }));
    };

    const handleSearch = (value: string) => {
        setPage(0);
        setSearchText(value);
    };

    const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

    if (error) {
        return (
            <Card>
                <CardContent className="py-8">
                    <p className="text-center text-destructive">
                        Fehler beim Laden der Transaktionen: {error.message}
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Transaktionen</h1>
                <p className="text-muted-foreground">
                    Alle importierten Banktransaktionen anzeigen und verwalten.
                </p>
            </div>

            {/* Filters */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                        <Filter className="h-4 w-4" />
                        Filter
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                        {/* Search */}
                        <div className="space-y-2">
                            <Label>Suche</Label>
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Verwendungszweck, Name..."
                                    className="pl-9"
                                    value={searchText}
                                    onChange={(e) => handleSearch(e.target.value)}
                                />
                            </div>
                        </div>

                        {/* Account Filter */}
                        <div className="space-y-2">
                            <Label>Konto</Label>
                            <Select
                                value={filters.bank_account_id || 'all'}
                                onValueChange={(v) => handleFilterChange('bank_account_id', v)}
                            >
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

                        {/* Status Filter */}
                        <div className="space-y-2">
                            <Label>Abgleich-Status</Label>
                            <Select
                                value={filters.reconciliation_status || 'all'}
                                onValueChange={(v) => handleFilterChange('reconciliation_status', v)}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder="Alle Status" />
                                </SelectTrigger>
                                <SelectContent>
                                    {RECONCILIATION_STATUS_OPTIONS.map((option) => (
                                        <SelectItem key={option.value} value={option.value}>
                                            {option.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Date From */}
                        <div className="space-y-2">
                            <Label>Von Datum</Label>
                            <Input
                                type="date"
                                value={filters.date_from || ''}
                                onChange={(e) => handleFilterChange('date_from', e.target.value || undefined)}
                            />
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Table */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <ArrowLeftRight className="h-5 w-5" />
                        Transaktionen ({data?.total ?? 0})
                    </CardTitle>
                    <CardDescription>
                        Importierte Kontobewegungen mit Abgleich-Status.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3, 4, 5].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : !data?.items.length ? (
                        <div className="py-8 text-center">
                            <ArrowLeftRight className="mx-auto h-12 w-12 text-muted-foreground/50" />
                            <h3 className="mt-4 text-lg font-semibold">Keine Transaktionen</h3>
                            <p className="text-muted-foreground">
                                Importieren Sie Kontoauszüge, um Transaktionen anzuzeigen.
                            </p>
                            <Button className="mt-4" asChild>
                                <a href="/admin/banking">Zum Banking</a>
                            </Button>
                        </div>
                    ) : (
                        <>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Datum</TableHead>
                                        <TableHead>Gegenpartei</TableHead>
                                        <TableHead>Verwendungszweck</TableHead>
                                        <TableHead className="text-right">Betrag</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Verknüpfung</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {data.items.map((tx) => (
                                        <TableRow key={tx.id}>
                                            <TableCell className="whitespace-nowrap">
                                                {formatDate(tx.booking_date)}
                                            </TableCell>
                                            <TableCell className="max-w-[200px] truncate">
                                                {tx.counterparty_name || '-'}
                                            </TableCell>
                                            <TableCell className="max-w-[300px] truncate text-muted-foreground text-sm">
                                                {tx.reference_text || '-'}
                                            </TableCell>
                                            <TableCell
                                                className={`text-right font-mono whitespace-nowrap ${
                                                    tx.amount >= 0 ? 'text-green-600' : 'text-red-600'
                                                }`}
                                            >
                                                {tx.amount >= 0 ? '+' : ''}
                                                {formatCurrency(tx.amount, { currency: tx.currency })}
                                            </TableCell>
                                            <TableCell>
                                                <TransactionStatusBadge status={tx.reconciliation_status} />
                                            </TableCell>
                                            <TableCell>
                                                {tx.matched_document_id ? (
                                                    <Button variant="ghost" size="sm" asChild>
                                                        <a href={`/documents/${tx.matched_document_id}`}>
                                                            <ExternalLink className="h-4 w-4 mr-1" />
                                                            {tx.matched_invoice_number || 'Dokument'}
                                                        </a>
                                                    </Button>
                                                ) : (
                                                    <span className="text-muted-foreground text-sm">-</span>
                                                )}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>

                            {/* Pagination */}
                            {totalPages > 1 && (
                                <div className="flex items-center justify-between mt-4 pt-4 border-t">
                                    <p className="text-sm text-muted-foreground">
                                        Seite {page + 1} von {totalPages} ({data.total} Transaktionen)
                                    </p>
                                    <div className="flex gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setPage((p) => Math.max(0, p - 1))}
                                            disabled={page === 0}
                                        >
                                            <ChevronLeft className="h-4 w-4" />
                                            Zurück
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                                            disabled={page >= totalPages - 1}
                                        >
                                            Weiter
                                            <ChevronRight className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
