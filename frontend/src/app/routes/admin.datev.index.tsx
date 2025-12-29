/**
 * DATEV Export - Übersicht (Index Route)
 *
 * Dashboard mit Quick-Stats, letzten Exports und Quick-Actions.
 */

import { createFileRoute, Link } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
    Settings,
    Download,
    FileSpreadsheet,
    CheckCircle2,
    AlertCircle,
    Clock,
    ArrowRight,
} from 'lucide-react';
import { useConfigs, useExportHistory, useDefaultConfig } from '@/features/datev/hooks/use-datev-queries';
import { formatDate, formatExportStatus, getExportStatusVariant } from '@/features/datev/utils';
import type { DATEVExportStatus } from '@/lib/api/services/datev';

export const Route = createFileRoute('/admin/datev/')({
    component: DATEVOverviewPage,
});

function DATEVOverviewPage() {
    const { data: configs, isLoading: configsLoading } = useConfigs();
    const { data: defaultConfig, isLoading: defaultConfigLoading } = useDefaultConfig(true);
    const { data: historyData, isLoading: historyLoading } = useExportHistory({ page: 1, page_size: 5 });

    const hasConfig = configs && configs.length > 0;
    const hasDefaultConfig = !!defaultConfig;
    const recentExports = historyData?.items || [];
    const totalExports = historyData?.total || 0;

    // Statistiken berechnen
    const successfulExports = recentExports.filter((e) => e.status === 'completed').length;
    const totalDocuments = recentExports.reduce((sum, e) => sum + e.document_count, 0);

    return (
        <div className="space-y-6">
            {/* Setup-Hinweis wenn keine Konfiguration */}
            {!configsLoading && !hasConfig && (
                <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Konfiguration erforderlich</AlertTitle>
                    <AlertDescription>
                        Bevor Sie DATEV-Exporte erstellen können, müssen Sie eine Konfiguration
                        mit Beraternummer, Mandantennummer und Kontenrahmen anlegen.
                        <Link to="/admin/datev/config" className="ml-2 underline">
                            Jetzt konfigurieren
                        </Link>
                    </AlertDescription>
                </Alert>
            )}

            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {/* Konfiguration Status */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Konfiguration</CardTitle>
                        <Settings className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {configsLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">
                                    {hasConfig ? (
                                        <span className="text-green-600">Aktiv</span>
                                    ) : (
                                        <span className="text-yellow-600">Ausstehend</span>
                                    )}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {hasConfig
                                        ? `${configs.length} Konfiguration${configs.length > 1 ? 'en' : ''}`
                                        : 'Noch nicht eingerichtet'}
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Kontenrahmen */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Kontenrahmen</CardTitle>
                        <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {defaultConfigLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">
                                    {hasDefaultConfig ? defaultConfig.kontenrahmen : '–'}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {hasDefaultConfig
                                        ? 'Standard-Konfiguration'
                                        : 'Keine Standard-Konfiguration'}
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Exports gesamt */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Exports gesamt</CardTitle>
                        <Download className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {historyLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">{totalExports}</div>
                                <p className="text-xs text-muted-foreground">
                                    {totalDocuments} Dokumente exportiert
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Erfolgsrate */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Erfolgsrate</CardTitle>
                        <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {historyLoading ? (
                            <Skeleton className="h-8 w-20" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">
                                    {recentExports.length > 0
                                        ? `${Math.round((successfulExports / recentExports.length) * 100)}%`
                                        : '–'}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    Letzte {recentExports.length} Exports
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Quick Actions + Letzte Exports */}
            <div className="grid gap-6 lg:grid-cols-2">
                {/* Quick Actions */}
                <Card>
                    <CardHeader>
                        <CardTitle>Schnellaktionen</CardTitle>
                        <CardDescription>
                            Häufig verwendete Funktionen für den DATEV-Export.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <Button asChild className="w-full justify-between" variant="outline">
                            <Link to="/admin/datev/export">
                                <span className="flex items-center gap-2">
                                    <Download className="h-4 w-4" />
                                    Neuen Export erstellen
                                </span>
                                <ArrowRight className="h-4 w-4" />
                            </Link>
                        </Button>

                        <Button asChild className="w-full justify-between" variant="outline">
                            <Link to="/admin/datev/config">
                                <span className="flex items-center gap-2">
                                    <Settings className="h-4 w-4" />
                                    Konfiguration verwalten
                                </span>
                                <ArrowRight className="h-4 w-4" />
                            </Link>
                        </Button>

                        <Button asChild className="w-full justify-between" variant="outline">
                            <Link to="/admin/datev/vendors">
                                <span className="flex items-center gap-2">
                                    <FileSpreadsheet className="h-4 w-4" />
                                    Lieferanten-Konten zuweisen
                                </span>
                                <ArrowRight className="h-4 w-4" />
                            </Link>
                        </Button>
                    </CardContent>
                </Card>

                {/* Letzte Exports */}
                <Card>
                    <CardHeader>
                        <CardTitle>Letzte Exports</CardTitle>
                        <CardDescription>
                            Die letzten {recentExports.length} DATEV-Exporte.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {historyLoading ? (
                            <div className="space-y-3">
                                {[1, 2, 3].map((i) => (
                                    <Skeleton key={i} className="h-12 w-full" />
                                ))}
                            </div>
                        ) : recentExports.length === 0 ? (
                            <div className="text-center py-6 text-muted-foreground">
                                <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                <p>Noch keine Exports vorhanden</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {recentExports.map((exp) => (
                                    <div
                                        key={exp.id}
                                        className="flex items-center justify-between p-3 rounded-lg border"
                                    >
                                        <div className="space-y-1">
                                            <p className="text-sm font-medium">{exp.filename}</p>
                                            <p className="text-xs text-muted-foreground">
                                                {formatDate(exp.exported_at)} •{' '}
                                                {exp.document_count} Dokumente
                                            </p>
                                        </div>
                                        <StatusBadge status={exp.status} />
                                    </div>
                                ))}

                                {totalExports > 5 && (
                                    <Button asChild variant="ghost" className="w-full mt-2">
                                        <Link to="/admin/datev/history">
                                            Alle {totalExports} Exports anzeigen
                                            <ArrowRight className="ml-2 h-4 w-4" />
                                        </Link>
                                    </Button>
                                )}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

// Status Badge Komponente
function StatusBadge({ status }: { status: DATEVExportStatus }) {
    const variant = getExportStatusVariant(status);
    const label = formatExportStatus(status);

    return (
        <Badge
            variant={variant === 'success' ? 'default' : variant === 'destructive' ? 'destructive' : 'secondary'}
            className={variant === 'success' ? 'bg-green-100 text-green-800 hover:bg-green-100' : variant === 'warning' ? 'bg-yellow-100 text-yellow-800 hover:bg-yellow-100' : ''}
        >
            {label}
        </Badge>
    );
}
