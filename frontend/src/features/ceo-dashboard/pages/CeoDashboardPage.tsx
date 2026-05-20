/**
 * CEO Dashboard Page
 *
 * Executive dashboard showing company health, KPIs, trends, and anomalies.
 */

import { useState } from 'react';
import { HealthScoreGauge } from '../components/HealthScoreGauge';
import { KPICards } from '../components/KPICards';
import { TrendSparklines } from '../components/TrendSparklines';
import { AnomalyAlerts } from '../components/AnomalyAlerts';
import {
  useCeoOverview,
  useCeoTrends,
  useCeoAnomalies,
} from '../hooks/use-ceo-dashboard-queries';
import { Card, CardContent } from '@/components/ui/card';
import { Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function CeoDashboardPage() {
  const [trendDays, setTrendDays] = useState(30);

  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useCeoOverview();

  const {
    data: trends,
    isLoading: trendsLoading,
    error: trendsError,
  } = useCeoTrends(trendDays);

  const {
    data: anomalies,
    isLoading: anomaliesLoading,
    error: anomaliesError,
  } = useCeoAnomalies();

  // Error state
  if (overviewError || trendsError || anomaliesError) {
    return (
      <div className="container mx-auto p-6">
        <Card>
          <CardContent className="p-6">
            <div className="text-center text-red-600 dark:text-red-400">
              Fehler beim Laden des Dashboards.{' '}
              <Button
                variant="link"
                onClick={() => refetchOverview()}
                className="text-red-600 dark:text-red-400"
              >
                Erneut versuchen
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Loading state
  if (overviewLoading || !overview) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          <span className="ml-3 text-muted-foreground">
            Dashboard wird geladen...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Unternehmens-Dashboard
          </h1>
          <p className="text-muted-foreground mt-1">
            Ihr digitaler Zwilling auf einen Blick
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetchOverview()}
          className="gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Aktualisieren
        </Button>
      </div>

      {/* Health Score and KPIs Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Health Score Gauge */}
        <div className="lg:col-span-1">
          <HealthScoreGauge healthScore={overview.healthScore} />
        </div>

        {/* KPI Cards */}
        <div className="lg:col-span-2">
          <KPICards overview={overview} />
        </div>
      </div>

      {/* Trend Sparklines */}
      {trendsLoading || !trends ? (
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              <span className="ml-3 text-muted-foreground">
                Trends werden geladen...
              </span>
            </div>
          </CardContent>
        </Card>
      ) : (
        <TrendSparklines
          trendData={trends}
          days={trendDays}
          onDaysChange={setTrendDays}
        />
      )}

      {/* Anomaly Alerts */}
      {anomaliesLoading ? (
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              <span className="ml-3 text-muted-foreground">
                Anomalien werden geladen...
              </span>
            </div>
          </CardContent>
        </Card>
      ) : anomalies && anomalies.length > 0 ? (
        <AnomalyAlerts anomalies={anomalies} />
      ) : null}

      {/* Last Updated Footer */}
      <div className="text-xs text-muted-foreground text-center pt-4 border-t border-border">
        Letzte Aktualisierung:{' '}
        {overview.generatedAt.toLocaleString('de-DE', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        })}
      </div>
    </div>
  );
}
