/**
 * ImportMonitoringPanel - Echtzeit-Import-Monitoring.
 *
 * Zeigt Statistiken, Verbindungsstatus und eine Aktivitäts-Timeline
 * mit WebSocket-Updates.
 */

import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  FileText,
  Mail,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useRealtimeEvent, useEventStream, type RealtimeEvent } from '@/lib/websocket';
import { emailImportKeys, getImportStats } from '../api/email-import-api';
import type { ImportStats } from '../types/email-types';

type SyncHealth = 'healthy' | 'warning' | 'error';

function getSyncHealth(lastSyncAt: string | null): SyncHealth {
  if (!lastSyncAt) return 'error';
  const diffMs = Date.now() - new Date(lastSyncAt).getTime();
  const diffMinutes = diffMs / 60_000;
  if (diffMinutes < 5) return 'healthy';
  if (diffMinutes < 30) return 'warning';
  return 'error';
}

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

interface ImportEvent {
  id: string;
  timestamp: string;
  type: 'started' | 'progress' | 'completed' | 'error';
  description: string;
}

export function ImportMonitoringPanel() {
  const [importEvents, setImportEvents] = useState<ImportEvent[]>([]);

  const { data: stats, refetch } = useQuery<ImportStats>({
    queryKey: emailImportKeys.stats(),
    queryFn: getImportStats,
    refetchInterval: 30_000,
  });

  const addEvent = useCallback((type: ImportEvent['type'], description: string, eventId: string) => {
    setImportEvents((prev) => {
      const event: ImportEvent = {
        id: eventId,
        timestamp: new Date().toISOString(),
        type,
        description,
      };
      return [event, ...prev].slice(0, 10);
    });
  }, []);

  // WebSocket event subscriptions
  useRealtimeEvent('system.notification', (event: RealtimeEvent) => {
    const payload = event.payload;
    const eventType = payload.import_event as string | undefined;
    if (!eventType) return;

    switch (eventType) {
      case 'import.started':
        addEvent('started', `Import gestartet: ${payload.config_name ?? 'Manuell'}`, event.event_id);
        break;
      case 'import.progress':
        addEvent(
          'progress',
          `${payload.emails_processed ?? 0} E-Mails verarbeitet`,
          event.event_id,
        );
        break;
      case 'import.completed':
        addEvent(
          'completed',
          `Import abgeschlossen: ${payload.documents_created ?? 0} Dokumente erstellt`,
          event.event_id,
        );
        void refetch();
        break;
      case 'import.error':
        addEvent('error', `Fehler: ${payload.error_message ?? 'Unbekannt'}`, event.event_id);
        void refetch();
        break;
    }
  });

  const health = getSyncHealth(stats?.last_sync_at ?? null);

  return (
    <div className="space-y-4">
      {/* Connection health */}
      <div className="flex items-center gap-2">
        <div
          className={cn(
            'h-3 w-3 rounded-full',
            health === 'healthy' && 'bg-green-500',
            health === 'warning' && 'bg-yellow-500',
            health === 'error' && 'bg-red-500',
          )}
        />
        <span className="text-sm text-muted-foreground">
          {health === 'healthy' && 'Synchronisierung aktiv'}
          {health === 'warning' && 'Letzte Synchronisierung vor >5 Min.'}
          {health === 'error' && 'Keine Verbindung'}
        </span>
        {stats?.last_sync_at && (
          <span className="text-xs text-muted-foreground ml-auto">
            Zuletzt: {formatTimestamp(stats.last_sync_at)}
          </span>
        )}
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{stats?.today_emails ?? 0}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">Heute importiert</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{stats?.today_documents ?? 0}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">Dokumente erstellt</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-bold">{stats?.today_errors ?? 0}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">Fehler</p>
          </CardContent>
        </Card>
      </div>

      {/* Activity timeline */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Aktivität
          </CardTitle>
        </CardHeader>
        <CardContent>
          {importEvents.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              Keine aktuellen Aktivitäten
            </p>
          ) : (
            <div className="space-y-3">
              {importEvents.map((evt) => (
                <div key={evt.id} className="flex items-start gap-3">
                  <div className="mt-0.5">
                    {evt.type === 'started' && (
                      <RefreshCw className="h-4 w-4 text-blue-500" />
                    )}
                    {evt.type === 'progress' && (
                      <Clock className="h-4 w-4 text-yellow-500" />
                    )}
                    {evt.type === 'completed' && (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    )}
                    {evt.type === 'error' && (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{evt.description}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatTimestamp(evt.timestamp)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
