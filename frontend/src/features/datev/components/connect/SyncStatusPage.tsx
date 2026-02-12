/**
 * DATEV Connect - Sync-Status Dashboard
 *
 * Übersicht über Synchronisierungen und manuelle Sync-Trigger.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    RefreshCw,
    CheckCircle,
    XCircle,
    Clock,
    Database,
    FileText,
    Users,
    BookOpen,
    Play,
    Loader2,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
    useConnections,
    useSyncStatus,
    useSyncHistory,
    useTriggerSync,
} from '@/features/datev/hooks/use-datev-connect-queries';
import { formatSyncType, type DATEVSyncType } from '@/lib/api/services/datev-connect';

export function SyncStatusPage() {
    const { data: connections, isLoading: connectionsLoading } = useConnections();
    const [selectedConnectionId, setSelectedConnectionId] = useState<string>('');
    const { toast } = useToast();

    // Auto-select erste verbundene Verbindung
    if (!selectedConnectionId && connections && connections.length > 0) {
        const connected = connections.find((c) => c.status === 'connected');
        if (connected) {
            setSelectedConnectionId(connected.id);
        }
    }

    // Sync-Status und Historie
    const { data: syncStatus, isLoading: statusLoading, refetch: refetchStatus } = useSyncStatus(
        selectedConnectionId,
        !!selectedConnectionId
    );
    const { data: syncHistory, isLoading: historyLoading, refetch: refetchHistory } = useSyncHistory(
        selectedConnectionId,
        { page_size: 10 },
        !!selectedConnectionId
    );

    const triggerSync = useTriggerSync();

    const handleTriggerSync = async (syncTypes?: DATEVSyncType[]) => {
        if (!selectedConnectionId) return;

        try {
            const result = await triggerSync.mutateAsync({
                connectionId: selectedConnectionId,
                syncTypes,
            });
            toast({
                title: 'Synchronisierung gestartet',
                description: `${result.task_ids.length} Sync-Task(s) wurden gestartet.`,
            });
            // Refresh nach kurzer Verzögerung
            setTimeout(() => {
                refetchStatus();
                refetchHistory();
            }, 2000);
        } catch {
            toast({
                title: 'Sync fehlgeschlagen',
                description: 'Die Synchronisierung konnte nicht gestartet werden.',
                variant: 'destructive',
            });
        }
    };

    const getSyncIcon = (type: DATEVSyncType) => {
        switch (type) {
            case 'stammdaten':
                return <Users className="h-4 w-4" />;
            case 'kontenplan':
                return <BookOpen className="h-4 w-4" />;
            case 'buchungen':
                return <FileText className="h-4 w-4" />;
            case 'belege':
                return <Database className="h-4 w-4" />;
            default:
                return <RefreshCw className="h-4 w-4" />;
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case 'completed':
                return (
                    <Badge className="bg-green-100 text-green-800">
                        <CheckCircle className="h-3 w-3 mr-1" />
                        Erfolgreich
                    </Badge>
                );
            case 'running':
                return (
                    <Badge className="bg-blue-100 text-blue-800">
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        Läuft
                    </Badge>
                );
            case 'failed':
                return (
                    <Badge className="bg-red-100 text-red-800">
                        <XCircle className="h-3 w-3 mr-1" />
                        Fehlgeschlagen
                    </Badge>
                );
            default:
                return <Badge variant="secondary">{status}</Badge>;
        }
    };

    const formatDateTime = (dateString: string | null) => {
        if (!dateString) return '–';
        return new Date(dateString).toLocaleString('de-DE');
    };

    const formatRelativeTime = (dateString: string | null) => {
        if (!dateString) return 'Nie';
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'Gerade eben';
        if (diffMins < 60) return `Vor ${diffMins} Min.`;
        if (diffHours < 24) return `Vor ${diffHours} Std.`;
        return `Vor ${diffDays} Tag${diffDays > 1 ? 'en' : ''}`;
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h2 className="text-xl font-semibold">Synchronisierung</h2>
                    <p className="text-sm text-muted-foreground">
                        Überwachen und steuern Sie die Datensynchronisierung mit DATEV.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Select
                        value={selectedConnectionId || 'none'}
                        onValueChange={(value) => {
                            if (value !== 'none') {
                                setSelectedConnectionId(value);
                            }
                        }}
                    >
                        <SelectTrigger className="w-[250px]">
                            <SelectValue placeholder="Verbindung wählen..." />
                        </SelectTrigger>
                        <SelectContent>
                            {connectionsLoading ? (
                                <SelectItem value="none" disabled>
                                    Lade...
                                </SelectItem>
                            ) : !connections || connections.length === 0 ? (
                                <SelectItem value="none" disabled>
                                    Keine Verbindungen
                                </SelectItem>
                            ) : (
                                connections
                                    .filter((c) => c.status === 'connected')
                                    .map((conn) => (
                                        <SelectItem key={conn.id} value={conn.id}>
                                            {conn.name}
                                        </SelectItem>
                                    ))
                            )}
                        </SelectContent>
                    </Select>
                    <Button
                        onClick={() => handleTriggerSync()}
                        disabled={!selectedConnectionId || triggerSync.isPending}
                    >
                        {triggerSync.isPending ? (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                            <Play className="mr-2 h-4 w-4" />
                        )}
                        Alle synchronisieren
                    </Button>
                </div>
            </div>

            {/* Status Cards */}
            {selectedConnectionId && (
                <div className="grid gap-4 md:grid-cols-4">
                    {(['stammdaten', 'kontenplan', 'buchungen', 'belege'] as DATEVSyncType[]).map(
                        (syncType) => (
                            <Card key={syncType}>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        {getSyncIcon(syncType)}
                                        {formatSyncType(syncType)}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {statusLoading ? (
                                        <Skeleton className="h-8 w-full" />
                                    ) : (
                                        <>
                                            <p className="text-2xl font-bold">
                                                {formatRelativeTime(syncStatus?.last_sync[syncType] || null)}
                                            </p>
                                            <div className="flex justify-between items-center mt-2">
                                                <p className="text-xs text-muted-foreground">
                                                    Letzter Sync
                                                </p>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    className="h-6 px-2"
                                                    onClick={() => handleTriggerSync([syncType])}
                                                    disabled={triggerSync.isPending}
                                                >
                                                    <RefreshCw className="h-3 w-3" />
                                                </Button>
                                            </div>
                                        </>
                                    )}
                                </CardContent>
                            </Card>
                        )
                    )}
                </div>
            )}

            {/* Pending Items */}
            {syncStatus && (syncStatus.pending_items.buchungen > 0 || syncStatus.pending_items.belege > 0) && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Ausstehende Synchronisierung</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {syncStatus.pending_items.buchungen > 0 && (
                            <div>
                                <div className="flex justify-between mb-2">
                                    <span className="text-sm">Buchungen</span>
                                    <span className="text-sm font-medium">
                                        {syncStatus.pending_items.buchungen} ausstehend
                                    </span>
                                </div>
                                <Progress value={0} className="h-2" />
                            </div>
                        )}
                        {syncStatus.pending_items.belege > 0 && (
                            <div>
                                <div className="flex justify-between mb-2">
                                    <span className="text-sm">Belege</span>
                                    <span className="text-sm font-medium">
                                        {syncStatus.pending_items.belege} ausstehend
                                    </span>
                                </div>
                                <Progress value={0} className="h-2" />
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Sync Historie */}
            <Card>
                <CardHeader>
                    <div className="flex justify-between items-center">
                        <div>
                            <CardTitle className="text-base">Sync-Historie</CardTitle>
                            <CardDescription>
                                Die letzten Synchronisierungsvorgänge.
                            </CardDescription>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => refetchHistory()}
                            disabled={!selectedConnectionId || historyLoading}
                        >
                            <RefreshCw className={`h-4 w-4 ${historyLoading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    {!selectedConnectionId ? (
                        <div className="text-center py-10">
                            <RefreshCw className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Wählen Sie eine Verbindung aus, um die Historie anzuzeigen.
                            </p>
                        </div>
                    ) : historyLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-12 w-full" />
                            ))}
                        </div>
                    ) : !syncHistory || syncHistory.items.length === 0 ? (
                        <div className="text-center py-10">
                            <Clock className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                            <p className="text-muted-foreground">
                                Keine Sync-Historie vorhanden.
                            </p>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Typ</TableHead>
                                    <TableHead>Gestartet</TableHead>
                                    <TableHead>Beendet</TableHead>
                                    <TableHead>Elemente</TableHead>
                                    <TableHead>Status</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {syncHistory.items.map((item) => (
                                    <TableRow key={item.id}>
                                        <TableCell className="flex items-center gap-2">
                                            {getSyncIcon(item.sync_type)}
                                            {formatSyncType(item.sync_type)}
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {formatDateTime(item.started_at)}
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {formatDateTime(item.completed_at)}
                                        </TableCell>
                                        <TableCell>{item.items_synced}</TableCell>
                                        <TableCell>{getStatusBadge(item.status)}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>

            {/* Nächster geplanter Sync */}
            {syncStatus?.next_scheduled && (
                <Card>
                    <CardContent className="py-4">
                        <div className="flex items-center gap-3">
                            <Clock className="h-5 w-5 text-muted-foreground" />
                            <div>
                                <p className="text-sm font-medium">Nächster geplanter Sync</p>
                                <p className="text-sm text-muted-foreground">
                                    {formatDateTime(syncStatus.next_scheduled)}
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
