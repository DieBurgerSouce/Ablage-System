/**
 * DATEV Export Vorschau Komponente
 *
 * Zeigt eine Vorschau der zu exportierenden Buchungen.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { FileText, Calculator, Calendar } from 'lucide-react';
import { formatCurrency, formatDate, formatPeriod } from '@/features/datev/utils';
import { ExportWarnings } from './ExportWarnings';
import type { DATEVExportPreview as ExportPreviewData } from '@/lib/api/services/datev';

interface ExportPreviewProps {
    preview: ExportPreviewData;
}

export function ExportPreview({ preview }: ExportPreviewProps) {
    return (
        <div className="space-y-6">
            {/* Statistiken */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Dokumente</CardTitle>
                        <FileText className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{preview.document_count}</div>
                        <p className="text-xs text-muted-foreground">
                            Buchungen zum Export bereit
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Gesamtbetrag</CardTitle>
                        <Calculator className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {formatCurrency(preview.total_amount)}
                        </div>
                        <p className="text-xs text-muted-foreground">Summe aller Buchungen</p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Zeitraum</CardTitle>
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-lg font-bold">
                            {formatPeriod(preview.period_from, preview.period_to)}
                        </div>
                        <p className="text-xs text-muted-foreground">Belegdatum-Bereich</p>
                    </CardContent>
                </Card>
            </div>

            {/* Warnungen */}
            <ExportWarnings
                warnings={preview.warnings}
                skippedCount={preview.skipped_count}
                skippedReasons={preview.skipped_reasons}
            />

            {/* Beispiel-Buchungen */}
            {preview.sample_entries.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Beispiel-Buchungen</CardTitle>
                        <CardDescription>
                            Die ersten {preview.sample_entries.length} Buchungen aus dem Export
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="rounded-md border overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Betrag</TableHead>
                                        <TableHead>S/H</TableHead>
                                        <TableHead>Konto</TableHead>
                                        <TableHead>Gegenkonto</TableHead>
                                        <TableHead>BU</TableHead>
                                        <TableHead>Belegdatum</TableHead>
                                        <TableHead>Beleg-Nr.</TableHead>
                                        <TableHead>Buchungstext</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {preview.sample_entries.map((entry, index) => (
                                        <TableRow key={index}>
                                            <TableCell className="font-mono">
                                                {formatCurrency(entry.umsatz as number)}
                                            </TableCell>
                                            <TableCell>
                                                <Badge
                                                    variant={
                                                        entry.soll_haben === 'S'
                                                            ? 'default'
                                                            : 'secondary'
                                                    }
                                                >
                                                    {entry.soll_haben as string}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="font-mono">
                                                {entry.konto as string}
                                            </TableCell>
                                            <TableCell className="font-mono">
                                                {entry.gegenkonto as string}
                                            </TableCell>
                                            <TableCell className="font-mono">
                                                {(entry.bu_schluessel as string) || '–'}
                                            </TableCell>
                                            <TableCell>
                                                {formatDate(entry.belegdatum as string)}
                                            </TableCell>
                                            <TableCell className="font-mono text-sm">
                                                {(entry.belegfeld_1 as string) || '–'}
                                            </TableCell>
                                            <TableCell className="max-w-[200px] truncate">
                                                {(entry.buchungstext as string) || '–'}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                        {preview.document_count > preview.sample_entries.length && (
                            <p className="text-sm text-muted-foreground mt-4 text-center">
                                ... und {preview.document_count - preview.sample_entries.length}{' '}
                                weitere Buchungen
                            </p>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Keine Buchungen */}
            {preview.document_count === 0 && (
                <Card>
                    <CardContent className="py-10 text-center text-muted-foreground">
                        <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <h3 className="text-lg font-medium mb-2">Keine exportierbaren Dokumente</h3>
                        <p className="text-sm">
                            Es wurden keine Dokumente gefunden, die den Filterkriterien entsprechen.
                        </p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
