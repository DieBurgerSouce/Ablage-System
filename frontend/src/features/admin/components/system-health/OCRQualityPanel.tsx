import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, Eye } from 'lucide-react';
import type { DegradationAlertResponse } from '@/lib/api/services/monitoring';

interface OCRQualityPanelProps {
    degradationAlerts: DegradationAlertResponse[] | undefined;
    isLoading: boolean;
}

function getSeverityBadge(severity: string) {
    switch (severity) {
        case 'critical':
            return <Badge variant="destructive">Kritisch</Badge>;
        case 'warning':
            return <Badge className="bg-yellow-500 text-white hover:bg-yellow-600">Warnung</Badge>;
        default:
            return <Badge variant="secondary">Normal</Badge>;
    }
}

function getBackendDisplayName(backend: string): string {
    const names: Record<string, string> = {
        deepseek: 'DeepSeek-Janus-Pro',
        'got-ocr': 'GOT-OCR 2.0',
        surya: 'Surya + Docling',
        'surya-gpu': 'Surya GPU',
    };
    return names[backend] ?? backend;
}

function getMetricDisplayName(metric: string): string {
    const names: Record<string, string> = {
        cer: 'Character Error Rate',
        wer: 'Word Error Rate',
        confidence: 'Konfidenz',
        umlaut_accuracy: 'Umlaut-Genauigkeit',
    };
    return names[metric] ?? metric;
}

export function OCRQualityPanel({ degradationAlerts, isLoading }: OCRQualityPanelProps) {
    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Eye className="h-5 w-5" />
                        OCR-Qualität
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    const alerts = degradationAlerts ?? [];

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Eye className="h-5 w-5" />
                    OCR-Qualität
                </CardTitle>
                <CardDescription>
                    Überwachung der OCR-Backend-Qualität und Degradations-Erkennung
                </CardDescription>
            </CardHeader>
            <CardContent>
                {alerts.length === 0 ? (
                    <div className="text-center py-6 text-muted-foreground">
                        <p className="text-sm">Keine Qualitätsprobleme erkannt</p>
                        <p className="text-xs mt-1">Alle OCR-Backends arbeiten im normalen Bereich</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {alerts.map((alert, idx) => (
                            <div
                                key={`${alert.backend}-${alert.metric}-${idx}`}
                                className="flex items-start justify-between p-3 rounded-lg border bg-muted/30"
                            >
                                <div className="space-y-1 flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium text-sm">
                                            {getBackendDisplayName(alert.backend)}
                                        </span>
                                        {getSeverityBadge(alert.severity)}
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                        {getMetricDisplayName(alert.metric)}: {(alert.current_value * 100).toFixed(1)}%
                                        {alert.days_to_threshold != null && (
                                            <> &mdash; Schwellwert in {alert.days_to_threshold.toFixed(0)} Tagen</>
                                        )}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        {alert.recommendation}
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
