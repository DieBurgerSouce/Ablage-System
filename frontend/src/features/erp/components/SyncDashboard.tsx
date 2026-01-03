/**
 * ERP Sync Dashboard Component
 *
 * Zeigt Sync-Status, Historie und ermoeglicht manuelle Syncs.
 */

import { useState } from 'react';
import {
  RefreshCw,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Loader2,
  ArrowDownToLine,
  ArrowUpFromLine,
  ArrowLeftRight,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';

import {
  useERPConnections,
  useSyncHistory,
  useTriggerSync,
} from '../hooks/useERP';
import type { ERPSyncHistory, ERPSyncStatus, ERPSyncDirection } from '../types';

// =============================================================================
// Status Components
// =============================================================================

function SyncStatusBadge({ status }: { status: ERPSyncStatus }) {
  const config: Record<ERPSyncStatus, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: React.ReactNode; label: string }> = {
    running: {
      variant: 'outline',
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
      label: 'Laeuft',
    },
    success: {
      variant: 'default',
      icon: <CheckCircle className="h-3 w-3" />,
      label: 'Erfolgreich',
    },
    failed: {
      variant: 'destructive',
      icon: <XCircle className="h-3 w-3" />,
      label: 'Fehlgeschlagen',
    },
    partial: {
      variant: 'secondary',
      icon: <AlertTriangle className="h-3 w-3" />,
      label: 'Teilweise',
    },
  };

  const { variant, icon, label } = config[status];

  return (
    <Badge variant={variant} className="gap-1">
      {icon}
      {label}
    </Badge>
  );
}

function DirectionIcon({ direction }: { direction: ERPSyncDirection }) {
  const icons: Record<ERPSyncDirection, React.ReactNode> = {
    pull: <ArrowDownToLine className="h-4 w-4 text-blue-500" />,
    push: <ArrowUpFromLine className="h-4 w-4 text-green-500" />,
    bidirectional: <ArrowLeftRight className="h-4 w-4 text-purple-500" />,
  };

  const labels: Record<ERPSyncDirection, string> = {
    pull: 'Import',
    push: 'Export',
    bidirectional: 'Bidirektional',
  };

  return (
    <div className="flex items-center gap-1.5">
      {icons[direction]}
      <span className="text-sm">{labels[direction]}</span>
    </div>
  );
}

// =============================================================================
// Sync Stats Card
// =============================================================================

function SyncStatsCard({ history }: { history: ERPSyncHistory[] }) {
  const successCount = history.filter((h) => h.status === 'success').length;
  const failedCount = history.filter((h) => h.status === 'failed').length;
  const totalRecords = history.reduce((sum, h) => sum + h.records_synced, 0);
  const totalConflicts = history.reduce((sum, h) => sum + h.conflicts_detected, 0);

  const successRate = history.length > 0
    ? Math.round((successCount / history.length) * 100)
    : 0;

  return (
    <div className="grid grid-cols-4 gap-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Erfolgsrate</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2">
            <div className="text-2xl font-bold">{successRate}%</div>
            <Progress value={successRate} className="flex-1" />
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {successCount} erfolgreich, {failedCount} fehlgeschlagen
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Synchronisierte Datensaetze</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{totalRecords.toLocaleString('de-DE')}</div>
          <p className="text-xs text-muted-foreground mt-1">
            Insgesamt synchronisiert
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Konflikte erkannt</CardTitle>
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${totalConflicts > 0 ? 'text-yellow-600' : ''}`}>
            {totalConflicts}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Konflikte in diesem Zeitraum
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Syncs gesamt</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{history.length}</div>
          <p className="text-xs text-muted-foreground mt-1">
            Synchronisierungen durchgefuehrt
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function SyncDashboard() {
  const [selectedConnection, setSelectedConnection] = useState<string>('');

  const { data: connections } = useERPConnections();
  // ERROR HANDLING FIX: Error State hinzugefuegt
  const { data: history, isLoading: historyLoading, error: historyError } = useSyncHistory(
    selectedConnection,
    50
  );
  const triggerSync = useTriggerSync();

  const handleSync = (syncType: 'full' | 'delta') => {
    if (selectedConnection) {
      triggerSync.mutate({ connectionId: selectedConnection, syncType });
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '-';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
  };

  const entityLabels: Record<string, string> = {
    customer: 'Kunden',
    supplier: 'Lieferanten',
    invoice: 'Rechnungen',
    payment: 'Zahlungen',
    product: 'Produkte',
    document: 'Dokumente',
    order: 'Bestellungen',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Sync-Dashboard</h2>
          <p className="text-muted-foreground">
            Ueberwachen Sie die ERP-Synchronisation
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Select value={selectedConnection} onValueChange={setSelectedConnection}>
            <SelectTrigger className="w-[250px]">
              <SelectValue placeholder="Verbindung waehlen..." />
            </SelectTrigger>
            <SelectContent>
              {connections?.map((conn) => (
                <SelectItem key={conn.id} value={conn.id}>
                  {conn.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button
            variant="outline"
            onClick={() => handleSync('delta')}
            disabled={!selectedConnection || triggerSync.isPending}
          >
            <Play className="h-4 w-4 mr-2" />
            Delta-Sync
          </Button>

          <Button
            onClick={() => handleSync('full')}
            disabled={!selectedConnection || triggerSync.isPending}
          >
            {triggerSync.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Voll-Sync
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {history && history.length > 0 && <SyncStatsCard history={history} />}

      {/* Sync History Table */}
      <Card>
        <CardHeader>
          <CardTitle>Sync-Historie</CardTitle>
          <CardDescription>
            Letzte 50 Synchronisierungen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!selectedConnection ? (
            <div className="text-center py-8 text-muted-foreground">
              Waehlen Sie eine Verbindung aus, um die Historie anzuzeigen
            </div>
          ) : historyLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : historyError ? (
            // ERROR HANDLING FIX: Error State fuer fehlgeschlagene Queries
            <div className="text-center py-8">
              <AlertTriangle className="h-12 w-12 mx-auto mb-2 text-destructive opacity-70" />
              <p className="text-destructive">Fehler beim Laden der Sync-Historie</p>
              <p className="text-sm text-muted-foreground mt-1">
                {historyError instanceof Error ? historyError.message : 'Unbekannter Fehler'}
              </p>
            </div>
          ) : !history?.length ? (
            <div className="text-center py-8 text-muted-foreground">
              <Clock className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>Keine Sync-Historie vorhanden</p>
              <Button
                variant="link"
                onClick={() => handleSync('full')}
                disabled={triggerSync.isPending}
              >
                Ersten Sync starten
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Zeitpunkt</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Entitaet</TableHead>
                  <TableHead>Richtung</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Datensaetze</TableHead>
                  <TableHead className="text-right">Dauer</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((sync) => (
                  <TableRow key={sync.id}>
                    <TableCell>
                      <div className="text-sm">{formatDate(sync.started_at)}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {sync.sync_type === 'full' ? 'Voll' :
                         sync.sync_type === 'delta' ? 'Delta' : 'Manuell'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {entityLabels[sync.entity] || sync.entity}
                    </TableCell>
                    <TableCell>
                      <DirectionIcon direction={sync.direction} />
                    </TableCell>
                    <TableCell>
                      <SyncStatusBadge status={sync.status} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="text-sm">
                        <span className="font-medium">{sync.records_synced}</span>
                        {sync.records_failed > 0 && (
                          <span className="text-destructive ml-1">
                            ({sync.records_failed} Fehler)
                          </span>
                        )}
                      </div>
                      {sync.conflicts_detected > 0 && (
                        <div className="text-xs text-yellow-600">
                          {sync.conflicts_detected} Konflikte
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {formatDuration(sync.duration_seconds)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
