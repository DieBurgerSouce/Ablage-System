/**
 * Mirror Status Card
 *
 * Zeigt den Zustand des Odoo-Vollarchiv-Spiegels (GoBD-Zweitablage) je
 * Verbindung: letzter Lauf, Cursor, Zähler, Fehlerserie. Bislang war der
 * Backend-Endpoint /admin/erp/mirror-status im Frontend unsichtbar
 * (Go-Live-Runbook-Befund 2026-07-11).
 */

import { AlertTriangle, Archive, CheckCircle, PauseCircle } from 'lucide-react';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

import { useMirrorStatus } from '../hooks/useERP';
import type { OdooMirrorStatus } from '../types';

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function MirrorRowStatus({ row }: { row: OdooMirrorStatus }) {
  if (row.is_paused) {
    return (
      <Badge variant="outline">
        <PauseCircle className="h-3 w-3 mr-1" />
        Pausiert
      </Badge>
    );
  }
  if (row.consecutive_failures > 0) {
    return (
      <Badge variant="destructive">
        <AlertTriangle className="h-3 w-3 mr-1" />
        {row.consecutive_failures} Fehlläufe
      </Badge>
    );
  }
  return (
    <Badge variant="secondary">
      <CheckCircle className="h-3 w-3 mr-1" />
      OK
    </Badge>
  );
}

export function MirrorStatusCard() {
  const { data: rows, isLoading, isError } = useMirrorStatus();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Archive className="h-4 w-4" />
          Odoo-Vollarchiv-Spiegel
        </CardTitle>
        <CardDescription>
          GoBD-Zweitablage aller Odoo-Belege (automatischer Lauf alle 30 Minuten)
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Lade Spiegel-Status …</p>
        ) : isError ? (
          <p className="text-sm text-destructive">
            Spiegel-Status konnte nicht geladen werden
          </p>
        ) : !rows || rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Noch kein Spiegel-Lauf erfasst — der Status erscheint nach dem ersten
            Lauf gegen eine aktive Odoo-Verbindung.
          </p>
        ) : (
          <div className="space-y-3">
            {rows.map((row) => (
              <div
                key={`${row.connection_id}-${row.data_type}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {row.connection_name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Letzter Erfolg: {formatDateTime(row.last_successful_sync_at)}
                    {' · '}Gesamt gespiegelt: {row.total_records_synced}
                    {row.last_record_count !== null &&
                      ` · Letzter Lauf: ${row.last_record_count}`}
                  </p>
                  {row.last_error && row.consecutive_failures > 0 && (
                    <p className="text-xs text-destructive truncate">
                      {row.last_error}
                    </p>
                  )}
                </div>
                <MirrorRowStatus row={row} />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
