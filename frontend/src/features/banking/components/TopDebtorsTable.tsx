/**
 * Top Debtors/Creditors Table
 * Zeigt die groessten Schuldner oder Glaeubiger
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { useTopDebtors, useTopCreditors } from '../hooks/use-banking-queries';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { formatCurrency } from '../utils/format';

interface TopDebtorsTableProps {
    type?: 'debtors' | 'creditors';
    limit?: number;
}

export function TopDebtorsTable({ type = 'debtors', limit = 10 }: TopDebtorsTableProps) {
    // Nur den benoetigten Query ausfuehren (Performance-Optimierung)
    const debtorsQuery = useTopDebtors(limit, type === 'debtors');
    const creditorsQuery = useTopCreditors(limit, type === 'creditors');

    const { data, isLoading, error } = type === 'debtors' ? debtorsQuery : creditorsQuery;

    const title = type === 'debtors' ? 'Top Schuldner' : 'Top Gläubiger';
    const description = type === 'debtors'
        ? 'Kunden mit den höchsten offenen Forderungen'
        : 'Lieferanten mit den höchsten offenen Verbindlichkeiten';
    const Icon = type === 'debtors' ? ArrowUpRight : ArrowDownRight;
    const iconColor = type === 'debtors' ? 'text-green-600' : 'text-red-600';

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-32" />
                    <Skeleton className="h-4 w-64" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[250px] w-full" />
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

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center gap-2">
                    <Icon className={`h-5 w-5 ${iconColor}`} />
                    <CardTitle>{title}</CardTitle>
                </div>
                <CardDescription>{description}</CardDescription>
            </CardHeader>
            <CardContent>
                <div className="rounded-md border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="w-[50px]">#</TableHead>
                                <TableHead>{type === 'debtors' ? 'Kunde' : 'Lieferant'}</TableHead>
                                <TableHead className="text-right">Betrag</TableHead>
                                <TableHead className="text-right">Rechnungen</TableHead>
                                <TableHead className="text-right">Ø Tage</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {data.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                                        Keine Einträge gefunden
                                    </TableCell>
                                </TableRow>
                            ) : (
                                data.map((item, index) => (
                                    <TableRow key={item.counterparty}>
                                        <TableCell className="text-muted-foreground">
                                            {index + 1}
                                        </TableCell>
                                        <TableCell className="font-medium">
                                            {item.counterparty || 'Unbekannt'}
                                        </TableCell>
                                        <TableCell className="text-right font-mono">
                                            {formatCurrency(item.total_amount)}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {item.invoice_count}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {item.avg_days_overdue > 0 ? (
                                                <span className="text-destructive">
                                                    {Math.round(item.avg_days_overdue)}
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground">-</span>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
}
