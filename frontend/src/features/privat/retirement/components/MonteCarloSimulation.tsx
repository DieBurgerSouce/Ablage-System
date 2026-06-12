/**
 * MonteCarloSimulation Component
 *
 * Interaktive Monte-Carlo-Simulation zur Analyse der Portfolio-Langlebigkeit
 * mit visueller Darstellung der Simulationspfade.
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Area, ComposedChart } from 'recharts';
import { Activity, AlertTriangle, CheckCircle2, ChevronRight, Play, Target, BarChart3 } from 'lucide-react';
import { useRunMonteCarlo } from '../hooks/useRetirementQueries';
import type { MonteCarloResult, RiskProfile } from '@/lib/api/services/retirement';

interface MonteCarloSimulationProps {
  spaceId: string;
  initialPortfolio?: number;
  annualWithdrawal?: number;
  onSimulationComplete?: (result: MonteCarloResult) => void;
}

// Formatierung
const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

const formatCurrencyCompact = (value: number): string => {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)} Mio. EUR`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(0)} Tsd. EUR`;
  }
  return formatCurrency(value);
};

// Risikoprofil-Labels
const riskProfileLabels: Record<RiskProfile, string> = {
  konservativ: 'Konservativ (4% Rendite, 6% Volatilität)',
  ausgewogen: 'Ausgewogen (6% Rendite, 12% Volatilität)',
  wachstum: 'Wachstum (8% Rendite, 18% Volatilität)',
};

export function MonteCarloSimulation({
  spaceId,
  initialPortfolio: defaultPortfolio = 500000,
  annualWithdrawal: defaultWithdrawal = 20000,
  onSimulationComplete,
}: MonteCarloSimulationProps) {
  // Form State
  const [portfolio, setPortfolio] = React.useState(defaultPortfolio);
  const [withdrawal, setWithdrawal] = React.useState(defaultWithdrawal);
  const [timeHorizon, setTimeHorizon] = React.useState(30);
  const [riskProfile, setRiskProfile] = React.useState<RiskProfile>('ausgewogen');
  const [iterations, setIterations] = React.useState(1000);

  // Result State
  const [result, setResult] = React.useState<MonteCarloResult | null>(null);

  // Mutation
  const simulationMutation = useRunMonteCarlo();

  // Entnahmerate berechnen
  const withdrawalRate = portfolio > 0 ? (withdrawal / portfolio) * 100 : 0;

  const handleSimulate = async () => {
    try {
      const data = await simulationMutation.mutateAsync({
        spaceId,
        request: {
          initialPortfolio: portfolio,
          annualWithdrawal: withdrawal,
          timeHorizonYears: timeHorizon,
          riskProfile,
          iterations,
          inflationAdjusted: true,
        },
      });
      setResult(data);
      onSimulationComplete?.(data);
    } catch (error) {
      // Error handling durch API-Client
    }
  };

  return (
    <div className="space-y-6">
      {/* Eingabe-Formular */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Monte-Carlo-Simulation
          </CardTitle>
          <CardDescription>
            Simulieren Sie 1.000 verschiedene Marktszenarien, um die Wahrscheinlichkeit
            zu berechnen, dass Ihr Portfolio bis zum Lebensende reicht.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            {/* Startportfolio */}
            <div className="space-y-2">
              <Label htmlFor="portfolio">Startportfolio</Label>
              <div className="relative">
                <Input
                  id="portfolio"
                  type="number"
                  value={portfolio}
                  onChange={(e) => setPortfolio(Number(e.target.value))}
                  className="pr-12"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                  EUR
                </span>
              </div>
            </div>

            {/* Jährliche Entnahme */}
            <div className="space-y-2">
              <Label htmlFor="withdrawal">Jährliche Entnahme</Label>
              <div className="relative">
                <Input
                  id="withdrawal"
                  type="number"
                  value={withdrawal}
                  onChange={(e) => setWithdrawal(Number(e.target.value))}
                  className="pr-12"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                  EUR
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                Entnahmerate: {withdrawalRate.toFixed(1)}% (empfohlen: 3-4%)
              </p>
            </div>

            {/* Zeithorizont */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label>Zeithorizont</Label>
                <span className="text-sm font-medium">{timeHorizon} Jahre</span>
              </div>
              <Slider
                value={[timeHorizon]}
                onValueChange={([value]) => setTimeHorizon(value)}
                min={10}
                max={50}
                step={5}
              />
            </div>

            {/* Risikoprofil */}
            <div className="space-y-2">
              <Label>Risikoprofil</Label>
              <Select value={riskProfile} onValueChange={(v) => setRiskProfile(v as RiskProfile)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="konservativ">Konservativ</SelectItem>
                  <SelectItem value="ausgewogen">Ausgewogen</SelectItem>
                  <SelectItem value="wachstum">Wachstum</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {riskProfileLabels[riskProfile]}
              </p>
            </div>
          </div>

          <Button
            onClick={handleSimulate}
            disabled={simulationMutation.isPending}
            className="w-full"
          >
            {simulationMutation.isPending ? (
              'Simulation läuft...'
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                {iterations.toLocaleString('de-DE')} Szenarien simulieren
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Loading */}
      {simulationMutation.isPending && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-center gap-3">
              <Activity className="h-6 w-6 animate-pulse text-primary" />
              <span>Simulation läuft... Bitte warten.</span>
            </div>
            <div className="mt-4 space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-64" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ergebnis */}
      {result && !simulationMutation.isPending && (
        <MonteCarloResultDisplay result={result} />
      )}

      {/* Fehler */}
      {simulationMutation.isError && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Simulationsfehler</AlertTitle>
          <AlertDescription>
            Die Monte-Carlo-Simulation konnte nicht durchgeführt werden.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

// ==================== Result Display ====================

interface MonteCarloResultDisplayProps {
  result: MonteCarloResult;
}

function MonteCarloResultDisplay({ result }: MonteCarloResultDisplayProps) {
  // Erfolgsrate-Farbe
  const successColor =
    result.successRate >= 95
      ? 'text-green-600'
      : result.successRate >= 80
        ? 'text-yellow-600'
        : 'text-red-600';

  const successBadgeVariant =
    result.successRate >= 95
      ? 'default'
      : result.successRate >= 80
        ? 'secondary'
        : 'destructive';

  // Chart-Daten vorbereiten
  const chartData = React.useMemo(() => {
    if (!result.portfolioPaths || result.portfolioPaths.length === 0) {
      return [];
    }

    // Berechne Perzentile pro Jahr
    const years = result.portfolioPaths[0]?.length ?? 0;
    const data = [];

    for (let year = 0; year < years; year++) {
      const values = result.portfolioPaths
        .map((path) => path[year] ?? 0)
        .filter((v) => v !== undefined)
        .sort((a, b) => a - b);

      const n = values.length;
      if (n === 0) continue;

      const p5 = values[Math.floor(n * 0.05)] ?? 0;
      const p25 = values[Math.floor(n * 0.25)] ?? 0;
      const median = values[Math.floor(n * 0.5)] ?? 0;
      const p75 = values[Math.floor(n * 0.75)] ?? 0;
      const p95 = values[Math.floor(n * 0.95)] ?? 0;

      data.push({
        year,
        p5,
        p25,
        median,
        p75,
        p95,
      });
    }

    return data;
  }, [result.portfolioPaths]);

  return (
    <div className="space-y-6">
      {/* Hauptergebnis */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              Simulationsergebnis
            </CardTitle>
            <Badge variant={successBadgeVariant}>
              {result.iterations.toLocaleString('de-DE')} Szenarien
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Erfolgsrate */}
          <div className="text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              {result.successRate >= 90 ? (
                <CheckCircle2 className="h-8 w-8 text-green-600" />
              ) : (
                <AlertTriangle className="h-8 w-8 text-yellow-600" />
              )}
              <span className={`text-5xl font-bold ${successColor}`}>
                {result.successRate.toFixed(1)}%
              </span>
            </div>
            <p className="text-muted-foreground">Erfolgswahrscheinlichkeit</p>
            <p className="text-sm text-muted-foreground mt-1">
              In {(result.successRate * result.iterations / 100).toFixed(0)} von{' '}
              {result.iterations.toLocaleString('de-DE')} Szenarien reicht das Portfolio
              über {result.timeHorizonYears} Jahre.
            </p>
          </div>

          {/* Statistiken */}
          <div className="grid gap-4 md:grid-cols-4">
            <div className="rounded-lg border p-4 text-center">
              <p className="text-sm text-muted-foreground">Startportfolio</p>
              <p className="text-lg font-bold">{formatCurrencyCompact(result.initialPortfolio)}</p>
            </div>
            <div className="rounded-lg border p-4 text-center">
              <p className="text-sm text-muted-foreground">Median Endwert</p>
              <p className="text-lg font-bold text-blue-600">
                {formatCurrencyCompact(result.medianEndPortfolio)}
              </p>
            </div>
            <div className="rounded-lg border p-4 text-center">
              <p className="text-sm text-muted-foreground">5%-Perzentil</p>
              <p className="text-lg font-bold text-red-600">
                {formatCurrencyCompact(result.percentile5)}
              </p>
              <p className="text-xs text-muted-foreground">Worst Case</p>
            </div>
            <div className="rounded-lg border p-4 text-center">
              <p className="text-sm text-muted-foreground">95%-Perzentil</p>
              <p className="text-lg font-bold text-green-600">
                {formatCurrencyCompact(result.percentile95)}
              </p>
              <p className="text-xs text-muted-foreground">Best Case</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Visualisierung */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Portfolio-Entwicklung (Konfidenzbänder)
          </CardTitle>
          <CardDescription>
            Zeigt die Bandbreite möglicher Portfolio-Entwicklungen. Das dunkle Band
            repräsentiert 50% der Szenarien (25.-75. Perzentil).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="year"
                  label={{ value: 'Jahre', position: 'insideBottomRight', offset: -10 }}
                />
                <YAxis
                  tickFormatter={(v) => formatCurrencyCompact(v)}
                  label={{
                    value: 'Portfolio',
                    angle: -90,
                    position: 'insideLeft',
                  }}
                />
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  labelFormatter={(label) => `Jahr ${label}`}
                />
                <ReferenceLine y={0} stroke="red" strokeDasharray="3 3" />

                {/* 5-95 Perzentil Band */}
                <Area
                  dataKey="p95"
                  stroke="none"
                  fill="#22c55e"
                  fillOpacity={0.1}
                  name="95%-Perzentil"
                />
                <Area
                  dataKey="p5"
                  stroke="none"
                  fill="#ffffff"
                  name="5%-Perzentil"
                />

                {/* 25-75 Perzentil Band */}
                <Area
                  dataKey="p75"
                  stroke="none"
                  fill="#3b82f6"
                  fillOpacity={0.2}
                  name="75%-Perzentil"
                />
                <Area
                  dataKey="p25"
                  stroke="none"
                  fill="#ffffff"
                  name="25%-Perzentil"
                />

                {/* Median Linie */}
                <Line
                  type="monotone"
                  dataKey="median"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                  name="Median"
                />

                {/* Perzentil-Linien */}
                <Line
                  type="monotone"
                  dataKey="p5"
                  stroke="#ef4444"
                  strokeWidth={1}
                  strokeDasharray="5 5"
                  dot={false}
                  name="5%-Perzentil"
                />
                <Line
                  type="monotone"
                  dataKey="p95"
                  stroke="#22c55e"
                  strokeWidth={1}
                  strokeDasharray="5 5"
                  dot={false}
                  name="95%-Perzentil"
                />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-muted-foreground">
              Keine Visualisierungsdaten verfügbar
            </div>
          )}
        </CardContent>
      </Card>

      {/* Empfehlungen */}
      {result.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Empfehlungen</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {result.recommendations.map((rec, index) => (
                <li key={index} className="flex items-start gap-2 text-sm">
                  <ChevronRight className="h-4 w-4 mt-0.5 text-primary shrink-0" />
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default MonteCarloSimulation;
