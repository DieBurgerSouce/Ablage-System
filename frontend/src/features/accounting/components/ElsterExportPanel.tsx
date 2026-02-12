/**
 * ElsterExportPanel - USt-VA ELSTER XML Export
 *
 * Panel zum Anzeigen der berechneten USt-Beträge
 * und Download als ELSTER-kompatibles XML.
 */

import { useState, useMemo } from 'react';
import { FileOutput, Download, Loader2, CheckCircle2, AlertCircle, Calendar } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useVatMonthlyReport, useVatQuarterlyReport, useElsterXmlDownload } from '../hooks/use-elster-queries';

interface ElsterExportPanelProps {
    companyId: string;
}

const MONTHS = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
];

const QUARTERS = ['Q1 (Jan-Mrz)', 'Q2 (Apr-Jun)', 'Q3 (Jul-Sep)', 'Q4 (Okt-Dez)'];

type PeriodType = 'monthly' | 'quarterly';

function formatCurrency(value: number): string {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
    }).format(value);
}

export function ElsterExportPanel({ companyId }: ElsterExportPanelProps) {
    const currentDate = useMemo(() => new Date(), []);
    const [year, setYear] = useState(() => new Date().getFullYear());
    const [periodType, setPeriodType] = useState<PeriodType>('monthly');
    const [month, setMonth] = useState(() => Math.max(1, new Date().getMonth())); // vorheriger Monat
    const [quarter, setQuarter] = useState(() => Math.max(1, Math.ceil(new Date().getMonth() / 3)));

    const years = useMemo(() => {
        const current = currentDate.getFullYear();
        return [current, current - 1, current - 2];
    }, [currentDate]);

    // Monatsbericht
    const monthlyReport = useVatMonthlyReport(
        companyId,
        year,
        month,
        periodType === 'monthly',
    );

    // Quartalsbericht
    const quarterlyReport = useVatQuarterlyReport(
        companyId,
        year,
        quarter,
        periodType === 'quarterly',
    );

    const report = periodType === 'monthly' ? monthlyReport : quarterlyReport;
    const reportData = report.data;

    // Download-Mutation
    const downloadMutation = useElsterXmlDownload();

    // Für den XML-Download benötigen wir den Monat:
    // Bei Quartal: erster Monat des Quartals
    const downloadMonth = periodType === 'monthly' ? month : (quarter - 1) * 3 + 1;

    const handleDownload = () => {
        downloadMutation.mutate({
            companyId,
            year,
            month: downloadMonth,
        });
    };

    const isLoading = report.isLoading;
    const isError = report.isError;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <FileOutput className="h-8 w-8 text-primary" />
                <div>
                    <h1 className="text-3xl font-bold tracking-tight font-display">
                        ELSTER XML Export
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        USt-Voranmeldung als ELSTER-kompatibles XML exportieren
                    </p>
                </div>
            </div>

            {/* Perioden-Auswahl */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Calendar className="h-5 w-5" />
                        Meldezeitraum
                    </CardTitle>
                    <CardDescription>
                        Wählen Sie den Zeitraum für die USt-Voranmeldung
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-4 items-end">
                        {/* Periodentyp */}
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Zeitraumart</label>
                            <Select
                                value={periodType}
                                onValueChange={(v) => setPeriodType(v as PeriodType)}
                            >
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="monthly">Monatlich</SelectItem>
                                    <SelectItem value="quarterly">Quartalsweise</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Jahr */}
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Jahr</label>
                            <Select
                                value={String(year)}
                                onValueChange={(v) => setYear(Number(v))}
                            >
                                <SelectTrigger className="w-[120px]">
                                    <SelectValue />
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

                        {/* Monat oder Quartal */}
                        {periodType === 'monthly' ? (
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Monat</label>
                                <Select
                                    value={String(month)}
                                    onValueChange={(v) => setMonth(Number(v))}
                                >
                                    <SelectTrigger className="w-[180px]">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {MONTHS.map((name, idx) => (
                                            <SelectItem key={idx + 1} value={String(idx + 1)}>
                                                {name}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Quartal</label>
                                <Select
                                    value={String(quarter)}
                                    onValueChange={(v) => setQuarter(Number(v))}
                                >
                                    <SelectTrigger className="w-[200px]">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {QUARTERS.map((name, idx) => (
                                            <SelectItem key={idx + 1} value={String(idx + 1)}>
                                                {name}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Ladestate */}
            {isLoading && (
                <Card>
                    <CardContent className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        <span className="ml-3 text-muted-foreground">USt-Daten werden berechnet...</span>
                    </CardContent>
                </Card>
            )}

            {/* Fehler */}
            {isError && (
                <Card className="border-destructive">
                    <CardContent className="flex items-center gap-3 py-6">
                        <AlertCircle className="h-6 w-6 text-destructive" />
                        <div>
                            <p className="font-medium text-destructive">Fehler beim Laden der USt-Daten</p>
                            <p className="text-sm text-muted-foreground">
                                Bitte prüfen Sie, ob Buchungen für den gewaehlten Zeitraum vorhanden sind.
                            </p>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Report-Daten */}
            {reportData && (
                <>
                    {/* Status-Badge */}
                    <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">Zeitraum:</span>
                        <Badge variant="outline">{reportData.period_label}</Badge>
                        {reportData.status === 'draft' && (
                            <Badge variant="secondary">Entwurf</Badge>
                        )}
                        {reportData.status === 'submitted' && (
                            <Badge variant="default" className="bg-green-600">
                                <CheckCircle2 className="h-3 w-3 mr-1" />
                                Eingereicht
                            </Badge>
                        )}
                        {reportData.status === 'accepted' && (
                            <Badge variant="default" className="bg-green-700">
                                <CheckCircle2 className="h-3 w-3 mr-1" />
                                Akzeptiert
                            </Badge>
                        )}
                    </div>

                    {/* Umsätze */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Umsätze (Output VAT)</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                <ReportRow
                                    label="Steuerpflichtige Umsätze 19% (Kz 81)"
                                    net={reportData.output_vat_19.net_amount}
                                    vat={reportData.output_vat_19.vat_amount}
                                    count={reportData.output_vat_19.count}
                                />
                                <ReportRow
                                    label="Steuerpflichtige Umsätze 7% (Kz 86)"
                                    net={reportData.output_vat_7.net_amount}
                                    vat={reportData.output_vat_7.vat_amount}
                                    count={reportData.output_vat_7.count}
                                />
                                <ReportRow
                                    label="Innergemeinschaftliche Lieferungen (Kz 41)"
                                    net={reportData.inner_eu_deliveries.net_amount}
                                    count={reportData.inner_eu_deliveries.count}
                                />
                                <ReportRow
                                    label="Ausfuhrlieferungen (Kz 43)"
                                    net={reportData.export_deliveries.net_amount}
                                    count={reportData.export_deliveries.count}
                                />
                                <Separator />
                                <div className="flex justify-between font-semibold">
                                    <span>Umsatzsteuer gesamt</span>
                                    <span>{formatCurrency(reportData.total_output_vat)}</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Vorsteuer */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Vorsteuer (Input VAT)</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                <ReportRow
                                    label="Vorsteuer aus Rechnungen (Kz 66)"
                                    vat={reportData.input_vat.vat_amount}
                                    count={reportData.input_vat.count}
                                />
                                <ReportRow
                                    label="Vorsteuer innergem. Erwerb (Kz 61)"
                                    vat={reportData.input_vat_inner_eu.vat_amount}
                                    count={reportData.input_vat_inner_eu.count}
                                />
                                <ReportRow
                                    label="Vorsteuer Reverse Charge (Kz 67)"
                                    vat={reportData.input_vat_reverse_charge.vat_amount}
                                    count={reportData.input_vat_reverse_charge.count}
                                />
                                <Separator />
                                <div className="flex justify-between font-semibold">
                                    <span>Vorsteuer gesamt</span>
                                    <span>{formatCurrency(reportData.total_input_vat)}</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Zahllast */}
                    <Card className={reportData.vat_payable >= 0 ? 'border-orange-300' : 'border-green-300'}>
                        <CardContent className="pt-6">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-lg font-semibold">
                                        {reportData.vat_payable >= 0 ? 'Zahllast (Kz 83)' : 'Erstattungsanspruch (Kz 83)'}
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Umsatzsteuer abzueglich Vorsteuer
                                    </p>
                                </div>
                                <span className={`text-2xl font-bold ${reportData.vat_payable >= 0 ? 'text-orange-600' : 'text-green-600'}`}>
                                    {formatCurrency(Math.abs(reportData.vat_payable))}
                                </span>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Download-Button */}
                    <Card>
                        <CardContent className="pt-6">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="font-medium">ELSTER XML herunterladen</p>
                                    <p className="text-sm text-muted-foreground">
                                        Datei kann in ElsterOnline oder ELSTER-Software importiert werden
                                    </p>
                                </div>
                                <Button
                                    onClick={handleDownload}
                                    disabled={downloadMutation.isPending}
                                    size="lg"
                                >
                                    {downloadMutation.isPending ? (
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    ) : (
                                        <Download className="h-4 w-4 mr-2" />
                                    )}
                                    {downloadMutation.isPending ? 'Wird erstellt...' : 'ELSTER XML herunterladen'}
                                </Button>
                            </div>
                            {downloadMutation.isSuccess && (
                                <div className="mt-3 flex items-center gap-2 text-sm text-green-600">
                                    <CheckCircle2 className="h-4 w-4" />
                                    XML-Datei wurde erfolgreich heruntergeladen
                                </div>
                            )}
                            {downloadMutation.isError && (
                                <div className="mt-3 flex items-center gap-2 text-sm text-destructive">
                                    <AlertCircle className="h-4 w-4" />
                                    Fehler beim Erstellen der XML-Datei
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </>
            )}
        </div>
    );
}

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

interface ReportRowProps {
    label: string;
    net?: number;
    vat?: number;
    count: number;
}

function ReportRow({ label, net, vat, count }: ReportRowProps) {
    return (
        <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
                <span>{label}</span>
                {count > 0 && (
                    <Badge variant="secondary" className="text-xs h-5 px-1.5">
                        {count}
                    </Badge>
                )}
            </div>
            <div className="flex gap-6 text-right">
                {net !== undefined && (
                    <div className="w-28">
                        <span className="text-muted-foreground text-xs block">Netto</span>
                        {formatCurrency(net)}
                    </div>
                )}
                {vat !== undefined && (
                    <div className="w-28">
                        <span className="text-muted-foreground text-xs block">MwSt</span>
                        {formatCurrency(vat)}
                    </div>
                )}
            </div>
        </div>
    );
}
