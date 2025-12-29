/**
 * Import Preview
 * Zeigt Vorschau der zu importierenden Transaktionen
 */

import { CheckCircle, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
// Badge nicht genutzt
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import type { ImportPreview as ImportPreviewType } from '@/lib/api/services/banking';

interface ImportPreviewProps {
    preview: ImportPreviewType;
}

export function ImportPreview({ preview }: ImportPreviewProps) {
    const hasWarnings = preview.warnings.length > 0;

    return (
        <div className="space-y-4">
            {/* Summary */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Transaktionen</CardDescription>
                        <CardTitle className="text-2xl">{preview.transaction_count}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Einnahmen</CardDescription>
                        <CardTitle className="text-2xl text-green-600">
                            {formatCurrency(preview.total_credits)}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Ausgaben</CardDescription>
                        <CardTitle className="text-2xl text-red-500">
                            {formatCurrency(preview.total_debits)}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Zeitraum</CardDescription>
                        <CardTitle className="text-sm">
                            {preview.date_from && preview.date_to
                                ? `${formatDate(preview.date_from)} - ${formatDate(preview.date_to)}`
                                : '-'}
                        </CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Warnings */}
            {hasWarnings && (
                <Alert>
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>Warnungen</AlertTitle>
                    <AlertDescription>
                        <ul className="list-disc list-inside mt-2">
                            {preview.warnings.map((warning, i) => (
                                <li key={i}>{warning}</li>
                            ))}
                        </ul>
                    </AlertDescription>
                </Alert>
            )}

            {/* Preview Table */}
            {preview.sample_transactions.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Vorschau (Beispiel-Transaktionen)</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Datum</TableHead>
                                    <TableHead>Gegenpartei</TableHead>
                                    <TableHead>Verwendungszweck</TableHead>
                                    <TableHead className="text-right">Betrag</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {preview.sample_transactions.map((item, index) => {
                                    const amount = (item as { amount?: number }).amount ?? 0;
                                    const currency = (item as { currency?: string }).currency ?? 'EUR';
                                    const bookingDate = (item as { booking_date?: string }).booking_date;
                                    const counterparty = (item as { counterparty_name?: string }).counterparty_name;
                                    const reference = (item as { reference_text?: string }).reference_text;

                                    return (
                                        <TableRow key={index}>
                                            <TableCell className="whitespace-nowrap">
                                                {bookingDate ? formatDate(bookingDate) : '-'}
                                            </TableCell>
                                            <TableCell className="max-w-[150px] truncate">
                                                {counterparty || '-'}
                                            </TableCell>
                                            <TableCell className="max-w-[200px] truncate text-sm text-muted-foreground">
                                                {reference || '-'}
                                            </TableCell>
                                            <TableCell
                                                className={`text-right font-mono whitespace-nowrap ${
                                                    amount >= 0 ? 'text-green-600' : 'text-red-600'
                                                }`}
                                            >
                                                {amount >= 0 ? '+' : ''}
                                                {formatCurrency(amount, { currency })}
                                            </TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            )}

            {/* Ready indicator */}
            {preview.transaction_count > 0 && (
                <Alert className="border-green-500 bg-green-50 dark:bg-green-950">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    <AlertTitle className="text-green-700 dark:text-green-300">
                        Bereit zum Import
                    </AlertTitle>
                    <AlertDescription className="text-green-600 dark:text-green-400">
                        {preview.transaction_count} Transaktionen können importiert werden.
                        Format erkannt: {preview.format_detected} ({Math.round(preview.format_confidence * 100)}% Konfidenz)
                    </AlertDescription>
                </Alert>
            )}
        </div>
    );
}
