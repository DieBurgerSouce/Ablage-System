import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, AlertTriangle, Clock } from 'lucide-react';
import type { PredictiveAlertResponse } from '@/lib/api/services/monitoring';

interface PredictiveAlertsListProps {
    alerts: PredictiveAlertResponse[] | undefined;
    isLoading: boolean;
}

function getSeverityBadge(severity: string) {
    switch (severity) {
        case 'critical':
            return <Badge variant="destructive">Kritisch</Badge>;
        case 'high':
            return <Badge className="bg-orange-500 text-white hover:bg-orange-600">Hoch</Badge>;
        case 'warning':
        case 'medium':
            return <Badge className="bg-yellow-500 text-white hover:bg-yellow-600">Warnung</Badge>;
        default:
            return <Badge variant="secondary">Info</Badge>;
    }
}

function formatEta(etaMinutes: number | null): string {
    if (etaMinutes == null) return 'Unbekannt';
    if (etaMinutes < 60) return `${Math.round(etaMinutes)} Min.`;
    if (etaMinutes < 1440) return `${(etaMinutes / 60).toFixed(1)} Std.`;
    return `${(etaMinutes / 1440).toFixed(1)} Tage`;
}

export function PredictiveAlertsList({ alerts, isLoading }: PredictiveAlertsListProps) {
    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5" />
                        Proaktive Warnungen
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

    const alertList = alerts ?? [];

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5" />
                    Proaktive Warnungen
                </CardTitle>
                <CardDescription>
                    Vorhergesagte Probleme basierend auf aktuellen Trends
                </CardDescription>
            </CardHeader>
            <CardContent>
                {alertList.length === 0 ? (
                    <div className="text-center py-6 text-muted-foreground">
                        <p className="text-sm">Keine aktiven Warnungen</p>
                        <p className="text-xs mt-1">Das System laeuft im normalen Betrieb</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {alertList.map((alert) => (
                            <div
                                key={alert.id}
                                className="flex items-start gap-3 p-3 rounded-lg border bg-muted/30"
                            >
                                <div className="space-y-1 flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-medium text-sm">{alert.title}</span>
                                        {getSeverityBadge(alert.severity)}
                                        {alert.acknowledged && (
                                            <Badge variant="outline" className="text-xs">
                                                Bestaetigt
                                            </Badge>
                                        )}
                                    </div>
                                    <p className="text-xs text-muted-foreground">{alert.message}</p>
                                    <div className="flex items-center gap-4 mt-1">
                                        {alert.eta_minutes != null && (
                                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                                                <Clock className="h-3 w-3" />
                                                Voraussichtlich in {formatEta(alert.eta_minutes)}
                                            </span>
                                        )}
                                        <span className="text-xs text-muted-foreground">
                                            Konfidenz: {(alert.confidence * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    {alert.recommendation && (
                                        <p className="text-xs text-primary mt-1">{alert.recommendation}</p>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
