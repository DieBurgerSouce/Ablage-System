/**
 * Import Sync Status Widget für Dashboard
 *
 * Zeigt Status aller Import-Quellen:
 * - DATEV, Lexware, Email, Folder Import
 * - Letzter Sync-Zeitpunkt
 * - Fehler und Warnungen
 * - Sync-Queue Status
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    RefreshCw,
    CheckCircle2,
    AlertTriangle,
    XCircle,
    ChevronRight,
    Clock,
    FileSpreadsheet,
    Mail,
    FolderInput,
    Link2,
    Loader2,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface ImportSourceStatus {
    source: string;
    display_name: string;
    status: 'synced' | 'syncing' | 'error' | 'stale' | 'disabled';
    last_sync_at: string | null;
    next_sync_at: string | null;
    items_pending: number;
    items_processed_today: number;
    error_message: string | null;
    error_count: number;
}

interface ImportSyncSummary {
    sources: ImportSourceStatus[];
    total_pending: number;
    total_errors: number;
    last_global_sync: string | null;
    sync_in_progress: boolean;
}

// API Hook
function useImportSyncStatus() {
    return useQuery({
        queryKey: ['imports', 'sync-status'],
        queryFn: async (): Promise<ImportSyncSummary> => {
            const response = await api.get('/api/v1/imports/sync-status');
            return response.data;
        },
        staleTime: 30 * 1000, // 30 seconds
        refetchInterval: 60 * 1000, // 1 minute
    });
}

// Helper functions
const formatRelativeTime = (dateString: string | null): string => {
    if (!dateString) return 'Nie';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Gerade eben';
    if (diffMins < 60) return `vor ${diffMins} Min.`;
    if (diffHours < 24) return `vor ${diffHours} Std.`;
    if (diffDays < 7) return `vor ${diffDays} Tagen`;

    return date.toLocaleDateString('de-DE');
};

const getSourceIcon = (source: string) => {
    switch (source) {
        case 'datev':
        case 'datev_connect':
            return FileSpreadsheet;
        case 'lexware':
            return FileSpreadsheet;
        case 'email':
            return Mail;
        case 'folder':
            return FolderInput;
        default:
            return Link2;
    }
};

const getStatusIcon = (status: string) => {
    switch (status) {
        case 'synced':
            return CheckCircle2;
        case 'syncing':
            return Loader2;
        case 'error':
            return XCircle;
        case 'stale':
            return AlertTriangle;
        case 'disabled':
            return Clock;
        default:
            return RefreshCw;
    }
};

const getStatusColor = (status: string): string => {
    switch (status) {
        case 'synced':
            return 'text-green-600';
        case 'syncing':
            return 'text-blue-600 animate-spin';
        case 'error':
            return 'text-red-600';
        case 'stale':
            return 'text-yellow-600';
        case 'disabled':
            return 'text-muted-foreground';
        default:
            return 'text-muted-foreground';
    }
};

const getStatusLabel = (status: string): string => {
    const labels: Record<string, string> = {
        synced: 'Synchronisiert',
        syncing: 'Sync läuft...',
        error: 'Fehler',
        stale: 'Veraltet',
        disabled: 'Deaktiviert',
    };
    return labels[status] || status;
};

// Components
function SourceStatusItem({ source }: { source: ImportSourceStatus }) {
    const SourceIcon = getSourceIcon(source.source);
    const StatusIcon = getStatusIcon(source.status);
    const isError = source.status === 'error';
    const isStale = source.status === 'stale';

    return (
        <div className={cn(
            'p-3 rounded-lg border transition-colors',
            isError && 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
            isStale && 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
            !isError && !isStale && 'bg-muted/30'
        )}>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                    <SourceIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                        <p className="text-sm font-medium truncate">
                            {source.display_name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                            {formatRelativeTime(source.last_sync_at)}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {source.items_pending > 0 && (
                        <Badge variant="secondary" className="text-xs">
                            {source.items_pending} ausstehend
                        </Badge>
                    )}
                    <StatusIcon className={cn('h-4 w-4', getStatusColor(source.status))} />
                </div>
            </div>
            {isError && source.error_message && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-2 line-clamp-1">
                    {source.error_message}
                </p>
            )}
        </div>
    );
}

function ImportSyncStatusWidgetContent() {
    // Real-time updates
    useWidgetSubscription('import-sync', {
        debounceMs: 500,
        autoInvalidate: true,
        queryKeysToInvalidate: [['imports']],
    });

    const {
        data: summary,
        isLoading,
        isError,
        refetch,
    } = useImportSyncStatus();

    if (isLoading) {
        return (
            <div className="space-y-3">
                {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-16 rounded-lg" />
                ))}
            </div>
        );
    }

    if (isError || !summary) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">Sync-Status nicht verfügbar</p>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => refetch()}
                    className="mt-2"
                >
                    <RefreshCw className="h-4 w-4 mr-1" />
                    Erneut versuchen
                </Button>
            </div>
        );
    }

    const hasErrors = summary.total_errors > 0;
    const hasPending = summary.total_pending > 0;
    const allSynced = summary.sources.every(s => s.status === 'synced' || s.status === 'disabled');

    return (
        <div className="space-y-4">
            {/* Summary Stats */}
            <div className="grid grid-cols-3 gap-2">
                <div className={cn(
                    'p-2 rounded-lg text-center',
                    allSynced ? 'bg-green-50 dark:bg-green-900/20' : 'bg-muted/30'
                )}>
                    <p className="text-lg font-bold">
                        {summary.sources.filter(s => s.status === 'synced').length}
                    </p>
                    <p className="text-xs text-muted-foreground">Synchron</p>
                </div>
                <div className={cn(
                    'p-2 rounded-lg text-center',
                    hasPending ? 'bg-yellow-50 dark:bg-yellow-900/20' : 'bg-muted/30'
                )}>
                    <p className="text-lg font-bold">{summary.total_pending}</p>
                    <p className="text-xs text-muted-foreground">Ausstehend</p>
                </div>
                <div className={cn(
                    'p-2 rounded-lg text-center',
                    hasErrors ? 'bg-red-50 dark:bg-red-900/20' : 'bg-muted/30'
                )}>
                    <p className="text-lg font-bold">{summary.total_errors}</p>
                    <p className="text-xs text-muted-foreground">Fehler</p>
                </div>
            </div>

            {/* Source List */}
            <div className="space-y-2">
                {summary.sources.slice(0, 4).map((source) => (
                    <SourceStatusItem key={source.source} source={source} />
                ))}
            </div>

            {/* Sync Status Footer */}
            {summary.sync_in_progress && (
                <div className="flex items-center gap-2 text-xs text-blue-600">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Synchronisierung läuft...
                </div>
            )}

            {/* Link to imports page */}
            <Link
                to="/admin/imports"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                Import-Einstellungen
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function ImportSyncStatusWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Import Sync" />}
            errorTitle="Import Sync Fehler"
            errorDescription="Der Import-Status konnte nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <RefreshCw className="h-5 w-5 text-primary" />
                        Import Sync Status
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <ImportSyncStatusWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
