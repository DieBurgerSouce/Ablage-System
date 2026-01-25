/**
 * Missed Skonto Dashboard
 * Hauptseite fuer verpasste Skonto-Uebersicht
 */

import { useState, useMemo } from 'react';
import { Download, Calendar, Filter } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { useMissedSkonto, useSkontoStatistics, useMonthlySkontoSummary, useExportMissedSkonto } from '../hooks';
import { MissedSkontoStats } from './MissedSkontoStats';
import { MissedSkontoTable } from './MissedSkontoTable';
import { MissedSkontoChart } from './MissedSkontoChart';
import type { StatsPeriod } from '../types';

// Hilfsfunktionen fuer Datumsbereiche
function getDateRange(period: StatsPeriod): { startDate: string; endDate: string } {
  const now = new Date();
  const endDate = now.toISOString().slice(0, 10);

  let startDate: string;
  switch (period) {
    case 'month':
      startDate = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
      break;
    case 'quarter':
      const quarterStart = Math.floor(now.getMonth() / 3) * 3;
      startDate = new Date(now.getFullYear(), quarterStart, 1).toISOString().slice(0, 10);
      break;
    case 'year':
      startDate = new Date(now.getFullYear(), 0, 1).toISOString().slice(0, 10);
      break;
    default:
      startDate = new Date(now.getFullYear(), 0, 1).toISOString().slice(0, 10);
  }

  return { startDate, endDate };
}

export function MissedSkontoDashboard() {
  const [period, setPeriod] = useState<StatsPeriod>('year');
  const [page, setPage] = useState(1);
  const perPage = 20;

  const { startDate, endDate } = useMemo(() => getDateRange(period), [period]);

  // Queries
  const {
    data: missedData,
    isLoading: isLoadingMissed,
  } = useMissedSkonto({
    startDate,
    endDate,
    page,
    perPage,
  });

  const {
    data: statistics,
    isLoading: isLoadingStats,
  } = useSkontoStatistics(startDate, endDate);

  const {
    data: monthlyData,
    isLoading: isLoadingMonthly,
  } = useMonthlySkontoSummary(12);

  const exportMutation = useExportMissedSkonto();

  const handleExport = (format: 'xlsx' | 'csv') => {
    exportMutation.mutate({
      format,
      filters: { startDate, endDate },
    });
  };

  const handlePeriodChange = (value: string) => {
    setPeriod(value as StatsPeriod);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Verpasste Skonto-Moeglichkeiten</h1>
          <p className="text-muted-foreground">
            Analyse verpasster Fruehzahlerrabatte und Optimierungspotenzial.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleExport('xlsx')}
            disabled={exportMutation.isPending}
          >
            <Download className="mr-2 h-4 w-4" />
            Excel
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleExport('csv')}
            disabled={exportMutation.isPending}
          >
            <Download className="mr-2 h-4 w-4" />
            CSV
          </Button>
        </div>
      </div>

      {/* Alert bei hohem Verlust */}
      {statistics && statistics.missedSavings > 1000 && (
        <Alert variant="destructive">
          <Calendar className="h-4 w-4" />
          <AlertTitle>Hohe verpasste Ersparnis</AlertTitle>
          <AlertDescription>
            Im ausgewaehlten Zeitraum wurden{' '}
            {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
              statistics.missedSavings
            )}{' '}
            an Skonto-Ersparnissen verpasst. Pruefen Sie die Zahlungsprozesse.
          </AlertDescription>
        </Alert>
      )}

      {/* Filter */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Zeitraum
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            <div className="space-y-2">
              <Label htmlFor="period">Zeitraum</Label>
              <Select value={period} onValueChange={handlePeriodChange}>
                <SelectTrigger id="period" className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="month">Aktueller Monat</SelectItem>
                  <SelectItem value="quarter">Aktuelles Quartal</SelectItem>
                  <SelectItem value="year">Aktuelles Jahr</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <p className="text-sm text-muted-foreground">
                {new Date(startDate).toLocaleDateString('de-DE')} -{' '}
                {new Date(endDate).toLocaleDateString('de-DE')}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Statistics Cards */}
      <MissedSkontoStats statistics={statistics} isLoading={isLoadingStats} />

      {/* Chart */}
      <MissedSkontoChart data={monthlyData} isLoading={isLoadingMonthly} />

      <Separator />

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle>Verpasste Skonto-Rechnungen</CardTitle>
          <CardDescription>
            Liste aller Rechnungen, bei denen die Skonto-Frist nicht genutzt wurde.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MissedSkontoTable
            items={missedData?.items}
            isLoading={isLoadingMissed}
            total={missedData?.total}
            page={page}
            perPage={perPage}
            onPageChange={setPage}
          />
        </CardContent>
      </Card>

      {/* Summary Footer */}
      {missedData && missedData.totalMissedAmount > 0 && (
        <Card className="bg-muted/50">
          <CardContent className="pt-6">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <p className="text-sm text-muted-foreground">
                Gesamte verpasste Ersparnis im Zeitraum:
              </p>
              <p className="text-2xl font-bold text-red-600">
                {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
                  missedData.totalMissedAmount
                )}
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
