/**
 * Aging Report Table
 * Zeigt Forderungen oder Verbindlichkeiten als Tabelle
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import { ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import { useReceivablesAging, usePayablesAging } from '../hooks/use-banking-queries';
import { formatCurrency, formatDate } from '../utils/format';

interface AgingReportTableProps {
    type: 'receivables' | 'payables';
}

const BUCKET_LABELS: Record<string, string> = {
    'current': 'Aktuell',
    '1-30': '1-30 Tage',
    '31-60': '31-60 Tage',
    '61-90': '61-90 Tage',
    '90+': '90+ Tage',
};

const BUCKET_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
    'current': 'default',
    '1-30': 'secondary',
    '31-60': 'outline',
    '61-90': 'outline',
    '90+': 'destructive',
};

function BucketBadge({ bucket }: { bucket: string }) {
    const isOverdue = bucket !== 'current';
    const label = BUCKET_LABELS[bucket] ?? bucket;
    return (
        <Badge
            variant={BUCKET_VARIANTS[bucket] ?? 'outline'}
            aria-label={isOverdue ? `${label} überfällig` : label}
        >
            {label}
            {isOverdue && <span className="sr-only"> (überfällig)</span>}
        </Badge>
    );
}

export function AgingReportTable({ type }: AgingReportTableProps) {
    const [page, setPage] = useState(0);
    const [bucketFilter, setBucketFilter] = useState<string>('all');
    const pageSize = 10;

    // Nur den benötigten Query ausführen (Performance-Optimierung)
    const receivablesQuery = useReceivablesAging(undefined, type === 'receivables');
    const payablesQuery = usePayablesAging(undefined, type === 'payables');

    const { data, isLoading, error } = type === 'receivables' ? receivablesQuery : payablesQuery;

    const title = type === 'receivables' ? 'Offene Forderungen' : 'Offene Verbindlichkeiten';
    const counterpartyLabel = type === 'receivables' ? 'Debitor' : 'Kreditor';

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-4 w-64" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[400px] w-full" />
                </CardContent>
            </Card>
        );
    }

    if (error || !data) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>{title}</CardTitle>
                    <CardDescription className="text-destructive">
                        Fehler beim Laden der Daten
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    // Filter und Paginierung
    let filteredItems = data.line_items;
    if (bucketFilter !== 'all') {
        filteredItems = filteredItems.filter((item) => item.bucket === bucketFilter);
    }

    const totalItems = filteredItems.length;
    const totalPages = Math.ceil(totalItems / pageSize);
    const paginatedItems = filteredItems.slice(page * pageSize, (page + 1) * pageSize);

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle>{title}</CardTitle>
                    <CardDescription>
                        {data.summary.total_count} Positionen, Summe: {formatCurrency(data.summary.total_amount)}
                        {data.summary.total_overdue > 0 && (
                            <span className="text-destructive ml-2">
                                ({formatCurrency(data.summary.total_overdue)} überfällig)
                            </span>
                        )}
                    </CardDescription>
                </div>
                <Select value={bucketFilter} onValueChange={(v) => { setBucketFilter(v); setPage(0); }}>
                    <SelectTrigger className="w-[140px]">
                        <SelectValue placeholder="Filter" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle</SelectItem>
                        <SelectItem value="current">Aktuell</SelectItem>
                        <SelectItem value="1-30">1-30 Tage</SelectItem>
                        <SelectItem value="31-60">31-60 Tage</SelectItem>
                        <SelectItem value="61-90">61-90 Tage</SelectItem>
                        <SelectItem value="90+">90+ Tage</SelectItem>
                    </SelectContent>
                </Select>
            </CardHeader>
            <CardContent>
                <div className="rounded-md border overflow-x-auto">
                    <Table className="min-w-[700px]">
                        <TableHeader>
                            <TableRow>
                                <TableHead scope="col">Rechnung</TableHead>
                                <TableHead scope="col">{counterpartyLabel}</TableHead>
                                <TableHead scope="col" className="text-right">Betrag</TableHead>
                                <TableHead scope="col">Fälligkeit</TableHead>
                                <TableHead scope="col">Status</TableHead>
                                <TableHead scope="col" className="text-right">Tage</TableHead>
                                <TableHead scope="col" className="w-[50px]">
                                    <span className="sr-only">Aktionen</span>
                                </TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {paginatedItems.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                                        Keine Einträge gefunden
                                    </TableCell>
                                </TableRow>
                            ) : (
                                paginatedItems.map((item) => (
                                    <TableRow key={item.document_id}>
                                        <TableCell className="font-medium">
                                            {item.invoice_number || '-'}
                                        </TableCell>
                                        <TableCell>{item.counterparty || '-'}</TableCell>
                                        <TableCell className="text-right font-mono">
                                            {formatCurrency(item.amount)}
                                        </TableCell>
                                        <TableCell>{formatDate(item.due_date)}</TableCell>
                                        <TableCell>
                                            <BucketBadge bucket={item.bucket} />
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {item.days_overdue > 0 ? (
                                                <span
                                                    className="text-destructive font-medium"
                                                    aria-label={`${item.days_overdue} Tage überfällig`}
                                                >
                                                    +{item.days_overdue}
                                                    <span className="sr-only"> Tage überfällig</span>
                                                </span>
                                            ) : (
                                                <span
                                                    className="text-muted-foreground"
                                                    aria-label={item.days_overdue === 0 ? 'Heute fällig' : `${Math.abs(item.days_overdue)} Tage bis zur Fälligkeit`}
                                                >
                                                    {item.days_overdue}
                                                    <span className="sr-only">
                                                        {item.days_overdue === 0 ? ' (heute fällig)' : ` Tage bis zur Fälligkeit`}
                                                    </span>
                                                </span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <Button variant="ghost" size="icon" asChild aria-label={`Dokument ${item.invoice_number || item.document_id} in neuem Tab öffnen`}>
                                                <a href={`/documents/${item.document_id}`} target="_blank" rel="noopener noreferrer">
                                                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                                                </a>
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="flex items-center justify-between mt-4">
                        <p className="text-sm text-muted-foreground">
                            Zeige {page * pageSize + 1}-{Math.min((page + 1) * pageSize, totalItems)} von {totalItems}
                        </p>
                        <div className="flex gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setPage((p) => Math.max(0, p - 1))}
                                disabled={page === 0}
                                aria-label="Vorherige Seite"
                            >
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                                disabled={page >= totalPages - 1}
                                aria-label="Nächste Seite"
                            >
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
