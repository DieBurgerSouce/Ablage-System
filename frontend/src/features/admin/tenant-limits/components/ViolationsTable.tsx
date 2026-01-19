/**
 * Violations Table Component
 *
 * Zeigt die Rate-Limit-Verletzungen als Tabelle.
 */

import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { AlertTriangle, Shield } from 'lucide-react';
import type { ViolationResponse } from '../hooks/use-tenant-limits';

interface ViolationsTableProps {
  violations: ViolationResponse[];
  isLoading?: boolean;
}

const LIMIT_TYPE_LABELS: Record<string, string> = {
  minute: 'Minuten-Limit',
  hour: 'Stunden-Limit',
  day: 'Tages-Limit',
  burst: 'Burst-Limit',
};

const LIMIT_TYPE_COLORS: Record<string, string> = {
  minute: 'bg-blue-500',
  hour: 'bg-amber-500',
  day: 'bg-purple-500',
  burst: 'bg-red-500',
};

export function ViolationsTable({ violations, isLoading }: ViolationsTableProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Rate-Limit-Verletzungen
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-32 text-muted-foreground">
            Lade Verletzungen...
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Rate-Limit-Verletzungen
        </CardTitle>
        <CardDescription>
          {violations.length === 0
            ? 'Keine Verletzungen in den letzten 24 Stunden'
            : `${violations.length} Verletzung${violations.length === 1 ? '' : 'en'} gefunden`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {violations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
            <Shield className="h-12 w-12 mb-4 text-green-500" />
            <p className="text-lg font-medium">Alles in Ordnung!</p>
            <p className="text-sm">Keine Rate-Limit-Verletzungen im ausgewaehlten Zeitraum.</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Zeitpunkt</TableHead>
                <TableHead>Endpoint</TableHead>
                <TableHead>Methode</TableHead>
                <TableHead>Limit-Typ</TableHead>
                <TableHead className="text-right">Limit</TableHead>
                <TableHead className="text-right">Aktuell</TableHead>
                <TableHead>IP-Adresse</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {violations.map((violation) => (
                <TableRow key={violation.id}>
                  <TableCell className="whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                      <span title={new Date(violation.occurred_at).toLocaleString('de-DE')}>
                        {formatDistanceToNow(new Date(violation.occurred_at), {
                          addSuffix: true,
                          locale: de,
                        })}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-xs max-w-[200px] truncate">
                    {violation.endpoint}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{violation.method}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge className={LIMIT_TYPE_COLORS[violation.limit_type] || 'bg-gray-500'}>
                      {LIMIT_TYPE_LABELS[violation.limit_type] || violation.limit_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {violation.limit_value}
                  </TableCell>
                  <TableCell className="text-right font-mono text-destructive font-medium">
                    {violation.current_count}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {violation.ip_address}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
