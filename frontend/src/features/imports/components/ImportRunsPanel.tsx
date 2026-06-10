/**
 * ImportRunsPanel (F2 — Pilot-Vertrauens-Loop)
 *
 * Live-Status der letzten Import-Läufe (gruppiert nach batch_id). Gibt dem
 * Nutzer den sichtbaren Beweis, dass ein Import wirklich arbeitet:
 * "Lauf 14:32 — 12 E-Mails, 10 OK, 2 Fehler". Pollt automatisch (Hook),
 * solange ein Lauf aktiv ist.
 */

import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  CheckCircle2,
  XCircle,
  SkipForward,
  Loader2,
  Inbox,
  AlertCircle,
} from 'lucide-react';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useImportRuns } from '../hooks/use-import-queries';
import type { ImportRun } from '../types/import-types';

interface ImportRunsPanelProps {
  /** Filtert auf eine Quellart; ohne Angabe werden alle Läufe gezeigt. */
  sourceType?: 'email' | 'folder';
  /** Anzahl der letzten Läufe (Default 10). */
  limit?: number;
}

function formatStarted(iso: string): string {
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: de });
  } catch {
    return iso;
  }
}

function RunRow({ run }: { run: ImportRun }) {
  return (
    <div
      className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between"
      data-testid="import-run-row"
    >
      <div className="flex items-center gap-3">
        {run.isRunning ? (
          <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
        ) : run.failed > 0 ? (
          <AlertCircle className="h-5 w-5 shrink-0 text-amber-500" />
        ) : (
          <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
        )}
        <div>
          <p className="font-medium">
            {run.total} {run.sourceType === 'email' ? 'E-Mails' : 'Dateien'}
            {run.isRunning && (
              <span className="ml-2 text-sm text-muted-foreground">
                wird verarbeitet…
              </span>
            )}
          </p>
          <p className="text-sm text-muted-foreground">
            {formatStarted(run.startedAt)}
            {run.documentsCreated > 0 && (
              <> · {run.documentsCreated} Dokumente abgelegt</>
            )}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {run.completed > 0 && (
          <Badge
            variant="outline"
            className="gap-1 border-green-200 text-green-700"
          >
            <CheckCircle2 className="h-3 w-3" />
            {run.completed} OK
          </Badge>
        )}
        {run.failed > 0 && (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="h-3 w-3" />
            {run.failed} Fehler
          </Badge>
        )}
        {run.skipped > 0 && (
          <Badge variant="secondary" className="gap-1">
            <SkipForward className="h-3 w-3" />
            {run.skipped} übersprungen
          </Badge>
        )}
        {run.pending > 0 && (
          <Badge variant="outline" className="gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            {run.pending} offen
          </Badge>
        )}
      </div>
    </div>
  );
}

export function ImportRunsPanel({ sourceType, limit = 10 }: ImportRunsPanelProps) {
  const { data: runs, isLoading, isError } = useImportRuns(sourceType, { limit });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Letzte Import-Läufe</CardTitle>
        <CardDescription>
          Status der zuletzt ausgeführten Importe. Läuft gerade etwas, aktualisiert
          sich die Anzeige automatisch.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && (
          <>
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </>
        )}

        {isError && (
          <p className="text-sm text-destructive">
            Import-Läufe konnten nicht geladen werden.
          </p>
        )}

        {!isLoading && !isError && (!runs || runs.length === 0) && (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
            <Inbox className="h-8 w-8" />
            <p>Noch keine Import-Läufe.</p>
            <p className="text-sm">
              Starten Sie einen Import, um den Live-Status hier zu sehen.
            </p>
          </div>
        )}

        {!isLoading &&
          !isError &&
          runs &&
          runs.map((run) => <RunRow key={run.batchId} run={run} />)}
      </CardContent>
    </Card>
  );
}

export default ImportRunsPanel;
