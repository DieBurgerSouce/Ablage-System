/**
 * Sync Status Dashboard
 *
 * Zeigt den aktuellen Synchronisierungs-Status, Statistiken
 * und ermöglicht manuelle Synchronisierung.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Clock, RefreshCw, Loader2, CheckCircle2, XCircle, AlertTriangle, ArrowUpCircle, Trash2, ChevronDown, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useToast } from '@/hooks/use-toast';
import { calendarSyncKeys, getSyncStatus, triggerSync } from '../api/calendar-sync-api';
import type { SyncResult } from '../types/calendar-types';

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMinutes < 1) return 'gerade eben';
  if (diffMinutes === 1) return 'vor 1 Minute';
  if (diffMinutes < 60) return `vor ${diffMinutes} Minuten`;
  if (diffHours === 1) return 'vor 1 Stunde';
  if (diffHours < 24) return `vor ${diffHours} Stunden`;
  if (diffDays === 1) return 'vor 1 Tag';
  return `vor ${diffDays} Tagen`;
}

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  colorClass: string;
}

function StatCard({ label, value, icon, colorClass }: StatCardProps) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border bg-card">
      <div className={colorClass}>{icon}</div>
      <div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

export function SyncStatusDashboard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [lastResult, setLastResult] = useState<SyncResult | null>(null);
  const [errorsOpen, setErrorsOpen] = useState(false);

  const { data: syncStatus, isLoading } = useQuery({
    queryKey: calendarSyncKeys.syncStatus(),
    queryFn: getSyncStatus,
    refetchInterval: 60000,
  });

  const syncMutation = useMutation({
    mutationFn: triggerSync,
    onSuccess: (data) => {
      setLastResult(data);
      queryClient.invalidateQueries({ queryKey: calendarSyncKeys.syncStatus() });
      queryClient.invalidateQueries({ queryKey: calendarSyncKeys.preview() });
      toast({
        title: 'Synchronisierung erfolgreich',
        description: `${data.created} erstellt, ${data.updated} aktualisiert, ${data.deleted} gelöscht`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Synchronisierung fehlgeschlagen',
        description: error.message || 'Unbekannter Fehler bei der Synchronisierung',
        variant: 'destructive',
      });
    },
  });

  const getStatusBadge = () => {
    if (!syncStatus) return null;
    if (syncStatus.is_syncing) {
      return (
        <Badge variant="default" className="bg-blue-100 text-blue-700">
          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          Synchronisiert...
        </Badge>
      );
    }
    if (syncStatus.last_error) {
      return (
        <Badge variant="destructive">
          <XCircle className="h-3 w-3 mr-1" />
          Fehler
        </Badge>
      );
    }
    if (syncStatus.last_sync_at) {
      return (
        <Badge variant="default" className="bg-green-100 text-green-700">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Aktiv
        </Badge>
      );
    }
    return (
      <Badge variant="secondary">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Inaktiv
      </Badge>
    );
  };

  const allErrors = [
    ...(syncStatus?.last_error ? [syncStatus.last_error] : []),
    ...(lastResult?.errors ?? []),
  ];

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5" />
              Sync-Status
            </CardTitle>
            <CardDescription>Synchronisierungsstatus und manuelle Auslösung</CardDescription>
          </div>
          {getStatusBadge()}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Last sync time */}
        <div className="flex items-center gap-2 p-3 rounded-lg border bg-muted/30">
          <Clock className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">Letzter Sync</p>
            <p className="text-xs text-muted-foreground">
              {syncStatus?.last_sync_at
                ? formatRelativeTime(syncStatus.last_sync_at)
                : 'Noch keine Synchronisierung durchgeführt'}
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            label="Synchronisiert"
            value={syncStatus?.events_synced ?? 0}
            icon={<CheckCircle2 className="h-5 w-5" />}
            colorClass="text-blue-600"
          />
          <StatCard
            label="Erstellt"
            value={lastResult?.created ?? 0}
            icon={<ArrowUpCircle className="h-5 w-5" />}
            colorClass="text-green-600"
          />
          <StatCard
            label="Aktualisiert"
            value={lastResult?.updated ?? 0}
            icon={<RefreshCw className="h-5 w-5" />}
            colorClass="text-yellow-600"
          />
          <StatCard
            label="Gelöscht"
            value={lastResult?.deleted ?? 0}
            icon={<Trash2 className="h-5 w-5" />}
            colorClass="text-red-600"
          />
        </div>

        {/* Error log */}
        <Collapsible open={errorsOpen} onOpenChange={setErrorsOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-3 h-auto border">
              <div className="flex items-center gap-2">
                {errorsOpen ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
                <span className="text-sm font-medium">Fehlerprotokoll</span>
              </div>
              {allErrors.length > 0 && (
                <Badge variant="destructive" className="text-xs">
                  {allErrors.length}
                </Badge>
              )}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-1 p-3 border rounded-lg bg-muted/30">
            {allErrors.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-2">Keine Fehler</p>
            ) : (
              <ul className="space-y-2">
                {allErrors.map((error, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm">
                    <XCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                    <span className="text-muted-foreground">{error}</span>
                  </li>
                ))}
              </ul>
            )}
          </CollapsibleContent>
        </Collapsible>

        {/* Sync trigger button */}
        <div className="flex justify-end">
          <Button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending || syncStatus?.is_syncing}
          >
            {syncMutation.isPending || syncStatus?.is_syncing ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Jetzt synchronisieren
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
