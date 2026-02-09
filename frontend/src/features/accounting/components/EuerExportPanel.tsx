/**
 * EuerExportPanel - Anlage EUeR Export
 *
 * Panel zur Anzeige der EUeR-Zusammenfassung und
 * Export als PDF (HTML-Druck) oder JSON.
 */

import { useState, useMemo } from 'react';
import {
    Calculator,
    Printer,
    Download,
    Loader2,
    AlertCircle,
    TrendingUp,
    TrendingDown,
    ArrowRight
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { useAnlageEuer, useEurReport } from '../hooks/use-euer-queries';
import { getAnlageEuerHtmlUrl } from '../api/euer-api';
import type { AnlageEUeRResponse, EURReportResponse } from '../api/euer-api';

interface EuerExportPanelProps {
    companyId: string;
}

function formatCurrency(value: number): string {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
    }).format(value);
}

// Anlage EUeR Zeilen-Definitionen
const ANLAGE_ZEILEN: Array<{
    key: string;
    zeile: string;
    label: string;
    section: 'einnahmen' | 'ausgaben' | 'ergebnis';
    isSummary: boolean;
}> = [
    { key: 'Zeile_11', zeile: '11', label: 'Betriebseinnahmen (Waren)', section: 'einnahmen', isSummary: false },
    { key: 'Zeile_12', zeile: '12', label: 'Betriebseinnahmen (Dienstleistungen)', section: 'einnahmen', isSummary: false },
    { key: 'Zeile_14', zeile: '14', label: 'Zinsertraege', section: 'einnahmen', isSummary: false },
    { key: 'Zeile_16', zeile: '16', label: 'Sonstige Einnahmen', section: 'einnahmen', isSummary: false },
    { key: 'Zeile_18', zeile: '18', label: 'Summe Betriebseinnahmen', section: 'einnahmen', isSummary: true },
    { key: 'Zeile_20', zeile: '20', label: 'Wareneinkauf', section: 'ausgaben', isSummary: false },
    { key: 'Zeile_22', zeile: '22', label: 'Personalkosten', section: 'ausgaben', isSummary: false },
    { key: 'Zeile_27', zeile: '27', label: 'Miete/Pacht', section: 'ausgaben', isSummary: false },
    { key: 'Zeile_30', zeile: '30', label: 'Fahrzeugkosten', section: 'ausgaben', isSummary: false },
    { key: 'Zeile_35', zeile: '35', label: 'Buerokosten', section: 'ausgaben', isSummary: false },
    { key: 'Zeile_36', zeile: '36', label: 'Abschreibungen (AfA)', section: 'ausgaben', isSummary: false },
    { key: 'Zeile_40', zeile: '40', label: 'Sonstige Betriebsausgaben', section: 'ausgaben', isSummary: false },
    { key: 'Zeile_42', zeile: '42', label: 'Summe Betriebsausgaben', section: 'ausgaben', isSummary: true },
    { key: 'Zeile_43', zeile: '43', label: 'Gewinn / Verlust', section: 'ergebnis', isSummary: true },
];

export function EuerExportPanel({ companyId }: EuerExportPanelProps) {
    const currentDate = useMemo(() => new Date(), []);
    const [year, setYear] = useState(() => new Date().getFullYear());

    const years = useMemo(() => {
        const current = currentDate.getFullYear();
        return [current, current - 1, current - 2, current - 3];
    }, [currentDate]);

    // Daten laden
    const anlageQuery = useAnlageEuer(companyId, year, !!companyId);
    const reportQuery = useEurReport(companyId, year, !!companyId);

    const isLoading = anlageQuery.isLoading || reportQuery.isLoading;
    const error = anlageQuery.error || reportQuery.error;

    const anlageData = anlageQuery.data as AnlageEUeRResponse | undefined;
    const reportData = reportQuery.data as EURReportResponse | undefined;

    // PDF/Druck oeffnen
    const handlePrintPdf = () => {
        const url = getAnlageEuerHtmlUrl(companyId, year);
        window.open(url, '_blank');
    };

    // JSON herunterladen
    const handleDownloadJson = () => {
        if (!anlageData) return;
        const json = JSON.stringify(anlageData, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `Anlage_EUeR_${year}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
                        <Calculator className="h-6 w-6" />
                        Anlage E&Uuml;R
                    </h2>
                    <p className="text-muted-foreground">
                        Einnahmen-&Uuml;berschuss-Rechnung gem. &sect; 4 Abs. 3 EStG
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Select
                        value={String(year)}
                        onValueChange={(val) => setYear(Number(val))}
                    >
                        <SelectTrigger className="w-[140px]">
                            <SelectValue placeholder="Jahr" />
                        </SelectTrigger>
                        <SelectContent>
                            {years.map((y) => (
                                <SelectItem key={y} value={String(y)}>
                                    {y}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            </div>

            {/* Fehler-Anzeige */}
            {error && (
                <Card className="border-destructive">
                    <CardContent className="flex items-center gap-2 py-4">
                        <AlertCircle className="h-5 w-5 text-destructive" />
                        <span className="text-destructive">
                            Fehler beim Laden der Daten: {(error as Error).message}
                        </span>
                    </CardContent>
                </Card>
            )}

            {/* Lade-Anzeige */}
            {isLoading && (
                <Card>
                    <CardContent className="flex items-center justify-center gap-2 py-12">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span className="text-muted-foreground">Daten werden geladen...</span>
                    </CardContent>
                </Card>
            )}

            {/* Zusammenfassung */}
            {reportData && !isLoading && (
                <>
                    <div className="grid gap-4 md:grid-cols-3">
                        <Card>
                            <CardHeader className="pb-2">
                                <CardDescription>Einnahmen</CardDescription>
                                <CardTitle className="text-2xl text-green-600 dark:text-green-400">
                                    {formatCurrency(reportData.total_income)}
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                    <TrendingUp className="h-3 w-3" />
                                    {reportData.income_categories.length} Kategorien
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardHeader className="pb-2">
                                <CardDescription>Ausgaben</CardDescription>
                                <CardTitle className="text-2xl text-red-600 dark:text-red-400">
                                    {formatCurrency(reportData.total_expenses)}
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                    <TrendingDown className="h-3 w-3" />
                                    {reportData.expense_categories.length} Kategorien
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardHeader className="pb-2">
                                <CardDescription>
                                    {reportData.is_profit ? 'Gewinn' : 'Verlust'}
                                </CardDescription>
                                <CardTitle className={`text-2xl ${reportData.is_profit ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                    {formatCurrency(reportData.profit_loss)}
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <Badge variant={reportData.is_profit ? 'default' : 'destructive'}>
                                    {reportData.is_profit ? 'Gewinn' : 'Verlust'}
                                </Badge>
                            </CardContent>
                        </Card>
                    </div>

                    <Separator />
                </>
            )}

            {/* Anlage EUeR Zeilen-Tabelle */}
            {anlageData && !isLoading && (
                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle>Anlage E&Uuml;R - Zeilen&uuml;bersicht</CardTitle>
                                <CardDescription>
                                    Steuerformular-Zeilen nach BMF-Vorgabe fuer {year}
                                </CardDescription>
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleDownloadJson}
                                >
                                    <Download className="h-4 w-4 mr-2" />
                                    Als JSON herunterladen
                                </Button>
                                <Button
                                    size="sm"
                                    onClick={handlePrintPdf}
                                >
                                    <Printer className="h-4 w-4 mr-2" />
                                    Als PDF drucken
                                </Button>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-[80px]">Zeile</TableHead>
                                    <TableHead>Bezeichnung</TableHead>
                                    <TableHead className="text-right w-[180px]">Betrag</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {/* Einnahmen-Sektion */}
                                <TableRow className="bg-muted/50">
                                    <TableCell colSpan={3} className="font-semibold">
                                        I. Betriebseinnahmen
                                    </TableCell>
                                </TableRow>
                                {ANLAGE_ZEILEN.filter((z) => z.section === 'einnahmen').map((z) => {
                                    const value = anlageData.anlage_eur[z.key as keyof typeof anlageData.anlage_eur] as number;
                                    return (
                                        <TableRow key={z.key} className={z.isSummary ? 'font-bold border-t-2' : ''}>
                                            <TableCell className="text-muted-foreground">{z.zeile}</TableCell>
                                            <TableCell>{z.label}</TableCell>
                                            <TableCell className="text-right">{formatCurrency(value)}</TableCell>
                                        </TableRow>
                                    );
                                })}

                                {/* Ausgaben-Sektion */}
                                <TableRow className="bg-muted/50">
                                    <TableCell colSpan={3} className="font-semibold">
                                        II. Betriebsausgaben
                                    </TableCell>
                                </TableRow>
                                {ANLAGE_ZEILEN.filter((z) => z.section === 'ausgaben').map((z) => {
                                    const value = anlageData.anlage_eur[z.key as keyof typeof anlageData.anlage_eur] as number;
                                    return (
                                        <TableRow key={z.key} className={z.isSummary ? 'font-bold border-t-2' : ''}>
                                            <TableCell className="text-muted-foreground">{z.zeile}</TableCell>
                                            <TableCell>{z.label}</TableCell>
                                            <TableCell className="text-right">{formatCurrency(value)}</TableCell>
                                        </TableRow>
                                    );
                                })}

                                {/* Ergebnis-Sektion */}
                                <TableRow className="bg-muted/50">
                                    <TableCell colSpan={3} className="font-semibold">
                                        III. Ergebnis
                                    </TableCell>
                                </TableRow>
                                {ANLAGE_ZEILEN.filter((z) => z.section === 'ergebnis').map((z) => {
                                    const value = anlageData.anlage_eur[z.key as keyof typeof anlageData.anlage_eur] as number;
                                    const isProfit = value >= 0;
                                    return (
                                        <TableRow key={z.key} className="font-bold text-lg border-t-2">
                                            <TableCell className="text-muted-foreground">{z.zeile}</TableCell>
                                            <TableCell>{z.label}</TableCell>
                                            <TableCell className={`text-right ${isProfit ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                                {formatCurrency(value)}
                                            </TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            )}

            {/* Kategorien-Aufschluesselung */}
            {reportData && !isLoading && (
                <div className="grid gap-4 md:grid-cols-2">
                    {/* Einnahmen nach Kategorie */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Einnahmen nach Kategorie</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {reportData.income_categories.length === 0 ? (
                                <p className="text-sm text-muted-foreground">Keine Einnahmen erfasst.</p>
                            ) : (
                                <div className="space-y-3">
                                    {reportData.income_categories.map((cat) => (
                                        <div key={cat.category} className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <ArrowRight className="h-3 w-3 text-green-500" />
                                                <span className="text-sm">{cat.label}</span>
                                                <Badge variant="secondary" className="text-xs">
                                                    {cat.count}
                                                </Badge>
                                            </div>
                                            <span className="text-sm font-medium">
                                                {formatCurrency(cat.amount)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Ausgaben nach Kategorie */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Ausgaben nach Kategorie</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {reportData.expense_categories.length === 0 ? (
                                <p className="text-sm text-muted-foreground">Keine Ausgaben erfasst.</p>
                            ) : (
                                <div className="space-y-3">
                                    {reportData.expense_categories.map((cat) => (
                                        <div key={cat.category} className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <ArrowRight className="h-3 w-3 text-red-500" />
                                                <span className="text-sm">{cat.label}</span>
                                                <Badge variant="secondary" className="text-xs">
                                                    {cat.count}
                                                </Badge>
                                            </div>
                                            <span className="text-sm font-medium">
                                                {formatCurrency(cat.amount)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    );
}
