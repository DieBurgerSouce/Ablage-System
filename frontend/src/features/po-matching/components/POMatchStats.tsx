/**
 * POMatchStats - Statistik-Dashboard fuer PO-Matching
 *
 * Zeigt:
 * - 4 KPI-Karten: Gesamte Matches, Erfolgsquote, Offene Abweichungen, Auto-Match Quote
 * - Status-Verteilung mit farbigen Badges
 * - Datumsbereich-Auswahl
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Loader2,
  BarChart3,
  CheckCircle2,
  AlertTriangle,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePOMatchStats } from '../hooks/usePOMatching';

// ==================== Helpers ====================

function getDefaultDateRange(): { start: string; end: string } {
  const now = new Date();
  const end = now.toISOString().split('T')[0];
  const start = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
    .toISOString()
    .split('T')[0];
  return { start, end };
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

// ==================== Status-Verteilung ====================

interface StatusItem {
  label: string;
  count: number;
  className: string;
}

// ==================== Component ====================

export function POMatchStats() {
  const defaults = useMemo(() => getDefaultDateRange(), []);
  const [periodStart, setPeriodStart] = useState(defaults.start);
  const [periodEnd, setPeriodEnd] = useState(defaults.end);

  const { data: stats, isLoading, refetch } = usePOMatchStats(
    periodStart,
    periodEnd
  );

  const successRate =
    stats && stats.total_matches > 0
      ? (stats.full_matches / stats.total_matches) * 100
      : 0;

  const autoMatchRate =
    stats && stats.total_matches > 0
      ? (stats.auto_matched_count / stats.total_matches) * 100
      : 0;

  const statusDistribution: StatusItem[] = stats
    ? [
        {
          label: 'Ausstehend',
          count: stats.pending_matches,
          className: 'bg-gray-100 text-gray-800 border-gray-200',
        },
        {
          label: 'Teilweise',
          count: stats.partial_matches,
          className: 'bg-yellow-100 text-yellow-800 border-yellow-200',
        },
        {
          label: 'Vollstaendig',
          count: stats.full_matches,
          className: 'bg-green-100 text-green-800 border-green-200',
        },
        {
          label: 'Abweichung',
          count: stats.discrepancy_matches,
          className: 'bg-red-100 text-red-800 border-red-200',
        },
        {
          label: 'Freigegeben',
          count: stats.approved_matches,
          className: 'bg-green-600 text-white border-green-700',
        },
        {
          label: 'Abgelehnt',
          count: stats.rejected_matches,
          className: 'bg-destructive text-destructive-foreground',
        },
      ]
    : [];

  return (
    <div className="space-y-6">
      {/* Datumsbereich */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="period-start">Von</Label>
              <Input
                id="period-start"
                type="date"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                className="w-44"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="period-end">Bis</Label>
              <Input
                id="period-end"
                type="date"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                className="w-44"
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isLoading}
            >
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Aktualisieren
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* KPI Karten */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : stats ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Gesamte Matches */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Gesamte Matches
                </CardTitle>
                <BarChart3 className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold tabular-nums">
                  {stats.total_matches}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Durchschn. Score: {formatPercent(stats.avg_match_score)}
                </p>
              </CardContent>
            </Card>

            {/* Erfolgsquote */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Erfolgsquote
                </CardTitle>
                <CheckCircle2 className="h-4 w-4 text-green-600" />
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold tabular-nums">
                  {formatPercent(successRate)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {stats.full_matches} von {stats.total_matches} vollstaendig
                </p>
              </CardContent>
            </Card>

            {/* Offene Abweichungen */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Offene Abweichungen
                </CardTitle>
                <AlertTriangle className="h-4 w-4 text-yellow-600" />
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold tabular-nums">
                  {stats.unresolved_discrepancies}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  von {stats.total_discrepancies} gesamt
                  {stats.avg_amount_deviation_percent > 0 && (
                    <span>
                      {' '}
                      (durchschn. {formatPercent(stats.avg_amount_deviation_percent)}{' '}
                      Abweichung)
                    </span>
                  )}
                </p>
              </CardContent>
            </Card>

            {/* Auto-Match Quote */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Auto-Match Quote
                </CardTitle>
                <Zap className="h-4 w-4 text-blue-600" />
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold tabular-nums">
                  {formatPercent(autoMatchRate)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {stats.auto_matched_count} automatisch zugeordnet
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Status-Verteilung */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Status-Verteilung</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-3">
                {statusDistribution.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center gap-2"
                  >
                    <Badge
                      variant="outline"
                      className={cn('text-xs', item.className)}
                    >
                      {item.label}
                    </Badge>
                    <span className="text-sm font-medium tabular-nums">
                      {item.count}
                    </span>
                  </div>
                ))}
              </div>

              {/* Einfache Balkenanzeige */}
              {stats.total_matches > 0 && (
                <div className="mt-4 flex h-3 w-full rounded-full overflow-hidden bg-muted">
                  {stats.full_matches > 0 && (
                    <div
                      className="bg-green-500 transition-all"
                      style={{
                        width: `${(stats.full_matches / stats.total_matches) * 100}%`,
                      }}
                      title={`Vollstaendig: ${stats.full_matches}`}
                    />
                  )}
                  {stats.approved_matches > 0 && (
                    <div
                      className="bg-green-700 transition-all"
                      style={{
                        width: `${(stats.approved_matches / stats.total_matches) * 100}%`,
                      }}
                      title={`Freigegeben: ${stats.approved_matches}`}
                    />
                  )}
                  {stats.partial_matches > 0 && (
                    <div
                      className="bg-yellow-500 transition-all"
                      style={{
                        width: `${(stats.partial_matches / stats.total_matches) * 100}%`,
                      }}
                      title={`Teilweise: ${stats.partial_matches}`}
                    />
                  )}
                  {stats.pending_matches > 0 && (
                    <div
                      className="bg-gray-400 transition-all"
                      style={{
                        width: `${(stats.pending_matches / stats.total_matches) * 100}%`,
                      }}
                      title={`Ausstehend: ${stats.pending_matches}`}
                    />
                  )}
                  {stats.discrepancy_matches > 0 && (
                    <div
                      className="bg-red-500 transition-all"
                      style={{
                        width: `${(stats.discrepancy_matches / stats.total_matches) * 100}%`,
                      }}
                      title={`Abweichung: ${stats.discrepancy_matches}`}
                    />
                  )}
                  {stats.rejected_matches > 0 && (
                    <div
                      className="bg-red-800 transition-all"
                      style={{
                        width: `${(stats.rejected_matches / stats.total_matches) * 100}%`,
                      }}
                      title={`Abgelehnt: ${stats.rejected_matches}`}
                    />
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <p>Keine Statistiken verfuegbar.</p>
          <p className="text-sm mt-1">
            Bitte waehlen Sie einen Zeitraum und klicken Sie auf Aktualisieren.
          </p>
        </div>
      )}
    </div>
  );
}
