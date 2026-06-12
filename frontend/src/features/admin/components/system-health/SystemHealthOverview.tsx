import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
    Cpu,
    MemoryStick,
    HardDrive,
    MonitorSpeaker,
    Loader2,
    AlertCircle,
    RefreshCw,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { monitoringService } from '@/lib/api/services/monitoring';
import { MetricCard } from './MetricCard';
import { OCRQualityPanel } from './OCRQualityPanel';
import { PredictiveAlertsList } from './PredictiveAlertsList';

const AUTO_REFRESH_INTERVAL = 30_000; // 30 Sekunden

function getStatusBadge(status: string) {
    switch (status) {
        case 'gesund':
            return <Badge className="bg-green-600 text-white">Gesund</Badge>;
        case 'beeinträchtigt':
            return <Badge className="bg-yellow-500 text-white">Beeinträchtigt</Badge>;
        case 'kritisch':
            return <Badge variant="destructive">Kritisch</Badge>;
        default:
            return <Badge variant="secondary">{status}</Badge>;
    }
}

export function SystemHealthOverview() {
    const [autoRefresh, setAutoRefresh] = useState(true);

    const {
        data: healthData,
        isLoading: healthLoading,
        error: healthError,
        dataUpdatedAt,
    } = useQuery({
        queryKey: ['system-health', 'detailed'],
        queryFn: monitoringService.getDetailedHealth,
        refetchInterval: autoRefresh ? AUTO_REFRESH_INTERVAL : false,
        staleTime: 10_000,
    });

    const {
        data: predictiveAlerts,
        isLoading: alertsLoading,
    } = useQuery({
        queryKey: ['system-health', 'predictive-alerts'],
        queryFn: monitoringService.getPredictiveAlerts,
        refetchInterval: autoRefresh ? AUTO_REFRESH_INTERVAL : false,
        staleTime: 10_000,
    });

    const {
        data: ocrDegradation,
        isLoading: ocrLoading,
    } = useQuery({
        queryKey: ['system-health', 'ocr-degradation'],
        queryFn: monitoringService.getOCRDegradation,
        refetchInterval: autoRefresh ? AUTO_REFRESH_INTERVAL : false,
        staleTime: 10_000,
    });

    if (healthLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="flex items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin" />
                    <span>Lade Systemdaten...</span>
                </div>
            </div>
        );
    }

    if (healthError) {
        return (
            <div className="flex items-center justify-center h-64">
                <Card className="max-w-md">
                    <CardContent className="pt-6">
                        <div className="flex items-start gap-3">
                            <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="font-medium">Fehler beim Laden</p>
                                <p className="text-sm text-muted-foreground mt-1">
                                    Die Systemdaten konnten nicht geladen werden.
                                    Bitte versuchen Sie es später erneut.
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        );
    }

    const komponenten = healthData?.komponenten ?? {};

    // Extract component metrics
    const gpuDetails = komponenten.gpu?.details as Record<string, number> | null;
    const diskDetails = komponenten.speicherplatz?.details as Record<string, number> | null;

    const gpuPercentage = gpuDetails?.speicher_prozent ?? 0;
    const diskPercentage = diskDetails?.belegt_prozent ?? 0;
    const dbLatency = komponenten.datenbank?.latenz_ms ?? 0;
    const redisLatency = komponenten.cache?.latenz_ms ?? 0;

    return (
        <div className="space-y-8">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">
                        Systemgesundheit
                    </h1>
                    <p className="text-muted-foreground mt-2">
                        {healthData?.zusammenfassung ?? 'Übersicht aller Systemkomponenten'}
                    </p>
                </div>
                <div className="flex items-center gap-4">
                    {healthData && getStatusBadge(healthData.status)}
                    <div className="flex items-center gap-2">
                        <label
                            htmlFor="auto-refresh-toggle"
                            className="text-sm text-muted-foreground flex items-center gap-1"
                        >
                            <RefreshCw className={`h-3.5 w-3.5 ${autoRefresh ? 'animate-spin' : ''}`} style={autoRefresh ? { animationDuration: '3s' } : undefined} />
                            Auto-Aktualisierung
                        </label>
                        <Switch
                            id="auto-refresh-toggle"
                            checked={autoRefresh}
                            onCheckedChange={setAutoRefresh}
                            aria-label="Auto-Aktualisierung ein/aus"
                        />
                    </div>
                    {dataUpdatedAt > 0 && (
                        <span className="text-xs text-muted-foreground">
                            Zuletzt: {new Date(dataUpdatedAt).toLocaleTimeString('de-DE')}
                        </span>
                    )}
                </div>
            </div>

            {/* Metric Cards Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                    icon={<Cpu className="h-4 w-4" />}
                    title="Datenbank"
                    value={dbLatency > 0 ? dbLatency.toFixed(0) : '-'}
                    unit="ms"
                    percentage={dbLatency > 0 ? Math.min(100, (dbLatency / 100) * 100) : 0}
                    subtitle={komponenten.datenbank?.nachricht ?? 'Nicht verfügbar'}
                />
                <MetricCard
                    icon={<MemoryStick className="h-4 w-4" />}
                    title="Cache (Redis)"
                    value={redisLatency > 0 ? redisLatency.toFixed(0) : '-'}
                    unit="ms"
                    percentage={redisLatency > 0 ? Math.min(100, (redisLatency / 50) * 100) : 0}
                    subtitle={komponenten.cache?.nachricht ?? 'Nicht verfügbar'}
                />
                <MetricCard
                    icon={<HardDrive className="h-4 w-4" />}
                    title="Festplatte"
                    value={diskDetails?.frei_gb != null ? diskDetails.frei_gb.toFixed(1) : '-'}
                    unit="GB frei"
                    percentage={diskPercentage}
                    subtitle={
                        diskDetails
                            ? `${diskDetails.belegt_gb?.toFixed(1)} / ${diskDetails.gesamt_gb?.toFixed(1)} GB belegt`
                            : 'Nicht verfügbar'
                    }
                />
                <MetricCard
                    icon={<MonitorSpeaker className="h-4 w-4" />}
                    title="Grafikkarte (GPU)"
                    value={
                        gpuDetails?.speicher_belegt_gb != null
                            ? gpuDetails.speicher_belegt_gb.toFixed(1)
                            : '-'
                    }
                    unit={
                        gpuDetails?.speicher_total_gb != null
                            ? `/ ${gpuDetails.speicher_total_gb.toFixed(1)} GB`
                            : 'GB'
                    }
                    percentage={gpuPercentage}
                    subtitle={komponenten.gpu?.nachricht ?? 'Nicht verfügbar'}
                />
            </div>

            {/* Service Status Row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                {Object.entries(komponenten).map(([name, status]) => (
                    <Card key={name} className="p-4">
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-medium capitalize">
                                {name.replace(/_/g, ' ')}
                            </span>
                            <div
                                className={`h-2.5 w-2.5 rounded-full ${
                                    status.gesund ? 'bg-green-500' : 'bg-red-500'
                                }`}
                                role="status"
                                aria-label={`${name}: ${status.gesund ? 'Gesund' : 'Fehlerhaft'}`}
                            />
                        </div>
                        {status.latenz_ms != null && (
                            <p className="text-xs text-muted-foreground mt-1">
                                {status.latenz_ms.toFixed(1)} ms
                            </p>
                        )}
                    </Card>
                ))}
            </div>

            {/* Bottom Grid: OCR Quality + Predictive Alerts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <OCRQualityPanel
                    degradationAlerts={ocrDegradation}
                    isLoading={ocrLoading}
                />
                <PredictiveAlertsList
                    alerts={predictiveAlerts}
                    isLoading={alertsLoading}
                />
            </div>

            {/* Version Info */}
            {healthData?.version && (
                <p className="text-xs text-muted-foreground text-right">
                    API Version: {healthData.version}
                </p>
            )}
        </div>
    );
}
