/**
 * Restore Tests Panel
 *
 * Zeigt History und Status von automatischen Restore-Tests.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { RestoreTestHistory, RestoreTestResult } from '../api';

interface RestoreTestsPanelProps {
  history?: RestoreTestHistory;
  isLoading: boolean;
  onRunTest: () => void;
  isRunningTest: boolean;
}

const formatDate = (dateStr: string) => {
  try {
    return format(new Date(dateStr), 'dd.MM.yyyy HH:mm', { locale: de });
  } catch {
    return dateStr;
  }
};

const formatDuration = (seconds?: number) => {
  if (!seconds) return '-';
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
};

const getStatusBadge = (status: RestoreTestResult['status']) => {
  const statusConfig: Record<
    RestoreTestResult['status'],
    { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: any }
  > = {
    success: { label: 'Erfolgreich', variant: 'default', icon: CheckCircle2 },
    failed: { label: 'Fehlgeschlagen', variant: 'destructive', icon: XCircle },
    running: { label: 'Läuft', variant: 'secondary', icon: Clock },
    aborted: { label: 'Abgebrochen', variant: 'outline', icon: AlertTriangle },
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className="gap-1">
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
};

export function RestoreTestsPanel({
  history,
  isLoading,
  onRunTest,
  isRunningTest,
}: RestoreTestsPanelProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48 mb-2" />
          <Skeleton className="h-4 w-72" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const tests = history?.tests ?? [];
  const successRate = history?.success_rate ?? 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Automatische Restore-Tests</CardTitle>
            <CardDescription>
              Wöchentliche Tests zur Validierung der Backup-Wiederherstellung
            </CardDescription>
          </div>
          <Button onClick={onRunTest} disabled={isRunningTest}>
            <Play className="h-4 w-4 mr-2" />
            {isRunningTest ? 'Test läuft...' : 'Test starten'}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Statistics */}
        <div className="grid grid-cols-3 gap-4">
          <div className="p-3 rounded-lg bg-muted">
            <div className="text-sm text-muted-foreground mb-1">Erfolgsrate</div>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold">{(successRate * 100).toFixed(1)}%</span>
              {successRate >= 0.9 ? (
                <TrendingUp className="h-4 w-4 text-green-600" />
              ) : (
                <TrendingDown className="h-4 w-4 text-red-600" />
              )}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted">
            <div className="text-sm text-muted-foreground mb-1">Tests (90 Tage)</div>
            <div className="text-2xl font-bold">{history?.total_tests ?? 0}</div>
          </div>

          <div className="p-3 rounded-lg bg-muted">
            <div className="text-sm text-muted-foreground mb-1">Ø Dauer</div>
            <div className="text-2xl font-bold font-mono">
              {formatDuration(history?.average_duration_seconds)}
            </div>
          </div>
        </div>

        {/* Latest Test Alert */}
        {history?.latest_test && history.latest_test.status === 'failed' && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Letzter Test fehlgeschlagen</AlertTitle>
            <AlertDescription>
              Der letzte Restore-Test am {formatDate(history.latest_test.started_at)} ist
              fehlgeschlagen. Bitte prüfen Sie die Details.
            </AlertDescription>
          </Alert>
        )}

        {/* Test History Table */}
        {tests.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Clock className="h-12 w-12 mb-4 opacity-50" />
            <p>Noch keine Restore-Tests durchgeführt</p>
          </div>
        ) : (
          <div className="border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Datum</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Backup</TableHead>
                  <TableHead>Dauer</TableHead>
                  <TableHead>RTO</TableHead>
                  <TableHead>RPO</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tests.map((test) => (
                  <TableRow key={test.id}>
                    <TableCell className="font-mono text-sm">
                      {formatDate(test.started_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{test.test_type}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{test.backup_name}</TableCell>
                    <TableCell className="font-mono text-sm">
                      {formatDuration(test.duration_seconds)}
                    </TableCell>
                    <TableCell>
                      {test.rto_achieved ? (
                        <Badge variant="default" className="gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Erreicht
                        </Badge>
                      ) : (
                        <Badge variant="destructive" className="gap-1">
                          <XCircle className="h-3 w-3" />
                          Verfehlt
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {test.rpo_achieved ? (
                        <Badge variant="default" className="gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Erreicht
                        </Badge>
                      ) : (
                        <Badge variant="destructive" className="gap-1">
                          <XCircle className="h-3 w-3" />
                          Verfehlt
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>{getStatusBadge(test.status)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
