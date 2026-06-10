/**
 * DATEV Export Seite
 *
 * Wizard-artige Oberflaeche zum Erstellen von DATEV-Exporten.
 */

import { useState } from 'react';
import { logger } from '@/lib/logger';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Loader2, Download, Eye, AlertCircle, CheckCircle2, FileSpreadsheet, ArrowRight } from 'lucide-react';
import { Link } from '@tanstack/react-router';
import {
    useConfigs,
    useDefaultConfig,
    useExportPreview,
    useExecuteExport,
} from '@/features/datev/hooks/use-datev-queries';
import { formatKontenrahmen } from '@/features/datev/utils';
import { ExportPreview } from './ExportPreview';
import type { DATEVExportPreview as ExportPreviewData } from '@/lib/api/services/datev';

export function ExportPage() {
    const { data: configs, isLoading: configsLoading } = useConfigs();
    const { data: defaultConfig } = useDefaultConfig();

    // Formular-State
    const [selectedConfigId, setSelectedConfigId] = useState<string>('');
    const [periodFrom, setPeriodFrom] = useState<string>('');
    const [periodTo, setPeriodTo] = useState<string>('');
    const [includeAlreadyExported, setIncludeAlreadyExported] = useState(false);

    // Preview-State
    const [preview, setPreview] = useState<ExportPreviewData | null>(null);
    const [exportSuccess, setExportSuccess] = useState(false);

    const exportPreviewMutation = useExportPreview();
    const executeExportMutation = useExecuteExport();

    // Effektive Konfiguration (ausgewählte oder Default)
    const effectiveConfigId = selectedConfigId || defaultConfig?.id || '';
    const selectedConfig = configs?.find((c) => c.id === effectiveConfigId);

    const handlePreview = async () => {
        setExportSuccess(false);
        try {
            const result = await exportPreviewMutation.mutateAsync({
                config_id: effectiveConfigId || undefined,
                period_from: periodFrom || undefined,
                period_to: periodTo || undefined,
                include_already_exported: includeAlreadyExported,
            });
            setPreview(result);
        } catch (error) {
            // IMMER loggen (auch Production) - Fehler sind kritisch für Monitoring
            logger.error('DATEV: Preview-Fehler', error);
        }
    };

    const handleExport = async () => {
        try {
            await executeExportMutation.mutateAsync({
                config_id: effectiveConfigId || undefined,
                period_from: periodFrom || undefined,
                period_to: periodTo || undefined,
                include_already_exported: includeAlreadyExported,
            });
            setExportSuccess(true);
            // Preview zurücksetzen nach erfolgreichem Export
            setPreview(null);
        } catch (error) {
            // IMMER loggen (auch Production) - Fehler sind kritisch für Monitoring
            logger.error('DATEV: Export-Fehler', error);
        }
    };

    // Keine Konfigurationen vorhanden
    if (!configsLoading && (!configs || configs.length === 0)) {
        return (
            <Card>
                <CardContent className="py-12">
                    <div className="text-center">
                        <FileSpreadsheet className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                        <h3 className="text-lg font-medium mb-2">
                            Keine Konfiguration vorhanden
                        </h3>
                        <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
                            Bevor Sie einen Export erstellen können, müssen Sie zuerst eine
                            DATEV-Konfiguration mit Beraternummer und Mandantennummer anlegen.
                        </p>
                        <Button asChild>
                            <Link to="/admin/datev/config">
                                Konfiguration erstellen
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Export-Erfolgs-Meldung */}
            {exportSuccess && (
                <Alert className="border-green-200 bg-green-50">
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                    <AlertTitle className="text-green-800">Export erfolgreich</AlertTitle>
                    <AlertDescription className="text-green-700">
                        Der DATEV-Export wurde erstellt und der Download gestartet.
                    </AlertDescription>
                </Alert>
            )}

            {/* Export-Formular */}
            <Card>
                <CardHeader>
                    <CardTitle>Neuen Export erstellen</CardTitle>
                    <CardDescription>
                        Wählen Sie eine Konfiguration und optional einen Zeitraum für den Export.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Konfiguration */}
                    <div className="space-y-2">
                        <Label htmlFor="config">Konfiguration</Label>
                        {configsLoading ? (
                            <Skeleton className="h-10 w-full" />
                        ) : (
                            <Select
                                value={effectiveConfigId}
                                onValueChange={setSelectedConfigId}
                            >
                                <SelectTrigger
                                    id="config"
                                    aria-label="DATEV-Konfiguration auswählen"
                                >
                                    <SelectValue placeholder="Konfiguration wählen" />
                                </SelectTrigger>
                                <SelectContent>
                                    {configs?.map((config) => (
                                        <SelectItem key={config.id} value={config.id}>
                                            {config.berater_nr} / {config.mandanten_nr} -{' '}
                                            {formatKontenrahmen(config.kontenrahmen)}
                                            {config.is_default && ' (Standard)'}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}
                        {selectedConfig && (
                            <p className="text-xs text-muted-foreground">
                                Kontenrahmen: {formatKontenrahmen(selectedConfig.kontenrahmen)} |
                                WJ-Beginn: {selectedConfig.wj_beginn}
                            </p>
                        )}
                    </div>

                    {/* Zeitraum */}
                    <div className="space-y-2">
                        <Label>Zeitraum (optional)</Label>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="period_from" className="text-xs text-muted-foreground">
                                    Von
                                </Label>
                                <Input
                                    id="period_from"
                                    type="date"
                                    value={periodFrom}
                                    onChange={(e) => setPeriodFrom(e.target.value)}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="period_to" className="text-xs text-muted-foreground">
                                    Bis
                                </Label>
                                <Input
                                    id="period_to"
                                    type="date"
                                    value={periodTo}
                                    onChange={(e) => setPeriodTo(e.target.value)}
                                />
                            </div>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Wenn leer, werden alle verfügbaren Dokumente exportiert.
                        </p>
                    </div>

                    {/* Optionen */}
                    <div className="space-y-4">
                        <Label>Optionen</Label>
                        <div className="flex items-center space-x-2">
                            <Checkbox
                                id="include_already_exported"
                                checked={includeAlreadyExported}
                                onCheckedChange={(checked) =>
                                    setIncludeAlreadyExported(!!checked)
                                }
                            />
                            <Label htmlFor="include_already_exported" className="cursor-pointer">
                                Bereits exportierte Dokumente einschließen
                            </Label>
                        </div>
                    </div>

                    {/* Aktionen */}
                    <div className="flex gap-4 pt-4">
                        <Button
                            variant="outline"
                            onClick={handlePreview}
                            disabled={
                                !effectiveConfigId ||
                                exportPreviewMutation.isPending ||
                                executeExportMutation.isPending // Cross-disable
                            }
                        >
                            {exportPreviewMutation.isPending ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Analysiere...
                                </>
                            ) : (
                                <>
                                    <Eye className="mr-2 h-4 w-4" />
                                    Vorschau
                                </>
                            )}
                        </Button>

                        <Button
                            onClick={handleExport}
                            disabled={
                                !effectiveConfigId ||
                                executeExportMutation.isPending ||
                                exportPreviewMutation.isPending || // Cross-disable
                                // F4: Export erst nach erfolgreicher Vorprüfung freigeben
                                // (kein blinder Export); leere Vorschau bleibt gesperrt.
                                preview === null ||
                                preview.document_count === 0
                            }
                        >
                            {executeExportMutation.isPending ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Exportiere...
                                </>
                            ) : (
                                <>
                                    <Download className="mr-2 h-4 w-4" />
                                    Export starten
                                </>
                            )}
                        </Button>
                    </div>
                    {preview === null && (
                        <p className="text-xs text-muted-foreground">
                            Bitte zuerst eine Vorschau erstellen, um den Export zu prüfen.
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* Vorschau */}
            {preview && <ExportPreview preview={preview} />}

            {/* Fehler-Anzeige mit Retry-Option */}
            {exportPreviewMutation.isError && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Fehler bei der Vorschau</AlertTitle>
                    <AlertDescription className="flex flex-col gap-3">
                        <span>
                            {exportPreviewMutation.error instanceof Error
                                ? exportPreviewMutation.error.message
                                : 'Die Verbindung zum Server ist fehlgeschlagen.'}
                        </span>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handlePreview}
                            disabled={exportPreviewMutation.isPending}
                            className="w-fit"
                        >
                            Erneut versuchen
                        </Button>
                    </AlertDescription>
                </Alert>
            )}

            {executeExportMutation.isError && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Fehler beim Export</AlertTitle>
                    <AlertDescription className="flex flex-col gap-3">
                        <span>
                            {executeExportMutation.error instanceof Error
                                ? executeExportMutation.error.message
                                : 'Die Verbindung zum Server ist fehlgeschlagen.'}
                        </span>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleExport}
                            disabled={executeExportMutation.isPending}
                            className="w-fit"
                        >
                            Erneut versuchen
                        </Button>
                    </AlertDescription>
                </Alert>
            )}
        </div>
    );
}
