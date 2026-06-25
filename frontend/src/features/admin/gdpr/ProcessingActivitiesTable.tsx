/**
 * Art.30 Verarbeitungsverzeichnis - Tabelle
 *
 * Zeigt das Verzeichnis von Verarbeitungstaetigkeiten (Art. 30 DSGVO) fuer
 * Administratoren. Subject-IDs sind pseudonymisiert (Art. 4(5) DSGVO).
 */

import { useState } from 'react';
import { AlertCircle, ShieldCheck } from 'lucide-react';
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
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useProcessingActivities,
  type ProcessingActivityEntry,
} from './gdpr-processing-api';

const PAGE_SIZE = 50;

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function ActivityRow({ activity }: { activity: ProcessingActivityEntry }) {
  return (
    <TableRow>
      <TableCell className="font-medium">{activity.purpose}</TableCell>
      <TableCell>{activity.legal_basis}</TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {activity.data_categories.length > 0 ? (
            activity.data_categories.map((cat) => (
              <Badge key={cat} variant="secondary" className="text-xs">
                {cat}
              </Badge>
            ))
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </div>
      </TableCell>
      <TableCell className="whitespace-nowrap">
        {activity.retention_period_days} Tage
        {activity.retention_expires_at && (
          <span className="block text-xs text-muted-foreground">
            bis {formatDate(activity.retention_expires_at)}
          </span>
        )}
      </TableCell>
      <TableCell>{activity.processing_backend ?? '—'}</TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {activity.subject_id ?? '—'}
      </TableCell>
      <TableCell className="whitespace-nowrap">
        {formatDate(activity.created_at)}
      </TableCell>
    </TableRow>
  );
}

export function ProcessingActivitiesTable() {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error } = useProcessingActivities({
    limit: PAGE_SIZE,
    offset,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary" />
          Verarbeitungstätigkeiten
        </CardTitle>
        <CardDescription>
          {data
            ? `${data.total.toLocaleString('de-DE')} Einträge — abgedeckte DSGVO-Artikel: ${
                data.gdpr_articles_covered.join(', ') || '—'
              }`
            : 'Verzeichnis gemäß Art. 30 DSGVO'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>
              Fehler beim Laden des Verarbeitungsverzeichnisses. Möglicherweise
              fehlen Administrator-Rechte.
            </span>
          </div>
        ) : isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : !data || data.activities.length === 0 ? (
          <div className="py-12 text-center text-muted-foreground">
            Keine Verarbeitungstätigkeiten erfasst.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Zweck</TableHead>
                    <TableHead>Rechtsgrundlage</TableHead>
                    <TableHead>Datenkategorien</TableHead>
                    <TableHead>Aufbewahrung</TableHead>
                    <TableHead>Backend</TableHead>
                    <TableHead>Subject-ID (pseudonym)</TableHead>
                    <TableHead>Erstellt</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.activities.map((a) => (
                    <ActivityRow key={a.id} activity={a} />
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} von{' '}
                {data.total.toLocaleString('de-DE')}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Zurück
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + PAGE_SIZE >= data.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Weiter
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
