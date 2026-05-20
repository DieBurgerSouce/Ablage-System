/**
 * DSO Tracker Widget
 *
 * Dashboard-Widget für Forderungslaufzeit (Days Sales Outstanding).
 *
 * Features:
 * - Aktueller DSO-Wert mit Trend-Pfeil
 * - Mini-Sparkline (Recharts LineChart)
 * - Branchen-Benchmark Vergleich
 * - Bewertung (gut / mittel / schlecht)
 * - Deutsche Beschriftung
 *
 * Phase C: Business KPIs
 */

import { useMemo } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  LineChart,
  Line,
  ResponsiveContainer,
  YAxis,
} from 'recharts';
import {
  Clock3,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';
import { useTheme } from '@/lib/theme/ThemeContext';
import { useDSOTracker } from '../../hooks/useDSOTracker';

/**
 * Bewertungs-Konfiguration
 */
const RATING_CONFIG = {
  gut: {
    label: 'Gut',
    color: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
    border: 'border-green-200 dark:border-green-800',
    bg: 'bg-green-50 dark:bg-green-950/20',
  },
  mittel: {
    label: 'Mittel',
    color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
    border: 'border-yellow-200 dark:border-yellow-800',
    bg: 'bg-yellow-50 dark:bg-yellow-950/20',
  },
  schlecht: {
    label: 'Schlecht',
    color: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    border: 'border-red-200 dark:border-red-800',
    bg: 'bg-red-50 dark:bg-red-950/20',
  },
} as const;

function useSparklineColor() {
  const { displayMode } = useTheme();

  return useMemo(() => {
    const computedStyle = getComputedStyle(document.documentElement);
    const value = computedStyle.getPropertyValue('--chart-1').trim();
    return value || 'oklch(0.55 0.18 250)';
  }, [displayMode]);
}

export function DSOTrackerWidget() {
  const sparklineColor = useSparklineColor();

  useWidgetSubscription('dso-tracker', {
    debounceMs: 500,
    autoInvalidate: true,
    queryKeysToInvalidate: [['dashboard-widgets', 'dso-tracker']],
  });

  const { data, isLoading, isError, error, refetch } = useDSOTracker();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full mb-3" />
          <Skeleton className="h-[80px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock3 className="w-5 h-5" />
            Forderungslaufzeit (DSO)
          </CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der DSO-Daten
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between">
              <span>{error?.message || 'Verbindung fehlgeschlagen'}</span>
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4 mr-1" />
                Wiederholen
              </Button>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const ratingConfig = RATING_CONFIG[data.rating];
  const dsoDiff = data.currentDSO - data.previousDSO;
  const dsoImproved = dsoDiff < 0; // Lower DSO is better
  const dsoUnchanged = dsoDiff === 0;
  const vsBenchmark = data.currentDSO - data.industryBenchmark;

  // Sparkline-Daten
  const sparkData = data.trend.map((t) => ({ dso: t.dso }));

  return (
    <ErrorBoundary
      fallback={<DashboardSectionError section="Forderungslaufzeit" />}
      errorTitle="DSO Fehler"
      errorDescription="Die Forderungslaufzeit konnte nicht geladen werden."
    >
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Clock3 className="w-5 h-5" />
                Forderungslaufzeit (DSO)
              </CardTitle>
              <CardDescription>
                Days Sales Outstanding
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge className={ratingConfig.color}>
                {ratingConfig.label}
              </Badge>
              <Button variant="ghost" size="icon" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* Haupt-KPI */}
          <div className={`p-4 rounded-lg border ${ratingConfig.border} ${ratingConfig.bg} mb-4`}>
            <div className="flex items-end justify-between">
              <div>
                <p className="text-xs text-muted-foreground mb-1">Aktueller DSO</p>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold">
                    {data.currentDSO.toFixed(0)}
                  </span>
                  <span className="text-sm text-muted-foreground">Tage</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {dsoUnchanged ? (
                  <Minus className="w-4 h-4 text-muted-foreground" />
                ) : dsoImproved ? (
                  <TrendingDown className="w-4 h-4 text-green-600" />
                ) : (
                  <TrendingUp className="w-4 h-4 text-red-600" />
                )}
                <span className={`text-sm font-medium ${
                  dsoUnchanged ? 'text-muted-foreground' : dsoImproved ? 'text-green-600' : 'text-red-600'
                }`}>
                  {dsoUnchanged ? '0' : `${dsoDiff > 0 ? '+' : ''}${dsoDiff.toFixed(0)}`} Tage
                </span>
              </div>
            </div>
          </div>

          {/* Benchmark-Vergleich */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="p-3 rounded-lg border bg-muted/30">
              <p className="text-xs text-muted-foreground mb-1">Vorperiode</p>
              <p className="text-base font-semibold">{data.previousDSO.toFixed(0)} Tage</p>
            </div>
            <div className="p-3 rounded-lg border bg-muted/30">
              <p className="text-xs text-muted-foreground mb-1">Branchen-Benchmark</p>
              <p className="text-base font-semibold">
                {data.industryBenchmark.toFixed(0)} Tage
                <span className={`text-xs ml-1 ${vsBenchmark <= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  ({vsBenchmark > 0 ? '+' : ''}{vsBenchmark.toFixed(0)})
                </span>
              </p>
            </div>
          </div>

          {/* Sparkline */}
          {sparkData.length > 1 && (
            <div className="h-[80px]" role="img" aria-label="DSO Trendverlauf">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sparkData}>
                  <YAxis hide domain={['dataMin - 5', 'dataMax + 5']} />
                  <Line
                    type="monotone"
                    dataKey="dso"
                    stroke={sparklineColor}
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </ErrorBoundary>
  );
}
