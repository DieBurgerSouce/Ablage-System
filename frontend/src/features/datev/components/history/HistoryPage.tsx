/**
 * DATEV Export Historie Seite
 *
 * Zeigt die vollstaendige Export-Historie mit Pagination.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { ChevronLeft, ChevronRight, History, FileSpreadsheet } from 'lucide-react';
import { useExportHistory } from '@/features/datev/hooks/use-datev-queries';
import { formatDateTime, formatPeriod, formatNumber } from '@/features/datev/utils';
import { ExportStatusBadge } from './ExportStatusBadge';

const PAGE_SIZE = 20;

export function HistoryPage() {
    const [page, setPage] = useState(1);

    const { data, isLoading, error } = useExportHistory({
        page,
        page_size: PAGE_SIZE,
    });

    const exports = data?.items || [];
    const total = data?.total || 0;
    const totalPages = Math.ceil(total / PAGE_SIZE);

    const handlePreviousPage = () => {
        setPage((p) => Math.max(1, p - 1));
    };

    const handleNextPage = () => {
        setPage((p) => Math.min(totalPages, p + 1));
    };

    if (error) {
        return (
            <Card>
                <CardContent className="py-10 text-center text-muted-foreground">
                    Fehler beim Laden der Export-Historie.
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h2 className="text-xl font-semibold">Export-Historie</h2>
                <p className="text-sm text-muted-foreground">
                    Alle bisherigen DATEV-Exporte mit Status und Details.
                </p>
            </div>

            {/* Historie-Tabelle */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                        <History className="h-4 w-4" />
                        Exportierte Buchungsstapel
                    </CardTitle>
                    <CardDescription>
                        {isLoading ? 'Lade...' : `${total} Export${total !== 1 ? 's' : ''} insgesamt`}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3, 4, 5].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : exports.length === 0 ? (
                        <div className="text-center py-10">
                            <FileSpreadsheet className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <h3 className="text-lg font-medium mb-2">Keine Exports vorhanden</h3>
                            <p className="text-sm text-muted-foreground mb-4">
                                Sie haben noch keine DATEV-Exporte erstellt. Starten Sie Ihren
                                ersten Export auf der Export-Seite.
                            </p>
                        </div>
                    ) : (
                        <>
                            <div className="rounded-md border">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Dateiname</TableHead>
                                            <TableHead>Zeitraum</TableHead>
                                            <TableHead className="text-right">Dokumente</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead>Exportiert am</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {exports.map((exp) => (
                                            <TableRow key={exp.id}>
                                                <TableCell className="font-mono text-sm">
                                                    {exp.filename}
                                                </TableCell>
                                                <TableCell>
                                                    {formatPeriod(exp.period_from, exp.period_to)}
                                                </TableCell>
                                                <TableCell className="text-right font-mono">
                                                    {formatNumber(exp.document_count)}
                                                </TableCell>
                                                <TableCell>
                                                    <ExportStatusBadge status={exp.status} />
                                                </TableCell>
                                                <TableCell>
                                                    {formatDateTime(exp.exported_at)}
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>

                            {/* Pagination */}
                            {totalPages > 1 && (
                                <div className="flex items-center justify-between mt-4">
                                    <p className="text-sm text-muted-foreground">
                                        Seite {page} von {totalPages}
                                    </p>
                                    <div className="flex gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={handlePreviousPage}
                                            disabled={page === 1}
                                        >
                                            <ChevronLeft className="h-4 w-4 mr-1" />
                                            Zurueck
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={handleNextPage}
                                            disabled={page === totalPages}
                                        >
                                            Weiter
                                            <ChevronRight className="h-4 w-4 ml-1" />
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
